"""Client-side resolution of GitOps ``Secret`` sources.

A ``Secret`` manifest names where each key's value comes from — inline
(``stringData`` / base64 ``data``), an environment variable (``fromEnv``), or a
cloud secret manager (``fromGcpSecretManager``, ``fromAwsSecretsManager``,
``fromAzureKeyVault``). Every source is resolved **here**, with this process's
environment and ambient cloud identity, never by the server: a server-side
resolver would dereference manifest-supplied names with the deployment's
identity.

Resolved values are then written back into the spec as ``encryptedData``
entries (sealed values plus their provenance), or as plaintext
``stringData`` when sealing is disabled. Provenance is deliberately not
secret: ``GEMINI_API_KEY`` or ``projects/p/secrets/s`` names where a credential
lives, not what it is, and naming it is what lets an export re-emit the
original declaration.

Cloud SDKs are optional and imported lazily; install the matching extra
(``ragnerock[gcp]``, ``ragnerock[aws]``, ``ragnerock[azure]``) to use a
provider.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, NamedTuple, NoReturn

from pydantic import BaseModel, ConfigDict

from ragnerock.errors import GitOpsError


class SecretSourceType(StrEnum):
    """Where a ``Secret`` key's value was authored from.

    Every member except :attr:`INLINE` names the ``spec`` field that carried
    the reference.
    """

    INLINE = "inline"
    """Pasted into the manifest (``stringData`` or ``data``)."""

    FROM_ENV = "fromEnv"
    """An environment variable of the applying process."""

    FROM_GCP_SECRET_MANAGER = "fromGcpSecretManager"
    """GCP Secret Manager."""

    FROM_AWS_SECRETS_MANAGER = "fromAwsSecretsManager"
    """AWS Secrets Manager."""

    FROM_AZURE_KEY_VAULT = "fromAzureKeyVault"
    """Azure Key Vault."""


class SecretSource(BaseModel):
    """The authored origin of one ``Secret`` key.

    Attributes:
        type (SecretSourceType): Which source block the key came from.
        env (str | None): Environment-variable name, for
            :attr:`SecretSourceType.FROM_ENV`.
        ref (dict[str, str] | None): The authored reference block, verbatim,
            for the cloud secret-manager sources.
    """

    model_config = ConfigDict(extra="forbid")

    type: SecretSourceType
    env: str | None = None
    ref: dict[str, str] | None = None


class SealedSecretEntry(BaseModel):
    """One key of an uploaded ``Secret``: its sealed value plus its provenance.

    Attributes:
        ciphertext (str): The value sealed to the instance's public key.
        source (SecretSource): Where the value was read from.
    """

    model_config = ConfigDict(extra="forbid")

    ciphertext: str
    source: SecretSource


class SecretValue(NamedTuple):
    """A resolved secret value and the source it was read from.

    Attributes:
        value (str): The resolved plaintext.
        source (SecretSource): Where the value came from.
    """

    value: str
    source: SecretSource


Transform = Callable[[str], str]
"""Applied to every value on its way into the upload: seals it, or elides it."""


class CloudProvider(StrEnum):
    """A cloud secret manager a ``Secret`` key can be sourced from.

    The member value is the ``spec`` field carrying that provider's
    references.
    """

    GCP = SecretSourceType.FROM_GCP_SECRET_MANAGER.value
    AWS = SecretSourceType.FROM_AWS_SECRETS_MANAGER.value
    AZURE = SecretSourceType.FROM_AZURE_KEY_VAULT.value

    @property
    def extra(self) -> str:
        """Return the ``ragnerock`` package extra that installs this provider's SDK."""
        match self:
            case CloudProvider.GCP:
                return "gcp"
            case CloudProvider.AWS:
                return "aws"
            case CloudProvider.AZURE:
                return "azure"

    @property
    def source_type(self) -> SecretSourceType:
        """Return the provenance recorded for keys read from this provider."""
        return SecretSourceType(self.value)


AUTHORED_SOURCE_FIELDS: tuple[str, ...] = (
    "stringData",
    "data",
    SecretSourceType.FROM_ENV.value,
    *(provider.value for provider in CloudProvider),
)
"""Every ``Secret`` spec field a human authors. All resolve client-side, so
all are stripped before upload."""

