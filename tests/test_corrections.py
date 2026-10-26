from __future__ import annotations

import copy
import json

import pytest
from test_collector import Backend

from openai_academy_api import corrections
from openai_academy_api.collector import Collector, make_plan, session_request
from openai_academy_api.storage import SnapshotStore

COVER = {
    "url": "https://d2xo500swnpgl1.cloudfront.net/cover.png",
    "sourceUrl": "https://academy.openai.com/pages/courses",
    "alt": None,
}


def fix(artifact: dict, sha: str = "a" * 64, **fields) -> dict:
    url = artifact["resources"][0]["url"]
    return {"url": url, "sourceSha256": sha, "fields": fields, "reason": "Verified by hand."}


def test_correction_applies_only_to_the_verified_page(artifact):
    item = fix(artifact, **{"duration.pathMinutes": None, "level": None})
    artifact["resources"][0]["duration"]["pathMinutes"] = 100
    url = artifact["resources"][0]["url"]
    result, notes = corrections.apply(
        artifact, receipts={url: "a" * 64}, previous={}, corrections=[item]
    )
    assert result["resources"][0]["duration"]["pathMinutes"] is None
    assert artifact["resources"][0]["duration"]["pathMinutes"] == 100  # Input unchanged.
    assert notes == [
        {"url": url, "state": "corrected", "fields": ["duration.pathMinutes", "level"]}
    ]


def test_changed_source_keeps_the_published_record_for_review(tmp_path, artifact, write_artifact):
    path = tmp_path / "snapshot.json"
    verified = copy.deepcopy(artifact)
    verified["resources"][0]["summary"] = "Verified summary."
    SnapshotStore(path).publish(write_artifact(verified), method="manual")
    state = tmp_path / "runs"
    state.mkdir()
    item = fix(artifact, sha="c" * 64, summary="Verified summary.")
    (state / "corrections.json").write_text(json.dumps({"schemaVersion": 1, "corrections": [item]}))
    artifact["resources"][0]["summary"] = "Template text copied from another course."
    plan = make_plan()
    result = Collector(state, path, Backend(plan, artifact)).start(
        plan, session_request(plan, "Mounted instructions.")
    )
    assert result["state"] == "published"
    assert result["review"] == [
        {"url": item["url"], "state": "held-for-review", "reason": "source changed"}
    ]
    kept = next(r for r in SnapshotStore(path).read().resources if r.url == item["url"])
    assert kept.summary == "Verified summary." and kept.provenance.method == "manual"


def test_changed_source_without_published_record_is_not_published(artifact):
    url = artifact["resources"][0]["url"]
    result, _ = corrections.apply(
        artifact, receipts={url: "c" * 64}, previous={}, corrections=[fix(artifact, level=None)]
    )
    assert url not in {r["url"] for r in result["resources"]}
    work = next(c for c in result["coverage"] if c["categoryId"] == "work")
    assert work == {"categoryId": "work", "state": "partial", "discovered": 1, "collected": 0}


def test_extractor_omission_keeps_the_verified_cover(artifact):
    url = artifact["resources"][0]["url"]
    published = copy.deepcopy(artifact["resources"][0])
    published["artwork"] = COVER
    published["provenance"]["sourceUrls"].append(COVER["sourceUrl"])
    result, notes = corrections.apply(
        artifact, receipts={url: "a" * 64}, previous={url: published}, corrections=[]
    )
    assert result["resources"][0]["artwork"] == COVER
    assert COVER["sourceUrl"] in result["resources"][0]["provenance"]["sourceUrls"]
    assert notes == [{"url": url, "state": "cover-retained"}]


@pytest.mark.parametrize(
    "value",
    [
        {"schemaVersion": 2, "corrections": []},
        {"schemaVersion": 1, "corrections": [{"url": "x", "fields": {"level": None}}]},
        {
            "schemaVersion": 1,
            "corrections": [{"url": "x", "sourceSha256": "a" * 64, "fields": {}, "reason": "r"}],
        },
    ],
)
def test_malformed_corrections_are_rejected(tmp_path, value):
    (tmp_path / "corrections.json").write_text(json.dumps(value))
    with pytest.raises(ValueError):
        corrections.load(tmp_path)


def test_daily_publication_applies_saved_corrections(tmp_path, artifact):
    state = tmp_path / "runs"
    state.mkdir()
    item = fix(artifact, summary="Verified summary.")
    (state / "corrections.json").write_text(json.dumps({"schemaVersion": 1, "corrections": [item]}))
    plan = make_plan()
    result = Collector(state, tmp_path / "snapshot.json", Backend(plan, artifact)).start(
        plan, session_request(plan, "Mounted instructions.")
    )
    assert result["state"] == "published"
    assert result["review"] == [{"url": item["url"], "state": "corrected", "fields": ["summary"]}]
    snapshot = SnapshotStore(tmp_path / "snapshot.json").read()
    assert (
        next(r for r in snapshot.resources if r.url == item["url"]).summary == "Verified summary."
    )
