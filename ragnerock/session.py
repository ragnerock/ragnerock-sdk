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
    ValidationError,
)
from ragnerock.iterator import PageResult, PaginatedIterator
from ragnerock.query_result import QueryResult
from ragnerock.resources import (
    Annotation,
    Chunk,
    Document,
    DocumentGroup,
    Job,
    JobStatus,
    Operator,
    Page,
    Workflow,
    WorkflowNode,
)
from ragnerock.resources.base import _Resource

if TYPE_CHECKING:
    from ragnerock.engine import Engine

T = TypeVar("T", bound=_Resource)


_READ_ONLY_TYPES = (Page,)
_UPDATE_UNSUPPORTED_TYPES = (Page, Chunk)


class _Pending:
    """Internal unit-of-work queue, preserving insertion order across ops.

    A single ordered list of ``(op, resource)`` pairs so a mixed sequence of
    :meth:`Session.add`, :meth:`Session.update`, and :meth:`Session.delete`
    calls flushes in exactly the order the caller staged them.

    Attributes:
        ops (list[tuple[str, _Resource]]): Staged operations in insertion
            order; ``op`` is one of ``"add"``, ``"update"``, ``"delete"``.
    """

    ops: list[tuple[str, _Resource]]

    def __init__(self) -> None:
        """Initialize an empty unit of work."""
        self.ops = []

    def is_empty(self) -> bool:
        """Report whether the queue is empty.

        Returns:
            bool: ``True`` if nothing is staged, ``False`` otherwise.
        """
        return not self.ops

    def clear(self) -> None:
        """Drop every staged operation."""
        self.ops.clear()

    def has(self, op: str, resource: _Resource) -> bool:
        """Return ``True`` if ``resource`` is already staged for ``op``."""
        return any(o == op and r is resource for o, r in self.ops)

    def remove_add(self, resource: _Resource) -> bool:
        """Drop a pending add of ``resource``. Returns ``True`` if removed."""
        for i, (op, r) in enumerate(self.ops):
            if op == "add" and r is resource:
                self.ops.pop(i)
                return True
        return False


def _as_uuid(value: UUID | str) -> UUID:
    """Coerce a string identifier to a :class:`~uuid.UUID`.

    Args:
        value (UUID | str): Either a UUID instance or its string
            representation.

    Returns:
        UUID: The equivalent :class:`~uuid.UUID`. Instances are returned
        unchanged.
    """
    if isinstance(value, UUID):
        return value
    return UUID(value)


def _resource_id(resource: _Resource) -> UUID | None:
    """Return the server-assigned identity of a resource.

    Every resource except :class:`Annotation` exposes its identity as ``id``.
    Annotations use ``root_id`` on the wire, so this helper normalizes the
    lookup for internal code that doesn't care about the distinction.

    Args:
        resource (_Resource): The resource to inspect.

    Returns:
        UUID | None: The UUID identity, or ``None`` if the resource is not
        yet persisted.
    """
    if isinstance(resource, Annotation):
        return resource.root_id
    return getattr(resource, "id", None)


