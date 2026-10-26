"""GET-only fetch helper staged in the managed sandbox; no third-party dependencies."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import UTC, datetime
from pathlib import Path

try:
    from .security import public_academy_url
except ImportError:  # Staged beside security.py in the hosted sandbox.
    from security import public_academy_url

USER_AGENT = "AcademyMetadataBot/0.1"
ROBOTS_URL = "https://academy.openai.com/robots.txt"
CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "text/xml",
    "application/xml",
    "application/json",
    "application/ld+json",
}


class FetchBlocked(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FetchBlocked("Redirects require a separately validated public URL")


class PublicFetcher:
    def __init__(self, plan: dict, workspace: Path):
        self.plan = plan
        self.workspace = workspace
        self.cache = workspace / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.receipts_path = workspace / "outputs" / "fetch-receipts.json"
        self.receipts_path.parent.mkdir(parents=True, exist_ok=True)
        self.deadline = datetime.fromisoformat(plan["deadlineAt"].replace("Z", "+00:00"))
        if self.deadline.tzinfo is None:
            raise FetchBlocked("Deadline must have a timezone")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def _save(self, value: dict) -> None:
        temporary = self.receipts_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n")
        os.replace(temporary, self.receipts_path)

    def _remaining(self) -> float:
        remaining = (self.deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise FetchBlocked("Collection deadline reached")
        return remaining

    def _request(self, url: str, state: dict) -> bytes:
        url = public_academy_url(url, discovery=True)
        if len(state["requests"]) >= self.plan["maxPages"]:
            raise FetchBlocked("Request budget reached")
        self._remaining()
        delay = max(0.5, self.plan["requestDelaySeconds"])
        last = state.get("lastRequestAt", 0)
        wait = max(0, delay - (time.time() - last))
        if wait >= self._remaining():
            raise FetchBlocked("Insufficient time for request spacing")
        time.sleep(wait)
        record = {
            "url": url,
            "checkedAt": datetime.now(UTC).isoformat(),
            "status": None,
            "bytes": 0,
            "sha256": None,
            "contentType": None,
        }
        state["requests"].append(record)
        state["lastRequestAt"] = time.time()
        self._save(state)  # Count the attempt before making the network request.
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html, application/xml, text/plain, application/json",
            },
            method="GET",
        )
        try:
            with self.opener.open(request, timeout=min(15, self._remaining())) as response:
                record["status"] = response.status
                content_type = response.headers.get_content_type()
                record["contentType"] = content_type
                if content_type not in CONTENT_TYPES:
                    raise FetchBlocked("Response is not public text metadata")
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > self.plan["maxResponseBytes"]:
                    raise FetchBlocked("Response exceeds size limit")
                body = bytearray()
                while True:
                    self._remaining()
                    chunk = response.read1(
                        min(65536, self.plan["maxResponseBytes"] + 1 - len(body))
                    )
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > self.plan["maxResponseBytes"]:
                        raise FetchBlocked("Response exceeds size limit")
                record["bytes"] = len(body)
                record["sha256"] = hashlib.sha256(body).hexdigest()
                return bytes(body)
        except urllib.error.HTTPError as exc:
            record["status"] = exc.code
            raise FetchBlocked(f"HTTP request failed with status {exc.code}") from None
        finally:
            self._save(state)

    def fetch(self, value: str) -> dict:
        url = public_academy_url(value, discovery=True)
        with (self.cache / "fetch.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.receipts_path.exists():
                state = json.loads(self.receipts_path.read_text())
                if state["runId"] != self.plan["runId"]:
                    raise FetchBlocked("Workspace belongs to another run")
            else:
                state = {
                    "schemaVersion": 1,
                    "runId": self.plan["runId"],
                    "requests": [],
                    "robotsChecked": False,
                }
            robots_path = self.cache / "robots.txt"
            if not state["robotsChecked"]:
                robots = self._request(ROBOTS_URL, state)
                robots_path.write_bytes(robots)
                state["robotsChecked"] = True
                self._save(state)
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(robots_path.read_text().splitlines())
            if not parser.can_fetch(USER_AGENT, url):
                raise FetchBlocked("robots.txt disallows this URL")
            crawl_delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*")
            if crawl_delay:
                self.plan["requestDelaySeconds"] = max(
                    crawl_delay, self.plan["requestDelaySeconds"]
                )
            if url == ROBOTS_URL:
                data = robots_path.read_bytes()
            else:
                data = self._request(url, state)
            destination = self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".body")
            destination.write_bytes(data)
            return {
                "url": url,
                "path": str(destination),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "requests": len(state["requests"]),
            }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--plan", type=Path, default=Path("/workspace/input/collection-plan.json"))
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    args = parser.parse_args()
    fetcher = PublicFetcher(json.loads(args.plan.read_text()), args.workspace)
    try:
        print(json.dumps(fetcher.fetch(args.url)))
    except (ValueError, OSError, urllib.error.URLError) as exc:
        parser.exit(1, f"Fetch blocked: {exc}\n")


if __name__ == "__main__":
    main()
