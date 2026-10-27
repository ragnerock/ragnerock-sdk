"""End-to-end tests for ``ragnerock apply`` against a mocked server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from ragnerock.cli.app import app
from tests.unit.conftest import TEST_HOST
from tests.unit.gitops.helpers import agent_doc, secret_doc

APPLY_URL = f"{TEST_HOST}/api/gitops/apply"
KEY_URL = f"{TEST_HOST}/api/gitops/sealing-key"


def _report(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ok": True,
        "dry_run": False,
        "structural_errors": [],
        "results": [
            {"kind": "Secret", "name": "creds", "action": "created"},
            {
                "kind": "Agent",
                "name": "scorer",
                "action": "updated",
                "warnings": ["model binding 'primary' did not resolve"],
            },
        ],
    }
    base.update(overrides)
    return base


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the CLI for token auth against the test host, with no project."""
    for var in (
        "RAGNEROCK_CONNECTION_STRING",
        "RAGNEROCK_PROJECT",
        "RAGNEROCK_EMAIL",
        "RAGNEROCK_PASSWORD",
        "RAGNEROCK_SEALING_PUBLIC_KEY",
        "GITHUB_ACTIONS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("RAGNEROCK_HOST", TEST_HOST)
    monkeypatch.setenv("RAGNEROCK_API_TOKEN", "rgnk_cli")


@pytest.fixture
def manifests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory holding one Secret and one Agent."""
    monkeypatch.setenv("CLI_TEST_SECRET", "from-env-value")
    (tmp_path / "secrets.yaml").write_text(
        yaml.safe_dump(
            secret_doc(
                {
                    "stringData": {"a": "inline-value"},
                    "fromEnv": {"b": "CLI_TEST_SECRET"},
                }
            )
        )
    )
    (tmp_path / "agent.yaml").write_text(yaml.safe_dump(agent_doc()))
    return tmp_path


def test_dry_run_needs_no_config_and_prints_redacted_manifest(
    runner: CliRunner,
    httpx_mock: Any,
    manifests: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAGNEROCK_HOST", raising=False)
    result = runner.invoke(app, ["apply", "-f", str(manifests), "--dry-run"])
    assert result.exit_code == 0, result.stderr
    assert "inline-value" not in result.stdout
    assert "from-env-value" not in result.stdout
    docs = list(yaml.safe_load_all(result.stdout))
    secret = next(d for d in docs if d["kind"] == "Secret")
    assert set(secret["spec"]) == {"encryptedData"}
    assert secret["spec"]["encryptedData"]["b"]["source"] == {
        "type": "fromEnv",
        "env": "CLI_TEST_SECRET",
    }
    assert "Discovered 2 Ragnerock manifest document(s)" in result.stderr
    assert httpx_mock.get_requests() == []


def test_apply_seals_uploads_and_reports(
    runner: CliRunner, httpx_mock: Any, env: None, manifests: Path, sealing_pem: str
) -> None:
    httpx_mock.add_response(method="GET", url=KEY_URL, json={"public_key": sealing_pem})
    httpx_mock.add_response(method="POST", url=APPLY_URL, json=_report())

    result = runner.invoke(app, ["apply", "-f", str(manifests)])

    assert result.exit_code == 0, result.stderr
    assert "Secret  creds  created" in result.stdout
    assert "Agent   scorer  updated" in result.stdout
    assert "OK — 2 changed, 1 warning(s), 2 object(s)" in result.stdout
    assert "model binding 'primary' did not resolve" in result.stderr
    assert "fetched from the instance" in result.stderr
    assert "Pin it with --sealing-public-key" in result.stderr
    assert "Resolved 1 fromEnv secret key(s) locally." in result.stderr
    upload = httpx_mock.get_requests()[-1]
    assert upload.headers["Authorization"] == "Bearer rgnk_cli"
    body = upload.content.decode()
    assert "inline-value" not in body
    assert "from-env-value" not in body
    assert "rgnk-sealed.v1." in body


def test_pinned_key_from_file_skips_the_key_fetch(
    runner: CliRunner,
    httpx_mock: Any,
    env: None,
    manifests: Path,
    sealing_pem: str,
    tmp_path: Path,
) -> None:
    pem_file = tmp_path / "key.pem"
    pem_file.write_text(sealing_pem)
    httpx_mock.add_response(method="POST", url=APPLY_URL, json=_report())

    result = runner.invoke(
        app, ["apply", "-f", str(manifests), "--sealing-public-key", f"@{pem_file}"]
    )

    assert result.exit_code == 0, result.stderr
    assert "(pinned)" in result.stderr
    assert [r.url.path for r in httpx_mock.get_requests()] == ["/api/gitops/apply"]


def test_pinned_key_from_env_var(
    runner: CliRunner,
    httpx_mock: Any,
    env: None,
    manifests: Path,
    sealing_pem: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAGNEROCK_SEALING_PUBLIC_KEY", sealing_pem)
    httpx_mock.add_response(method="POST", url=APPLY_URL, json=_report())
    result = runner.invoke(app, ["apply", "-f", str(manifests)])
    assert result.exit_code == 0, result.stderr
    assert "(pinned)" in result.stderr


def test_plan_reports_without_applying(
    runner: CliRunner, httpx_mock: Any, env: None, tmp_path: Path
) -> None:
    (tmp_path / "agent.yaml").write_text(yaml.safe_dump(agent_doc()))
    httpx_mock.add_response(
        method="POST", url=f"{APPLY_URL}?dry_run=true", json=_report(dry_run=True)
    )
    result = runner.invoke(app, ["apply", "-f", str(tmp_path), "--plan"])
    assert result.exit_code == 0, result.stderr
    assert "OK (plan, nothing was applied)" in result.stdout


def test_failed_apply_exits_1(
    runner: CliRunner, httpx_mock: Any, env: None, tmp_path: Path
) -> None:
    (tmp_path / "agent.yaml").write_text(yaml.safe_dump(agent_doc()))
    httpx_mock.add_response(
        method="POST",
        url=APPLY_URL,
        json=_report(
            ok=False,
            structural_errors=["duplicate Agent 'scorer'"],
            results=[
                {
                    "kind": "Agent",
                    "name": "scorer",
                    "action": "error",
                    "errors": ["schema 'missing' does not exist"],
                }
            ],
        ),
    )
    result = runner.invoke(app, ["apply", "-f", str(tmp_path)])
    assert result.exit_code == 1
    assert "FAILED — 0 changed, 1 object(s)" in result.stdout
    assert "schema 'missing' does not exist" in result.stderr
    assert "duplicate Agent 'scorer'" in result.stderr


def test_json_output(
    runner: CliRunner, httpx_mock: Any, env: None, tmp_path: Path
) -> None:
    (tmp_path / "agent.yaml").write_text(yaml.safe_dump(agent_doc()))
    httpx_mock.add_response(method="POST", url=APPLY_URL, json=_report())
    result = runner.invoke(app, ["apply", "-f", str(tmp_path), "-o", "json"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert [r["action"] for r in payload["results"]] == ["created", "updated"]


def test_stdin_source(runner: CliRunner, httpx_mock: Any, env: None) -> None:
    httpx_mock.add_response(method="POST", url=APPLY_URL, json=_report())
    result = runner.invoke(
        app, ["apply", "-f", "-"], input=yaml.safe_dump(agent_doc("piped"))
    )
    assert result.exit_code == 0, result.stderr
    assert "piped" in httpx_mock.get_requests()[-1].content.decode()


def test_server_error_exits_2(
    runner: CliRunner, httpx_mock: Any, env: None, tmp_path: Path
) -> None:
    (tmp_path / "agent.yaml").write_text(yaml.safe_dump(agent_doc()))
    httpx_mock.add_response(
        method="POST", url=APPLY_URL, status_code=500, json={"detail": "boom"}
    )
    result = runner.invoke(app, ["apply", "-f", str(tmp_path)])
    assert result.exit_code == 2
    assert "boom" in result.stderr


def test_rejected_manifest_exits_1(
    runner: CliRunner, httpx_mock: Any, env: None, tmp_path: Path
) -> None:
    (tmp_path / "agent.yaml").write_text(yaml.safe_dump(agent_doc()))
    httpx_mock.add_response(
        method="POST", url=APPLY_URL, status_code=422, json={"detail": "bad spec"}
    )
    result = runner.invoke(app, ["apply", "-f", str(tmp_path)])
    assert result.exit_code == 1
    assert "bad spec" in result.stderr


def test_instance_without_sealing_key_exits_1(
    runner: CliRunner, httpx_mock: Any, env: None, manifests: Path
) -> None:
    httpx_mock.add_response(method="GET", url=KEY_URL, status_code=404, json={})
    result = runner.invoke(app, ["apply", "-f", str(manifests)])
    assert result.exit_code == 1
    assert "does not have secret sealing configured" in result.stderr
    assert not [r for r in httpx_mock.get_requests() if r.method == "POST"]


def test_no_seal_warns_and_uploads_plaintext(
    runner: CliRunner, httpx_mock: Any, env: None, manifests: Path
) -> None:
    httpx_mock.add_response(method="POST", url=APPLY_URL, json=_report())
    result = runner.invoke(app, ["apply", "-f", str(manifests), "--no-seal"])
    assert result.exit_code == 0, result.stderr
    assert "uploaded as plaintext" in result.stderr
    assert "inline-value" in httpx_mock.get_requests()[-1].content.decode()


def test_github_actions_annotations(
    runner: CliRunner,
    httpx_mock: Any,
    env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    (tmp_path / "agent.yaml").write_text(yaml.safe_dump(agent_doc()))
    httpx_mock.add_response(method="POST", url=APPLY_URL, json=_report())
    result = runner.invoke(app, ["apply", "-f", str(tmp_path)])
    assert result.exit_code == 0, result.stderr
    assert (
        "::warning title=Agent scorer::model binding 'primary' did not resolve"
        in result.stdout
    )


def test_no_manifests_is_a_clean_noop(
    runner: CliRunner, httpx_mock: Any, env: None, tmp_path: Path
) -> None:
    (tmp_path / "ci.yaml").write_text(yaml.safe_dump({"on": "push"}))
    result = runner.invoke(app, ["apply", "-f", str(tmp_path)])
    assert result.exit_code == 0
    assert "nothing to apply" in result.stdout
    assert httpx_mock.get_requests() == []


def test_missing_path_exits_1(runner: CliRunner, env: None) -> None:
    result = runner.invoke(app, ["apply", "-f", "/does/not/exist.yaml"])
    assert result.exit_code == 1
    assert "does not exist" in result.stderr


def test_missing_config_exits_1(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in ("RAGNEROCK_CONNECTION_STRING", "RAGNEROCK_HOST", "RAGNEROCK_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "agent.yaml").write_text(yaml.safe_dump(agent_doc()))
    result = runner.invoke(app, ["apply", "-f", str(tmp_path)])
    assert result.exit_code == 1
    assert "ConfigError" in result.stderr
    assert "RAGNEROCK_PROJECT" not in result.stderr


def test_dry_run_and_plan_are_exclusive(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["apply", "-f", str(tmp_path), "--dry-run", "--plan"])
    assert result.exit_code == 2
