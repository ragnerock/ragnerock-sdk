"""CRUD tests for ``Agent``."""

from __future__ import annotations

import json
import re

import pytest

from ragnerock import Agent, AgentNode
from ragnerock.errors import ValidationError


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        agent_id = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/agents/{agent_id}$"),
            json=payloads.agent(id=agent_id),
        )
        agent = session.get(Agent, id=agent_id)
        assert agent is not None
        assert agent.name == "ingest"

    def test_get_by_name(self, httpx_mock, session, payloads):
        agent_id = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/agents/\?.*"),
            json=payloads.list_envelope(
                "agents",
                [payloads.agent(id=agent_id, name="ingest")],
            ),
        )
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/agents/{agent_id}$"),
            json=payloads.agent(id=agent_id, name="ingest"),
        )
        agent = session.get(Agent, name="ingest")
        assert agent is not None

    def test_get_carries_inputs_outputs_and_node_fields(
        self, httpx_mock, session, payloads
    ):
        agent_id = "00000000-0000-0000-0000-000000000701"
        input_id = "00000000-0000-0000-0000-0000000007c1"
        context_id = "00000000-0000-0000-0000-0000000007c2"
        output_id = "00000000-0000-0000-0000-0000000007d1"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/agents/{agent_id}$"),
            json=payloads.agent(
                id=agent_id,
                inputs=[{"id": input_id, "name": "filings", "kind": "file"}],
                outputs=[{"id": output_id, "name": "digest", "kind": "email"}],
                nodes=[
                    payloads.agent_node_info(
                        on_error="FAIL_RUN",
                        target_input_id=input_id,
                        context_input_ids=[context_id],
                    )
                ],
            ),
        )
        agent = session.get(Agent, id=agent_id)
        assert agent is not None
        assert [i["name"] for i in agent.inputs] == ["filings"]
        assert [o["name"] for o in agent.outputs] == ["digest"]
        (node,) = agent.nodes
        assert node.on_error == "FAIL_RUN"
        assert str(node.target_input_id) == input_id
        assert [str(c) for c in node.context_input_ids] == [context_id]
        assert not hasattr(agent, "resources")
        assert not hasattr(agent, "sinks")

    def test_get_missing_by_name_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/agents/\?.*"),
            json=payloads.list_envelope("agents", []),
        )
        assert session.get(Agent, name="nope") is None


class TestGetNode:
    agent_id = "00000000-0000-0000-0000-000000000701"
    node_a = "00000000-0000-0000-0000-0000000007a1"
    node_b = "00000000-0000-0000-0000-0000000007b1"

    def _agent_with_nodes(self, payloads):
        return payloads.agent(
            id=self.agent_id,
            name="ingest",
            # Embedded nodes carry no agent_id on the wire.
            nodes=[
                payloads.agent_node_info(id=self.node_a, task_name="extract"),
                payloads.agent_node_info(id=self.node_b, task_name="classify"),
            ],
        )

    def test_get_by_node_id_and_agent_id(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/agents/{self.agent_id}$"),
            json=self._agent_with_nodes(payloads),
        )
        node = session.get(AgentNode, id=self.node_b, agent_id=self.agent_id)
        assert node is not None
        assert str(node.id) == self.node_b
        assert node.task_name == "classify"

    def test_get_by_node_name_matches_task_name(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/agents/{self.agent_id}$"),
            json=self._agent_with_nodes(payloads),
        )
        node = session.get(AgentNode, name="extract", agent_id=self.agent_id)
        assert node is not None
        assert str(node.id) == self.node_a

    def test_get_by_agent_name(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/agents/\?.*"),
            json=payloads.list_envelope(
                "agents",
                [payloads.agent(id=self.agent_id, name="ingest")],
            ),
        )
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/agents/{self.agent_id}$"),
            json=self._agent_with_nodes(payloads),
        )
        node = session.get(AgentNode, name="classify", agent_name="ingest")
        assert node is not None
        assert str(node.id) == self.node_b

    def test_missing_node_id_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/agents/{self.agent_id}$"),
            json=self._agent_with_nodes(payloads),
        )
        missing = "00000000-0000-0000-0000-0000000000ff"
        assert session.get(AgentNode, id=missing, agent_id=self.agent_id) is None

    def test_missing_node_name_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/agents/{self.agent_id}$"),
            json=self._agent_with_nodes(payloads),
        )
        assert session.get(AgentNode, name="nope", agent_id=self.agent_id) is None

    def test_missing_agent_name_returns_none(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/agents/\?.*"),
            json=payloads.list_envelope("agents", []),
        )
        assert session.get(AgentNode, id=self.node_a, agent_name="nope") is None

    def test_raises_without_agent_identifier(self, session):
        with pytest.raises(ValidationError, match="agent_id"):
            session.get(AgentNode, id=self.node_a)

    def test_raises_without_node_identifier(self, session):
        with pytest.raises(ValidationError, match="id= or name="):
            session.get(AgentNode, agent_id=self.agent_id)


