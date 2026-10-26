from __future__ import annotations

import copy
import json
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest
from test_collector import Backend
from test_security import Response
from test_security import plan as fetch_plan

from openai_academy_api.artwork_refresh import prepare_artwork_refresh
from openai_academy_api.cli import collect
from openai_academy_api.collector import Collector, make_plan, session_request
from openai_academy_api.course_artwork import apply_course_artwork, parse_course_page
from openai_academy_api.fetch_public import PublicFetcher
from openai_academy_api.models import CollectionArtifact, Snapshot, build_snapshot
from openai_academy_api.storage import SnapshotStore

PARENT_URL = "https://academy.openai.com/public/courses/ai-foundations-dnq5w"
CHILD_URL = "https://academy.openai.com/public/courses/ai-foundations-juzjs"
ROBOTS_URL = "https://academy.openai.com/robots.txt"
COVER_URL = "https://d2xo500swnpgl1.cloudfront.net/uploads/oaiacademy/square.jpeg"
BANNER_URL = "https://d2xo500swnpgl1.cloudfront.net/uploads/oaiacademy/wide.jpeg"
PARENT = {
    "id": "6aa029e413151ab4c6afe5fe",
    "slug": "ai-foundations-dnq5w",
    "type": "LearningPath",
    "coverUrl": COVER_URL,
    "bannerUrl": None,
    "courseLearningPath": {
        "courses": [{"id": "6a23f24912a1d50cb9b2cf93", "slug": "ai-foundations-juzjs"}]
    },
    "containedInLearningPaths": [],
}
CHILD = {
    "id": "6a23f24912a1d50cb9b2cf93",
    "slug": "ai-foundations-juzjs",
    "type": "SCORM",
    "coverUrl": COVER_URL,
    "bannerUrl": BANNER_URL,
    "containedInLearningPaths": [{"id": PARENT["id"], "slug": PARENT["slug"]}],
}


def page(course):
    payload = {
        "props": {"pageProps": {"data": {"course": {"course": course}}}},
        "participants": [{"avatarUrl": COVER_URL, "name": "Unrelated person"}],
    }
    return (
        '<meta property="og:image" content="https://example.com/generic.jpg">'
        '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"
    ).encode()


