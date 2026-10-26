from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from email.message import Message
from io import BytesIO

import pytest
from pydantic import ValidationError

from openai_academy_api.fetch_public import FetchBlocked, PublicFetcher
from openai_academy_api.models import CollectionArtifact
from openai_academy_api.security import public_academy_url, stable_id


@pytest.mark.parametrize(
    "url",
    [
        "http://academy.openai.com/public/courses/a",
        "https://academy.openai.com.evil.example/public/courses/a",
        "https://academy.openai.com@evil.example/public/courses/a",
        "https://user:secret@academy.openai.com/public/courses/a",
        "https://127.0.0.1/public/courses/a",
        "https://[::1]/public/courses/a",
        "https://169.254.169.254/latest/meta-data/",
        "https://academy.openai.com:444/public/courses/a",
        "https://academy.openai.com/public/courses/%2e%2e/login",
        "https://academy.openai.com/public/courses/%252e%252e/login",
        "https://academy.openai.com/public/courses/a/lessons/secret",
        "https://academy.openai.com/public/clubs/builders/members",
        "https://academy.openai.com/sitemap/forum/sitemap.xml",
        "https://academy.openai.com/public/videos/a\\b",
        "https://academy.openai.com/public/videos/a%0d%0aHost:evil",
    ],
)
def test_exact_hosts_and_public_resource_paths(url):
    with pytest.raises(ValueError):
        public_academy_url(url, discovery=True)


def test_alias_tracking_normalization_and_id_stability():
    a = "https://academy.openai.com/public/courses/ai-foundations-juzjs"
    b = "https://academy.openai.com/home/courses/ai-foundations-juzjs?tracking=yes#overview"
    assert public_academy_url(b) == a
    assert stable_id(a) == stable_id(b)


def test_unknown_media_permission_is_rejected(artifact):
    artifact["resources"][0]["media"] = [
        {
            "kind": "video",
            "url": "https://vimeo.com/123",
            "permission": "unknown",
            "permissionEvidenceUrl": artifact["resources"][0]["url"],
        }
    ]
    with pytest.raises(ValidationError):
        CollectionArtifact.model_validate_json(json.dumps(artifact))


class Response(BytesIO):
    status = 200

    def __init__(self, body, content_type):
        super().__init__(body)
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read1(self, size):
        return self.read(size)


class Opener:
    def __init__(self, robots=b"User-agent: *\nAllow: /\n"):
        self.calls = []
        self.robots = robots

    def open(self, request, timeout):
        self.calls.append(request.full_url)
        assert request.method == "GET"
        return Response(
            self.robots if request.full_url.endswith("robots.txt") else b"<html></html>",
            "text/plain" if request.full_url.endswith("robots.txt") else "text/html",
        )


def plan():
    return {
        "runId": "fixture-run",
        "deadlineAt": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
        "maxPages": 2,
        "maxResponseBytes": 1024,
        "requestDelaySeconds": 0.5,
    }


def test_fetcher_enforces_budget_and_records_robots(tmp_path, monkeypatch):
    monkeypatch.setattr("openai_academy_api.fetch_public.time.sleep", lambda _: None)
    fetcher = PublicFetcher(plan(), tmp_path)
    opener = Opener()
    fetcher.opener = opener
    result = fetcher.fetch("https://academy.openai.com/pages/courses")
    assert result["requests"] == 2
    assert len(opener.calls) == 2
    with pytest.raises(FetchBlocked, match="budget"):
        fetcher.fetch("https://academy.openai.com/public/content")
    assert len(opener.calls) == 2
    receipts = json.loads(fetcher.receipts_path.read_text())
    assert receipts["robotsChecked"] is True
    assert all(r["sha256"] for r in receipts["requests"])


def test_robots_denial_and_ssrf_do_not_fetch_target(tmp_path):
    fetcher = PublicFetcher(plan(), tmp_path)
    opener = Opener(b"User-agent: *\nDisallow: /public/videos/\n")
    fetcher.opener = opener
    with pytest.raises(FetchBlocked, match="robots"):
        fetcher.fetch("https://academy.openai.com/public/videos/not-permitted")
    assert opener.calls == ["https://academy.openai.com/robots.txt"]
    with pytest.raises(ValueError):
        fetcher.fetch("https://localhost/secret")
    assert len(opener.calls) == 1
