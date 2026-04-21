"""``ragnerock delete`` — remove resources by name or manifest."""

from __future__ import annotations

from typing import Annotated

import typer

from ragnerock.cli.manifest import ManifestError, read_manifests
from ragnerock.cli.resources import KindSpec, UnknownKindError, resolve_kind
from ragnerock.cli.session import open_session
from ragnerock.resources import Annotation, Chunk, Page
from ragnerock.session import Session


def delete_cmd(
    kind: Annotated[
        str | None,
        typer.Argument(help="Resource kind. Omit when using -f."),
    ] = None,
    name: Annotated[
        str | None,
        typer.Argument(help="Resource name. Required when kind is given."),
    ] = None,
    files: Annotated[
        list[str] | None,
        typer.Option(
            "--file",
            "-f",
            help="Delete resources listed in manifest(s). Use '-' for STDIN.",
        ),
    ] = None,
) -> None:
    """Delete one resource by ``kind name``, or every resource in -f files."""
    if files:
        _delete_from_files(files)
        return

    if not kind or not name:
        raise typer.BadParameter("delete requires either <kind> <name> or -f <file>.")

    try:
        spec = resolve_kind(kind)
    except UnknownKindError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    with open_session() as session:
        _delete_one(session, spec, name)


def _delete_from_files(sources: list[str]) -> None:
    try:
        docs = read_manifests(sources)
    except ManifestError as e:
        typer.echo(f"ManifestError: {e}", err=True)
        raise typer.Exit(code=1) from e

    with open_session() as session:
        for doc in docs:
            _delete_one(session, doc.spec_kind, doc.name)


def _delete_one(session: Session, spec: KindSpec, name: str) -> None:
    if spec.cls in (Annotation, Chunk, Page):
        typer.echo(
            f"{spec.kind} does not support name-based delete in the CLI.",
            err=True,
        )
        raise typer.Exit(code=1)

    resource = session.get(spec.cls, name=name)
    if resource is None:
        typer.echo(f"{spec.kind.lower()}/{name} not found", err=True)
        raise typer.Exit(code=1)
    session.delete(resource)
    session.commit()
    typer.echo(f"{spec.kind.lower()}/{name} deleted")