_INLINE_SOURCE = SecretSource(type=SecretSourceType.INLINE)
_GCP_DEFAULT_VERSION = "latest"
_GCP_RESOURCE_PREFIX = "projects/"


@dataclass(frozen=True)
class GcpRef:
    """A GCP Secret Manager secret version.

    Attributes:
        project (str | None): Project ID, or ``None`` for the ADC default.
        secret (str): The secret's short ID.
        version (str): Version number or alias.
    """

    project: str | None
    secret: str
    version: str


@dataclass(frozen=True)
class AwsRef:
    """An AWS Secrets Manager secret value.

    Attributes:
        secret_id (str): Secret name or ARN.
        region (str | None): Region, or ``None`` for the ambient config.
        version_stage (str | None): Staging label, or ``None``.
        version_id (str | None): Version ID, or ``None``.
    """

    secret_id: str
    region: str | None
    version_stage: str | None
    version_id: str | None


@dataclass(frozen=True)
class AzureRef:
    """An Azure Key Vault secret.

    Attributes:
        vault_url (str): Full vault URL, e.g. ``https://v.vault.azure.net``.
        secret (str): The secret's name.
        version (str | None): Version, or ``None`` for the current one.
    """

    vault_url: str
    secret: str
    version: str | None


CloudRef = GcpRef | AwsRef | AzureRef


class CloudBinding(NamedTuple):
    """One manifest key bound to a cloud reference.

    ``json_field`` is kept beside the reference so the reference alone is the
    fetch-cache key: two keys reading different fields of the same remote
    secret share one API call.

    Attributes:
        key (str): The key within the ``Secret``.
        ref (CloudRef): What to fetch.
        json_field (str | None): Field to extract from a JSON secret.
        authored (dict[str, str]): The reference block as written, recorded
            as provenance.
    """

    key: str
    ref: CloudRef
    json_field: str | None
    authored: dict[str, str]


# -- reference grammars --------------------------------------------------------


def _check_fields(raw: object, allowed: set[str], where: str) -> dict[str, Any]:
    """Validate a reference block is a mapping carrying only known fields.

    Args:
        raw (object): The parsed reference block.
        allowed (set[str]): Field names this provider accepts.
        where (str): Human location, for error messages.

    Returns:
        dict[str, Any]: ``raw``, narrowed to a mapping.

    Raises:
        GitOpsError: If the block is not a mapping or carries unknown fields.
    """
    if not isinstance(raw, dict):
        raise GitOpsError(f"{where} must be a mapping of reference fields")
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise GitOpsError(
            f"{where} has unknown field(s) {', '.join(unknown)}; "
            f"allowed: {', '.join(sorted(allowed))}"
        )
    return raw


def _required_str(block: dict[str, Any], name: str, where: str) -> str:
    """Return a required non-empty string field.

    Raises:
        GitOpsError: If the field is missing, not a string, or empty.
    """
    value = block.get(name)
    if not isinstance(value, str) or not value:
        raise GitOpsError(f"{where} requires a non-empty string '{name}'")
    return value


def _optional_str(block: dict[str, Any], name: str, where: str) -> str | None:
    """Return an optional non-empty string field, or ``None`` if absent.

    Raises:
        GitOpsError: If the field is present but not a non-empty string.
    """
    if name not in block:
        return None
    value = block[name]
    if not isinstance(value, str) or not value:
        raise GitOpsError(f"{where} field '{name}' must be a non-empty string")
    return value


def _split_gcp_resource_name(name: str, where: str) -> GcpRef:
    """Split a full ``projects/<p>/secrets/<s>[/versions/<v>]`` name.

    Raises:
        GitOpsError: If the name is not one of the two complete forms.
    """
    match name.split("/"):
        case ["projects", project, "secrets", secret] if project and secret:
            return GcpRef(project, secret, _GCP_DEFAULT_VERSION)
        case ["projects", project, "secrets", secret, "versions", version] if (
            project and secret and version
        ):
            return GcpRef(project, secret, version)
    raise GitOpsError(
        f"{where} 'secret' is not a complete resource name; expected "
        f"'projects/<project>/secrets/<secret>' with an optional "
        f"'/versions/<version>'"
    )


