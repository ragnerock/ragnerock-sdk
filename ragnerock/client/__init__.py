"""Low-level HTTP client: one method per Ragnerock API endpoint.

:class:`RagnerockClient` owns a pooled connection and exposes each API area as
a section property (``client.documents``, ``client.workflows``,
``client.endpoints``, ...). Response payloads are lenient pydantic models: the
commonly read fields are declared and typed, and any other field the server
returns is still available as an attribute.

Most code should use the higher-level :class:`~ragnerock.engine.Engine` and
:class:`~ragnerock.session.Session`, reaching for ``engine.client`` only for
API areas the session layer doesn't model.
"""

from __future__ import annotations

from ragnerock.client._base import UNSET, MessageResponse
from ragnerock.client._client import RagnerockClient
from ragnerock.client.annotations import AnnotationListResponse, AnnotationResponse
from ragnerock.client.auth import AuthTokenResponse
from ragnerock.client.chunks import ChunkListResponse, ChunkResponse
from ragnerock.client.documents import DocumentListResponse, DocumentResponse
from ragnerock.client.gitops import (
    GitOpsApplyResponse,
    GitOpsApplyResult,
    SealingKeyResponse,
)
from ragnerock.client.groups import DocumentGroupListResponse, DocumentGroupResponse
from ragnerock.client.jobs import (
    CreateManualJobsResponse,
    JobActionResponse,
    JobListResponse,
    JobResponse,
)
from ragnerock.client.operators import OperatorListResponse, OperatorResponse
from ragnerock.client.pages import PageListResponse, PageResponse
from ragnerock.client.projects import ProjectListResponse, ProjectResponse
from ragnerock.client.queries import QueryResultResponse
from ragnerock.client.workflows import (
    WorkflowListResponse,
    WorkflowNodeResponse,
    WorkflowResponse,
)

__all__ = [
    "UNSET",
    "AnnotationListResponse",
    "AnnotationResponse",
    "AuthTokenResponse",
    "ChunkListResponse",
    "ChunkResponse",
    "CreateManualJobsResponse",
    "DocumentGroupListResponse",
    "DocumentGroupResponse",
    "DocumentListResponse",
    "DocumentResponse",
    "GitOpsApplyResponse",
    "GitOpsApplyResult",
    "JobActionResponse",
    "JobListResponse",
    "JobResponse",
    "MessageResponse",
    "OperatorListResponse",
    "OperatorResponse",
    "PageListResponse",
    "PageResponse",
    "ProjectListResponse",
    "ProjectResponse",
    "QueryResultResponse",
    "RagnerockClient",
    "SealingKeyResponse",
    "WorkflowListResponse",
    "WorkflowNodeResponse",
    "WorkflowResponse",
]
