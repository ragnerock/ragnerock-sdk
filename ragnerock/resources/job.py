"""Job resource."""

from __future__ import annotations

import time
from datetime import datetime
from enum import IntEnum, auto
from typing import Any
from uuid import UUID

from ragnerock.resources.base import _Resource


class JobStatus(IntEnum):
    """Job lifecycle status. Numeric values match the API."""

    NOT_STARTED = 1
    IN_PROGRESS = 2
    SUCCEEDED = 3
    FAILED = 4


class JobType(IntEnum):
    """Job type. Mirrors the server-side enum values."""

    AUTOMATIC = auto()
    MANUAL = auto()


class Job(_Resource):
    """A single workflow execution against a single document.

    Created by ``session.run(workflow, documents=[...])``. Not created directly
    by users.

    Attributes:
        id (UUID | None): Job UUID.
        document_id (UUID | None): Document the job is processing.
        status (JobStatus | None): Current status.
        status_message (str | None): Human-readable status detail.
        start_time (datetime | None): When the job began executing.
        end_time (datetime | None): When the job finished (or ``None`` if
            still running).
        execution_trace (list[dict[str, Any]] | None): Per-node execution
            trace, when captured.
        job_type (JobType | None): Automatic vs manual job type.
        should_parse (bool | None): Whether the server should parse the
            document as part of the job.
        capture_execution_log (bool | None): Whether the server records a
            per-node execution trace.
        n_tokens (int | None): Token count processed by the job.
        n_pages (int | None): Page count processed by the job.
        n_mb (float | None): Document size in megabytes processed.
        phase (str | None): Current execution phase, when reported.
    """

    id: UUID | None = None
    document_id: UUID | None = None
    status: JobStatus | None = None
    status_message: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    execution_trace: list[dict[str, Any]] | None = None
    job_type: JobType | None = None
    should_parse: bool | None = None
    capture_execution_log: bool | None = None
    n_tokens: int | None = None
    n_pages: int | None = None
    n_mb: float | None = None
    phase: str | None = None

    def refresh(self) -> None:
        """Re-fetch this job from the server and overwrite fields in place.

        Equivalent to ``session.refresh(job)``.

        Raises:
            RuntimeError: If the job has no session back-reference.
        """
        if self._session is None:
            raise RuntimeError("Job is not bound to a session; cannot refresh.")
        self._session.refresh(self)

    def wait(
        self, *, timeout: float | None = None, poll_interval: float = 2.0
    ) -> None:
        """Poll the job until it reaches a terminal status.

        Terminal statuses are :attr:`JobStatus.SUCCEEDED` and
        :attr:`JobStatus.FAILED`. Returns immediately if the job is already
        terminal when called; otherwise refreshes every ``poll_interval``
        seconds until it is.

        Args:
            timeout (float | None): Maximum total seconds to wait. ``None``
                (the default) waits indefinitely.
            poll_interval (float): Seconds between refreshes.

        Raises:
            TimeoutError: If ``timeout`` elapses before the job reaches a
                terminal status.
            RuntimeError: If the job has no session back-reference.
        """
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            if self.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                return
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Job {self.id} did not reach terminal status within {timeout}s"
                )
            time.sleep(poll_interval)
            self.refresh()

    def cancel(self) -> None:
        """Request server-side cancellation of this job.

        The server transitions the job toward a terminal state; this method
        updates local fields from the server's response (so ``status`` and
        related fields reflect the post-cancel state). Already-terminal jobs
        are left alone server-side.

        Raises:
            RuntimeError: If the job is not bound to a session, or has no
                ``id`` yet.
        """
        if self._session is None:
            raise RuntimeError("Job is not bound to a session; cannot cancel.")
        if self.id is None:
            raise RuntimeError("Job has no id; cannot cancel.")
        response = self._session._engine.client.jobs.cancel(self.id)
        self._update_from(response)

    def retry(self) -> None:
        """Request a retry of this job and refresh local state.

        Typically used on a failed job. The server resets execution state;
        this method updates local fields from the response so ``status`` and
        related fields reflect the post-retry state.

        Raises:
            RuntimeError: If the job is not bound to a session, or has no
                ``id`` yet.
        """
        if self._session is None:
            raise RuntimeError("Job is not bound to a session; cannot retry.")
        if self.id is None:
            raise RuntimeError("Job has no id; cannot retry.")
        response = self._session._engine.client.jobs.retry(self.id)
        self._update_from(response)

    def _update_from(self, response: Any) -> None:
        """Copy recognized fields from a server response onto this job.

        Accepts either a :class:`Job` instance (from ``model_dump()``) or a
        plain dict. Unknown fields in ``response`` are ignored; fields absent
        from ``response`` are left untouched on this instance. Silently
        returns if ``response`` is ``None`` or an unsupported type so that
        action endpoints returning minimal payloads stay non-destructive.

        Args:
            response (Any): The server response to merge into this instance.
        """
        if response is None:
            return
        if isinstance(response, Job):
            data = response.model_dump()
        elif isinstance(response, dict):
            data = response
        else:
            return
        for field_name in type(self).model_fields:
            if field_name in data:
                setattr(self, field_name, data[field_name])
