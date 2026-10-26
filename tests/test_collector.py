from __future__ import annotations

import copy
import json
from datetime import timedelta

import pytest

from openai_academy_api.collector import (
    OUTPUT_PATH,
    RECEIPTS_PATH,
    Collector,
    CollectorError,
    make_plan,
    session_request,
)
from openai_academy_api.edge import PurgeError
from openai_academy_api.storage import SnapshotStore


class Backend:
    def __init__(self, plan, artifact):
        self.plan, self.artifact = plan, copy.deepcopy(artifact)
        self.creates = 0
        self.keys = []
        self.turn_status = None
        self.fail_submit = False
        self.fail_create = False
        self.inspect_failure = False
        self.cancelled = False
        self.deleted = False
        self.delete_busy = False
        self.remote_error = None
        self.inspections = 0
        timestamp = plan.started_at + timedelta(milliseconds=1)
        self.artifact["generatedAt"] = (timestamp + timedelta(seconds=1)).isoformat()
        for resource in self.artifact["resources"]:
            resource["provenance"]["fetchedAt"] = timestamp.isoformat()
        urls = ["https://academy.openai.com/robots.txt"] + [r["url"] for r in artifact["resources"]]
        self.receipts = {
            "runId": plan.run_id,
            "robotsChecked": True,
            "requests": [
                {
                    "url": url,
                    "status": 200,
                    "bytes": 100,
                    "sha256": "a" * 64,
                    "checkedAt": timestamp.isoformat(),
                }
                for url in urls
            ],
        }

    def create(self, request):
        self.creates += 1
        if self.fail_create:
            raise ConnectionError("lost create response")
        return {"id": "sess_fixture"}

    def submit(self, session_id, key):
        self.keys.append(key)
        self.turn_status = "completed"
        if self.fail_submit:
            raise ConnectionError("accepted but disconnected")

    def inspect(self, session_id):
        self.inspections += 1
        if self.inspect_failure:
            raise ConnectionError("lost connection")
        session = {
            "status": "idle",
            "required_actions": [],
            "metadata": {"collector_run_id": self.plan.run_id},
        }
        turns = (
            [
                {
                    "id": "turn_fixture",
                    "status": self.turn_status,
                    "subagent_id": None,
                    "error": self.remote_error,
                }
            ]
            if self.turn_status
            else []
        )
        return session, turns

    def ready(self, session):
        return {"state": "connected", "environmentId": "env_fixture"}

    def cancel(self, session_id):
        self.cancelled = True
        self.turn_status = "cancelled"

    def delete(self, session_id):
        if self.delete_busy:
            raise RuntimeError("busy")
        self.deleted = True
        return True

    def download(self, session_id, turn_id, path, destination):
        assert session_id == "sess_fixture" and turn_id == "turn_fixture"
        if path == "/workspace/outputs/preflight.json":
            destination.write_text(
                json.dumps(
                    {
                        "robotsChecked": True,
                        "proxyPresent": {
                            name: False
                            for name in (
                                "HTTP_PROXY",
                                "HTTPS_PROXY",
                                "ALL_PROXY",
                                "http_proxy",
                                "https_proxy",
                                "all_proxy",
                            )
                        },
                    }
                )
            )
            return
        data = self.artifact if path == OUTPUT_PATH else self.receipts
        assert path in (OUTPUT_PATH, RECEIPTS_PATH)
        destination.write_text(json.dumps(data))


def test_request_uses_managed_hosted_codex_with_exact_allowlist():
    plan = make_plan(seed_urls=["https://academy.openai.com/public/content"])
    request = session_request(plan, "Use the mounted collection plan and contract.")
    assert request["agent"]["model"] == "gpt-6.1-sol"
    assert request["agent"]["reasoning"] == {"effort": "max"}
    assert request["environment"]["type"] == "openai_hosted"
    assert request["environment"]["container_size"] == "small"
    assert request["environment"]["network"] == {
        "access": "restricted",
        "allowed_domains": ["academy.openai.com"],
    }
    assert request["agent"]["tools"] == []
    assert "input" not in request  # Save the session ID before starting inference.
    assert not request["environment"].get("env")
    with pytest.raises(ValueError):
        make_plan(seed_urls=["https://localhost/secret"])


