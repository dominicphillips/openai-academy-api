"""Private managed Agents API runner. Public HTTP routes do not import this module."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path

from pydantic import AwareDatetime, Field

from .models import CollectionArtifact, Model
from .security import NETWORK_HOSTS, public_academy_url
from .storage import MAX_ARTIFACT_BYTES, SnapshotStore, atomic_json, bounded_json, now

PLAN_PATH = "/workspace/input/collection-plan.json"
SCHEMA_PATH = "/workspace/input/collection.schema.json"
OUTPUT_PATH = "/workspace/outputs/academy-snapshot.json"
RECEIPTS_PATH = "/workspace/outputs/fetch-receipts.json"
SEEDS = (
    "https://academy.openai.com/pages/courses",
    "https://academy.openai.com/sitemap.xml",
    "https://academy.openai.com/public/content",
    "https://academy.openai.com/public/clubs",
)


class CollectorError(ValueError):
    pass


class SessionMissing(CollectorError):
    pass


class Plan(Model):
    run_id: str
    seed_urls: list[str]
    max_pages: int = Field(default=80, ge=1, le=500)
    max_resources: int = Field(default=500, ge=1, le=5000)
    max_seconds: int = Field(default=600, ge=10, le=1800)
    max_response_bytes: int = Field(default=2097152, ge=1024, le=2097152)
    request_delay_seconds: float = Field(default=0.5, ge=0.5, le=60)
    started_at: AwareDatetime
    deadline_at: AwareDatetime
    output_path: str = OUTPUT_PATH


def make_plan(*, seed_urls: list[str] | None = None, **limits) -> Plan:
    timestamp = now()
    maximum = limits.get("max_seconds", 600)
    seeds = list(
        dict.fromkeys(
            public_academy_url(url, discovery=True)
            for url in (seed_urls if seed_urls is not None else SEEDS)
        )
    )
    if not 1 <= len(seeds) <= 500:
        raise CollectorError("Provide between 1 and 500 public seed URLs")
    return Plan(
        run_id=str(uuid.uuid4()),
        seed_urls=seeds,
        started_at=timestamp,
        deadline_at=timestamp + timedelta(seconds=maximum),
        **limits,
    )


def inline(path: str, data: bytes) -> dict:
    return {"type": "inline", "path": path, "data": base64.b64encode(data).decode()}


def session_request(plan: Plan, instructions: str) -> dict:
    if not instructions.strip() or len(instructions.encode()) > 65536:
        raise CollectorError("Collector instructions are missing or too large")
    for url in plan.seed_urls:
        public_academy_url(url, discovery=True)
    package = files("openai_academy_api")
    schema = json.dumps(CollectionArtifact.model_json_schema(by_alias=True)).encode()
    return {
        "agent": {
            "model": "gpt-6.1-sol",
            "instructions": instructions,
            "reasoning": {"effort": "max"},
            "multi_agent": {"enabled": False},
            "tools": [],
        },
        "environment": {
            "type": "openai_hosted",
            "container_size": "small",
            "network": {"access": "restricted", "allowed_domains": list(NETWORK_HOSTS)},
            "files": [
                inline(PLAN_PATH, plan.model_dump_json(by_alias=True).encode()),
                inline(SCHEMA_PATH, schema),
                inline(
                    "/workspace/tools/fetch_public.py",
                    package.joinpath("fetch_public.py").read_bytes(),
                ),
                inline(
                    "/workspace/tools/security.py", package.joinpath("security.py").read_bytes()
                ),
            ],
        },
        "metadata": {"collector_run_id": plan.run_id},
    }


class ManagedAgents:
    """Small adapter over the official SDK, constructed only by an explicit live command."""

    def __init__(self, client):
        self.client = client
        self.sessions = client.beta.agents.sessions

    def create(self, request: dict) -> dict:
        # No input yet: persist the returned session ID before starting inference.
        return self.sessions.create(**request, stream=False).model_dump(mode="json")

    def submit(self, session_id: str, key: str) -> None:
        self.sessions.events.create(
            session_id,
            idempotency_key=key,
            events=[
                {
                    "type": "agent.session.input.message",
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": json.dumps(
                                        {
                                            "planPath": PLAN_PATH,
                                            "schemaPath": SCHEMA_PATH,
                                            "outputPath": OUTPUT_PATH,
                                        }
                                    ),
                                }
                            ],
                        }
                    ],
                }
            ],
        )

    def inspect(self, session_id: str) -> tuple[dict, list[dict]]:
        from openai import NotFoundError

        try:
            session = self.sessions.retrieve(session_id).model_dump(mode="json")
            page = self.sessions.turns.list(session_id, order="desc", limit=20)
        except NotFoundError:
            raise SessionMissing("Managed session no longer exists") from None
        return session, [x.model_dump(mode="json") for x in page.data]

    def cancel(self, session_id: str) -> None:
        self.sessions.events.create(session_id, events=[{"type": "agent.session.input.cancel"}])

    def delete(self, session_id: str) -> bool:
        from openai import NotFoundError

        try:
            response = self.sessions.delete(session_id)
        except NotFoundError:
            return True
        return response.deleted is True

    def download(self, session_id: str, turn_id: str, remote_path: str, destination: Path) -> None:
        page = self.sessions.artifacts.list(session_id, order="desc", limit=100)
        matches = [a for a in page.data if a.turn_id == turn_id and a.path == remote_path]
        if len(matches) != 1:
            raise CollectorError("The completed turn did not publish exactly one required artifact")
        artifact = matches[0]
        # The actual byte count is enforced too; never trust a model-reported size.
        written = 0
        with (
            self.sessions.artifacts.with_streaming_response.content(
                artifact.id,
                session_id=session_id,
            ) as response,
            destination.open("wb") as output,
        ):
            for chunk in response.iter_bytes(chunk_size=65536):
                written += len(chunk)
                if written > MAX_ARTIFACT_BYTES:
                    raise CollectorError("Published artifact exceeds size limit")
                output.write(chunk)


class Collector:
    def __init__(
        self, state_dir: Path, snapshot_path: Path, backend, *, sleep=time.sleep, clock=now
    ):
        self.state_dir = state_dir
        self.store = SnapshotStore(snapshot_path)
        self.backend = backend
        self.sleep, self.clock = sleep, clock

    @contextmanager
    def _locked(self, run_id: str):
        try:
            uuid.UUID(run_id)
        except ValueError:
            raise CollectorError("Invalid run ID") from None
        directory = self.state_dir / run_id
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (directory / "run.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CollectorError("This run is already controlled by another process") from None
            yield directory

    @staticmethod
    def _save(directory: Path, journal: dict) -> None:
        journal["updatedAt"] = now().isoformat()
        atomic_json(directory / "journal.json", journal)

    def start(self, plan: Plan, request: dict) -> dict:
        with self._locked(plan.run_id) as directory:
            if (directory / "journal.json").exists():
                raise CollectorError("Run already exists; resume it")
            journal = {
                "runId": plan.run_id,
                "state": "creating",
                "sessionId": None,
                "turnId": None,
                "submissionKey": str(uuid.uuid4()),
                "plan": plan.model_dump(mode="json", by_alias=True),
                "requestHash": hashlib.sha256(
                    json.dumps(request, sort_keys=True).encode()
                ).hexdigest(),
                "remoteMayBeRunning": False,
            }
            self._save(directory, journal)
            try:
                session = self.backend.create(request)
            except Exception:
                journal["state"] = "creation-uncertain"
                self._save(directory, journal)
                raise CollectorError(
                    "Session creation outcome is unknown; recover by run metadata"
                ) from None
            journal.update(sessionId=session["id"], state="session-created")
            self._save(directory, journal)
            return self._continue(directory, journal)

    def resume(self, run_id: str, *, session_id: str | None = None) -> dict:
        with self._locked(run_id) as directory:
            try:
                journal = json.loads(bounded_json(directory / "journal.json"))
            except (OSError, ValueError):
                raise CollectorError("No valid journal exists for this run") from None
            if journal["runId"] != run_id:
                raise CollectorError("Journal run ID mismatch")
            if journal["state"] == "published":
                self._cleanup(directory, journal)
                return journal
            if journal["state"] in {"failed", "cancelled"}:
                raise CollectorError("Run is terminal; inference will not be retried")
            if not journal.get("sessionId"):
                if not session_id:
                    raise CollectorError(
                        "Adopt the original session ID; do not create another session"
                    )
                session, _ = self.backend.inspect(session_id)
                if session.get("metadata", {}).get("collector_run_id") != run_id:
                    raise CollectorError("Session does not belong to this run")
                journal.update(sessionId=session_id, state="session-created")
                self._save(directory, journal)
            elif session_id and session_id != journal["sessionId"]:
                raise CollectorError("Journal already belongs to another session")
            return self._continue(directory, journal)

    def cleanup(self, run_id: str) -> dict:
        with self._locked(run_id) as directory:
            journal = json.loads(bounded_json(directory / "journal.json"))
            if journal["runId"] != run_id or not journal.get("sessionId"):
                raise CollectorError("No saved session exists for cleanup")
            self._cleanup(directory, journal)
            return journal

    def _cleanup(self, directory: Path, journal: dict) -> None:
        cleanup = journal.setdefault("cleanup", {"state": "pending", "attempts": 0})
        if cleanup["state"] == "complete":
            return
        cleanup["attempts"] += 1
        cleanup["lastAttemptAt"] = now().isoformat()
        self._save(directory, journal)
        try:
            session, turns = self.backend.inspect(journal["sessionId"])
            active = any(t["status"] not in {"completed", "failed", "cancelled"} for t in turns)
            if session["status"] not in {"idle", "failed"} or active:
                cleanup.update(state="deferred", reason="session-not-confirmed-inactive")
            elif self.backend.delete(journal["sessionId"]):
                cleanup.update(state="complete", reason=None)
                journal["remoteMayBeRunning"] = False
            else:
                cleanup.update(state="deferred", reason="deletion-not-confirmed")
        except SessionMissing:
            cleanup.update(state="complete", reason=None)
            journal["remoteMayBeRunning"] = False
        except Exception:
            # A busy or disconnected cleanup must not roll back a published snapshot.
            cleanup.update(state="deferred", reason="deletion-busy-or-unverified")
        self._save(directory, journal)

    def _cancel(self, directory: Path, journal: dict) -> None:
        journal.update(state="cancel-requested", remoteMayBeRunning=True)
        self._save(directory, journal)
        try:
            self.backend.cancel(journal["sessionId"])
            # Receipt is not proof of cancellation; inspect the explicit turn outcome.
            for _ in range(3):
                session, turns = self.backend.inspect(journal["sessionId"])
                if turns and turns[0]["status"] in {"cancelled", "failed", "completed"}:
                    journal.update(state=turns[0]["status"], remoteMayBeRunning=False)
                    break
                if session["status"] == "failed":
                    journal.update(state="failed", remoteMayBeRunning=False)
                    break
                self.sleep(1)
        except Exception:
            pass
        self._save(directory, journal)

    def _continue(self, directory: Path, journal: dict) -> dict:
        plan = Plan.model_validate_json(json.dumps(journal["plan"]))
        session_id = journal["sessionId"]
        try:
            # Inspect before any retry. Existing work always wins over re-submission.
            session, turns = self.backend.inspect(session_id)
            if not turns and not journal.get("inputSubmitted", False):
                if self.clock() >= plan.deadline_at:
                    raise CollectorError("Run deadline has passed")
                journal.update(state="submission-uncertain", remoteMayBeRunning=True)
                self._save(directory, journal)
                self.backend.submit(session_id, journal["submissionKey"])
                journal.update(state="submitted", inputSubmitted=True)
                self._save(directory, journal)
            for _ in range(901):
                session, turns = self.backend.inspect(session_id)
                root_turns = [x for x in turns if not x.get("subagent_id")]
                if len(root_turns) > 1:
                    raise CollectorError(
                        "Unexpected additional turn; refusing ambiguous publication"
                    )
                turn = root_turns[0] if root_turns else None
                if session["status"] == "failed":
                    error = turn.get("error") if turn else None
                    journal.update(state="failed", remoteMayBeRunning=False)
                    journal["remoteError"] = (
                        {"code": error.get("code"), "message": error.get("message")}
                        if isinstance(error, dict)
                        else {"code": None, "message": session.get("error")}
                    )
                    self._save(directory, journal)
                    raise CollectorError("Managed session failed")
                if session["status"] == "requires_action" or session.get("required_actions"):
                    self._cancel(directory, journal)
                    raise CollectorError("Collection requested an unsupported action")
                if turn:
                    journal["turnId"] = turn["id"]
                    if turn["status"] in {"failed", "cancelled"}:
                        journal.update(state=turn["status"], remoteMayBeRunning=False)
                        error = turn.get("error")
                        if isinstance(error, dict):
                            journal["remoteError"] = {
                                "code": error.get("code"),
                                "message": error.get("message"),
                            }
                        self._save(directory, journal)
                        raise CollectorError("Managed turn did not complete")
                    if turn["status"] == "completed":
                        journal.update(state="completed", remoteMayBeRunning=False)
                        self._save(directory, journal)
                        return self._finish(directory, journal, plan)
                if self.clock() >= plan.deadline_at:
                    self._cancel(directory, journal)
                    raise CollectorError("Collection deadline reached")
                journal.update(state="running", remoteMayBeRunning=True)
                self._save(directory, journal)
                self.sleep(min(2, (plan.deadline_at - self.clock()).total_seconds()))
            self._cancel(directory, journal)
            raise CollectorError("Polling limit reached")
        except Exception as exc:
            # A disconnected controller must never start another session automatically.
            if journal["state"] not in {"published", "failed", "cancelled", "cancel-requested"}:
                journal["state"] = "interrupted"
            journal["errorCode"] = (
                "collector-error" if isinstance(exc, CollectorError) else "controller-interrupted"
            )
            self._save(directory, journal)
            self.store.record_attempt(success=False, code=journal["errorCode"])
            raise

    def _finish(self, directory: Path, journal: dict, plan: Plan) -> dict:
        artifact_path, receipts_path = directory / "artifact.json", directory / "receipts.json"
        for remote, target in ((OUTPUT_PATH, artifact_path), (RECEIPTS_PATH, receipts_path)):
            self.backend.download(journal["sessionId"], journal["turnId"], remote, target)
        artifact = CollectionArtifact.model_validate_json(bounded_json(artifact_path))
        receipts = json.loads(bounded_json(receipts_path))
        requests = receipts.get("requests", [])
        if (
            receipts.get("runId") != plan.run_id
            or receipts.get("robotsChecked") is not True
            or not isinstance(requests, list)
            or len(requests) > plan.max_pages
            or artifact.fetch_report.requests != len(requests)
            or len(artifact.resources) > plan.max_resources
        ):
            raise CollectorError("Collection receipts or limits do not match the run")
        fetched = set()
        for receipt in requests:
            url = public_academy_url(receipt["url"], discovery=True)
            if receipt.get("bytes", 0) > plan.max_response_bytes:
                raise CollectorError("Source response exceeded byte limit")
            checked_at = datetime.fromisoformat(receipt["checkedAt"].replace("Z", "+00:00"))
            if checked_at.tzinfo is None or not plan.started_at <= checked_at <= plan.deadline_at:
                raise CollectorError("Source receipt is outside the collection window")
            if receipt["status"] == 200:
                size = receipt.get("bytes")
                digest = receipt.get("sha256")
                if (
                    type(size) is not int
                    or size <= 0
                    or not isinstance(digest, str)
                    or re.fullmatch(r"[a-f0-9]{64}", digest) is None
                ):
                    raise CollectorError("Successful source receipt is incomplete")
                fetched.add(url)
        if "https://academy.openai.com/robots.txt" not in fetched:
            raise CollectorError("No successful robots receipt")
        if any(r.url not in fetched for r in artifact.resources):
            raise CollectorError("A resource lacks a successful source receipt")
        if not plan.started_at <= artifact.generated_at <= plan.deadline_at:
            raise CollectorError("Artifact was generated outside the collection window")
        snapshot = self.store.publish(artifact_path, method="managed-agent")
        journal.update(state="published", snapshotId=snapshot.snapshot_id, remoteMayBeRunning=False)
        self._save(directory, journal)
        self._cleanup(directory, journal)
        return journal
