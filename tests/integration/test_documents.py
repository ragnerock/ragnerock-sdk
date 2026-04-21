"""End-to-end Document flows: upload, download, list, get-by-name, rename, delete."""

from __future__ import annotations

from uuid import uuid4

import pytest

from ragnerock import Document, ValidationError


def _write_fake_pdf(tmp_path, name: str) -> str:
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4\n% fake test doc\n%%EOF\n")
    return str(p)


class TestCreate:
    def test_upload_populates_server_fields(self, session, unique_name, tmp_path):
        """After commit, the local object carries server-assigned id/storage_path/timestamps."""
        file_path = _write_fake_pdf(tmp_path, f"{unique_name}.pdf")
        doc = Document(file_path=file_path, name=unique_name)
        session.add(doc)
        session.commit()
        try:
            assert doc.id is not None
            assert doc.storage_path
            assert doc.created_at is not None
        finally:
            session.delete(doc)
            session.commit()

    def test_create_requires_file_path_or_source_url(self, session):
        doc = Document(name="empty")  # neither file_path nor source_url
        session.add(doc)
        with pytest.raises(ValidationError):
            session.commit()


class TestGetByID:
    def test_get_by_id_round_trips(self, session, unique_name, tmp_path):
        file_path = _write_fake_pdf(tmp_path, f"{unique_name}.pdf")
        doc = Document(file_path=file_path, name=unique_name)
        session.add(doc)
        session.commit()
        try:
            fetched = session.get(Document, id=doc.id)
            assert fetched is not None
            assert fetched.id == doc.id
            assert fetched.name == unique_name
        finally:
            session.delete(doc)
            session.commit()

    def test_get_by_missing_id_returns_none(self, session):
        assert session.get(Document, id=uuid4()) is None


class TestGetByName:
    def test_get_by_name_round_trips(self, session, unique_name, tmp_path):
        file_path = _write_fake_pdf(tmp_path, f"{unique_name}.pdf")
        doc = Document(file_path=file_path, name=unique_name)
        session.add(doc)
        session.commit()
        try:
            by_name = session.get(Document, name=unique_name)
            assert by_name is not None
            assert by_name.id == doc.id
        finally:
            session.delete(doc)
            session.commit()

    def test_get_by_missing_name_returns_none(self, session):
        assert (
            session.get(Document, name=f"definitely-missing-{uuid4().hex[:8]}") is None
        )


class TestList:
    def test_list_includes_new_document(self, session, unique_name, tmp_path):
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


class TestUpdate:
    def test_rename(self, session, unique_name, tmp_path):
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


class TestDelete:
    def test_delete_then_lookup_returns_none(self, session, unique_name, tmp_path):
        file_path = _write_fake_pdf(tmp_path, f"{unique_name}.pdf")
        doc = Document(file_path=file_path, name=unique_name)
        session.add(doc)
        session.commit()
        doc_id = doc.id

        session.delete(doc)
        session.commit()

        assert session.get(Document, id=doc_id) is None


class TestContentDownload:
    def test_content_returns_uploaded_bytes(self, session, unique_name, tmp_path):
        file_path = _write_fake_pdf(tmp_path, f"{unique_name}.pdf")
        doc = Document(file_path=file_path, name=unique_name)
        session.add(doc)
        session.commit()
        try:
            data = doc.content()
            assert isinstance(data, bytes)
            assert data.startswith(b"%PDF-1.4")
        finally:
            session.delete(doc)
            session.commit()
