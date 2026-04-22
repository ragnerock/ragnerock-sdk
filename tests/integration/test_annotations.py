"""End-to-end Annotation flows.

Creating an annotation requires a real operator and a real attachment point
(document, chunk, or page). These tests cover CRUD plus the listing variants:
by document, by operator (with and without hydration), and filtering an
operator's annotations to a specific document.
"""

from __future__ import annotations

import time

import pytest

from ragnerock import Annotation, Chunk, ChunkType, Document, Operator, ValidationError


_INGESTION_POLL_TIMEOUT = 30.0
_INGESTION_POLL_INTERVAL = 2.0


def _make_operator(name: str) -> Operator:
    return Operator(
        name=name,
        description="SDK integration test operator",
        jsonschema={
            "type": "object",
            "properties": {"total": {"type": "number"}},
        },
        generation_prompt="Return a JSON object.",
        chunk_type=ChunkType.DOCUMENT,
    )


@pytest.fixture
def operator_and_document(session, unique_name, tmp_path):
    """An operator + document committed on the live server, cleaned up after."""
    op = _make_operator(unique_name)
    session.add(op)
    session.commit()

    file_path = tmp_path / f"{unique_name}.txt"
    file_path.write_text("Small text for annotation.")
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

    yield op, doc

    try:
        session.delete(doc)
        session.commit()
    except Exception as e:  # noqa: BLE001
        print(f"cleanup doc failed: {e}")
    try:
        session.delete(op)
        session.commit()
    except Exception as e:  # noqa: BLE001
        print(f"cleanup op failed: {e}")


class TestCreateValidation:
    """Client-side validation fires before any network call — mocks not needed."""

    def test_create_requires_operator(self, session, operator_and_document):
        _, doc = operator_and_document
        a = Annotation(document_id=doc.id, data={"x": 1})
        session.add(a)
        with pytest.raises(ValidationError):
            session.commit()

    def test_create_requires_attachment_point(self, session, operator_and_document):
        op, _ = operator_and_document
        a = Annotation(operator_id=op.id, data={"x": 1})  # no doc/chunk/page
        session.add(a)
        with pytest.raises(ValidationError):
            session.commit()


class TestCrud:
    def test_create_get_update_delete(self, session, operator_and_document):
        op, doc = operator_and_document

        annotation = Annotation(
            operator_id=op.id,
            document_id=doc.id,
            data={"total": 42},
            confidence_score=0.9,
        )
        session.add(annotation)
        session.commit()
        assert annotation.root_id is not None

        try:
            # Get by root_id.
            fetched = session.get(Annotation, id=annotation.root_id)
            assert fetched is not None
            assert fetched.data == {"total": 42}

            # Update in place.
            annotation.data = {"total": 99}
            session.update(annotation)
            session.commit()
            session.refresh(annotation)
            assert annotation.data == {"total": 99}
        finally:
            session.delete(annotation)
            session.commit()

        assert session.get(Annotation, id=annotation.root_id) is None


class TestListByDocument:
    def test_list_by_document(self, session, operator_and_document):
        op, doc = operator_and_document
        a = Annotation(operator_id=op.id, document_id=doc.id, data={"total": 1})
        session.add(a)
        session.commit()

        try:
            listed = list(session.list(Annotation, document_id=doc.id))
            assert any(x.root_id == a.root_id for x in listed)

            # Document shortcut should return the same.
            via_doc = list(doc.list(Annotation))
            assert any(x.root_id == a.root_id for x in via_doc)
        finally:
            session.delete(a)
            session.commit()

    def test_list_by_document_and_operator_name(self, session, operator_and_document):
        op, doc = operator_and_document
        a = Annotation(operator_id=op.id, document_id=doc.id, data={"total": 2})
        session.add(a)
        session.commit()
        session.refresh(a)

        try:
            listed = list(
                session.list(
                    Annotation, document_id=doc.id, operator_name=op.name
                ).all()
            )

            assert any(x.root_id == a.root_id for x in listed)
        finally:
            session.delete(a)
            session.commit()


class TestListByOperator:
    def test_list_by_operator(self, session, operator_and_document):
        op, doc = operator_and_document
        a = Annotation(operator_id=op.id, document_id=doc.id, data={"total": 3})
        session.add(a)
        session.commit()

        try:
            listed = list(session.list(Annotation, operator_id=op.id))
            assert any(x.root_id == a.root_id for x in listed)
        finally:
            session.delete(a)
            session.commit()

    def test_hydrated_by_operator(self, session, operator_and_document):
        op, doc = operator_and_document
        a = Annotation(operator_id=op.id, document_id=doc.id, data={"total": 4})
        session.add(a)
        session.commit()

        try:
            listed = list(session.list(Annotation, operator_id=op.id, hydrated=True))
            matching = [x for x in listed if x.root_id == a.root_id]
            assert matching, "hydrated listing should include the annotation"
            assert matching[0].data is not None
        finally:
            session.delete(a)
            session.commit()

    def test_operator_shortcut_with_document_filter(
        self, session, operator_and_document
    ):
        op, doc = operator_and_document
        a = Annotation(operator_id=op.id, document_id=doc.id, data={"total": 5})
        session.add(a)
        session.commit()

        try:
            listed = list(op.list(Annotation, document=doc).all())
            assert any(x.root_id == a.root_id for x in listed)
        finally:
            session.delete(a)
            session.commit()


class TestListByChunk:
    """Listing by chunk requires a real chunk, which only appears after ingestion.

    If ingestion doesn't complete in time the test is inconclusive rather than
    failing — slow instances shouldn't break CI.
    """

    def test_list_by_chunk_after_ingestion(self, session, operator_and_document):
        op, doc = operator_and_document

        deadline = time.monotonic() + _INGESTION_POLL_TIMEOUT
        chunks: list = []
        while time.monotonic() < deadline:
            chunks = list(doc.list(Chunk).limit(1))
            if chunks:
                break
            time.sleep(_INGESTION_POLL_INTERVAL)
        if not chunks:
            pytest.skip("ingestion did not produce chunks within the poll window")

        chunk = chunks[0]
        a = Annotation(operator_id=op.id, chunk_id=chunk.id, data={"total": 6})
        session.add(a)
        session.commit()

        try:
            listed = list(session.list(Annotation, chunk_id=chunk.id))
            assert any(x.root_id == a.root_id for x in listed)

            via_chunk = list(chunk.list(Annotation))
            assert any(x.root_id == a.root_id for x in via_chunk)
        finally:
            session.delete(a)
            session.commit()