def parse_gcp_ref(raw: object, where: str) -> tuple[GcpRef, str | None]:
    """Parse a ``fromGcpSecretManager`` reference.

    ``secret`` takes either a short ID or a full resource name; combining a
    full name with ``project``/``version`` is an error rather than a silent
    precedence rule.

    Args:
        raw (object): The parsed reference block.
        where (str): Human location, for error messages.

    Returns:
        tuple[GcpRef, str | None]: The reference and its ``jsonField``.

    Raises:
        GitOpsError: On any malformed or contradictory reference.
    """
    block = _check_fields(raw, {"secret", "project", "version", "jsonField"}, where)
    secret = _required_str(block, "secret", where)
    project = _optional_str(block, "project", where)
    version = _optional_str(block, "version", where)
    json_field = _optional_str(block, "jsonField", where)

    if secret.startswith(_GCP_RESOURCE_PREFIX):
        if project is not None or version is not None:
            raise GitOpsError(
                f"{where} gives 'secret' as a full resource name, so "
                f"'project'/'version' must not also be set — the name already "
                f"carries them"
            )
        return _split_gcp_resource_name(secret, where), json_field
    if "/" in secret:
        raise GitOpsError(
            f"{where} 'secret' must be a short secret ID or a full "
            f"'projects/<project>/secrets/<secret>[/versions/<version>]' name"
        )
    return GcpRef(project, secret, version or _GCP_DEFAULT_VERSION), json_field


def parse_aws_ref(raw: object, where: str) -> tuple[AwsRef, str | None]:
    """Parse a ``fromAwsSecretsManager`` reference.

    Args:
        raw (object): The parsed reference block.
        where (str): Human location, for error messages.

    Returns:
        tuple[AwsRef, str | None]: The reference and its ``jsonField``.

    Raises:
        GitOpsError: On a malformed reference, or both version fields set.
    """
    block = _check_fields(
        raw, {"secretId", "region", "versionStage", "versionId", "jsonField"}, where
    )
    secret_id = _required_str(block, "secretId", where)
    region = _optional_str(block, "region", where)
    version_stage = _optional_str(block, "versionStage", where)
    version_id = _optional_str(block, "versionId", where)
    json_field = _optional_str(block, "jsonField", where)
    if version_stage is not None and version_id is not None:
        raise GitOpsError(
            f"{where} sets both 'versionStage' and 'versionId'; set one or neither"
        )
    return AwsRef(secret_id, region, version_stage, version_id), json_field


def parse_azure_ref(raw: object, where: str) -> tuple[AzureRef, str | None]:
    """Parse a ``fromAzureKeyVault`` reference.

    Args:
        raw (object): The parsed reference block.
        where (str): Human location, for error messages.

    Returns:
        tuple[AzureRef, str | None]: The reference and its ``jsonField``.

    Raises:
        GitOpsError: On a malformed reference or a non-HTTPS vault URL.
    """
    block = _check_fields(raw, {"vaultUrl", "secret", "version", "jsonField"}, where)
    vault_url = _required_str(block, "vaultUrl", where)
    if not vault_url.startswith("https://"):
        raise GitOpsError(
            f"{where} 'vaultUrl' must be the full https:// vault URL, "
            f"e.g. https://my-vault.vault.azure.net"
        )
    secret = _required_str(block, "secret", where)
    version = _optional_str(block, "version", where)
    json_field = _optional_str(block, "jsonField", where)
    return AzureRef(vault_url.rstrip("/"), secret, version), json_field


def parse_ref(
    provider: CloudProvider, raw: object, where: str
) -> tuple[CloudRef, str | None]:
    """Parse one reference with a provider's grammar.

    Args:
        provider (CloudProvider): Which provider's grammar to apply.
        raw (object): The parsed reference block.
        where (str): Human location, for error messages.

    Returns:
        tuple[CloudRef, str | None]: The reference and its ``jsonField``.

    Raises:
        GitOpsError: On a malformed reference.
    """
    match provider:
        case CloudProvider.GCP:
            return parse_gcp_ref(raw, where)
        case CloudProvider.AWS:
            return parse_aws_ref(raw, where)
        case CloudProvider.AZURE:
            return parse_azure_ref(raw, where)


