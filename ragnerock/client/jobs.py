"""Job endpoints (``/api/jobs/...``)."""

from __future__ import annotations

from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section


class JobResponse(_ApiModel):
    """Response payload representing a single job."""

    id: UUID
    status: int


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
    """Response payload returned when creating one or more manual jobs."""

    job_ids: list[UUID]


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
        document_ids: list[UUID],
        workflow_ids: list[UUID],
        capture_execution_log: bool = False,
    ) -> CreateManualJobsResponse:
        """Create one job per (document, workflow) pair.

        Calls ``POST /api/jobs/``. The server returns one job id per created
        job in the order ``document_ids × workflow_ids``.

        Args:
            document_ids (list[UUID]): Documents to run against.
            workflow_ids (list[UUID]): Workflows to run.
            capture_execution_log (bool): If ``True``, the server records a
                per-node execution trace on each resulting job. More
                expensive; useful for debugging.

        Returns:
            CreateManualJobsResponse: A response whose ``job_ids`` list contains the created job ids.
        """
        body = {
            "document_ids": [str(x) for x in document_ids],
            "workflow_ids": [str(x) for x in workflow_ids],
            "capture_execution_log": capture_execution_log,
        }
        response = self._parent._request("POST", "/api/jobs/", json_body=body)
        return CreateManualJobsResponse.model_validate(response.json())

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
