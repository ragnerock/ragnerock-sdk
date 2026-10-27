"""Notebook, cell, and artifact endpoints (``/api/notebooks/...``, ``/api/artifacts/...``)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ragnerock.client._base import (
    UNSET,
    _ApiModel,
    _body,
    _jsonable,
    _patch_body,
    _Section,
)
from ragnerock.timestamps import UtcDatetime

if TYPE_CHECKING:
    import httpx


class CellType(StrEnum):
    """Kinds of notebook cell."""

    MESSAGE = "message"
    """A chat message; its ``role`` says who wrote it."""

    CODE = "code"
    """Python source run in the notebook's code session."""

    MARKDOWN = "markdown"
    """Rendered notes."""

    QUERY = "query"
    """An annotation SQL query."""

    COMPACTION = "compaction"
    """A summary that replaces every cell above it in the agent's history."""


class CellRole(StrEnum):
    """Who wrote a ``message`` cell."""

    SYSTEM = "system"
    TOOL = "tool"
    USER = "user"
    MODEL = "model"
    TOOL_CALL = "tool_call"


class ReasoningEffort(StrEnum):
    """How hard the model reasons on a notebook's agent turns."""

    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ArtifactType(StrEnum):
    """Kinds of artifact an agent turn can produce."""

    SEARCH_RESULTS = "search_results"
    DATAFRAME = "dataframe"
    DOCUMENTS = "documents"
    OPERATORS = "operators"
    PLOT = "plot"
    ANALYSIS_REPORT = "analysis_report"
    CITATION = "citation"
    CODE = "code"
    WORKFLOW_PROPOSAL = "workflow_proposal"
    MEMORY = "memory"
    TODO_LIST = "todo_list"
    WORKFLOW = "workflow"


class NotebookResponse(_ApiModel):
    """A notebook, or a conversation with an agent.

    Attributes:
        id (UUID): The notebook.
        project_id (UUID | None): Its project.
        title (str | None): Its title.
        agent_id (UUID | None): The agent the notebook is a conversation
            with; ``None`` for the research agent.
        agent_name (str | None): That agent's display name.
        assignment_id (UUID | None): The assignment, when the notebook is an
            assignment's transcript.
        visibility (str | None): ``"user"`` for a notebook a person works in,
            ``"agent_transcript"`` for an assignment's record.
        ai_config_id (UUID | None): The notebook's own AI config binding;
            ``None`` uses the agent's or the account default.
        reasoning_effort (str | None): A :class:`ReasoningEffort` value, or
            ``None`` for no reasoning.
        model_source (str | None): Whose setting decides the model:
            ``"notebook"``, ``"agent"`` or ``"account"``.
    """

    id: UUID
    project_id: UUID | None = None
    title: str | None = None
    folder_id: UUID | None = None
    created_by: UUID | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None
    agent_id: UUID | None = None
    agent_name: str | None = None
    assignment_id: UUID | None = None
    visibility: str | None = None
    ai_config_id: UUID | None = None
    reasoning_effort: str | None = None
    model_source: str | None = None


class NotebookListItem(_ApiModel):
    """The compact notebook shape list responses carry."""

    id: UUID
    title: str | None = None
    folder_id: UUID | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None


class NotebookListResponse(_ApiModel):
    """Paginated list response for notebooks."""

    notebooks: list[NotebookListItem] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class ArtifactPreview(_ApiModel):
    """Display metadata for an artifact, readable without its data."""

    title: str | None = None
    description: str | None = None
    size_bytes: int | None = None
    preview_data: dict[str, Any] | None = None
    thumbnail_url: str | None = None


class ArtifactReference(_ApiModel):
    """A cell's pointer to an artifact it produced."""

    artifact_id: UUID
    artifact_type: str | None = None
    preview: ArtifactPreview | None = None


