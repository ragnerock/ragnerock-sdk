# Integration tests

These tests hit a real Ragnerock instance over the network. They are the only test suite in this repo — `pytest` with no arguments will run them, and they auto-skip when credentials aren't configured (safe in CI).

## What they cover

One file per resource area, each exercising a full round-trip flow:

- [test_engine.py](test_engine.py) — connection-string parsing, login, project resolution, bearer-token threading, session context manager
- [test_documents.py](test_documents.py) — upload, download, list, get-by-name, rename, delete, validation
- [test_document_groups.py](test_document_groups.py) — group CRUD + moving documents between groups
- [test_chunks_pages.py](test_chunks_pages.py) — list chunks / pages on an uploaded document (read-only after ingestion)
- [test_operators.py](test_operators.py) — CRUD, get-by-name
- [test_annotations.py](test_annotations.py) — create against a real operator + document; list by document / chunk / operator; hydrated; delete
- [test_workflows.py](test_workflows.py) — CRUD; opt-in `run()` + `wait()`
- [test_jobs.py](test_jobs.py) — list / get; opt-in lifecycle (cancel, retry, wait)
- [test_queries.py](test_queries.py) — execute SQL, QueryResult conversions, syntax errors
- [test_errors.py](test_errors.py) — error hierarchy, 404 and 422 mappings
- [test_transactions.py](test_transactions.py) — commit ordering, rollback, refresh, CommitError
- [test_pagination.py](test_pagination.py) — lazy iteration, `limit`, `first`, `all`

## Configuration

Set either a full connection string:

```bash
export RAGNEROCK_CONNECTION_STRING="ragnerock://you@example.com:pass@api.example.com/my_project"
```

…or the individual pieces (combined into a connection string at runtime):

```bash
export RAGNEROCK_HOST="api.example.com"
export RAGNEROCK_EMAIL="you@example.com"
export RAGNEROCK_PASSWORD="secret"
export RAGNEROCK_PROJECT="my_project"
```

If neither is set, every integration test is skipped — safe to run blind in CI.

### Credits

Before the first test runs, the test session purchases credits so quota-consuming tests don't fail mid-flight. Controlled by:

- `RAGNEROCK_ITEST_CREDITS` — number of credits to purchase at session start (default `1000`). Set to `0` to skip the purchase entirely (use when credits are managed externally, e.g. seeded by a CI task). If the current balance already meets or exceeds the requested amount, the purchase is skipped.

Per the `POST /api/credits/purchase` contract, Stripe payment confirmation is expected to have happened before the call. Dev / test instances treat this as a direct credit grant — no real charge.

### Optional opt-ins

Some tests create server-side side effects that cost real resources (LLM calls, long-running jobs). They're skipped by default and enabled via:

- `RAGNEROCK_ITEST_RUN_WORKFLOWS=1` — run `session.run()` + `job.wait()`. Uses real operator quota.
- `RAGNEROCK_ITEST_PAGINATION=1` — create enough documents (>page_size) to exercise multi-page iteration.

## Running

```bash
# All integration tests against the configured environment
uv run pytest tests/integration/

# Just one file
uv run pytest tests/integration/test_documents.py -v

# With the workflow-run opt-in
RAGNEROCK_ITEST_RUN_WORKFLOWS=1 uv run pytest tests/integration/test_workflows.py
```

## Test design rules

- Every test creates its own resources with a unique name (e.g. `sdk-itest-<uuid4>`) and cleans them up in a `finally` or fixture teardown.
- Tests must be idempotent — re-running after a crash shouldn't break the next run.
- No shared mutable state between tests. Each test is independent.
- No assumptions about pre-existing data in the project.

If you see leftover `sdk-itest-*` resources after a failed run, delete them manually — the teardown tried and lost.
