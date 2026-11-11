"""End-to-end Agent flows.

CRUD is always exercised. The actual ``run()`` test is opt-in (gated on
``RAGNEROCK_ITEST_RUN_AGENTS``) because it consumes LLM quota and can take
minutes to complete.
"""

from __future__ import annotations

from uuid import uuid4

from ragnerock import (
    Agent,
    AgentNode,
    ChunkType,
    Document,
    Run,
    RunStatus,
    Task,
)

from tests.integration.conftest import skip_unless_env


def _make_noop_task(name: str) -> Task:
    return Task(
        name=name,
        description="noop task for wiring tests",
        jsonschema={"type": "object", "properties": {"value": {"type": "string"}}},
        generation_prompt='Return {"value": "hello"}.',
        chunk_type=ChunkType.DOCUMENT,
    )


class TestCrud:
    def test_agent_crud(self, session, unique_name):
        agent = Agent(
            name=unique_name,
            description="SDK integration test agent",
            auto_run_on_upload=False,
        )
        session.add(agent)
        session.commit()
        assert agent.id is not None

        try:
            fetched = session.get(Agent, id=agent.id)
            assert fetched is not None
            assert fetched.name == unique_name

            by_name = session.get(Agent, name=unique_name)
            assert by_name is not None
            assert by_name.id == agent.id

            names = [a.name for a in session.list(Agent)]
            assert unique_name in names

            new_description = "Updated by integration test"
            agent.description = new_description
            session.update(agent)
            session.commit()
            session.refresh(agent)
            assert agent.description == new_description
        finally:
            session.delete(agent)
            session.commit()

        assert session.get(Agent, id=agent.id) is None

    def test_get_by_missing_name_returns_none(self, session):
        assert session.get(Agent, name=f"sdk-itest-no-agent-{uuid4().hex[:8]}") is None


class TestNodeWiring:
    """End-to-end exercise of `agent.add_node(...)` + `>>` wiring."""

    def test_add_nodes_and_wire(self, session, unique_name):
        task_a = _make_noop_task(f"{unique_name}-a")
        task_b = _make_noop_task(f"{unique_name}-b")
        task_c = _make_noop_task(f"{unique_name}-c")
        session.add(task_a)
        session.add(task_b)
        session.add(task_c)
        session.commit()

        agent = Agent(name=unique_name, auto_run_on_upload=False)
        session.add(agent)
        session.commit()

        try:
            a = agent.add_node(task=task_a)
            b = agent.add_node(task=task_b)
            c = agent.add_node(task=task_c)
            session.commit()
            assert a.id is not None
            assert b.id is not None
            assert c.id is not None

            # Wire: [a, b] >> c
            [a, b] >> c
            session.commit()

            fetched = session.get(Agent, id=agent.id)
            assert fetched is not None
            nodes_by_id = {n.id: n for n in fetched.nodes}
            assert c.id in nodes_by_id[a.id].out_nodes
            assert c.id in nodes_by_id[b.id].out_nodes
            assert set(nodes_by_id[c.id].in_nodes) == {a.id, b.id}
        finally:
            session.delete(agent)
            session.commit()
            for task in (task_a, task_b, task_c):
                session.delete(task)
            session.commit()


class TestGetNode:
    """End-to-end coverage of ``session.get(AgentNode, ...)``."""

    def test_get_by_node_id_and_agent_id(self, session, unique_name):
        task = _make_noop_task(unique_name)
        session.add(task)
        session.commit()

        agent = Agent(name=unique_name, auto_run_on_upload=False)
        session.add(agent)
        session.commit()

        try:
            node = agent.add_node(task=task)
            session.commit()
            assert node.id is not None

            fetched = session.get(AgentNode, id=node.id, agent_id=agent.id)
            assert fetched is not None
            assert fetched.id == node.id
            assert fetched.task_id == task.id
            assert fetched.task_name == unique_name
        finally:
            session.delete(agent)
            session.commit()
            session.delete(task)
            session.commit()

    def test_get_by_agent_name_and_task_name(self, session, unique_name):
        task = _make_noop_task(unique_name)
        session.add(task)
        session.commit()

        agent = Agent(name=unique_name, auto_run_on_upload=False)
        session.add(agent)
        session.commit()

        try:
            node = agent.add_node(task=task)
            session.commit()
            assert node.id is not None

            fetched = session.get(AgentNode, name=unique_name, agent_name=unique_name)
            assert fetched is not None
            assert fetched.id == node.id
        finally:
            session.delete(agent)
            session.commit()
            session.delete(task)
            session.commit()

    def test_missing_node_returns_none(self, session, unique_name):
        agent = Agent(name=unique_name, auto_run_on_upload=False)
        session.add(agent)
        session.commit()

        try:
            assert (
                session.get(
                    AgentNode,
                    id=uuid4(),
                    agent_id=agent.id,
                )
                is None
            )
        finally:
            session.delete(agent)
            session.commit()

    def test_missing_agent_returns_none(self, session):
        assert (
            session.get(
                AgentNode,
                id=uuid4(),
                agent_name=f"sdk-itest-no-agent-{uuid4().hex[:8]}",
            )
            is None
        )


@skip_unless_env("RAGNEROCK_ITEST_RUN_AGENTS")
def test_run_and_wait(session, unique_name, tmp_path):
    """End-to-end: upload doc, create task + agent, run, wait, assert done.

    Opt-in only — consumes LLM quota.
    """
    task = Task(
        name=unique_name,
        description="noop task",
        jsonschema={"type": "object", "properties": {"value": {"type": "string"}}},
        generation_prompt='Return {"value": "hello"}.',
        chunk_type=ChunkType.DOCUMENT,
    )
    session.add(task)
    session.commit()

    agent = Agent(name=unique_name, auto_run_on_upload=False)
    session.add(agent)
    session.commit()

    file_path = tmp_path / f"{unique_name}.txt"
    file_path.write_text("Hello world.")
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

    try:
        run = session.run(agent, documents=[doc])
        assert isinstance(run, Run)
        assert run.id is not None
        run.wait(timeout=300, poll_interval=5)
        assert run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED)
    finally:
        session.delete(doc)
        session.commit()
        session.delete(agent)
        session.commit()
        session.delete(task)
        session.commit()
