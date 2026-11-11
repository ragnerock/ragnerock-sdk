"""End-to-end DocumentFolder flows: CRUD + moving documents between folders."""

from __future__ import annotations

from ragnerock import Document, DocumentFolder


def test_document_folder_crud(session, unique_name):
    folder = DocumentFolder(name=unique_name)
    session.add(folder)
    session.commit()
    assert folder.id is not None

    try:
        round_tripped = session.get(DocumentFolder, id=folder.id)
        assert round_tripped is not None
        assert round_tripped.name == unique_name

        names = [f.name for f in session.list(DocumentFolder)]
        assert unique_name in names

        new_name = f"{unique_name}-renamed"
        folder.name = new_name
        session.update(folder)
        session.commit()
        session.refresh(folder)
        assert folder.name == new_name
    finally:
        session.delete(folder)
        session.commit()

    assert session.get(DocumentFolder, id=folder.id) is None


def test_move_document_into_folder(session, unique_name, tmp_path):
    """Upload a doc, assign it to a folder via update, list docs in folder."""
    folder = DocumentFolder(name=unique_name)
    session.add(folder)
    session.commit()

    file_path = tmp_path / f"{unique_name}.pdf"
    file_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

    try:
        doc.document_folder_id = folder.id
        session.update(doc)
        session.commit()

        session.refresh(doc)
        assert doc.document_folder_id == folder.id

        docs_in_folder = list(folder.list(Document))
        assert any(d.id == doc.id for d in docs_in_folder)
    finally:
        session.delete(doc)
        session.commit()
        session.delete(folder)
        session.commit()
