"""Operator endpoints (``/api/operators/...``).

Operators are called "agents" in the Ragnerock UI and in GitOps manifests.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragnerock.client._base import UNSET, _ApiModel, _body, _patch_body, _Section


class OperatorResponse(_ApiModel):
    """Response payload representing a single operator.

    List responses carry a compact item shape (no ``project_id``, prompt or
    code); fetch the operator by id for the full record.
    """

    id: UUID
    project_id: UUID | None = None
    name: str
    description: str | None = None
    operator_kind: str | None = None
    chunk_type: int | None = None
    jsonschema: dict[str, Any] | None = None
    output_schema_id: UUID | None = None
    generation_prompt: str | None = None
    code_source: str | None = None
    ai_config_id: UUID | None = None
    model_name: str | None = None
    warnings: list[str] = []


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
        active_only: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> OperatorListResponse:
        """List operators, optionally scoped to one or more projects.

        Calls ``GET /api/operators/``.

        Args:
            project_ids (str | None): Comma-separated string of project UUIDs, or ``None``
                to list across every accessible project.
            active_only (bool): Exclude archived operators.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            OperatorListResponse: A page of operators.
        """
        response = self._parent._request(
            "GET",
            "/api/operators/",
            params={
                "project_ids": project_ids,
                "active_only": active_only,
                "skip": skip,
                "limit": limit,
            },
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
        chunk_type: int,
        operator_kind: str = "LLM",
        jsonschema: dict[str, Any] | None = None,
        output_schema_id: UUID | None = None,
        generation_prompt: str | None = None,
        description: str | None = None,
        batch_size: int | None = None,
        input_columns: list[str] | None = None,
        multi_annotation: bool = False,
        code_source: str | None = None,
        network_access: bool = False,
        code_timeout_seconds: int | None = None,
        ai_config_id: UUID | None = None,
        model_name: str | None = None,
        skill_ids: list[UUID] | None = None,
        tool_ids: list[UUID] | None = None,
        notification_template: str | None = None,
        change_request_prompt: str | None = None,
        change_request_signal: str | None = None,
    ) -> OperatorResponse:
        """Create an operator.

        Calls ``POST /api/operators/``. The kind is always explicit and decides
        which payload applies:

        - ``"LLM"``: needs ``generation_prompt``; may bind ``ai_config_id`` /
          ``model_name``, ``skill_ids`` and ``tool_ids``.
        - ``"CODE"``: needs ``code_source`` (a Python snippet defining
          ``main()``), which the server security-reviews.
        - ``"MESSAGE"``: needs ``notification_template``.
        - ``"CHANGE_REQUEST"``: needs ``change_request_prompt`` at document scope.
        - ``"MANUAL"``: none of the above.

        The output shape comes from exactly one of ``jsonschema`` (the operator
        gets its own schema) or ``output_schema_id`` (link an existing schema).

        Args:
            project_id (UUID): Owning project.
            name (str): Operator name. Becomes the queryable table name in
                annotation SQL; must be unique within the project.
            chunk_type (int): Integer value of a
                :class:`~ragnerock.resources.chunk.ChunkType` — the scope the
                operator runs at.
            operator_kind (str): A :class:`~ragnerock.resources.operator.OperatorKind` value.
            jsonschema (dict[str, Any] | None): JSON Schema describing each annotation's shape.
            output_schema_id (UUID | None): An existing schema to link instead.
            generation_prompt (str | None): Prompt for LLM operators.
            description (str | None): Optional human-readable description.
            batch_size (int | None): Rows per LLM call; ROW scope only.
            input_columns (list[str] | None): Sheet columns a ROW/SHEET
                operator is shown, by exact name. ``None`` shows every column.
            multi_annotation (bool): Whether the operator may emit more than one
                annotation per input.
            code_source (str | None): Python source for CODE operators.
            network_access (bool): Whether a CODE operator may reach the network.
            code_timeout_seconds (int | None): Per-execution deadline for a CODE
                operator; ``None`` uses the platform default.
            ai_config_id (UUID | None): AI provider config to bind (LLM only).
            model_name (str | None): Model override (LLM only).
            skill_ids (list[UUID] | None): Skills an LLM operator may load.
            tool_ids (list[UUID] | None): Agent tools an LLM operator may call.
            notification_template (str | None): Message template for MESSAGE
                operators, with optional ``{{ operator.field }}`` placeholders.
            change_request_prompt (str | None): Instructions for a
                CHANGE_REQUEST operator.
            change_request_signal (str | None): Optional per-document signal
                template for a CHANGE_REQUEST operator.

        Returns:
            OperatorResponse: The newly created operator response.
        """
        body = _body(
            project_id=project_id,
            name=name,
            description=description,
            operator_kind=operator_kind,
            chunk_type=int(chunk_type),
            jsonschema=jsonschema,
            output_schema_id=output_schema_id,
            generation_prompt=generation_prompt,
            batch_size=batch_size,
            input_columns=input_columns,
            multi_annotation=multi_annotation,
            code_source=code_source,
            network_access=network_access,
            code_timeout_seconds=code_timeout_seconds,
            ai_config_id=ai_config_id,
            model_name=model_name,
            skill_ids=skill_ids,
            tool_ids=tool_ids,
            notification_template=notification_template,
            change_request_prompt=change_request_prompt,
            change_request_signal=change_request_signal,
        )
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
        operator_kind: str | None = None,
        multi_annotation: bool | None = None,
        code_source: str | None = None,
        network_access: bool | None = None,
        skill_ids: list[UUID] | None = None,
        tool_ids: list[UUID] | None = None,
        notification_template: str | None = None,
        change_request_prompt: str | None = None,
        batch_size: Any = UNSET,
        input_columns: Any = UNSET,
        code_timeout_seconds: Any = UNSET,
        ai_config_id: Any = UNSET,
        model_name: Any = UNSET,
        change_request_signal: Any = UNSET,
    ) -> OperatorResponse:
        """Patch an operator's writable fields; omitted fields are left unchanged.

        Calls ``PUT /api/operators/{operator_id}``. For most fields ``None``
        means "leave unchanged". The fields defaulting to
        :data:`~ragnerock.client.UNSET` — ``batch_size``, ``input_columns``,
        ``code_timeout_seconds``, ``ai_config_id``, ``model_name`` and
        ``change_request_signal`` — distinguish the two: omit them to leave the
        stored value alone, or pass ``None`` to clear it. Clearing
        ``batch_size`` is required when moving scope off ROW, and clearing
        ``input_columns`` when moving off ROW/SHEET.

        Changing ``jsonschema`` or ``chunk_type`` can invalidate existing
        annotations — the server enforces its own compatibility rules.

        Args:
            operator_id (UUID): Operator to update.
            name (str | None): New name.
            description (str | None): New description.
            jsonschema (dict[str, Any] | None): New JSON Schema.
            generation_prompt (str | None): New LLM prompt.
            chunk_type (int | None): New integer :class:`~ragnerock.resources.chunk.ChunkType` value.
            operator_kind (str | None): New kind; fields the new kind forbids
                are cleared server-side.
            multi_annotation (bool | None): Whether the operator now emits multiple
                annotations per input.
            code_source (str | None): New Python snippet.
            network_access (bool | None): New network-access flag.
            skill_ids (list[UUID] | None): Replacement skill selection;
                ``[]`` clears it.
            tool_ids (list[UUID] | None): Replacement tool selection;
                ``[]`` clears it.
            notification_template (str | None): New MESSAGE template.
            change_request_prompt (str | None): New CHANGE_REQUEST instructions.
            batch_size (int | None): New rows per LLM call; ``None`` clears.
            input_columns (list[str] | None): New column selection; ``None``
                clears (shows every column).
            code_timeout_seconds (int | None): New CODE deadline; ``None``
                restores the platform default.
            ai_config_id (UUID | None): New AI config binding; ``None`` clears.
            model_name (str | None): New model override; ``None`` clears.
            change_request_signal (str | None): New signal template; ``None``
                clears.

        Returns:
            OperatorResponse: The updated operator response.
        """
        body = _body(
            name=name,
            description=description,
            jsonschema=jsonschema,
            generation_prompt=generation_prompt,
            chunk_type=int(chunk_type) if chunk_type is not None else None,
            operator_kind=operator_kind,
            multi_annotation=multi_annotation,
            code_source=code_source,
            network_access=network_access,
            skill_ids=skill_ids,
            tool_ids=tool_ids,
            notification_template=notification_template,
            change_request_prompt=change_request_prompt,
        )
        body.update(
            _patch_body(
                batch_size=batch_size,
                input_columns=input_columns,
                code_timeout_seconds=code_timeout_seconds,
                ai_config_id=ai_config_id,
                model_name=model_name,
                change_request_signal=change_request_signal,
            )
        )
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
