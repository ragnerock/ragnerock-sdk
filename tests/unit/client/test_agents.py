"""Tests for ``client.agents`` and ``client.agents.change_requests``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from ragnerock.client import RagnerockClient
from ragnerock.client.agents import (
    ChangeRequestStatus,
    DraftSharedTasks,
    tool_call_input,
    web_fetch_input,
)
from ragnerock.errors import AuthenticationError, RagnerockError
from ragnerock.resources.agent import AgentSchedule
from ragnerock.resources.document import FileType
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

AGENT_ID = UUID("00000000-0000-0000-0000-000000000701")
NODE_ID = UUID("00000000-0000-0000-0000-000000000702")
TASK_ID = UUID("00000000-0000-0000-0000-000000000601")
REQUEST_ID = UUID("00000000-0000-0000-0000-000000000901")
PROPOSAL_ID = UUID("00000000-0000-0000-0000-000000000902")
DRAFT_ID = UUID("00000000-0000-0000-0000-000000000703")
RUN_ID = UUID("00000000-0000-0000-0000-000000000801")
PROVENANCE_ID = UUID("00000000-0000-0000-0000-000000000802")
BACKFILL_RUN_ID = UUID("00000000-0000-0000-0000-000000000811")
BACKFILL_PROVENANCE_ID = UUID("00000000-0000-0000-0000-000000000812")
AG = f"/api/agents/{AGENT_ID}"
CR = f"{AG}/change-requests/{REQUEST_ID}"
DRAFT = f"/api/agents/{DRAFT_ID}/draft-changes"


def _agent(**overrides: Any) -> dict[str, Any]:
    """An agent response body."""
    body: dict[str, Any] = {
        "id": str(AGENT_ID),
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
    """An agent node response body."""
    body: dict[str, Any] = {
        "id": str(NODE_ID),
        "agent_id": str(AGENT_ID),
        "task_id": str(TASK_ID),
        "task_name": "scout",
        "task_jsonschema": {},
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
        "agent_id": str(AGENT_ID),
        "trigger_task_id": str(TASK_ID),
        "trigger_task_name": "new_form_type",
        "status": "pending",
        "document_count": 3,
        "opened_by_run_id": "00000000-0000-0000-0000-0000000000cc",
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
        "proposed_manifest": [{"kind": "Agent"}],
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
        "run_id": str(RUN_ID),
        "provenance_id": str(PROVENANCE_ID),
        "signal": "unknown form 8-K/A",
        "created_at": "2026-09-30T00:00:00Z",
    }
    body.update(overrides)
    return body


class TestAgentCrud:
    def test_list(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/agents/?project_ids={PROJECT_ID}&skip=0&limit=100"),
            json={
                "agents": [_agent(node_count=2)],
                "total": 1,
                "skip": 0,
                "limit": 100,
            },
        )
        page = client.agents.list(project_ids=PROJECT_ID)
        assert page.total == 1
        assert page.agents[0].id == AGENT_ID
        assert page.agents[0].node_count == 2

    def test_list_without_projects_omits_the_filter(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/agents/?skip=10&limit=5"),
            json={"agents": [], "total": 0, "skip": 10, "limit": 5},
        )
        client.agents.list(skip=10, limit=5)
        assert "project_ids" not in last_params(httpx_mock)

    def test_get_parses_nodes_inputs_outputs_and_schedule(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        output_id = "00000000-0000-0000-0000-000000000a01"
        input_id = "00000000-0000-0000-0000-000000000b01"
        httpx_mock.add_response(
            method="GET",
            url=url(AG),
            json=_agent(
                nodes=[
                    {
                        "id": str(NODE_ID),
                        "task_id": str(TASK_ID),
                        "task_name": "scout",
                        "task_jsonschema": {},
                        "task_chunk_type": 0,
                        "task_kind": "LLM",
                        "condition": None,
                        "persist": True,
                        "on_error": "FAIL_RUN",
                        "annotations_only": False,
                        "condition_mode": None,
                        "position_x": 1,
                        "position_y": 2,
                        "position_z": None,
                        "in_nodes": [],
                        "out_nodes": [],
                        "target_input_id": input_id,
                        "context_input_ids": [],
                        "required_functions": ["crm__get_customer"],
                    }
                ],
                inputs=[
                    {
                        "id": input_id,
                        "name": "input",
                        "type": "file",
                        "position": 0,
                    }
                ],
                outputs=[
                    {
                        "id": output_id,
                        "name": "table",
                        "kind": "artifact",
                        "position": 0,
                        "node_id": "00000000-0000-0000-0000-000000000a02",
                        "task_id": "00000000-0000-0000-0000-000000000a03",
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
        agent = client.agents.get(AGENT_ID)
        assert agent.nodes[0].task_id == TASK_ID
        assert agent.nodes[0].task_name == "scout"
        assert agent.nodes[0].task_kind == "LLM"
        assert agent.nodes[0].on_error == "FAIL_RUN"
        assert agent.nodes[0].target_input_id == UUID(input_id)
        assert agent.nodes[0].required_functions == ["crm__get_customer"]
        assert agent.nodes[0].position_x == 1
        assert agent.inputs[0].name == "input"
        assert str(agent.outputs[0].id) == output_id
        assert agent.outputs[0].config["format"] == "csv"
        assert agent.schedule == AgentSchedule(cron="0 6 * * *")
        assert agent.schedule_state is not None
        assert agent.schedule_state.paused is True
        assert agent.pending_change_request_count == 2
        assert agent.shadow_of_id is None
        assert agent.created_at is not None and agent.created_at.tzinfo is not None

    def test_create_sends_defaults(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(method="POST", url=url("/api/agents/"), json=_agent())
        agent = client.agents.create(project_id=UUID(PROJECT_ID), name="ingest")
        assert agent.id == AGENT_ID
        assert last_json(httpx_mock) == {
            "project_id": PROJECT_ID,
            "name": "ingest",
            "is_active": True,
            "auto_run_on_upload": False,
            "is_draft": False,
        }

    def test_create_with_inputs_and_schedule(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(method="POST", url=url("/api/agents/"), json=_agent())
        client.agents.create(
            project_id=UUID(PROJECT_ID),
            name="daily",
            description="Daily pull",
            is_draft=True,
            inputs=[web_fetch_input("page", "https://example.com/page")],
            schedule=AgentSchedule(cron="0 6 * * *", timezone="America/New_York"),
        )
        body = last_json(httpx_mock)
        assert body["description"] == "Daily pull"
        assert body["is_draft"] is True
        assert "resources" not in body
        assert body["inputs"] == [
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
        httpx_mock.add_response(method="POST", url=url("/api/agents/"), json=_agent())
        client.agents.create(project_id=UUID(PROJECT_ID), name="x", inputs=[])
        assert last_json(httpx_mock)["inputs"] == []

    def test_update_sends_only_given_fields(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(method="PUT", url=url(AG), json=_agent(is_active=False))
        agent = client.agents.update(AGENT_ID, is_active=False)
        assert last_json(httpx_mock) == {"is_active": False}
        assert agent.is_active is False

    def test_delete(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(method="DELETE", url=url(AG), status_code=204)
        assert client.agents.delete(AGENT_ID) is None
        assert last_request(httpx_mock).method == "DELETE"


class TestNodes:
    def test_add_node_sends_empty_lists_by_default(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(method="PUT", url=url(f"{AG}/nodes/"), json=_node())
        node = client.agents.add_node(AGENT_ID, task_id=TASK_ID)
        assert node.id == NODE_ID
        assert last_json(httpx_mock) == {
            "task_id": str(TASK_ID),
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
            url=url(f"{AG}/nodes/"),
            json=_node(
                required_functions=["crm__get_customer"],
                decorators=decorators,
                in_nodes=[str(upstream)],
            ),
        )
        node = client.agents.add_node(
            AGENT_ID,
            task_id=TASK_ID,
            condition={"score": {"$gt": 0.5}},
            on_error="FAIL_RUN",
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
        assert body["on_error"] == "FAIL_RUN"
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
            url=url(f"{AG}/nodes/{NODE_ID}"),
            json=_node(required_functions=sent or []),
        )
        client.agents.update_node(
            AGENT_ID, NODE_ID, persist=False, required_functions=given
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
            method="PUT", url=url(f"{AG}/nodes/{NODE_ID}"), json=_node()
        )
        client.agents.update_node(
            AGENT_ID,
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

    def test_update_node_sends_input_wiring(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        target = UUID("00000000-0000-0000-0000-000000000b01")
        context = UUID("00000000-0000-0000-0000-000000000b02")
        httpx_mock.add_response(
            method="PUT",
            url=url(f"{AG}/nodes/{NODE_ID}"),
            json=_node(context_input_ids=[str(context)]),
        )
        node = client.agents.update_node(
            AGENT_ID,
            NODE_ID,
            task_id=TASK_ID,
            target_input_id=target,
            context_input_ids=[context],
        )
        assert last_json(httpx_mock) == {
            "task_id": str(TASK_ID),
            "target_input_id": str(target),
            "context_input_ids": [str(context)],
        }
        assert node.task_id == TASK_ID
        assert node.context_input_ids == [context]

    def test_update_node_clears_the_target_input(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="PUT", url=url(f"{AG}/nodes/{NODE_ID}"), json=_node()
        )
        client.agents.update_node(AGENT_ID, NODE_ID, clear_target_input=True)
        assert last_json(httpx_mock) == {"clear_target_input": True}

    def test_update_node_omits_unset_flags(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="PUT", url=url(f"{AG}/nodes/{NODE_ID}"), json=_node()
        )
        client.agents.update_node(AGENT_ID, NODE_ID, max_retries=2)
        assert last_json(httpx_mock) == {"max_retries": 2}

    def test_delete_node(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="DELETE", url=url(f"{AG}/nodes/{NODE_ID}"), status_code=204
        )
        assert client.agents.delete_node(AGENT_ID, NODE_ID) is None

    def test_test_condition(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{AG}/nodes/{NODE_ID}/test-condition"),
            json={"result": True, "evaluation_trace": "score > 0.5"},
        )
        result = client.agents.test_condition(
            AGENT_ID, NODE_ID, sample_context={"scout": {"score": 0.9}}
        )
        assert last_json(httpx_mock) == {"sample_context": {"scout": {"score": 0.9}}}
        assert result.result is True
        assert result.evaluation_trace == "score > 0.5"


class TestInputsAndOutputs:
    def test_set_inputs_puts_the_whole_set(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="PUT", url=url(f"{AG}/inputs"), json=_agent(inputs=[])
        )
        spec = tool_call_input(
            "activity",
            tool="pendo",
            function="get_events",
            arguments={"since": "{{ schedule.window_start }}"},
            file_type=FileType.CSV,
        )
        response = client.agents.set_inputs(AGENT_ID, inputs=[spec])
        assert last_json(httpx_mock) == {"inputs": [spec]}
        assert response.inputs == []

    def test_set_outputs_puts_the_whole_set(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(method="PUT", url=url(f"{AG}/outputs"), json=_agent())
        output = {
            "name": "table",
            "parent_node_ids": [NODE_ID],
            "config": {"kind": "artifact", "format": "csv"},
        }
        response = client.agents.set_outputs(AGENT_ID, outputs=[output])
        assert last_json(httpx_mock) == {
            "outputs": [
                {
                    "name": "table",
                    "parent_node_ids": [str(NODE_ID)],
                    "config": {"kind": "artifact", "format": "csv"},
                }
            ]
        }
        assert response.outputs == []

    def test_test_fetch_sends_the_source(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{AG}/inputs/test-fetch"),
            json={
                "ok": True,
                "content_type": "text/csv",
                "content_bytes": 12,
                "preview": "a,b\n1,2\n",
                "resolved_arguments": {"since": "2026-10-26T00:00:00Z"},
            },
        )
        source = tool_call_input(
            "activity",
            tool="pendo",
            function="get_events",
            arguments={"since": "{{ schedule.window_start }}"},
        )["source"]
        result = client.agents.test_fetch(AGENT_ID, source=source, window_hours=48)
        assert last_json(httpx_mock) == {"source": source, "window_hours": 48}
        assert result.ok is True
        assert result.resolved_arguments == {"since": "2026-10-26T00:00:00Z"}
        assert result.error is None

    def test_test_fetch_reports_a_failure(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{AG}/inputs/test-fetch"),
            json={"ok": False, "error": "the tool's server refused the call"},
        )
        result = client.agents.test_fetch(
            AGENT_ID, source={"kind": "web_fetch", "url": "https://example.com"}
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
            url=url(f"{AG}/schedule"),
            json=_agent(schedule={"cron": "0 6 * * *", "enabled": False}),
        )
        agent = client.agents.set_schedule(
            AGENT_ID,
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
        assert agent.schedule is not None
        assert agent.schedule.enabled is False

    def test_set_schedule_defaults(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(method="PUT", url=url(f"{AG}/schedule"), json=_agent())
        client.agents.set_schedule(AGENT_ID, cron="0 6 * * *")
        assert last_json(httpx_mock) == {
            "cron": "0 6 * * *",
            "timezone": "UTC",
            "enabled": True,
        }

    @pytest.mark.parametrize(
        "schedule",
        [
            AgentSchedule(cron="0 6 * * 1-5", timezone="America/New_York"),
            {"cron": "0 6 * * 1-5", "timezone": "America/New_York", "enabled": True},
        ],
        ids=["model", "dict"],
    )
    def test_set_schedule_from_a_schedule(
        self,
        httpx_mock: Any,
        client: RagnerockClient,
        schedule: AgentSchedule | dict[str, Any],
    ) -> None:
        httpx_mock.add_response(method="PUT", url=url(f"{AG}/schedule"), json=_agent())
        client.agents.set_schedule(AGENT_ID, schedule)
        assert last_json(httpx_mock) == {
            "cron": "0 6 * * 1-5",
            "timezone": "America/New_York",
            "enabled": True,
        }

    def test_set_schedule_refuses_both_forms(self, client: RagnerockClient) -> None:
        with pytest.raises(ValueError, match="not both"):
            client.agents.set_schedule(
                AGENT_ID, AgentSchedule(cron="0 6 * * *"), cron="0 7 * * *"
            )

    def test_set_schedule_requires_a_cron(self, client: RagnerockClient) -> None:
        with pytest.raises(ValueError, match="requires"):
            client.agents.set_schedule(AGENT_ID)

    def test_set_schedule_refuses_a_bare_crontab(self, client: RagnerockClient) -> None:
        with pytest.raises(TypeError, match="cron="):
            client.agents.set_schedule(AGENT_ID, "0 6 * * *")  # type: ignore[arg-type]

    def test_clear_schedule(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="DELETE", url=url(f"{AG}/schedule"), json=_agent(schedule=None)
        )
        agent = client.agents.clear_schedule(AGENT_ID)
        assert agent.schedule is None

    def test_resume_schedule(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{AG}/schedule/resume"),
            json=_agent(schedule_state={"paused": False}),
        )
        agent = client.agents.resume_schedule(AGENT_ID)
        assert last_request(httpx_mock).content == b""
        assert agent.schedule_state is not None
        assert agent.schedule_state.paused is False

    def test_schedule_preview(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/agents/schedule-preview"),
            json={"fires": ["2026-10-28T06:00:00Z"], "errors": []},
        )
        preview = client.agents.schedule_preview(cron="0 6 * * *")
        assert last_json(httpx_mock) == {"cron": "0 6 * * *", "timezone": "UTC"}
        assert preview.fires == ["2026-10-28T06:00:00Z"]
        assert preview.errors == []

    def test_run_now_creates_one_run_with_no_bindings(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        run_id = "00000000-0000-0000-0000-000000000801"
        provenance_id = "00000000-0000-0000-0000-000000000802"
        httpx_mock.add_response(
            method="POST",
            url=url("/api/runs/"),
            json={"run_ids": [run_id], "provenance_ids": [provenance_id]},
        )
        result = client.agents.run_now(AGENT_ID, capture_execution_log=True)
        body = last_json(httpx_mock)
        assert body == {
            "agent_id": str(AGENT_ID),
            "runs": [{"inputs": {}}],
            "capture_execution_log": True,
        }
        # Explicit mode only: the per-document fan-out fields stay unset.
        assert "document_ids" not in body and "agent_ids" not in body
        assert result.run_ids == [UUID(run_id)]
        assert "X-Ragnerock-Driver-Token" not in last_request(httpx_mock).headers


class TestInputBuilders:
    def test_tool_call_input_declares_a_file_by_default(self) -> None:
        spec = tool_call_input(
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

    def test_tool_call_input_reduces_a_qualified_function(self) -> None:
        spec = tool_call_input("a", tool="crm", function="crm__get_customer")
        assert spec["source"]["function"] == "get_customer"

    def test_tool_call_input_keeps_another_tool_s_prefix(self) -> None:
        spec = tool_call_input("a", tool="crm", function="erp__get_order")
        assert spec["source"]["function"] == "erp__get_order"

    def test_as_value_declares_a_value_input(self) -> None:
        spec = web_fetch_input(
            "page", "https://example.com/page", as_value=True, description="Page"
        )
        assert spec["type"] == "value"
        assert spec["description"] == "Page"
        assert spec["source"]["kind"] == "web_fetch"
        assert "file_type" not in spec["source"]

    def test_string_file_types_are_lowercased(self) -> None:
        spec = web_fetch_input(
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
            url=url(f"{AG}/change-requests?skip=0&limit=50&status=pending"),
            json={"items": [_change_request()], "total": 1, "skip": 0, "limit": 50},
        )
        page = client.agents.change_requests.list(
            AGENT_ID, status=ChangeRequestStatus.PENDING
        )
        assert page.total == 1
        assert page.items[0].status == ChangeRequestStatus.PENDING
        assert page.items[0].resolved_at is None
        assert page.items[0].trigger_task_name == "new_form_type"

    def test_list_without_status(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"{AG}/change-requests?skip=50&limit=25"),
            json={"items": [], "total": 0, "skip": 50, "limit": 25},
        )
        page = client.agents.change_requests.list(AGENT_ID, skip=50, limit=25)
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
        detail = client.agents.change_requests.get(AGENT_ID, REQUEST_ID)
        assert detail.request.id == REQUEST_ID
        assert detail.signals[0].count == 3
        assert detail.documents is not None
        assert detail.documents.items[0].signal == "unknown form 8-K/A"
        assert detail.revisions[0].revision == 1
        assert detail.latest_proposal is not None
        assert detail.latest_proposal.proposed_manifest == [{"kind": "Agent"}]

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
        page = client.agents.change_requests.documents(AGENT_ID, REQUEST_ID, skip=50)
        assert page.total == 51
        assert page.items[0].document_missing is True

    def test_documents_parse_runs_and_provenances(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"{CR}/documents?skip=0&limit=50"),
            json={
                "items": [
                    _document(
                        backfill_run_id=str(BACKFILL_RUN_ID),
                        backfill_provenance_id=str(BACKFILL_PROVENANCE_ID),
                    )
                ],
                "total": 1,
                "skip": 0,
                "limit": 50,
            },
        )
        record = client.agents.change_requests.documents(AGENT_ID, REQUEST_ID).items[0]
        # ``run_id`` is the run; ``provenance_id`` is what that run pinned.
        assert record.run_id == RUN_ID
        assert record.provenance_id == PROVENANCE_ID
        assert record.backfill_run_id == BACKFILL_RUN_ID
        assert record.backfill_provenance_id == BACKFILL_PROVENANCE_ID

    def test_get_proposal(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET", url=url(f"{CR}/proposals/{PROPOSAL_ID}"), json=_proposal()
        )
        proposal = client.agents.change_requests.get_proposal(
            AGENT_ID, REQUEST_ID, PROPOSAL_ID
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
                "agent_id": str(AGENT_ID),
                "tasks_created": 1,
                "tasks_updated": 1,
                "snapshot_id": "00000000-0000-0000-0000-000000000904",
                "documents_awaiting_backfill": 3,
            },
        )
        result = client.agents.change_requests.approve(
            AGENT_ID, REQUEST_ID, proposal_id=PROPOSAL_ID
        )
        assert last_json(httpx_mock) == {"proposal_id": str(PROPOSAL_ID)}
        assert result.documents_awaiting_backfill == 3
        assert result.orphaned_tasks == []

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
            client.agents.change_requests.approve(
                AGENT_ID, REQUEST_ID, proposal_id=PROPOSAL_ID
            )

    def test_approve_a_stale_revision_surfaces_the_409(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{CR}/approve"),
            status_code=409,
            json={"detail": "The agent changed since this revision"},
        )
        with pytest.raises(RagnerockError) as exc_info:
            client.agents.change_requests.approve(
                AGENT_ID, REQUEST_ID, proposal_id=PROPOSAL_ID
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
        result = client.agents.change_requests.reject(AGENT_ID, REQUEST_ID, note="no")
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
        client.agents.change_requests.reject(AGENT_ID, REQUEST_ID)
        assert last_json(httpx_mock) == {}

    def test_backfill(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{CR}/backfill"),
            json={
                "run_ids": [str(BACKFILL_RUN_ID)],
                "provenance_ids": [str(BACKFILL_PROVENANCE_ID)],
                "skipped_missing": 1,
                "remaining": 0,
            },
        )
        result = client.agents.change_requests.backfill(AGENT_ID, REQUEST_ID)
        assert last_request(httpx_mock).content == b""
        assert result.run_ids == [BACKFILL_RUN_ID]
        assert result.provenance_ids == [BACKFILL_PROVENANCE_ID]
        assert result.skipped_missing == 1
        assert result.remaining == 0


class TestDraftChanges:
    def test_draft_changes(self, httpx_mock: Any, client: RagnerockClient) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(DRAFT),
            json={
                "draft_id": str(DRAFT_ID),
                "original_id": str(AGENT_ID),
                "original_name": "ingest",
                "original_changed": False,
                "diff": {"objects": [], "nodes": [], "edges": [], "warnings": []},
                "shared_changes": [
                    {
                        "kind": "Task",
                        "name": "scout",
                        "agents": ["triage"],
                        "private_drafts": 1,
                    }
                ],
                "endpoints": ["scout-api"],
                "problems": [],
            },
        )
        changes = client.agents.draft_changes(DRAFT_ID)
        assert last_request(httpx_mock).method == "GET"
        assert changes.draft_id == DRAFT_ID
        assert changes.original_id == AGENT_ID
        assert changes.original_changed is False
        assert changes.diff is not None and changes.diff["warnings"] == []
        assert changes.shared_changes[0].kind == "Task"
        assert changes.shared_changes[0].agents == ["triage"]
        assert changes.shared_changes[0].private_drafts == 1
        assert changes.endpoints == ["scout-api"]
        assert changes.problems == []

    def test_draft_changes_without_a_diff(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(DRAFT),
            json={
                "draft_id": str(DRAFT_ID),
                "original_id": str(AGENT_ID),
                "original_name": "ingest",
                "original_changed": True,
                "diff": None,
                "problems": ["The agent changed since this draft was made."],
            },
        )
        changes = client.agents.draft_changes(DRAFT_ID)
        assert changes.original_changed is True
        assert changes.diff is None
        assert changes.shared_changes == []
        assert changes.problems == ["The agent changed since this draft was made."]

    @pytest.mark.parametrize(
        "shared_tasks",
        [DraftSharedTasks.ONLY_THIS_AGENT, "only_this_agent"],
        ids=["enum", "str"],
    )
    def test_keep_sends_where_shared_changes_go(
        self,
        httpx_mock: Any,
        client: RagnerockClient,
        shared_tasks: DraftSharedTasks | str,
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{DRAFT}/keep"),
            json={
                "agent_id": str(AGENT_ID),
                "agent_name": "ingest",
                "warnings": ["Code in 'summary' reads the renamed task 'scout'."],
            },
        )
        result = client.agents.keep_draft_changes(DRAFT_ID, shared_tasks=shared_tasks)
        assert last_json(httpx_mock) == {"shared_tasks": "only_this_agent"}
        assert result.agent_id == AGENT_ID
        assert result.agent_name == "ingest"
        assert result.warnings == ["Code in 'summary' reads the renamed task 'scout'."]

    def test_keep_without_shared_tasks_sends_an_empty_body(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{DRAFT}/keep"),
            json={"agent_id": str(AGENT_ID), "agent_name": "ingest"},
        )
        result = client.agents.keep_draft_changes(DRAFT_ID)
        assert last_json(httpx_mock) == {}
        assert result.warnings == []

    def test_keep_refused_surfaces_the_error(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{DRAFT}/keep"),
            status_code=409,
            json={"detail": "The agent changed since this draft was made"},
        )
        with pytest.raises(RagnerockError) as exc_info:
            client.agents.keep_draft_changes(
                DRAFT_ID, shared_tasks=DraftSharedTasks.EVERY_AGENT
            )
        assert exc_info.value.status_code == 409
        assert last_json(httpx_mock) == {"shared_tasks": "every_agent"}

    def test_refresh_returns_the_draft(
        self, httpx_mock: Any, client: RagnerockClient
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"{DRAFT}/refresh"),
            json=_agent(id=str(DRAFT_ID), is_draft=True, shadow_of_id=str(AGENT_ID)),
        )
        draft = client.agents.refresh_draft_changes(DRAFT_ID)
        assert last_request(httpx_mock).content == b""
        assert draft.id == DRAFT_ID
        assert draft.is_draft is True
        assert draft.shadow_of_id == AGENT_ID
