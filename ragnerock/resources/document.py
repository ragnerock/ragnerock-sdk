"""Document and DocumentFolder resources."""

from __future__ import annotations

from enum import IntEnum, StrEnum, auto
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ragnerock.resources.base import OptionalDateTime, _Resource

if TYPE_CHECKING:
    from ragnerock.resources.run import Run


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

    HTML = auto()
    """HTML page."""

    SQL_RESULT = auto()
    """The table a SQL ingest source maintains. Rows are written by ingest
    runs rather than parsed from a stored file."""

    XML = auto()
    """XML document."""


class DocumentStatus(StrEnum):
    """Processing state the server reports for a document."""

    PENDING = "pending"
    """Uploaded, waiting to be processed."""

    PROCESSING = "processing"
    """Being parsed, chunked, or embedded."""

    READY = "ready"
    """Fully processed and available to agents and queries."""

    ERROR = "error"
    """Processing failed."""

    FETCHING = "fetching"
    """A pull-source placeholder whose content has not been fetched yet."""

    NOT_FETCHED = "not_fetched"
    """A pull-source placeholder whose run finished without filling it."""


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
    document_folder_id: UUID | None = None
    file_path: str | None = None
    source_url: str | None = None
    file_type: FileType | None = None
    storage_path: str | None = None
    filesize: int | None = None
    created_at: OptionalDateTime = None
    updated_at: OptionalDateTime = None
    created_by_id: UUID | None = None
    status: DocumentStatus | None = None
    is_sample: bool = False
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

    def latest_run(self) -> Run:
        """Fetch the latest processing run for this document.

        Useful for following ingestion progress (``phase``, stage counters)
        beyond the coarse :attr:`status`.

        Returns:
            Run: The document's most recent run, bound to the session.

        Raises:
            RuntimeError: If this document has no session back-reference, or
                has not been committed yet (no ``id``).
            NotFoundError: If the document has no run.
        """
        if self._session is None:
            raise RuntimeError("Document is not bound to a session; cannot fetch run.")
        if self.id is None:
            raise RuntimeError("Document has no id; cannot fetch run.")
        return self._session._document_run(self.id)


class DocumentFolder(_Resource):
    """A named folder of documents within a project.

    Documents join a folder through their ``document_folder_id``. The
    folder's own ``folder_id`` is the resource folder it is filed under in
    the project's folder tree, not another document folder.
    """

    id: UUID | None = None
    name: str | None = None
    project_id: UUID | None = None
    folder_id: UUID | None = None
    created_at: OptionalDateTime = None
