"""Tests for the notebook, cell, and artifact sections (:mod:`ragnerock.client.notebooks`)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from ragnerock.client import UNSET, RagnerockClient
from ragnerock.client.notebooks import (
    ArtifactType,
    CellRole,
    CellType,
    NotebookResponse,
    ReasoningEffort,
)
from ragnerock.errors import NotFoundError, ValidationError
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

NOW = "2026-09-24T00:00:00Z"


def _notebook(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "project_id": PROJECT_ID,
        "title": "Supply Chain Analyst",
        "created_at": NOW,
        "updated_at": NOW,
        "created_by": str(uuid.uuid4()),
    }
    payload.update(overrides)
    return payload


def _cell(notebook_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "notebook_id": str(notebook_id),
        "content": "hello",
        "cell_type": "message",
        "role": "user",
        "output": None,
        "position": 0,
        "created_at": NOW,
    }
    payload.update(overrides)
    return payload


def _artifact(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "project_id": PROJECT_ID,
        "created_by_id": str(uuid.uuid4()),
        "artifact_type": "dataframe",
        "preview": {"title": "Counterparties", "size_bytes": 512},
        "data": {"rows": []},
        "storage_path": None,
        "created_at": NOW,
    }
    payload.update(overrides)
    return payload


def _ndjson(*events: Any) -> bytes:
    """Encode events as NDJSON, interleaving blank keep-alive lines."""
    return ("\n\n".join(json.dumps(e) for e in events) + "\n").encode()


class TestNotebookCreate:
    def test_an_agent_id_reaches_the_body(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        agent_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url("/api/notebooks/"),
            json=_notebook(agent_id=str(agent_id)),
        )

        created = client.notebooks.create(
            project_id=uuid.UUID(PROJECT_ID), title="Chat", agent_id=agent_id
        )

        assert last_json(httpx_mock) == {
            "project_id": PROJECT_ID,
            "title": "Chat",
            "agent_id": str(agent_id),
        }
        assert created.agent_id == agent_id

    def test_an_unbound_create_sends_no_binding(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        """The research agent: no ``agent_id`` reaches the server."""
        httpx_mock.add_response(
            method="POST", url=url("/api/notebooks/"), json=_notebook()
        )

        created = client.notebooks.create(
            project_id=uuid.UUID(PROJECT_ID), title="Scratch"
        )

        assert "agent_id" not in last_json(httpx_mock)
        assert created.agent_id is None


class TestOpenConversation:
    def test_it_posts_to_the_resolve_or_create_route(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        agent_id = uuid.uuid4()
        payload = _notebook(agent_id=str(agent_id))
        httpx_mock.add_response(
            method="POST",
            url=url("/api/notebooks/conversations"),
            json=payload,
            is_reusable=True,
        )

        first = client.notebooks.open_conversation(
            project_id=uuid.UUID(PROJECT_ID), agent_id=agent_id
        )
        second = client.notebooks.open_conversation(
            project_id=uuid.UUID(PROJECT_ID), agent_id=agent_id
        )

        assert last_json(httpx_mock) == {
            "project_id": PROJECT_ID,
            "agent_id": str(agent_id),
        }
        assert first.agent_id == agent_id
        assert first.id == second.id


class TestNotebookList:
    def test_the_defaults_send_neither_filter(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/notebooks/?skip=0&limit=100"),
            json={"notebooks": [], "total": 0, "skip": 0, "limit": 100},
        )

        listed = client.notebooks.list()

        assert last_params(httpx_mock) == {"skip": "0", "limit": "100"}
        assert listed.notebooks == []

    def test_the_filters_ride_the_query_string(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        agent_id = uuid.uuid4()
        item = {"id": str(uuid.uuid4()), "title": "Chat", "created_at": NOW}
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/notebooks/?skip=5&limit=10&project_ids={PROJECT_ID}"
                f"&agent_id={agent_id}&mine=true"
            ),
            json={"notebooks": [item], "total": 6, "skip": 5, "limit": 10},
        )

        listed = client.notebooks.list(
            project_ids=PROJECT_ID, skip=5, limit=10, agent_id=agent_id, mine=True
        )

        assert listed.total == 6
        assert listed.notebooks[0].title == "Chat"


class TestNotebookReadAndWrite:
    def test_get(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        payload = _notebook()
        httpx_mock.add_response(
            method="GET", url=url(f"/api/notebooks/{payload['id']}"), json=payload
        )

        got = client.notebooks.get(uuid.UUID(payload["id"]))

        assert str(got.id) == payload["id"]
        assert got.title == "Supply Chain Analyst"

    def test_update_sends_only_the_title(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        payload = _notebook(title="Renamed")
        httpx_mock.add_response(
            method="PUT", url=url(f"/api/notebooks/{payload['id']}"), json=payload
        )

        updated = client.notebooks.update(uuid.UUID(payload["id"]), title="Renamed")

        assert last_json(httpx_mock) == {"title": "Renamed"}
        assert updated.title == "Renamed"

    def test_update_sets_the_model_binding(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id, config_id = uuid.uuid4(), uuid.uuid4()
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/notebooks/{notebook_id}"),
            json=_notebook(
                id=str(notebook_id),
                ai_config_id=str(config_id),
                reasoning_effort="high",
            ),
        )

        updated = client.notebooks.update(
            notebook_id, ai_config_id=config_id, reasoning_effort=ReasoningEffort.HIGH
        )

        assert last_json(httpx_mock) == {
            "ai_config_id": str(config_id),
            "reasoning_effort": "high",
        }
        assert updated.reasoning_effort == ReasoningEffort.HIGH

    def test_update_with_none_clears_the_model_binding(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id = uuid.uuid4()
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/notebooks/{notebook_id}"),
            json=_notebook(id=str(notebook_id)),
        )

        client.notebooks.update(notebook_id, ai_config_id=None, reasoning_effort=None)

        assert last_json(httpx_mock) == {"ai_config_id": None, "reasoning_effort": None}

    def test_update_leaves_unset_bindings_out(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id = uuid.uuid4()
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/notebooks/{notebook_id}"),
            json=_notebook(id=str(notebook_id)),
        )

        client.notebooks.update(notebook_id, ai_config_id=UNSET, reasoning_effort=None)

        assert last_json(httpx_mock) == {"reasoning_effort": None}

    def test_delete(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        notebook_id = uuid.uuid4()
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/notebooks/{notebook_id}"),
            json={"message": "ok"},
        )

        assert client.notebooks.delete(notebook_id) is None
        assert last_params(httpx_mock) == {}

    def test_delete_a_transcript_confirms_ending_the_assignment(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id = uuid.uuid4()
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/notebooks/{notebook_id}?end_assignment=true"),
            json={"message": "ok"},
        )

        client.notebooks.delete(notebook_id, end_assignment=True)

        assert last_params(httpx_mock) == {"end_assignment": "true"}


class TestCompaction:
    def test_compact_appends_a_compaction_cell(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/notebooks/{notebook_id}/compaction"),
            json=_cell(
                notebook_id, cell_type="compaction", role=None, content="So far"
            ),
        )

        cell = client.notebooks.compact(notebook_id)

        assert last_request(httpx_mock).content == b""
        assert cell.cell_type == CellType.COMPACTION
        assert cell.content == "So far"

    def test_regenerate_compaction(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id, cell_id = uuid.uuid4(), uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/notebooks/{notebook_id}/compaction/{cell_id}/regenerate"),
            json=_cell(notebook_id, id=str(cell_id), cell_type="compaction"),
        )

        cell = client.notebooks.regenerate_compaction(notebook_id, cell_id)

        assert cell.id == cell_id


class TestStreamInput:
    def test_it_yields_each_event_and_skips_keepalives(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id = uuid.uuid4()
        user_cell = _cell(notebook_id, content="hi")
        agent_event = {"action": {"response": "Hello"}, "usage": {"input_tokens": 1}}
        body = _ndjson(user_cell, agent_event) + b"not json\n"
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/notebooks/{notebook_id}/input"),
            content=body,
            headers={"content-type": "application/x-ndjson"},
        )

        events = list(
            client.notebooks.stream_input(
                notebook_id,
                content="hi",
                cell_type=CellType.MESSAGE,
                role=CellRole.USER,
            )
        )

        request = last_request(httpx_mock)
        assert request.headers["accept"] == "application/x-ndjson"
        assert request.extensions["timeout"]["read"] is None
        assert json.loads(request.content) == {
            "content": "hi",
            "cell_type": "message",
            "role": "user",
        }
        assert events == [
            user_cell,
            agent_event,
            {"type": "text", "content": "not json"},
        ]

    def test_an_omitted_role_is_not_sent(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/notebooks/{notebook_id}/input"),
            content=b"",
        )

        events = list(
            client.notebooks.stream_input(
                notebook_id, content="x = 1", cell_type="code"
            )
        )

        assert last_json(httpx_mock) == {"content": "x = 1", "cell_type": "code"}
        assert events == []

    def test_an_error_status_raises_the_sdk_error(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/notebooks/{notebook_id}/input"),
            status_code=404,
            json={"detail": "Notebook not found"},
        )

        with pytest.raises(NotFoundError, match="Notebook not found"):
            list(
                client.notebooks.stream_input(
                    notebook_id, content="hello", cell_type="message"
                )
            )


class TestNotebookResponseFields:
    def test_a_bound_notebook_names_its_agent_and_its_model_source(self) -> None:
        agent_id = uuid.uuid4()
        parsed = NotebookResponse.model_validate(
            _notebook(
                agent_id=str(agent_id),
                agent_name="Supply Chain Analyst",
                model_source="agent",
                visibility="user",
            )
        )

        assert parsed.agent_id == agent_id
        assert parsed.agent_name == "Supply Chain Analyst"
        assert parsed.model_source == "agent"
        assert parsed.created_at is not None and parsed.created_at.tzinfo is not None

    def test_an_unbound_notebook_has_no_agent(self) -> None:
        parsed = NotebookResponse.model_validate(_notebook())

        assert parsed.agent_id is None
        assert parsed.agent_name is None
        assert parsed.model_source is None

    def test_a_transcript_carries_its_assignment(self) -> None:
        assignment_id = uuid.uuid5(uuid.uuid4(), "1")
        parsed = NotebookResponse.model_validate(
            _notebook(
                assignment_id=str(assignment_id),
                visibility="agent_transcript",
                assignment={"id": str(assignment_id), "status": "running"},
            )
        )

        assert parsed.assignment_id == assignment_id
        assert parsed.visibility == "agent_transcript"
        # Undeclared fields stay reachable.
        assert parsed.model_dump()["assignment"]["status"] == "running"


class TestCells:
    def test_create(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        notebook_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/notebooks/{notebook_id}/cells/"),
            json=_cell(notebook_id, cell_type="markdown", role=None, content="# Notes"),
        )

        cell = client.cells.create(notebook_id, content="# Notes", cell_type="markdown")

        assert last_json(httpx_mock) == {"content": "# Notes", "cell_type": "markdown"}
        assert cell.cell_type == CellType.MARKDOWN
        assert cell.role is None

    def test_create_with_role_and_output(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id = uuid.uuid4()
        output = {"outputs": [{"type": "stream", "name": "stdout", "text": "1\n"}]}
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/notebooks/{notebook_id}/cells/"),
            json=_cell(notebook_id, output=output),
        )

        cell = client.cells.create(
            notebook_id,
            content="hi",
            cell_type=CellType.MESSAGE,
            role=CellRole.USER,
            output=output,
        )

        assert last_json(httpx_mock) == {
            "content": "hi",
            "cell_type": "message",
            "role": "user",
            "output": output,
        }
        assert cell.output == output

    def test_list(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        notebook_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        cell = _cell(
            notebook_id,
            artifact_references=[
                {
                    "artifact_id": str(artifact_id),
                    "artifact_type": "plot",
                    "preview": {"title": "Revenue", "size_bytes": 2048},
                }
            ],
        )
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/notebooks/{notebook_id}/cells/"
                f"?notebook_id={notebook_id}&skip=0&limit=100"
            ),
            json={"cells": [cell], "total": 1, "skip": 0, "limit": 100},
        )

        listed = client.cells.list(notebook_id)

        assert listed.total == 1
        reference = listed.cells[0].artifact_references[0]
        assert reference.artifact_id == artifact_id
        assert reference.preview is not None
        assert reference.preview.title == "Revenue"

    def test_get(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        notebook_id = uuid.uuid4()
        payload = _cell(notebook_id)
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/notebooks/{notebook_id}/cells/{payload['id']}"),
            json=payload,
        )

        cell = client.cells.get(notebook_id, uuid.UUID(payload["id"]))

        assert str(cell.id) == payload["id"]
        assert cell.notebook_id == notebook_id

    def test_update_sends_only_the_supplied_fields(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        notebook_id = uuid.uuid4()
        payload = _cell(notebook_id, content="edited")
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/notebooks/{notebook_id}/cells/{payload['id']}"),
            json=payload,
        )

        cell = client.cells.update(
            notebook_id, uuid.UUID(payload["id"]), content="edited"
        )

        assert last_json(httpx_mock) == {"content": "edited"}
        assert cell.content == "edited"

    def test_delete(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        notebook_id, cell_id = uuid.uuid4(), uuid.uuid4()
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/notebooks/{notebook_id}/cells/{cell_id}"),
            json={"message": "Cell deleted successfully"},
        )

        assert client.cells.delete(notebook_id, cell_id) is None
        assert last_request(httpx_mock).method == "DELETE"


class TestArtifacts:
    def test_create_always_sends_data(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        """``data`` is required (but nullable) on the wire."""
        artifact_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url("/api/artifacts/"),
            json={"artifact_id": str(artifact_id)},
        )

        created = client.artifacts.create(
            project_id=uuid.UUID(PROJECT_ID),
            artifact_type=ArtifactType.ANALYSIS_REPORT,
            preview={"title": "Summary", "size_bytes": 10},
        )

        assert last_json(httpx_mock) == {
            "project_id": PROJECT_ID,
            "artifact_type": "analysis_report",
            "preview": {"title": "Summary", "size_bytes": 10},
            "data": None,
        }
        assert created.artifact_id == artifact_id

    def test_create_with_data(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        document_id = uuid.uuid4()
        httpx_mock.add_response(
            method="POST",
            url=url("/api/artifacts/"),
            json={"artifact_id": str(uuid.uuid4())},
        )

        client.artifacts.create(
            project_id=uuid.UUID(PROJECT_ID),
            artifact_type="documents",
            preview={"title": "Filings", "size_bytes": 100},
            data={"document_ids": [document_id]},
        )

        assert last_json(httpx_mock)["data"] == {"document_ids": [str(document_id)]}

    def test_get(self, client: RagnerockClient, httpx_mock: HTTPXMock) -> None:
        payload = _artifact()
        httpx_mock.add_response(
            method="GET", url=url(f"/api/artifacts/{payload['id']}"), json=payload
        )

        artifact = client.artifacts.get(uuid.UUID(payload["id"]))

        assert artifact.artifact_type == ArtifactType.DATAFRAME
        assert artifact.preview is not None
        assert artifact.preview.size_bytes == 512
        assert artifact.data == {"rows": []}

    def test_list_builds_its_query_string(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/artifacts/?project_id={PROJECT_ID}&skip=10&limit=5"),
            json={
                "artifacts": [_artifact(data=None)],
                "total": 11,
                "skip": 10,
                "limit": 5,
            },
        )

        listed = client.artifacts.list(
            project_id=uuid.UUID(PROJECT_ID), skip=10, limit=5
        )

        assert last_params(httpx_mock) == {
            "project_id": PROJECT_ID,
            "skip": "10",
            "limit": "5",
        }
        assert listed.total == 11
        assert listed.artifacts[0].data is None

    def test_a_refused_create_raises(
        self, client: RagnerockClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/artifacts/"),
            status_code=422,
            json={"detail": "artifact_type is invalid"},
        )

        with pytest.raises(ValidationError, match="artifact_type is invalid"):
            client.artifacts.create(
                project_id=uuid.UUID(PROJECT_ID),
                artifact_type="nonsense",
                preview={"title": "x", "size_bytes": 0},
            )
