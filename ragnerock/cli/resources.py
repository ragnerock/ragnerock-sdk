"""Registry mapping CLI resource kinds to SDK classes, aliases, and columns.

Most kinds wrap a :mod:`ragnerock.resources` class and go through the
:class:`~ragnerock.session.Session`. Read-only *client-backed* kinds (skills,
endpoints, provider configs, ...) have no resource class; they list through
the low-level client instead.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

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

if TYPE_CHECKING:
    from ragnerock.session import Session

ListFn = Callable[["Session"], list[BaseModel]]
"""Lists every item of a client-backed kind in the session's project."""


@dataclass(frozen=True)
class KindSpec:
    """Per-kind CLI metadata.

    Attributes:
        kind (str): Canonical name used in output and error messages.
        cls (type[_Resource] | None): The SDK resource class this kind wraps,
            or ``None`` for a client-backed kind.
        aliases (tuple[str, ...]): Alternate CLI names, all lowercase.
        list_columns (tuple[tuple[str, str], ...]): ``(header, field_name)``
            pairs for table output. ``field_name`` is read via
            :func:`getattr` on each item.
        deletable (bool): Whether ``delete <kind> <name>`` accepts this kind.
        list_fn (ListFn | None): For client-backed kinds, lists every item.
            Lookup by name matches :data:`NAME_FIELDS` (then ``id``) over
            this list.
    """

    kind: str
    cls: type[_Resource] | None = None
    aliases: tuple[str, ...] = ()
    list_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    deletable: bool = False
    list_fn: ListFn | None = None


