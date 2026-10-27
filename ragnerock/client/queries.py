"""Annotation SQL query and saved-query endpoints (``/api/query/...``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _body, _Section
from ragnerock.timestamps import UtcDatetime


class QueryResultResponse(_ApiModel):
    """Response payload for an annotation SQL query.

    Carries the result columns, row data, row count, and optional
    server-reported execution time. ``truncated`` is ``True`` when the query
    matched more rows than the requested limit; ``provenance`` is filled only
    when the request asked for it.
    """

    columns: list[str]
    data: list[dict[str, Any]]
    row_count: int
    truncated: bool = False
    query_time_ms: int | None = None
    provenance: Any = None


class SavedQueryResponse(_ApiModel):
    """Response payload representing a saved query.

    List responses carry a compact item shape (no ``project_id`` or SQL);
    fetch the query by id for the full record.
    """

    id: UUID
    name: str
    project_id: UUID | None = None
    query_sql: str | None = None
    description: str | None = None
    folder_id: UUID | None = None
    created_by_id: UUID | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None


class SavedQueryListResponse(_ApiModel):
    """Paginated list response for saved queries."""

    queries: list[SavedQueryResponse]
    total: int
    skip: int
    limit: int


class _QueriesSection(_Section):
    """Annotation SQL query and saved-query endpoints."""

    def execute(
        self,
        *,
        project_id: UUID,
        query: str,
        format: str = "dataframe",
        limit: int = 1000,
        timeout: int | None = None,
        hide_key_columns: bool = False,
        include_provenance: bool = False,
    ) -> QueryResultResponse:
        """Run a SQL query against a project's annotations.

        Calls ``POST /api/query/projects/{project_id}/query``.

        Args:
            project_id (UUID): Project whose annotations to query.
            query (str): SQL text. Tables are operator names; columns come from
                each operator's JSON schema.
            format (str): Server-side result format. ``"dataframe"`` (the default)
                returns rows and columns suitable for tabular conversion.
            limit (int): Maximum rows to return. Applied in SQL, so
                ``row_count`` is what came back rather than what matched;
                check ``truncated`` to see whether more rows exist.
            timeout (int | None): Server-side execution timeout in seconds. ``None`` uses
                the server default.
            hide_key_columns (bool): Leave key columns such as ``document_id``
                and ``annotation_id`` out of each ``*`` in the outermost
                ``SELECT``. Columns the query names are returned either way.
            include_provenance (bool): Also report where each result column and
                row came from. Never changes the columns or rows returned.

        Returns:
            QueryResultResponse: A :class:`QueryResultResponse` carrying columns, rows, the row
            count, and server-reported execution time.

        Raises:
            QueryError: If the query fails parsing, validation, or
                execution.
        """
        body: dict[str, Any] = {
            "query": query,
            "format": format,
            "limit": limit,
            "hide_key_columns": hide_key_columns,
            "include_provenance": include_provenance,
        }
        if timeout is not None:
            body["timeout"] = timeout
        response = self._parent._request(
            "POST",
            f"/api/query/projects/{project_id}/query",
            json_body=body,
        )
        return QueryResultResponse.model_validate(response.json())

    def create(
        self,
        project_id: UUID,
        *,
        name: str,
        query_sql: str,
        description: str | None = None,
    ) -> SavedQueryResponse:
        """Save a query in a project.

        Calls ``POST /api/query/projects/{project_id}/saved-queries``.

        Args:
            project_id (UUID): Project to save the query in.
            name (str): Name for the query.
            query_sql (str): The SQL to save.
            description (str | None): Optional description.

        Returns:
            SavedQueryResponse: The saved query.
        """
        body = _body(name=name, query_sql=query_sql, description=description)
        response = self._parent._request(
            "POST",
            f"/api/query/projects/{project_id}/saved-queries",
            json_body=body,
        )
        return SavedQueryResponse.model_validate(response.json())

    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> SavedQueryListResponse:
        """List saved queries, optionally scoped to one or more projects.

        Calls ``GET /api/query/saved-queries/``.

        Args:
            project_ids (str | None): Comma-separated string of project UUIDs, or
                ``None`` to list across every accessible project.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            SavedQueryListResponse: A page of saved queries.
        """
        response = self._parent._request(
            "GET",
            "/api/query/saved-queries/",
            params={"project_ids": project_ids, "skip": skip, "limit": limit},
        )
        return SavedQueryListResponse.model_validate(response.json())

    def get(self, query_id: UUID) -> SavedQueryResponse:
        """Fetch a saved query by id.

        Calls ``GET /api/query/saved-queries/{query_id}``.

        Args:
            query_id (UUID): The saved query.

        Returns:
            SavedQueryResponse: The saved query, including its SQL.

        Raises:
            NotFoundError: If no saved query has that id.
        """
        response = self._parent._request("GET", f"/api/query/saved-queries/{query_id}")
        return SavedQueryResponse.model_validate(response.json())

    def update(
        self,
        query_id: UUID,
        *,
        name: str | None = None,
        query_sql: str | None = None,
        description: str | None = None,
    ) -> SavedQueryResponse:
        """Patch a saved query; omitted fields are left unchanged.

        Calls ``PUT /api/query/saved-queries/{query_id}``.

        Args:
            query_id (UUID): The saved query to update.
            name (str | None): New name.
            query_sql (str | None): New SQL.
            description (str | None): New description.

        Returns:
            SavedQueryResponse: The updated saved query.
        """
        body = _body(name=name, query_sql=query_sql, description=description)
        response = self._parent._request(
            "PUT", f"/api/query/saved-queries/{query_id}", json_body=body
        )
        return SavedQueryResponse.model_validate(response.json())

    def delete(self, query_id: UUID) -> None:
        """Delete a saved query.

        Calls ``DELETE /api/query/saved-queries/{query_id}``.

        Args:
            query_id (UUID): The saved query to delete.

        Raises:
            NotFoundError: If no saved query has that id.
        """
        self._parent._request("DELETE", f"/api/query/saved-queries/{query_id}")
