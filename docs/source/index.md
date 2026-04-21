# ragnerock — Python SDK

A SQLAlchemy-shaped client for the Ragnerock API. Connect with a URL, open a session, work with resource objects.

```{toctree}
:maxdepth: 1
:caption: User guide:
annotations.md
connecting.md
documents
errors
jobs
operators
queries
sessions
workflows
```

```{toctree}
:maxdepth: 2
:caption: API reference:
api/ragnerock
api/engine
api/session
api/client
api/errors
api/query_result
api/iterator
api/resources
```

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
