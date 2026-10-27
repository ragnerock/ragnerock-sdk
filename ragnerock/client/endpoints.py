"""Endpoint endpoints (``/api/projects/{id}/endpoints/...`` and ``/api/endpoints/...``)."""

from __future__ import annotations

import json
from contextlib import ExitStack
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, Field

from ragnerock.client._base import UNSET, _ApiModel, _body, _patch_body, _Section
from ragnerock.enums import CompatFormat

LATEST_SNAPSHOT_TAG = "latest"
"""The snapshot reference that follows the source workflow's latest version."""

_COMPAT_PATH_SUFFIXES: dict[CompatFormat, str] = {
    CompatFormat.OPENAI: "/openai/v1",
    CompatFormat.ANTHROPIC: "/anthropic",
    CompatFormat.GEMINI: "/gemini",
}


class EndpointType(StrEnum):
    """What an endpoint exposes."""

    WORKFLOW = "WORKFLOW"
    """Submit inputs, run a snapshot of a workflow, and poll for its results."""

    MODEL_COMPAT = "MODEL_COMPAT"
    """Serve a configured model over an OpenAI, Anthropic, or Gemini wire format."""


class EndpointTaskStatus(StrEnum):
    """The status of a submitted endpoint task.

    ``accepted`` appears only in a submit response; a poll reports
    ``processing`` until the task finishes.
    """

    ACCEPTED = "accepted"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EndpointResponse(_ApiModel):
    """A deployed endpoint.

    Attributes:
        id (UUID): The endpoint's id.
        project_id (UUID | None): Owning project.
        name (str): Display name.
        description (str | None): Optional description.
        endpoint_type (str | None): An :class:`EndpointType` value.
        is_enabled (bool | None): Whether the endpoint accepts requests.
        workflow_id (UUID | None): The snapshot workflow it runs (WORKFLOW).
        source_workflow_id (UUID | None): The workflow it was deployed from.
        accepted_file_types (list[str] | None): Accepted file extensions.
        return_fields (list[dict[str, Any]] | None): Annotation fields returned.
        snapshot_tag (str | None): The snapshot it serves: ``"latest"``, a
            user tag, or ``None`` when pinned to ``active_snapshot_id``.
        active_snapshot_id (UUID | None): The snapshot currently served.
        resources (list[dict[str, Any]]): The inputs a submission supplies.
        compat_format (str | None): A :class:`~ragnerock.enums.CompatFormat`
            value (MODEL_COMPAT).
        ai_config_id (UUID | None): Bound AI provider config (MODEL_COMPAT).
        model_name (str | None): Backing model (MODEL_COMPAT).
        default_params (dict[str, Any] | None): Generation defaults
            (MODEL_COMPAT).
        ip_whitelist (list[str] | None): Allowed IP addresses / CIDRs.
        rate_limit_rpm (int | None): Requests-per-minute limit.
        api_key_prefix (str | None): The visible prefix of the endpoint's key.
        api_key_expires_at (datetime | None): When the key expires.
        mcp_tool_name (str | None): The stored MCP run-tool name.
        mcp_tool_name_effective (str | None): The run-tool name clients see.
        warnings (list[str]): Advisories from a create or redeploy.
    """

    id: UUID
    project_id: UUID | None = None
    name: str
    description: str | None = None
    endpoint_type: str | None = None
    is_enabled: bool | None = None
    workflow_id: UUID | None = None
    source_workflow_id: UUID | None = None
    accepted_file_types: list[str] | None = None
    return_fields: list[dict[str, Any]] | None = None
    include_content: bool | None = None
    ephemeral: bool | None = None
    snapshot_tag: str | None = None
    active_snapshot_id: UUID | None = None
    resources: list[dict[str, Any]] = []
    compat_format: str | None = None
    ai_config_id: UUID | None = None
    model_name: str | None = None
    default_params: dict[str, Any] | None = None
    ip_whitelist: list[str] | None = None
    rate_limit_rpm: int | None = None
    auto_archive_jobs: bool | None = None
    api_key_prefix: str | None = None
    api_key_expires_at: datetime | None = None
    mcp_tool_name: str | None = None
    mcp_tool_name_effective: str | None = None
    mcp_tool_description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    warnings: list[str] = []


