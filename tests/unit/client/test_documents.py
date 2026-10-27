"""Tests for the document section: listing filters, metadata, and ingest changes."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from ragnerock.client import RagnerockClient
from ragnerock.client.documents import (
    DocumentFilterField,
    DocumentSortField,
    FilterOperator,
    SortOrder,
)
from ragnerock.errors import NotFoundError
from ragnerock.resources.document import DocumentStatus
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

DOC_ID = uuid.UUID("00000000-0000-4000-8000-000000000101")
DOC_2 = uuid.UUID("00000000-0000-4000-8000-000000000102")
GROUP_ID = uuid.UUID("00000000-0000-4000-8000-000000000201")
CONFIG_ID = "00000000-0000-4000-8000-000000000301"
RUN_ID = "00000000-0000-4000-8000-000000000401"
SOURCE_ID = "00000000-0000-4000-8000-000000000501"

_EMPTY_PAGE: dict[str, Any] = {"documents": [], "total": 0, "skip": 0, "limit": 100}


def _document(doc_id: uuid.UUID = DOC_ID, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(doc_id),
        "project_id": PROJECT_ID,
        "group_id": str(GROUP_ID),
        "created_by_id": None,
        "name": "report.pdf",
        "storage_path": "projects/demo/report.pdf",
        "source_url": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "filesize": 1024,
        "file_type": 3,
        "status": "ready",
        "is_sample": False,
    }
    payload.update(overrides)
    return payload


def _change(doc_id: uuid.UUID = DOC_ID) -> dict[str, Any]:
    return {
        "document_id": str(doc_id),
        "config_id": CONFIG_ID,
        "config_name": "Nightly crawl",
        "source_id": SOURCE_ID,
        "run_id": RUN_ID,
        "changed_at": "2026-03-01T08:00:00Z",
        "detail": {"kind": "web", "change": "updated"},
    }


_DOCS_URL = re.compile(re.escape(url("/api/documents/")) + r"\?.*")


class TestList:
    def test_defaults_send_only_the_page_and_the_id_order(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/documents/?skip=0&limit=100&sort_by=id&sort_order=asc"),
            json=_EMPTY_PAGE,
        )

        result = client.documents.list()

        assert result.documents == []
        assert result.total == 0

    def test_sends_scope_sort_filters_and_time_zone(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(method="GET", url=_DOCS_URL, json=_EMPTY_PAGE)

        client.documents.list(
            project_ids=PROJECT_ID,
            limit=25,
            group_id=GROUP_ID,
            name="acme",
            filters=[
                {
                    "field": DocumentFilterField.FILESIZE,
                    "operator": FilterOperator.GT,
                    "value": 1024,
                    "value2": None,
                }
            ],
            time_zone="Europe/Paris",
            sort_by=DocumentSortField.CREATED_AT,
            sort_order=SortOrder.DESC,
        )

        params = last_params(httpx_mock)
        assert last_request(httpx_mock).url.path == "/api/documents/"
        assert params["project_ids"] == PROJECT_ID
        assert params["group_id"] == str(GROUP_ID)
        assert params["limit"] == "25"
        assert params["name"] == "acme"
        assert json.loads(params["filters"]) == [
            {"field": "filesize", "operator": "gt", "value": 1024, "value2": None}
        ]
        assert params["timezone"] == "Europe/Paris"
        assert params["sort_by"] == "created_at"
        assert params["sort_order"] == "desc"
        assert "ungrouped" not in params
        assert "is_sample" not in params

    def test_plain_string_sort_values_are_accepted(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(method="GET", url=_DOCS_URL, json=_EMPTY_PAGE)

        client.documents.list(sort_by="name", sort_order="desc")

        params = last_params(httpx_mock)
        assert params["sort_by"] == "name"
        assert params["sort_order"] == "desc"

    def test_statuses_repeat_the_parameter(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(method="GET", url=_DOCS_URL, json=_EMPTY_PAGE)

        client.documents.list(
            project_ids=PROJECT_ID,
            statuses=[DocumentStatus.ERROR, DocumentStatus.PENDING],
        )

        assert last_request(httpx_mock).url.params.get_list("statuses") == [
            "error",
            "pending",
        ]

    def test_ungrouped_and_is_sample(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(method="GET", url=_DOCS_URL, json=_EMPTY_PAGE)

        client.documents.list(ungrouped=True, is_sample=False)

        params = last_params(httpx_mock)
        assert params["ungrouped"] == "true"
        assert params["is_sample"] == "false"

    def test_parses_document_fields(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=_DOCS_URL,
            json={"documents": [_document()], "total": 1, "skip": 0, "limit": 100},
        )

        doc = client.documents.list().documents[0]

        assert doc.id == DOC_ID
        assert doc.group_id == GROUP_ID
        assert doc.file_type == 3
        assert doc.status == "ready"
        assert doc.filesize == 1024
        assert doc.created_at == datetime(2026, 1, 1, tzinfo=UTC)


class TestListByGroup:
    def test_sends_filters_to_the_group_route(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=re.compile(
                re.escape(url(f"/api/documents/group/{GROUP_ID}")) + r"\?.*"
            ),
            json=_EMPTY_PAGE,
        )

        client.documents.list_by_group(
            GROUP_ID,
            skip=50,
            filters=[{"field": "name", "operator": "contains", "value": "10-K"}],
            is_sample=True,
            statuses=["ready"],
        )

        params = last_params(httpx_mock)
        assert last_request(httpx_mock).url.path == f"/api/documents/group/{GROUP_ID}"
        assert params["skip"] == "50"
        assert json.loads(params["filters"])[0]["value"] == "10-K"
        assert params["is_sample"] == "true"
        assert params["statuses"] == "ready"
        assert params["sort_by"] == "id"
        # Scope parameters belong to the project-wide listing only.
        assert "project_ids" not in params
        assert "group_id" not in params

    def test_defaults(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/documents/group/{GROUP_ID}"
                "?skip=0&limit=100&sort_by=id&sort_order=asc"
            ),
            json=_EMPTY_PAGE,
        )

        assert client.documents.list_by_group(GROUP_ID).total == 0


class TestMetadata:
    def test_get_metadata(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/documents/{DOC_ID}/metadata"),
            json={
                "metadata": [
                    {"key": "author", "val": "Ada", "dtype": "str"},
                    {"key": "pages", "val": "12", "dtype": "int"},
                ]
            },
        )

        result = client.documents.get_metadata(DOC_ID)

        assert last_request(httpx_mock).method == "GET"
        assert [(m.key, m.val, m.dtype) for m in result.metadata] == [
            ("author", "Ada", "str"),
            ("pages", "12", "int"),
        ]

    def test_delete_metadata_key(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/documents/{DOC_ID}/metadata/author"),
            json={"message": "deleted"},
        )

        assert client.documents.delete_metadata_key(DOC_ID, "author") is None
        assert last_request(httpx_mock).method == "DELETE"

    def test_delete_metadata(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/documents/{DOC_ID}/metadata"),
            json={"message": "deleted"},
        )

        assert client.documents.delete_metadata(DOC_ID) is None
        assert last_request(httpx_mock).url.path == f"/api/documents/{DOC_ID}/metadata"

    def test_missing_key_raises(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/documents/{DOC_ID}/metadata/nope"),
            status_code=404,
            json={"detail": "Metadata key not found"},
        )

        with pytest.raises(NotFoundError):
            client.documents.delete_metadata_key(DOC_ID, "nope")


class TestIngestChanges:
    def test_get_ingest_change(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/documents/{DOC_ID}/ingest-change"),
            json=_change(),
        )

        change = client.documents.get_ingest_change(DOC_ID)

        assert change.document_id == DOC_ID
        assert change.config_name == "Nightly crawl"
        assert change.run_id == uuid.UUID(RUN_ID)
        assert change.changed_at == datetime(2026, 3, 1, 8, tzinfo=UTC)
        assert change.detail == {"kind": "web", "change": "updated"}

    def test_get_ingest_change_not_found(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/documents/{DOC_ID}/ingest-change"),
            status_code=404,
            json={"detail": "No ingest change"},
        )

        with pytest.raises(NotFoundError):
            client.documents.get_ingest_change(DOC_ID)

    def test_get_ingest_changes_posts_ids_and_keys_by_document(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/documents/ingest-change/batch"),
            json={str(DOC_ID): _change(DOC_ID)},
        )

        result = client.documents.get_ingest_changes([DOC_ID, DOC_2])

        assert last_json(httpx_mock) == {"document_ids": [str(DOC_ID), str(DOC_2)]}
        # Documents with no ingest change are simply absent.
        assert list(result) == [str(DOC_ID)]
        assert result[str(DOC_ID)].config_id == uuid.UUID(CONFIG_ID)

    def test_get_ingest_changes_empty_input_skips_the_request(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        assert client.documents.get_ingest_changes([]) == {}
        assert httpx_mock.get_requests() == []


class TestGetJob:
    def test_parses_job_fields(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/documents/{DOC_ID}/job"),
            json={
                "id": "00000000-0000-4000-8000-000000000801",
                "document_id": str(DOC_ID),
                "status": 2,
                "status_message": None,
                "job_type": 1,
                "phase": "parsing",
                "end_time": "",
            },
        )

        job = client.documents.get_job(DOC_ID)

        assert job.document_id == DOC_ID
        assert job.phase == "parsing"
        assert job.end_time is None
