"""Engine / Session / auth flows against a live Ragnerock instance.

Covers:
    - engine construction is lazy (doesn't authenticate up front)
    - live login + project resolution
    - typed errors for bad credentials and unknown projects
    - context-manager semantics: enter returns a session, exit doesn't auto-commit
"""

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import urlparse

import pytest

from ragnerock import (
    AuthenticationError,
    Document,
    NotFoundError,
    Session,
    create_engine,
)


class TestLazyConnect:
    """Constructing an engine must not issue any HTTP request."""

    def test_create_engine_does_not_authenticate(self, conn_str):
        with patch("httpx.Client.request") as mock_request:
            engine = create_engine(conn_str)
            assert engine is not None
        assert mock_request.call_count == 0


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
    conn_str: str, *, credential: str | None = None, project: str | None = None
) -> str:
    """Rebuild a connection string with one component replaced.

    Mode-aware:
      - ``email:password@host`` — ``credential`` swaps the password.
      - ``token:apitoken@host`` — ``credential`` swaps the API token.
      - bare ``host`` (env-var token mode) — ``credential`` is injected as an
        inline ``token:<credential>`` so the result is self-contained and
        doesn't depend on the ambient ``RAGNEROCK_API_TOKEN``.
    """
    parsed = urlparse(conn_str)
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("Cannot swap: connection string has no hostname")
    port = f":{parsed.port}" if parsed.port is not None else ""

    if credential is not None:
        if parsed.username == "token":
            user, pwd = "token", credential
        elif parsed.username:
            user, pwd = parsed.username, credential
        else:
            user, pwd = "token", credential
        netloc = f"{user}:{pwd}@{hostname}{port}"
    elif parsed.username:
        existing_pwd = parsed.password or ""
        netloc = f"{parsed.username}:{existing_pwd}@{hostname}{port}"
    else:
        netloc = f"{hostname}{port}"

    new_project = project if project is not None else parsed.path.lstrip("/")
    return f"ragnerock://{netloc}/{new_project}"


class TestAuthFailures:
    """Failures at login / project resolution surface as typed errors."""

    def test_bad_credentials_raises_authentication_error(self, conn_str):
        bad = _swap_conn_str(conn_str, credential="definitely-not-the-credential-xyz")
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
