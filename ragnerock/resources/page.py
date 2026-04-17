"""Page resource (read-only)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragnerock.resources.base import _Resource


class Page(_Resource):
    """A single page within a document.

    Pages are read-only: the API does not expose create / update / delete.

    Attributes:
        id: Page UUID.
        document_id: Owning document.
        page_number: 1-based page number within the document.
        content: Extracted text content.
        metadata: Arbitrary key-value metadata.
    """

    id: UUID | None = None
    document_id: UUID | None = None
    page_number: int | None = None
    content: str | None = None
    metadata: dict[str, Any] | None = None
