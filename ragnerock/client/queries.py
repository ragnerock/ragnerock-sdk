"""Annotation SQL query endpoints (``/api/query/...``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section


class QueryResultResponse(_ApiModel):
    """Response payload for an annotation SQL query.

    Carries the result columns, row data, row count, and optional
    server-reported execution time.
    """

    columns: list[str]
    data: list[dict[str, Any]]
    row_count: int
    query_time_ms: int | None = None


class _QueriesSection(_Section):
    """Annotation SQL query endpoints."""

    def execute(
        self,
        *,
        project_id: UUID,
        query: str,
        format: str = "dataframe",
        limit: int = 1000,
        timeout: int | None = None,
    ) -> QueryResultResponse:
        """Run a SQL query against a project's annotations.

        Calls ``POST /api/query/projects/{project_id}/query``.

        Args:
            project_id (UUID): Project whose annotations to query.
            query (str): SQL text. Tables are operator names; columns come from
                each operator's JSON schema.
            format (str): Server-side result format. ``"dataframe"`` (the default)
                returns rows and columns suitable for tabular conversion.
            limit (int): Maximum rows to return.
            timeout (int | None): Server-side execution timeout in seconds. ``None`` uses
                the server default.

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
        }
        if timeout is not None:
            body["timeout"] = timeout
        response = self._parent._request(
            "POST",
            f"/api/query/projects/{project_id}/query",
            json_body=body,
        )
        return QueryResultResponse.model_validate(response.json())
