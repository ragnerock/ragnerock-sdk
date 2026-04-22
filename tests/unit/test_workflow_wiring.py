"""Tests for the `>>` DAG-wiring operator and `Workflow.add_node`."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from ragnerock import Operator, Workflow, WorkflowNode
from ragnerock.errors import ValidationError


class _FakeSession:
    """Minimal session stand-in that records staged resources.

    The `>>` operator only needs `session.update(node)`, and `Workflow.add_node`
    only needs `session.add(node)`. We don't care about network calls here.
    """

    def __init__(self) -> None:
        self.added: list[object] = []
        self.updated: list[object] = []

    def add(self, resource: object) -> None:
        for existing in self.added:
            if existing is resource:
                return
        self.added.append(resource)

    def update(self, resource: object) -> None:
        for existing in self.updated:
            if existing is resource:
                return
        self.updated.append(resource)


def _make_node(session: _FakeSession, workflow_id: UUID) -> WorkflowNode:
    node = WorkflowNode(
        id=uuid4(),
        workflow_id=workflow_id,
        operator_id=uuid4(),
        operator_name="op",
    )
    node._bind(session)  # type: ignore[arg-type]
    return node


@pytest.fixture
def session() -> _FakeSession:
    return _FakeSession()


@pytest.fixture
def workflow_id() -> UUID:
    return uuid4()


@pytest.fixture
def nodes(session, workflow_id):
    """Five nodes (a, b, c, d, e) all sharing a session and workflow."""
    return [_make_node(session, workflow_id) for _ in range(5)]


class TestBasicWiring:
    def test_single_node_wiring(self, session, nodes):
        a, b, *_ = nodes
        result = a >> b
        assert result is b
        assert a.out_nodes == [b.id]
        assert b.in_nodes == [a.id]
        assert a in session.updated
        assert b in session.updated

    def test_chain_returns_right_side(self, session, nodes):
        a, b, c, *_ = nodes
        result = a >> b >> c
        assert result is c
        assert a.out_nodes == [b.id]
        assert b.in_nodes == [a.id]
        assert b.out_nodes == [c.id]
        assert c.in_nodes == [b.id]

    def test_fan_out_with_list_rhs(self, session, nodes):
        a, b, c, *_ = nodes
        result = a >> [b, c]
        assert result == [b, c]
        assert a.out_nodes == [b.id, c.id]
        assert b.in_nodes == [a.id]
        assert c.in_nodes == [a.id]

    def test_fan_in_with_list_lhs(self, session, nodes):
        a, b, c, d, _ = nodes
        result = [a, b, c] >> d
        assert result is d
        assert d.in_nodes == [a.id, b.id, c.id]
        assert a.out_nodes == [d.id]
        assert b.out_nodes == [d.id]
        assert c.out_nodes == [d.id]

    def test_fan_in_then_fan_out(self, session, nodes):
        a, b, c, d, e = nodes
        # [a, b] >> c >> [d, e]
        result = [a, b] >> c >> [d, e]
        assert result == [d, e]
        assert c.in_nodes == [a.id, b.id]
        assert c.out_nodes == [d.id, e.id]
        assert d.in_nodes == [c.id]
        assert e.in_nodes == [c.id]


class TestIdempotency:
    def test_duplicate_edges_are_deduped(self, session, nodes):
        a, b, *_ = nodes
        a >> b
        a >> b
        a >> b
        assert a.out_nodes == [b.id]
        assert b.in_nodes == [a.id]

    def test_session_update_is_idempotent(self, session, nodes):
        a, b, *_ = nodes
        a >> b
        a >> b
        # The fake session dedups by identity, so each node appears once.
        assert session.updated.count(a) == 1
        assert session.updated.count(b) == 1


class TestValidation:
    def test_wiring_unpersisted_node_raises(self, session, workflow_id, nodes):
        a = nodes[0]
        unpersisted = WorkflowNode(workflow_id=workflow_id, operator_id=uuid4())
        unpersisted._bind(session)  # type: ignore[arg-type]
        with pytest.raises(ValidationError, match="no id yet"):
            a >> unpersisted
        with pytest.raises(ValidationError, match="no id yet"):
            unpersisted >> a

    def test_wiring_unbound_node_raises(self, workflow_id, nodes):
        a = nodes[0]
        floating = WorkflowNode(
            id=uuid4(), workflow_id=workflow_id, operator_id=uuid4()
        )
        # not bound to any session
        with pytest.raises(RuntimeError, match="bound to a session"):
            a >> floating

    def test_cross_workflow_wiring_raises(self, session, nodes):
        a = nodes[0]
        other = WorkflowNode(id=uuid4(), workflow_id=uuid4(), operator_id=uuid4())
        other._bind(session)  # type: ignore[arg-type]
        with pytest.raises(ValidationError, match="different workflows"):
            a >> other

    def test_cross_session_wiring_raises(self, workflow_id, nodes):
        a = nodes[0]
        other_session = _FakeSession()
        other = WorkflowNode(id=uuid4(), workflow_id=workflow_id, operator_id=uuid4())
        other._bind(other_session)  # type: ignore[arg-type]
        with pytest.raises(ValidationError, match="different sessions"):
            a >> other

    def test_rshift_with_wrong_type_raises(self, nodes):
        a = nodes[0]
        with pytest.raises(TypeError, match="WorkflowNode"):
            a >> "not-a-node"  # type: ignore[operator]

    def test_rshift_list_with_wrong_type_raises(self, nodes):
        a = nodes[0]
        with pytest.raises(TypeError, match="WorkflowNode"):
            a >> [nodes[1], "not-a-node"]  # type: ignore[list-item]


class TestWorkflowAddNode:
    def test_add_node_stages_and_returns(self, session, workflow_id):
        wf = Workflow(id=workflow_id, name="wf")
        wf._bind(session)  # type: ignore[arg-type]

        op = Operator(id=uuid4(), name="extract")
        node = wf.add_node(operator=op)

        assert isinstance(node, WorkflowNode)
        assert node.workflow_id == wf.id
        assert node.operator_id == op.id
        assert node.operator_name == "extract"
        assert node in wf.nodes
        assert node in session.added

    def test_add_node_forwards_config(self, session, workflow_id):
        wf = Workflow(id=workflow_id, name="wf")
        wf._bind(session)  # type: ignore[arg-type]
        op = Operator(id=uuid4(), name="classify")

        node = wf.add_node(
            operator=op,
            condition={"extract.total": {"$gt": 0}},
            persist=False,
            on_error="SKIP_NODE",
            max_retries=3,
        )
        assert node.condition == {
            "type": "field_comparison",
            "field_path": "extract.total",
            "operator": ">",
            "value": 0,
        }
        assert node.persist is False
        assert node.on_error == "SKIP_NODE"
        assert node.max_retries == 3

    def test_add_node_rejects_malformed_condition(self, session, workflow_id):
        wf = Workflow(id=workflow_id, name="wf")
        wf._bind(session)  # type: ignore[arg-type]
        op = Operator(id=uuid4(), name="classify")

        with pytest.raises(ValidationError, match="unknown operator"):
            wf.add_node(operator=op, condition={"score": {"$bogus": 0}})

    def test_add_node_on_unbound_workflow_raises(self, workflow_id):
        wf = Workflow(id=workflow_id, name="wf")
        op = Operator(id=uuid4(), name="op")
        with pytest.raises(RuntimeError, match="not bound to a session"):
            wf.add_node(operator=op)

    def test_add_node_on_unpersisted_workflow_raises(self, session):
        wf = Workflow(name="wf")
        wf._bind(session)  # type: ignore[arg-type]
        op = Operator(id=uuid4(), name="op")
        with pytest.raises(ValidationError, match="unpersisted workflow"):
            wf.add_node(operator=op)

    def test_add_node_with_unpersisted_operator_raises(self, session, workflow_id):
        wf = Workflow(id=workflow_id, name="wf")
        wf._bind(session)  # type: ignore[arg-type]
        op = Operator(name="op")  # no id
        with pytest.raises(ValidationError, match="unpersisted operator"):
            wf.add_node(operator=op)
