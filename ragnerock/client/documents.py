"""Document endpoints (``/api/documents/...``)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section
from ragnerock.client.jobs import JobResponse


class DocumentResponse(_ApiModel):
    """Response payload representing a single document."""

    id: UUID
    project_id: UUID
    name: str


class DocumentListResponse(_ApiModel):
    """Paginated list response for documents."""

    documents: list[DocumentResponse]
    total: int
    skip: int
    limit: int


class _DocumentsSection(_Section):
    """Document CRUD endpoints."""

    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> DocumentListResponse:
        """List documents, optionally scoped to one or more projects.

        Calls ``GET /api/documents/``.

        Args:
            project_ids (str | None): Comma-separated string of project UUIDs, or ``None``
                to list across every accessible project.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            DocumentListResponse: A page of documents with ``total`` set to the full result size.
        """
        response = self._parent._request(
            "GET",
            "/api/documents/",
            params={"project_ids": project_ids, "skip": skip, "limit": limit},
        )
        return DocumentListResponse.model_validate(response.json())

    def get(self, document_id: UUID) -> DocumentResponse:
        """Fetch a single document by id.

        Calls ``GET /api/documents/{document_id}``.

        Args:
            document_id (UUID): UUID of the document.

        Returns:
            DocumentResponse: The document response.

        Raises:
            NotFoundError: If no document has that id.
        """
        response = self._parent._request("GET", f"/api/documents/{document_id}")
        return DocumentResponse.model_validate(response.json())

    def get_by_name(self, document_name: str, project_id: UUID) -> DocumentResponse:
        """Fetch a document by name within a project.

        Calls ``GET /api/documents/name/{document_name}``. Names are unique
        within a project, so this returns a single document.

        Args:
            document_name (str): Exact name to match.
            project_id (UUID): Project to scope the lookup to.

        Returns:
            DocumentResponse: The document response.

        Raises:
            NotFoundError: If no document with that name exists in the
                project.
        """
        response = self._parent._request(
            "GET",
            f"/api/documents/name/{document_name}",
            params={"project_id": str(project_id)},
        )
        return DocumentResponse.model_validate(response.json())

    def create(
        self,
        *,
        project_id: UUID,
        file_path: str | None = None,
        source_url: str | None = None,
        name: str | None = None,
        group_id: UUID | None = None,
        file_type: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DocumentResponse:
        """Create a document by uploading a file or pointing at a URL.

        Calls ``POST /api/documents/`` as multipart. Exactly one of
        ``file_path`` or ``source_url`` is the source of truth:

        - ``file_path`` uploads the local file's bytes.
        - ``source_url`` asks the server to fetch the URL itself.

        Args:
            project_id (UUID): Owning project.
            file_path (str | None): Local path to a readable file to upload.
            source_url (str | None): URL the server should fetch.
            name (str | None): Display name. If omitted, the server derives one.
            group_id (UUID | None): Optional group membership.
            file_type (int | None): Integer value of a :class:`FileType`.
            metadata (dict[str, Any] | None): Arbitrary JSON metadata stored alongside the document.

        Returns:
            DocumentResponse: The newly created document response.

        Raises:
            ValidationError: If neither ``file_path`` nor ``source_url`` is
                supplied (and the server rejects the request).
        """
        form: dict[str, Any] = {"project_id": str(project_id)}
        if name is not None:
            form["name"] = name
        if group_id is not None:
            form["group_id"] = str(group_id)
        if file_type is not None:
            form["file_type"] = str(int(file_type))
        if source_url is not None:
            form["source_url"] = source_url
        if metadata is not None:
            form["metadata"] = json.dumps(metadata)

        files: dict[str, Any] = {}
        if file_path is not None:
            with open(file_path, "rb") as fh:
                file_bytes = fh.read()
            files["file"] = (file_path.rsplit("/", 1)[-1], file_bytes)

        if files:
            response = self._parent._request(
                "POST", "/api/documents/", data=form, files=files
            )
        else:
            multipart_files = {k: (None, v) for k, v in form.items()}
            response = self._parent._request(
                "POST", "/api/documents/", files=multipart_files
            )
        return DocumentResponse.model_validate(response.json())

    def update(
        self,
        document_id: UUID,
        *,
        name: str | None = None,
        group_id: UUID | None = None,
        storage_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DocumentResponse:
        """Patch a document's writable fields.

        Calls ``PUT /api/documents/{document_id}``. Only fields passed as
        non-``None`` are sent; the server preserves anything omitted.

        Args:
            document_id (UUID): Document to update.
            name (str | None): New display name.
            group_id (UUID | None): New group membership.
            storage_path (str | None): New storage path (rarely used; admin scenarios).
            metadata (dict[str, Any] | None): Replacement metadata dict.

        Returns:
            DocumentResponse: The updated document response.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if group_id is not None:
            body["group_id"] = str(group_id)
        if storage_path is not None:
            body["storage_path"] = storage_path
        if metadata is not None:
            # The update endpoint takes metadata as a JSON-encoded string.
            body["metadata"] = json.dumps(metadata)
        response = self._parent._request(
            "PUT", f"/api/documents/{document_id}", json_body=body
        )
        return DocumentResponse.model_validate(response.json())

    def delete(self, document_id: UUID) -> None:
        """Delete a document.

        Calls ``DELETE /api/documents/{document_id}``.

        Args:
            document_id (UUID): Document to delete.

        Raises:
            NotFoundError: If no document has that id.
        """
        self._parent._request("DELETE", f"/api/documents/{document_id}")

    def content(self, document_id: UUID) -> bytes:
        """Download the raw file bytes for a document.

        Calls ``GET /api/documents/{document_id}/content``. No parsing or
        text extraction is performed; callers get the exact bytes the server
        has on disk.

        Args:
            document_id (UUID): Document whose content to fetch.

        Returns:
            bytes: The raw file bytes.
        """
        response = self._parent._request("GET", f"/api/documents/{document_id}/content")
        return response.content

    def list_by_group(
        self, group_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> DocumentListResponse:
        """List documents belonging to a group.

        Calls ``GET /api/documents/group/{group_id}``.

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

    def get_job(self, document_id: UUID) -> JobResponse:
        """Fetch the latest processing job for a document.

        Calls ``GET /api/documents/{document_id}/job``.

        Args:
            document_id (UUID): Document whose job to fetch.

        Returns:
            JobResponse: The document's most recent job.

        Raises:
            NotFoundError: If the document has no job.
        """
        response = self._parent._request("GET", f"/api/documents/{document_id}/job")
        return JobResponse.model_validate(response.json())
