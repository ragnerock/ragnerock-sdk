"""``ragnerock version`` — print the installed SDK version."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import typer


def version_cmd() -> None:
    """Print the installed ``ragnerock`` package version."""
    try:
        typer.echo(version("ragnerock"))
    except (
        PackageNotFoundError
    ):  # pragma: no cover — only hits for source trees without metadata
        typer.echo("unknown")
