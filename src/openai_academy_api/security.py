"""URL policy shared by artifact validation and the sandbox fetch helper."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import unquote, urlsplit, urlunsplit

ACADEMY_HOST = "academy.openai.com"
SOURCE_HOSTS = frozenset({ACADEMY_HOST, "openai.com", "help.openai.com"})
MEDIA_HOSTS = frozenset(
    {
        "vimeo.com",
        "www.youtube.com",
        "youtu.be",
        "cdn.openai.com",
        "cdn.gradual.com",
        "d2xo500swnpgl1.cloudfront.net",
    }
)
NETWORK_HOSTS = (ACADEMY_HOST,)


def checked_https_url(value: str, hosts: frozenset[str]) -> str:
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError("Invalid URL")
    if any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError("URL contains unsafe characters")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc
    if parts.scheme != "https" or parts.hostname not in hosts:
        raise ValueError("URL host is not allowed")
    if parts.username is not None or parts.password is not None or port not in (None, 443):
        raise ValueError("URL credentials and nonstandard ports are not allowed")
    # Repeated decoding catches encoded traversal and delimiter smuggling.
    decoded = parts.path
    for _ in range(3):
        decoded = unquote(decoded)
    if "\\" in decoded or "//" in decoded or any(x in (".", "..") for x in decoded.split("/")):
        raise ValueError("Unsafe URL path")
    if any(ord(c) < 32 or ord(c) == 127 for c in decoded):
        raise ValueError("Unsafe URL path")
    return urlunsplit(("https", parts.hostname, parts.path or "/", parts.query, ""))


def public_academy_url(value: str, *, discovery: bool = False) -> str:
    url = checked_https_url(value, frozenset({ACADEMY_HOST}))
    p = urlsplit(url)
    path = p.path
    # These are observed anonymous aliases, not permission to open lesson endpoints.
    if path.startswith("/home/"):
        path = "/public/" + path[len("/home/") :]
    segments = unquote(path).lower().split("/")
    if any(
        s
        in {
            "lessons",
            "lesson",
            "forum",
            "forums",
            "members",
            "people",
            "login",
            "activation",
            "integrations",
            "viewonly",
            "widgets",
        }
        for s in segments
    ):
        raise ValueError("Nonpublic or excluded Academy path")
    if path.startswith("/public/clubs/"):
        allowed = bool(
            re.fullmatch(
                r"/public/clubs(?:/[a-zA-Z0-9_-]+)?(?:/(?:overview|content|resources|videos|events)"
                r"(?:/[a-zA-Z0-9_-]+)?)?/?",
                path,
            )
        )
    else:
        allowed = bool(
            re.fullmatch(
                r"/public/(?:courses|blogs|videos|resources|events|collections|external-content)"
                r"(?:/[a-zA-Z0-9_-]+)?/?",
                path,
            )
        ) or path in {"/pages/courses", "/public/content", "/public/clubs"}
    if discovery:
        allowed = allowed or path in {
            "/",
            "/robots.txt",
            "/sitemap.xml",
            "/sitemap/content/sitemap.xml",
            "/sitemap/events/sitemap.xml",
            "/sitemap/clubs/sitemap.xml",
        }
    if not allowed:
        raise ValueError("Academy path is outside public learning resources")
    # Canonical resource identities exclude navigation, tracking and fragments.
    return urlunsplit(("https", ACADEMY_HOST, path.rstrip("/") or "/", "", ""))


def source_url(value: str) -> str:
    url = checked_https_url(value, SOURCE_HOSTS)
    if urlsplit(url).hostname == ACADEMY_HOST:
        return public_academy_url(url, discovery=True)
    p = urlsplit(url)
    if p.query:
        raise ValueError("Source URLs cannot contain query parameters")
    return url


def stable_id(url: str) -> str:
    canonical = public_academy_url(url)
    return "oa_" + hashlib.sha256(canonical.encode()).hexdigest()[:24]
