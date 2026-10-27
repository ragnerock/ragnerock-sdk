"""Prepare and apply a GitOps manifest set.

:func:`apply_manifests` is the one-call entry point: discover manifests,
resolve every ``Secret`` source client-side, seal the values to the
instance's public key, upload, and return the server's report.
:func:`prepare_manifest` and :func:`render_dry_run` expose the steps for
callers that want to inspect the upload before (or instead of) sending it.
"""

from __future__ import annotations

import copy
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import IO, TYPE_CHECKING, Any

import yaml

from ragnerock.errors import GitOpsError, NotFoundError
from ragnerock.gitops.discovery import ManifestSet, load_manifests
from ragnerock.gitops.sealing import key_fingerprint, load_public_key
from ragnerock.gitops.sealing import seal as _seal
from ragnerock.gitops.secrets import (
    CloudSecretFetcher,
    ResolvedSecrets,
    resolve_secrets,
)

if TYPE_CHECKING:
    from ragnerock.client import RagnerockClient
    from ragnerock.client.gitops import GitOpsApplyResponse

REDACTED = "<redacted>"
"""Stand-in for every secret value in dry-run output."""

_MIN_MASK_LENGTH = 4


@dataclass
class PreparedManifest:
    """A manifest set rewritten for upload.

    Attributes:
        documents (list[dict[str, Any]]): The documents to upload. ``Secret``
            specs carry ``encryptedData`` (or ``stringData`` when unsealed)
            instead of their authored sources.
        secrets (ResolvedSecrets): What was resolved, for reporting.
        sealed (bool): Whether values were sealed (or would be, for a dry run).
        sealing_fingerprint (str | None): Fingerprint of the key values were
            sealed to; ``None`` when nothing was sealed.
        sealing_key_pinned (bool): Whether that key was supplied by the
            caller rather than fetched from the instance.
        redacted (bool): Whether values were elided (a dry run).
    """

    documents: list[dict[str, Any]]
    secrets: ResolvedSecrets
    sealed: bool
    sealing_fingerprint: str | None = None
    sealing_key_pinned: bool = False
    redacted: bool = False

    def to_yaml(self) -> str:
        """Serialize the documents as one multi-document YAML stream.

        Returns:
            str: The YAML to upload (or print, for a dry run).
        """
        return yaml.safe_dump_all(
            self.documents, sort_keys=False, default_flow_style=False
        )


