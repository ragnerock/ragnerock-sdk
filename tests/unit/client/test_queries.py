"""Tests for the query section: SQL execution and saved queries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from ragnerock.client import RagnerockClient
from ragnerock.errors import NotFoundError, QueryError
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

QUERY_ID = uuid.UUID("00000000-0000-4000-8000-000000000c01")
USER_ID = "00000000-0000-4000-8000-0000000000aa"
QUERY_URL = url(f"/api/query/projects/{PROJECT_ID}/query")

_RESULT: dict[str, Any] = {
    "columns": ["name", "topic"],
    "data": [{"name": "a.pdf", "topic": "finance"}],
    "row_count": 1,
    "truncated": True,
    "query_time_ms": 12,
}


def _saved(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(QUERY_ID),
        "project_id": PROJECT_ID,
        "created_by_id": USER_ID,
        "name": "Finance docs",
        "query_sql": "SELECT * FROM topics WHERE topic = 'finance'",
        "description": None,
        "created_at": "2026-02-01T00:00:00Z",
        "updated_at": "2026-02-02T00:00:00Z",
    }
    payload.update(overrides)
    return payload


class TestExecute:
    def test_default_body_and_parsed_result(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(method="POST", url=QUERY_URL, json=_RESULT)

        result = client.queries.execute(
            project_id=uuid.UUID(PROJECT_ID), query="SELECT * FROM documents"
        )

        assert last_request(httpx_mock).method == "POST"
        assert last_json(httpx_mock) == {
            "query": "SELECT * FROM documents",
            "format": "dataframe",
            "limit": 1000,
            "hide_key_columns": False,
            "include_provenance": False,
        }
        assert result.columns == ["name", "topic"]
        assert result.row_count == 1
        assert result.truncated is True
        assert result.query_time_ms == 12
        assert result.provenance is None

    def test_forwards_options_and_parses_provenance(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        provenance = {"status": "analyzed", "columns": [], "rows": []}
        httpx_mock.add_response(
            method="POST", url=QUERY_URL, json={**_RESULT, "provenance": provenance}
        )

        result = client.queries.execute(
            project_id=uuid.UUID(PROJECT_ID),
            query="SELECT 1",
            format="json",
            limit=5,
            timeout=30,
            hide_key_columns=True,
            include_provenance=True,
        )

        body = last_json(httpx_mock)
        assert body["format"] == "json"
        assert body["limit"] == 5
        assert body["timeout"] == 30
        assert body["hide_key_columns"] is True
        assert body["include_provenance"] is True
        assert result.provenance == provenance

    def test_truncated_defaults_to_false(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=QUERY_URL,
            json={"columns": [], "data": [], "row_count": 0},
        )

        result = client.queries.execute(
            project_id=uuid.UUID(PROJECT_ID), query="SELECT 1"
        )

        assert result.truncated is False

    def test_structured_query_error_is_raised(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=QUERY_URL,
            status_code=400,
            json={
                "detail": {
                    "error_code": "UNKNOWN_TABLE",
                    "message": "Table 'nope' does not exist",
                    "suggestion": "Use one of: documents, chunks",
                }
            },
        )

        with pytest.raises(QueryError) as exc_info:
            client.queries.execute(
                project_id=uuid.UUID(PROJECT_ID), query="SELECT * FROM nope"
            )

        assert exc_info.value.error_code == "UNKNOWN_TABLE"
        assert exc_info.value.status_code == 400
        assert exc_info.value.suggestion == "Use one of: documents, chunks"

    def test_missing_project_raises_not_found(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=QUERY_URL,
            status_code=404,
            json={"detail": "Project not found"},
        )

        with pytest.raises(NotFoundError):
            client.queries.execute(project_id=uuid.UUID(PROJECT_ID), query="SELECT 1")


class TestSavedQueries:
    def test_create(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/query/projects/{PROJECT_ID}/saved-queries"),
            json=_saved(),
        )

        result = client.queries.create(
            uuid.UUID(PROJECT_ID),
            name="Finance docs",
            query_sql="SELECT * FROM topics WHERE topic = 'finance'",
        )

        assert last_json(httpx_mock) == {
            "name": "Finance docs",
            "query_sql": "SELECT * FROM topics WHERE topic = 'finance'",
        }
        assert result.id == QUERY_ID
        assert result.project_id == uuid.UUID(PROJECT_ID)
        assert result.created_at == datetime(2026, 2, 1, tzinfo=UTC)

    def test_create_with_description(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/query/projects/{PROJECT_ID}/saved-queries"),
            json=_saved(description="All finance"),
        )

        client.queries.create(
            uuid.UUID(PROJECT_ID), name="n", query_sql="SELECT 1", description="d"
        )

        assert last_json(httpx_mock)["description"] == "d"

    def test_list(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/query/saved-queries/?project_ids={PROJECT_ID}&skip=0&limit=100"
            ),
            json={
                "queries": [
                    {
                        "id": str(QUERY_ID),
                        "name": "Finance docs",
                        "description": None,
                        "folder_id": None,
                        "created_at": "2026-02-01T00:00:00Z",
                    }
                ],
                "total": 1,
                "skip": 0,
                "limit": 100,
            },
        )

        result = client.queries.list(project_ids=PROJECT_ID)

        assert result.total == 1
        item = result.queries[0]
        assert item.name == "Finance docs"
        assert item.query_sql is None

    def test_list_defaults(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/query/saved-queries/?skip=0&limit=100"),
            json={"queries": [], "total": 0, "skip": 0, "limit": 100},
        )

        client.queries.list()

        assert "project_ids" not in last_params(httpx_mock)

    def test_get(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET", url=url(f"/api/query/saved-queries/{QUERY_ID}"), json=_saved()
        )

        result = client.queries.get(QUERY_ID)

        assert result.query_sql == "SELECT * FROM topics WHERE topic = 'finance'"
        assert result.created_by_id == uuid.UUID(USER_ID)

    def test_update_sends_only_given_fields(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/query/saved-queries/{QUERY_ID}"),
            json=_saved(name="Renamed"),
        )

        result = client.queries.update(QUERY_ID, name="Renamed")

        assert last_json(httpx_mock) == {"name": "Renamed"}
        assert result.name == "Renamed"

    def test_delete(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/query/saved-queries/{QUERY_ID}"),
            json={"message": "deleted"},
        )

        assert client.queries.delete(QUERY_ID) is None
        assert last_request(httpx_mock).method == "DELETE"

    def test_delete_missing_raises(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/query/saved-queries/{QUERY_ID}"),
            status_code=404,
            json={"detail": "Saved query not found"},
        )

        with pytest.raises(NotFoundError):
            client.queries.delete(QUERY_ID)
