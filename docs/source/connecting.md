# Connecting

## Authentication options

The SDK supports two ways to authenticate against the Ragnerock API:

- **Email + password** — for interactive accounts. The SDK exchanges these for a bearer token on the first session via `POST /api/auth/login`.
- **API token** — for CI, scripts, and service accounts. A pre-issued bearer token is attached to every request as `Authorization: Bearer <token>`; no login round-trip is made.

## Connection string

```
ragnerock://{email}:{password}@{host}[:{port}]/{project_name}
ragnerock://token:{api_token}@{host}[:{port}]/{project_name}
ragnerock://{host}[:{port}]/{project_name}                  # token from env
```

The literal username `token` is a sentinel: it means the "password" slot holds a bearer token instead of a password. When no userinfo is present, the token is read from the `RAGNEROCK_API_TOKEN` environment variable.

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

The email and password are URL-encoded; characters like `@`, `:`, `/`, and `#` in a password must be percent-encoded. The same applies to API tokens embedded in the DSN: characters like `:`, `/`, `@`, `?`, `#`, `%` must be percent-encoded. Most tokens (JWTs, opaque alphanumerics) are safe as-is.

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

### Precedence

For tokens specifically:

1. A token embedded in the DSN (`token:…@host` form) wins.
2. Otherwise, `RAGNEROCK_API_TOKEN` from the environment is used.
3. If the DSN supplies email/password while `RAGNEROCK_API_TOKEN` is also set in the environment, `create_engine` raises `ValueError` rather than silently picking one.

## Security

- Prefer `RAGNEROCK_API_TOKEN` over inline DSNs in shared environments — connection strings can end up in shell history, CI logs, and process listings.
- Never commit a token-bearing DSN to source control.
- The SDK does not log the token. If you build error messages from your own code, be careful not to echo the DSN back.

## Lazy connection

`create_engine(...)` does not hit the network. Authentication and project lookup happen on the first `with Session(engine):`:

```python
engine = create_engine("...")        # no network I/O
with Session(engine) as session:     # login + project lookup happen here
    ...
```

If the credentials are wrong or the project doesn't exist, `Session(engine).__enter__` raises. With API-token mode there is no login call — a bad token surfaces as `AuthenticationError` on the first protected request (typically the project-name lookup).

## Errors you might see here

| Exception | Meaning |
|---|---|
| `ValueError` | The connection string is malformed (missing scheme, host, or project), the API token is empty, or conflicting credentials are supplied. |
| `AuthenticationError` | Login failed — bad email/password, or the API token was rejected. |
| `NotFoundError` | Project name didn't match any project you have access to. |
| `RagnerockError` | Some other API error during connection. |

See [errors.md](errors.md) for the full hierarchy.
