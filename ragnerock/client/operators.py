"""Operator endpoints (``/api/operators/...``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section


class OperatorResponse(_ApiModel):
    """Response payload representing a single operator."""

    id: UUID
    project_id: UUID | None = None
    name: str


class OperatorListResponse(_ApiModel):
    """Paginated list response for operators."""

    operators: list[OperatorResponse]
    total: int
    skip: int
    limit: int


class _OperatorsSection(_Section):
    """Operator CRUD endpoints."""

    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> OperatorListResponse:
        """List operators, optionally scoped to one or more projects.

        Calls ``GET /api/operators/``.

        Args:
            project_ids (str | None): Comma-separated string of project UUIDs, or ``None``
                to list across every accessible project.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            OperatorListResponse: A page of operators.
        """
        response = self._parent._request(
            "GET",
            "/api/operators/",
            params={"project_ids": project_ids, "skip": skip, "limit": limit},
        )
        return OperatorListResponse.model_validate(response.json())

    def get(self, operator_id: UUID) -> OperatorResponse:
        """Fetch a single operator by id.

        Calls ``GET /api/operators/{operator_id}``.

        Args:
            operator_id (UUID): UUID of the operator.

        Returns:
            OperatorResponse: The operator response.

        Raises:
            NotFoundError: If no operator has that id.
        """
        response = self._parent._request("GET", f"/api/operators/{operator_id}")
        return OperatorResponse.model_validate(response.json())

    def create(
        self,
        *,
        project_id: UUID,
        name: str,
        jsonschema: dict[str, Any],
        generation_prompt: str,
        chunk_type: int,
        description: str | None = None,
        batch_size: int | None = None,
        multi_annotation: bool = False,
    ) -> OperatorResponse:
        """Create an operator.

        Calls ``POST /api/operators/``.

        Args:
            project_id (UUID): Owning project.
            name (str): Operator name. Becomes the queryable table name in
                annotation SQL; must be unique within the project.
            jsonschema (dict[str, Any]): JSON Schema describing each annotation's shape.
            generation_prompt (str): LLM prompt used to produce annotations.
            chunk_type (int): Integer value of a :class:`ChunkType` — the scope
                at which the operator runs.
            description (str | None): Optional human-readable description.
            batch_size (int | None): Batch size for annotation generation.
            multi_annotation (bool): Whether the operator may emit more than one
                annotation per input chunk.

        Returns:
            OperatorResponse: The newly created operator response.
        """
        body: dict[str, Any] = {
            "project_id": str(project_id),
            "name": name,
            "jsonschema": jsonschema,
            "generation_prompt": generation_prompt,
            "chunk_type": chunk_type,
            "multi_annotation": multi_annotation,
        }
        if description is not None:
            body["description"] = description
        if batch_size is not None:
            body["batch_size"] = batch_size
        response = self._parent._request("POST", "/api/operators/", json_body=body)
        return OperatorResponse.model_validate(response.json())

    def update(
        self,
        operator_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        jsonschema: dict[str, Any] | None = None,
        generation_prompt: str | None = None,
        chunk_type: int | None = None,
        batch_size: int | None = None,
        multi_annotation: bool | None = None,
    ) -> OperatorResponse:
        """Patch an operator's writable fields.

        Calls ``PUT /api/operators/{operator_id}``. Only fields passed as
        non-``None`` are sent. Changing ``jsonschema`` or ``chunk_type`` can
        invalidate existing annotations — the server enforces its own
        compatibility rules.

        Args:
            operator_id (UUID): Operator to update.
            name (str | None): New name.
            description (str | None): New description.
            jsonschema (dict[str, Any] | None): New JSON Schema.
            generation_prompt (str | None): New LLM prompt.
            chunk_type (int | None): New integer :class:`ChunkType` value.
            batch_size (int | None): New batch size.
            multi_annotation (bool | None): Whether the operator now emits multiple
                annotations per input.

        Returns:
            OperatorResponse: The updated operator response.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if jsonschema is not None:
            body["jsonschema"] = jsonschema
        if generation_prompt is not None:
            body["generation_prompt"] = generation_prompt
        if chunk_type is not None:
            body["chunk_type"] = chunk_type
        if batch_size is not None:
            body["batch_size"] = batch_size
        if multi_annotation is not None:
            body["multi_annotation"] = multi_annotation
        response = self._parent._request(
            "PUT", f"/api/operators/{operator_id}", json_body=body
        )
        return OperatorResponse.model_validate(response.json())

    def delete(self, operator_id: UUID) -> None:
        """Delete an operator.

        Calls ``DELETE /api/operators/{operator_id}``. Workflows and
        annotations referencing the operator may break — callers should
        clean those up first (or be ready for the server's reference
        semantics, which may cascade or reject).

        Args:
            operator_id (UUID): Operator to delete.
        """
        self._parent._request("DELETE", f"/api/operators/{operator_id}")
