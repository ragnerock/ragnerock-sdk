"""Document endpoints (``/api/documents/...``)."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _jsonable, _Section
from ragnerock.client.jobs import JobResponse
from ragnerock.timestamps import UtcDatetime


class DocumentSortField(StrEnum):
    """The key a document listing is sorted by. Ties are always broken by id."""

    ID = "id"
    """Document id: stable across pages. The default."""

    NAME = "name"
    """Document name, ignoring case."""

    CREATED_AT = "created_at"
    """Upload time."""

    FILESIZE = "filesize"
    """Size in bytes."""


class SortOrder(StrEnum):
    """Direction of a sorted listing."""

    ASC = "asc"
    DESC = "desc"


class DocumentFilterField(StrEnum):
    """A document attribute a listing filter can test."""

    NAME = "name"
    """File name, compared as text."""

    FILESIZE = "filesize"
    """Size in bytes, compared as a number."""

    FILE_TYPE = "file_type"
    """File type, compared by equality only."""

    CREATED_AT = "created_at"
    """Creation date, compared by whole ``YYYY-MM-DD`` days."""


class FilterOperator(StrEnum):
    """How a listing filter compares a field with its value."""

    EQ = "eq"
    NE = "ne"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"


class DocumentResponse(_ApiModel):
    """Response payload representing a single document."""

    id: UUID
    project_id: UUID
    name: str
    group_id: UUID | None = None
    file_type: int | None = None
    status: str | None = None
    filesize: int | None = None
    storage_path: str | None = None
    source_url: str | None = None
    is_sample: bool = False
    created_by_id: UUID | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None


class DocumentListResponse(_ApiModel):
    """Paginated list response for documents."""

    documents: list[DocumentResponse]
    total: int
    skip: int
    limit: int


class DocumentMetadataResponse(_ApiModel):
    """One passthrough metadata entry stored on a document."""

    key: str
    val: str | None = None
    dtype: str | None = None


class DocumentMetadataListResponse(_ApiModel):
    """A document's passthrough metadata entries."""

    metadata: list[DocumentMetadataResponse] = []


class IngestDocumentChangeResponse(_ApiModel):
    """The ingest run that last changed a document, and what it changed."""

    document_id: UUID
    config_id: UUID | None = None
    config_name: str | None = None
    source_id: UUID | None = None
    run_id: UUID | None = None
    changed_at: UtcDatetime = None
    detail: dict[str, Any] | None = None


def _document_listing_params(
    skip: int,
    limit: int,
    *,
    is_sample: bool | None,
    name: str | None,
    filters: list[Any] | None,
    time_zone: str | None,
    statuses: list[str] | None,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any]:
    """Build the query parameters every document listing shares.

    Args:
        skip (int): Number of matching documents to skip.
        limit (int): Page size.
        is_sample (bool | None): Only samples or only corpus documents.
        name (str | None): Only names containing this text, ignoring case.
        filters (list[Any] | None): Filter conditions, sent as a JSON array.
        time_zone (str | None): IANA time zone for date filters.
        statuses (list[str] | None): Only documents in one of these states,
            sent as a repeated parameter.
        sort_by (str): The sort key.
        sort_order (str): The sort direction.

    Returns:
        dict[str, Any]: The parameters, leaving out the unset filters.
    """
    params: dict[str, Any] = {
        "skip": skip,
        "limit": limit,
        "sort_by": _jsonable(sort_by),
        "sort_order": _jsonable(sort_order),
    }
    if is_sample is not None:
        params["is_sample"] = str(is_sample).lower()
    if name is not None:
        params["name"] = name
    if filters:
        params["filters"] = json.dumps(_jsonable(list(filters)))
    if time_zone is not None:
        params["timezone"] = time_zone
    if statuses:
        params["statuses"] = [_jsonable(s) for s in statuses]
    return params


