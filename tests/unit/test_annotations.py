"""CRUD + scoped-list tests for ``Annotation``."""

from __future__ import annotations

import re

import pytest

from ragnerock import (
    Annotation,
    Chunk,
    Document,
    Operator,
    ValidationError,
)


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        root_id = "00000000-0000-0000-0000-000000000501"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/annotations/{root_id}$"),
            json=payloads.annotation(root_id=root_id),
        )
        ann = session.get(Annotation, id=root_id)
        assert ann is not None
        assert ann.id == ann.root_id
        assert ann.data == {"total": 1234.56, "vendor": "Acme"}

    def test_get_by_name_raises(self, session):
        with pytest.raises(ValidationError):
            session.get(Annotation, name="x")


class TestListRequiresScope:
    def test_requires_scope(self, session):
        with pytest.raises(ValidationError):
            session.list(Annotation).all()


class TestListByDocument:
    def test_list_by_document(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/document/.*"),
            json=payloads.list_envelope(
                "annotations",
                [payloads.annotation()],
            ),
        )
        anns = session.list(
            Annotation, document_id="00000000-0000-0000-0000-000000000101"
        ).all()
        assert len(anns) == 1

    def test_list_by_document_and_operator_id_hits_scoped_endpoint(
        self, httpx_mock, session, payloads
    ):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/document/.*/operator/.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        session.list(
            Annotation,
            document_id="00000000-0000-0000-0000-000000000101",
            operator_id="00000000-0000-0000-0000-000000000601",
        ).all()
        req = next(
            r
            for r in httpx_mock.get_requests()
            if "/annotations/document/" in r.url.path and "/operator/" in r.url.path
        )
        assert req is not None

    def test_list_by_document_and_operator_name_hits_name_endpoint(
        self, httpx_mock, session, payloads
    ):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                r".*/api/annotations/document/.*/operator-name/invoice_extract.*"
            ),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        session.list(
            Annotation,
            document_id="00000000-0000-0000-0000-000000000101",
            operator_name="invoice_extract",
        ).all()


class TestListByChunk:
    def test_list_by_chunk(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/chunk/.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        anns = session.list(
            Annotation, chunk_id="00000000-0000-0000-0000-000000000301"
        ).all()
        assert len(anns) == 1


class TestListByOperator:
    def test_plain_list(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/operator/[^/]+\?.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        session.list(
            Annotation, operator_id="00000000-0000-0000-0000-000000000601"
        ).all()

    def test_hydrated_list(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/operator/.*/hydrated.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        session.list(
            Annotation,
            operator_id="00000000-0000-0000-0000-000000000601",
            hydrated=True,
        ).all()


class TestCreate:
    def test_create_sends_body(self, httpx_mock, session, payloads, base_url):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/annotations/",
            json=payloads.annotation(
                root_id="00000000-0000-0000-0000-0000000aaaa1",
            ),
        )
        ann = Annotation(
            operator_id="00000000-0000-0000-0000-000000000601",
            document_id="00000000-0000-0000-0000-000000000101",
            data={"total": 10.5},
        )
        session.add(ann)
        session.commit()
        assert ann.root_id is not None

    def test_create_requires_operator_id(self, session):
        ann = Annotation(
            document_id="00000000-0000-0000-0000-000000000101",
            data={"x": 1},
        )
        session.add(ann)
        with pytest.raises(ValidationError):
            session.commit()

    def test_create_requires_attachment_point(self, session):
        ann = Annotation(
            operator_id="00000000-0000-0000-0000-000000000601",
            data={"x": 1},
        )
        session.add(ann)
        with pytest.raises(ValidationError):
            session.commit()


class TestUpdateDelete:
    def test_update(self, httpx_mock, session, payloads, base_url):
        root_id = "00000000-0000-0000-0000-000000000501"
        httpx_mock.add_response(
            method="PUT",
            url=re.compile(rf"{re.escape(base_url)}/api/annotations/{root_id}.*"),
            json=payloads.annotation(root_id=root_id, data={"total": 999}),
        )
        ann = Annotation(**payloads.annotation(root_id=root_id))
        ann.data = {"total": 999}
        session.update(ann)
        session.commit()
        assert ann.data == {"total": 999}

    def test_delete(self, httpx_mock, session, payloads, base_url):
        root_id = "00000000-0000-0000-0000-000000000501"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{base_url}/api/annotations/{root_id}",
            status_code=204,
            text="",
        )
        ann = Annotation(**payloads.annotation(root_id=root_id))
        session.delete(ann)
        session.commit()


class TestParentNavigation:
    def test_document_list_annotations(self, httpx_mock, session, payloads):
        doc = Document(**payloads.document())
        session._bind(doc)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/document/.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        assert len(doc.list(Annotation).all()) == 1

    def test_chunk_list_annotations(self, httpx_mock, session, payloads):
        chunk = Chunk(**payloads.chunk())
        session._bind(chunk)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/chunk/.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        assert len(chunk.list(Annotation).all()) == 1

    def test_operator_list_annotations(self, httpx_mock, session, payloads):
        op = Operator(**payloads.operator())
        session._bind(op)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/operator/.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        assert len(op.list(Annotation).all()) == 1
