"""Chunk endpoints (``/api/chunks/...``)."""

from __future__ import annotations

from uuid import UUID

from ragnerock.client._base import _ApiModel, _body, _Section


class ChunkResponse(_ApiModel):
    """Response payload representing a single chunk."""

    id: UUID
    document_id: UUID
    content: str | None = None
    document_offset: int | None = None
    chunk_type: int | None = None
    start_char_idx: int | None = None
    end_char_idx: int | None = None
    page_id: UUID | None = None


class ChunkListResponse(_ApiModel):
    """Paginated list response for chunks."""

    chunks: list[ChunkResponse]
    total: int
    skip: int
    limit: int


class _ChunksSection(_Section):
    """Chunk CRUD endpoints."""

    def list(
        self,
        *,
        document_ids: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> ChunkListResponse:
        """List chunks, optionally scoped to one or more documents.

        Calls ``GET /api/chunks/``.

        Args:
            document_ids (str | None): Comma-separated string of document UUIDs, or
                ``None`` to list across every accessible document.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            ChunkListResponse: A page of chunks.
        """
        response = self._parent._request(
            "GET",
            "/api/chunks/",
            params={"document_ids": document_ids, "skip": skip, "limit": limit},
        )
        return ChunkListResponse.model_validate(response.json())

    def get(self, chunk_id: UUID) -> ChunkResponse:
        """Fetch a single chunk by id.

        Calls ``GET /api/chunks/{chunk_id}``.

        Args:
            chunk_id (UUID): UUID of the chunk.

        Returns:
            ChunkResponse: The chunk response.

        Raises:
            NotFoundError: If no chunk has that id.
        """
        response = self._parent._request("GET", f"/api/chunks/{chunk_id}")
        return ChunkResponse.model_validate(response.json())

    def create(
        self,
        *,
        document_id: UUID,
        content: str,
        document_offset: int,
        chunk_type: int,
        start_char_idx: int | None = None,
        end_char_idx: int | None = None,
    ) -> ChunkResponse:
        """Create a chunk on a document.

        Calls ``POST /api/chunks/``.

        Args:
            document_id (UUID): Owning document.
            content (str): Text content of the chunk.
            document_offset (int): The chunk's ordinal position within the
                document.
            chunk_type (int): Integer value of a
                :class:`~ragnerock.resources.chunk.ChunkType` — the scope the
                chunk covers.
            start_char_idx (int | None): Character offset where the chunk
                begins in the document's extracted text.
            end_char_idx (int | None): Character offset where the chunk ends
                (exclusive).

        Returns:
            ChunkResponse: The newly created chunk response.
        """
        body = _body(
            document_id=document_id,
            content=content,
            document_offset=document_offset,
            chunk_type=int(chunk_type),
            start_char_idx=start_char_idx,
            end_char_idx=end_char_idx,
        )
        response = self._parent._request("POST", "/api/chunks/", json_body=body)
        return ChunkResponse.model_validate(response.json())

    def delete(self, chunk_id: UUID) -> None:
        """Delete a chunk.

        Calls ``DELETE /api/chunks/{chunk_id}``.

        Args:
            chunk_id (UUID): Chunk to delete.
        """
        self._parent._request("DELETE", f"/api/chunks/{chunk_id}")
