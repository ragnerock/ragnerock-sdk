"""Tests for the ingest sources section (:mod:`ragnerock.client.ingest`)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from ragnerock.client import RagnerockClient
from ragnerock.client.ingest import SQL_PREVIEW_TIMEOUT_SECONDS, IngestRunResponse
from ragnerock.enums import IngestRunStatus, IngestRunTrigger, IngestSourceType
from ragnerock.errors import NotFoundError, RagnerockError, ValidationError
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

NOW = "2026-10-01T12:00:00Z"
CONNECTION = "postgresql://ingest_ro:hunter2@db.example.com:5432/sales"
CA_PEM = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"


def _page(*items: dict[str, Any], skip: int = 0, limit: int = 100) -> dict[str, Any]:
    return {"items": list(items), "total": len(items), "skip": skip, "limit": limit}


def _source(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "project_id": PROJECT_ID,
        "name": "filings",
        "source_type": "S3",
        "detail": {"source_type": "S3", "bucket": "filings", "prefix": "10-K/"},
        "created_at": NOW,
        "entries_count": 3,
    }
    payload.update(overrides)
    return payload


def _run(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "source_id": str(uuid.uuid4()),
        "config_id": str(uuid.uuid4()),
        "project_id": PROJECT_ID,
        "status": "QUEUED",
        "trigger": "MANUAL",
        "created_at": NOW,
    }
    payload.update(overrides)
    return payload


def _config(source: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "project_id": PROJECT_ID,
        "ingest_source_id": str(uuid.uuid4()),
        "name": "filings",
        "cron": None,
        "source": source,
        "document_group_id": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload.update(overrides)
    return payload


def _s3_view() -> dict[str, Any]:
    return {
        "source_type": "S3",
        "bucket": "valid-bucket",
        "region": None,
        "prefix": "10-K/",
        "recursive": True,
        "file_patterns": [],
        "endpoint_url": None,
        "is_public": False,
        "max_objects": 1000,
        "max_object_bytes": 12345,
        "credentials_configured": True,
    }


def _sql_source() -> dict[str, Any]:
    """A SQL source with a password and an uploaded CA certificate."""
    return {
        "source_type": IngestSourceType.SQL,
        "connection_string": CONNECTION,
        "query": "SELECT id, name FROM customers",
        "key_columns": ["id"],
        "duplicate_key_policy": "KEEP_FIRST",
        "ca_cert_pem": CA_PEM,
    }


def _preview() -> dict[str, Any]:
    return {
        "dialect": "postgresql",
        "columns": [
            {"name": "id", "dtype": "integer"},
            {"name": "name", "dtype": "string"},
        ],
        "rows": [{"id": 1, "name": "Ada"}, {"id": 2, "name": None}],
        "truncated": True,
        "suggested_key_columns": ["id"],
        "warnings": [{"kind": "NO_ORDER_BY", "message": "Add an ORDER BY."}],
        "query_duration_ms": 12,
    }


class TestSources:
    def test_list_filters_by_source_type(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/sources/{PROJECT_ID}?skip=0&limit=100&source_type=S3"),
            json=_page(_source()),
        )

        listed = client.ingest_sources.list(
            uuid.UUID(PROJECT_ID), source_type=IngestSourceType.S3
        )

        assert last_params(httpx_mock)["source_type"] == "S3"
        assert listed.total == 1
        source = listed.items[0]
        assert source.source_type == IngestSourceType.S3
        assert source.detail is not None and source.detail["bucket"] == "filings"
        assert source.entries_count == 3

    def test_list_without_a_filter(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/sources/{PROJECT_ID}?skip=20&limit=10"),
            json=_page(skip=20, limit=10),
        )

        listed = client.ingest_sources.list(uuid.UUID(PROJECT_ID), skip=20, limit=10)

        assert "source_type" not in last_params(httpx_mock)
        assert (listed.skip, listed.limit) == (20, 10)

    def test_get(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        payload = _source(
            source_type="SQL",
            detail={
                "source_type": "SQL",
                "dialect": "postgresql",
                "connection_hint": "postgresql://db.example.com/sales",
                "row_count": 42,
            },
        )
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/sources/{PROJECT_ID}/{payload['id']}"),
            json=payload,
        )

        source = client.ingest_sources.get(
            uuid.UUID(PROJECT_ID), uuid.UUID(payload["id"])
        )

        assert str(source.id) == payload["id"]
        assert source.detail is not None and source.detail["row_count"] == 42

    def test_list_entries(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        source_id = uuid.uuid4()
        entry = {
            "id": str(uuid.uuid4()),
            "source_id": str(source_id),
            "external_id": "10-K/acme.pdf",
            "name": "acme.pdf",
            "content_type": "application/pdf",
            "versions_count": 2,
            "removed_at": None,
        }
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/ingest/sources/{PROJECT_ID}/{source_id}/entries?skip=0&limit=100"
            ),
            json=_page(entry),
        )

        listed = client.ingest_sources.list_entries(uuid.UUID(PROJECT_ID), source_id)

        assert listed.items[0].external_id == "10-K/acme.pdf"
        assert listed.items[0].versions_count == 2

    def test_list_versions(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        entry_id, run_id, document_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        version = {
            "id": str(uuid.uuid4()),
            "entry_id": str(entry_id),
            "run_id": str(run_id),
            "document_id": str(document_id),
            "parent_version_id": None,
            "change": "MODIFIED",
            "detail": {"source_type": "S3", "size_bytes": 10},
            "created_at": NOW,
        }
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/entries/{PROJECT_ID}/{entry_id}/versions?skip=0&limit=5"),
            json=_page(version, limit=5),
        )

        listed = client.ingest_sources.list_versions(
            uuid.UUID(PROJECT_ID), entry_id, limit=5
        )

        assert listed.items[0].change == "MODIFIED"
        assert listed.items[0].document_id == document_id


class TestRuns:
    def test_list_runs_for_a_source(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        source_id = uuid.uuid4()
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/sources/{PROJECT_ID}/{source_id}/runs?skip=0&limit=100"),
            json=_page(_run(source_id=str(source_id))),
        )

        listed = client.ingest_sources.list_runs(uuid.UUID(PROJECT_ID), source_id)

        assert listed.items[0].source_id == source_id

    def test_list_project_runs(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/runs/{PROJECT_ID}?skip=0&limit=100"),
            json=_page(_run(), _run(status="COMPLETED")),
        )

        listed = client.ingest_sources.list_project_runs(uuid.UUID(PROJECT_ID))

        assert [run.status for run in listed.items] == [
            IngestRunStatus.QUEUED,
            IngestRunStatus.COMPLETED,
        ]

    def test_get_run_parses_counts_and_error(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        payload = _run(
            status="FAILED",
            counts={
                "added": 2,
                "modified": 1,
                "unchanged": 5,
                "removed": 0,
                "errored": 1,
            },
            error={
                "reason": "CONNECTION_FAILED",
                "category": "TRANSIENT",
                "message": "Couldn't connect to the database.",
            },
        )
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/runs/{PROJECT_ID}/{payload['id']}"),
            json=payload,
        )

        run = client.ingest_sources.get_run(
            uuid.UUID(PROJECT_ID), uuid.UUID(payload["id"])
        )

        assert run.status == IngestRunStatus.FAILED
        assert (run.counts.added, run.counts.errored) == (2, 1)
        assert run.error is not None and run.error.reason == "CONNECTION_FAILED"

    def test_a_queued_run_has_zero_counts(self) -> None:
        run = IngestRunResponse.model_validate(_run())

        assert run.counts.added == 0
        assert run.error is None

    def test_trigger_queues_a_run(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        config_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/ingest/trigger/{PROJECT_ID}/{config_id}"),
            status_code=202,
            json=_run(config_id=str(config_id)),
        )

        run = client.ingest_sources.trigger(uuid.UUID(PROJECT_ID), config_id)

        assert last_request(httpx_mock).content == b""
        assert run.config_id == config_id
        assert run.trigger == IngestRunTrigger.MANUAL

    def test_trigger_while_a_run_is_active_raises(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        config_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/ingest/trigger/{PROJECT_ID}/{config_id}"),
            status_code=409,
            json={
                "detail": {
                    "message": "A run is already in progress.",
                    "active_run_id": str(uuid.uuid4()),
                }
            },
        )

        with pytest.raises(RagnerockError) as exc_info:
            client.ingest_sources.trigger(uuid.UUID(PROJECT_ID), config_id)

        assert exc_info.value.status_code == 409


class TestConfigs:
    def test_create_an_s3_config(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/ingest/configure/{PROJECT_ID}"),
            status_code=201,
            json=_config(_s3_view(), cron="0 * * * *"),
        )

        created = client.ingest_sources.create_config(
            uuid.UUID(PROJECT_ID),
            name="filings",
            cron="0 * * * *",
            source={
                "source_type": "S3",
                "bucket": "valid-bucket",
                "prefix": "10-K/",
                "aws_access_key_id": "AKIA-test",
                "aws_secret_access_key": "very-secret",
            },
        )

        assert last_json(httpx_mock) == {
            "name": "filings",
            "cron": "0 * * * *",
            "source": {
                "source_type": "S3",
                "bucket": "valid-bucket",
                "prefix": "10-K/",
                "aws_access_key_id": "AKIA-test",
                "aws_secret_access_key": "very-secret",
            },
        }
        assert created.cron == "0 * * * *"
        # The response reports whether credentials are stored, never the values.
        assert created.source["credentials_configured"] is True
        assert "aws_secret_access_key" not in created.source

    def test_create_without_a_schedule_sends_no_cron(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/ingest/configure/{PROJECT_ID}"),
            json=_config({"source_type": "WEB_SCRAPE", "url": "https://example.com"}),
        )

        created = client.ingest_sources.create_config(
            uuid.UUID(PROJECT_ID),
            name="site",
            source={"source_type": "WEB_SCRAPE", "url": "https://example.com"},
        )

        assert "cron" not in last_json(httpx_mock)
        assert created.cron is None

    @pytest.mark.parametrize("method", ["create_config", "update_config"])
    def test_sql_secrets_reach_the_api(
        self, client: RagnerockClient, httpx_mock: HTTPXMock, method: str
    ) -> None:
        config_id = uuid.uuid4()
        httpx_mock.add_response(
            url=url(
                f"/ingest/configure/{PROJECT_ID}"
                + (f"/{config_id}" if method == "update_config" else "")
            ),
            status_code=400,
            json={"detail": "stop here"},
        )

        with pytest.raises(RagnerockError, match="stop here"):
            if method == "create_config":
                client.ingest_sources.create_config(
                    uuid.UUID(PROJECT_ID), name="customers", source=_sql_source()
                )
            else:
                client.ingest_sources.update_config(
                    uuid.UUID(PROJECT_ID),
                    config_id,
                    name="customers",
                    source=_sql_source(),
                )

        request = last_request(httpx_mock)
        assert request.method == ("POST" if method == "create_config" else "PUT")
        source = last_json(httpx_mock)["source"]
        assert source["source_type"] == "SQL"
        assert source["connection_string"] == CONNECTION
        assert source["ca_cert_pem"] == CA_PEM
        assert source["duplicate_key_policy"] == "KEEP_FIRST"

    def test_update_can_omit_and_clear_secrets(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        """An update that keeps the connection and clears the CA sends no secrets."""
        config_id = uuid.uuid4()
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/ingest/configure/{PROJECT_ID}/{config_id}"),
            json=_config(
                {
                    "source_type": "SQL",
                    "dialect": "postgresql",
                    "connection_hint": "postgresql://db.example.com/sales",
                    "secrets": {"password_configured": True},
                    "query": "SELECT 1 AS id",
                    "key_columns": [],
                    "duplicate_key_policy": "FAIL",
                    "change_detection_columns": [],
                    "max_rows": 100_000,
                },
                id=str(config_id),
            ),
        )

        updated = client.ingest_sources.update_config(
            uuid.UUID(PROJECT_ID),
            config_id,
            name="customers",
            source={
                "source_type": "SQL",
                "query": "SELECT 1 AS id",
                "clear_ca_cert": True,
            },
        )

        source = last_json(httpx_mock)["source"]
        assert "connection_string" not in source
        assert source["clear_ca_cert"] is True
        assert updated.id == config_id
        assert updated.source["secrets"]["password_configured"] is True

    def test_get_config(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        payload = _config(_s3_view())
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/configure/{PROJECT_ID}/{payload['id']}"),
            json=payload,
        )

        config = client.ingest_sources.get_config(
            uuid.UUID(PROJECT_ID), uuid.UUID(payload["id"])
        )

        assert config.name == "filings"
        assert config.source["bucket"] == "valid-bucket"

    def test_list_configs(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/configure/{PROJECT_ID}?skip=0&limit=100"),
            json=_page(_config(_s3_view())),
        )

        listed = client.ingest_sources.list_configs(uuid.UUID(PROJECT_ID))

        assert listed.total == 1
        assert listed.items[0].source["source_type"] == IngestSourceType.S3

    def test_delete_config(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        config_id = uuid.uuid4()
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/ingest/configure/{PROJECT_ID}/{config_id}"),
            json={"message": "Ingest config deleted"},
        )

        assert (
            client.ingest_sources.delete_config(uuid.UUID(PROJECT_ID), config_id)
            is None
        )

    def test_deleting_a_config_in_use_raises(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        config_id = uuid.uuid4()
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/ingest/configure/{PROJECT_ID}/{config_id}"),
            status_code=409,
            json={
                "detail": {
                    "message": "Workflows still use this config.",
                    "workflows": [],
                }
            },
        )

        with pytest.raises(RagnerockError) as exc_info:
            client.ingest_sources.delete_config(uuid.UUID(PROJECT_ID), config_id)

        assert exc_info.value.status_code == 409


class TestPreviewSql:
    def test_posts_unsaved_settings_with_secrets(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/ingest/sql/preview/{PROJECT_ID}"),
            json=_preview(),
        )

        preview = client.ingest_sources.preview_sql(
            uuid.UUID(PROJECT_ID), source=_sql_source()
        )

        request = last_request(httpx_mock)
        assert request.extensions["timeout"]["read"] == SQL_PREVIEW_TIMEOUT_SECONDS
        body = last_json(httpx_mock)
        assert "config_id" not in body
        assert body["source"]["source_type"] == "SQL"
        assert body["source"]["connection_string"] == CONNECTION
        assert body["source"]["ca_cert_pem"] == CA_PEM
        assert body["source"]["key_columns"] == ["id"]

        assert preview.dialect == "postgresql"
        assert [(c.name, c.dtype) for c in preview.columns] == [
            ("id", "integer"),
            ("name", "string"),
        ]
        assert preview.rows[1] == {"id": 2, "name": None}
        assert preview.truncated is True
        assert preview.suggested_key_columns == ["id"]
        assert preview.warnings[0].kind == "NO_ORDER_BY"
        assert preview.query_duration_ms == 12
        assert preview.estimated_bytes_processed is None

    def test_saved_config_sends_only_its_id(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        config_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/ingest/sql/preview/{PROJECT_ID}"),
            json=_preview(),
        )

        client.ingest_sources.preview_sql(uuid.UUID(PROJECT_ID), config_id=config_id)

        assert last_json(httpx_mock) == {"config_id": str(config_id)}

    def test_refused_query_raises_validation_error(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/ingest/sql/preview/{PROJECT_ID}"),
            status_code=422,
            json={"detail": "The query must only read data."},
        )

        with pytest.raises(ValidationError, match="only read data"):
            client.ingest_sources.preview_sql(
                uuid.UUID(PROJECT_ID), source=_sql_source()
            )

    def test_database_failure_raises(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/ingest/sql/preview/{PROJECT_ID}"),
            status_code=502,
            json={"detail": "Couldn't connect to the database."},
        )

        with pytest.raises(RagnerockError, match="Couldn't connect"):
            client.ingest_sources.preview_sql(
                uuid.UUID(PROJECT_ID), source=_sql_source()
            )


class TestWorkflowBindings:
    def test_list_config_workflows(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        config_id = uuid.uuid4()
        ref = {
            "workflow_id": str(uuid.uuid4()),
            "workflow_name": "filing_review",
            "resource_id": str(uuid.uuid4()),
            "resource_name": "filings",
            "process_mode": "FULL",
            "trigger": False,
        }
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/workflows/{PROJECT_ID}/{config_id}"),
            json=[ref],
        )

        refs = client.ingest_sources.list_config_workflows(
            uuid.UUID(PROJECT_ID), config_id
        )

        assert last_request(httpx_mock).headers["Authorization"] == "Bearer rgnk_test"
        assert [r.workflow_name for r in refs] == ["filing_review"]
        assert refs[0].trigger is False
        assert refs[0].process_mode == "FULL"

    def test_list_workflow_link_notices(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notice = {
            "id": str(uuid.uuid4()),
            "config_id": str(uuid.uuid4()),
            "config_name": "filings",
            "workflow_id": str(uuid.uuid4()),
            "workflow_name": "filing_review",
        }
        httpx_mock.add_response(
            method="GET",
            url=url(f"/ingest/workflow-link-notices/{PROJECT_ID}"),
            json=[notice],
        )

        notices = client.ingest_sources.list_workflow_link_notices(
            uuid.UUID(PROJECT_ID)
        )

        assert [str(n.id) for n in notices] == [notice["id"]]
        assert notices[0].workflow_name == "filing_review"

    @pytest.mark.parametrize("action", ["link", "dismiss"])
    def test_resolving_a_notice_accepts_an_empty_204(
        self, client: RagnerockClient, httpx_mock: HTTPXMock, action: str
    ) -> None:
        notice_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/ingest/workflow-link-notices/{PROJECT_ID}/{notice_id}/{action}"),
            status_code=204,
        )
        method = (
            client.ingest_sources.link_workflow_notice
            if action == "link"
            else client.ingest_sources.dismiss_workflow_notice
        )

        assert method(uuid.UUID(PROJECT_ID), notice_id) is None
        assert last_request(httpx_mock).content == b""

    def test_a_missing_notice_raises(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notice_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/ingest/workflow-link-notices/{PROJECT_ID}/{notice_id}/link"),
            status_code=404,
            json={"detail": "already resolved"},
        )

        with pytest.raises(NotFoundError, match="already resolved"):
            client.ingest_sources.link_workflow_notice(uuid.UUID(PROJECT_ID), notice_id)
