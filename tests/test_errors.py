"""Tests for the error hierarchy and HTTP → exception mapping."""

from __future__ import annotations

import re

import pytest

from ragnerock import (
    AuthenticationError,
    Document,
    NotFoundError,
    RagnerockError,
    ValidationError,
)
from tests.conftest import TEST_HOST


class TestHierarchy:
    def test_all_errors_subclass_base(self):
        from ragnerock import CommitError, QueryError

        for cls in (
            AuthenticationError,
            NotFoundError,
            ValidationError,
            QueryError,
            CommitError,
        ):
            assert issubclass(cls, RagnerockError)


class TestStatusMapping:
    def test_401_maps_to_auth_error(self, httpx_mock, session):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/.*"),
            status_code=401,
            json={"detail": {"message": "token expired"}},
        )
        with pytest.raises(AuthenticationError) as exc:
            session.get(Document, id="00000000-0000-0000-0000-000000000101")
        assert exc.value.status_code == 401

    def test_403_maps_to_auth_error(self, httpx_mock, session):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/.*"),
            status_code=403,
            json={"detail": {"message": "forbidden"}},
        )
        with pytest.raises(AuthenticationError):
            session.get(Document, id="00000000-0000-0000-0000-000000000101")

    def test_404_on_update_maps_to_not_found(self, httpx_mock, session, payloads):
        """404 during a write surfaces as NotFoundError (not None)."""
        doc_id = "00000000-0000-0000-0000-000000000101"
        httpx_mock.add_response(
            method="PUT",
            url=f"{TEST_HOST}/api/documents/{doc_id}",
            status_code=404,
            json={"detail": {"message": "gone"}},
        )
        doc = Document(**payloads.document(id=doc_id))
        doc.name = "x"
        session.update(doc)
        # commit surfaces the server 404 as a RagnerockError subclass
        from ragnerock import CommitError

        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, NotFoundError)

    def test_422_maps_to_validation_error(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/documents/",
            status_code=422,
            json={"detail": {"message": "missing field"}},
        )
        doc = Document(file_path="./x.pdf")
        session.add(doc)
        from ragnerock import CommitError

        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, ValidationError)


class TestErrorBodyParsing:
    def test_suggestion_surfaces(self, httpx_mock, session):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/.*"),
            status_code=422,
            json={
                "detail": {
                    "message": "bad",
                    "suggestion": "try harder",
                    "details": {"field": "name"},
                }
            },
        )
        with pytest.raises(ValidationError) as exc:
            session.get(Document, id="00000000-0000-0000-0000-000000000101")
        assert exc.value.suggestion == "try harder"
        assert exc.value.details == {"field": "name"}
