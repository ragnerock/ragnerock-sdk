"""Shared fixtures for integration tests.

Integration tests require a live Ragnerock instance. Configuration comes from
env vars — see ``integration/README.md`` for the full list. When credentials
aren't provided, every test in this directory is skipped.

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
def engine() -> Engine:
    """One engine per test session — auth happens once, project resolves once."""
    assert CONN_STR is not None  # guarded by pytest_collection_modifyitems
    return create_engine(CONN_STR)


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