_KINDS: tuple[KindSpec, ...] = (
    KindSpec(
        kind="Document",
        cls=Document,
        aliases=("document", "documents", "doc", "docs"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("FILE_TYPE", "file_type"),
            ("STATUS", "status"),
            ("GROUP", "group_id"),
            ("CREATED", "created_at"),
        ),
        deletable=True,
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
        deletable=True,
    ),
    KindSpec(
        kind="Operator",
        cls=Operator,
        aliases=("operator", "operators", "op", "ops"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("KIND", "operator_kind"),
            ("CHUNK_TYPE", "chunk_type"),
            ("CREATED", "created_at"),
        ),
        deletable=True,
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
        deletable=True,
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
    ),
    KindSpec(
        kind="Chunk",
        cls=Chunk,
        aliases=("chunk", "chunks"),
        list_columns=(
            ("ID", "id"),
            ("DOCUMENT", "document_id"),
            ("TYPE", "chunk_type"),
            ("OFFSET", "document_offset"),
            ("PAGE", "page_id"),
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


_PAGE_SIZE = 50

# Attributes that identify an item, in lookup order, after which ``id`` is tried.
NAME_FIELDS: tuple[str, ...] = (
    "name",
    "operator_name",
    "config_name",
    "title",
    "file_name",
    "slug",
)


def _paged(fetch: Callable[[int, int], Any], field_name: str) -> list[BaseModel]:
    """Collect every item from a skip/limit-paginated list endpoint.

    Args:
        fetch (Callable[[int, int], Any]): Calls the endpoint with
            ``(skip, limit)`` and returns its list response.
        field_name (str): The response attribute holding the page's items.

    Returns:
        list[BaseModel]: Every item, in server order.
    """
    items: list[BaseModel] = []
    skip = 0
    while True:
        page = fetch(skip, _PAGE_SIZE)
        batch = list(getattr(page, field_name))
        items.extend(batch)
        skip += len(batch)
        total = getattr(page, "total", None)
        if len(batch) < _PAGE_SIZE or (total is not None and skip >= total):
            return items


def _list_artifacts(session: Session) -> list[BaseModel]:
    """Collect every workflow artifact in the project by following cursors."""
    client = session._engine.client
    project_id = session._engine.project_id
    items: list[BaseModel] = []
    cursor: str | None = None
    while True:
        page = client.workflow_artifacts.list(
            project_id, cursor=cursor, limit=_PAGE_SIZE
        )
        items.extend(page.artifacts)
        cursor = page.next_cursor
        if not cursor or not page.artifacts:
            return items


def _project_scoped(
    section: str, method: str, field_name: str, *, project_kw: str | None = None
) -> ListFn:
    """Build a :data:`ListFn` for a paginated, project-scoped list endpoint.

    Args:
        section (str): Client section attribute, e.g. ``"skills"``.
        method (str): Method on the section, e.g. ``"list"``.
        field_name (str): Response attribute holding the items.
        project_kw (str | None): Pass the project as this keyword (as a
            string) instead of positionally — for endpoints that filter by
            ``project_ids``.

    Returns:
        ListFn: The list function.
    """

    def list_fn(session: Session) -> list[BaseModel]:
        fn = getattr(getattr(session._engine.client, section), method)
        project_id = session._engine.project_id
        if project_kw is not None:
            kwargs = {project_kw: str(project_id)}
            return _paged(
                lambda skip, limit: fn(skip=skip, limit=limit, **kwargs), field_name
            )
        return _paged(
            lambda skip, limit: fn(project_id, skip=skip, limit=limit), field_name
        )

    return list_fn


def _account_scoped(section: str, field_name: str) -> ListFn:
    """Build a :data:`ListFn` for an unpaginated, account-level list endpoint."""

    def list_fn(session: Session) -> list[BaseModel]:
        page = getattr(session._engine.client, section).list()
        return list(getattr(page, field_name))

    return list_fn


def _list_projects(session: Session) -> list[BaseModel]:
    """Collect every project the caller can access."""
    client = session._engine.client
    return _paged(
        lambda skip, limit: client.projects.list(skip=skip, limit=limit), "projects"
    )


_CLIENT_KINDS: tuple[KindSpec, ...] = (
    KindSpec(
        kind="Project",
        aliases=("project", "projects", "proj"),
        list_columns=(("NAME", "name"), ("ID", "id"), ("OWNER", "owner_email")),
        list_fn=_list_projects,
    ),
    KindSpec(
        kind="Skill",
        aliases=("skill", "skills"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("AVAILABLE", "is_available"),
            ("AGENTS", "operator_count"),
            ("UPDATED", "updated_at"),
        ),
        list_fn=_project_scoped("skills", "list", "skills"),
    ),
    KindSpec(
        kind="Tool",
        aliases=(
            "tool",
            "tools",
            "agenttool",
            "agenttools",
            "agent-tool",
            "agent-tools",
        ),
        list_columns=(
            ("NAME", "name"),
            ("SLUG", "slug"),
            ("KIND", "kind"),
            ("AVAILABLE", "is_available"),
            ("ID", "id"),
        ),
        list_fn=_project_scoped("tools", "list", "tools"),
    ),
    KindSpec(
        kind="Endpoint",
        aliases=("endpoint", "endpoints", "ep", "eps"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("TYPE", "endpoint_type"),
            ("ENABLED", "is_enabled"),
            ("CREATED", "created_at"),
        ),
        list_fn=_project_scoped("endpoints", "list", "items"),
    ),
    KindSpec(
        kind="Notebook",
        aliases=("notebook", "notebooks", "nb", "nbs"),
        list_columns=(("TITLE", "title"), ("ID", "id"), ("UPDATED", "updated_at")),
        list_fn=_project_scoped(
            "notebooks", "list", "notebooks", project_kw="project_ids"
        ),
    ),
    KindSpec(
        kind="SavedQuery",
        aliases=("savedquery", "savedqueries", "saved-query", "saved-queries", "sq"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("DESCRIPTION", "description"),
            ("UPDATED", "updated_at"),
        ),
        list_fn=_project_scoped("queries", "list", "queries", project_kw="project_ids"),
    ),
    KindSpec(
        kind="WorkflowArtifact",
        aliases=(
            "workflowartifact",
            "workflowartifacts",
            "workflow-artifact",
            "workflow-artifacts",
            "artifact",
            "artifacts",
        ),
        list_columns=(
            ("FILE", "file_name"),
            ("ID", "id"),
            ("WORKFLOW", "workflow_name"),
            ("FORMAT", "format"),
            ("SIZE", "size_bytes"),
            ("CREATED", "created_at"),
        ),
        list_fn=_list_artifacts,
    ),
    KindSpec(
        kind="IngestSource",
        aliases=("ingestsource", "ingestsources", "ingest-source", "ingest-sources"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("TYPE", "source_type"),
            ("ENTRIES", "entries_count"),
            ("CREATED", "created_at"),
        ),
        list_fn=_project_scoped("ingest_sources", "list", "items"),
    ),
    KindSpec(
        kind="IngestConfig",
        aliases=("ingestconfig", "ingestconfigs", "ingest-config", "ingest-configs"),
        list_columns=(
            ("NAME", "name"),
            ("ID", "id"),
            ("CRON", "cron"),
            ("UPDATED", "updated_at"),
        ),
        list_fn=_project_scoped("ingest_sources", "list_configs", "items"),
    ),
    KindSpec(
        kind="AIConfig",
        aliases=("aiconfig", "aiconfigs", "ai-config", "ai-configs"),
        list_columns=(
            ("NAME", "config_name"),
            ("ID", "id"),
            ("PROVIDER", "provider_type"),
            ("MODEL", "model_name"),
            ("STATUS", "status"),
        ),
        list_fn=_account_scoped("ai_configs", "configs"),
    ),
    KindSpec(
        kind="DBConfig",
        aliases=("dbconfig", "dbconfigs", "db-config", "db-configs"),
        list_columns=(
            ("NAME", "config_name"),
            ("ID", "id"),
            ("PROVIDER", "provider_type"),
            ("ACTIVE", "is_active"),
            ("HEALTH", "connection_health"),
        ),
        list_fn=_account_scoped("db_configs", "configs"),
    ),
    KindSpec(
        kind="BlobConfig",
        aliases=("blobconfig", "blobconfigs", "blob-config", "blob-configs"),
        list_columns=(
            ("NAME", "config_name"),
            ("ID", "id"),
            ("PROVIDER", "provider_type"),
            ("BUCKET", "bucket_name"),
            ("ACTIVE", "is_active"),
        ),
        list_fn=_account_scoped("blob_configs", "configs"),
    ),
)

_KINDS = _KINDS + _CLIENT_KINDS

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


def resource_name(resource: BaseModel) -> str | None:
    """Compute a best-effort display name for a resource.

    Uses the first of :data:`NAME_FIELDS` that is set — ``name`` for most
    kinds, ``operator_name`` for annotations, ``config_name`` for provider
    configs, ``title`` for notebooks, ``file_name`` for artifacts — then the
    id as a last resort. Returns
    ``None`` only for resources that have no identity at all, which should
    never happen for server-returned instances.

    Args:
        resource (BaseModel): The resource (or client response item) to name.

    Returns:
        str | None: A human-usable name, or ``None`` if none of the
        candidate attributes are set.
    """
    for attr in NAME_FIELDS:
        value = getattr(resource, attr, None)
        if value:
            return str(value)
    rid: Any = getattr(resource, "id", None) or getattr(resource, "root_id", None)
    return str(rid) if rid is not None else None
