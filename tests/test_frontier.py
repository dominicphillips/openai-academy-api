from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta

import pytest
from test_collector import Backend

from openai_academy_api import cli
from openai_academy_api.collector import Collector, make_plan, session_request
from openai_academy_api.frontier import Frontier, next_pass, simulate

LISTING = "https://academy.openai.com/pages/courses"
COURSE = "https://academy.openai.com/public/courses/"


def receipt(url: str, minutes_ago: int, status: int = 200) -> dict:
    checked = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return {
        "url": url,
        "status": status,
        "bytes": 10,
        "sha256": "b" * 64,
        "checkedAt": checked.isoformat(),
    }


def row(url: str, *sources: str) -> dict:
    return {"url": url, "provenance": {"sourceUrls": list(sources) or [url]}}


def saved_run() -> tuple[dict, dict]:
    receipts = {
        "runId": "run-1",
        "requests": [
            receipt("https://academy.openai.com/robots.txt", 9),
            receipt(LISTING, 8),
            receipt(COURSE + "fetched-a", 7),
            receipt("https://academy.openai.com/public/clubs", 6, status=404),
        ],
    }
    artifact = {
        "resources": [
            row(COURSE + "fetched-a", COURSE + "fetched-a", LISTING),
            row(COURSE + "listed-b", LISTING),
            row(COURSE + "listed-c", LISTING),
            # Its listing page failed, so nothing vouches for this link.
            row(COURSE + "orphan-d", "https://academy.openai.com/public/clubs"),
            row("https://example.com/elsewhere", LISTING),
            row("https://academy.openai.com/public/courses/x/lessons/1", LISTING),
        ]
    }
    return artifact, receipts


def test_bootstrap_queues_only_vouched_public_discoveries(tmp_path):
    artifact, receipts = saved_run()
    result = Frontier(tmp_path).record(artifact, receipts, run_id="run-1")
    state = Frontier(tmp_path).read()
    assert result == {"added": 2, "fetched": 3, "unfetched": 2, "total": 4}
    assert sorted(state["urls"]) == sorted(
        [LISTING, COURSE + "fetched-a", COURSE + "listed-b", COURSE + "listed-c"]
    )
    assert state["urls"][COURSE + "listed-b"]["discoveredFrom"] == [LISTING]
    assert state["urls"][COURSE + "listed-b"]["lastFetchedAt"] is None
    assert state["urls"][LISTING]["lastRunId"] == "run-1"


def test_passes_take_unfetched_first_then_oldest_fetched(tmp_path):
    artifact, receipts = saved_run()
    store = Frontier(tmp_path)
    store.record(artifact, receipts, run_id="run-1")
    state = store.read()
    assert next_pass(state, 3) == [COURSE + "listed-b", COURSE + "listed-c", LISTING]
    days = simulate(state, 2, 3)
    assert days == [
        [COURSE + "listed-b", COURSE + "listed-c"],
        [LISTING, COURSE + "fetched-a"],
        [COURSE + "listed-b", COURSE + "listed-c"],
    ]
    assert store.read() == state  # A preview never writes queue state.


def test_url_that_failed_in_a_published_run_waits_behind_older_fetches(tmp_path):
    artifact, receipts = saved_run()
    store = Frontier(tmp_path)
    store.record(artifact, receipts, run_id="run-1")
    failed = {"runId": "run-2", "requests": [receipt(COURSE + "listed-b", 0, status=404)]}
    store.record({"resources": []}, failed, run_id="run-2")
    urls = store.read()["urls"]
    assert urls[COURSE + "listed-b"]["lastFetchedAt"] is None
    assert next_pass(store.read(), 4) == [
        COURSE + "listed-c",
        LISTING,
        COURSE + "fetched-a",
        COURSE + "listed-b",
    ]


def test_unpublished_run_keeps_queue_position_and_adds_discoveries(tmp_path):
    artifact, receipts = saved_run()
    store = Frontier(tmp_path)
    store.record({"resources": []}, receipts, run_id="run-0")
    before = store.read()["urls"][COURSE + "fetched-a"]["lastFetchedAt"]
    receipts["requests"][2] = receipt(COURSE + "fetched-a", 1)
    extra = [{"url": COURSE + "private-e", "sourceUrl": LISTING}]
    store.record(artifact, receipts, run_id="run-1", extra=extra, mark_fetched=False)
    urls = store.read()["urls"]
    assert urls[COURSE + "fetched-a"]["lastFetchedAt"] == before
    assert urls[COURSE + "private-e"]["lastFetchedAt"] is None
    assert len(urls) == 5


def test_failed_publication_still_queues_listing_only_links(tmp_path, artifact):
    plan = make_plan()
    backend = Backend(plan, artifact)
    fetched = artifact["resources"][0]["url"]
    backend.artifact["resources"].append(
        {**artifact["resources"][0], "url": COURSE + "listed-only", "title": "Listed only"}
    )
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", backend)
    with pytest.raises(ValueError):
        collector.start(plan, session_request(plan, "Mounted instructions."))
    urls = Frontier(tmp_path / "runs").read()["urls"]
    assert urls[COURSE + "listed-only"]["discoveredFrom"] == [fetched]
    assert all(entry["lastFetchedAt"] is None for entry in urls.values())


def test_published_run_moves_fetched_urls_behind_unfetched(tmp_path, artifact):
    plan = make_plan()
    collector = Collector(tmp_path / "runs", tmp_path / "snapshot.json", Backend(plan, artifact))
    result = collector.start(plan, session_request(plan, "Mounted instructions."))
    assert result["state"] == "published" and result["frontier"]["state"] == "recorded"
    urls = Frontier(tmp_path / "runs").read()["urls"]
    assert {r["url"] for r in artifact["resources"]} <= set(urls)
    assert all(urls[r["url"]]["lastRunId"] == plan.run_id for r in artifact["resources"])


def test_frontier_plan_cli_needs_no_key_or_network(tmp_path, monkeypatch, capsys):
    artifact, receipts = saved_run()
    Frontier(tmp_path).record(artifact, receipts, run_id="run-1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("network used"))
    argv = ["academy-collector", "--state-dir", str(tmp_path), "frontier", "plan"]
    monkeypatch.setattr(sys, "argv", [*argv, "--max-pages", "3", "--passes", "2"])
    cli.collect()
    output = json.loads(capsys.readouterr().out)
    assert output["live"] is False and output["unfetched"] == 2
    assert output["passes"][0]["urls"] == [COURSE + "listed-b", COURSE + "listed-c"]
    assert output["passes"][1]["urls"] == [LISTING, COURSE + "fetched-a"]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "academy-collector",
            "--state-dir",
            str(tmp_path),
            "dry-run",
            "--from-frontier",
            "--max-pages",
            "3",
        ],
    )
    cli.collect()
    plan = json.loads(capsys.readouterr().out)["plan"]
    assert plan["seedUrls"] == [COURSE + "listed-b", COURSE + "listed-c"]
