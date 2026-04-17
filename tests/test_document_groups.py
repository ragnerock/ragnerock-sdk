"""Tests for DocumentGroup CRUD and listing documents in a group."""

from __future__ import annotations

import re
from uuid import UUID

from ragnerock import Document, DocumentGroup
from tests.conftest import TEST_HOST, TEST_PROJECT_ID


class TestList:
    def test_list_groups(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                rf"{re.escape(TEST_HOST)}/api/projects/{TEST_PROJECT_ID}/groups/\?.*"
            ),
            json=payloads.list_envelope("groups", [payloads.document_group()]),
        )
        groups = session.list(DocumentGroup).all()
        assert len(groups) == 1
        assert groups[0].name == "Q1 contracts"


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        gid = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/projects/{TEST_PROJECT_ID}/groups/{gid}",
            json=payloads.document_group(id=gid),
        )
        g = session.get(DocumentGroup, id=gid)
        assert g is not None
        assert g.id == UUID(gid)


class TestCreate:
    def test_add_commit_posts_to_project_groups(
        self, httpx_mock, session, payloads
    ):
        new_id = "00000000-0000-0000-0000-000000000210"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/projects/{TEST_PROJECT_ID}/groups/",
            json=payloads.document_group(id=new_id, name="Invoices"),
        )
        g = DocumentGroup(name="Invoices")
        session.add(g)
        session.commit()
        assert g.id == UUID(new_id)


class TestUpdate:
    def test_update_renames(self, httpx_mock, session, payloads):
        gid = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="PUT",
            url=f"{TEST_HOST}/api/projects/{TEST_PROJECT_ID}/groups/{gid}",
            json=payloads.document_group(id=gid, name="Renamed"),
        )
        g = DocumentGroup(**payloads.document_group(id=gid))
        g.name = "Renamed"
        session.update(g)
        session.commit()
        assert g.name == "Renamed"


class TestDelete:
    def test_delete_removes(self, httpx_mock, session, payloads):
        gid = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{TEST_HOST}/api/projects/{TEST_PROJECT_ID}/groups/{gid}",
            json={},
        )
        g = DocumentGroup(**payloads.document_group(id=gid))
        session.delete(g)
        session.commit()


class TestListDocumentsInGroup:
    def test_docs_in_group(self, httpx_mock, session, payloads):
        gid = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                rf"{re.escape(TEST_HOST)}/api/documents/group/{gid}\?.*"
            ),
            json=payloads.list_envelope("documents", [payloads.document()]),
        )
        g = DocumentGroup(**payloads.document_group(id=gid))
        session._bind(g)
        docs = g.list(Document).all()
        assert len(docs) == 1
