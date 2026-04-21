"""``ragnerock get`` and ``ragnerock describe`` commands.

Both commands share the same formatter pipeline and list/get mechanics. They
differ only in the default output format: ``get`` defaults to ``table``,
``describe`` defaults to ``yaml``.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ragnerock.cli.output import OutputFormat, render
from ragnerock.cli.resources import KindSpec, UnknownKindError, resolve_kind
from ragnerock.cli.session import open_session
from ragnerock.resources import Annotation, Chunk, Page
from ragnerock.resources.base import _Resource
from ragnerock.session import Session

_FILTER_HELP = (
    "Repeatable filter in key=value form. Required for some kinds "
    "(e.g. chunk, page require document=...)."
)


def get_cmd(
    kind: Annotated[str, typer.Argument(help="Resource kind (e.g. doc, workflow).")],
    name: Annotated[
        str | None,
        typer.Argument(help="Optional resource name. Omit to list all of this kind."),
    ] = None,
    output: Annotated[
        OutputFormat,
        typer.Option("--output", "-o", help="Output format."),
    ] = OutputFormat.TABLE,
    filters: Annotated[
        list[str] | None,
        typer.Option("--filter", help=_FILTER_HELP),
    ] = None,
) -> None:
    """List resources of a kind, or fetch a single one by name."""
    _run_get(kind, name, output, filters or [])


def describe_cmd(
    kind: Annotated[str, typer.Argument(help="Resource kind.")],
    name: Annotated[str, typer.Argument(help="Resource name.")],
    output: Annotated[
        OutputFormat,
        typer.Option("--output", "-o", help="Output format."),
    ] = OutputFormat.YAML,
) -> None:
    """Fetch a single resource and render it in detail (YAML by default)."""
    _run_get(kind, name, output, [])


def _run_get(
    kind: str,
    name: str | None,
    output: OutputFormat,
    filter_args: list[str],
) -> None:
    try:
        spec = resolve_kind(kind)
    except UnknownKindError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    filters = _parse_filters(filter_args)
    with open_session() as session:
        if name is not None:
            item = _fetch_single(session, spec, name, filters)
            items: list[_Resource] = [item] if item is not None else []
        else:
            items = _fetch_list(session, spec, filters)

    if name is not None and not items:
        typer.echo(f"{spec.kind} {name!r} not found.", err=True)
        raise typer.Exit(code=1)

    render(items, spec, output)


def _parse_filters(raw: list[str]) -> dict[str, str]:
    """Parse ``k=v`` tokens into a dict."""
    out: dict[str, str] = {}
    for token in raw:
        if "=" not in token:
            raise typer.BadParameter(f"Invalid filter {token!r}; expected key=value.")
        key, _, value = token.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            raise typer.BadParameter(f"Invalid filter {token!r}; empty key.")
        out[key] = value
    return out


def _fetch_single(
    session: Session,
    spec: KindSpec,
    name: str,
    filters: dict[str, str],
) -> _Resource | None:
    """Fetch a single resource, preferring lookup-by-name when supported."""
    if spec.cls in (Annotation, Chunk, Page):
        typer.echo(
            f"{spec.kind} does not support lookup by name. "
            "Use list + --filter to scope the result.",
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        result = session.get(spec.cls, name=name)
    except Exception as e:
        raise typer.Exit(code=_exit_for(e)) from e
    return result  # type: ignore[return-value]


def _fetch_list(
    session: Session,
    spec: KindSpec,
    filters: dict[str, str],
) -> list[_Resource]:
    """Fetch a list of resources, applying kind-specific filter translations."""
    kwargs = _translate_list_filters(spec, filters)
    try:
        iterator = session.list(spec.cls, **kwargs)
        return list(iterator.all())  # type: ignore[arg-type]
    except Exception as e:
        raise typer.Exit(code=_exit_for(e)) from e


def _translate_list_filters(spec: KindSpec, filters: dict[str, str]) -> dict[str, str]:
    """Map CLI filter keys to session.list() keyword argument names."""
    aliases = {
        "document": "document_id",
        "chunk": "chunk_id",
        "operator": "operator_id",
        "operator-name": "operator_name",
        "operator_name": "operator_name",
    }
    out: dict[str, str] = {}
    for key, value in filters.items():
        translated = aliases.get(key, key)
        out[translated] = value
    return out


def _exit_for(exc: Exception) -> int:
    """Pick an exit code from an SDK exception.

    1 for user/lookup errors, 2 for anything else (server/network).
    """
    from ragnerock.errors import NotFoundError, ValidationError

    if isinstance(exc, (NotFoundError, ValidationError)):
        typer.echo(f"{type(exc).__name__}: {exc}", err=True)
        return 1
    typer.echo(f"{type(exc).__name__}: {exc}", err=True)
    return 2
