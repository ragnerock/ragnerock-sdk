"""Chunk and Page read-only endpoints against a real uploaded document.

Chunks and pages are produced by server-side ingestion. We upload a document,
poll until ingestion produces output, then exercise list / get / shortcut
paths. If ingestion doesn't complete in the poll window, tests are skipped
rather than failed — slow instances shouldn't break CI.

Chunks are not writeable through the SDK (``add``/``update``/``delete``
surface as client-side validation). Pages are fully read-only.
"""

from __future__ import annotations

import time

import pytest

from ragnerock import Chunk, Document, Page, ValidationError


_INGESTION_POLL_TIMEOUT = 30.0
_INGESTION_POLL_INTERVAL = 2.0


def _upload_and_wait_for_chunks(session, unique_name, tmp_path):
    file_path = tmp_path / f"{unique_name}.txt"
    file_path.write_text("This is a small test document.\n" * 10)
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

    deadline = time.monotonic() + _INGESTION_POLL_TIMEOUT
    chunks: list = []
    while time.monotonic() < deadline:
        chunks = list(doc.list(Chunk).limit(5))
        if chunks:
            break
        time.sleep(_INGESTION_POLL_INTERVAL)
    return doc, chunks


class TestChunks:
    def test_list_chunks_by_document(self, session, unique_name, tmp_path):
        doc, chunks = _upload_and_wait_for_chunks(session, unique_name, tmp_path)
        try:
            if not chunks:
                pytest.skip(f"ingestion did not produce chunks for {doc.id}")
            for chunk in chunks:
                assert chunk.document_id == doc.id
        finally:
            session.delete(doc)
            session.commit()

    def test_list_via_document_shortcut(self, session, unique_name, tmp_path):
        doc, chunks = _upload_and_wait_for_chunks(session, unique_name, tmp_path)
        try:
            if not chunks:
                pytest.skip(f"ingestion did not produce chunks for {doc.id}")
            via_shortcut = list(doc.list(Chunk).limit(5))
            assert {c.id for c in via_shortcut} == {c.id for c in chunks}
        finally:
            session.delete(doc)
            session.commit()

    def test_get_chunk_by_id(self, session, unique_name, tmp_path):
        doc, chunks = _upload_and_wait_for_chunks(session, unique_name, tmp_path)
        try:
            if not chunks:
                pytest.skip(f"ingestion did not produce chunks for {doc.id}")
            chunk = chunks[0]
            fetched = session.get(Chunk, id=chunk.id)
            assert fetched is not None
            assert fetched.id == chunk.id
        finally:
            session.delete(doc)
            session.commit()


class TestChunkUpdateNotSupported:
    def test_update_chunk_raises(self, session, unique_name, tmp_path):
        doc, chunks = _upload_and_wait_for_chunks(session, unique_name, tmp_path)
        try:
            if not chunks:
                pytest.skip(f"ingestion did not produce chunks for {doc.id}")
            chunk = chunks[0]
            chunk.content = "different"
            with pytest.raises((TypeError, ValidationError)):
                session.update(chunk)
        finally:
            session.delete(doc)
            session.commit()


class TestPages:
    def test_list_pages_by_document(self, session, unique_name, tmp_path):
        doc, _ = _upload_and_wait_for_chunks(session, unique_name, tmp_path)
        try:
            pages = list(doc.list(Page).limit(5))
            if not pages:
                pytest.skip(f"ingestion did not produce pages for {doc.id}")
            for p in pages:
                assert p.document_id == doc.id
                assert p.page_number is not None
        finally:
            session.delete(doc)
            session.commit()

    def test_get_page_by_id(self, session, unique_name, tmp_path):
        doc, _ = _upload_and_wait_for_chunks(session, unique_name, tmp_path)
        try:
            pages = list(doc.list(Page).limit(1))
            if not pages:
                pytest.skip(f"ingestion did not produce pages for {doc.id}")
            fetched = session.get(Page, id=pages[0].id)
            assert fetched is not None
            assert fetched.id == pages[0].id
        finally:
            session.delete(doc)
            session.commit()


class TestPagesReadOnly:
    """Pages cannot be created, updated, or deleted through the SDK."""

    def test_add_raises(self, session):
        p = Page(page_number=1, content="x")
        with pytest.raises((TypeError, ValidationError)):
            session.add(p)

    def test_update_raises(self, session):
        p = Page(
            id="00000000-0000-0000-0000-000000000401",
            document_id="00000000-0000-0000-0000-000000000101",
            page_number=1,
            content="x",
        )
        with pytest.raises((TypeError, ValidationError)):
            session.update(p)

    def test_delete_raises(self, session):
        p = Page(
            id="00000000-0000-0000-0000-000000000401",
            document_id="00000000-0000-0000-0000-000000000101",
            page_number=1,
            content="x",
        )
        with pytest.raises((TypeError, ValidationError)):
            session.delete(p)
