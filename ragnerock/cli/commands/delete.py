"""``ragnerock delete`` — remove a resource by kind and name."""

from __future__ import annotations

from typing import Annotated

import typer

from ragnerock.cli.resources import KindSpec, UnknownKindError, all_kinds, resolve_kind
from ragnerock.cli.session import open_session
from ragnerock.session import Session


def delete_cmd(
    kind: Annotated[
        str, typer.Argument(help="Resource kind, e.g. 'doc' or 'workflow'.")
    ],
    name: Annotated[str, typer.Argument(help="Resource name.")],
) -> None:
    """Delete one resource by ``kind name``.

    GitOps apply never deletes, so this is how objects are removed from the
    CLI. Supported kinds: Document, DocumentGroup, Operator, Workflow.
    """
    try:
        spec = resolve_kind(kind)
    except UnknownKindError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    with open_session() as session:
        _delete_one(session, spec, name)


def _delete_one(session: Session, spec: KindSpec, name: str) -> None:
    """Delete a single resource by kind and name.

    Only kinds marked ``deletable`` are accepted: annotations need an id,
    chunks and pages are server-managed, and the remaining kinds are
    read-only in the CLI.

    Args:
        session (Session): Open session used to look up and stage the delete.
        spec (KindSpec): Resource kind resolved from the CLI argument.
        name (str): Name of the resource to delete.

    Raises:
        typer.Exit: Exits with code 1 if the kind is not delete-by-name, or
            if no resource with that name exists.
    """
    if not spec.deletable or spec.cls is None:
        supported = ", ".join(s.kind for s in all_kinds() if s.deletable)
        typer.echo(
            f"{spec.kind} does not support name-based delete in the CLI "
            f"(supported: {supported}).",
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
