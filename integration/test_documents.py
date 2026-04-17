"""End-to-end Document flows."""

from __future__ import annotations

from ragnerock import Document


def _write_fake_pdf(tmp_path, name: str) -> str:
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4\n% fake test doc\n%%EOF\n")
    return str(p)


def test_upload_get_download_delete(session, unique_name, tmp_path):
    """Upload a local file, fetch it back by id and by name, download, delete."""
    file_path = _write_fake_pdf(tmp_path, f"{unique_name}.pdf")
    doc = Document(file_path=file_path, name=unique_name)
    session.add(doc)
    session.commit()
    assert doc.id is not None
    assert doc.storage_path

    try:
        # Get by id.
        round_tripped = session.get(Document, id=doc.id)
        assert round_tripped is not None
        assert round_tripped.name == unique_name

        # Get by name.
        by_name = session.get(Document, name=unique_name)
        assert by_name is not None
        assert by_name.id == doc.id

        # Download content.
        data = doc.content()
        assert isinstance(data, bytes)
        assert data.startswith(b"%PDF-1.4")
    finally:
        session.delete(doc)
        session.commit()

    # After delete, lookup should return None.
    assert session.get(Document, id=doc.id) is None


def test_list_includes_new_document(session, unique_name, tmp_path):
    """A freshly-created document shows up in the list within the same session."""
    file_path = _write_fake_pdf(tmp_path, f"{unique_name}.pdf")
    doc = Document(file_path=file_path, name=unique_name)
    session.add(doc)
    session.commit()

    try:
        names = [d.name for d in session.list(Document)]
        assert unique_name in names
    finally:
        session.delete(doc)
        session.commit()


def test_rename(session, unique_name, tmp_path):
    """Update a document's name and verify the change round-trips."""
    file_path = _write_fake_pdf(tmp_path, f"{unique_name}.pdf")
    doc = Document(file_path=file_path, name=unique_name)
    session.add(doc)
    session.commit()

    try:
        new_name = f"{unique_name}-renamed"
        doc.name = new_name
        session.update(doc)
        session.commit()

        session.refresh(doc)
        assert doc.name == new_name
    finally:
        session.delete(doc)
        session.commit()


def test_get_missing_returns_none(session):
    from uuid import uuid4

    assert session.get(Document, id=uuid4()) is None
    assert session.get(Document, name=f"definitely-missing-{uuid4().hex[:8]}") is None
