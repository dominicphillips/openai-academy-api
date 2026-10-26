import copy
import json

import pytest
from pydantic import ValidationError

from openai_academy_api.models import CollectionArtifact, Snapshot, build_snapshot


def test_sourced_artwork_is_additive_and_changes_hash_not_stable_id(artifact):
    original = build_snapshot(
        CollectionArtifact.model_validate_json(json.dumps(artifact)), "fixture"
    )
    resource = artifact["resources"][0]
    resource["artwork"] = {
        "url": "https://d2xo500swnpgl1.cloudfront.net/uploads/oaiacademy/fixture.jpeg",
        "alt": None,
        "sourceUrl": resource["url"],
    }
    updated = build_snapshot(
        CollectionArtifact.model_validate_json(json.dumps(artifact)), "fixture"
    )
    before = {r.url: r for r in original.resources}[resource["url"]]
    after = {r.url: r for r in updated.resources}[resource["url"]]
    assert before.id == after.id
    assert before.provenance.content_hash != after.provenance.content_hash
    assert original.snapshot_id != updated.snapshot_id
    assert after.artwork.alt is None and after.media == []


def test_old_snapshot_without_artwork_still_validates(artifact):
    snapshot = build_snapshot(
        CollectionArtifact.model_validate_json(json.dumps(artifact)), "fixture"
    )
    old = snapshot.model_dump(mode="json", by_alias=True)
    for resource in old["resources"]:
        resource.pop("artwork")
    loaded = Snapshot.model_validate_json(json.dumps(old))
    assert loaded.snapshot_id == snapshot.snapshot_id
    assert all(r.artwork is None for r in loaded.resources)


@pytest.mark.parametrize(
    "url,source",
    [
        ("https://evil.example/cover.png", None),
        ("http://d2xo500swnpgl1.cloudfront.net/cover.png", None),
        (
            "https://d2xo500swnpgl1.cloudfront.net/cover.png",
            "https://academy.openai.com/public/courses/other",
        ),
    ],
)
def test_artwork_requires_allowed_host_https_and_source_provenance(artifact, url, source):
    value = copy.deepcopy(artifact)
    resource = value["resources"][0]
    resource["artwork"] = {"url": url, "sourceUrl": source or resource["url"], "alt": None}
    with pytest.raises(ValidationError):
        CollectionArtifact.model_validate_json(json.dumps(value))
