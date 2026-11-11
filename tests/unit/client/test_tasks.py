"""Tests for the tasks section (``client.tasks``)."""

from __future__ import annotations

import inspect
from typing import Any
from uuid import UUID

import pytest

from ragnerock.client import RagnerockClient
from ragnerock.client.tasks import _TasksSection
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

TASK_ID = UUID("00000000-0000-0000-0000-000000000601")
SCHEMA_ID = UUID("00000000-0000-0000-0000-000000000611")
TASK = f"/api/tasks/{TASK_ID}"


def _task(**overrides: Any) -> dict[str, Any]:
    """A task response body."""
    body: dict[str, Any] = {
        "id": str(TASK_ID),
        "project_id": PROJECT_ID,
        "name": "scout",
        "description": None,
        "jsonschema": {"type": "object"},
        "generation_prompt": "Find the vendor.",
        "chunk_type": 0,
        "batch_size": None,
        "multi_annotation": False,
        "created_at": "2026-10-19T00:00:00Z",
        "updated_at": "2026-10-19T00:00:00Z",
        "task_kind": "LLM",
        "agent_count": 2,
        "warnings": [],
    }
    body.update(overrides)
    return body


def test_list_sends_scope_and_paging(httpx_mock: Any, client: RagnerockClient) -> None:
    httpx_mock.add_response(
        method="GET",
        url=url(
            f"/api/tasks/?project_ids={PROJECT_ID}&active_only=false&skip=0&limit=10"
        ),
        json={"tasks": [_task()], "total": 1, "skip": 0, "limit": 10},
    )

    page = client.tasks.list(project_ids=PROJECT_ID, active_only=False, limit=10)

    assert last_params(httpx_mock)["project_ids"] == PROJECT_ID
    assert page.total == 1
    assert page.tasks[0].id == TASK_ID
    assert page.tasks[0].task_kind == "LLM"


def test_get_parses_the_task(httpx_mock: Any, client: RagnerockClient) -> None:
    httpx_mock.add_response(method="GET", url=url(TASK), json=_task())

    task = client.tasks.get(TASK_ID)

    assert task.name == "scout"
    assert task.task_kind == "LLM"
    assert task.generation_prompt == "Find the vendor."


def test_create_sends_the_kind_and_payload(
    httpx_mock: Any, client: RagnerockClient
) -> None:
    httpx_mock.add_response(method="POST", url=url("/api/tasks/"), json=_task())

    client.tasks.create(
        project_id=UUID(PROJECT_ID),
        name="scout",
        chunk_type=0,
        task_kind="CODE",
        output_schema_id=SCHEMA_ID,
        code_source="def main(content):\n    return {}\n",
        code_timeout_seconds=30,
    )

    assert last_json(httpx_mock) == {
        "project_id": PROJECT_ID,
        "name": "scout",
        "task_kind": "CODE",
        "chunk_type": 0,
        "output_schema_id": str(SCHEMA_ID),
        "multi_annotation": False,
        "code_source": "def main(content):\n    return {}\n",
        "network_access": False,
        "code_timeout_seconds": 30,
    }


def test_update_clears_unset_fields_only_when_passed(
    httpx_mock: Any, client: RagnerockClient
) -> None:
    httpx_mock.add_response(method="PUT", url=url(TASK), json=_task())

    client.tasks.update(TASK_ID, name="scout2", model_name=None)

    assert last_json(httpx_mock) == {"name": "scout2", "model_name": None}


@pytest.mark.parametrize("method", ["create", "update"])
@pytest.mark.parametrize(
    "removed",
    ["notification_template", "change_request_prompt", "change_request_signal"],
)
def test_removed_fields_are_not_accepted(method: str, removed: str) -> None:
    """The server dropped these with the MESSAGE and CHANGE_REQUEST kinds."""
    assert removed not in inspect.signature(getattr(_TasksSection, method)).parameters


def test_delete(httpx_mock: Any, client: RagnerockClient) -> None:
    httpx_mock.add_response(method="DELETE", url=url(TASK), status_code=204)

    assert client.tasks.delete(TASK_ID) is None
    assert last_request(httpx_mock).method == "DELETE"
