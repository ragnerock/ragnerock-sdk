"""Tests for ``session.commit`` / ``rollback`` and the unit-of-work model."""

from __future__ import annotations

import re

import pytest

from ragnerock import CommitError, Document, DocumentGroup, Operator


class TestCommitOrdering:
    """Adds run before updates before deletes; insertion order preserved within each bucket."""

    def test_add_then_update_then_delete(self, httpx_mock, session, payloads, base_url):
        # --- add
        add_doc = Document(source_url="https://example.com/new.pdf")
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/documents/",
            json=payloads.document(
                id="00000000-0000-0000-0000-00000000000a", name="new.pdf"
            ),
        )

        # --- update
        upd_doc = Document(
            **payloads.document(id="00000000-0000-0000-0000-00000000000b")
        )
        upd_doc.name = "renamed.pdf"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/documents/00000000-0000-0000-0000-00000000000b",
            json=payloads.document(
                id="00000000-0000-0000-0000-00000000000b", name="renamed.pdf"
            ),
        )

        # --- delete
        del_doc = Document(
            **payloads.document(id="00000000-0000-0000-0000-00000000000c")
        )
        httpx_mock.add_response(
            method="DELETE",
            url=f"{base_url}/api/documents/00000000-0000-0000-0000-00000000000c",
            status_code=204,
            text="",
        )

        session.add(add_doc)
        session.update(upd_doc)
        session.delete(del_doc)
        session.commit()

        # Ops flushed leave pending empty.
        assert session._pending.is_empty()

        methods = [
            r.method for r in httpx_mock.get_requests() if "/documents" in r.url.path
        ]
        post_idx = methods.index("POST")
        put_idx = methods.index("PUT")
        del_idx = methods.index("DELETE")
        assert post_idx < put_idx < del_idx


class TestCommitFailureSemantics:
    def test_failure_mid_batch_populates_committed_and_pending(
        self, httpx_mock, session, payloads, base_url
    ):
        # three adds; first two succeed, third fails
        ok1 = Operator(
            name="a",
            jsonschema={"type": "object"},
            generation_prompt="p",
            chunk_type=1,
        )
        ok2 = Operator(
            name="b",
            jsonschema={"type": "object"},
            generation_prompt="p",
            chunk_type=1,
        )
        bad = Operator(
            name="c",
            jsonschema={"type": "object"},
            generation_prompt="p",
            chunk_type=1,
        )

        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/operators/",
            json=payloads.operator(id="00000000-0000-0000-0000-0000000000a1", name="a"),
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/operators/",
            json=payloads.operator(id="00000000-0000-0000-0000-0000000000a2", name="b"),
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/operators/",
            status_code=500,
            json={"detail": {"message": "boom"}},
        )

        session.add(ok1)
        session.add(ok2)
        session.add(bad)
        with pytest.raises(CommitError) as exc:
            session.commit()

        assert ok1 in exc.value.committed
        assert ok2 in exc.value.committed
        assert bad in exc.value.pending
        # After a CommitError the staging queues must be empty.
        assert session._pending.is_empty()

    def test_rollback_after_failure_is_noop(
        self, httpx_mock, session, payloads, base_url
    ):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/documents/",
            status_code=500,
            json={"detail": {"message": "boom"}},
        )
        doc = Document(source_url="https://example.com/x.pdf")
        session.add(doc)
        with pytest.raises(CommitError):
            session.commit()
        # Staging is already empty after the CommitError, so rollback is a noop.
        session.rollback()
        assert session._pending.is_empty()


class TestAddDeleteInteraction:
    def test_delete_after_add_cancels_pending_add(self, httpx_mock, session, payloads):
        doc = Document(source_url="https://example.com/x.pdf")
        session.add(doc)
        session.delete(doc)
        # Commit should be a no-op — nothing should be flushed.
        session.commit()
        assert not any(
            r.method == "POST" and "/documents/" in r.url.path
            for r in httpx_mock.get_requests()
        )


class TestMixedTypeCommit:
    def test_operator_and_document_together(
        self, httpx_mock, session, payloads, base_url
    ):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/operators/",
            json=payloads.operator(id="00000000-0000-0000-0000-0000000000c1"),
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/documents/",
            json=payloads.document(id="00000000-0000-0000-0000-0000000000c2"),
        )
        op = Operator(
            name="x",
            jsonschema={"type": "object"},
            generation_prompt="p",
            chunk_type=1,
        )
        doc = Document(source_url="https://example.com/x.pdf")
        session.add(op)
        session.add(doc)
        session.commit()
        assert op.id is not None
        assert doc.id is not None


class TestRefresh:
    def test_refresh_overwrites_fields(self, httpx_mock, session, payloads):
        doc = Document(**payloads.document())
        session._bind(doc)
        # Overwrite name server-side.
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/documents/{doc.id}$"),
            json=payloads.document(id=str(doc.id), name="updated.pdf"),
        )
        session.refresh(doc)
        assert doc.name == "updated.pdf"

    def test_refresh_document_group(self, httpx_mock, session, payloads, project_id):
        group = DocumentGroup(**payloads.document_group())
        session._bind(group)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/projects/{project_id}/groups/{group.id}$"),
            json=payloads.document_group(id=str(group.id), name="Q3"),
        )
        session.refresh(group)
        assert group.name == "Q3"
