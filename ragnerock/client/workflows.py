"""Workflow endpoints (``/api/workflows/...``), including change requests."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from ragnerock.client._base import _ApiModel, _body, _Section
from ragnerock.client.jobs import CreateManualJobsResponse
from ragnerock.resources.document import FileType
from ragnerock.resources.workflow import WorkflowSchedule
from ragnerock.timestamps import UtcDatetime

_FUNCTION_NAME_DELIMITER = "__"
"""Separator between a tool's slug and a function name (``crm__get_customer``)."""


class ChangeRequestStatus(StrEnum):
    """Lifecycle of a workflow change request."""

    PENDING = "pending"
    """Open: collecting documents and awaiting review."""

    APPROVED = "approved"
    """A proposal was applied to the workflow."""

    REJECTED = "rejected"
    """A reviewer closed it without applying anything."""

    SUPERSEDED = "superseded"
    """The trigger or workflow it belonged to is gone."""


class ChangeProposalStatus(StrEnum):
    """Lifecycle of one proposal revision on a change request."""

    READY = "ready"
    """Generated and validated; approvable while it is the latest revision."""

    INVALID = "invalid"
    """Generated but failed validation; not approvable."""

    SUPERSEDED = "superseded"
    """A newer revision exists, or the request closed."""

    APPLIED = "applied"
    """This revision was approved and applied."""


# -- workflow responses -------------------------------------------------------


class WorkflowNodeInfo(_ApiModel):
    """A node as embedded in a workflow payload.

    Attributes:
        id (UUID): The node.
        operator_id (UUID | None): The operator the node runs.
        operator_name (str | None): That operator's name.
        condition (dict[str, Any] | None): When the node fires.
        in_nodes (list[UUID]): Upstream node ids.
        out_nodes (list[UUID]): Downstream node ids.
        target_resource_id (UUID | None): The file resource the node
            annotates; ``None`` means the workflow's only file resource.
        required_functions (list[str]): Functions the node's agent must call
            before it answers, in order.
    """

    id: UUID
    operator_id: UUID | None = None
    operator_name: str | None = None
    operator_kind: str | None = None
    operator_chunk_type: int | None = None
    condition: dict[str, Any] | None = None
    persist: bool = True
    on_error: str = "SKIP_NODE"
    annotations_only: bool = False
    decorators: list[dict[str, Any]] | None = None
    position_x: int | None = None
    position_y: int | None = None
    position_z: int | None = None
    in_nodes: list[UUID] = []
    out_nodes: list[UUID] = []
    target_resource_id: UUID | None = None
    context_resource_ids: list[UUID] = []
    include_schedule_context: bool = False
    required_functions: list[str] = []


class WorkflowResourceInfo(_ApiModel):
    """A workflow input (resource) as returned on workflow reads.

    Attributes:
        id (UUID): The resource.
        name (str): Unique within the workflow.
        type (str | None): ``"file"``, ``"value"``, or ``"ingest"``.
        source (dict[str, Any] | None): Where the platform fetches each
            version from; ``None`` for a resource supplied at run time.
    """

    id: UUID
    name: str
    type: str | None = None
    description: str | None = None
    media_type: str | None = None
    source: dict[str, Any] | None = None
    default_version_id: UUID | None = None
    position: int = 0


class WorkflowSinkInfo(_ApiModel):
    """A workflow output (sink) as returned on workflow reads.

    Attributes:
        id (UUID): The output; stable across edits.
        name (str): Unique within the workflow.
        kind (str | None): ``"notification"``, ``"email"``, or ``"artifact"``.
        parent_node_ids (list[UUID]): The nodes feeding the output.
        config (dict[str, Any]): What to deliver and where.
        issues (list[dict[str, Any]]): What is currently wrong with the output.
    """

    id: UUID
    name: str
    kind: str | None = None
    description: str | None = None
    parent_node_ids: list[UUID] = []
    scope: int | None = None
    position: int = 0
    node_id: UUID | None = None
    operator_id: UUID | None = None
    table_name: str | None = None
    config: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []


class ScheduleStateInfo(_ApiModel):
    """A schedule's runtime state, maintained by the server.

    Attributes:
        next_fire_at (datetime | None): The next slot the schedule is due.
        last_fire_at (datetime | None): The slot of the last run it created.
        last_error (str | None): Why the last fire failed, if it did.
        consecutive_failures (int): Failures since the last success.
        paused (bool): Whether repeated failures paused the schedule; see
            :meth:`_WorkflowsSection.resume_schedule`.
        runs_as_user_id (UUID | None): The identity every fire runs as.
    """

    next_fire_at: UtcDatetime = None
    last_fire_at: UtcDatetime = None
    last_error: str | None = None
    consecutive_failures: int = 0
    paused: bool = False
    runs_as_user_id: UUID | None = None
    runs_as_user_email: str | None = None


