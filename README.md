# OpenAI Academy Metadata API

`openai-academy-api` is an unofficial, read-only HTTP service and CLI toolset that serves structured metadata for public [OpenAI Academy](https://academy.openai.com) learning resources. It is independent of OpenAI.

The HTTP server (`academy-api`) reads a validated local snapshot file on disk. Incoming requests never crawl `academy.openai.com`, invoke a model, or require an `OPENAI_API_KEY`. Learner sign-in, course delivery, assessments, and progress tracking remain on OpenAI Academy.

## Public service

The public read-only API is live at [`https://openai-academy.deployedwork.com`](https://openai-academy.deployedwork.com), with interactive Swagger UI at [`/docs`](https://openai-academy.deployedwork.com/docs) and the OpenAPI 3.1 specification at [`/openapi.json`](https://openai-academy.deployedwork.com/openapi.json). All read endpoints are public and require no authentication:

```bash
curl -s https://openai-academy.deployedwork.com/v1/status | python3 -m json.tool
curl -s "https://openai-academy.deployedwork.com/v1/resources?limit=5" | python3 -m json.tool
```

## Local quickstart with the synthetic fixture

Requires Python `>=3.11` and [`uv`](https://docs.astral.sh/uv/).

[`examples/collection.fixture.json`](examples/collection.fixture.json) contains one synthetic resource record (`https://academy.openai.com/public/resources/fixture-only-example`) for verifying the local CLI and HTTP responses offline. It is not real OpenAI Academy data. Import it into a temporary path such as `/tmp/academy-example/snapshot.json` rather than `data/snapshot.json`:

```bash
uv sync --frozen
uv run --locked academy-collector validate examples/collection.fixture.json
uv run --locked academy-collector --snapshot /tmp/academy-example/snapshot.json import examples/collection.fixture.json --method fixture
uv run academy-api --snapshot /tmp/academy-example/snapshot.json --host 127.0.0.1 --port 8000
```

In a second terminal, query the local server:

```bash
curl -s http://127.0.0.1:8000/v1/status | python3 -m json.tool
curl -s "http://127.0.0.1:8000/v1/resources?limit=5" | python3 -m json.tool
```

## Importing a validated manual collection artifact

Serving is separated from collection:

- **Manual bootstrap (current workflow):** Validate a collection artifact that conforms to [`schema/collection.schema.json`](schema/collection.schema.json) and import it with `--method manual`. Note that the global `--snapshot` option precedes the `import` subcommand:

  ```bash
  uv run academy-collector validate path/to/collection.json
  uv run academy-collector --snapshot data/snapshot.json import path/to/collection.json --method manual
  uv run academy-api --snapshot data/snapshot.json --host 127.0.0.1 --port 8000
  ```

- **What import computes:** `academy-collector import` accepts `--method manual` (default) or `--method fixture`. It validates the input artifact with Pydantic, computes each resource's deterministic `id` and `provenance.contentHash`, sets `provenance.method` to `manual` or `fixture`, merges records without deleting prior entries, and writes the target snapshot atomically alongside `.previous.json` and `.status.json` files.
- **Hosted collector configuration:** A separately invoked private collector (`academy-collector` subcommands in [`examples/commands.json`](examples/commands.json) and runtime contract in [`schema/collector-runtime.json`](schema/collector-runtime.json)) is implemented in the repository for bounded operator runs and records `provenance.method: "managed-agent"` after verifying fetch receipts. Live collection is neither scheduled nor required to run the API, and no background scheduler is included.

## Serving options and optional static frontend directory

`academy-api` supports the following flags (see [`examples/commands.json`](examples/commands.json)):

- `--snapshot <path>`: Path to the validated snapshot JSON file (for example, `data/snapshot.json`).
- `--frontend-dir <path>`: Optional path to an existing built static frontend directory (such as `frontend/dist`).
- `--host <host>`: Bind address (for example, `127.0.0.1`).
- `--port <port>`: Bind port (for example, `8000`).

When `--frontend-dir` is provided, API routes (`/v1/*`, `/health`, `/health/ready`, `/openapi.json`, `/docs`) are registered first and never fall through to the single-page application handler. Fingerprinted files under `/assets/` are served with `immutable` cache headers, while HTML documents use `no-cache`. Frontend development in `frontend/` is managed separately and is not required to run the metadata API.

## HTTP endpoints, query filters, and cursor pagination

All read endpoints are public and require no authentication. Full route contracts live in [`schema/contract.json`](schema/contract.json) and [`schema/openapi.json`](schema/openapi.json).

| Endpoint                 | Purpose                                                                                                      | Status codes                                                                                                                                               |
| ------------------------ | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /v1/resources`      | Paginated resource list ordered by ascending resource `id`.                                                  | `200`, `400` (invalid cursor or filter mismatch), `409` (cursor from a different `snapshotId`), `422` (invalid query parameter), `503` (no valid snapshot) |
| `GET /v1/resources/{id}` | Single resource lookup by service-derived `id` (`^oa_[a-f0-9]{24}$`).                                        | `200`, `404` (unknown ID), `422`, `503` (no valid snapshot)                                                                                                |
| `GET /v1/categories`     | Category list with resource counts (`items`, `snapshotId`).                                                  | `200`, `503` (no valid snapshot)                                                                                                                           |
| `GET /v1/status`         | Snapshot availability, timestamps, `resourceCount`, and per-category `coverage` (`Cache-Control: no-store`). | `200` (`state` is `fresh`, `stale`, or `unavailable`)                                                                                                      |
| `GET /health`            | Process liveness check (`{"status": "ok"}`).                                                                 | `200` (remains `200` even when the snapshot file is missing)                                                                                               |
| `GET /health/ready`      | Snapshot readiness check (`{"status": "ready" \| "unavailable"}`).                                           | `200` when a valid snapshot is loaded, `503` when unavailable                                                                                              |
| `GET /openapi.json`      | OpenAPI 3.1 specification.                                                                                   | `200`                                                                                                                                                      |
| `GET /docs`              | Interactive Swagger UI.                                                                                      | `200`                                                                                                                                                      |

### Query parameters for `GET /v1/resources`

- `q`: Optional case-insensitive text search across resource `title`, `summary`, and `tags` (maximum 200 characters; omitted or empty values return unfiltered results, and whitespace is trimmed and collapsed).
- `category`: Optional category slug matching `^[a-z0-9]+(?:-[a-z0-9]+)*$` (`maxLength: 100`).
- `kind`: Optional resource kind: `course`, `learning-path`, `article`, `video`, `event`, `collection`, or `external`.
- `audience`: Optional audience filter: `general`, `knowledge-workers`, `developers`, `leaders`, `educators`, `students`, `admins`, or `other`.
- `cursor`: Optional opaque pagination cursor returned by a previous `GET /v1/resources` response (`maxLength: 1024`).
- `limit`: Page size from `1` to `100` (default `20`).

### Cursor pagination rules

`GET /v1/resources` returns `{"items": [...], "nextCursor": "...", "total": 0, "snapshotId": "..."}`. Pass `nextCursor` as `cursor` on the next request while keeping `q`, `category`, `kind`, and `audience` unchanged. Changing filters with an existing cursor returns `400`. If a new snapshot is published while paging, the server returns `409`; discard the old cursor and restart pagination from the first page.

## Resource schema, duration scopes, and provenance

Responses use `camelCase` field names, and all documented nullable keys are present in serialized output (see [`schema/resource.schema.json`](schema/resource.schema.json) and [`schema/snapshot.schema.json`](schema/snapshot.schema.json)). Unknown or unsupported values remain `null` or `[]` rather than inferred text.

- **`id`:** Deterministic identifier (`oa_` followed by the first 24 lowercase hex characters of the SHA-256 digest of the normalized canonical `https://academy.openai.com` URL). This ID is computed by this service, not issued by OpenAI.
- **`url`:** Canonical public `https://academy.openai.com` destination.
- **`kind`, `categoryIds`, `audiences`, `tags`, `summary`, `level`:** Normalized metadata fields (`level` is `beginner`, `intermediate`, `advanced`, or `null`).
- **`duration`:** Separates course, learning-path, and video duration fields:
  - `courseMinutes`: Course duration in minutes (`0..10000` or `null`).
  - `pathMinutes`: Learning-path duration in minutes (`0..10000` or `null`).
  - `videoSeconds`: Video duration in seconds (`0..604800` or `null`).
- **`detail`:** Contains `audience` (`string | null`), `prerequisites` (`string[]`), `objectives` (`string[]`), and `sections` (`[{"title": string | null, "context": string | null, "units": [{"title": string, "url": string, "kind": "lesson" | "quiz" | "course", "context": string | null, "videoCount": integer | null}]}]`).
- **`media`:** Array of permitted external media references (`MediaReference`). Defaults to `[]`. An entry is included only when an official `https://academy.openai.com` page explicitly establishes permission (`permission: "permitted"` and `permissionEvidenceUrl` set to that official page).
- **`provenance`:** Every resource records `sourceUrls` (1–16 official Academy URLs), `fetchedAt` (UTC ISO 8601 timestamp), `contentHash` (64-char hex SHA-256 of normalized resource metadata), and `method` (`manual` or `fixture` from `academy-collector import`, or `managed-agent` when published by the managed collector).

## Snapshot freshness and category coverage

- **Stale snapshots remain readable:** Failed refreshes keep the last valid snapshot available to `GET /v1/resources` and `GET /v1/categories`. By default, `GET /v1/status` reports `state: "stale"` when a snapshot's `generatedAt` timestamp is older than 7 days, when the latest read or refresh attempt failed, or when any category in `coverage[]` is not `complete`.
- **Freshness vs. completeness:** `state` on `GET /v1/status` (`fresh`, `stale`, or `unavailable`) does not replace per-category coverage or per-resource timestamps. Always inspect `coverage[]` (`state`: `complete`, `partial`, or `not-collected`, plus `discovered` and `collected` counts) and each resource's `provenance.fetchedAt`.

## Code license and source content rights

The software in this repository is licensed under the [MIT License](LICENSE) (Copyright (c) 2026 Dominic Phillips).

The MIT License applies solely to this repository's source code. It does not grant any license or redistribution rights to OpenAI Academy course text, videos, artwork, badges, or other provider content. Returning factual metadata and canonical `https://academy.openai.com` links does not redistribute courses or grant media usage permissions.
