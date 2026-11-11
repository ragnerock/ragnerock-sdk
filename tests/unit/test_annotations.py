"""CRUD + scoped-list tests for ``Annotation``."""

from __future__ import annotations

import re
from uuid import UUID

import pytest

from ragnerock import (
    Annotation,
    Chunk,
    Document,
    Task,
    ValidationError,
)

# What the document + task-name endpoint returns per annotation: no
# task or document ids, just identity, chunk, and values.
_SCOPED_ANNOTATION = {
    "root_id": "00000000-0000-0000-0000-000000000502",
    "chunk_id": None,
    "data": {"total": 5},
}


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

    def test_list_by_document_and_task_id_hits_scoped_endpoint(
        self, httpx_mock, session, payloads
    ):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/document/.*/task/.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        session.list(
            Annotation,
            document_id="00000000-0000-0000-0000-000000000101",
            task_id="00000000-0000-0000-0000-000000000601",
        ).all()
        req = next(
            r
            for r in httpx_mock.get_requests()
            if "/annotations/document/" in r.url.path and "/task/" in r.url.path
        )
        assert req is not None

    def test_list_by_document_and_task_name_hits_name_endpoint(
        self, httpx_mock, session, payloads
    ):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                r".*/api/annotations/document/.*/task-name/invoice_extract.*"
            ),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        session.list(
            Annotation,
            document_id="00000000-0000-0000-0000-000000000101",
            task_name="invoice_extract",
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


class TestListByTask:
    def test_plain_list(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/task/[^/]+\?.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        session.list(Annotation, task_id="00000000-0000-0000-0000-000000000601").all()

    def test_hydrated_list(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/task/.*/hydrated.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        session.list(
            Annotation,
            task_id="00000000-0000-0000-0000-000000000601",
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
            task_id="00000000-0000-0000-0000-000000000601",
            document_id="00000000-0000-0000-0000-000000000101",
            data={"total": 10.5},
        )
        session.add(ann)
        session.commit()
        assert ann.root_id is not None

    def test_create_requires_task_id(self, session):
        ann = Annotation(
            document_id="00000000-0000-0000-0000-000000000101",
            data={"x": 1},
        )
        session.add(ann)
        with pytest.raises(ValidationError):
            session.commit()

    def test_create_requires_attachment_point(self, session):
        ann = Annotation(
            task_id="00000000-0000-0000-0000-000000000601",
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

    def test_task_list_annotations(self, httpx_mock, session, payloads):
        task = Task(**payloads.task())
        session._bind(task)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/annotations/task/.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        assert len(task.list(Annotation).all()) == 1

    def test_document_list_annotations_by_task_object(
        self, httpx_mock, session, payloads
    ):
        # Routed by name: only that endpoint returns each annotation's root_id.
        doc = Document(**payloads.document())
        task = Task(**payloads.task())
        session._bind(doc)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                rf".*/api/annotations/document/{doc.id}/task-name/{task.name}\?.*"
            ),
            json=payloads.list_envelope("annotations", [_SCOPED_ANNOTATION]),
        )
        anns = doc.list(Annotation, task=task).all()
        assert [a.root_id for a in anns] == [UUID(_SCOPED_ANNOTATION["root_id"])]

    def test_document_list_annotations_by_unnamed_task_uses_id(
        self, httpx_mock, session, payloads
    ):
        doc = Document(**payloads.document())
        task = Task(**payloads.task(name=None))
        session._bind(doc)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/annotations/document/{doc.id}/task/{task.id}\?.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        assert len(doc.list(Annotation, task=task).all()) == 1

    def test_document_list_annotations_by_task_name(
        self, httpx_mock, session, payloads
    ):
        doc = Document(**payloads.document())
        session._bind(doc)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                r".*/api/annotations/document/.*/task-name/invoice_extract\?.*"
            ),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        assert len(doc.list(Annotation, task="invoice_extract").all()) == 1

    def test_document_list_annotations_by_task_name_kwarg(
        self, httpx_mock, session, payloads
    ):
        doc = Document(**payloads.document())
        session._bind(doc)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                r".*/api/annotations/document/.*/task-name/invoice_extract\?.*"
            ),
            json=payloads.list_envelope("annotations", [_SCOPED_ANNOTATION]),
        )
        anns = doc.list(Annotation, task_name="invoice_extract").all()
        assert [a.root_id for a in anns] == [UUID(_SCOPED_ANNOTATION["root_id"])]

    def test_document_list_annotations_by_task_id_kwarg(
        self, httpx_mock, session, payloads
    ):
        doc = Document(**payloads.document())
        session._bind(doc)
        task_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/annotations/document/{doc.id}/task/{task_id}\?.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        anns = doc.list(Annotation, task_id=task_id).all()
        assert [str(a.task_id) for a in anns] == [task_id]

    def test_task_list_annotations_scoped_by_document_id(
        self, httpx_mock, session, payloads
    ):
        task = Task(**payloads.task())
        session._bind(task)
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                rf".*/api/annotations/document/{doc_id}/task-name/{task.name}\?.*"
            ),
            json=payloads.list_envelope("annotations", [_SCOPED_ANNOTATION]),
        )
        anns = task.list(Annotation, document=doc_id).all()
        assert [a.root_id for a in anns] == [UUID(_SCOPED_ANNOTATION["root_id"])]

    def test_task_list_annotations_by_document_object(
        self, httpx_mock, session, payloads
    ):
        task = Task(**payloads.task())
        doc = Document(**payloads.document())
        session._bind(task)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                rf".*/api/annotations/document/{doc.id}/task-name/{task.name}\?.*"
            ),
            json=payloads.list_envelope("annotations", [_SCOPED_ANNOTATION]),
        )
        anns = task.list(Annotation, document=doc).all()
        assert [a.root_id for a in anns] == [UUID(_SCOPED_ANNOTATION["root_id"])]

    def test_unnamed_task_list_annotations_by_document_uses_id(
        self, httpx_mock, session, payloads
    ):
        task = Task(**payloads.task(name=None))
        session._bind(task)
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/annotations/document/{doc_id}/task/{task.id}\?.*"),
            json=payloads.list_envelope("annotations", [payloads.annotation()]),
        )
        assert len(task.list(Annotation, document=doc_id).all()) == 1


class TestLazyNavigation:
    def test_document_and_task_are_fetched_on_access(
        self, httpx_mock, session, payloads
    ):
        anno = Annotation(**payloads.annotation())
        session._bind(anno)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/documents/{anno.document_id}$"),
            json=payloads.document(),
        )
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/tasks/{anno.task_id}$"),
            json=payloads.task(),
        )
        document = anno.document
        task = anno.task
        assert document is not None and document.name == "sample.pdf"
        assert task is not None and task.name == "invoice_extract"

    def test_unset_targets_return_none_without_a_request(
        self, httpx_mock, session, payloads
    ):
        anno = Annotation(**payloads.annotation())
        session._bind(anno)
        before = len(httpx_mock.get_requests())
        assert anno.chunk is None
        assert anno.page is None
        assert len(httpx_mock.get_requests()) == before

    def test_unbound_annotation_raises(self, payloads):
        with pytest.raises(RuntimeError):
            _ = Annotation(**payloads.annotation()).document