def receipt(url, course=None, timestamp=None):
    value = {
        "url": url,
        "status": 200,
        "bytes": 100,
        "sha256": "a" * 64,
        "checkedAt": (timestamp or datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    if course is not None:
        value["courseArtwork"] = parse_course_page(page(course), url)
    return value


def receipts():
    return {
        "robotsChecked": True,
        "requests": [receipt(ROBOTS_URL), receipt(PARENT_URL, PARENT), receipt(CHILD_URL, CHILD)],
    }


def test_parser_reads_only_the_exact_course_and_no_unrelated_page_data():
    metadata = parse_course_page(page(CHILD), CHILD_URL)
    assert metadata["bannerUrl"] == BANNER_URL
    assert "participants" not in json.dumps(metadata) and "avatarUrl" not in json.dumps(metadata)
    assert parse_course_page(page(CHILD), PARENT_URL) is None
    assert parse_course_page(page(CHILD), "https://academy.openai.com/pages/courses") is None
    assert parse_course_page(b'<meta property="og:image" content="generic">', CHILD_URL) is None
    assert parse_course_page(page(CHILD) + page(CHILD), CHILD_URL) is None


@pytest.mark.parametrize("banner", ["https://evil.example/cover.jpg", "http://example.com/a", None])
def test_parser_rejects_unapproved_artwork_hosts(banner):
    course = {**CHILD, "bannerUrl": banner}
    assert parse_course_page(page(course), CHILD_URL)["bannerUrl"] is None


def test_path_uses_verified_child_banner_and_preserves_other_fields(artifact):
    original = copy.deepcopy(artifact)
    updated = apply_course_artwork(artifact, receipts()["requests"])
    row = updated["resources"][0]
    assert row["artwork"] == {"url": BANNER_URL, "alt": None, "sourceUrl": CHILD_URL}
    assert row["provenance"]["sourceUrls"] == [PARENT_URL, CHILD_URL]
    row.pop("artwork")
    row["provenance"]["sourceUrls"].remove(CHILD_URL)
    assert updated == original == artifact
    own_banner = copy.deepcopy(PARENT)
    own_banner["bannerUrl"] = COVER_URL
    values = [receipt(PARENT_URL, own_banner), receipt(CHILD_URL, CHILD)]
    assert apply_course_artwork(artifact, values)["resources"][0]["artwork"]["url"] == COVER_URL


@pytest.mark.parametrize("change", ["child-id", "parent-id", "parent-slug", "child-slug"])
def test_child_banner_requires_exact_reciprocal_ids_and_slugs(artifact, change):
    child = copy.deepcopy(CHILD)
    if change == "child-id":
        child["id"] = "b" * 24
    elif change == "parent-id":
        child["containedInLearningPaths"][0]["id"] = "b" * 24
    elif change == "parent-slug":
        child["containedInLearningPaths"][0]["slug"] = "another-course"
    else:
        child["slug"] = "another-course"
    values = [receipt(PARENT_URL, PARENT), receipt(CHILD_URL, child)]
    artwork = apply_course_artwork(artifact, values)["resources"][0]["artwork"]
    assert artwork == {"url": COVER_URL, "alt": None, "sourceUrl": PARENT_URL}


class PageOpener:
    def __init__(self, failure=None, robots=b"User-agent: *\nAllow: /\n"):
        self.calls = []
        self.failure, self.robots = failure, robots

    def open(self, request, timeout):
        url = request.full_url
        self.calls.append(url)
        if url == CHILD_URL and self.failure:
            raise urllib.error.HTTPError(url, 503, "Unavailable", None, None)
        if url == ROBOTS_URL:
            return Response(self.robots, "text/plain")
        return Response(page(PARENT if url == PARENT_URL else CHILD), "text/html")


@pytest.mark.parametrize("mode", ["success", "budget", "robots", "network"])
def test_fetcher_follows_only_explicit_first_child_within_limits(tmp_path, monkeypatch, mode):
    monkeypatch.setattr("openai_academy_api.fetch_public.time.sleep", lambda _: None)
    plan = fetch_plan()
    plan.update(maxPages=2 if mode == "budget" else 3, maxResponseBytes=10000)
    opener = PageOpener(
        failure=mode == "network",
        robots=(
            b"User-agent: *\nDisallow: /public/courses/ai-foundations-juzjs\n"
            if mode == "robots"
            else b"User-agent: *\nAllow: /\n"
        ),
    )
    fetcher = PublicFetcher(plan, tmp_path)
    fetcher.opener = opener
    result = fetcher.fetch(PARENT_URL)
    assert result["artworkDetailFetched"] is (mode == "success")
    assert result["requests"] <= plan["maxPages"]
    assert opener.calls == [ROBOTS_URL, PARENT_URL] + (
        [CHILD_URL] if mode in {"success", "network"} else []
    )
    fetched = json.loads(fetcher.receipts_path.read_text())["requests"]
    if mode == "success":
        assert fetched[-1]["courseArtwork"]["bannerUrl"] == BANNER_URL
    else:
        prior = {"url": BANNER_URL, "sourceUrl": CHILD_URL, "alt": "Existing cover"}
        row = {
            "url": PARENT_URL,
            "kind": "learning-path",
            "artwork": prior,
            "provenance": {"sourceUrls": [PARENT_URL, CHILD_URL]},
        }
        assert (
            apply_course_artwork({"resources": [row]}, fetched)["resources"][0]["artwork"] == prior
        )


def test_refresh_preserves_semantics_methods_and_unchanged_resource_hashes(artifact):
    original = build_snapshot(
        CollectionArtifact.model_validate_json(json.dumps(artifact)), "manual"
    )
    proof = receipts()
    refreshed, prepared = prepare_artwork_refresh(original, proof)
    before = {row.url: row.model_dump(mode="json", by_alias=True) for row in original.resources}
    for resource in refreshed.resources:
        old = before[resource.url]
        after = resource.model_dump(mode="json", by_alias=True)
        if resource.url != PARENT_URL:
            assert old == after
        else:
            assert old["id"] == after["id"]
            assert after["provenance"]["method"] == old["provenance"]["method"]
            assert set(old["provenance"]["sourceUrls"]) <= set(after["provenance"]["sourceUrls"])
            old.pop("artwork")
            after.pop("artwork")
            for field in ("sourceUrls", "fetchedAt", "contentHash"):
                old["provenance"].pop(field)
                after["provenance"].pop(field)
            assert old == after
    assert len(prepared.resources) == len(original.resources)
    assert refreshed.snapshot_id != original.snapshot_id
    assert prepare_artwork_refresh(original, proof)[0].snapshot_id == refreshed.snapshot_id


def test_verified_cover_survives_semantic_correction_hold(tmp_path, artifact, write_artifact):
    approved = copy.deepcopy(artifact)
    approved["resources"][0]["summary"] = "Approved summary."
    path = tmp_path / "snapshot.json"
    previous = SnapshotStore(path).publish(write_artifact(approved), method="manual")
    state = tmp_path / "runs"
    state.mkdir()
    (state / "corrections.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "corrections": [
                    {
                        "url": PARENT_URL,
                        "sourceSha256": "b" * 64,
                        "fields": {"summary": "Approved summary."},
                        "reason": "Verified.",
                    }
                ],
            }
        )
    )
    plan = make_plan()
    backend = Backend(plan, artifact)
    for item in backend.receipts["requests"]:
        if item["url"] == PARENT_URL:
            item["courseArtwork"] = parse_course_page(page(PARENT), PARENT_URL)
    checked = datetime.fromisoformat(backend.receipts["requests"][0]["checkedAt"])
    backend.receipts["requests"].append(receipt(CHILD_URL, CHILD, checked))
    backend.artifact["fetchReport"]["requests"] = len(backend.receipts["requests"])
    result = Collector(state, path, backend).start(plan, session_request(plan, "Instructions."))
    assert result["review"][0]["state"] == "held-for-review"
    old = next(row for row in previous.resources if row.url == PARENT_URL)
    updated = next(row for row in SnapshotStore(path).read().resources if row.url == PARENT_URL)
    assert updated.artwork.url == BANNER_URL and updated.summary == old.summary
    assert updated.detail == old.detail and updated.duration == old.duration
    assert updated.provenance.method == old.provenance.method == "manual"


def test_refresh_cli_writes_candidates_without_changing_source(
    tmp_path, artifact, write_artifact, monkeypatch, capsys
):
    source = tmp_path / "current.json"
    SnapshotStore(source).publish(write_artifact(artifact), method="manual")
    original = source.read_bytes()
    proof = tmp_path / "receipts.json"
    proof.write_text(json.dumps(receipts()))
    candidate, prepared = tmp_path / "candidate.json", tmp_path / "collection.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "academy-collector",
            "--snapshot",
            str(source),
            "refresh-artwork",
            str(proof),
            "--output",
            str(candidate),
            "--artifact-output",
            str(prepared),
        ],
    )
    collect()
    assert source.read_bytes() == original
    assert Snapshot.model_validate_json(candidate.read_bytes())
    assert CollectionArtifact.model_validate_json(prepared.read_bytes())
    assert json.loads(capsys.readouterr().out)["updated"] == [PARENT_URL]
