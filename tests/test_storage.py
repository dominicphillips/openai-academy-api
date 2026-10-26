from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from openai_academy_api.models import CollectionArtifact, Snapshot
from openai_academy_api.storage import SnapshotStore


def test_failed_refresh_preserves_last_snapshot(tmp_path, artifact, write_artifact):
    path = tmp_path / "snapshot.json"
    store = SnapshotStore(path)
    original = store.publish(write_artifact(artifact), method="fixture")
    before = path.read_bytes()
    artifact["resources"][0]["courseBody"] = "This field must never pass through."
    with pytest.raises(ValidationError):
        store.publish(write_artifact(artifact))
    assert path.read_bytes() == before
    assert store.read().snapshot_id == original.snapshot_id
    assert store.status().state == "stale"


def test_partial_refresh_preserves_prior_resources_and_categories(
    tmp_path, artifact, write_artifact
):
    path = tmp_path / "snapshot.json"
    store = SnapshotStore(path)
    original = store.publish(write_artifact(artifact), method="fixture")
    partial = copy.deepcopy(artifact)
    partial["generatedAt"] = datetime.now(UTC).isoformat()
    partial["resources"] = partial["resources"][:1]
    partial["resources"][0]["summary"] = "Changed metadata from the bounded pass."
    partial["categories"] = partial["categories"][:1]
    partial["coverage"] = [
        {"categoryId": "work", "state": "partial", "discovered": None, "collected": 1}
    ]
    result = store.publish(write_artifact(partial))
    assert len(result.resources) == 3
    assert {c.id for c in result.categories} == {c.id for c in original.categories}
    assert all(c.state == "partial" for c in result.coverage)
    assert result.resources != original.resources
    assert store.status().state == "stale"
    assert json.loads(store.previous_path.read_text())["snapshotId"] == original.snapshot_id


def test_corrupt_disk_keeps_memory_or_persisted_last_good(tmp_path, artifact, write_artifact):
    path = tmp_path / "snapshot.json"
    store = SnapshotStore(path)
    first = store.publish(write_artifact(artifact), method="fixture")
    artifact["generatedAt"] = datetime.now(UTC).isoformat()
    second = store.publish(write_artifact(artifact))
    path.write_text("{invalid}")
    assert store.read().snapshot_id == second.snapshot_id
    assert store.status().state == "stale"
    restarted = SnapshotStore(path)
    assert restarted.read().snapshot_id == first.snapshot_id


@pytest.mark.parametrize("field", ["generated", "fetched"])
def test_future_timestamps_are_rejected(artifact, field):
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    artifact["generatedAt"] = future
    if field == "fetched":
        artifact["resources"][0]["provenance"]["fetchedAt"] = future
    with pytest.raises(ValidationError):
        CollectionArtifact.model_validate_json(json.dumps(artifact))


def test_content_hashes_and_ids_are_verified(tmp_path, artifact, write_artifact):
    snapshot = SnapshotStore(tmp_path / "snapshot.json").publish(write_artifact(artifact))
    data = snapshot.model_dump(mode="json", by_alias=True)
    data["resources"][0]["title"] = "Tampered title"
    with pytest.raises(ValidationError):
        Snapshot.model_validate_json(json.dumps(data))


def test_collection_counts_reject_invented_coverage(artifact):
    artifact["coverage"][0]["collected"] = 2
    artifact["coverage"][0]["discovered"] = 2
    with pytest.raises(ValidationError):
        CollectionArtifact.model_validate_json(json.dumps(artifact))
