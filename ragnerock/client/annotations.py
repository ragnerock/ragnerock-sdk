"""Annotation endpoints (``/api/annotations/...``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _body, _Section
from ragnerock.client.chunks import ChunkResponse
from ragnerock.client.documents import DocumentResponse
from ragnerock.timestamps import UtcDatetime


class AnnotationResponse(_ApiModel):
    """Response payload representing a single annotation.

    ``root_id`` and ``operator_id`` are optional because the server omits them
    from the narrow-scope list endpoints (list by document + operator). The
    compact list endpoints (by document, chunk, or operator) carry identity,
    ``operator_name``, and ``confidence_score`` but no ``data``; fetch the
    annotation by ``root_id``, or use a hydrated listing, for the values.
    """

    root_id: UUID | None = None
    operator_id: UUID | None = None
    operator_name: str | None = None
    schema_id: UUID | None = None
    data: dict[str, Any] | None = None
    document_id: UUID | None = None
    document_name: str | None = None
    chunk_id: UUID | None = None
    page_id: UUID | None = None
    row_id: UUID | None = None
    sheet_id: UUID | None = None
    confidence_score: float | None = None
    generation_metadata: dict[str, Any] | None = None
    created_at: UtcDatetime = None
    created_by_id: UUID | None = None
    updated_at: UtcDatetime = None
    updated_by_id: UUID | None = None


class AnnotationListResponse(_ApiModel):
    """Paginated list response for annotations."""

    annotations: list[AnnotationResponse]
    total: int
    skip: int
    limit: int


class AnnotationRevisionResponse(_ApiModel):
    """One revision in an annotation's edit history.

    ``source`` says where the revision came from: ``"operator"`` (the
    original machine output), ``"user"`` (a user-created original),
    ``"legacy"`` (the pre-edit state of an annotation edited before history
    was kept, origin unknown), ``"user_edit"``, ``"restore"``, or
    ``"assignment"`` (an agent delivering an assignment's output).
    ``restored_from_index`` is set only for ``"restore"`` revisions.
    """

    revision_index: int
    data: dict[str, Any] = {}
    source: str | None = None
    confidence_score: float | None = None
    restored_from_index: int | None = None
    restored_from_id: UUID | None = None
    created_at: UtcDatetime = None
    created_by_id: UUID | None = None
    created_by_email: str | None = None


class AnnotationRevisionListResponse(_ApiModel):
    """Paginated revision history for one annotation, newest first."""

    revisions: list[AnnotationRevisionResponse]
    total: int
    skip: int
    limit: int


class DocumentWithAnnotations(_ApiModel):
    """A document paired with how many annotations an operator made on it."""

    document: DocumentResponse
    annotation_count: int = 0


class DocumentsWithAnnotationsListResponse(_ApiModel):
    """Paginated list of documents carrying an operator's annotations."""

    documents: list[DocumentWithAnnotations]
    total: int
    skip: int
    limit: int


class ChunkWithAnnotationData(_ApiModel):
    """A chunk paired with its annotation, if it has one."""

    chunk: ChunkResponse
    annotation: AnnotationResponse | None = None


class ChunkWithAnnotationDataListResponse(_ApiModel):
    """Paginated list of a document's chunks with their annotations."""

    chunks: list[ChunkWithAnnotationData]
    total: int
    skip: int
    limit: int


class _AnnotationsSection(_Section):
    """Annotation CRUD, revision, and scoped-list endpoints."""

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
        generation_metadata: dict[str, Any] | None = None,
        row_id: UUID | None = None,
        sheet_id: UUID | None = None,
    ) -> AnnotationResponse:
        """Create an annotation, attaching it to a target.

        Calls ``POST /api/annotations/``. Callers supply one of
        ``document_id``, ``chunk_id``, or ``page_id`` — typically the one
        that matches the operator's ``chunk_type``. Annotations on tabular
        data may also name the ``sheet_id`` or ``row_id`` they describe.

        Args:
            operator_id (UUID): Operator the annotation belongs to. Its JSON schema
                validates ``data`` server-side.
            data (dict[str, Any]): Annotation payload matching the operator's schema.
            document_id (UUID | None): Document this annotation is about.
            chunk_id (UUID | None): Chunk this annotation is about.
            page_id (UUID | None): Page this annotation is about.
            confidence_score (float | None): Optional confidence in ``[0.0, 1.0]``.
            generation_metadata (dict[str, Any] | None): Free-form details about
                how the values were produced (model, prompt version, ...).
            row_id (UUID | None): Spreadsheet row this annotation is about.
            sheet_id (UUID | None): Spreadsheet sheet this annotation is about.

        Returns:
            AnnotationResponse: The newly created annotation response.

        Raises:
            ValidationError: If ``data`` does not match the operator's schema
                or the target is missing or ambiguous.
        """
        body = _body(
            operator_id=operator_id,
            data=data,
            document_id=document_id,
            chunk_id=chunk_id,
            page_id=page_id,
            row_id=row_id,
            sheet_id=sheet_id,
            confidence_score=confidence_score,
            generation_metadata=generation_metadata,
        )
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
        Each values-changing edit is recorded as a revision; see
        :meth:`list_revisions`.

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

    def list_revisions(
        self, root_id: UUID, *, skip: int = 0, limit: int = 50
    ) -> AnnotationRevisionListResponse:
        """List an annotation's revision history, newest first.

        Calls ``GET /api/annotations/{root_id}/revisions``. Every
        values-changing edit appends a revision, and the first edit also
        records the pre-edit state, so an edited annotation's oldest revision
        is its original. A never-edited annotation has no revisions.

        Because the list is newest first, page until ``total`` is reached to
        find the original of an annotation with more revisions than one page.

        Args:
            root_id (UUID): Annotation whose history to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page (at most 1000).

        Returns:
            AnnotationRevisionListResponse: A page of revisions.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/{root_id}/revisions",
            params={"skip": skip, "limit": limit},
        )
        return AnnotationRevisionListResponse.model_validate(response.json())

    def restore(self, root_id: UUID, revision_index: int) -> AnnotationResponse:
        """Restore an annotation to one of its earlier revisions.

        Calls ``POST /api/annotations/{root_id}/revisions/{revision_index}/restore``.
        The revision's values become the current values and are recorded as a
        new ``"restore"`` revision, so history is never rewritten. Restoring
        the current state is a no-op.

        Args:
            root_id (UUID): Annotation to restore.
            revision_index (int): The revision to restore.

        Returns:
            AnnotationResponse: The restored annotation.

        Raises:
            NotFoundError: If the annotation or revision does not exist.
        """
        response = self._parent._request(
            "POST", f"/api/annotations/{root_id}/revisions/{revision_index}/restore"
        )
        return AnnotationResponse.model_validate(response.json())

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

    def list_hydrated_by_schema(
        self,
        schema_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        edited_only: bool = False,
        user_created_only: bool = False,
        document_id: UUID | None = None,
    ) -> AnnotationListResponse:
        """List the annotations conforming to an annotation schema, with their values.

        Calls ``GET /api/annotations/schema/{schema_id}/hydrated``. Works for
        any schema, whether an operator's output schema or one an agent
        created for its memory.

        ``edited_only`` matches every annotation that has been edited,
        including edits that only changed the confidence score, so a matched
        annotation can have no revisions.

        Args:
            schema_id (UUID): Annotation schema to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page (at most 1000).
            search (str | None): Text to search for in annotation values.
            edited_only (bool): Only annotations a person has edited.
            user_created_only (bool): Only annotations a person created.
            document_id (UUID | None): Only annotations on this document.

        Returns:
            AnnotationListResponse: A page of hydrated annotations.
        """
        params: dict[str, Any] = {"skip": skip, "limit": limit, "search": search}
        if edited_only:
            params["edited_only"] = True
        if user_created_only:
            params["user_created_only"] = True
        if document_id is not None:
            params["document_id"] = str(document_id)
        response = self._parent._request(
            "GET", f"/api/annotations/schema/{schema_id}/hydrated", params=params
        )
        return AnnotationListResponse.model_validate(response.json())

    def list_documents_with_schema_annotations(
        self, operator_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> DocumentsWithAnnotationsListResponse:
        """List the documents an operator has annotated, with annotation counts.

        Calls ``GET /api/annotations/operator/{operator_id}/documents``.

        Args:
            operator_id (UUID): Operator whose documents to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            DocumentsWithAnnotationsListResponse: A page of documents, each
            with its annotation count.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/operator/{operator_id}/documents",
            params={"skip": skip, "limit": limit},
        )
        return DocumentsWithAnnotationsListResponse.model_validate(response.json())

    def list_chunks_with_schema_annotations(
        self, operator_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> AnnotationListResponse:
        """List an operator's chunk-level annotations.

        Calls ``GET /api/annotations/operator/{operator_id}/chunks``.

        Args:
            operator_id (UUID): Operator whose chunk-level annotations to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AnnotationListResponse: A page of annotations, each carrying its
            ``chunk_id`` and ``data``.
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/operator/{operator_id}/chunks",
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

    def list_chunks_with_annotations_by_document(
        self,
        document_id: UUID,
        *,
        operator_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> ChunkWithAnnotationDataListResponse:
        """List a document's chunks, each paired with its annotation.

        Calls
        ``GET /api/annotations/document/{document_id}/chunks-with-annotations``.

        Args:
            document_id (UUID): Document whose chunks to list.
            operator_name (str | None): Restrict to annotations produced by an
                operator with this exact name.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            ChunkWithAnnotationDataListResponse: A page of chunks with their
            annotations (``None`` for a chunk without one).
        """
        response = self._parent._request(
            "GET",
            f"/api/annotations/document/{document_id}/chunks-with-annotations",
            params={"operator_name": operator_name, "skip": skip, "limit": limit},
        )
        return ChunkWithAnnotationDataListResponse.model_validate(response.json())
