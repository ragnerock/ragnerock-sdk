"""``ragnerock apply`` — create or update resources from manifest files."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ragnerock.cli.manifest import (
    ManifestDoc,
    ManifestError,
    read_manifests,
    sort_by_apply_order,
)
from ragnerock.cli.session import open_session
from ragnerock.errors import ValidationError
from ragnerock.resources import (
    Annotation,
    ChunkType,
    Document,
    DocumentGroup,
    FileType,
    Operator,
    Workflow,
    WorkflowNode,
)
from ragnerock.resources.base import _Resource
from ragnerock.resources.condition import compile_condition
from ragnerock.session import Session


def apply_cmd(
    files: Annotated[
        list[str] | None,
        typer.Option(
            "--file",
            "-f",
            help=(
                "Manifest source. Repeatable. Accepts a file path, a "
                "directory (recursively loads every '*.yaml' / '*.yml' file "
                "beneath it in sorted order; hidden and non-YAML entries are "
                "skipped), or '-' to read a YAML stream from STDIN "
                "(supports heredocs and pipes)."
            ),
        ),
    ] = None,
) -> None:
    """Apply manifest documents idempotently.

    New resources (no match on ``metadata.name``) are created; existing ones
    are updated in place. Manifests are sorted by a fixed kind-dependency
    order (groups → operators → documents → workflows → annotations) so
    cross-manifest name lookups resolve correctly.
    """
    sources = files or []
    try:
        docs = read_manifests(sources)
    except ManifestError as e:
        typer.echo(f"ManifestError: {e}", err=True)
        raise typer.Exit(code=1) from e

    ordered = sort_by_apply_order(docs)

    with open_session() as session:
        _apply_docs(session, ordered)


def _apply_docs(session: Session, docs: list[ManifestDoc]) -> None:
    """Apply a list of manifests in dependency order, one kind stratum at a time."""
    for doc in docs:
        _apply_one(session, doc)
        session.commit()


def _apply_one(session: Session, doc: ManifestDoc) -> None:
    """Dispatch a single manifest to its kind-specific apply path."""
    kind = doc.spec_kind.kind
    if kind == "DocumentGroup":
        _apply_document_group(session, doc)
    elif kind == "Operator":
        _apply_operator(session, doc)
    elif kind == "Document":
        _apply_document(session, doc)
    elif kind == "Workflow":
        _apply_workflow(session, doc)
    elif kind == "Annotation":
        _apply_annotation(session, doc)
    else:  # pragma: no cover — guarded earlier by manifest._validate_doc
        raise typer.BadParameter(f"apply: unsupported kind {kind!r}")


def _apply_document_group(session: Session, doc: ManifestDoc) -> None:
    """Create or update a :class:`DocumentGroup` from a manifest.

    Looks up the group by ``metadata.name``; if missing, creates it. If
    present, overlays the spec fields onto the existing resource and stages
    an update. Either path is idempotent.

    Args:
        session (Session): Open session used to look up and stage changes.
        doc (ManifestDoc): Parsed manifest for a ``DocumentGroup``.
    """
    existing = session.get(DocumentGroup, name=doc.name)
    if existing is None:
        group = DocumentGroup(name=doc.name, **_clean(doc.spec))
        session.add(group)
        typer.echo(f"documentgroup/{doc.name} created")
        return
    _copy_spec(existing, doc.spec)
    session.update(existing)
    typer.echo(f"documentgroup/{doc.name} configured")


def _apply_operator(session: Session, doc: ManifestDoc) -> None:
    """Create or update an :class:`Operator` from a manifest.

    String enum values in ``spec.chunk_type`` are coerced to :class:`ChunkType`
    before the create/update decision.

    Args:
        session (Session): Open session used to look up and stage changes.
        doc (ManifestDoc): Parsed manifest for an ``Operator``.
    """
    spec = _coerce_operator_spec(doc.spec)
    existing = session.get(Operator, name=doc.name)
    if existing is None:
        op = Operator(name=doc.name, **spec)
        session.add(op)
        typer.echo(f"operator/{doc.name} created")
        return
    _copy_spec(existing, spec)
    session.update(existing)
    typer.echo(f"operator/{doc.name} configured")


def _apply_document(session: Session, doc: ManifestDoc) -> None:
    """Create or update a :class:`Document` from a manifest.

    ``spec.file_type`` strings are coerced to :class:`FileType`, and a
    ``spec.group`` name is resolved to a ``group_id`` via the session before
    the create/update decision.

    Args:
        session (Session): Open session used to resolve references and stage
            changes.
        doc (ManifestDoc): Parsed manifest for a ``Document``.
    """
    spec = _coerce_document_spec(session, doc.spec)
    existing = session.get(Document, name=doc.name)
    if existing is None:
        new_doc = Document(name=doc.name, **spec)
        session.add(new_doc)
        typer.echo(f"document/{doc.name} created")
        return
    _copy_spec(existing, spec)
    session.update(existing)
    typer.echo(f"document/{doc.name} configured")


def _apply_workflow(session: Session, doc: ManifestDoc) -> None:
    """Create or update a :class:`Workflow` along with its nodes and edges.

    Nodes and edges are popped off the spec before the workflow itself is
    created or updated, then reconciled in a second pass — the node CRUD
    calls need a server-assigned workflow id, so the workflow-level change
    is committed first.

    Args:
        session (Session): Open session used to look up and stage changes.
            Committed partway through so downstream node calls can reference
            the workflow id.
        doc (ManifestDoc): Parsed manifest for a ``Workflow``.
    """
    nodes_spec = doc.spec.pop("nodes", None) or []
    edges_spec = doc.spec.pop("edges", None) or []

    existing = session.get(Workflow, name=doc.name)
    if existing is None:
        wf = Workflow(name=doc.name, **_clean(doc.spec))
        session.add(wf)
        session.commit()  # node/edge work below needs the workflow id
        workflow = wf
        typer.echo(f"workflow/{doc.name} created")
    else:
        _copy_spec(existing, doc.spec)
        session.update(existing)
        session.commit()
        workflow = existing
        typer.echo(f"workflow/{doc.name} configured")

    _apply_workflow_nodes(session, workflow, nodes_spec, edges_spec)


def _apply_workflow_nodes(
    session: Session,
    workflow: Workflow,
    nodes_spec: list[Any],
    edges_spec: list[Any],
) -> None:
    """Reconcile the workflow's nodes and edges with the manifest."""
    if not isinstance(nodes_spec, list):
        raise typer.BadParameter("workflow.spec.nodes must be a list")
    if not isinstance(edges_spec, list):
        raise typer.BadParameter("workflow.spec.edges must be a list")

    nodes_by_op = {}  # operator name → committed WorkflowNode
    for entry in nodes_spec:
        if not isinstance(entry, dict):
            raise typer.BadParameter("each workflow node must be a mapping")
        # Accept `operator_name` as an alias so YAML emitted by `get -o yaml`
        # (which serializes the SDK field name) round-trips back through apply.
        op_name = entry.get("operator") or entry.get("operator_name")
        if not op_name:
            raise typer.BadParameter(
                "each workflow node requires 'operator' (or 'operator_name')"
            )
        operator = session.get(Operator, name=op_name)
        if operator is None:
            typer.echo(
                f"workflow {workflow.name!r}: operator {op_name!r} not found",
                err=True,
            )
            raise typer.Exit(code=1)
        existing = _find_node_by_operator(workflow, op_name)
        try:
            if existing is None:
                node = workflow.add_node(
                    operator=operator,
                    condition=entry.get("condition"),
                    persist=entry.get("persist", True),
                    on_error=entry.get("on_error", "FAIL_JOB"),
                    max_retries=entry.get("max_retries", 0),
                )
                nodes_by_op[op_name] = node
            else:
                # Workflow GET responses carry each node's `id` but often
                # omit `workflow_id` / `operator_id` (they're implicit from
                # the URL and operator name). Backfill them from context so
                # the update call has everything it needs.
                if existing.workflow_id is None:
                    existing.workflow_id = workflow.id
                if existing.operator_id is None:
                    existing.operator_id = operator.id
                if "condition" in entry:
                    raw = entry["condition"]
                    existing.condition = (
                        compile_condition(raw) if raw is not None else None
                    )
                if "persist" in entry:
                    existing.persist = entry["persist"]
                if "on_error" in entry:
                    existing.on_error = entry["on_error"]
                if "max_retries" in entry:
                    existing.max_retries = entry["max_retries"]
                session.update(existing)
                nodes_by_op[op_name] = existing
        except ValidationError as e:
            raise typer.BadParameter(
                f"workflow {workflow.name!r} node {op_name!r}: {e}"
            ) from e

    session.commit()

    for edge in edges_spec:
        if isinstance(edge, list) and len(edge) == 2:
            src_name, dst_name = edge
        elif isinstance(edge, dict):
            src_name = edge.get("from")
            dst_name = edge.get("to")
        else:
            raise typer.BadParameter(
                "each edge must be [src, dst] or {from: src, to: dst}"
            )
        src = nodes_by_op.get(src_name)
        dst = nodes_by_op.get(dst_name)
        if src is None or dst is None:
            typer.echo(
                f"workflow {workflow.name!r}: edge references unknown operator "
                f"({src_name!r} -> {dst_name!r})",
                err=True,
            )
            raise typer.Exit(code=1)
        _ = src >> dst  # wiring via the WorkflowNode `>>` operator

    session.commit()