def parse_refs(provider: CloudProvider, block: object, name: str) -> list[CloudBinding]:
    """Parse every reference in one provider's source block.

    Args:
        provider (CloudProvider): The provider whose block this is.
        block (object): The parsed ``key -> reference`` mapping.
        name (str): The secret's name, for error messages.

    Returns:
        list[CloudBinding]: One binding per key.

    Raises:
        GitOpsError: If the block is not a mapping, or any reference is
            malformed.
    """
    if not isinstance(block, dict):
        raise GitOpsError(
            f"Secret '{name}' {provider.value} must be a mapping of key -> reference"
        )
    bindings: list[CloudBinding] = []
    for key, raw in block.items():
        ref, json_field = parse_ref(
            provider, raw, f"Secret '{name}' {provider.value} key '{key}'"
        )
        authored = {k: str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
        bindings.append(CloudBinding(key, ref, json_field, authored))
    return bindings


# -- fetching ------------------------------------------------------------------


def _missing_sdk(provider: CloudProvider) -> NoReturn:
    """Raise an error naming the extra that installs a provider's SDK.

    Raises:
        GitOpsError: Always.
    """
    raise GitOpsError(
        f"{provider.value} needs the cloud SDK that ships with the "
        f"'{provider.extra}' extra. Install it with: "
        f"pip install 'ragnerock[{provider.extra}]'"
    )


def _decode_payload(payload: bytes, where: str) -> str:
    """Decode a secret payload as UTF-8 text.

    Raises:
        GitOpsError: If the payload is not valid UTF-8.
    """
    try:
        return payload.decode()
    except UnicodeDecodeError:
        raise GitOpsError(
            f"{where} is not valid UTF-8 text; Ragnerock secrets hold text values only"
        ) from None


def _fetch_gcp(ref: GcpRef) -> str:  # pragma: no cover - needs a live provider
    """Fetch a secret version's payload from GCP Secret Manager.

    Raises:
        GitOpsError: If the SDK is absent, no credentials or default project
            are available, or the API call fails.
    """
    try:
        import google.auth  # type: ignore[import-not-found]
        from google.api_core import (  # type: ignore[import-not-found]
            exceptions as gcp_exceptions,
        )
        from google.auth import (  # type: ignore[import-not-found]
            exceptions as gcp_auth_exceptions,
        )
        from google.cloud import secretmanager  # type: ignore[import-not-found]
    except ImportError:
        _missing_sdk(CloudProvider.GCP)

    project = ref.project
    if project is None:
        try:
            _, project = google.auth.default()
        except gcp_auth_exceptions.DefaultCredentialsError as e:
            raise GitOpsError(f"no Google credentials are available: {e}") from e
        if not project:
            raise GitOpsError(
                f"secret '{ref.secret}' gives no 'project' and the ambient Google "
                f"credentials carry no default project; set 'project' on the reference"
            )

    path = f"projects/{project}/secrets/{ref.secret}/versions/{ref.version}"
    try:
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(name=path)
    except gcp_auth_exceptions.GoogleAuthError as e:
        raise GitOpsError(f"could not authenticate to GCP Secret Manager: {e}") from e
    except gcp_exceptions.GoogleAPIError as e:
        raise GitOpsError(f"could not read {path} from GCP Secret Manager: {e}") from e
    return _decode_payload(response.payload.data, path)


def _fetch_aws(ref: AwsRef) -> str:  # pragma: no cover - needs a live provider
    """Fetch a secret value from AWS Secrets Manager.

    Raises:
        GitOpsError: If the SDK is absent, the API call fails, or the secret
            holds binary rather than string material.
    """
    try:
        import boto3  # type: ignore[import-not-found]
        from botocore import (  # type: ignore[import-not-found]
            exceptions as boto_exceptions,
        )
    except ImportError:
        _missing_sdk(CloudProvider.AWS)

    try:
        client = boto3.client("secretsmanager", region_name=ref.region)
    except boto_exceptions.BotoCoreError as e:
        raise GitOpsError(
            f"could not create an AWS Secrets Manager client for secret "
            f"'{ref.secret_id}': {e}"
        ) from e

    request: dict[str, str] = {"SecretId": ref.secret_id}
    if ref.version_stage is not None:
        request["VersionStage"] = ref.version_stage
    if ref.version_id is not None:
        request["VersionId"] = ref.version_id
    try:
        response = client.get_secret_value(**request)
    except (boto_exceptions.BotoCoreError, boto_exceptions.ClientError) as e:
        raise GitOpsError(f"could not read AWS secret '{ref.secret_id}': {e}") from e

    secret_string = response.get("SecretString")
    if secret_string is None:
        raise GitOpsError(
            f"AWS secret '{ref.secret_id}' is stored as SecretBinary; "
            f"Ragnerock secrets hold text values only"
        )
    return secret_string


def _fetch_azure(ref: AzureRef) -> str:  # pragma: no cover - needs a live provider
    """Fetch a secret from Azure Key Vault.

    Raises:
        GitOpsError: If the SDK is absent, the API call fails, or the secret
            has no value.
    """
    try:
        from azure.core import (  # type: ignore[import-not-found]
            exceptions as azure_exceptions,
        )
        from azure.identity import (  # type: ignore[import-not-found]
            DefaultAzureCredential,
        )
        from azure.keyvault.secrets import (  # type: ignore[import-not-found]
            SecretClient,
        )
    except ImportError:
        _missing_sdk(CloudProvider.AZURE)

    try:
        client = SecretClient(
            vault_url=ref.vault_url, credential=DefaultAzureCredential()
        )
        secret = client.get_secret(ref.secret, version=ref.version)
    except azure_exceptions.AzureError as e:
        raise GitOpsError(
            f"could not read secret '{ref.secret}' from {ref.vault_url}: {e}"
        ) from e

    if secret.value is None:
        raise GitOpsError(f"secret '{ref.secret}' in {ref.vault_url} has no value")
    return secret.value


def fetch_ref(ref: CloudRef) -> str:
    """Fetch one cloud reference's raw payload with the ambient cloud identity.

    Args:
        ref (CloudRef): The reference to read.

    Returns:
        str: The payload, before any ``jsonField`` extraction.

    Raises:
        GitOpsError: If the fetch fails or the provider SDK is missing.
    """
    match ref:
        case GcpRef():
            return _fetch_gcp(ref)
        case AwsRef():
            return _fetch_aws(ref)
        case AzureRef():
            return _fetch_azure(ref)


def extract_json_field(payload: str, name: str, where: str) -> str:
    """Extract one scalar field from a JSON-object secret.

    Args:
        payload (str): The fetched secret payload.
        name (str): The field to extract.
        where (str): Human location, for error messages.

    Returns:
        str: The field's value, with numbers and booleans rendered as JSON.

    Raises:
        GitOpsError: If the payload is not a JSON object, the field is absent,
            or the field holds something that is not a scalar. The payload
            itself is never echoed into the message.
    """
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        raise GitOpsError(
            f"{where} sets 'jsonField', but the secret is not JSON"
        ) from None
    if not isinstance(parsed, dict):
        raise GitOpsError(
            f"{where} sets 'jsonField', but the secret is not a JSON object"
        )
    if name not in parsed:
        raise GitOpsError(f"{where} secret has no JSON field '{name}'")
    value = parsed[name]
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, int, float)):
        return json.dumps(value)
    raise GitOpsError(
        f"{where} JSON field '{name}' must hold a string, number, or boolean"
    )


