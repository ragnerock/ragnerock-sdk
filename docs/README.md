# ragnerock — Python SDK

A SQLAlchemy-shaped client for the Ragnerock API. Connect with a URL, open a session, work with resource objects.

## Install

```bash
pip install ragnerock
```

For `QueryResult.to_pandas()`, also install pandas:

```bash
pip install 'ragnerock[pandas]'
```

## 60-second quick start

```python
from ragnerock import create_engine, Session, Document

engine = create_engine("ragnerock://you@example.com:pass@api.ragnerock.com/my_project")

with Session(engine) as session:
    # read
    docs = session.list(Document).all()
    doc = session.get(Document, name="contract.pdf")

    # write
    new = Document(file_path="./report.pdf", name="q1-report")
    session.add(new)
    session.commit()        # new.id is populated here

    # query
    result = session.query("SELECT * FROM invoice_extract WHERE total > 1000")
    df = result.to_pandas()
```

## Pages

- [connecting.md](connecting.md) — connection strings, auth, common errors
- [sessions.md](sessions.md) — the read/write verbs, transactions, pagination
- [documents.md](documents.md) — documents, groups, chunks, pages
- [annotations.md](annotations.md) — creating and listing annotations
- [operators.md](operators.md) — operators
- [workflows.md](workflows.md) — workflows
- [jobs.md](jobs.md) — jobs (running workflows, polling, cancel / retry)
- [queries.md](queries.md) — SQL queries
- [errors.md](errors.md) — the error hierarchy

## Design in one paragraph

An `Engine` holds the connection config. A `Session` is scoped to a single project and supplies seven verbs: the reads (`get`, `list`, `query`, `run`) fire immediately; the writes (`add`, `update`, `delete`) stage into a unit of work that flushes on `commit()`. If commit fails partway, it stops and raises a `CommitError` — the Ragnerock API has no server-side rollback, so already-committed ops stay applied. `refresh(obj)` re-pulls state from the server; `rollback()` drops anything staged but not yet committed.
