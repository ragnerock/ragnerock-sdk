"""Annotation resource for operator-produced annotations on documents, chunks, or pages."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from ragnerock.resources.base import _Resource


class Annotation(_Resource):
    """An annotation produced by an operator, attached to a document, chunk, or page.

    Exactly one of ``document_id``, ``chunk_id``, or ``page_id`` is typically
    set, depending on the operator's ``chunk_type``. The server-assigned
    identity is carried on ``root_id``; the :attr:`id` property exposes it
    under the same name used by every other resource.
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
