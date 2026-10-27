"""Bring-your-own database and blob storage config endpoints."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from ragnerock.client._base import MessageResponse, _ApiModel, _body, _Section
from ragnerock.timestamps import UtcDatetime

BLOB_VALIDATE_TIMEOUT = 60.0
"""Read timeout, in seconds, for validating a blob storage config.

Validation writes, reads and deletes a test object in the bucket, which can
take longer than an ordinary request.
"""


class DBProviderType(StrEnum):
    """Database providers a database config can point at."""

    POSTGRESQL = "postgresql"
    BIGQUERY = "bigquery"
    SNOWFLAKE = "snowflake"
    DATABRICKS = "databricks"
    ORACLE = "oracle"
    DB2 = "db2"
    """Self-hosted deployments with Db2 support only; check
    ``client.db_configs.providers()``."""


class BlobProviderType(StrEnum):
    """Object storage providers a blob storage config can point at."""

    GCS = "gcs"
    S3 = "s3"
    AZURE = "azure"
    ORACLE = "oracle"


# -- database configs ----------------------------------------------------------


class BigQueryConfigDetail(_ApiModel):
    """BigQuery-specific settings of a database config."""

    gcp_project_id: str | None = None
    dataset_name: str | None = None
    dataset_location: str | None = None


class DBConfigDetail(_ApiModel):
    """A stored database config. Credentials are never returned.

    Attributes:
        id (UUID): Config id.
        config_name (str | None): Friendly name.
        provider_type (str | None): A :class:`DBProviderType` value.
        connection_string_masked (str | None): The connection string with its
            password masked.
        schema_name (str | None): Schema the data lives in.
        is_active (bool): Whether this is the account's active database.
        is_validated (bool): Whether the schema has been initialized.
        last_connected_at (datetime | None): Last successful connection.
        last_connection_error (str | None): Why the last connection failed.
        consecutive_failures (int): Failed connections in a row.
        connection_health (str | None): ``"healthy"`` or ``"unhealthy"`` (after
            a sustained outage).
        failure_streak_started_at (datetime | None): When the current failure
            streak began.
        bigquery_config (BigQueryConfigDetail | None): BigQuery settings, for
            BigQuery configs only.
        credential_files (list[str]): Which credential files the config holds
            (never their contents).
    """

    id: UUID
    config_name: str | None = None
    provider_type: str | None = None
    connection_string_masked: str | None = None
    schema_name: str | None = None
    is_active: bool = False
    is_validated: bool = False
    last_connected_at: UtcDatetime = None
    last_connection_error: str | None = None
    consecutive_failures: int = 0
    connection_health: str | None = None
    failure_streak_started_at: UtcDatetime = None
    bigquery_config: BigQueryConfigDetail | None = None
    credential_files: list[str] = []


class ListDBConfigsResponse(_ApiModel):
    """The account's database configs."""

    configs: list[DBConfigDetail] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class CreateDBConfigResponse(_ApiModel):
    """Result of creating a database config."""

    id: UUID
    message: str | None = None


class UpdateDBConfigResponse(_ApiModel):
    """Result of updating a database config."""

    id: UUID
    message: str | None = None


class DBAuthMethodAvailability(_ApiModel):
    """Whether one of a provider's authentication methods can be used here.

    Attributes:
        method (str): The method, e.g. Db2's ``"password"``, ``"iam"``,
            ``"kerberos"`` or ``"certificate"``.
        available (bool): Whether this deployment supports it.
        reason (str | None): Why not, when it isn't available.
    """

    method: str
    available: bool = False
    reason: str | None = None


class DBProviderAvailability(_ApiModel):
    """Whether a provider can be used for one purpose in this deployment.

    Attributes:
        available (bool): Whether it can be used.
        reason (str | None): Why not, when it can't.
        auth_methods (list[DBAuthMethodAvailability]): Per-method
            availability, for providers with a choice of auth method.
    """

    available: bool = False
    reason: str | None = None
    auth_methods: list[DBAuthMethodAvailability] = []