def test_completed_turn_publishes_validated_artifact(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    result = collector.start(plan, session_request(plan, "Mounted instructions."))
    assert result["state"] == "published"
    assert result["remoteMayBeRunning"] is False
    assert result["cleanup"]["state"] == "complete"
    assert backend.deleted
    assert backend.creates == len(backend.keys) == 1
    assert len(SnapshotStore(tmp_path / "snapshot.json").read().resources) == 3
    again = collector.resume(plan.run_id)
    assert again["snapshotId"] == result["snapshotId"]
    assert backend.creates == len(backend.keys) == 1


def test_disconnect_after_input_acceptance_resumes_without_duplicate(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.fail_submit = True
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(ConnectionError):
        collector.start(plan, session_request(plan, "Mounted instructions."))
    journal = json.loads((tmp_path / "runs" / plan.run_id / "journal.json").read_text())
    assert journal["sessionId"] == "sess_fixture"
    assert journal["remoteMayBeRunning"] is True
    backend.fail_submit = False
    assert collector.resume(plan.run_id)["state"] == "published"
    assert backend.creates == len(backend.keys) == 1


def test_uncertain_submission_reuses_saved_idempotency_key(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.fail_submit = True
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(ConnectionError):
        collector.start(plan, session_request(plan, "Mounted instructions."))
    backend.turn_status = None  # No saved turn yet: retry only the same submission key.
    backend.fail_submit = False
    assert collector.resume(plan.run_id)["state"] == "published"
    assert len(backend.keys) == 2 and backend.keys[0] == backend.keys[1]
    assert backend.creates == 1


def test_unknown_create_outcome_never_creates_again(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.fail_create = True
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(CollectorError, match="unknown"):
        collector.start(plan, session_request(plan, "Mounted instructions."))
    with pytest.raises(CollectorError, match="original session"):
        collector.resume(plan.run_id)
    assert backend.creates == 1
    backend.fail_create = False
    assert collector.resume(plan.run_id, session_id="sess_fixture")["state"] == "published"
    assert backend.creates == 1


def test_idle_is_not_completion_and_deadline_cancels(tmp_path, artifact):
    plan = make_plan(max_seconds=10)
    backend = Backend(plan, artifact)
    clock = [plan.started_at]

    def sleep(seconds):
        clock[0] += timedelta(seconds=max(seconds, 1))

    def submit(session_id, key):
        backend.keys.append(key)  # Accepted, but no completed turn ever appears.

    backend.submit = submit
    collector = Collector(
        tmp_path / "runs", tmp_path / "snapshot.json", backend, sleep=sleep, clock=lambda: clock[0]
    )
    with pytest.raises(CollectorError, match="deadline"):
        collector.start(plan, session_request(plan, "Mounted instructions."))
    assert backend.cancelled
    assert not (tmp_path / "snapshot.json").exists()
    journal = json.loads((tmp_path / "runs" / plan.run_id / "journal.json").read_text())
    assert journal["state"] == "cancelled"
    assert journal["remoteMayBeRunning"] is False


def test_missing_receipt_preserves_prior_snapshot(tmp_path, artifact, write_artifact):
    path = tmp_path / "snapshot.json"
    previous = SnapshotStore(path).publish(write_artifact(artifact), method="fixture")
    before = path.read_bytes()
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.receipts["requests"] = backend.receipts["requests"][:1]
    backend.artifact["fetchReport"]["requests"] = 1
    collector = Collector(tmp_path / "runs", path, backend)
    with pytest.raises(CollectorError, match="source receipt"):
        collector.start(plan, session_request(plan, "Mounted instructions."))
    assert path.read_bytes() == before
    assert SnapshotStore(path).read().snapshot_id == previous.snapshot_id


def test_fake_artifact_extra_data_is_not_passed_through(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.artifact["resources"][0]["participants"] = [{"email": "not-for-publication"}]
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(ValueError):
        collector.start(plan, session_request(plan, "Mounted instructions."))
    assert not (tmp_path / "snapshot.json").exists()


def test_live_cli_requires_explicit_flag_without_constructing_client(monkeypatch):
    from openai_academy_api.cli import collect

    monkeypatch.setattr("sys.argv", ["academy-collector", "run"])
    with pytest.raises(SystemExit) as exc:
        collect()
    assert exc.value.code == 2


def test_custom_seed_file_dry_run_has_no_network(tmp_path, monkeypatch, capsys):
    from openai_academy_api.cli import collect

    seeds = tmp_path / "seeds.json"
    seeds.write_text(json.dumps(["https://academy.openai.com/public/content"]))
    instructions = tmp_path / "instructions.md"
    instructions.write_text("Use the mounted collection plan.")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "academy-collector",
            "dry-run",
            "--instructions",
            str(instructions),
            "--seeds-file",
            str(seeds),
        ],
    )
    collect()
    result = json.loads(capsys.readouterr().out)
    assert result["live"] is False
    assert result["plan"]["seedUrls"] == ["https://academy.openai.com/public/content"]


def test_cleanup_failure_does_not_undo_publication(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.delete_busy = True
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    result = collector.start(plan, session_request(plan, "Mounted instructions."))
    assert result["state"] == "published"
    assert result["cleanup"]["state"] == "deferred"
    assert len(SnapshotStore(tmp_path / "snapshot.json").read().resources) == 3
    backend.delete_busy = False
    cleaned = collector.cleanup(plan.run_id)
    assert cleaned["state"] == "published"
    assert cleaned["cleanup"]["state"] == "complete"
    assert backend.creates == len(backend.keys) == 1


def test_cleanup_never_deletes_an_active_recovery_session(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.fail_submit = True
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(ConnectionError):
        collector.start(plan, session_request(plan, "Mounted instructions."))
    backend.turn_status = "in_progress"
    result = collector.cleanup(plan.run_id)
    assert result["cleanup"]["state"] == "deferred"
    assert backend.deleted is False
    assert result["remoteMayBeRunning"] is True


@pytest.mark.parametrize("field,value", [("bytes", 0), ("sha256", None), ("sha256", "invalid")])
def test_aborted_200_response_cannot_support_publication(tmp_path, artifact, field, value):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.receipts["requests"][-1][field] = value
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(CollectorError, match="receipt is incomplete"):
        collector.start(plan, session_request(plan, "Mounted instructions."))
    assert not (tmp_path / "snapshot.json").exists()


def test_terminal_quota_failure_records_exact_error_and_never_retries(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.remote_error = {
        "code": "usage_limit_exceeded",
        "message": "Fixture organization usage limit reached.",
    }

    def quota_failure(session_id, key):
        backend.keys.append(key)
        backend.turn_status = "failed"

    backend.submit = quota_failure
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(CollectorError, match="did not complete"):
        collector.start(plan, session_request(plan, "Mounted instructions."))
    journal = json.loads((tmp_path / "runs" / plan.run_id / "journal.json").read_text())
    assert journal["state"] == "failed"
    assert journal["remoteError"] == backend.remote_error
    assert journal["remoteMayBeRunning"] is False
    calls = backend.inspections
    with pytest.raises(CollectorError, match="terminal"):
        collector.resume(plan.run_id)
    assert backend.inspections == calls
    assert backend.creates == len(backend.keys) == 1
    assert not (tmp_path / "snapshot.json").exists()


def test_new_run_refuses_unresolved_previous_session(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.fail_create = True
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(CollectorError, match="unknown"):
        collector.start(plan, session_request(plan, "instructions"))
    with pytest.raises(CollectorError, match="prior run requires recovery"):
        next_plan = make_plan()
        collector.start(next_plan, session_request(next_plan, "instructions"))
    assert backend.creates == 1


def test_controller_lock_excludes_distinct_run_ids(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    first = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    second = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with first._controller_locked():
        with pytest.raises(CollectorError, match="Another collector"):
            second.start(plan, session_request(plan, "instructions"))
    assert backend.creates == 0


def test_new_quota_failure_blocks_daily_new_run_for_same_credential(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.remote_error = {"code": "usage_limit_exceeded", "message": "Fixture limit"}

    def fail(session_id, key):
        backend.keys.append(key)
        backend.turn_status = "failed"

    backend.submit = fail
    collector = Collector(
        tmp_path / "runs", tmp_path / "snapshot.json", backend, credential_fingerprint="a" * 64
    )
    with pytest.raises(CollectorError):
        collector.start(plan, session_request(plan, "instructions"))
    next_plan = make_plan()
    with pytest.raises(CollectorError, match="terminal credential/quota"):
        collector.start(next_plan, session_request(next_plan, "instructions"))
    assert backend.creates == len(backend.keys) == 1


def test_resume_refuses_changed_credential_before_provider_calls(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.fail_submit = True
    collector = Collector(
        tmp_path / "runs", tmp_path / "snapshot.json", backend, credential_fingerprint="a" * 64
    )
    with pytest.raises(ConnectionError):
        collector.start(plan, session_request(plan, "instructions"))
    before = backend.inspections
    changed = Collector(
        tmp_path / "runs", tmp_path / "snapshot.json", backend, credential_fingerprint="b" * 64
    )
    with pytest.raises(CollectorError, match="original credential"):
        changed.resume(plan.run_id)
    assert backend.inspections == before


def test_creation_auth_failure_is_terminal_and_redacts_key(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)

    class Rejected(Exception):
        status_code = 401
        body = {"code": "invalid_api_key", "message": "Bad sk-fixture-secret-value"}

    def rejected(request):
        backend.creates += 1
        raise Rejected()

    backend.create = rejected
    collector = Collector(
        tmp_path / "runs", tmp_path / "snapshot.json", backend, credential_fingerprint="a" * 64
    )
    with pytest.raises(CollectorError, match="rejected"):
        collector.start(plan, session_request(plan, "instructions"))
    path = tmp_path / "runs" / plan.run_id / "journal.json"
    saved = json.loads(path.read_text())
    assert saved["state"] == "failed" and saved["remoteError"]["code"] == "invalid_api_key"
    assert "sk-fixture" not in path.read_text()
    with pytest.raises(CollectorError, match="terminal"):
        collector.resume(plan.run_id)
    assert backend.creates == 1


@pytest.mark.parametrize(
    "state,cleanup,skipped",
    [("published", "complete", True), ("running", None, False), ("failed", None, False)],
)
def test_daily_mode_never_resubmits_existing_day_before_loading_key(
    tmp_path, monkeypatch, capsys, state, cleanup, skipped
):
    import uuid

    from openai_academy_api.cli import collect
    from openai_academy_api.storage import now

    state_dir = tmp_path / "runs"
    timestamp = now()
    monkeypatch.setattr("openai_academy_api.storage.now", lambda: timestamp)
    run_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"academy-collector:{state_dir.resolve()}:{timestamp.date().isoformat()}",
        )
    )
    directory = state_dir / run_id
    directory.mkdir(parents=True)
    (directory / "journal.json").write_text(
        json.dumps({"state": state, "cleanup": {"state": cleanup}})
    )
    instructions = tmp_path / "instructions.md"
    instructions.write_text("Use the collection plan.")
    monkeypatch.setattr(
        "sys.argv",
        [
            "academy-collector",
            "--env-file",
            str(tmp_path / "missing.env"),
            "--snapshot",
            str(tmp_path / "snapshot.json"),
            "--state-dir",
            str(state_dir),
            "run",
            "--live",
            "--daily",
            "--instructions",
            str(instructions),
        ],
    )
    if skipped:
        collect()
        assert json.loads(capsys.readouterr().out) == {
            "runId": run_id,
            "dailyAlreadyComplete": True,
        }
    else:
        with pytest.raises(SystemExit) as exc:
            collect()
        assert exc.value.code == 1
        assert "no daily resubmission" in capsys.readouterr().err
    assert not (tmp_path / "snapshot.json").exists()


def test_failed_setup_never_submits_input(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.ready = lambda session: {"state": "failed", "environmentId": "env_fixture"}
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(CollectorError, match="no inference submitted"):
        collector.start(plan, session_request(plan, "instructions"))
    saved = json.loads((tmp_path / "runs" / plan.run_id / "journal.json").read_text())
    assert saved["state"] == "failed"
    assert saved["preflight"]["state"] == "failed"
    assert backend.creates == 1 and backend.keys == []
    assert not (tmp_path / "snapshot.json").exists()


def test_source_helper_honors_runtime_proxy_and_still_rejects_private_target(tmp_path, monkeypatch):
    import urllib.request

    from openai_academy_api.fetch_public import PublicFetcher

    monkeypatch.setenv("https_proxy", "http://127.0.0.1:9")
    fetcher = PublicFetcher(make_plan().model_dump(mode="json", by_alias=True), tmp_path)
    handlers = [h for h in fetcher.opener.handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert handlers[0].proxies["https"] == "http://127.0.0.1:9"

    class NeverOpen:
        def open(self, *args, **kwargs):
            raise AssertionError("A rejected target must never reach a proxy")

    fetcher.opener = NeverOpen()
    with pytest.raises(ValueError):
        fetcher.fetch("https://127.0.0.1/private")


def test_cleanup_refuses_changed_credential_before_provider_calls(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.delete_busy = True
    collector = Collector(
        tmp_path / "runs", tmp_path / "snapshot.json", backend, credential_fingerprint="a" * 64
    )
    result = collector.start(plan, session_request(plan, "instructions"))
    assert result["cleanup"]["state"] == "deferred"
    before = backend.inspections
    backend.delete_busy = False
    changed = Collector(
        tmp_path / "runs", tmp_path / "snapshot.json", backend, credential_fingerprint="b" * 64
    )
    # Another account would see the session as missing, which must not count as deleted.
    with pytest.raises(CollectorError, match="original credential"):
        changed.cleanup(plan.run_id)
    assert backend.inspections == before and backend.deleted is False
    saved = json.loads((tmp_path / "runs" / plan.run_id / "journal.json").read_text())
    assert saved["cleanup"]["state"] == "deferred"
    assert collector.cleanup(plan.run_id)["cleanup"]["state"] == "complete"


def test_failed_run_holds_daily_refresh_until_acknowledged(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.ready = lambda session: {"state": "failed", "environmentId": "env_fixture"}
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(CollectorError, match="no inference submitted"):
        collector.start(plan, session_request(plan, "instructions"))
    next_plan = make_plan()
    later = Backend(next_plan, artifact)
    daily = Collector(tmp_path / "runs", tmp_path / "snapshot.json", later)
    request = session_request(next_plan, "instructions")
    with pytest.raises(CollectorError, match="acknowledge"):
        daily.start(next_plan, request, daily=True)
    assert later.creates == 0
    assert daily.acknowledge(plan.run_id)["acknowledgedAt"]
    assert daily.start(next_plan, request, daily=True)["state"] == "published"
    assert later.creates == len(later.keys) == 1


def test_acknowledgement_clears_same_key_quota_hold_only_for_stopped_runs(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    backend.remote_error = {"code": "usage_limit_exceeded", "message": "Fixture limit"}

    def fail(session_id, key):
        backend.keys.append(key)
        backend.turn_status = "failed"

    backend.submit = fail
    collector = Collector(
        tmp_path / "runs", tmp_path / "snapshot.json", backend, credential_fingerprint="a" * 64
    )
    with pytest.raises(CollectorError):
        collector.start(plan, session_request(plan, "instructions"))
    collector.acknowledge(plan.run_id)
    next_plan = make_plan()
    later = Backend(next_plan, artifact)
    later.fail_submit = True
    renewed = Collector(
        tmp_path / "runs", tmp_path / "snapshot.json", later, credential_fingerprint="a" * 64
    )
    with pytest.raises(ConnectionError):
        renewed.start(next_plan, session_request(next_plan, "instructions"))
    # Input may have been accepted, so this run cannot be waved through.
    with pytest.raises(CollectorError, match="stopped"):
        renewed.acknowledge(next_plan.run_id)
    saved = json.loads((tmp_path / "runs" / next_plan.run_id / "journal.json").read_text())
    assert "acknowledgedAt" not in saved and saved["remoteMayBeRunning"] is True


def test_changed_publication_requests_one_purge_before_cleanup(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    calls = []

    def purge():
        calls.append(backend.deleted)
        return "abc123"

    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend, purge=purge)
    result = collector.start(plan, session_request(plan, "instructions"))
    assert result["edgePurge"]["state"] == "accepted"
    assert result["edgePurge"]["purgeId"] == "abc123"
    assert result["edgePurge"]["snapshotId"] == result["snapshotId"]
    assert calls == [False]  # Requested right after publication, before session cleanup.
    collector.resume(plan.run_id)
    assert len(calls) == 1


def test_unchanged_publication_skips_purge(tmp_path, artifact, write_artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    path = tmp_path / "snapshot.json"
    SnapshotStore(path).publish(write_artifact(backend.artifact), method="managed-agent")
    calls = []
    collector = Collector(tmp_path / "runs", path, backend, purge=lambda: calls.append(1))
    result = collector.start(plan, session_request(plan, "instructions"))
    assert result["state"] == "published" and "edgePurge" not in result
    assert calls == []


@pytest.mark.parametrize(
    "failure,reason",
    [
        (PurgeError("Cloudflare returned HTTP 403: 10000 Authentication error"), "HTTP 403"),
        (RuntimeError("fixture-secret-token"), "RuntimeError"),
    ],
)
def test_purge_failure_keeps_publication_without_new_collection(
    tmp_path, artifact, failure, reason
):
    plan = make_plan()
    backend = Backend(plan, artifact)

    def purge():
        raise failure

    path = tmp_path / "snapshot.json"
    collector = Collector(tmp_path / "runs", path, backend, purge=purge)
    result = collector.start(plan, session_request(plan, "instructions"))
    assert result["state"] == "published" and result["cleanup"]["state"] == "complete"
    assert result["edgePurge"]["state"] == "failed"
    assert reason in result["edgePurge"]["reason"]
    journal = (tmp_path / "runs" / plan.run_id / "journal.json").read_text()
    assert "fixture-secret-token" not in journal
    assert len(SnapshotStore(path).read().resources) == 3
    assert json.loads(path.with_suffix(".status.json").read_text())["lastAttemptSucceeded"] is True
    assert backend.creates == len(backend.keys) == 1


def _live_argv(tmp_path, *extra):
    env_file = tmp_path / "collector.env"
    env_file.write_text("OPENAI_API_KEY=fixture-key-value\n")
    instructions = tmp_path / "instructions.md"
    instructions.write_text("Use the collection plan.")
    return [
        "academy-collector",
        "--env-file",
        str(env_file),
        "--snapshot",
        str(tmp_path / "snapshot.json"),
        "--state-dir",
        str(tmp_path / "runs"),
        "run",
        "--live",
        *extra,
        "--instructions",
        str(instructions),
    ]


def test_daily_cli_stops_after_unreviewed_failure_before_provider_calls(
    tmp_path, monkeypatch, capsys
):
    from openai_academy_api.cli import collect
    from openai_academy_api.collector import ManagedAgents

    failed = tmp_path / "runs" / "6f1c2b9e-0c5f-4a43-9a43-4d55a0d1f0aa"
    failed.mkdir(parents=True)
    (failed / "journal.json").write_text(
        json.dumps({"runId": failed.name, "state": "failed", "remoteMayBeRunning": False})
    )

    def never(*args, **kwargs):
        raise AssertionError("No provider call is allowed")

    monkeypatch.setattr(ManagedAgents, "create", never)
    monkeypatch.setattr("sys.argv", _live_argv(tmp_path, "--daily"))
    with pytest.raises(SystemExit) as exc:
        collect()
    assert exc.value.code == 1 and "acknowledge" in capsys.readouterr().err
    monkeypatch.setattr(
        "sys.argv",
        ["academy-collector", "--state-dir", str(tmp_path / "runs"), "acknowledge", failed.name],
    )
    collect()
    assert json.loads(capsys.readouterr().out)["acknowledgedAt"]


def test_cli_reports_purge_failure_without_failing_publication(tmp_path, monkeypatch, capsys):
    from openai_academy_api.cli import collect

    published = {"state": "published", "edgePurge": {"state": "failed", "reason": "HTTP 403"}}
    monkeypatch.setattr(Collector, "start", lambda self, plan, request, daily=False: published)
    monkeypatch.setattr("sys.argv", _live_argv(tmp_path))
    with pytest.raises(SystemExit) as exc:
        collect()
    captured = capsys.readouterr()
    assert exc.value.code == 3
    assert json.loads(captured.out)["state"] == "published"
    assert "Do not rerun collection" in captured.err


def test_purge_cache_cli_requires_live_flag_and_settings(tmp_path, monkeypatch, capsys):
    from openai_academy_api.cli import collect
    from openai_academy_api.edge import HostnamePurge

    monkeypatch.setattr("sys.argv", ["academy-collector", "purge-cache"])
    with pytest.raises(SystemExit) as exc:
        collect()
    assert exc.value.code == 2
    monkeypatch.setattr("sys.argv", ["academy-collector", "purge-cache", "--live"])
    with pytest.raises(SystemExit) as exc:
        collect()
    assert exc.value.code == 1 and "missing" in capsys.readouterr().err
    token = tmp_path / "purge-token"
    token.write_text("fixture-purge-token-0123456789\n")
    monkeypatch.setenv("ACADEMY_CLOUDFLARE_ZONE_ID", "0" * 32)
    monkeypatch.setenv("ACADEMY_CLOUDFLARE_HOSTNAME", "api.example.com")
    monkeypatch.setenv("ACADEMY_CLOUDFLARE_PURGE_TOKEN_FILE", str(token))
    monkeypatch.setattr(HostnamePurge, "__call__", lambda self: "abc123")
    collect()
    out = capsys.readouterr().out
    assert json.loads(out) == {
        "hostname": "api.example.com",
        "state": "accepted",
        "purgeId": "abc123",
    }
    assert "fixture-purge-token" not in out
