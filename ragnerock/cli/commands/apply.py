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
from ragnerock.resources import (
    Annotation,
    ChunkType,
    Document,
    DocumentGroup,
    FileType,
    Operator,
    Workflow,
)
from ragnerock.resources.base import _Resource
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

    alias_to_node = {}  # manifest alias → committed WorkflowNode
    for entry in nodes_spec:
        if not isinstance(entry, dict):
            raise typer.BadParameter("each workflow node must be a mapping")
        alias = entry.get("name")
        op_name = entry.get("operator")
        if not alias or not op_name:
            raise typer.BadParameter(
                "each workflow node requires 'name' and 'operator'"
            )
        operator = session.get(Operator, name=op_name)
        if operator is None:
            typer.echo(
                f"workflow {workflow.name!r}: operator {op_name!r} not found",
                err=True,
            )
            raise typer.Exit(code=1)
        existing = _find_node_by_operator(workflow, op_name)
        if existing is None:
            node = workflow.add_node(
                operator=operator,
                condition=entry.get("condition"),
                persist=entry.get("persist", True),
                on_error=entry.get("on_error", "FAIL_JOB"),
                max_retries=entry.get("max_retries", 0),
            )
            alias_to_node[alias] = node
        else:
            if "condition" in entry:
                existing.condition = entry["condition"]
            if "persist" in entry:
                existing.persist = entry["persist"]
            if "on_error" in entry:
                existing.on_error = entry["on_error"]
            if "max_retries" in entry:
                existing.max_retries = entry["max_retries"]
            session.update(existing)
            alias_to_node[alias] = existing

    session.commit()

    for edge in edges_spec:
        if isinstance(edge, list) and len(edge) == 2:
            src_alias, dst_alias = edge
        elif isinstance(edge, dict):
            src_alias = edge.get("from")
            dst_alias = edge.get("to")
        else:
            raise typer.BadParameter(
                "each edge must be [src, dst] or {from: src, to: dst}"
            )
        src = alias_to_node.get(src_alias)
        dst = alias_to_node.get(dst_alias)
        if src is None or dst is None:
            typer.echo(
                f"workflow {workflow.name!r}: edge references unknown node "
                f"alias ({src_alias!r} -> {dst_alias!r})",
                err=True,
            )
            raise typer.Exit(code=1)
        _ = src >> dst  # wiring via the WorkflowNode `>>` operator

    session.commit()


def _find_node_by_operator(workflow: Workflow, operator_name: str) -> Any:
    for node in workflow.nodes:
        if node.operator_name == operator_name:
            return node
    return None


def _apply_annotation(session: Session, doc: ManifestDoc) -> None:
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
