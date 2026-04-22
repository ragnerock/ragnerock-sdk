"""End-to-end query flows.

Querying always works even against an empty project: ``SELECT`` against the
built-in ``documents`` table should return well-shaped results regardless of
project contents. Syntax errors surface as :class:`QueryError`.
"""

from __future__ import annotations

import pytest

from ragnerock import QueryError, QueryResult


class TestExecute:
    def test_query_documents_table(self, session):
        """Query the built-in documents table. Always succeeds, may return 0 rows."""
        result = session.query("SELECT id, name FROM documents LIMIT 5")
        assert isinstance(result, QueryResult)
        assert "id" in result.columns
        assert isinstance(result.row_count, int)

    def test_query_respects_limit(self, session):
        """A LIMIT clause caps the result set regardless of project size."""
        result = session.query("SELECT id FROM documents LIMIT 3")
        assert result.row_count <= 3


class TestQueryResultConversion:
    def test_to_dict(self, session):
        result = session.query("SELECT id, name FROM documents LIMIT 5")
        rows = result.to_dict()
        assert isinstance(rows, list)
        assert len(rows) == result.row_count
        if rows:
            assert "id" in rows[0]

    def test_to_pandas(self, session):
        try:
            import pandas  # noqa: F401
        except ImportError:
            pytest.skip("pandas not installed; install 'ragnerock[pandas]' to run")

        result = session.query("SELECT id, name FROM documents LIMIT 5")
        df = result.to_pandas()
        assert len(df) == result.row_count

    def test_len(self, session):
        result = session.query("SELECT id FROM documents LIMIT 5")
        assert len(result) == result.row_count


class TestErrorMapping:
    def test_bad_syntax_raises_query_error(self, session):
        with pytest.raises(QueryError):
            session.query("SELEKT * FROM documents")
