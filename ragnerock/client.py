"""Low-level HTTP client: one method per Ragnerock API endpoint."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict

from ragnerock.errors import raise_for_status


class _ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class AuthTokenResponse(_ApiModel):
    access_token: str
    token_type: str = "bearer"


class ProjectResponse(_ApiModel):
    id: UUID
    name: str


class ProjectListResponse(_ApiModel):
    projects: list[ProjectResponse]
    total: int
    skip: int
    limit: int


class DocumentResponse(_ApiModel):
    id: UUID
    project_id: UUID
    name: str


class DocumentListResponse(_ApiModel):
    documents: list[DocumentResponse]
    total: int
    skip: int
    limit: int


class DocumentGroupResponse(_ApiModel):
    id: UUID
    project_id: UUID | None = None
    name: str


class DocumentGroupListResponse(_ApiModel):
    groups: list[DocumentGroupResponse]
    total: int
    skip: int
    limit: int


class ChunkResponse(_ApiModel):
    id: UUID
    document_id: UUID


class ChunkListResponse(_ApiModel):
    chunks: list[ChunkResponse]
    total: int
    skip: int
    limit: int


class PageResponse(_ApiModel):
    id: UUID
    document_id: UUID
    page_number: int


class PageListResponse(_ApiModel):
    pages: list[PageResponse]
    total: int
    skip: int
    limit: int


class AnnotationResponse(_ApiModel):
    root_id: UUID
    operator_id: UUID


class AnnotationListResponse(_ApiModel):
    annotations: list[AnnotationResponse]
    total: int
    skip: int
    limit: int


class OperatorResponse(_ApiModel):
    id: UUID
    project_id: UUID | None = None
    name: str


class OperatorListResponse(_ApiModel):
    operators: list[OperatorResponse]
    total: int
    skip: int
    limit: int


class WorkflowResponse(_ApiModel):
    id: UUID
    project_id: UUID | None = None
    name: str


class WorkflowListResponse(_ApiModel):
    workflows: list[WorkflowResponse]
    total: int
    skip: int
    limit: int


class WorkflowNodeResponse(_ApiModel):
    id: UUID
    workflow_id: UUID
    operator_id: UUID


class JobResponse(_ApiModel):
    id: UUID
    status: int


class JobListResponse(_ApiModel):
    jobs: list[JobResponse]
    total: int
    skip: int
    limit: int


class JobActionResponse(_ApiModel):
    job_id: UUID
    status: str


class CreateManualJobsResponse(_ApiModel):
    job_ids: list[UUID]


class QueryResultResponse(_ApiModel):
    columns: list[str]
    data: list[dict[str, Any]]
    row_count: int
    query_time_ms: int | None = None


def _drop_none(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None}


def _stringify_uuids(data: dict[str, Any]) -> dict[str, Any]:
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
        host: Base URL of the API (e.g. ``https://api.ragnerock.com``).
        auth_token: Optional pre-existing bearer token. If ``None``, the caller
            must log in via ``client.auth.login(...)`` before calling protected
            endpoints.
    """

    def __init__(self, *, host: str, auth_token: str | None = None) -> None:
        self._host = host.rstrip("/")
        self._auth_token = auth_token
        self._client = httpx.Client(base_url=self._host, timeout=30.0)
        if auth_token is not None:
            self._client.headers["Authorization"] = f"Bearer {auth_token}"

    @property
    def auth_token(self) -> str | None:
        """Current bearer token, if authenticated."""
        return self._auth_token

    @auth_token.setter
    def auth_token(self, value: str | None) -> None:
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
        self._client.close()

    def __enter__(self) -> RagnerockClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @property
    def auth(self) -> _AuthSection:
        return _AuthSection(self)

    @property
    def projects(self) -> _ProjectsSection:
        return _ProjectsSection(self)

    @property
    def documents(self) -> _DocumentsSection:
        return _DocumentsSection(self)

    @property
    def groups(self) -> _GroupsSection:
        return _GroupsSection(self)

    @property
    def chunks(self) -> _ChunksSection:
        return _ChunksSection(self)

    @property
    def pages(self) -> _PagesSection:
        return _PagesSection(self)

    @property
    def annotations(self) -> _AnnotationsSection:
        return _AnnotationsSection(self)

    @property
    def operators(self) -> _OperatorsSection:
        return _OperatorsSection(self)

    @property
    def workflows(self) -> _WorkflowsSection:
        return _WorkflowsSection(self)

    @property
    def jobs(self) -> _JobsSection:
        return _JobsSection(self)

    @property
    def queries(self) -> _QueriesSection:
        return _QueriesSection(self)


