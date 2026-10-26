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
