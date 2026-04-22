"""Shared context manager for opening a :class:`Session` from env-var config."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import typer

from ragnerock.cli.config import ConfigError, build_engine
from ragnerock.session import Session


@contextmanager
def open_session() -> Iterator[Session]:
    """Yield a connected :class:`Session` sourced from environment variables.

    Builds an :class:`Engine` via :func:`build_engine` (which reads
    ``RAGNEROCK_*`` env vars) and opens a :class:`Session` as a context
    manager, so the session is guaranteed to be closed when the ``with``
    block exits. A :class:`ConfigError` during engine construction is
    converted to a ``typer.Exit(1)`` with a message on stderr, since it
    means the CLI was invoked without its required environment.

    Yields:
        Session: A session ready to issue requests against the configured
        project.

    Raises:
        typer.Exit: Exits with code 1 if the environment is missing or
            malformed.
    """
    try:
        engine = build_engine()
    except ConfigError as e:
        typer.echo(f"ConfigError: {e}", err=True)
        raise typer.Exit(code=1) from e

    with Session(engine) as session:
        yield session
