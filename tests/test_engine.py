"""Tests for `Engine`, `create_engine`, and connection-string parsing.

These tests describe the contract a user sees when constructing an engine
and opening a session: string parsing, lazy connection, auth failure paths,
and project resolution.
"""

from __future__ import annotations

import pytest

from ragnerock import AuthenticationError, NotFoundError, Session, create_engine
from tests.conftest import TEST_EMAIL, TEST_HOST, TEST_PASSWORD, TEST_PROJECT_NAME


class TestConnectionString:
    """`create_engine` parses a ragnerock:// URL into a host + project + creds."""

    def test_parses_valid_https_string(self):
        engine = create_engine(
            f"ragnerock://{TEST_EMAIL}:{TEST_PASSWORD}@api.ragnerock.com/demo"
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
    """Constructing an engine must not hit the network."""

    def test_create_engine_is_offline(self, httpx_mock, conn_str):
        # No mocks registered — if create_engine made any HTTP call, the test
        # would fail with an unexpected-request error from httpx_mock.
        create_engine(conn_str)

    def test_session_enter_triggers_login(self, httpx_mock, engine):
        # engine fixture sets up mock_login. Opening the session fires the
        # auth + project-lookup calls.
        with Session(engine) as s:
            assert s is not None

        # Two outbound requests should have been made: login + project lookup.
        requests = httpx_mock.get_requests()
        paths = [r.url.path for r in requests]
        assert "/api/auth/login" in paths
        assert any(p.startswith("/api/projects/name/") for p in paths)


class TestAuthFailures:
    """Failures at login / project resolution surface as typed errors."""

    def test_bad_credentials_raises_authentication_error(self, httpx_mock, conn_str):
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/auth/login",
            status_code=401,
            json={"detail": {"message": "invalid credentials"}},
        )
        engine = create_engine(conn_str)
        with pytest.raises(AuthenticationError) as exc_info:
            with Session(engine):
                pass
        assert exc_info.value.status_code == 401

    def test_unknown_project_raises_not_found(self, httpx_mock, conn_str):
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/auth/login",
            json={"access_token": "tok", "token_type": "bearer"},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/projects/name/{TEST_PROJECT_NAME}",
            json={"projects": [], "total": 0, "skip": 0, "limit": 100},
        )
        engine = create_engine(conn_str)
        with pytest.raises(NotFoundError):
            with Session(engine):
                pass


class TestAuthHeader:
    """After login, subsequent requests must carry the bearer token."""

    def test_token_used_on_subsequent_request(self, httpx_mock, session, payloads):
        import re

        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf"{re.escape(TEST_HOST)}/api/documents/\?.*"),
            json=payloads.list_envelope("documents", []),
            is_reusable=True,
        )
        from ragnerock import Document

        session.list(Document).all()

        doc_requests = [
            r for r in httpx_mock.get_requests() if r.url.path == "/api/documents/"
        ]
        assert doc_requests, "expected at least one list documents request"
        assert doc_requests[0].headers.get("authorization") == "Bearer test-access-token-xyz"
