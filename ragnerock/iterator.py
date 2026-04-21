"""Lazy paginated iterator over skip/limit list endpoints."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Generic, TypeVar

T = TypeVar("T")


class PageResult(Generic[T]):
    """A single page of results returned by a list endpoint.

    Attributes:
        items (list[T]): Items on this page.
        total (int): Total item count across every page, as reported by the
            server.
    """

    def __init__(self, items: list[T], total: int) -> None:
        """Initialize a page result.

        Args:
            items (list[T]): Items on this page.
            total (int): Server-reported total count across every page.
        """
        self.items = items
        self.total = total


FetchPage = Callable[[int, int], PageResult[T]]


class PaginatedIterator(Generic[T]):
    """Lazy paginated iterator. Fetches pages from the server on demand.

    Iterate to yield items one at a time, or use the helpers:

    - :meth:`all` -- eagerly fetch everything and return a list
    - :meth:`first` -- fetch and return only the first item (or ``None``)
    - :meth:`limit` -- return a new iterator capped at ``n`` items

    Iteration pulls pages lazily from the underlying ``fetch_page`` callable
    and yields items one at a time in server order.

    Example::

        for item in session.documents.list():
            print(item)

        first = session.documents.list().first()
        top10 = session.documents.list().limit(10).all()
    """

    def __init__(
        self,
        fetch_page: FetchPage[T],
        *,
        page_size: int = 100,
    ) -> None:
        """Initialize the iterator.

        Args:
            fetch_page (FetchPage[T]): Callable taking ``(skip, limit)`` and
                returning a :class:`PageResult`. Called on demand as the
                caller consumes items.
            page_size (int): Number of items to request per page.
        """
        self._fetch_page = fetch_page
        self._page_size = page_size
        self._limit: int | None = None
        self._buffer: list[T] = []
        self._skip = 0
        self._total: int | None = None
        self._yielded = 0
        self._exhausted = False

    def limit(self, n: int) -> PaginatedIterator[T]:
        """Return a fresh iterator that yields at most ``n`` items.

        Args:
            n (int): Maximum number of items the new iterator will yield.

        Returns:
            PaginatedIterator[T]: A new iterator over the same pages, capped
            at ``n`` items. The original iterator is unaffected.
        """
        new = PaginatedIterator(self._fetch_page, page_size=self._page_size)
        new._limit = n
        return new

    def all(self) -> list[T]:
        """Fetch every page and return all items as a list.

        Prefer iteration for large result sets — this materializes everything
        in memory.

        Returns:
            list[T]: Every item across every page, in server order.
        """
        return list(iter(self))

    def first(self) -> T | None:
        """Fetch a single-item page and return its first item.

        Returns:
            T | None: The first item, or ``None`` if the result set is empty.
        """
        page = self._fetch_page(0, 1)
        if not page.items:
            return None
        return page.items[0]

    def __iter__(self) -> Iterator[T]:
        """Return ``self`` so the iterator can be used in ``for`` loops.

        Returns:
            Iterator[T]: This iterator instance.
        """
        return self

    def __next__(self) -> T:
        """Yield the next item, fetching another page from the server if the
        local buffer is empty.

        Returns:
            T: The next item in server order.

        Raises:
            StopIteration: When the configured ``limit`` is reached, the
                server-reported total is exhausted, or a fetched page comes
                back empty.
        """
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
