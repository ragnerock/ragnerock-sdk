# Agents

An agent is a DAG of [tasks](tasks.md) that processes the documents you give it. Each place in the graph is an `AgentNode` wrapping one task. An agent runs in three ways:

1. It has `auto_run_on_upload` set to `True` (the default is `False`), and a document is uploaded to Ragnerock.
2. You start it with `session.run(my_agent, documents=[...])`.
3. It has a schedule (see [Schedules, inputs, outputs, and change requests](#schedules-inputs-outputs-and-change-requests)).

Each document an agent processes gets a [run](runs.md).

## Accessing existing agents

List agents with:

```python
from ragnerock import Agent

agents = session.list(Agent).all()
```

You can also get one agent by ID or by name:

```python
from ragnerock import Agent

agent_1 = session.get(Agent, id="...")
agent_2 = session.get(Agent, name="...")
```

## Creating an agent

Create the agent itself first, then add its nodes ([tasks](tasks.md)):

```python
my_agent = Agent(
    name="ingest",
    description="Extract + classify pipeline",
    auto_run_on_upload=True,
)
session.add(my_agent)
session.commit()
```

Then add the tasks you want to run. `my_agent.add_node(...)` stages a new node for creation and returns it, so you can keep a reference for wiring later.

```python
# Run the task no matter what
extract = my_agent.add_node(task=extract_task)

# Only run the task when the upstream condition matches
classify = my_agent.add_node(
    task=classify_task,
    condition={"extract_task.total": {"gt": 0}},
)

# Commit so each node gets a server-assigned id — ids are required before
# wiring the graph with `>>` below.
session.commit()
```

## Chaining agent nodes

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

## Updating an existing agent

To update an agent, get it, change any attributes, and commit:

```python
my_agent.description = "Updated description"
my_agent.is_active = False

session.update(my_agent)
session.commit()
```

## Deleting an agent

Delete the agent from the session and commit:

```python
session.delete(my_agent)
session.commit()
```

## Deleting agent nodes

Remove a node with `session.delete(node)` and a commit. The server rewires the surrounding edges.

```python
# extract is an existing node
session.delete(extract)
session.commit()
```

## Getting agent nodes

Nodes live under a parent agent, so fetching one always identifies the agent, by either `agent_id=` or `agent_name=`. Look up the node itself by `id=` or by `name=`; `name=` matches the node's `task_name` and returns the first match.

```python
from ragnerock import AgentNode

# By node id, agent by id
node = session.get(AgentNode, id="...", agent_id="...")

# By node id, agent by name
node = session.get(AgentNode, id="...", agent_name="ingest")

# By task name, agent by name
node = session.get(AgentNode, name="classify_task", agent_name="ingest")
```

Returns `None` if either the agent or the node isn't found.

If you already have the agent loaded, its nodes are on it directly, with no extra request:

```python
my_agent = session.get(Agent, id="...")
node = next(n for n in my_agent.nodes if n.id == node_id)
```

## Running an agent

```python
run = session.run(my_agent, documents=[doc1, doc2])
run.wait()                 # block until SUCCEEDED / FAILED
```

See [Runs](runs.md) for tracking, cancelling, and retrying runs and polling their status.

Every document you pass must already be committed (have an `id`). Passing an unpersisted `Document` raises `ValidationError`.

## Agent nodes

Nodes wrap tasks with per-node configuration: when to fire, whether to persist output, and how to handle errors.

Access them through `my_agent.nodes`. Create them with `my_agent.add_node(task=...)`, wire them with `>>`, update them with `session.update(node)`, and remove them with `session.delete(node)`.

## Node options

`add_node` accepts `persist` (store the node's annotations), `on_error` (`"SKIP_NODE"`, the default, or `"FAIL_RUN"`), `max_retries`, and `annotations_only`. Nodes loaded with an agent (`session.get(Agent, ...)`) are bound to the session and can be updated, deleted, or wired with `>>` directly.

A node's `target_input_id` names the file input it annotates (`None` means the agent's only file input), and `context_input_ids` lists the inputs wired to it as context.

## Schedules, inputs, outputs, and change requests

Agent features beyond the node graph are on the low-level client, `engine.client.agents`:

```python
from ragnerock import AgentSchedule
from ragnerock.client.agents import web_fetch_input

client = engine.client

# Recurring runs
client.agents.set_schedule(my_agent.id, AgentSchedule(cron="0 6 * * 1-5", timezone="America/New_York"))
client.agents.schedule_preview(cron="0 6 * * 1-5", timezone="America/New_York")
client.agents.clear_schedule(my_agent.id)

# Where the agent's data comes from, and where its results go
client.agents.set_inputs(
    my_agent.id,
    inputs=[web_fetch_input("filings", "https://example.com/filings.csv")],
)
client.agents.set_outputs(
    my_agent.id,
    outputs=[
        {
            "name": "table",
            "parent_node_ids": [str(classify.id)],
            "config": {"kind": "artifact", "format": "csv"},
        }
    ],
)

# Change requests opened by the agent's change-request outputs
for cr in client.agents.change_requests.list(my_agent.id).items:
    print(cr.id, cr.status, cr.document_count)
```

Saving a schedule authorizes recurring runs under your identity. To manage agents as configuration (nodes, conditions, decorators, inputs, outputs, and schedules together), prefer [GitOps manifests](gitops.md). See [Platform APIs](platform.md) for the full client surface.