def _find_node_by_operator(
    workflow: Workflow, operator_name: str
) -> WorkflowNode | None:
    """Find a workflow node whose operator has the given name.

    Args:
        workflow (Workflow): Workflow whose nodes to search.
        operator_name (str): Operator name to match on, as present in
            :attr:`WorkflowNode.operator_name`.

    Returns:
        WorkflowNode | None: The first matching node, or ``None`` if no node
        references that operator. Node identity within a workflow is by
        operator, so there is at most one match.
    """
    for node in workflow.nodes:
        if node.operator_name == operator_name:
            return node
    return None


def _apply_annotation(session: Session, doc: ManifestDoc) -> None:
    """Create an :class:`Annotation` from a manifest.

    Annotations are additive only — there is no server-side update-by-name
    path — so each apply creates a new annotation. A ``spec.operator`` name
    is resolved to ``operator_id`` before creation. The manifest's
    ``metadata.name`` is used for CLI output only; annotation identity lives
    on ``root_id``.

    Args:
        session (Session): Open session used to resolve the operator and
            stage the create.
        doc (ManifestDoc): Parsed manifest for an ``Annotation``.
    """
    spec = dict(doc.spec)
    op_name = spec.pop("operator", None)
    if op_name is not None and "operator_id" not in spec:
        operator = session.get(Operator, name=op_name)
        if operator is None:
            typer.echo(
                f"annotation/{doc.name}: operator {op_name!r} not found", err=True
            )
            raise typer.Exit(code=1)
        spec["operator_id"] = operator.id
    # Annotations: name is advisory only; identity is on root_id.
    ann = Annotation(**_clean(spec))
    session.add(ann)
    typer.echo(f"annotation/{doc.name} created")


