from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from openai_academy_api.app import create_app
from openai_academy_api.storage import SnapshotStore


def test_read_only_search_filters_and_cursor(tmp_path, artifact, write_artifact):
    target = tmp_path / "snapshot.json"
    store = SnapshotStore(target)
    store.publish(write_artifact(artifact), method="fixture")
    client = TestClient(create_app(target))
    first = client.get("/v1/resources", params={"limit": 1}).json()
    assert first["total"] == 3
    assert first["nextCursor"]
    ids = [first["items"][0]["id"]]
    cursor = first["nextCursor"]
    while cursor:
        page = client.get("/v1/resources", params={"limit": 1, "cursor": cursor})
        assert page.status_code == 200
        ids.extend(r["id"] for r in page.json()["items"])
        cursor = page.json()["nextCursor"]
    assert len(ids) == len(set(ids)) == 3
    assert ids == sorted(ids)
    assert client.get("/v1/resources", params={"q": "  codex  "}).json()["total"] == 1
    assert client.get("/v1/resources", params={"category": "builders"}).json()["total"] == 1
    assert client.get("/v1/resources", params={"audience": "students"}).json()["total"] == 0
    assert client.get("/v1/resources", params={"kind": "video"}).json()["total"] == 0
    assert client.get("/v1/resources", params={"limit": 101}).status_code == 422
    assert client.get("/v1/resources", params={"q": "x" * 201}).status_code == 422
    assert client.get("/v1/resources", params={"kind": "made-up"}).status_code == 422
    assert client.get("/v1/resources", params={"cursor": "not-a-valid-cursor"}).status_code == 400
    assert (
        client.get(
            "/v1/resources", params={"cursor": first["nextCursor"], "q": "Codex"}
        ).status_code
        == 400
    )
    assert client.get("/v1/resources/" + ids[0]).status_code == 200
    assert client.get("/v1/resources/unknown").status_code == 404
    assert client.post("/v1/resources").status_code == 405
    assert client.get("/v1/categories").json()["items"][0]["count"] == 1

    artifact["generatedAt"] = datetime.now(UTC).isoformat()
    artifact["resources"][0]["summary"] = "Updated public metadata."
    store.publish(write_artifact(artifact))
    assert client.get("/v1/resources", params={"cursor": first["nextCursor"]}).status_code == 409


def test_unavailable_and_status_do_not_start_collection(tmp_path, monkeypatch):
    # Importing or serving the app must not need an OpenAI key or network.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(tmp_path / "missing.json"))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 503
    assert client.get("/v1/resources").status_code == 503
    status = client.get("/v1/status")
    assert status.json()["state"] == "unavailable"
    assert "termsReviewRequired" not in status.json()
    assert status.headers["cache-control"] == "no-store"
    assert client.get("/openapi.json").status_code == 200
    assert not list(tmp_path.iterdir())


def test_security_headers_cors_and_frontend_isolation(tmp_path, artifact, write_artifact):
    static = tmp_path / "frontend"
    static.mkdir()
    (static / "assets").mkdir()
    (static / "index.html").write_text("<!doctype html><div id='app'></div>")
    (static / "assets" / "index-AbCd1234.js").write_text("export const x = 1;")
    secret = tmp_path / "private.txt"
    secret.write_text("not-public")
    (static / "assets" / "leak.txt").symlink_to(secret)
    snapshot = tmp_path / "data" / "snapshot.json"
    SnapshotStore(snapshot).publish(write_artifact(artifact), method="fixture")
    client = TestClient(create_app(snapshot, static))
    html = client.get("/reference/overview")
    assert html.status_code == 200
    assert html.headers["cache-control"] == "no-cache"
    assert "script-src 'self'" in html.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in html.headers["content-security-policy"]
    assert (
        client.get("/docs").headers["content-security-policy"]
        != html.headers["content-security-policy"]
    )
    js = client.get("/assets/index-AbCd1234.js")
    assert "immutable" in js.headers["cache-control"]
    for path in (
        "/v1/unknown",
        "/health/unknown",
        "/snapshot.json",
        "/.env",
        "/assets/leak.txt",
        "/assets/%2e%2e/%2e%2e/private.txt",
    ):
        assert client.get(path).status_code == 404, path
    api = client.get("/v1/resources", headers={"Origin": "https://example.com"})
    assert api.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in api.headers
    assert api.headers["x-content-type-options"] == "nosniff"
    assert api.headers["x-frame-options"] == "DENY"
    schema = client.get("/openapi.json").json()
    assert "/{document_path}" not in schema["paths"]
    assert "/v1/resources" in schema["paths"]


def test_stale_snapshot_remains_available(tmp_path, artifact, write_artifact):
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    artifact["generatedAt"] = old
    for r in artifact["resources"]:
        r["provenance"]["fetchedAt"] = old
    path = tmp_path / "snapshot.json"
    SnapshotStore(path).publish(write_artifact(artifact), method="fixture")
    client = TestClient(create_app(path))
    assert client.get("/v1/status").json()["state"] == "stale"
    assert client.get("/v1/resources").status_code == 200


def test_openapi_schema_matches_generated_contract():
    from pathlib import Path

    generated = json.loads(Path("schema/openapi.json").read_text())
    assert create_app("/nonexistent/snapshot.json").openapi() == generated