class WorkflowResponse(_ApiModel):
    """Response payload representing a single workflow.

    List responses carry a compact item shape (no nodes, sinks, or schedule;
    a ``node_count`` instead); fetch the workflow by id for the full record.
    """

    id: UUID
    project_id: UUID | None = None
    name: str
    description: str | None = None
    created_by_id: UUID | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None
    is_active: bool = True
    auto_run_on_upload: bool = False
    is_draft: bool = False
    node_count: int | None = None
    execution_order: list[str] = []
    nodes: list[WorkflowNodeInfo] = []
    resources: list[WorkflowResourceInfo] = []
    sinks: list[WorkflowSinkInfo] = []
    schedule: WorkflowSchedule | None = None
    schedule_state: ScheduleStateInfo | None = None
    schedules_enabled: bool = True
    pending_change_request_count: int = 0


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
    operator_name: str | None = None
    condition: dict[str, Any] | None = None
    condition_mode: str | None = None
    persist: bool = True
    on_error: str = "SKIP_NODE"
    max_retries: int = 0
    annotations_only: bool = False
    decorators: list[dict[str, Any]] | None = None
    position_x: int | None = None
    position_y: int | None = None
    position_z: int | None = None
    in_nodes: list[UUID] = []
    out_nodes: list[UUID] = []
    context_resource_ids: list[UUID] = []
    required_functions: list[str] = []


class SchedulePreviewResponse(_ApiModel):
    """What a crontab would do next.

    Attributes:
        fires (list[str]): The next fire times as RFC 3339 UTC strings,
            soonest first.
        errors (list[str]): Why the schedule is unusable; empty when
            ``fires`` is populated. These are the same messages saving the
            schedule would fail with.
    """

    fires: list[str] = []
    errors: list[str] = []


class ResourceTestFetchResponse(_ApiModel):
    """What one trial fetch of a resource source returned. Nothing is stored.

    Attributes:
        ok (bool): Whether the fetch succeeded.
        content_type (str | None): The media type the source declared.
        content_bytes (int): How much came back, up to the preview cap.
        truncated (bool): Whether the preview was cut at
            ``preview_max_bytes``. A real run reads more, so a truncated
            preview does not mean a truncated fetch.
        preview (str): The beginning of the payload as text.
        resolved_arguments (dict[str, Any]): The call's arguments after
            ``{{ schedule.* }}`` templates were rendered.
        error (str | None): Why the fetch failed, when it did.
    """

    ok: bool = False
    content_type: str | None = None
    content_bytes: int = 0
    truncated: bool = False
    preview_max_bytes: int = 0
    duration_ms: int = 0
    preview: str = ""
    resolved_arguments: dict[str, Any] = {}
    error: str | None = None


class ConditionTestResponse(_ApiModel):
    """The outcome of evaluating a node's condition against sample data.

    Attributes:
        result (bool): Whether the condition matched.
        evaluation_trace (str | None): How the condition was evaluated.
    """

    result: bool = False
    evaluation_trace: str | None = None


# -- change request responses -------------------------------------------------


class ChangeRequestResponse(_ApiModel):
    """A workflow change request, without its documents or proposals.

    Attributes:
        id (UUID): The change request.
        status (str | None): A :class:`ChangeRequestStatus` value.
        trigger_operator_name (str | None): The change-request agent that
            opened it.
        document_count (int): How many documents have been recorded on it.
        generating (bool): Whether a proposal is being generated.
        applied_proposal_id (UUID | None): The revision approval applied.
    """

    id: UUID
    project_id: UUID | None = None
    workflow_id: UUID | None = None
    trigger_operator_id: UUID | None = None
    trigger_operator_name: str | None = None
    status: str | None = None
    document_count: int = 0
    opened_quietly: bool = False
    generating: bool = False
    resolved_by_id: UUID | None = None
    resolved_at: UtcDatetime = None
    rejection_note: str | None = None
    applied_proposal_id: UUID | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None


