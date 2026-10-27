"""Annotation endpoints (``/api/annotations/...``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section


class AnnotationResponse(_ApiModel):
    """Response payload representing a single annotation.

    ``root_id`` and ``operator_id`` are optional because the server omits them
    from the narrow-scope list endpoints (list by document + operator).
    """

    root_id: UUID | None = None
    operator_id: UUID | None = None


class AnnotationListResponse(_ApiModel):
    """Paginated list response for annotations."""

    annotations: list[AnnotationResponse]
    total: int
    skip: int
    limit: int


class _AnnotationsSection(_Section):
    """Annotation CRUD and scoped-list endpoints."""

    def get(self, root_id: UUID) -> AnnotationResponse:
        """Fetch a single annotation by its ``root_id``.

        Calls ``GET /api/annotations/{root_id}``.

        Args:
            root_id (UUID): Server-assigned annotation identity.

        Returns:
            AnnotationResponse: The annotation response.

        Raises:
            NotFoundError: If no annotation has that id.
        """
        response = self._parent._request("GET", f"/api/annotations/{root_id}")
        return AnnotationResponse.model_validate(response.json())

    def create(
        self,
        *,
        operator_id: UUID,
        data: dict[str, Any],
        document_id: UUID | None = None,
        chunk_id: UUID | None = None,
        page_id: UUID | None = None,
        confidence_score: float | None = None,
    ) -> AnnotationResponse:
        """Create an annotation, attaching it to exactly one target.

        Calls ``POST /api/annotations/``. Callers must supply exactly one of
        ``document_id``, ``chunk_id``, or ``page_id`` — typically the one
        that matches the operator's ``chunk_type``.

        Args:
            operator_id (UUID): Operator the annotation belongs to. Its JSON schema
                validates ``data`` server-side.
            data (dict[str, Any]): Annotation payload matching the operator's schema.
            document_id (UUID | None): Document this annotation is about.
            chunk_id (UUID | None): Chunk this annotation is about.
            page_id (UUID | None): Page this annotation is about.
            confidence_score (float | None): Optional confidence in ``[0.0, 1.0]``.

        Returns:
            AnnotationResponse: The newly created annotation response.
        """
        body: dict[str, Any] = {
            "operator_id": str(operator_id),
            "data": data,
        }
        if document_id is not None:
            body["document_id"] = str(document_id)
        if chunk_id is not None:
            body["chunk_id"] = str(chunk_id)
        if page_id is not None:
            body["page_id"] = str(page_id)
        if confidence_score is not None:
            body["confidence_score"] = confidence_score
        response = self._parent._request("POST", "/api/annotations/", json_body=body)
        return AnnotationResponse.model_validate(response.json())

    def update(
        self,
        root_id: UUID,
        *,
        data: dict[str, Any],
        confidence_score: float | None = None,
    ) -> AnnotationResponse:
        """Replace an annotation's ``data`` payload.

        Calls ``PUT /api/annotations/{root_id}``. The JSON body is the new
        ``data`` payload; ``confidence_score`` rides as a query parameter
        when provided. Attachment target (document/chunk/page) and operator
        are not editable — create a fresh annotation if those need to change.

        Args:
            root_id (UUID): Annotation to update.
            data (dict[str, Any]): Replacement payload. Must still validate against the
                operator's schema.
            confidence_score (float | None): Optional replacement confidence.

        Returns:
            AnnotationResponse: The updated annotation response.
        """
        params: dict[str, Any] = {}
        if confidence_score is not None:
            params["confidence_score"] = confidence_score
        response = self._parent._request(
            "PUT",
            f"/api/annotations/{root_id}",
            params=params or None,
            json_body=data,
        )
        return AnnotationResponse.model_validate(response.json())

    def delete(self, root_id: UUID) -> None:
        """Delete an annotation.

        Calls ``DELETE /api/annotations/{root_id}``.

        Args:
            root_id (UUID): Annotation to delete.
        """
        self._parent._request("DELETE", f"/api/annotations/{root_id}")

    def list_by_document(
        self,
        document_id: UUID,
        *,
        operator_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> AnnotationListResponse:
        """List annotations attached to a document.

        Calls ``GET /api/annotations/document/{document_id}``. Covers
        document-level annotations plus annotations on the document's
        children (chunks, pages).

        Args:
            document_id (UUID): Document to list.
            operator_name (str | None): Restrict to annotations produced by an operator
                with this exact name.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/document/{document_id}",
            params={
                "operator_name": operator_name,
                "skip": skip,
                "limit": limit,
            },
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_by_chunk(
        self,
        chunk_id: UUID,
        *,
        operator_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> AnnotationListResponse:
        """List annotations attached to a chunk.

        Calls ``GET /api/annotations/chunk/{chunk_id}``.

        Args:
            chunk_id (UUID): Chunk to list.
            operator_name (str | None): Restrict to annotations produced by an operator
                with this exact name.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/chunk/{chunk_id}",
            params={
                "operator_name": operator_name,
                "skip": skip,
                "limit": limit,
            },
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_by_operator(
        self, operator_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> AnnotationListResponse:
        """List every annotation produced by a given operator.

        Calls ``GET /api/annotations/operator/{operator_id}``. Results span
        all documents the operator has run against. For operator metadata
        joined into each row, use :meth:`list_hydrated_by_operator` instead.

        Args:
            operator_id (UUID): Operator to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/operator/{operator_id}",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_hydrated_by_operator(
        self, operator_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> AnnotationListResponse:
        """Like :meth:`list_by_operator`, but with operator metadata joined in.

        Calls ``GET /api/annotations/operator/{operator_id}/hydrated``. Each
        row carries ``operator_name`` and any other joined fields the server
        attaches. Costs more server-side than the plain list.

        Args:
            operator_id (UUID): Operator to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of hydrated annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/operator/{operator_id}/hydrated",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_by_document_and_operator_id(
        self,
        document_id: UUID,
        operator_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> AnnotationListResponse:
        """List annotations from a specific operator on a specific document.

        Calls
        ``GET /api/annotations/document/{document_id}/operator/{operator_id}``.
        The narrow-scope form of :meth:`list_by_document` when you already
        have the operator's id.

        Args:
            document_id (UUID): Document to scope to.
            operator_id (UUID): Operator to scope to.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/document/{document_id}/operator/{operator_id}",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_by_document_and_operator_name(
        self,
        document_id: UUID,
        operator_name: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> AnnotationListResponse:
        """Like :meth:`list_by_document_and_operator_id`, keyed by operator name.

        Calls
        ``GET /api/annotations/document/{document_id}/operator-name/{operator_name}``.
        Use this when you want to avoid a separate lookup to resolve the
        operator's id.

        Args:
            document_id (UUID): Document to scope to.
            operator_name (str): Exact operator name to scope to.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/document/{document_id}/operator-name/{operator_name}",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationListResponse.model_validate(response.json())
