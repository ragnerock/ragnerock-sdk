# Jobs

A job is a single workflow execution against a single document. Created by `session.run(workflow, documents=[...])` — not by hand.

## Getting a job handle

```python
job = session.run(wf, documents=[doc])   # returns the first Job

# Fetch explicitly
job = session.get(Job, id="...")
```

## Polling status

```python
from ragnerock import JobStatus

job.refresh()
if job.status == JobStatus.IN_PROGRESS:
    ...
elif job.status == JobStatus.SUCCEEDED:
    ...
elif job.status == JobStatus.FAILED:
    print(job.status_message)
```

`JobStatus` values: `NOT_STARTED`, `IN_PROGRESS`, `SUCCEEDED`, `FAILED`.

## Waiting

```python
job.wait()                               # poll until terminal
job.wait(timeout=60, poll_interval=2)    # with a 60s cap; raises TimeoutError
```

## Listing jobs

```python
from ragnerock import Job, JobStatus

jobs = session.list(Job).all()

# Filter by status
jobs = session.list(Job, status=JobStatus.FAILED).all()
jobs = session.list(Job, status=[JobStatus.NOT_STARTED, JobStatus.IN_PROGRESS]).all()
```

## Cancel and retry

```python
job.cancel()     # stop a pending / in-progress job
job.retry()      # re-run a failed job
```

Both require a bound session.