@dataclass
class CloudSecretFetcher:
    """Reads cloud secret-manager values, once per distinct reference.

    Two manifest keys naming the same remote secret cost one API call, even
    across different ``Secret`` documents, because the cache is keyed on the
    reference itself and ``jsonField`` is applied afterwards.

    An ``offline`` fetcher contacts nothing: references are still parsed (so
    a malformed one still fails), but every value resolves to ``""``. That is
    what a dry run wants — it elides values anyway.

    Attributes:
        offline (bool): Skip fetching and return an empty placeholder.
        fetch (Callable[[CloudRef], str]): The function that reads one
            reference. Defaults to :func:`fetch_ref`; tests substitute a stub.
    """

    offline: bool = False
    fetch: Callable[[CloudRef], str] = fetch_ref
    _cache: dict[CloudRef, str] = field(default_factory=dict, init=False, repr=False)

    def resolve(self, binding: CloudBinding, where: str) -> str:
        """Resolve one binding to its plaintext value.

        Args:
            binding (CloudBinding): The key, reference, and optional field.
            where (str): Human location, for error messages.

        Returns:
            str: The resolved value.

        Raises:
            GitOpsError: If the fetch or the field extraction fails.
        """
        if self.offline:
            return ""
        payload = self._cache.get(binding.ref)
        if payload is None:
            payload = self.fetch(binding.ref)
            self._cache[binding.ref] = payload
        if binding.json_field is None:
            return payload
        return extract_json_field(payload, binding.json_field, where)


