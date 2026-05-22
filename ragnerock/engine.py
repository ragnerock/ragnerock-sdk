"""Engine and connection-string parsing."""

from __future__ import annotations

import os
from urllib.parse import unquote, urlparse
from uuid import UUID

from ragnerock.client import RagnerockClient
from ragnerock.errors import AuthenticationError, NotFoundError, RagnerockError

API_TOKEN_ENV_VAR = "RAGNEROCK_API_TOKEN"
_TOKEN_USERNAME_SENTINEL = "token"


class Engine:
    """Holds connection config and manages authentication.

    Created via :func:`create_engine` and passed to :class:`Session`.
    Authentication and project resolution are deferred until the first
    :class:`Session` opens, so constructing an engine never raises network
    errors.

    Attributes:
        host (str): Base API URL (e.g. ``https://api.ragnerock.com``).
        project_name (str): Project name parsed from the connection string.
    """

    def __init__(
        self,
        *,
        host: str,
        project_name: str,
        email: str | None = None,
        password: str | None = None,
        auth_token: str | None = None,
    ) -> None:
        """Store connection config. Performs no network I/O.

        Prefer :func:`create_engine` for the usual connection-string path; use
        this constructor directly only when you already have the individual
        fields in hand (for example, in tests).

        Exactly one of ``auth_token`` or the (``email``, ``password``) pair
        must be supplied.

        Args:
            host (str): Fully-qualified base URL, including scheme
                (e.g. ``https://api.ragnerock.com``).
            project_name (str): Project to scope sessions to. Resolved to a
                project ID on the first session open.
            email (str | None): Account email used for email/password
                authentication.
            password (str | None): Account password used for email/password
                authentication.
            auth_token (str | None): Pre-issued bearer token. When provided,
                ``POST /api/auth/login`` is skipped and the token is attached
                directly to outgoing requests.

        Raises:
            ValueError: If neither, or both, authentication methods are
                supplied.
        """
        has_password_auth = email is not None and password is not None
        has_token_auth = auth_token is not None
        if has_password_auth and has_token_auth:
            raise ValueError(
                "Provide either auth_token or (email, password), not both"
            )
        if not has_password_auth and not has_token_auth:
            raise ValueError(
                "Missing authentication: provide auth_token or (email, password)"
            )

        self.host = host
        self.project_name = project_name
        self._email = email
        self._password = password
        self._auth_token = auth_token
        self._client = RagnerockClient(host=host, auth_token=auth_token)
        self._project_id: UUID | None = None
        self._connected = False

    def _ensure_connected(self) -> None:
        """Authenticate and resolve ``project_name`` to a project ID.

        Idempotent: subsequent calls are no-ops once the client has a bearer
        token and the project ID is cached.

        Raises:
            AuthenticationError: Login failed (bad credentials, unreachable
                host surfacing as an auth failure, etc.).
            NotFoundError: The configured ``project_name`` does not exist on
                the server.
        """
        if self._connected:
            return

        if self._auth_token is None:
            assert self._email is not None and self._password is not None
            try:
                self._client.auth.login(email=self._email, password=self._password)
            except AuthenticationError:
                raise
            except RagnerockError as e:
                raise AuthenticationError(
                    e.message,
                    status_code=e.status_code,
                    suggestion=e.suggestion,
                    details=e.details,
                ) from e

        project_list = self._client.projects.get_by_name(self.project_name)
        if not project_list.projects:
            raise NotFoundError(f"Project '{self.project_name}' not found")

        self._project_id = project_list.projects[0].id
        self._connected = True

    @property
    def client(self) -> RagnerockClient:
        """Low-level HTTP client bound to this engine.

        Returns the client without triggering authentication; a freshly
        constructed engine has no bearer token yet. Authentication happens
        when a :class:`~ragnerock.session.Session` is opened or when
        :attr:`project_id` is accessed.

        Returns:
            RagnerockClient: The low-level client. Its ``auth_token`` is
            populated only after :meth:`_ensure_connected` has run.
        """
        return self._client

    @property
    def project_id(self) -> UUID:
        """UUID of the project this engine is scoped to.

        Triggers authentication on first access; subsequent accesses are free.

        Returns:
            UUID: The resolved project id.

        Raises:
            AuthenticationError: If authentication fails on first access.
            NotFoundError: If the configured project cannot be resolved.
        """
        self._ensure_connected()
        assert self._project_id is not None
        return self._project_id


