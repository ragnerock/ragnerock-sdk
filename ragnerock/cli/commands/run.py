"""``ragnerock run`` — execute a workflow against a batch of documents."""

from __future__ import annotations

from typing import Annotated

import typer

from ragnerock.cli.session import open_session
from ragnerock.resources import Document, JobStatus, Workflow


def run_cmd(
    workflow_name: Annotated[
        str, typer.Argument(help="Name of the workflow to execute.")
    ],
    documents: Annotated[
        str,
        typer.Option(
            "--documents",
            help="Comma-separated document names to process.",
        ),
    ],
    wait: Annotated[
        bool,
        typer.Option(
            "--wait/--no-wait",
            help="Block until the job reaches a terminal state.",
        ),
    ] = False,
    poll_interval: Annotated[
        float,
        typer.Option(
            "--poll-interval",
            help="Seconds between status polls when --wait is set.",
        ),
    ] = 2.0,
    timeout: Annotated[
        float | None,
        typer.Option(
            "--timeout",
            help="Maximum seconds to wait. Unlimited if unset.",
        ),
    ] = None,
) -> None:
    """Kick off a workflow and optionally block until it completes.

    Exit codes:
    * ``0`` — job succeeded (or wasn't waited on).
    * ``1`` — workflow or document not found.
    * ``2`` — job failed or timed out.
    """
    names = [n.strip() for n in documents.split(",") if n.strip()]
    if not names:
        raise typer.BadParameter("--documents must list at least one document name.")

    with open_session() as session:
        workflow = session.get(Workflow, name=workflow_name)
        if workflow is None:
            typer.echo(f"workflow/{workflow_name} not found", err=True)
            raise typer.Exit(code=1)

        resolved: list[Document] = []
        missing: list[str] = []
        for doc_name in names:
            doc = session.get(Document, name=doc_name)
            if doc is None:
                missing.append(doc_name)
            else:
                resolved.append(doc)
        if missing:
            typer.echo(
                "document(s) not found: " + ", ".join(missing),
                err=True,
            )
            raise typer.Exit(code=1)

        job = session.run(workflow, documents=resolved)
        typer.echo(f"job/{job.id} started")

        if not wait:
            return

        try:
            job.wait(timeout=timeout, poll_interval=poll_interval)
        except TimeoutError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2) from e

        status_name = getattr(job.status, "name", str(job.status))
        typer.echo(f"job/{job.id} finished with status {status_name}")
        if job.status is not JobStatus.SUCCEEDED:
            raise typer.Exit(code=2)