# -- resolution and rewriting --------------------------------------------------


def resolve_secret_values(
    name: str,
    spec: Mapping[str, Any],
    fetcher: CloudSecretFetcher,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, SecretValue]:
    """Resolve one ``Secret``'s sources to plaintext without mutating the spec.

    ``data`` is base64-decoded strictly, ``fromEnv`` is read from ``env``, and
    cloud references are fetched through ``fetcher``. A key may appear in only
    one source. Every cloud reference is parsed before any is fetched, so a
    typo in the last block fails before a provider is contacted.

    Args:
        name (str): The secret's name, for error messages.
        spec (Mapping[str, Any]): The ``Secret`` spec.
        fetcher (CloudSecretFetcher): Shared cloud-fetch cache for this run.
        env (Mapping[str, str] | None): Environment for ``fromEnv``. Defaults
            to :data:`os.environ`.

    Returns:
        dict[str, SecretValue]: Resolved values by key.

    Raises:
        GitOpsError: On a key in multiple sources, invalid base64, an unset
            environment variable, or an unreadable cloud reference.
    """
    environ = os.environ if env is None else env
    string_data = spec.get("stringData") or {}
    data = spec.get("data") or {}
    from_env = spec.get(SecretSourceType.FROM_ENV.value) or {}

    values: dict[str, SecretValue] = {}

    def claim(key: str) -> None:
        if key in values:
            raise GitOpsError(
                f"Secret '{name}' key '{key}' is defined in more than one source "
                f"({'/'.join(AUTHORED_SOURCE_FIELDS)})"
            )

    for key, value in string_data.items():
        claim(key)
        values[key] = SecretValue(str(value), _INLINE_SOURCE)

    for key, value in data.items():
        claim(key)
        try:
            decoded = base64.b64decode(value, validate=True).decode()
        except (binascii.Error, ValueError, UnicodeDecodeError, TypeError):
            raise GitOpsError(
                f"Secret '{name}' data key '{key}' is not valid base64"
            ) from None
        values[key] = SecretValue(decoded, _INLINE_SOURCE)

    for key, env_var in from_env.items():
        claim(key)
        if env_var not in environ:
            raise GitOpsError(
                f"Secret '{name}' key '{key}' -> environment variable "
                f"${env_var} is not set"
            )
        values[key] = SecretValue(
            environ[env_var],
            SecretSource(type=SecretSourceType.FROM_ENV, env=env_var),
        )

    bindings: list[tuple[CloudProvider, CloudBinding]] = []
    for provider in CloudProvider:
        block = spec.get(provider.value)
        if not block:
            continue
        for binding in parse_refs(provider, block, name):
            claim(binding.key)
            # Placeholder: reserves the key so a later source collides.
            values[binding.key] = SecretValue("", _INLINE_SOURCE)
            bindings.append((provider, binding))

    for provider, binding in bindings:
        where = f"Secret '{name}' {provider.value} key '{binding.key}'"
        values[binding.key] = SecretValue(
            fetcher.resolve(binding, where),
            SecretSource(type=provider.source_type, ref=binding.authored),
        )

    return values


def write_sealed(
    spec: dict[str, Any], values: Mapping[str, SecretValue], transform: Transform
) -> None:
    """Replace a Secret's authored sources with an ``encryptedData`` block.

    Args:
        spec (dict[str, Any]): The ``Secret`` spec, mutated in place.
        values (Mapping[str, SecretValue]): Resolved values for this secret.
        transform (Transform): Seals a value, or elides it for a dry run.
    """
    for name in AUTHORED_SOURCE_FIELDS:
        spec.pop(name, None)
    encrypted = {
        key: SealedSecretEntry(
            ciphertext=transform(resolved.value), source=resolved.source
        ).model_dump(mode="json", exclude_none=True)
        for key, resolved in values.items()
    }
    if encrypted:
        spec["encryptedData"] = encrypted


