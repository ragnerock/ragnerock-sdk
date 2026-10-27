"""Document-group endpoints (``/api/projects/{id}/groups/...``)."""

from __future__ import annotations

from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section
from ragnerock.client.documents import DocumentListResponse


class DocumentGroupResponse(_ApiModel):
    """Response payload representing a single document group."""

    id: UUID
    project_id: UUID | None = None
    name: str


class DocumentGroupListResponse(_ApiModel):
    """Paginated list response for document groups."""

    groups: list[DocumentGroupResponse]
    total: int
    skip: int
    limit: int


class _GroupsSection(_Section):
    """Document-group CRUD endpoints, scoped by project."""

    def list(
        self, project_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> DocumentGroupListResponse:
        """List document groups in a project.

        Calls ``GET /api/projects/{project_id}/groups/``.

        Args:
            project_id (UUID): Project whose groups to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            DocumentGroupListResponse: A page of groups.
        """
        response = self._parent._request(
            "GET",
            f"/api/projects/{project_id}/groups/",
            params={"skip": skip, "limit": limit},
        )
        return DocumentGroupListResponse.model_validate(response.json())

    def get(self, project_id: UUID, group_id: UUID) -> DocumentGroupResponse:
        """Fetch a single document group.

        Calls ``GET /api/projects/{project_id}/groups/{group_id}``.

        Args:
            project_id (UUID): Owning project.
            group_id (UUID): Group to fetch.

        Returns:
            DocumentGroupResponse: The group response.

        Raises:
            NotFoundError: If no group with that id exists in the project.
        """
        response = self._parent._request(
            "GET", f"/api/projects/{project_id}/groups/{group_id}"
        )
        return DocumentGroupResponse.model_validate(response.json())

    def create(self, project_id: UUID, *, name: str) -> DocumentGroupResponse:
        """Create a new document group in a project.

        Calls ``POST /api/projects/{project_id}/groups/``.

        Args:
            project_id (UUID): Owning project.
            name (str): Group name. Must be unique within the project.

        Returns:
            DocumentGroupResponse: The newly created group response.
        """
        response = self._parent._request(
            "POST",
            f"/api/projects/{project_id}/groups/",
            json_body={"name": name},
        )
        return DocumentGroupResponse.model_validate(response.json())

    def update(
        self, project_id: UUID, group_id: UUID, *, name: str
    ) -> DocumentGroupResponse:
        """Rename a document group.

        Calls ``PUT /api/projects/{project_id}/groups/{group_id}``.

        Args:
            project_id (UUID): Owning project.
            group_id (UUID): Group to rename.
            name (str): New group name.

        Returns:
            DocumentGroupResponse: The updated group response.
        """
        response = self._parent._request(
            "PUT",
            f"/api/projects/{project_id}/groups/{group_id}",
            json_body={"name": name},
        )
        return DocumentGroupResponse.model_validate(response.json())

    def delete(self, project_id: UUID, group_id: UUID) -> None:
        """Delete a document group.

        Calls ``DELETE /api/projects/{project_id}/groups/{group_id}``. The
        group's documents are not deleted — they are unassociated from the
        group.

        Args:
            project_id (UUID): Owning project.
            group_id (UUID): Group to delete.
        """
        self._parent._request("DELETE", f"/api/projects/{project_id}/groups/{group_id}")

    def list_documents(
        self, group_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> DocumentListResponse:
        """List documents in a group.

        Calls ``GET /api/documents/group/{group_id}``. This is the same
        endpoint as :meth:`~._DocumentsSection.list_by_group`; it's exposed
        here as well so callers working at the group level don't have to
        reach across sections.

        Args:
            group_id (UUID): Group to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            DocumentListResponse: A page of documents in the group.
        """
        response = self._parent._request(
            "GET",
            f"/api/documents/group/{group_id}",
            params={"skip": skip, "limit": limit},
        )
        return DocumentListResponse.model_validate(response.json())
