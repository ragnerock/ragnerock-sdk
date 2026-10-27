"""Tests for the annotation section: CRUD, revisions, and scoped listings."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from ragnerock.client import RagnerockClient
from ragnerock.errors import NotFoundError, RagnerockError, ValidationError
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

ROOT_ID = uuid.UUID("00000000-0000-4000-8000-000000000501")
OPERATOR_ID = uuid.UUID("00000000-0000-4000-8000-000000000601")
SCHEMA_ID = uuid.UUID("00000000-0000-4000-8000-000000000701")
DOC_ID = uuid.UUID("00000000-0000-4000-8000-000000000101")
CHUNK_ID = uuid.UUID("00000000-0000-4000-8000-000000000301")
ROW_ID = uuid.UUID("00000000-0000-4000-8000-000000000901")


def _annotation(root_id: uuid.UUID = ROOT_ID, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "data": {"topic": "finance"},
        "root_id": str(root_id),
        "operator_id": str(OPERATOR_ID),
        "schema_id": str(SCHEMA_ID),
        "document_id": str(DOC_ID),
        "chunk_id": None,
        "page_id": None,
        "confidence_score": 0.9,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": None,
        "generation_metadata": {},
    }
    payload.update(overrides)
    return payload


def _page(key: str, items: list[Any], *, total: int | None = None, skip: int = 0):
    return {
        key: items,
        "total": len(items) if total is None else total,
        "skip": skip,
        "limit": 100,
    }


def _revision(index: int, source: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "revision_index": index,
        "data": data,
        "confidence_score": None,
        "source": source,
        "restored_from_index": None,
        "restored_from_id": None,
        "created_at": "2026-08-10T00:00:00Z",
        "created_by_id": None,
        "created_by_email": None,
    }


class TestGet:
    def test_parses_hydrated_fields(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET", url=url(f"/api/annotations/{ROOT_ID}"), json=_annotation()
        )

        annotation = client.annotations.get(ROOT_ID)

        assert annotation.root_id == ROOT_ID
        assert annotation.schema_id == SCHEMA_ID
        assert annotation.data == {"topic": "finance"}
        assert annotation.document_id == DOC_ID
        assert annotation.created_at == datetime(2026, 1, 1, tzinfo=UTC)
        assert annotation.updated_at is None


class TestCreate:
    def test_posts_body_for_single_target(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST", url=url("/api/annotations/"), json=_annotation()
        )

        result = client.annotations.create(
            operator_id=OPERATOR_ID,
            data={"topic": "finance"},
            document_id=DOC_ID,
            confidence_score=0.75,
            generation_metadata={"model": "m"},
        )

        assert last_request(httpx_mock).method == "POST"
        assert last_json(httpx_mock) == {
            "operator_id": str(OPERATOR_ID),
            "data": {"topic": "finance"},
            "document_id": str(DOC_ID),
            "confidence_score": 0.75,
            "generation_metadata": {"model": "m"},
        }
        assert result.root_id == ROOT_ID
        assert result.document_id == DOC_ID

    def test_row_target_and_empty_data(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/annotations/"),
            json=_annotation(data={}, row_id=str(ROW_ID)),
        )

        result = client.annotations.create(
            operator_id=OPERATOR_ID, data={}, document_id=DOC_ID, row_id=ROW_ID
        )

        body = last_json(httpx_mock)
        assert body["data"] == {}
        assert body["row_id"] == str(ROW_ID)
        assert "sheet_id" not in body
        assert "generation_metadata" not in body
        assert result.row_id == ROW_ID

    def test_validation_error_surfaces(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/annotations/"),
            status_code=422,
            json={"detail": "Data does not match schema"},
        )

        with pytest.raises(ValidationError, match="Data does not match schema"):
            client.annotations.create(
                operator_id=OPERATOR_ID, data={}, chunk_id=CHUNK_ID
            )


class TestUpdate:
    def test_puts_data_and_confidence_param(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/annotations/{ROOT_ID}?confidence_score=0.5"),
            json=_annotation(data={"topic": "tech"}),
        )

        result = client.annotations.update(
            ROOT_ID, data={"topic": "tech"}, confidence_score=0.5
        )

        assert last_json(httpx_mock) == {"topic": "tech"}
        assert result.data == {"topic": "tech"}

    def test_omits_confidence_when_not_given(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT", url=url(f"/api/annotations/{ROOT_ID}"), json=_annotation()
        )

        client.annotations.update(ROOT_ID, data={"topic": "finance"})

        assert last_params(httpx_mock) == {}

    def test_not_found_raises(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/annotations/{ROOT_ID}"),
            status_code=404,
            json={"detail": "Annotation not found"},
        )

        with pytest.raises(NotFoundError) as exc_info:
            client.annotations.update(ROOT_ID, data={})
        assert exc_info.value.status_code == 404


class TestDelete:
    def test_deletes_by_root_id(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="DELETE", url=url(f"/api/annotations/{ROOT_ID}"), json={}
        )

        assert client.annotations.delete(ROOT_ID) is None

    @pytest.mark.parametrize(
        ("status_code", "error_type"),
        [(404, NotFoundError), (500, RagnerockError)],
    )
    def test_error_status_raises(
        self,
        client: RagnerockClient,
        httpx_mock: Any,
        status_code: int,
        error_type: type[RagnerockError],
    ) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/annotations/{ROOT_ID}"),
            status_code=status_code,
            json={"detail": "boom"},
        )

        with pytest.raises(error_type) as exc_info:
            client.annotations.delete(ROOT_ID)
        assert exc_info.value.status_code == status_code


class TestRevisions:
    def test_list_revisions_sends_pagination(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/annotations/{ROOT_ID}/revisions?skip=5&limit=10"),
            json={
                "revisions": [_revision(2, "user_edit", {"topic": "tech"})],
                "total": 6,
                "skip": 5,
                "limit": 10,
            },
        )

        result = client.annotations.list_revisions(ROOT_ID, skip=5, limit=10)

        assert result.total == 6
        revision = result.revisions[0]
        assert revision.revision_index == 2
        assert revision.source == "user_edit"
        assert revision.data == {"topic": "tech"}
        assert revision.created_at == datetime(2026, 8, 10, tzinfo=UTC)

    def test_list_revisions_defaults(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/annotations/{ROOT_ID}/revisions?skip=0&limit=50"),
            json={"revisions": [], "total": 0, "skip": 0, "limit": 50},
        )

        assert client.annotations.list_revisions(ROOT_ID).revisions == []

    def test_restore_posts_to_the_revision(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/annotations/{ROOT_ID}/revisions/3/restore"),
            json=_annotation(data={"topic": "original"}),
        )

        result = client.annotations.restore(ROOT_ID, 3)

        assert last_request(httpx_mock).content == b""
        assert result.data == {"topic": "original"}


class TestCorrectionsRecipe:
    """Pair each edited annotation's machine original with its latest state.

    The original is the *oldest* revision and the history is newest first, so
    the history must be paged to the end to find it.
    """

    @staticmethod
    def _run_recipe(
        client: RagnerockClient,
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        edited = client.annotations.list_hydrated_by_schema(SCHEMA_ID, edited_only=True)
        for ann in edited.annotations:
            assert ann.root_id is not None
            revs: list[Any] = []
            total: int | None = None
            while total is None or len(revs) < total:
                page = client.annotations.list_revisions(ann.root_id, skip=len(revs))
                revs.extend(page.revisions)
                total = page.total
            original = next((r for r in reversed(revs) if r.source == "operator"), None)
            if original is None or revs[0].data == original.data:
                continue
            pairs.append((original.data, revs[0].data))
        return pairs

    def test_finds_original_beyond_page_one(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        original = {"label": "machine"}
        corrected = {"label": "human-final"}
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/annotations/schema/{SCHEMA_ID}/hydrated"
                "?skip=0&limit=100&edited_only=true"
            ),
            json=_page("annotations", [_annotation(data=corrected)]),
        )
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/annotations/{ROOT_ID}/revisions?skip=0&limit=50"),
            json=_page(
                "revisions",
                [
                    _revision(3, "user_edit", corrected),
                    _revision(2, "user_edit", {"label": "human-draft"}),
                ],
                total=3,
            ),
        )
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/annotations/{ROOT_ID}/revisions?skip=2&limit=50"),
            json=_page(
                "revisions", [_revision(1, "operator", original)], total=3, skip=2
            ),
        )

        assert self._run_recipe(client) == [(original, corrected)]

    def test_skips_legacy_origin_and_empty_histories(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        legacy_root = uuid.UUID("00000000-0000-4000-8000-0000000005a1")
        untouched_root = uuid.UUID("00000000-0000-4000-8000-0000000005a2")
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/annotations/schema/{SCHEMA_ID}/hydrated"
                "?skip=0&limit=100&edited_only=true"
            ),
            json=_page(
                "annotations",
                [_annotation(legacy_root), _annotation(untouched_root)],
            ),
        )
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/annotations/{legacy_root}/revisions?skip=0&limit=50"),
            json=_page(
                "revisions",
                [
                    _revision(2, "user_edit", {"label": "edited"}),
                    _revision(1, "legacy", {"label": "who-knows"}),
                ],
            ),
        )
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/annotations/{untouched_root}/revisions?skip=0&limit=50"),
            json=_page("revisions", []),
        )

        assert self._run_recipe(client) == []


class TestListHydratedBySchema:
    def test_sends_defaults_without_optional_filters(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/annotations/schema/{SCHEMA_ID}/hydrated?skip=0&limit=100"),
            json=_page("annotations", [_annotation()]),
        )

        result = client.annotations.list_hydrated_by_schema(SCHEMA_ID)

        assert result.annotations[0].schema_id == SCHEMA_ID

    def test_sends_all_filters(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/annotations/schema/{SCHEMA_ID}/hydrated"
                f"?skip=20&limit=10&search=acme&edited_only=true"
                f"&user_created_only=true&document_id={DOC_ID}"
            ),
            json=_page("annotations", []),
        )

        client.annotations.list_hydrated_by_schema(
            SCHEMA_ID,
            skip=20,
            limit=10,
            search="acme",
            edited_only=True,
            user_created_only=True,
            document_id=DOC_ID,
        )

        assert last_params(httpx_mock) == {
            "skip": "20",
            "limit": "10",
            "search": "acme",
            "edited_only": "true",
            "user_created_only": "true",
            "document_id": str(DOC_ID),
        }


class TestOperatorScopedListings:
    def test_documents_with_annotations(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        document = {
            "id": str(DOC_ID),
            "project_id": PROJECT_ID,
            "name": "report.pdf",
            "group_id": None,
        }
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/annotations/operator/{OPERATOR_ID}/documents?skip=0&limit=100"
            ),
            json=_page("documents", [{"document": document, "annotation_count": 4}]),
        )

        result = client.annotations.list_documents_with_schema_annotations(OPERATOR_ID)

        item = result.documents[0]
        assert item.document.id == DOC_ID
        assert item.document.name == "report.pdf"
        assert item.annotation_count == 4

    def test_chunks_with_schema_annotations(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/annotations/operator/{OPERATOR_ID}/chunks?skip=10&limit=5"),
            json=_page("annotations", [_annotation(chunk_id=str(CHUNK_ID))]),
        )

        result = client.annotations.list_chunks_with_schema_annotations(
            OPERATOR_ID, skip=10, limit=5
        )

        assert result.annotations[0].chunk_id == CHUNK_ID
        assert result.annotations[0].data == {"topic": "finance"}


class TestDocumentScopedListings:
    def test_chunks_with_annotations_by_document(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        chunk = {"id": str(CHUNK_ID), "document_id": str(DOC_ID), "content": "Hello"}
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/annotations/document/{DOC_ID}/chunks-with-annotations"
                "?operator_name=topics&skip=0&limit=100"
            ),
            json=_page(
                "chunks",
                [
                    {"chunk": chunk, "annotation": _annotation(chunk_id=str(CHUNK_ID))},
                    {"chunk": chunk, "annotation": None},
                ],
            ),
        )

        result = client.annotations.list_chunks_with_annotations_by_document(
            DOC_ID, operator_name="topics"
        )

        assert result.chunks[0].chunk.id == CHUNK_ID
        first = result.chunks[0].annotation
        assert first is not None
        assert first.root_id == ROOT_ID
        assert result.chunks[1].annotation is None

    def test_chunks_with_annotations_omits_unset_operator(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/annotations/document/{DOC_ID}/chunks-with-annotations"
                "?skip=0&limit=100"
            ),
            json=_page("chunks", []),
        )

        assert (
            client.annotations.list_chunks_with_annotations_by_document(DOC_ID).chunks
            == []
        )

    def test_by_document_and_operator_id(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/annotations/document/{DOC_ID}/operator/{OPERATOR_ID}"
                "?skip=0&limit=100"
            ),
            json=_page(
                "annotations",
                [{"root_id": None, "chunk_id": str(CHUNK_ID), "data": {"a": 1}}],
            ),
        )

        result = client.annotations.list_by_document_and_operator_id(
            DOC_ID, OPERATOR_ID
        )

        assert result.annotations[0].root_id is None
        assert result.annotations[0].data == {"a": 1}

    def test_by_document_compact_items(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/annotations/document/{DOC_ID}"
                "?operator_name=topics&skip=0&limit=100"
            ),
            json=_page(
                "annotations",
                [
                    {
                        "root_id": str(ROOT_ID),
                        "operator_id": str(OPERATOR_ID),
                        "operator_name": "topics",
                        "confidence_score": None,
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ],
            ),
        )

        result = client.annotations.list_by_document(DOC_ID, operator_name="topics")

        item = result.annotations[0]
        assert item.operator_name == "topics"
        assert item.data is None
