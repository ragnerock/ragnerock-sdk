"""Tests for the unit-of-work: add / update / delete / commit / rollback / refresh.

These tests define the transaction model's exact behavior:

- Staging doesn't hit the network.
- `commit()` flushes in order (adds → updates → deletes) and populates server
  fields on the local objects.
- `commit()` failure raises `CommitError` with `committed` and `pending` lists.
- `rollback()` is local-only.
- `refresh()` GETs the resource and overwrites fields in place.
- Delete-after-add dequeues without a network call.
- Double-add is a no-op.
"""

from __future__ import annotations

import re
from uuid import UUID

import pytest

from ragnerock import CommitError, Document, Operator, ValidationError
from tests.conftest import TEST_HOST


def _resource_posts(httpx_mock) -> list:
    """POSTs to resource endpoints — excludes the login handshake."""
    return [
        r
        for r in httpx_mock.get_requests()
        if r.method == "POST" and not r.url.path.startswith("/api/auth/")
    ]


class TestStagingIsLocalOnly:
    def test_add_does_not_hit_network(self, httpx_mock, session):
        doc = Document(file_path="./x.pdf")
        session.add(doc)
        assert doc.id is None, "id must not be set before commit"

        assert not _resource_posts(httpx_mock), "add() must not fire a network call"

    def test_update_does_not_hit_network(self, httpx_mock, session, payloads):
        doc = Document(**payloads.document())
        doc.name = "renamed.pdf"
        session.update(doc)

        puts = [r for r in httpx_mock.get_requests() if r.method == "PUT"]
        assert not puts

    def test_delete_does_not_hit_network(self, httpx_mock, session, payloads):
        doc = Document(**payloads.document())
        session.delete(doc)

        deletes = [r for r in httpx_mock.get_requests() if r.method == "DELETE"]
        assert not deletes


class TestCommitFlushesInOrder:
    def test_add_commits_to_post(self, httpx_mock, session, payloads):
        # The Document create endpoint is multipart; the server echoes back a
        # full DocumentResponse with id, storage_path, etc. populated.
        new_id = "00000000-0000-0000-0000-000000000110"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/documents/",
            json=payloads.document(id=new_id, name="report.pdf"),
        )

        doc = Document(file_path="./report.pdf", name="report.pdf")
        session.add(doc)
        session.commit()

        assert doc.id == UUID(new_id)
        assert doc.storage_path is not None
        assert doc.created_at is not None

    def test_commit_order_adds_then_updates_then_deletes(
        self, httpx_mock, session, payloads
    ):
        # Register responses for all three ops.
        add_id = "00000000-0000-0000-0000-0000000000a1"
        upd_id = "00000000-0000-0000-0000-0000000000a2"
        del_id = "00000000-0000-0000-0000-0000000000a3"

        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/documents/",
            json=payloads.document(id=add_id, name="new.pdf"),
        )
        httpx_mock.add_response(
            method="PUT",
            url=f"{TEST_HOST}/api/documents/{upd_id}",
            json=payloads.document(id=upd_id, name="renamed.pdf"),
        )
        httpx_mock.add_response(
            method="DELETE",
            url=f"{TEST_HOST}/api/documents/{del_id}",
            json={},
        )

        new_doc = Document(file_path="./new.pdf", name="new.pdf")
        upd_doc = Document(**payloads.document(id=upd_id))
        upd_doc.name = "renamed.pdf"
        del_doc = Document(**payloads.document(id=del_id))

        session.add(new_doc)
        session.update(upd_doc)
        session.delete(del_doc)
        session.commit()

        requests = [r for r in httpx_mock.get_requests() if r.url.path.startswith("/api/documents")]
        # Filter out any pre-commit GETs; we only care about the writes.
        writes = [r for r in requests if r.method in ("POST", "PUT", "DELETE")]
        methods = [r.method for r in writes]
        assert methods == ["POST", "PUT", "DELETE"], (
            f"commit order wrong: {methods}"
        )

    def test_commit_empties_queue(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/documents/",
            json=payloads.document(id="00000000-0000-0000-0000-0000000000b1"),
        )

        doc = Document(file_path="./x.pdf")
        session.add(doc)
        session.commit()

        # Second commit should be a no-op (no additional requests).
        before = len(httpx_mock.get_requests())
        session.commit()
        after = len(httpx_mock.get_requests())
        assert before == after, "commit() on empty queue must not hit the network"


