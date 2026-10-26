"""Validated snapshots with atomic replacement and an in-process last good copy."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import (
    CollectionArtifact,
    Coverage,
    Snapshot,
    Status,
    assemble_snapshot,
    build_snapshot,
)

MAX_ARTIFACT_BYTES = 16 * 1024 * 1024


def now() -> datetime:
    return datetime.now(UTC)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def bounded_json(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError("Artifact exceeds size limit")
    return data


class SnapshotUnavailable(ValueError):
    pass


class SnapshotStore:
    def __init__(self, path: Path, stale_after: timedelta = timedelta(days=7)):
        self.path = path
        self.state_path = path.with_suffix(".status.json")
        self.previous_path = path.with_suffix(".previous.json")
        self.stale_after = stale_after
        self._cached: Snapshot | None = None
        self._signature: tuple[int, int] | None = None
        self._read_failed = False
        self._lock = threading.RLock()

    def read(self) -> Snapshot:
        with self._lock:
            try:
                stat = self.path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if signature != self._signature or self._cached is None:
                    candidate = Snapshot.model_validate_json(bounded_json(self.path))
                    self._cached, self._signature = candidate, signature
                self._read_failed = False
            except (OSError, ValueError):
                self._read_failed = True
                if self._cached is None:
                    try:
                        self._cached = Snapshot.model_validate_json(
                            bounded_json(self.previous_path)
                        )
                    except (OSError, ValueError):
                        raise SnapshotUnavailable("No valid snapshot") from None
            assert self._cached is not None
            return self._cached

    def _state(self) -> dict:
        try:
            data = json.loads(bounded_json(self.state_path))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def record_attempt(self, *, success: bool, code: str | None = None) -> None:
        state = self._state()
        timestamp = now().isoformat()
        state.update(lastAttemptAt=timestamp, lastAttemptSucceeded=success, errorCode=code)
        if success:
            state["lastSuccessAt"] = timestamp
        atomic_json(self.state_path, state)

    def publish(
        self, artifact_path: Path, *, method: str = "manual", artwork_receipts: dict | None = None
    ) -> Snapshot:
        try:
            artifact = CollectionArtifact.model_validate_json(bounded_json(artifact_path))
            snapshot = build_snapshot(artifact, method)  # type: ignore[arg-type]
            payload = snapshot.model_dump(mode="json", by_alias=True)
            with self._lock:
                try:
                    old = self.read()
                except SnapshotUnavailable:
                    old = None
                if old is not None:
                    snapshot = merge_snapshot(old, snapshot)
                if artwork_receipts is not None:
                    from .artwork_refresh import prepare_artwork_refresh

                    snapshot, _ = prepare_artwork_refresh(snapshot, artwork_receipts, previous=old)
                payload = snapshot.model_dump(mode="json", by_alias=True)
                if old is not None:
                    atomic_json(self.previous_path, old.model_dump(mode="json", by_alias=True))
                atomic_json(self.path, payload)
                self._signature = None
                self._cached = snapshot
                self.record_attempt(success=True)
            return snapshot
        except (OSError, ValueError):
            self.record_attempt(success=False, code="validation-or-publication-failed")
            raise

    def status(self) -> Status:
        state = self._state()
        try:
            snapshot = self.read()
        except SnapshotUnavailable:
            snapshot = None

        def date(key: str) -> datetime | None:
            try:
                value = datetime.fromisoformat(state[key].replace("Z", "+00:00"))
                return value if value.tzinfo is not None else None
            except (KeyError, TypeError, ValueError, AttributeError):
                return None

        freshness = "unavailable"
        if snapshot:
            stale = (
                now() - snapshot.generated_at > self.stale_after
                or self._read_failed
                or state.get("lastAttemptSucceeded") is False
                or any(x.state != "complete" for x in snapshot.coverage)
            )
            freshness = "stale" if stale else "fresh"
        return Status(
            state=freshness,
            snapshot_id=snapshot.snapshot_id if snapshot else None,
            generated_at=snapshot.generated_at if snapshot else None,
            last_attempt_at=date("lastAttemptAt"),
            last_success_at=date("lastSuccessAt"),
            resource_count=len(snapshot.resources) if snapshot else 0,
            coverage=snapshot.coverage if snapshot else [],
        )


def merge_snapshot(previous: Snapshot, incoming: Snapshot) -> Snapshot:
    """Refresh observed records without treating a bounded pass as deletion authority."""
    if incoming.generated_at < previous.generated_at:
        raise ValueError("A refresh cannot move snapshot time backwards")
    resources = {x.id: x for x in previous.resources}
    resources.update({x.id: x for x in incoming.resources})
    categories = {x.id: x for x in previous.categories}
    categories.update({x.id: x for x in incoming.categories})
    incoming_ids = {r.id for r in incoming.resources}
    incoming_coverage = {c.category_id: c for c in incoming.coverage}
    coverage = []
    for category_id in categories:
        count = sum(category_id in r.category_ids for r in resources.values())
        retained = any(
            r.id not in incoming_ids and category_id in r.category_ids for r in resources.values()
        )
        observed = incoming_coverage.get(category_id)
        state = "partial" if retained or observed is None else observed.state
        discovered = observed.discovered if observed else None
        if discovered is not None and discovered < count:
            discovered = None
        if state == "complete" and discovered != count:
            state = "partial"
        coverage.append(
            Coverage(category_id=category_id, state=state, discovered=discovered, collected=count)
        )
    return assemble_snapshot(
        incoming.generated_at, list(categories.values()), list(resources.values()), coverage
    )