def create_engine(connection_string: str) -> Engine:
    """Create an :class:`Engine` from a connection string.

    Two authentication modes are supported:

    1. **Email + password** (interactive accounts)::

        ragnerock://{email}:{password}@{host}[:{port}]/{project_name}

    2. **API token** (CI, scripts, service accounts) — the literal username
       ``token`` is a sentinel that means "the password slot holds a bearer
       token, not a password"::

        ragnerock://token:{api_token}@{host}[:{port}]/{project_name}

    When no userinfo is present in the DSN
    (``ragnerock://{host}/{project_name}``), the token is read from the
    ``RAGNEROCK_API_TOKEN`` environment variable. Precedence: an inline DSN
    token wins over the env var. Supplying email/password in the DSN while
    also setting ``RAGNEROCK_API_TOKEN`` raises :class:`ValueError` rather
    than silently picking one.

    Tokens containing ``:``, ``/``, ``@``, ``?``, ``#``, ``%`` must be
    percent-encoded.

    Examples::

        create_engine("ragnerock://user@example.com:pass@api.ragnerock.com/my_project")
        create_engine("ragnerock://token:abc123@api.ragnerock.com/my_project")
        # With RAGNEROCK_API_TOKEN set in the environment:
        create_engine("ragnerock://api.ragnerock.com/my_project")

    Args:
        connection_string (str): A Ragnerock connection string.

    Returns:
        Engine: An unconnected :class:`Engine` (no network I/O has happened
        yet).

    Raises:
        ValueError: If the connection string is malformed, no authentication
            method can be resolved, or conflicting credentials are supplied.
    """
    parsed = urlparse(connection_string)

    if not parsed.scheme:
        raise ValueError(
            "Invalid connection string: missing scheme (expected 'ragnerock://...')"
        )
    if parsed.scheme != "ragnerock":
        raise ValueError(
            f"Invalid connection string: scheme must be 'ragnerock', got '{parsed.scheme}'"
        )
    if not parsed.hostname:
        raise ValueError("Invalid connection string: missing host")

    project_name = parsed.path.lstrip("/")
    if not project_name:
        raise ValueError(
            "Invalid connection string: missing project name (expected '.../{project_name}')"
        )

    dsn_token: str | None = None
    dsn_email: str | None = None
    dsn_password: str | None = None

    if parsed.username == _TOKEN_USERNAME_SENTINEL:
        if not parsed.password:
            raise ValueError(
                "Invalid connection string: empty API token "
                "(expected 'token:<api_token>@host')"
            )
        dsn_token = unquote(parsed.password)
    elif parsed.username:
        if not parsed.password:
            raise ValueError(
                "Invalid connection string: missing password "
                "(expected 'email:password@host')"
            )
        dsn_email = parsed.username
        dsn_password = parsed.password
    elif parsed.password:
        raise ValueError(
            "Invalid connection string: missing email (expected 'email:password@host')"
        )

    env_token = (os.environ.get(API_TOKEN_ENV_VAR) or "").strip() or None
    if dsn_email is not None and env_token is not None:
        raise ValueError(
            f"Conflicting credentials: connection string supplies email/password "
            f"but {API_TOKEN_ENV_VAR} is also set. Pick one."
        )

    auth_token = dsn_token if dsn_token is not None else env_token

    if auth_token is None and dsn_email is None:
        raise ValueError(
            "Invalid connection string: no authentication supplied. "
            f"Use 'email:password@host', 'token:<api_token>@host', or set "
            f"{API_TOKEN_ENV_VAR}."
        )

    hostname = parsed.hostname
    if hostname in ("localhost", "127.0.0.1"):
        scheme_out = "http"
    else:
        scheme_out = "https"

    if parsed.port is not None:
        host = f"{scheme_out}://{hostname}:{parsed.port}"
    else:
        host = f"{scheme_out}://{hostname}"

    if auth_token is not None:
        return Engine(host=host, project_name=project_name, auth_token=auth_token)
    return Engine(
        host=host,
        project_name=project_name,
        email=dsn_email,
        password=dsn_password,
    )
