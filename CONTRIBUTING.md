# Contributing to OpenAI Academy Metadata API

This guide covers local setup, offline verification checks, and contract maintenance for contributors.

## Backend setup and offline checks

Requires Python `>=3.11` (CI runs on Python `3.11` and `3.13`) and `uv`.

Install locked dependencies and run the backend verification suite from the repository root (matching [`.github/workflows/ci.yml`](.github/workflows/ci.yml)):

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Unit tests in [`tests/test_api.py`](tests/test_api.py) and [`tests/test_security.py`](tests/test_security.py) run offline against temporary snapshots and local fixtures. No `OPENAI_API_KEY`, network access, or live collector run is required for testing.

To verify the CLI against the synthetic fixture, import into a temporary snapshot path rather than `data/snapshot.json`:

```bash
uv run --locked academy-collector validate examples/collection.fixture.json
uv run --locked academy-collector --snapshot /tmp/academy-example/snapshot.json import examples/collection.fixture.json --method fixture
```

## Keeping schemas, examples, and tests in sync

When changing route behavior, query validation, normalization rules, or CLI options, update the corresponding files in the same change:

- **API and schema contracts:** [`schema/contract.json`](schema/contract.json), [`schema/openapi.json`](schema/openapi.json), [`schema/resource.schema.json`](schema/resource.schema.json), [`schema/snapshot.schema.json`](schema/snapshot.schema.json), [`schema/collection.schema.json`](schema/collection.schema.json), and [`schema/collector-runtime.json`](schema/collector-runtime.json).
- **OpenAPI parity test:** `test_openapi_schema_matches_generated_contract` in [`tests/test_api.py`](tests/test_api.py) asserts that `create_app("/nonexistent/snapshot.json").openapi()` equals the contents of [`schema/openapi.json`](schema/openapi.json). If you modify FastAPI routes or Pydantic response/query models, update `schema/openapi.json` and the JSON Schema files in `schema/` so the parity check passes.
- **Examples and documentation:** Keep [`examples/commands.json`](examples/commands.json), [`examples/collection.fixture.json`](examples/collection.fixture.json), [`prompts/collector.md`](prompts/collector.md), and [`README.md`](README.md) aligned with actual CLI flags and field names.

## Frontend checks for changes in `frontend/`

Frontend work in `frontend/` is tracked separately from the Python service. If your change touches files under `frontend/`, run the Node `24` checks defined in [`frontend/package.json`](frontend/package.json) and [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm run copy:check -- --strict
npm run build
```

## Commit messages and pull requests

- Write clear, neutral, imperative commit messages that state what changed and why.
- Include test coverage for bug fixes, validation rules, and contract changes, and report the exact commands you ran in your pull request description.
