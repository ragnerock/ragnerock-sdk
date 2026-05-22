"""Tests for env-var-based CLI configuration."""

from __future__ import annotations

import pytest

from ragnerock.cli.config import ConfigError, build_engine


def test_connection_string_wins_over_split_vars() -> None:
    env = {
        "RAGNEROCK_CONNECTION_STRING": "ragnerock://u@x.com:pw@api.test.local/proj",
        "RAGNEROCK_HOST": "ignored",
        "RAGNEROCK_EMAIL": "ignored@example.com",
        "RAGNEROCK_PASSWORD": "ignored",
        "RAGNEROCK_PROJECT": "ignored",
    }
    engine = build_engine(env=env)
    assert engine.project_name == "proj"
    assert "api.test.local" in engine.host


def test_split_vars_assemble_connection_string() -> None:
    env = {
        "RAGNEROCK_HOST": "https://api.test.local",
        "RAGNEROCK_EMAIL": "alice@example.com",
        "RAGNEROCK_PASSWORD": "hunter2",
        "RAGNEROCK_PROJECT": "my-project",
    }
    engine = build_engine(env=env)
    assert engine.project_name == "my-project"
    assert engine.host == "https://api.test.local"


def test_split_vars_bare_host_defaults_to_https() -> None:
    env = {
        "RAGNEROCK_HOST": "api.test.local",
        "RAGNEROCK_EMAIL": "alice@example.com",
        "RAGNEROCK_PASSWORD": "hunter2",
        "RAGNEROCK_PROJECT": "my-project",
    }
    engine = build_engine(env=env)
    assert engine.host == "https://api.test.local"


def test_missing_env_vars_raises_with_list_of_missing() -> None:
    env = {"RAGNEROCK_HOST": "api.test.local"}
    with pytest.raises(ConfigError) as excinfo:
        build_engine(env=env)
    msg = str(excinfo.value)
    assert "RAGNEROCK_EMAIL" in msg
    assert "RAGNEROCK_PASSWORD" in msg
    assert "RAGNEROCK_PROJECT" in msg
    assert "RAGNEROCK_HOST" not in msg.split("Missing: ")[-1]


def test_empty_env_raises() -> None:
    with pytest.raises(ConfigError):
        build_engine(env={})


def test_malformed_connection_string_raises() -> None:
    env = {"RAGNEROCK_CONNECTION_STRING": "not-a-valid-dsn"}
    with pytest.raises(ConfigError) as excinfo:
        build_engine(env=env)
    assert "malformed" in str(excinfo.value)


def test_email_with_at_sign_preserved() -> None:
    env = {
        "RAGNEROCK_HOST": "api.test.local",
        "RAGNEROCK_EMAIL": "alice@example.com",
        "RAGNEROCK_PASSWORD": "hunter2",
        "RAGNEROCK_PROJECT": "proj",
    }
    engine = build_engine(env=env)
    assert engine._email == "alice@example.com"
    assert engine._password == "hunter2"


def test_api_token_split_vars_builds_engine() -> None:
    env = {
        "RAGNEROCK_HOST": "api.test.local",
        "RAGNEROCK_PROJECT": "proj",
        "RAGNEROCK_API_TOKEN": "tok-abc-123",
    }
    engine = build_engine(env=env)
    assert engine.project_name == "proj"
    assert engine.host == "https://api.test.local"
    assert engine._client.auth_token == "tok-abc-123"
    assert engine._email is None
    assert engine._password is None


def test_api_token_with_special_chars_round_trips() -> None:
    env = {
        "RAGNEROCK_HOST": "api.test.local",
        "RAGNEROCK_PROJECT": "proj",
        "RAGNEROCK_API_TOKEN": "a+b/c=d",
    }
    engine = build_engine(env=env)
    assert engine._client.auth_token == "a+b/c=d"


def test_connection_string_with_token_dsn() -> None:
    env = {
        "RAGNEROCK_CONNECTION_STRING": "ragnerock://token:abc123@api.test.local/proj",
    }
    engine = build_engine(env=env)
    assert engine.project_name == "proj"
    assert engine._client.auth_token == "abc123"


def test_missing_password_and_token_raises_config_error() -> None:
    env = {
        "RAGNEROCK_HOST": "api.test.local",
        "RAGNEROCK_EMAIL": "alice@example.com",
        "RAGNEROCK_PROJECT": "proj",
    }
    with pytest.raises(ConfigError) as excinfo:
        build_engine(env=env)
    msg = str(excinfo.value)
    assert "RAGNEROCK_PASSWORD" in msg
    assert "RAGNEROCK_API_TOKEN" in msg


def test_api_token_env_var_whitespace_stripped() -> None:
    env = {
        "RAGNEROCK_HOST": "api.test.local",
        "RAGNEROCK_PROJECT": "proj",
        "RAGNEROCK_API_TOKEN": "  tok-with-padding  \n",
    }
    engine = build_engine(env=env)
    assert engine._client.auth_token == "tok-with-padding"


def test_token_takes_priority_over_email_password_in_split_vars() -> None:
    env = {
        "RAGNEROCK_HOST": "api.test.local",
        "RAGNEROCK_PROJECT": "proj",
        "RAGNEROCK_API_TOKEN": "tok",
        "RAGNEROCK_EMAIL": "alice@example.com",
        "RAGNEROCK_PASSWORD": "hunter2",
    }
    engine = build_engine(env=env)
    assert engine._client.auth_token == "tok"
    assert engine._email is None
