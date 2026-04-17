"""Tests for Document CRUD, upload (multipart), download, and name lookup."""

from __future__ import annotations

import re
from uuid import UUID

import pytest

from ragnerock import Document
from tests.conftest import TEST_HOST, TEST_PROJECT_ID


class TestList:
    def test_list_documents(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf"{re.escape(TEST_HOST)}/api/documents/\?.*"),
            json=payloads.list_envelope(
                "documents",
                [payloads.document(), payloads.document(id="00000000-0000-0000-0000-000000000102", name="other.pdf")],
            ),
        )
        docs = session.list(Document).all()
        assert len(docs) == 2
        assert {d.name for d in docs} == {"sample.pdf", "other.pdf"}

    def test_list_filters_by_project(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*project_ids=.*"),
            json=payloads.list_envelope("documents", []),
        )
        session.list(Document).all()

        requests = [
            r for r in httpx_mock.get_requests() if r.url.path == "/api/documents/"
        ]
        assert requests
        # project_ids should be in the query string.
        assert "project_ids" in str(requests[0].url)


class TestGetByID:
    def test_get_by_id_hits_id_endpoint(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/documents/{doc_id}",
            json=payloads.document(id=doc_id),
        )
        doc = session.get(Document, id=doc_id)
        assert doc is not None
        assert doc.id == UUID(doc_id)

    def test_get_by_id_returns_none_on_404(self, httpx_mock, session):
        doc_id = "00000000-0000-0000-0000-000000000199"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/documents/{doc_id}",
            status_code=404,
            json={"detail": {"message": "not found"}},
        )
        assert session.get(Document, id=doc_id) is None


class TestGetByName:
    def test_get_by_name_uses_name_endpoint(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/documents/name/sample.pdf\?.*"),
            json=payloads.document(name="sample.pdf"),
        )
        doc = session.get(Document, name="sample.pdf")
        assert doc is not None
        assert doc.name == "sample.pdf"

    def test_get_by_name_returns_none_on_404(self, httpx_mock, session):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/name/.*"),
            status_code=404,
            json={"detail": {"message": "not found"}},
        )
        assert session.get(Document, name="missing.pdf") is None


class TestCreate:
    def test_add_commit_posts_multipart_with_project_id(
        self, httpx_mock, session, payloads, tmp_path
    ):
        file_path = tmp_path / "report.pdf"
        file_path.write_bytes(b"%PDF-1.4 fake")

        new_id = "00000000-0000-0000-0000-000000000110"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/documents/",
            json=payloads.document(id=new_id, name="report.pdf"),
        )

        doc = Document(file_path=str(file_path), name="report.pdf")
        session.add(doc)
        session.commit()

        req = next(
            r
            for r in httpx_mock.get_requests()
            if r.method == "POST" and r.url.path == "/api/documents/"
        )
        body = req.content.decode("latin-1")
        # Multipart body should include project_id and the file bytes.
        assert str(TEST_PROJECT_ID) in body
        assert b"%PDF-1.4 fake".decode("latin-1") in body

    def test_create_requires_file_path_or_source_url(self, session):
        from ragnerock import ValidationError

        doc = Document(name="empty")  # neither file_path nor source_url
        session.add(doc)
        with pytest.raises(ValidationError):
            session.commit()

    def test_source_url_variant(self, httpx_mock, session, payloads):
        new_id = "00000000-0000-0000-0000-000000000111"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/documents/",
            json=payloads.document(id=new_id, source_url="https://x.com/a.pdf"),
        )
        doc = Document(source_url="https://x.com/a.pdf", name="a.pdf")
        session.add(doc)
        session.commit()
        assert doc.id == UUID(new_id)


class TestUpdate:
    def test_update_puts_to_id_endpoint(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="PUT",
            url=f"{TEST_HOST}/api/documents/{doc_id}",
            json=payloads.document(id=doc_id, name="renamed.pdf"),
        )
        doc = Document(**payloads.document(id=doc_id))
        doc.name = "renamed.pdf"
        session.update(doc)
        session.commit()
        assert doc.name == "renamed.pdf"


class TestDelete:
    def test_delete_hits_id_endpoint(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{TEST_HOST}/api/documents/{doc_id}",
            json={},
        )
        doc = Document(**payloads.document(id=doc_id))
        session.delete(doc)
        session.commit()


class TestContentDownload:
    def test_content_returns_raw_bytes(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/documents/{doc_id}/content",
            content=b"\x89PNG binary data",
        )
        doc = Document(**payloads.document(id=doc_id))
        session._bind(doc)
        data = doc.content()
        assert data == b"\x89PNG binary data"
