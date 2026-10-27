"""GitOps apply against a live instance, in plan mode so nothing persists."""

from __future__ import annotations

from typing import Any

import pytest

from ragnerock import Engine, create_client
from ragnerock.errors import GitOpsError, NotFoundError
from ragnerock.gitops import (
    ManifestSet,
    apply_manifests,
    key_fingerprint,
    load_public_key,
)


def _docs(project: str, name: str) -> list[dict[str, Any]]:
    annotations = {"ragnerock.com/project": project}
    return [
        {
            "apiVersion": "ragnerock.com/v1alpha1",
            "kind": "Schema",
            "metadata": {"name": f"{name}_schema", "annotations": annotations},
            "spec": {
                "description": "SDK integration test",
                "jsonSchema": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}},
                    "required": ["label"],
                },
            },
        },
        {
            "apiVersion": "ragnerock.com/v1alpha1",
            "kind": "Agent",
            "metadata": {"name": f"{name}_agent", "annotations": annotations},
            "spec": {
                "description": "SDK integration test",
                "generationPrompt": "Label the passage.",
                "chunkType": "paragraph",
                "schema": f"{name}_schema",
            },
        },
    ]


def test_plan_reports_creates_and_rolls_back(
    conn_str: str, engine: Engine, unique_name: str
) -> None:
    name = unique_name.replace("-", "_")
    with create_client(conn_str) as client:
        report = apply_manifests(
            client, ManifestSet(documents=_docs(engine.project_name, name)), plan=True
        )
    assert report.dry_run
    assert report.ok, report.model_dump()
    actions = {(r.kind, r.name): r.action for r in report.results}
    assert actions[("Schema", f"{name}_schema")] == "created"
    assert actions[("Agent", f"{name}_agent")] == "created"


def test_sealing_key_fingerprint_is_stable(conn_str: str) -> None:
    with create_client(conn_str) as client:
        try:
            key = client.gitops.sealing_key()
        except NotFoundError:
            pytest.skip("instance has no sealing key configured")
        again = client.gitops.sealing_key()
    fingerprint = key_fingerprint(load_public_key(key.public_key))
    assert fingerprint == key_fingerprint(load_public_key(again.public_key))
    if key.fingerprint is not None:
        assert key.fingerprint == fingerprint


def test_plan_with_a_sealed_secret(conn_str: str, unique_name: str) -> None:
    secret = {
        "apiVersion": "ragnerock.com/v1alpha1",
        "kind": "Secret",
        "metadata": {"name": unique_name.replace("-", "_")},
        "spec": {"stringData": {"token": "integration-test-value"}},
    }
    with create_client(conn_str) as client:
        try:
            report = apply_manifests(client, ManifestSet(documents=[secret]), plan=True)
        except GitOpsError as e:
            if "sealing" in str(e):
                pytest.skip("instance has no sealing key configured")
            raise
    assert report.ok, report.model_dump()
    assert [r.action for r in report.results] == ["created"]