class TestCommitFailure:
    def test_failure_raises_commit_error_with_committed_and_pending(
        self, httpx_mock, session, payloads
    ):
        # First add succeeds; second fails with 422.
        ok_id = "00000000-0000-0000-0000-0000000000c1"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/documents/",
            json=payloads.document(id=ok_id, name="ok.pdf"),
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/documents/",
            status_code=422,
            json={"detail": {"message": "file too large"}},
        )

        ok_doc = Document(file_path="./ok.pdf", name="ok.pdf")
        bad_doc = Document(file_path="./bad.pdf", name="bad.pdf")
        unattempted = Document(file_path="./z.pdf", name="z.pdf")

        session.add(ok_doc)
        session.add(bad_doc)
        session.add(unattempted)

        with pytest.raises(CommitError) as exc_info:
            session.commit()

        err = exc_info.value
        # ok_doc made it through.
        assert ok_doc in err.committed
        # bad_doc and unattempted did not.
        assert bad_doc in err.pending
        assert unattempted in err.pending
        # The root cause is attached.
        assert err.cause is not None


class TestRollback:
    def test_rollback_empties_queue_without_network(self, httpx_mock, session):
        before = len(_resource_posts(httpx_mock))
        session.add(Document(file_path="./x.pdf"))
        session.add(Document(file_path="./y.pdf"))
        session.rollback()

        # No resource-level writes fired.
        assert len(_resource_posts(httpx_mock)) == before

        # A subsequent commit is a no-op.
        session.commit()
        assert len(_resource_posts(httpx_mock)) == before

    def test_rollback_empty_queue_is_fine(self, session):
        session.rollback()  # shouldn't raise


class TestRefresh:
    def test_refresh_overwrites_fields_in_place(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        doc = Document(**payloads.document(id=doc_id, name="old.pdf"))

        # Pretend the server now shows a different name.
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/documents/{doc_id}$"),
            json=payloads.document(id=doc_id, name="new.pdf"),
        )
        session.refresh(doc)
        assert doc.name == "new.pdf"

    def test_refresh_without_id_raises(self, session):
        doc = Document(file_path="./x.pdf")  # no id
        with pytest.raises(ValidationError):
            session.refresh(doc)


class TestStagingSemantics:
    def test_delete_after_add_is_local_only(self, httpx_mock, session):
        """Deleting a resource that is still in `added` drops it — no round trips."""
        doc = Document(file_path="./x.pdf")
        session.add(doc)
        session.delete(doc)
        session.commit()

        deletes = [r for r in httpx_mock.get_requests() if r.method == "DELETE"]
        assert not _resource_posts(httpx_mock)
        assert not deletes

    def test_double_add_is_noop(self, session):
        doc = Document(file_path="./x.pdf")
        session.add(doc)
        session.add(doc)  # must not raise; must not duplicate

    def test_update_requires_persisted_resource(self, session):
        doc = Document(file_path="./x.pdf")  # no id
        with pytest.raises(ValidationError):
            session.update(doc)

    def test_add_persisted_resource_raises(self, session, payloads):
        """Adding an already-persisted resource is probably a user error."""
        doc = Document(**payloads.document())  # has an id
        with pytest.raises(ValidationError):
            session.add(doc)


class TestMixedTypeCommit:
    """Operators and Documents can be added in the same commit."""

    def test_add_operator_and_document_together(self, httpx_mock, session, payloads):
        op_id = "00000000-0000-0000-0000-0000000000d1"
        doc_id = "00000000-0000-0000-0000-0000000000d2"

        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/operators/",
            json=payloads.operator(id=op_id, name="x"),
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/documents/",
            json=payloads.document(id=doc_id),
        )

        op = Operator(
            name="x",
            jsonschema={"type": "object"},
            generation_prompt="p",
            chunk_type=1,
        )
        doc = Document(file_path="./x.pdf")
        session.add(op)
        session.add(doc)
        session.commit()

        assert op.id == UUID(op_id)
        assert doc.id == UUID(doc_id)
