"""Tests for the skills section (``client.skills``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from ragnerock.client import RagnerockClient
from ragnerock.client.skills import SkillDeleteResponse, SkillList, SkillResponse
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

SKILL_ID = "00000000-0000-0000-0000-0000000000a1"


def _skill(**overrides: Any) -> dict[str, Any]:
    """Build a skill payload as the server returns it."""
    payload: dict[str, Any] = {
        "id": SKILL_ID,
        "project_id": PROJECT_ID,
        "name": "Tax forms",
        "description": "Use when reading W-2 or 1099 forms.",
        "body": "# Tax forms\n\nRead box 1 first.",
        "is_available": True,
        "operator_count": 2,
        "created_at": "2026-09-04T00:00:00Z",
        "updated_at": "2026-09-04T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_list_sends_project_and_paging(httpx_mock, client: RagnerockClient) -> None:
    httpx_mock.add_response(
        method="GET",
        url=url(f"/api/skills/?project_id={PROJECT_ID}&skip=10&limit=5"),
        json={"skills": [_skill()], "total": 11, "skip": 10, "limit": 5},
    )

    result = client.skills.list(UUID(PROJECT_ID), skip=10, limit=5)

    assert last_params(httpx_mock) == {
        "project_id": PROJECT_ID,
        "skip": "10",
        "limit": "5",
    }
    assert isinstance(result, SkillList)
    assert result.total == 11
    assert result.skills[0].name == "Tax forms"
    assert result.skills[0].operator_count == 2


def test_get_parses_the_skill(httpx_mock, client: RagnerockClient) -> None:
    httpx_mock.add_response(
        method="GET", url=url(f"/api/skills/{SKILL_ID}"), json=_skill()
    )

    result = client.skills.get(UUID(SKILL_ID))

    assert isinstance(result, SkillResponse)
    assert result.id == UUID(SKILL_ID)
    assert result.body is not None and result.body.startswith("# Tax forms")
    assert result.created_at is not None


def test_create_sends_every_field(httpx_mock, client: RagnerockClient) -> None:
    httpx_mock.add_response(method="POST", url=url("/api/skills/"), json=_skill())

    result = client.skills.create(
        project_id=UUID(PROJECT_ID),
        name="Tax forms",
        description="Use when reading W-2 or 1099 forms.",
        body="# Tax forms",
        is_available=False,
    )

    assert last_request(httpx_mock).method == "POST"
    assert last_json(httpx_mock) == {
        "project_id": PROJECT_ID,
        "name": "Tax forms",
        "description": "Use when reading W-2 or 1099 forms.",
        "body": "# Tax forms",
        "is_available": False,
    }
    assert result.id == UUID(SKILL_ID)


def test_update_sends_only_supplied_fields(httpx_mock, client: RagnerockClient) -> None:
    """No skill field is clearable, so an explicit null would be refused."""
    httpx_mock.add_response(
        method="PUT", url=url(f"/api/skills/{SKILL_ID}"), json=_skill(name="Renamed")
    )

    result = client.skills.update(UUID(SKILL_ID), name="Renamed")

    assert last_json(httpx_mock) == {"name": "Renamed"}
    assert result.name == "Renamed"


def test_update_sends_a_false_switch(httpx_mock, client: RagnerockClient) -> None:
    httpx_mock.add_response(
        method="PUT", url=url(f"/api/skills/{SKILL_ID}"), json=_skill()
    )

    client.skills.update(UUID(SKILL_ID), is_available=False)

    assert last_json(httpx_mock) == {"is_available": False}


def test_delete_reports_unlinked_agents_and_released_tools(
    httpx_mock, client: RagnerockClient
) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=url(f"/api/skills/{SKILL_ID}"),
        json={"id": SKILL_ID, "operator_count": 3, "released_tool_count": 1},
    )

    result = client.skills.delete(UUID(SKILL_ID))

    assert last_request(httpx_mock).method == "DELETE"
    assert isinstance(result, SkillDeleteResponse)
    assert result.operator_count == 3
    assert result.released_tool_count == 1


def test_unknown_fields_are_kept(httpx_mock, client: RagnerockClient) -> None:
    skill_id = uuid4()
    httpx_mock.add_response(
        method="GET",
        url=url(f"/api/skills/{skill_id}"),
        json=_skill(id=str(skill_id), new_server_field="x"),
    )

    result = client.skills.get(skill_id)

    assert result.model_extra == {"new_server_field": "x"}
