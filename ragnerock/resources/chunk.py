"""Chunk resource."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any
from uuid import UUID

from ragnerock.resources.base import _Resource


class ChunkType(IntEnum):
    """Chunk scope. Mirrors the server-side enum values.

    The numeric values match the API's integer enum.
    """

    DOCUMENT = 1
    PAGE = 2
    SECTION = 3
    PARAGRAPH = 4
    SENTENCE = 5


class Chunk(_Resource):
    """A content slice within a document.

    Attributes:
        id: Server-assigned UUID. ``None`` until committed.
        document_id: Owning document.
        content: Text content of the chunk.
        start_index: Character offset where the chunk begins in the document.
        end_index: Character offset where the chunk ends (exclusive).
        chunk_type: Chunk scope (DOCUMENT / PAGE / SECTION / …).
        metadata: Arbitrary key-value metadata.
    """

    id: UUID | None = None
    document_id: UUID | None = None
    content: str | None = None
    start_index: int | None = None
    end_index: int | None = None
    chunk_type: ChunkType | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