class DBProviderInfo(_ApiModel):
    """What this deployment supports for one database provider.

    Attributes:
        provider_type (str): A :class:`DBProviderType` value.
        byodb (DBProviderAvailability | None): As the account's data database.
        sql_ingest (DBProviderAvailability | None): As a SQL ingest source.
    """

    provider_type: str
    byodb: DBProviderAvailability | None = None
    sql_ingest: DBProviderAvailability | None = None


class ListDBProvidersResponse(_ApiModel):
    """The database providers this deployment supports."""

    providers: list[DBProviderInfo] = []


class DBHealthCheckResponse(_ApiModel):
    """Result of a database connectivity check.

    Attributes:
        config_id (UUID): The checked config.
        is_healthy (bool): Whether the connection succeeded.
        last_connected_at (datetime | None): Last successful connection.
        last_connection_error (str | None): Why the latest failed check failed.
        consecutive_failures (int): Failed connections in a row.
        is_active (bool): Whether the config is the account's active one. A
            health check never changes it.
        connection_health (str | None): ``"healthy"`` or ``"unhealthy"``.
        failure_streak_started_at (datetime | None): When the current failure
            streak began.
        recorded (bool): Whether this check updated the config's stored
            health. Checks by callers who can't manage the config are
            read-only.
    """

    config_id: UUID
    is_healthy: bool = False
    last_connected_at: UtcDatetime = None
    last_connection_error: str | None = None
    consecutive_failures: int = 0
    is_active: bool = False
    connection_health: str | None = None
    failure_streak_started_at: UtcDatetime = None
    recorded: bool = False


# -- blob storage configs ------------------------------------------------------


class BlobConfigDetail(_ApiModel):
    """A stored blob storage config. Credentials are never returned.

    Attributes:
        id (UUID): Config id.
        config_name (str | None): Friendly name.
        provider_type (str | None): A :class:`BlobProviderType` value.
        bucket_name (str | None): Bucket or container.
        region (str | None): Bucket region.
        path_prefix (str | None): Prefix for every stored object.
        credentials_hint (str | None): Masked description of the stored
            credentials.
        provider_config (dict[str, Any]): Non-secret provider settings, such
            as an S3-compatible ``endpoint_url``.
        is_active (bool): Whether new uploads go to this storage.
        is_validated (bool): Whether the bucket passed validation.
        last_connected_at (datetime | None): Last successful connection.
        last_connection_error (str | None): Why the last connection failed.
        consecutive_failures (int): Failed connections in a row.
        connection_health (str | None): ``"healthy"`` or ``"unhealthy"``.
        failure_streak_started_at (datetime | None): When the current failure
            streak began.
        created_at (datetime | None): When the config was created.
    """

    id: UUID
    config_name: str | None = None
    provider_type: str | None = None
    bucket_name: str | None = None
    region: str | None = None
    path_prefix: str | None = None
    credentials_hint: str | None = None
    provider_config: dict[str, Any] = {}
    is_active: bool = False
    is_validated: bool = False
    last_connected_at: UtcDatetime = None
    last_connection_error: str | None = None
    consecutive_failures: int = 0
    connection_health: str | None = None
    failure_streak_started_at: UtcDatetime = None
    created_at: UtcDatetime = None


class ListBlobConfigsResponse(_ApiModel):
    """The account's blob storage configs."""

    configs: list[BlobConfigDetail] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class CreateBlobConfigResponse(_ApiModel):
    """Result of creating a blob storage config."""

    id: UUID
    message: str | None = None


class UpdateBlobConfigResponse(_ApiModel):
    """Result of updating a blob storage config."""

    id: UUID
    message: str | None = None


class BlobValidationResponse(_ApiModel):
    """Result of validating a blob storage config.

    Attributes:
        is_valid (bool): Whether every check passed.
        can_write (bool): Whether a test object could be written.
        can_read (bool): Whether it could be read back.
        can_delete (bool): Whether it could be deleted.
        error_message (str | None): Why validation failed, if it did.
        message (str | None): Human-readable outcome.
    """

    is_valid: bool = False
    can_write: bool = False
    can_read: bool = False
    can_delete: bool = False
    error_message: str | None = None
    message: str | None = None


# -- sections ------------------------------------------------------------------


