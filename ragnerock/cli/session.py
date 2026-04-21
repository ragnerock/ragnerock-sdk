"""Shared context manager for opening a :class:`Session` from env-var config."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import typer

from ragnerock.cli.config import ConfigError, build_engine
from ragnerock.session import Session


@contextmanager
def open_session() -> Iterator[Session]:
    """Yield a connected :class:`Session` or exit with a config error.

    Pulls credentials from environment variables (see :mod:`ragnerock.cli.config`),
    constructs an engine, and opens a session context-manager style. On
    :class:`ConfigError`, prints a message to stderr and exits non-zero.
    """
    try:
        engine = build_engine()
    except ConfigError as e:
        typer.echo(f"ConfigError: {e}", err=True)
        raise typer.Exit(code=1) from e

    with Session(engine) as session:
        yield session