class EndpointCreateResponse(EndpointResponse):
    """A newly created endpoint, with its credentials.

    The plaintext ``api_key`` and ``signing_secret`` are returned only here
    (and by a key regeneration); store them now.
    """

    api_key: str | None = None
    signing_secret: str | None = None


class EndpointListResponse(_ApiModel):
    """A page of endpoints."""

    items: list[EndpointResponse] = []
    total: int = 0


class EndpointKeyRegenerateResponse(_ApiModel):
    """A new API key and signing secret for an endpoint."""

    api_key: str
    api_key_prefix: str | None = None
    signing_secret: str | None = None
    expires_at: datetime | None = None


class EndpointMetricStats(_ApiModel):
    """Summary statistics for one execution metric."""

    count: int = 0
    mean: float | None = None
    std_dev: float | None = None
    min: float | None = None
    median: float | None = None
    p95: float | None = None
    p99: float | None = None
    max: float | None = None


class EndpointStatsResponse(_ApiModel):
    """Execution statistics for an endpoint."""

    total_executions: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    success_rate: float | None = None
    duration: EndpointMetricStats | None = None
    input_tokens: EndpointMetricStats | None = None
    output_tokens: EndpointMetricStats | None = None
    pages_processed: EndpointMetricStats | None = None
    compute_seconds: EndpointMetricStats | None = None
    percentiles_as_of: datetime | None = None


class EndpointExecutionResponse(_ApiModel):
    """One execution of an endpoint.

    Attributes:
        id (UUID): The execution's id.
        task_id (UUID | None): The task id callers poll (same as ``id``).
        request_id (UUID | None): The submission's request id.
        status (str | None): An :class:`EndpointTaskStatus` value.
        error_code (str | None): Machine-readable failure code.
        error_message (str | None): Failure description.
    """

    id: UUID
    task_id: UUID | None = None
    request_id: UUID | None = None
    status: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    compute_seconds: float | None = None
    pages_processed: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    idempotency_key: str | None = None


class EndpointExecutionListResponse(_ApiModel):
    """A page of endpoint executions."""

    items: list[EndpointExecutionResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class McpToolDescriptor(_ApiModel):
    """One MCP tool an endpoint publishes, as ``tools/list`` returns it.

    Attributes:
        name (str): The name ``tools/call`` addresses.
        title (str | None): A human-readable label.
        description (str | None): What the tool does.
        input_schema (dict[str, Any]): JSON Schema for the arguments
            (``inputSchema`` on the wire).
        output_schema (dict[str, Any] | None): JSON Schema for the structured
            result (``outputSchema`` on the wire).
        annotations (dict[str, Any] | None): Behavioural hints.
        meta (dict[str, Any] | None): Vendor extensions (``_meta`` on the wire).
    """

    name: str
    title: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("inputSchema", "input_schema"),
    )
    output_schema: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("outputSchema", "output_schema"),
    )
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = Field(
        default=None, validation_alias=AliasChoices("_meta", "meta")
    )


class McpToolsPreviewResponse(_ApiModel):
    """The MCP tool contract an endpoint publishes.

    Attributes:
        tools (list[McpToolDescriptor]): The descriptors, exactly as an MCP
            client discovers them.
        warnings (list[str]): Problems for the endpoint's owner, such as a
            resource whose name collides with a run-tool argument.
        enabled (bool): Whether this deployment serves endpoint MCP at all.
        oauth_enabled (bool): Whether callers may sign in instead of using a key.
        default_wait_seconds (int | None): The run tool's default wait.
        max_wait_seconds (int | None): The run tool's maximum wait.
    """

    tools: list[McpToolDescriptor] = []
    warnings: list[str] = []
    enabled: bool = True
    oauth_enabled: bool = False
    default_wait_seconds: int | None = None
    max_wait_seconds: int | None = None


class EndpointSubmitResponse(_ApiModel):
    """The response to an accepted submission.

    Attributes:
        task_id (UUID): The task to poll.
        request_id (UUID | None): The submission's request id.
        status (str | None): Always ``"accepted"``.
        poll_url (str | None): The path to poll, relative to the API host.
    """

    task_id: UUID
    request_id: UUID | None = None
    status: str | None = None
    poll_url: str | None = None


