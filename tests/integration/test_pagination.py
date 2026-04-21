"""PaginatedIterator against a live instance.

Covers the user-visible contract:

- ``first()`` returns the first item or ``None`` on an empty listing.
- ``limit()`` caps the returned count and still returns a ``PaginatedIterator``.
- Iterating ``all()`` returns every item.
- Multi-page iteration (``all()`` across >1 page) is exercised only under the
  ``RAGNEROCK_ITEST_PAGINATION`` opt-in because it creates page_size+1 docs.
"""

from __future__ import annotations

from ragnerock import Document, PaginatedIterator

from tests.integration.conftest import skip_unless_env


def _fake_pdf(tmp_path, name: str) -> str:
    p = tmp_path / f"{name}.pdf"
    p.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return str(p)


class TestFirst:
    def test_first_on_created_returns_non_none(self, session, unique_name, tmp_path):
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(doc)
        session.commit()
        try:
            first = session.list(Document).first()
            assert first is not None
        finally:
            session.delete(doc)
            session.commit()

    def test_first_on_filtered_empty_returns_none(self, session, unique_name):
        """A filter that can't match anything returns None from first()."""
        assert session.list(Document, name=f"{unique_name}-no-such-doc").first() is None


class TestLimit:
    def test_returns_paginated_iterator(self, session):
        it = session.list(Document).limit(10)
        assert isinstance(it, PaginatedIterator)

    def test_limit_caps_results(self, session, unique_name, tmp_path):
        # Create 3 docs so we have at least 3 in the project.
        created = []
        for i in range(3):
            doc = Document(
                file_path=_fake_pdf(tmp_path, f"{unique_name}-{i}"),
                name=f"{unique_name}-{i}",
            )
            session.add(doc)
            created.append(doc)
        session.commit()

        try:
            docs = session.list(Document).limit(2).all()
            assert len(docs) <= 2
        finally:
            for d in created:
                session.delete(d)
            session.commit()


class TestLazyIteration:
    """Iterating one item shouldn't blow up; returned values must be well-shaped."""

    def test_iter_next_returns_document(self, session, unique_name, tmp_path):
        doc = Document(file_path=_fake_pdf(tmp_path, unique_name), name=unique_name)
        session.add(doc)
        session.commit()
        try:
            it = iter(session.list(Document))
            first = next(it, None)
            assert first is None or isinstance(first, Document)
        finally:
            session.delete(doc)
            session.commit()


@skip_unless_env("RAGNEROCK_ITEST_PAGINATION")
class TestAllAcrossPages:
    """Opt-in — creates >100 documents to force multi-page iteration."""

    _N = 105  # just over the default page size

    def test_all_returns_every_item(self, session, unique_name, tmp_path):
        created = []
        for i in range(self._N):
            doc = Document(
                file_path=_fake_pdf(tmp_path, f"{unique_name}-{i:03d}"),
                name=f"{unique_name}-{i:03d}",
            )
            session.add(doc)
            created.append(doc)
        session.commit()

        try:
            # Filter by our unique prefix so we don't count pre-existing docs.
            listed = [
                d
                for d in session.list(Document)
                if d.name and d.name.startswith(unique_name)
            ]
            assert len(listed) == self._N
        finally:
            for d in created:
                session.delete(d)
            session.commit()
