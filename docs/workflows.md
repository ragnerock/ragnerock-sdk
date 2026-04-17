# Workflows

A workflow is a DAG of operators that runs against documents. Workflows don't execute on their own — run them with `session.run(workflow, documents=[...])`, which creates [jobs](jobs.md).

## Listing and getting

```python
from ragnerock import Workflow

workflows = session.list(Workflow).all()
wf = session.get(Workflow, id="...")
wf = session.get(Workflow, name="ingest")
```

## Creating

```python
wf = Workflow(
    name="ingest",
    description="Extract + classify pipeline",
    auto_run_on_upload=True,
)
session.add(wf)
session.commit()

# Add nodes (operators to run)
wf.add_node(operator=extract_op)
wf.add_node(operator=classify_op, condition={"total": {"gt": 0}})
session.commit()
```

`auto_run_on_upload=True` makes the server automatically run this workflow whenever a new document is uploaded to the project.

## Updating

```python
wf.description = "Updated description"
wf.is_active = False
session.update(wf)
session.commit()
```

## Deleting

```python
session.delete(wf)
session.commit()
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

Access via `wf.nodes`. Full CRUD on individual nodes is exposed via the low-level client (`session._engine.client.workflows.add_node(...)` etc.) and is planned for a later SDK surface.
