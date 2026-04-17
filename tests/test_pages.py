"""Tests for Page (read-only)."""

from __future__ import annotations

import re
from uuid import UUID

import pytest

from ragnerock import Document, Page, ValidationError
from tests.conftest import TEST_HOST


class TestList:
    def test_list_pages_by_document(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/pages/document/{doc_id}\?.*"),
            json=payloads.list_envelope(
                "pages",
                [payloads.page(page_number=1), payloads.page(id="00000000-0000-0000-0000-000000000402", page_number=2)],
            ),
        )
        pages = session.list(Page, document_id=doc_id).all()
        assert [p.page_number for p in pages] == [1, 2]

    def test_list_via_document_shortcut(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/pages/document/{doc_id}\?.*"),
            json=payloads.list_envelope("pages", [payloads.page()]),
        )
        doc = Document(**payloads.document(id=doc_id))
        session._bind(doc)
        pages = doc.list(Page).all()
        assert len(pages) == 1


class TestGet:
    def test_get_page_by_id(self, httpx_mock, session, payloads):
        pid = "00000000-0000-0000-0000-000000000401"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/pages/{pid}",
            json=payloads.page(id=pid),
        )
        p = session.get(Page, id=pid)
        assert p is not None
        assert p.id == UUID(pid)


class TestReadOnly:
    def test_add_raises(self, session, payloads):
        p = Page(page_number=1, content="x")
        with pytest.raises((TypeError, ValidationError)):
            session.add(p)

    def test_update_raises(self, session, payloads):
        p = Page(**payloads.page())
        with pytest.raises((TypeError, ValidationError)):
            session.update(p)

    def test_delete_raises(self, session, payloads):
        p = Page(**payloads.page())
        with pytest.raises((TypeError, ValidationError)):
            session.delete(p)
