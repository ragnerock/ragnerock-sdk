"""Document and DocumentGroup resources."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, auto
from typing import Any
from uuid import UUID

from ragnerock.resources.base import _Resource


class FileType(IntEnum):
    """File type. Mirrors the server-side enum values."""

    PLAINTEXT = auto()
    MARKDOWN = auto()
    PDF = auto()
    DOCX = auto()
    XLSX = auto()
    CSV = auto()
    IPYNB = auto()
    JPG = auto()
    JPEG = auto()
    PNG = auto()


class Document(_Resource):
    """A document stored in a Ragnerock project.

    For creation, provide either ``file_path`` (local file to upload) or
    ``source_url`` (remote URL the server will fetch). After ``session.add``
    and ``session.commit``, server-assigned fields (``id``, ``storage_path``,
    ``created_at``, etc.) are populated in place.

    Attributes:
        id (UUID | None): Server-assigned UUID. ``None`` until committed.
        name (str | None): Human-readable document name.
        project_id (UUID | None): Owning project.
        group_id (UUID | None): Optional group membership.
        file_path (str | None): Local filesystem path for upload (pre-commit
            only).
        source_url (str | None): Remote URL for server-side fetch (pre-commit
            only).
        file_type (FileType | None): File type enum (PDF, DOCX, …).
        storage_path (str | None): Server-side storage location.
        filesize (int | None): Byte size of the document.
        created_at (datetime | None): Creation timestamp.
        updated_at (datetime | None): Last-modified timestamp.
        created_by_id (UUID | None): User who created the document.
        metadata (dict[str, Any] | None): Arbitrary key-value metadata.
    """

    id: UUID | None = None
    name: str | None = None
    project_id: UUID | None = None
    group_id: UUID | None = None
    file_path: str | None = None
    source_url: str | None = None
    file_type: FileType | None = None
    storage_path: str | None = None
    filesize: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by_id: UUID | None = None
    metadata: dict[str, Any] | None = None

    def content(self) -> bytes:
        """Download the underlying file from the server.

        Returns the raw bytes the server has on disk — no parsing or text
        extraction is performed.

        Returns:
            bytes: The document's raw file content.

        Raises:
            RuntimeError: If this document has no session back-reference, or
                has not been committed yet (no ``id``).
        """
        if self._session is None:
            raise RuntimeError(
                "Document is not bound to a session; cannot fetch content."
            )
        if self.id is None:
            raise RuntimeError("Document has no id; cannot fetch content.")
        return self._session._engine.client.documents.content(self.id)


class DocumentGroup(_Resource):
    """A named collection of documents within a project.

    Attributes:
        id (UUID | None): Server-assigned UUID. ``None`` until committed.
        name (str | None): Group name.
        project_id (UUID | None): Owning project.
        created_at (datetime | None): Creation timestamp.
    """

    id: UUID | None = None
    name: str | None = None
    project_id: UUID | None = None
    created_at: datetime | None = None
