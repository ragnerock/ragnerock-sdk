"""Engine / Session / auth flows against a live Ragnerock instance.

Covers:
    - connection-string parsing (pure, no network)
    - engine construction is lazy (doesn't authenticate up front)
    - live login + project resolution
    - typed errors for bad credentials and unknown projects
    - context-manager semantics: enter returns a session, exit doesn't auto-commit
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from ragnerock import (
    AuthenticationError,
    Document,
    NotFoundError,
    Session,
    create_engine,
)


class TestConnectionString:
    """`create_engine` parses a ragnerock:// URL. These checks don't touch the network."""

    def test_parses_valid_https_string(self):
        engine = create_engine(
            "ragnerock://alice@example.com:hunter2@api.ragnerock.com/demo"
        )
        assert engine.host == "https://api.ragnerock.com"
        assert engine.project_name == "demo"

    def test_localhost_uses_http(self):
        engine = create_engine("ragnerock://u@e.com:p@localhost:8000/demo")
        assert engine.host == "http://localhost:8000"

    def test_127_0_0_1_uses_http(self):
        engine = create_engine("ragnerock://u@e.com:p@127.0.0.1:8000/demo")
        assert engine.host == "http://127.0.0.1:8000"

    def test_custom_port_preserved(self):
        engine = create_engine("ragnerock://u@e.com:p@ragnerock.internal:8443/demo")
        assert engine.host == "https://ragnerock.internal:8443"

    def test_missing_scheme_raises(self):
        with pytest.raises(ValueError):
            create_engine("u@e.com:p@host/demo")

    def test_wrong_scheme_raises(self):
        with pytest.raises(ValueError):
            create_engine("postgres://u:p@host/demo")

    def test_missing_user_raises(self):
        with pytest.raises(ValueError):
            create_engine("ragnerock://:p@host/demo")

    def test_missing_password_raises(self):
        with pytest.raises(ValueError):
            create_engine("ragnerock://u@e.com@host/demo")

    def test_missing_host_raises(self):
        with pytest.raises(ValueError):
            create_engine("ragnerock://u@e.com:p@/demo")

    def test_missing_project_raises(self):
        with pytest.raises(ValueError):
            create_engine("ragnerock://u@e.com:p@host/")


class TestLazyConnect:
    """Constructing an engine must not authenticate."""

    def test_create_engine_does_not_authenticate(self, conn_str):
        engine = create_engine(conn_str)
        # Token only appears after a Session is opened.
        assert not engine.client.auth_token


class TestLiveConnection:
    """Opening a session against a live instance succeeds and resolves the project."""

    def test_engine_resolves_project(self, engine):
        with Session(engine):
            assert engine.project_id is not None
            assert engine.client.auth_token

    def test_session_reads_work(self, session):
        """If auth succeeded, the simplest read should return without raising."""
        session.list(Document).first()


def _swap_conn_str(
    conn_str: str, *, password: str | None = None, project: str | None = None
) -> str:
    """Rebuild a connection string with one component replaced."""
    parsed = urlparse(conn_str)
    new_user = parsed.username or ""
    new_pass = password if password is not None else (parsed.password or "")
    netloc = f"{new_user}:{new_pass}@{parsed.hostname}"
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    new_project = project if project is not None else parsed.path.lstrip("/")
    return f"ragnerock://{netloc}/{new_project}"


class TestAuthFailures:
    """Failures at login / project resolution surface as typed errors."""

    def test_bad_credentials_raises_authentication_error(self, conn_str):
        bad = _swap_conn_str(conn_str, password="definitely-not-the-password-xyz")
        engine = create_engine(bad)
        with pytest.raises(AuthenticationError) as exc_info:
            with Session(engine):
                pass
        assert exc_info.value.status_code in (401, 403)

    def test_unknown_project_raises_not_found(self, conn_str):
        bogus = _swap_conn_str(conn_str, project="sdk-itest-no-such-project-xyz123")
        engine = create_engine(bogus)
        with pytest.raises(NotFoundError):
            with Session(engine):
                pass


class TestContextManager:
    def test_enter_returns_session(self, engine):
        with Session(engine) as s:
            assert isinstance(s, Session)

    def test_exit_does_not_autocommit(self, engine, unique_name, tmp_path):
        """Staged ops must be discarded on `__exit__`, not pushed to the server."""
        file_path = tmp_path / f"{unique_name}.pdf"
        file_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

        with Session(engine) as s:
            doc = Document(file_path=str(file_path), name=unique_name)
            s.add(doc)
            # leave the `with` block without calling commit()

        # Reopen and verify nothing with that name exists.
        with Session(engine) as s:
            assert s.get(Document, name=unique_name) is None

    def test_exit_on_exception_does_not_autocommit(self, engine, unique_name, tmp_path):
        class _Boom(Exception):
            pass

        file_path = tmp_path / f"{unique_name}.pdf"
        file_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

        with pytest.raises(_Boom):
            with Session(engine) as s:
                s.add(Document(file_path=str(file_path), name=unique_name))
                raise _Boom

        with Session(engine) as s:
            assert s.get(Document, name=unique_name) is None
