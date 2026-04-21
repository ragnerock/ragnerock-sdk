"""Tests for ``Page`` (read-only resource)."""

from __future__ import annotations

import re

import pytest

from ragnerock import Document, Page, ValidationError


class TestReadOnly:
    """Pages are exposed read-only; write ops must be rejected locally."""

    def test_add_page_raises(self, session):
        with pytest.raises((TypeError, ValidationError)):
            session.add(Page(page_number=1))

    def test_update_page_raises(self, session, payloads):
        p = Page(**payloads.page())
        with pytest.raises((TypeError, ValidationError)):
            session.update(p)

    def test_delete_page_raises(self, session, payloads):
        p = Page(**payloads.page())
        with pytest.raises((TypeError, ValidationError)):
            session.delete(p)


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        page_id = "00000000-0000-0000-0000-000000000401"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/pages/{page_id}$"),
            json=payloads.page(id=page_id, page_number=3),
        )
        page = session.get(Page, id=page_id)
        assert page is not None
        assert page.page_number == 3

    def test_get_missing_returns_none(self, httpx_mock, session):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/pages/.*"),
            status_code=404,
            json={"detail": {"message": "no"}},
        )
        assert session.get(Page, id="00000000-0000-0000-0000-000000000999") is None

    def test_get_by_name_raises(self, session):
        with pytest.raises(ValidationError):
            session.get(Page, name="whatever")


class TestList:
    def test_list_requires_document_id(self, session):
        with pytest.raises(ValidationError):
            session.list(Page).all()

    def test_list_returns_pages_in_order(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/pages/document/.*"),
            json=payloads.list_envelope(
                "pages",
                [payloads.page(page_number=1), payloads.page(page_number=2)],
            ),
        )
        pages = session.list(
            Page, document_id="00000000-0000-0000-0000-000000000101"
        ).all()
        assert [p.page_number for p in pages] == [1, 2]

    def test_document_list_pages(self, httpx_mock, session, payloads):
        doc = Document(**payloads.document())
        session._bind(doc)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/pages/document/.*"),
            json=payloads.list_envelope("pages", [payloads.page()]),
        )
        pages = doc.list(Page).all()
        assert len(pages) == 1
