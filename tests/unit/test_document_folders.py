"""CRUD tests for ``DocumentFolder`` and its document navigation."""

from __future__ import annotations

import re

import pytest

from ragnerock import Document, DocumentFolder, ValidationError


class TestCrud:
    def test_create(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=re.compile(r".*/api/projects/.*/document-folders/$"),
            json=payloads.document_folder(name="Q1"),
        )
        folder = DocumentFolder(name="Q1")
        session.add(folder)
        session.commit()
        assert folder.id is not None

    def test_create_requires_name(self, session):
        """Missing name is raised from ``_create_resource`` inside ``commit``,
        so it surfaces wrapped in a ``CommitError``."""
        from ragnerock import CommitError

        folder = DocumentFolder()
        session.add(folder)
        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, ValidationError)

    def test_get_by_id(self, httpx_mock, session, payloads, base_url, project_id):
        document_folder_id = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/api/projects/{project_id}/document-folders/{document_folder_id}",
            json=payloads.document_folder(id=document_folder_id),
        )
        folder = session.get(DocumentFolder, id=document_folder_id)
        assert folder is not None
        assert folder.name == "Q1 contracts"

    def test_get_by_name_lists_then_fetches(
        self, httpx_mock, session, payloads, base_url, project_id
    ):
        document_folder_id = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/projects/{project_id}/document-folders/\?.*"),
            json=payloads.list_envelope(
                "document_folders",
                [payloads.document_folder(id=document_folder_id, name="Q1 contracts")],
            ),
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/api/projects/{project_id}/document-folders/{document_folder_id}",
            json=payloads.document_folder(id=document_folder_id, name="Q1 contracts"),
        )
        folder = session.get(DocumentFolder, name="Q1 contracts")
        assert folder is not None
        assert folder.id is not None
        assert str(folder.id) == document_folder_id
        assert folder.name == "Q1 contracts"

    def test_get_by_missing_name_returns_none(
        self, httpx_mock, session, payloads, project_id
    ):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/projects/{project_id}/document-folders/\?.*"),
            json=payloads.list_envelope("document_folders", []),
        )
        assert session.get(DocumentFolder, name="does_not_exist") is None

    def test_update_sends_new_name(
        self, httpx_mock, session, payloads, base_url, project_id
    ):
        document_folder_id = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/projects/{project_id}/document-folders/{document_folder_id}",
            json=payloads.document_folder(id=document_folder_id, name="Q2"),
        )
        folder = DocumentFolder(**payloads.document_folder(id=document_folder_id))
        folder.name = "Q2"
        session.update(folder)
        session.commit()
        assert folder.name == "Q2"

    def test_delete(self, httpx_mock, session, payloads, base_url, project_id):
        document_folder_id = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{base_url}/api/projects/{project_id}/document-folders/{document_folder_id}",
            status_code=204,
            text="",
        )
        folder = DocumentFolder(**payloads.document_folder(id=document_folder_id))
        session.delete(folder)
        session.commit()


class TestList:
    def test_list_returns_document_folders(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/projects/.*/document-folders/\?.*"),
            json=payloads.list_envelope(
                "document_folders",
                [
                    payloads.document_folder(name="A"),
                    payloads.document_folder(name="B"),
                ],
            ),
        )
        document_folders = session.list(DocumentFolder).all()
        assert [f.name for f in document_folders] == ["A", "B"]


class TestNavigation:
    def test_list_documents_in_folder(self, httpx_mock, session, payloads):
        folder = DocumentFolder(**payloads.document_folder())
        session._bind(folder)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/documents/document-folder/{folder.id}.*"),
            json=payloads.list_envelope("documents", [payloads.document()]),
        )
        docs = folder.list(Document).all()
        assert len(docs) == 1
