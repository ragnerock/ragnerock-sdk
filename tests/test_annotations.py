"""Tests for Annotation CRUD and the various listing endpoints."""

from __future__ import annotations

import re
from uuid import UUID

import pytest

from ragnerock import Annotation, Chunk, Document, Operator
from tests.conftest import TEST_HOST


class TestCreate:
    def test_add_commit_posts_annotation(self, httpx_mock, session, payloads):
        new_root = "00000000-0000-0000-0000-000000000510"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/annotations/",
            json=payloads.annotation(root_id=new_root),
        )
        a = Annotation(
            operator_id="00000000-0000-0000-0000-000000000601",
            document_id="00000000-0000-0000-0000-000000000101",
            data={"total": 500.0},
        )
        session.add(a)
        session.commit()
        assert a.root_id == UUID(new_root)

    def test_create_requires_operator(self, session):
        from ragnerock import ValidationError

        a = Annotation(document_id="00000000-0000-0000-0000-000000000101", data={"x": 1})
        session.add(a)
        with pytest.raises(ValidationError):
            session.commit()

    def test_create_requires_attachment_point(self, session):
        from ragnerock import ValidationError

        a = Annotation(
            operator_id="00000000-0000-0000-0000-000000000601",
            data={"x": 1},
        )  # no document_id, chunk_id, or page_id
        session.add(a)
        with pytest.raises(ValidationError):
            session.commit()


class TestGet:
    def test_get_by_root_id(self, httpx_mock, session, payloads):
        rid = "00000000-0000-0000-0000-000000000501"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/annotations/{rid}",
            json=payloads.annotation(root_id=rid),
        )
        a = session.get(Annotation, id=rid)
        assert a is not None
        assert a.root_id == UUID(rid)


class TestListByDocument:
    def test_list_by_document(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/annotations/document/{doc_id}(\?.*)?$"),
            json=payloads.list_envelope(
                "annotations", [payloads.annotation()]
            ),
        )
        annotations = session.list(Annotation, document_id=doc_id).all()
        assert len(annotations) == 1

    def test_list_by_document_and_operator_name(
        self, httpx_mock, session, payloads
    ):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                rf".*/api/annotations/document/{doc_id}/operator-name/invoice_extract\?.*"
            ),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        annotations = session.list(
            Annotation, document_id=doc_id, operator_name="invoice_extract"
        ).all()
        assert len(annotations) == 1

    def test_document_shortcut_passes_id(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/annotations/document/{doc_id}(\?.*)?$"),
            json=payloads.list_envelope("annotations", []),
        )
        doc = Document(**payloads.document(id=doc_id))
        session._bind(doc)
        doc.list(Annotation).all()


class TestListByChunk:
    def test_list_by_chunk(self, httpx_mock, session, payloads):
        cid = "00000000-0000-0000-0000-000000000301"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/annotations/chunk/{cid}(\?.*)?$"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        annotations = session.list(Annotation, chunk_id=cid).all()
        assert len(annotations) == 1

    def test_chunk_shortcut(self, httpx_mock, session, payloads):
        cid = "00000000-0000-0000-0000-000000000301"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/annotations/chunk/{cid}(\?.*)?$"),
            json=payloads.list_envelope("annotations", []),
        )
        c = Chunk(**payloads.chunk(id=cid))
        session._bind(c)
        c.list(Annotation).all()


class TestListByOperator:
    def test_list_by_operator(self, httpx_mock, session, payloads):
        oid = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/annotations/operator/{oid}(\?.*)?$"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        annotations = session.list(Annotation, operator_id=oid).all()
        assert len(annotations) == 1

    def test_hydrated_by_operator(self, httpx_mock, session, payloads):
        oid = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/annotations/operator/{oid}/hydrated\?.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        annotations = session.list(
            Annotation, operator_id=oid, hydrated=True
        ).all()
        assert len(annotations) == 1
        # Hydrated annotations have full data.
        assert annotations[0].data is not None

    def test_operator_shortcut_with_document_filter(
        self, httpx_mock, session, payloads
    ):
        oid = "00000000-0000-0000-0000-000000000601"
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                rf".*/api/annotations/document/{doc_id}/operator/{oid}\?.*"
            ),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        op = Operator(**payloads.operator(id=oid))
        doc = Document(**payloads.document(id=doc_id))
        session._bind(op)
        session._bind(doc)
        op.list(Annotation, document=doc).all()


class TestUpdate:
    def test_update_puts(self, httpx_mock, session, payloads):
        rid = "00000000-0000-0000-0000-000000000501"
        httpx_mock.add_response(
            method="PUT",
            url=f"{TEST_HOST}/api/annotations/{rid}",
            json=payloads.annotation(root_id=rid, data={"total": 9999}),
        )
        a = Annotation(**payloads.annotation(root_id=rid))
        a.data = {"total": 9999}
        session.update(a)
        session.commit()
        assert a.data == {"total": 9999}


class TestDelete:
    def test_delete_by_root_id(self, httpx_mock, session, payloads):
        rid = "00000000-0000-0000-0000-000000000501"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{TEST_HOST}/api/annotations/{rid}",
            json={},
        )
        a = Annotation(**payloads.annotation(root_id=rid))
        session.delete(a)
        session.commit()
