"""End-to-end CLI tests using Typer's CliRunner with a fake session."""

from __future__ import annotations

import textwrap
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from typer.testing import CliRunner

from ragnerock.cli import app as app_module
from ragnerock.cli import commands
from ragnerock.cli.app import app
from ragnerock.resources import (
    ChunkType,
    Document,
    FileType,
    JobStatus,
    Operator,
    Workflow,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def fake_session(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch every ``open_session`` call site so commands use a fake session."""
    session = MagicMock()
    session.commit = MagicMock()
    session.add = MagicMock()
    session.update = MagicMock()
    session.delete = MagicMock()

    @contextmanager
    def fake_open() -> Iterator[MagicMock]:
        yield session

    for mod in (
        app_module,
        commands.get,
        commands.apply,
        commands.delete,
        commands.run,
        commands.query,
    ):
        if hasattr(mod, "open_session"):
            monkeypatch.setattr(mod, "open_session", fake_open)

    return session


def _operator(name: str = "sentiment") -> Operator:
    return Operator(
        id=UUID("00000000-0000-0000-0000-000000000601"),
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
        name=name,
        description="test",
        jsonschema={"type": "object"},
        generation_prompt="Classify",
        chunk_type=ChunkType.PARAGRAPH,
    )


def _document(name: str = "doc.pdf") -> Document:
    return Document(
        id=UUID("00000000-0000-0000-0000-000000000101"),
        name=name,
        file_type=FileType.PDF,
    )


def _workflow(name: str = "pipeline") -> Workflow:
    return Workflow(
        id=UUID("00000000-0000-0000-0000-000000000701"),
        name=name,
        is_active=True,
    )


# -- version ---------------------------------------------------------------


def test_version_prints_package_version(runner: CliRunner) -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


# -- get -------------------------------------------------------------------


def test_get_list_json(runner: CliRunner, fake_session: MagicMock) -> None:
    iterator = MagicMock()
    iterator.all.return_value = [_operator("a"), _operator("b")]
    fake_session.list.return_value = iterator

    result = runner.invoke(app, ["get", "op", "-o", "json"])
    assert result.exit_code == 0, result.stderr
    assert '"sentiment"' not in result.stdout or '"a"' in result.stdout


def test_get_by_name_yaml(runner: CliRunner, fake_session: MagicMock) -> None:
    fake_session.get.return_value = _operator("sentiment")
    result = runner.invoke(app, ["get", "operator", "sentiment", "-o", "yaml"])
    assert result.exit_code == 0, result.stderr
    assert "kind: Operator" in result.stdout
    assert "name: sentiment" in result.stdout


def test_get_missing_returns_exit_1(runner: CliRunner, fake_session: MagicMock) -> None:
    fake_session.get.return_value = None
    result = runner.invoke(app, ["get", "op", "missing"])
    assert result.exit_code == 1
    assert "not found" in result.stderr


def test_describe_defaults_to_yaml(runner: CliRunner, fake_session: MagicMock) -> None:
    fake_session.get.return_value = _operator("sentiment")
    result = runner.invoke(app, ["describe", "op", "sentiment"])
    assert result.exit_code == 0, result.stderr
    assert "kind: Operator" in result.stdout


def test_describe_accepts_output_flag(
    runner: CliRunner, fake_session: MagicMock
) -> None:
    fake_session.get.return_value = _operator("sentiment")
    result = runner.invoke(app, ["describe", "op", "sentiment", "-o", "json"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip().startswith("[")


def test_unknown_kind_exits_with_error(
    runner: CliRunner, fake_session: MagicMock
) -> None:
    result = runner.invoke(app, ["get", "widget"])
    assert result.exit_code != 0
    assert "Unknown resource kind" in (result.stderr or result.stdout)


# -- apply -----------------------------------------------------------------


def test_apply_from_stdin(runner: CliRunner, fake_session: MagicMock) -> None:
    fake_session.get.return_value = None
    manifest = textwrap.dedent(
        """
        kind: Operator
        metadata: { name: sentiment }
        spec:
          generation_prompt: "Classify"
          chunk_type: PARAGRAPH
          jsonschema: { type: object }
        """
    )
    result = runner.invoke(app, ["apply", "-f", "-"], input=manifest)
    assert result.exit_code == 0, result.stderr
    fake_session.add.assert_called()
    fake_session.commit.assert_called()
    assert "operator/sentiment created" in result.stdout


def test_apply_updates_existing(runner: CliRunner, fake_session: MagicMock) -> None:
    existing = _operator("sentiment")
    fake_session.get.return_value = existing
    manifest = textwrap.dedent(
        """
        kind: Operator
        metadata: { name: sentiment }
        spec:
          generation_prompt: "Updated"
        """
    )
    result = runner.invoke(app, ["apply", "-f", "-"], input=manifest)
    assert result.exit_code == 0, result.stderr
    assert existing.generation_prompt == "Updated"
    fake_session.update.assert_called_with(existing)
    assert "operator/sentiment configured" in result.stdout


def test_apply_missing_file_raises(runner: CliRunner, fake_session: MagicMock) -> None:
    result = runner.invoke(app, ["apply", "-f", "/does/not/exist.yaml"])
    assert result.exit_code == 1
    assert "ManifestError" in result.stderr


# -- delete ----------------------------------------------------------------


def test_delete_by_kind_and_name(runner: CliRunner, fake_session: MagicMock) -> None:
    fake_session.get.return_value = _operator("sentiment")
    result = runner.invoke(app, ["delete", "op", "sentiment"])
    assert result.exit_code == 0, result.stderr
    fake_session.delete.assert_called()
    fake_session.commit.assert_called()
    assert "operator/sentiment deleted" in result.stdout


def test_delete_not_found(runner: CliRunner, fake_session: MagicMock) -> None:
    fake_session.get.return_value = None
    result = runner.invoke(app, ["delete", "op", "missing"])
    assert result.exit_code == 1
    assert "not found" in result.stderr


def test_delete_from_stdin(runner: CliRunner, fake_session: MagicMock) -> None:
    fake_session.get.return_value = _operator("sentiment")
    manifest = textwrap.dedent(
        """
        kind: Operator
        metadata: { name: sentiment }
        spec: {}
        """
    )
    result = runner.invoke(app, ["delete", "-f", "-"], input=manifest)
    assert result.exit_code == 0, result.stderr
    fake_session.delete.assert_called()


# -- run -------------------------------------------------------------------


def test_run_kicks_off_job_no_wait(runner: CliRunner, fake_session: MagicMock) -> None:
    workflow = _workflow()
    doc = _document("report.pdf")

    def get_side_effect(cls: Any, **kwargs: Any) -> Any:
        if cls is Workflow:
            return workflow
        if cls is Document:
            return doc
        return None

    fake_session.get.side_effect = get_side_effect
    job = MagicMock()
    job.id = UUID("00000000-0000-0000-0000-000000000801")
    job.status = JobStatus.NOT_STARTED
    fake_session.run.return_value = job

    result = runner.invoke(app, ["run", "pipeline", "--documents", "report.pdf"])
    assert result.exit_code == 0, result.stderr
    fake_session.run.assert_called_once()
    assert "started" in result.stdout


def test_run_reports_all_missing_documents(
    runner: CliRunner, fake_session: MagicMock
) -> None:
    def get_side_effect(cls: Any, **kwargs: Any) -> Any:
        if cls is Workflow:
            return _workflow()
        return None

    fake_session.get.side_effect = get_side_effect
    result = runner.invoke(app, ["run", "pipeline", "--documents", "a.pdf,b.pdf"])
    assert result.exit_code == 1
    assert "a.pdf" in result.stderr
    assert "b.pdf" in result.stderr


def test_run_wait_exits_nonzero_on_failure(
    runner: CliRunner, fake_session: MagicMock
) -> None:
    workflow = _workflow()
    doc = _document("report.pdf")

    def get_side_effect(cls: Any, **kwargs: Any) -> Any:
        if cls is Workflow:
            return workflow
        if cls is Document:
            return doc
        return None

    fake_session.get.side_effect = get_side_effect
    job = MagicMock()
    job.id = UUID("00000000-0000-0000-0000-000000000801")
    job.status = JobStatus.FAILED
    fake_session.run.return_value = job

    result = runner.invoke(
        app, ["run", "pipeline", "--documents", "report.pdf", "--wait"]
    )
    assert result.exit_code == 2
    assert "FAILED" in result.stdout or "FAILED" in result.stderr
