"""Annotation resource (exposed as ``Annotation`` — the API calls these Document Annotations)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from ragnerock.resources.base import _Resource


class Annotation(_Resource):
    """An annotation produced by an operator, attached to a document, chunk, or page.

    Exactly one of ``document_id``, ``chunk_id``, or ``page_id`` is typically
    set, depending on the operator's chunk_type.

    Attributes:
        root_id: Stable annotation identity (server-assigned).
        operator_id: Operator that produced (or will produce) this annotation.
        operator_name: Cached operator name, when the server hydrates it.
        document_id: Document this annotation is attached to.
        chunk_id: Chunk this annotation is attached to.
        page_id: Page this annotation is attached to.
        data: Arbitrary JSON matching the operator's schema.
        confidence_score: Optional confidence value (0.0 – 1.0).
        generation_metadata: Optional server-side metadata about how the
            annotation was generated.
        created_at: Creation timestamp.
        updated_at: Last-modified timestamp.
    """

    root_id: UUID | None = None
    operator_id: UUID | None = None
    operator_name: str | None = None
    document_id: UUID | None = None
    chunk_id: UUID | None = None
    page_id: UUID | None = None
    data: dict[str, Any] | None = None
    confidence_score: float | None = None
    generation_metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def id(self) -> UUID | None:
        """Alias for ``root_id``, for uniformity with other resources."""
        return self.root_id
