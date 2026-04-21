"""Shared fixtures for integration tests.

Integration tests require a live Ragnerock instance. Configuration comes from
env vars — see ``tests/integration/README.md`` for the full list. When
credentials aren't provided, every test in this directory is skipped.

Fixtures here own the engine/session lifecycle and supply helpers for creating
uniquely-named resources with automatic teardown.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

from ragnerock import Engine, Session, create_engine


def _build_conn_str() -> str | None:
    """Resolve a connection string from env. Returns None if config is incomplete."""
    direct = os.environ.get("RAGNEROCK_CONN_STR")
    if direct:
        return direct

    host = os.environ.get("RAGNEROCK_HOST")
    email = os.environ.get("RAGNEROCK_EMAIL")
    password = os.environ.get("RAGNEROCK_PASSWORD")
    project = os.environ.get("RAGNEROCK_PROJECT")
    if all([host, email, password, project]):
        return f"ragnerock://{email}:{password}@{host}/{project}"
    return None


CONN_STR = _build_conn_str()


def pytest_collection_modifyitems(config, items):
    """Skip every integration test if config is missing."""
    if CONN_STR is not None:
        return
    skip = pytest.mark.skip(
        reason=(
            "No Ragnerock credentials configured — set RAGNEROCK_CONN_STR or "
            "RAGNEROCK_HOST/EMAIL/PASSWORD/PROJECT to run integration tests."
        )
    )
    for item in items:
        item.add_marker(skip)


@pytest.fixture(scope="session")
def conn_str() -> str:
    """The connection string assembled from env. Guaranteed non-None at fixture time."""
    assert CONN_STR is not None  # guarded by pytest_collection_modifyitems
    return CONN_STR


_DEFAULT_CREDIT_TOP_UP = 1000


def _ensure_credits(engine: Engine) -> None:
    """Top up the account's credit balance at the start of a test session.

    Controlled by ``RAGNEROCK_ITEST_CREDITS``:
        - unset: purchase the default (``1000``) credits
        - set to a positive integer: purchase that many credits
        - set to ``0``: skip the purchase entirely (use when credits are
          managed externally, e.g. seeded by a CI task)

    Per the API docstring, ``POST /api/credits/purchase`` expects Stripe
    payment processing to have already happened. In dev / test instances it
    simply adds the credits directly.
    """
    raw = os.environ.get("RAGNEROCK_ITEST_CREDITS")
    if raw == "0":
        return
    try:
        amount = int(raw) if raw else _DEFAULT_CREDIT_TOP_UP
    except ValueError:
        pytest.fail(f"RAGNEROCK_ITEST_CREDITS must be an integer, got {raw!r}")

    # Triggers login + project resolution on first access.
    client = engine.client

    balance_resp = client._request("GET", "/api/credits/balance")
    balance = balance_resp.json().get("balance", 0)
    if balance >= amount:
        # Already have enough; don't spend.
        return

    client._request(
        "POST",
        "/api/credits/purchase",
        json_body={"credits": amount},
    )


@pytest.fixture(scope="session")
def engine(conn_str) -> Engine:
    """One engine per test session — auth happens once, project resolves once.

    Before the first test runs, the engine purchases credits so tests that
    consume quota don't fail mid-flight. See :func:`_ensure_credits` for the
    controlling env var.
    """
    engine = create_engine(conn_str)
    _ensure_credits(engine)
    return engine


@pytest.fixture
def session(engine) -> Iterator[Session]:
    """Fresh Session per test."""
    with Session(engine) as s:
        yield s


@pytest.fixture
def unique_name() -> str:
    """A collision-free name for server-side resources created by a test."""
    return f"sdk-itest-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def cleanup(session):
    """Register resources for teardown. Calls session.delete + commit on each.

    Usage::

        def test_something(session, cleanup):
            doc = Document(file_path=...)
            session.add(doc); session.commit()
            cleanup(doc)
            ...

    Teardown is best-effort — failures are logged, not raised.
    """
    registered: list = []

    def _register(resource) -> None:
        registered.append(resource)

    yield _register

    for resource in reversed(registered):
        try:
            session.delete(resource)
            session.commit()
        except Exception as e:  # noqa: BLE001 — best-effort cleanup
            print(f"cleanup failed for {type(resource).__name__}: {e}")


def skip_unless_env(name: str) -> pytest.MarkDecorator:
    """Skip a test unless the named env var is truthy."""
    value = os.environ.get(name)
    return pytest.mark.skipif(
        not value,
        reason=f"opt-in: set {name}=1 to enable",
    )
