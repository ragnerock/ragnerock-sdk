"""Shared fixtures and payload builders for the SDK test suite.

Every test uses ``pytest-httpx`` to intercept outbound HTTP calls. The fixtures
here give you:

- ``base_url``: the canonical test host.
- ``conn_str``: a valid connection string for ``create_engine``.
- ``mock_login``: stub the auth + project lookup endpoints so ``Session.__enter__``
  succeeds without pre-arranging each test.
- ``session``: a ready-to-use ``Session`` bound to a mocked engine.
- ``payloads``: canonical JSON payloads for every resource, so tests stay short.

Each fixture is intentionally small and composable — mix and match per test.

During Phase 1 the SDK is stubbed (raises ``NotImplementedError``) so mocked
responses are never consumed. We disable pytest-httpx's strict "every response
was requested" / "every request was expected" assertions here so teardown
doesn't paper over the real ``NotImplementedError`` failures that Phase 2 has
to resolve. Phase 2 can re-enable strictness per-test or globally.
"""

from __future__ import annotations

from uuid import UUID

import pytest


def pytest_collection_modifyitems(config, items):
    """Apply a relaxed httpx_mock marker to every test.

    Keeps Phase 1 failure output focused on NotImplementedError, not on
    pytest-httpx teardown complaints about unused mocks.
    """
    marker = pytest.mark.httpx_mock(
        assert_all_responses_were_requested=False,
        assert_all_requests_were_expected=False,
    )
    for item in items:
        item.add_marker(marker)


# -- constants ----------------------------------------------------------------

TEST_HOST = "https://api.test.ragnerock.local"
TEST_EMAIL = "alice@example.com"
TEST_PASSWORD = "hunter2"
TEST_PROJECT_NAME = "demo"
TEST_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_TOKEN = "test-access-token-xyz"


@pytest.fixture
def base_url() -> str:
    return TEST_HOST


@pytest.fixture
def conn_str() -> str:
    return f"ragnerock://{TEST_EMAIL}:{TEST_PASSWORD}@{TEST_HOST.removeprefix('https://')}/{TEST_PROJECT_NAME}"


@pytest.fixture
def project_id() -> UUID:
    return TEST_PROJECT_ID


# -- authentication stubs -----------------------------------------------------


@pytest.fixture
def mock_login(httpx_mock):
    """Stub out `/api/auth/login` and the project-name lookup.

    Call this in any test that opens a Session. The mocks are registered as
    "allow repeated matches" so tests don't have to worry about ordering.
    """

    httpx_mock.add_response(
        method="POST",
        url=f"{TEST_HOST}/api/auth/login",
        json={"access_token": TEST_TOKEN, "token_type": "bearer"},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{TEST_HOST}/api/projects/name/{TEST_PROJECT_NAME}",
        json={
            "projects": [
                {
                    "id": str(TEST_PROJECT_ID),
                    "name": TEST_PROJECT_NAME,
                    "description": None,
                    "owner_id": "00000000-0000-0000-0000-0000000000aa",
                }
            ],
            "total": 1,
            "skip": 0,
            "limit": 100,
        },
        is_reusable=True,
    )


@pytest.fixture
def engine(conn_str, mock_login):
    """A not-yet-connected engine; `Session.__enter__` will do the auth handshake."""
    from ragnerock import create_engine

    return create_engine(conn_str)


@pytest.fixture
def session(engine):
    """A ready-to-use session. Yielded inside `with`, so the connection is live."""
    from ragnerock import Session

    with Session(engine) as s:
        yield s


# -- payload helpers ----------------------------------------------------------


@pytest.fixture
def payloads():
    """Canonical JSON payloads for each resource type.

    Returns an object exposing ``.document()``, ``.chunk()``, etc. — callable
    builders that accept overrides. Tests use these to keep bodies short.
    """

    return _Payloads()


