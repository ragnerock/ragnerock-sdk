"""Annotation resource for operator-produced annotations on documents, chunks, or pages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from ragnerock.resources.base import OptionalDateTime, _Resource

if TYPE_CHECKING:
    from ragnerock.resources.chunk import Chunk
    from ragnerock.resources.document import Document
    from ragnerock.resources.operator import Operator
    from ragnerock.resources.page import Page


class Annotation(_Resource):
    """An annotation produced by an operator, attached to a document, chunk, or page.

    Exactly one target id (``document_id``, ``chunk_id``, ``page_id``, or for
    tabular sources ``row_id`` / ``sheet_id``) is typically set, depending on
    the operator's ``chunk_type``. The server-assigned
    identity is carried on ``root_id``; the :attr:`id` property exposes it
    under the same name used by every other resource.
    """

    root_id: UUID | None = None
    operator_id: UUID | None = None
    operator_name: str | None = None
    schema_id: UUID | None = None
    document_id: UUID | None = None
    chunk_id: UUID | None = None
    page_id: UUID | None = None
    row_id: UUID | None = None
    sheet_id: UUID | None = None
    data: dict[str, Any] | None = None
    confidence_score: float | None = None
    generation_metadata: dict[str, Any] | None = None
    created_by_id: UUID | None = None
    updated_by_id: UUID | None = None
    created_at: OptionalDateTime = None
    updated_at: OptionalDateTime = None

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

    def _require_session(self, what: str) -> Any:
        """Return the bound session, or raise if there is none.

        Args:
            what (str): The thing being fetched, for the error message.

        Returns:
            Any: The bound session.

        Raises:
            RuntimeError: If the annotation is not bound to a session.
        """
        if self._session is None:
            raise RuntimeError(
                f"Annotation is not bound to a session; cannot fetch {what}."
            )
        return self._session

    @property
    def document(self) -> Document | None:
        """The document this annotation belongs to, fetched on access.

        Returns:
            Document | None: The document, or ``None`` if ``document_id`` is
            unset or the document no longer exists.

        Raises:
            RuntimeError: If the annotation is not bound to a session.
        """
        from ragnerock.resources.document import Document

        if self.document_id is None:
            return None
        return self._require_session("its document").get(Document, id=self.document_id)

    @property
    def chunk(self) -> Chunk | None:
        """The chunk this annotation is attached to, fetched on access.

        Returns:
            Chunk | None: The chunk, or ``None`` for annotations not attached
            to a chunk.

        Raises:
            RuntimeError: If the annotation is not bound to a session.
        """
        from ragnerock.resources.chunk import Chunk

        if self.chunk_id is None:
            return None
        return self._require_session("its chunk").get(Chunk, id=self.chunk_id)

    @property
    def page(self) -> Page | None:
        """The page this annotation is attached to, fetched on access.

        Returns:
            Page | None: The page, or ``None`` for annotations not attached
            to a page.

        Raises:
            RuntimeError: If the annotation is not bound to a session.
        """
        from ragnerock.resources.page import Page

        if self.page_id is None:
            return None
        return self._require_session("its page").get(Page, id=self.page_id)

    @property
    def operator(self) -> Operator | None:
        """The operator that produced this annotation, fetched on access.

        Returns:
            Operator | None: The operator, or ``None`` if ``operator_id`` is
            unset or the operator no longer exists.

        Raises:
            RuntimeError: If the annotation is not bound to a session.
        """
        from ragnerock.resources.operator import Operator

        if self.operator_id is None:
            return None
        return self._require_session("its operator").get(Operator, id=self.operator_id)
