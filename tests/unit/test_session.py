"""Tests for ``Session`` lifecycle, staging queues, and commit semantics."""

from __future__ import annotations

import re

import pytest

from ragnerock import (
    Annotation,
    Chunk,
    Document,
    DocumentGroup,
    Job,
    Page,
    Session,
    ValidationError,
    Workflow,
)


class TestContextManager:
    """Entering/exiting the session as a ``with`` block."""

    def test_enter_returns_the_session(self, engine):
        with Session(engine) as s:
            assert isinstance(s, Session)

    def test_exit_does_not_auto_commit(self, httpx_mock, engine):
        """Leaving a ``with`` block without ``commit()`` must drop pending writes."""
        with Session(engine) as s:
            s.add(Document(file_path="./x.pdf"))

        posts = [
            r
            for r in httpx_mock.get_requests()
            if r.method == "POST" and r.url.path == "/api/documents/"
        ]
        assert posts == []

    def test_exit_on_exception_does_not_auto_commit(self, httpx_mock, engine):
        class _Boom(Exception):
            pass

        with pytest.raises(_Boom):
            with Session(engine) as s:
                s.add(Document(file_path="./x.pdf"))
                raise _Boom

        posts = [
            r
            for r in httpx_mock.get_requests()
            if r.method == "POST" and r.url.path == "/api/documents/"
        ]
        assert posts == []


class TestAddValidation:
    """``session.add`` rejects types / states that can't be created."""

    def test_add_page_raises(self, session):
        with pytest.raises((TypeError, ValidationError)):
            session.add(Page(page_number=1))

    def test_add_job_raises(self, session):
        with pytest.raises((TypeError, ValidationError)):
            session.add(Job())

    def test_add_persisted_resource_raises(self, session):
        existing = Document(id="00000000-0000-0000-0000-000000000101")
        with pytest.raises(ValidationError):
            session.add(existing)

    def test_add_unsupported_type_raises(self, session):
        class NotAResource:
            pass

        with pytest.raises((TypeError, ValidationError)):
            session.add(NotAResource())  # type: ignore[arg-type]

    def test_double_add_is_idempotent(self, session):
        doc = Document(file_path="./x.pdf")
        session.add(doc)
        session.add(doc)
        assert session._pending.ops == [("add", doc)]


class TestUpdateValidation:
    """``session.update`` rejects types / states that can't be updated."""

    def test_update_requires_id(self, session):
        with pytest.raises(ValidationError):
            session.update(Document(name="x"))

    def test_update_page_raises(self, session):
        p = Page(id="00000000-0000-0000-0000-000000000401", page_number=1)
        with pytest.raises((TypeError, ValidationError)):
            session.update(p)

    def test_update_chunk_raises(self, session):
        c = Chunk(id="00000000-0000-0000-0000-000000000301", start_index=0, end_index=1)
        with pytest.raises((TypeError, ValidationError)):
            session.update(c)


class TestDeleteValidation:
    """``session.delete`` has staging-specific behaviors."""

    def test_delete_page_raises(self, session):
        p = Page(id="00000000-0000-0000-0000-000000000401", page_number=1)
        with pytest.raises((TypeError, ValidationError)):
            session.delete(p)

    def test_delete_without_id_raises(self, session):
        with pytest.raises(ValidationError):
            session.delete(Document())

    def test_delete_cancels_pending_add(self, session):
        """Deleting a freshly-added resource should just pop it from the queue."""
        doc = Document(file_path="./x.pdf")
        session.add(doc)
        assert session._pending.ops == [("add", doc)]
        session.delete(doc)
        assert session._pending.ops == []


class TestGetValidation:
    """``session.get`` requires exactly one of id or name."""

    def test_get_without_id_or_name_raises(self, session):
        with pytest.raises(ValidationError):
            session.get(Document)

    def test_get_document_group_by_name_unsupported(self, session):
        with pytest.raises(ValidationError):
            session.get(DocumentGroup, name="whatever")

    def test_get_chunk_by_name_unsupported(self, session):
        with pytest.raises(ValidationError):
            session.get(Chunk, name="whatever")

    def test_get_unsupported_type_raises(self, session):
        class _X:
            pass

        with pytest.raises(TypeError):
            session.get(_X, id="00000000-0000-0000-0000-000000000101")  # type: ignore[arg-type]


class TestListRequiredFilters:
    """``session.list`` enforces per-resource required filters."""

    def test_chunk_requires_document_id(self, session):
        with pytest.raises(ValidationError):
            session.list(Chunk).all()

    def test_page_requires_document_id(self, session):
        with pytest.raises(ValidationError):
            session.list(Page).all()

    def test_annotation_requires_a_scope(self, session):
        with pytest.raises(ValidationError):
            session.list(Annotation).all()


class TestRunRequiresPersistedResources:
    """``session.run`` does not auto-flush; resources must be committed first."""

    def test_uncommitted_workflow_raises(self, session):
        wf = Workflow(name="new")
        doc = Document(id="00000000-0000-0000-0000-000000000101")
        with pytest.raises(ValidationError):
            session.run(wf, documents=[doc])

    def test_uncommitted_document_raises(self, session):
        wf = Workflow(id="00000000-0000-0000-0000-000000000701", name="ingest")
        doc = Document(file_path="./x.pdf")
        with pytest.raises(ValidationError):
            session.run(wf, documents=[doc])


class TestRollback:
    """``rollback`` drops staged work but leaves committed work alone."""

    def test_rollback_empties_queues(self, session):
        session.add(Document(file_path="./x.pdf"))
        session.rollback()
        assert session._pending.is_empty()

    def test_rollback_on_empty_is_noop(self, session):
        session.rollback()  # should not raise

    def test_commit_empty_is_noop(self, httpx_mock, session):
        session.commit()  # should not raise and not make any HTTP requests
        posts = [r for r in httpx_mock.get_requests() if r.method == "POST"]
        # Only login POST may have been made on session setup
        assert all(r.url.path == "/api/auth/login" for r in posts)


class TestResourceBinding:
    """Resources returned from a session must carry a back-reference."""

    def test_get_binds_resource(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/documents/{doc_id}$"),
            json=payloads.document(id=doc_id),
        )
        doc = session.get(Document, id=doc_id)
        assert doc is not None
        assert doc._is_bound

    def test_list_items_are_bound(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/\?.*"),
            json=payloads.list_envelope("documents", [payloads.document()]),
        )
        docs = session.list(Document).all()
        assert docs
        assert all(d._is_bound for d in docs)

    def test_add_commit_binds_resource(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=re.compile(r".*/api/projects/.*/groups/$"),
            json=payloads.document_group(),
        )
        group = DocumentGroup(name="Q1 contracts")
        session.add(group)
        session.commit()
        assert group._is_bound
