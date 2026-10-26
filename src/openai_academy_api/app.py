"""Read-only HTTP routes. Importing this module never constructs an API client."""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from . import __version__
from .models import (
    Audience,
    CategoryCount,
    CategoryPage,
    Hash,
    Kind,
    Model,
    Resource,
    ResourcePage,
    Slug,
    Status,
    json_hash,
)
from .storage import SnapshotStore, SnapshotUnavailable

# Browsers revalidate after a minute; shared caches keep a day and are purged on publication.
CATALOG_CACHE = "public, max-age=60, s-maxage=86400"


class Cursor(Model):
    version: int
    snapshot_id: Hash
    filters_hash: Hash
    after_id: str


def fail(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


def encode_cursor(snapshot: str, filters_hash: str, last_id: str) -> str:
    value = Cursor(version=1, snapshot_id=snapshot, filters_hash=filters_hash, after_id=last_id)
    return (
        base64.urlsafe_b64encode(value.model_dump_json(by_alias=True).encode()).decode().rstrip("=")
    )


def decode_cursor(value: str) -> Cursor:
    if len(value) > 1024 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise fail(400, "invalid-cursor")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        cursor = Cursor.model_validate_json(raw)
        if cursor.version != 1:
            raise ValueError("Cursor version")
        return cursor
    except (ValueError, UnicodeError):
        raise fail(400, "invalid-cursor") from None


def cached_result(request: Request, value: Model) -> Response:
    data = value.model_dump(mode="json", by_alias=True)
    etag = f'W/"{json_hash(data)}"'
    headers = {"ETag": etag, "Cache-Control": CATALOG_CACHE}
    candidates = request.headers.get("if-none-match", "").split(",")
    if any(
        token.strip() == "*" or token.strip().removeprefix("W/") == etag.removeprefix("W/")
        for token in candidates
    ):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=data, headers=headers)


