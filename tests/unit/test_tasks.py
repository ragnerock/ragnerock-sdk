"""CRUD tests for ``Task``."""

from __future__ import annotations

import json
import re
from uuid import UUID

import pytest

from ragnerock import ChunkType, Task, TaskKind, ValidationError


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        task_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/tasks/{task_id}$"),
            json=payloads.task(id=task_id),
        )
        task = session.get(Task, id=task_id)
        assert task is not None
        assert task.chunk_type == ChunkType.DOCUMENT

    def test_get_by_name_lists_then_fetches(self, httpx_mock, session, payloads):
        task_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/tasks/\?.*"),
            json=payloads.list_envelope(
                "tasks",
                [payloads.task(id=task_id, name="invoice_extract")],
            ),
        )
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/tasks/{task_id}$"),
            json=payloads.task(id=task_id, name="invoice_extract"),
        )
        task = session.get(Task, name="invoice_extract")
        assert task is not None
        assert task.name == "invoice_extract"

    def test_get_by_missing_name_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/tasks/\?.*"),
            json=payloads.list_envelope("tasks", []),
        )
        assert session.get(Task, name="does_not_exist") is None


class TestList:
    def test_list_returns_tasks(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/tasks/\?.*"),
            json=payloads.list_envelope(
                "tasks",
                [payloads.task(name="a"), payloads.task(name="b")],
            ),
        )
        tasks = session.list(Task).all()
        assert [t.name for t in tasks] == ["a", "b"]


class TestCreate:
    def test_create(self, httpx_mock, session, payloads, base_url):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/tasks/",
            json=payloads.task(id="00000000-0000-0000-0000-0000000000f1"),
        )
        task = Task(
            name="invoice_extract",
            jsonschema={"type": "object"},
            generation_prompt="Extract totals.",
            chunk_type=ChunkType.DOCUMENT,
        )
        session.add(task)
        session.commit()
        assert task.id is not None
        body = json.loads(httpx_mock.get_requests()[-1].content)
        assert body["task_kind"] == "LLM"
        assert body["chunk_type"] == 0
        for removed in (
            "notification_template",
            "change_request_prompt",
            "change_request_signal",
        ):
            assert removed not in body

    def test_create_code_task(self, httpx_mock, session, payloads, base_url):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/tasks/",
            json=payloads.task(
                id="00000000-0000-0000-0000-0000000000f2",
                task_kind="CODE",
                generation_prompt=None,
            ),
        )
        task = Task(
            name="row_total",
            task_kind=TaskKind.CODE,
            jsonschema={"type": "object"},
            code_source="def main(content):\n    return {}",
            chunk_type=ChunkType.ROW,
        )
        session.add(task)
        session.commit()
        body = json.loads(httpx_mock.get_requests()[-1].content)
        assert body["task_kind"] == "CODE"
        assert body["code_source"].startswith("def main")
        assert "generation_prompt" not in body
        assert task.task_kind == TaskKind.CODE

    def test_code_task_requires_code_source(self, session):
        from ragnerock import CommitError

        task = Task(
            name="x",
            task_kind=TaskKind.CODE,
            jsonschema={"type": "object"},
            chunk_type=ChunkType.ROW,
        )
        session.add(task)
        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, ValidationError)

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

        task = Task(**kwargs)
        session.add(task)
        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, ValidationError)


class TestTaskKind:
    def test_members(self):
        assert [k.value for k in TaskKind] == ["LLM", "CODE", "MANUAL", "OUTPUT"]

    def test_removed_fields_are_gone(self):
        fields = Task.model_fields
        for removed in (
            "notification_template",
            "change_request_prompt",
            "change_request_signal",
        ):
            assert removed not in fields


class TestUpdateDelete:
    def test_update(self, httpx_mock, session, payloads, base_url):
        task_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/tasks/{task_id}",
            json=payloads.task(id=task_id, description="new desc"),
        )
        task = Task(**payloads.task(id=task_id))
        task.description = "new desc"
        session.update(task)
        session.commit()
        assert task.description == "new desc"
        body = json.loads(httpx_mock.get_requests()[-1].content)
        assert body["task_kind"] == "LLM"
        assert "change_request_signal" not in body

    def test_delete(self, httpx_mock, session, payloads, base_url):
        task_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{base_url}/api/tasks/{task_id}",
            status_code=204,
            text="",
        )
        task = Task(**payloads.task(id=task_id))
        session.delete(task)
        session.commit()


class TestClientUpdateUnset:
    """``client.tasks.update`` distinguishes omitted from explicit ``None``."""

    def test_omitted_clearable_fields_are_not_sent(
        self, httpx_mock, engine, payloads, base_url
    ):
        task_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/tasks/{task_id}",
            json=payloads.task(),
        )
        engine.client.tasks.update(UUID(task_id), name="renamed")
        body = json.loads(httpx_mock.get_requests()[-1].content)
        assert body == {"name": "renamed"}

    def test_explicit_none_clears(self, httpx_mock, engine, payloads, base_url):
        task_id = "00000000-0000-0000-0000-000000000601"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/tasks/{task_id}",
            json=payloads.task(),
        )
        engine.client.tasks.update(UUID(task_id), ai_config_id=None, batch_size=None)
        body = json.loads(httpx_mock.get_requests()[-1].content)
        assert body == {"ai_config_id": None, "batch_size": None}
