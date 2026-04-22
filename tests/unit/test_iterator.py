"""Tests for ``PaginatedIterator`` and pagination behavior end-to-end."""

from __future__ import annotations

import re

from ragnerock import Document, PaginatedIterator
from ragnerock.iterator import PageResult


class TestPaginatedIteratorUnit:
    """Exercise the iterator directly with a stub fetch_page."""

    def test_all_returns_every_item_across_pages(self):
        pages = [
            PageResult(items=[1, 2, 3], total=5),
            PageResult(items=[4, 5], total=5),
            PageResult(items=[], total=5),
        ]
        calls: list[tuple[int, int]] = []

        def fetch(skip: int, limit: int) -> PageResult[int]:
            calls.append((skip, limit))
            return pages.pop(0)

        it: PaginatedIterator[int] = PaginatedIterator(fetch, page_size=3)
        assert it.all() == [1, 2, 3, 4, 5]

    def test_limit_caps_output(self):
        def fetch(skip: int, limit: int) -> PageResult[int]:
            return PageResult(items=list(range(skip, skip + limit)), total=1000)

        it: PaginatedIterator[int] = PaginatedIterator(fetch, page_size=10)
        capped = it.limit(4).all()
        assert capped == [0, 1, 2, 3]

    def test_first_only_fetches_one(self):
        calls: list[tuple[int, int]] = []

        def fetch(skip: int, limit: int) -> PageResult[int]:
            calls.append((skip, limit))
            return PageResult(items=[42], total=100)

        it: PaginatedIterator[int] = PaginatedIterator(fetch)
        assert it.first() == 42
        assert calls == [(0, 1)]

    def test_first_on_empty_returns_none(self):
        def fetch(skip: int, limit: int) -> PageResult[int]:
            return PageResult(items=[], total=0)

        it: PaginatedIterator[int] = PaginatedIterator(fetch)
        assert it.first() is None

    def test_iteration_stops_when_empty_page_returned(self):
        pages = [
            PageResult(items=[1, 2], total=4),
            PageResult(items=[], total=4),  # server returns nothing mid-stream
        ]

        def fetch(skip: int, limit: int) -> PageResult[int]:
            return pages.pop(0)

        it: PaginatedIterator[int] = PaginatedIterator(fetch, page_size=2)
        assert list(it) == [1, 2]


class TestPaginationOverHttp:
    """Walking a ``session.list`` iterator should fetch pages lazily."""

    def test_listing_follows_skip_limit(self, httpx_mock, session, payloads):
        # total=3, page_size=100: one request returns all three; a second call
        # for the next skip yields an empty page and stops iteration.
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/\?.*"),
            json=payloads.list_envelope(
                "documents",
                [payloads.document(), payloads.document(), payloads.document()],
                total=3,
            ),
            is_reusable=True,
        )
        docs = session.list(Document).all()
        assert len(docs) == 3