class CellResponse(_ApiModel):
    """A notebook cell.

    Attributes:
        id (UUID): The cell.
        notebook_id (UUID | None): Its notebook.
        content (str | None): The message text, source code, or summary.
        cell_type (str | None): A :class:`CellType` value.
        role (str | None): A :class:`CellRole` value, for ``message`` cells.
        output (dict[str, Any] | None): The cell's output, e.g. a code run's
            results.
        position (int | None): Its place in the notebook; order cells by it.
        tool_name (str | None): The tool, when the cell is half of a tool
            exchange.
        artifact_references (list[ArtifactReference]): Artifacts the cell
            produced.
    """

    id: UUID
    notebook_id: UUID | None = None
    content: str | None = None
    cell_type: str | None = None
    role: str | None = None
    output: dict[str, Any] | None = None
    position: int | None = None
    tool_name: str | None = None
    turn_id: UUID | None = None
    assignment_id: UUID | None = None
    created_at: UtcDatetime = None
    artifact_references: list[ArtifactReference] = []


class CellListResponse(_ApiModel):
    """Paginated list response for cells."""

    cells: list[CellResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class ArtifactResponse(_ApiModel):
    """An artifact.

    Attributes:
        id (UUID): The artifact.
        project_id (UUID | None): Its project.
        artifact_type (str | None): An :class:`ArtifactType` value.
        preview (ArtifactPreview | None): Its display metadata.
        data (Any): Its payload, whose shape depends on ``artifact_type``.
            List responses omit it.
        storage_path (str | None): Where a large artifact's data is stored.
    """

    id: UUID
    project_id: UUID | None = None
    created_by_id: UUID | None = None
    artifact_type: str | None = None
    preview: ArtifactPreview | None = None
    data: Any = None
    storage_path: str | None = None
    created_at: UtcDatetime = None


class ArtifactListResponse(_ApiModel):
    """Paginated list response for artifacts."""

    artifacts: list[ArtifactResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class ArtifactCreateResponse(_ApiModel):
    """Acknowledgement returned when an artifact is created."""

    artifact_id: UUID


def _iter_ndjson_or_text(response: httpx.Response) -> Iterator[dict[str, Any]]:
    """Yield one decoded event per non-empty line of an NDJSON stream.

    A line that isn't valid JSON is yielded as ``{"type": "text", "content":
    line}`` rather than ending the stream.

    Args:
        response (httpx.Response): A streaming response.

    Yields:
        dict[str, Any]: One decoded line.
    """
    for line in response.iter_lines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            yield {"type": "text", "content": line}


class _NotebooksSection(_Section):
    """Notebooks and agent conversations."""

    def create(
        self,
        *,
        project_id: UUID,
        title: str,
        agent_id: UUID | None = None,
    ) -> NotebookResponse:
        """Create a notebook, optionally bound to an agent.

        Calls ``POST /api/notebooks/``. A notebook bound to an agent is a
        conversation with it: its turns run with the agent's prompt, skills,
        memory and model binding. To reach *the* conversation between you and
        an agent, use :meth:`open_conversation` — creating repeatedly leaves
        several transcripts with the same agent.

        Args:
            project_id (UUID): Project to create the notebook in.
            title (str): Notebook title.
            agent_id (UUID | None): The agent to bind, a live LLM agent in this
                project. ``None`` is the research agent.

        Returns:
            NotebookResponse: The created notebook.
        """
        body = _body(project_id=project_id, title=title, agent_id=agent_id)
        response = self._parent._request("POST", "/api/notebooks/", json_body=body)
        return NotebookResponse.model_validate(response.json())

    def open_conversation(
        self, *, project_id: UUID, agent_id: UUID
    ) -> NotebookResponse:
        """Resolve your conversation with one agent, creating it the first time.

        Calls ``POST /api/notebooks/conversations``. There is one conversation
        per agent and user, so calling this twice returns the same notebook.

        Args:
            project_id (UUID): The project the conversation lives in.
            agent_id (UUID): The agent to talk to.

        Returns:
            NotebookResponse: The existing or newly created conversation.
        """
        body = _body(project_id=project_id, agent_id=agent_id)
        response = self._parent._request(
            "POST", "/api/notebooks/conversations", json_body=body
        )
        return NotebookResponse.model_validate(response.json())

    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
        agent_id: UUID | None = None,
        mine: bool = False,
    ) -> NotebookListResponse:
        """List notebooks across the projects you can read.

        Calls ``GET /api/notebooks/``.

        Args:
            project_ids (str | None): Comma-separated project UUIDs. Omitted,
                lists your own notebooks across every project you belong to.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.
            agent_id (UUID | None): Only conversations bound to this agent.
            mine (bool): Only notebooks you created. Implied when
                ``project_ids`` is omitted.

        Returns:
            NotebookListResponse: A page of notebooks, most recently created
            first.
        """
        response = self._parent._request(
            "GET",
            "/api/notebooks/",
            params={
                "skip": skip,
                "limit": limit,
                "project_ids": project_ids,
                "agent_id": str(agent_id) if agent_id is not None else None,
                "mine": "true" if mine else None,
            },
        )
        return NotebookListResponse.model_validate(response.json())

    def get(self, notebook_id: UUID) -> NotebookResponse:
        """Fetch a single notebook by id.

        Calls ``GET /api/notebooks/{notebook_id}``.

        Args:
            notebook_id (UUID): The notebook.

        Returns:
            NotebookResponse: The notebook.

        Raises:
            NotFoundError: If no notebook has that id.
        """
        response = self._parent._request("GET", f"/api/notebooks/{notebook_id}")
        return NotebookResponse.model_validate(response.json())

    def update(
        self,
        notebook_id: UUID,
        *,
        title: str | None = None,
        ai_config_id: Any = UNSET,
        reasoning_effort: Any = UNSET,
    ) -> NotebookResponse:
        """Update a notebook; omitted fields are left unchanged.

        Calls ``PUT /api/notebooks/{notebook_id}``. The model-binding fields
        default to :data:`~ragnerock.client.UNSET`: omit them to leave the
        binding alone, or pass ``None`` to clear it back to the account
        default (``ai_config_id``) or no reasoning (``reasoning_effort``).

        Args:
            notebook_id (UUID): The notebook to update.
            title (str | None): New title; ``None`` leaves it unchanged.
            ai_config_id (UUID | None): AI config to bind; ``None`` clears.
            reasoning_effort (str | None): A :class:`ReasoningEffort` value;
                ``None`` clears.

        Returns:
            NotebookResponse: The updated notebook.
        """
        body = _body(title=title)
        body.update(
            _patch_body(ai_config_id=ai_config_id, reasoning_effort=reasoning_effort)
        )
        response = self._parent._request(
            "PUT", f"/api/notebooks/{notebook_id}", json_body=body
        )
        return NotebookResponse.model_validate(response.json())

    def delete(self, notebook_id: UUID, *, end_assignment: bool = False) -> None:
        """Delete a notebook.

        Calls ``DELETE /api/notebooks/{notebook_id}``. An assignment's
        transcript is its record, so deleting one requires
        ``end_assignment=True``: that ends the assignment if it is still in
        progress and removes the record of its work. Without it, deleting a
        transcript is refused.

        Args:
            notebook_id (UUID): The notebook.
            end_assignment (bool): Confirms deleting an assignment transcript;
                ignored for any other notebook.
        """
        self._parent._request(
            "DELETE",
            f"/api/notebooks/{notebook_id}",
            params={"end_assignment": "true"} if end_assignment else None,
        )

    def compact(self, notebook_id: UUID) -> CellResponse:
        """Summarize the notebook so far and append a compaction cell.

        Calls ``POST /api/notebooks/{notebook_id}/compaction``. From the next
        turn on, the new cell's summary replaces everything above it in the
        history the agent sees. The cells themselves stay in the notebook, and
        deleting the compaction cell restores the full history. Runs one model
        call on the notebook's model binding.

        Args:
            notebook_id (UUID): The notebook to compact.

        Returns:
            CellResponse: The created ``compaction`` cell.
        """
        response = self._parent._request(
            "POST", f"/api/notebooks/{notebook_id}/compaction"
        )
        return CellResponse.model_validate(response.json())

    def regenerate_compaction(self, notebook_id: UUID, cell_id: UUID) -> CellResponse:
        """Rebuild an existing compaction cell's summary.

        Calls ``POST /api/notebooks/{notebook_id}/compaction/{cell_id}/regenerate``.
        The summary is rebuilt from the cells above it and the cell is updated
        in place, replacing any edits made to the summary.

        Args:
            notebook_id (UUID): The notebook owning the cell.
            cell_id (UUID): The ``compaction`` cell to regenerate.

        Returns:
            CellResponse: The updated ``compaction`` cell.
        """
        response = self._parent._request(
            "POST", f"/api/notebooks/{notebook_id}/compaction/{cell_id}/regenerate"
        )
        return CellResponse.model_validate(response.json())

    def stream_input(
        self,
        notebook_id: UUID,
        *,
        content: str,
        cell_type: str,
        role: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Add input to a notebook and stream the response.

        Calls ``POST /api/notebooks/{notebook_id}/input`` and reads the
        newline-delimited JSON reply. For a ``message`` cell the agent's turn
        is streamed as it runs. The request has no timeout, since a turn can
        take a while.

        Args:
            notebook_id (UUID): The notebook to add input to.
            content (str): The cell's content.
            cell_type (str): A :class:`CellType` value, e.g. ``"message"``.
            role (str | None): A :class:`CellRole` value for ``message``
                cells, e.g. ``"user"``.

        Yields:
            dict[str, Any]: Each event as decoded JSON: the cells the turn
            creates, the agent's output, and artifact references. A line that
            isn't JSON arrives as ``{"type": "text", "content": line}``.

        Raises:
            RagnerockError: Or a subclass, when the server refuses the input.
                Raised on the first iteration.
        """
        body = _body(content=content, cell_type=cell_type, role=role)
        with self._parent._stream(
            "POST",
            f"/api/notebooks/{notebook_id}/input",
            json_body=body,
            headers={"accept": "application/x-ndjson"},
            timeout=None,
        ) as response:
            yield from _iter_ndjson_or_text(response)


class _CellsSection(_Section):
    """Cells within a notebook."""

    def create(
        self,
        notebook_id: UUID,
        *,
        content: str,
        cell_type: str,
        role: str | None = None,
        output: dict[str, Any] | None = None,
    ) -> CellResponse:
        """Append a cell to a notebook without running an agent turn.

        Calls ``POST /api/notebooks/{notebook_id}/cells/``. Use
        ``client.notebooks.stream_input`` to add a message and have the agent
        answer it.

        Args:
            notebook_id (UUID): The notebook.
            content (str): The cell's content.
            cell_type (str): A :class:`CellType` value.
            role (str | None): A :class:`CellRole` value, for ``message`` cells.
            output (dict[str, Any] | None): Output to store on the cell.

        Returns:
            CellResponse: The created cell.
        """
        body = _body(content=content, cell_type=cell_type, role=role, output=output)
        response = self._parent._request(
            "POST", f"/api/notebooks/{notebook_id}/cells/", json_body=body
        )
        return CellResponse.model_validate(response.json())

    def list(
        self, notebook_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> CellListResponse:
        """List a notebook's visible cells, in order.

        Calls ``GET /api/notebooks/{notebook_id}/cells/``. Hidden tool cells
        are left out, and ``total`` counts visible cells only.

        Args:
            notebook_id (UUID): The notebook.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            CellListResponse: A page of cells.
        """
        response = self._parent._request(
            "GET",
            f"/api/notebooks/{notebook_id}/cells/",
            params={"notebook_id": str(notebook_id), "skip": skip, "limit": limit},
        )
        return CellListResponse.model_validate(response.json())

    def get(self, notebook_id: UUID, cell_id: UUID) -> CellResponse:
        """Fetch a single cell.

        Calls ``GET /api/notebooks/{notebook_id}/cells/{cell_id}``.

        Args:
            notebook_id (UUID): The cell's notebook.
            cell_id (UUID): The cell.

        Returns:
            CellResponse: The cell.

        Raises:
            NotFoundError: If no visible cell has that id.
        """
        response = self._parent._request(
            "GET", f"/api/notebooks/{notebook_id}/cells/{cell_id}"
        )
        return CellResponse.model_validate(response.json())

    def update(
        self,
        notebook_id: UUID,
        cell_id: UUID,
        *,
        content: str | None = None,
        cell_type: str | None = None,
        role: str | None = None,
        output: dict[str, Any] | None = None,
    ) -> CellResponse:
        """Update a cell; omitted fields are left unchanged.

        Calls ``PUT /api/notebooks/{notebook_id}/cells/{cell_id}``. Editing an
        agent-written code cell's source or type makes it yours.

        Args:
            notebook_id (UUID): The cell's notebook.
            cell_id (UUID): The cell to update.
            content (str | None): New content.
            cell_type (str | None): New :class:`CellType` value.
            role (str | None): New :class:`CellRole` value.
            output (dict[str, Any] | None): New output.

        Returns:
            CellResponse: The updated cell.
        """
        body = _body(content=content, cell_type=cell_type, role=role, output=output)
        response = self._parent._request(
            "PUT", f"/api/notebooks/{notebook_id}/cells/{cell_id}", json_body=body
        )
        return CellResponse.model_validate(response.json())

    def delete(self, notebook_id: UUID, cell_id: UUID) -> None:
        """Delete a cell.

        Calls ``DELETE /api/notebooks/{notebook_id}/cells/{cell_id}``.

        Args:
            notebook_id (UUID): The cell's notebook.
            cell_id (UUID): The cell to delete.
        """
        self._parent._request("DELETE", f"/api/notebooks/{notebook_id}/cells/{cell_id}")


class _ArtifactsSection(_Section):
    """Artifacts produced in notebooks and conversations."""

    def create(
        self,
        *,
        project_id: UUID,
        artifact_type: str,
        preview: dict[str, Any],
        data: Any = None,
    ) -> ArtifactCreateResponse:
        """Create an artifact.

        Calls ``POST /api/artifacts/``.

        Args:
            project_id (UUID): The project the artifact belongs to.
            artifact_type (str): An :class:`ArtifactType` value.
            preview (dict[str, Any]): Display metadata: ``title`` and
                ``size_bytes`` are required; ``description``,
                ``preview_data`` and ``thumbnail_url`` are optional.
            data (Any): The artifact's payload, shaped for its type. Sent as
                ``null`` when ``None``.

        Returns:
            ArtifactCreateResponse: The new artifact's id.
        """
        body = _body(
            project_id=project_id, artifact_type=artifact_type, preview=preview
        )
        # ``data`` is a required (nullable) field, so it is always sent.
        body["data"] = _jsonable(data)
        response = self._parent._request("POST", "/api/artifacts/", json_body=body)
        return ArtifactCreateResponse.model_validate(response.json())

    def get(self, artifact_id: UUID) -> ArtifactResponse:
        """Fetch a single artifact, with its data.

        Calls ``GET /api/artifacts/{artifact_id}``.

        Args:
            artifact_id (UUID): The artifact.

        Returns:
            ArtifactResponse: The artifact.

        Raises:
            NotFoundError: If no artifact has that id.
        """
        response = self._parent._request("GET", f"/api/artifacts/{artifact_id}")
        return ArtifactResponse.model_validate(response.json())

    def list(
        self, *, project_id: UUID, skip: int = 0, limit: int = 100
    ) -> ArtifactListResponse:
        """List a project's artifacts, without their data.

        Calls ``GET /api/artifacts/``.

        Args:
            project_id (UUID): The project.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            ArtifactListResponse: A page of artifacts.
        """
        response = self._parent._request(
            "GET",
            "/api/artifacts/",
            params={"project_id": str(project_id), "skip": skip, "limit": limit},
        )
        return ArtifactListResponse.model_validate(response.json())
