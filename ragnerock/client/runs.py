"""Run endpoints (``/api/runs/...``)."""

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


class RunResponse(_ApiModel):
    """Response payload representing a single run.

    ``status`` is an integer :class:`~ragnerock.resources.run.RunStatus`
    value. Project listings add ``document_name`` and ``created_at``; fetching
    a run by id adds its stage list, subtasks, and provenance.

    Attributes:
        kind (int | None): An integer
            :class:`~ragnerock.resources.run.RunKind` value: ``1``
            (automatic) or ``2`` (manual).
        agent_ids (list[UUID]): The agents the run belongs to.
        provenance (dict[str, Any] | None): What the run pinned: its input
            versions and derived status. ``None`` for runs from before
            provenances were recorded.
    """

    id: UUID
    status: int
    document_id: UUID | None = None
    document_name: str | None = None
    status_message: str | None = None
    kind: int | None = None
    phase: str | None = None
    current_stage_name: str | None = None
    current_stage_index: int | None = None
    total_stages: int | None = None
    agent_ids: list[UUID] = []
    capture_execution_log: bool | None = None
    execution_trace: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    created_at: UtcDatetime = None
    start_time: UtcDatetime = None
    end_time: UtcDatetime = None
    archived_at: UtcDatetime = None


class RunListResponse(_ApiModel):
    """Paginated list response for runs."""

    runs: list[RunResponse]
    total: int
    skip: int
    limit: int


class RunActionResponse(_ApiModel):
    """Response payload for a run lifecycle action (cancel, retry)."""

    run_id: UUID
    status: str | None = None


class CreateManualRunsResponse(_ApiModel):
    """Response payload returned when creating one or more manual runs.

    ``run_ids`` and ``provenance_ids`` are ordered to match the request:
    ``provenance_ids[i]`` records what ``run_ids[i]`` pinned.
    """

    run_ids: list[UUID]
    provenance_ids: list[UUID] = []


class OutputDeliveryInfo(_ApiModel):
    """What one agent output delivered for one result in a run.

    ``status`` is one of ``"pending"``, ``"running"``, ``"succeeded"``,
    ``"skipped"``, ``"suppressed"``, or ``"failed"``; ``reason`` and
    ``detail`` explain any outcome other than ``"succeeded"``.
    """

    id: UUID
    output_id: UUID | None = None
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


class OutputDeliveryGroup(_ApiModel):
    """One agent output's deliveries in a run.

    ``deliveries`` holds the most recent deliveries, newest first;
    ``truncated`` says whether it stops short of all of them, and
    ``status_counts`` counts every delivery by status.
    """

    output_id: UUID
    output_name: str | None = None
    kind: str | None = None
    status_counts: dict[str, int] = {}
    notifications_sent: int = 0
    deliveries: list[OutputDeliveryInfo] = []
    truncated: bool = False


class RunOutputDeliveriesResponse(_ApiModel):
    """A run's agent outputs and what each delivered."""

    groups: list[OutputDeliveryGroup] = []


class OutputDeliveryRetryResponse(_ApiModel):
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


