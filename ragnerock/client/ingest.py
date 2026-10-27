"""Ingest source endpoints (``/ingest/...``).

An ingest *config* names a source — a website, an S3 bucket, or a SQL query —
and an optional cron schedule. Each run of a config syncs the source into the
project: the *source* tracks each item it found as an *entry*, and every
change to an entry is recorded as an entry *version*.

Unlike the rest of the API, these routes live under ``/ingest/``, not
``/api/``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from ragnerock.client._base import _ApiModel, _body, _Section
from ragnerock.timestamps import UtcDatetime

SQL_PREVIEW_TIMEOUT_SECONDS = 75.0
"""Read timeout for a SQL preview.

The preview connects to the customer's database and runs the query, which
the server allows its own (shorter) deadline for; the client waits longer so a
slow but successful preview isn't reported as a timeout.
"""


# -- configs -------------------------------------------------------------------


class IngestConfigResponse(_ApiModel):
    """One ingest config.

    Attributes:
        id (UUID): The config.
        ingest_source_id (UUID | None): The source its runs sync.
        name (str | None): The config's name.
        cron (str | None): Its schedule, or ``None`` for manual runs only.
        source (dict[str, Any]): The source settings, keyed by
            ``source_type``. Secrets are never returned; flags such as
            ``credentials_configured`` (web, S3) or ``secrets`` (SQL) say
            which are stored.
        document_group_id (UUID | None): The document group the config files
            its documents in, once its first run has filed any.
    """

    id: UUID
    project_id: UUID | None = None
    ingest_source_id: UUID | None = None
    name: str | None = None
    cron: str | None = None
    source: dict[str, Any] = {}
    document_group_id: UUID | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None


class IngestConfigsPaginatedResponse(_ApiModel):
    """A page of ingest configs."""

    items: list[IngestConfigResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class IngestConfigWorkflowRef(_ApiModel):
    """A workflow ingest resource that follows an ingest config.

    Attributes:
        workflow_id (UUID): The workflow.
        resource_id (UUID): Its ingest resource bound to the config.
        process_mode (str | None): ``"CHANGES"`` (only changed entries) or
            ``"FULL"`` (every entry).
        trigger (bool | None): Whether a run of the config starts the
            workflow.
    """

    workflow_id: UUID
    workflow_name: str | None = None
    resource_id: UUID
    resource_name: str | None = None
    process_mode: str | None = None
    trigger: bool | None = None


class IngestWorkflowLinkNoticeResponse(_ApiModel):
    """A pending suggestion to bind an ingest source to a workflow."""

    id: UUID
    config_id: UUID | None = None
    config_name: str | None = None
    workflow_id: UUID | None = None
    workflow_name: str | None = None


# -- sources, entries and versions -----------------------------------------------


class IngestSourceResponse(_ApiModel):
    """One ingest source.

    Attributes:
        id (UUID): The source.
        source_type (str | None): An :class:`~ragnerock.enums.IngestSourceType`
            value.
        detail (dict[str, Any] | None): Type-specific detail, e.g. the URL,
            the bucket and prefix, or a SQL source's table document and row
            count.
        entries_count (int): Items tracked under the source.
    """

    id: UUID
    project_id: UUID | None = None
    name: str | None = None
    source_type: str | None = None
    detail: dict[str, Any] | None = None
    created_at: UtcDatetime = None
    entries_count: int = 0


class IngestSourcesPaginatedResponse(_ApiModel):
    """A page of ingest sources."""

    items: list[IngestSourceResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class IngestEntryResponse(_ApiModel):
    """One item tracked under an ingest source.

    Attributes:
        id (UUID): The entry.
        external_id (str | None): The item's id in the source, e.g. a URL or
            object key.
        removed_at (datetime | None): When the item disappeared from the
            source, if it has.
    """

    id: UUID
    source_id: UUID | None = None
    external_id: str | None = None
    name: str | None = None
    content_type: str | None = None
    versions_count: int = 0
    removed_at: UtcDatetime = None


class IngestEntriesPaginatedResponse(_ApiModel):
    """A page of ingest entries."""

    items: list[IngestEntryResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class IngestEntryVersionResponse(_ApiModel):
    """One recorded change to an ingest entry.

    Attributes:
        id (UUID): The version.
        run_id (UUID | None): The run that recorded it.
        document_id (UUID | None): The document holding this version.
        change (str | None): ``"ADDED"``, ``"MODIFIED"``, ``"UNCHANGED"`` or
            ``"REMOVED"``.
    """

    id: UUID
    entry_id: UUID | None = None
    run_id: UUID | None = None
    document_id: UUID | None = None
    parent_version_id: UUID | None = None
    change: str | None = None
    detail: dict[str, Any] | None = None
    created_at: UtcDatetime = None


class IngestEntryVersionsPaginatedResponse(_ApiModel):
    """A page of ingest entry versions."""

    items: list[IngestEntryVersionResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


# -- runs -------------------------------------------------------------------------


class IngestRunCounts(_ApiModel):
    """How many entries a run added, modified, left alone, removed, or failed on."""

    added: int = 0
    modified: int = 0
    unchanged: int = 0
    removed: int = 0
    errored: int = 0


class IngestRunError(_ApiModel):
    """Why a run failed.

    Attributes:
        reason (str | None): A machine-readable reason, e.g.
            ``"CONNECTION_FAILED"``.
        category (str | None): ``"TRANSIENT"`` or ``"PERMANENT"``.
        message (str | None): A plain-language explanation.
    """

    reason: str | None = None
    category: str | None = None
    message: str | None = None


class IngestRunResponse(_ApiModel):
    """One ingest run.

    Attributes:
        id (UUID): The run.
        status (str | None): An :class:`~ragnerock.enums.IngestRunStatus`
            value.
        trigger (str | None): An :class:`~ragnerock.enums.IngestRunTrigger`
            value.
        counts (IngestRunCounts): Per-change entry counts.
        error (IngestRunError | None): Why the run failed, if it did.
    """

    id: UUID
    source_id: UUID | None = None
    config_id: UUID | None = None
    project_id: UUID | None = None
    status: str | None = None
    trigger: str | None = None
    created_at: UtcDatetime = None
    started_at: UtcDatetime = None
    completed_at: UtcDatetime = None
    counts: IngestRunCounts = Field(default_factory=IngestRunCounts)
    error: IngestRunError | None = None


class IngestRunsPaginatedResponse(_ApiModel):
    """A page of ingest runs."""

    items: list[IngestRunResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


# -- SQL preview -------------------------------------------------------------------


class SqlResultColumn(_ApiModel):
    """One column of a SQL query's result."""

    name: str
    dtype: str | None = None


