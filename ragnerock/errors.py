"""Error hierarchy for the Ragnerock SDK."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ragnerock.resources.base import _Resource


class RagnerockError(Exception):
    """Base exception for every error the SDK raises.

    Attributes:
        message: Human-readable error message.
        status_code: HTTP status code from the API response, if applicable.
        suggestion: Optional suggestion for how to fix the error.
        details: Additional structured error details from the API.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
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


class QueryError(RagnerockError):
    """Raised when an annotation SQL query fails.

    Attributes:
        error_code: Structured error code from the query engine.
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
        committed: Resources whose server-side write succeeded before the failure.
        pending: Resources whose write was never attempted (or failed, in slot 0).
        cause: The underlying exception that triggered the abort.
    """

    def __init__(
        self,
        message: str,
        *,
        committed: list[_Resource],
        pending: list[_Resource],
        cause: Exception,
    ) -> None:
        super().__init__(message)
        self.committed = committed
        self.pending = pending
        self.cause = cause


def _parse_detail(response_text: str) -> tuple[str, str | None, dict[str, Any] | None, str | None]:
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


def raise_for_status(status_code: int, response_text: str) -> None:
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

    raise RagnerockError(
        message,
        status_code=status_code,
        suggestion=suggestion,
        details=details,
    )
