"""Manifest loading, validation, and apply-order sorting.

A manifest is a multi-doc YAML file (or stream) where each document has the
shape::

    apiVersion: v1
    kind: <ResourceKind>
    metadata:
      name: <string>
      # optional extra fields (id, labels, …)
    spec:
      # kind-specific body
"""

from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass
from typing import Any

import yaml

from ragnerock.cli.resources import KindSpec, UnknownKindError, resolve_kind


_YAML_EXTENSIONS: frozenset[str] = frozenset({".yaml", ".yml"})

DEFAULT_API_VERSION: str = "v1"
SUPPORTED_API_VERSIONS: frozenset[str] = frozenset({"v1"})


class ManifestError(Exception):
    """Raised on any manifest shape / parse / reference error."""


@dataclass
class ManifestDoc:
    """A single parsed manifest document.

    Attributes:
        api_version (str): Value of ``apiVersion``; defaults to ``v1`` when
            absent. Only versions in :data:`SUPPORTED_API_VERSIONS` are
            accepted.
        spec_kind (KindSpec): The resolved kind metadata.
        name (str): Value of ``metadata.name``. Required on every manifest.
        metadata (dict[str, Any]): Full ``metadata`` block, minus ``name``.
        spec (dict[str, Any]): Full ``spec`` block, empty dict if absent.
        source (str): Label used in error messages (file path or ``<stdin>``).
        index (int): 0-based index within the source.
    """

    api_version: str
    spec_kind: KindSpec
    name: str
    metadata: dict[str, Any]
    spec: dict[str, Any]
    source: str
    index: int


_APPLY_ORDER: tuple[str, ...] = (
    "DocumentGroup",
    "Operator",
    "Document",
    "Workflow",
    "Annotation",
)


def _expand_sources(sources: list[str]) -> list[str]:
    """Expand directory sources to their contained YAML files.

    ``-`` and non-directory paths pass through unchanged (non-existent paths
    are left for :func:`read_manifests` to surface with its existing error
    wording). Directory sources are walked recursively, sorted for
    deterministic ordering, with hidden entries and non-YAML files skipped.
    """
    expanded: list[str] = []
    for source in sources:
        if source == "-" or not os.path.isdir(source):
            expanded.append(source)
            continue

        def _raise(err: OSError, directory: str = source) -> None:
            raise ManifestError(f"Cannot read directory {directory!r}: {err}")

        found: list[str] = []
        for dirpath, dirnames, filenames in os.walk(
            source, followlinks=False, onerror=_raise
        ):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                if os.path.splitext(name)[1].lower() not in _YAML_EXTENSIONS:
                    continue
                found.append(os.path.join(dirpath, name))

        if not found:
            raise ManifestError(f"No YAML manifests found under directory {source!r}.")
        expanded.extend(found)
    return expanded


def read_manifests(sources: list[str]) -> list[ManifestDoc]:
    """Load manifests from a mix of file paths, directories, and ``-`` (STDIN).

    Args:
        sources (list[str]): One or more sources. ``-`` reads from
            :data:`sys.stdin`; a directory is expanded recursively to every
            ``*.yaml`` / ``*.yml`` file beneath it (sorted, hidden entries
            skipped); anything else is treated as a file path.

    Returns:
        list[ManifestDoc]: Parsed manifest documents, in the order they were
        encountered across all sources.

    Raises:
        ManifestError: If any source is empty, unreadable, or malformed.
    """
    if not sources:
        raise ManifestError("At least one -f/--file source is required.")

    expanded = _expand_sources(sources)

    docs: list[ManifestDoc] = []
    for source in expanded:
        if source == "-":
            text = sys.stdin.read()
            label = "<stdin>"
        else:
            try:
                with open(source, encoding="utf-8") as f:
                    text = f.read()
            except OSError as e:
                raise ManifestError(f"Cannot read manifest {source!r}: {e}") from e
            label = source
        docs.extend(_parse_stream(text, label))

    if not docs:
        raise ManifestError("No manifest documents were found in the provided inputs.")
    return docs


def _parse_stream(text: str, source: str) -> list[ManifestDoc]:
    """Parse a YAML stream (which may contain multiple documents)."""
    try:
        raw_docs = list(yaml.safe_load_all(io.StringIO(text)))
    except yaml.YAMLError as e:
        raise ManifestError(f"Invalid YAML in {source}: {e}") from e

    parsed: list[ManifestDoc] = []
    for idx, raw in enumerate(raw_docs):
        if raw is None:
            continue
        parsed.append(_validate_doc(raw, source, idx))
    return parsed


def _validate_doc(raw: Any, source: str, index: int) -> ManifestDoc:
    """Shape-check a single parsed document and resolve its kind."""
    where = f"{source} (doc #{index})"
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: manifest document must be a mapping.")

    api_version = raw.get("apiVersion", DEFAULT_API_VERSION)
    if not isinstance(api_version, str):
        raise ManifestError(f"{where}: 'apiVersion' must be a string.")
    if api_version not in SUPPORTED_API_VERSIONS:
        raise ManifestError(
            f"{where}: unsupported apiVersion {api_version!r} "
            f"(supported: {sorted(SUPPORTED_API_VERSIONS)})."
        )

    kind_str = raw.get("kind")
    if not isinstance(kind_str, str) or not kind_str:
        raise ManifestError(f"{where}: missing or invalid 'kind'.")

    try:
        spec_kind = resolve_kind(kind_str)
    except UnknownKindError as e:
        raise ManifestError(f"{where}: {e}") from e

    if not spec_kind.writable:
        raise ManifestError(
            f"{where}: kind {spec_kind.kind!r} is read-only and cannot be applied."
        )

    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ManifestError(f"{where}: 'metadata' must be a mapping.")
    name = metadata.get("name")
    if not isinstance(name, str) or not name:
        raise ManifestError(f"{where}: 'metadata.name' is required.")

    spec_body = raw.get("spec") or {}
    if not isinstance(spec_body, dict):
        raise ManifestError(f"{where}: 'spec' must be a mapping.")

    metadata_rest = {k: v for k, v in metadata.items() if k != "name"}

    return ManifestDoc(
        api_version=api_version,
        spec_kind=spec_kind,
        name=name,
        metadata=metadata_rest,
        spec=spec_body,
        source=source,
        index=index,
    )


def sort_by_apply_order(docs: list[ManifestDoc]) -> list[ManifestDoc]:
    """Sort manifests by kind dependency so parents commit before children.

    Order: ``DocumentGroup → Operator → Document → Workflow → Annotation``.
    Within a kind, declaration order is preserved (stable sort).
    """
    priority = {kind: i for i, kind in enumerate(_APPLY_ORDER)}
    return sorted(docs, key=lambda d: priority.get(d.spec_kind.kind, len(_APPLY_ORDER)))
