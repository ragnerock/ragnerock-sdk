"""Job endpoints (``/api/jobs/...``)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _body, _Section
from ragnerock.timestamps import UtcDatetime

if TYPE_CHECKING:
    from ragnerock.client._client import RagnerockClient


class JobResponse(_ApiModel):
    """Response payload representing a single job.

    ``status`` is an integer :class:`~ragnerock.resources.job.JobStatus`
    value. Project listings add ``document_name`` and ``created_at``; fetching
    a job by id adds its stage list, subtasks, and run details.
    """

    id: UUID
    status: int
    document_id: UUID | None = None
    document_name: str | None = None
    status_message: str | None = None
    job_type: int | None = None
    phase: str | None = None
    current_stage_name: str | None = None
    current_stage_index: int | None = None
    total_stages: int | None = None
    workflow_ids: list[UUID] = []
    capture_execution_log: bool | None = None
    execution_trace: dict[str, Any] | None = None
    run: dict[str, Any] | None = None
    created_at: UtcDatetime = None
    start_time: UtcDatetime = None
    end_time: UtcDatetime = None
    archived_at: UtcDatetime = None


class JobListResponse(_ApiModel):
    """Paginated list response for jobs."""

    jobs: list[JobResponse]
    total: int
    skip: int
    limit: int


class JobActionResponse(_ApiModel):
    """Response payload for a job lifecycle action (cancel, retry)."""

    job_id: UUID
    status: str


class CreateManualJobsResponse(_ApiModel):
    """Response payload returned when creating one or more manual jobs.

    ``job_ids`` and ``run_ids`` are ordered to match the request.
    """

    job_ids: list[UUID]
    run_ids: list[UUID] = []


class SinkDeliveryInfo(_ApiModel):
    """What one workflow output delivered for one result in a run.

    ``status`` is one of ``"pending"``, ``"running"``, ``"succeeded"``,
    ``"skipped"``, ``"suppressed"``, or ``"failed"``; ``reason`` and
    ``detail`` explain any outcome other than ``"succeeded"``.
    """

    id: UUID
    sink_id: UUID | None = None
    kind: str | None = None
    status: str | None = None
    reason: str | None = None
    detail: str | None = None
    document_id: UUID | None = None
    target_id: UUID | None = None
    iteration_index: int | None = None
    composed: dict[str, Any] | None = None
    created_at: UtcDatetime = None
    completed_at: UtcDatetime = None


class SinkDeliveryGroup(_ApiModel):
    """One workflow output's deliveries in a run.

    ``deliveries`` holds the most recent deliveries, newest first;
    ``truncated`` says whether it stops short of all of them, and
    ``status_counts`` counts every delivery by status.
    """

    sink_id: UUID
    sink_name: str | None = None
    kind: str | None = None
    status_counts: dict[str, int] = {}
    notifications_sent: int = 0
    deliveries: list[SinkDeliveryInfo] = []
    truncated: bool = False


class JobSinkDeliveriesResponse(_ApiModel):
    """A run's workflow outputs and what each delivered."""

    groups: list[SinkDeliveryGroup] = []


class SinkDeliveryRetryResponse(_ApiModel):
    """How many of an output's deliveries in a run were queued again."""

    retried: int = 0


