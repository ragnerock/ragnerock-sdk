# Sessions

A `Session` is scoped to one project. It supplies seven verbs.

## The seven verbs

| Verb | Immediate or staged? | What it does |
|---|---|---|
| `session.get(Type, id=..., name=...)` | immediate | Fetch one resource. Returns `None` if not found. |
| `session.list(Type, **filters)` | immediate | Return a lazy `PaginatedIterator`. |
| `session.query(sql)` | immediate | Run a SQL query and return a `QueryResult`. |
| `session.run(workflow, documents=[...])` | immediate | Kick off a workflow. Returns a `Job`. |
| `session.add(obj)` | **staged** | Queue creation. Flush with `commit()`. |
| `session.update(obj)` | **staged** | Queue update. Flush with `commit()`. |
| `session.delete(obj)` | **staged** | Queue deletion. Flush with `commit()`. |

Plus three transaction controls:

| Call | What it does |
|---|---|
| `session.commit()` | Flush all staged ops to the API, in order: adds → updates → deletes. |
| `session.refresh(obj)` | GET the resource from the server and overwrite local fields in place. |
| `session.rollback()` | Discard the staging queue (local-only). |

## Reads are immediate

```python
doc = session.get(Document, name="contract.pdf")        # one round trip
docs = session.list(Document).all()                     # paginated
result = session.query("SELECT * FROM invoice_extract") # one round trip
```

None of these touch the staging queue. You don't need to `commit()` after a read.

## Writes are staged

`add` / `update` / `delete` don't hit the network. They record intent.

```python
doc = Document(file_path="./report.pdf")
session.add(doc)
assert doc.id is None              # still unpersisted
session.commit()
assert doc.id is not None          # now it has a server ID
```

The same pattern for update and delete:

```python
doc.name = "renamed.pdf"
session.update(doc)                # staged
session.delete(other_doc)          # staged
session.commit()                   # both flush here, in order
```

### Why stage?

- Lets you build up a batch of changes and commit them together.
- Mirrors SQLAlchemy, so the pattern is familiar.
- Makes it obvious when network I/O happens.

## commit() is not atomic

Ragnerock has no server-side transaction primitive. If `commit()` fails partway, earlier successful ops stay applied. The exception tells you exactly what made it through:

```python
from ragnerock import CommitError

try:
    session.commit()
except CommitError as e:
    print(f"failed: {e}")
    print(f"these succeeded: {e.committed}")
    print(f"these did not run: {e.pending}")
    print(f"underlying cause: {e.cause}")
```

If you need an all-or-nothing guarantee, make the ops small and idempotent and retry at the application level.

## rollback()

`rollback()` only clears the local staging queue. It does not undo writes that already hit the server.

```python
session.add(doc)
session.rollback()       # fine — nothing was committed yet
# doc.id is still None

session.add(doc)
session.commit()         # doc is now on the server
session.rollback()       # no-op — nothing is staged
session.delete(doc)      # if you really want to undo, stage + commit a delete
session.commit()
```

## The context manager

```python
with Session(engine) as session:
    ...
```

`__enter__` lazy-connects the engine (login + project lookup) and raises on auth failure.

`__exit__` does **not** auto-commit. If the block exits with staged ops — including via exception — they're discarded. This matches SQLAlchemy and avoids surprise writes on unhappy paths.

If you want writes to survive, call `commit()` explicitly.

## run() needs committed resources

`session.run(workflow, documents=[...])` will refuse unpersisted resources. Call `commit()` first.

```python
doc = Document(file_path="./x.pdf")
session.add(doc)
session.run(wf, documents=[doc])   # raises ValidationError — doc has no id

session.commit()
session.run(wf, documents=[doc])   # OK
```

There is no autoflush. It's explicit by design.

## Pagination

`session.list(...)` returns a `PaginatedIterator`. It's lazy — pages come from the server as you iterate.

```python
it = session.list(Document)

it.all()                # fetch everything, return list
it.first()              # fetch just the first page, return item 0 (or None)
it.limit(50).all()      # return at most 50

for doc in it:          # iterate lazily
    print(doc.name)
```

`.limit(n)` returns a new iterator with a cap. `.all()` exhausts the iterator.

## Resource shortcut methods

Every fetched resource has a back-reference to its session, so it can navigate directly:

```python
doc = session.get(Document, id=...)
chunks = doc.list(Chunk).all()         # equivalent to session.list(Chunk, document_id=doc.id)
```

Which relationships are supported is documented on each resource page.