class _Section:
    def __init__(self, parent: RagnerockClient) -> None:
        self._parent = parent


class _AuthSection(_Section):
    def login(self, *, email: str, password: str) -> AuthTokenResponse:
        """POST /api/auth/login (form-urlencoded). Sets this client's token."""
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
    def get(self, project_id: UUID) -> ProjectResponse:
        """GET /api/projects/{project_id}."""
        response = self._parent._request("GET", f"/api/projects/{project_id}")
        return ProjectResponse.model_validate(response.json())

    def get_by_name(self, project_name: str) -> ProjectListResponse:
        """GET /api/projects/name/{project_name}. Returns a project list."""
        response = self._parent._request(
            "GET", f"/api/projects/name/{project_name}"
        )
        return ProjectListResponse.model_validate(response.json())


class _DocumentsSection(_Section):
    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> DocumentListResponse:
        response = self._parent._request(
            "GET",
            "/api/documents/",
            params={"project_ids": project_ids, "skip": skip, "limit": limit},
        )
        return DocumentListResponse.model_validate(response.json())

    def get(self, document_id: UUID) -> DocumentResponse:
        response = self._parent._request("GET", f"/api/documents/{document_id}")
        return DocumentResponse.model_validate(response.json())

    def get_by_name(
        self, document_name: str, project_id: UUID
    ) -> DocumentResponse:
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
        """POST /api/documents/ (multipart)."""
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
        self._parent._request("DELETE", f"/api/documents/{document_id}")

    def content(self, document_id: UUID) -> bytes:
        """GET /api/documents/{id}/content — raw file bytes."""
        response = self._parent._request(
            "GET", f"/api/documents/{document_id}/content"
        )
        return response.content

    def list_by_group(
        self, group_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> DocumentListResponse:
        response = self._parent._request(
            "GET",
            f"/api/documents/group/{group_id}",
            params={"skip": skip, "limit": limit},
        )
        return DocumentListResponse.model_validate(response.json())


class _GroupsSection(_Section):
    def list(
        self, project_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> DocumentGroupListResponse:
        response = self._parent._request(
            "GET",
            f"/api/projects/{project_id}/groups/",
            params={"skip": skip, "limit": limit},
        )
        return DocumentGroupListResponse.model_validate(response.json())

    def get(self, project_id: UUID, group_id: UUID) -> DocumentGroupResponse:
        response = self._parent._request(
            "GET", f"/api/projects/{project_id}/groups/{group_id}"
        )
        return DocumentGroupResponse.model_validate(response.json())

    def create(self, project_id: UUID, *, name: str) -> DocumentGroupResponse:
        response = self._parent._request(
            "POST",
            f"/api/projects/{project_id}/groups/",
            json_body={"name": name},
        )
        return DocumentGroupResponse.model_validate(response.json())

    def update(
        self, project_id: UUID, group_id: UUID, *, name: str
    ) -> DocumentGroupResponse:
        response = self._parent._request(
            "PUT",
            f"/api/projects/{project_id}/groups/{group_id}",
            json_body={"name": name},
        )
        return DocumentGroupResponse.model_validate(response.json())

    def delete(self, project_id: UUID, group_id: UUID) -> None:
        self._parent._request(
            "DELETE", f"/api/projects/{project_id}/groups/{group_id}"
        )

    def list_documents(
        self, group_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> DocumentListResponse:
        """GET /api/documents/group/{group_id}."""
        response = self._parent._request(
            "GET",
            f"/api/documents/group/{group_id}",
            params={"skip": skip, "limit": limit},
        )
        return DocumentListResponse.model_validate(response.json())


class _ChunksSection(_Section):
    def list(
        self,
        *,
        document_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> ChunkListResponse:
        response = self._parent._request(
            "GET",
            "/api/chunks/",
            params={"document_ids": document_ids, "skip": skip, "limit": limit},
        )
        return ChunkListResponse.model_validate(response.json())

    def get(self, chunk_id: UUID) -> ChunkResponse:
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
        body: dict[str, Any] = {
            "document_id": str(document_id),
            "start_index": start_index,
            "end_index": end_index,
        }
        if content is not None:
            body["content"] = content
        if metadata is not None:
            body["metadata"] = metadata
        response = self._parent._request(
            "POST", "/api/chunks/", json_body=body
        )
        return ChunkResponse.model_validate(response.json())

    def delete(self, chunk_id: UUID) -> None:
        self._parent._request("DELETE", f"/api/chunks/{chunk_id}")


class _PagesSection(_Section):
    def list(
        self, document_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> PageListResponse:
        response = self._parent._request(
            "GET",
            f"/api/pages/document/{document_id}",
            params={"skip": skip, "limit": limit},
        )
        return PageListResponse.model_validate(response.json())

    def get(self, page_id: UUID) -> PageResponse:
        response = self._parent._request("GET", f"/api/pages/{page_id}")
        return PageResponse.model_validate(response.json())


class _AnnotationsSection(_Section):
    def get(self, root_id: UUID) -> AnnotationResponse:
        response = self._parent._request(
            "GET", f"/api/annotations/{root_id}"
        )
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
        response = self._parent._request(
            "POST", "/api/annotations/", json_body=body
        )
        return AnnotationResponse.model_validate(response.json())

    def update(
        self,
        root_id: UUID,
        *,
        data: dict[str, Any],
        confidence_score: float | None = None,
    ) -> AnnotationResponse:
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
        self._parent._request("DELETE", f"/api/annotations/{root_id}")

    def list_by_document(
        self,
        document_id: UUID,
        *,
        operator_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> AnnotationListResponse:
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
        response = self._parent._request(
            "GET",
            f"/api/annotations/operator/{operator_id}",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_hydrated_by_operator(
        self, operator_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> AnnotationListResponse:
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
        response = self._parent._request(
            "GET",
            f"/api/annotations/document/{document_id}/operator-name/{operator_name}",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationListResponse.model_validate(response.json())


class _OperatorsSection(_Section):
    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> OperatorListResponse:
        response = self._parent._request(
            "GET",
            "/api/operators/",
            params={"project_ids": project_ids, "skip": skip, "limit": limit},
        )
        return OperatorListResponse.model_validate(response.json())

    def get(self, operator_id: UUID) -> OperatorResponse:
        response = self._parent._request(
            "GET", f"/api/operators/{operator_id}"
        )
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
        response = self._parent._request(
            "POST", "/api/operators/", json_body=body
        )
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
        self._parent._request("DELETE", f"/api/operators/{operator_id}")


class _WorkflowsSection(_Section):
    def list(
        self,
        *,
        project_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> WorkflowListResponse:
        response = self._parent._request(
            "GET",
            "/api/workflows/",
            params={"project_ids": project_ids, "skip": skip, "limit": limit},
        )
        return WorkflowListResponse.model_validate(response.json())

    def get(self, workflow_id: UUID) -> WorkflowResponse:
        response = self._parent._request(
            "GET", f"/api/workflows/{workflow_id}"
        )
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
        body: dict[str, Any] = {
            "project_id": str(project_id),
            "name": name,
            "is_active": is_active,
            "auto_run_on_upload": auto_run_on_upload,
        }
        if description is not None:
            body["description"] = description
        response = self._parent._request(
            "POST", "/api/workflows/", json_body=body
        )
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
        body = _stringify_uuids({k: v for k, v in fields.items() if v is not None})
        response = self._parent._request(
            "PUT",
            f"/api/workflows/{workflow_id}/nodes/{node_id}",
            json_body=body,
        )
        return WorkflowNodeResponse.model_validate(response.json())

    def delete_node(self, workflow_id: UUID, node_id: UUID) -> None:
        self._parent._request(
            "DELETE",
            f"/api/workflows/{workflow_id}/nodes/{node_id}",
        )


class _JobsSection(_Section):
    def list(
        self,
        *,
        project_id: UUID,
        status_filter: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> JobListResponse:
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
        response = self._parent._request("GET", f"/api/jobs/{job_id}")
        return JobResponse.model_validate(response.json())

    def create_manual(
        self,
        *,
        document_ids: list[UUID],
        workflow_ids: list[UUID],
        capture_execution_log: bool = False,
    ) -> CreateManualJobsResponse:
        body = {
            "document_ids": [str(x) for x in document_ids],
            "workflow_ids": [str(x) for x in workflow_ids],
            "capture_execution_log": capture_execution_log,
        }
        response = self._parent._request(
            "POST", "/api/jobs/", json_body=body
        )
        return CreateManualJobsResponse.model_validate(response.json())

    def cancel(self, job_id: UUID) -> JobActionResponse:
        response = self._parent._request(
            "POST", f"/api/jobs/{job_id}/cancel"
        )
        return JobActionResponse.model_validate(response.json())

    def retry(self, job_id: UUID) -> JobActionResponse:
        response = self._parent._request(
            "POST", f"/api/jobs/{job_id}/retry"
        )
        return JobActionResponse.model_validate(response.json())


class _QueriesSection(_Section):
    def execute(
        self,
        *,
        project_id: UUID,
        query: str,
        format: str = "dataframe",
        limit: int = 1000,
        timeout: int | None = None,
    ) -> QueryResultResponse:
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
