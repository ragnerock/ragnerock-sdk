"""Page resource (read-only)."""

from __future__ import annotations

from uuid import UUID

from ragnerock.resources.base import OptionalDateTime, _Resource


class Page(_Resource):
    """A single page within a document.

    Pages are read-only: the API does not expose create, update, or delete
    operations for them. Page numbering is 1-based within the owning
    :class:`~ragnerock.resources.document.Document`.
    """

    id: UUID | None = None
    document_id: UUID | None = None
    page_number: int | None = None
    content: str | None = None
    created_at: OptionalDateTime = None
