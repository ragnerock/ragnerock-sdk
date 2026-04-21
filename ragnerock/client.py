"""Low-level HTTP client: one method per Ragnerock API endpoint."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict

from ragnerock.errors import raise_for_status


class _ApiModel(BaseModel):
    """Base pydantic model for Ragnerock API response payloads.

    Allows extra fields so the SDK stays forward-compatible with additive
    server-side schema changes.
    """

    model_config = ConfigDict(extra="allow")


class AuthTokenResponse(_ApiModel):
    """Response payload for the login endpoint, carrying a bearer token."""

    access_token: str
    token_type: str = "bearer"


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


class ChunkResponse(_ApiModel):
    """Response payload representing a single chunk."""

    id: UUID
    document_id: UUID


class ChunkListResponse(_ApiModel):
    """Paginated list response for chunks."""

    chunks: list[ChunkResponse]
    total: int
    skip: int
    limit: int


class PageResponse(_ApiModel):
    """Response payload representing a single extracted document page."""

    id: UUID
    document_id: UUID
    page_number: int


class PageListResponse(_ApiModel):
    """Paginated list response for pages."""

    pages: list[PageResponse]
    total: int
    skip: int
    limit: int


class AnnotationResponse(_ApiModel):
    """Response payload representing a single annotation."""

    root_id: UUID
    operator_id: UUID


class AnnotationListResponse(_ApiModel):
    """Paginated list response for annotations."""

    annotations: list[AnnotationResponse]
    total: int
    skip: int
    limit: int


class OperatorResponse(_ApiModel):
    """Response payload representing a single operator."""

    id: UUID
    project_id: UUID | None = None
    name: str


class OperatorListResponse(_ApiModel):
    """Paginated list response for operators."""

    operators: list[OperatorResponse]
    total: int
    skip: int
    limit: int


class WorkflowResponse(_ApiModel):
    """Response payload representing a single workflow."""

    id: UUID
    project_id: UUID | None = None
    name: str


class WorkflowListResponse(_ApiModel):
    """Paginated list response for workflows."""

    workflows: list[WorkflowResponse]
    total: int
    skip: int
    limit: int


class WorkflowNodeResponse(_ApiModel):
    """Response payload representing a single workflow node."""

    id: UUID
    workflow_id: UUID
    operator_id: UUID


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


class QueryResultResponse(_ApiModel):
    """Response payload for an annotation SQL query.

    Carries the result columns, row data, row count, and optional
    server-reported execution time.
    """

    columns: list[str]
    data: list[dict[str, Any]]
    row_count: int
    query_time_ms: int | None = None


def _drop_none(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of ``data`` with ``None`` values removed.

    Used to build query-string and form payloads without pushing explicit
    ``null``s over the wire — the API distinguishes "field omitted" from
    "field set to null" on some endpoints.

    Args:
        data (dict[str, Any]): Dict to filter.

    Returns:
        dict[str, Any]: A new dict containing only the entries with non-``None`` values.
    """
    return {k: v for k, v in data.items() if v is not None}


