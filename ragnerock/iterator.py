"""Lazy paginated iterator over skip/limit list endpoints."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Generic, TypeVar

T = TypeVar("T")


class PageResult(Generic[T]):
    """A single page of results returned by a list endpoint.

    Attributes:
        items: Items on this page.
        total: Total item count across every page (server-reported).
    """

    def __init__(self, items: list[T], total: int) -> None:
        self.items = items
        self.total = total


FetchPage = Callable[[int, int], PageResult[T]]


class PaginatedIterator(Generic[T]):
    """Lazy paginated iterator. Fetches pages from the server on demand.

    Iterate to yield items one at a time, or use the helpers:

    - ``.all()`` — eagerly fetch everything and return a list
    - ``.first()`` — fetch and return only the first item (or ``None``)
    - ``.limit(n)`` — return a new iterator capped at ``n`` items
    """

    def __init__(
        self,
        fetch_page: FetchPage[T],
        *,
        page_size: int = 100,
    ) -> None:
        self._fetch_page = fetch_page
        self._page_size = page_size
        self._limit: int | None = None
        self._buffer: list[T] = []
        self._skip = 0
        self._total: int | None = None
        self._yielded = 0
        self._exhausted = False

    def limit(self, n: int) -> PaginatedIterator[T]:
        """Return a new iterator that yields at most ``n`` items."""
        new = PaginatedIterator(self._fetch_page, page_size=self._page_size)
        new._limit = n
        return new

    def all(self) -> list[T]:
        """Eagerly fetch all results and return them as a list."""
        return list(iter(self))

    def first(self) -> T | None:
        """Return the first item, or ``None`` if empty."""
        page = self._fetch_page(0, 1)
        if not page.items:
            return None
        return page.items[0]

    def __iter__(self) -> Iterator[T]:
        return self

    def __next__(self) -> T:
        if self._limit is not None and self._yielded >= self._limit:
            raise StopIteration

        if not self._buffer:
            if self._exhausted:
                raise StopIteration
            if self._total is not None and self._skip >= self._total:
                raise StopIteration

            page = self._fetch_page(self._skip, self._page_size)
            self._total = page.total
            self._buffer = list(page.items)
            self._skip += len(page.items) if page.items else self._page_size

            if not page.items:
                self._exhausted = True
                raise StopIteration

        item = self._buffer.pop(0)
        self._yielded += 1
        return item