def _coerce_operator_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Coerce string enum names (e.g. ``PARAGRAPH``) to their SDK enums."""
    out = dict(spec)
    chunk = out.get("chunk_type")
    if isinstance(chunk, str):
        out["chunk_type"] = ChunkType[chunk.upper()]
    return _clean(out)


def _coerce_document_spec(session: Session, spec: dict[str, Any]) -> dict[str, Any]:
    """Coerce file_type enums and resolve ``group: <name>`` → ``group_id``."""
    out = dict(spec)
    ft = out.get("file_type")
    if isinstance(ft, str):
        out["file_type"] = FileType[ft.upper()]
    group = out.pop("group", None)
    if group is not None and "group_id" not in out:
        matched = (
            session.get(DocumentGroup, name=group) if isinstance(group, str) else None
        )
        if matched is None:
            raise typer.BadParameter(f"DocumentGroup {group!r} not found")
        out["group_id"] = matched.id
    return _clean(out)


def _copy_spec(target: _Resource, spec: dict[str, Any]) -> None:
    """Copy scalar fields from ``spec`` onto ``target`` in place."""
    model_fields = type(target).model_fields
    for key, value in spec.items():
        if key in model_fields:
            setattr(target, key, value)


def _clean(spec: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values so we don't overwrite model defaults with nulls."""
    return {k: v for k, v in spec.items() if v is not None}