class EndpointTaskProgress(_ApiModel):
    """Subtask counters on a processing task. Display only; may lag the status."""

    subtasks_completed: int = 0
    subtasks_total: int = 0


class EndpointTaskError(_ApiModel):
    """Why a task failed."""

    code: str | None = None
    message: str | None = None


class EndpointTaskResult(_ApiModel):
    """The state of a submitted task, discriminated by ``status``.

    The same shape a webhook callback delivers and the endpoint's MCP tools
    return. Which fields are set depends on ``status``:

    - ``"processing"``: ``phase``, ``progress``, ``created_at``, and
      ``elapsed_seconds``, so a caller can decide for itself that a run has
      gone on too long.
    - ``"succeeded"``: ``result``, ``metadata`` (the caller's own echo
      payload), and ``ragnerock_metadata`` (metering).
    - ``"failed"``: ``error``.

    Attributes:
        task_id (UUID): The task's id.
        status (str): An :class:`EndpointTaskStatus` value.
        phase (str | None): The current phase, while processing.
        progress (EndpointTaskProgress | None): Subtask counters, while
            processing.
        created_at (datetime | None): When the task was accepted.
        elapsed_seconds (float | None): How long it has been running.
        result (dict[str, Any] | None): The assembled result, on success.
        metadata (dict[str, Any] | None): The metadata the caller submitted.
        ragnerock_metadata (dict[str, Any] | None): Execution metering, on
            success.
        truncated (bool): Whether nested result collections were dropped to fit
            a size cap.
        error (EndpointTaskError | None): The failure, on failure.
    """

    task_id: UUID
    status: str
    phase: str | None = None
    progress: EndpointTaskProgress | None = None
    created_at: datetime | None = None
    elapsed_seconds: float | None = None
    result: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    ragnerock_metadata: dict[str, Any] | None = None
    truncated: bool = False
    error: EndpointTaskError | None = None


