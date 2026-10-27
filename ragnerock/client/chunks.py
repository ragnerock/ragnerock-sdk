"""Chunk endpoints (``/api/chunks/...``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section


class ChunkResponse(_ApiModel):
    """Response payload representing a single chunk."""

    id: UUID
    document_id: UUID


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
        start_index: int,
        end_index: int,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChunkResponse:
        """Create a chunk on a document.

        Calls ``POST /api/chunks/``. ``end_index`` is exclusive, matching
        Python slice semantics.

        Args:
            document_id (UUID): Owning document.
            start_index (int): Character offset where the chunk begins.
            end_index (int): Character offset where the chunk ends (exclusive).
            content (str | None): Text content of the chunk. If omitted, the server
                extracts it from the document at the given offsets.
            metadata (dict[str, Any] | None): Arbitrary JSON metadata.

        Returns:
            ChunkResponse: The newly created chunk response.
        """
        body: dict[str, Any] = {
            "document_id": str(document_id),
            "start_index": start_index,
            "end_index": end_index,
        }
        if content is not None:
            body["content"] = content
        if metadata is not None:
            body["metadata"] = metadata
        response = self._parent._request("POST", "/api/chunks/", json_body=body)
        return ChunkResponse.model_validate(response.json())

    def delete(self, chunk_id: UUID) -> None:
        """Delete a chunk.

        Calls ``DELETE /api/chunks/{chunk_id}``.

        Args:
            chunk_id (UUID): Chunk to delete.
        """
        self._parent._request("DELETE", f"/api/chunks/{chunk_id}")
