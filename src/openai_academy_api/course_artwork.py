"""Resolve course artwork from anonymous Academy page metadata without fetching media."""

from __future__ import annotations

import copy
import json
import re
from html.parser import HTMLParser

try:
    from .security import ARTWORK_HOSTS, checked_https_url, public_academy_url
except ImportError:  # Staged beside security.py in the hosted sandbox.
    from security import ARTWORK_HOSTS, checked_https_url, public_academy_url


class _PageData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts: list[list[str]] = []
        self.active = False

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self.scripts.append([])
            self.active = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.scripts[-1].append(data)


def _identity(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    identifier, slug = value.get("id"), value.get("slug")
    if (
        not isinstance(identifier, str)
        or re.fullmatch(r"[a-f0-9]{24}", identifier) is None
        or not isinstance(slug, str)
        or re.fullmatch(r"[a-zA-Z0-9_-]{1,300}", slug) is None
    ):
        return None
    try:
        public_academy_url("https://academy.openai.com/public/courses/" + slug)
    except ValueError:
        return None
    return {"id": identifier, "slug": slug}


def _image(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return checked_https_url(value, ARTWORK_HOSTS)
    except ValueError:
        return None


def _metadata(value: object) -> dict | None:
    identity = _identity(value)
    if identity is None:
        return None
    path = value.get("courseLearningPath")
    courses = path.get("courses", []) if isinstance(path, dict) else []
    parents = value.get("containedInLearningPaths", [])
    if not isinstance(courses, list) or not isinstance(parents, list):
        return None
    return {
        **identity,
        "type": "LearningPath" if value.get("type") == "LearningPath" else None,
        "bannerUrl": _image(value.get("bannerUrl")),
        "coverUrl": _image(value.get("coverUrl")),
        "courseLearningPath": {"courses": [_identity(item) for item in courses[:200]]},
        "containedInLearningPaths": [_identity(item) for item in parents[:200]],
    }


def _url(identity: dict) -> str:
    return public_academy_url("https://academy.openai.com/public/courses/" + identity["slug"])


def parse_course_page(body: bytes, source_url: str) -> dict | None:
    """Return only cover fields and explicit course relationships for this page's exact slug."""
    try:
        source_url = public_academy_url(source_url)
        if "/public/courses/" not in source_url:
            return None
        parser = _PageData()
        parser.feed(body.decode("utf-8"))
        if len(parser.scripts) != 1:
            return None
        value = json.loads("".join(parser.scripts[0]))
        for key in ("props", "pageProps", "data", "course", "course"):
            value = value[key]
        metadata = _metadata(value)
        return metadata if metadata and _url(metadata) == source_url else None
    except (ValueError, KeyError, TypeError, RecursionError):
        return None


def apply_course_artwork(
    artifact: dict, receipts: list[dict], *, previous: dict[str, dict] | None = None
) -> dict:
    """Change only artwork and its source URLs, using successful source receipts."""
    artifact = copy.deepcopy(artifact)
    courses = {}
    for receipt in receipts:
        if receipt.get("status") != 200:
            continue
        metadata = _metadata(receipt.get("courseArtwork"))
        if metadata is None:
            continue
        try:
            url = public_academy_url(receipt["url"])
            if _url(metadata) == url:
                courses[url] = metadata
        except (KeyError, ValueError, TypeError):
            continue
    for resource in artifact["resources"]:
        url = resource["url"]
        old = (previous or {}).get(url, resource)
        own = courses.get(url)
        if own is None:
            if resource.get("kind") in {"course", "learning-path"} and old.get("artwork"):
                resource["artwork"] = copy.deepcopy(old["artwork"])
                source = old["artwork"]["sourceUrl"]
                if source not in resource["provenance"]["sourceUrls"]:
                    resource["provenance"]["sourceUrls"].append(source)
            continue
        image, source = own["bannerUrl"] or own["coverUrl"], url
        banner = bool(own["bannerUrl"])
        if not own["bannerUrl"] and own["type"] == "LearningPath":
            children = own["courseLearningPath"]["courses"]
            first = children[0] if children else None
            child_url = _url(first) if first else None
            child = courses.get(child_url)
            if (
                child is not None
                and child["id"] == first["id"]
                and child["bannerUrl"]
                and _identity(own) in child["containedInLearningPaths"]
            ):
                image, source = child["bannerUrl"], child_url
                banner = True
        if not banner and own["type"] == "LearningPath" and old.get("artwork"):
            image = old["artwork"]["url"]
            source = old["artwork"]["sourceUrl"]
        sources = resource["provenance"]["sourceUrls"]
        if source not in sources and len(sources) >= 16:
            image, source = own["bannerUrl"] or own["coverUrl"], url
        if image:
            resource["artwork"] = (
                copy.deepcopy(old["artwork"])
                if old.get("artwork")
                and old["artwork"]["url"] == image
                and old["artwork"]["sourceUrl"] == source
                else {"url": image, "alt": None, "sourceUrl": source}
            )
            if source not in sources:
                sources.append(source)
    return artifact
