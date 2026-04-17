"""Base resource class.

All resource types (``Document``, ``Chunk``, ``Annotation``, …) inherit
from ``_Resource``. A resource is a plain pydantic model with a back-reference
to the ``Session`` that fetched or created it, so it can offer convenience
methods like ``doc.list(Chunk)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, PrivateAttr

if TYPE_CHECKING:
    from ragnerock.iterator import PaginatedIterator
    from ragnerock.session import Session


class _Resource(BaseModel):
    """Base class for every SDK resource.

    Resources are plain pydantic models. After a resource is returned from a
    session call, its ``_session`` back-reference is set, which enables
    convenience navigation methods.

    The ``_session`` attribute is private and excluded from serialization.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _session: Session | None = PrivateAttr(default=None)

    def _bind(self, session: Session) -> None:
        """Attach a session reference. Called by the session, not by users."""
        self._session = session

    @property
    def _is_bound(self) -> bool:
        return self._session is not None

    def list(self, resource_type: type[_Resource], **kwargs: Any) -> PaginatedIterator[Any]:
        """Convenience: list related resources via the bound session.

        For example, ``document.list(Chunk)`` is equivalent to
        ``session.list(Chunk, document_id=document.id)``.
        """
        if self._session is None:
            raise RuntimeError(
                f"{type(self).__name__} is not bound to a session; "
                "cannot list related resources."
            )
        return self._session._list_related(self, resource_type, **kwargs)
