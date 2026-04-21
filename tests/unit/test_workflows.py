"""CRUD tests for ``Workflow``."""

from __future__ import annotations

import re

import pytest

from ragnerock import Workflow, WorkflowNode
from ragnerock.errors import ValidationError


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        wf_id = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/workflows/{wf_id}$"),
            json=payloads.workflow(id=wf_id),
        )
        wf = session.get(Workflow, id=wf_id)
        assert wf is not None
        assert wf.name == "ingest"

    def test_get_by_name(self, httpx_mock, session, payloads):
        wf_id = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/workflows/\?.*"),
            json=payloads.list_envelope(
                "workflows",
                [payloads.workflow(id=wf_id, name="ingest")],
            ),
        )
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/workflows/{wf_id}$"),
            json=payloads.workflow(id=wf_id, name="ingest"),
        )
        wf = session.get(Workflow, name="ingest")
        assert wf is not None

    def test_get_missing_by_name_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/workflows/\?.*"),
            json=payloads.list_envelope("workflows", []),
        )
        assert session.get(Workflow, name="nope") is None


class TestGetNode:
    wf_id = "00000000-0000-0000-0000-000000000701"
    node_a = "00000000-0000-0000-0000-0000000007a1"
    node_b = "00000000-0000-0000-0000-0000000007b1"

    def _workflow_with_nodes(self, payloads):
        return payloads.workflow(
            id=self.wf_id,
            name="ingest",
            nodes=[
                payloads.workflow_node(
                    id=self.node_a,
                    workflow_id=self.wf_id,
                    operator_name="extract",
                ),
                payloads.workflow_node(
                    id=self.node_b,
                    workflow_id=self.wf_id,
                    operator_name="classify",
                ),
            ],
        )

    def test_get_by_node_id_and_workflow_id(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/workflows/{self.wf_id}$"),
            json=self._workflow_with_nodes(payloads),
        )
        node = session.get(WorkflowNode, id=self.node_b, workflow_id=self.wf_id)
        assert node is not None
        assert str(node.id) == self.node_b
        assert node.operator_name == "classify"

    def test_get_by_node_name_matches_operator_name(
        self, httpx_mock, session, payloads
    ):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/workflows/{self.wf_id}$"),
            json=self._workflow_with_nodes(payloads),
        )
        node = session.get(WorkflowNode, name="extract", workflow_id=self.wf_id)
        assert node is not None
        assert str(node.id) == self.node_a

    def test_get_by_workflow_name(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/workflows/\?.*"),
            json=payloads.list_envelope(
                "workflows",
                [payloads.workflow(id=self.wf_id, name="ingest")],
            ),
        )
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/workflows/{self.wf_id}$"),
            json=self._workflow_with_nodes(payloads),
        )
        node = session.get(WorkflowNode, name="classify", workflow_name="ingest")
        assert node is not None
        assert str(node.id) == self.node_b

    def test_missing_node_id_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/workflows/{self.wf_id}$"),
            json=self._workflow_with_nodes(payloads),
        )
        missing = "00000000-0000-0000-0000-0000000000ff"
        assert session.get(WorkflowNode, id=missing, workflow_id=self.wf_id) is None

    def test_missing_node_name_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/workflows/{self.wf_id}$"),
            json=self._workflow_with_nodes(payloads),
        )
        assert session.get(WorkflowNode, name="nope", workflow_id=self.wf_id) is None

    def test_missing_workflow_name_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/workflows/\?.*"),
            json=payloads.list_envelope("workflows", []),
        )
        assert session.get(WorkflowNode, id=self.node_a, workflow_name="nope") is None

    def test_raises_without_workflow_identifier(self, session):
        with pytest.raises(ValidationError, match="workflow_id"):
            session.get(WorkflowNode, id=self.node_a)

    def test_raises_without_node_identifier(self, session):
        with pytest.raises(ValidationError, match="id= or name="):
            session.get(WorkflowNode, workflow_id=self.wf_id)


class TestList:
    def test_list_returns_workflows(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/workflows/\?.*"),
            json=payloads.list_envelope(
                "workflows",
                [payloads.workflow(name="a"), payloads.workflow(name="b")],
            ),
        )
        wfs = session.list(Workflow).all()
        assert [w.name for w in wfs] == ["a", "b"]


class TestCrud:
    def test_create(self, httpx_mock, session, payloads, base_url):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/workflows/",
            json=payloads.workflow(id="00000000-0000-0000-0000-0000000000f2"),
        )
        wf = Workflow(name="ingest")
        session.add(wf)
        session.commit()
        assert wf.id is not None

    def test_update(self, httpx_mock, session, payloads, base_url):
        wf_id = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/workflows/{wf_id}",
            json=payloads.workflow(id=wf_id, is_active=False),
        )
        wf = Workflow(**payloads.workflow(id=wf_id))
        wf.is_active = False
        session.update(wf)
        session.commit()
        assert wf.is_active is False

    def test_delete(self, httpx_mock, session, payloads, base_url):
        wf_id = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{base_url}/api/workflows/{wf_id}",
            status_code=204,
            text="",
        )
        wf = Workflow(**payloads.workflow(id=wf_id))
        session.delete(wf)
        session.commit()
