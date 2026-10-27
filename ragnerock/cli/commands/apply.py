"""``ragnerock apply`` — apply GitOps manifests to a Ragnerock instance."""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Annotated

import httpx
import typer
import yaml
from rich.console import Console
from rich.markup import escape

from ragnerock.cli.config import SEALING_PUBLIC_KEY_VAR, ConfigError, build_client
from ragnerock.cli.errors import SERVER_ERROR, USER_ERROR, exit_code_for
from ragnerock.client.gitops import GitOpsApplyResponse, GitOpsApplyResult
from ragnerock.errors import GitOpsError, RagnerockError
from ragnerock.gitops import (
    ManifestSet,
    PreparedManifest,
    load_manifests,
    prepare_manifest,
    render_dry_run,
)

_ACTION_STYLES = {
    "created": "green",
    "updated": "blue",
    "unchanged": "bright_black",
    "error": "red",
}


class ApplyOutput(str, Enum):
    """Supported ``-o/--output`` values for ``apply``."""

    TABLE = "table"
    JSON = "json"
    YAML = "yaml"


def apply_cmd(
    files: Annotated[
        list[str],
        typer.Option(
            "--file",
            "-f",
            help=(
                "Manifest file, directory (walked recursively for '*.yaml' / "
                "'*.yml'), or '-' for STDIN. Repeatable; every source is "
                "uploaded together."
            ),
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=(
                "Print the manifest that would be uploaded, with secret values "
                "elided, without contacting the server or any cloud provider."
            ),
        ),
    ] = False,
    plan: Annotated[
        bool,
        typer.Option(
            "--plan",
            help=(
                "Upload and report what would change, then have the server "
                "roll it all back. Validates against the real account."
            ),
        ),
    ] = False,
    no_seal: Annotated[
        bool,
        typer.Option(
            "--no-seal",
            help=(
                "Upload secret values as plaintext instead of sealing them to "
                "the instance's public key. Only for instances with no "
                "sealing key configured."
            ),
        ),
    ] = False,
    sealing_public_key: Annotated[
        str | None,
        typer.Option(
            "--sealing-public-key",
            envvar=SEALING_PUBLIC_KEY_VAR,
            help=(
                "PEM public key to seal secrets to, or '@path' to a PEM file, "
                "instead of fetching it from the instance. Pinning the key "
                "also protects against a TLS-terminating intermediary."
            ),
        ),
    ] = None,
    output: Annotated[
        ApplyOutput,
        typer.Option(
            "--output",
            "-o",
            help="Report format: table, json, or yaml.",
            case_sensitive=False,
        ),
    ] = ApplyOutput.TABLE,
) -> None:
    """Apply Ragnerock GitOps manifests (``apiVersion: ragnerock.com/...``).

    Every document found across the sources is uploaded in one request and
    upserted by name. Objects absent from the manifests are never deleted.
    ``Secret`` values are resolved locally and sealed before upload.
    """
    err = Console(stderr=True, highlight=False, soft_wrap=True)

    if dry_run and plan:
        raise typer.BadParameter("--dry-run and --plan are mutually exclusive.")

    try:
        manifests = load_manifests(files)
    except GitOpsError as e:
        raise typer.Exit(code=exit_code_for(e)) from e

    sources = ", ".join(files)
    if not manifests.documents:
        typer.echo(f"No Ragnerock manifests found under {sources} — nothing to apply.")
        return

    _report_discovery(err, manifests, sources)

    if dry_run:
        try:
            prepared = render_dry_run(manifests, seal=not no_seal)
        except GitOpsError as e:
            raise typer.Exit(code=exit_code_for(e)) from e
        _report_secrets(err, prepared, dry_run=True)
        err.print("\n--- manifest to upload (dry run; secret values elided) ---\n")
        typer.echo(prepared.to_yaml())
        return

    pinned_pem = _read_pem(sealing_public_key)

    try:
        client = build_client()
    except ConfigError as e:
        typer.echo(f"ConfigError: {e}", err=True)
        raise typer.Exit(code=USER_ERROR) from e
    except RagnerockError as e:
        raise typer.Exit(code=exit_code_for(e)) from e

    with client:
        try:
            prepared = prepare_manifest(
                manifests,
                client=client,
                seal=not no_seal,
                sealing_public_key=pinned_pem,
            )
        except RagnerockError as e:
            raise typer.Exit(code=exit_code_for(e)) from e
        _report_secrets(err, prepared, dry_run=False)
        if no_seal and prepared.secrets.key_count:
            _warn_unsealed(err, prepared.secrets.key_count)

        try:
            report = client.gitops.apply(prepared.to_yaml(), dry_run=plan)
        except RagnerockError as e:
            raise typer.Exit(code=exit_code_for(e)) from e
        except httpx.HTTPError as e:
            typer.echo(f"{type(e).__name__}: could not reach the server: {e}", err=True)
            raise typer.Exit(code=SERVER_ERROR) from e

    if output is ApplyOutput.TABLE:
        _render_report(report)
    else:
        payload = report.model_dump(mode="json")
        if output is ApplyOutput.JSON:
            typer.echo(json.dumps(payload, indent=2))
        else:
            typer.echo(yaml.safe_dump(payload, sort_keys=False).rstrip())
    _annotate_warnings(report)

    if not report.ok:
        raise typer.Exit(code=USER_ERROR)


