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
        id: Job UUID.
        document_id: Document the job is processing.
        status: Current status.
        status_message: Human-readable status detail.
        start_time: When the job began executing.
        end_time: When the job finished (or ``None`` if still running).
        execution_trace: Per-node execution trace, when captured.
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
        """Shortcut for ``session.refresh(self)``. Updates this job in place."""
        if self._session is None:
            raise RuntimeError("Job is not bound to a session; cannot refresh.")
        self._session.refresh(self)

    def wait(self, *, timeout: float | None = None, poll_interval: float = 2.0) -> None:
        """Block until the job reaches a terminal status (SUCCEEDED / FAILED).

        Args:
            timeout: Optional seconds to wait before raising ``TimeoutError``.
            poll_interval: Seconds between status polls.
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
        """Cancel this job. Requires a bound session and ``id``."""
        if self._session is None:
            raise RuntimeError("Job is not bound to a session; cannot cancel.")
        if self.id is None:
            raise RuntimeError("Job has no id; cannot cancel.")
        response = self._session._engine.client.jobs.cancel(self.id)
        self._update_from(response)

    def retry(self) -> None:
        """Retry this job. Requires a bound session and ``id``."""
        if self._session is None:
            raise RuntimeError("Job is not bound to a session; cannot retry.")
        if self.id is None:
            raise RuntimeError("Job has no id; cannot retry.")
        response = self._session._engine.client.jobs.retry(self.id)
        self._update_from(response)

    def _update_from(self, response: Any) -> None:
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
