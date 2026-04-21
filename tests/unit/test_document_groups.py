"""CRUD tests for ``DocumentGroup`` and its document navigation."""

from __future__ import annotations

import re

import pytest

from ragnerock import Document, DocumentGroup, ValidationError


class TestCrud:
    def test_create(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=re.compile(r".*/api/projects/.*/groups/$"),
            json=payloads.document_group(name="Q1"),
        )
        group = DocumentGroup(name="Q1")
        session.add(group)
        session.commit()
        assert group.id is not None

    def test_create_requires_name(self, session):
        """Missing name is raised from ``_create_resource`` inside ``commit``,
        so it surfaces wrapped in a ``CommitError``."""
        from ragnerock import CommitError

        group = DocumentGroup()
        session.add(group)
        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, ValidationError)

    def test_get_by_id(self, httpx_mock, session, payloads, base_url, project_id):
        group_id = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/api/projects/{project_id}/groups/{group_id}",
            json=payloads.document_group(id=group_id),
        )
        group = session.get(DocumentGroup, id=group_id)
        assert group is not None
        assert group.name == "Q1 contracts"

    def test_get_by_name_raises(self, session):
        with pytest.raises(ValidationError):
            session.get(DocumentGroup, name="whatever")

    def test_update_sends_new_name(
        self, httpx_mock, session, payloads, base_url, project_id
    ):
        group_id = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/projects/{project_id}/groups/{group_id}",
            json=payloads.document_group(id=group_id, name="Q2"),
        )
        group = DocumentGroup(**payloads.document_group(id=group_id))
        group.name = "Q2"
        session.update(group)
        session.commit()
        assert group.name == "Q2"

    def test_delete(self, httpx_mock, session, payloads, base_url, project_id):
        group_id = "00000000-0000-0000-0000-000000000201"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{base_url}/api/projects/{project_id}/groups/{group_id}",
            status_code=204,
            text="",
        )
        group = DocumentGroup(**payloads.document_group(id=group_id))
        session.delete(group)
        session.commit()


class TestList:
    def test_list_returns_groups(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/projects/.*/groups/\?.*"),
            json=payloads.list_envelope(
                "groups",
                [
                    payloads.document_group(name="A"),
                    payloads.document_group(name="B"),
                ],
            ),
        )
        groups = session.list(DocumentGroup).all()
        assert [g.name for g in groups] == ["A", "B"]


class TestNavigation:
    def test_list_documents_in_group(self, httpx_mock, session, payloads):
        group = DocumentGroup(**payloads.document_group())
        session._bind(group)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/documents/group/{group.id}.*"),
            json=payloads.list_envelope("documents", [payloads.document()]),
        )
        docs = group.list(Document).all()
        assert len(docs) == 1
