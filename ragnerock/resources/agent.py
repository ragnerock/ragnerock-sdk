"""Agent and AgentNode resources."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from ragnerock.errors import ValidationError
from ragnerock.resources.base import OptionalDateTime, _Resource
from ragnerock.resources.condition import compile_condition

if TYPE_CHECKING:
    from ragnerock.resources.task import Task
    from ragnerock.session import Session


class AgentSchedule(BaseModel):
    """An agent's recurring-run schedule.

    Saving a schedule authorizes recurring unattended runs under the saving
    user's identity. The expression and timezone are validated server-side.

    Attributes:
        cron (str): A five-field crontab expression, e.g. ``"0 6 * * 1-5"``.
        timezone (str): IANA timezone the crontab is interpreted in.
        enabled (bool): Whether the schedule fires.
        lookback (int | None): Minimum width of each run's fetch window, in
            seconds. ``None`` uses whatever the schedule's tiling produces.
    """

    model_config = ConfigDict(extra="allow")

    cron: str
    timezone: str = "UTC"
    enabled: bool = True
    lookback: int | None = None


class AgentNode(_Resource):
    """One node in an agent, wrapping a task with execution configuration.

    Nodes are created via :meth:`Agent.add_node` and wired into a DAG with
    the ``>>`` operator (see :meth:`__rshift__` and :meth:`__rrshift__`). The
    ``in_nodes`` and ``out_nodes`` lists record the node's position in the
    graph; ``on_error`` accepts ``"SKIP_NODE"`` (the server default) or
    ``"FAIL_RUN"``. ``target_input_id`` names the file input the node
    annotates (``None`` means the agent's sole file input), and
    ``context_input_ids`` lists the inputs wired to it as context.
    """

    id: UUID | None = None
    agent_id: UUID | None = None
    task_id: UUID | None = None
    task_name: str | None = None
    condition: dict[str, Any] | None = None
    persist: bool = True
    on_error: str = "SKIP_NODE"
    max_retries: int = 0
    annotations_only: bool = False
    in_nodes: list[UUID] = []
    out_nodes: list[UUID] = []
    position_x: int | None = None
    position_y: int | None = None
    position_z: int | None = None
    target_input_id: UUID | None = None
    context_input_ids: list[UUID] = []
    include_schedule_context: bool = False
    required_functions: list[str] = []

    def __rshift__(
        self, other: AgentNode | list[AgentNode]
    ) -> AgentNode | list[AgentNode]:
        """Wire this node as an upstream of ``other``.

        ``a >> b`` appends ``b.id`` to ``a.out_nodes`` and ``a.id`` to
        ``b.in_nodes``, deduped, and stages both nodes for update on the next
        :meth:`Session.commit`. Returns ``other`` so expressions chain
        (``a >> b >> c`` wires ``a→b`` then ``b→c``).

        Args:
            other (AgentNode | list[AgentNode]): A single downstream
                node or a list of downstream nodes (fan-out).

        Returns:
            AgentNode | list[AgentNode]: ``other`` unchanged, for
            chaining.

        Raises:
            ValidationError: Either node is not yet committed, or the two
                nodes belong to different agents.
            RuntimeError: Either node has no session back-reference.
            TypeError: ``other`` is not a :class:`AgentNode` or a list of
                :class:`AgentNode`.
        """
        if isinstance(other, list):
            for dst in other:
                if not isinstance(dst, AgentNode):
                    raise TypeError(
                        "Right-hand side list must contain only AgentNode "
                        f"instances; got {type(dst).__name__}"
                    )
                _wire(self, dst)
            return other
        if isinstance(other, AgentNode):
            _wire(self, other)
            return other
        raise TypeError(
            "Right-hand side of `>>` must be an AgentNode or list of "
            f"AgentNode; got {type(other).__name__}"
        )

    def __rrshift__(self, other: list[AgentNode]) -> AgentNode:
        """Wire a list of upstream nodes into this node (``[a, b] >> self``).

        Python dispatches the reflected operator when the left-hand side is a
        plain ``list`` (which has no ``__rshift__``). Returns ``self`` so the
        chain continues.

        Args:
            other (list[AgentNode]): Upstream nodes to fan in.

        Returns:
            AgentNode: ``self``, for chaining.

        Raises:
            TypeError: ``other`` is not a list of :class:`AgentNode`.
            ValidationError: Any node is not yet committed, or any node is in
                a different agent.
            RuntimeError: Any node has no session back-reference.
        """
        if not isinstance(other, list):
            raise TypeError(
                "Left-hand side of `>>` into an AgentNode must be a list; "
                f"got {type(other).__name__}"
            )
        for src in other:
            if not isinstance(src, AgentNode):
                raise TypeError(
                    "Left-hand side list must contain only AgentNode "
                    f"instances; got {type(src).__name__}"
                )
            _wire(src, self)
        return self


def _wire(src: AgentNode, dst: AgentNode) -> None:
    """Record a directed edge ``src → dst`` locally and stage both nodes.

    Mutates ``src.out_nodes`` and ``dst.in_nodes`` in place (deduped) and
    enqueues both nodes onto the shared session's dirty queue so the next
    :meth:`Session.commit` flushes the edge to the server.
    """
    if src._session is None or dst._session is None:
        raise RuntimeError(
            "Both agent nodes must be bound to a session before wiring; "
            "call session.commit() after add_node to assign IDs."
        )
    if src._session is not dst._session:
        raise ValidationError("Cannot wire agent nodes from different sessions.")
    if src.id is None or dst.id is None:
        raise ValidationError(
            "Cannot wire agent nodes that have no id yet; "
            "call session.commit() to assign ids before using `>>`."
        )
    if src.agent_id != dst.agent_id:
        raise ValidationError(
            "Cannot wire agent nodes that belong to different agents."
        )

    if dst.id not in src.out_nodes:
        src.out_nodes = [*src.out_nodes, dst.id]
    if src.id not in dst.in_nodes:
        dst.in_nodes = [*dst.in_nodes, src.id]

    src._session.update(src)
    src._session.update(dst)


class Agent(_Resource):
    """A DAG of tasks to run against documents.

    Agents do not execute on their own. Build an agent by calling
    :meth:`add_node` for each task and wiring the returned
    :class:`AgentNode` instances with ``>>``, then trigger execution via
    :meth:`~ragnerock.session.Session.run`, which returns
    :class:`~ragnerock.resources.run.Run` instances.

    ``inputs`` and ``outputs`` carry the agent's inputs (where its documents
    and context come from) and outputs (where its results are delivered) as
    the server describes them.
    """

    id: UUID | None = None
    project_id: UUID | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool = True
    auto_run_on_upload: bool = False
    is_draft: bool = False
    created_by_id: UUID | None = None
    created_at: OptionalDateTime = None
    updated_at: OptionalDateTime = None
    execution_order: list[str] = []
    nodes: list[AgentNode] = []
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    schedule: AgentSchedule | None = None
    schedule_state: dict[str, Any] | None = None
    schedules_enabled: bool = True
    pending_change_request_count: int = 0

    @model_validator(mode="after")
    def _adopt_nodes(self) -> Agent:
        """Stamp this agent's id onto nested nodes that lack one.

        The server's agent payload describes nodes without repeating the
        parent id, but a node needs ``agent_id`` to be updated, deleted, or
        wired with ``>>``.

        Returns:
            Agent: ``self``.
        """
        if self.id is not None:
            for node in self.nodes:
                if node.agent_id is None:
                    node.agent_id = self.id
                if node._session is None and self._session is not None:
                    node._bind(self._session)
        return self

    def _bind(self, session: Session) -> None:
        """Attach a session to this agent and to each of its nodes.

        Args:
            session (Session): The session that produced this agent.
        """
        super()._bind(session)
        for node in self.nodes:
            node._bind(session)

    def add_node(
        self,
        *,
        task: Task,
        condition: dict[str, Any] | None = None,
        persist: bool = True,
        on_error: str = "SKIP_NODE",
        max_retries: int = 0,
        annotations_only: bool = False,
    ) -> AgentNode:
        """Stage a new :class:`AgentNode` wrapping ``task``.

        Creates the node locally, appends it to :attr:`nodes`, and stages it
        via ``session.add(node)`` so it is created on the server at the next
        :meth:`Session.commit`. After commit, the returned node's ``id`` is
        populated and it can be wired with ``>>``.

        Args:
            task (Task): A persisted task (must have an ``id``).
            condition (dict[str, Any] | None): Optional MongoDB-style predicate
                restricting when the node fires. Compiled into the server's
                condition grammar via
                :func:`ragnerock.resources.condition.compile_condition`.
            persist (bool): Whether annotations produced here are persisted.
            on_error (str): Error-handling policy: ``"SKIP_NODE"`` (default)
                or ``"FAIL_RUN"``.
            max_retries (int): Retry count on transient failure.
            annotations_only (bool): Whether the node only emits annotations
                (no downstream documents or outputs).

        Returns:
            AgentNode: The newly staged node.

        Raises:
            RuntimeError: This agent has no session back-reference.
            ValidationError: This agent has not been committed,
                ``task`` has no ``id``, or ``condition`` is malformed.
        """
        if self._session is None:
            raise RuntimeError(
                "Agent is not bound to a session; "
                "call session.add(agent) and session.commit() first."
            )
        if self.id is None:
            raise ValidationError(
                "Cannot add a node to an unpersisted agent; "
                "call session.commit() first."
            )
        if task.id is None:
            raise ValidationError(
                "Cannot add a node for an unpersisted task; "
                "call session.commit() after adding the task."
            )

        compiled = compile_condition(condition) if condition is not None else None

        node = AgentNode(
            agent_id=self.id,
            task_id=task.id,
            task_name=task.name,
            condition=compiled,
            persist=persist,
            on_error=on_error,
            max_retries=max_retries,
            annotations_only=annotations_only,
        )
        self._session.add(node)
        self.nodes = [*self.nodes, node]
        return node
