"""Tests for client-side ``Secret`` resolution (:mod:`ragnerock.gitops.secrets`).

Every authored source must resolve here, before upload — the server resolves
none of them — and the fold into ``encryptedData`` must keep every value and
its provenance while leaving no plaintext behind.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric import rsa

from ragnerock.errors import GitOpsError
from ragnerock.gitops import seal
from ragnerock.gitops.secrets import (
    AUTHORED_SOURCE_FIELDS,
    AwsRef,
    AzureRef,
    CloudBinding,
    CloudProvider,
    CloudSecretFetcher,
    GcpRef,
    SecretSource,
    SecretSourceType,
    SecretValue,
    _missing_sdk,
    extract_json_field,
    parse_aws_ref,
    parse_azure_ref,
    parse_gcp_ref,
    parse_refs,
    resolve_secret_values,
    resolve_secrets,
    secret_specs,
    write_inline,
    write_sealed,
)
from tests.unit.gitops.helpers import agent_doc, secret_doc

_INLINE = SecretSource(type=SecretSourceType.INLINE)


def _stub_fetcher(calls: list[object] | None = None) -> CloudSecretFetcher:
    """A fetcher whose fetch returns a deterministic per-reference value."""

    def fetch(ref: object) -> str:
        if calls is not None:
            calls.append(ref)
        return f"value-for-{type(ref).__name__}"

    return CloudSecretFetcher(fetch=fetch)  # type: ignore[arg-type]


def _resolve(
    spec: dict[str, Any],
    *,
    env: dict[str, str] | None = None,
    fetcher: CloudSecretFetcher | None = None,
) -> dict[str, SecretValue]:
    return resolve_secret_values(
        "creds", spec, fetcher or _stub_fetcher(), env=env or {}
    )


def _sealer(key: rsa.RSAPrivateKey) -> Callable[[str], str]:
    public_key = key.public_key()
    return lambda value: seal(value, public_key)


# -- cloud reference grammars ---------------------------------------------------


class TestGcpRef:
    def test_short_id_defaults_version_and_project(self) -> None:
        ref, json_field = parse_gcp_ref({"secret": "anthropic-api-key"}, "where")
        assert ref == GcpRef(None, "anthropic-api-key", "latest")
        assert json_field is None

    def test_short_id_with_explicit_project_and_version(self) -> None:
        ref, _ = parse_gcp_ref(
            {"secret": "k", "project": "my-proj", "version": "3"}, "w"
        )
        assert ref == GcpRef("my-proj", "k", "3")

    def test_full_resource_name_without_version(self) -> None:
        ref, _ = parse_gcp_ref({"secret": "projects/p/secrets/s"}, "w")
        assert ref == GcpRef("p", "s", "latest")

    def test_full_resource_name_with_version(self) -> None:
        ref, _ = parse_gcp_ref({"secret": "projects/p/secrets/s/versions/7"}, "w")
        assert ref == GcpRef("p", "s", "7")

    def test_full_resource_name_rejects_redundant_project(self) -> None:
        with pytest.raises(GitOpsError, match="already carries them"):
            parse_gcp_ref({"secret": "projects/p/secrets/s", "project": "other"}, "w")

    def test_partial_resource_path_rejected(self) -> None:
        with pytest.raises(GitOpsError, match="complete resource name"):
            parse_gcp_ref({"secret": "projects/p/secrets"}, "w")

    def test_short_id_with_slash_rejected(self) -> None:
        with pytest.raises(GitOpsError, match="short secret ID"):
            parse_gcp_ref({"secret": "some/thing"}, "w")

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(GitOpsError, match=r"unknown field\(s\) jsonfield"):
            parse_gcp_ref({"secret": "k", "jsonfield": "oops"}, "w")

    def test_requires_secret(self) -> None:
        with pytest.raises(GitOpsError, match="requires a non-empty string 'secret'"):
            parse_gcp_ref({"project": "p"}, "w")

    def test_reference_block_must_be_a_mapping(self) -> None:
        with pytest.raises(GitOpsError, match="must be a mapping"):
            parse_gcp_ref("just-a-string", "w")


class TestAwsRef:
    def test_minimal_reference(self) -> None:
        ref, json_field = parse_aws_ref({"secretId": "prod/db"}, "w")
        assert ref == AwsRef("prod/db", None, None, None)
        assert json_field is None

    def test_accepts_arn_and_json_field(self) -> None:
        arn = "arn:aws:secretsmanager:us-east-1:1:secret:prod/db-AbCdEf"
        ref, json_field = parse_aws_ref(
            {"secretId": arn, "region": "us-east-1", "jsonField": "password"}, "w"
        )
        assert ref == AwsRef(arn, "us-east-1", None, None)
        assert json_field == "password"

    def test_version_fields_are_mutually_exclusive(self) -> None:
        with pytest.raises(GitOpsError, match="set one or neither"):
            parse_aws_ref(
                {"secretId": "s", "versionStage": "AWSCURRENT", "versionId": "abc"}, "w"
            )

    def test_either_version_field_alone_is_fine(self) -> None:
        staged, _ = parse_aws_ref({"secretId": "s", "versionStage": "AWSPREVIOUS"}, "w")
        pinned, _ = parse_aws_ref({"secretId": "s", "versionId": "abc"}, "w")
        assert staged.version_stage == "AWSPREVIOUS"
        assert pinned.version_id == "abc"


class TestAzureRef:
    def test_trailing_slash_is_normalized(self) -> None:
        ref, _ = parse_azure_ref(
            {"vaultUrl": "https://v.vault.azure.net/", "secret": "k"}, "w"
        )
        assert ref == AzureRef("https://v.vault.azure.net", "k", None)

    def test_rejects_non_https_vault_url(self) -> None:
        with pytest.raises(GitOpsError, match="full https:// vault URL"):
            parse_azure_ref({"vaultUrl": "my-vault", "secret": "k"}, "w")

    def test_sovereign_cloud_url_accepted(self) -> None:
        ref, _ = parse_azure_ref(
            {"vaultUrl": "https://v.vault.usgovcloudapi.net", "secret": "k"}, "w"
        )
        assert ref.vault_url == "https://v.vault.usgovcloudapi.net"


def test_parse_refs_rejects_non_mapping_block() -> None:
    with pytest.raises(GitOpsError, match="mapping of key -> reference"):
        parse_refs(CloudProvider.GCP, ["nope"], "s")


# -- jsonField ---------------------------------------------------------------------


class TestJsonField:
    def test_extracts_string(self) -> None:
        payload = json.dumps({"username": "u", "password": "p"})
        assert extract_json_field(payload, "password", "w") == "p"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(5432, "5432"), (1.5, "1.5"), (True, "true"), (False, "false")],
    )
    def test_renders_scalars_as_json(self, value: object, expected: str) -> None:
        assert extract_json_field(json.dumps({"f": value}), "f", "w") == expected

    @pytest.mark.parametrize("value", [{"nested": 1}, [1, 2], None])
    def test_rejects_non_scalar(self, value: object) -> None:
        with pytest.raises(GitOpsError, match="string, number, or boolean"):
            extract_json_field(json.dumps({"f": value}), "f", "w")

    def test_absent_field(self) -> None:
        with pytest.raises(GitOpsError, match="no JSON field 'b'"):
            extract_json_field('{"a": 1}', "b", "w")

    def test_non_json_payload(self) -> None:
        with pytest.raises(GitOpsError, match="not JSON"):
            extract_json_field("sk-plain-value", "f", "w")

    def test_json_array(self) -> None:
        with pytest.raises(GitOpsError, match="not a JSON object"):
            extract_json_field("[1, 2]", "f", "w")

    def test_error_never_echoes_the_payload(self) -> None:
        with pytest.raises(GitOpsError) as exc:
            extract_json_field("sk-super-secret-value", "f", "w")
        assert "sk-super-secret-value" not in str(exc.value)


# -- fetching ----------------------------------------------------------------------


class TestFetcher:
    def test_caches_by_reference(self) -> None:
        calls: list[object] = []

        def fetch(ref: object) -> str:
            calls.append(ref)
            return json.dumps({"user": "u", "pass": "p"})

        fetcher = CloudSecretFetcher(fetch=fetch)  # type: ignore[arg-type]
        ref = AwsRef("prod/db", None, None, None)
        user = fetcher.resolve(CloudBinding("u", ref, "user", {}), "w")
        password = fetcher.resolve(CloudBinding("p", ref, "pass", {}), "w")
        assert (user, password) == ("u", "p")
        assert len(calls) == 1

    def test_does_not_conflate_distinct_references(self) -> None:
        calls: list[object] = []
        fetcher = _stub_fetcher(calls)
        fetcher.resolve(CloudBinding("a", GcpRef("p", "s", "1"), None, {}), "w")
        fetcher.resolve(CloudBinding("b", GcpRef("p", "s", "2"), None, {}), "w")
        assert len(calls) == 2

    def test_offline_parses_references_without_fetching(self) -> None:
        def explode(ref: object) -> str:
            raise AssertionError("an offline fetcher must not fetch")

        spec: dict[str, Any] = {
            "fromAzureKeyVault": {
                "k": {"vaultUrl": "https://unreachable.vault.azure.net", "secret": "s"}
            }
        }
        fetcher = CloudSecretFetcher(offline=True, fetch=explode)  # type: ignore[arg-type]
        values = _resolve(spec, fetcher=fetcher)
        assert values["k"].source.type is SecretSourceType.FROM_AZURE_KEY_VAULT
        assert values["k"].source.ref == {
            "vaultUrl": "https://unreachable.vault.azure.net",
            "secret": "s",
        }

    def test_offline_still_rejects_a_malformed_reference(self) -> None:
        spec: dict[str, Any] = {"fromAzureKeyVault": {"k": {"vaultUrl": "http://x"}}}
        with pytest.raises(GitOpsError, match="https://"):
            _resolve(spec, fetcher=CloudSecretFetcher(offline=True))

    @pytest.mark.parametrize(
        ("provider", "extra"),
        [
            (CloudProvider.GCP, "gcp"),
            (CloudProvider.AWS, "aws"),
            (CloudProvider.AZURE, "azure"),
        ],
    )
    def test_missing_sdk_names_the_extra(
        self, provider: CloudProvider, extra: str
    ) -> None:
        with pytest.raises(GitOpsError, match=rf"ragnerock\[{extra}\]"):
            _missing_sdk(provider)


# -- resolution ----------------------------------------------------------------------


class TestResolution:
    def test_resolves_every_source(self) -> None:
        spec: dict[str, Any] = {
            "stringData": {"a": "inline"},
            "data": {"b": "ZGVjb2RlZA=="},  # base64 of "decoded"
            "fromEnv": {"c": "SOME_VAR"},
            "fromGcpSecretManager": {"d": {"secret": "s", "project": "p"}},
            "fromAwsSecretsManager": {"e": {"secretId": "s"}},
            "fromAzureKeyVault": {
                "f": {"vaultUrl": "https://v.vault.azure.net", "secret": "s"}
            },
        }
        values = _resolve(spec, env={"SOME_VAR": "from-the-environment"})

        assert values["a"] == ("inline", _INLINE)
        assert values["b"] == ("decoded", _INLINE)
        assert values["c"] == (
            "from-the-environment",
            SecretSource(type=SecretSourceType.FROM_ENV, env="SOME_VAR"),
        )
        assert values["d"] == (
            "value-for-GcpRef",
            SecretSource(
                type=SecretSourceType.FROM_GCP_SECRET_MANAGER,
                ref={"secret": "s", "project": "p"},
            ),
        )
        assert values["e"] == (
            "value-for-AwsRef",
            SecretSource(
                type=SecretSourceType.FROM_AWS_SECRETS_MANAGER, ref={"secretId": "s"}
            ),
        )
        assert values["f"] == (
            "value-for-AzureRef",
            SecretSource(
                type=SecretSourceType.FROM_AZURE_KEY_VAULT,
                ref={"vaultUrl": "https://v.vault.azure.net", "secret": "s"},
            ),
        )
        # Resolution reads the spec; rewriting it is the write step's job.
        assert set(spec) == set(AUTHORED_SOURCE_FIELDS)

    def test_reads_os_environ_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITOPS_TEST_VAR", "from-os")
        values = resolve_secret_values(
            "creds", {"fromEnv": {"k": "GITOPS_TEST_VAR"}}, _stub_fetcher()
        )
        assert values["k"].value == "from-os"

    def test_key_in_two_sources_is_rejected(self) -> None:
        spec: dict[str, Any] = {"stringData": {"a": "x"}, "fromEnv": {"a": "SOME_VAR"}}
        with pytest.raises(GitOpsError, match="more than one source"):
            _resolve(spec, env={"SOME_VAR": "y"})

    def test_cloud_source_collides_with_inline_source(self) -> None:
        spec: dict[str, Any] = {
            "stringData": {"k": "inline"},
            "fromGcpSecretManager": {"k": {"secret": "s", "project": "p"}},
        }
        with pytest.raises(GitOpsError, match="more than one source"):
            _resolve(spec)

    def test_cloud_sources_collide_with_each_other(self) -> None:
        spec: dict[str, Any] = {
            "fromGcpSecretManager": {"k": {"secret": "s", "project": "p"}},
            "fromAwsSecretsManager": {"k": {"secretId": "s"}},
        }
        with pytest.raises(GitOpsError, match="more than one source"):
            _resolve(spec)

    def test_malformed_reference_fails_before_any_fetch(self) -> None:
        calls: list[object] = []
        spec: dict[str, Any] = {
            "fromAwsSecretsManager": {"good": {"secretId": "s"}},
            "fromAzureKeyVault": {"bad": {"vaultUrl": "not-a-url", "secret": "s"}},
        }
        with pytest.raises(GitOpsError):
            _resolve(spec, fetcher=_stub_fetcher(calls))
        assert calls == []

    def test_invalid_base64_is_rejected(self) -> None:
        with pytest.raises(GitOpsError, match="not valid base64"):
            _resolve({"data": {"a": "!!!not base64!!!"}})

    def test_unset_environment_variable_is_rejected(self) -> None:
        with pytest.raises(GitOpsError, match="MISSING_VAR"):
            _resolve({"fromEnv": {"a": "MISSING_VAR"}})

    def test_authored_source_fields_match_the_cloud_providers(self) -> None:
        assert set(AUTHORED_SOURCE_FIELDS) == {"stringData", "data", "fromEnv"} | {
            p.value for p in CloudProvider
        }


# -- writing the upload ---------------------------------------------------------------


class TestWriteSealed:
    def test_upload_carries_no_plaintext(self, sealing_key: rsa.RSAPrivateKey) -> None:
        spec: dict[str, Any] = {
            "stringData": {"a": "inline-secret-value"},
            "data": {"b": "ZGVjb2RlZA=="},
            "fromEnv": {"c": "SOME_VAR"},
        }
        doc = secret_doc(spec)
        values = _resolve(spec, env={"SOME_VAR": "env-secret-value"})
        write_sealed(spec, values, _sealer(sealing_key))
        manifest = yaml.safe_dump_all([doc])

        for plaintext in ("inline-secret-value", "decoded", "env-secret-value"):
            assert plaintext not in manifest
        assert set(spec) == {"encryptedData"}
        assert all(
            e["ciphertext"].startswith("rgnk-sealed.v1.")
            for e in spec["encryptedData"].values()
        )

    def test_values_unseal_to_the_originals(
        self, sealing_key: rsa.RSAPrivateKey, unseal: Callable[[str], str]
    ) -> None:
        spec: dict[str, Any] = {
            "stringData": {"a": "inline-secret-value"},
            "data": {"b": "ZGVjb2RlZA=="},
            "fromEnv": {"c": "SOME_VAR"},
        }
        values = _resolve(spec, env={"SOME_VAR": "env-secret-value"})
        write_sealed(spec, values, _sealer(sealing_key))
        opened = {k: unseal(e["ciphertext"]) for k, e in spec["encryptedData"].items()}
        assert opened == {
            "a": "inline-secret-value",
            "b": "decoded",
            "c": "env-secret-value",
        }

    def test_cloud_values_are_sealed_like_any_other(
        self, sealing_key: rsa.RSAPrivateKey, unseal: Callable[[str], str]
    ) -> None:
        spec: dict[str, Any] = {
            "fromGcpSecretManager": {"d": {"secret": "s", "project": "p"}}
        }
        values = _resolve(spec)
        write_sealed(spec, values, _sealer(sealing_key))
        assert set(spec) == {"encryptedData"}
        assert unseal(spec["encryptedData"]["d"]["ciphertext"]) == "value-for-GcpRef"

    def test_from_env_provenance_survives_sealing(
        self, sealing_key: rsa.RSAPrivateKey
    ) -> None:
        spec: dict[str, Any] = {"stringData": {"a": "x"}, "fromEnv": {"c": "SOME_VAR"}}
        values = _resolve(spec, env={"SOME_VAR": "y"})
        write_sealed(spec, values, _sealer(sealing_key))
        assert spec["encryptedData"]["c"]["source"] == {
            "type": "fromEnv",
            "env": "SOME_VAR",
        }
        assert spec["encryptedData"]["a"]["source"] == {"type": "inline"}

    def test_strips_every_authored_source(self, sealing_key: rsa.RSAPrivateKey) -> None:
        spec: dict[str, Any] = {
            "description": "kept",
            "stringData": {"a": "x"},
            "data": {"b": "eQ=="},
            "fromEnv": {"c": "SOME_VAR"},
            "fromGcpSecretManager": {"d": {"secret": "s", "project": "p"}},
            "fromAwsSecretsManager": {"e": {"secretId": "s"}},
            "fromAzureKeyVault": {
                "f": {"vaultUrl": "https://v.vault.azure.net", "secret": "s"}
            },
        }
        write_sealed(spec, {"a": SecretValue("x", _INLINE)}, _sealer(sealing_key))
        assert set(spec) == {"description", "encryptedData"}


class TestWriteInline:
    def test_inlines_into_string_data(self) -> None:
        spec: dict[str, Any] = {"data": {"b": "ZGVjb2RlZA=="}, "fromEnv": {"c": "V"}}
        values = _resolve(spec, env={"V": "env-secret-value"})
        write_inline(spec, values, lambda v: v)
        assert spec == {"stringData": {"b": "decoded", "c": "env-secret-value"}}

    def test_strips_cloud_sources(self) -> None:
        spec: dict[str, Any] = {
            "fromGcpSecretManager": {"d": {"secret": "s", "project": "p"}}
        }
        values = _resolve(spec)
        write_inline(spec, values, lambda v: v)
        assert spec == {"stringData": {"d": "value-for-GcpRef"}}


@pytest.mark.parametrize("writer", [write_sealed, write_inline])
def test_elided_values_never_reach_the_output(writer: Any) -> None:
    spec: dict[str, Any] = {
        "stringData": {"a": "inline-secret-value"},
        "fromEnv": {"c": "SOME_VAR"},
    }
    doc = secret_doc(spec)
    values = _resolve(spec, env={"SOME_VAR": "env-secret-value"})
    writer(spec, values, lambda _: "<redacted>")
    printed = yaml.safe_dump_all([doc])
    assert "inline-secret-value" not in printed
    assert "env-secret-value" not in printed
    assert "<redacted>" in printed


# -- document selection ------------------------------------------------------------


def test_only_secret_documents_are_rewritten() -> None:
    docs = [
        secret_doc({"stringData": {"a": "v"}}),
        agent_doc(),
        {"kind": "Secret", "spec": None},
    ]
    assert [name for name, _ in secret_specs(docs)] == ["creds"]


def test_resolve_secrets_counts_sources() -> None:
    docs = [
        secret_doc(
            {
                "stringData": {"a": "v"},
                "fromEnv": {"b": "V"},
                "fromAwsSecretsManager": {"c": {"secretId": "s"}},
            }
        ),
        agent_doc(),
    ]
    resolved = resolve_secrets(docs, env={"V": "x"}, fetcher=_stub_fetcher())
    assert resolved.key_count == 3
    assert resolved.env_key_count == 1
    assert resolved.cloud_reference_count == 1
    assert sorted(resolved.plaintexts()) == ["v", "value-for-AwsRef", "x"]


# -- wire contract -----------------------------------------------------------------


def test_wire_models_are_pinned() -> None:
    """The ``encryptedData`` entry shape the server reads must not drift."""
    from ragnerock.gitops.secrets import SealedSecretEntry

    source = SecretSource.model_json_schema()
    assert source["additionalProperties"] is False
    assert source["required"] == ["type"]
    assert set(source["properties"]) == {"type", "env", "ref"}

    entry = SealedSecretEntry.model_json_schema()
    assert entry["additionalProperties"] is False
    assert entry["required"] == ["ciphertext", "source"]

    assert {m.value for m in SecretSourceType} == {
        "inline",
        "fromEnv",
        "fromGcpSecretManager",
        "fromAwsSecretsManager",
        "fromAzureKeyVault",
    }