def mask_in_github_actions(
    values: Iterable[str], *, stream: IO[str] | None = None
) -> None:
    """Register secret values for masking in GitHub Actions logs.

    Emits an ``::add-mask::`` workflow command for each value and for each of
    its lines, because GitHub does not reliably redact a multi-line secret
    (service-account JSON, PEM keys) from a single mask. Values shorter than
    four characters are skipped. A no-op outside GitHub Actions.

    Args:
        values (Iterable[str]): Plaintext secret values.
        stream (IO[str] | None): Where to write the commands. Defaults to
            :data:`sys.stdout`.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    out = stream if stream is not None else sys.stdout
    for value in values:
        for candidate in {value, *value.splitlines()}:
            stripped = candidate.strip()
            if len(stripped) >= _MIN_MASK_LENGTH:
                print(f"::add-mask::{stripped}", file=out, flush=True)


def _as_manifest_set(
    manifests: ManifestSet | Sequence[str | os.PathLike[str]],
    stdin: IO[str] | None,
) -> ManifestSet:
    """Return ``manifests`` as a :class:`ManifestSet`, loading paths if needed."""
    if isinstance(manifests, ManifestSet):
        return manifests
    return load_manifests(manifests, stdin=stdin)


def render_dry_run(
    manifests: ManifestSet,
    *,
    seal: bool = True,
    env: Mapping[str, str] | None = None,
) -> PreparedManifest:
    """Build the upload a real apply would send, with every secret value elided.

    Entirely offline: no server, no credentials, no cloud calls. Cloud
    references are parsed (so a malformed one still fails) but not fetched,
    and ``fromEnv`` variables must still be set.

    Args:
        manifests (ManifestSet): The manifests to render.
        seal (bool): Render the sealed (``encryptedData``) shape, or the
            unsealed ``stringData`` shape.
        env (Mapping[str, str] | None): Environment for ``fromEnv``. Defaults
            to :data:`os.environ`.

    Returns:
        PreparedManifest: The redacted upload.

    Raises:
        GitOpsError: If a secret fails to resolve.
    """
    documents = copy.deepcopy(manifests.documents)
    secrets = resolve_secrets(documents, offline=True, env=env)
    secrets.write(sealed=seal, transform=lambda _: REDACTED)
    return PreparedManifest(
        documents=documents, secrets=secrets, sealed=seal, redacted=True
    )


def prepare_manifest(
    manifests: ManifestSet,
    *,
    client: RagnerockClient | None = None,
    seal: bool = True,
    sealing_public_key: str | None = None,
    env: Mapping[str, str] | None = None,
    fetcher: CloudSecretFetcher | None = None,
) -> PreparedManifest:
    """Resolve every ``Secret`` source and rewrite the documents for upload.

    The input set is not modified. Under GitHub Actions, every resolved value
    is registered for log masking before anything else can echo it.

    A sealing key is needed only when there are secret values to seal: a set
    with none never contacts the instance for one. The key is the pinned
    ``sealing_public_key`` when given, otherwise fetched with ``client``.

    Args:
        manifests (ManifestSet): The manifests to prepare.
        client (RagnerockClient | None): Client used to fetch the sealing key.
            Not needed when ``sealing_public_key`` is given or ``seal`` is off.
        seal (bool): Seal values to the instance key. ``False`` uploads them
            as plaintext ``stringData`` — only for instances with no sealing
            key configured.
        sealing_public_key (str | None): PEM public key to seal to instead of
            fetching one. Pinning also defends against an intermediary that
            terminates TLS.
        env (Mapping[str, str] | None): Environment for ``fromEnv``. Defaults
            to :data:`os.environ`.
        fetcher (CloudSecretFetcher | None): Cloud fetcher override.

    Returns:
        PreparedManifest: The documents ready to upload.

    Raises:
        GitOpsError: If a secret fails to resolve, the key is unusable, or the
            instance has no sealing key configured. Sealing never silently
            falls back to plaintext.
    """
    documents = copy.deepcopy(manifests.documents)
    secrets = resolve_secrets(documents, env=env, fetcher=fetcher)
    mask_in_github_actions(secrets.plaintexts())

    if not seal:
        secrets.write(sealed=False, transform=lambda v: v)
        return PreparedManifest(documents=documents, secrets=secrets, sealed=False)

    if secrets.key_count == 0:
        return PreparedManifest(documents=documents, secrets=secrets, sealed=True)

    pinned = bool(sealing_public_key)
    if sealing_public_key:
        pem = sealing_public_key
    else:
        if client is None:
            raise GitOpsError(
                "a client or a sealing_public_key is required to seal secret values"
            )
        try:
            pem = client.gitops.sealing_key().public_key
        except NotFoundError as e:
            raise GitOpsError(
                "this instance does not have secret sealing configured, so secret "
                "values cannot be encrypted before upload",
                suggestion=(
                    "Configure a sealing key on the instance, or re-run with "
                    "sealing disabled (--no-seal / seal=False) to upload the "
                    "values as plaintext."
                ),
            ) from e
    public_key = load_public_key(pem)
    secrets.write(sealed=True, transform=lambda v: _seal(v, public_key))
    return PreparedManifest(
        documents=documents,
        secrets=secrets,
        sealed=True,
        sealing_fingerprint=key_fingerprint(public_key),
        sealing_key_pinned=pinned,
    )


def apply_manifests(
    client: RagnerockClient,
    manifests: ManifestSet | Sequence[str | os.PathLike[str]],
    *,
    plan: bool = False,
    seal: bool = True,
    sealing_public_key: str | None = None,
    env: Mapping[str, str] | None = None,
    fetcher: CloudSecretFetcher | None = None,
    stdin: IO[str] | None = None,
) -> GitOpsApplyResponse:
    """Discover, prepare, and apply GitOps manifests.

    Every Ragnerock document across all sources is uploaded in one request,
    so the server's apply ordering and cross-file ``secretKeyRef`` resolution
    work across files. Apply is an upsert by name; objects absent from the
    manifests are never deleted.

    Example::

        from ragnerock import create_client
        from ragnerock.gitops import apply_manifests

        client = create_client("ragnerock://token:rgnk_...@api.ragnerock.com")
        report = apply_manifests(client, ["manifests/"], plan=True)
        for result in report.results:
            print(result.kind, result.name, result.action)

    Args:
        client (RagnerockClient): An authenticated client.
        manifests (ManifestSet | Sequence[str | os.PathLike[str]]): A loaded
            :class:`ManifestSet`, or files / directories / ``-`` to load.
        plan (bool): Validate against the real account and report what would
            change, then have the server roll everything back.
        seal (bool): Seal secret values to the instance key (see
            :func:`prepare_manifest`).
        sealing_public_key (str | None): PEM key to seal to instead of
            fetching one.
        env (Mapping[str, str] | None): Environment for ``fromEnv``. Defaults
            to :data:`os.environ`.
        fetcher (CloudSecretFetcher | None): Cloud fetcher override.
        stdin (IO[str] | None): Stream to read for a ``-`` source.

    Returns:
        GitOpsApplyResponse: The server's report. An empty manifest set
        returns an ``ok`` report with no results and makes no request.

    Raises:
        GitOpsError: If manifests or secrets cannot be prepared.
        RagnerockError: If the server rejects the upload.
    """
    from ragnerock.client.gitops import GitOpsApplyResponse

    manifest_set = _as_manifest_set(manifests, stdin)
    if not manifest_set.documents:
        return GitOpsApplyResponse(ok=True, dry_run=plan)
    prepared = prepare_manifest(
        manifest_set,
        client=client,
        seal=seal,
        sealing_public_key=sealing_public_key,
        env=env,
        fetcher=fetcher,
    )
    return client.gitops.apply(prepared.to_yaml(), dry_run=plan)
