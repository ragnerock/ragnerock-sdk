"""Output formatters for CLI resource listings."""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import IO, Any

import yaml
from rich.console import Console
from rich.table import Table

from ragnerock.cli.manifest import DEFAULT_API_VERSION
from ragnerock.cli.resources import KindSpec, resource_name
from ragnerock.resources.base import _Resource


class OutputFormat(str, Enum):
    """Supported ``-o/--output`` values for ``get``/``describe``."""

    TABLE = "table"
    JSON = "json"
    YAML = "yaml"
    NAME = "name"


def render(
    items: list[_Resource],
    spec: KindSpec,
    fmt: OutputFormat,
    *,
    stream: IO[str] | None = None,
) -> None:
    """Write ``items`` to ``stream`` in the requested format.

    Args:
        items (list[_Resource]): Resources of the same kind.
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


def _render_table(items: list[_Resource], spec: KindSpec, stream: IO[str]) -> None:
    """Render a Rich table using ``spec.list_columns``.

    Empty result sets emit a ``"No <kind> resources found."`` line instead
    of a headers-only table, since a blank table is visually confusing.

    Args:
        items (list[_Resource]): Resources to display.
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


def _render_json(items: list[_Resource], stream: IO[str]) -> None:
    """Render resources as a JSON array of ``model_dump(mode='json')`` outputs.

    ``default=str`` is used so stray UUIDs or datetimes that slip through
    pydantic's JSON mode still serialize cleanly rather than raising.

    Args:
        items (list[_Resource]): Resources to serialize.
        stream (IO[str]): Destination stream; the array is followed by a
            trailing newline.
    """
    payload = [item.model_dump(mode="json") for item in items]
    json.dump(payload, stream, indent=2, default=str)
    stream.write("\n")


def _render_yaml(items: list[_Resource], spec: KindSpec, stream: IO[str]) -> None:
    """Render resources as a YAML manifest stream.

    Each item is shaped into a ``{apiVersion, kind, metadata, spec}``
    document. This is the inverse of the manifest format, so ``get -o yaml``
    output flows back into ``apply -f -`` unchanged. A single item emits
    one document; multiple items emit a YAML stream.

    Args:
        items (list[_Resource]): Resources to serialize.
        spec (KindSpec): Kind metadata; supplies the ``kind`` field on each
            document.
        stream (IO[str]): Destination stream.
    """
    documents = [_to_manifest_doc(item, spec) for item in items]
    if len(documents) == 1:
        yaml.safe_dump(documents[0], stream, sort_keys=False)
    else:
        yaml.safe_dump_all(documents, stream, sort_keys=False)


def _to_manifest_doc(item: _Resource, spec: KindSpec) -> dict[str, Any]:
    """Shape a resource into the ``{kind, metadata, spec}`` manifest form.

    Identity fields (``name``, ``operator_name``, ``id``, ``root_id``) are
    lifted out of the model's field dump into ``metadata``; everything else
    stays under ``spec``. This mirrors how :mod:`ragnerock.cli.manifest`
    parses inputs.

    Args:
        item (_Resource): Resource to shape.
        spec (KindSpec): Kind metadata; supplies the ``kind`` label.

    Returns:
        dict[str, Any]: Manifest-shaped document ready for YAML dump.
    """
    data = item.model_dump(mode="json")

    name = data.pop("name", None) or data.pop("operator_name", None)
    metadata: dict[str, Any] = {}
    if name is not None:
        metadata["name"] = name

    rid = data.pop("id", None) or data.pop("root_id", None)
    if rid is not None:
        metadata["id"] = rid

    return {
        "apiVersion": DEFAULT_API_VERSION,
        "kind": spec.kind,
        "metadata": metadata,
        "spec": data,
    }


def _render_name(items: list[_Resource], stream: IO[str]) -> None:
    """Render one display name (or id) per line.

    Resources without a usable name — :func:`resource_name` returns an empty
    string — are skipped rather than producing blank lines, so downstream
    tools like ``xargs`` don't trip on them.

    Args:
        items (list[_Resource]): Resources to name.
        stream (IO[str]): Destination stream.
    """
    for item in items:
        name = resource_name(item)
        if name:
            stream.write(f"{name}\n")