def create_app(snapshot_path: Path | str, frontend_dir: Path | str | None = None) -> FastAPI:
    store = SnapshotStore(Path(snapshot_path))
    app = FastAPI(title="Academy Resource API", version=__version__, debug=False, redoc_url=None)
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "HEAD"],
        allow_headers=["Accept", "Content-Type", "If-None-Match"],
        expose_headers=["ETag"],
    )

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if (
            "application/json" in response.headers.get("Content-Type", "")
            or response.status_code == 304
        ):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )
        elif "text/html" in response.headers.get("Content-Type", ""):
            swagger = request.url.path == "/docs"
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
                "script-src https://cdn.jsdelivr.net 'unsafe-inline'; "
                "style-src https://cdn.jsdelivr.net 'unsafe-inline'; "
                "img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'"
                if swagger
                else "default-src 'self'; base-uri 'self'; object-src 'none'; "
                "frame-ancestors 'none'; "
                "script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https://d2xo500swnpgl1.cloudfront.net; "
                "connect-src 'self'; "
                "form-action 'none'"
            )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path.startswith("/v1/"):
            # Edge caches key on the URL alone, so CORS headers must not depend on Origin.
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Expose-Headers"] = "ETag"
        response.headers.setdefault("Cache-Control", "public, max-age=60")
        if (
            response.status_code >= 400
            or request.url.path.startswith("/health")
            or request.url.path == "/v1/status"
        ):
            response.headers["Cache-Control"] = "no-store"
            if "ETag" in response.headers:
                del response.headers["ETag"]
        return response

    @app.exception_handler(SnapshotUnavailable)
    async def unavailable(_request: Request, _exc: SnapshotUnavailable):
        return JSONResponse(
            status_code=503,
            content={"detail": {"code": "snapshot-unavailable"}},
            headers={"Cache-Control": "no-store", "Retry-After": "60"},
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            store.read()
        except SnapshotUnavailable:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ready"}

    @app.get("/v1/status", response_model=Status)
    def status():
        return store.status()

    @app.get(
        "/v1/categories",
        response_model=CategoryPage,
        responses={304: {"description": "Not modified"}},
    )
    def categories(request: Request):
        snapshot = store.read()
        counts = {
            x.id: sum(x.id in r.category_ids for r in snapshot.resources)
            for x in snapshot.categories
        }
        items = [
            CategoryCount(id=x.id, label=x.label, count=counts[x.id])
            for x in sorted(snapshot.categories, key=lambda c: c.id)
        ]
        return cached_result(request, CategoryPage(items=items, snapshot_id=snapshot.snapshot_id))

    @app.get(
        "/v1/resources",
        response_model=ResourcePage,
        responses={304: {"description": "Not modified"}},
    )
    def resources(
        request: Request,
        q: Annotated[str | None, Query(max_length=200)] = None,
        category: Annotated[Slug | None, Query()] = None,
        kind: Kind | None = None,
        audience: Audience | None = None,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        snapshot = store.read()
        search = " ".join((q or "").split()).casefold()
        filters_hash = json_hash(
            {"q": search, "category": category, "kind": kind, "audience": audience}
        )
        items = [
            r
            for r in snapshot.resources
            if (category is None or category in r.category_ids)
            and (kind is None or r.kind == kind)
            and (audience is None or audience in r.audiences)
            and (not search or search in " ".join([r.title, r.summary or "", *r.tags]).casefold())
        ]
        items.sort(key=lambda r: r.id)
        start = 0
        if cursor:
            parsed = decode_cursor(cursor)
            if parsed.snapshot_id != snapshot.snapshot_id:
                raise fail(409, "snapshot-changed")
            if parsed.filters_hash != filters_hash:
                raise fail(400, "cursor-filter-mismatch")
            positions = {r.id: i for i, r in enumerate(items)}
            if parsed.after_id not in positions:
                raise fail(400, "invalid-cursor")
            start = positions[parsed.after_id] + 1
        page = items[start : start + limit]
        next_cursor = (
            encode_cursor(snapshot.snapshot_id, filters_hash, page[-1].id)
            if page and start + limit < len(items)
            else None
        )
        return cached_result(
            request,
            ResourcePage(
                items=page,
                next_cursor=next_cursor,
                total=len(items),
                snapshot_id=snapshot.snapshot_id,
            ),
        )

    @app.get(
        "/v1/resources/{resource_id}",
        response_model=Resource,
        responses={304: {"description": "Not modified"}},
    )
    def resource(resource_id: str, request: Request):
        if not re.fullmatch(r"oa_[a-f0-9]{24}", resource_id):
            raise fail(404, "resource-not-found")
        for item in store.read().resources:
            if item.id == resource_id:
                return cached_result(request, item)
        raise fail(404, "resource-not-found")

    if frontend_dir is not None:
        root = Path(frontend_dir).resolve(strict=True)
        if not root.is_dir() or not (root / "index.html").is_file():
            raise ValueError("Frontend directory must contain index.html")
        # No API/snapshot directories may be served through a broad document root.
        try:
            store.path.resolve().relative_to(root)
        except ValueError:
            pass
        else:
            raise ValueError("Snapshot must be outside the frontend directory")

        @app.api_route("/{document_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        def frontend(document_path: str):
            parts = document_path.split("/")
            if parts[0] in {"v1", "health", "docs", "redoc", "openapi.json"} or any(
                p.startswith(".") or "\\" in p for p in parts
            ):
                raise fail(404, "not-found")
            target = (root / document_path).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise fail(404, "not-found") from None
            if target.is_file():
                immutable = parts[0] == "assets" and bool(
                    re.search(r"-[A-Za-z0-9_-]{8,}\.[a-zA-Z0-9]+$", target.name)
                )
                cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
                return FileResponse(target, headers={"Cache-Control": cache})
            if target.suffix:
                raise fail(404, "not-found")
            return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

    return app
