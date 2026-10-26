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
- **Hosted collector configuration:** A separately invoked private collector (`academy-collector` subcommands in [`examples/commands.json`](examples/commands.json) and runtime contract in [`schema/collector-runtime.json`](schema/collector-runtime.json)) is implemented in the repository for bounded operator runs and records `provenance.method: "managed-agent"` after verifying fetch receipts. Live collection is not required to run the API. A launchd example for one run per day is included but nothing installs or enables it; see [Self-hosting the API and daily collector](#self-hosting-the-api-and-daily-collector).

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

### Caching and conditional requests

- **Catalog responses:** Successful `GET /v1/resources`, `GET /v1/resources/{id}`, and `GET /v1/categories` responses send `Cache-Control: public, max-age=60, s-maxage=86400` and a weak `ETag`. Browsers revalidate after 60 seconds; shared caches such as a CDN may keep a copy for up to one day. Send the `ETag` value in `If-None-Match` to receive `304 Not Modified` with an empty body.
- **Never cached:** Every error response (including `409` cursor conflicts), `GET /v1/status`, `GET /health`, and `GET /health/ready` send `Cache-Control: no-store` and no `ETag`.
- **Cache key:** CORS headers are the same for every request, so a shared cache can key catalog responses on the full URL, including the query string.
- **After publication:** Until a shared cache is purged or its copy expires, it may serve responses from the previous snapshot. `GET /v1/status` is never cached and reports the current `snapshotId`, which you can compare with the `snapshotId` on catalog responses. A cursor from an older snapshot that reaches the server returns `409`.

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

## Self-hosting the API and daily collector

The server needs Python `>=3.11`, [`uv`](https://docs.astral.sh/uv/), and a validated snapshot file; it reads no key or env file. Collection additionally needs an OpenAI API key in a private env file passed with `--env-file`. Copy [`.env.template`](.env.template) for the key; the template also lists the optional settings that come from the collector's process environment.

```bash
uv sync --frozen
uv run --frozen academy-collector validate-snapshot /srv/academy/snapshot.json
uv run --frozen academy-api --snapshot /srv/academy/snapshot.json --host 127.0.0.1 --port 8000
```

### One collection per day

Check the plan offline first; `dry-run` reads neither the key nor the network. Then run the same pass live with `--daily`. The global options go before the subcommand:

```bash
uv run --frozen academy-collector --state-dir /srv/academy/collector dry-run --from-frontier --seed https://academy.openai.com/pages/courses --max-pages 30 --max-resources 100 --max-seconds 900
uv run --frozen academy-collector --env-file /srv/academy/collector.env --snapshot /srv/academy/snapshot.json --state-dir /srv/academy/collector run --live --daily --from-frontier --seed https://academy.openai.com/pages/courses --max-pages 30 --max-resources 100 --max-seconds 900
```

`--daily` gives each UTC date and state directory one run ID, so a scheduler can call the command repeatedly without paying for a second pass:

- A day that already published and cleaned up its session exits without any network call. A failed or unfinished day is never submitted again.
- A new day does not start while an earlier run might still be running, while a published run's session cleanup is incomplete, or after any failed or cancelled run that nobody has reviewed. A quota or authentication failure for the same key also holds every new run.
- Only one controller can use a state directory at a time. Keep every manual and scheduled command on the same `--state-dir`.

After reviewing a failed run, record the review so daily runs can continue. This makes no provider call and does not retry the failed run:

```bash
uv run --frozen academy-collector --state-dir /srv/academy/collector acknowledge RUN_UUID
```

### Reaching the whole Academy over several days

Each pass stays within its page, resource and time limits. To reach pages beyond the seeds, the collector keeps a private queue of URLs, `frontier.json`, in the state directory. With `--from-frontier`, a pass first takes URLs that have never been fetched, then the ones fetched longest ago, after any `--seed` URLs and the `robots.txt` request.

- Links the collector saw only on a listing page join the queue. They are never published; a resource is published only when its own page was fetched in that run.
- The queue only grows. A failed or unpublished run adds its new links but leaves every URL in its place, so the next pass retries the same work. Daily holds and the state-directory lock still apply.

Seed the queue from a saved run, then preview the next passes. The preview reads neither the key nor the network and changes nothing:

```bash
uv run --frozen academy-collector --state-dir /srv/academy/collector frontier bootstrap STATE_DIR/RUN_UUID/artifact.json STATE_DIR/RUN_UUID/receipts.json
uv run --frozen academy-collector --state-dir /srv/academy/collector frontier plan --max-pages 30 --passes 5
```

### Corrections and kept covers

Known extractor errors can be listed in `corrections.json` in the state directory. Each entry names a page, the SHA-256 of the page version it was checked against, the fields to set and a reason:

```json
{"schemaVersion": 1, "corrections": [{"url": "https://academy.openai.com/public/courses/example", "sourceSha256": "<64 hex characters>", "fields": {"duration.pathMinutes": null}, "reason": "The page states no path total."}]}
```

A correction applies only while the page fetched that day has the same hash. If the page changed, the collector does not publish the new extraction for that URL: the published record stays as it was, and the run journal lists the URL under `review` as `held-for-review`. If a fetch returns no cover for a record that already has one, the published cover is kept.

### Scheduling

Run the daily command once a day from a scheduler that does not restart or retry it. For macOS, [`deploy/launchd/academy-collector.plist`](deploy/launchd/academy-collector.plist) is an example LaunchAgent: replace the `/path/to/...` values, then install it with `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/academy-collector.plist`. It runs at 04:17 local time, never at load, with a private file mode mask, and clears the inherited environment. Remove it with `launchctl bootout gui/$(id -u)/com.example.academy-collector`.

### Optional Cloudflare cache purge

When the API is behind Cloudflare, the collector can ask Cloudflare to purge the API hostname after a publication that changes the snapshot. Set all three variables in the collector's process environment, or none:

- `ACADEMY_CLOUDFLARE_ZONE_ID`: the zone ID.
- `ACADEMY_CLOUDFLARE_HOSTNAME`: the exact API hostname. Only this hostname is purged, never the whole zone.
- `ACADEMY_CLOUDFLARE_PURGE_TOKEN_FILE`: a private file holding an API token limited to the Cache Purge permission for that zone.

Incomplete or invalid settings stop the command before any paid call, and the token is never sent to the hosted session or written to the journal. Cloudflare's success response means it accepted the purge request, which the run journal records as `edgePurge.state: "accepted"`. If the purge fails, the new snapshot stays published, the failure is recorded in the journal, and the command exits with status `3`. Do not rerun collection; retry only the purge, which is also the step to run after a manual `import` into the served snapshot:

```bash
uv run --frozen academy-collector purge-cache --live
```

## Code license and source content rights

The software in this repository is licensed under the [MIT License](LICENSE) (Copyright (c) 2026 Dominic Phillips).

The MIT License applies solely to this repository's source code. It does not grant any license or redistribution rights to OpenAI Academy course text, videos, artwork, badges, or other provider content. Returning factual metadata and canonical `https://academy.openai.com` links does not redistribute courses or grant media usage permissions.
