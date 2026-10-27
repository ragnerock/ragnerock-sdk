"""Tests for the project lookup section."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from ragnerock.client import RagnerockClient
from ragnerock.errors import NotFoundError
from tests.unit.client.conftest import PROJECT_ID, last_params, last_request, url

OWNER_ID = "00000000-0000-4000-8000-0000000000aa"


def _project(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": PROJECT_ID,
        "name": "demo",
        "description": "Demo project",
        "owner_id": OWNER_ID,
        "auto_archive_succeeded_jobs_after_days": 30,
    }
    payload.update(overrides)
    return payload


def _list_item(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": PROJECT_ID,
        "name": "demo",
        "description": None,
        "account_id": "00000000-0000-4000-8000-0000000000bb",
        "owner_id": OWNER_ID,
        "owner_email": "owner@example.com",
    }
    payload.update(overrides)
    return payload


class TestList:
    def test_sends_pagination_and_parses_items(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/projects/?skip=10&limit=5"),
            json={"projects": [_list_item()], "total": 11, "skip": 10, "limit": 5},
        )

        result = client.projects.list(skip=10, limit=5)

        assert last_request(httpx_mock).url.path == "/api/projects/"
        assert last_params(httpx_mock) == {"skip": "10", "limit": "5"}
        assert result.total == 11
        project = result.projects[0]
        assert project.id == uuid.UUID(PROJECT_ID)
        assert project.owner_email == "owner@example.com"
        assert project.description is None

    def test_defaults(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/projects/?skip=0&limit=100"),
            json={"projects": [], "total": 0, "skip": 0, "limit": 100},
        )

        assert client.projects.list().projects == []


class TestGet:
    def test_parses_full_record(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET", url=url(f"/api/projects/{PROJECT_ID}"), json=_project()
        )

        project = client.projects.get(uuid.UUID(PROJECT_ID))

        assert project.name == "demo"
        assert project.description == "Demo project"
        assert project.owner_id == uuid.UUID(OWNER_ID)
        assert project.auto_archive_succeeded_jobs_after_days == 30

    def test_minimal_payload_parses(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/projects/{PROJECT_ID}"),
            json={"id": PROJECT_ID, "name": "demo"},
        )

        project = client.projects.get(uuid.UUID(PROJECT_ID))

        assert project.owner_id is None
        assert project.auto_archive_succeeded_jobs_after_days is None

    def test_missing_project_raises(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/projects/{PROJECT_ID}"),
            status_code=404,
            json={"detail": "Project not found"},
        )

        with pytest.raises(NotFoundError):
            client.projects.get(uuid.UUID(PROJECT_ID))


class TestGetByName:
    def test_returns_matching_projects(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/projects/name/demo"),
            json={"projects": [_list_item()], "total": 1, "skip": 0, "limit": 100},
        )

        result = client.projects.get_by_name("demo")

        assert last_params(httpx_mock) == {}
        assert [p.name for p in result.projects] == ["demo"]