def write_inline(
    spec: dict[str, Any], values: Mapping[str, SecretValue], transform: Transform
) -> None:
    """Fold a Secret's resolved sources into plaintext ``stringData``.

    The unsealed path, for instances with no sealing key. ``stringData`` has
    nowhere to record provenance, so a ``fromEnv`` binding resolved this way
    is not reproducible on export.

    Args:
        spec (dict[str, Any]): The ``Secret`` spec, mutated in place.
        values (Mapping[str, SecretValue]): Resolved values for this secret.
        transform (Transform): Identity, or elides the value for a dry run.
    """
    for name in AUTHORED_SOURCE_FIELDS:
        spec.pop(name, None)
    if values:
        spec["stringData"] = {k: transform(v.value) for k, v in values.items()}


@dataclass
class ResolvedSecret:
    """One ``Secret`` document with its sources resolved.

    Attributes:
        name (str): The secret's ``metadata.name``.
        spec (dict[str, Any]): The document's spec, which :meth:`ResolvedSecrets.write`
            rewrites in place.
        values (dict[str, SecretValue]): The resolved values by key.
    """

    name: str
    spec: dict[str, Any]
    values: dict[str, SecretValue]


@dataclass
class ResolvedSecrets:
    """Every ``Secret`` in a manifest set, resolved and ready to be rewritten.

    Attributes:
        secrets (list[ResolvedSecret]): One entry per ``Secret`` document.
        cloud_reference_count (int): Cloud references across all secrets.
    """

    secrets: list[ResolvedSecret]
    cloud_reference_count: int = 0

    @property
    def key_count(self) -> int:
        """Total resolved keys across every secret."""
        return sum(len(s.values) for s in self.secrets)

    @property
    def env_key_count(self) -> int:
        """Keys resolved from environment variables."""
        return sum(
            1
            for s in self.secrets
            for v in s.values.values()
            if v.source.type is SecretSourceType.FROM_ENV
        )

    def plaintexts(self) -> Iterator[str]:
        """Yield every resolved plaintext value, e.g. for log masking."""
        for s in self.secrets:
            for v in s.values.values():
                yield v.value

    def write(self, *, sealed: bool, transform: Transform) -> None:
        """Rewrite every secret's spec in place for upload.

        Args:
            sealed (bool): Write ``encryptedData`` (``True``) or plaintext
                ``stringData`` (``False``).
            transform (Transform): Applied to each value — seals it, elides
                it, or passes it through.
        """
        writer = write_sealed if sealed else write_inline
        for s in self.secrets:
            writer(s.spec, s.values, transform)


def secret_specs(documents: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(name, spec)`` for every ``Secret`` document that has a spec.

    Args:
        documents (list[dict[str, Any]]): Parsed Ragnerock manifest documents.

    Returns:
        list[tuple[str, dict[str, Any]]]: The name and mutable spec of each Secret.
    """
    out: list[tuple[str, dict[str, Any]]] = []
    for doc in documents:
        if doc.get("kind") != "Secret":
            continue
        spec = doc.get("spec")
        if isinstance(spec, dict):
            out.append(((doc.get("metadata") or {}).get("name", "<unnamed>"), spec))
    return out


def resolve_secrets(
    documents: list[dict[str, Any]],
    *,
    offline: bool = False,
    env: Mapping[str, str] | None = None,
    fetcher: CloudSecretFetcher | None = None,
) -> ResolvedSecrets:
    """Resolve the sources of every ``Secret`` document in a manifest set.

    Args:
        documents (list[dict[str, Any]]): Parsed Ragnerock manifest documents.
        offline (bool): Parse cloud references but fetch none of them.
        env (Mapping[str, str] | None): Environment for ``fromEnv``. Defaults
            to :data:`os.environ`.
        fetcher (CloudSecretFetcher | None): Fetcher to use; one is created
            (honouring ``offline``) when omitted.

    Returns:
        ResolvedSecrets: The resolved secrets, not yet written back.

    Raises:
        GitOpsError: If any secret fails to resolve.
    """
    fetcher = fetcher if fetcher is not None else CloudSecretFetcher(offline=offline)
    secrets: list[ResolvedSecret] = []
    cloud_count = 0
    for name, spec in secret_specs(documents):
        cloud_count += sum(len(spec.get(p.value) or {}) for p in CloudProvider)
        values = resolve_secret_values(name, spec, fetcher, env=env)
        secrets.append(ResolvedSecret(name=name, spec=spec, values=values))
    return ResolvedSecrets(secrets=secrets, cloud_reference_count=cloud_count)
