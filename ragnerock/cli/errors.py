"""Shared error reporting for CLI commands.

Exit codes: ``0`` success, ``1`` a user or input error (bad arguments, a
missing resource, an invalid manifest, a failed apply), ``2`` a server or
network error.
"""

from __future__ import annotations

import typer

from ragnerock.errors import GitOpsError, NotFoundError, ValidationError

USER_ERROR = 1
"""Exit code for user, lookup, and input errors."""

SERVER_ERROR = 2
"""Exit code for server and network errors."""


def exit_code_for(exc: Exception) -> int:
    """Report an exception on stderr and pick the matching exit code.

    Args:
        exc (Exception): The error to report.

    Returns:
        int: :data:`USER_ERROR` for lookup, validation, and GitOps
        preparation errors; :data:`SERVER_ERROR` for everything else.
    """
    typer.echo(f"{type(exc).__name__}: {exc}", err=True)
    if isinstance(exc, (NotFoundError, ValidationError, GitOpsError)):
        return USER_ERROR
    return SERVER_ERROR