def _stringify_uuids(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce any UUID values (including those inside lists) to strings.

    The Ragnerock API accepts string UUIDs; this avoids scattering ``str(...)``
    calls through every JSON body builder.

    Args:
        data (dict[str, Any]): Dict whose values may contain UUIDs or lists of UUIDs.

    Returns:
        dict[str, Any]: A new dict with UUIDs serialized to strings. Non-UUID values, and
        non-UUID entries inside lists, are passed through unchanged.
    """
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, UUID):
            out[k] = str(v)
        elif isinstance(v, list):
            out[k] = [str(x) if isinstance(x, UUID) else x for x in v]
        else:
            out[k] = v
    return out


class RagnerockClient:
    """Low-level HTTP client for the Ragnerock API.

    Args:
        host (str): Base URL of the API (e.g. ``https://api.ragnerock.com``).
        auth_token (str | None): Optional pre-existing bearer token. If
            ``None``, the caller must log in via ``client.auth.login(...)``
            before calling protected endpoints.
    """

    def __init__(self, *, host: str, auth_token: str | None = None) -> None:
        """Build a client bound to ``host``.

        Args:
            host (str): Base URL of the API. A trailing slash is trimmed.
            auth_token (str | None): Optional pre-existing bearer token. When provided,
                it's set as the ``Authorization`` header immediately;
                otherwise the caller must call ``client.auth.login(...)``
                before any protected endpoint.
        """
        self._host = host.rstrip("/")
        self._auth_token = auth_token
        self._client = httpx.Client(base_url=self._host, timeout=30.0)
        if auth_token is not None:
            self._client.headers["Authorization"] = f"Bearer {auth_token}"

    @property
    def auth_token(self) -> str | None:
        """The bearer token currently attached to outgoing requests.

        Returns:
            str | None: The token, or ``None`` if the client is not
            authenticated.
        """
        return self._auth_token

    @auth_token.setter
    def auth_token(self, value: str | None) -> None:
        """Swap the bearer token and update the default Authorization header.

        Passing ``None`` clears the header, putting the client back in an
        unauthenticated state.

        Args:
            value (str | None): The new bearer token, or ``None`` to clear.
        """
        self._auth_token = value
        if value is None:
            self._client.headers.pop("Authorization", None)
        else:
            self._client.headers["Authorization"] = f"Bearer {value}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Issue an HTTP request and raise SDK errors on non-2xx responses.

        Centralizes ``None``-filtering for query strings and form bodies, and
        converts any 4xx/5xx into the matching
        :class:`~ragnerock.errors.RagnerockError` subclass via
        :func:`~ragnerock.errors.raise_for_status`.

        Args:
            method (str): HTTP verb (``GET``, ``POST``, ``PUT``, ``DELETE``).
            path (str): Path relative to the client's base URL.
            params (dict[str, Any] | None): Query-string parameters. ``None``
                values are dropped.
            json_body (Any): Request body to serialize as JSON.
            data (dict[str, Any] | None): Form-urlencoded or multipart body
                fields. ``None`` values are dropped.
            files (dict[str, Any] | None): Multipart file parts, passed
                straight through to httpx.

        Returns:
            httpx.Response: The underlying :class:`httpx.Response` for 2xx/3xx
            replies.

        Raises:
            RagnerockError: Or a subclass, for any response with status >= 400.
        """
        kwargs: dict[str, Any] = {}
        if params is not None:
            kwargs["params"] = _drop_none(params)
        if json_body is not None:
            kwargs["json"] = json_body
        if data is not None:
            kwargs["data"] = _drop_none(data)
        if files is not None:
            kwargs["files"] = files
        response = self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise_for_status(response.status_code, response.text)
        return response

    def close(self) -> None:
        """Close the underlying HTTP connection pool.

        Safe to call multiple times. Using the client as a context manager is
        usually preferable.
        """
        self._client.close()

    def __enter__(self) -> RagnerockClient:
        """Return ``self`` so the client can be used as a context manager."""
        return self

    def __exit__(self, *_: Any) -> None:
        """Close the underlying HTTP connection pool on context exit."""
        self.close()

    @property
    def auth(self) -> _AuthSection:
        """Endpoints for authentication (``/api/auth/...``)."""
        return _AuthSection(self)

    @property
    def projects(self) -> _ProjectsSection:
        """Endpoints for project lookup (``/api/projects/...``)."""
        return _ProjectsSection(self)

    @property
    def documents(self) -> _DocumentsSection:
        """Endpoints for document CRUD and content download."""
        return _DocumentsSection(self)

    @property
    def groups(self) -> _GroupsSection:
        """Endpoints for document-group CRUD scoped by project."""
        return _GroupsSection(self)

    @property
    def chunks(self) -> _ChunksSection:
        """Endpoints for chunk CRUD."""
        return _ChunksSection(self)

    @property
    def pages(self) -> _PagesSection:
        """Read-only endpoints for extracted document pages."""
        return _PagesSection(self)

    @property
    def annotations(self) -> _AnnotationsSection:
        """Endpoints for annotation CRUD and scoped listing."""
        return _AnnotationsSection(self)

    @property
    def operators(self) -> _OperatorsSection:
        """Endpoints for operator CRUD."""
        return _OperatorsSection(self)

    @property
    def workflows(self) -> _WorkflowsSection:
        """Endpoints for workflow CRUD and node management."""
        return _WorkflowsSection(self)

    @property
    def jobs(self) -> _JobsSection:
        """Endpoints for job creation, inspection, and lifecycle actions."""
        return _JobsSection(self)

    @property
    def queries(self) -> _QueriesSection:
        """Endpoints for executing annotation SQL queries."""
        return _QueriesSection(self)


class _Section:
    """Base class for endpoint sections. Holds a reference to the parent client."""

    def __init__(self, parent: RagnerockClient) -> None:
        """Store a back-reference to the owning client.

        Args:
            parent (RagnerockClient): The client whose HTTP session and auth token this section
                will use.
        """
        self._parent = parent


class _AuthSection(_Section):
    """Authentication endpoints."""

    def login(self, *, email: str, password: str) -> AuthTokenResponse:
        """Exchange email/password for a bearer token and attach it.

        Calls ``POST /api/auth/login`` with a form-urlencoded body. On
        success, the returned access token is stored on the parent client, so
        subsequent requests authenticate automatically.

        Args:
            email (str): Account email.
            password (str): Account password.

        Returns:
            AuthTokenResponse: The token response. The token is also set on the client.

        Raises:
            AuthenticationError: If the credentials are rejected.
        """
        response = self._parent._client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code >= 400:
            raise_for_status(response.status_code, response.text)
        model = AuthTokenResponse.model_validate(response.json())
        self._parent.auth_token = model.access_token
        return model


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
            body["metadata"] = metadata
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


class _ChunksSection(_Section):
    """Chunk CRUD endpoints."""

    def list(
        self,
        *,
        document_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> ChunkListResponse:
        """List chunks, optionally scoped to one or more documents.

        Calls ``GET /api/chunks/``.

        Args:
            document_ids (str | None): Comma-separated string of document UUIDs, or
                ``None`` to list across every accessible document.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            ChunkListResponse: A page of chunks.
        """
        response = self._parent._request(
            "GET",
            "/api/chunks/",
            params={"document_ids": document_ids, "skip": skip, "limit": limit},
        )
        return ChunkListResponse.model_validate(response.json())

    def get(self, chunk_id: UUID) -> ChunkResponse:
        """Fetch a single chunk by id.

        Calls ``GET /api/chunks/{chunk_id}``.

        Args:
            chunk_id (UUID): UUID of the chunk.

        Returns:
            ChunkResponse: The chunk response.

        Raises:
            NotFoundError: If no chunk has that id.
        """
        response = self._parent._request("GET", f"/api/chunks/{chunk_id}")
        return ChunkResponse.model_validate(response.json())

    def create(
        self,
        *,
        document_id: UUID,
        start_index: int,
        end_index: int,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChunkResponse:
        """Create a chunk on a document.

        Calls ``POST /api/chunks/``. ``end_index`` is exclusive, matching
        Python slice semantics.

        Args:
            document_id (UUID): Owning document.
            start_index (int): Character offset where the chunk begins.
            end_index (int): Character offset where the chunk ends (exclusive).
            content (str | None): Text content of the chunk. If omitted, the server
                extracts it from the document at the given offsets.
            metadata (dict[str, Any] | None): Arbitrary JSON metadata.

        Returns:
            ChunkResponse: The newly created chunk response.
        """
        body: dict[str, Any] = {
            "document_id": str(document_id),
            "start_index": start_index,
            "end_index": end_index,
        }
        if content is not None:
            body["content"] = content
        if metadata is not None:
            body["metadata"] = metadata
        response = self._parent._request("POST", "/api/chunks/", json_body=body)
        return ChunkResponse.model_validate(response.json())

    def delete(self, chunk_id: UUID) -> None:
        """Delete a chunk.

        Calls ``DELETE /api/chunks/{chunk_id}``.

        Args:
            chunk_id (UUID): Chunk to delete.
        """
        self._parent._request("DELETE", f"/api/chunks/{chunk_id}")


class _PagesSection(_Section):
    """Read-only page endpoints. Pages are produced by document parsing."""

    def list(
        self, document_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> PageListResponse:
        """List the pages of a document.

        Calls ``GET /api/pages/document/{document_id}``. Pages are ordered by
        ``page_number`` in the response.

        Args:
            document_id (UUID): Document whose pages to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            PageListResponse: A page of pages.
        """
        response = self._parent._request(
            "GET",
            f"/api/pages/document/{document_id}",
            params={"skip": skip, "limit": limit},
        )
        return PageListResponse.model_validate(response.json())

    def get(self, page_id: UUID) -> PageResponse:
        """Fetch a single page by id.

        Calls ``GET /api/pages/{page_id}``.

        Args:
            page_id (UUID): UUID of the page.

        Returns:
            PageResponse: The page response.

        Raises:
            NotFoundError: If no page has that id.
        """
        response = self._parent._request("GET", f"/api/pages/{page_id}")
        return PageResponse.model_validate(response.json())


class _AnnotationsSection(_Section):
    """Annotation CRUD and scoped-list endpoints."""

    def get(self, root_id: UUID) -> AnnotationResponse:
        """Fetch a single annotation by its ``root_id``.

        Calls ``GET /api/annotations/{root_id}``.

        Args:
            root_id (UUID): Server-assigned annotation identity.

        Returns:
            AnnotationResponse: The annotation response.

        Raises:
            NotFoundError: If no annotation has that id.
        """
        response = self._parent._request("GET", f"/api/annotations/{root_id}")
        return AnnotationResponse.model_validate(response.json())

    def create(
        self,
        *,
        operator_id: UUID,
        data: dict[str, Any],
        document_id: UUID | None = None,
        chunk_id: UUID | None = None,
        page_id: UUID | None = None,
        confidence_score: float | None = None,
    ) -> AnnotationResponse:
        """Create an annotation, attaching it to exactly one target.

        Calls ``POST /api/annotations/``. Callers must supply exactly one of
        ``document_id``, ``chunk_id``, or ``page_id`` — typically the one
        that matches the operator's ``chunk_type``.

        Args:
            operator_id (UUID): Operator the annotation belongs to. Its JSON schema
                validates ``data`` server-side.
            data (dict[str, Any]): Annotation payload matching the operator's schema.
            document_id (UUID | None): Document this annotation is about.
            chunk_id (UUID | None): Chunk this annotation is about.
            page_id (UUID | None): Page this annotation is about.
            confidence_score (float | None): Optional confidence in ``[0.0, 1.0]``.

        Returns:
            AnnotationResponse: The newly created annotation response.
        """
        body: dict[str, Any] = {
            "operator_id": str(operator_id),
            "data": data,
        }
        if document_id is not None:
            body["document_id"] = str(document_id)
        if chunk_id is not None:
            body["chunk_id"] = str(chunk_id)
        if page_id is not None:
            body["page_id"] = str(page_id)
        if confidence_score is not None:
            body["confidence_score"] = confidence_score
        response = self._parent._request("POST", "/api/annotations/", json_body=body)
        return AnnotationResponse.model_validate(response.json())

    def update(
        self,
        root_id: UUID,
        *,
        data: dict[str, Any],
        confidence_score: float | None = None,
    ) -> AnnotationResponse:
        """Replace an annotation's ``data`` payload.

        Calls ``PUT /api/annotations/{root_id}``. The JSON body is the new
        ``data`` payload; ``confidence_score`` rides as a query parameter
        when provided. Attachment target (document/chunk/page) and operator
        are not editable — create a fresh annotation if those need to change.

        Args:
            root_id (UUID): Annotation to update.
            data (dict[str, Any]): Replacement payload. Must still validate against the
                operator's schema.
            confidence_score (float | None): Optional replacement confidence.

        Returns:
            AnnotationResponse: The updated annotation response.
        """
        params: dict[str, Any] = {}
        if confidence_score is not None:
            params["confidence_score"] = confidence_score
        response = self._parent._request(
            "PUT",
            f"/api/annotations/{root_id}",
            params=params or None,
            json_body=data,
        )
        return AnnotationResponse.model_validate(response.json())

    def delete(self, root_id: UUID) -> None:
        """Delete an annotation.

        Calls ``DELETE /api/annotations/{root_id}``.

        Args:
            root_id (UUID): Annotation to delete.
        """
        self._parent._request("DELETE", f"/api/annotations/{root_id}")

    def list_by_document(
        self,
        document_id: UUID,
        *,
        operator_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> AnnotationListResponse:
        """List annotations attached to a document.

        Calls ``GET /api/annotations/document/{document_id}``. Covers
        document-level annotations plus annotations on the document's
        children (chunks, pages).

        Args:
            document_id (UUID): Document to list.
            operator_name (str | None): Restrict to annotations produced by an operator
                with this exact name.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/document/{document_id}",
            params={
                "operator_name": operator_name,
                "skip": skip,
                "limit": limit,
            },
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_by_chunk(
        self,
        chunk_id: UUID,
        *,
        operator_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> AnnotationListResponse:
        """List annotations attached to a chunk.

        Calls ``GET /api/annotations/chunk/{chunk_id}``.

        Args:
            chunk_id (UUID): Chunk to list.
            operator_name (str | None): Restrict to annotations produced by an operator
                with this exact name.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/chunk/{chunk_id}",
            params={
                "operator_name": operator_name,
                "skip": skip,
                "limit": limit,
            },
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_by_operator(
        self, operator_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> AnnotationListResponse:
        """List every annotation produced by a given operator.

        Calls ``GET /api/annotations/operator/{operator_id}``. Results span
        all documents the operator has run against. For operator metadata
        joined into each row, use :meth:`list_hydrated_by_operator` instead.

        Args:
            operator_id (UUID): Operator to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/operator/{operator_id}",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_hydrated_by_operator(
        self, operator_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> AnnotationListResponse:
        """Like :meth:`list_by_operator`, but with operator metadata joined in.

        Calls ``GET /api/annotations/operator/{operator_id}/hydrated``. Each
        row carries ``operator_name`` and any other joined fields the server
        attaches. Costs more server-side than the plain list.

        Args:
            operator_id (UUID): Operator to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of hydrated annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/operator/{operator_id}/hydrated",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_by_document_and_operator_id(
        self,
        document_id: UUID,
        operator_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> AnnotationListResponse:
        """List annotations from a specific operator on a specific document.

        Calls
        ``GET /api/annotations/document/{document_id}/operator/{operator_id}``.
        The narrow-scope form of :meth:`list_by_document` when you already
        have the operator's id.

        Args:
            document_id (UUID): Document to scope to.
            operator_id (UUID): Operator to scope to.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/document/{document_id}/operator/{operator_id}",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_by_document_and_operator_name(
        self,
        document_id: UUID,
        operator_name: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> AnnotationListResponse:
        """Like :meth:`list_by_document_and_operator_id`, keyed by operator name.

        Calls
        ``GET /api/annotations/document/{document_id}/operator-name/{operator_name}``.
        Use this when you want to avoid a separate lookup to resolve the
        operator's id.

        Args:
            document_id (UUID): Document to scope to.
            operator_name (str): Exact operator name to scope to.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/document/{document_id}/operator-name/{operator_name}",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationListResponse.model_validate(response.json())


class _OperatorsSection(_Section):
    """Operator CRUD endpoints."""

    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> OperatorListResponse:
        """List operators, optionally scoped to one or more projects.

        Calls ``GET /api/operators/``.

        Args:
            project_ids (str | None): Comma-separated string of project UUIDs, or ``None``
                to list across every accessible project.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            OperatorListResponse: A page of operators.
        """
        response = self._parent._request(
            "GET",
            "/api/operators/",
            params={"project_ids": project_ids, "skip": skip, "limit": limit},
        )
        return OperatorListResponse.model_validate(response.json())

    def get(self, operator_id: UUID) -> OperatorResponse:
        """Fetch a single operator by id.

        Calls ``GET /api/operators/{operator_id}``.

        Args:
            operator_id (UUID): UUID of the operator.

        Returns:
            OperatorResponse: The operator response.

        Raises:
            NotFoundError: If no operator has that id.
        """
        response = self._parent._request("GET", f"/api/operators/{operator_id}")
        return OperatorResponse.model_validate(response.json())

    def create(
        self,
        *,
        project_id: UUID,
        name: str,
        jsonschema: dict[str, Any],
        generation_prompt: str,
        chunk_type: int,
        description: str | None = None,
        batch_size: int | None = None,
        multi_annotation: bool = False,
    ) -> OperatorResponse:
        """Create an operator.

        Calls ``POST /api/operators/``.

        Args:
            project_id (UUID): Owning project.
            name (str): Operator name. Becomes the queryable table name in
                annotation SQL; must be unique within the project.
            jsonschema (dict[str, Any]): JSON Schema describing each annotation's shape.
            generation_prompt (str): LLM prompt used to produce annotations.
            chunk_type (int): Integer value of a :class:`ChunkType` — the scope
                at which the operator runs.
            description (str | None): Optional human-readable description.
            batch_size (int | None): Batch size for annotation generation.
            multi_annotation (bool): Whether the operator may emit more than one
                annotation per input chunk.

        Returns:
            OperatorResponse: The newly created operator response.
        """
        body: dict[str, Any] = {
            "project_id": str(project_id),
            "name": name,
            "jsonschema": jsonschema,
            "generation_prompt": generation_prompt,
            "chunk_type": chunk_type,
            "multi_annotation": multi_annotation,
        }
        if description is not None:
            body["description"] = description
        if batch_size is not None:
            body["batch_size"] = batch_size
        response = self._parent._request("POST", "/api/operators/", json_body=body)
        return OperatorResponse.model_validate(response.json())

    def update(
        self,
        operator_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        jsonschema: dict[str, Any] | None = None,
        generation_prompt: str | None = None,
        chunk_type: int | None = None,
        batch_size: int | None = None,
        multi_annotation: bool | None = None,
    ) -> OperatorResponse:
        """Patch an operator's writable fields.

        Calls ``PUT /api/operators/{operator_id}``. Only fields passed as
        non-``None`` are sent. Changing ``jsonschema`` or ``chunk_type`` can
        invalidate existing annotations — the server enforces its own
        compatibility rules.

        Args:
            operator_id (UUID): Operator to update.
            name (str | None): New name.
            description (str | None): New description.
            jsonschema (dict[str, Any] | None): New JSON Schema.
            generation_prompt (str | None): New LLM prompt.
            chunk_type (int | None): New integer :class:`ChunkType` value.
            batch_size (int | None): New batch size.
            multi_annotation (bool | None): Whether the operator now emits multiple
                annotations per input.

        Returns:
            OperatorResponse: The updated operator response.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if jsonschema is not None:
            body["jsonschema"] = jsonschema
        if generation_prompt is not None:
            body["generation_prompt"] = generation_prompt
        if chunk_type is not None:
            body["chunk_type"] = chunk_type
        if batch_size is not None:
            body["batch_size"] = batch_size
        if multi_annotation is not None:
            body["multi_annotation"] = multi_annotation
        response = self._parent._request(
            "PUT", f"/api/operators/{operator_id}", json_body=body
        )
        return OperatorResponse.model_validate(response.json())

    def delete(self, operator_id: UUID) -> None:
        """Delete an operator.

        Calls ``DELETE /api/operators/{operator_id}``. Workflows and
        annotations referencing the operator may break — callers should
        clean those up first (or be ready for the server's reference
        semantics, which may cascade or reject).

        Args:
            operator_id (UUID): Operator to delete.
        """
        self._parent._request("DELETE", f"/api/operators/{operator_id}")


class _WorkflowsSection(_Section):
    """Workflow CRUD endpoints plus node management."""

    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> WorkflowListResponse:
        """List workflows, optionally scoped to one or more projects.

        Calls ``GET /api/workflows/``.

        Args:
            project_ids (str | None): Comma-separated string of project UUIDs, or ``None``
                to list across every accessible project.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            WorkflowListResponse: A page of workflows.
        """
        response = self._parent._request(
            "GET",
            "/api/workflows/",
            params={"project_ids": project_ids, "skip": skip, "limit": limit},
        )
        return WorkflowListResponse.model_validate(response.json())

    def get(self, workflow_id: UUID) -> WorkflowResponse:
        """Fetch a single workflow by id.

        Calls ``GET /api/workflows/{workflow_id}``.

        Args:
            workflow_id (UUID): UUID of the workflow.

        Returns:
            WorkflowResponse: The workflow response.

        Raises:
            NotFoundError: If no workflow has that id.
        """
        response = self._parent._request("GET", f"/api/workflows/{workflow_id}")
        return WorkflowResponse.model_validate(response.json())

    def create(
        self,
        *,
        project_id: UUID,
        name: str,
        description: str | None = None,
        is_active: bool = True,
        auto_run_on_upload: bool = True,
    ) -> WorkflowResponse:
        """Create a workflow with no nodes.

        Calls ``POST /api/workflows/``. Add operator nodes afterward with
        :meth:`add_node`.

        Args:
            project_id (UUID): Owning project.
            name (str): Workflow name.
            description (str | None): Optional description.
            is_active (bool): Whether the workflow is enabled and eligible to run.
            auto_run_on_upload (bool): Whether the server should run this workflow
                automatically when a document is uploaded to the project.

        Returns:
            WorkflowResponse: The newly created workflow response.
        """
        body: dict[str, Any] = {
            "project_id": str(project_id),
            "name": name,
            "is_active": is_active,
            "auto_run_on_upload": auto_run_on_upload,
        }
        if description is not None:
            body["description"] = description
        response = self._parent._request("POST", "/api/workflows/", json_body=body)
        return WorkflowResponse.model_validate(response.json())

    def update(
        self,
        workflow_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
        auto_run_on_upload: bool | None = None,
    ) -> WorkflowResponse:
        """Patch a workflow's writable fields.

        Calls ``PUT /api/workflows/{workflow_id}``. Only fields passed as
        non-``None`` are sent.

        Args:
            workflow_id (UUID): Workflow to update.
            name (str | None): New name.
            description (str | None): New description.
            is_active (bool | None): New enabled flag.
            auto_run_on_upload (bool | None): New auto-run flag.

        Returns:
            WorkflowResponse: The updated workflow response.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if is_active is not None:
            body["is_active"] = is_active
        if auto_run_on_upload is not None:
            body["auto_run_on_upload"] = auto_run_on_upload
        response = self._parent._request(
            "PUT", f"/api/workflows/{workflow_id}", json_body=body
        )
        return WorkflowResponse.model_validate(response.json())

    def delete(self, workflow_id: UUID) -> None:
        """Delete a workflow.

        Calls ``DELETE /api/workflows/{workflow_id}``. Running jobs belonging
        to the workflow are not cancelled implicitly — cancel them first if
        needed.

        Args:
            workflow_id (UUID): Workflow to delete.
        """
        self._parent._request("DELETE", f"/api/workflows/{workflow_id}")

    def add_node(
        self,
        workflow_id: UUID,
        *,
        operator_id: UUID,
        condition: dict[str, Any] | None = None,
        persist: bool = True,
        on_error: str = "FAIL_JOB",
        max_retries: int = 0,
    ) -> WorkflowNodeResponse:
        """Append an operator node to a workflow.

        Calls ``PUT /api/workflows/{workflow_id}/nodes/``. The server slots
        the new node into the workflow's execution graph.

        Args:
            workflow_id (UUID): Workflow to add to.
            operator_id (UUID): Operator the node executes.
            condition (dict[str, Any] | None): Optional predicate restricting when the node fires
                (serialized per the server's condition grammar).
            persist (bool): Whether annotations produced here are persisted.
            on_error (str): Error-handling policy. Expected values include
                ``"FAIL_JOB"`` (default) and ``"SKIP_NODE"``; the server is
                the source of truth for the full set.
            max_retries (int): Retry count on transient failure.

        Returns:
            WorkflowNodeResponse: The newly created node response.
        """
        body: dict[str, Any] = {
            "operator_id": str(operator_id),
            "persist": persist,
            "on_error": on_error,
            "max_retries": max_retries,
        }
        if condition is not None:
            body["condition"] = condition
        response = self._parent._request(
            "PUT",
            f"/api/workflows/{workflow_id}/nodes/",
            json_body=body,
        )
        return WorkflowNodeResponse.model_validate(response.json())

    def update_node(
        self,
        workflow_id: UUID,
        node_id: UUID,
        **fields: Any,
    ) -> WorkflowNodeResponse:
        """Patch a workflow node's fields.

        Calls ``PUT /api/workflows/{workflow_id}/nodes/{node_id}``. Kwargs
        are forwarded verbatim to the server after stringifying UUIDs and
        dropping ``None`` values, so this is intentionally flexible — callers
        should pass the exact field names the API expects (``operator_id``,
        ``condition``, ``persist``, ``on_error``, ``max_retries``,
        ``in_nodes``, ``out_nodes``).

        Args:
            workflow_id (UUID): Owning workflow.
            node_id (UUID): Node to update.
            **fields: Fields to patch. ``None`` values are dropped; ``UUID``
                values (including those inside lists) are stringified.

        Returns:
            WorkflowNodeResponse: The updated node response.
        """
        body = _stringify_uuids({k: v for k, v in fields.items() if v is not None})
        response = self._parent._request(
            "PUT",
            f"/api/workflows/{workflow_id}/nodes/{node_id}",
            json_body=body,
        )
        return WorkflowNodeResponse.model_validate(response.json())

    def delete_node(self, workflow_id: UUID, node_id: UUID) -> None:
        """Delete a node from a workflow.

        Calls ``DELETE /api/workflows/{workflow_id}/nodes/{node_id}``. The
        server rewires the surrounding graph; callers don't need to touch
        ``in_nodes``/``out_nodes`` manually.

        Args:
            workflow_id (UUID): Owning workflow.
            node_id (UUID): Node to delete.
        """
        self._parent._request(
            "DELETE",
            f"/api/workflows/{workflow_id}/nodes/{node_id}",
        )


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


class _QueriesSection(_Section):
    """Annotation SQL query endpoints."""

    def execute(
        self,
        *,
        project_id: UUID,
        query: str,
        format: str = "dataframe",
        limit: int = 1000,
        timeout: int | None = None,
    ) -> QueryResultResponse:
        """Run a SQL query against a project's annotations.

        Calls ``POST /api/query/projects/{project_id}/query``.

        Args:
            project_id (UUID): Project whose annotations to query.
            query (str): SQL text. Tables are operator names; columns come from
                each operator's JSON schema.
            format (str): Server-side result format. ``"dataframe"`` (the default)
                returns rows and columns suitable for tabular conversion.
            limit (int): Maximum rows to return.
            timeout (int | None): Server-side execution timeout in seconds. ``None`` uses
                the server default.

        Returns:
            QueryResultResponse: A :class:`QueryResultResponse` carrying columns, rows, the row
            count, and server-reported execution time.

        Raises:
            QueryError: If the query fails parsing, validation, or
                execution.
        """
        body: dict[str, Any] = {
            "query": query,
            "format": format,
            "limit": limit,
        }
        if timeout is not None:
            body["timeout"] = timeout
        response = self._parent._request(
            "POST",
            f"/api/query/projects/{project_id}/query",
            json_body=body,
        )
        return QueryResultResponse.model_validate(response.json())