class _RunsSection(_Section):
    """Run creation, inspection, and lifecycle endpoints."""

    def list(
        self,
        *,
        project_id: UUID,
        status_filter: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> RunListResponse:
        """List runs in a project, optionally filtered by status.

        Calls ``GET /api/runs/``.

        Args:
            project_id (UUID): Project to list.
            status_filter (str | None): Comma-separated string of integer
                :class:`RunStatus` values, or ``None`` to list every status.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            RunListResponse: A page of runs.
        """
        response = self._parent._request(
            "GET",
            "/api/runs/",
            params={
                "project_id": str(project_id),
                "status_filter": status_filter,
                "skip": skip,
                "limit": limit,
            },
        )
        return RunListResponse.model_validate(response.json())

    def get(self, run_id: UUID) -> RunResponse:
        """Fetch a single run by id.

        Calls ``GET /api/runs/{run_id}``.

        Args:
            run_id (UUID): UUID of the run.

        Returns:
            RunResponse: The run response.

        Raises:
            NotFoundError: If no run has that id.
        """
        response = self._parent._request("GET", f"/api/runs/{run_id}")
        return RunResponse.model_validate(response.json())

    def create(
        self,
        *,
        document_ids: list[UUID] | None = None,
        agent_ids: list[UUID] | None = None,
        capture_execution_log: bool = False,
        recreate_memory_document_ids: list[UUID] | None = None,
        agent_id: UUID | None = None,
        runs: list[dict[str, Any]] | None = None,
        group_id: UUID | None = None,
        force_refresh: bool = False,
        force_refresh_node_ids: list[UUID] | None = None,
    ) -> CreateManualRunsResponse:
        """Create manual runs, each with its own provenance.

        Calls ``POST /api/runs/``. Works in one of two modes, which cannot be
        mixed:

        - **Fan-out**: ``document_ids`` + ``agent_ids`` creates one run per
          document, linked to every listed agent.
        - **Explicit**: ``agent_id`` + ``runs`` creates one run per spec.
          Each spec is ``{"inputs": {...}, "client_key": ...}``: ``inputs``
          maps each agent input name to a document id (file inputs) or an
          inline value (value inputs), and the optional ``client_key`` makes
          a retried request return the runs it already created instead of
          duplicating them (unique within ``group_id``). Inputs left out of
          ``inputs`` that allow it are run empty.

        Args:
            document_ids (list[UUID] | None): Documents to run against
                (fan-out mode).
            agent_ids (list[UUID] | None): Agents to run (fan-out mode).
            capture_execution_log (bool): If ``True``, the server records a
                per-node execution trace on each resulting run. More
                expensive; useful for debugging.
            recreate_memory_document_ids (list[UUID] | None): Documents whose
                runs also rebuild their memories, wiping the existing ones
                first (fan-out mode). ``None`` applies the server default:
                rebuild only when automatic memory is on and the document has
                none yet.
            agent_id (UUID | None): The agent to run (explicit mode).
            runs (list[dict[str, Any]] | None): One spec per run (explicit
                mode).
            group_id (UUID | None): A batch key tying several requests
                together, e.g. the chunks of one manifest; see
                :meth:`create_from_manifest`. Not a document folder.
            force_refresh (bool): Recompute every node instead of reusing
                earlier results.
            force_refresh_node_ids (list[UUID] | None): Recompute only these
                agent nodes.

        Returns:
            CreateManualRunsResponse: The created run and provenance ids,
            ordered to match the request.

        Raises:
            RagnerockError: If the server rejects the request, e.g. because
                the modes are mixed or a binding is invalid.
        """
        body = _body(
            document_ids=document_ids,
            agent_ids=agent_ids,
            agent_id=agent_id,
            runs=runs,
            group_id=group_id,
            force_refresh=force_refresh,
            force_refresh_node_ids=force_refresh_node_ids,
            capture_execution_log=capture_execution_log,
            recreate_memory_document_ids=recreate_memory_document_ids,
        )
        response = self._parent._request("POST", "/api/runs/", json_body=body)
        return CreateManualRunsResponse.model_validate(response.json())

    def run_all_ingest(
        self,
        *,
        agent_id: UUID,
        input_id: UUID,
        capture_execution_log: bool = False,
    ) -> CreateManualRunsResponse:
        """Run an agent over every current entry of its ingest source.

        Calls ``POST /api/runs/ingest-run-all``. Creates one manual run per
        live entry of the ingest source bound to ``input_id``, each pinned
        to the source's latest completed ingest run. Use it to reprocess a
        whole source on purpose, e.g. after changing a prompt; runs the source
        starts by itself only cover what changed.

        Args:
            agent_id (UUID): The agent to run.
            input_id (UUID): The agent's ingest input.
            capture_execution_log (bool): Record a per-node execution trace.

        Returns:
            CreateManualRunsResponse: The created run and provenance ids.

        Raises:
            RagnerockError: If the source has no completed run yet, or has
                more entries than one request may run.
        """
        body = _body(
            agent_id=agent_id,
            input_id=input_id,
            capture_execution_log=capture_execution_log,
        )
        response = self._parent._request(
            "POST", "/api/runs/ingest-run-all", json_body=body
        )
        return CreateManualRunsResponse.model_validate(response.json())

    def create_from_manifest(
        self,
        *,
        agent_id: UUID,
        manifest: str | Path | Iterable[dict[str, Any]],
        chunk_size: int = 200,
        capture_execution_log: bool = False,
    ) -> CreateManualRunsResponse:
        """Create many runs of one agent from a manifest.

        Calls ``POST /api/runs/`` in explicit mode once per chunk of
        ``chunk_size`` rows, after reading the agent's inputs with
        ``GET /api/agents/{agent_id}``. Every row is
        ``{"inputs": {...}}``, as in a :meth:`create` run spec. A file
        input may be bound by document id or by exact document name; names
        are resolved within the agent's project (listing its documents
        once, only if needed), and a name shared by several documents must be
        given as an id.

        All chunks share one generated ``group_id`` and each row is keyed by
        its position, so re-sending a chunk after a lost response does not
        create duplicate runs. A failed chunk raises; runs from earlier
        chunks remain.

        Args:
            agent_id (UUID): The agent every run targets.
            manifest (str | Path | Iterable[dict[str, Any]]): A path to a
                JSONL file (one row per line) or a JSON-array file, or the
                rows themselves.
            chunk_size (int): Rows per request; the server accepts at most
                500.
            capture_execution_log (bool): Record a per-node execution trace.

        Returns:
            CreateManualRunsResponse: Every created run and provenance id, in
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

        agent = self._parent.agents.get(agent_id)
        file_names = {i.name for i in agent.inputs if i.type == "file"}
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
                            self._parent, agent.project_id
                        )
                    if value not in name_to_id:
                        raise ValueError(
                            f"Manifest references unknown document {value!r}"
                        )
                    inputs[name] = name_to_id[value]
            specs.append({"inputs": inputs, "client_key": f"row-{i}"})

        group_id = uuid.uuid4()
        run_ids: list[UUID] = []
        provenance_ids: list[UUID] = []
        for start in range(0, len(specs), chunk_size):
            result = self.create(
                agent_id=agent_id,
                runs=specs[start : start + chunk_size],
                group_id=group_id,
                capture_execution_log=capture_execution_log,
            )
            run_ids.extend(result.run_ids)
            provenance_ids.extend(result.provenance_ids)
        return CreateManualRunsResponse(run_ids=run_ids, provenance_ids=provenance_ids)

    def cancel(self, run_id: UUID) -> RunActionResponse:
        """Cancel a run in progress.

        Calls ``POST /api/runs/{run_id}/cancel``. Already-terminal runs are
        a no-op server-side.

        Args:
            run_id (UUID): Run to cancel.

        Returns:
            RunActionResponse: The action response with the resulting status.
        """
        response = self._parent._request("POST", f"/api/runs/{run_id}/cancel")
        return RunActionResponse.model_validate(response.json())

    def retry(self, run_id: UUID) -> RunActionResponse:
        """Retry a failed run in place.

        Calls ``POST /api/runs/{run_id}/retry``. The server resets execution
        state and re-queues the run. To run a succeeded run again as a new
        run, use :meth:`rerun`.

        Args:
            run_id (UUID): Run to retry.

        Returns:
            RunActionResponse: The action response with the resulting status.
        """
        response = self._parent._request("POST", f"/api/runs/{run_id}/retry")
        return RunActionResponse.model_validate(response.json())

    def rerun(self, run_id: UUID) -> CreateManualRunsResponse:
        """Re-run a succeeded run as a new run.

        Calls ``POST /api/runs/{run_id}/rerun``. The new run covers the same
        document and agents (or, for an agent with explicit inputs, the same
        inputs). The original run and its results are left as they are.

        Args:
            run_id (UUID): The succeeded run to re-run.

        Returns:
            CreateManualRunsResponse: The new run's id and its provenance's.
        """
        response = self._parent._request("POST", f"/api/runs/{run_id}/rerun")
        return CreateManualRunsResponse.model_validate(response.json())

    def output_deliveries(self, run_id: UUID) -> RunOutputDeliveriesResponse:
        """List a run's agent outputs and what each delivered.

        Calls ``GET /api/runs/{run_id}/output-deliveries``.

        Args:
            run_id (UUID): The run.

        Returns:
            RunOutputDeliveriesResponse: One group per output, with counts by
            status and the most recent deliveries.
        """
        response = self._parent._request("GET", f"/api/runs/{run_id}/output-deliveries")
        return RunOutputDeliveriesResponse.model_validate(response.json())

    def retry_output_deliveries(
        self, run_id: UUID, *, output_id: UUID
    ) -> OutputDeliveryRetryResponse:
        """Retry an output's failed or held-back deliveries in a run.

        Calls ``POST /api/runs/{run_id}/output-deliveries/retry``.

        Args:
            run_id (UUID): The run.
            output_id (UUID): The agent output whose deliveries to retry.

        Returns:
            OutputDeliveryRetryResponse: How many deliveries were queued again.
        """
        response = self._parent._request(
            "POST",
            f"/api/runs/{run_id}/output-deliveries/retry",
            json_body=_body(output_id=output_id),
        )
        return OutputDeliveryRetryResponse.model_validate(response.json())
