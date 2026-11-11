"""Document-folder endpoints (``/api/projects/{id}/document-folders/...``)."""

from __future__ import annotations

from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section
from ragnerock.client.documents import DocumentListResponse


class DocumentFolderResponse(_ApiModel):
    """Response payload representing a single document folder.

    Attributes:
        id (UUID): The document folder's id: the ``document_folder_id`` its
            documents carry.
        project_id (UUID | None): Owning project.
        name (str): Display name, unique within the project.
        folder_id (UUID | None): The resource folder it is filed in, if any.
            Not a document folder: resource folders organize a project's
            resources in the sidebar.
    """

    id: UUID
    project_id: UUID | None = None
    name: str
    folder_id: UUID | None = None


class DocumentFolderListResponse(_ApiModel):
    """Paginated list response for document folders."""

    document_folders: list[DocumentFolderResponse]
    total: int
    skip: int
    limit: int


class _DocumentFoldersSection(_Section):
    """Document-folder CRUD endpoints, scoped by project."""

    def list(
        self, project_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> DocumentFolderListResponse:
        """List the document folders in a project.

        Calls ``GET /api/projects/{project_id}/document-folders/``.

        Args:
            project_id (UUID): Project whose document folders to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            DocumentFolderListResponse: A page of document folders.
        """
        response = self._parent._request(
            "GET",
            f"/api/projects/{project_id}/document-folders/",
            params={"skip": skip, "limit": limit},
        )
        return DocumentFolderListResponse.model_validate(response.json())

    def get(self, project_id: UUID, document_folder_id: UUID) -> DocumentFolderResponse:
        """Fetch a single document folder.

        Calls ``GET /api/projects/{project_id}/document-folders/{document_folder_id}``.

        Args:
            project_id (UUID): Owning project.
            document_folder_id (UUID): Document folder to fetch.

        Returns:
            DocumentFolderResponse: The document folder.

        Raises:
            NotFoundError: If no document folder with that id exists in the
                project.
        """
        response = self._parent._request(
            "GET", f"/api/projects/{project_id}/document-folders/{document_folder_id}"
        )
        return DocumentFolderResponse.model_validate(response.json())

    def create(self, project_id: UUID, *, name: str) -> DocumentFolderResponse:
        """Create a new document folder in a project.

        Calls ``POST /api/projects/{project_id}/document-folders/``.

        Args:
            project_id (UUID): Owning project.
            name (str): Folder name. Must be unique within the project.

        Returns:
            DocumentFolderResponse: The newly created document folder.
        """
        response = self._parent._request(
            "POST",
            f"/api/projects/{project_id}/document-folders/",
            json_body={"name": name},
        )
        return DocumentFolderResponse.model_validate(response.json())

    def update(
        self, project_id: UUID, document_folder_id: UUID, *, name: str
    ) -> DocumentFolderResponse:
        """Rename a document folder.

        Calls ``PUT /api/projects/{project_id}/document-folders/{document_folder_id}``.

        Args:
            project_id (UUID): Owning project.
            document_folder_id (UUID): Document folder to rename.
            name (str): New folder name.

        Returns:
            DocumentFolderResponse: The updated document folder.
        """
        response = self._parent._request(
            "PUT",
            f"/api/projects/{project_id}/document-folders/{document_folder_id}",
            json_body={"name": name},
        )
        return DocumentFolderResponse.model_validate(response.json())

    def delete(self, project_id: UUID, document_folder_id: UUID) -> None:
        """Delete a document folder.

        Calls
        ``DELETE /api/projects/{project_id}/document-folders/{document_folder_id}``.
        The folder's documents are not deleted; they become unfiled.

        Args:
            project_id (UUID): Owning project.
            document_folder_id (UUID): Document folder to delete.
        """
        self._parent._request(
            "DELETE",
            f"/api/projects/{project_id}/document-folders/{document_folder_id}",
        )

    def list_documents(
        self, document_folder_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> DocumentListResponse:
        """List the documents in a document folder.

        Calls ``GET /api/documents/document-folder/{document_folder_id}``. This
        is the same endpoint as
        :meth:`~._DocumentsSection.list_by_document_folder`; it's exposed here
        as well so callers working at the folder level don't have to reach
        across sections.

        Args:
            document_folder_id (UUID): Document folder to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            DocumentListResponse: A page of documents in the folder.
        """
        response = self._parent._request(
            "GET",
            f"/api/documents/document-folder/{document_folder_id}",
            params={"skip": skip, "limit": limit},
        )
        return DocumentListResponse.model_validate(response.json())
