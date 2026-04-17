"""Tests for Chunk list / get / create / delete."""

from __future__ import annotations

import re
from uuid import UUID

from ragnerock import Chunk, ChunkType, Document
from tests.conftest import TEST_HOST


class TestList:
    def test_list_chunks_by_document(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/chunks/\?.*document_ids={doc_id}.*"),
            json=payloads.list_envelope("chunks", [payloads.chunk()]),
        )
        chunks = session.list(Chunk, document_id=doc_id).all()
        assert len(chunks) == 1
        assert chunks[0].chunk_type == ChunkType.PARAGRAPH

    def test_list_via_document_shortcut(self, httpx_mock, session, payloads):
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/chunks/\?.*document_ids={doc_id}.*"),
            json=payloads.list_envelope("chunks", [payloads.chunk()]),
        )
        doc = Document(**payloads.document(id=doc_id))
        session._bind(doc)
        chunks = doc.list(Chunk).all()
        assert len(chunks) == 1


class TestGet:
    def test_get_chunk_by_id(self, httpx_mock, session, payloads):
        cid = "00000000-0000-0000-0000-000000000301"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/chunks/{cid}",
            json=payloads.chunk(id=cid),
        )
        c = session.get(Chunk, id=cid)
        assert c is not None
        assert c.id == UUID(cid)


class TestCreate:
    def test_add_commit_posts_chunk(self, httpx_mock, session, payloads):
        new_id = "00000000-0000-0000-0000-000000000310"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/chunks/",
            json=payloads.chunk(id=new_id),
        )
        c = Chunk(
            document_id="00000000-0000-0000-0000-000000000101",
            start_index=0,
            end_index=10,
            content="hello",
            chunk_type=ChunkType.PARAGRAPH,
        )
        session.add(c)
        session.commit()
        assert c.id == UUID(new_id)


class TestDelete:
    def test_delete_removes(self, httpx_mock, session, payloads):
        cid = "00000000-0000-0000-0000-000000000301"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{TEST_HOST}/api/chunks/{cid}",
            json={},
        )
        c = Chunk(**payloads.chunk(id=cid))
        session.delete(c)
        session.commit()


class TestUpdateNotSupported:
    def test_update_chunk_raises(self, session, payloads):
        import pytest

        from ragnerock import ValidationError

        c = Chunk(**payloads.chunk())
        c.content = "different"
        with pytest.raises((TypeError, ValidationError)):
            session.update(c)