class _DatabaseConfigsSection(_Section):
    """Database configs (``/api/db-configs/...``).

    A database config stores the account's documents, chunks and annotations
    in its own database. The lifecycle is create, :meth:`initialize` (creates
    the schema), then :meth:`activate`.
    """

    def create(
        self,
        *,
        provider_type: str,
        connection_string: str,
        config_name: str | None = None,
        schema_name: str | None = None,
        credential_files: dict[str, Any] | None = None,
    ) -> CreateDBConfigResponse:
        """Create a database config.

        Calls ``POST /api/db-configs/``. BigQuery and blob-backed (ephemeral)
        configs have their own create calls.

        A Db2 connection string names its auth method with ``auth``:
        ``db2://user:password@host:port/database?auth=password``,
        ``db2://iam:<API key>@host:port/database?auth=iam``,
        ``db2://<principal>@host:port/database?auth=kerberos&service_principal=<principal>``
        or ``db2://@host:port/database?auth=certificate`` (principals
        percent-encoded). Db2 needs a self-hosted deployment with Db2 support;
        :meth:`providers` says whether this one has it.

        Args:
            provider_type (str): A :class:`DBProviderType` value.
            connection_string (str): Connection string; stored encrypted.
            config_name (str | None): Friendly name.
            schema_name (str | None): Schema to use, for multi-tenant
                databases.
            credential_files (dict[str, Any] | None): Db2 only: file material
                the connection authenticates with, stored encrypted. Keys are
                ``ca_cert_pem``, ``client_cert_pem``, ``client_key_pem``,
                ``client_key_passphrase`` and ``keytab_base64`` (a
                base64-encoded Kerberos keytab); all optional.

        Returns:
            CreateDBConfigResponse: The new config's id.

        Raises:
            RagnerockError: If the server refuses the config, e.g. credential
                files on a provider that doesn't take them.
        """
        body = _body(
            provider_type=provider_type,
            connection_string=connection_string,
            config_name=config_name,
            schema_name=schema_name,
            credential_files=credential_files,
        )
        response = self._parent._request("POST", "/api/db-configs/", json_body=body)
        return CreateDBConfigResponse.model_validate(response.json())

    def providers(self) -> ListDBProvidersResponse:
        """List the database providers this deployment supports, and for what.

        Calls ``GET /api/db-configs/providers``.

        Returns:
            ListDBProvidersResponse: Each provider's availability as a data
            database and as a SQL ingest source.
        """
        response = self._parent._request("GET", "/api/db-configs/providers")
        return ListDBProvidersResponse.model_validate(response.json())

    def create_bigquery(
        self,
        *,
        gcp_project_id: str,
        dataset_name: str,
        credentials_json: str,
        config_name: str | None = None,
        dataset_location: str | None = None,
    ) -> CreateDBConfigResponse:
        """Create a BigQuery database config.

        Calls ``POST /api/db-configs/bigquery``.

        Args:
            gcp_project_id (str): Google Cloud project id.
            dataset_name (str): BigQuery dataset.
            credentials_json (str): Service account key JSON; stored
                encrypted.
            config_name (str | None): Friendly name.
            dataset_location (str | None): Dataset location (e.g. ``"US"``,
                ``"EU"``). Detected from an existing dataset when omitted.

        Returns:
            CreateDBConfigResponse: The new config's id.
        """
        body = _body(
            config_name=config_name,
            bigquery_config=_body(
                gcp_project_id=gcp_project_id,
                dataset_name=dataset_name,
                credentials_json=credentials_json,
                dataset_location=dataset_location,
            ),
        )
        response = self._parent._request(
            "POST", "/api/db-configs/bigquery", json_body=body
        )
        return CreateDBConfigResponse.model_validate(response.json())

    def create_ephemeral(
        self,
        *,
        blob_config_id: UUID,
        config_name: str | None = None,
    ) -> CreateDBConfigResponse:
        """Create an ephemeral database config backed by blob storage.

        Calls ``POST /api/db-configs/ephemeral``. Ephemeral mode keeps
        document data (chunks, annotations) in the account's blob storage
        instead of a database.

        Args:
            blob_config_id (UUID): A validated blob storage config to store
                the data in.
            config_name (str | None): Friendly name.

        Returns:
            CreateDBConfigResponse: The new config's id.
        """
        body = _body(blob_config_id=blob_config_id, config_name=config_name)
        response = self._parent._request(
            "POST", "/api/db-configs/ephemeral", json_body=body
        )
        return CreateDBConfigResponse.model_validate(response.json())

    def list(self) -> ListDBConfigsResponse:
        """List the account's database configs.

        Calls ``GET /api/db-configs/``.

        Returns:
            ListDBConfigsResponse: Every config, with masked credentials.
        """
        response = self._parent._request("GET", "/api/db-configs/")
        return ListDBConfigsResponse.model_validate(response.json())

    def get(self, config_id: UUID) -> DBConfigDetail:
        """Fetch one database config.

        Calls ``GET /api/db-configs/{config_id}``.

        Args:
            config_id (UUID): Config to fetch.

        Returns:
            DBConfigDetail: The config.

        Raises:
            NotFoundError: If the account has no config with that id.
        """
        response = self._parent._request("GET", f"/api/db-configs/{config_id}")
        return DBConfigDetail.model_validate(response.json())

    def update(
        self,
        config_id: UUID,
        *,
        config_name: str | None = None,
        connection_string: str | None = None,
        schema_name: str | None = None,
        credential_files: dict[str, Any] | None = None,
    ) -> UpdateDBConfigResponse:
        """Update a database config; ``None`` fields are left unchanged.

        Calls ``PUT /api/db-configs/{config_id}``. A new connection string or
        new credential files deactivate the config; initialize and activate
        it again afterwards.

        Args:
            config_id (UUID): Config to update.
            config_name (str | None): New friendly name.
            connection_string (str | None): New connection string; stored
                encrypted.
            schema_name (str | None): New schema.
            credential_files (dict[str, Any] | None): Db2 only: files that
                replace every stored file (keys as for :meth:`create`). ``{}``
                removes them all; ``None`` keeps the stored ones that still
                apply.

        Returns:
            UpdateDBConfigResponse: The outcome.

        Raises:
            RagnerockError: If the server refuses the update, e.g. a new
                target without the keytab or client certificate it needs.
        """
        body = _body(
            config_name=config_name,
            connection_string=connection_string,
            schema_name=schema_name,
            credential_files=credential_files,
        )
        response = self._parent._request(
            "PUT", f"/api/db-configs/{config_id}", json_body=body
        )
        return UpdateDBConfigResponse.model_validate(response.json())

    def update_bigquery(
        self,
        config_id: UUID,
        *,
        credentials_json: str | None = None,
        dataset_location: str | None = None,
    ) -> UpdateDBConfigResponse:
        """Update a BigQuery database config's BigQuery settings.

        Calls ``PUT /api/db-configs/{config_id}/bigquery``. New credentials
        mean the config must be initialized and activated again.

        Args:
            config_id (UUID): Config to update.
            credentials_json (str | None): New service account key JSON.
            dataset_location (str | None): New dataset location.

        Returns:
            UpdateDBConfigResponse: The outcome.
        """
        body = _body(
            credentials_json=credentials_json, dataset_location=dataset_location
        )
        response = self._parent._request(
            "PUT", f"/api/db-configs/{config_id}/bigquery", json_body=body
        )
        return UpdateDBConfigResponse.model_validate(response.json())

    def delete(self, config_id: UUID) -> None:
        """Delete a database config.

        Calls ``DELETE /api/db-configs/{config_id}``. An active config can't
        be deleted; :meth:`deactivate` it first.

        Args:
            config_id (UUID): Config to delete.

        Raises:
            RagnerockError: If the config is still active.
        """
        self._parent._request("DELETE", f"/api/db-configs/{config_id}")

    def initialize(self, config_id: UUID) -> MessageResponse:
        """Create Ragnerock's schema in the database and check connectivity.

        Calls ``PUT /api/db-configs/{config_id}/initialize``. Required before
        :meth:`activate`.

        Args:
            config_id (UUID): Config to initialize.

        Returns:
            MessageResponse: The outcome.
        """
        response = self._parent._request(
            "PUT", f"/api/db-configs/{config_id}/initialize"
        )
        return MessageResponse.model_validate(response.json())

    def validate(self, config_id: UUID) -> MessageResponse:
        """Validate a database config; an alias for :meth:`initialize`.

        Calls ``PUT /api/db-configs/{config_id}/initialize``.

        Args:
            config_id (UUID): Config to validate.

        Returns:
            MessageResponse: The outcome.
        """
        return self.initialize(config_id)

    def activate(self, config_id: UUID) -> MessageResponse:
        """Make a database config the account's active one.

        Calls ``PUT /api/db-configs/{config_id}/activate``. The config must be
        initialized first, and only one config can be active per account.

        Args:
            config_id (UUID): Config to activate.

        Returns:
            MessageResponse: The outcome.
        """
        response = self._parent._request("PUT", f"/api/db-configs/{config_id}/activate")
        return MessageResponse.model_validate(response.json())

    def deactivate(self, config_id: UUID) -> MessageResponse:
        """Go back to storing documents in Ragnerock's database.

        Calls ``PUT /api/db-configs/{config_id}/deactivate``. Documents
        already in the account's database stay there.

        Args:
            config_id (UUID): Config to deactivate.

        Returns:
            MessageResponse: The outcome.
        """
        response = self._parent._request(
            "PUT", f"/api/db-configs/{config_id}/deactivate"
        )
        return MessageResponse.model_validate(response.json())

    def health(self, config_id: UUID) -> DBHealthCheckResponse:
        """Test a database config's connection and report its health.

        Calls ``GET /api/db-configs/{config_id}/health``.

        Args:
            config_id (UUID): Config to check.

        Returns:
            DBHealthCheckResponse: The check's result.
        """
        response = self._parent._request("GET", f"/api/db-configs/{config_id}/health")
        return DBHealthCheckResponse.model_validate(response.json())


