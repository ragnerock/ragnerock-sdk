# Errors

Every error the SDK raises is a subclass of `RagnerockError`.

```
RagnerockError
├── AuthenticationError    401, 403
├── NotFoundError          404 (where we don't prefer returning None)
├── ValidationError        422, client-side precondition failures
├── QueryError             structured query engine errors
└── CommitError            session.commit() failed partway
```

## Shared attributes

Every `RagnerockError` has:

| Attribute | Meaning |
|---|---|
| `message` | Human-readable error text. |
| `status_code` | HTTP status, if applicable. |
| `suggestion` | Server-provided suggestion, if any. |
| `details` | Any additional structured info from the API. |

## When each one fires

### `AuthenticationError`
- Login failed (wrong email / password).
- Token rejected mid-session (expired, revoked).

### `NotFoundError`
- A named resource lookup used by the Engine didn't resolve (e.g. the project in the connection string).
- Most `session.get(Type, id=...)` calls return `None` instead — `NotFoundError` is reserved for cases where "not found" is an actual error, not a legitimate outcome.

### `ValidationError`
- Server 422 — request body violates the API schema.
- Client-side preconditions: `session.run()` called with uncommitted resources; `session.refresh()` on an unpersisted object; `Document` created without `file_path` or `source_url`.

### `QueryError`
Raised when `session.query(...)` fails. Adds one more attribute:

| Attribute | Meaning |
|---|---|
| `error_code` | Structured code from the query engine (e.g. `SYNTAX_ERROR`, `UNKNOWN_TABLE`). |

```python
from ragnerock import QueryError

try:
    session.query("SELEKT 1")
except QueryError as e:
    print(e.error_code, e.message, e.suggestion)
```

### `CommitError`
Raised when `session.commit()` fails before the queue is empty. Adds:

| Attribute | Meaning |
|---|---|
| `committed` | Resources that were successfully written to the server before the abort. |
| `pending` | Resources that were not written. |
| `cause` | The underlying exception that stopped commit. |

Because the API has no rollback, `committed` items are still applied server-side. Your job is to decide what to do about `pending`.

```python
from ragnerock import CommitError

try:
    session.commit()
except CommitError as e:
    log.error("commit failed", exc_info=e.cause)
    log.info("wrote %d, %d left", len(e.committed), len(e.pending))
```
