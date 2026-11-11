# Runs

A run is one execution of an [agent](agents.md) against one document. `session.run(agent, documents=[...])` creates them; you don't construct them by hand. Ragnerock also starts runs on its own, for example when an agent runs on upload; those have `kind == RunKind.AUTOMATIC`.

## Getting a run handle

```python
from ragnerock import Run

run = session.run(my_agent, documents=[doc])   # returns the first Run

# Fetch explicitly
run = session.get(Run, id="...")
```

A document's most recent run is also available from the document itself: `doc.latest_run()` (see [Documents](documents.md)).

## Polling status

```python
from ragnerock import RunStatus

run.refresh()
if run.status == RunStatus.IN_PROGRESS:
    ...
elif run.status == RunStatus.SUCCEEDED:
    ...
elif run.status == RunStatus.FAILED:
    print(run.status_message)
```

`RunStatus` values: `NOT_STARTED`, `IN_PROGRESS`, `SUCCEEDED`, `FAILED`.

## Waiting

```python
run.wait()                               # poll until terminal
run.wait(timeout=60, poll_interval=2)    # with a 60s cap; raises TimeoutError
```

## Listing runs

```python
from ragnerock import Run, RunStatus

runs = session.list(Run).all()

# Filter by status
runs = session.list(Run, status=RunStatus.FAILED).all()
runs = session.list(Run, status=[RunStatus.NOT_STARTED, RunStatus.IN_PROGRESS]).all()
```

## Cancel and retry

```python
run.cancel()     # stop a pending / in-progress run
run.retry()      # re-run a failed run
```

Both require a bound session. To run a succeeded run again as a new run, leaving the original and its results alone, use the low-level `engine.client.runs.rerun(run.id)`; see [Platform APIs](platform.md#runs-and-output-deliveries).
