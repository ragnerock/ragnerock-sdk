"""Tests for preparing and applying a manifest set (:mod:`ragnerock.gitops.apply`)."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from ragnerock.client import RagnerockClient
from ragnerock.errors import GitOpsError, ValidationError
from ragnerock.gitops import (
    REDACTED,
    ManifestSet,
    apply_manifests,
    key_fingerprint,
    load_public_key,
    mask_in_github_actions,
    prepare_manifest,
    render_dry_run,
)
from tests.unit.conftest import TEST_HOST
from tests.unit.gitops.helpers import agent_doc, secret_doc

APPLY_URL = f"{TEST_HOST}/api/gitops/apply"
KEY_URL = f"{TEST_HOST}/api/gitops/sealing-key"

_REPORT: dict[str, Any] = {
    "ok": True,
    "dry_run": False,
    "structural_errors": [],
    "results": [
        {
            "kind": "Secret",
            "name": "creds",
            "action": "created",
            "errors": [],
            "warnings": [],
        },
        {
            "kind": "Agent",
            "name": "scorer",
            "action": "unchanged",
            "errors": [],
            "warnings": [],
        },
    ],
}


@pytest.fixture
def client() -> RagnerockClient:
    return RagnerockClient(host=TEST_HOST, auth_token="rgnk_test")


def _manifests(*docs: dict[str, Any]) -> ManifestSet:
    return ManifestSet(documents=list(docs), files=["test.yaml"])


def _uploaded(httpx_mock: Any) -> list[dict[str, Any]]:
    """Parse the YAML file part out of the last apply request."""
    request = [
        r for r in httpx_mock.get_requests() if r.url.path == "/api/gitops/apply"
    ][-1]
    body = request.content.decode()
    start = body.index("\r\n\r\n") + 4
    end = body.rindex("\r\n--")
    return [d for d in yaml.safe_load_all(body[start:end]) if d is not None]


class TestPrepare:
    def test_seals_with_a_pinned_key_without_contacting_the_server(
        self, httpx_mock: Any, sealing_pem: str, unseal: Callable[[str], str]
    ) -> None:
        prepared = prepare_manifest(
            _manifests(secret_doc({"stringData": {"a": "s3cret"}})),
            sealing_public_key=sealing_pem,
        )
        assert httpx_mock.get_requests() == []
        entry = prepared.documents[0]["spec"]["encryptedData"]["a"]
        assert unseal(entry["ciphertext"]) == "s3cret"
        assert prepared.sealing_key_pinned
        assert prepared.sealing_fingerprint == key_fingerprint(
            load_public_key(sealing_pem)
        )

    def test_fetches_the_instance_key_when_not_pinned(
        self, httpx_mock: Any, client: RagnerockClient, sealing_pem: str
    ) -> None:
        httpx_mock.add_response(
            method="GET", url=KEY_URL, json={"public_key": sealing_pem}
        )
        prepared = prepare_manifest(
            _manifests(secret_doc({"stringData": {"a": "s3cret"}})), client=client
        )
        assert not prepared.sealing_key_pinned
        assert "s3cret" not in prepared.to_yaml()
        request = httpx_mock.get_requests()[0]
        assert request.headers["Authorization"] == "Bearer rgnk_test"

    def test_instance_without_a_sealing_key_fails_rather_than_downgrading(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET", url=KEY_URL, status_code=404, json={"detail": "Not Found"}
        )
        with pytest.raises(
            GitOpsError, match="does not have secret sealing configured"
        ):
            prepare_manifest(
                _manifests(secret_doc({"stringData": {"a": "s3cret"}})), client=client
            )

    def test_no_secret_values_never_asks_for_a_key(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        prepared = prepare_manifest(_manifests(agent_doc()), client=client)
        assert httpx_mock.get_requests() == []
        assert prepared.sealing_fingerprint is None

    def test_unsealed_upload_inlines_plaintext(self, client: RagnerockClient) -> None:
        prepared = prepare_manifest(
            _manifests(secret_doc({"fromEnv": {"a": "V"}})),
            client=client,
            seal=False,
            env={"V": "plain"},
        )
        assert prepared.documents[0]["spec"] == {"stringData": {"a": "plain"}}
        assert not prepared.sealed

    def test_input_set_is_not_modified(self, sealing_pem: str) -> None:
        manifests = _manifests(secret_doc({"stringData": {"a": "s3cret"}}))
        prepare_manifest(manifests, sealing_public_key=sealing_pem)
        assert manifests.documents[0]["spec"] == {"stringData": {"a": "s3cret"}}

    def test_sealing_without_client_or_key_is_an_error(self) -> None:
        with pytest.raises(GitOpsError, match="sealing_public_key"):
            prepare_manifest(_manifests(secret_doc({"stringData": {"a": "s3cret"}})))


class TestDryRun:
    def test_elides_every_value_and_fetches_nothing(self, httpx_mock: Any) -> None:
        manifests = _manifests(
            secret_doc(
                {
                    "stringData": {"a": "inline-secret"},
                    "fromEnv": {"b": "V"},
                    "fromAwsSecretsManager": {"c": {"secretId": "prod/db"}},
                }
            ),
            agent_doc(),
        )
        prepared = render_dry_run(manifests, env={"V": "env-secret"})
        text = prepared.to_yaml()
        assert "inline-secret" not in text
        assert "env-secret" not in text
        encrypted = prepared.documents[0]["spec"]["encryptedData"]
        assert {e["ciphertext"] for e in encrypted.values()} == {REDACTED}
        assert encrypted["c"]["source"] == {
            "type": "fromAwsSecretsManager",
            "ref": {"secretId": "prod/db"},
        }
        assert httpx_mock.get_requests() == []

    def test_unsealed_shape(self) -> None:
        prepared = render_dry_run(
            _manifests(secret_doc({"stringData": {"a": "x"}})), seal=False
        )
        assert prepared.documents[0]["spec"] == {"stringData": {"a": REDACTED}}

    def test_unset_env_still_fails(self) -> None:
        with pytest.raises(GitOpsError, match="MISSING"):
            render_dry_run(
                _manifests(secret_doc({"fromEnv": {"a": "MISSING"}})), env={}
            )


class TestApplyManifests:
    def test_uploads_every_document_in_one_request(
        self,
        httpx_mock: Any,
        client: RagnerockClient,
        sealing_pem: str,
        tmp_path: Path,
        unseal: Callable[[str], str],
    ) -> None:
        (tmp_path / "secrets.yaml").write_text(
            yaml.safe_dump(secret_doc({"stringData": {"a": "s3cret"}}))
        )
        (tmp_path / "agents.yaml").write_text(yaml.safe_dump(agent_doc()))
        httpx_mock.add_response(method="POST", url=APPLY_URL, json=_REPORT)

        report = apply_manifests(client, [tmp_path], sealing_public_key=sealing_pem)

        assert report.ok
        assert report.changed == 1
        docs = _uploaded(httpx_mock)
        assert [d["kind"] for d in docs] == ["Agent", "Secret"]
        assert unseal(docs[1]["spec"]["encryptedData"]["a"]["ciphertext"]) == "s3cret"
        request = httpx_mock.get_requests()[-1]
        assert "dry_run" not in request.url.params
        assert 'filename="manifest.yaml"' in request.content.decode()
        assert "application/x-yaml" in request.content.decode()

    def test_plan_asks_the_server_to_roll_back(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=f"{APPLY_URL}?dry_run=true",
            json={**_REPORT, "dry_run": True},
        )
        report = apply_manifests(client, _manifests(agent_doc()), plan=True)
        assert report.dry_run

    def test_empty_set_makes_no_request(
        self, httpx_mock: Any, client: RagnerockClient, tmp_path: Path
    ) -> None:
        report = apply_manifests(client, [tmp_path])
        assert report.ok
        assert report.results == []
        assert httpx_mock.get_requests() == []

    def test_reads_stdin(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(method="POST", url=APPLY_URL, json=_REPORT)
        stdin = io.StringIO(yaml.safe_dump(agent_doc("piped")))
        apply_manifests(client, ["-"], stdin=stdin)
        assert _uploaded(httpx_mock)[0]["metadata"]["name"] == "piped"

    def test_server_rejection_raises(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=APPLY_URL,
            status_code=422,
            json={"detail": "Secret 'creds' carries an authored source"},
        )
        with pytest.raises(ValidationError, match="authored source"):
            apply_manifests(client, _manifests(agent_doc()))


class TestMasking:
    def test_masks_each_line_of_a_multiline_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        out = io.StringIO()
        mask_in_github_actions(
            ["-----BEGIN KEY-----\nsecretline\n-----END KEY-----"], stream=out
        )
        assert "::add-mask::secretline" in out.getvalue()
        assert "::add-mask::-----BEGIN KEY-----" in out.getvalue()

    def test_skips_short_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        out = io.StringIO()
        mask_in_github_actions(["ab"], stream=out)
        assert out.getvalue() == ""

    def test_noop_outside_actions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        out = io.StringIO()
        mask_in_github_actions(["a-real-looking-secret"], stream=out)
        assert out.getvalue() == ""

    def test_prepare_masks_resolved_values(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        sealing_pem: str,
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        prepare_manifest(
            _manifests(secret_doc({"stringData": {"a": "masked-value"}})),
            sealing_public_key=sealing_pem,
        )
        assert "::add-mask::masked-value" in capsys.readouterr().out