class _DocumentsSection(_Section):
    """Document CRUD endpoints."""

    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
        group_id: UUID | None = None,
        ungrouped: bool = False,
        is_sample: bool | None = None,
        name: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        time_zone: str | None = None,
        statuses: list[str] | None = None,
        sort_by: str = DocumentSortField.ID,
        sort_order: str = SortOrder.ASC,
    ) -> DocumentListResponse:
        """List documents, optionally scoped to one or more projects.

        Calls ``GET /api/documents/``.

        Args:
            project_ids (str | None): Comma-separated string of project UUIDs, or ``None``
                to list across every accessible project.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page (at most 1000).
            group_id (UUID | None): Only documents in this group.
            ungrouped (bool): Only documents in no group. Cannot be combined
                with ``group_id``.
            is_sample (bool | None): ``True`` for sample documents only,
                ``False`` for corpus documents only, ``None`` for both.
            name (str | None): Only names containing this text, ignoring case.
            filters (list[dict[str, Any]] | None): Conditions that must all
                hold. Each is ``{"field", "operator", "value", "value2"}`` with
                a :class:`DocumentFilterField` field and a
                :class:`FilterOperator`; ``value2`` is the upper bound for
                ``"between"``.
            time_zone (str | None): IANA time zone the days in date filters are
                taken in; ``None`` means UTC.
            statuses (list[str] | None): Only documents in one of these
                :class:`~ragnerock.resources.document.DocumentStatus` states.
            sort_by (str): A :class:`DocumentSortField` value.
            sort_order (str): A :class:`SortOrder` value.

        Returns:
            DocumentListResponse: A page of documents with ``total`` set to the full result size.
        """
        params = _document_listing_params(
            skip,
            limit,
            is_sample=is_sample,
            name=name,
            filters=filters,
            time_zone=time_zone,
            statuses=statuses,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        params["project_ids"] = project_ids
        if group_id is not None:
            params["group_id"] = str(group_id)
        if ungrouped:
            params["ungrouped"] = "true"
        response = self._parent._request("GET", "/api/documents/", params=params)
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
        self,
        group_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100,
        is_sample: bool | None = None,
        name: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        time_zone: str | None = None,
        statuses: list[str] | None = None,
        sort_by: str = DocumentSortField.ID,
        sort_order: str = SortOrder.ASC,
    ) -> DocumentListResponse:
        """List documents belonging to a group.

        Calls ``GET /api/documents/group/{group_id}``. Takes the same filters
        as :meth:`list`.

        Args:
            group_id (UUID): Group to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page (at most 1000).
            is_sample (bool | None): ``True`` for sample documents only,
                ``False`` for corpus documents only, ``None`` for both.
            name (str | None): Only names containing this text, ignoring case.
            filters (list[dict[str, Any]] | None): Conditions that must all
                hold; see :meth:`list`.
            time_zone (str | None): IANA time zone the days in date filters are
                taken in; ``None`` means UTC.
            statuses (list[str] | None): Only documents in one of these
                :class:`~ragnerock.resources.document.DocumentStatus` states.
            sort_by (str): A :class:`DocumentSortField` value.
            sort_order (str): A :class:`SortOrder` value.

        Returns:
            DocumentListResponse: A page of documents in the group.
        """
        params = _document_listing_params(
            skip,
            limit,
            is_sample=is_sample,
            name=name,
            filters=filters,
            time_zone=time_zone,
            statuses=statuses,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        response = self._parent._request(
            "GET", f"/api/documents/group/{group_id}", params=params
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

    def get_metadata(self, document_id: UUID) -> DocumentMetadataListResponse:
        """Fetch a document's passthrough metadata entries.

        Calls ``GET /api/documents/{document_id}/metadata``.

        Args:
            document_id (UUID): Document whose metadata to fetch.

        Returns:
            DocumentMetadataListResponse: The metadata entries.

        Raises:
            NotFoundError: If no document has that id.
        """
        response = self._parent._request(
            "GET", f"/api/documents/{document_id}/metadata"
        )
        return DocumentMetadataListResponse.model_validate(response.json())

    def delete_metadata_key(self, document_id: UUID, key: str) -> None:
        """Delete one metadata key from a document.

        Calls ``DELETE /api/documents/{document_id}/metadata/{key}``.

        Args:
            document_id (UUID): Document to modify.
            key (str): Metadata key to remove.

        Raises:
            NotFoundError: If the document or key does not exist.
        """
        self._parent._request("DELETE", f"/api/documents/{document_id}/metadata/{key}")

    def delete_metadata(self, document_id: UUID) -> None:
        """Delete all of a document's metadata.

        Calls ``DELETE /api/documents/{document_id}/metadata``.

        Args:
            document_id (UUID): Document to modify.

        Raises:
            NotFoundError: If no document has that id.
        """
        self._parent._request("DELETE", f"/api/documents/{document_id}/metadata")

    def get_ingest_change(self, document_id: UUID) -> IngestDocumentChangeResponse:
        """Fetch what the last ingest run did to a document.

        Calls ``GET /api/documents/{document_id}/ingest-change``.

        Args:
            document_id (UUID): Document to look up.

        Returns:
            IngestDocumentChangeResponse: The run that last changed the
            document, what it changed, and the ingest config it belongs to.

        Raises:
            NotFoundError: If the document does not exist, is not readable,
                or was never written by an ingest run.
        """
        response = self._parent._request(
            "GET", f"/api/documents/{document_id}/ingest-change"
        )
        return IngestDocumentChangeResponse.model_validate(response.json())

    def get_ingest_changes(
        self, document_ids: list[UUID]
    ) -> dict[str, IngestDocumentChangeResponse]:
        """Fetch what the last ingest run did to each of several documents.

        Calls ``POST /api/documents/ingest-change/batch``. Documents the
        caller cannot read, and documents no ingest run ever wrote, are left
        out of the result rather than raising. An empty ``document_ids``
        returns ``{}`` without a request.

        Args:
            document_ids (list[UUID]): Documents to look up.

        Returns:
            dict[str, IngestDocumentChangeResponse]: The changes, keyed by
            document id.
        """
        if not document_ids:
            return {}
        response = self._parent._request(
            "POST",
            "/api/documents/ingest-change/batch",
            json_body={"document_ids": [str(d) for d in document_ids]},
        )
        return {
            key: IngestDocumentChangeResponse.model_validate(value)
            for key, value in response.json().items()
        }
