from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def artifact():
    timestamp = datetime.now(UTC) - timedelta(seconds=2)
    generated = timestamp.isoformat()
    categories = [
        {"id": "work", "label": "Apply AI at Work"},
        {"id": "builders", "label": "Build with AI"},
        {"id": "leaders", "label": "Lead AI Adoption"},
    ]
    resources = []
    for title, slug, category, audience, minutes in [
        ("AI Foundations", "ai-foundations-dnq5w", "work", "knowledge-workers", 70),
        ("Get Started with Codex", "get-started-with-codex-jkhsq", "builders", "developers", 80),
        ("AI Leadership", "ai-leadership-kaf7k", "leaders", "leaders", 180),
    ]:
        url = "https://academy.openai.com/public/courses/" + slug
        resources.append(
            {
                "title": title,
                "url": url,
                "kind": "learning-path",
                "categoryIds": [category],
                "audiences": [audience],
                "tags": [],
                "summary": None,
                "level": None,
                "duration": {"courseMinutes": minutes, "pathMinutes": None, "videoSeconds": None},
                "detail": {"audience": None, "prerequisites": [], "objectives": [], "sections": []},
                "media": [],
                "provenance": {"sourceUrls": [url], "fetchedAt": generated},
            }
        )
    return {
        "schemaVersion": 1,
        "generatedAt": generated,
        "categories": categories,
        "resources": resources,
        "coverage": [
            {"categoryId": c["id"], "state": "complete", "discovered": 1, "collected": 1}
            for c in categories
        ],
        "fetchReport": {"requests": 4, "robotsChecked": True, "completedWithinLimits": True},
    }


@pytest.fixture
def write_artifact(tmp_path):
    def write(value: dict, name="artifact.json") -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return path

    return write
