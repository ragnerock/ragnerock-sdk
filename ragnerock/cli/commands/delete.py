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
    _require_deletable(spec)

    with open_session() as session:
        _delete_one(session, spec, name)


def _require_deletable(spec: KindSpec) -> None:
    """Exit with code 1 unless ``delete <kind> <name>`` supports this kind.

    Annotations need an id, chunks and pages are server-managed, and the
    remaining kinds are read-only in the CLI.

    Args:
        spec (KindSpec): The resolved kind.

    Raises:
        typer.Exit: With code 1 if the kind is not deletable by name.
    """
    if spec.deletable and spec.cls is not None:
        return
    supported = ", ".join(s.kind for s in all_kinds() if s.deletable)
    typer.echo(
        f"{spec.kind} does not support name-based delete in the CLI "
        f"(supported: {supported}).",
        err=True,
    )
    raise typer.Exit(code=1)


def _delete_one(session: Session, spec: KindSpec, name: str) -> None:
    """Delete a single resource by kind and name.

    Args:
        session (Session): Open session used to look up and stage the delete.
        spec (KindSpec): A deletable resource kind.
        name (str): Name of the resource to delete.

    Raises:
        typer.Exit: Exits with code 1 if no resource with that name exists.
    """
    assert spec.cls is not None
    resource = session.get(spec.cls, name=name)
    if resource is None:
        typer.echo(f"{spec.kind.lower()}/{name} not found", err=True)
        raise typer.Exit(code=1)
    session.delete(resource)
    session.commit()
    typer.echo(f"{spec.kind.lower()}/{name} deleted")
