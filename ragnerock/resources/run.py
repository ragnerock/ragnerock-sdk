"""Run resource."""

from __future__ import annotations

import time
from enum import IntEnum, auto
from typing import Any
from uuid import UUID

from ragnerock.resources.base import OptionalDateTime, _Resource


class RunStatus(IntEnum):
    """Run lifecycle status. Numeric values match the API."""

    NOT_STARTED = 1
    """The run has been created but execution has not begun."""

    IN_PROGRESS = 2
    """The run is currently executing."""

    SUCCEEDED = 3
    """The run finished successfully (terminal)."""

    FAILED = 4
    """The run finished with an error (terminal)."""


class RunKind(IntEnum):
    """How a run was started. Mirrors the server-side enum values."""

    AUTOMATIC = auto()
    """Run started automatically by the server (e.g. on upload)."""

    MANUAL = auto()
    """Run started explicitly via :meth:`~ragnerock.session.Session.run`."""


class Run(_Resource):
    """A single agent run against a single document.

    Runs are created by :meth:`~ragnerock.session.Session.run` (for example,
    ``session.run(agent, documents=[...])``) rather than constructed
    directly. Use :meth:`refresh` or :meth:`wait` to observe progress and
    :meth:`cancel` / :meth:`retry` to control execution.
    """

    id: UUID | None = None
    document_id: UUID | None = None
    status: RunStatus | None = None
    status_message: str | None = None
    start_time: OptionalDateTime = None
    end_time: OptionalDateTime = None
    execution_trace: dict[str, Any] | None = None
    kind: RunKind | None = None
    should_parse: bool | None = None
    capture_execution_log: bool | None = None
    n_tokens: int | None = None
    n_pages: int | None = None
    n_mb: float | None = None
    phase: str | None = None
    current_stage_index: int | None = None
    total_stages: int | None = None
    current_stage_name: str | None = None
    current_stage_type: str | None = None
    current_stage_subtasks_completed: int | None = None
    current_stage_subtasks_total: int | None = None
    agent_ids: list[UUID] = []
    archived_at: OptionalDateTime = None
    live_assignments: int = 0

    def refresh(self) -> None:
        """Re-fetch this run from the server and overwrite fields in place.

        Equivalent to ``session.refresh(run)``.

        Raises:
            RuntimeError: If the run has no session back-reference.
        """
        if self._session is None:
            raise RuntimeError("Run is not bound to a session; cannot refresh.")
        self._session.refresh(self)

    def wait(self, *, timeout: float | None = None, poll_interval: float = 2.0) -> None:
        """Poll the run until it reaches a terminal status.

        Terminal statuses are :attr:`RunStatus.SUCCEEDED` and
        :attr:`RunStatus.FAILED`. Returns immediately if the run is already
        terminal when called; otherwise refreshes every ``poll_interval``
        seconds until it is.

        Args:
            timeout (float | None): Maximum total seconds to wait. ``None``
                (the default) waits indefinitely.
            poll_interval (float): Seconds between refreshes.

        Raises:
            TimeoutError: If ``timeout`` elapses before the run reaches a
                terminal status.
            RuntimeError: If the run has no session back-reference.
        """
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            if self.status in (RunStatus.SUCCEEDED, RunStatus.FAILED):
                return
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Run {self.id} did not reach terminal status within {timeout}s"
                )
            time.sleep(poll_interval)
            self.refresh()

    def cancel(self) -> None:
        """Request server-side cancellation of this run and refresh local state.

        The server transitions the run toward a terminal state; this method
        then re-fetches the run so ``status`` and related fields reflect the
        post-cancel state. Already-terminal runs are left alone server-side.

        Raises:
            RuntimeError: If the run is not bound to a session, or has no
                ``id`` yet.
        """
        if self._session is None:
            raise RuntimeError("Run is not bound to a session; cannot cancel.")
        if self.id is None:
            raise RuntimeError("Run has no id; cannot cancel.")
        self._session._engine.client.runs.cancel(self.id)
        self.refresh()

    def retry(self) -> None:
        """Request a retry of this run and refresh local state.

        Typically used on a failed run. The server resets execution state and
        re-queues the run; this method then re-fetches it so ``status`` and
        related fields reflect the post-retry state.

        Raises:
            RuntimeError: If the run is not bound to a session, or has no
                ``id`` yet.
        """
        if self._session is None:
            raise RuntimeError("Run is not bound to a session; cannot retry.")
        if self.id is None:
            raise RuntimeError("Run has no id; cannot retry.")
        self._session._engine.client.runs.retry(self.id)
        self.refresh()