def _copy_fields(target: _Resource, response: Any) -> None:
    """Overlay fields from a server response onto a resource in place.

    Copies only keys that appear both in ``response`` and in ``target``'s
    model fields. Silently no-ops for ``None`` or unsupported response shapes
    so callers don't need to defend against action endpoints that return
    minimal payloads.

    Args:
        target (_Resource): The resource to mutate.
        response (Any): A server response: either a pydantic model (with
            ``model_dump``) or a plain dict.
    """
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
        """Bind this session to an engine.

        Args:
            engine (Engine): The engine whose client and project this session
                will use. The engine is not connected here; use the session
                as a context manager or call any read method to trigger
                authentication.
        """
        self._engine = engine
        self._pending = _Pending()

    # -- context manager -------------------------------------------------------

    def __enter__(self) -> Session:
        """Open the session and force authentication up front.

        Entering the context triggers :meth:`Engine._ensure_connected`, so any
        credential or project-resolution error surfaces here rather than on
        the first read inside the block.

        Returns:
            Session: This session.

        Raises:
            AuthenticationError: If login fails.
            NotFoundError: If the configured project does not exist.
        """
        self._engine._ensure_connected()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Discard any uncommitted staged operations on block exit.

        This does not auto-commit. If the caller wanted their writes to land,
        they must call :meth:`commit` explicitly before exiting the block.

        Args:
            exc_type (object): Exception class raised in the block, if any.
            exc_val (object): Exception instance raised in the block, if any.
            exc_tb (object): Traceback for the raised exception, if any.
        """
        self._pending.clear()

    # -- reads (immediate) -----------------------------------------------------

    def get(
        self,
        resource_type: type[T],
        *,
        id: UUID | str | None = None,
        name: str | None = None,
        workflow_id: UUID | str | None = None,
        workflow_name: str | None = None,
    ) -> T | None:
        """Fetch a single resource by id or name.

        Exactly one of ``id`` or ``name`` must be supplied. Not every resource
        type supports name lookup: :class:`DocumentGroup`, :class:`Chunk`,
        :class:`Page`, :class:`Annotation`, and :class:`Job` are id-only.
        :class:`Operator` and :class:`Workflow` support name lookup by
        listing and matching client-side. :class:`WorkflowNode` requires the
        parent workflow via either ``workflow_id=`` or ``workflow_name=``;
        the server has no standalone node endpoint, so this fetches the
        parent workflow and returns the matching node. Node ``name=`` lookup
        matches against ``operator_name`` and returns the first match.

        Args:
            resource_type (type[T]): The resource class to fetch.
            id (UUID | str | None): Server-assigned UUID (or its string
                form) to look up.
            name (str | None): Human-readable name to look up (where
                supported). For :class:`WorkflowNode`, matches
                ``operator_name``.
            workflow_id (UUID | str | None): Parent workflow id. Required
                when ``resource_type`` is :class:`WorkflowNode` unless
                ``workflow_name=`` is given.
            workflow_name (str | None): Parent workflow name, as an
                alternative to ``workflow_id=`` for :class:`WorkflowNode`
                lookups.

        Returns:
            T | None: The resource bound to this session, or ``None`` if
            nothing matches.

        Raises:
            ValidationError: If neither (or both) identifiers are supplied,
                or if the requested lookup mode is unsupported for the type.
            TypeError: If ``resource_type`` is not a supported resource class.
        """
        if id is None and name is None:
            raise ValidationError("get() requires either id= or name=")

        client = self._engine.client

        if resource_type is Document:
            try:
                if id is not None:
                    response = client.documents.get(_as_uuid(id))
                else:
                    assert name is not None
                    response = client.documents.get_by_name(
                        name,
                        project_id=self._engine.project_id,
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

        if resource_type is WorkflowNode:
            if workflow_id is None and workflow_name is None:
                raise ValidationError(
                    "WorkflowNode get requires workflow_id= or workflow_name="
                )
            if workflow_id is not None:
                try:
                    wf_response = client.workflows.get(_as_uuid(workflow_id))
                except NotFoundError:
                    return None
                workflow = _build(Workflow, wf_response)
            else:
                parent = self.get(Workflow, name=workflow_name)
                if parent is None:
                    return None
                workflow = parent
            if id is not None:
                target_id = _as_uuid(id)
                for node in workflow.nodes:
                    if node.id == target_id:
                        return self._bind(node)  # type: ignore[return-value]
                return None
            for node in workflow.nodes:
                if node.operator_name == name:
                    return self._bind(node)  # type: ignore[return-value]
            return None

        raise TypeError(f"get() does not support resource type {resource_type!r}")

    def _find_by_name_via_list(
        self,
        resource_type: type[T],
        name: str | None,
        *,
        _fetch_operator_by_id: Any,
    ) -> T | None:
        """Look up a resource by name by scanning the list endpoint.

        Used for resource types whose list response is compact (no nested
        data). After finding a match by name, this fetches the full resource
        by id so the caller gets hydrated fields.

        Args:
            resource_type (type[T]): The resource class to search.
            name (str | None): Name to match exactly.
            _fetch_operator_by_id (Any): Callable taking a UUID and returning
                the hydrated response. Passed in so this helper doesn't need
                to re-dispatch on resource type.

        Returns:
            T | None: The matched resource bound to this session, or ``None``
            if no entry has that name.

        Raises:
            ValidationError: If ``name`` is ``None``.
        """
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
        """List resources of a given type, filtered by keyword args.

        Returns a lazy iterator: pages are fetched only as items are
        consumed. Required filters vary by resource:

        - ``Chunk`` / ``Page``: must pass ``document_id=``.
        - ``Annotation``: must pass one of ``document_id=``, ``chunk_id=``,
          or ``operator_id=``. ``operator_id=`` additionally accepts
          ``hydrated=True`` to fetch annotations with operator metadata
          joined server-side, and pairing ``document_id=`` with either
          ``operator_id=`` or ``operator_name=`` narrows the scope further.
        - ``Job``: accepts an optional ``status=`` of a single
          :class:`JobStatus` (or an iterable of them).
        - ``Document``, ``DocumentGroup``, ``Operator``, ``Workflow``: no
          filters; list is scoped to this session's project.

        Args:
            resource_type (type[T]): The resource class to list.
            **filters (Any): Type-specific filters as described above.

        Returns:
            PaginatedIterator[T]: A lazy paginated iterator over the matching
            resources.

        Raises:
            ValidationError: If a required filter is missing.
            TypeError: If ``resource_type`` is not a supported resource class.
        """
        client = self._engine.client
        project_id = self._engine.project_id

        if resource_type is Document:
            name = filters.get("name")

            if name is not None:

                def fetch_documents_by_name(
                    skip: int, limit: int
                ) -> PageResult[Document]:
                    try:
                        response = client.documents.get_by_name(
                            name, project_id=project_id
                        )
                    except NotFoundError:
                        return PageResult([], 0)
                    if skip > 0:
                        return PageResult([], 1)
                    doc = self._bind(_build(Document, response))
                    return PageResult([doc], 1)

                return PaginatedIterator(fetch_documents_by_name)  # type: ignore[return-value]

            def fetch_documents(skip: int, limit: int) -> PageResult[Document]:
                response = client.documents.list(
                    project_ids=str(project_id), skip=skip, limit=limit
                )
                items = [self._bind(_build(Document, r)) for r in response.documents]
                return PageResult(items, response.total)

            return PaginatedIterator(fetch_documents)  # type: ignore[return-value]

        if resource_type is DocumentGroup:

            def fetch_groups(skip: int, limit: int) -> PageResult[DocumentGroup]:
                response = client.groups.list(project_id, skip=skip, limit=limit)
                items = [self._bind(_build(DocumentGroup, r)) for r in response.groups]
                return PageResult(items, response.total)

            return PaginatedIterator(fetch_groups)  # type: ignore[return-value]

        if resource_type is Chunk:
            document_id = filters.get("document_id")
            if document_id is None:
                raise ValidationError("Chunk list requires document_id=")

            def fetch_chunks(skip: int, limit: int) -> PageResult[Chunk]:
                response = client.chunks.list(
                    document_ids=str(_as_uuid(document_id)), skip=skip, limit=limit
                )
                items = [self._bind(_build(Chunk, r)) for r in response.chunks]
                return PageResult(items, response.total)

            return PaginatedIterator(fetch_chunks)  # type: ignore[return-value]

        if resource_type is Page:
            document_id = filters.get("document_id")
            if document_id is None:
                raise ValidationError("Page list requires document_id=")

            def fetch_pages(skip: int, limit: int) -> PageResult[Page]:
                response = client.pages.list(
                    _as_uuid(document_id), skip=skip, limit=limit
                )
                items = [self._bind(_build(Page, r)) for r in response.pages]
                return PageResult(items, response.total)

            return PaginatedIterator(fetch_pages)  # type: ignore[return-value]

        if resource_type is Annotation:
            return self._list_annotations(**filters)  # type: ignore[return-value]

        if resource_type is Operator:

            def fetch_operators(skip: int, limit: int) -> PageResult[Operator]:
                response = client.operators.list(
                    project_ids=str(project_id), skip=skip, limit=limit
                )
                items = [self._bind(_build(Operator, r)) for r in response.operators]
                return PageResult(items, response.total)

            return PaginatedIterator(fetch_operators)  # type: ignore[return-value]

        if resource_type is Workflow:

            def fetch_workflows(skip: int, limit: int) -> PageResult[Workflow]:
                response = client.workflows.list(
                    project_ids=str(project_id), skip=skip, limit=limit
                )
                items = [self._bind(_build(Workflow, r)) for r in response.workflows]
                return PageResult(items, response.total)

            return PaginatedIterator(fetch_workflows)  # type: ignore[return-value]

        if resource_type is Job:
            status = filters.get("status")
            status_filter: str | None = None
            if status is not None:
                if isinstance(status, (list, tuple, set)):
                    status_filter = ",".join(str(int(s)) for s in status)
                else:
                    status_filter = str(int(status))

            def fetch_jobs(skip: int, limit: int) -> PageResult[Job]:
                response = client.jobs.list(
                    project_id=project_id,
                    status_filter=status_filter,
                    skip=skip,
                    limit=limit,
                )
                items = [self._bind(_build(Job, r)) for r in response.jobs]
                return PageResult(items, response.total)

            return PaginatedIterator(fetch_jobs)  # type: ignore[return-value]

        raise TypeError(f"list() does not support resource type {resource_type!r}")

    def _list_annotations(self, **filters: Any) -> PaginatedIterator[Annotation]:
        """Dispatch annotation listing to the appropriate API endpoint.

        Annotations have several scoped list endpoints instead of a single
        filterable one; this helper picks the right endpoint based on which
        filters the caller supplied.

        Args:
            **filters (Any): Any of ``document_id``, ``chunk_id``,
                ``operator_id``, ``operator_name``, and ``hydrated``. See
                :meth:`list` for the allowed combinations.

        Returns:
            PaginatedIterator[Annotation]: A lazy paginated iterator over the
            matching annotations.

        Raises:
            ValidationError: If none of ``document_id``, ``chunk_id``, or
                ``operator_id`` were supplied.
        """
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
                        self._bind(_build(Annotation, r)) for r in response.annotations
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
                        self._bind(_build(Annotation, r)) for r in response.annotations
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
                response = client.annotations.list_by_chunk(cid, skip=skip, limit=limit)
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
                        self._bind(_build(Annotation, r)) for r in response.annotations
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
        """Execute a SQL query against this project's annotations.

        Each committed operator becomes a table in the query namespace (keyed
        by operator name), with columns drawn from the operator's JSON schema.

        Args:
            sql (str): The SQL query to run.
            limit (int): Maximum number of rows to return. Applied
                server-side.

        Returns:
            QueryResult: A :class:`QueryResult` with column names, rows, and
            the server-reported execution time.

        Raises:
            QueryError: If the query is malformed or references an unknown
                operator/column.
            AuthenticationError: If authentication fails on first access.
        """
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
        """Start a workflow against a batch of documents.

        The workflow and every document must already be committed — this
        method does not auto-flush the unit of work. Callers can use the
        returned :class:`Job` to poll for completion or cancel.

        Args:
            workflow (Workflow): A committed workflow to execute.
            documents (list[Document]): Committed documents to process. Must
                contain at least one document.

        Returns:
            Job: A :class:`Job` handle bound to this session, with ``status``
            initialized to :attr:`JobStatus.NOT_STARTED`.

        Raises:
            ValidationError: If the workflow or any document has not yet been
                committed (i.e. lacks an ``id``).
        """
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
        """Stage a resource for creation on the next :meth:`commit`.

        Idempotent: adding the same instance twice is a no-op. Adding is
        local-only; no HTTP request is made until :meth:`commit` runs.

        Args:
            resource (_Resource): The unsaved resource to create. Must be one
                of :class:`Document`, :class:`DocumentGroup`, :class:`Chunk`,
                :class:`Annotation`, :class:`Operator`, or :class:`Workflow`,
                and must not already have a server-assigned id.

        Raises:
            ValidationError: If the resource type is read-only (e.g.
                :class:`Page`), if it is a :class:`Job` (jobs are created via
                :meth:`run`), or if the resource already has an id (use
                :meth:`update` instead).
            TypeError: If the resource type is otherwise unsupported.
        """
        if isinstance(resource, _READ_ONLY_TYPES):
            raise ValidationError(f"{type(resource).__name__} is read-only; cannot add")
        if isinstance(resource, Job):
            raise ValidationError(
                "Jobs cannot be added directly; use session.run(workflow, documents=[...])"
            )
        if not isinstance(
            resource,
            (
                Document,
                DocumentGroup,
                Chunk,
                Annotation,
                Operator,
                Workflow,
                WorkflowNode,
            ),
        ):
            raise TypeError(
                f"add() does not support resource type {type(resource).__name__}"
            )
        if _resource_id(resource) is not None:
            raise ValidationError(
                f"Cannot add an already-persisted {type(resource).__name__}; "
                "use session.update() instead"
            )
        if self._pending.has("add", resource):
            return
        self._pending.ops.append(("add", resource))

    def update(self, resource: _Resource) -> None:
        """Stage a persisted resource for update on the next :meth:`commit`.

        Idempotent: staging the same instance twice is a no-op. The resource
        is sent to the server verbatim on commit — mutate the fields you want
        to change before calling :meth:`commit`.

        Args:
            resource (_Resource): A persisted resource (must have an ``id``).
                Must be one of :class:`Document`, :class:`DocumentGroup`,
                :class:`Annotation`, :class:`Operator`, or :class:`Workflow`.

        Raises:
            ValidationError: If the resource type does not support update
                (:class:`Page`, :class:`Chunk`), or if the resource has no id.
            TypeError: If the resource type is otherwise unsupported.
        """
        if isinstance(resource, _UPDATE_UNSUPPORTED_TYPES):
            raise ValidationError(f"{type(resource).__name__} does not support update")
        if not isinstance(
            resource,
            (Document, DocumentGroup, Annotation, Operator, Workflow, WorkflowNode),
        ):
            raise TypeError(
                f"update() does not support resource type {type(resource).__name__}"
            )
        if _resource_id(resource) is None:
            raise ValidationError(
                f"Cannot update an unpersisted {type(resource).__name__}; "
                "it must have an id"
            )
        if self._pending.has("update", resource):
            return
        self._pending.ops.append(("update", resource))

    def delete(self, resource: _Resource) -> None:
        """Stage a resource for deletion on the next :meth:`commit`.

        If the resource was staged for creation via :meth:`add` and has not
        yet been committed, this cancels the pending add instead of queuing a
        server-side delete. Idempotent: staging the same instance twice is a
        no-op.

        Args:
            resource (_Resource): The resource to delete. For
                already-persisted resources, must have an ``id``. Must be
                one of :class:`Document`, :class:`DocumentGroup`,
                :class:`Chunk`, :class:`Annotation`, :class:`Operator`, or
                :class:`Workflow`.

        Raises:
            ValidationError: If the resource type is read-only, or if it has
                not been persisted and was not previously added.
            TypeError: If the resource type is otherwise unsupported.
        """
        if isinstance(resource, _READ_ONLY_TYPES):
            raise ValidationError(
                f"{type(resource).__name__} is read-only; cannot delete"
            )
        if not isinstance(
            resource,
            (
                Document,
                DocumentGroup,
                Chunk,
                Annotation,
                Operator,
                Workflow,
                WorkflowNode,
            ),
        ):
            raise TypeError(
                f"delete() does not support resource type {type(resource).__name__}"
            )
        if self._pending.remove_add(resource):
            return
        if _resource_id(resource) is None:
            raise ValidationError(
                f"Cannot delete an unpersisted {type(resource).__name__}; "
                "it must have an id"
            )
        if self._pending.has("delete", resource):
            return
        self._pending.ops.append(("delete", resource))

    def commit(self) -> None:
        """Flush every staged add / update / delete to the server.

        Operations run sequentially in the exact order they were staged —
        interleaved add/update/delete calls flush in the same order the
        caller made them. Resources passed to :meth:`add` are hydrated in
        place once their server write succeeds.

        The API has no transaction primitive: a mid-batch failure leaves
        earlier writes applied server-side. When that happens this method
        raises :class:`~ragnerock.errors.CommitError` carrying the committed
        and still-pending resources so the caller can recover.

        Called with an empty staging queue, this is a no-op.

        Raises:
            CommitError: A staged operation failed. Operations that ran
                before the failure are recorded on the exception's
                ``committed`` list; the failing op and everything after it
                are recorded on ``pending``.
            ValidationError: A precheck failed before any HTTP call was made
                (e.g. a Document was staged without ``file_path`` or
                ``source_url``).
        """
        if self._pending.is_empty():
            return

        all_ops: list[tuple[str, _Resource]] = list(self._pending.ops)

        for op, resource in all_ops:
            if op == "add":
                self._precheck_create(resource)

        committed: list[_Resource] = []
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
        """Validate a staged resource before any HTTP calls are made.

        Catches the common shape errors (missing file source on a document,
        annotation without an operator id or attachment target) here so that
        :meth:`commit` fails fast before any partial writes land.

        Args:
            resource (_Resource): The staged-for-creation resource to
                validate.

        Raises:
            ValidationError: If the resource is missing required fields.
        """
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
        elif isinstance(resource, WorkflowNode):
            if resource.workflow_id is None:
                raise ValidationError("WorkflowNode create requires workflow_id")
            if resource.operator_id is None:
                raise ValidationError("WorkflowNode create requires operator_id")

    def refresh(self, resource: _Resource) -> None:
        """Re-fetch a persisted resource and overwrite its fields in place.

        Use this to pick up server-side changes (e.g. to observe a job's
        status transition) without allocating a new object.

        Args:
            resource (_Resource): A persisted resource bound to this session.
                Must have an ``id`` (or ``root_id`` for annotations).

        Raises:
            ValidationError: If the resource has not been persisted.
            TypeError: If the resource type does not support refresh.
            NotFoundError: If the resource no longer exists server-side.
        """
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
        """Discard every staged operation without contacting the server.

        Has no effect on resources whose writes already succeeded (e.g. on
        the surviving operations of a failed :meth:`commit`).
        """
        self._pending.clear()

    # -- per-type create / update / delete -------------------------------------

    def _create_resource(self, resource: _Resource) -> None:
        """Issue the appropriate create call for ``resource`` and hydrate it.

        On success, the resource is mutated in place with the server's
        assigned fields (``id``, timestamps, etc.) and bound to this session.

        Args:
            resource (_Resource): The resource to create. Must match one of
                the supported types; shape validation happens here as a
                second line of defense after :meth:`_precheck_create`.

        Raises:
            ValidationError: If required fields are missing.
            TypeError: If the resource type is not supported for creation.
            RagnerockError: If the server rejects the request.
        """
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
            self._bind(resource)
            return

        if isinstance(resource, DocumentGroup):
            if not resource.name:
                raise ValidationError("DocumentGroup create requires name")
            response = client.groups.create(self._engine.project_id, name=resource.name)
            _copy_fields(resource, response)
            self._bind(resource)
            return

        if isinstance(resource, Chunk):
            if resource.document_id is None:
                raise ValidationError("Chunk create requires document_id")
            if resource.start_index is None or resource.end_index is None:
                raise ValidationError("Chunk create requires start_index and end_index")
            response = client.chunks.create(
                document_id=resource.document_id,
                start_index=resource.start_index,
                end_index=resource.end_index,
                content=resource.content,
                metadata=resource.metadata,
            )
            _copy_fields(resource, response)
            self._bind(resource)
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
            self._bind(resource)
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
            self._bind(resource)
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
            self._bind(resource)
            return

        if isinstance(resource, WorkflowNode):
            if resource.workflow_id is None:
                raise ValidationError("WorkflowNode create requires workflow_id")
            if resource.operator_id is None:
                raise ValidationError("WorkflowNode create requires operator_id")
            response = client.workflows.add_node(
                resource.workflow_id,
                operator_id=resource.operator_id,
                condition=resource.condition,
                persist=resource.persist,
                on_error=resource.on_error,
                max_retries=resource.max_retries,
            )
            _copy_fields(resource, response)
            self._bind(resource)
            return

        raise TypeError(f"create dispatch not supported for {type(resource).__name__}")

    def _update_resource(self, resource: _Resource) -> None:
        """Issue the appropriate update call for ``resource`` and hydrate it.

        The full current field set is sent; the server decides which fields
        are writable and silently drops the rest.

        Args:
            resource (_Resource): The resource to update. Must have an
                identity.

        Raises:
            TypeError: If the resource type is not supported for update.
            RagnerockError: If the server rejects the request.
        """
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
                chunk_type=int(resource.chunk_type)
                if resource.chunk_type is not None
                else None,
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

        if isinstance(resource, WorkflowNode):
            if resource.workflow_id is None or resource.id is None:
                raise ValidationError("WorkflowNode update requires workflow_id and id")
            response = client.workflows.update_node(
                resource.workflow_id,
                resource.id,
                condition=resource.condition,
                persist=resource.persist,
                on_error=resource.on_error,
                max_retries=resource.max_retries,
                in_nodes=list(resource.in_nodes),
                out_nodes=list(resource.out_nodes),
            )
            _copy_fields(resource, response)
            return

        raise TypeError(f"update dispatch not supported for {type(resource).__name__}")

    def _delete_resource(self, resource: _Resource) -> None:
        """Issue the appropriate delete call for ``resource``.

        No local state is modified — the resource object is left intact so
        callers can still inspect it (or re-add it, if that makes sense).

        Args:
            resource (_Resource): The resource to delete. Must have an
                identity.

        Raises:
            TypeError: If the resource type is not supported for deletion.
            RagnerockError: If the server rejects the request.
        """
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
        if isinstance(resource, WorkflowNode):
            if resource.workflow_id is None or resource.id is None:
                raise ValidationError("WorkflowNode delete requires workflow_id and id")
            client.workflows.delete_node(resource.workflow_id, resource.id)
            return

        raise TypeError(f"delete dispatch not supported for {type(resource).__name__}")

    # -- internal --------------------------------------------------------------

    def _bind(self, resource: T) -> T:
        """Attach this session to ``resource`` and return it for chaining.

        Args:
            resource (T): The resource to bind.

        Returns:
            T: The same resource, now carrying a session back-reference.
        """
        resource._bind(self)
        return resource

    def _list_related(
        self,
        parent: _Resource,
        resource_type: type[T],
        **kwargs: Any,
    ) -> PaginatedIterator[T]:
        """Dispatch a ``parent.list(child_type, ...)`` call to the right endpoint.

        Supported navigations:

        - :class:`Document` → :class:`Chunk`, :class:`Page`,
          :class:`Annotation` (optional ``operator_name=``)
        - :class:`Chunk` → :class:`Annotation`
        - :class:`DocumentGroup` → :class:`Document`
        - :class:`Operator` → :class:`Annotation` (optional ``document=``
          to scope, ``hydrated=True`` for joined operator metadata)

        Args:
            parent (_Resource): The resource to navigate from.
            resource_type (type[T]): The related resource class to list.
            **kwargs (Any): Extra filters forwarded to the right list
                endpoint.

        Returns:
            PaginatedIterator[T]: A lazy paginated iterator over the related
            resources.

        Raises:
            TypeError: If no navigation exists from ``parent`` to
                ``resource_type``.
        """
        if isinstance(parent, Document):
            if resource_type is Chunk:
                return self.list(Chunk, document_id=parent.id)  # type: ignore[return-value]
            if resource_type is Page:
                return self.list(Page, document_id=parent.id)  # type: ignore[return-value]
            if resource_type is Annotation:
                operator_name = kwargs.get("operator_name")
                if operator_name is not None:
                    return self.list(  # type: ignore[return-value]
                        Annotation,
                        document_id=parent.id,
                        operator_name=operator_name,
                    )
                return self.list(Annotation, document_id=parent.id)  # type: ignore[return-value]

        if isinstance(parent, Chunk):
            if resource_type is Annotation:
                return self.list(Annotation, chunk_id=parent.id)  # type: ignore[return-value]

        if isinstance(parent, DocumentGroup):
            if resource_type is Document:
                group_id = parent.id
                if group_id is None:
                    raise ValidationError(
                        "DocumentGroup must have an id to list its documents"
                    )
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
                    return self.list(  # type: ignore[return-value]
                        Annotation,
                        document_id=doc.id,
                        operator_id=parent.id,
                    )
                hydrated = kwargs.get("hydrated", False)
                return self.list(Annotation, operator_id=parent.id, hydrated=hydrated)  # type: ignore[return-value]

        raise TypeError(
            f"{type(parent).__name__} does not support list({resource_type.__name__})"
        )


def _build(resource_type: type[T], response: Any) -> T:
    """Construct a resource from a client-layer response object.

    Keeps only the fields that match ``resource_type``'s schema, so the
    extra ``extra="allow"`` fields carried by client response models don't
    bleed into the resource model and trip pydantic validation.

    Args:
        resource_type (type[T]): The resource class to instantiate.
        response (Any): A client-layer response (pydantic model or dict).
            ``None`` yields an empty instance.

    Returns:
        T: A resource instance populated from ``response``. Not yet bound to
        a session — callers must pass it through :meth:`Session._bind`.

    Raises:
        TypeError: If ``response`` is neither a pydantic model, a dict, nor
            ``None``.
    """
    if response is None:
        return resource_type()
    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif isinstance(response, dict):
        data = dict(response)
    else:
        raise TypeError(
            f"Cannot build {resource_type.__name__} from {type(response)!r}"
        )

    filtered = {k: v for k, v in data.items() if k in resource_type.model_fields}
    return resource_type(**filtered)
