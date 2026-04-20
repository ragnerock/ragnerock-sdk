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
        root_id (UUID | None): Stable annotation identity (server-assigned).
        operator_id (UUID | None): Operator that produced (or will produce)
            this annotation.
        operator_name (str | None): Cached operator name, when the server
            hydrates it.
        document_id (UUID | None): Document this annotation is attached to.
        chunk_id (UUID | None): Chunk this annotation is attached to.
        page_id (UUID | None): Page this annotation is attached to.
        data (dict[str, Any] | None): Arbitrary JSON matching the operator's
            schema.
        confidence_score (float | None): Optional confidence value
            (0.0 – 1.0).
        generation_metadata (dict[str, Any] | None): Optional server-side
            metadata about how the annotation was generated.
        created_at (datetime | None): Creation timestamp.
        updated_at (datetime | None): Last-modified timestamp.
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
        """Alias for :attr:`root_id`.

        Every other resource exposes its server-assigned identity as ``id``;
        annotations use ``root_id`` on the wire. This property lets callers
        treat annotations uniformly.

        Returns:
            UUID | None: The annotation's ``root_id``, or ``None`` if not yet
            persisted.
        """
        return self.root_id
