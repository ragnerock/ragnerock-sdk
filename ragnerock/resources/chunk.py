"""Chunk resource."""

from __future__ import annotations

from enum import IntEnum
from typing import Any
from uuid import UUID

from ragnerock.resources.base import OptionalDateTime, _Resource


class ChunkType(IntEnum):
    """Chunk scope. Mirrors the server-side integer enum values."""

    DOCUMENT = 1
    """Whole-document scope."""

    PAGE = 2
    """Per-page scope."""

    SECTION = 3
    """Section-level scope."""

    PARAGRAPH = 4
    """Paragraph-level scope."""

    SENTENCE = 5
    """Sentence-level scope."""


class Chunk(_Resource):
    """A content slice within a document.

    A chunk carries the extracted text for a range of a document along with
    its offsets and scope (:class:`ChunkType`). Chunks are typically produced
    by server-side ingestion and are the unit of work many operators run on.
    """

    id: UUID | None = None
    document_id: UUID | None = None
    content: str | None = None
    start_index: int | None = None
    end_index: int | None = None
    chunk_type: ChunkType | None = None
    metadata: dict[str, Any] | None = None
    created_at: OptionalDateTime = None