class TestList:
    def test_list_returns_agents(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/agents/\?.*"),
            json=payloads.list_envelope(
                "agents",
                [payloads.agent(name="a"), payloads.agent(name="b")],
            ),
        )
        agents = session.list(Agent).all()
        assert [a.name for a in agents] == ["a", "b"]


class TestCrud:
    def test_create(self, httpx_mock, session, payloads, base_url):
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/agents/",
            json=payloads.agent(id="00000000-0000-0000-0000-0000000000f2"),
        )
        agent = Agent(name="ingest")
        session.add(agent)
        session.commit()
        assert agent.id is not None
        body = json.loads(httpx_mock.get_requests()[-1].content)
        assert body["auto_run_on_upload"] is False

    def test_update(self, httpx_mock, session, payloads, base_url):
        agent_id = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="PUT",
            url=f"{base_url}/api/agents/{agent_id}",
            json=payloads.agent(id=agent_id, is_active=False),
        )
        agent = Agent(**payloads.agent(id=agent_id))
        agent.is_active = False
        session.update(agent)
        session.commit()
        assert agent.is_active is False

    def test_delete(self, httpx_mock, session, payloads, base_url):
        agent_id = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{base_url}/api/agents/{agent_id}",
            status_code=204,
            text="",
        )
        agent = Agent(**payloads.agent(id=agent_id))
        session.delete(agent)
        session.commit()


class TestNodesFromFetchedAgent:
    """Nodes embedded in an agent payload must be usable for wiring."""

    agent_id = "00000000-0000-0000-0000-000000000701"
    node_a = "00000000-0000-0000-0000-0000000007a1"
    node_b = "00000000-0000-0000-0000-0000000007b1"

    def _register(self, httpx_mock, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/agents/{self.agent_id}$"),
            json=payloads.agent(
                id=self.agent_id,
                nodes=[
                    payloads.agent_node_info(id=self.node_a, task_name="a"),
                    payloads.agent_node_info(id=self.node_b, task_name="b"),
                ],
            ),
        )

    def test_nodes_inherit_agent_id_and_session(self, httpx_mock, session, payloads):
        self._register(httpx_mock, payloads)
        agent = session.get(Agent, id=self.agent_id)
        assert agent is not None
        assert all(str(n.agent_id) == self.agent_id for n in agent.nodes)
        assert all(n._is_bound for n in agent.nodes)

    def test_wiring_fetched_nodes_commits(self, httpx_mock, session, payloads):
        self._register(httpx_mock, payloads)
        for node_id in (self.node_a, self.node_b):
            httpx_mock.add_response(
                method="PUT",
                url=re.compile(rf".*/api/agents/{self.agent_id}/nodes/{node_id}$"),
                json=payloads.agent_node(id=node_id, agent_id=self.agent_id),
            )
        agent = session.get(Agent, id=self.agent_id)
        assert agent is not None
        a, b = agent.nodes
        a >> b
        session.commit()
        puts = [r for r in httpx_mock.get_requests() if r.method == "PUT"]
        assert len(puts) == 2
        assert json.loads(puts[0].content)["out_node_ids"] == [self.node_b]
        assert json.loads(puts[1].content)["in_node_ids"] == [self.node_a]
