"""Output formatters for CLI resource listings."""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import IO, Any

import yaml
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from ragnerock.cli.resources import KindSpec, resource_name


class OutputFormat(str, Enum):
    """Supported ``-o/--output`` values for ``get``/``describe``."""

    TABLE = "table"
    JSON = "json"
    YAML = "yaml"
    NAME = "name"


def render(
    items: list[BaseModel],
    spec: KindSpec,
    fmt: OutputFormat,
    *,
    stream: IO[str] | None = None,
) -> None:
    """Write ``items`` to ``stream`` in the requested format.

    Args:
        items (list[BaseModel]): Resources of the same kind.
        spec (KindSpec): Kind metadata (used for column layout + YAML kind field).
        fmt (OutputFormat): Desired output format.
        stream (IO[str] | None): Where to write. Defaults to ``sys.stdout``.
    """
    out = stream if stream is not None else sys.stdout

    if fmt is OutputFormat.TABLE:
        _render_table(items, spec, out)
    elif fmt is OutputFormat.JSON:
        _render_json(items, out)
    elif fmt is OutputFormat.YAML:
        _render_yaml(items, spec, out)
    elif fmt is OutputFormat.NAME:
        _render_name(items, out)


def _render_table(items: list[BaseModel], spec: KindSpec, stream: IO[str]) -> None:
    """Render a Rich table using ``spec.list_columns``.

    Empty result sets emit a ``"No <kind> resources found."`` line instead
    of a headers-only table, since a blank table is visually confusing.

    Args:
        items (list[BaseModel]): Resources to display.
        spec (KindSpec): Kind metadata; ``list_columns`` drives column layout.
        stream (IO[str]): Destination stream. Terminal detection is based on
            this stream's ``isatty()``.
    """
    console = Console(file=stream, force_terminal=stream.isatty())
    table = Table(show_header=True, header_style="bold")
    for header, _ in spec.list_columns:
        table.add_column(header)
    for item in items:
        row = [
            _cell(getattr(item, field_name, None))
            for _, field_name in spec.list_columns
        ]
        table.add_row(*row)
    if not items:
        console.print(f"No {spec.kind} resources found.")
        return
    console.print(table)


def _cell(value: Any) -> str:
    """Format a single cell value for table output.

    Enums and similar objects that carry a ``name`` string attribute are
    displayed by that name (so ``ChunkType.PARAGRAPH`` renders as
    ``"PARAGRAPH"`` rather than its integer value). ``None`` becomes an
    empty string.

    Args:
        value (Any): Raw attribute value from the resource.

    Returns:
        str: Display-ready cell text.
    """
    if value is None:
        return ""
    if hasattr(value, "name") and isinstance(getattr(value, "name", None), str):
        return value.name
    return str(value)


def _render_json(items: list[BaseModel], stream: IO[str]) -> None:
    """Render resources as a JSON array of ``model_dump(mode='json')`` outputs.

    ``default=str`` is used so stray UUIDs or datetimes that slip through
    pydantic's JSON mode still serialize cleanly rather than raising.

    Args:
        items (list[BaseModel]): Resources to serialize.
        stream (IO[str]): Destination stream; the array is followed by a
            trailing newline.
    """
    payload = [item.model_dump(mode="json") for item in items]
    json.dump(payload, stream, indent=2, default=str)
    stream.write("\n")


def _render_yaml(items: list[BaseModel], spec: KindSpec, stream: IO[str]) -> None:
    """Render resources as YAML: one document per resource.

    Each document is the resource's JSON-mode field dump. A single item
    emits one document; multiple items emit a YAML stream. (To manage
    configuration declaratively, write GitOps manifests and use
    ``ragnerock apply``.)

    Args:
        items (list[BaseModel]): Resources to serialize.
        spec (KindSpec): Kind metadata (unused; kept for a uniform signature).
        stream (IO[str]): Destination stream.
    """
    documents = [item.model_dump(mode="json") for item in items]
    if len(documents) == 1:
        yaml.safe_dump(documents[0], stream, sort_keys=False)
    else:
        yaml.safe_dump_all(documents, stream, sort_keys=False)


def _render_name(items: list[BaseModel], stream: IO[str]) -> None:
    """Render one display name (or id) per line.

    Resources without a usable name — :func:`resource_name` returns an empty
    string — are skipped rather than producing blank lines, so downstream
    tools like ``xargs`` don't trip on them.

    Args:
        items (list[BaseModel]): Resources to name.
        stream (IO[str]): Destination stream.
    """
    for item in items:
        name = resource_name(item)
        if name:
            stream.write(f"{name}\n")
