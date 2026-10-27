"""Workflow endpoints (``/api/workflows/...``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section, _stringify_uuids


class WorkflowResponse(_ApiModel):
    """Response payload representing a single workflow."""

    id: UUID
    project_id: UUID | None = None
    name: str


class WorkflowListResponse(_ApiModel):
    """Paginated list response for workflows."""

    workflows: list[WorkflowResponse]
    total: int
    skip: int
    limit: int


class WorkflowNodeResponse(_ApiModel):
    """Response payload representing a single workflow node."""

    id: UUID
    workflow_id: UUID
    operator_id: UUID


class _WorkflowsSection(_Section):
    """Workflow CRUD endpoints plus node management."""

    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> WorkflowListResponse:
        """List workflows, optionally scoped to one or more projects.

        Calls ``GET /api/workflows/``.

        Args:
            project_ids (str | None): Comma-separated string of project UUIDs, or ``None``
                to list across every accessible project.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            WorkflowListResponse: A page of workflows.
        """
        response = self._parent._request(
            "GET",
            "/api/workflows/",
            params={"project_ids": project_ids, "skip": skip, "limit": limit},
        )
        return WorkflowListResponse.model_validate(response.json())

    def get(self, workflow_id: UUID) -> WorkflowResponse:
        """Fetch a single workflow by id.

        Calls ``GET /api/workflows/{workflow_id}``.

        Args:
            workflow_id (UUID): UUID of the workflow.

        Returns:
            WorkflowResponse: The workflow response.

        Raises:
            NotFoundError: If no workflow has that id.
        """
        response = self._parent._request("GET", f"/api/workflows/{workflow_id}")
        return WorkflowResponse.model_validate(response.json())

    def create(
        self,
        *,
        project_id: UUID,
        name: str,
        description: str | None = None,
        is_active: bool = True,
        auto_run_on_upload: bool = False,
    ) -> WorkflowResponse:
        """Create a workflow with no nodes.

        Calls ``POST /api/workflows/``. Add operator nodes afterward with
        :meth:`add_node`.

        Args:
            project_id (UUID): Owning project.
            name (str): Workflow name.
            description (str | None): Optional description.
            is_active (bool): Whether the workflow is enabled and eligible to run.
            auto_run_on_upload (bool): Whether the server should run this workflow
                automatically when a document is uploaded to the project.

        Returns:
            WorkflowResponse: The newly created workflow response.
        """
        body: dict[str, Any] = {
            "project_id": str(project_id),
            "name": name,
            "is_active": is_active,
            "auto_run_on_upload": auto_run_on_upload,
        }
        if description is not None:
            body["description"] = description
        response = self._parent._request("POST", "/api/workflows/", json_body=body)
        return WorkflowResponse.model_validate(response.json())

    def update(
        self,
        workflow_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
        auto_run_on_upload: bool | None = None,
    ) -> WorkflowResponse:
        """Patch a workflow's writable fields.

        Calls ``PUT /api/workflows/{workflow_id}``. Only fields passed as
        non-``None`` are sent.

        Args:
            workflow_id (UUID): Workflow to update.
            name (str | None): New name.
            description (str | None): New description.
            is_active (bool | None): New enabled flag.
            auto_run_on_upload (bool | None): New auto-run flag.

        Returns:
            WorkflowResponse: The updated workflow response.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if is_active is not None:
            body["is_active"] = is_active
        if auto_run_on_upload is not None:
            body["auto_run_on_upload"] = auto_run_on_upload
        response = self._parent._request(
            "PUT", f"/api/workflows/{workflow_id}", json_body=body
        )
        return WorkflowResponse.model_validate(response.json())

    def delete(self, workflow_id: UUID) -> None:
        """Delete a workflow.

        Calls ``DELETE /api/workflows/{workflow_id}``. Running jobs belonging
        to the workflow are not cancelled implicitly — cancel them first if
        needed.

        Args:
            workflow_id (UUID): Workflow to delete.
        """
        self._parent._request("DELETE", f"/api/workflows/{workflow_id}")

    def add_node(
        self,
        workflow_id: UUID,
        *,
        operator_id: UUID,
        condition: dict[str, Any] | None = None,
        persist: bool = True,
        on_error: str = "SKIP_NODE",
        max_retries: int = 0,
        annotations_only: bool = False,
    ) -> WorkflowNodeResponse:
        """Append an operator node to a workflow.

        Calls ``PUT /api/workflows/{workflow_id}/nodes/``. The server slots
        the new node into the workflow's execution graph.

        Args:
            workflow_id (UUID): Workflow to add to.
            operator_id (UUID): Operator the node executes.
            condition (dict[str, Any] | None): Optional predicate restricting when the node fires
                (serialized per the server's condition grammar).
            persist (bool): Whether annotations produced here are persisted.
            on_error (str): Error-handling policy: ``"SKIP_NODE"`` (the
                default) or ``"FAIL_JOB"``.
            max_retries (int): Retry count on transient failure.
            annotations_only (bool): Whether the node only emits annotations.

        Returns:
            WorkflowNodeResponse: The newly created node response.
        """
        body: dict[str, Any] = {
            "operator_id": str(operator_id),
            "persist": persist,
            "on_error": on_error,
            "max_retries": max_retries,
            "annotations_only": annotations_only,
        }
        if condition is not None:
            body["condition"] = condition
        response = self._parent._request(
            "PUT",
            f"/api/workflows/{workflow_id}/nodes/",
            json_body=body,
        )
        return WorkflowNodeResponse.model_validate(response.json())

    def update_node(
        self,
        workflow_id: UUID,
        node_id: UUID,
        **fields: Any,
    ) -> WorkflowNodeResponse:
        """Patch a workflow node's fields.

        Calls ``PUT /api/workflows/{workflow_id}/nodes/{node_id}``. Kwargs
        are forwarded verbatim to the server after stringifying UUIDs and
        dropping ``None`` values, so this is intentionally flexible — callers
        should pass the exact field names the API expects (``operator_id``,
        ``condition``, ``persist``, ``on_error``, ``max_retries``,
        ``in_node_ids``, ``out_node_ids``).

        Args:
            workflow_id (UUID): Owning workflow.
            node_id (UUID): Node to update.
            **fields: Fields to patch. ``None`` values are dropped; ``UUID``
                values (including those inside lists) are stringified.

        Returns:
            WorkflowNodeResponse: The updated node response.
        """
        body = _stringify_uuids({k: v for k, v in fields.items() if v is not None})
        response = self._parent._request(
            "PUT",
            f"/api/workflows/{workflow_id}/nodes/{node_id}",
            json_body=body,
        )
        return WorkflowNodeResponse.model_validate(response.json())

    def delete_node(self, workflow_id: UUID, node_id: UUID) -> None:
        """Delete a node from a workflow.

        Calls ``DELETE /api/workflows/{workflow_id}/nodes/{node_id}``. The
        server rewires the surrounding graph; callers don't need to touch
        ``in_nodes``/``out_nodes`` manually.

        Args:
            workflow_id (UUID): Owning workflow.
            node_id (UUID): Node to delete.
        """
        self._parent._request(
            "DELETE",
            f"/api/workflows/{workflow_id}/nodes/{node_id}",
        )
