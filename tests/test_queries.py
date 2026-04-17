"""Tests for `session.query(...)` and the `QueryResult` wrapper."""

from __future__ import annotations

import pytest

from ragnerock import QueryError, QueryResult
from tests.conftest import TEST_HOST, TEST_PROJECT_ID


class TestExecute:
    def test_query_returns_query_result(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/query/projects/{TEST_PROJECT_ID}/query",
            json=payloads.query_result(),
        )
        result = session.query("SELECT vendor, total FROM invoice_extract")
        assert isinstance(result, QueryResult)
        assert result.row_count == 1
        assert result.columns == ["vendor", "total"]

    def test_query_body_carries_sql_and_limit(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/query/projects/{TEST_PROJECT_ID}/query",
            json=payloads.query_result(),
        )
        session.query("SELECT 1", limit=50)

        req = next(
            r
            for r in httpx_mock.get_requests()
            if r.method == "POST"
            and f"{TEST_PROJECT_ID}" in r.url.path
        )
        body = req.read()
        assert b"SELECT 1" in body
        assert b"50" in body


class TestQueryResultConversion:
    def test_to_dict(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/query/projects/{TEST_PROJECT_ID}/query",
            json=payloads.query_result(
                data=[
                    {"vendor": "Acme", "total": 1234.56},
                    {"vendor": "Globex", "total": 789.0},
                ],
                row_count=2,
            ),
        )
        result = session.query("SELECT * FROM invoice_extract")
        rows = result.to_dict()
        assert len(rows) == 2
        assert rows[0]["vendor"] == "Acme"

    def test_to_pandas(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/query/projects/{TEST_PROJECT_ID}/query",
            json=payloads.query_result(),
        )
        result = session.query("SELECT vendor, total FROM invoice_extract")
        df = result.to_pandas()
        # pandas is installed in the dev env.
        assert list(df.columns) == ["vendor", "total"]
        assert len(df) == 1

    def test_len(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/query/projects/{TEST_PROJECT_ID}/query",
            json=payloads.query_result(row_count=3),
        )
        result = session.query("SELECT 1")
        assert len(result) == 3


class TestErrorMapping:
    def test_syntax_error_raises_query_error(self, httpx_mock, session):
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/query/projects/{TEST_PROJECT_ID}/query",
            status_code=400,
            json={
                "detail": {
                    "message": "syntax error at 'SELEKT'",
                    "error_code": "SYNTAX_ERROR",
                    "suggestion": "Did you mean SELECT?",
                }
            },
        )
        with pytest.raises(QueryError) as exc_info:
            session.query("SELEKT 1")
        assert exc_info.value.error_code == "SYNTAX_ERROR"
        assert "SELECT" in (exc_info.value.suggestion or "")
