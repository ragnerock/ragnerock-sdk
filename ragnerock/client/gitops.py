"""GitOps endpoints (``/api/gitops/...``).

Most callers should use :func:`ragnerock.gitops.apply_manifests` (or the
``ragnerock apply`` command), which discovers manifests, resolves and seals
``Secret`` values, and then calls :meth:`_GitOpsSection.apply`.
"""

from __future__ import annotations

from typing import Any

from ragnerock.client._base import _ApiModel, _Section

APPLY_TIMEOUT_SECONDS = 300.0
"""Read timeout for an apply.

An apply is not just database work: each code agent in the manifest is
security-reviewed with an LLM call. The client waits comfortably longer than
the server's own budget for that, because timing out would report a failure
for an apply the server had already committed.
"""


class SealingKeyResponse(_ApiModel):
    """The instance's public key for sealing GitOps secret values.

    Attributes:
        public_key (str): PEM-encoded RSA public key.
        algorithm (str | None): Sealing algorithm identifier, e.g.
            ``"rsa-oaep-sha256"``.
        fingerprint (str | None): ``sha256:<hex>`` fingerprint of the key.
    """

    public_key: str
    algorithm: str | None = None
    fingerprint: str | None = None


class GitOpsApplyResult(_ApiModel):
    """The outcome for one manifest object.

    Attributes:
        kind (str): The document's ``kind``.
        name (str): The document's ``metadata.name``.
        action (str): ``"created"``, ``"updated"``, ``"unchanged"``, or
            ``"error"``.
        errors (list[Any]): Why the object failed to apply.
        warnings (list[Any]): Problems the server applied around, which will
            otherwise surface only at run time — e.g. an agent whose model
            binding did not resolve, or a workflow node nothing feeds.
    """

    kind: str
    name: str
    action: str
    errors: list[Any] = []
    warnings: list[Any] = []


class GitOpsApplyResponse(_ApiModel):
    """The server's report for an apply.

    Attributes:
        ok (bool): ``True`` when nothing failed.
        dry_run (bool): ``True`` when the apply was rolled back (a plan).
        structural_errors (list[Any]): Problems with the manifest set as a
            whole (e.g. an unknown kind or a duplicate name).
        results (list[GitOpsApplyResult]): One entry per object, in apply order.
    """

    ok: bool = False
    dry_run: bool = False
    structural_errors: list[Any] = []
    results: list[GitOpsApplyResult] = []

    @property
    def changed(self) -> int:
        """Number of objects created or updated."""
        return sum(1 for r in self.results if r.action in ("created", "updated"))

    @property
    def warning_count(self) -> int:
        """Total warnings across every object."""
        return sum(len(r.warnings) for r in self.results)


class _GitOpsSection(_Section):
    """GitOps apply and sealing-key endpoints."""

    def sealing_key(self) -> SealingKeyResponse:
        """Fetch the instance's public key for sealing secret values.

        Calls ``GET /api/gitops/sealing-key``.

        Returns:
            SealingKeyResponse: The PEM public key.

        Raises:
            NotFoundError: If the instance has no sealing key configured.
        """
        response = self._parent._request("GET", "/api/gitops/sealing-key")
        return SealingKeyResponse.model_validate(response.json())

    def apply(
        self,
        manifest: str,
        *,
        dry_run: bool = False,
        timeout: float = APPLY_TIMEOUT_SECONDS,
    ) -> GitOpsApplyResponse:
        """Upload a multi-document manifest and apply it.

        Calls ``POST /api/gitops/apply`` with the YAML as a multipart file.
        Apply is an upsert by name: existing objects are updated, missing ones
        created, and objects absent from the manifest are never deleted. The
        server orders documents by kind before applying, so document order
        doesn't matter.

        ``Secret`` documents must already be resolved — the server refuses
        authored sources such as ``fromEnv``. Use
        :func:`ragnerock.gitops.apply_manifests` to resolve and seal them.

        Args:
            manifest (str): Multi-document YAML.
            dry_run (bool): Validate against the real account, report what
                would change, then roll everything back.
            timeout (float): Read timeout in seconds.

        Returns:
            GitOpsApplyResponse: The per-object report. Check ``ok``.
        """
        response = self._parent._request(
            "POST",
            "/api/gitops/apply",
            params={"dry_run": "true"} if dry_run else None,
            files={"file": ("manifest.yaml", manifest, "application/x-yaml")},
            timeout=timeout,
        )
        return GitOpsApplyResponse.model_validate(response.json())
