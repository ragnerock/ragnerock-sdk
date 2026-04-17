"""End-to-end Annotation flows.

Creating an annotation requires both a real operator and a real document.
"""

from __future__ import annotations

from ragnerock import Annotation, ChunkType, Document, Operator


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


def test_annotation_crud(session, unique_name, tmp_path):
    op = _make_operator(unique_name)
    session.add(op)
    session.commit()

    file_path = tmp_path / f"{unique_name}.txt"
    file_path.write_text("Small text for annotation.")
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

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

        # List via document shortcut.
        doc_annotations = list(doc.list(Annotation))
        assert any(a.root_id == annotation.root_id for a in doc_annotations)

        # Update.
        annotation.data = {"total": 99}
        session.update(annotation)
        session.commit()
        session.refresh(annotation)
        assert annotation.data == {"total": 99}
    finally:
        session.delete(annotation)
        session.commit()
        session.delete(doc)
        session.commit()
        session.delete(op)
        session.commit()
