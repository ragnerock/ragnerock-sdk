"""Shared building blocks for the low-level client: base models and helpers."""

from __future__ import annotations

import email.utils
import json
import time
from collections.abc import Iterator
from enum import Enum
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from ragnerock.client._client import RagnerockClient


class _ApiModel(BaseModel):
    """Base pydantic model for Ragnerock API response payloads.

    Allows extra fields so the SDK stays forward-compatible with additive
    server-side schema changes. Subclasses declare only the fields callers
    commonly read; everything else the server sends is still reachable as an
    attribute (or via :meth:`~pydantic.BaseModel.model_dump`).
    """

    model_config = ConfigDict(extra="allow")


class MessageResponse(_ApiModel):
    """Generic acknowledgement payload returned by action endpoints."""

    message: str | None = None


class _Unset:
    """Sentinel type for "leave this field unchanged" in update calls.

    Update methods use :data:`UNSET` as the default for fields that can be
    explicitly cleared, so ``None`` can mean "clear it" while an omitted
    argument means "don't touch it".
    """

    _instance: _Unset | None = None

    def __new__(cls) -> _Unset:
        """Return the single shared instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        """Render as ``UNSET``."""
        return "UNSET"

    def __bool__(self) -> bool:
        """Treat the sentinel as falsy."""
        return False


UNSET: Final = _Unset()
"""Default for update arguments where ``None`` means "clear the field"."""


def _drop_none(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of ``data`` with ``None`` values removed.

    Used to build query-string and form payloads without pushing explicit
    ``null``s over the wire — the API distinguishes "field omitted" from
    "field set to null" on some endpoints.

    Args:
        data (dict[str, Any]): Dict to filter.

    Returns:
        dict[str, Any]: A new dict containing only the entries with non-``None`` values.
    """
    return {k: v for k, v in data.items() if v is not None}


def _drop_unset(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of ``data`` with :data:`UNSET` values removed.

    Unlike :func:`_drop_none`, explicit ``None`` values are kept, so they reach
    the server as JSON ``null`` and clear the field.

    Args:
        data (dict[str, Any]): Dict to filter.

    Returns:
        dict[str, Any]: A new dict without the entries left at :data:`UNSET`.
    """
    return {k: v for k, v in data.items() if v is not UNSET}


def _jsonable(value: Any) -> Any:
    """Recursively convert a value into something :mod:`json` can encode.

    UUIDs become strings, enums become their values, pydantic models are
    dumped in JSON mode, and dicts, lists, and tuples are converted
    element-wise. Everything else passes through unchanged.

    Args:
        value (Any): The value to convert.

    Returns:
        Any: A JSON-encodable equivalent.
    """
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _body(**fields: Any) -> dict[str, Any]:
    """Build a JSON request body from keyword arguments.

    Drops ``None`` and :data:`UNSET` values and converts UUIDs, enums, and
    models to their JSON form. Use :func:`_patch_body` when ``None`` must be
    sent to clear a field.

    Args:
        **fields: Candidate body fields.

    Returns:
        dict[str, Any]: The JSON-ready body.
    """
    return {
        k: _jsonable(v) for k, v in fields.items() if v is not None and v is not UNSET
    }


def _patch_body(**fields: Any) -> dict[str, Any]:
    """Build a JSON request body for a partial update.

    Drops only :data:`UNSET` values, so an explicit ``None`` is sent as
    ``null`` and clears the field server-side.

    Args:
        **fields: Candidate body fields.

    Returns:
        dict[str, Any]: The JSON-ready body.
    """
    return {k: _jsonable(v) for k, v in _drop_unset(fields).items()}


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value into seconds.

    RFC 7231 allows either a non-negative integer (delta-seconds) or an
    HTTP-date. Returns ``None`` if the header is absent, unparseable, or
    negative.

    Args:
        value (str | None): Raw header value, or ``None``.

    Returns:
        float | None: Seconds to wait, clamped at zero on the low end.
    """
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        seconds = float(s)
    except ValueError:
        seconds = None
    if seconds is not None:
        return max(0.0, seconds)
    parsed = email.utils.parsedate_to_datetime(s)
    if parsed is None:
        return None
    delta = parsed.timestamp() - time.time()
    return max(0.0, delta)


def _stringify_uuids(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce any UUID values (including those inside lists) to strings.

    The Ragnerock API accepts string UUIDs; this avoids scattering ``str(...)``
    calls through every JSON body builder.

    Args:
        data (dict[str, Any]): Dict whose values may contain UUIDs or lists of UUIDs.

    Returns:
        dict[str, Any]: A new dict with UUIDs serialized to strings. Non-UUID values, and
        non-UUID entries inside lists, are passed through unchanged.
    """
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, UUID):
            out[k] = str(v)
        elif isinstance(v, list):
            out[k] = [str(x) if isinstance(x, UUID) else x for x in v]
        else:
            out[k] = v
    return out


def _csv(values: list[UUID] | list[str] | None) -> str | None:
    """Join a list of ids into the comma-separated form list endpoints accept.

    Args:
        values (list[UUID] | list[str] | None): Ids to join, or ``None``.

    Returns:
        str | None: ``"a,b,c"``, or ``None`` when ``values`` is ``None`` or empty.
    """
    if not values:
        return None
    return ",".join(str(v) for v in values)


def _iter_sse_data(response: httpx.Response) -> Iterator[str]:
    """Yield the ``data`` payload of each Server-Sent Event in a response.

    Multi-line ``data:`` fields are joined with newlines, comments and other
    fields are ignored, and an event is emitted at each blank line.

    Args:
        response (httpx.Response): A streaming response.

    Yields:
        str: One event's data payload.
    """
    buffer: list[str] = []
    for line in response.iter_lines():
        if not line:
            if buffer:
                yield "\n".join(buffer)
                buffer = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if field == "data":
            buffer.append(value[1:] if value.startswith(" ") else value)
    if buffer:
        yield "\n".join(buffer)


def _iter_ndjson(response: httpx.Response) -> Iterator[dict[str, Any]]:
    """Yield one decoded JSON object per non-empty line of a streaming response.

    Args:
        response (httpx.Response): A streaming response.

    Yields:
        dict[str, Any]: One decoded line.
    """
    for line in response.iter_lines():
        if line.strip():
            yield json.loads(line)


class _Section:
    """Base class for endpoint sections. Holds a reference to the parent client."""

    def __init__(self, parent: RagnerockClient) -> None:
        """Store a back-reference to the owning client.

        Args:
            parent (RagnerockClient): The client whose HTTP session and auth token this section
                will use.
        """
        self._parent = parent
