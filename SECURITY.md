# Security Policy and Trust Boundaries

`openai-academy-api` separates unauthenticated public read serving from offline and operator-invoked metadata collection.

## Read-only HTTP serving and credential isolation

- **No collection or model calls on HTTP requests:** Public endpoints (`/v1/resources`, `/v1/resources/{id}`, `/v1/categories`, `/v1/status`, `/health`, `/health/ready`, `/openapi.json`, `/docs`) are read-only and unauthenticated. Serving requests only reads a pre-validated local snapshot file; it never crawls `academy.openai.com`, starts a collector run, calls a model, or spends API budget.
- **No API keys needed to serve:** Importing `openai_academy_api` or running `academy-api` does not require `OPENAI_API_KEY`.
- **Public metadata only in snapshots:** Published snapshots contain only normalized public resource metadata, categories, coverage counts, and provenance (`sourceUrls`, `fetchedAt`, `contentHash`, `method`). Private credentials, collector run journals (`STATE_DIR/RUN_UUID/journal.json`), fetch receipts (`receipts.json`), and raw fetched HTML/JSON bodies must never be placed in served snapshot files or static assets.

## Static file serving and response headers

When `academy-api` serves HTTP responses and optional `--frontend-dir` assets (tested in [`tests/test_api.py`](tests/test_api.py)):

- API and health routes are registered before static serving; unknown paths under `/v1/*` and `/health/*` return `404` and never fall back to `index.html`.
- Static resolution requires the snapshot file to reside outside `--frontend-dir` and rejects symbolic links, path traversal (`..`), dotfiles (such as `/.env`), and direct requests for `/snapshot.json` with `404`.
- All responses include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
- `Content-Security-Policy` is scoped by response type: JSON API responses (`application/json`) send `default-src 'none'; frame-ancestors 'none'`; served frontend HTML documents restrict scripts to `'self'` (`default-src 'self'`, `script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`); and `/docs` uses a separate HTML policy (`default-src 'none'; frame-ancestors 'none'`) that allows Swagger UI's `https://cdn.jsdelivr.net` and inline scripts/styles.
- Public API responses set `Access-Control-Allow-Origin: *` without `Access-Control-Allow-Credentials`.

## Untrusted source content and collector validation boundaries

Source pages, sitemaps, JSON-LD blocks, embedded frontend state, and collection plan files are treated strictly as untrusted data (see [`schema/collector-runtime.json`](schema/collector-runtime.json), [`prompts/collector.md`](prompts/collector.md), and [`tests/test_security.py`](tests/test_security.py)):

- **No authority from source text:** Embedded instructions, role-change claims, tool overrides, or permission claims inside retrieved content cannot alter collector authority, allowed hosts, request budgets, output paths, or validation rules.
- **Host and path enforcement:** `public_academy_url` requires `https://academy.openai.com` on the default port with no credentials, IP literals, path traversal, or control/newline characters, and restricts fetches to allowed public discovery and resource paths (rejecting authenticated `/home/...` routes, club member lists, forum sitemaps, and SCORM packages).
- **Fetch helper vs. provider network allowlist:** In the hosted collector configuration, outbound domain access (`academy.openai.com`) is restricted by the provider environment, whereas `robots.txt` checks, `GET`-only requests, single concurrency, request delays (`requestDelaySeconds`), response size caps (`maxResponseBytes`), and page budgets (`maxPages`) are enforced by the fetch helper (`fetch_public.py`) and verified against saved receipts. Provider network allowlisting alone does not enforce a request-count quota.
- **Offline manual/fixture import validation (`academy-collector import`):** Validates the local artifact against [`schema/collection.schema.json`](schema/collection.schema.json) (`CollectionArtifact`), enforces canonical `https://academy.openai.com` URL rules and `MediaReference` permission invariants (`permission: "permitted"` and an official `permissionEvidenceUrl`), computes deterministic IDs and content hashes, and writes the snapshot atomically with `--method manual` or `fixture`. Offline import does not fetch source URLs or verify HTTP fetch receipts.
- **Managed collector receipt verification (`Collector._finish`):** Before publishing a managed run with `method="managed-agent"`, the collector downloads both the output artifact and `fetch-receipts.json`, validates the artifact schema, and verifies that receipts match `runId`, confirm `robotsChecked: true` with an `HTTP 200` receipt for `https://academy.openai.com/robots.txt`, stay within `maxPages`, `maxResources`, `maxResponseBytes`, and `[startedAt, deadlineAt]`, and record an `HTTP 200` receipt with positive byte count and 64-character hex SHA-256 digest for every published resource URL.

## Reporting a vulnerability privately

Do not report security vulnerabilities, exploit details, or exposed credentials in public issues, pull requests, or discussions.

- If private vulnerability reporting is enabled on the repository host where you accessed this project, submit your report through that private security advisory feature.
- Otherwise, contact the maintainer (`Dominic Phillips`, listed in [`LICENSE`](LICENSE)) to request a private reporting channel before disclosing technical details.

When reporting, include the affected component (`academy-api`, `academy-collector`, URL validation, or static file serving), reproduction steps, and the observed impact without including private keys or sensitive host data.
