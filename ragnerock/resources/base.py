"""Base resource class.

All resource types (``Document``, ``Chunk``, ``Annotation``, …) inherit
from ``_Resource``. A resource is a plain pydantic model with a back-reference
to the ``Session`` that fetched or created it, so it can offer convenience
methods like ``doc.list(Chunk)``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, PrivateAttr

if TYPE_CHECKING:
    from ragnerock.iterator import PaginatedIterator
    from ragnerock.session import Session


def _empty_str_to_none(value: Any) -> Any:
    if isinstance(value, str) and value == "":
        return None
    return value


OptionalDateTime = Annotated[datetime | None, BeforeValidator(_empty_str_to_none)]


class _Resource(BaseModel):
    """Base class for every SDK resource.

    Resources are plain pydantic models. After a resource is returned from a
    session call, its ``_session`` back-reference is set, which enables
    convenience navigation methods.

    The ``_session`` attribute is private and excluded from serialization.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    _session: Session | None = PrivateAttr(default=None)

    def _bind(self, session: Session) -> None:
        """Attach a session back-reference to this resource.

        Called by the session whenever it returns a resource to the caller.
        Users should not call this directly.

        Args:
            session (Session): The session that produced this resource.
        """
        self._session = session

    @property
    def _is_bound(self) -> bool:
        """Whether this resource has a session back-reference attached.

        Returns:
            bool: ``True`` if a session is attached, ``False`` otherwise.
        """
        return self._session is not None

    def list(
        self, resource_type: type[_Resource], **kwargs: Any
    ) -> PaginatedIterator[Any]:
        """List related resources via the bound session.

        This is sugar for ``session.list(resource_type, <parent_id>=self.id)``.
        For example, ``document.list(Chunk)`` is equivalent to
        ``session.list(Chunk, document_id=document.id)``.

        Args:
            resource_type (type[_Resource]): The related resource class to
                list.
            **kwargs (Any): Additional filters forwarded to the session. The
                parent id filter is supplied automatically.

        Returns:
            PaginatedIterator[Any]: A lazy paginated iterator over the
            related resources.

        Raises:
            RuntimeError: If this resource has no session back-reference
                (e.g. it was constructed locally and never committed).
            TypeError: If the bound session does not know how to navigate from
                this resource type to ``resource_type``.
        """
        if self._session is None:
            raise RuntimeError(
                f"{type(self).__name__} is not bound to a session; "
                "cannot list related resources."
            )
        return self._session._list_related(self, resource_type, **kwargs)
