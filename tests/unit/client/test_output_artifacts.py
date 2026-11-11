"""Tests for ``client.output_artifacts``."""

from __future__ import annotations

import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
import pytest

from ragnerock.client import RagnerockClient
from ragnerock.client.output_artifacts import ArtifactFormat
from ragnerock.errors import NotFoundError
from tests.unit.client.conftest import PROJECT_ID, last_params, last_request, url

ARTIFACT_ID = UUID("00000000-0000-0000-0000-000000000c01")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000701")
OUTPUT_ID = UUID("00000000-0000-0000-0000-000000000a01")
RUN_ID = UUID("00000000-0000-0000-0000-000000000801")
PROVENANCE_ID = UUID("00000000-0000-0000-0000-000000000802")
ARTIFACT = f"/api/output-artifacts/{ARTIFACT_ID}"
CONTENT = f"{ARTIFACT}/content"


def _artifact(**overrides: Any) -> dict[str, Any]:
    """An output artifact response body."""
    body: dict[str, Any] = {
        "id": str(ARTIFACT_ID),
        "project_id": PROJECT_ID,
        "agent_id": str(AGENT_ID),
        "agent_name": "daily",
        "output_id": str(OUTPUT_ID),
        "output_name": "table",
        "provenance_id": str(PROVENANCE_ID),
        "run_id": str(RUN_ID),
        "delivery_id": "00000000-0000-0000-0000-000000000c02",
        "document_id": None,
        "document_name": None,
        "file_name": "table.csv",
        "format": "csv",
        "media_type": "text/csv",
        "size_bytes": 24,
        "row_count": 2,
        "items_failed": 0,
        "cells_truncated": 0,
        "sha256": "abc",
        "created_at": "2026-10-19T00:00:00Z",
        "updated_at": "2026-10-19T00:00:00Z",
    }
    body.update(overrides)
    return body


class TestList:
    def test_list_sends_its_filters(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/projects/{PROJECT_ID}/output-artifacts"
                f"?limit=10&agent_id={AGENT_ID}"
            ),
            json={"artifacts": [], "next_cursor": None},
        )
        page = client.output_artifacts.list(
            UUID(PROJECT_ID), agent_id=AGENT_ID, limit=10
        )
        assert page.artifacts == []
        assert page.next_cursor is None
        assert last_params(httpx_mock) == {
            "limit": "10",
            "agent_id": str(AGENT_ID),
        }

    def test_list_pages_with_the_cursor(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        created_after = datetime(2026, 10, 1, tzinfo=UTC)
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/projects/{PROJECT_ID}/output-artifacts"
                f"?limit=50&output_id={OUTPUT_ID}&provenance_id={PROVENANCE_ID}&cursor=abc"
                "&created_after=2026-10-01T00%3A00%3A00%2B00%3A00"
            ),
            json={"artifacts": [_artifact()], "next_cursor": "def"},
        )
        page = client.output_artifacts.list(
            UUID(PROJECT_ID),
            output_id=OUTPUT_ID,
            provenance_id=PROVENANCE_ID,
            created_after=created_after,
            cursor="abc",
        )
        assert page.next_cursor == "def"
        assert page.artifacts[0].id == ARTIFACT_ID
        assert page.artifacts[0].format == ArtifactFormat.CSV


class TestReadAndDelete:
    def test_get(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(method="GET", url=url(ARTIFACT), json=_artifact())
        info = client.output_artifacts.get(ARTIFACT_ID)
        assert info.file_name == "table.csv"
        assert info.row_count == 2
        assert info.agent_id == AGENT_ID
        assert info.agent_name == "daily"
        assert info.output_id == OUTPUT_ID
        assert info.output_name == "table"
        # ``run_id`` is the run; ``provenance_id`` is what that run pinned.
        assert info.run_id == RUN_ID
        assert info.provenance_id == PROVENANCE_ID
        assert info.created_at == datetime(2026, 10, 19, tzinfo=UTC)

    def test_download_streams_to_disk(
        self, httpx_mock: Any, client: RagnerockClient, tmp_path: Path
    ) -> None:
        httpx_mock.add_response(method="GET", url=url(CONTENT), content=b"a,b\n1,2\n")
        target = tmp_path / "out.csv"
        written = client.output_artifacts.download(ARTIFACT_ID, str(target))
        assert written == target
        assert target.read_bytes() == b"a,b\n1,2\n"
        assert last_request(httpx_mock).method == "GET"

    def test_download_error_writes_nothing(
        self, httpx_mock: Any, client: RagnerockClient, tmp_path: Path
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(CONTENT),
            status_code=404,
            json={"detail": "Artifact not found"},
        )
        target = tmp_path / "out.csv"
        with pytest.raises(NotFoundError):
            client.output_artifacts.download(ARTIFACT_ID, target)
        assert not target.exists()

    def test_delete(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(method="DELETE", url=url(ARTIFACT), status_code=204)
        assert client.output_artifacts.delete(ARTIFACT_ID) is None
        assert last_request(httpx_mock).method == "DELETE"


class TestToDataFrame:
    def test_csv(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(method="GET", url=url(ARTIFACT), json=_artifact())
        httpx_mock.add_response(
            method="GET",
            url=url(CONTENT),
            content="﻿vendor,total\nacme,10\nglobex,20\n".encode(),
        )
        df = client.output_artifacts.to_dataframe(ARTIFACT_ID)
        # The byte-order mark does not leak into the first column name.
        assert list(df.columns) == ["vendor", "total"]
        assert df["total"].tolist() == [10, 20]

    def test_json_records_are_flattened(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET", url=url(ARTIFACT), json=_artifact(format="json")
        )
        records = {
            "records": [
                {"document_name": "a.pdf", "output": {"vendor": "acme", "total": 10}},
                {"document_name": "b.pdf", "output": {"vendor": "globex", "total": 20}},
            ]
        }
        httpx_mock.add_response(
            method="GET", url=url(CONTENT), content=json.dumps(records).encode()
        )
        df = client.output_artifacts.to_dataframe(ARTIFACT_ID)
        assert list(df.columns) == ["document_name", "vendor", "total"]
        assert df.iloc[1].to_dict() == {
            "document_name": "b.pdf",
            "vendor": "globex",
            "total": 20,
        }

    def test_xlsx_is_read_with_read_excel(
        self,
        httpx_mock: Any,
        client: RagnerockClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        seen: list[bytes] = []

        def fake_read_excel(body: io.BytesIO) -> pd.DataFrame:
            seen.append(body.getvalue())
            return pd.DataFrame({"a": [1]})

        monkeypatch.setattr(pd, "read_excel", fake_read_excel)
        httpx_mock.add_response(
            method="GET", url=url(ARTIFACT), json=_artifact(format="xlsx")
        )
        httpx_mock.add_response(method="GET", url=url(CONTENT), content=b"PK\x03\x04")
        df = client.output_artifacts.to_dataframe(ARTIFACT_ID)
        assert seen == [b"PK\x03\x04"]
        assert df["a"].tolist() == [1]

    def test_a_report_is_refused_before_downloading(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET", url=url(ARTIFACT), json=_artifact(format="docx")
        )
        with pytest.raises(ValueError, match="docx"):
            client.output_artifacts.to_dataframe(ARTIFACT_ID)
        assert len(httpx_mock.get_requests()) == 1

    def test_missing_pandas_names_the_extra(
        self, client: RagnerockClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "pandas", None)
        with pytest.raises(ImportError, match=r"ragnerock\[pandas\]"):
            client.output_artifacts.to_dataframe(ARTIFACT_ID)
