"""Tests for the error hierarchy and HTTP status → exception mapping."""

from __future__ import annotations

import re

import pytest

from ragnerock import (
    AuthenticationError,
    CommitError,
    Document,
    NotFoundError,
    QueryError,
    RagnerockError,
    ValidationError,
)
from ragnerock.errors import raise_for_status


class TestHierarchy:
    """Every SDK exception must subclass ``RagnerockError``."""

    @pytest.mark.parametrize(
        "cls",
        [AuthenticationError, NotFoundError, ValidationError, QueryError, CommitError],
    )
    def test_all_errors_subclass_base(self, cls):
        assert issubclass(cls, RagnerockError)

    def test_base_exception_str_contains_status_and_suggestion(self):
        err = RagnerockError(
            "boom",
            status_code=418,
            suggestion="use a teapot",
        )
        text = str(err)
        assert "[418]" in text
        assert "boom" in text
        assert "Suggestion: use a teapot" in text

    def test_query_error_carries_error_code(self):
        err = QueryError("bad sql", status_code=400, error_code="SYNTAX_ERROR")
        assert err.error_code == "SYNTAX_ERROR"


class TestRaiseForStatus:
    """``raise_for_status`` picks the right subclass for each status code."""

    def test_2xx_is_noop(self):
        raise_for_status(200, "")
        raise_for_status(204, "")

    def test_401_maps_to_auth(self):
        with pytest.raises(AuthenticationError):
            raise_for_status(401, '{"detail": {"message": "nope"}}')

    def test_403_maps_to_auth(self):
        with pytest.raises(AuthenticationError):
            raise_for_status(403, '{"detail": {"message": "nope"}}')

    def test_404_maps_to_not_found(self):
        with pytest.raises(NotFoundError):
            raise_for_status(404, '{"detail": {"message": "gone"}}')

    def test_422_maps_to_validation(self):
        with pytest.raises(ValidationError):
            raise_for_status(422, '{"detail": {"message": "bad field"}}')

    def test_error_code_overrides_status_mapping(self):
        """When the body includes ``error_code``, a QueryError is preferred."""
        with pytest.raises(QueryError) as exc:
            raise_for_status(
                400,
                '{"detail": {"message": "bad sql", "error_code": "SYNTAX"}}',
            )
        assert exc.value.error_code == "SYNTAX"

    def test_generic_5xx_falls_back_to_base(self):
        with pytest.raises(RagnerockError) as exc:
            raise_for_status(500, '{"detail": {"message": "boom"}}')
        assert not isinstance(
            exc.value, (AuthenticationError, NotFoundError, ValidationError)
        )
        assert exc.value.status_code == 500

    def test_non_json_body_becomes_message(self):
        with pytest.raises(RagnerockError) as exc:
            raise_for_status(502, "gateway down, plain text")
        assert "gateway" in exc.value.message

    def test_fastapi_validation_list_body(self):
        body = '{"detail": [{"loc": ["body", "x"], "msg": "missing"}]}'
        with pytest.raises(RagnerockError) as exc:
            raise_for_status(422, body)
        assert exc.value.details is not None
        assert "errors" in exc.value.details


class TestStatusMappingOverHttp:
    """Verify the same mapping when a real httpx response triggers it."""

    def test_401_during_read_surfaces_as_auth_error(self, httpx_mock, session):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/.*"),
            status_code=401,
            json={"detail": {"message": "token expired"}},
        )
        with pytest.raises(AuthenticationError) as exc:
            session.get(Document, id="00000000-0000-0000-0000-000000000101")
        assert exc.value.status_code == 401

    def test_422_during_create_wraps_in_commit_error(
        self, httpx_mock, session, base_url
    ):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/documents/",
            status_code=422,
            json={"detail": {"message": "missing field"}},
        )
        doc = Document(file_path="./local-missing.pdf")
        session.add(doc)
        with pytest.raises(CommitError) as exc:
            session.commit()
        assert isinstance(exc.value.cause, ValidationError)

    def test_suggestion_and_details_carried_through(self, httpx_mock, session):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/documents/.*"),
            status_code=422,
            json={
                "detail": {
                    "message": "invalid",
                    "suggestion": "retry with a name",
                    "details": {"field": "name"},
                }
            },
        )
        with pytest.raises(ValidationError) as exc:
            session.get(Document, id="00000000-0000-0000-0000-000000000101")
        assert exc.value.suggestion == "retry with a name"
        assert exc.value.details == {"field": "name"}


class TestCommitError:
    """``CommitError`` captures which resources committed vs. remain pending."""

    def test_committed_and_pending_split_on_failure(
        self, httpx_mock, session, payloads, base_url
    ):
        doc1 = Document(source_url="https://example.com/a.pdf")
        doc2 = Document(source_url="https://example.com/b.pdf")

        # first POST succeeds
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/documents/",
            json=payloads.document(
                id="00000000-0000-0000-0000-00000000aaaa", name="a.pdf"
            ),
        )
        # second POST fails
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/documents/",
            status_code=500,
            json={"detail": {"message": "server bork"}},
        )

        session.add(doc1)
        session.add(doc2)
        with pytest.raises(CommitError) as exc:
            session.commit()

        assert doc1 in exc.value.committed
        assert doc2 in exc.value.pending
        assert isinstance(exc.value.cause, RagnerockError)
