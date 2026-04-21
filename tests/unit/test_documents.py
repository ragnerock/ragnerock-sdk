"""CRUD tests for ``Document``, including URL-only uploads and downloads."""

from __future__ import annotations

import re

import pytest

from ragnerock import Document, FileType, NotFoundError, ValidationError


class TestGet:
    def test_get_by_id_returns_document(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/documents/{doc_id}$"),
            json=payloads.document(id=doc_id, name="contract.pdf"),
        )
        doc = session.get(Document, id=doc_id)
        assert doc is not None
        assert doc.name == "contract.pdf"
        assert doc.file_type == FileType.PDF

    def test_get_by_name_returns_document(
        self, httpx_mock, session, payloads, base_url
    ):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                rf"{re.escape(base_url)}/api/documents/name/contract\.pdf.*"
            ),
            json=payloads.document(name="contract.pdf"),
        )
        doc = session.get(Document, name="contract.pdf")
        assert doc is not None
        assert doc.name == "contract.pdf"

    def test_get_missing_returns_none(self, httpx_mock, session):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/.*"),
            status_code=404,
            json={"detail": {"message": "not found"}},
        )
        doc = session.get(Document, id="00000000-0000-0000-0000-000000000999")
        assert doc is None


class TestList:
    def test_list_returns_all_documents(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/\?.*"),
            json=payloads.list_envelope(
                "documents",
                [payloads.document(name="a"), payloads.document(name="b")],
            ),
        )
        docs = session.list(Document).all()
        assert [d.name for d in docs] == ["a", "b"]

    def test_list_params_include_project_and_skip_limit(
        self, httpx_mock, session, payloads
    ):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/\?.*"),
            json=payloads.list_envelope("documents", []),
        )
        session.list(Document).all()
        req = next(
            r for r in httpx_mock.get_requests() if r.url.path == "/api/documents/"
        )
        params = dict(req.url.params)
        assert "project_ids" in params
        assert params["skip"] == "0"


class TestCreate:
    def test_create_via_source_url(self, httpx_mock, session, payloads, base_url):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/documents/",
            json=payloads.document(
                id="00000000-0000-0000-0000-0000000000a1", name="a.pdf"
            ),
        )
        doc = Document(source_url="https://example.com/a.pdf", name="a.pdf")
        session.add(doc)
        session.commit()
        assert doc.id is not None
        assert doc.name == "a.pdf"

    def test_create_requires_file_path_or_source_url(self, session):
        doc = Document(name="noop")
        session.add(doc)
        with pytest.raises(ValidationError):
            session.commit()


class TestUpdate:
    def test_update_sends_patch(self, httpx_mock, session, payloads, base_url):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/documents/{doc_id}",
            json=payloads.document(id=doc_id, name="renamed.pdf"),
        )
        doc = Document(**payloads.document(id=doc_id))
        doc.name = "renamed.pdf"
        session.update(doc)
        session.commit()
        assert doc.name == "renamed.pdf"

    def test_update_404_wraps_not_found_in_commit_error(
        self, httpx_mock, session, payloads, base_url
    ):
        from ragnerock import CommitError

        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/documents/{doc_id}",
            status_code=404,
            json={"detail": {"message": "gone"}},
        )
        doc = Document(**payloads.document(id=doc_id))
        doc.name = "x"
        session.update(doc)
        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, NotFoundError)


class TestDelete:
    def test_delete_issues_http_delete(self, httpx_mock, session, payloads, base_url):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{base_url}/api/documents/{doc_id}",
            status_code=204,
            text="",
        )
        doc = Document(**payloads.document(id=doc_id))
        session.delete(doc)
        session.commit()
        deletes = [
            r
            for r in httpx_mock.get_requests()
            if r.method == "DELETE" and r.url.path == f"/api/documents/{doc_id}"
        ]
        assert len(deletes) == 1


class TestContentDownload:
    def test_content_returns_raw_bytes(self, httpx_mock, session, payloads, base_url):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/documents/{doc_id}$"),
            json=payloads.document(id=doc_id),
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/api/documents/{doc_id}/content",
            content=b"PDF-bytes",
        )
        doc = session.get(Document, id=doc_id)
        assert doc is not None
        assert doc.content() == b"PDF-bytes"

    def test_content_on_unbound_document_raises(self):
        doc = Document(id="00000000-0000-0000-0000-000000000101")
        with pytest.raises(RuntimeError):
            doc.content()

    def test_content_without_id_raises(self, session):
        doc = Document()
        session._bind(doc)
        with pytest.raises(RuntimeError):
            doc.content()
