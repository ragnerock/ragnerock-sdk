"""Tests for the job section: run creation modes, manifests, and sink deliveries."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from ragnerock.client import RagnerockClient
from ragnerock.errors import RagnerockError
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

JOB_ID = uuid.UUID("00000000-0000-4000-8000-000000000801")
RUN_ID = uuid.UUID("00000000-0000-4000-8000-000000000802")
DOC_ID = uuid.UUID("00000000-0000-4000-8000-000000000101")
DOC_2 = uuid.UUID("00000000-0000-4000-8000-000000000102")
WORKFLOW_ID = uuid.UUID("00000000-0000-4000-8000-000000000701")
NODE_ID = uuid.UUID("00000000-0000-4000-8000-000000000702")
RESOURCE_ID = uuid.UUID("00000000-0000-4000-8000-000000000703")
SINK_ID = uuid.UUID("00000000-0000-4000-8000-000000000a01")
GROUP_ID = uuid.UUID("00000000-0000-4000-8000-000000000b01")


def _job(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(JOB_ID),
        "document_id": str(DOC_ID),
        "start_time": "2026-04-16T12:00:00Z",
        "end_time": None,
        "status": 2,
        "status_message": None,
        "job_type": 2,
        "should_parse": True,
        "capture_execution_log": False,
        "n_tokens": None,
        "n_pages": None,
        "n_mb": None,
        "phase": "annotation",
        "current_stage_name": "Topics",
        "workflow_ids": [str(WORKFLOW_ID)],
        "run": {"id": str(RUN_ID), "trigger": "manual", "status": 2, "pins": []},
    }
    payload.update(overrides)
    return payload


class TestListAndGet:
    def test_list_sends_scope_and_filter(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url(
                f"/api/jobs/?project_id={PROJECT_ID}&status_filter=1%2C2&skip=0&limit=50"
            ),
            json={
                "jobs": [_job(document_name="report.pdf")],
                "total": 1,
                "skip": 0,
                "limit": 50,
            },
        )

        result = client.jobs.list(project_id=uuid.UUID(PROJECT_ID), status_filter="1,2")

        assert result.jobs[0].document_name == "report.pdf"

    def test_get_parses_commonly_read_fields(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET", url=url(f"/api/jobs/{JOB_ID}"), json=_job()
        )

        job = client.jobs.get(JOB_ID)

        assert job.id == JOB_ID
        assert job.status == 2
        assert job.document_id == DOC_ID
        assert job.phase == "annotation"
        assert job.workflow_ids == [WORKFLOW_ID]
        assert job.start_time == datetime(2026, 4, 16, 12, tzinfo=UTC)
        assert job.end_time is None
        assert job.run is not None and job.run["id"] == str(RUN_ID)


class TestCreateManual:
    def test_fan_out_mode(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/jobs/"),
            json={"job_ids": [str(JOB_ID)]},
        )

        result = client.jobs.create_manual(
            document_ids=[DOC_ID], workflow_ids=[WORKFLOW_ID]
        )

        assert last_json(httpx_mock) == {
            "document_ids": [str(DOC_ID)],
            "workflow_ids": [str(WORKFLOW_ID)],
            "force_refresh": False,
            "capture_execution_log": False,
        }
        assert result.job_ids == [JOB_ID]
        assert result.run_ids == []

    def test_empty_memory_list_is_sent_not_dropped(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST", url=url("/api/jobs/"), json={"job_ids": [str(JOB_ID)]}
        )

        client.jobs.create_manual(
            document_ids=[DOC_ID],
            workflow_ids=[WORKFLOW_ID],
            recreate_memory_document_ids=[],
        )

        # ``[]`` means "recreate memory for no document", unlike ``None``.
        assert last_json(httpx_mock)["recreate_memory_document_ids"] == []

    def test_explicit_mode(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/jobs/"),
            json={"job_ids": [str(JOB_ID)], "run_ids": [str(RUN_ID)]},
        )

        result = client.jobs.create_manual(
            workflow_id=WORKFLOW_ID,
            runs=[
                {"inputs": {"report": DOC_ID, "params": {"k": 1}}, "client_key": "a"}
            ],
            group_id=GROUP_ID,
            force_refresh_node_ids=[NODE_ID],
            capture_execution_log=True,
        )

        body = last_json(httpx_mock)
        assert body == {
            "workflow_id": str(WORKFLOW_ID),
            "runs": [
                {
                    "inputs": {"report": str(DOC_ID), "params": {"k": 1}},
                    "client_key": "a",
                }
            ],
            "group_id": str(GROUP_ID),
            "force_refresh": False,
            "force_refresh_node_ids": [str(NODE_ID)],
            "capture_execution_log": True,
        }
        # Explicit mode only: the fan-out fields stay unset.
        assert "document_ids" not in body
        assert "workflow_ids" not in body
        assert result.run_ids == [RUN_ID]

    def test_mixed_modes_surface_the_server_error(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/jobs/"),
            status_code=400,
            json={"detail": "Cannot mix fan-out and explicit fields"},
        )

        with pytest.raises(RagnerockError) as exc_info:
            client.jobs.create_manual(
                document_ids=[DOC_ID], workflow_id=WORKFLOW_ID, runs=[{"inputs": {}}]
            )
        assert exc_info.value.status_code == 400


class TestRunAllIngest:
    def test_posts_workflow_and_resource(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/jobs/ingest-run-all"),
            json={"job_ids": [str(JOB_ID)], "run_ids": [str(RUN_ID)]},
        )

        result = client.jobs.run_all_ingest(
            workflow_id=WORKFLOW_ID, resource_id=RESOURCE_ID
        )

        assert last_json(httpx_mock) == {
            "workflow_id": str(WORKFLOW_ID),
            "resource_id": str(RESOURCE_ID),
            "capture_execution_log": False,
        }
        assert result.job_ids == [JOB_ID]
        assert result.run_ids == [RUN_ID]


class TestLifecycleActions:
    def test_cancel(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/jobs/{JOB_ID}/cancel"),
            json={"job_id": str(JOB_ID), "status": "cancelled"},
        )

        assert client.jobs.cancel(JOB_ID).status == "cancelled"

    def test_retry(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/jobs/{JOB_ID}/retry"),
            json={"job_id": str(JOB_ID), "status": "retrying"},
        )

        assert client.jobs.retry(JOB_ID).job_id == JOB_ID


class TestSinkDeliveries:
    def test_lists_groups_and_deliveries(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        delivery_id = "00000000-0000-4000-8000-000000000a11"
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/jobs/{JOB_ID}/sink-deliveries"),
            json={
                "groups": [
                    {
                        "sink_id": str(SINK_ID),
                        "sink_name": "Weekly email",
                        "kind": "email",
                        "status_counts": {"failed": 1, "succeeded": 2},
                        "notifications_sent": 0,
                        "deliveries": [
                            {
                                "id": delivery_id,
                                "sink_id": str(SINK_ID),
                                "run_id": str(RUN_ID),
                                "job_id": str(JOB_ID),
                                "kind": "email",
                                "status": "failed",
                                "reason": "send_rejected",
                                "detail": "Recipient refused",
                                "target_scope": 1,
                                "target_id": str(DOC_ID),
                                "iteration_index": 0,
                                "created_at": "2026-05-01T00:00:00Z",
                                "updated_at": "2026-05-01T00:00:00Z",
                                "sends": [],
                            }
                        ],
                        "truncated": False,
                    }
                ]
            },
        )

        result = client.jobs.sink_deliveries(JOB_ID)

        group = result.groups[0]
        assert group.sink_id == SINK_ID
        assert group.status_counts == {"failed": 1, "succeeded": 2}
        delivery = group.deliveries[0]
        assert delivery.id == uuid.UUID(delivery_id)
        assert delivery.status == "failed"
        assert delivery.reason == "send_rejected"

    def test_empty_run(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET", url=url(f"/api/jobs/{JOB_ID}/sink-deliveries"), json={}
        )

        assert client.jobs.sink_deliveries(JOB_ID).groups == []

    def test_retry_posts_the_sink(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/jobs/{JOB_ID}/sink-deliveries/retry"),
            json={"retried": 3},
        )

        result = client.jobs.retry_sink_deliveries(JOB_ID, sink_id=SINK_ID)

        assert last_json(httpx_mock) == {"sink_id": str(SINK_ID)}
        assert result.retried == 3


class FakeApi:
    """Serves the requests the manifest flow makes.

    One workflow (with a ``report`` file resource and a ``params`` value
    resource), a paginated document listing, and the job-creation endpoint.
    """

    def __init__(
        self, documents: list[tuple[str, uuid.UUID]], page_size: int = 100
    ) -> None:
        self.documents = documents
        self.page_size = page_size
        self.job_requests: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, str]] = []
        self.workflow_gets = 0
        self.fail_job_request: int | None = None

    def _workflow(self) -> dict[str, Any]:
        return {
            "id": str(WORKFLOW_ID),
            "project_id": PROJECT_ID,
            "name": "wf",
            "resources": [
                {"id": str(uuid.uuid4()), "name": "report", "type": "file"},
                {"id": str(uuid.uuid4()), "name": "params", "type": "value"},
            ],
        }

    def _document_page(self, skip: int, limit: int) -> dict[str, Any]:
        page = self.documents[skip : skip + min(limit, self.page_size)]
        return {
            "documents": [
                {"id": str(doc_id), "project_id": PROJECT_ID, "name": name}
                for name, doc_id in page
            ],
            "total": len(self.documents),
            "skip": skip,
            "limit": limit,
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == f"/api/workflows/{WORKFLOW_ID}":
            self.workflow_gets += 1
            return httpx.Response(200, json=self._workflow())
        if request.method == "GET" and path == "/api/documents/":
            params = dict(request.url.params)
            self.list_calls.append(params)
            page = self._document_page(int(params["skip"]), int(params["limit"]))
            return httpx.Response(200, json=page)
        if request.method == "POST" and path == "/api/jobs/":
            body = json.loads(request.content)
            self.job_requests.append(body)
            if self.fail_job_request == len(self.job_requests):
                return httpx.Response(500, json={"detail": "Server error"})
            count = len(body["runs"])
            return httpx.Response(
                200,
                json={
                    "job_ids": [str(uuid.uuid4()) for _ in range(count)],
                    "run_ids": [str(uuid.uuid4()) for _ in range(count)],
                },
            )
        raise AssertionError(f"unexpected request {request.method} {path}")


class TestCreateRunsFromManifest:
    def test_rows_chunked_under_one_group_with_ordered_ids(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        fake = FakeApi(documents=[])
        httpx_mock.add_callback(fake, is_reusable=True)
        doc_ids = [uuid.uuid4() for _ in range(5)]
        rows = [{"inputs": {"report": str(d)}} for d in doc_ids]

        result = client.jobs.create_runs_from_manifest(
            workflow_id=WORKFLOW_ID,
            manifest=rows,
            chunk_size=2,
            capture_execution_log=True,
        )

        assert [len(r["runs"]) for r in fake.job_requests] == [2, 2, 1]
        group_ids = {r["group_id"] for r in fake.job_requests}
        assert len(group_ids) == 1
        assert all(r["workflow_id"] == str(WORKFLOW_ID) for r in fake.job_requests)
        assert all(r["capture_execution_log"] is True for r in fake.job_requests)
        sent = [run for r in fake.job_requests for run in r["runs"]]
        assert [run["client_key"] for run in sent] == [f"row-{i}" for i in range(5)]
        assert [run["inputs"]["report"] for run in sent] == [str(d) for d in doc_ids]
        assert len(result.job_ids) == 5
        assert len(result.run_ids) == 5
        # Id bindings never trigger a document-name lookup.
        assert fake.list_calls == []
        assert fake.workflow_gets == 1

    def test_document_names_resolved_across_pages(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        documents = [(f"doc-{i}.pdf", uuid.uuid4()) for i in range(3)]
        fake = FakeApi(documents=documents, page_size=2)
        httpx_mock.add_callback(fake, is_reusable=True)
        rows = [
            {"inputs": {"report": "doc-2.pdf", "params": "free text"}},
            {"inputs": {"report": "doc-0.pdf"}},
        ]

        client.jobs.create_runs_from_manifest(workflow_id=WORKFLOW_ID, manifest=rows)

        runs = fake.job_requests[0]["runs"]
        assert runs[0]["inputs"]["report"] == str(documents[2][1])
        # Value resources pass through untouched, even when not a UUID.
        assert runs[0]["inputs"]["params"] == "free text"
        assert runs[1]["inputs"]["report"] == str(documents[0][1])
        assert [c["skip"] for c in fake.list_calls] == ["0", "2"]
        assert all(c["project_ids"] == PROJECT_ID for c in fake.list_calls)

    def test_unknown_document_name_rejected_before_submission(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        fake = FakeApi(documents=[("a.pdf", uuid.uuid4())])
        httpx_mock.add_callback(fake, is_reusable=True)

        with pytest.raises(ValueError, match=r"unknown document 'missing\.pdf'"):
            client.jobs.create_runs_from_manifest(
                workflow_id=WORKFLOW_ID,
                manifest=[{"inputs": {"report": "missing.pdf"}}],
            )
        assert fake.job_requests == []

    def test_ambiguous_document_name_rejected(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        fake = FakeApi(documents=[("dup.pdf", DOC_ID), ("dup.pdf", DOC_2)])
        httpx_mock.add_callback(fake, is_reusable=True)

        with pytest.raises(ValueError, match=r"unknown document 'dup\.pdf'"):
            client.jobs.create_runs_from_manifest(
                workflow_id=WORKFLOW_ID, manifest=[{"inputs": {"report": "dup.pdf"}}]
            )
        assert fake.job_requests == []

    @pytest.mark.parametrize("layout", ["jsonl", "array"])
    def test_manifest_file_formats(
        self,
        client: RagnerockClient,
        httpx_mock: Any,
        tmp_path: Path,
        layout: str,
    ) -> None:
        fake = FakeApi(documents=[])
        httpx_mock.add_callback(fake, is_reusable=True)
        rows = [{"inputs": {"report": str(uuid.uuid4())}} for _ in range(2)]
        manifest = tmp_path / "manifest.jsonl"
        if layout == "jsonl":
            manifest.write_text("\n".join(json.dumps(r) for r in rows) + "\n\n")
        else:
            manifest.write_text(json.dumps(rows))

        result = client.jobs.create_runs_from_manifest(
            workflow_id=WORKFLOW_ID, manifest=manifest
        )

        assert [run["inputs"] for run in fake.job_requests[0]["runs"]] == [
            r["inputs"] for r in rows
        ]
        assert len(result.job_ids) == 2

    def test_chunk_failure_propagates(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        fake = FakeApi(documents=[])
        fake.fail_job_request = 2
        httpx_mock.add_callback(fake, is_reusable=True)
        rows = [{"inputs": {"report": str(uuid.uuid4())}} for _ in range(4)]

        with pytest.raises(RagnerockError) as exc_info:
            client.jobs.create_runs_from_manifest(
                workflow_id=WORKFLOW_ID, manifest=rows, chunk_size=2
            )
        assert exc_info.value.status_code == 500
        assert len(fake.job_requests) == 2

    def test_rejects_non_positive_chunk_size(self, client: RagnerockClient) -> None:
        with pytest.raises(ValueError, match="chunk_size"):
            client.jobs.create_runs_from_manifest(
                workflow_id=WORKFLOW_ID, manifest=[], chunk_size=0
            )


def test_list_drops_unset_status_filter(
    client: RagnerockClient, httpx_mock: Any
) -> None:
    """An unset status filter is left out of the query string."""
    httpx_mock.add_response(
        method="GET",
        url=url(f"/api/jobs/?project_id={PROJECT_ID}&skip=0&limit=50"),
        json={"jobs": [], "total": 0, "skip": 0, "limit": 50},
    )

    client.jobs.list(project_id=uuid.UUID(PROJECT_ID))

    assert last_request(httpx_mock).method == "GET"
    assert "status_filter" not in last_params(httpx_mock)
