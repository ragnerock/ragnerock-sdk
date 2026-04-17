"""Workflow and WorkflowNode resources."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from ragnerock.resources.base import _Resource


class WorkflowNode(_Resource):
    """One node in a workflow — wraps an operator with execution configuration.

    Attributes:
        id: Node UUID within the workflow.
        workflow_id: Parent workflow.
        operator_id: Operator this node executes.
        operator_name: Cached operator name.
        condition: Optional predicate restricting when the node fires.
        persist: Whether annotations produced here are persisted.
        on_error: Error-handling policy (``"FAIL_JOB"``, ``"SKIP_NODE"``, etc.).
        max_retries: Retry count on transient failure.
        in_nodes: Upstream node IDs.
        out_nodes: Downstream node IDs.
    """

    id: UUID | None = None
    workflow_id: UUID | None = None
    operator_id: UUID | None = None
    operator_name: str | None = None
    condition: dict[str, Any] | None = None
    persist: bool = True
    on_error: str = "FAIL_JOB"
    max_retries: int = 0
    in_nodes: list[UUID] = []
    out_nodes: list[UUID] = []


class Workflow(_Resource):
    """A DAG of operators to run against documents.

    Workflows don't execute on their own — run them with
    ``session.run(workflow, documents=[...])``, which creates jobs.

    Attributes:
        id: Server-assigned UUID. ``None`` until committed.
        project_id: Owning project.
        name: Workflow name.
        description: Human-readable description.
        is_active: Whether the workflow is enabled.
        auto_run_on_upload: Whether the server automatically runs this
            workflow on document uploads in this project.
        created_by_id: User who created the workflow.
        created_at: Creation timestamp.
        updated_at: Last-modified timestamp.
        execution_order: Topological order of node IDs.
        nodes: The workflow's nodes.
    """

    id: UUID | None = None
    project_id: UUID | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool = True
    auto_run_on_upload: bool = True
    created_by_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    execution_order: list[UUID] = []
    nodes: list[WorkflowNode] = []
