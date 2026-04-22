"""Document and DocumentGroup resources."""

from __future__ import annotations

from enum import IntEnum, auto
from typing import Any
from uuid import UUID

from ragnerock.resources.base import OptionalDateTime, _Resource


class FileType(IntEnum):
    """Supported document file types. Mirrors the server-side enum values."""

    PLAINTEXT = auto()
    """Plain text file."""

    MARKDOWN = auto()
    """Markdown (``.md``) file."""

    PDF = auto()
    """PDF document."""

    DOCX = auto()
    """Microsoft Word document."""

    XLSX = auto()
    """Microsoft Excel spreadsheet."""

    CSV = auto()
    """Comma-separated values file."""

    IPYNB = auto()
    """Jupyter notebook."""

    JPG = auto()
    """JPEG image."""

    JPEG = auto()
    """JPEG image (alternate extension)."""

    PNG = auto()
    """PNG image."""


class Document(_Resource):
    """A document stored in a Ragnerock project.

    For creation, provide either ``file_path`` (local file to upload) or
    ``source_url`` (remote URL the server will fetch). After ``session.add``
    and ``session.commit``, server-assigned fields (``id``, ``storage_path``,
    ``created_at``, etc.) are populated in place.
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
    created_at: OptionalDateTime = None
    updated_at: OptionalDateTime = None
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
    """A named collection of documents within a project."""

    id: UUID | None = None
    name: str | None = None
    project_id: UUID | None = None
    created_at: OptionalDateTime = None
