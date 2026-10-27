"""Timestamp types shared by resources and response models.

The API sends timestamps as ISO-8601 strings in UTC. Resources expose them as
timezone-aware :class:`~datetime.datetime` values normalized to UTC, so values
from different endpoints compare and sort correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator


def _empty_str_to_none(value: Any) -> Any:
    """Map an empty string to ``None``.

    Some endpoints send ``""`` for a timestamp that has not happened yet
    (e.g. a job's ``end_time`` while it is running).

    Args:
        value (Any): The raw field value.

    Returns:
        Any: ``None`` for ``""``, otherwise ``value`` unchanged.
    """
    if isinstance(value, str) and value == "":
        return None
    return value


def to_utc(value: datetime | None) -> datetime | None:
    """Normalize a datetime to timezone-aware UTC.

    Naive values are assumed to already be in UTC, which is what the API
    always sends.

    Args:
        value (datetime | None): The datetime to normalize.

    Returns:
        datetime | None: The same instant as an aware UTC datetime, or
        ``None`` when ``value`` is ``None``.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


UtcDatetime = Annotated[
    datetime | None,
    BeforeValidator(_empty_str_to_none),
    AfterValidator(to_utc),
]
"""An optional timestamp normalized to timezone-aware UTC.

Accepts ISO-8601 strings, :class:`~datetime.datetime` values, ``None``, and
``""`` (treated as ``None``).
"""
