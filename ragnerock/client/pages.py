"""Page endpoints (``/api/pages/...``)."""

from __future__ import annotations

from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section


class PageResponse(_ApiModel):
    """Response payload representing a single extracted document page."""

    id: UUID
    document_id: UUID
    page_number: int


class PageListResponse(_ApiModel):
    """Paginated list response for pages."""

    pages: list[PageResponse]
    total: int
    skip: int
    limit: int


class _PagesSection(_Section):
    """Read-only page endpoints. Pages are produced by document parsing."""

    def list(
        self, document_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> PageListResponse:
        """List the pages of a document.

        Calls ``GET /api/pages/document/{document_id}``. Pages are ordered by
        ``page_number`` in the response.

        Args:
            document_id (UUID): Document whose pages to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            PageListResponse: A page of pages.
        """
        response = self._parent._request(
            "GET",
            f"/api/pages/document/{document_id}",
            params={"skip": skip, "limit": limit},
        )
        return PageListResponse.model_validate(response.json())

    def get(self, page_id: UUID) -> PageResponse:
        """Fetch a single page by id.

        Calls ``GET /api/pages/{page_id}``.

        Args:
            page_id (UUID): UUID of the page.

        Returns:
            PageResponse: The page response.

        Raises:
            NotFoundError: If no page has that id.
        """
        response = self._parent._request("GET", f"/api/pages/{page_id}")
        return PageResponse.model_validate(response.json())
