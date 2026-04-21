"""End-to-end Operator flows: CRUD, get-by-name."""

from __future__ import annotations

from uuid import uuid4

from ragnerock import ChunkType, Operator


def _make_operator(name: str) -> Operator:
    return Operator(
        name=name,
        description="SDK integration test operator",
        jsonschema={
            "type": "object",
            "properties": {"total": {"type": "number"}},
            "required": ["total"],
        },
        generation_prompt="Return a JSON object with a 'total' field set to 0.",
        chunk_type=ChunkType.DOCUMENT,
    )


def test_operator_crud(session, unique_name):
    op = _make_operator(unique_name)
    session.add(op)
    session.commit()
    assert op.id is not None

    try:
        fetched = session.get(Operator, id=op.id)
        assert fetched is not None
        assert fetched.name == unique_name

        by_name = session.get(Operator, name=unique_name)
        assert by_name is not None
        assert by_name.id == op.id

        names = [o.name for o in session.list(Operator)]
        assert unique_name in names

        op.generation_prompt = 'Return {"total": 1}.'
        session.update(op)
        session.commit()
        session.refresh(op)
        assert "1" in op.generation_prompt
    finally:
        session.delete(op)
        session.commit()

    assert session.get(Operator, id=op.id) is None


def test_get_by_missing_name_returns_none(session):
    assert session.get(Operator, name=f"sdk-itest-no-op-{uuid4().hex[:8]}") is None
