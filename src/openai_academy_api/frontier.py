"""Private URL frontier for bounded daily collection passes. Public routes never read it."""

from __future__ import annotations

import copy
import fcntl
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .security import public_academy_url
from .storage import atomic_json, bounded_json, now

FRONTIER_FILE = "frontier.json"
ROBOTS_URL = "https://academy.openai.com/robots.txt"
MAX_URLS = 5000


def _url(value: object) -> str | None:
    try:
        return public_academy_url(value, discovery=True) if isinstance(value, str) else None
    except ValueError:
        return None


def successful_urls(receipts: dict, *, success: bool = True) -> dict[str, str]:
    """Map each URL with a successful (or, with success=False, failed) receipt to its check time."""
    found: dict[str, str] = {}
    requests = receipts.get("requests")
    for receipt in requests if isinstance(requests, list) else []:
        if not isinstance(receipt, dict) or (receipt.get("status") == 200) is not success:
            continue
        url, checked = _url(receipt.get("url")), receipt.get("checkedAt")
        if url and isinstance(checked, str) and checked > found.get(url, ""):
            found[url] = checked
    return found


def discoveries(artifact: dict, receipts: dict, extra: list | None = None) -> list[dict]:
    """Return listing-only links: public URLs without their own successful receipt.

    Links come from the private discoveries output, or from older artifacts that put them
    in resources. Each counts only when a listing page that names it has a successful
    receipt. They are queued for a later pass and are never published.
    """
    fetched = successful_urls(receipts)
    rows = artifact.get("resources")
    rows = list(rows) if isinstance(rows, list) else []
    for item in extra or []:
        if isinstance(item, dict):
            rows.append(
                {"url": item.get("url"), "provenance": {"sourceUrls": [item.get("sourceUrl")]}}
            )
    found: dict[str, set[str]] = {}
    for row in rows:
        if not isinstance(row, dict) or (url := _url(row.get("url"))) is None or url in fetched:
            continue
        provenance = row.get("provenance")
        sources = provenance.get("sourceUrls") if isinstance(provenance, dict) else None
        if not isinstance(sources, list):
            continue
        listings = {s for s in map(_url, sources) if s and s != url and s in fetched}
        if listings:
            found.setdefault(url, set()).update(listings)
    return [{"url": url, "discoveredFrom": sorted(found[url])} for url in sorted(found)]


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _seen(entry: dict) -> datetime | None:
    times = [t for t in (entry["lastFetchedAt"], entry.get("lastAttemptAt")) if t]
    return max(map(_time, times)) if times else None


def next_pass(state: dict, max_urls: int) -> list[str]:
    """Pick never-tried URLs first, then the URLs fetched or tried longest ago.

    A URL that failed in a published run waits its turn, so a lasting 404 cannot take
    part of every day's budget.
    """
    entries = [(u, e, _seen(e)) for u, e in state["urls"].items()]
    fresh = sorted((_time(e["discoveredAt"]), u) for u, e, seen in entries if seen is None)
    rest = sorted((seen, u) for u, e, seen in entries if seen is not None)
    return [url for _, url in fresh + rest][: max(max_urls, 0)]


def simulate(state: dict, max_urls: int, passes: int) -> list[list[str]]:
    """Show the next daily passes as if each one succeeded. Never writes state."""
    state, plans = copy.deepcopy(state), []
    for day in range(passes):
        picks = next_pass(state, max_urls)
        stamp = (now() + timedelta(days=day + 1)).isoformat()
        for url in picks:
            state["urls"][url]["lastFetchedAt"] = stamp
        plans.append(picks)
    return plans


class Frontier:
    """Queue state lives beside run journals in the private collector state directory."""

    def __init__(self, state_dir: Path):
        self.path = state_dir / FRONTIER_FILE

    def read(self) -> dict:
        try:
            state = json.loads(bounded_json(self.path))
        except FileNotFoundError:
            return {"schemaVersion": 1, "updatedAt": None, "urls": {}}
        if state.get("schemaVersion") != 1 or not isinstance(state.get("urls"), dict):
            raise ValueError("Unsupported frontier file")
        return state

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (self.path.parent / ".frontier.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Another frontier update is in progress") from None
            yield

    def record(
        self,
        artifact: dict,
        receipts: dict,
        *,
        run_id: str | None,
        extra: list | None = None,
        mark_fetched: bool = True,
    ) -> dict:
        """Merge one run's discoveries and, once published, its fetches. Never drops URLs."""
        fetched = successful_urls(receipts) if mark_fetched else {}
        failed = successful_urls(receipts, success=False) if mark_fetched else {}
        found = discoveries(artifact, receipts, extra)
        with self._locked():
            state = self.read()
            urls, stamp, added = state["urls"], now().isoformat(), 0
            blank = {"discoveredFrom": [], "lastFetchedAt": None, "lastRunId": None}
            for item in found:
                if item["url"] not in urls and len(urls) >= MAX_URLS:
                    continue
                if item["url"] not in urls:
                    urls[item["url"]] = {**blank, "discoveredAt": stamp}
                    added += 1
                entry = urls[item["url"]]
                entry["discoveredFrom"] = sorted(
                    {*entry["discoveredFrom"], *item["discoveredFrom"]}
                )
            for url, checked in fetched.items():
                if url == ROBOTS_URL or (url not in urls and len(urls) >= MAX_URLS):
                    continue
                entry = urls.setdefault(url, {**blank, "discoveredAt": checked})
                if not entry["lastFetchedAt"] or _time(checked) > _time(entry["lastFetchedAt"]):
                    entry.update(lastFetchedAt=checked, lastRunId=run_id)
            for url, checked in failed.items():
                entry = urls.get(url)
                if entry is not None and not (
                    entry.get("lastAttemptAt") and _time(entry["lastAttemptAt"]) >= _time(checked)
                ):
                    entry["lastAttemptAt"] = checked
            state["updatedAt"] = stamp
            atomic_json(self.path, state)
        unfetched = sum(1 for e in urls.values() if not e["lastFetchedAt"])
        return {"added": added, "fetched": len(fetched), "unfetched": unfetched, "total": len(urls)}