class SqlPreviewWarning(_ApiModel):
    """One problem a SQL preview found.

    Attributes:
        kind (str | None): ``"DUPLICATE_KEYS"``, ``"NULL_KEYS"``,
            ``"NO_KEY_COLUMNS"`` or ``"NO_ORDER_BY"``.
        message (str | None): A plain-language explanation.
    """

    kind: str | None = None
    message: str | None = None


class SqlPreviewResponse(_ApiModel):
    """A sample of a SQL source's query result.

    Attributes:
        dialect (str | None): The database that was queried, e.g.
            ``"postgresql"``.
        columns (list[SqlResultColumn]): The result columns and their types.
        rows (list[dict[str, Any]]): The sample rows.
        truncated (bool): Whether the query returned more rows than shown.
        suggested_key_columns (list[str]): Columns unique and non-null in the
            sample.
        warnings (list[SqlPreviewWarning]): Problems found in the sample.
        query_duration_ms (int | None): How long the query ran.
        estimated_bytes_processed (int | None): The bytes BigQuery estimated
            the query scans; ``None`` for other databases.
    """

    dialect: str | None = None
    columns: list[SqlResultColumn] = []
    rows: list[dict[str, Any]] = []
    truncated: bool = False
    suggested_key_columns: list[str] = []
    warnings: list[SqlPreviewWarning] = []
    query_duration_ms: int | None = None
    estimated_bytes_processed: int | None = None