class ChangeRequestList(_ApiModel):
    """A page of a workflow's change requests, newest first."""

    items: list[ChangeRequestResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class ChangeRequestDocumentResponse(_ApiModel):
    """One document recorded on a change request.

    Attributes:
        id (UUID): The record.
        document_id (UUID | None): The document.
        signal (str | None): What the change-request agent noted about it.
        backfill_run_id (UUID | None): The run that re-processed it after
            approval, once one has.
        document_missing (bool): The document was deleted before a backfill
            reached it, so it will never be re-run.
    """

    id: UUID
    change_request_id: UUID | None = None
    document_id: UUID | None = None
    job_id: UUID | None = None
    run_id: UUID | None = None
    signal: str | None = None
    backfill_job_id: UUID | None = None
    backfill_run_id: UUID | None = None
    document_missing: bool = False
    created_at: UtcDatetime = None


class ChangeRequestDocumentList(_ApiModel):
    """A page of the documents recorded on a change request, oldest first."""

    items: list[ChangeRequestDocumentResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class ChangeRequestSignalCount(_ApiModel):
    """How many recorded documents carried one signal."""

    signal: str
    count: int = 0


class ChangeProposalSummary(_ApiModel):
    """One revision in a change request's history, without its manifest."""

    id: UUID
    revision: int | None = None
    status: str | None = None
    summary: str | None = None
    reviewer_note: str | None = None
    created_at: UtcDatetime = None


class ChangeProposalResponse(_ApiModel):
    """One proposal revision, with its diff against the live workflow.

    Attributes:
        id (UUID): The revision.
        revision (int | None): Its number within the change request.
        status (str | None): A :class:`ChangeProposalStatus` value.
        summary (str | None): What the proposal changes, in plain language.
        validation_errors (list[str]): Why an invalid revision failed.
        proposed_manifest (list[dict[str, Any]]): The GitOps manifest that
            approving this revision would apply.
        diff (dict[str, Any]): The object, node, and edge differences, with
            warnings.
    """

    id: UUID
    change_request_id: UUID | None = None
    revision: int | None = None
    status: str | None = None
    summary: str | None = None
    reviewer_note: str | None = None
    validation_errors: list[str] = []
    created_at: UtcDatetime = None
    proposed_manifest: list[dict[str, Any]] = []
    diff: dict[str, Any] = {}


class ChangeRequestDetail(_ApiModel):
    """A change request with its signal tally, documents, and revisions.

    Attributes:
        request (ChangeRequestResponse): The change request.
        signals (list[ChangeRequestSignalCount]): Distinct signals with how
            many documents carried each, most frequent first.
        documents (ChangeRequestDocumentList | None): The first page of
            recorded documents; page through the rest with
            :meth:`_WorkflowChangeRequestsSection.documents`.
        revisions (list[ChangeProposalSummary]): Every revision, newest first.
        latest_proposal (ChangeProposalResponse | None): The newest revision
            with its diff, or ``None`` before the first is generated.
        documents_awaiting_backfill (int): Documents not yet re-run.
    """

    request: ChangeRequestResponse
    signals: list[ChangeRequestSignalCount] = []
    documents: ChangeRequestDocumentList | None = None
    revisions: list[ChangeProposalSummary] = []
    latest_proposal: ChangeProposalResponse | None = None
    documents_awaiting_backfill: int = 0


class ApproveChangeRequestResponse(_ApiModel):
    """What approving a change request applied.

    Attributes:
        operators_created (int): Agents the proposal added.
        operators_updated (int): Agents the proposal changed.
        orphaned_operators (list[str]): Agents no workflow uses any more.
            They are never deleted.
        snapshot_id (UUID | None): The restore point taken before applying.
        documents_awaiting_backfill (int): Recorded documents to re-run with
            :meth:`_WorkflowChangeRequestsSection.backfill`.
    """

    workflow_id: UUID | None = None
    operators_created: int = 0
    operators_updated: int = 0
    orphaned_operators: list[str] = []
    snapshot_id: UUID | None = None
    operator_version_ids: list[UUID] = []
    documents_awaiting_backfill: int = 0


class BackfillChangeRequestResponse(_ApiModel):
    """The runs one backfill call created.

    Attributes:
        job_ids (list[UUID]): The jobs created.
        run_ids (list[UUID]): The runs created.
        skipped_missing (int): Recorded documents since deleted; never re-run.
        remaining (int): Documents still awaiting a backfill. Call again while
            this is above zero.
    """

    job_ids: list[UUID] = []
    run_ids: list[UUID] = []
    skipped_missing: int = 0
    remaining: int = 0


# -- resource builders --------------------------------------------------------


def _file_type_name(file_type: FileType | str) -> str:
    """Return the wire form of a pulled file's type: its lowercase name.

    Args:
        file_type (FileType | str): A :class:`~ragnerock.resources.document.FileType`
            member or a type name such as ``"csv"``.

    Returns:
        str: The lowercase type name.
    """
    if isinstance(file_type, FileType):
        return file_type.name.lower()
    return file_type.lower()


def _sourced_resource(
    name: str,
    source: dict[str, Any],
    *,
    as_value: bool,
    file_type: FileType | str | None,
    embed: bool,
    description: str | None,
    position: int,
) -> dict[str, Any]:
    """Assemble a resource spec around a fetch source.

    Args:
        name (str): The resource name.
        source (dict[str, Any]): The kind-specific source fields.
        as_value (bool): Declare a ``value`` resource instead of a ``file``.
        file_type (FileType | str | None): The document type of a pulled file.
        embed (bool): Index a pulled file in project search.
        description (str | None): Optional description.
        position (int): Display order.

    Returns:
        dict[str, Any]: The resource spec.
    """
    source = {**source, "embed": embed}
    if file_type is not None:
        source["file_type"] = _file_type_name(file_type)
    spec: dict[str, Any] = {
        "name": name,
        "type": "value" if as_value else "file",
        "position": position,
        "source": source,
    }
    if description is not None:
        spec["description"] = description
    return spec


def tool_call_resource(
    name: str,
    *,
    tool: str,
    function: str,
    arguments: dict[str, Any] | None = None,
    as_value: bool = False,
    file_type: FileType | str | None = None,
    embed: bool = False,
    description: str | None = None,
    position: int = 0,
) -> dict[str, Any]:
    """Declare a workflow input the platform fetches by calling an agent tool.

    The call runs once per run, before any agent sees the input, with no model
    deciding whether or how to make it. String values inside ``arguments``
    may carry templates such as ``{{ schedule.window_start }}``, rendered per
    run.

    Args:
        name (str): The resource name.
        tool (str): The agent tool's slug.
        function (str): The function to call. A name qualified with the
            tool's slug (``"<slug>__<function>"``) is reduced to the function.
        arguments (dict[str, Any] | None): The call's arguments.
        as_value (bool): Declare a ``value`` resource (an inline payload for
            prompt context) instead of a ``file`` resource, which becomes a
            document that can be annotated.
        file_type (FileType | str | None): File resources only; the document
            type to store the payload as, e.g. ``FileType.CSV`` or ``"csv"``.
            ``None`` derives it from the response.
        embed (bool): File resources only; index the fetched document in
            project search. Off by default, since a recurring fetch would
            otherwise fill search with near-duplicates.
        description (str | None): Optional description.
        position (int): Display order.

    Returns:
        dict[str, Any]: A resource spec for :meth:`_WorkflowsSection.create`
        or :meth:`_WorkflowsSection.set_resources`. Its ``"source"`` entry can
        be passed to :meth:`_WorkflowsSection.test_fetch`.
    """
    prefix = f"{tool}{_FUNCTION_NAME_DELIMITER}"
    if function.startswith(prefix) and len(function) > len(prefix):
        function = function[len(prefix) :]
    return _sourced_resource(
        name,
        {
            "kind": "tool_call",
            "tool": tool,
            "function": function,
            "arguments": arguments or {},
        },
        as_value=as_value,
        file_type=file_type,
        embed=embed,
        description=description,
        position=position,
    )


def web_fetch_resource(
    name: str,
    url: str,
    *,
    as_value: bool = False,
    file_type: FileType | str | None = None,
    embed: bool = False,
    description: str | None = None,
    position: int = 0,
) -> dict[str, Any]:
    """Declare a workflow input the platform fetches by reading a fixed URL.

    The address is fixed by you, not chosen by a model, and is checked
    against the account's web access policy when the workflow is saved.

    Args:
        name (str): The resource name.
        url (str): The address to read.
        as_value (bool): Declare a ``value`` resource instead of a ``file``
            one. See :func:`tool_call_resource`.
        file_type (FileType | str | None): File resources only; see
            :func:`tool_call_resource`.
        embed (bool): File resources only; see :func:`tool_call_resource`.
        description (str | None): Optional description.
        position (int): Display order.

    Returns:
        dict[str, Any]: A resource spec for :meth:`_WorkflowsSection.create`
        or :meth:`_WorkflowsSection.set_resources`.
    """
    return _sourced_resource(
        name,
        {"kind": "web_fetch", "url": url},
        as_value=as_value,
        file_type=file_type,
        embed=embed,
        description=description,
        position=position,
    )


# -- sections -----------------------------------------------------------------


class _WorkflowChangeRequestsSection(_Section):
    """A workflow's change requests.

    A workflow's change-request agent opens a request when it fires, and a
    reviewer turns it into a proposed change to the workflow. Proposals are
    generated interactively in the workflow editor; this section reads,
    approves, rejects, and backfills them.
    """

    def _path(self, workflow_id: UUID, change_request_id: UUID | None = None) -> str:
        """Build a change-request path.

        Args:
            workflow_id (UUID): The workflow.
            change_request_id (UUID | None): The request, if any.

        Returns:
            str: The API path.
        """
        path = f"/api/workflows/{workflow_id}/change-requests"
        if change_request_id is not None:
            path = f"{path}/{change_request_id}"
        return path

    def list(
        self,
        workflow_id: UUID,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> ChangeRequestList:
        """List a workflow's change requests, newest first.

        Calls ``GET /api/workflows/{workflow_id}/change-requests``.

        Args:
            workflow_id (UUID): The workflow.
            status (str | None): Only requests in this
                :class:`ChangeRequestStatus`.
            skip (int): Requests to skip.
            limit (int): Page size (at most 200).

        Returns:
            ChangeRequestList: One page of change requests.
        """
        response = self._parent._request(
            "GET",
            self._path(workflow_id),
            params={"skip": skip, "limit": limit, "status": status},
        )
        return ChangeRequestList.model_validate(response.json())

    def get(self, workflow_id: UUID, change_request_id: UUID) -> ChangeRequestDetail:
        """Fetch a change request with its signals, documents, and revisions.

        Calls ``GET /api/workflows/{workflow_id}/change-requests/{change_request_id}``.

        Args:
            workflow_id (UUID): The workflow.
            change_request_id (UUID): The change request.

        Returns:
            ChangeRequestDetail: The request, its signal tally, its first page
            of documents, every revision, and the latest revision's diff.

        Raises:
            NotFoundError: If the change request does not exist.
        """
        response = self._parent._request(
            "GET", self._path(workflow_id, change_request_id)
        )
        return ChangeRequestDetail.model_validate(response.json())

    def documents(
        self,
        workflow_id: UUID,
        change_request_id: UUID,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> ChangeRequestDocumentList:
        """Page through the documents recorded on a change request.

        Calls ``GET /api/workflows/{workflow_id}/change-requests/{change_request_id}/documents``.

        Args:
            workflow_id (UUID): The workflow.
            change_request_id (UUID): The change request.
            skip (int): Documents to skip.
            limit (int): Page size (at most 200).

        Returns:
            ChangeRequestDocumentList: One page of documents, oldest first.
        """
        response = self._parent._request(
            "GET",
            f"{self._path(workflow_id, change_request_id)}/documents",
            params={"skip": skip, "limit": limit},
        )
        return ChangeRequestDocumentList.model_validate(response.json())

    def get_proposal(
        self,
        workflow_id: UUID,
        change_request_id: UUID,
        proposal_id: UUID,
    ) -> ChangeProposalResponse:
        """Fetch one proposal revision with its diff.

        Calls ``GET /api/workflows/{workflow_id}/change-requests/{change_request_id}/proposals/{proposal_id}``.

        Args:
            workflow_id (UUID): The workflow.
            change_request_id (UUID): The change request.
            proposal_id (UUID): The revision.

        Returns:
            ChangeProposalResponse: The revision.

        Raises:
            NotFoundError: If the revision does not exist.
        """
        response = self._parent._request(
            "GET",
            f"{self._path(workflow_id, change_request_id)}/proposals/{proposal_id}",
        )
        return ChangeProposalResponse.model_validate(response.json())

    def approve(
        self,
        workflow_id: UUID,
        change_request_id: UUID,
        *,
        proposal_id: UUID,
    ) -> ApproveChangeRequestResponse:
        """Approve a proposal revision, applying it to the workflow.

        Calls ``POST /api/workflows/{workflow_id}/change-requests/{change_request_id}/approve``.
        Approval needs a signed-in user: called with an API token (including a
        service account's), the server refuses. The revision must be the
        latest and ready, and the workflow must not have changed since it was
        generated. A restore point is taken before applying.

        Args:
            workflow_id (UUID): The workflow.
            change_request_id (UUID): The change request.
            proposal_id (UUID): The revision to apply.

        Returns:
            ApproveChangeRequestResponse: What was applied and the restore
            point taken first.

        Raises:
            AuthenticationError: If called with an API token.
            RagnerockError: With status 409 if the revision is stale.
        """
        response = self._parent._request(
            "POST",
            f"{self._path(workflow_id, change_request_id)}/approve",
            json_body=_body(proposal_id=proposal_id),
        )
        return ApproveChangeRequestResponse.model_validate(response.json())

    def reject(
        self,
        workflow_id: UUID,
        change_request_id: UUID,
        *,
        note: str | None = None,
    ) -> ChangeRequestResponse:
        """Close a change request without applying anything.

        Calls ``POST /api/workflows/{workflow_id}/change-requests/{change_request_id}/reject``.

        Args:
            workflow_id (UUID): The workflow.
            change_request_id (UUID): The change request.
            note (str | None): Why, for the record.

        Returns:
            ChangeRequestResponse: The closed request.
        """
        response = self._parent._request(
            "POST",
            f"{self._path(workflow_id, change_request_id)}/reject",
            json_body=_body(note=note),
        )
        return ChangeRequestResponse.model_validate(response.json())

    def backfill(
        self, workflow_id: UUID, change_request_id: UUID
    ) -> BackfillChangeRequestResponse:
        """Re-run the next batch of an approved request's documents.

        Calls ``POST /api/workflows/{workflow_id}/change-requests/{change_request_id}/backfill``.
        Each call creates a bounded number of runs; call again while
        ``remaining`` is above zero. A document is never re-run twice.

        Args:
            workflow_id (UUID): The workflow.
            change_request_id (UUID): The approved change request.

        Returns:
            BackfillChangeRequestResponse: The runs created and how many
            documents remain.
        """
        response = self._parent._request(
            "POST", f"{self._path(workflow_id, change_request_id)}/backfill"
        )
        return BackfillChangeRequestResponse.model_validate(response.json())


class _WorkflowsSection(_Section):
    """Workflow CRUD, nodes, inputs, outputs, schedules, and change requests."""

    @property
    def change_requests(self) -> _WorkflowChangeRequestsSection:
        """Endpoints for a workflow's change requests."""
        return _WorkflowChangeRequestsSection(self._parent)

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
        is_draft: bool = False,
        resources: Sequence[dict[str, Any] | BaseModel] | None = None,
        schedule: WorkflowSchedule | dict[str, Any] | None = None,
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
            is_draft (bool): Create the workflow as a draft visible only to
                its creator.
            resources (Sequence[dict[str, Any] | BaseModel] | None): The
                workflow's inputs (see :func:`tool_call_resource` and
                :func:`web_fetch_resource`). ``None`` creates a single file
                input named ``input``; ``[]`` creates a workflow with no
                inputs.
            schedule (WorkflowSchedule | dict[str, Any] | None): A recurring
                run schedule. Saving one authorizes unattended runs under your
                identity, and needs execute access on the workflow.

        Returns:
            WorkflowResponse: The newly created workflow response.
        """
        body = _body(
            project_id=project_id,
            name=name,
            description=description,
            is_active=is_active,
            auto_run_on_upload=auto_run_on_upload,
            is_draft=is_draft,
            resources=None if resources is None else list(resources),
            schedule=schedule,
        )
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
        body = _body(
            name=name,
            description=description,
            is_active=is_active,
            auto_run_on_upload=auto_run_on_upload,
        )
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

    def set_resources(
        self,
        workflow_id: UUID,
        *,
        resources: Sequence[dict[str, Any] | BaseModel],
    ) -> WorkflowResponse:
        """Replace a workflow's inputs.

        Calls ``PUT /api/workflows/{workflow_id}/resources``. The list is the
        whole desired set, matched by name: a matching name updates the input
        in place and keeps its id, a new name creates one, and an absent name
        removes it.

        Args:
            workflow_id (UUID): The workflow.
            resources (Sequence[dict[str, Any] | BaseModel]): Every input the
                workflow should have. See :func:`tool_call_resource` and
                :func:`web_fetch_resource` for inputs the platform fetches.

        Returns:
            WorkflowResponse: The workflow, with its new ``resources``.
        """
        response = self._parent._request(
            "PUT",
            f"/api/workflows/{workflow_id}/resources",
            json_body=_body(resources=list(resources)),
        )
        return WorkflowResponse.model_validate(response.json())

    def set_sinks(
        self,
        workflow_id: UUID,
        *,
        sinks: Sequence[dict[str, Any] | BaseModel],
    ) -> WorkflowResponse:
        """Replace a workflow's outputs.

        Calls ``PUT /api/workflows/{workflow_id}/sinks``. Matched by name, like
        :meth:`set_resources`. Each output names its ``parent_node_ids`` and a
        ``config`` whose ``kind`` is ``"notification"``, ``"email"``, or
        ``"artifact"``, for example::

            {
                "name": "table",
                "parent_node_ids": [str(node_id)],
                "config": {"kind": "artifact", "format": "csv"},
            }

        Args:
            workflow_id (UUID): The workflow.
            sinks (Sequence[dict[str, Any] | BaseModel]): Every output the
                workflow should have.

        Returns:
            WorkflowResponse: The workflow, with ``sinks`` and their issues.
        """
        response = self._parent._request(
            "PUT",
            f"/api/workflows/{workflow_id}/sinks",
            json_body=_body(sinks=list(sinks)),
        )
        return WorkflowResponse.model_validate(response.json())

    def set_schedule(
        self,
        workflow_id: UUID,
        schedule: WorkflowSchedule | dict[str, Any] | None = None,
        *,
        cron: str | None = None,
        timezone: str | None = None,
        enabled: bool | None = None,
        lookback: int | None = None,
    ) -> WorkflowResponse:
        """Set or replace a workflow's recurring-run schedule.

        Calls ``PUT /api/workflows/{workflow_id}/schedule``. Pass either a
        whole ``schedule`` or its fields (``cron`` and optionally the rest)
        as keywords.

        Saving a schedule authorizes the workflow to run unattended on that
        cadence — every fetched input, every agent tool, every model call —
        under your identity and the account's credits, until it is disabled,
        you lose execute access, or repeated failures pause it.

        Args:
            workflow_id (UUID): The workflow to schedule.
            schedule (WorkflowSchedule | dict[str, Any] | None): The whole
                schedule.
            cron (str | None): A five-field crontab expression.
            timezone (str | None): An IANA timezone name to interpret it in.
                Defaults to ``"UTC"``.
            enabled (bool | None): Whether the schedule fires. A disabled
                schedule is kept but does not run. Defaults to ``True``.
            lookback (int | None): Minimum width, in seconds, of the fetch
                window each run covers.

        Returns:
            WorkflowResponse: The workflow, with its schedule and runtime state.

        Raises:
            ValueError: If both or neither of ``schedule`` and ``cron`` are
                given.
            TypeError: If ``schedule`` is a string; pass it as ``cron``.
        """
        fields = (cron, timezone, enabled, lookback)
        if schedule is not None:
            if any(f is not None for f in fields):
                raise ValueError("Pass either schedule or its fields, not both")
            if isinstance(schedule, str):
                raise TypeError("Pass a crontab expression as cron=...")
            if isinstance(schedule, WorkflowSchedule):
                schedule = schedule.model_dump(mode="json")
            body = _body(**schedule)
        elif cron is None:
            raise ValueError("set_schedule requires schedule or cron")
        else:
            body = _body(
                cron=cron,
                timezone="UTC" if timezone is None else timezone,
                enabled=True if enabled is None else enabled,
                lookback=lookback,
            )
        response = self._parent._request(
            "PUT", f"/api/workflows/{workflow_id}/schedule", json_body=body
        )
        return WorkflowResponse.model_validate(response.json())

    def clear_schedule(self, workflow_id: UUID) -> WorkflowResponse:
        """Remove a workflow's schedule so it no longer runs on its own.

        Calls ``DELETE /api/workflows/{workflow_id}/schedule``. Refused while
        any input's arguments still use a ``{{ schedule.* }}`` template, which
        would have nothing to render against; remove the template first.

        Args:
            workflow_id (UUID): The workflow to unschedule.

        Returns:
            WorkflowResponse: The workflow, with no schedule.
        """
        response = self._parent._request(
            "DELETE", f"/api/workflows/{workflow_id}/schedule"
        )
        return WorkflowResponse.model_validate(response.json())

    def resume_schedule(self, workflow_id: UUID) -> WorkflowResponse:
        """Restart a schedule that paused itself after repeated failures.

        Calls ``POST /api/workflows/{workflow_id}/schedule/resume``. Nothing
        else un-pauses a schedule, so fix whatever made it fail first.
        Resuming changes nothing else about the schedule: the first run after
        a resume covers the period the pause skipped, capped like any other
        gap.

        Args:
            workflow_id (UUID): The workflow whose schedule is paused.

        Returns:
            WorkflowResponse: The workflow, with its schedule running again.
        """
        response = self._parent._request(
            "POST", f"/api/workflows/{workflow_id}/schedule/resume"
        )
        return WorkflowResponse.model_validate(response.json())

    def schedule_preview(
        self, *, cron: str, timezone: str = "UTC"
    ) -> SchedulePreviewResponse:
        """Ask what a crontab would do next, without saving it.

        Calls ``POST /api/workflows/schedule-preview``.

        Args:
            cron (str): A five-field crontab expression.
            timezone (str): An IANA timezone name to interpret it in.

        Returns:
            SchedulePreviewResponse: The next few fire times, or the reasons
            the schedule is unusable.
        """
        response = self._parent._request(
            "POST",
            "/api/workflows/schedule-preview",
            json_body=_body(cron=cron, timezone=timezone),
        )
        return SchedulePreviewResponse.model_validate(response.json())

    def run_now(
        self, workflow_id: UUID, *, capture_execution_log: bool = False
    ) -> CreateManualJobsResponse:
        """Run a workflow once, right now, with no inputs supplied.

        Calls ``POST /api/jobs/``. Every input is either fetched by its source
        or left at its default, so this is how to run a workflow whose inputs
        are all fetched (or that has none) — a scheduled one ahead of its next
        fire, or one with no schedule at all. ``{{ schedule.* }}`` templates
        render against a window ending now.

        A workflow with a supplied input that has no default cannot be run
        this way; create the run with its inputs bound instead.

        Args:
            workflow_id (UUID): The workflow to run.
            capture_execution_log (bool): Record a detailed per-node
                execution log on the job.

        Returns:
            CreateManualJobsResponse: The one job (and run) created.
        """
        body = _body(
            workflow_id=workflow_id,
            runs=[{"inputs": {}}],
            capture_execution_log=capture_execution_log,
        )
        response = self._parent._request("POST", "/api/jobs/", json_body=body)
        return CreateManualJobsResponse.model_validate(response.json())

    def test_fetch(
        self,
        workflow_id: UUID,
        *,
        source: dict[str, Any] | BaseModel,
        window_hours: int = 24,
    ) -> ResourceTestFetchResponse:
        """Try an input's fetch source once and see what it returns.

        Calls ``POST /api/workflows/{workflow_id}/resources/test-fetch``.
        Nothing is stored — no document, no version, no run — so this is how
        to check a source before saving a workflow that uses it. It is a real
        request to the source, carrying the tool's stored credentials, so it
        needs update access on the workflow and is rate-limited.

        Args:
            workflow_id (UUID): The workflow whose project owns the tool.
            source (dict[str, Any] | BaseModel): The source to try, e.g.
                ``tool_call_resource(...)["source"]``. It need not be saved on
                an input yet.
            window_hours (int): How wide a window, ending now, the
                ``{{ schedule.* }}`` templates render.

        Returns:
            ResourceTestFetchResponse: What came back, or why it did not.
        """
        response = self._parent._request(
            "POST",
            f"/api/workflows/{workflow_id}/resources/test-fetch",
            json_body=_body(source=source, window_hours=window_hours),
        )
        return ResourceTestFetchResponse.model_validate(response.json())

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
        decorators: list[dict[str, Any]] | None = None,
        position_x: int | None = None,
        position_y: int | None = None,
        position_z: int | None = None,
        in_node_ids: list[UUID] | None = None,
        out_node_ids: list[UUID] | None = None,
        include_schedule_context: bool = False,
        required_functions: list[str] | None = None,
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
            decorators (list[dict[str, Any]] | None): Ordered decorator specs
                (outermost first), each with a ``type`` of ``"JUDGE"``,
                ``"CHECK"``, ``"CRITIC"``, or ``"TOKEN_BUDGET"``.
            position_x (int | None): Canvas x position.
            position_y (int | None): Canvas y position.
            position_z (int | None): Canvas stacking order.
            in_node_ids (list[UUID] | None): Upstream nodes to wire in.
            out_node_ids (list[UUID] | None): Downstream nodes to wire out.
            include_schedule_context (bool): Add the run's schedule window to
                this node's prompt context.
            required_functions (list[str] | None): Functions the node's agent
                must call before it answers, in the order they are forced, by
                their qualified names (``"crm__get_customer"``). Each must
                belong to a tool the agent carries.

        Returns:
            WorkflowNodeResponse: The newly created node response.
        """
        body = _body(
            operator_id=operator_id,
            condition=condition,
            persist=persist,
            on_error=on_error,
            max_retries=max_retries,
            annotations_only=annotations_only,
            decorators=decorators,
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
            in_node_ids=in_node_ids or [],
            out_node_ids=out_node_ids or [],
            include_schedule_context=include_schedule_context,
            required_functions=required_functions or [],
        )
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
        *,
        operator_id: UUID | None = None,
        condition: dict[str, Any] | None = None,
        clear_condition: bool = False,
        persist: bool | None = None,
        on_error: str | None = None,
        max_retries: int | None = None,
        annotations_only: bool | None = None,
        decorators: list[dict[str, Any]] | None = None,
        position_x: int | None = None,
        position_y: int | None = None,
        position_z: int | None = None,
        in_node_ids: list[UUID] | None = None,
        out_node_ids: list[UUID] | None = None,
        target_resource_id: UUID | None = None,
        clear_target_resource: bool = False,
        context_resource_ids: list[UUID] | None = None,
        include_schedule_context: bool | None = None,
        required_functions: list[str] | None = None,
        **fields: Any,
    ) -> WorkflowNodeResponse:
        """Patch a workflow node's fields and edges.

        Calls ``PUT /api/workflows/{workflow_id}/nodes/{node_id}``. ``None``
        means "leave unchanged" for every field; list fields replace the
        stored list, so ``[]`` clears it. Additional keyword arguments are
        forwarded verbatim, for fields this method does not name.

        Args:
            workflow_id (UUID): Owning workflow.
            node_id (UUID): Node to update.
            operator_id (UUID | None): Swap the operator the node runs.
            condition (dict[str, Any] | None): New condition.
            clear_condition (bool): Remove the node's condition.
            persist (bool | None): New persist flag.
            on_error (str | None): New error-handling policy.
            max_retries (int | None): New retry count.
            annotations_only (bool | None): New annotations-only flag.
            decorators (list[dict[str, Any]] | None): Replacement decorator
                list; ``[]`` removes every decorator.
            position_x (int | None): New canvas x position.
            position_y (int | None): New canvas y position.
            position_z (int | None): New canvas stacking order.
            in_node_ids (list[UUID] | None): Replacement upstream nodes.
            out_node_ids (list[UUID] | None): Replacement downstream nodes.
            target_resource_id (UUID | None): The file input the node
                annotates. Required once a workflow has more than one.
            clear_target_resource (bool): Reset the target to the workflow's
                only file input.
            context_resource_ids (list[UUID] | None): Replacement inputs wired
                into the node's context.
            include_schedule_context (bool | None): New schedule-context flag.
            required_functions (list[str] | None): Replacement required
                functions; ``[]`` clears them.
            **fields: Other fields to patch. ``None`` values are dropped;
                ``UUID`` values (including those inside lists) are
                stringified.

        Returns:
            WorkflowNodeResponse: The updated node response.
        """
        body = _body(
            operator_id=operator_id,
            condition=condition,
            clear_condition=clear_condition or None,
            persist=persist,
            on_error=on_error,
            max_retries=max_retries,
            annotations_only=annotations_only,
            decorators=decorators,
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
            in_node_ids=in_node_ids,
            out_node_ids=out_node_ids,
            target_resource_id=target_resource_id,
            clear_target_resource=clear_target_resource or None,
            context_resource_ids=context_resource_ids,
            include_schedule_context=include_schedule_context,
            required_functions=required_functions,
            **fields,
        )
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

    def test_condition(
        self,
        workflow_id: UUID,
        node_id: UUID,
        *,
        sample_context: dict[str, Any],
    ) -> ConditionTestResponse:
        """Evaluate a node's condition against sample data.

        Calls ``POST /api/workflows/{workflow_id}/nodes/{node_id}/test-condition``.

        Args:
            workflow_id (UUID): Owning workflow.
            node_id (UUID): Node whose condition to test.
            sample_context (dict[str, Any]): The upstream results to evaluate
                the condition against.

        Returns:
            ConditionTestResponse: Whether it matched, with a trace.
        """
        response = self._parent._request(
            "POST",
            f"/api/workflows/{workflow_id}/nodes/{node_id}/test-condition",
            json_body=_body(sample_context=sample_context),
        )
        return ConditionTestResponse.model_validate(response.json())
