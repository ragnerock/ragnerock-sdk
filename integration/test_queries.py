"""End-to-end query flows.

Querying always works even against an empty project: `SELECT 1` and queries
against the built-in ``documents`` / ``chunks`` tables should return well-shaped
results regardless of project contents.
"""

from __future__ import annotations

from ragnerock import QueryError, QueryResult


def test_query_documents_table(session):
    """Query the built-in documents table. Always succeeds, may return 0 rows."""
    result = session.query("SELECT id, name FROM documents LIMIT 5")
    assert isinstance(result, QueryResult)
    assert result.columns == ["id", "name"] or "id" in result.columns
    assert isinstance(result.row_count, int)
    # Converts to dicts.
    assert isinstance(result.to_dict(), list)


def test_query_to_pandas(session):
    pd_available = False
    try:
        import pandas as pd  # noqa: F401

        pd_available = True
    except ImportError:
        pass

    if not pd_available:
        import pytest

        pytest.skip("pandas not installed; install 'ragnerock[pandas]' to run")

    result = session.query("SELECT id, name FROM documents LIMIT 5")
    df = result.to_pandas()
    assert len(df) == result.row_count


def test_bad_syntax_raises_query_error(session):
    import pytest

    with pytest.raises(QueryError):
        session.query("SELEKT * FROM documents")
