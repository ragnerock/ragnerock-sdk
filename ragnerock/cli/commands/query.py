"""``ragnerock query`` — run a SQL query against the project's annotations."""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ragnerock.cli.session import open_session


class QueryFormat(str, Enum):
    """Output formats accepted by ``ragnerock query``."""

    TABLE = "table"
    JSON = "json"


def query_cmd(
    sql: Annotated[str, typer.Argument(help="SQL query to execute.")],
    output: Annotated[
        QueryFormat,
        typer.Option("--output", "-o", help="Output format."),
    ] = QueryFormat.TABLE,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Maximum rows to return."),
    ] = 1000,
) -> None:
    """Run a SQL query and print rows."""
    with open_session() as session:
        result = session.query(sql, limit=limit)

    if output is QueryFormat.JSON:
        payload = {
            "columns": result.columns,
            "rows": result.data,
            "row_count": result.row_count,
            "query_time_ms": result.query_time_ms,
        }
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return

    console = Console()
    table = Table(show_header=True, header_style="bold")
    for col in result.columns:
        table.add_column(col)
    for row in result.data:
        table.add_row(*[_cell(row.get(col)) for col in result.columns])
    console.print(table)
    console.print(f"[dim]{result.row_count} row(s) in {result.query_time_ms} ms[/dim]")


def _cell(value: object) -> str:
    return "" if value is None else str(value)
