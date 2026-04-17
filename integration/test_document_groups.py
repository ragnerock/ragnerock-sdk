"""End-to-end DocumentGroup flows."""

from __future__ import annotations

from ragnerock import Document, DocumentGroup


def test_group_crud(session, unique_name):
    group = DocumentGroup(name=unique_name)
    session.add(group)
    session.commit()
    assert group.id is not None

    try:
        # Read it back.
        round_tripped = session.get(DocumentGroup, id=group.id)
        assert round_tripped is not None
        assert round_tripped.name == unique_name

        # List sees it.
        names = [g.name for g in session.list(DocumentGroup)]
        assert unique_name in names

        # Rename.
        new_name = f"{unique_name}-renamed"
        group.name = new_name
        session.update(group)
        session.commit()
        session.refresh(group)
        assert group.name == new_name
    finally:
        session.delete(group)
        session.commit()

    assert session.get(DocumentGroup, id=group.id) is None


def test_move_document_into_group(session, unique_name, tmp_path):
    """Upload a doc, assign it to a group via update, list docs in group."""
    group = DocumentGroup(name=unique_name)
    session.add(group)
    session.commit()

    file_path = tmp_path / f"{unique_name}.pdf"
    file_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

    try:
        # Assign the doc to the group.
        doc.group_id = group.id
        session.update(doc)
        session.commit()

        session.refresh(doc)
        assert doc.group_id == group.id

        # group.list(Document) should now include it.
        docs_in_group = list(group.list(Document))
        assert any(d.id == doc.id for d in docs_in_group)
    finally:
        session.delete(doc)
        session.commit()
        session.delete(group)
        session.commit()