class _BlobConfigsSection(_Section):
    """Blob storage configs (``/api/blob-configs/...``).

    A blob storage config keeps the account's uploaded files in its own
    bucket. The lifecycle is create, :meth:`validate`, then :meth:`activate`.
    """

    def create(
        self,
        *,
        provider_type: str,
        bucket_name: str,
        credentials: dict[str, Any],
        config_name: str | None = None,
        region: str | None = None,
        path_prefix: str = "ragnerock/data/",
        provider_config: dict[str, Any] | None = None,
    ) -> CreateBlobConfigResponse:
        """Create a blob storage config.

        Calls ``POST /api/blob-configs/``.

        Args:
            provider_type (str): A :class:`BlobProviderType` value.
            bucket_name (str): Bucket or container name.
            credentials (dict[str, Any]): Provider-specific credentials,
                stored encrypted: a service account key for GCS, an access
                key id and secret for S3, a connection string or account key
                for Azure.
            config_name (str | None): Friendly name.
            region (str | None): Bucket region (e.g. ``"us-east-1"``).
            path_prefix (str): Prefix for every stored object.
            provider_config (dict[str, Any] | None): Non-secret provider
                settings, e.g. ``endpoint_url`` for an S3-compatible service.

        Returns:
            CreateBlobConfigResponse: The new config's id.
        """
        body = _body(
            provider_type=provider_type,
            bucket_name=bucket_name,
            credentials=credentials,
            config_name=config_name,
            region=region,
            path_prefix=path_prefix,
            provider_config=provider_config,
        )
        response = self._parent._request("POST", "/api/blob-configs/", json_body=body)
        return CreateBlobConfigResponse.model_validate(response.json())

    def list(self) -> ListBlobConfigsResponse:
        """List the account's blob storage configs.

        Calls ``GET /api/blob-configs/``.

        Returns:
            ListBlobConfigsResponse: Every config, with masked credentials.
        """
        response = self._parent._request("GET", "/api/blob-configs/")
        return ListBlobConfigsResponse.model_validate(response.json())

    def get(self, config_id: UUID) -> BlobConfigDetail:
        """Fetch one blob storage config.

        Calls ``GET /api/blob-configs/{config_id}``.

        Args:
            config_id (UUID): Config to fetch.

        Returns:
            BlobConfigDetail: The config.

        Raises:
            NotFoundError: If the account has no config with that id.
        """
        response = self._parent._request("GET", f"/api/blob-configs/{config_id}")
        return BlobConfigDetail.model_validate(response.json())

    def update(
        self,
        config_id: UUID,
        *,
        config_name: str | None = None,
        region: str | None = None,
        path_prefix: str | None = None,
        credentials: dict[str, Any] | None = None,
        provider_config: dict[str, Any] | None = None,
        bucket_name: str | None = None,
    ) -> UpdateBlobConfigResponse:
        """Update a blob storage config; ``None`` fields are left unchanged.

        Calls ``PUT /api/blob-configs/{config_id}``. New ``credentials`` are
        sent first, to ``PUT /api/blob-configs/{config_id}/credentials``; if
        that fails nothing else is changed. A change of credentials, bucket or
        path prefix means the config must be validated again before it can
        be activated.

        Args:
            config_id (UUID): Config to update.
            config_name (str | None): New friendly name.
            region (str | None): New region.
            path_prefix (str | None): New object prefix.
            credentials (dict[str, Any] | None): Replacement credentials;
                stored encrypted.
            provider_config (dict[str, Any] | None): New non-secret provider
                settings.
            bucket_name (str | None): New bucket.

        Returns:
            UpdateBlobConfigResponse: The outcome of the settings update, or
            of the credentials update when only credentials changed.
        """
        result: UpdateBlobConfigResponse | None = None
        if credentials is not None:
            response = self._parent._request(
                "PUT",
                f"/api/blob-configs/{config_id}/credentials",
                json_body={"credentials": credentials},
            )
            result = UpdateBlobConfigResponse.model_validate(response.json())

        body = _body(
            config_name=config_name,
            bucket_name=bucket_name,
            region=region,
            path_prefix=path_prefix,
            provider_config=provider_config,
        )
        if body or result is None:
            response = self._parent._request(
                "PUT", f"/api/blob-configs/{config_id}", json_body=body
            )
            result = UpdateBlobConfigResponse.model_validate(response.json())
        return result

    def delete(self, config_id: UUID) -> None:
        """Delete a blob storage config.

        Calls ``DELETE /api/blob-configs/{config_id}``. An active config
        can't be deleted; :meth:`deactivate` it first. Documents uploaded
        under the config become inaccessible.

        Args:
            config_id (UUID): Config to delete.

        Raises:
            RagnerockError: If the config is still active.
        """
        self._parent._request("DELETE", f"/api/blob-configs/{config_id}")

    def validate(self, config_id: UUID) -> BlobValidationResponse:
        """Check that Ragnerock can write, read and delete in the bucket.

        Calls ``POST /api/blob-configs/{config_id}/validate``. Waits up to
        :data:`BLOB_VALIDATE_TIMEOUT`. Required before :meth:`activate`.

        Args:
            config_id (UUID): Config to validate.

        Returns:
            BlobValidationResponse: Which checks passed.
        """
        response = self._parent._request(
            "POST",
            f"/api/blob-configs/{config_id}/validate",
            timeout=BLOB_VALIDATE_TIMEOUT,
        )
        return BlobValidationResponse.model_validate(response.json())

    def activate(self, config_id: UUID) -> MessageResponse:
        """Send new uploads to this blob storage config.

        Calls ``PUT /api/blob-configs/{config_id}/activate``. The config must
        be validated first, and only one config can be active per account.

        Args:
            config_id (UUID): Config to activate.

        Returns:
            MessageResponse: The outcome.
        """
        response = self._parent._request(
            "PUT", f"/api/blob-configs/{config_id}/activate"
        )
        return MessageResponse.model_validate(response.json())

    def deactivate(self, config_id: UUID) -> MessageResponse:
        """Go back to storing uploads in Ragnerock's storage.

        Calls ``PUT /api/blob-configs/{config_id}/deactivate``. Files
        uploaded under the config stay accessible while it exists.

        Args:
            config_id (UUID): Config to deactivate.

        Returns:
            MessageResponse: The outcome.
        """
        response = self._parent._request(
            "PUT", f"/api/blob-configs/{config_id}/deactivate"
        )
        return MessageResponse.model_validate(response.json())
