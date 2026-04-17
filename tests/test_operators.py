"""Tests for Operator CRUD and get-by-name via list filter."""

from __future__ import annotations

import re
from uuid import UUID

from ragnerock import ChunkType, Operator
from tests.conftest import TEST_HOST


class TestList:
    def test_list_operators(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/operators/\?.*"),
            json=payloads.list_envelope("operators", [payloads.operator()]),
        )
        ops = session.list(Operator).all()
        assert len(ops) == 1
        assert ops[0].name == "invoice_extract"


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        oid = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/operators/{oid}",
            json=payloads.operator(id=oid),
        )
        op = session.get(Operator, id=oid)
        assert op is not None
        assert op.id == UUID(oid)

    def test_get_by_name_falls_back_to_list(self, httpx_mock, session, payloads):
        """There's no server-side get-by-name, so the SDK lists and filters."""
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/operators/\?.*"),
            json=payloads.list_envelope(
                "operators",
                [
                    payloads.operator(name="other"),
                    payloads.operator(name="invoice_extract"),
                ],
            ),
            is_reusable=True,
        )
        # Some implementations will then GET the operator by id to fetch the
        # full payload — allow both patterns.
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/operators/[0-9a-f-]+$"),
            json=payloads.operator(name="invoice_extract"),
            is_reusable=True,
        )
        op = session.get(Operator, name="invoice_extract")
        assert op is not None
        assert op.name == "invoice_extract"

    def test_get_by_name_missing_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/operators/\?.*"),
            json=payloads.list_envelope(
                "operators", [payloads.operator(name="other")]
            ),
        )
        assert session.get(Operator, name="nope") is None


class TestCreate:
    def test_add_commit_posts_operator(self, httpx_mock, session, payloads):
        new_id = "00000000-0000-0000-0000-000000000610"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/operators/",
            json=payloads.operator(id=new_id, name="new_op"),
        )
        op = Operator(
            name="new_op",
            jsonschema={"type": "object"},
            generation_prompt="prompt",
            chunk_type=ChunkType.DOCUMENT,
        )
        session.add(op)
        session.commit()
        assert op.id == UUID(new_id)


class TestUpdate:
    def test_update_prompt(self, httpx_mock, session, payloads):
        oid = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="PUT",
            url=f"{TEST_HOST}/api/operators/{oid}",
            json=payloads.operator(id=oid, generation_prompt="updated"),
        )
        op = Operator(**payloads.operator(id=oid))
        op.generation_prompt = "updated"
        session.update(op)
        session.commit()
        assert op.generation_prompt == "updated"


class TestDelete:
    def test_delete_removes(self, httpx_mock, session, payloads):
        oid = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{TEST_HOST}/api/operators/{oid}",
            json={},
        )
        op = Operator(**payloads.operator(id=oid))
        session.delete(op)
        session.commit()
