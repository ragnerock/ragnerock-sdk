"""Tests for the `Session` context manager and resource-type dispatch.

These tests focus on the session's behavior as a container: context manager
semantics, unsupported type handling, and the `run()` precondition that
resources be committed.
"""

from __future__ import annotations

import pytest

from ragnerock import (
    Document,
    DocumentGroup,
    Page,
    Session,
    ValidationError,
    Workflow,
)


class TestContextManager:
    def test_enter_returns_session(self, engine):
        with Session(engine) as s:
            assert isinstance(s, Session)

    def test_exit_does_not_autocommit(self, httpx_mock, engine, payloads):
        """Staged ops must be discarded on `__exit__`, not pushed to the server."""
        with Session(engine) as s:
            doc = Document(file_path="./x.pdf")
            s.add(doc)
            # leave the `with` block without calling commit()

        # No POST to /api/documents/ should have gone out.
        post_docs = [
            r
            for r in httpx_mock.get_requests()
            if r.method == "POST" and r.url.path == "/api/documents/"
        ]
        assert post_docs == [], "commit must not happen on __exit__"

    def test_exit_on_exception_does_not_autocommit(self, httpx_mock, engine):
        class _Boom(Exception):
            pass

        with pytest.raises(_Boom):
            with Session(engine) as s:
                s.add(Document(file_path="./x.pdf"))
                raise _Boom

        post_docs = [
            r
            for r in httpx_mock.get_requests()
            if r.method == "POST" and r.url.path == "/api/documents/"
        ]
        assert post_docs == []


class TestResourceBinding:
    """Resources returned from the session should carry a session back-reference."""

    def test_get_binds_resource(self, httpx_mock, session, payloads):
        import re

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
        import re

        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/\?.*"),
            json=payloads.list_envelope("documents", [payloads.document()]),
        )
        docs = session.list(Document).all()
        assert len(docs) == 1
        assert docs[0]._is_bound

    def test_add_commit_binds_resource(self, httpx_mock, session, payloads):
        """Resources created via add()+commit() must carry the session back-reference.

        Regression: without this, `group.list(Document)` after a fresh commit
        raises "not bound to a session".
        """
        import re

        httpx_mock.add_response(
            method="POST",
            url=re.compile(r".*/api/projects/.*/groups/$"),
            json=payloads.document_group(),
        )
        group = DocumentGroup(name="Q1 contracts")
        session.add(group)
        session.commit()
        assert group._is_bound


class TestUnsupportedDispatch:
    """Ops that don't make sense for a resource type must raise clearly."""

    def test_add_page_raises(self, session):
        # Pages are read-only; add/update/delete should be rejected.
        p = Page(page_number=1)
        with pytest.raises((TypeError, ValidationError)):
            session.add(p)

    def test_delete_page_raises(self, session):
        p = Page(id="00000000-0000-0000-0000-000000000401", page_number=1)
        with pytest.raises((TypeError, ValidationError)):
            session.delete(p)


class TestRunRequiresCommitted:
    """`session.run()` refuses uncommitted resources — no autoflush."""

    def test_run_with_uncommitted_doc_raises(self, session):
        wf = Workflow(id="00000000-0000-0000-0000-000000000701", name="ingest")
        doc = Document(file_path="./x.pdf")  # no id
        with pytest.raises(ValidationError):
            session.run(wf, documents=[doc])

    def test_run_with_uncommitted_workflow_raises(self, session):
        wf = Workflow(name="new")  # no id
        doc = Document(id="00000000-0000-0000-0000-000000000101")
        with pytest.raises(ValidationError):
            session.run(wf, documents=[doc])
