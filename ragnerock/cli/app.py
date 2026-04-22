"""Top-level Typer app for the ``ragnerock`` CLI."""

from __future__ import annotations

import typer

from ragnerock.cli.commands.apply import apply_cmd
from ragnerock.cli.commands.delete import delete_cmd
from ragnerock.cli.commands.get import describe_cmd, get_cmd
from ragnerock.cli.commands.query import query_cmd
from ragnerock.cli.commands.run import run_cmd
from ragnerock.cli.commands.version import version_cmd

app = typer.Typer(
    name="ragnerock",
    help=(
        "kubectl-style CLI for the Ragnerock SDK. "
        "Inspect resources, apply YAML manifests, and run workflows."
    ),
    no_args_is_help=True,
    add_completion=False,
)

app.command("get", help="List resources or fetch one by name.")(get_cmd)
app.command(
    "describe", help="Show full details of a single resource (YAML by default)."
)(describe_cmd)
app.command("apply", help="Create or update resources from YAML manifest files.")(
    apply_cmd
)
app.command("delete", help="Delete a resource by name or via manifest files.")(
    delete_cmd
)
app.command("run", help="Execute a workflow against a batch of documents.")(run_cmd)
app.command("query", help="Run a SQL query against the project's annotations.")(
    query_cmd
)
app.command("version", help="Print the installed ragnerock package version.")(
    version_cmd
)


def main() -> None:
    """Console-script entry point registered in ``pyproject.toml``."""
    app()


if __name__ == "__main__":
    main()
