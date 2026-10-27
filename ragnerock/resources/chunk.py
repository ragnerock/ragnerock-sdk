"""Chunk resource."""

from __future__ import annotations

from enum import IntEnum
from uuid import UUID

from ragnerock.resources.base import _Resource


class ChunkType(IntEnum):
    """Scope a chunk covers, or an operator runs at. Mirrors the server's integer values.

    Two families share the enum: the document family
    (``DOCUMENT > PAGE > PARAGRAPH > SENTENCE``) and the tabular family
    (``DOCUMENT > SHEET > ROW``) used by spreadsheet and SQL sources.
    """

    DOCUMENT = 0
    """Whole-document scope."""

    PAGE = 1
    """Per-page scope."""

    PARAGRAPH = 2
    """Paragraph-level scope."""

    SENTENCE = 3
    """Sentence-level scope."""

    ROW = 4
    """One row of a tabular sheet."""

    ROW_WINDOW = 5
    """A sliding window of rows centred on each row of a sheet."""

    SHEET = 6
    """An entire sheet of a tabular document."""

    @property
    def accepts_input_columns(self) -> bool:
        """Whether an operator at this scope may narrow the columns it is shown.

        Only :attr:`ROW` and :attr:`SHEET` targets carry a sheet's column
        definitions, so only those scopes accept an operator's
        ``input_columns``.

        Returns:
            bool: ``True`` for ``ROW`` and ``SHEET``.
        """
        return self in (ChunkType.ROW, ChunkType.SHEET)


class Chunk(_Resource):
    """A content slice within a document.

    A chunk carries the extracted text for a range of a document along with
    its position and scope (:class:`ChunkType`). Chunks are typically produced
    by server-side ingestion and are the unit of work many operators run on.

    ``document_offset`` is the chunk's ordinal position within the document;
    ``start_char_idx`` / ``end_char_idx`` optionally locate it in the
    document's extracted text (end exclusive).
    """

    id: UUID | None = None
    document_id: UUID | None = None
    page_id: UUID | None = None
    content: str | None = None
    document_offset: int | None = None
    chunk_type: ChunkType | None = None
    start_char_idx: int | None = None
    end_char_idx: int | None = None
