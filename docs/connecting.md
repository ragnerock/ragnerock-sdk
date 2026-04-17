# Connecting

## Connection string

```
ragnerock://{email}:{password}@{host}[:{port}]/{project_name}
```

Examples:

```python
from ragnerock import create_engine

# Production
engine = create_engine("ragnerock://you@example.com:pass@api.ragnerock.com/my_project")

# Self-hosted, with an explicit port
engine = create_engine("ragnerock://you@example.com:pass@ragnerock.internal:8443/my_project")
```

The email and password are URL-encoded; characters like `@`, `:`, `/`, and `#` in a password must be percent-encoded.

## Lazy connection

`create_engine(...)` does not hit the network. Authentication and project lookup happen on the first `with Session(engine):`:

```python
engine = create_engine("...")        # no network I/O
with Session(engine) as session:     # login + project lookup happen here
    ...
```

If the credentials are wrong or the project doesn't exist, `Session(engine).__enter__` raises.

## Errors you might see here

| Exception | Meaning |
|---|---|
| `ValueError` | The connection string is malformed (missing scheme, user, host, or project). |
| `AuthenticationError` | Login failed — bad email or password. |
| `NotFoundError` | Project name didn't match any project you have access to. |
| `RagnerockError` | Some other API error during connection. |

See [errors.md](errors.md) for the full hierarchy.
