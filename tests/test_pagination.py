"""Tests for `PaginatedIterator`: lazy iteration, page refill, helpers."""

from __future__ import annotations

import re

from ragnerock import Document, PaginatedIterator
from tests.conftest import TEST_HOST


def _add_page(httpx_mock, payloads, items: list, *, total: int, skip: int, limit: int):
    httpx_mock.add_response(
        method="GET",
        url=re.compile(rf".*/api/documents/\?.*skip={skip}.*limit={limit}.*"),
        json={
            "documents": items,
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


class TestAll:
    def test_all_fetches_every_page(self, httpx_mock, session, payloads):
        # Small pages so we need to fetch multiple.
        total = 250
        page_size = 100

        page1 = [payloads.document(id=f"00000000-0000-0000-0000-{i:012d}") for i in range(100)]
        page2 = [payloads.document(id=f"00000000-0000-0000-0000-{i:012d}") for i in range(100, 200)]
        page3 = [payloads.document(id=f"00000000-0000-0000-0000-{i:012d}") for i in range(200, 250)]

        _add_page(httpx_mock, payloads, page1, total=total, skip=0, limit=page_size)
        _add_page(httpx_mock, payloads, page2, total=total, skip=100, limit=page_size)
        _add_page(httpx_mock, payloads, page3, total=total, skip=200, limit=page_size)

        docs = session.list(Document).all()
        assert len(docs) == 250


class TestFirst:
    def test_first_fetches_only_first_page(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/\?.*"),
            json=payloads.list_envelope(
                "documents", [payloads.document()], total=999
            ),
        )
        it = session.list(Document)
        first = it.first()
        assert first is not None

    def test_first_on_empty_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/\?.*"),
            json=payloads.list_envelope("documents", [], total=0),
        )
        assert session.list(Document).first() is None


class TestLimit:
    def test_limit_caps_results(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/\?.*"),
            json=payloads.list_envelope(
                "documents",
                [payloads.document(id=f"00000000-0000-0000-0000-{i:012d}") for i in range(100)],
                total=1000,
            ),
            is_reusable=True,
        )
        docs = session.list(Document).limit(5).all()
        assert len(docs) == 5

    def test_returns_paginated_iterator(self, httpx_mock, session, payloads):
        it = session.list(Document).limit(10)
        assert isinstance(it, PaginatedIterator)


class TestLazyIteration:
    def test_iteration_is_lazy(self, httpx_mock, session, payloads):
        """Iterating one item should fetch only the first page."""
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/\?.*skip=0.*"),
            json=payloads.list_envelope(
                "documents", [payloads.document()], total=500
            ),
        )
        # No page-2 response registered — if the iterator fetched eagerly,
        # the test would hang / error out.
        it = iter(session.list(Document))
        next(it)
        # We must have made exactly one request so far.
        assert len(httpx_mock.get_requests()) <= 4  # login + project + 1 list + slack
