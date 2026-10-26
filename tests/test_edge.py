import io
import json
import urllib.error
import urllib.request

import pytest

from openai_academy_api.edge import HostnamePurge, PurgeError, purge_from_environment

ZONE = "0123456789abcdef0123456789abcdef"
TOKEN = "fixture-purge-token-0123456789"
ACCEPTED = {"success": True, "errors": [], "messages": [], "result": {"id": "abc123"}}


class Opener:
    def __init__(self, status=200, body=ACCEPTED, error=None):
        self.status, self.body, self.error = status, body, error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        payload = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        if self.status != 200:
            raise urllib.error.HTTPError(
                request.full_url, self.status, "rejected", {}, io.BytesIO(payload)
            )
        return io.BytesIO(payload)


def test_purge_sends_one_exact_hostname_and_returns_request_id():
    opener = Opener()
    purge = HostnamePurge(ZONE, "api.example.com", TOKEN, opener=opener)
    assert purge() == "abc123"
    ((request, timeout),) = opener.requests
    assert request.full_url == f"https://api.cloudflare.com/client/v4/zones/{ZONE}/purge_cache"
    assert request.get_method() == "POST" and timeout == 15
    assert json.loads(request.data) == {"hosts": ["api.example.com"]}
    assert request.get_header("Authorization") == f"Bearer {TOKEN}"
    assert request.get_header("Content-type") == "application/json"
    assert TOKEN not in repr(purge)


@pytest.mark.parametrize(
    "opener",
    [
        Opener(status=403, body={"success": False, "errors": [{"code": 10000, "message": TOKEN}]}),
        Opener(body={"success": False, "errors": [{"code": 1134, "message": "Not entitled"}]}),
        Opener(body=b"<html>gateway</html>"),
        Opener(error=urllib.error.URLError("offline")),
        Opener(error=TimeoutError()),
    ],
)
def test_purge_failure_is_reported_without_the_token(opener):
    with pytest.raises(PurgeError) as exc:
        HostnamePurge(ZONE, "api.example.com", TOKEN, opener=opener)()
    assert TOKEN not in str(exc.value)
    assert len(opener.requests) == 1  # No retry and no broader fallback purge.


def test_default_transport_ignores_ambient_proxy_and_never_follows_redirects(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")

    def proxies(opener):
        return [
            h.proxies
            for h in opener.handlers
            if isinstance(h, urllib.request.ProxyHandler) and h.proxies
        ]

    assert proxies(urllib.request.build_opener())  # The default opener would use the proxy.
    purge = HostnamePurge(ZONE, "api.example.com", TOKEN)
    assert proxies(purge._opener) == []
    handlers = purge._opener.handlers
    redirects = [h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
    request = urllib.request.Request("https://api.cloudflare.com/client/v4/")
    assert redirects[0].redirect_request(request, None, 302, "Found", {}, "https://x.test/") is None


def test_configuration_comes_only_from_complete_deployment_environment(tmp_path):
    token_file = tmp_path / "purge-token"
    token_file.write_text(TOKEN + "\n")
    valid = {
        "ACADEMY_CLOUDFLARE_ZONE_ID": ZONE,
        "ACADEMY_CLOUDFLARE_HOSTNAME": "api.example.com",
        "ACADEMY_CLOUDFLARE_PURGE_TOKEN_FILE": str(token_file),
    }
    assert purge_from_environment({}) is None
    purge = purge_from_environment(valid)
    assert purge.zone_id == ZONE and purge.hostname == "api.example.com"
    assert TOKEN not in repr(purge)
    empty, double = tmp_path / "empty", tmp_path / "double"
    empty.write_text("\n")
    double.write_text(f"{TOKEN} {TOKEN}\n")
    for change in [
        {"ACADEMY_CLOUDFLARE_HOSTNAME": ""},
        {"ACADEMY_CLOUDFLARE_ZONE_ID": "not-a-zone"},
        {"ACADEMY_CLOUDFLARE_HOSTNAME": "*.example.com"},
        {"ACADEMY_CLOUDFLARE_HOSTNAME": "https://api.example.com/"},
        {"ACADEMY_CLOUDFLARE_HOSTNAME": "API.example.com"},
        {"ACADEMY_CLOUDFLARE_HOSTNAME": "localhost"},
        {"ACADEMY_CLOUDFLARE_PURGE_TOKEN_FILE": str(tmp_path / "missing")},
        {"ACADEMY_CLOUDFLARE_PURGE_TOKEN_FILE": str(empty)},
        {"ACADEMY_CLOUDFLARE_PURGE_TOKEN_FILE": str(double)},
    ]:
        with pytest.raises(ValueError) as exc:
            purge_from_environment(valid | change)
        assert TOKEN not in str(exc.value)
