"""Tests for ``client.workflows`` and ``client.workflows.change_requests``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from ragnerock.client import RagnerockClient
from ragnerock.client.workflows import (
    ChangeRequestStatus,
    tool_call_resource,
    web_fetch_resource,
)
from ragnerock.errors import AuthenticationError, RagnerockError
from ragnerock.resources.document import FileType
from ragnerock.resources.workflow import WorkflowSchedule
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

WORKFLOW_ID = UUID("00000000-0000-0000-0000-000000000701")
NODE_ID = UUID("00000000-0000-0000-0000-000000000702")
OPERATOR_ID = UUID("00000000-0000-0000-0000-000000000601")
REQUEST_ID = UUID("00000000-0000-0000-0000-000000000901")
PROPOSAL_ID = UUID("00000000-0000-0000-0000-000000000902")
WF = f"/api/workflows/{WORKFLOW_ID}"
CR = f"{WF}/change-requests/{REQUEST_ID}"


def _workflow(**overrides: Any) -> dict[str, Any]:
    """A workflow response body."""
    body: dict[str, Any] = {
        "id": str(WORKFLOW_ID),
        "project_id": PROJECT_ID,
        "name": "ingest",
        "description": None,
        "created_by_id": "00000000-0000-0000-0000-0000000000aa",
        "created_at": "2026-10-19T00:00:00Z",
        "updated_at": "2026-10-19T00:00:00Z",
        "is_active": True,
        "auto_run_on_upload": False,
        "execution_order": [],
        "nodes": [],
    }
    body.update(overrides)
    return body


def _node(**overrides: Any) -> dict[str, Any]:
    """A workflow node response body."""
    body: dict[str, Any] = {
        "id": str(NODE_ID),
        "workflow_id": str(WORKFLOW_ID),
        "operator_id": str(OPERATOR_ID),
        "operator_name": "scout",
        "operator_jsonschema": {},
        "condition": None,
        "persist": True,
        "on_error": "SKIP_NODE",
        "max_retries": 0,
        "annotations_only": False,
        "condition_mode": None,
        "position_x": None,
        "position_y": None,
        "position_z": None,
        "in_nodes": [],
        "out_nodes": [],
        "required_functions": [],
    }
    body.update(overrides)
    return body


def _change_request(**overrides: Any) -> dict[str, Any]:
    """A change request response body."""
    body: dict[str, Any] = {
        "id": str(REQUEST_ID),
        "account_id": "00000000-0000-0000-0000-0000000000bb",
        "project_id": PROJECT_ID,
        "workflow_id": str(WORKFLOW_ID),
        "trigger_operator_id": str(OPERATOR_ID),
        "trigger_operator_name": "new_form_type",
        "status": "pending",
        "document_count": 3,
        "opened_by_job_id": "00000000-0000-0000-0000-0000000000cc",
        "created_at": "2026-09-30T00:00:00Z",
        "updated_at": "2026-09-30T00:00:00Z",
    }
    body.update(overrides)
    return body


def _proposal(**overrides: Any) -> dict[str, Any]:
    """A change proposal response body."""
    body: dict[str, Any] = {
        "id": str(PROPOSAL_ID),
        "change_request_id": str(REQUEST_ID),
        "revision": 1,
        "status": "ready",
        "summary": "Add a say-on-pay agent",
        "validation_errors": [],
        "created_at": "2026-09-30T00:00:00Z",
        "proposed_manifest": [{"kind": "Workflow"}],
        "diff": {"objects": [], "nodes": [], "edges": [], "warnings": []},
    }
    body.update(overrides)
    return body


def _document(**overrides: Any) -> dict[str, Any]:
    """A change request document response body."""
    body: dict[str, Any] = {
        "id": "00000000-0000-0000-0000-000000000903",
        "change_request_id": str(REQUEST_ID),
        "document_id": "00000000-0000-0000-0000-000000000101",
        "job_id": "00000000-0000-0000-0000-000000000801",
        "signal": "unknown form 8-K/A",
        "created_at": "2026-09-30T00:00:00Z",
    }
    body.update(overrides)
    return body


class TestWorkflowCrud:
    def test_list(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/workflows/?project_ids={PROJECT_ID}&skip=0&limit=100"),
            json={
                "workflows": [_workflow(node_count=2)],
                "total": 1,
                "skip": 0,
                "limit": 100,
            },
        )
        page = client.workflows.list(project_ids=PROJECT_ID)
        assert page.total == 1
        assert page.workflows[0].id == WORKFLOW_ID
        assert page.workflows[0].node_count == 2

    def test_list_without_projects_omits_the_filter(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/workflows/?skip=10&limit=5"),
            json={"workflows": [], "total": 0, "skip": 10, "limit": 5},
        )
        client.workflows.list(skip=10, limit=5)
        assert "project_ids" not in last_params(httpx_mock)

    def test_get_parses_nodes_inputs_outputs_and_schedule(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        sink_id = "00000000-0000-0000-0000-000000000a01"
        resource_id = "00000000-0000-0000-0000-000000000b01"
        httpx_mock.add_response(
            method="GET",
            url=url(WF),
            json=_workflow(
                nodes=[
                    {
                        "id": str(NODE_ID),
                        "operator_id": str(OPERATOR_ID),
                        "operator_name": "scout",
                        "operator_jsonschema": {},
                        "operator_chunk_type": 0,
                        "condition": None,
                        "persist": True,
                        "on_error": "SKIP_NODE",
                        "annotations_only": False,
                        "condition_mode": None,
                        "position_x": 1,
                        "position_y": 2,
                        "position_z": None,
                        "in_nodes": [],
                        "out_nodes": [],
                        "required_functions": ["crm__get_customer"],
                    }
                ],
                resources=[
                    {
                        "id": resource_id,
                        "name": "input",
                        "type": "file",
                        "position": 0,
                    }
                ],
                sinks=[
                    {
                        "id": sink_id,
                        "name": "table",
                        "kind": "artifact",
                        "position": 0,
                        "node_id": "00000000-0000-0000-0000-000000000a02",
                        "operator_id": "00000000-0000-0000-0000-000000000a03",
                        "table_name": "table",
                        "parent_node_ids": [str(NODE_ID)],
                        "config": {"kind": "artifact", "format": "csv"},
                        "issues": [],
                    }
                ],
                schedule={"cron": "0 6 * * *", "timezone": "UTC", "enabled": True},
                schedule_state={"paused": True, "consecutive_failures": 3},
                pending_change_request_count=2,
            ),
        )
        wf = client.workflows.get(WORKFLOW_ID)
        assert wf.nodes[0].required_functions == ["crm__get_customer"]
        assert wf.nodes[0].position_x == 1
        assert wf.resources[0].name == "input"
        assert str(wf.sinks[0].id) == sink_id
        assert wf.sinks[0].config["format"] == "csv"
        assert wf.schedule == WorkflowSchedule(cron="0 6 * * *")
        assert wf.schedule_state is not None
        assert wf.schedule_state.paused is True
        assert wf.pending_change_request_count == 2
        assert wf.created_at is not None and wf.created_at.tzinfo is not None

    def test_create_sends_defaults(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST", url=url("/api/workflows/"), json=_workflow()
        )
        wf = client.workflows.create(project_id=UUID(PROJECT_ID), name="ingest")
        assert wf.id == WORKFLOW_ID
        assert last_json(httpx_mock) == {
            "project_id": PROJECT_ID,
            "name": "ingest",
            "is_active": True,
            "auto_run_on_upload": False,
            "is_draft": False,
        }

    def test_create_with_resources_and_schedule(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST", url=url("/api/workflows/"), json=_workflow()
        )
        client.workflows.create(
            project_id=UUID(PROJECT_ID),
            name="daily",
            description="Daily pull",
            is_draft=True,
            resources=[web_fetch_resource("page", "https://example.com/page")],
            schedule=WorkflowSchedule(cron="0 6 * * *", timezone="America/New_York"),
        )
        body = last_json(httpx_mock)
        assert body["description"] == "Daily pull"
        assert body["is_draft"] is True
        assert body["resources"] == [
            {
                "name": "page",
                "type": "file",
                "position": 0,
                "source": {
                    "kind": "web_fetch",
                    "url": "https://example.com/page",
                    "embed": False,
                },
            }
        ]
        assert body["schedule"] == {
            "cron": "0 6 * * *",
            "timezone": "America/New_York",
            "enabled": True,
        }

    def test_create_with_no_inputs_sends_an_empty_list(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST", url=url("/api/workflows/"), json=_workflow()
        )
        client.workflows.create(project_id=UUID(PROJECT_ID), name="x", resources=[])
        assert last_json(httpx_mock)["resources"] == []

    def test_update_sends_only_given_fields(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="PUT", url=url(WF), json=_workflow(is_active=False)
        )
        wf = client.workflows.update(WORKFLOW_ID, is_active=False)
        assert last_json(httpx_mock) == {"is_active": False}
        assert wf.is_active is False

    def test_delete(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(method="DELETE", url=url(WF), status_code=204)
        assert client.workflows.delete(WORKFLOW_ID) is None
        assert last_request(httpx_mock).method == "DELETE"


class TestNodes:
    def test_add_node_sends_empty_lists_by_default(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(method="PUT", url=url(f"{WF}/nodes/"), json=_node())
        node = client.workflows.add_node(WORKFLOW_ID, operator_id=OPERATOR_ID)
        assert node.id == NODE_ID
        assert last_json(httpx_mock) == {
            "operator_id": str(OPERATOR_ID),
            "persist": True,
            "on_error": "SKIP_NODE",
            "max_retries": 0,
            "annotations_only": False,
            "in_node_ids": [],
            "out_node_ids": [],
            "include_schedule_context": False,
            "required_functions": [],
        }

    def test_add_node_sends_every_node_field(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        upstream = UUID("00000000-0000-0000-0000-0000000007a1")
        decorators = [{"type": "TOKEN_BUDGET", "max_tokens": 1000}]
        httpx_mock.add_response(
            method="PUT",
            url=url(f"{WF}/nodes/"),
            json=_node(
                required_functions=["crm__get_customer"],
                decorators=decorators,
                in_nodes=[str(upstream)],
            ),
        )
        node = client.workflows.add_node(
            WORKFLOW_ID,
            operator_id=OPERATOR_ID,
            condition={"score": {"$gt": 0.5}},
            on_error="FAIL_JOB",
            decorators=decorators,
            position_x=10,
            position_y=20,
            position_z=1,
            in_node_ids=[upstream],
            include_schedule_context=True,
            required_functions=["crm__get_customer"],
        )
        body = last_json(httpx_mock)
        assert body["condition"] == {"score": {"$gt": 0.5}}
        assert body["on_error"] == "FAIL_JOB"
        assert body["decorators"] == decorators
        assert (body["position_x"], body["position_y"], body["position_z"]) == (
            10,
            20,
            1,
        )
        assert body["in_node_ids"] == [str(upstream)]
        assert body["include_schedule_context"] is True
        assert body["required_functions"] == ["crm__get_customer"]
        assert node.required_functions == ["crm__get_customer"]
        assert node.in_nodes == [upstream]

    @pytest.mark.parametrize(
        ("given", "sent"),
        [(None, None), ([], []), (["crm__get_customer"], ["crm__get_customer"])],
        ids=["unchanged", "cleared", "replaced"],
    )
    def test_update_node_required_functions(
        self,
        httpx_mock: Any,
        client: RagnerockClient,
        given: list[str] | None,
        sent: list[str] | None,
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"{WF}/nodes/{NODE_ID}"),
            json=_node(required_functions=sent or []),
        )
        client.workflows.update_node(
            WORKFLOW_ID, NODE_ID, persist=False, required_functions=given
        )
        body = last_json(httpx_mock)
        assert body.get("required_functions") == sent
        assert ("required_functions" in body) is (given is not None)
        assert body["persist"] is False

    def test_update_node_clear_flags_and_passthrough(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        downstream = UUID("00000000-0000-0000-0000-0000000007b1")
        httpx_mock.add_response(
            method="PUT", url=url(f"{WF}/nodes/{NODE_ID}"), json=_node()
        )
        client.workflows.update_node(
            WORKFLOW_ID,
            NODE_ID,
            clear_condition=True,
            out_node_ids=[downstream],
            replay_policy="never",
            condition=None,
        )
        assert last_json(httpx_mock) == {
            "clear_condition": True,
            "out_node_ids": [str(downstream)],
            "replay_policy": "never",
        }

    def test_update_node_omits_unset_flags(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="PUT", url=url(f"{WF}/nodes/{NODE_ID}"), json=_node()
        )
        client.workflows.update_node(WORKFLOW_ID, NODE_ID, max_retries=2)
        assert last_json(httpx_mock) == {"max_retries": 2}

    def test_delete_node(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="DELETE", url=url(f"{WF}/nodes/{NODE_ID}"), status_code=204
        )
        assert client.workflows.delete_node(WORKFLOW_ID, NODE_ID) is None

    def test_test_condition(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{WF}/nodes/{NODE_ID}/test-condition"),
            json={"result": True, "evaluation_trace": "score > 0.5"},
        )
        result = client.workflows.test_condition(
            WORKFLOW_ID, NODE_ID, sample_context={"scout": {"score": 0.9}}
        )
        assert last_json(httpx_mock) == {"sample_context": {"scout": {"score": 0.9}}}
        assert result.result is True
        assert result.evaluation_trace == "score > 0.5"


class TestInputsAndOutputs:
    def test_set_resources_puts_the_whole_set(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="PUT", url=url(f"{WF}/resources"), json=_workflow(resources=[])
        )
        spec = tool_call_resource(
            "activity",
            tool="pendo",
            function="get_events",
            arguments={"since": "{{ schedule.window_start }}"},
            file_type=FileType.CSV,
        )
        client.workflows.set_resources(WORKFLOW_ID, resources=[spec])
        assert last_json(httpx_mock) == {"resources": [spec]}

    def test_set_sinks_puts_the_whole_set(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(method="PUT", url=url(f"{WF}/sinks"), json=_workflow())
        sink = {
            "name": "table",
            "parent_node_ids": [NODE_ID],
            "config": {"kind": "artifact", "format": "csv"},
        }
        response = client.workflows.set_sinks(WORKFLOW_ID, sinks=[sink])
        assert last_json(httpx_mock) == {
            "sinks": [
                {
                    "name": "table",
                    "parent_node_ids": [str(NODE_ID)],
                    "config": {"kind": "artifact", "format": "csv"},
                }
            ]
        }
        assert response.sinks == []

    def test_test_fetch_sends_the_source(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{WF}/resources/test-fetch"),
            json={
                "ok": True,
                "content_type": "text/csv",
                "content_bytes": 12,
                "preview": "a,b\n1,2\n",
                "resolved_arguments": {"since": "2026-10-26T00:00:00Z"},
            },
        )
        source = tool_call_resource(
            "activity",
            tool="pendo",
            function="get_events",
            arguments={"since": "{{ schedule.window_start }}"},
        )["source"]
        result = client.workflows.test_fetch(
            WORKFLOW_ID, source=source, window_hours=48
        )
        assert last_json(httpx_mock) == {"source": source, "window_hours": 48}
        assert result.ok is True
        assert result.resolved_arguments == {"since": "2026-10-26T00:00:00Z"}
        assert result.error is None

    def test_test_fetch_reports_a_failure(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{WF}/resources/test-fetch"),
            json={"ok": False, "error": "the tool's server refused the call"},
        )
        result = client.workflows.test_fetch(
            WORKFLOW_ID, source={"kind": "web_fetch", "url": "https://example.com"}
        )
        assert last_json(httpx_mock)["window_hours"] == 24
        assert result.ok is False
        assert result.error == "the tool's server refused the call"


class TestSchedules:
    def test_set_schedule_from_fields(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"{WF}/schedule"),
            json=_workflow(schedule={"cron": "0 6 * * *", "enabled": False}),
        )
        wf = client.workflows.set_schedule(
            WORKFLOW_ID,
            cron="0 6 * * *",
            timezone="America/New_York",
            enabled=False,
            lookback=3600,
        )
        assert last_json(httpx_mock) == {
            "cron": "0 6 * * *",
            "timezone": "America/New_York",
            "enabled": False,
            "lookback": 3600,
        }
        assert wf.schedule is not None
        assert wf.schedule.enabled is False

    def test_set_schedule_defaults(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="PUT", url=url(f"{WF}/schedule"), json=_workflow()
        )
        client.workflows.set_schedule(WORKFLOW_ID, cron="0 6 * * *")
        assert last_json(httpx_mock) == {
            "cron": "0 6 * * *",
            "timezone": "UTC",
            "enabled": True,
        }

    @pytest.mark.parametrize(
        "schedule",
        [
            WorkflowSchedule(cron="0 6 * * 1-5", timezone="America/New_York"),
            {"cron": "0 6 * * 1-5", "timezone": "America/New_York", "enabled": True},
        ],
        ids=["model", "dict"],
    )
    def test_set_schedule_from_a_schedule(
        self,
        httpx_mock: Any,
        client: RagnerockClient,
        schedule: WorkflowSchedule | dict[str, Any],
    ) -> None:
        httpx_mock.add_response(
            method="PUT", url=url(f"{WF}/schedule"), json=_workflow()
        )
        client.workflows.set_schedule(WORKFLOW_ID, schedule)
        assert last_json(httpx_mock) == {
            "cron": "0 6 * * 1-5",
            "timezone": "America/New_York",
            "enabled": True,
        }

    def test_set_schedule_refuses_both_forms(self, client: RagnerockClient) -> None:
        with pytest.raises(ValueError, match="not both"):
            client.workflows.set_schedule(
                WORKFLOW_ID, WorkflowSchedule(cron="0 6 * * *"), cron="0 7 * * *"
            )

    def test_set_schedule_requires_a_cron(self, client: RagnerockClient) -> None:
        with pytest.raises(ValueError, match="requires"):
            client.workflows.set_schedule(WORKFLOW_ID)

    def test_set_schedule_refuses_a_bare_crontab(self, client: RagnerockClient) -> None:
        with pytest.raises(TypeError, match="cron="):
            client.workflows.set_schedule(WORKFLOW_ID, "0 6 * * *")  # type: ignore[arg-type]

    def test_clear_schedule(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="DELETE", url=url(f"{WF}/schedule"), json=_workflow(schedule=None)
        )
        wf = client.workflows.clear_schedule(WORKFLOW_ID)
        assert wf.schedule is None

    def test_resume_schedule(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{WF}/schedule/resume"),
            json=_workflow(schedule_state={"paused": False}),
        )
        wf = client.workflows.resume_schedule(WORKFLOW_ID)
        assert last_request(httpx_mock).content == b""
        assert wf.schedule_state is not None
        assert wf.schedule_state.paused is False

    def test_schedule_preview(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/workflows/schedule-preview"),
            json={"fires": ["2026-10-28T06:00:00Z"], "errors": []},
        )
        preview = client.workflows.schedule_preview(cron="0 6 * * *")
        assert last_json(httpx_mock) == {"cron": "0 6 * * *", "timezone": "UTC"}
        assert preview.fires == ["2026-10-28T06:00:00Z"]
        assert preview.errors == []

    def test_run_now_creates_one_run_with_no_bindings(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        job_id = "00000000-0000-0000-0000-000000000801"
        run_id = "00000000-0000-0000-0000-000000000802"
        httpx_mock.add_response(
            method="POST",
            url=url("/api/jobs/"),
            json={"job_ids": [job_id], "run_ids": [run_id]},
        )
        result = client.workflows.run_now(WORKFLOW_ID, capture_execution_log=True)
        body = last_json(httpx_mock)
        assert body == {
            "workflow_id": str(WORKFLOW_ID),
            "runs": [{"inputs": {}}],
            "capture_execution_log": True,
        }
        # Explicit mode only: the per-document fan-out fields stay unset.
        assert "document_ids" not in body and "workflow_ids" not in body
        assert result.job_ids == [UUID(job_id)]
        assert "X-Ragnerock-Driver-Token" not in last_request(httpx_mock).headers


class TestResourceBuilders:
    def test_tool_call_resource_declares_a_file_by_default(self) -> None:
        spec = tool_call_resource(
            "activity", tool="pendo", function="get_events", file_type=FileType.CSV
        )
        assert spec == {
            "name": "activity",
            "type": "file",
            "position": 0,
            "source": {
                "kind": "tool_call",
                "tool": "pendo",
                "function": "get_events",
                "arguments": {},
                "embed": False,
                # The file type crosses the wire as its lowercase name.
                "file_type": "csv",
            },
        }

    def test_tool_call_resource_reduces_a_qualified_function(self) -> None:
        spec = tool_call_resource("a", tool="crm", function="crm__get_customer")
        assert spec["source"]["function"] == "get_customer"

    def test_tool_call_resource_keeps_another_tool_s_prefix(self) -> None:
        spec = tool_call_resource("a", tool="crm", function="erp__get_order")
        assert spec["source"]["function"] == "erp__get_order"

    def test_as_value_declares_a_value_resource(self) -> None:
        spec = web_fetch_resource(
            "page", "https://example.com/page", as_value=True, description="Page"
        )
        assert spec["type"] == "value"
        assert spec["description"] == "Page"
        assert spec["source"]["kind"] == "web_fetch"
        assert "file_type" not in spec["source"]

    def test_string_file_types_are_lowercased(self) -> None:
        spec = web_fetch_resource(
            "page", "https://example.com/a.md", file_type="Markdown", embed=True
        )
        assert spec["source"]["file_type"] == "markdown"
        assert spec["source"]["embed"] is True


class TestChangeRequests:
    def test_list_filters_by_status(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"{WF}/change-requests?skip=0&limit=50&status=pending"),
            json={"items": [_change_request()], "total": 1, "skip": 0, "limit": 50},
        )
        page = client.workflows.change_requests.list(
            WORKFLOW_ID, status=ChangeRequestStatus.PENDING
        )
        assert page.total == 1
        assert page.items[0].status == ChangeRequestStatus.PENDING
        assert page.items[0].resolved_at is None
        assert page.items[0].trigger_operator_name == "new_form_type"

    def test_list_without_status(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"{WF}/change-requests?skip=50&limit=25"),
            json={"items": [], "total": 0, "skip": 50, "limit": 25},
        )
        page = client.workflows.change_requests.list(WORKFLOW_ID, skip=50, limit=25)
        assert page.items == []

    def test_get_detail(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(CR),
            json={
                "request": _change_request(),
                "signals": [{"signal": "unknown form 8-K/A", "count": 3}],
                "documents": {
                    "items": [_document()],
                    "total": 3,
                    "skip": 0,
                    "limit": 50,
                },
                "revisions": [
                    {
                        "id": str(PROPOSAL_ID),
                        "revision": 1,
                        "status": "ready",
                        "summary": "Add a say-on-pay agent",
                        "generated_by_id": "00000000-0000-0000-0000-0000000000aa",
                        "created_at": "2026-09-30T00:00:00Z",
                    }
                ],
                "latest_proposal": _proposal(),
                "documents_awaiting_backfill": 0,
            },
        )
        detail = client.workflows.change_requests.get(WORKFLOW_ID, REQUEST_ID)
        assert detail.request.id == REQUEST_ID
        assert detail.signals[0].count == 3
        assert detail.documents is not None
        assert detail.documents.items[0].signal == "unknown form 8-K/A"
        assert detail.revisions[0].revision == 1
        assert detail.latest_proposal is not None
        assert detail.latest_proposal.proposed_manifest == [{"kind": "Workflow"}]

    def test_documents(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"{CR}/documents?skip=50&limit=50"),
            json={
                "items": [_document(document_missing=True)],
                "total": 51,
                "skip": 50,
                "limit": 50,
            },
        )
        page = client.workflows.change_requests.documents(
            WORKFLOW_ID, REQUEST_ID, skip=50
        )
        assert page.total == 51
        assert page.items[0].document_missing is True

    def test_get_proposal(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET", url=url(f"{CR}/proposals/{PROPOSAL_ID}"), json=_proposal()
        )
        proposal = client.workflows.change_requests.get_proposal(
            WORKFLOW_ID, REQUEST_ID, PROPOSAL_ID
        )
        assert proposal.status == "ready"
        assert proposal.diff["warnings"] == []

    def test_approve_sends_the_revision(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{CR}/approve"),
            json={
                "workflow_id": str(WORKFLOW_ID),
                "operators_created": 1,
                "operators_updated": 1,
                "snapshot_id": "00000000-0000-0000-0000-000000000904",
                "documents_awaiting_backfill": 3,
            },
        )
        result = client.workflows.change_requests.approve(
            WORKFLOW_ID, REQUEST_ID, proposal_id=PROPOSAL_ID
        )
        assert last_json(httpx_mock) == {"proposal_id": str(PROPOSAL_ID)}
        assert result.documents_awaiting_backfill == 3
        assert result.orphaned_operators == []

    def test_approve_with_a_token_surfaces_the_403(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{CR}/approve"),
            status_code=403,
            json={"detail": "Change requests must be approved by a signed-in user"},
        )
        with pytest.raises(AuthenticationError):
            client.workflows.change_requests.approve(
                WORKFLOW_ID, REQUEST_ID, proposal_id=PROPOSAL_ID
            )

    def test_approve_a_stale_revision_surfaces_the_409(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{CR}/approve"),
            status_code=409,
            json={"detail": "The workflow changed since this revision"},
        )
        with pytest.raises(RagnerockError) as exc_info:
            client.workflows.change_requests.approve(
                WORKFLOW_ID, REQUEST_ID, proposal_id=PROPOSAL_ID
            )
        assert exc_info.value.status_code == 409

    def test_reject_sends_the_note(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{CR}/reject"),
            json=_change_request(status="rejected", rejection_note="no"),
        )
        result = client.workflows.change_requests.reject(
            WORKFLOW_ID, REQUEST_ID, note="no"
        )
        assert last_json(httpx_mock) == {"note": "no"}
        assert result.status == ChangeRequestStatus.REJECTED
        assert result.rejection_note == "no"

    def test_reject_without_a_note(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{CR}/reject"),
            json=_change_request(status="rejected"),
        )
        client.workflows.change_requests.reject(WORKFLOW_ID, REQUEST_ID)
        assert last_json(httpx_mock) == {}

    def test_backfill(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{CR}/backfill"),
            json={"job_ids": [], "run_ids": [], "skipped_missing": 1, "remaining": 0},
        )
        result = client.workflows.change_requests.backfill(WORKFLOW_ID, REQUEST_ID)
        assert last_request(httpx_mock).content == b""
        assert result.skipped_missing == 1
        assert result.remaining == 0
