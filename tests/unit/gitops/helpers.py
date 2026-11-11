"""Manifest document builders shared by the GitOps and CLI apply tests."""

from __future__ import annotations

from typing import Any

from ragnerock.gitops import API_VERSION


def secret_doc(spec: dict[str, Any], name: str = "creds") -> dict[str, Any]:
    """Build a ``Secret`` manifest document around a spec."""
    return {
        "apiVersion": API_VERSION,
        "kind": "Secret",
        "metadata": {"name": name},
        "spec": spec,
    }


def task_doc(name: str = "scorer") -> dict[str, Any]:
    """Build a minimal ``Task`` manifest document."""
    return {
        "apiVersion": API_VERSION,
        "kind": "Task",
        "metadata": {"name": name, "annotations": {"ragnerock.com/project": "p"}},
        "spec": {"generationPrompt": "go", "chunkType": "document"},
    }
