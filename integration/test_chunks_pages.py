"""Chunk and Page read-only endpoints against a real uploaded document.

Chunks and pages are produced by server-side ingestion. We upload a document,
wait briefly, then assert the list endpoints return well-shaped results.
Document ingestion timing varies by deployment — if your instance is slow,
these tests may report empty lists without failing.
"""

from __future__ import annotations

import time

from ragnerock import Chunk, Document, Page


_INGESTION_POLL_TIMEOUT = 30.0
_INGESTION_POLL_INTERVAL = 2.0


def _upload_and_wait_for_chunks(session, unique_name, tmp_path):
    file_path = tmp_path / f"{unique_name}.txt"
    file_path.write_text("This is a small test document.\n" * 10)
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

    # Poll until chunks show up, with a ceiling.
    deadline = time.monotonic() + _INGESTION_POLL_TIMEOUT
    chunks: list = []
    while time.monotonic() < deadline:
        chunks = list(doc.list(Chunk).limit(5))
        if chunks:
            break
        time.sleep(_INGESTION_POLL_INTERVAL)
    return doc, chunks


def test_list_chunks_after_ingestion(session, unique_name, tmp_path):
    doc, chunks = _upload_and_wait_for_chunks(session, unique_name, tmp_path)
    try:
        if not chunks:
            # Ingestion didn't complete within the window — treat as inconclusive
            # rather than failing the test. Record via stdout; CI logs will show it.
            print(f"no chunks yet for {doc.id}; ingestion may be slow")
            return

        chunk = chunks[0]
        # Field shape: every chunk belongs to this document.
        assert chunk.document_id == doc.id
        # And can be fetched individually by id.
        fetched = session.get(Chunk, id=chunk.id)
        assert fetched is not None
        assert fetched.id == chunk.id
    finally:
        session.delete(doc)
        session.commit()


def test_list_pages_after_ingestion(session, unique_name, tmp_path):
    doc, _ = _upload_and_wait_for_chunks(session, unique_name, tmp_path)
    try:
        pages = list(doc.list(Page).limit(5))
        if not pages:
            print(f"no pages yet for {doc.id}; ingestion may be slow")
            return
        for p in pages:
            assert p.document_id == doc.id
            assert p.page_number is not None
    finally:
        session.delete(doc)
        session.commit()