class _Payloads:
    def document(self, **overrides):
        base = {
            "id": "00000000-0000-0000-0000-000000000101",
            "project_id": str(TEST_PROJECT_ID),
            "name": "sample.pdf",
            "group_id": None,
            "file_type": "application/pdf",
            "source_url": None,
            "storage_path": "projects/demo/sample.pdf",
            "filesize": 12345,
            "created_at": "2026-04-16T12:00:00Z",
            "updated_at": "2026-04-16T12:00:00Z",
            "created_by_id": "00000000-0000-0000-0000-0000000000aa",
            "metadata": None,
        }
        base.update(overrides)
        return base

    def document_group(self, **overrides):
        base = {
            "id": "00000000-0000-0000-0000-000000000201",
            "project_id": str(TEST_PROJECT_ID),
            "name": "Q1 contracts",
            "created_at": "2026-04-16T12:00:00Z",
        }
        base.update(overrides)
        return base

    def chunk(self, **overrides):
        base = {
            "id": "00000000-0000-0000-0000-000000000301",
            "document_id": "00000000-0000-0000-0000-000000000101",
            "content": "Hello world.",
            "start_index": 0,
            "end_index": 12,
            "chunk_type": 4,  # PARAGRAPH
            "metadata": None,
            "created_at": "2026-04-16T12:00:00Z",
        }
        base.update(overrides)
        return base

    def page(self, **overrides):
        base = {
            "id": "00000000-0000-0000-0000-000000000401",
            "document_id": "00000000-0000-0000-0000-000000000101",
            "page_number": 1,
            "content": "Page one text",
            "metadata": None,
        }
        base.update(overrides)
        return base

    def annotation(self, **overrides):
        base = {
            "root_id": "00000000-0000-0000-0000-000000000501",
            "operator_id": "00000000-0000-0000-0000-000000000601",
            "operator_name": "invoice_extract",
            "document_id": "00000000-0000-0000-0000-000000000101",
            "chunk_id": None,
            "page_id": None,
            "data": {"total": 1234.56, "vendor": "Acme"},
            "confidence_score": 0.92,
            "generation_metadata": None,
            "created_at": "2026-04-16T12:00:00Z",
            "updated_at": "2026-04-16T12:00:00Z",
        }
        base.update(overrides)
        return base

    def operator(self, **overrides):
        base = {
            "id": "00000000-0000-0000-0000-000000000601",
            "project_id": str(TEST_PROJECT_ID),
            "name": "invoice_extract",
            "description": "Extract invoice totals",
            "jsonschema": {"type": "object", "properties": {"total": {"type": "number"}}},
            "generation_prompt": "Extract the total.",
            "chunk_type": 1,  # DOCUMENT
            "batch_size": None,
            "multi_annotation": False,
            "created_at": "2026-04-16T12:00:00Z",
        }
        base.update(overrides)
        return base

    def workflow(self, **overrides):
        base = {
            "id": "00000000-0000-0000-0000-000000000701",
            "project_id": str(TEST_PROJECT_ID),
            "name": "ingest",
            "description": "Ingest pipeline",
            "created_by_id": "00000000-0000-0000-0000-0000000000aa",
            "created_at": "2026-04-16T12:00:00Z",
            "updated_at": "2026-04-16T12:00:00Z",
            "is_active": True,
            "auto_run_on_upload": True,
            "execution_order": [],
            "nodes": [],
        }
        base.update(overrides)
        return base

    def job(self, **overrides):
        base = {
            "id": "00000000-0000-0000-0000-000000000801",
            "document_id": "00000000-0000-0000-0000-000000000101",
            "start_time": "2026-04-16T12:00:00Z",
            "end_time": None,
            "status": 2,  # IN_PROGRESS
            "status_message": None,
            "job_type": "workflow",
            "should_parse": True,
            "capture_execution_log": False,
            "n_tokens": None,
            "n_pages": None,
            "n_mb": None,
            "execution_trace": None,
            "phase": None,
        }
        base.update(overrides)
        return base

    def list_envelope(self, key: str, items: list, total: int | None = None):
        """Wrap items in the API's standard `{key: [...], total, skip, limit}` shape."""

        return {
            key: items,
            "total": total if total is not None else len(items),
            "skip": 0,
            "limit": 100,
        }

    def query_result(self, **overrides):
        base = {
            "columns": ["vendor", "total"],
            "data": [{"vendor": "Acme", "total": 1234.56}],
            "row_count": 1,
            "query_time_ms": 42,
        }
        base.update(overrides)
        return base