def _is_uuid(value: str) -> bool:
    """Return whether ``value`` parses as a UUID.

    Args:
        value (str): The candidate string.

    Returns:
        bool: ``True`` if it is a UUID.
    """
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _load_manifest_rows(
    manifest: str | Path | Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Load manifest rows from a JSONL or JSON-array file, or an iterable.

    Args:
        manifest (str | Path | Iterable[dict[str, Any]]): A path to a JSONL
            file (one object per line; blank lines are skipped) or a JSON
            array file, or the rows themselves.

    Returns:
        list[dict[str, Any]]: The rows, in order.
    """
    if isinstance(manifest, (str, Path)):
        text = Path(manifest).read_text().strip()
        if text.startswith("["):
            return list(json.loads(text))
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return list(manifest)


def _document_name_index(
    client: RagnerockClient, project_id: UUID | None
) -> dict[str, UUID]:
    """Map each unambiguous document name in a project to its id.

    Names shared by more than one document are left out, so they can only be
    bound by id.

    Args:
        client (RagnerockClient): The client to list documents with.
        project_id (UUID | None): The project to index.

    Returns:
        dict[str, UUID]: Document name to id.
    """
    name_to_id: dict[str, UUID] = {}
    ambiguous: set[str] = set()
    skip = 0
    while True:
        page = client.documents.list(
            project_ids=str(project_id) if project_id is not None else None,
            skip=skip,
            limit=100,
        )
        for doc in page.documents:
            if doc.name in name_to_id:
                ambiguous.add(doc.name)
            name_to_id[doc.name] = doc.id
        skip += len(page.documents)
        if skip >= page.total or not page.documents:
            break
    for name in ambiguous:
        name_to_id.pop(name, None)
    return name_to_id


class _JobsSection(_Section):
    """Job lifecycle endpoints."""

    def list(
        self,
        *,
        project_id: UUID,
        status_filter: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> JobListResponse:
        """List jobs in a project, optionally filtered by status.

        Calls ``GET /api/jobs/``.

        Args:
            project_id (UUID): Project to list.
            status_filter (str | None): Comma-separated string of integer
                :class:`JobStatus` values, or ``None`` to list every status.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            JobListResponse: A page of jobs.
        """
        response = self._parent._request(
            "GET",
            "/api/jobs/",
            params={
                "project_id": str(project_id),
                "status_filter": status_filter,
                "skip": skip,
                "limit": limit,
            },
        )
        return JobListResponse.model_validate(response.json())

    def get(self, job_id: UUID) -> JobResponse:
        """Fetch a single job by id.

        Calls ``GET /api/jobs/{job_id}``.

        Args:
            job_id (UUID): UUID of the job.

        Returns:
            JobResponse: The job response.

        Raises:
            NotFoundError: If no job has that id.
        """
        response = self._parent._request("GET", f"/api/jobs/{job_id}")
        return JobResponse.model_validate(response.json())

    def create_manual(
        self,
        *,
        document_ids: list[UUID] | None = None,
        workflow_ids: list[UUID] | None = None,
        capture_execution_log: bool = False,
        recreate_memory_document_ids: list[UUID] | None = None,
        workflow_id: UUID | None = None,
        runs: list[dict[str, Any]] | None = None,
        group_id: UUID | None = None,
        force_refresh: bool = False,
        force_refresh_node_ids: list[UUID] | None = None,
    ) -> CreateManualJobsResponse:
        """Create manual runs, each with its own job.

        Calls ``POST /api/jobs/``. Works in one of two modes, which cannot be
        mixed:

        - **Fan-out**: ``document_ids`` + ``workflow_ids`` creates one job per
          document, linked to every listed workflow.
        - **Explicit**: ``workflow_id`` + ``runs`` creates one run per spec.
          Each spec is ``{"inputs": {...}, "client_key": ...}``: ``inputs``
          maps each workflow resource name to a document id (file resources)
          or an inline value (value resources), and the optional
          ``client_key`` makes a retried request return the runs it already
          created instead of duplicating them (unique within ``group_id``).
          Resources left out of ``inputs`` that allow it are run empty.

        Args:
            document_ids (list[UUID] | None): Documents to run against
                (fan-out mode).
            workflow_ids (list[UUID] | None): Workflows to run (fan-out mode).
            capture_execution_log (bool): If ``True``, the server records a
                per-node execution trace on each resulting job. More
                expensive; useful for debugging.
            recreate_memory_document_ids (list[UUID] | None): Documents whose
                jobs also rebuild their memories, wiping the existing ones
                first (fan-out mode). ``None`` applies the server default:
                rebuild only when automatic memory is on and the document has
                none yet.
            workflow_id (UUID | None): The workflow to run (explicit mode).
            runs (list[dict[str, Any]] | None): One spec per run (explicit
                mode).
            group_id (UUID | None): Ties several requests together, e.g. the
                chunks of one manifest; see :meth:`create_runs_from_manifest`.
            force_refresh (bool): Recompute every node instead of reusing
                earlier results.
            force_refresh_node_ids (list[UUID] | None): Recompute only these
                workflow nodes.

        Returns:
            CreateManualJobsResponse: The created job and run ids, ordered to
            match the request.

        Raises:
            RagnerockError: If the server rejects the request, e.g. because
                the modes are mixed or a binding is invalid.
        """
        body = _body(
            document_ids=document_ids,
            workflow_ids=workflow_ids,
            workflow_id=workflow_id,
            runs=runs,
            group_id=group_id,
            force_refresh=force_refresh,
            force_refresh_node_ids=force_refresh_node_ids,
            capture_execution_log=capture_execution_log,
            recreate_memory_document_ids=recreate_memory_document_ids,
        )
        response = self._parent._request("POST", "/api/jobs/", json_body=body)
        return CreateManualJobsResponse.model_validate(response.json())

    def run_all_ingest(
        self,
        *,
        workflow_id: UUID,
        resource_id: UUID,
        capture_execution_log: bool = False,
    ) -> CreateManualJobsResponse:
        """Run a workflow over every current entry of its ingest source.

        Calls ``POST /api/jobs/ingest-run-all``. Creates one manual run per
        live entry of the ingest source bound to ``resource_id``, each pinned
        to the source's latest completed ingest run. Use it to reprocess a
        whole source on purpose, e.g. after changing a prompt; runs the source
        starts by itself only cover what changed.

        Args:
            workflow_id (UUID): The workflow to run.
            resource_id (UUID): The workflow's ingest resource.
            capture_execution_log (bool): Record a per-node execution trace.

        Returns:
            CreateManualJobsResponse: The created job and run ids.

        Raises:
            RagnerockError: If the source has no completed run yet, or has
                more entries than one request may run.
        """
        body = _body(
            workflow_id=workflow_id,
            resource_id=resource_id,
            capture_execution_log=capture_execution_log,
        )
        response = self._parent._request(
            "POST", "/api/jobs/ingest-run-all", json_body=body
        )
        return CreateManualJobsResponse.model_validate(response.json())

    def create_runs_from_manifest(
        self,
        *,
        workflow_id: UUID,
        manifest: str | Path | Iterable[dict[str, Any]],
        chunk_size: int = 200,
        capture_execution_log: bool = False,
    ) -> CreateManualJobsResponse:
        """Create many runs of one workflow from a manifest.

        Calls ``POST /api/jobs/`` in explicit mode once per chunk of
        ``chunk_size`` rows, after reading the workflow's resources with
        ``GET /api/workflows/{workflow_id}``. Every row is
        ``{"inputs": {...}}``, as in a :meth:`create_manual` run spec. A file
        resource may be bound by document id or by exact document name; names
        are resolved within the workflow's project (listing its documents
        once, only if needed), and a name shared by several documents must be
        given as an id.

        All chunks share one generated ``group_id`` and each row is keyed by
        its position, so re-sending a chunk after a lost response does not
        create duplicate runs. A failed chunk raises; runs from earlier
        chunks remain.

        Args:
            workflow_id (UUID): The workflow every run targets.
            manifest (str | Path | Iterable[dict[str, Any]]): A path to a
                JSONL file (one row per line) or a JSON-array file, or the
                rows themselves.
            chunk_size (int): Rows per request; the server accepts at most
                500.
            capture_execution_log (bool): Record a per-node execution trace.

        Returns:
            CreateManualJobsResponse: Every created job and run id, in
            manifest order.

        Raises:
            ValueError: If ``chunk_size`` is not positive, or a row names a
                document that does not exist or is ambiguous. Nothing is
                submitted in that case.
            RagnerockError: If the server rejects a chunk.
        """
        if chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")
        rows = _load_manifest_rows(manifest)

        workflow = self._parent.workflows.get(workflow_id)
        resources = workflow.model_dump(mode="json").get("resources") or []
        file_names = {
            r.get("name")
            for r in resources
            if isinstance(r, dict) and r.get("type") == "file"
        }
        name_to_id: dict[str, UUID] | None = None

        specs: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            inputs = dict(row.get("inputs", {}))
            for name, value in list(inputs.items()):
                if (
                    name in file_names
                    and isinstance(value, str)
                    and not _is_uuid(value)
                ):
                    if name_to_id is None:
                        name_to_id = _document_name_index(
                            self._parent, workflow.project_id
                        )
                    if value not in name_to_id:
                        raise ValueError(
                            f"Manifest references unknown document {value!r}"
                        )
                    inputs[name] = name_to_id[value]
            specs.append({"inputs": inputs, "client_key": f"row-{i}"})

        group_id = uuid.uuid4()
        job_ids: list[UUID] = []
        run_ids: list[UUID] = []
        for start in range(0, len(specs), chunk_size):
            result = self.create_manual(
                workflow_id=workflow_id,
                runs=specs[start : start + chunk_size],
                group_id=group_id,
                capture_execution_log=capture_execution_log,
            )
            job_ids.extend(result.job_ids)
            run_ids.extend(result.run_ids)
        return CreateManualJobsResponse(job_ids=job_ids, run_ids=run_ids)

    def cancel(self, job_id: UUID) -> JobActionResponse:
        """Cancel a running job.

        Calls ``POST /api/jobs/{job_id}/cancel``. Already-terminal jobs are
        a no-op server-side.

        Args:
            job_id (UUID): Job to cancel.

        Returns:
            JobActionResponse: The action response with the resulting status.
        """
        response = self._parent._request("POST", f"/api/jobs/{job_id}/cancel")
        return JobActionResponse.model_validate(response.json())

    def retry(self, job_id: UUID) -> JobActionResponse:
        """Retry a failed job.

        Calls ``POST /api/jobs/{job_id}/retry``. The server resets execution
        state and re-queues the job.

        Args:
            job_id (UUID): Job to retry.

        Returns:
            JobActionResponse: The action response with the resulting status.
        """
        response = self._parent._request("POST", f"/api/jobs/{job_id}/retry")
        return JobActionResponse.model_validate(response.json())

    def sink_deliveries(self, job_id: UUID) -> JobSinkDeliveriesResponse:
        """List a run's workflow outputs and what each delivered.

        Calls ``GET /api/jobs/{job_id}/sink-deliveries``.

        Args:
            job_id (UUID): The job.

        Returns:
            JobSinkDeliveriesResponse: One group per output, with counts by
            status and the most recent deliveries.
        """
        response = self._parent._request("GET", f"/api/jobs/{job_id}/sink-deliveries")
        return JobSinkDeliveriesResponse.model_validate(response.json())

    def retry_sink_deliveries(
        self, job_id: UUID, *, sink_id: UUID
    ) -> SinkDeliveryRetryResponse:
        """Retry an output's failed or held-back deliveries in a run.

        Calls ``POST /api/jobs/{job_id}/sink-deliveries/retry``.

        Args:
            job_id (UUID): The job.
            sink_id (UUID): The workflow output whose deliveries to retry.

        Returns:
            SinkDeliveryRetryResponse: How many deliveries were queued again.
        """
        response = self._parent._request(
            "POST",
            f"/api/jobs/{job_id}/sink-deliveries/retry",
            json_body=_body(sink_id=sink_id),
        )
        return SinkDeliveryRetryResponse.model_validate(response.json())
