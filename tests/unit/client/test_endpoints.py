"""Tests for the endpoints section (``client.endpoints``)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from uuid import UUID

import pytest

from ragnerock.client import UNSET, RagnerockClient
from ragnerock.client.endpoints import (
    LATEST_SNAPSHOT_TAG,
    EndpointCreateResponse,
    EndpointExecutionListResponse,
    EndpointKeyRegenerateResponse,
    EndpointListResponse,
    EndpointResponse,
    EndpointStatsResponse,
    EndpointSubmitResponse,
    EndpointTaskResult,
    EndpointTaskStatus,
    EndpointType,
    McpToolsPreviewResponse,
)
from ragnerock.enums import CompatFormat
from ragnerock.errors import NotFoundError
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)
from tests.unit.conftest import TEST_HOST

ENDPOINT_ID = "00000000-0000-0000-0000-0000000000c1"
TASK_ID = "00000000-0000-0000-0000-0000000000d1"
WORKFLOW_ID = "00000000-0000-0000-0000-0000000000e1"
CONFIG_ID = "00000000-0000-0000-0000-0000000000f1"
NOW = "2026-09-08T00:00:00Z"
BASE = f"/api/projects/{PROJECT_ID}/endpoints"
PUBLIC = f"/api/endpoints/{ENDPOINT_ID}"


def _endpoint(**overrides: Any) -> dict[str, Any]:
    """Build an endpoint payload as the server returns it."""
    payload: dict[str, Any] = {
        "id": ENDPOINT_ID,
        "project_id": PROJECT_ID,
        "name": "W-2 Extractor",
        "description": None,
        "is_enabled": True,
        "endpoint_type": "WORKFLOW",
        "workflow_id": WORKFLOW_ID,
        "source_workflow_id": WORKFLOW_ID,
        "accepted_file_types": ["pdf"],
        "return_fields": [],
        "include_content": False,
        "ephemeral": False,
        "compat_format": None,
        "ai_config_id": None,
        "model_name": None,
        "default_params": None,
        "ip_whitelist": None,
        "rate_limit_rpm": 60,
        "auto_archive_jobs": False,
        "api_key_prefix": "rgnk_ep_a1b2",
        "api_key_expires_at": None,
        "active_snapshot_id": None,
        "snapshot_tag": "latest",
        "resources": [],
        "mcp_tool_name": "extract_w2",
        "mcp_tool_name_effective": "extract_w2",
        "mcp_tool_description": None,
        "created_at": NOW,
        "updated_at": NOW,
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _compat_endpoint(**overrides: Any) -> dict[str, Any]:
    return _endpoint(
        name="Compat",
        endpoint_type="MODEL_COMPAT",
        workflow_id=None,
        source_workflow_id=None,
        accepted_file_types=None,
        return_fields=None,
        compat_format="OPENAI",
        model_name="gpt-4o",
        mcp_tool_name=None,
        mcp_tool_name_effective=None,
        **overrides,
    )


def _metric() -> dict[str, Any]:
    return {
        "count": 4,
        "mean": 2.0,
        "std_dev": 0.5,
        "min": 1.0,
        "median": 2.0,
        "p95": 3.0,
        "p99": 3.0,
        "max": 3.0,
    }


class TestCreate:
    def test_workflow_create(self, httpx_mock, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{BASE}/"),
            json=_endpoint(api_key="rgnk_ep_plaintext", signing_secret="secret"),
        )

        result = client.endpoints.create(
            UUID(PROJECT_ID),
            name="W-2 Extractor",
            workflow_id=UUID(WORKFLOW_ID),
            accepted_file_types=["pdf"],
            return_fields=[{"operator_id": WORKFLOW_ID, "field_name": "wages"}],
            mcp_tool_name="extract_w2",
            mcp_tool_description="Pulls wages off a W-2.",
        )

        assert last_request(httpx_mock).method == "POST"
        assert last_json(httpx_mock) == {
            "name": "W-2 Extractor",
            "endpoint_type": "WORKFLOW",
            "workflow_id": WORKFLOW_ID,
            "accepted_file_types": ["pdf"],
            "return_fields": [{"operator_id": WORKFLOW_ID, "field_name": "wages"}],
            "include_content": False,
            "snapshot_tag": LATEST_SNAPSHOT_TAG,
            "ephemeral": False,
            "rate_limit_rpm": 60,
            "auto_archive_jobs": False,
            "mcp_tool_name": "extract_w2",
            "mcp_tool_description": "Pulls wages off a W-2.",
        }
        assert isinstance(result, EndpointCreateResponse)
        assert result.api_key == "rgnk_ep_plaintext"
        assert result.signing_secret == "secret"
        assert result.mcp_tool_name_effective == "extract_w2"

    def test_omitting_the_tool_name_leaves_it_to_the_server(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        """Absent means "derive one from the endpoint name"."""
        httpx_mock.add_response(
            method="POST",
            url=url(f"{BASE}/"),
            json=_endpoint(api_key="k", signing_secret="s"),
        )

        client.endpoints.create(
            UUID(PROJECT_ID),
            name="W-2 Extractor",
            workflow_id=UUID(WORKFLOW_ID),
            accepted_file_types=["pdf"],
            return_fields=[],
        )

        body = last_json(httpx_mock)
        assert "mcp_tool_name" not in body
        assert body["return_fields"] == []

    def test_compat_create_sends_the_binding(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{BASE}/"),
            json=_compat_endpoint(api_key="rgnk_ep_plaintext", signing_secret="s"),
        )

        result = client.endpoints.create(
            UUID(PROJECT_ID),
            name="Compat",
            endpoint_type=EndpointType.MODEL_COMPAT,
            compat_format=CompatFormat.OPENAI,
            ai_config_id=UUID(CONFIG_ID),
            model_name="gpt-4o",
            default_params={"temperature": 0.3},
            ip_whitelist=["10.0.0.0/8"],
            api_key_expires_in_days=30,
        )

        body = last_json(httpx_mock)
        assert body["endpoint_type"] == "MODEL_COMPAT"
        assert body["compat_format"] == "OPENAI"
        assert body["ai_config_id"] == CONFIG_ID
        assert body["model_name"] == "gpt-4o"
        assert body["default_params"] == {"temperature": 0.3}
        assert body["ip_whitelist"] == ["10.0.0.0/8"]
        assert body["api_key_expires_in_days"] == 30
        assert "workflow_id" not in body
        assert result.endpoint_type == EndpointType.MODEL_COMPAT
        assert result.compat_format == CompatFormat.OPENAI


class TestRead:
    def test_list(self, httpx_mock, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"{BASE}/?skip=0&limit=50"),
            json={"items": [_endpoint(), _compat_endpoint()], "total": 2},
        )

        result = client.endpoints.list(UUID(PROJECT_ID))

        assert last_params(httpx_mock) == {"skip": "0", "limit": "50"}
        assert isinstance(result, EndpointListResponse)
        assert result.total == 2
        assert [e.endpoint_type for e in result.items] == ["WORKFLOW", "MODEL_COMPAT"]

    def test_get_reports_both_tool_names(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET", url=url(f"{BASE}/{ENDPOINT_ID}"), json=_endpoint()
        )

        result = client.endpoints.get(UUID(PROJECT_ID), UUID(ENDPOINT_ID))

        assert isinstance(result, EndpointResponse)
        assert result.mcp_tool_name == "extract_w2"
        assert result.mcp_tool_name_effective == "extract_w2"
        assert result.snapshot_tag == "latest"

    def test_a_legacy_endpoint_reports_only_the_effective_name(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"{BASE}/{ENDPOINT_ID}"),
            json=_endpoint(mcp_tool_name=None, mcp_tool_name_effective="w_2_extractor"),
        )

        result = client.endpoints.get(UUID(PROJECT_ID), UUID(ENDPOINT_ID))

        assert result.mcp_tool_name is None
        assert result.mcp_tool_name_effective == "w_2_extractor"

    def test_get_missing_raises(self, httpx_mock, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"{BASE}/{ENDPOINT_ID}"),
            status_code=404,
            json={"detail": "Endpoint not found"},
        )

        with pytest.raises(NotFoundError):
            client.endpoints.get(UUID(PROJECT_ID), UUID(ENDPOINT_ID))


class TestUpdate:
    def _body(self, httpx_mock, client: RagnerockClient, **kwargs: Any) -> Any:
        httpx_mock.add_response(
            method="PATCH", url=url(f"{BASE}/{ENDPOINT_ID}"), json=_endpoint()
        )
        client.endpoints.update(UUID(PROJECT_ID), UUID(ENDPOINT_ID), **kwargs)
        assert last_request(httpx_mock).method == "PATCH"
        return last_json(httpx_mock)

    def test_omitted_fields_are_absent(self, httpx_mock, client: RagnerockClient):
        """A full dump would clear the bindings and tool name on every rename."""
        assert self._body(httpx_mock, client, name="Renamed") == {"name": "Renamed"}

    def test_explicit_none_clears_the_binding(
        self, httpx_mock, client: RagnerockClient
    ):
        assert self._body(httpx_mock, client, ai_config_id=None) == {
            "ai_config_id": None
        }

    def test_binding_set_and_defaults(self, httpx_mock, client: RagnerockClient):
        body = self._body(
            httpx_mock,
            client,
            ai_config_id=UUID(CONFIG_ID),
            model_name="gemini-2.5-pro",
            default_params={"max_tokens": 2048},
        )
        assert body == {
            "model_name": "gemini-2.5-pro",
            "ai_config_id": CONFIG_ID,
            "default_params": {"max_tokens": 2048},
        }

    def test_clearable_description_and_whitelist(
        self, httpx_mock, client: RagnerockClient
    ):
        body = self._body(httpx_mock, client, description=None, ip_whitelist=None)
        assert body == {"description": None, "ip_whitelist": None}

    def test_none_snapshot_tag_pins_the_endpoint(
        self, httpx_mock, client: RagnerockClient
    ):
        assert self._body(httpx_mock, client, snapshot_tag=None) == {
            "snapshot_tag": None
        }

    def test_tool_name_set_and_cleared_independently(
        self, httpx_mock, client: RagnerockClient
    ):
        assert self._body(httpx_mock, client, mcp_tool_name="renamed_tool") == {
            "mcp_tool_name": "renamed_tool"
        }
        assert self._body(httpx_mock, client, mcp_tool_name=None) == {
            "mcp_tool_name": None
        }
        assert self._body(httpx_mock, client, mcp_tool_description=None) == {
            "mcp_tool_description": None
        }

    def test_switches_are_sent(self, httpx_mock, client: RagnerockClient):
        body = self._body(
            httpx_mock,
            client,
            is_enabled=False,
            auto_archive_jobs=True,
            rate_limit_rpm=120,
            description=UNSET,
        )
        assert body == {
            "is_enabled": False,
            "auto_archive_jobs": True,
            "rate_limit_rpm": 120,
        }


class TestLifecycle:
    def test_delete(self, httpx_mock, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"{BASE}/{ENDPOINT_ID}"),
            json={"message": "Endpoint deleted"},
        )

        result = client.endpoints.delete(UUID(PROJECT_ID), UUID(ENDPOINT_ID))

        assert last_request(httpx_mock).method == "DELETE"
        assert result is None

    def test_redeploy(self, httpx_mock, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{BASE}/{ENDPOINT_ID}/redeploy"),
            json=_endpoint(warnings=["memory tools are disabled in endpoints"]),
        )

        result = client.endpoints.redeploy(UUID(PROJECT_ID), UUID(ENDPOINT_ID))

        assert last_request(httpx_mock).content == b""
        assert result.warnings == ["memory tools are disabled in endpoints"]

    def test_regenerate_key_without_expiry_sends_no_body(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{BASE}/{ENDPOINT_ID}/regenerate-key"),
            json={
                "api_key": "rgnk_ep_new",
                "api_key_prefix": "rgnk_ep_new",
                "signing_secret": "s2",
                "expires_at": None,
            },
        )

        result = client.endpoints.regenerate_key(UUID(PROJECT_ID), UUID(ENDPOINT_ID))

        assert last_request(httpx_mock).content == b""
        assert isinstance(result, EndpointKeyRegenerateResponse)
        assert result.api_key == "rgnk_ep_new"
        assert result.expires_at is None

    def test_regenerate_key_with_expiry(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{BASE}/{ENDPOINT_ID}/regenerate-key"),
            json={
                "api_key": "rgnk_ep_new",
                "api_key_prefix": "rgnk_ep_new",
                "signing_secret": "s2",
                "expires_at": "2026-10-08T00:00:00Z",
            },
        )

        result = client.endpoints.regenerate_key(
            UUID(PROJECT_ID), UUID(ENDPOINT_ID), expires_in_days=30
        )

        assert last_json(httpx_mock) == {"expires_in_days": 30}
        assert result.expires_at is not None


class TestMetrics:
    def test_get_stats(self, httpx_mock, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"{BASE}/{ENDPOINT_ID}/stats"),
            json={
                "total_executions": 4,
                "succeeded_count": 3,
                "failed_count": 1,
                "success_rate": 0.75,
                "duration": _metric(),
                "input_tokens": _metric(),
                "output_tokens": _metric(),
                "pages_processed": _metric(),
                "compute_seconds": _metric(),
                "percentiles_as_of": NOW,
            },
        )

        result = client.endpoints.get_stats(UUID(PROJECT_ID), UUID(ENDPOINT_ID))

        assert isinstance(result, EndpointStatsResponse)
        assert result.success_rate == 0.75
        assert result.duration is not None
        assert result.duration.p95 == 3.0

    def test_list_executions_defaults(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"{BASE}/{ENDPOINT_ID}/executions"
                "?sort_by=created_at&sort_order=desc&skip=0&limit=50"
            ),
            json={
                "items": [
                    {
                        "id": TASK_ID,
                        "task_id": TASK_ID,
                        "request_id": TASK_ID,
                        "status": "succeeded",
                        "created_at": NOW,
                        "completed_at": NOW,
                        "duration_seconds": 1.5,
                        "compute_seconds": 1.2,
                        "error_code": None,
                        "error_message": None,
                    }
                ],
                "total": 1,
                "skip": 0,
                "limit": 50,
            },
        )

        result = client.endpoints.list_executions(UUID(PROJECT_ID), UUID(ENDPOINT_ID))

        assert last_params(httpx_mock) == {
            "sort_by": "created_at",
            "sort_order": "desc",
            "skip": "0",
            "limit": "50",
        }
        assert isinstance(result, EndpointExecutionListResponse)
        assert result.items[0].status == EndpointTaskStatus.SUCCEEDED
        assert result.items[0].compute_seconds == 1.2

    def test_list_executions_filters(self, httpx_mock, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET",
            url=re.compile(re.escape(url(f"{BASE}/{ENDPOINT_ID}/executions")) + r"\?"),
            json={"items": [], "total": 0, "skip": 10, "limit": 5},
        )

        client.endpoints.list_executions(
            UUID(PROJECT_ID),
            UUID(ENDPOINT_ID),
            status="failed",
            date_from="2026-09-01T00:00:00Z",
            date_to="2026-09-08T00:00:00Z",
            sort_by="compute_seconds",
            sort_order="asc",
            skip=10,
            limit=5,
        )

        assert last_params(httpx_mock) == {
            "status": "failed",
            "date_from": "2026-09-01T00:00:00Z",
            "date_to": "2026-09-08T00:00:00Z",
            "sort_by": "compute_seconds",
            "sort_order": "asc",
            "skip": "10",
            "limit": "5",
        }


class TestUrls:
    def test_mcp_url_is_built_from_the_host(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        assert (
            client.endpoints.mcp_url(UUID(ENDPOINT_ID))
            == f"{TEST_HOST}/api/endpoints/{ENDPOINT_ID}/mcp"
        )
        # A URL builder: no request is made.
        assert httpx_mock.get_requests() == []

    @pytest.mark.parametrize(
        ("fmt", "suffix"),
        [
            (CompatFormat.OPENAI, "/openai/v1"),
            (CompatFormat.ANTHROPIC, "/anthropic"),
            ("GEMINI", "/gemini"),
        ],
    )
    def test_compat_base_url_per_format(
        self, httpx_mock, client: RagnerockClient, fmt: str, suffix: str
    ) -> None:
        assert (
            client.endpoints.compat_base_url(UUID(ENDPOINT_ID), fmt)
            == f"{TEST_HOST}/api/endpoints/{ENDPOINT_ID}{suffix}"
        )
        assert httpx_mock.get_requests() == []

    def test_compat_base_url_rejects_an_unknown_format(
        self, client: RagnerockClient
    ) -> None:
        with pytest.raises(ValueError):
            client.endpoints.compat_base_url(UUID(ENDPOINT_ID), "COHERE")


class TestMcpTools:
    def test_returns_raw_descriptors_and_warnings(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        """Descriptors keep MCP's own wire names (``inputSchema``, ``_meta``)."""
        httpx_mock.add_response(
            method="GET",
            url=url(f"{BASE}/{ENDPOINT_ID}/mcp/tools"),
            json={
                "default_wait_seconds": 55,
                "max_wait_seconds": 240,
                "tools": [
                    {
                        "name": "extract_w2",
                        "description": "d",
                        "inputSchema": {"type": "object"},
                        "outputSchema": {"type": "object", "properties": {}},
                        "annotations": {"readOnlyHint": False},
                        "_meta": {"anthropic/maxResultSizeChars": 98304},
                    }
                ],
                "warnings": ["a resource is named wait_seconds"],
            },
        )

        result = client.endpoints.mcp_tools(UUID(PROJECT_ID), UUID(ENDPOINT_ID))

        assert isinstance(result, McpToolsPreviewResponse)
        tool = result.tools[0]
        assert tool.name == "extract_w2"
        assert tool.input_schema == {"type": "object"}
        assert tool.output_schema == {"type": "object", "properties": {}}
        assert tool.annotations == {"readOnlyHint": False}
        assert tool.meta == {"anthropic/maxResultSizeChars": 98304}
        assert result.warnings == ["a resource is named wait_seconds"]
        assert result.default_wait_seconds == 55
        assert result.enabled is True


