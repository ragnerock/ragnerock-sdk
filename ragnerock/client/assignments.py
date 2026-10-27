"""Agent assignment endpoints (``/api/projects/{id}/assignments/...``).

An assignment is an agent given a task. The task opens a transcript — a
notebook that is the agent's own record, hidden from notebook lists — and the
agent works through it turn by turn until it answers. An assignment runs as
the person who gave it (their credentials and credits), and is bounded by a
token budget, a turn cap and a deadline.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ragnerock.client._base import _ApiModel, _body, _iter_sse_data, _Section
from ragnerock.client.notebooks import CellResponse
from ragnerock.timestamps import UtcDatetime

STREAM_READ_TIMEOUT_SECONDS = 60.0
"""Read timeout for an assignment's live stream.

The server sends a keepalive after every fifteen seconds of quiet, so a read
that waits four times that long has lost the connection.
"""


class AssignmentStatus(StrEnum):
    """Where an assignment stands."""

    QUEUED = "queued"
    """Ready to run its next turn."""

    RUNNING = "running"
    """Running a turn."""

    WAITING = "waiting"
    """Suspended until a child finishes, a person answers, or a time passes."""

    HALTED = "halted"
    """Paused, and resumable from where it stopped."""

    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentQuestionStatus(StrEnum):
    """Where a question an agent asked a person stands."""

    OPEN = "open"
    """Waiting for an answer."""

    ANSWERED = "answered"
    EXPIRED = "expired"
    """Its deadline passed unanswered."""


class AssignmentResponse(_ApiModel):
    """An agent assignment.

    Attributes:
        id (UUID): The assignment.
        project_id (UUID | None): Its project.
        agent_id (UUID | None): The agent it runs as; ``None`` for the
            research agent.
        notebook_id (UUID | None): Its transcript, readable through
            ``client.notebooks`` and ``client.cells`` like any notebook.
        status (str | None): An :class:`AssignmentStatus` value.
        status_reason (str | None): Why it stopped, for a failed, halted or
            cancelled assignment (e.g. ``"budget_exhausted"``).
        last_error (str | None): Why its last turn failed.
        parent_id (UUID | None): The assignment that dispatched it, if any.
        depth (int): 0 for one a person gave, one more than its parent's for a
            child.
        budget_cost_weighted_tokens (int | None): What it may spend, in
            cost-weighted tokens.
        spent_cost_weighted_tokens (int | None): What it has spent.
        anchor_document_id (UUID | None): The document its deliverable is
            written on, when it declares an output schema.
    """

    id: UUID
    project_id: UUID | None = None
    agent_id: UUID | None = None
    notebook_id: UUID | None = None
    runs_as_user_id: UUID | None = None
    status: str | None = None
    status_reason: str | None = None
    last_error: str | None = None
    parent_id: UUID | None = None
    depth: int = 0
    turns: int | None = None
    budget_cost_weighted_tokens: int | None = None
    spent_cost_weighted_tokens: int | None = None
    output_schema_id: UUID | None = None
    anchor_document_id: UUID | None = None
    expires_at: UtcDatetime = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None


class AssignmentListResponse(_ApiModel):
    """Paginated list response for a project's assignments."""

    assignments: list[AssignmentResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class AssignmentSpend(_ApiModel):
    """What your assignments of one agent were given and have spent."""

    assignments: int = 0
    budget_cost_weighted_tokens: int = 0
    spent_cost_weighted_tokens: int = 0


class AgentAssignmentListResponse(_ApiModel):
    """A page of one agent's assignments, with its per-status counts.

    Attributes:
        counts (dict[str, int]): The agent's assignments in each status,
            whatever the filter.
        spend (AssignmentSpend | None): Your own spend on this agent.
        retention_days (int | None): How many days a finished assignment's
            transcript is kept.
    """

    assignments: list[AssignmentResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0
    counts: dict[str, int] = {}
    spend: AssignmentSpend | None = None
    retention_days: int | None = None


class AgentThread(_ApiModel):
    """One assignment transcript or conversation with an agent.

    Attributes:
        kind (str | None): ``"transcript"`` or ``"conversation"``.
        notebook_id (UUID): The notebook it is.
        assignment_id (UUID | None): A transcript's assignment.
        status (str | None): That assignment's :class:`AssignmentStatus`.
    """

    notebook_id: UUID
    kind: str | None = None
    title: str | None = None
    created_by: UUID | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None
    assignment_id: UUID | None = None
    status: str | None = None


class AgentThreadListResponse(_ApiModel):
    """Paginated list response for an agent's threads."""

    threads: list[AgentThread] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class AgentQuestionResponse(_ApiModel):
    """A question an agent asked a person.

    Attributes:
        id (UUID): The question.
        assignment_id (UUID | None): The assignment that asked it.
        notebook_id (UUID | None): The assignment's transcript.
        question (str | None): What the agent asked.
        status (str | None): An :class:`AgentQuestionStatus` value.
        answer (str | None): The answer, once there is one.
        deadline (datetime | None): When the agent stops waiting.
    """

    id: UUID
    project_id: UUID | None = None
    assignment_id: UUID | None = None
    agent_id: UUID | None = None
    agent_name: str | None = None
    notebook_id: UUID | None = None
    question: str | None = None
    status: str | None = None
    answer: str | None = None
    deadline: UtcDatetime = None
    answered_at: UtcDatetime = None
    created_at: UtcDatetime = None


class AgentQuestionListResponse(_ApiModel):
    """Paginated list response for agent questions."""

    questions: list[AgentQuestionResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class AssignmentStatusEvent(_ApiModel):
    """A stream event carrying the assignment as it now stands."""

    kind: str = "status"
    assignment: AssignmentResponse


class AssignmentCellEvent(_ApiModel):
    """A stream event carrying a transcript cell you can see."""

    kind: str = "cell"
    cell: CellResponse


def _parse_stream_event(
    payload: str,
) -> AssignmentStatusEvent | AssignmentCellEvent | None:
    """Decode one assignment stream event by its ``kind``.

    Args:
        payload (str): The event's SSE data.

    Returns:
        AssignmentStatusEvent | AssignmentCellEvent | None: The event, or
        ``None`` for a kind this SDK doesn't know.
    """
    data = json.loads(payload)
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    if kind == "status":
        return AssignmentStatusEvent.model_validate(data)
    if kind == "cell":
        return AssignmentCellEvent.model_validate(data)
    return None


class _AssignmentsSection(_Section):
    """Assignments: tasks given to agents, and the questions they ask."""

    def create(
        self,
        project_id: UUID,
        *,
        agent_id: UUID,
        task: str,
        output_schema_id: UUID | None = None,
        deadline: datetime | None = None,
        budget: int | None = None,
    ) -> AssignmentResponse:
        """Give an agent a task, and start it working.

        Calls ``POST /api/projects/{project_id}/assignments``.

        Args:
            project_id (UUID): The project the work is in.
            agent_id (UUID): The agent, one of the project's AI agents.
            task (str): What the agent is to do.
            output_schema_id (UUID | None): A schema of the project the
                agent's deliverable must match. Without one, the agent's
                answer in the transcript is the deliverable.
            deadline (datetime | None): When the assignment fails for age,
                whatever it is doing. Timezone-aware, and in the future.
            budget (int | None): What it may spend, in cost-weighted tokens: at
                most the account's per-assignment budget, which it gets when
                this is ``None``.

        Returns:
            AssignmentResponse: The new assignment, queued.

        Raises:
            ValueError: If ``deadline`` has no time zone (nothing is sent).
        """
        if deadline is not None and deadline.utcoffset() is None:
            raise ValueError("deadline must be timezone-aware")
        body = _body(
            agent_id=agent_id,
            task=task,
            output_schema_id=output_schema_id,
            deadline=deadline.isoformat() if deadline is not None else None,
            budget_cost_weighted_tokens=budget,
        )
        response = self._parent._request(
            "POST", f"/api/projects/{project_id}/assignments", json_body=body
        )
        return AssignmentResponse.model_validate(response.json())

    def dispatch(
        self,
        project_id: UUID,
        *,
        parent_id: UUID,
        agent_id: UUID,
        task: str,
        output_schema_id: UUID | None = None,
        budget: int | None = None,
    ) -> AssignmentResponse:
        """Give one of your running assignments a child: another agent on part of the work.

        Calls ``POST /api/projects/{project_id}/assignments`` with a
        ``parent_id``. The child runs as you, until its parent's deadline, on a
        share of its parent's budget; its parent reads its result when it ends.
        Only the person the parent runs as may give it a child.

        Args:
            project_id (UUID): The project the work is in.
            parent_id (UUID): The running assignment the child belongs to.
            agent_id (UUID): The agent, one of the project's AI agents.
            task (str): What the child is to do.
            output_schema_id (UUID | None): A schema of the project its
                deliverable must match.
            budget (int | None): Its share of the parent's budget, in
                cost-weighted tokens; ``None`` for an equal share of what the
                parent has left.

        Returns:
            AssignmentResponse: The child, queued.
        """
        body = _body(
            agent_id=agent_id,
            task=task,
            output_schema_id=output_schema_id,
            parent_id=parent_id,
            budget_cost_weighted_tokens=budget,
        )
        response = self._parent._request(
            "POST", f"/api/projects/{project_id}/assignments", json_body=body
        )
        return AssignmentResponse.model_validate(response.json())

    def list(
        self, project_id: UUID, *, skip: int = 0, limit: int = 50
    ) -> AssignmentListResponse:
        """List a project's assignments, newest first.

        Calls ``GET /api/projects/{project_id}/assignments``.

        Args:
            project_id (UUID): The project.
            skip (int): Offset into the result set.
            limit (int): Page size, at most 200.

        Returns:
            AssignmentListResponse: A page of assignments.
        """
        response = self._parent._request(
            "GET",
            f"/api/projects/{project_id}/assignments",
            params={"skip": skip, "limit": limit},
        )
        return AssignmentListResponse.model_validate(response.json())

    def get(self, project_id: UUID, assignment_id: UUID) -> AssignmentResponse:
        """Fetch one assignment: where it stands, and where its transcript is.

        Calls ``GET /api/projects/{project_id}/assignments/{assignment_id}``.

        Args:
            project_id (UUID): The project.
            assignment_id (UUID): The assignment.

        Returns:
            AssignmentResponse: The assignment.

        Raises:
            NotFoundError: If no assignment has that id.
        """
        response = self._parent._request(
            "GET", f"/api/projects/{project_id}/assignments/{assignment_id}"
        )
        return AssignmentResponse.model_validate(response.json())

    def questions(
        self,
        *,
        status: str | None = AgentQuestionStatus.OPEN,
        skip: int = 0,
        limit: int = 50,
    ) -> AgentQuestionListResponse:
        """List the questions agents have asked you, newest first.

        Calls ``GET /api/agent-questions``. By default, only the open ones:
        the agents waiting on your answer.

        Args:
            status (str | None): An :class:`AgentQuestionStatus` value to
                filter by; ``None`` lists every question.
            skip (int): Offset into the result set.
            limit (int): Page size, at most 200.

        Returns:
            AgentQuestionListResponse: A page of questions.
        """
        response = self._parent._request(
            "GET",
            "/api/agent-questions",
            params={
                "skip": skip,
                "limit": limit,
                "status": str(status) if status is not None else None,
            },
        )
        return AgentQuestionListResponse.model_validate(response.json())

    def answer(
        self, project_id: UUID, question_id: UUID, *, answer: str
    ) -> AgentQuestionResponse:
        """Answer a question an agent asked you, and let it carry on.

        Calls ``POST /api/projects/{project_id}/agent-questions/{question_id}/answer``.
        The answer is written into the assignment's transcript as your message
        and wakes the assignment. Answering a question that is already
        answered changes nothing; the first answer stands.

        Args:
            project_id (UUID): The project.
            question_id (UUID): The question.
            answer (str): Your answer.

        Returns:
            AgentQuestionResponse: The question, answered.
        """
        response = self._parent._request(
            "POST",
            f"/api/projects/{project_id}/agent-questions/{question_id}/answer",
            json_body={"answer": answer},
        )
        return AgentQuestionResponse.model_validate(response.json())

    def cancel(self, project_id: UUID, assignment_id: UUID) -> AssignmentResponse:
        """Cancel an assignment that has not finished.

        Calls ``POST /api/projects/{project_id}/assignments/{assignment_id}/cancel``.
        Final: a turn in progress stops at its next step, and the assignment
        ends ``cancelled``. What it already wrote stays.

        Args:
            project_id (UUID): The project.
            assignment_id (UUID): The assignment.

        Returns:
            AssignmentResponse: The assignment, cancelled.
        """
        response = self._parent._request(
            "POST", f"/api/projects/{project_id}/assignments/{assignment_id}/cancel"
        )
        return AssignmentResponse.model_validate(response.json())

    def list_for_agent(
        self,
        project_id: UUID,
        agent_id: UUID,
        *,
        status: list[str] | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> AgentAssignmentListResponse:
        """List one agent's assignments in a project, newest first.

        Calls ``GET /api/projects/{project_id}/agents/{agent_id}/assignments``.
        Beside the page come the agent's counts in every status, whatever the
        filter, and what your own assignments of it have spent.

        Args:
            project_id (UUID): The project.
            agent_id (UUID): The agent.
            status (list[str] | None): Only these :class:`AssignmentStatus`
                values, sent as a repeated ``status`` parameter; ``None`` for
                every status.
            skip (int): Offset into the result set.
            limit (int): Page size, at most 200.

        Returns:
            AgentAssignmentListResponse: The page, the total, the counts and
            your spend.
        """
        response = self._parent._request(
            "GET",
            f"/api/projects/{project_id}/agents/{agent_id}/assignments",
            params={
                "skip": skip,
                "limit": limit,
                "status": [str(s) for s in status] if status is not None else None,
            },
        )
        return AgentAssignmentListResponse.model_validate(response.json())

    def threads(
        self, project_id: UUID, agent_id: UUID, *, skip: int = 0, limit: int = 50
    ) -> AgentThreadListResponse:
        """List an agent's transcripts and your conversations with it, newest first.

        Calls ``GET /api/projects/{project_id}/agents/{agent_id}/threads``.

        Args:
            project_id (UUID): The project.
            agent_id (UUID): The agent.
            skip (int): Offset into the result set.
            limit (int): Page size, at most 200.

        Returns:
            AgentThreadListResponse: A page of threads.
        """
        response = self._parent._request(
            "GET",
            f"/api/projects/{project_id}/agents/{agent_id}/threads",
            params={"skip": skip, "limit": limit},
        )
        return AgentThreadListResponse.model_validate(response.json())

    def stream(
        self, project_id: UUID, assignment_id: UUID
    ) -> Iterator[AssignmentStatusEvent | AssignmentCellEvent]:
        """Follow an assignment live, until it ends.

        Calls ``GET /api/projects/{project_id}/assignments/{assignment_id}/stream``
        and reads the server-sent events. Yields where the assignment stands
        first, then each change: a status event whenever it moves, and a cell
        event for each transcript cell you can see, when it first appears and
        again whenever its position changes. Keep cells by ``id`` and order
        them by ``position``. Iteration ends once the assignment has ended;
        after a dropped connection, call this again and the transcript is sent
        again. Events of a kind this SDK doesn't know are skipped.

        Args:
            project_id (UUID): The project.
            assignment_id (UUID): The assignment.

        Yields:
            AssignmentStatusEvent | AssignmentCellEvent: Each event, by
            ``kind``.

        Raises:
            RagnerockError: Or a subclass, when the server refuses the stream.
                Raised on the first iteration.
        """
        with self._parent._stream(
            "GET",
            f"/api/projects/{project_id}/assignments/{assignment_id}/stream",
            headers={"accept": "text/event-stream"},
            timeout=STREAM_READ_TIMEOUT_SECONDS,
        ) as response:
            for payload in _iter_sse_data(response):
                event = _parse_stream_event(payload)
                if event is not None:
                    yield event

    def resume(self, project_id: UUID, assignment_id: UUID) -> AssignmentResponse:
        """Resume a paused (``halted``) assignment from where it stopped.

        Calls ``POST /api/projects/{project_id}/assignments/{assignment_id}/resume``.
        Refused while whatever paused it still stands — a pause on its agent,
        a person or model it can no longer run as, an account out of credits.

        Args:
            project_id (UUID): The project.
            assignment_id (UUID): The assignment.

        Returns:
            AssignmentResponse: The assignment, queued.
        """
        response = self._parent._request(
            "POST", f"/api/projects/{project_id}/assignments/{assignment_id}/resume"
        )
        return AssignmentResponse.model_validate(response.json())
