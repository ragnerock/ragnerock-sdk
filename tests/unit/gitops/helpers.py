"""Manifest document builders shared by the GitOps and CLI apply tests."""

from __future__ import annotations

from typing import Any


def secret_doc(spec: dict[str, Any], name: str = "creds") -> dict[str, Any]:
    """Build a ``Secret`` manifest document around a spec."""
    return {
        "apiVersion": "ragnerock.com/v1alpha1",
        "kind": "Secret",
        "metadata": {"name": name},
        "spec": spec,
    }


def agent_doc(name: str = "scorer") -> dict[str, Any]:
    """Build a minimal ``Agent`` manifest document."""
    return {
        "apiVersion": "ragnerock.com/v1alpha1",
        "kind": "Agent",
        "metadata": {"name": name, "annotations": {"ragnerock.com/project": "p"}},
        "spec": {"generationPrompt": "go", "chunkType": "document"},
    }