def _accepted() -> dict[str, Any]:
    return {
        "task_id": TASK_ID,
        "request_id": TASK_ID,
        "status": "accepted",
        "poll_url": f"/api/endpoints/{ENDPOINT_ID}/{TASK_ID}",
    }


class TestSubmit:
    """What goes on the wire for each signature an endpoint can have."""

    def test_uses_the_endpoint_key(self, httpx_mock, client: RagnerockClient) -> None:
        httpx_mock.add_response(method="POST", url=url(PUBLIC), json=_accepted())

        result = client.endpoints.submit(UUID(ENDPOINT_ID), api_key="rk_ep_x")

        assert last_request(httpx_mock).headers["Authorization"] == "Bearer rk_ep_x"
        assert isinstance(result, EndpointSubmitResponse)
        assert result.task_id == UUID(TASK_ID)
        assert result.status == EndpointTaskStatus.ACCEPTED

    def test_a_no_input_endpoint_is_called_with_no_body(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(method="POST", url=url(PUBLIC), json=_accepted())

        client.endpoints.submit(UUID(ENDPOINT_ID), api_key="rk_ep_x")

        request = last_request(httpx_mock)
        assert request.content == b""
        assert "content-type" not in request.headers

    def test_a_single_file_endpoint_sends_the_data_part(
        self, httpx_mock, client: RagnerockClient, tmp_path: Path
    ) -> None:
        upload = tmp_path / "w2.pdf"
        upload.write_bytes(b"%PDF-")
        httpx_mock.add_response(method="POST", url=url(PUBLIC), json=_accepted())

        client.endpoints.submit(
            UUID(ENDPOINT_ID), api_key="rk_ep_x", file_path=str(upload)
        )

        request = last_request(httpx_mock)
        assert request.headers["content-type"].startswith("multipart/form-data")
        assert b'name="data"; filename="w2.pdf"' in request.content
        assert b"%PDF-" in request.content

    def test_named_parts_and_values_are_sent_by_resource_name(
        self, httpx_mock, client: RagnerockClient, tmp_path: Path
    ) -> None:
        first = tmp_path / "w2.pdf"
        first.write_bytes(b"%PDF-")
        second = tmp_path / "1040.pdf"
        second.write_bytes(b"%PDF-")
        httpx_mock.add_response(method="POST", url=url(PUBLIC), json=_accepted())

        client.endpoints.submit(
            UUID(ENDPOINT_ID),
            api_key="rk_ep_x",
            file_parts={"w2": str(first), "return": second},
            values={"tax_year": "2025"},
            metadata={"client": "acme"},
            callback_url="https://hooks.example.com/rk",
            idempotency_key="retry-1",
        )

        content = last_request(httpx_mock).content
        assert b'name="w2"; filename="w2.pdf"' in content
        assert b'name="return"; filename="1040.pdf"' in content
        assert b'name="data"' not in content
        assert b'name="tax_year"\r\n\r\n2025' in content
        assert b'name="metadata"\r\n\r\n{"client": "acme"}' in content
        assert b'name="callback_url"\r\n\r\nhttps://hooks.example.com/rk' in content
        assert b'name="idempotency_key"\r\n\r\nretry-1' in content

    def test_values_alone_are_form_encoded(
        self, httpx_mock, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(method="POST", url=url(PUBLIC), json=_accepted())

        client.endpoints.submit(
            UUID(ENDPOINT_ID),
            api_key="rk_ep_x",
            values={"tax_year": "2025"},
            metadata={"a": 1},
        )

        request = last_request(httpx_mock)
        assert request.headers["content-type"] == "application/x-www-form-urlencoded"
        form = parse_qs(request.content.decode())
        assert form["tax_year"] == ["2025"]
        assert json.loads(form["metadata"][0]) == {"a": 1}

    def test_it_refuses_both_kinds_of_file_input(
        self, httpx_mock, client: RagnerockClient, tmp_path: Path
    ) -> None:
        """An endpoint binds the unnamed part or named ones, never both."""
        upload = tmp_path / "w2.pdf"
        upload.write_bytes(b"%PDF-")

        with pytest.raises(ValueError, match="not both"):
            client.endpoints.submit(
                UUID(ENDPOINT_ID),
                api_key="rk_ep_x",
                file_path=upload,
                file_parts={"w2": upload},
            )
        assert httpx_mock.get_requests() == []


class TestPoll:
    def _poll(self, httpx_mock, client: RagnerockClient, payload: dict[str, Any]):
        httpx_mock.add_response(
            method="GET", url=url(f"{PUBLIC}/{TASK_ID}"), json=payload
        )
        result = client.endpoints.poll(
            UUID(ENDPOINT_ID), UUID(TASK_ID), api_key="rk_ep_x"
        )
        assert last_request(httpx_mock).headers["Authorization"] == "Bearer rk_ep_x"
        assert isinstance(result, EndpointTaskResult)
        return result

    def test_processing(self, httpx_mock, client: RagnerockClient) -> None:
        result = self._poll(
            httpx_mock,
            client,
            {
                "task_id": TASK_ID,
                "status": "processing",
                "phase": "annotating",
                "progress": {"subtasks_completed": 1, "subtasks_total": 3},
                "created_at": NOW,
                "elapsed_seconds": 2.5,
            },
        )

        assert result.status == EndpointTaskStatus.PROCESSING
        assert result.phase == "annotating"
        assert result.progress is not None
        assert result.progress.subtasks_total == 3
        assert result.elapsed_seconds == 2.5
        assert result.result is None

    def test_succeeded(self, httpx_mock, client: RagnerockClient) -> None:
        result = self._poll(
            httpx_mock,
            client,
            {
                "task_id": TASK_ID,
                "status": "succeeded",
                "metadata": {},
                "ragnerock_metadata": {
                    "endpoint_id": ENDPOINT_ID,
                    "workflow_id": WORKFLOW_ID,
                    "duration_seconds": 1.0,
                    "compute_seconds": 1.0,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "pages_processed": 2,
                },
                "result": {"wages": 1},
                "truncated": False,
            },
        )

        assert result.status == EndpointTaskStatus.SUCCEEDED
        assert result.result == {"wages": 1}
        assert result.metadata == {}
        assert result.ragnerock_metadata is not None
        assert result.ragnerock_metadata["pages_processed"] == 2
        assert result.truncated is False
        assert result.error is None

    def test_failed(self, httpx_mock, client: RagnerockClient) -> None:
        result = self._poll(
            httpx_mock,
            client,
            {
                "task_id": TASK_ID,
                "status": "failed",
                "error": {"code": "workflow_execution_failed", "message": "boom"},
            },
        )

        assert result.status == EndpointTaskStatus.FAILED
        assert result.error is not None
        assert result.error.code == "workflow_execution_failed"
        assert result.error.message == "boom"
