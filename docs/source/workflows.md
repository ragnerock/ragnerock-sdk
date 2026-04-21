# Workflows

Workflows are a DAG of operators which are designed to process the documents provided. These can be triggered in two ways:

1. The workflow has `auto_run_on_upload` set to `True` and a document is uploaded to Ragnerock
2. The workflow is manually triggered via `session.run(my_workflow, documents=[...])`

Upon the successful execution of the workflow, a resulting [job](jobs.md) will be created

## Accessing existing workflows

Workflows can be listed via the folllowing

```python
from ragnerock import Workflow

workflows = session.list(Workflow).all()
```

Additionally, you can get individual workflows using an ID or a name

```python
from ragnerock import Workflow

workflow_1 = session.get(Workflow, id="...")
workflow_2 = session.get(Workflow, name="...")
```

## Creating a workflow

To create a workflow, you must first create the overarching object before adding nodes ([operators](operators.md))

```python
my_workflow = Workflow(
    name="ingest",
    description="Extract + classify pipeline",
    auto_run_on_upload=True,
)
session.add(wf)
session.commit()
```

Following this, you can then add the operators you want to execute. `wf.add_node(...)` stages a new node for creation and returns it so you can hold onto a reference for later wiring.

```python
# Run the operator no matter what
extract = wf.add_node(operator=extract_operator)

# Only run operator when the upstream condition matches
classify = wf.add_node(
    operator=classify_operator,
    condition={"extract_operator.total": {"gt": 0}},
)

# Commit so each node gets a server-assigned id — ids are required before
# wiring the graph with `>>` below.
session.commit()
```

## Chaining workflow nodes

Once the nodes above have ids (after `session.commit()`), use the `>>` operator to wire the execution graph. Both sides accept either a single node or a list of nodes.

```python
# Simple chain: extract -> classify
extract >> classify

# Fan-out: extract feeds both classify and summarize
extract >> [classify, summarize]

# Fan-in: extract + enrich both feed classify
[extract, enrich] >> classify

# Chained: [a, b] -> c -> [d, e]
[a, b] >> c >> [d, e]

session.commit()
```

`>>` is purely local — it mutates each node's `in_nodes` / `out_nodes` and stages both endpoints for update. Nothing hits the server until `session.commit()`. Wiring is deduped: running `a >> b` twice has no effect the second time.

## Updating an existing workflow

If you have an existing workflow you want to update, get the workflow object and then you can update any attributes and commit back to the server

```python
my_workflow.description = "Updated description"
my_workflow.is_active = False

session.update(wf)
session.commit()
```

## Deleting a workflow

Deletion of a workflow is relatively straightforward, just delete it from the session and commit back to the server

```python
session.delete(wf)
session.commit()
```

## Deleting workflow nodes

Individual nodes can be removed with `session.delete(node)` and a subsequent commit. The server rewires the surrounding edges.

```python
# Extract is an existing node

session.delete(extract)
session.commit()
```

## Getting workflow nodes

Nodes live under a parent workflow, so fetching one always requires identifying the workflow — by either `workflow_id=` or `workflow_name=`. The node itself can be looked up by `id=` or by `name=`, where `name=` matches the node's `operator_name` and returns the first match.

```python
from ragnerock import WorkflowNode

# By node id, workflow by id
node = session.get(WorkflowNode, id="...", workflow_id="...")

# By node id, workflow by name
node = session.get(WorkflowNode, id="...", workflow_name="ingest")

# By operator name, workflow by name
node = session.get(WorkflowNode, name="classify_operator", workflow_name="ingest")
```

Returns `None` if either the workflow or the node isn't found.

If you already have the workflow loaded, the nodes are on it directly — no extra request needed:

```python
wf = session.get(Workflow, id="...")
node = next(n for n in wf.nodes if n.id == node_id)
```

## Running a workflow

```python
job = session.run(wf, documents=[doc1, doc2])
job.wait()                 # block until SUCCEEDED / FAILED
```

See [jobs.md](jobs.md) for details on job tracking, cancel, retry, and status polling.

Every passed document must already be committed (have an `id`). Passing an unpersisted `Document` raises `ValidationError`.

## Workflow nodes

Nodes wrap operators with per-step config: when to fire, whether to persist output, how to handle errors.

Access via `wf.nodes`. Create them with `wf.add_node(operator=...)`, wire them with `>>`, update them through `session.update(node)`, and remove them with `session.delete(node)`.
