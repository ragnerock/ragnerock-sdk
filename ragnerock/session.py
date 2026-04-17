"""Session: the user-facing API.

A :class:`Session` is bound to a single :class:`~ragnerock.engine.Engine` and
a single project. It behaves like a SQLAlchemy session: reads are immediate;
writes stage into a unit of work and flush on :meth:`Session.commit`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from ragnerock.errors import (
    CommitError,
    NotFoundError,
    RagnerockError,
    ValidationError,
)
from ragnerock.iterator import PageResult, PaginatedIterator
from ragnerock.query_result import QueryResult
from ragnerock.resources import (
    Annotation,
    Chunk,
    ChunkType,
    Document,
    DocumentGroup,
    Job,
    JobStatus,
    Operator,
    Page,
    Workflow,
)
from ragnerock.resources.base import _Resource

if TYPE_CHECKING:
    from ragnerock.engine import Engine

T = TypeVar("T", bound=_Resource)


_READ_ONLY_TYPES = (Page,)
_UPDATE_UNSUPPORTED_TYPES = (Page, Chunk)


class _Pending:
    """Internal staging queue for the unit of work."""

    added: list[_Resource]
    dirty: list[_Resource]
    deleted: list[_Resource]

    def __init__(self) -> None:
        self.added = []
        self.dirty = []
        self.deleted = []

    def is_empty(self) -> bool:
        return not (self.added or self.dirty or self.deleted)

    def clear(self) -> None:
        self.added.clear()
        self.dirty.clear()
        self.deleted.clear()


def _as_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


def _resource_id(resource: _Resource) -> UUID | None:
    if isinstance(resource, Annotation):
        return resource.root_id
    return getattr(resource, "id", None)


def _copy_fields(target: _Resource, response: Any) -> None:
    if response is None:
        return
    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif isinstance(response, dict):
        data = response
    else:
        return
    for field_name in type(target).model_fields:
        if field_name in data:
            setattr(target, field_name, data[field_name])


class Session:
    """A session scoped to a single Ragnerock project.

    Reads (:meth:`get`, :meth:`list`, :meth:`query`, :meth:`run`) fire
    immediately. Writes (:meth:`add`, :meth:`update`, :meth:`delete`)
    stage; call :meth:`commit` to flush or :meth:`rollback` to discard.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._pending = _Pending()

    # -- context manager -------------------------------------------------------

    def __enter__(self) -> Session:
        """Connect the engine. Auth / project-resolution errors surface here."""
        self._engine._ensure_connected()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Discard any staged ops. Does NOT auto-commit."""
        self._pending.clear()

    # -- reads (immediate) -----------------------------------------------------

    def get(
        self,
        resource_type: type[T],
        *,
        id: UUID | str | None = None,
        name: str | None = None,
    ) -> T | None:
        """Fetch a single resource by ``id=`` or ``name=``."""
        if id is None and name is None:
            raise ValidationError("get() requires either id= or name=")

        client = self._engine.client

        if resource_type is Document:
            try:
                if id is not None:
                    response = client.documents.get(_as_uuid(id))
                else:
                    response = client.documents.get_by_name(
                        name, project_id=self._engine.project_id  # type: ignore[arg-type]
                    )
            except NotFoundError:
                return None
            return self._bind(_build(Document, response))  # type: ignore[return-value]

        if resource_type is DocumentGroup:
            if name is not None:
                raise ValidationError("DocumentGroup does not support lookup by name")
            try:
                response = client.groups.get(self._engine.project_id, _as_uuid(id))  # type: ignore[arg-type]
            except NotFoundError:
                return None
            return self._bind(_build(DocumentGroup, response))  # type: ignore[return-value]

        if resource_type is Chunk:
            if name is not None:
                raise ValidationError("Chunk does not support lookup by name")
            try:
                response = client.chunks.get(_as_uuid(id))  # type: ignore[arg-type]
            except NotFoundError:
                return None
            return self._bind(_build(Chunk, response))  # type: ignore[return-value]

        if resource_type is Page:
            if name is not None:
                raise ValidationError("Page does not support lookup by name")
            try:
                response = client.pages.get(_as_uuid(id))  # type: ignore[arg-type]
            except NotFoundError:
                return None
            return self._bind(_build(Page, response))  # type: ignore[return-value]

        if resource_type is Annotation:
            if name is not None:
                raise ValidationError("Annotation does not support lookup by name")
            try:
                response = client.annotations.get(_as_uuid(id))  # type: ignore[arg-type]
            except NotFoundError:
                return None
            return self._bind(_build(Annotation, response))  # type: ignore[return-value]

        if resource_type is Job:
            if name is not None:
                raise ValidationError("Job does not support lookup by name")
            try:
                response = client.jobs.get(_as_uuid(id))  # type: ignore[arg-type]
            except NotFoundError:
                return None
            return self._bind(_build(Job, response))  # type: ignore[return-value]

        if resource_type is Operator:
            if id is not None:
                try:
                    response = client.operators.get(_as_uuid(id))
                except NotFoundError:
                    return None
                return self._bind(_build(Operator, response))  # type: ignore[return-value]
            return self._find_by_name_via_list(  # type: ignore[return-value]
                Operator, name, _fetch_operator_by_id=client.operators.get
            )

        if resource_type is Workflow:
            if id is not None:
                try:
                    response = client.workflows.get(_as_uuid(id))
                except NotFoundError:
                    return None
                return self._bind(_build(Workflow, response))  # type: ignore[return-value]
            return self._find_by_name_via_list(  # type: ignore[return-value]
                Workflow, name, _fetch_operator_by_id=client.workflows.get
            )

        raise TypeError(f"get() does not support resource type {resource_type!r}")

    def _find_by_name_via_list(
        self,
        resource_type: type[T],
        name: str | None,
        *,
        _fetch_operator_by_id: Any,
    ) -> T | None:
        if name is None:
            raise ValidationError("get() requires either id= or name=")
        for item in self.list(resource_type).all():
            if getattr(item, "name", None) == name:
                item_id = getattr(item, "id", None)
                if item_id is not None:
                    try:
                        response = _fetch_operator_by_id(item_id)
                    except NotFoundError:
                        return None
                    return self._bind(_build(resource_type, response))
                return item
        return None

    def list(self, resource_type: type[T], **filters: Any) -> PaginatedIterator[T]:
        """List resources, optionally filtered."""
        client = self._engine.client
        project_id = self._engine.project_id

        if resource_type is Document:
            def fetch(skip: int, limit: int) -> PageResult[Document]:
                response = client.documents.list(
                    project_ids=str(project_id), skip=skip, limit=limit
                )
                items = [self._bind(_build(Document, r)) for r in response.documents]
                return PageResult(items, response.total)
            return PaginatedIterator(fetch)  # type: ignore[return-value]

        if resource_type is DocumentGroup:
            def fetch(skip: int, limit: int) -> PageResult[DocumentGroup]:
                response = client.groups.list(project_id, skip=skip, limit=limit)
                items = [
                    self._bind(_build(DocumentGroup, r)) for r in response.groups
                ]
                return PageResult(items, response.total)
            return PaginatedIterator(fetch)  # type: ignore[return-value]

        if resource_type is Chunk:
            document_id = filters.get("document_id")
            if document_id is None:
                raise ValidationError("Chunk list requires document_id=")

            def fetch(skip: int, limit: int) -> PageResult[Chunk]:
                response = client.chunks.list(
                    document_ids=str(_as_uuid(document_id)), skip=skip, limit=limit
                )
                items = [self._bind(_build(Chunk, r)) for r in response.chunks]
                return PageResult(items, response.total)
            return PaginatedIterator(fetch)  # type: ignore[return-value]

        if resource_type is Page:
            document_id = filters.get("document_id")
            if document_id is None:
                raise ValidationError("Page list requires document_id=")

            def fetch(skip: int, limit: int) -> PageResult[Page]:
                response = client.pages.list(
                    _as_uuid(document_id), skip=skip, limit=limit
                )
                items = [self._bind(_build(Page, r)) for r in response.pages]
                return PageResult(items, response.total)
            return PaginatedIterator(fetch)  # type: ignore[return-value]

        if resource_type is Annotation:
            return self._list_annotations(**filters)  # type: ignore[return-value]

        if resource_type is Operator:
            def fetch(skip: int, limit: int) -> PageResult[Operator]:
                response = client.operators.list(
                    project_ids=str(project_id), skip=skip, limit=limit
                )
                items = [
                    self._bind(_build(Operator, r)) for r in response.operators
                ]
                return PageResult(items, response.total)
            return PaginatedIterator(fetch)  # type: ignore[return-value]

        if resource_type is Workflow:
            def fetch(skip: int, limit: int) -> PageResult[Workflow]:
                response = client.workflows.list(
                    project_ids=str(project_id), skip=skip, limit=limit
                )
                items = [
                    self._bind(_build(Workflow, r)) for r in response.workflows
                ]
                return PageResult(items, response.total)
            return PaginatedIterator(fetch)  # type: ignore[return-value]

        if resource_type is Job:
            status = filters.get("status")
            status_filter: str | None = None
            if status is not None:
                if isinstance(status, (list, tuple, set)):
                    status_filter = ",".join(str(int(s)) for s in status)
                else:
                    status_filter = str(int(status))

            def fetch(skip: int, limit: int) -> PageResult[Job]:
                response = client.jobs.list(
                    project_id=project_id,
                    status_filter=status_filter,
                    skip=skip,
                    limit=limit,
                )
                items = [self._bind(_build(Job, r)) for r in response.jobs]
                return PageResult(items, response.total)
            return PaginatedIterator(fetch)  # type: ignore[return-value]

        raise TypeError(f"list() does not support resource type {resource_type!r}")

    def _list_annotations(self, **filters: Any) -> PaginatedIterator[Annotation]:
        client = self._engine.client
        document_id = filters.get("document_id")
        chunk_id = filters.get("chunk_id")
        operator_id = filters.get("operator_id")
        operator_name = filters.get("operator_name")
        hydrated = filters.get("hydrated", False)

        if document_id is not None:
            if operator_id is not None:
                op_id = _as_uuid(operator_id)
                doc_id = _as_uuid(document_id)

                def fetch(skip: int, limit: int) -> PageResult[Annotation]:
                    response = client.annotations.list_by_document_and_operator_id(
                        doc_id, op_id, skip=skip, limit=limit
                    )
                    items = [
                        self._bind(_build(Annotation, r))
                        for r in response.annotations
                    ]
                    return PageResult(items, response.total)
                return PaginatedIterator(fetch)

            if operator_name is not None:
                doc_id = _as_uuid(document_id)

                def fetch(skip: int, limit: int) -> PageResult[Annotation]:
                    response = client.annotations.list_by_document_and_operator_name(
                        doc_id, operator_name, skip=skip, limit=limit
                    )
                    items = [
                        self._bind(_build(Annotation, r))
                        for r in response.annotations
                    ]
                    return PageResult(items, response.total)
                return PaginatedIterator(fetch)

            doc_id = _as_uuid(document_id)

            def fetch(skip: int, limit: int) -> PageResult[Annotation]:
                response = client.annotations.list_by_document(
                    doc_id, skip=skip, limit=limit
                )
                items = [
                    self._bind(_build(Annotation, r)) for r in response.annotations
                ]
                return PageResult(items, response.total)
            return PaginatedIterator(fetch)

        if chunk_id is not None:
            cid = _as_uuid(chunk_id)

            def fetch(skip: int, limit: int) -> PageResult[Annotation]:
                response = client.annotations.list_by_chunk(
                    cid, skip=skip, limit=limit
                )
                items = [
                    self._bind(_build(Annotation, r)) for r in response.annotations
                ]
                return PageResult(items, response.total)
            return PaginatedIterator(fetch)

        if operator_id is not None:
            oid = _as_uuid(operator_id)
            if hydrated:
                def fetch(skip: int, limit: int) -> PageResult[Annotation]:
                    response = client.annotations.list_hydrated_by_operator(
                        oid, skip=skip, limit=limit
                    )
                    items = [
                        self._bind(_build(Annotation, r))
                        for r in response.annotations
                    ]
                    return PageResult(items, response.total)
                return PaginatedIterator(fetch)

            def fetch(skip: int, limit: int) -> PageResult[Annotation]:
                response = client.annotations.list_by_operator(
                    oid, skip=skip, limit=limit
                )
                items = [
                    self._bind(_build(Annotation, r)) for r in response.annotations
                ]
                return PageResult(items, response.total)
            return PaginatedIterator(fetch)

        raise ValidationError(
            "Annotation list requires one of document_id=, chunk_id=, or operator_id="
        )

    def query(self, sql: str, *, limit: int = 1000) -> QueryResult:
        """Execute an annotation SQL query."""
        response = self._engine.client.queries.execute(
            project_id=self._engine.project_id,
            query=sql,
            format="dataframe",
            limit=limit,
        )
        return QueryResult(
            columns=response.columns,
            data=response.data,
            row_count=response.row_count,
            query_time_ms=response.query_time_ms,
        )

    def run(self, workflow: Workflow, *, documents: list[Document]) -> Job:
        """Run a workflow on a set of documents. Returns a :class:`Job` handle."""
        if workflow.id is None:
            raise ValidationError(
                "run() requires committed resources; call session.commit() first"
            )
        for doc in documents:
            if doc.id is None:
                raise ValidationError(
                    "run() requires committed resources; call session.commit() first"
                )

        response = self._engine.client.jobs.create_manual(
            document_ids=[d.id for d in documents if d.id is not None],
            workflow_ids=[workflow.id],
        )
        job = Job(id=response.job_ids[0], status=JobStatus.NOT_STARTED)
        return self._bind(job)

    # -- writes (staged) -------------------------------------------------------

    def add(self, resource: _Resource) -> None:
        """Stage a resource for creation. Does not hit the network."""
        if isinstance(resource, _READ_ONLY_TYPES):
            raise ValidationError(
                f"{type(resource).__name__} is read-only; cannot add"
            )
        if isinstance(resource, Job):
            raise ValidationError(
                "Jobs cannot be added directly; use session.run(workflow, documents=[...])"
            )
        if not isinstance(
            resource,
            (Document, DocumentGroup, Chunk, Annotation, Operator, Workflow),
        ):
            raise TypeError(
                f"add() does not support resource type {type(resource).__name__}"
            )
        if _resource_id(resource) is not None:
            raise ValidationError(
                f"Cannot add an already-persisted {type(resource).__name__}; "
                "use session.update() instead"
            )
        for existing in self._pending.added:
            if existing is resource:
                return
        self._pending.added.append(resource)

    def update(self, resource: _Resource) -> None:
        """Stage an existing resource for update. Does not hit the network."""
        if isinstance(resource, _UPDATE_UNSUPPORTED_TYPES):
            raise ValidationError(
                f"{type(resource).__name__} does not support update"
            )
        if not isinstance(
            resource,
            (Document, DocumentGroup, Annotation, Operator, Workflow),
        ):
            raise TypeError(
                f"update() does not support resource type {type(resource).__name__}"
            )
        if _resource_id(resource) is None:
            raise ValidationError(
                f"Cannot update an unpersisted {type(resource).__name__}; "
                "it must have an id"
            )
        for existing in self._pending.dirty:
            if existing is resource:
                return
        self._pending.dirty.append(resource)

    def delete(self, resource: _Resource) -> None:
        """Stage a resource for deletion. Does not hit the network."""
        if isinstance(resource, _READ_ONLY_TYPES):
            raise ValidationError(
                f"{type(resource).__name__} is read-only; cannot delete"
            )
        if not isinstance(
            resource,
            (Document, DocumentGroup, Chunk, Annotation, Operator, Workflow),
        ):
            raise TypeError(
                f"delete() does not support resource type {type(resource).__name__}"
            )
        for i, existing in enumerate(self._pending.added):
            if existing is resource:
                self._pending.added.pop(i)
                return
        if _resource_id(resource) is None:
            raise ValidationError(
                f"Cannot delete an unpersisted {type(resource).__name__}; "
                "it must have an id"
            )
        for existing in self._pending.deleted:
            if existing is resource:
                return
        self._pending.deleted.append(resource)

    def commit(self) -> None:
        """Flush all staged ops to the API."""
        if self._pending.is_empty():
            return

        committed: list[_Resource] = []
        adds = list(self._pending.added)
        updates = list(self._pending.dirty)
        deletes = list(self._pending.deleted)

        for resource in adds:
            self._precheck_create(resource)

        all_ops: list[tuple[str, _Resource]] = (
            [("add", r) for r in adds]
            + [("update", r) for r in updates]
            + [("delete", r) for r in deletes]
        )

        for i, (op, resource) in enumerate(all_ops):
            try:
                if op == "add":
                    self._create_resource(resource)
                elif op == "update":
                    self._update_resource(resource)
                else:
                    self._delete_resource(resource)
                committed.append(resource)
            except Exception as e:
                pending = [r for _, r in all_ops[i:]]
                self._pending.clear()
                raise CommitError(
                    f"commit failed on {op} of {type(resource).__name__}: {e}",
                    committed=committed,
                    pending=pending,
                    cause=e,
                ) from e

        self._pending.clear()

    def _precheck_create(self, resource: _Resource) -> None:
        if isinstance(resource, Document):
            if not resource.file_path and not resource.source_url:
                raise ValidationError(
                    "Document create requires either file_path or source_url"
                )
        elif isinstance(resource, Annotation):
            if resource.operator_id is None:
                raise ValidationError("Annotation create requires operator_id")
            if (
                resource.document_id is None
                and resource.chunk_id is None
                and resource.page_id is None
            ):
                raise ValidationError(
                    "Annotation create requires one of document_id, chunk_id, or page_id"
                )

    def refresh(self, resource: _Resource) -> None:
        """Re-fetch ``resource`` from the server and overwrite fields in place."""
        rid = _resource_id(resource)
        if rid is None:
            raise ValidationError(
                f"Cannot refresh an unpersisted {type(resource).__name__}"
            )
        client = self._engine.client

        if isinstance(resource, Document):
            response = client.documents.get(rid)
        elif isinstance(resource, DocumentGroup):
            response = client.groups.get(self._engine.project_id, rid)
        elif isinstance(resource, Chunk):
            response = client.chunks.get(rid)
        elif isinstance(resource, Page):
            response = client.pages.get(rid)
        elif isinstance(resource, Annotation):
            response = client.annotations.get(rid)
        elif isinstance(resource, Operator):
            response = client.operators.get(rid)
        elif isinstance(resource, Workflow):
            response = client.workflows.get(rid)
        elif isinstance(resource, Job):
            response = client.jobs.get(rid)
        else:
            raise TypeError(
                f"refresh() does not support resource type {type(resource).__name__}"
            )

        _copy_fields(resource, response)

    def rollback(self) -> None:
        """Discard the staging queue. Local-only; does not touch the server."""
        self._pending.clear()

    # -- per-type create / update / delete -------------------------------------

    def _create_resource(self, resource: _Resource) -> None:
        client = self._engine.client

        if isinstance(resource, Document):
            if not resource.file_path and not resource.source_url:
                raise ValidationError(
                    "Document create requires either file_path or source_url"
                )
            import os

            file_path = resource.file_path
            if file_path is not None and not os.path.isfile(file_path):
                file_path = None
            response = client.documents.create(
                project_id=self._engine.project_id,
                file_path=file_path,
                source_url=resource.source_url,
                name=resource.name,
                group_id=resource.group_id,
                file_type=resource.file_type,
                metadata=resource.metadata,
            )
            _copy_fields(resource, response)
            return

        if isinstance(resource, DocumentGroup):
            if not resource.name:
                raise ValidationError("DocumentGroup create requires name")
            response = client.groups.create(
                self._engine.project_id, name=resource.name
            )
            _copy_fields(resource, response)
            return

        if isinstance(resource, Chunk):
            if resource.document_id is None:
                raise ValidationError("Chunk create requires document_id")
            if resource.start_index is None or resource.end_index is None:
                raise ValidationError(
                    "Chunk create requires start_index and end_index"
                )
            response = client.chunks.create(
                document_id=resource.document_id,
                start_index=resource.start_index,
                end_index=resource.end_index,
                content=resource.content,
                metadata=resource.metadata,
            )
            _copy_fields(resource, response)
            return

        if isinstance(resource, Annotation):
            if resource.operator_id is None:
                raise ValidationError("Annotation create requires operator_id")
            if (
                resource.document_id is None
                and resource.chunk_id is None
                and resource.page_id is None
            ):
                raise ValidationError(
                    "Annotation create requires one of document_id, chunk_id, or page_id"
                )
            response = client.annotations.create(
                operator_id=resource.operator_id,
                data=resource.data or {},
                document_id=resource.document_id,
                chunk_id=resource.chunk_id,
                page_id=resource.page_id,
                confidence_score=resource.confidence_score,
            )
            _copy_fields(resource, response)
            return

        if isinstance(resource, Operator):
            if not resource.name:
                raise ValidationError("Operator create requires name")
            if resource.jsonschema is None:
                raise ValidationError("Operator create requires jsonschema")
            if resource.generation_prompt is None:
                raise ValidationError("Operator create requires generation_prompt")
            if resource.chunk_type is None:
                raise ValidationError("Operator create requires chunk_type")
            response = client.operators.create(
                project_id=self._engine.project_id,
                name=resource.name,
                jsonschema=resource.jsonschema,
                generation_prompt=resource.generation_prompt,
                chunk_type=int(resource.chunk_type),
                description=resource.description,
                batch_size=resource.batch_size,
                multi_annotation=resource.multi_annotation,
            )
            _copy_fields(resource, response)
            return

        if isinstance(resource, Workflow):
            if not resource.name:
                raise ValidationError("Workflow create requires name")
            response = client.workflows.create(
                project_id=self._engine.project_id,
                name=resource.name,
                description=resource.description,
                is_active=resource.is_active,
                auto_run_on_upload=resource.auto_run_on_upload,
            )
            _copy_fields(resource, response)
            return

        raise TypeError(
            f"create dispatch not supported for {type(resource).__name__}"
        )

    def _update_resource(self, resource: _Resource) -> None:
        client = self._engine.client

        if isinstance(resource, Document):
            response = client.documents.update(
                resource.id,  # type: ignore[arg-type]
                name=resource.name,
                group_id=resource.group_id,
                storage_path=resource.storage_path,
                metadata=resource.metadata,
            )
            _copy_fields(resource, response)
            return

        if isinstance(resource, DocumentGroup):
            response = client.groups.update(
                self._engine.project_id,
                resource.id,  # type: ignore[arg-type]
                name=resource.name or "",
            )
            _copy_fields(resource, response)
            return

        if isinstance(resource, Annotation):
            response = client.annotations.update(
                resource.root_id,  # type: ignore[arg-type]
                data=resource.data or {},
            )
            _copy_fields(resource, response)
            return

        if isinstance(resource, Operator):
            response = client.operators.update(
                resource.id,  # type: ignore[arg-type]
                name=resource.name,
                description=resource.description,
                jsonschema=resource.jsonschema,
                generation_prompt=resource.generation_prompt,
                chunk_type=int(resource.chunk_type) if resource.chunk_type is not None else None,
                batch_size=resource.batch_size,
                multi_annotation=resource.multi_annotation,
            )
            _copy_fields(resource, response)
            return

        if isinstance(resource, Workflow):
            response = client.workflows.update(
                resource.id,  # type: ignore[arg-type]
                name=resource.name,
                description=resource.description,
                is_active=resource.is_active,
                auto_run_on_upload=resource.auto_run_on_upload,
            )
            _copy_fields(resource, response)
            return

        raise TypeError(
            f"update dispatch not supported for {type(resource).__name__}"
        )

    def _delete_resource(self, resource: _Resource) -> None:
        client = self._engine.client

        if isinstance(resource, Document):
            client.documents.delete(resource.id)  # type: ignore[arg-type]
            return
        if isinstance(resource, DocumentGroup):
            client.groups.delete(self._engine.project_id, resource.id)  # type: ignore[arg-type]
            return
        if isinstance(resource, Chunk):
            client.chunks.delete(resource.id)  # type: ignore[arg-type]
            return
        if isinstance(resource, Annotation):
            client.annotations.delete(resource.root_id)  # type: ignore[arg-type]
            return
        if isinstance(resource, Operator):
            client.operators.delete(resource.id)  # type: ignore[arg-type]
            return
        if isinstance(resource, Workflow):
            client.workflows.delete(resource.id)  # type: ignore[arg-type]
            return

        raise TypeError(
            f"delete dispatch not supported for {type(resource).__name__}"
        )

    # -- internal --------------------------------------------------------------

    def _bind(self, resource: T) -> T:
        """Attach this session to a resource."""
        resource._bind(self)
        return resource

    def _list_related(
        self,
        parent: _Resource,
        resource_type: type[T],
        **kwargs: Any,
    ) -> PaginatedIterator[T]:
        if isinstance(parent, Document):
            if resource_type is Chunk:
                return self.list(Chunk, document_id=parent.id)
            if resource_type is Page:
                return self.list(Page, document_id=parent.id)
            if resource_type is Annotation:
                operator_name = kwargs.get("operator_name")
                if operator_name is not None:
                    return self.list(
                        Annotation,
                        document_id=parent.id,
                        operator_name=operator_name,
                    )
                return self.list(Annotation, document_id=parent.id)

        if isinstance(parent, Chunk):
            if resource_type is Annotation:
                return self.list(Annotation, chunk_id=parent.id)

        if isinstance(parent, DocumentGroup):
            if resource_type is Document:
                group_id = parent.id
                client = self._engine.client

                def fetch(skip: int, limit: int) -> PageResult[Document]:
                    response = client.groups.list_documents(
                        group_id, skip=skip, limit=limit
                    )
                    items = [
                        self._bind(_build(Document, r)) for r in response.documents
                    ]
                    return PageResult(items, response.total)
                return PaginatedIterator(fetch)  # type: ignore[return-value]

        if isinstance(parent, Operator):
            if resource_type is Annotation:
                doc = kwargs.get("document")
                if doc is not None:
                    return self.list(
                        Annotation,
                        document_id=doc.id,
                        operator_id=parent.id,
                    )
                hydrated = kwargs.get("hydrated", False)
                return self.list(
                    Annotation, operator_id=parent.id, hydrated=hydrated
                )

        raise TypeError(
            f"{type(parent).__name__} does not support list({resource_type.__name__})"
        )


def _build(resource_type: type[T], response: Any) -> T:
    """Construct a resource from a client response model."""
    if response is None:
        return resource_type()
    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif isinstance(response, dict):
        data = dict(response)
    else:
        raise TypeError(f"Cannot build {resource_type.__name__} from {type(response)!r}")

    filtered = {
        k: v for k, v in data.items() if k in resource_type.model_fields
    }
    return resource_type(**filtered)
