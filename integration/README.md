# Integration tests

These tests hit a real Ragnerock instance over the network. They are **not** run by the default `pytest` invocation (which is scoped to `tests/` in `pyproject.toml`). Run them explicitly against a live API when you want to verify end-to-end behavior.

## What they cover

One test file per resource area, each exercising a round-trip flow:

- [test_auth.py](test_auth.py) — login, project resolution, auth header
- [test_documents.py](test_documents.py) — upload, download, list, get-by-name, rename, delete
- [test_document_groups.py](test_document_groups.py) — group CRUD + moving documents between groups
- [test_chunks_pages.py](test_chunks_pages.py) — list chunks / pages on an uploaded document (read-only)
- [test_operators.py](test_operators.py) — CRUD
- [test_annotations.py](test_annotations.py) — create against a real operator + document; list; delete
- [test_workflows.py](test_workflows.py) — CRUD; opt-in `run()` + `wait()`
- [test_queries.py](test_queries.py) — execute a SQL query

## Configuration

Set either a full connection string:

```bash
export RAGNEROCK_CONN_STR="ragnerock://you@example.com:pass@api.example.com/my_project"
```

…or the individual pieces (combined into a connection string at runtime):

```bash
export RAGNEROCK_HOST="api.example.com"
export RAGNEROCK_EMAIL="you@example.com"
export RAGNEROCK_PASSWORD="secret"
export RAGNEROCK_PROJECT="my_project"
```

If neither is set, every integration test is skipped — safe to run blind in CI.

### Optional opt-ins

Some tests create server-side side effects that cost real resources (LLM calls, long-running jobs). They're skipped by default and enabled via:

- `RAGNEROCK_ITEST_RUN_WORKFLOWS=1` — run `session.run()` + `job.wait()`. Uses real operator quota.

## Running

```bash
# All integration tests against the configured environment
uv run pytest integration/

# Just one file
uv run pytest integration/test_documents.py -v

# With the workflow-run opt-in
RAGNEROCK_ITEST_RUN_WORKFLOWS=1 uv run pytest integration/test_workflows.py
```

## Test design rules

- Every test creates its own resources with a unique name (e.g. `sdk-itest-<uuid4>`) and cleans them up in a `finally` or fixture teardown.
- Tests must be idempotent — re-running after a crash shouldn't break the next run.
- No shared mutable state between tests. Each test is independent.
- No assumptions about pre-existing data in the project.

If you see leftover `sdk-itest-*` resources after a failed run, delete them manually — the teardown tried and lost.