def _read_pem(value: str | None) -> str | None:
    """Resolve a ``--sealing-public-key`` value to PEM text.

    Args:
        value (str | None): PEM text, ``@path`` to a PEM file, or ``None``.

    Returns:
        str | None: The PEM text, or ``None`` when no key was pinned.

    Raises:
        typer.Exit: With code 1 if an ``@path`` file cannot be read.
    """
    if not value:
        return None
    if not value.startswith("@"):
        return value
    path = Path(value[1:]).expanduser()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        typer.echo(f"Cannot read sealing public key {str(path)!r}: {e}", err=True)
        raise typer.Exit(code=USER_ERROR) from e


def _report_discovery(err: Console, manifests: ManifestSet, sources: str) -> None:
    """Describe what discovery found, on stderr."""
    err.print(
        f"Discovered {len(manifests)} Ragnerock manifest document(s) in "
        f"{len(manifests.files)} file(s) under {escape(sources)}:"
    )
    for name in manifests.files:
        err.print(f"  • {escape(name)}")
    if manifests.skipped:
        err.print(f"Skipped {manifests.skipped} non-Ragnerock document(s).")


def _report_secrets(err: Console, prepared: PreparedManifest, *, dry_run: bool) -> None:
    """Describe secret resolution and sealing, on stderr."""
    secrets = prepared.secrets
    if secrets.env_key_count:
        err.print(f"Resolved {secrets.env_key_count} fromEnv secret key(s) locally.")
    if secrets.cloud_reference_count:
        if dry_run:
            err.print(
                f"Checked {secrets.cloud_reference_count} cloud secret reference(s); "
                "a dry run does not fetch them."
            )
        else:
            err.print(
                f"Resolved {secrets.cloud_reference_count} secret key(s) from cloud "
                "secret managers."
            )
    if prepared.sealing_fingerprint is not None:
        source = (
            "pinned" if prepared.sealing_key_pinned else "fetched from the instance"
        )
        err.print(f"Sealing secrets to key {prepared.sealing_fingerprint} ({source}).")
        if not prepared.sealing_key_pinned:
            err.print(
                "  note: the key was fetched over the same connection it protects. "
                "Pin it with --sealing-public-key to also defend against an "
                "intermediary that terminates TLS."
            )


def _warn_unsealed(err: Console, key_count: int) -> None:
    """Warn that secret values are about to be uploaded as plaintext."""
    message = (
        f"Sealing is disabled, so {key_count} secret value(s) will be uploaded as "
        "plaintext in the request body."
    )
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning::{message}", flush=True)
    else:
        err.print(f"[yellow]warning:[/] {message}")


def _render_report(report: GitOpsApplyResponse) -> None:
    """Print the per-object summary.

    Objects and the summary line go to stdout; errors and warnings go to
    stderr beneath the object they belong to.
    """
    out = Console(highlight=False, soft_wrap=True)
    err = Console(stderr=True, highlight=False, soft_wrap=True)

    for problem in report.structural_errors:
        err.print(f"  [red]structural error:[/] {escape(str(problem))}")

    width = max((len(r.kind) for r in report.results), default=0)
    for result in report.results:
        style = _ACTION_STYLES.get(result.action, "")
        action = (
            f"[{style}]{escape(result.action)}[/]" if style else escape(result.action)
        )
        out.print(f"  {escape(result.kind):<{width}}  {escape(result.name)}  {action}")
        for problem in result.errors:
            err.print(f"      [red]↳[/] {escape(str(problem))}")
        for warning in result.warnings:
            err.print(f"      [yellow]⚠[/] {escape(str(warning))}")

    prefix = "OK" if report.ok else "FAILED"
    if report.dry_run:
        prefix = f"{prefix} (plan, nothing was applied)"
    parts = [f"{report.changed} changed", f"{len(report.results)} object(s)"]
    if report.warning_count:
        parts.insert(1, f"{report.warning_count} warning(s)")
    out.print(f"\n{prefix} — {', '.join(parts)}")


def _annotate_warnings(report: GitOpsApplyResponse) -> None:
    """Raise each per-object warning as a GitHub Actions annotation.

    A no-op outside GitHub Actions. Inside it, warnings land on the workflow
    summary rather than only in the log body.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    for result in report.results:
        for warning in result.warnings:
            _annotate(result, str(warning))


def _annotate(result: GitOpsApplyResult, warning: str) -> None:
    """Emit one ``::warning`` workflow command for an object."""
    title = f"{result.kind} {result.name}"
    body = " ".join(warning.split())
    print(f"::warning title={title}::{body}", flush=True)
