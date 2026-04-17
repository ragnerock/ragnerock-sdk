"""Engine and connection-string parsing."""

from __future__ import annotations

from urllib.parse import urlparse
from uuid import UUID

from ragnerock.client import RagnerockClient
from ragnerock.errors import AuthenticationError, NotFoundError, RagnerockError


class Engine:
    """Holds connection config and manages authentication.

    Created via :func:`create_engine` and passed to :class:`Session`.
    Authentication and project resolution are deferred until the first
    :class:`Session` opens, so constructing an engine never raises network
    errors.

    Attributes:
        host: Base API URL (e.g. ``https://api.ragnerock.com``).
        project_name: The project name parsed from the connection string.
    """

    def __init__(
        self,
        *,
        host: str,
        project_name: str,
        email: str,
        password: str,
    ) -> None:
        self.host = host
        self.project_name = project_name
        self._email = email
        self._password = password
        self._client: RagnerockClient | None = None
        self._project_id: UUID | None = None

    def _ensure_connected(self) -> None:
        """Authenticate and resolve the project ID on first use.

        Idempotent after the first call.
        """
        if self._client is not None and self._project_id is not None:
            return

        client = RagnerockClient(host=self.host)
        try:
            client.auth.login(email=self._email, password=self._password)
        except AuthenticationError:
            raise
        except RagnerockError as e:
            raise AuthenticationError(
                e.message,
                status_code=e.status_code,
                suggestion=e.suggestion,
                details=e.details,
            ) from e

        project_list = client.projects.get_by_name(self.project_name)
        if not project_list.projects:
            raise NotFoundError(f"Project '{self.project_name}' not found")

        self._project_id = project_list.projects[0].id
        self._client = client

    @property
    def client(self) -> RagnerockClient:
        """Authenticated low-level client. Connects on first access."""
        self._ensure_connected()
        assert self._client is not None
        return self._client

    @property
    def project_id(self) -> UUID:
        """Resolved project UUID. Connects on first access."""
        self._ensure_connected()
        assert self._project_id is not None
        return self._project_id


def create_engine(connection_string: str) -> Engine:
    """Create an :class:`Engine` from a connection string.

    Format::

        ragnerock://{email}:{password}@{host}[:{port}]/{project_name}

    Examples::

        create_engine("ragnerock://user@example.com:pass@api.ragnerock.com/my_project")
        create_engine("ragnerock://user@example.com:pass@localhost:8080/my_project")

    Args:
        connection_string: A Ragnerock connection string.

    Returns:
        An unconnected :class:`Engine` (no network I/O has happened yet).

    Raises:
        ValueError: If the connection string is malformed.
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

    if not parsed.username:
        raise ValueError(
            "Invalid connection string: missing email (expected 'email:password@host')"
        )
    if not parsed.password:
        raise ValueError(
            "Invalid connection string: missing password (expected 'email:password@host')"
        )
    if not parsed.hostname:
        raise ValueError("Invalid connection string: missing host")

    project_name = parsed.path.lstrip("/")
    if not project_name:
        raise ValueError(
            "Invalid connection string: missing project name (expected '.../{project_name}')"
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

    return Engine(
        host=host,
        project_name=project_name,
        email=parsed.username,
        password=parsed.password,
    )
