"""Error hierarchy for the Ragnerock SDK."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ragnerock.resources.base import _Resource


class RagnerockError(Exception):
    """Base exception for every error the SDK raises.

    Attributes:
        message (str): Human-readable error message.
        status_code (int | None): HTTP status code from the API response, if
            applicable.
        suggestion (str | None): Optional suggestion for how to fix the error.
        details (dict[str, Any] | None): Additional structured error details
            from the API.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the exception with structured fields from the API.

        Args:
            message (str): Human-readable error message.
            status_code (int | None): HTTP status code from the response, if
                the error originated from an HTTP call.
            suggestion (str | None): Actionable hint returned by the server
                describing how to fix the request.
            details (dict[str, Any] | None): Extra structured error context
                from the server.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.suggestion = suggestion
        self.details = details

    def __str__(self) -> str:
        parts: list[str] = []
        if self.status_code is not None:
            parts.append(f"[{self.status_code}]")
        parts.append(self.message)
        s = " ".join(parts)
        if self.suggestion:
            s += f" (Suggestion: {self.suggestion})"
        return s


class AuthenticationError(RagnerockError):
    """Raised when authentication fails (invalid credentials, expired token)."""


class NotFoundError(RagnerockError):
    """Raised when a requested resource does not exist."""


class ValidationError(RagnerockError):
    """Raised when request parameters are invalid or preconditions fail."""


class RateLimitError(RagnerockError):
    """Raised when the API returns HTTP 429 after retries have been exhausted.

    Attributes:
        retry_after (float | None): Seconds to wait before retrying, parsed
            from the response's ``Retry-After`` header when present. ``None``
            if the server didn't send one (or it couldn't be parsed).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Initialize a rate-limit error.

        Args:
            message (str): Human-readable error message.
            status_code (int | None): HTTP status code (typically 429).
            suggestion (str | None): Actionable hint from the server.
            details (dict[str, Any] | None): Extra structured error context.
            retry_after (float | None): Seconds to wait before retrying, when
                the server provided a ``Retry-After`` header.
        """
        super().__init__(
            message,
            status_code=status_code,
            suggestion=suggestion,
            details=details,
        )
        self.retry_after = retry_after


class QueryError(RagnerockError):
    """Raised when an annotation SQL query fails.

    Attributes:
        error_code (str | None): Structured error code from the query engine.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the exception with query-engine fields.

        Args:
            message (str): Human-readable error message.
            status_code (int | None): HTTP status code from the response.
            error_code (str | None): Structured code from the query engine
                (e.g. a parse error or unknown-column code). Presence of this
                field is what distinguishes query errors from generic 4xx/5xx.
            suggestion (str | None): Actionable hint returned by the server.
            details (dict[str, Any] | None): Extra structured error context.
        """
        super().__init__(
            message,
            status_code=status_code,
            suggestion=suggestion,
            details=details,
        )
        self.error_code = error_code


class CommitError(RagnerockError):
    """Raised when ``session.commit()`` fails partway through a batch.

    The API has no transaction primitive, so ops that succeeded before the
    failure stay applied server-side. This exception records what made it
    through and what is still pending so the caller can recover.

    Attributes:
        committed (list[_Resource]): Resources whose server-side write
            succeeded before the failure.
        pending (list[_Resource]): Resources whose write was never attempted
            (or failed, in slot 0).
        cause (Exception): The underlying exception that triggered the abort.
    """

    def __init__(
        self,
        message: str,
        *,
        committed: list[_Resource],
        pending: list[_Resource],
        cause: Exception,
    ) -> None:
        """Record where the batch failed so the caller can recover.

        Args:
            message (str): Human-readable description of the failure.
            committed (list[_Resource]): Resources that were successfully
                written before the abort. These are live server-side.
            pending (list[_Resource]): Resources whose write was never
                attempted, plus the one that failed. Safe to retry once the
                underlying issue is resolved.
            cause (Exception): The exception that triggered the abort.
        """
        super().__init__(message)
        self.committed = committed
        self.pending = pending
        self.cause = cause


def _parse_detail(
    response_text: str,
) -> tuple[str, str | None, dict[str, Any] | None, str | None]:
    """Extract structured error fields from an API error response body.

    The Ragnerock API wraps errors in either ``{"detail": {...}}`` (the common
    case) or ``{"detail": [...]}`` (FastAPI validation errors). This helper
    pulls out the human-readable message, an optional suggestion, any
    additional details dict, and a query-engine error code when present.
    Bodies that are empty, non-JSON, or not shaped like an error envelope
    fall through to a plain-text message with the other fields unset.

    Args:
        response_text (str): Raw response body from an HTTP 4xx/5xx response.

    Returns:
        tuple[str, str | None, dict[str, Any] | None, str | None]: A 4-tuple
        of ``(message, suggestion, details, error_code)``.
    """
    message = response_text or ""
    suggestion: str | None = None
    details: dict[str, Any] | None = None
    error_code: str | None = None

    if not response_text:
        return message, suggestion, details, error_code

    try:
        payload = json.loads(response_text)
    except (ValueError, TypeError):
        return message, suggestion, details, error_code

    if not isinstance(payload, dict):
        return message, suggestion, details, error_code

    detail = payload.get("detail", payload)

    if isinstance(detail, dict):
        message = detail.get("message") or payload.get("message") or response_text
        suggestion = detail.get("suggestion")
        details = detail.get("details")
        error_code = detail.get("error_code")
    elif isinstance(detail, list):
        message = json.dumps(detail)
        details = {"errors": detail}
    else:
        message = str(detail)

    return message, suggestion, details, error_code


def raise_for_status(
    status_code: int,
    response_text: str,
    *,
    retry_after: float | None = None,
) -> None:
    """Raise the most specific SDK exception for an HTTP error response.

    No-ops for 2xx/3xx statuses. For 4xx/5xx, parses the body and picks the
    subclass that best describes the failure: ``QueryError`` when the server
    returned a query-engine error code, ``AuthenticationError`` for 401/403,
    ``NotFoundError`` for 404, ``ValidationError`` for 422,
    ``RateLimitError`` for 429, and the base ``RagnerockError`` for everything
    else.

    Args:
        status_code (int): HTTP status code from the response.
        response_text (str): Raw response body, used to extract error
            details.
        retry_after (float | None): Parsed ``Retry-After`` value, attached
            to ``RateLimitError`` when ``status_code`` is 429.

    Raises:
        RagnerockError: Or a subclass matching ``status_code``.
    """
    if status_code < 400:
        return

    message, suggestion, details, error_code = _parse_detail(response_text)

    if error_code is not None:
        raise QueryError(
            message,
            status_code=status_code,
            error_code=error_code,
            suggestion=suggestion,
            details=details,
        )

    if status_code in (401, 403):
        raise AuthenticationError(
            message,
            status_code=status_code,
            suggestion=suggestion,
            details=details,
        )
    if status_code == 404:
        raise NotFoundError(
            message,
            status_code=status_code,
            suggestion=suggestion,
            details=details,
        )
    if status_code == 422:
        raise ValidationError(
            message,
            status_code=status_code,
            suggestion=suggestion,
            details=details,
        )
    if status_code == 429:
        raise RateLimitError(
            message,
            status_code=status_code,
            suggestion=suggestion,
            details=details,
            retry_after=retry_after,
        )

    raise RagnerockError(
        message,
        status_code=status_code,
        suggestion=suggestion,
        details=details,
    )
