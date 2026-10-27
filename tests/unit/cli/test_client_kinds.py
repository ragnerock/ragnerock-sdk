"""``get`` / ``describe`` for read-only kinds backed by the low-level client."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from typer.testing import CliRunner

from ragnerock.cli import commands
from ragnerock.cli.app import app
from ragnerock.cli.resources import resolve_kind
from ragnerock.session import Session
from tests.unit.conftest import TEST_PROJECT_ID

SKILL_A = "00000000-0000-0000-0000-00000000a001"
SKILL_B = "00000000-0000-0000-0000-00000000a002"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def cli_session(monkeypatch: pytest.MonkeyPatch, session: Session) -> Session:
    """Route the get command through a real (HTTP-mocked) session."""

    @contextmanager
    def fake_open() -> Iterator[Session]:
        yield session

    monkeypatch.setattr(commands.get, "open_session", fake_open)
    return session


def _skill(skill_id: str, name: str) -> dict[str, Any]:
    return {
        "id": skill_id,
        "project_id": str(TEST_PROJECT_ID),
        "name": name,
        "description": "d",
        "body": "b",
        "is_available": True,
        "operator_count": 2,
    }


@pytest.mark.parametrize(
    ("alias", "kind"),
    [
        ("skills", "Skill"),
        ("tool", "Tool"),
        ("ep", "Endpoint"),
        ("nb", "Notebook"),
        ("saved-queries", "SavedQuery"),
        ("artifacts", "WorkflowArtifact"),
        ("ingest-sources", "IngestSource"),
        ("ingest-configs", "IngestConfig"),
        ("ai-configs", "AIConfig"),
        ("dbconfig", "DBConfig"),
        ("blob-configs", "BlobConfig"),
        ("projects", "Project"),
    ],
)
def test_aliases(alias: str, kind: str) -> None:
    spec = resolve_kind(alias)
    assert spec.kind == kind
    assert spec.cls is None and spec.list_fn is not None
    assert not spec.deletable


def test_list_pages_through_every_item(
    runner: CliRunner,
    httpx_mock: Any,
    cli_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ragnerock.cli.resources._PAGE_SIZE", 1)
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r".*/api/skills/\?.*skip=0.*"),
        json={"skills": [_skill(SKILL_A, "tone")], "total": 2, "skip": 0, "limit": 1},
    )
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r".*/api/skills/\?.*skip=1.*"),
        json={"skills": [_skill(SKILL_B, "style")], "total": 2, "skip": 1, "limit": 1},
    )
    result = runner.invoke(app, ["get", "skills", "-o", "name"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout.splitlines() == ["tone", "style"]
    params = httpx_mock.get_requests()[-1].url.params
    assert params["project_id"] == str(TEST_PROJECT_ID)


def test_get_by_name(runner: CliRunner, httpx_mock: Any, cli_session: Session) -> None:
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r".*/api/skills/\?.*"),
        json={
            "skills": [_skill(SKILL_A, "tone"), _skill(SKILL_B, "style")],
            "total": 2,
        },
    )
    result = runner.invoke(app, ["describe", "skill", "style", "-o", "json"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)[0]["id"] == SKILL_B


def test_get_by_id(runner: CliRunner, httpx_mock: Any, cli_session: Session) -> None:
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r".*/api/skills/\?.*"),
        json={"skills": [_skill(SKILL_A, "tone")], "total": 1},
    )
    result = runner.invoke(app, ["get", "skill", SKILL_A, "-o", "name"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == "tone"


def test_missing_name_exits_1(
    runner: CliRunner, httpx_mock: Any, cli_session: Session
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r".*/api/skills/\?.*"),
        json={"skills": [], "total": 0},
    )
    result = runner.invoke(app, ["get", "skill", "nope"])
    assert result.exit_code == 1
    assert "not found" in result.stderr


def test_account_level_kind_table(
    runner: CliRunner, httpx_mock: Any, cli_session: Session
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r".*/api/ai-configs/$"),
        json={
            "configs": [
                {
                    "id": "00000000-0000-0000-0000-00000000c001",
                    "config_name": "anthropic_primary",
                    "provider_type": "anthropic",
                    "model_name": "claude-x",
                    "status": "active",
                }
            ]
        },
    )
    result = runner.invoke(app, ["get", "ai-configs"])
    assert result.exit_code == 0, result.stderr
    assert "anthropic_primary" in result.stdout
    assert "PROVIDER" in result.stdout


def test_workflow_artifacts_follow_cursors(
    runner: CliRunner, httpx_mock: Any, cli_session: Session
) -> None:
    artifact = {"id": "00000000-0000-0000-0000-00000000d001", "file_name": "out.csv"}
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r".*/workflow-artifacts\?limit=50$"),
        json={"artifacts": [artifact], "next_cursor": "c2"},
    )
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r".*/workflow-artifacts\?.*cursor=c2.*"),
        json={
            "artifacts": [
                {
                    **artifact,
                    "id": "00000000-0000-0000-0000-00000000d002",
                    "file_name": "b.csv",
                }
            ],
            "next_cursor": None,
        },
    )
    result = runner.invoke(app, ["get", "artifacts", "-o", "name"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout.splitlines() == ["out.csv", "b.csv"]


def test_filters_are_rejected(runner: CliRunner, cli_session: Session) -> None:
    result = runner.invoke(app, ["get", "skills", "--filter", "x=y"])
    assert result.exit_code == 1
    assert "does not support --filter" in result.stderr


def test_delete_refuses_client_kinds(runner: CliRunner) -> None:
    result = runner.invoke(app, ["delete", "skill", "tone"])
    assert result.exit_code == 1
    assert "does not support name-based delete" in result.stderr
