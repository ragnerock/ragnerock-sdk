"""Registry mapping CLI resource kinds to SDK classes, aliases, and columns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ragnerock.resources import (
    Annotation,
    Chunk,
    Document,
    DocumentGroup,
    Job,
    Operator,
    Page,
    Workflow,
)
from ragnerock.resources.base import _Resource


@dataclass(frozen=True)
class KindSpec:
    """Per-kind CLI metadata.

    Attributes:
        kind (str): Canonical name used in manifests and error messages.
        cls (type[_Resource]): The SDK resource class this kind wraps.
        aliases (tuple[str, ...]): Alternate CLI names, all lowercase.
        list_columns (tuple[tuple[str, str], ...]): ``(header, field_name)``
            pairs for table output. ``field_name`` is read via
            :func:`getattr` on each resource.
        writable (bool): Whether ``apply``/``delete`` accept this kind.
    """

    kind: str
    cls: type[_Resource]
    aliases: tuple[str, ...] = ()
    list_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    writable: bool = False


_KINDS: tuple[KindSpec, ...] = (
    KindSpec(
        kind="Document",
        cls=Document,
        aliases=("document", "documents", "doc", "docs"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("FILE_TYPE", "file_type"),
            ("GROUP", "group_id"),
            ("CREATED", "created_at"),
        ),
        writable=True,
    ),
    KindSpec(
        kind="DocumentGroup",
        cls=DocumentGroup,
        aliases=("documentgroup", "documentgroups", "grp", "group", "groups"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("CREATED", "created_at"),
        ),
        writable=True,
    ),
    KindSpec(
        kind="Operator",
        cls=Operator,
        aliases=("operator", "operators", "op", "ops"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("CHUNK_TYPE", "chunk_type"),
            ("BATCH_SIZE", "batch_size"),
            ("CREATED", "created_at"),
        ),
        writable=True,
    ),
    KindSpec(
        kind="Workflow",
        cls=Workflow,
        aliases=("workflow", "workflows", "wf", "wfs"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("ACTIVE", "is_active"),
            ("AUTO_RUN", "auto_run_on_upload"),
            ("CREATED", "created_at"),
        ),
        writable=True,
    ),
    KindSpec(
        kind="Annotation",
        cls=Annotation,
        aliases=("annotation", "annotations", "anno", "annos"),
        list_columns=(
            ("ID", "root_id"),
            ("OPERATOR", "operator_name"),
            ("DOCUMENT", "document_id"),
            ("CHUNK", "chunk_id"),
            ("CREATED", "created_at"),
        ),
        writable=True,
    ),
    KindSpec(
        kind="Chunk",
        cls=Chunk,
        aliases=("chunk", "chunks"),
        list_columns=(
            ("ID", "id"),
            ("DOCUMENT", "document_id"),
            ("TYPE", "chunk_type"),
            ("START", "start_index"),
            ("END", "end_index"),
        ),
    ),
    KindSpec(
        kind="Page",
        cls=Page,
        aliases=("page", "pages"),
        list_columns=(
            ("ID", "id"),
            ("DOCUMENT", "document_id"),
        ),
    ),
    KindSpec(
        kind="Job",
        cls=Job,
        aliases=("job", "jobs"),
        list_columns=(
            ("ID", "id"),
            ("STATUS", "status"),
            ("DOCUMENT", "document_id"),
            ("START", "start_time"),
            ("END", "end_time"),
        ),
    ),
)


_BY_NAME: dict[str, KindSpec] = {}
for _spec in _KINDS:
    _BY_NAME[_spec.kind.lower()] = _spec
    for _alias in _spec.aliases:
        _BY_NAME[_alias.lower()] = _spec


class UnknownKindError(Exception):
    """Raised when a kind string does not match a registered kind or alias."""


def resolve_kind(name: str) -> KindSpec:
    """Resolve a user-supplied kind string to its :class:`KindSpec`.

    Matching is case-insensitive; aliases are accepted.

    Args:
        name (str): Kind name or alias (e.g. ``doc``, ``Document``, ``docs``).

    Returns:
        KindSpec: The matching spec.

    Raises:
        UnknownKindError: If ``name`` does not match any registered kind.
    """
    spec = _BY_NAME.get(name.lower())
    if spec is None:
        known = sorted({s.kind for s in _KINDS})
        raise UnknownKindError(
            f"Unknown resource kind {name!r}. Known kinds: {', '.join(known)}"
        )
    return spec


def all_kinds() -> tuple[KindSpec, ...]:
    """Return every registered :class:`KindSpec`.

    Returns:
        tuple[KindSpec, ...]: Specs in the declaration order of the registry.
    """
    return _KINDS


def resource_name(resource: _Resource) -> str | None:
    """Compute a best-effort display name for a resource.

    Uses ``name`` when present (most kinds), falls back to ``operator_name``
    (annotations and workflow nodes, which are identified by operator rather
    than a free-text name), then to the id as a last resort. Returns
    ``None`` only for resources that have no identity at all, which should
    never happen for server-returned instances.

    Args:
        resource (_Resource): The resource to name.

    Returns:
        str | None: A human-usable name, or ``None`` if none of the
        candidate attributes are set.
    """
    for attr in ("name", "operator_name"):
        value = getattr(resource, attr, None)
        if value:
            return str(value)
    rid: Any = getattr(resource, "id", None) or getattr(resource, "root_id", None)
    return str(rid) if rid is not None else None
