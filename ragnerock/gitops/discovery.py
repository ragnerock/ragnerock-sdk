"""Find and parse GitOps manifests.

Point discovery at files, directories, or ``-`` (standard input). Directories
are walked recursively for ``*.yaml`` / ``*.yml`` files (hidden entries are
skipped), and only documents whose ``apiVersion`` is in the ``ragnerock.com/``
API group are kept — any other YAML in the tree (CI configs, Kubernetes
manifests, …) is ignored. That lets you point it at a whole repository.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

import yaml

from ragnerock.errors import GitOpsError

API_GROUP = "ragnerock.com/"
"""Prefix every Ragnerock manifest's ``apiVersion`` carries."""

STDIN = "-"
"""Source token meaning "read manifests from standard input"."""

_YAML_SUFFIXES = (".yaml", ".yml")


@dataclass
class ManifestSet:
    """The Ragnerock manifest documents gathered from a set of sources.

    Attributes:
        documents (list[dict[str, Any]]): Every Ragnerock document, in
            discovery order. They are uploaded together, so the server's
            rank-based ordering and cross-file ``secretKeyRef`` resolution
            work across files.
        files (list[str]): Sources that contributed at least one document
            (``"<stdin>"`` for standard input).
        skipped (int): Non-Ragnerock YAML documents that were ignored.
    """

    documents: list[dict[str, Any]] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    skipped: int = 0

    def __len__(self) -> int:
        """Return the number of Ragnerock documents."""
        return len(self.documents)

    def kinds(self) -> list[str]:
        """Return the distinct ``kind`` values present, in first-seen order."""
        seen: dict[str, None] = {}
        for doc in self.documents:
            seen.setdefault(str(doc.get("kind", "")), None)
        return list(seen)


def is_ragnerock_document(doc: object) -> bool:
    """Return whether a parsed YAML document is a Ragnerock manifest.

    Args:
        doc (object): A parsed YAML document.

    Returns:
        bool: ``True`` for a mapping whose ``apiVersion`` starts with
        ``ragnerock.com/``.
    """
    return (
        isinstance(doc, dict)
        and isinstance(doc.get("apiVersion"), str)
        and doc["apiVersion"].startswith(API_GROUP)
    )


def expand_sources(sources: Sequence[str | os.PathLike[str]]) -> list[str]:
    """Expand directory sources to the YAML files beneath them.

    Files and ``-`` pass through unchanged. Directories are walked
    recursively in sorted order, skipping hidden files and directories and
    anything without a ``.yaml`` / ``.yml`` suffix.

    Args:
        sources (Sequence[str | os.PathLike[str]]): Files, directories, or ``-``.

    Returns:
        list[str]: Concrete file paths (and ``-``), in a stable order.

    Raises:
        GitOpsError: If a source does not exist or a directory is unreadable.
    """
    expanded: list[str] = []
    for raw in sources:
        source = os.fspath(raw)
        if source == STDIN:
            expanded.append(source)
            continue
        path = Path(source)
        if not path.exists():
            raise GitOpsError(f"path does not exist: {source}")
        if path.is_file():
            expanded.append(source)
            continue

        def _raise(err: OSError, directory: str = source) -> None:
            raise GitOpsError(f"cannot read directory {directory!r}: {err}")

        for dirpath, dirnames, filenames in os.walk(
            source, followlinks=False, onerror=_raise
        ):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                if os.path.splitext(name)[1].lower() in _YAML_SUFFIXES:
                    expanded.append(os.path.join(dirpath, name))
    return expanded


def load_manifests(
    sources: Sequence[str | os.PathLike[str]],
    *,
    stdin: IO[str] | None = None,
) -> ManifestSet:
    """Load every Ragnerock manifest document from files, directories, or stdin.

    Finding no Ragnerock documents is not an error — the returned set is
    simply empty — so callers can run discovery over a repository on every
    push without special-casing commits that touch no manifests.

    Args:
        sources (Sequence[str | os.PathLike[str]]): Files, directories, or
            ``-`` for standard input.
        stdin (IO[str] | None): Stream to read for ``-``. Defaults to
            :data:`sys.stdin`.

    Returns:
        ManifestSet: The Ragnerock documents found, and what was skipped.

    Raises:
        GitOpsError: If a source is missing or unreadable, or contains
            invalid YAML.
    """
    result = ManifestSet()
    for source in expand_sources(sources):
        if source == STDIN:
            text = (stdin if stdin is not None else sys.stdin).read()
            label = "<stdin>"
        else:
            try:
                text = Path(source).read_text(encoding="utf-8")
            except OSError as e:
                raise GitOpsError(f"cannot read {source!r}: {e}") from e
            label = source

        try:
            parsed = [doc for doc in yaml.safe_load_all(text) if doc is not None]
        except yaml.YAMLError as e:
            raise GitOpsError(f"invalid YAML in {label}: {e}") from e

        kept = [doc for doc in parsed if is_ragnerock_document(doc)]
        result.skipped += len(parsed) - len(kept)
        if kept:
            result.documents.extend(kept)
            result.files.append(label)
    return result
