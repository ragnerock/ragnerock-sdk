"""Project lookup endpoints (``/api/projects/...``)."""

from __future__ import annotations

from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section


class ProjectResponse(_ApiModel):
    """Response payload representing a single project."""

    id: UUID
    name: str


class ProjectListResponse(_ApiModel):
    """Paginated list response for projects."""

    projects: list[ProjectResponse]
    total: int
    skip: int
    limit: int


class _ProjectsSection(_Section):
    """Project lookup endpoints."""

    def get(self, project_id: UUID) -> ProjectResponse:
        """Fetch a project by id.

        Calls ``GET /api/projects/{project_id}``.

        Args:
            project_id (UUID): UUID of the project.

        Returns:
            ProjectResponse: The project response.

        Raises:
            NotFoundError: If no project has that id.
        """
        response = self._parent._request("GET", f"/api/projects/{project_id}")
        return ProjectResponse.model_validate(response.json())

    def get_by_name(self, project_name: str) -> ProjectListResponse:
        """Find projects with a given name.

        Calls ``GET /api/projects/name/{project_name}``. The server returns a
        list because project names are not guaranteed unique; callers who
        expect a single match should verify ``len(response.projects) == 1``.

        Args:
            project_name (str): Exact project name to match.

        Returns:
            ProjectListResponse: A list response (possibly empty).
        """
        response = self._parent._request("GET", f"/api/projects/name/{project_name}")
        return ProjectListResponse.model_validate(response.json())
