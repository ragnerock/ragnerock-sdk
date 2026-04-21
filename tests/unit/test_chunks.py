"""CRUD tests for ``Chunk`` and its relationship to ``Document``."""

from __future__ import annotations

import re

import pytest

from ragnerock import Chunk, ChunkType, Document, ValidationError


class TestList:
    def test_list_requires_document_id(self, session):
        with pytest.raises(ValidationError):
            session.list(Chunk).all()

    def test_list_returns_chunks(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/chunks/\?.*"),
            json=payloads.list_envelope(
                "chunks",
                [payloads.chunk(start_index=0, end_index=5)],
            ),
        )
        chunks = session.list(
            Chunk, document_id="00000000-0000-0000-0000-000000000101"
        ).all()
        assert len(chunks) == 1
        assert chunks[0].chunk_type == ChunkType.PARAGRAPH


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        chunk_id = "00000000-0000-0000-0000-000000000301"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/chunks/{chunk_id}$"),
            json=payloads.chunk(id=chunk_id),
        )
        chunk = session.get(Chunk, id=chunk_id)
        assert chunk is not None
        assert chunk.content == "Hello world."

    def test_get_missing_returns_none(self, httpx_mock, session):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/chunks/.*"),
            status_code=404,
            json={"detail": {"message": "no"}},
        )
        assert session.get(Chunk, id="00000000-0000-0000-0000-000000000999") is None

    def test_get_by_name_raises(self, session):
        with pytest.raises(ValidationError):
            session.get(Chunk, name="x")


class TestCreate:
    def test_create(self, httpx_mock, session, payloads, base_url):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/chunks/",
            json=payloads.chunk(
                id="00000000-0000-0000-0000-00000000cccc",
                start_index=0,
                end_index=5,
            ),
        )
        chunk = Chunk(
            document_id="00000000-0000-0000-0000-000000000101",
            content="hello",
            start_index=0,
            end_index=5,
        )
        session.add(chunk)
        session.commit()
        assert chunk.id is not None

    def test_create_requires_document_id(self, session):
        from ragnerock import CommitError

        chunk = Chunk(content="x", start_index=0, end_index=1)
        session.add(chunk)
        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, ValidationError)

    def test_create_requires_indices(self, session):
        from ragnerock import CommitError

        chunk = Chunk(
            document_id="00000000-0000-0000-0000-000000000101",
            content="x",
        )
        session.add(chunk)
        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, ValidationError)


class TestDelete:
    def test_delete(self, httpx_mock, session, payloads, base_url):
        chunk_id = "00000000-0000-0000-0000-000000000301"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{base_url}/api/chunks/{chunk_id}",
            status_code=204,
            text="",
        )
        chunk = Chunk(**payloads.chunk(id=chunk_id))
        session.delete(chunk)
        session.commit()

    def test_update_unsupported(self, session, payloads):
        chunk = Chunk(**payloads.chunk())
        with pytest.raises((TypeError, ValidationError)):
            session.update(chunk)


class TestDocumentChunkNavigation:
    def test_document_list_chunks(self, httpx_mock, session, payloads):
        doc = Document(**payloads.document())
        session._bind(doc)
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/chunks/\?.*"),
            json=payloads.list_envelope("chunks", [payloads.chunk()]),
        )
        chunks = doc.list(Chunk).all()
        assert len(chunks) == 1
