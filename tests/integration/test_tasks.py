"""End-to-end Task flows: CRUD, get-by-name."""

from __future__ import annotations

from uuid import uuid4

from ragnerock import ChunkType, Task


def _make_task(name: str) -> Task:
    return Task(
        name=name,
        description="SDK integration test task",
        jsonschema={
            "type": "object",
            "properties": {"total": {"type": "number"}},
            "required": ["total"],
        },
        generation_prompt="Return a JSON object with a 'total' field set to 0.",
        chunk_type=ChunkType.DOCUMENT,
    )


def test_task_crud(session, unique_name):
    task = _make_task(unique_name)
    session.add(task)
    session.commit()
    assert task.id is not None

    try:
        fetched = session.get(Task, id=task.id)
        assert fetched is not None
        assert fetched.name == unique_name

        by_name = session.get(Task, name=unique_name)
        assert by_name is not None
        assert by_name.id == task.id

        names = [t.name for t in session.list(Task)]
        assert unique_name in names

        task.generation_prompt = 'Return {"total": 1}.'
        session.update(task)
        session.commit()
        session.refresh(task)
        assert "1" in task.generation_prompt
    finally:
        session.delete(task)
        session.commit()

    assert session.get(Task, id=task.id) is None


def test_get_by_missing_name_returns_none(session):
    assert session.get(Task, name=f"sdk-itest-no-task-{uuid4().hex[:8]}") is None
