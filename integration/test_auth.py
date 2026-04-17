"""Auth, project lookup, bearer-token threading."""

from __future__ import annotations

from ragnerock import Document, Session


def test_engine_resolves_project(engine):
    """Opening a session triggers login + project-name → id lookup."""
    with Session(engine):
        assert engine.project_id is not None
        assert engine.client.auth_token


def test_session_reads_work(session):
    """If auth succeeded, the simplest read should return without raising."""
    # list() is lazy; .first() forces one fetch.
    session.list(Document).first()
