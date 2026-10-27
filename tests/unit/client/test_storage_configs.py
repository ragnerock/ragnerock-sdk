"""Tests for the database and blob storage config sections."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from ragnerock.client import MessageResponse, RagnerockClient
from ragnerock.client.storage_configs import (
    BLOB_VALIDATE_TIMEOUT,
    BlobProviderType,
    DBProviderType,
)
from ragnerock.errors import AuthenticationError, NotFoundError, RagnerockError
from tests.unit.client.conftest import last_json, last_request, url

CONFIG_ID = uuid.UUID("7f3c2a55-8a44-4a4c-9d1f-0d2c8f2b9e10")
BLOB_ID = uuid.UUID("00000000-0000-4000-8000-0000000000b1")

_KERBEROS_URL = (
    "db2://app%40EXAMPLE.COM@db2.example.com:50001/BLUDB?auth=kerberos"
    "&service_principal=db2inst1%2Fdb2.example.com%40EXAMPLE.COM"
)
_CA_PEM = "-----BEGIN CERTIFICATE-----\nMIIBca\n-----END CERTIFICATE-----\n"
_KEYTAB = "BQIAAABHAAIADkVYQU1QTEUuQ09NAANhcHA="
_UNAVAILABLE = "This deployment doesn't include Db2 support."


def _db_config_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(CONFIG_ID),
        "config_name": "Warehouse",
        "provider_type": "postgresql",
        "connection_string_masked": "postgresql://u:***@db:5432/d",
        "schema_name": None,
        "is_active": True,
        "is_validated": True,
        "last_connected_at": "2026-09-01T00:00:00Z",
        "last_connection_error": None,
        "consecutive_failures": 0,
        "connection_health": "healthy",
        "failure_streak_started_at": None,
        "bigquery_config": None,
        "credential_files": [],
    }
    payload.update(overrides)
    return payload


def _blob_config_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(CONFIG_ID),
        "config_name": "Archive",
        "provider_type": "s3",
        "bucket_name": "my-bucket",
        "region": "us-east-1",
        "path_prefix": "ragnerock/data/",
        "credentials_hint": "s3://my-bucket (AKIA...)",
        "is_active": False,
        "is_validated": True,
        "last_connected_at": None,
        "last_connection_error": None,
        "consecutive_failures": 0,
        "connection_health": "healthy",
        "failure_streak_started_at": None,
        "created_at": "2026-09-01T00:00:00Z",
        "provider_config": {"endpoint_url": "https://s3.example.com"},
    }
    payload.update(overrides)
    return payload


# -- database configs ----------------------------------------------------------


class TestDBCreate:
    def test_sends_the_settings_and_credential_files(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/db-configs/"),
            json={"id": str(CONFIG_ID), "message": "created"},
        )
        files = {"ca_cert_pem": _CA_PEM, "keytab_base64": _KEYTAB}

        created = client.db_configs.create(
            provider_type=DBProviderType.DB2,
            connection_string=_KERBEROS_URL,
            config_name="Db2",
            schema_name="RGNK",
            credential_files=files,
        )

        assert last_json(httpx_mock) == {
            "provider_type": "db2",
            "connection_string": _KERBEROS_URL,
            "config_name": "Db2",
            "schema_name": "RGNK",
            "credential_files": files,
        }
        assert created.id == CONFIG_ID
        assert created.message == "created"

    def test_without_files_omits_them(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/db-configs/"),
            json={"id": str(CONFIG_ID), "message": "ok"},
        )

        client.db_configs.create(
            provider_type="postgresql",
            connection_string="postgresql://u:p@db.example.com:5432/d",
        )

        assert last_json(httpx_mock) == {
            "provider_type": "postgresql",
            "connection_string": "postgresql://u:p@db.example.com:5432/d",
        }

    def test_create_bigquery_nests_the_bigquery_settings(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/db-configs/bigquery"),
            json={"id": str(CONFIG_ID), "message": "created"},
        )

        result = client.db_configs.create_bigquery(
            gcp_project_id="proj",
            dataset_name="ds",
            credentials_json='{"type": "service_account"}',
            config_name="BQ",
        )

        assert last_json(httpx_mock) == {
            "config_name": "BQ",
            "bigquery_config": {
                "gcp_project_id": "proj",
                "dataset_name": "ds",
                "credentials_json": '{"type": "service_account"}',
            },
        }
        assert result.id == CONFIG_ID

    def test_create_ephemeral(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/db-configs/ephemeral"),
            json={"id": str(CONFIG_ID), "message": "created"},
        )

        result = client.db_configs.create_ephemeral(
            blob_config_id=BLOB_ID, config_name="Ephemeral"
        )

        assert last_json(httpx_mock) == {
            "blob_config_id": str(BLOB_ID),
            "config_name": "Ephemeral",
        }
        assert result.id == CONFIG_ID


class TestDBProviders:
    def test_parses_providers_and_auth_methods(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        always = {"available": True, "reason": None, "auth_methods": []}
        httpx_mock.add_response(
            method="GET",
            url=url("/api/db-configs/providers"),
            json={
                "providers": [
                    {
                        "provider_type": "postgresql",
                        "byodb": always,
                        "sql_ingest": always,
                    },
                    {
                        "provider_type": "db2",
                        "byodb": {
                            "available": True,
                            "reason": None,
                            "auth_methods": [
                                {"method": "password", "available": True},
                                {
                                    "method": "kerberos",
                                    "available": False,
                                    "reason": "No Kerberos here.",
                                },
                            ],
                        },
                        "sql_ingest": {"available": False, "reason": _UNAVAILABLE},
                    },
                ]
            },
        )

        listing = client.db_configs.providers()

        assert last_request(httpx_mock).method == "GET"
        postgres, db2 = listing.providers
        assert postgres.provider_type == DBProviderType.POSTGRESQL
        assert postgres.byodb is not None
        assert postgres.byodb.available is True
        assert postgres.byodb.auth_methods == []
        assert db2.provider_type == DBProviderType.DB2
        assert db2.byodb is not None
        by_method = {m.method: m for m in db2.byodb.auth_methods}
        assert by_method["kerberos"].available is False
        assert by_method["kerberos"].reason == "No Kerberos here."
        assert by_method["password"].available is True
        assert db2.sql_ingest is not None
        assert db2.sql_ingest.available is False
        assert db2.sql_ingest.reason == _UNAVAILABLE

    def test_error_is_raised(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/db-configs/providers"),
            status_code=502,
            json={"detail": "Bad gateway"},
        )

        with pytest.raises(RagnerockError, match="Bad gateway"):
            client.db_configs.providers()


class TestDBReadAndUpdate:
    def test_list(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/db-configs/"),
            json={
                "configs": [_db_config_payload()],
                "total": 1,
                "skip": 0,
                "limit": 100,
            },
        )

        result = client.db_configs.list()

        (config,) = result.configs
        assert config.id == CONFIG_ID
        assert config.is_active is True
        assert config.connection_health == "healthy"
        assert config.last_connected_at is not None
        assert result.total == 1

    def test_get_parses_bigquery_and_credential_files(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/db-configs/{CONFIG_ID}"),
            json=_db_config_payload(
                provider_type="bigquery",
                bigquery_config={
                    "gcp_project_id": "proj",
                    "dataset_name": "ds",
                    "dataset_location": "US",
                },
                credential_files=["keytab"],
            ),
        )

        config = client.db_configs.get(CONFIG_ID)

        assert config.provider_type == DBProviderType.BIGQUERY
        assert config.bigquery_config is not None
        assert config.bigquery_config.dataset_location == "US"
        assert config.credential_files == ["keytab"]

    def test_get_missing_raises_not_found(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/db-configs/{CONFIG_ID}"),
            status_code=404,
            json={"detail": "missing"},
        )

        with pytest.raises(NotFoundError):
            client.db_configs.get(CONFIG_ID)

    def test_update_with_only_a_keytab(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/db-configs/{CONFIG_ID}"),
            json={"id": str(CONFIG_ID), "message": "updated"},
        )

        result = client.db_configs.update(
            CONFIG_ID, credential_files={"keytab_base64": _KEYTAB}
        )

        assert last_json(httpx_mock) == {"credential_files": {"keytab_base64": _KEYTAB}}
        assert result.message == "updated"

    def test_update_without_files_keeps_them(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/db-configs/{CONFIG_ID}"),
            json={"id": str(CONFIG_ID), "message": "updated"},
        )

        client.db_configs.update(CONFIG_ID, config_name="Renamed")

        assert last_json(httpx_mock) == {"config_name": "Renamed"}

    def test_update_empty_files_clears_them(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/db-configs/{CONFIG_ID}"),
            json={"id": str(CONFIG_ID), "message": "updated"},
        )

        client.db_configs.update(CONFIG_ID, credential_files={})

        assert last_json(httpx_mock) == {"credential_files": {}}

    def test_update_bigquery(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/db-configs/{CONFIG_ID}/bigquery"),
            json={"id": str(CONFIG_ID), "message": "updated"},
        )

        result = client.db_configs.update_bigquery(CONFIG_ID, dataset_location="EU")

        assert last_json(httpx_mock) == {"dataset_location": "EU"}
        assert result.id == CONFIG_ID


class TestDBLifecycle:
    def test_delete(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/db-configs/{CONFIG_ID}"),
            json={"message": "deleted"},
        )

        assert client.db_configs.delete(CONFIG_ID) is None
        assert last_request(httpx_mock).method == "DELETE"

    def test_delete_active_config_raises(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/db-configs/{CONFIG_ID}"),
            status_code=400,
            json={"detail": "Cannot delete an active configuration"},
        )

        with pytest.raises(RagnerockError, match="Cannot delete an active"):
            client.db_configs.delete(CONFIG_ID)

    @pytest.mark.parametrize(
        ("method_name", "suffix"),
        [
            ("initialize", "initialize"),
            ("validate", "initialize"),
            ("activate", "activate"),
            ("deactivate", "deactivate"),
        ],
    )
    def test_actions_put_to_their_endpoint(
        self,
        client: RagnerockClient,
        httpx_mock: Any,
        method_name: str,
        suffix: str,
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/db-configs/{CONFIG_ID}/{suffix}"),
            json={"message": f"{suffix} ok"},
        )

        result = getattr(client.db_configs, method_name)(CONFIG_ID)

        assert isinstance(result, MessageResponse)
        assert result.message == f"{suffix} ok"
        assert last_request(httpx_mock).content == b""

    def test_health(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/db-configs/{CONFIG_ID}/health"),
            json={
                "config_id": str(CONFIG_ID),
                "is_healthy": False,
                "last_connected_at": "2026-09-01T00:00:00Z",
                "last_connection_error": "timeout",
                "consecutive_failures": 3,
                "is_active": True,
                "connection_health": "unhealthy",
                "failure_streak_started_at": "2026-09-02T00:00:00Z",
                "recorded": True,
            },
        )

        health = client.db_configs.health(CONFIG_ID)

        assert health.config_id == CONFIG_ID
        assert health.is_healthy is False
        assert health.consecutive_failures == 3
        assert health.connection_health == "unhealthy"
        assert health.failure_streak_started_at is not None
        assert health.recorded is True


# -- blob storage configs ------------------------------------------------------


class TestBlobCreateAndRead:
    def test_create_sends_settings_with_default_prefix(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/blob-configs/"),
            json={"id": str(CONFIG_ID), "message": "created"},
        )

        result = client.blob_configs.create(
            provider_type=BlobProviderType.S3,
            bucket_name="my-bucket",
            credentials={"access_key_id": "AKIA", "secret_access_key": "s"},
            region="us-east-1",
            provider_config={"endpoint_url": "https://s3.example.com"},
        )

        assert last_json(httpx_mock) == {
            "provider_type": "s3",
            "bucket_name": "my-bucket",
            "credentials": {"access_key_id": "AKIA", "secret_access_key": "s"},
            "region": "us-east-1",
            "path_prefix": "ragnerock/data/",
            "provider_config": {"endpoint_url": "https://s3.example.com"},
        }
        assert result.id == CONFIG_ID

    def test_list(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/blob-configs/"),
            json={
                "configs": [_blob_config_payload()],
                "total": 1,
                "skip": 0,
                "limit": 100,
            },
        )

        (config,) = client.blob_configs.list().configs

        assert config.id == CONFIG_ID
        assert config.provider_type == BlobProviderType.S3
        assert config.provider_config == {"endpoint_url": "https://s3.example.com"}
        assert config.created_at is not None

    def test_get(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/blob-configs/{CONFIG_ID}"),
            json=_blob_config_payload(),
        )

        config = client.blob_configs.get(CONFIG_ID)

        assert config.bucket_name == "my-bucket"
        assert config.is_validated is True


class TestBlobUpdate:
    """``update`` routes credentials and settings to separate endpoints."""

    def test_settings_only_hit_the_config_endpoint(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/blob-configs/{CONFIG_ID}"),
            json={"id": str(CONFIG_ID), "message": "updated"},
        )

        result = client.blob_configs.update(
            CONFIG_ID, config_name="archive", path_prefix="data/"
        )

        assert len(httpx_mock.get_requests()) == 1
        assert last_json(httpx_mock) == {
            "config_name": "archive",
            "path_prefix": "data/",
        }
        assert result.message == "updated"

    def test_bucket_name_alone_is_sent(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/blob-configs/{CONFIG_ID}"),
            json={"id": str(CONFIG_ID), "message": "Config requires re-validation."},
        )

        result = client.blob_configs.update(CONFIG_ID, bucket_name="new-bucket")

        assert last_json(httpx_mock) == {"bucket_name": "new-bucket"}
        assert result.message is not None
        assert "re-validation" in result.message

    def test_credentials_only_hit_the_credentials_endpoint(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/blob-configs/{CONFIG_ID}/credentials"),
            json={"id": str(CONFIG_ID), "message": "rotated"},
        )

        result = client.blob_configs.update(CONFIG_ID, credentials={"key": "secret"})

        assert len(httpx_mock.get_requests()) == 1
        assert last_json(httpx_mock) == {"credentials": {"key": "secret"}}
        assert result.message == "rotated"

    def test_credentials_and_settings_hit_both_endpoints(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/blob-configs/{CONFIG_ID}/credentials"),
            json={"id": str(CONFIG_ID), "message": "rotated"},
        )
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/blob-configs/{CONFIG_ID}"),
            json={"id": str(CONFIG_ID), "message": "updated"},
        )

        result = client.blob_configs.update(
            CONFIG_ID, region="us-east-1", credentials={"key": "secret"}
        )

        paths = [r.url.path for r in httpx_mock.get_requests()]
        assert paths == [
            f"/api/blob-configs/{CONFIG_ID}/credentials",
            f"/api/blob-configs/{CONFIG_ID}",
        ]
        assert last_json(httpx_mock) == {"region": "us-east-1"}
        assert result.message == "updated"

    def test_no_changes_still_calls_update(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/blob-configs/{CONFIG_ID}"),
            json={"id": str(CONFIG_ID), "message": "noop"},
        )

        result = client.blob_configs.update(CONFIG_ID)

        assert last_json(httpx_mock) == {}
        assert result.message == "noop"

    def test_credentials_failure_stops_before_settings(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/blob-configs/{CONFIG_ID}/credentials"),
            status_code=403,
            json={"detail": "Only owners can update credentials"},
        )

        with pytest.raises(AuthenticationError):
            client.blob_configs.update(
                CONFIG_ID, config_name="x", credentials={"key": "secret"}
            )
        assert len(httpx_mock.get_requests()) == 1


class TestBlobLifecycle:
    def test_delete(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/blob-configs/{CONFIG_ID}"),
            json={"message": "ok"},
        )

        assert client.blob_configs.delete(CONFIG_ID) is None
        assert last_request(httpx_mock).method == "DELETE"

    def test_delete_active_config_raises(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/blob-configs/{CONFIG_ID}"),
            status_code=400,
            json={"detail": "Cannot delete an active configuration"},
        )

        with pytest.raises(RagnerockError, match="Cannot delete an active") as caught:
            client.blob_configs.delete(CONFIG_ID)
        assert caught.value.status_code == 400

    def test_validate_posts_with_the_extended_timeout(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/blob-configs/{CONFIG_ID}/validate"),
            json={
                "is_valid": True,
                "can_write": True,
                "can_read": True,
                "can_delete": True,
                "error_message": None,
                "message": "Validated",
            },
        )

        result = client.blob_configs.validate(CONFIG_ID)

        request = last_request(httpx_mock)
        assert request.extensions["timeout"]["read"] == BLOB_VALIDATE_TIMEOUT
        assert result.is_valid is True
        assert result.can_delete is True
        assert result.message == "Validated"

    @pytest.mark.parametrize("action", ["activate", "deactivate"])
    def test_activation_puts_to_its_endpoint(
        self, client: RagnerockClient, httpx_mock: Any, action: str
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/blob-configs/{CONFIG_ID}/{action}"),
            json={"message": f"{action} ok", "id": str(CONFIG_ID)},
        )

        result = getattr(client.blob_configs, action)(CONFIG_ID)

        assert isinstance(result, MessageResponse)
        assert result.message == f"{action} ok"

    @pytest.mark.parametrize(
        ("action", "method"),
        [("validate", "POST"), ("activate", "PUT"), ("deactivate", "PUT")],
    )
    def test_not_found_raises(
        self, client: RagnerockClient, httpx_mock: Any, action: str, method: str
    ) -> None:
        httpx_mock.add_response(
            method=method,
            url=url(f"/api/blob-configs/{CONFIG_ID}/{action}"),
            status_code=404,
            json={"detail": "missing"},
        )

        with pytest.raises(NotFoundError):
            getattr(client.blob_configs, action)(CONFIG_ID)
