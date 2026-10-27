"""Tests for the assignments section (:mod:`ragnerock.client.assignments`)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from ragnerock.client import RagnerockClient
from ragnerock.client.assignments import (
    STREAM_READ_TIMEOUT_SECONDS,
    AgentQuestionStatus,
    AssignmentCellEvent,
    AssignmentResponse,
    AssignmentStatus,
    AssignmentStatusEvent,
)
from ragnerock.errors import AuthenticationError
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

NOW = "2026-09-28T12:00:00Z"
ASSIGNMENTS = f"/api/projects/{PROJECT_ID}/assignments"


def _assignment(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "account_id": str(uuid.uuid4()),
        "project_id": PROJECT_ID,
        "agent_id": str(uuid.uuid4()),
        "notebook_id": str(uuid.uuid4()),
        "status": "queued",
        "turn_state": "ended",
        "runs_as_user_id": str(uuid.uuid4()),
        "turns": 0,
        "deliveries": 0,
        "wakes": 0,
        "compactions": 0,
        "budget_cost_weighted_tokens": 1_500_000,
        "spent_cost_weighted_tokens": 0,
        "reserved_cost_weighted_tokens": 0,
        "depth": 0,
        "last_error": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload.update(overrides)
    return payload


def _question(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "account_id": str(uuid.uuid4()),
        "project_id": PROJECT_ID,
        "assignment_id": str(uuid.uuid4()),
        "agent_id": str(uuid.uuid4()),
        "agent_name": "Filing reviewer",
        "notebook_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "question": "Which fiscal year?",
        "deadline": "2026-10-01T12:00:00Z",
        "status": "open",
        "answer": None,
        "answered_at": None,
        "answered_by_user_id": None,
        "created_at": "2026-09-29T12:00:00Z",
    }
    payload.update(overrides)
    return payload


def _sse(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode()


class TestCreate:
    def test_the_body_names_the_agent_the_task_and_the_rest(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        agent_id, schema_id = uuid.uuid4(), uuid.uuid4()
        deadline = datetime(2026, 10, 5, 9, tzinfo=UTC)
        httpx_mock.add_response(
            method="POST", url=url(ASSIGNMENTS), status_code=201, json=_assignment()
        )

        created = client.assignments.create(
            uuid.UUID(PROJECT_ID),
            agent_id=agent_id,
            task="Find the counterparties.",
            output_schema_id=schema_id,
            deadline=deadline,
        )

        body = last_json(httpx_mock)
        assert body["agent_id"] == str(agent_id)
        assert body["task"] == "Find the counterparties."
        assert body["output_schema_id"] == str(schema_id)
        assert datetime.fromisoformat(body["deadline"]) == deadline
        assert "parent_id" not in body
        assert created.status == AssignmentStatus.QUEUED

    def test_a_deadline_without_a_time_zone_is_refused_before_sending(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            client.assignments.create(
                uuid.UUID(PROJECT_ID),
                agent_id=uuid.uuid4(),
                task="Find the counterparties.",
                deadline=datetime(2026, 10, 5, 9),  # noqa: DTZ001 - naive on purpose
            )

        assert httpx_mock.get_requests() == []

    def test_create_carries_a_budget(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        agent_id = uuid.uuid4()
        httpx_mock.add_response(method="POST", url=url(ASSIGNMENTS), json=_assignment())

        client.assignments.create(
            uuid.UUID(PROJECT_ID), agent_id=agent_id, task="Check.", budget=40_000
        )

        assert last_json(httpx_mock) == {
            "agent_id": str(agent_id),
            "task": "Check.",
            "budget_cost_weighted_tokens": 40_000,
        }

    def test_dispatch_gives_a_running_assignment_a_child(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        parent_id, agent_id = uuid.uuid4(), uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(ASSIGNMENTS),
            json=_assignment(parent_id=str(parent_id), depth=1),
        )

        child = client.assignments.dispatch(
            uuid.UUID(PROJECT_ID),
            parent_id=parent_id,
            agent_id=agent_id,
            task="Review counterparty A.",
            budget=5_000,
        )

        assert last_json(httpx_mock) == {
            "agent_id": str(agent_id),
            "task": "Review counterparty A.",
            "parent_id": str(parent_id),
            "budget_cost_weighted_tokens": 5_000,
        }
        assert (child.parent_id, child.depth) == (parent_id, 1)


class TestReading:
    def test_list_pages_and_parses(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"{ASSIGNMENTS}?skip=5&limit=1"),
            json={"assignments": [_assignment()], "total": 7, "skip": 5, "limit": 1},
        )

        listed = client.assignments.list(uuid.UUID(PROJECT_ID), skip=5, limit=1)

        assert last_params(httpx_mock) == {"skip": "5", "limit": "1"}
        assert listed.total == 7
        assert len(listed.assignments) == 1

    def test_get_reads_one(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        payload = _assignment(anchor_document_id=str(uuid.uuid4()))
        httpx_mock.add_response(
            method="GET", url=url(f"{ASSIGNMENTS}/{payload['id']}"), json=payload
        )

        got = client.assignments.get(uuid.UUID(PROJECT_ID), uuid.UUID(payload["id"]))

        assert str(got.anchor_document_id) == payload["anchor_document_id"]
        assert str(got.notebook_id) == payload["notebook_id"]
        assert got.created_at is not None

    def test_derived_ids_are_accepted(self) -> None:
        """Assignment ids may be uuid5, so nothing may demand version 4."""
        derived = uuid.uuid5(uuid.uuid4(), "1")
        parsed = AssignmentResponse.model_validate(
            _assignment(id=str(derived), parent_id=str(derived))
        )

        assert parsed.id == derived
        assert parsed.parent_id == derived


class TestStopping:
    @pytest.mark.parametrize(
        ("action", "status", "reason"),
        [("cancel", "cancelled", "user_cancelled"), ("resume", "queued", None)],
    )
    def test_cancel_and_resume_post_to_the_assignment(
        self,
        client: RagnerockClient,
        httpx_mock: HTTPXMock,
        action: str,
        status: str,
        reason: str | None,
    ) -> None:
        assignment_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"{ASSIGNMENTS}/{assignment_id}/{action}"),
            json=_assignment(
                id=str(assignment_id), status=status, status_reason=reason
            ),
        )

        result = getattr(client.assignments, action)(
            uuid.UUID(PROJECT_ID), assignment_id
        )

        assert last_request(httpx_mock).content == b""
        assert result.id == assignment_id
        assert result.status == AssignmentStatus(status)
        assert result.status_reason == reason


class TestQuestions:
    def test_the_open_ones_by_default(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/agent-questions?skip=0&limit=50&status=open"),
            json={"questions": [_question()], "total": 1, "skip": 0, "limit": 50},
        )

        listed = client.assignments.questions()

        assert last_params(httpx_mock)["status"] == "open"
        assert listed.questions[0].status == AgentQuestionStatus.OPEN
        assert listed.questions[0].question == "Which fiscal year?"

    def test_all_of_them(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/agent-questions?skip=0&limit=50"),
            json={"questions": [], "total": 0, "skip": 0, "limit": 50},
        )

        client.assignments.questions(status=None)

        assert "status" not in last_params(httpx_mock)

    def test_a_status_filter(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/agent-questions?skip=0&limit=50&status=expired"),
            json={"questions": [], "total": 0, "skip": 0, "limit": 50},
        )

        client.assignments.questions(status=AgentQuestionStatus.EXPIRED)

        assert last_params(httpx_mock)["status"] == "expired"

    def test_answer_posts_the_answer(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        question_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/projects/{PROJECT_ID}/agent-questions/{question_id}/answer"),
            json=_question(id=str(question_id), status="answered", answer="FY2025."),
        )

        result = client.assignments.answer(
            uuid.UUID(PROJECT_ID), question_id, answer="FY2025."
        )

        assert last_json(httpx_mock) == {"answer": "FY2025."}
        assert result.answer == "FY2025."
        assert result.status == AgentQuestionStatus.ANSWERED


class TestAnAgentsWork:
    def _page(self, **overrides: Any) -> dict[str, Any]:
        page: dict[str, Any] = {
            "assignments": [],
            "total": 0,
            "skip": 0,
            "limit": 50,
            "counts": {status.value: 0 for status in AssignmentStatus},
            "spend": {
                "assignments": 0,
                "budget_cost_weighted_tokens": 0,
                "spent_cost_weighted_tokens": 0,
            },
            "retention_days": 365,
        }
        page.update(overrides)
        return page

    def test_list_for_agent_filters_by_status_and_reads_the_counts(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        agent_id = uuid.uuid4()
        path = f"/api/projects/{PROJECT_ID}/agents/{agent_id}/assignments"
        httpx_mock.add_response(
            method="GET",
            url=url(f"{path}?skip=0&limit=50&status=queued&status=running"),
            json=self._page(
                assignments=[_assignment(agent_id=str(agent_id))],
                total=1,
                counts={s.value: 0 for s in AssignmentStatus}
                | {"queued": 1, "done": 4},
                spend={
                    "assignments": 5,
                    "budget_cost_weighted_tokens": 500_000,
                    "spent_cost_weighted_tokens": 81_000,
                },
            ),
        )

        listed = client.assignments.list_for_agent(
            uuid.UUID(PROJECT_ID),
            agent_id,
            status=[AssignmentStatus.QUEUED, "running"],
        )

        params = last_request(httpx_mock).url.params
        assert params.get_list("status") == ["queued", "running"]
        assert (params["skip"], params["limit"]) == ("0", "50")
        assert listed.counts[AssignmentStatus.DONE] == 4
        assert listed.spend is not None
        assert listed.spend.spent_cost_weighted_tokens == 81_000
        assert listed.retention_days == 365

    def test_every_status_when_none_is_named(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        agent_id = uuid.uuid4()
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/projects/{PROJECT_ID}/agents/{agent_id}/assignments"
                "?skip=0&limit=50"
            ),
            json=self._page(),
        )

        client.assignments.list_for_agent(uuid.UUID(PROJECT_ID), agent_id)

        assert "status" not in last_params(httpx_mock)

    def test_threads_reads_both_kinds(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        agent_id = uuid.uuid4()
        page = {
            "threads": [
                {
                    "kind": "transcript",
                    "notebook_id": str(uuid.uuid4()),
                    "title": "Reviewer: Check the filing",
                    "created_by": str(uuid.uuid4()),
                    "created_at": NOW,
                    "updated_at": NOW,
                    "assignment_id": str(uuid.uuid4()),
                    "status": "waiting",
                },
                {
                    "kind": "conversation",
                    "notebook_id": str(uuid.uuid4()),
                    "title": "Chat",
                    "created_by": str(uuid.uuid4()),
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            ],
            "total": 2,
            "skip": 0,
            "limit": 50,
        }
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/projects/{PROJECT_ID}/agents/{agent_id}/threads?skip=0&limit=50"
            ),
            json=page,
        )

        listed = client.assignments.threads(uuid.UUID(PROJECT_ID), agent_id)

        assert [thread.kind for thread in listed.threads] == [
            "transcript",
            "conversation",
        ]
        assert listed.threads[0].status == AssignmentStatus.WAITING
        assert listed.threads[1].assignment_id is None


class TestFollowingOne:
    def test_it_yields_each_event_by_kind_and_skips_keepalives(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        assignment_id = uuid.uuid4()
        status_event = {
            "kind": "status",
            "assignment": _assignment(id=str(assignment_id), status="running"),
        }
        cell_event = {
            "kind": "cell",
            "cell": {
                "id": str(uuid.uuid4()),
                "notebook_id": str(uuid.uuid4()),
                "content": "Looking at the filing.",
                "cell_type": "message",
                "role": "model",
                "output": None,
                "position": 1,
                "created_at": "2026-10-01T12:00:00Z",
            },
        }
        future_event = {"kind": "something_new", "detail": 1}
        httpx_mock.add_response(
            method="GET",
            url=url(f"{ASSIGNMENTS}/{assignment_id}/stream"),
            content=_sse(
                "event: cell",
                f"data: {json.dumps(cell_event)}",
                "",
                ": heartbeat",
                "",
                f"data: {json.dumps(future_event)}",
                "",
                "event: status",
                f"data: {json.dumps(status_event)}",
                "",
            ),
            headers={"content-type": "text/event-stream"},
        )

        events = list(client.assignments.stream(uuid.UUID(PROJECT_ID), assignment_id))

        request = last_request(httpx_mock)
        assert request.method == "GET"
        assert request.url.query == b""
        assert request.headers["accept"] == "text/event-stream"
        assert request.extensions["timeout"]["read"] == STREAM_READ_TIMEOUT_SECONDS
        assert [type(event) for event in events] == [
            AssignmentCellEvent,
            AssignmentStatusEvent,
        ]
        cell, status = events
        assert isinstance(cell, AssignmentCellEvent)
        assert (cell.cell.position, cell.cell.content) == (1, "Looking at the filing.")
        assert isinstance(status, AssignmentStatusEvent)
        assert status.assignment.id == assignment_id
        assert status.assignment.status == AssignmentStatus.RUNNING

    def test_a_refusal_raises(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        assignment_id = uuid.uuid4()
        httpx_mock.add_response(
            method="GET",
            url=url(f"{ASSIGNMENTS}/{assignment_id}/stream"),
            status_code=403,
            json={"detail": "Forbidden"},
        )

        with pytest.raises(AuthenticationError, match="Forbidden"):
            list(client.assignments.stream(uuid.UUID(PROJECT_ID), assignment_id))
