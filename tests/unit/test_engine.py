"""Tests for ``create_engine`` and the lazy-connection contract of ``Engine``."""

from __future__ import annotations

import pytest

from ragnerock import AuthenticationError, NotFoundError, Session, create_engine


class TestConnectionString:
    """``create_engine`` parses a ``ragnerock://`` URL into host + creds + project."""

    def test_parses_valid_https_string(self):
        engine = create_engine(
            "ragnerock://alice@example.com:hunter2@api.ragnerock.com/demo"
        )
        assert engine.host == "https://api.ragnerock.com"
        assert engine.project_name == "demo"

    def test_localhost_downgrades_to_http(self):
        engine = create_engine("ragnerock://a@b.com:p@localhost:8000/demo")
        assert engine.host == "http://localhost:8000"

    def test_loopback_ip_downgrades_to_http(self):
        engine = create_engine("ragnerock://a@b.com:p@127.0.0.1:8000/demo")
        assert engine.host == "http://127.0.0.1:8000"

    def test_custom_port_is_preserved(self):
        engine = create_engine("ragnerock://a@b.com:p@ragnerock.internal:8443/demo")
        assert engine.host == "https://ragnerock.internal:8443"

    @pytest.mark.parametrize(
        "bad",
        [
            "user@host.com:pass@host/demo",  # missing scheme
            "postgres://u:p@host/demo",  # wrong scheme
            "ragnerock://:pass@host/demo",  # missing user
            "ragnerock://a@b.com@host/demo",  # missing password
            "ragnerock://a@b.com:p@/demo",  # missing host
            "ragnerock://a@b.com:p@host/",  # missing project
        ],
    )
    def test_malformed_string_raises_value_error(self, bad):
        with pytest.raises(ValueError):
            create_engine(bad)


class TestLazyConnect:
    """Building an ``Engine`` must not issue any HTTP call."""

    def test_create_engine_is_offline(self, httpx_mock, conn_str):
        # With zero mocks registered, any outbound call would fail collection.
        create_engine(conn_str)

    def test_session_enter_triggers_login_and_project_lookup(self, httpx_mock, engine):
        with Session(engine) as s:
            assert s is not None

        paths = [r.url.path for r in httpx_mock.get_requests()]
        assert "/api/auth/login" in paths
        assert any(p.startswith("/api/projects/name/") for p in paths)

    def test_engine_caches_login(self, httpx_mock, engine):
        """Multiple ``with Session(engine)`` must reuse the cached client."""
        with Session(engine):
            pass
        with Session(engine):
            pass
        logins = [
            r for r in httpx_mock.get_requests() if r.url.path == "/api/auth/login"
        ]
        assert len(logins) == 1


class TestAuthFailures:
    """Login / project errors surface as typed SDK errors on ``__enter__``."""

    def test_bad_credentials_raises_authentication_error(
        self, httpx_mock, conn_str, base_url
    ):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/auth/login",
            status_code=401,
            json={"detail": {"message": "invalid credentials"}},
        )
        engine = create_engine(conn_str)
        with pytest.raises(AuthenticationError) as exc_info:
            with Session(engine):
                pass
        assert exc_info.value.status_code == 401

    def test_unknown_project_raises_not_found(self, httpx_mock, conn_str, base_url):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/auth/login",
            json={"access_token": "tok", "token_type": "bearer"},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/api/projects/name/demo",
            json={"projects": [], "total": 0, "skip": 0, "limit": 100},
        )
        engine = create_engine(conn_str)
        with pytest.raises(NotFoundError):
            with Session(engine):
                pass


class TestAuthHeaderPropagation:
    """After login, downstream requests must carry the bearer token."""

    def test_token_used_on_subsequent_request(self, httpx_mock, session, payloads):
        import re

        from ragnerock import Document

        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/\?.*"),
            json=payloads.list_envelope("documents", []),
            is_reusable=True,
        )
        session.list(Document).all()
        requests = [
            r for r in httpx_mock.get_requests() if r.url.path == "/api/documents/"
        ]
        assert requests
        assert (
            requests[0].headers.get("authorization") == "Bearer test-access-token-xyz"
        )
