"""Apply Ragnerock GitOps manifests: configuration as code.

A GitOps manifest is a YAML document in the ``ragnerock.com/`` API group —
``Secret``, ``AIProviderConfig``, ``Schema``, ``Agent``, ``Workflow``,
``Endpoint``, ``IngestConfig``, and so on. Apply uploads a whole set in one
request; the server upserts each object by name and reports what changed.

``Secret`` values are resolved on the client (inline, environment variables,
or a cloud secret manager) and sealed to the instance's public key before
upload, so nothing recoverable crosses the wire.

Example::

    from ragnerock import create_client
    from ragnerock.gitops import apply_manifests

    client = create_client("ragnerock://token:rgnk_...@api.ragnerock.com")
    report = apply_manifests(client, ["manifests/"])
    assert report.ok

The ``ragnerock apply -f`` command wraps the same functions.
"""

from __future__ import annotations

from ragnerock.client.gitops import (
    GitOpsApplyResponse,
    GitOpsApplyResult,
    SealingKeyResponse,
)
from ragnerock.errors import GitOpsError
from ragnerock.gitops.apply import (
    REDACTED,
    PreparedManifest,
    apply_manifests,
    mask_in_github_actions,
    prepare_manifest,
    render_dry_run,
)
from ragnerock.gitops.discovery import (
    API_GROUP,
    ManifestSet,
    expand_sources,
    is_ragnerock_document,
    load_manifests,
)
from ragnerock.gitops.sealing import (
    SealingError,
    is_sealed,
    key_fingerprint,
    load_public_key,
    seal,
)
from ragnerock.gitops.secrets import (
    CloudProvider,
    CloudSecretFetcher,
    ResolvedSecrets,
    SealedSecretEntry,
    SecretSource,
    SecretSourceType,
    SecretValue,
    resolve_secrets,
)

__all__ = [
    "API_GROUP",
    "REDACTED",
    "CloudProvider",
    "CloudSecretFetcher",
    "GitOpsApplyResponse",
    "GitOpsApplyResult",
    "GitOpsError",
    "ManifestSet",
    "PreparedManifest",
    "ResolvedSecrets",
    "SealedSecretEntry",
    "SealingError",
    "SealingKeyResponse",
    "SecretSource",
    "SecretSourceType",
    "SecretValue",
    "apply_manifests",
    "expand_sources",
    "is_ragnerock_document",
    "is_sealed",
    "key_fingerprint",
    "load_manifests",
    "load_public_key",
    "mask_in_github_actions",
    "prepare_manifest",
    "render_dry_run",
    "resolve_secrets",
    "seal",
]
