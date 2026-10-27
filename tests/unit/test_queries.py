"""Tests for ``session.query`` and the ``QueryResult`` wrapper."""

from __future__ import annotations

import json
import re

import pytest

from ragnerock import QueryError, QueryResult


class TestQueryExecution:
    def test_query_returns_query_result(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=re.compile(r".*/api/query/projects/.*/query"),
            json=payloads.query_result(),
        )
        result = session.query("SELECT vendor, total FROM invoice_extract")
        assert isinstance(result, QueryResult)
        assert result.columns == ["vendor", "total"]
        assert result.row_count == 1
        assert result.query_time_ms == 42

    def test_query_body_includes_sql_and_limit(self, httpx_mock, session, payloads):
        import json

        httpx_mock.add_response(
            method="POST",
            url=re.compile(r".*/api/query/projects/.*/query"),
            json=payloads.query_result(),
        )
        session.query("SELECT 1", limit=25)
        req = next(
            r
            for r in httpx_mock.get_requests()
            if r.method == "POST" and "/query/projects/" in r.url.path
        )
        body = json.loads(req.read())
        assert body["query"] == "SELECT 1"
        assert body["limit"] == 25
        assert body["format"] == "dataframe"

    def test_query_error_code_raises_query_error(self, httpx_mock, session):
        httpx_mock.add_response(
            method="POST",
            url=re.compile(r".*/api/query/projects/.*/query"),
            status_code=400,
            json={
                "detail": {
                    "message": "unknown column",
                    "error_code": "UNKNOWN_COLUMN",
                }
            },
        )
        with pytest.raises(QueryError) as exc:
            session.query("SELECT nope FROM x")
        assert exc.value.error_code == "UNKNOWN_COLUMN"


class TestQueryResult:
    def test_len(self):
        r = QueryResult(columns=["a"], data=[{"a": 1}, {"a": 2}], row_count=2)
        assert len(r) == 2

    def test_to_dict_returns_rows(self):
        rows = [{"a": 1, "b": 2}]
        r = QueryResult(columns=["a", "b"], data=rows, row_count=1)
        assert r.to_dict() == rows

    def test_repr_contains_columns_and_count(self):
        r = QueryResult(columns=["c"], data=[], row_count=0, query_time_ms=7)
        text = repr(r)
        assert "columns=" in text
        assert "row_count=0" in text

    def test_to_pandas(self):
        pd = pytest.importorskip("pandas")

        rows = [{"vendor": "Acme", "total": 10.5}]
        r = QueryResult(columns=["vendor", "total"], data=rows, row_count=1)
        df = r.to_pandas()
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["vendor", "total"]
        assert df.iloc[0]["vendor"] == "Acme"

    def test_repr_omits_unknown_timing(self):
        from ragnerock import QueryResult

        result = QueryResult(columns=["a"], data=[], row_count=0)
        assert "query_time_ms" not in repr(result)

    def test_repr_flags_truncation(self):
        from ragnerock import QueryResult

        result = QueryResult(columns=["a"], data=[], row_count=0, truncated=True)
        assert "truncated=True" in repr(result)


class TestTruncationAndProvenance:
    def test_truncated_and_provenance_are_surfaced(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=re.compile(r".*/api/query/projects/.*/query$"),
            json=payloads.query_result(
                truncated=True, provenance=[{"document_id": "d1"}]
            ),
        )
        result = session.query("SELECT * FROM t", include_provenance=True)
        assert result.truncated is True
        assert result.provenance == [{"document_id": "d1"}]
        body = json.loads(httpx_mock.get_requests()[-1].content)
        assert body["include_provenance"] is True