class _EndpointsSection(_Section):
    """Deployed workflow and model-compatibility endpoints.

    Management calls authenticate as the signed-in user. :meth:`submit` and
    :meth:`poll` are the endpoint's public API and authenticate with the
    endpoint's own API key instead.
    """

    def create(
        self,
        project_id: UUID,
        *,
        name: str,
        workflow_id: UUID | None = None,
        accepted_file_types: list[str] | None = None,
        return_fields: list[dict[str, Any]] | None = None,
        description: str | None = None,
        include_content: bool = False,
        ephemeral: bool = False,
        snapshot_tag: str = LATEST_SNAPSHOT_TAG,
        endpoint_type: str = EndpointType.WORKFLOW,
        compat_format: str | None = None,
        ai_config_id: UUID | None = None,
        model_name: str | None = None,
        default_params: dict[str, Any] | None = None,
        ip_whitelist: list[str] | None = None,
        rate_limit_rpm: int = 60,
        auto_archive_jobs: bool = False,
        api_key_expires_in_days: int | None = None,
        mcp_tool_name: str | None = None,
        mcp_tool_description: str | None = None,
    ) -> EndpointCreateResponse:
        """Create an endpoint in a project.

        Calls ``POST /api/projects/{project_id}/endpoints/``. ``WORKFLOW``
        endpoints (the default) need ``workflow_id``, ``accepted_file_types``,
        and ``return_fields``. ``MODEL_COMPAT`` endpoints need
        ``compat_format`` and ``model_name`` instead, and refuse the
        workflow-only fields.

        Args:
            project_id (UUID): Project to create the endpoint in.
            name (str): Endpoint name.
            workflow_id (UUID | None): Workflow to snapshot (WORKFLOW only).
            accepted_file_types (list[str] | None): Accepted file extensions,
                e.g. ``[".pdf"]`` (WORKFLOW only).
            return_fields (list[dict[str, Any]] | None): Fields to return, each
                ``{"operator_id": ..., "field_name": ...}`` (WORKFLOW only).
            description (str | None): Optional description.
            include_content (bool): Include document content in results
                (WORKFLOW only).
            ephemeral (bool): Don't retain submitted documents (WORKFLOW only).
            snapshot_tag (str): Which snapshot to serve (WORKFLOW only):
                ``"latest"`` follows edits to the source workflow; any other
                tag is applied to the snapshot taken now.
            endpoint_type (str): An :class:`EndpointType` value.
            compat_format (str | None): A
                :class:`~ragnerock.enums.CompatFormat` value (MODEL_COMPAT only,
                required).
            ai_config_id (UUID | None): AI provider config to bind (MODEL_COMPAT
                only); omit for the Ragnerock-managed default model.
            model_name (str | None): The backing model (MODEL_COMPAT only,
                required).
            default_params (dict[str, Any] | None): Generation defaults:
                ``temperature``, ``top_p``, ``max_tokens``, ``stop``
                (MODEL_COMPAT only).
            ip_whitelist (list[str] | None): Allowed IP addresses / CIDRs.
            rate_limit_rpm (int): Requests-per-minute limit.
            auto_archive_jobs (bool): Archive jobs automatically when they finish.
            api_key_expires_in_days (int | None): Optional key lifetime.
            mcp_tool_name (str | None): The name of the MCP run tool (WORKFLOW
                only). Omit to derive one from ``name``.
            mcp_tool_description (str | None): What the run tool does (WORKFLOW
                only); falls back to ``description``.

        Returns:
            EndpointCreateResponse: The endpoint, with its plaintext API key and
            signing secret.
        """
        payload = _body(
            name=name,
            description=description,
            endpoint_type=endpoint_type,
            workflow_id=workflow_id,
            accepted_file_types=accepted_file_types,
            return_fields=return_fields,
            include_content=include_content,
            snapshot_tag=snapshot_tag,
            ephemeral=ephemeral,
            compat_format=compat_format,
            ai_config_id=ai_config_id,
            model_name=model_name,
            default_params=default_params,
            ip_whitelist=ip_whitelist,
            rate_limit_rpm=rate_limit_rpm,
            auto_archive_jobs=auto_archive_jobs,
            api_key_expires_in_days=api_key_expires_in_days,
            mcp_tool_name=mcp_tool_name,
            mcp_tool_description=mcp_tool_description,
        )
        response = self._parent._request(
            "POST", f"/api/projects/{project_id}/endpoints/", json_body=payload
        )
        return EndpointCreateResponse.model_validate(response.json())

    def list(
        self, project_id: UUID, *, skip: int = 0, limit: int = 50
    ) -> EndpointListResponse:
        """List a project's endpoints.

        Calls ``GET /api/projects/{project_id}/endpoints/``.

        Args:
            project_id (UUID): Project whose endpoints to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            EndpointListResponse: A page of endpoints plus the total count.
        """
        response = self._parent._request(
            "GET",
            f"/api/projects/{project_id}/endpoints/",
            params={"skip": skip, "limit": limit},
        )
        return EndpointListResponse.model_validate(response.json())

    def get(self, project_id: UUID, endpoint_id: UUID) -> EndpointResponse:
        """Fetch a single endpoint.

        Calls ``GET /api/projects/{project_id}/endpoints/{endpoint_id}``.

        Args:
            project_id (UUID): Owning project.
            endpoint_id (UUID): Endpoint to fetch.

        Returns:
            EndpointResponse: The endpoint.

        Raises:
            NotFoundError: If no such endpoint exists in the project.
        """
        response = self._parent._request(
            "GET", f"/api/projects/{project_id}/endpoints/{endpoint_id}"
        )
        return EndpointResponse.model_validate(response.json())

    def update(
        self,
        project_id: UUID,
        endpoint_id: UUID,
        *,
        name: str | None = None,
        description: Any = UNSET,
        accepted_file_types: list[str] | None = None,
        return_fields: list[dict[str, Any]] | None = None,
        include_content: bool | None = None,
        snapshot_tag: Any = UNSET,
        ephemeral: bool | None = None,
        ai_config_id: Any = UNSET,
        model_name: str | None = None,
        default_params: Any = UNSET,
        ip_whitelist: Any = UNSET,
        rate_limit_rpm: int | None = None,
        auto_archive_jobs: bool | None = None,
        is_enabled: bool | None = None,
        mcp_tool_name: Any = UNSET,
        mcp_tool_description: Any = UNSET,
    ) -> EndpointResponse:
        """Update an endpoint; omitted fields are left unchanged.

        Calls ``PATCH /api/projects/{project_id}/endpoints/{endpoint_id}``. For
        most fields ``None`` means "leave unchanged". The fields defaulting to
        :data:`~ragnerock.client.UNSET` (``description``, ``snapshot_tag``,
        ``ai_config_id``, ``default_params``, ``ip_whitelist``,
        ``mcp_tool_name``, ``mcp_tool_description``) can be cleared: omit them
        to leave the stored value alone, or pass ``None`` to clear it. The
        type and compat format of an endpoint can't change.

        Args:
            project_id (UUID): Owning project.
            endpoint_id (UUID): Endpoint to update.
            name (str | None): New name.
            description (str | None): New description; ``None`` clears.
            accepted_file_types (list[str] | None): New accepted file types
                (WORKFLOW only).
            return_fields (list[dict[str, Any]] | None): New return fields
                (WORKFLOW only).
            include_content (bool | None): New include-content setting
                (WORKFLOW only).
            snapshot_tag (str | None): Which snapshot to serve (WORKFLOW only):
                ``"latest"``, a user tag, or ``None`` to pin the endpoint to the
                snapshot it serves now.
            ephemeral (bool | None): New ephemeral setting (WORKFLOW only).
            ai_config_id (UUID | None): New AI config binding (MODEL_COMPAT
                only); ``None`` returns to the Ragnerock-managed default.
            model_name (str | None): New backing model (MODEL_COMPAT only).
            default_params (dict[str, Any] | None): New generation defaults
                (MODEL_COMPAT only); ``None`` clears.
            ip_whitelist (list[str] | None): New IP whitelist; ``None`` clears.
            rate_limit_rpm (int | None): New rate limit.
            auto_archive_jobs (bool | None): New auto-archive setting.
            is_enabled (bool | None): Enable or disable the endpoint.
            mcp_tool_name (str | None): New MCP run-tool name (WORKFLOW only);
                ``None`` returns to a name derived from the endpoint's name.
            mcp_tool_description (str | None): New run-tool description
                (WORKFLOW only); ``None`` clears.

        Returns:
            EndpointResponse: The updated endpoint.
        """
        payload = _body(
            name=name,
            accepted_file_types=accepted_file_types,
            return_fields=return_fields,
            include_content=include_content,
            ephemeral=ephemeral,
            model_name=model_name,
            rate_limit_rpm=rate_limit_rpm,
            auto_archive_jobs=auto_archive_jobs,
            is_enabled=is_enabled,
        )
        payload.update(
            _patch_body(
                description=description,
                snapshot_tag=snapshot_tag,
                ai_config_id=ai_config_id,
                default_params=default_params,
                ip_whitelist=ip_whitelist,
                mcp_tool_name=mcp_tool_name,
                mcp_tool_description=mcp_tool_description,
            )
        )
        response = self._parent._request(
            "PATCH",
            f"/api/projects/{project_id}/endpoints/{endpoint_id}",
            json_body=payload,
        )
        return EndpointResponse.model_validate(response.json())

    def delete(self, project_id: UUID, endpoint_id: UUID) -> None:
        """Delete an endpoint.

        Calls ``DELETE /api/projects/{project_id}/endpoints/{endpoint_id}``. The
        endpoint stops accepting requests and its key stops working.

        Args:
            project_id (UUID): Owning project.
            endpoint_id (UUID): Endpoint to delete.
        """
        self._parent._request(
            "DELETE", f"/api/projects/{project_id}/endpoints/{endpoint_id}"
        )

    def redeploy(self, project_id: UUID, endpoint_id: UUID) -> EndpointResponse:
        """Redeploy an endpoint from its source workflow.

        Calls ``POST /api/projects/{project_id}/endpoints/{endpoint_id}/redeploy``.
        A new snapshot of the source workflow is taken and served.

        Args:
            project_id (UUID): Owning project.
            endpoint_id (UUID): Endpoint to redeploy.

        Returns:
            EndpointResponse: The endpoint, serving the new snapshot.
        """
        response = self._parent._request(
            "POST", f"/api/projects/{project_id}/endpoints/{endpoint_id}/redeploy"
        )
        return EndpointResponse.model_validate(response.json())

    def regenerate_key(
        self,
        project_id: UUID,
        endpoint_id: UUID,
        *,
        expires_in_days: int | None = None,
    ) -> EndpointKeyRegenerateResponse:
        """Replace an endpoint's API key and signing secret.

        Calls ``POST /api/projects/{project_id}/endpoints/{endpoint_id}/regenerate-key``.
        The previous key stops working.

        Args:
            project_id (UUID): Owning project.
            endpoint_id (UUID): Endpoint whose key to replace.
            expires_in_days (int | None): Optional lifetime for the new key.

        Returns:
            EndpointKeyRegenerateResponse: The new plaintext key and signing
            secret, shown only once.
        """
        response = self._parent._request(
            "POST",
            f"/api/projects/{project_id}/endpoints/{endpoint_id}/regenerate-key",
            json_body=_body(expires_in_days=expires_in_days) or None,
        )
        return EndpointKeyRegenerateResponse.model_validate(response.json())

    def get_stats(self, project_id: UUID, endpoint_id: UUID) -> EndpointStatsResponse:
        """Fetch summary statistics for an endpoint's executions.

        Calls ``GET /api/projects/{project_id}/endpoints/{endpoint_id}/stats``.

        Args:
            project_id (UUID): Owning project.
            endpoint_id (UUID): Endpoint to summarize.

        Returns:
            EndpointStatsResponse: Counts, success rate, and per-metric
            statistics.
        """
        response = self._parent._request(
            "GET", f"/api/projects/{project_id}/endpoints/{endpoint_id}/stats"
        )
        return EndpointStatsResponse.model_validate(response.json())

    def list_executions(
        self,
        project_id: UUID,
        endpoint_id: UUID,
        *,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ) -> EndpointExecutionListResponse:
        """List an endpoint's executions with filtering and pagination.

        Calls ``GET /api/projects/{project_id}/endpoints/{endpoint_id}/executions``.

        Args:
            project_id (UUID): Owning project.
            endpoint_id (UUID): Endpoint whose executions to list.
            status (str | None): Only executions with this status, e.g.
                ``"succeeded"`` or ``"failed"``.
            date_from (str | None): Only executions created at or after this
                ISO 8601 time.
            date_to (str | None): Only executions created at or before this
                ISO 8601 time.
            sort_by (str): ``"created_at"``, ``"compute_seconds"``, or
                ``"input_tokens"``.
            sort_order (str): ``"asc"`` or ``"desc"``.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            EndpointExecutionListResponse: A page of executions.
        """
        response = self._parent._request(
            "GET",
            f"/api/projects/{project_id}/endpoints/{endpoint_id}/executions",
            params={
                "status": status,
                "date_from": date_from,
                "date_to": date_to,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "skip": skip,
                "limit": limit,
            },
        )
        return EndpointExecutionListResponse.model_validate(response.json())

    def mcp_url(self, endpoint_id: UUID) -> str:
        """Build the MCP server URL for a ``WORKFLOW`` endpoint.

        Makes no request. Point any MCP client at the URL with the endpoint's
        API key as a bearer token.

        Args:
            endpoint_id (UUID): The workflow endpoint's id.

        Returns:
            str: The absolute Streamable HTTP URL.
        """
        return f"{self._parent.host}/api/endpoints/{endpoint_id}/mcp"

    def mcp_tools(self, project_id: UUID, endpoint_id: UUID) -> McpToolsPreviewResponse:
        """Preview the MCP tool contract an endpoint publishes.

        Calls ``GET /api/projects/{project_id}/endpoints/{endpoint_id}/mcp/tools``.
        The descriptors are exactly what ``tools/list`` returns, plus warnings
        for the endpoint's owner.

        Args:
            project_id (UUID): Owning project.
            endpoint_id (UUID): Endpoint to preview.

        Returns:
            McpToolsPreviewResponse: The tool descriptors and warnings.
        """
        response = self._parent._request(
            "GET", f"/api/projects/{project_id}/endpoints/{endpoint_id}/mcp/tools"
        )
        return McpToolsPreviewResponse.model_validate(response.json())

    def compat_base_url(self, endpoint_id: UUID, fmt: str) -> str:
        """Build the base URL a provider SDK should be pointed at.

        Makes no request. Pass the URL as ``base_url`` to the official
        ``openai`` or ``anthropic`` client, or as ``http_options.base_url`` to
        ``google-genai``, with the endpoint's API key as the credential.

        Args:
            endpoint_id (UUID): The ``MODEL_COMPAT`` endpoint's id.
            fmt (str): The endpoint's :class:`~ragnerock.enums.CompatFormat`.

        Returns:
            str: The absolute base URL for that format.

        Raises:
            ValueError: If ``fmt`` is not a known compat format.
        """
        suffix = _COMPAT_PATH_SUFFIXES[CompatFormat(fmt)]
        return f"{self._parent.host}/api/endpoints/{endpoint_id}{suffix}"

    def submit(
        self,
        endpoint_id: UUID,
        *,
        api_key: str,
        file_path: str | Path | None = None,
        values: dict[str, str] | None = None,
        file_parts: dict[str, str | Path] | None = None,
        metadata: dict[str, Any] | None = None,
        callback_url: str | None = None,
        idempotency_key: str | None = None,
    ) -> EndpointSubmitResponse:
        """Submit work to an endpoint through its public API.

        Calls ``POST /api/endpoints/{endpoint_id}``, authenticated with the
        endpoint's API key rather than the client's token. Send only what the
        endpoint declares: an endpoint whose inputs are all fetched at run time
        (or which has none) takes no body at all; one with a single file input
        takes ``file_path``; one with several takes ``file_parts``; and value
        inputs go in ``values``.

        Args:
            endpoint_id (UUID): Endpoint to submit to.
            api_key (str): The endpoint's plaintext API key.
            file_path (str | Path | None): The file, for an endpoint with exactly
                one file input.
            values (dict[str, str] | None): Value inputs, keyed by resource name.
            file_parts (dict[str, str | Path] | None): File paths keyed by
                resource name, for an endpoint with several file inputs.
            metadata (dict[str, Any] | None): JSON metadata echoed back on the
                result (max 16 KB).
            callback_url (str | None): A webhook to receive the result.
            idempotency_key (str | None): A retry key, unique per endpoint.
                Reusing it attaches to the run already in progress instead of
                starting (and billing) another.

        Returns:
            EndpointSubmitResponse: The accepted task and where to poll it.

        Raises:
            ValueError: If both ``file_path`` and ``file_parts`` are given.
        """
        if file_path is not None and file_parts:
            raise ValueError(
                "pass file_path for an endpoint with one file input, or "
                "file_parts for one with several, not both"
            )
        data: dict[str, Any] = dict(values or {})
        if metadata is not None:
            data["metadata"] = json.dumps(metadata)
        if callback_url is not None:
            data["callback_url"] = callback_url
        if idempotency_key is not None:
            data["idempotency_key"] = idempotency_key

        with ExitStack() as stack:
            files: dict[str, Any] = {}
            if file_path is not None:
                files["data"] = stack.enter_context(Path(file_path).open("rb"))
            for part, path in (file_parts or {}).items():
                files[part] = stack.enter_context(Path(path).open("rb"))
            response = self._parent._request(
                "POST",
                f"/api/endpoints/{endpoint_id}",
                data=data or None,
                files=files or None,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        return EndpointSubmitResponse.model_validate(response.json())

    def poll(
        self, endpoint_id: UUID, task_id: UUID, *, api_key: str
    ) -> EndpointTaskResult:
        """Fetch the current state of a submitted task.

        Calls ``GET /api/endpoints/{endpoint_id}/{task_id}``, authenticated with
        the endpoint's API key rather than the client's token. Returns
        immediately; call again while ``status`` is ``"processing"``.

        Args:
            endpoint_id (UUID): Endpoint the task was submitted to.
            task_id (UUID): Task id from :meth:`submit`.
            api_key (str): The endpoint's plaintext API key.

        Returns:
            EndpointTaskResult: The processing, succeeded, or failed state.
        """
        response = self._parent._request(
            "GET",
            f"/api/endpoints/{endpoint_id}/{task_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        return EndpointTaskResult.model_validate(response.json())
