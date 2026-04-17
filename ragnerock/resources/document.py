"""Document and DocumentGroup resources."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from ragnerock.resources.base import _Resource


class Document(_Resource):
    """A document stored in a Ragnerock project.

    For creation, provide either ``file_path`` (local file to upload) or
    ``source_url`` (remote URL the server will fetch). After ``session.add``
    and ``session.commit``, server-assigned fields (``id``, ``storage_path``,
    ``created_at``, etc.) are populated in place.

    Attributes:
        id: Server-assigned UUID. ``None`` until committed.
        name: Human-readable document name.
        project_id: Owning project.
        group_id: Optional group membership.
        file_path: Local filesystem path for upload (pre-commit only).
        source_url: Remote URL for server-side fetch (pre-commit only).
        file_type: MIME type or extension.
        storage_path: Server-side storage location.
        filesize: Byte size of the document.
        created_at: Creation timestamp.
        updated_at: Last-modified timestamp.
        created_by_id: User who created the document.
        metadata: Arbitrary key-value metadata.
    """

    id: UUID | None = None
    name: str | None = None
    project_id: UUID | None = None
    group_id: UUID | None = None
    file_path: str | None = None
    source_url: str | None = None
    file_type: str | None = None
    storage_path: str | None = None
    filesize: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by_id: UUID | None = None
    metadata: dict[str, Any] | None = None

    def content(self) -> bytes:
        """Download this document's raw bytes. Requires a bound session and ``id``."""
        if self._session is None:
            raise RuntimeError("Document is not bound to a session; cannot fetch content.")
        if self.id is None:
            raise RuntimeError("Document has no id; cannot fetch content.")
        return self._session._engine.client.documents.content(self.id)


class DocumentGroup(_Resource):
    """A named collection of documents within a project.

    Attributes:
        id: Server-assigned UUID. ``None`` until committed.
        name: Group name.
        project_id: Owning project.
        created_at: Creation timestamp.
    """

    id: UUID | None = None
    name: str | None = None
    project_id: UUID | None = None
    created_at: datetime | None = None