class _IngestSourcesSection(_Section):
    """Ingest sources, their configs, runs, and entries."""

    # -- sources ----------------------------------------------------------------

    def list(
        self,
        project_id: UUID,
        *,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> IngestSourcesPaginatedResponse:
        """List a project's ingest sources, newest first.

        Calls ``GET /ingest/sources/{project_id}``.

        Args:
            project_id (UUID): The project.
            source_type (str | None): Only sources of this
                :class:`~ragnerock.enums.IngestSourceType`.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            IngestSourcesPaginatedResponse: A page of sources.
        """
        response = self._parent._request(
            "GET",
            f"/ingest/sources/{project_id}",
            params={
                "skip": skip,
                "limit": limit,
                "source_type": str(source_type) if source_type is not None else None,
            },
        )
        return IngestSourcesPaginatedResponse.model_validate(response.json())

    def get(self, project_id: UUID, source_id: UUID) -> IngestSourceResponse:
        """Fetch a single ingest source.

        Calls ``GET /ingest/sources/{project_id}/{source_id}``.

        Args:
            project_id (UUID): The project the source belongs to.
            source_id (UUID): The source.

        Returns:
            IngestSourceResponse: The source.

        Raises:
            NotFoundError: If no source has that id.
        """
        response = self._parent._request(
            "GET", f"/ingest/sources/{project_id}/{source_id}"
        )
        return IngestSourceResponse.model_validate(response.json())

    def list_runs(
        self, project_id: UUID, source_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> IngestRunsPaginatedResponse:
        """List the runs of one ingest source.

        Calls ``GET /ingest/sources/{project_id}/{source_id}/runs``.

        Args:
            project_id (UUID): The project the source belongs to.
            source_id (UUID): The source.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            IngestRunsPaginatedResponse: A page of runs.
        """
        response = self._parent._request(
            "GET",
            f"/ingest/sources/{project_id}/{source_id}/runs",
            params={"skip": skip, "limit": limit},
        )
        return IngestRunsPaginatedResponse.model_validate(response.json())

    def list_project_runs(
        self, project_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> IngestRunsPaginatedResponse:
        """List ingest runs across every source in a project.

        Calls ``GET /ingest/runs/{project_id}``.

        Args:
            project_id (UUID): The project.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            IngestRunsPaginatedResponse: A page of runs.
        """
        response = self._parent._request(
            "GET",
            f"/ingest/runs/{project_id}",
            params={"skip": skip, "limit": limit},
        )
        return IngestRunsPaginatedResponse.model_validate(response.json())

    def list_entries(
        self, project_id: UUID, source_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> IngestEntriesPaginatedResponse:
        """List the items tracked under an ingest source.

        Calls ``GET /ingest/sources/{project_id}/{source_id}/entries``.

        Args:
            project_id (UUID): The project the source belongs to.
            source_id (UUID): The source.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            IngestEntriesPaginatedResponse: A page of entries.
        """
        response = self._parent._request(
            "GET",
            f"/ingest/sources/{project_id}/{source_id}/entries",
            params={"skip": skip, "limit": limit},
        )
        return IngestEntriesPaginatedResponse.model_validate(response.json())

    def list_versions(
        self, project_id: UUID, entry_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> IngestEntryVersionsPaginatedResponse:
        """List the recorded versions of one ingest entry.

        Calls ``GET /ingest/entries/{project_id}/{entry_id}/versions``.

        Args:
            project_id (UUID): The project the entry belongs to.
            entry_id (UUID): The entry.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            IngestEntryVersionsPaginatedResponse: A page of versions.
        """
        response = self._parent._request(
            "GET",
            f"/ingest/entries/{project_id}/{entry_id}/versions",
            params={"skip": skip, "limit": limit},
        )
        return IngestEntryVersionsPaginatedResponse.model_validate(response.json())

    def get_run(self, project_id: UUID, run_id: UUID) -> IngestRunResponse:
        """Fetch a single ingest run, with its status and change counts.

        Calls ``GET /ingest/runs/{project_id}/{run_id}``.

        Args:
            project_id (UUID): The project the run belongs to.
            run_id (UUID): The run.

        Returns:
            IngestRunResponse: The run.

        Raises:
            NotFoundError: If no run has that id.
        """
        response = self._parent._request("GET", f"/ingest/runs/{project_id}/{run_id}")
        return IngestRunResponse.model_validate(response.json())

    # -- configs ----------------------------------------------------------------

    def create_config(
        self,
        project_id: UUID,
        *,
        name: str,
        source: dict[str, Any],
        cron: str | None = None,
    ) -> IngestConfigResponse:
        """Create an ingest config, and with it its source.

        Calls ``POST /ingest/configure/{project_id}``. The ``source`` dict is
        discriminated by ``source_type``. Secrets are write-only plain strings;
        responses report only whether each is stored.

        - ``"WEB_SCRAPE"``: ``url``; optional ``depth`` (1-3, default 1),
          ``limit`` (pages, default 10), ``username`` and ``password`` (sent
          together), ``reuse_window_seconds`` (default 3600) and
          ``force_refresh``.
        - ``"S3"``: ``bucket``; optional ``region``, ``prefix``, ``recursive``
          (default ``True``), ``file_patterns``, ``endpoint_url``,
          ``is_public``, ``max_objects`` (default 1000), ``max_object_bytes``
          (default 100 MiB), ``aws_access_key_id``, ``aws_secret_access_key``
          and ``aws_session_token``.
        - ``"SQL"``: ``connection_string`` (for BigQuery, the service-account
          key JSON) and ``query``; optional ``key_columns``,
          ``duplicate_key_policy`` (``"FAIL"``, ``"KEEP_FIRST"`` or
          ``"KEEP_LAST"``), ``change_detection_columns``, ``max_rows``
          (default 100,000), and TLS or key material such as ``ca_cert_pem``,
          ``client_cert_pem``, ``client_key_pem``, ``wallet_pem`` or
          ``private_key_pem``.

        Args:
            project_id (UUID): The project.
            name (str): The config's name.
            source (dict[str, Any]): The source settings (see above).
            cron (str | None): A cron schedule for automatic runs; ``None``
                runs only when triggered.

        Returns:
            IngestConfigResponse: The created config.
        """
        body = _body(name=name, cron=cron, source=source)
        response = self._parent._request(
            "POST", f"/ingest/configure/{project_id}", json_body=body
        )
        return IngestConfigResponse.model_validate(response.json())

    def get_config(self, project_id: UUID, config_id: UUID) -> IngestConfigResponse:
        """Fetch a single ingest config. Secrets are never returned.

        Calls ``GET /ingest/configure/{project_id}/{config_id}``.

        Args:
            project_id (UUID): The project the config belongs to.
            config_id (UUID): The config.

        Returns:
            IngestConfigResponse: The config.

        Raises:
            NotFoundError: If no config has that id.
        """
        response = self._parent._request(
            "GET", f"/ingest/configure/{project_id}/{config_id}"
        )
        return IngestConfigResponse.model_validate(response.json())

    def list_configs(
        self, project_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> IngestConfigsPaginatedResponse:
        """List a project's ingest configs.

        Calls ``GET /ingest/configure/{project_id}``.

        Args:
            project_id (UUID): The project.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            IngestConfigsPaginatedResponse: A page of configs.
        """
        response = self._parent._request(
            "GET",
            f"/ingest/configure/{project_id}",
            params={"skip": skip, "limit": limit},
        )
        return IngestConfigsPaginatedResponse.model_validate(response.json())

    def update_config(
        self,
        project_id: UUID,
        config_id: UUID,
        *,
        name: str,
        source: dict[str, Any],
        cron: str | None = None,
    ) -> IngestConfigResponse:
        """Replace an ingest config.

        Calls ``PUT /ingest/configure/{project_id}/{config_id}``. This is a
        full replacement: an omitted ``cron`` removes the schedule. Omitted
        secrets keep their stored values; set ``clear_credentials`` (web, S3)
        or the matching ``clear_*`` flag (SQL, e.g. ``clear_ca_cert``) in
        ``source`` to remove them; ``connection_string`` may be omitted too.
        The source type can't change.

        Args:
            project_id (UUID): The project the config belongs to.
            config_id (UUID): The config to replace.
            name (str): The config's name.
            source (dict[str, Any]): The source settings, as for
                :meth:`create_config`.
            cron (str | None): A cron schedule; ``None`` runs only when
                triggered.

        Returns:
            IngestConfigResponse: The updated config.
        """
        body = _body(name=name, cron=cron, source=source)
        response = self._parent._request(
            "PUT", f"/ingest/configure/{project_id}/{config_id}", json_body=body
        )
        return IngestConfigResponse.model_validate(response.json())

    def delete_config(self, project_id: UUID, config_id: UUID) -> None:
        """Delete an ingest config, its source and its schedule.

        Calls ``DELETE /ingest/configure/{project_id}/{config_id}``. A run
        already in progress is allowed to finish. A config that workflows are
        bound to can't be deleted until they stop using it (see
        :meth:`list_config_workflows`).

        Args:
            project_id (UUID): The project the config belongs to.
            config_id (UUID): The config to delete.

        Raises:
            RagnerockError: With status 409 if workflows are still bound to
                the config.
        """
        self._parent._request("DELETE", f"/ingest/configure/{project_id}/{config_id}")

    def trigger(self, project_id: UUID, config_id: UUID) -> IngestRunResponse:
        """Start an ingest run for a config.

        Calls ``POST /ingest/trigger/{project_id}/{config_id}``. The server
        builds everything the run needs from the saved config. A source runs
        at most once at a time.

        Args:
            project_id (UUID): The project the config belongs to.
            config_id (UUID): The config to run.

        Returns:
            IngestRunResponse: The queued run.

        Raises:
            RagnerockError: With status 409, naming the active run, if the
                source already has a run in progress.
        """
        response = self._parent._request(
            "POST", f"/ingest/trigger/{project_id}/{config_id}"
        )
        return IngestRunResponse.model_validate(response.json())

    def preview_sql(
        self,
        project_id: UUID,
        *,
        source: dict[str, Any] | None = None,
        config_id: UUID | None = None,
    ) -> SqlPreviewResponse:
        """Run a SQL source's query once and return a small sample.

        Calls ``POST /ingest/sql/preview/{project_id}``. Pass unsaved settings
        in ``source``, or a saved SQL config's ``config_id`` — optionally with
        a ``source`` overriding its query and columns, where any secret it
        omits comes from the saved config. The query runs read-only, with a
        short timeout and a small row limit, and the response suggests key
        columns and warns about duplicate or empty keys.

        Args:
            project_id (UUID): The project.
            source (dict[str, Any] | None): SQL source settings, as for
                :meth:`create_config` with ``source_type`` ``"SQL"``.
            config_id (UUID | None): A saved SQL config to preview.

        Returns:
            SqlPreviewResponse: The result columns, sample rows, suggested key
            columns and warnings.

        Raises:
            ValidationError: If the server refuses the query or settings
                (e.g. a query that writes).
            RagnerockError: If the database couldn't be reached or the query
                failed.
        """
        body = _body(source=source, config_id=config_id)
        response = self._parent._request(
            "POST",
            f"/ingest/sql/preview/{project_id}",
            json_body=body,
            timeout=SQL_PREVIEW_TIMEOUT_SECONDS,
        )
        return SqlPreviewResponse.model_validate(response.json())

    # -- workflow bindings ------------------------------------------------------

    def list_config_workflows(
        self, project_id: UUID, config_id: UUID
    ) -> list[IngestConfigWorkflowRef]:
        """List the workflows bound to an ingest config.

        Calls ``GET /ingest/workflows/{project_id}/{config_id}``. Each item is
        one workflow ingest resource that follows the config.

        Args:
            project_id (UUID): The project the config belongs to.
            config_id (UUID): The config.

        Returns:
            list[IngestConfigWorkflowRef]: The bound workflow resources.
        """
        response = self._parent._request(
            "GET", f"/ingest/workflows/{project_id}/{config_id}"
        )
        return [
            IngestConfigWorkflowRef.model_validate(item) for item in response.json()
        ]

    def list_workflow_link_notices(
        self, project_id: UUID
    ) -> list[IngestWorkflowLinkNoticeResponse]:
        """List a project's pending suggestions to bind a source to a workflow.

        Calls ``GET /ingest/workflow-link-notices/{project_id}``. Documents
        from ingest sources don't start workflows that run automatically on
        upload. Each notice names a workflow that used to run on a source's
        documents and can be linked to that source instead.

        Args:
            project_id (UUID): The project.

        Returns:
            list[IngestWorkflowLinkNoticeResponse]: The pending notices.
        """
        response = self._parent._request(
            "GET", f"/ingest/workflow-link-notices/{project_id}"
        )
        return [
            IngestWorkflowLinkNoticeResponse.model_validate(item)
            for item in response.json()
        ]

    def link_workflow_notice(self, project_id: UUID, notice_id: UUID) -> None:
        """Bind a notice's ingest source to its workflow and resolve the notice.

        Calls ``POST /ingest/workflow-link-notices/{project_id}/{notice_id}/link``.
        Adds an ingest resource for the source to the workflow.

        Args:
            project_id (UUID): The project.
            notice_id (UUID): The pending notice.

        Raises:
            NotFoundError: If the notice is unknown or already resolved.
        """
        self._parent._request(
            "POST", f"/ingest/workflow-link-notices/{project_id}/{notice_id}/link"
        )

    def dismiss_workflow_notice(self, project_id: UUID, notice_id: UUID) -> None:
        """Resolve a notice without changing its workflow.

        Calls ``POST /ingest/workflow-link-notices/{project_id}/{notice_id}/dismiss``.

        Args:
            project_id (UUID): The project.
            notice_id (UUID): The pending notice.

        Raises:
            NotFoundError: If the notice is unknown or already resolved.
        """
        self._parent._request(
            "POST", f"/ingest/workflow-link-notices/{project_id}/{notice_id}/dismiss"
        )
