# Connecting

## Authentication options

The SDK supports two authentication mechanisms

- Email + Password
- API token

## Connection string

```
ragnerock://{email}:{password}@{host}[:{port}]/{project_name}
ragnerock://token:{api_token}@{host}[:{port}]/{project_name}
ragnerock://{host}[:{port}]/{project_name}                    # Token pulled from `RAGNEROCK_API_TOKEN`
```

The literal username `token` indicates that the "password" slot in the connection string holds a bearer token instead of a password. When no userinfo is present, the token is read from the `RAGNEROCK_API_TOKEN` environment variable.

Examples:

```python
from ragnerock import create_engine

# Email + password
engine = create_engine("ragnerock://you@example.com:pass@api.ragnerock.com/my_project")

# Email + password, self-hosted with an explicit port
engine = create_engine("ragnerock://you@example.com:pass@ragnerock.internal:8443/my_project")

# API token in the DSN
engine = create_engine("ragnerock://token:eyJhbGciOi...@api.ragnerock.com/my_project")

# API token from the environment (RAGNEROCK_API_TOKEN must be set)
engine = create_engine("ragnerock://api.ragnerock.com/my_project")
```

The email and password are URL-encoded and characters like `@`, `:`, `/`, and `#` in a password must be percent-encoded

## From environment

The CLI's `build_engine` resolves an engine from these variables:

| Variable | Purpose |
|---|---|
| `RAGNEROCK_CONNECTION_STRING` | A full `ragnerock://...` DSN. Takes precedence over the split-var form. |
| `RAGNEROCK_HOST` | Hostname or full URL of the API. |
| `RAGNEROCK_PROJECT` | Project name. |
| `RAGNEROCK_API_TOKEN` | Pre-issued bearer token. Use this OR email/password. |
| `RAGNEROCK_EMAIL` | Account email (email/password mode). |
| `RAGNEROCK_PASSWORD` | Account password (email/password mode). |

When `RAGNEROCK_API_TOKEN` is set together with `RAGNEROCK_HOST` and `RAGNEROCK_PROJECT`, email and password are not required.

In the event a token is not specified in the DSN (e.g. `ragnerock://token:...@host...`), then the SDK will fall back to pulling from the `RAGNEROCK_API_TOKEN` environment variable. In the event that both an API token and email/password are supplied, the SDK will raise a `ValueError` to indicate this.

## Lazy connection

`create_engine(...)` does not hit the network. Authentication and project lookup happen on the first `with Session(engine):`:

```python
engine = create_engine("...")        # no network I/O
with Session(engine) as session:     # login + project lookup happen here
    ...
```

If the credentials are wrong or the project doesn't exist, `Session(engine).__enter__` raises. With API-token mode there is no login call, instead a bad token surfaces as `AuthenticationError` on the first protected request.

## Errors you might see here

| Exception | Meaning |
|---|---|
| `ValueError` | The connection string is malformed (missing scheme, host, or project), the API token is empty, or conflicting credentials are supplied. |
| `AuthenticationError` | Login failed — bad email/password, or the API token was rejected. |
| `NotFoundError` | Project name didn't match any project you have access to. |
| `RagnerockError` | Some other API error during connection. |

See [errors.md](errors.md) for the full hierarchy.
