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
    """Render a Rich table using ``spec.list_columns``."""
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
    """Format a single cell value for table output."""
    if value is None:
        return ""
    if hasattr(value, "name") and isinstance(getattr(value, "name", None), str):
        return value.name
    return str(value)


def _render_json(items: list[_Resource], stream: IO[str]) -> None:
    """Render as a JSON array of ``model_dump(mode='json')`` outputs."""
    payload = [item.model_dump(mode="json") for item in items]
    json.dump(payload, stream, indent=2, default=str)
    stream.write("\n")


def _render_yaml(items: list[_Resource], spec: KindSpec, stream: IO[str]) -> None:
    """Render as a multi-doc YAML stream of ``{kind, metadata, spec}`` documents.

    This is the inverse of the manifest format, so ``get -o yaml`` output
    flows back into ``apply -f -`` unchanged.
    """
    documents = [_to_manifest_doc(item, spec) for item in items]
    if len(documents) == 1:
        yaml.safe_dump(documents[0], stream, sort_keys=False)
    else:
        yaml.safe_dump_all(documents, stream, sort_keys=False)


def _to_manifest_doc(item: _Resource, spec: KindSpec) -> dict[str, Any]:
    """Shape a resource into the ``kind/metadata/spec`` manifest form."""
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
    """Render one display name (or id) per line."""
    for item in items:
        name = resource_name(item)
        if name:
            stream.write(f"{name}\n")
