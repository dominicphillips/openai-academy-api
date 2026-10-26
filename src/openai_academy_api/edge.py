"""Optional Cloudflare hostname purge, used only by the private collector CLI."""

from __future__ import annotations

import http.client
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ZONE_VARIABLE = "ACADEMY_CLOUDFLARE_ZONE_ID"
HOSTNAME_VARIABLE = "ACADEMY_CLOUDFLARE_HOSTNAME"
TOKEN_FILE_VARIABLE = "ACADEMY_CLOUDFLARE_PURGE_TOKEN_FILE"
HOSTNAME = re.compile(
    r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
)


class PurgeError(RuntimeError):
    """A purge failure whose message never contains the token."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the bearer token to another location.


def _read(stream) -> bytes:
    try:
        return stream.read(65536)
    except Exception:
        return b""


class HostnamePurge:
    """Purge one exact hostname. There is deliberately no whole-zone mode."""

    def __init__(self, zone_id: str, hostname: str, token: str, *, opener=None):
        self.zone_id, self.hostname, self._token = zone_id, hostname, token
        # Like the model client, ignore ambient proxy settings for a private credential.
        self._opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )

    def __repr__(self) -> str:
        return f"HostnamePurge(zone_id={self.zone_id!r}, hostname={self.hostname!r})"

    def __call__(self) -> str | None:
        """Return Cloudflare's request ID. Success means accepted, not yet completed."""
        request = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/purge_cache",
            data=json.dumps({"hosts": [self.hostname]}).encode(),
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=15) as response:
                body = _read(response)
        except urllib.error.HTTPError as exc:
            raise PurgeError(
                f"Cloudflare returned HTTP {exc.code}{self._errors(_read(exc))}"
            ) from None
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise PurgeError(f"Cloudflare purge request failed ({type(exc).__name__})") from None
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if not isinstance(data, dict) or data.get("success") is not True:
            raise PurgeError("Cloudflare did not accept the purge" + self._errors(body))
        result = data.get("result")
        purge_id = result.get("id") if isinstance(result, dict) else None
        if isinstance(purge_id, str) and re.fullmatch(r"[A-Za-z0-9]{1,64}", purge_id):
            return purge_id
        return None

    def _errors(self, body: bytes) -> str:
        try:
            errors = json.loads(body).get("errors") or []
            text = "; ".join(f"{e.get('code')} {e.get('message')}" for e in errors[:3])
        except (AttributeError, TypeError, ValueError):
            return ""
        text = re.sub(r"[^\x20-\x7e]", " ", text).replace(self._token, "[REDACTED]")[:300]
        return f": {text}" if text else ""


def purge_from_environment(environ=None) -> HostnamePurge | None:
    """Read optional deployment settings. Partial or invalid settings fail before collection."""
    environ = os.environ if environ is None else environ
    names = (ZONE_VARIABLE, HOSTNAME_VARIABLE, TOKEN_FILE_VARIABLE)
    zone, hostname, token_file = (environ.get(name, "").strip() for name in names)
    if not (zone or hostname or token_file):
        return None
    if not (zone and hostname and token_file):
        raise ValueError(f"Set all or none of {', '.join(names)}")
    if not re.fullmatch(r"[a-f0-9]{32}", zone):
        raise ValueError(f"{ZONE_VARIABLE} must be a 32-character lowercase hex zone ID")
    if not HOSTNAME.fullmatch(hostname):
        raise ValueError(f"{HOSTNAME_VARIABLE} must be one exact lowercase hostname")
    try:
        with Path(token_file).open("rb") as stream:
            raw = stream.read(4097)
        token = raw.decode("ascii").strip()
    except (OSError, UnicodeError):
        raise ValueError(f"{TOKEN_FILE_VARIABLE} must name a readable token file") from None
    if len(raw) > 4096 or not re.fullmatch(r"[\x21-\x7e]{20,1024}", token):
        raise ValueError(f"{TOKEN_FILE_VARIABLE} must contain exactly one token")
    return HostnamePurge(zone, hostname, token)
