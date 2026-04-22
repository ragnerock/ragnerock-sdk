"""CRUD tests for ``Operator``."""

from __future__ import annotations

import re

import pytest

from ragnerock import ChunkType, Operator, ValidationError


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        op_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/operators/{op_id}$"),
            json=payloads.operator(id=op_id),
        )
        op = session.get(Operator, id=op_id)
        assert op is not None
        assert op.chunk_type == ChunkType.DOCUMENT

    def test_get_by_name_lists_then_fetches(self, httpx_mock, session, payloads):
        op_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/operators/\?.*"),
            json=payloads.list_envelope(
                "operators",
                [payloads.operator(id=op_id, name="invoice_extract")],
            ),
        )
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/operators/{op_id}$"),
            json=payloads.operator(id=op_id, name="invoice_extract"),
        )
        op = session.get(Operator, name="invoice_extract")
        assert op is not None
        assert op.name == "invoice_extract"

    def test_get_by_missing_name_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/operators/\?.*"),
            json=payloads.list_envelope("operators", []),
        )
        assert session.get(Operator, name="does_not_exist") is None


class TestList:
    def test_list_returns_operators(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/operators/\?.*"),
            json=payloads.list_envelope(
                "operators",
                [payloads.operator(name="a"), payloads.operator(name="b")],
            ),
        )
        ops = session.list(Operator).all()
        assert [o.name for o in ops] == ["a", "b"]


class TestCreate:
    def test_create(self, httpx_mock, session, payloads, base_url):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/operators/",
            json=payloads.operator(id="00000000-0000-0000-0000-0000000000f1"),
        )
        op = Operator(
            name="invoice_extract",
            jsonschema={"type": "object"},
            generation_prompt="Extract totals.",
            chunk_type=ChunkType.DOCUMENT,
        )
        session.add(op)
        session.commit()
        assert op.id is not None

    @pytest.mark.parametrize(
        "kwargs",
        [
            {
                "jsonschema": {"type": "object"},
                "generation_prompt": "p",
                "chunk_type": ChunkType.DOCUMENT,
            },
            {"name": "x", "generation_prompt": "p", "chunk_type": ChunkType.DOCUMENT},
            {
                "name": "x",
                "jsonschema": {"type": "object"},
                "chunk_type": ChunkType.DOCUMENT,
            },
            {"name": "x", "jsonschema": {"type": "object"}, "generation_prompt": "p"},
        ],
    )
    def test_create_missing_required_field_raises(self, session, kwargs):
        from ragnerock import CommitError

        op = Operator(**kwargs)
        session.add(op)
        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, ValidationError)


class TestUpdateDelete:
    def test_update(self, httpx_mock, session, payloads, base_url):
        op_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/operators/{op_id}",
            json=payloads.operator(id=op_id, description="new desc"),
        )
        op = Operator(**payloads.operator(id=op_id))
        op.description = "new desc"
        session.update(op)
        session.commit()
        assert op.description == "new desc"

    def test_delete(self, httpx_mock, session, payloads, base_url):
        op_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{base_url}/api/operators/{op_id}",
            status_code=204,
            text="",
        )
        op = Operator(**payloads.operator(id=op_id))
        session.delete(op)
        session.commit()
