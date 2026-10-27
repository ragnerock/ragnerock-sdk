"""Resolve an :class:`~ragnerock.engine.Engine` from environment variables.

Two supported forms, tried in this order:

1. ``RAGNEROCK_CONNECTION_STRING`` — full ``ragnerock://...`` DSN.
2. Split vars: ``RAGNEROCK_HOST``, ``RAGNEROCK_PROJECT``, plus either
   ``RAGNEROCK_API_TOKEN`` (token mode) or both ``RAGNEROCK_EMAIL`` and
   ``RAGNEROCK_PASSWORD`` (email/password mode).

If neither form is complete, :func:`build_engine` raises :class:`ConfigError`.

:func:`build_client` reads the same variables but does not require a project,
for account-level commands such as ``ragnerock apply``.
"""

from __future__ import annotations

import os
from urllib.parse import quote, urlparse

from ragnerock.client import RagnerockClient
from ragnerock.engine import Engine, create_client, create_engine

CONNECTION_STRING_VAR = "RAGNEROCK_CONNECTION_STRING"
HOST_VAR = "RAGNEROCK_HOST"
EMAIL_VAR = "RAGNEROCK_EMAIL"
PASSWORD_VAR = "RAGNEROCK_PASSWORD"
PROJECT_VAR = "RAGNEROCK_PROJECT"
API_TOKEN_VAR = "RAGNEROCK_API_TOKEN"
SEALING_PUBLIC_KEY_VAR = "RAGNEROCK_SEALING_PUBLIC_KEY"


class ConfigError(Exception):
    """Raised when required environment variables are missing or malformed."""


def build_engine(env: dict[str, str] | None = None) -> Engine:
    """Create an :class:`Engine` from environment variables.

    Args:
        env (dict[str, str] | None): Optional override for the environment
            (primarily for tests). Defaults to :data:`os.environ`.

    Returns:
        Engine: An unconnected engine ready to open a session.

    Raises:
        ConfigError: If no configuration form is complete, or the connection
            string is malformed.
    """
    source = env if env is not None else os.environ

    conn = source.get(CONNECTION_STRING_VAR)
    if conn:
        try:
            return create_engine(conn)
        except ValueError as e:
            raise ConfigError(f"{CONNECTION_STRING_VAR} is malformed: {e}") from e

    host = source.get(HOST_VAR)
    project = source.get(PROJECT_VAR)
    email = source.get(EMAIL_VAR)
    password = source.get(PASSWORD_VAR)
    token = (source.get(API_TOKEN_VAR) or "").strip() or None

    if host and project and token:
        conn = _assemble_connection_string(host, project, token=token)
    elif host and project and email and password:
        conn = _assemble_connection_string(
            host, project, email=email, password=password
        )
    else:
        raise ConfigError(_missing_message(host, project, email, password, token))

    try:
        return create_engine(conn)
    except ValueError as e:
        raise ConfigError(f"Invalid configuration from split vars: {e}") from e


def build_client(env: dict[str, str] | None = None) -> RagnerockClient:
    """Create an authenticated :class:`RagnerockClient` from environment variables.

    Like :func:`build_engine`, but ``RAGNEROCK_PROJECT`` (and the project path
    of ``RAGNEROCK_CONNECTION_STRING``) is optional. With email/password
    credentials this logs in immediately.

    Args:
        env (dict[str, str] | None): Optional override for the environment
            (primarily for tests). Defaults to :data:`os.environ`.

    Returns:
        RagnerockClient: A client with its bearer token set.

    Raises:
        ConfigError: If no configuration form is complete, or the connection
            string is malformed.
        AuthenticationError: If an email/password login is rejected.
    """
    source = env if env is not None else os.environ

    conn = source.get(CONNECTION_STRING_VAR)
    if conn:
        try:
            return create_client(conn)
        except ValueError as e:
            raise ConfigError(f"{CONNECTION_STRING_VAR} is malformed: {e}") from e

    host = source.get(HOST_VAR)
    project = source.get(PROJECT_VAR) or None
    email = source.get(EMAIL_VAR)
    password = source.get(PASSWORD_VAR)
    token = (source.get(API_TOKEN_VAR) or "").strip() or None

    if host and token:
        conn = _assemble_connection_string(host, project, token=token)
    elif host and email and password:
        conn = _assemble_connection_string(
            host, project, email=email, password=password
        )
    else:
        raise ConfigError(
            _missing_message(
                host, project, email, password, token, require_project=False
            )
        )

    try:
        return create_client(conn)
    except ValueError as e:
        raise ConfigError(f"Invalid configuration from split vars: {e}") from e


def _missing_message(
    host: str | None,
    project: str | None,
    email: str | None,
    password: str | None,
    token: str | None,
    *,
    require_project: bool = True,
) -> str:
    """Compose a configuration error listing what's missing.

    Lists which split-var pieces aren't set, calling out both the
    email/password and token paths so the user knows either combination is
    acceptable.
    """
    missing: list[str] = []
    if not host:
        missing.append(HOST_VAR)
    if require_project and not project:
        missing.append(PROJECT_VAR)
    if not token:
        if not email:
            missing.append(EMAIL_VAR)
        if not password:
            missing.append(PASSWORD_VAR)
    required = f"{HOST_VAR} + {PROJECT_VAR}" if require_project else HOST_VAR
    return (
        "Missing Ragnerock configuration. Set "
        f"{CONNECTION_STRING_VAR}, or {required} plus either "
        f"{API_TOKEN_VAR} or both ({EMAIL_VAR}, {PASSWORD_VAR}). "
        f"Missing: {', '.join(missing)}."
    )


def _assemble_connection_string(
    host: str,
    project: str | None,
    *,
    email: str | None = None,
    password: str | None = None,
    token: str | None = None,
) -> str:
    """Build a ``ragnerock://`` DSN from split environment parts.

    Host may be given bare (``api.ragnerock.com``) or as a full URL
    (``https://api.ragnerock.com``). The scheme is dropped — the DSN form
    owns scheme selection — but any explicit port is preserved. Email and
    password are not percent-encoded: :func:`urllib.parse.urlparse` returns
    userinfo fields unchanged, so encoding here would round-trip into the
    stored credentials and break authentication. Tokens are percent-encoded
    because they may contain ``+``, ``=``, and ``/`` that survive
    ``urlparse`` decoding back to safe values.

    Exactly one of ``token`` or the (``email``, ``password``) pair must be
    supplied. Pre-validated by :func:`build_engine`; this helper does not
    re-check.

    Args:
        host (str): Hostname or full URL for the API.
        project (str | None): Project name, or ``None`` to omit the path.
        email (str | None): Account email (email/password mode).
        password (str | None): Account password (email/password mode).
        token (str | None): API token (token mode).

    Returns:
        str: A connection string accepted by :func:`create_engine`.
    """
    parsed = urlparse(host if "://" in host else f"https://{host}")
    hostname = parsed.hostname or host
    port = f":{parsed.port}" if parsed.port else ""

    if token is not None:
        userinfo = f"token:{quote(token, safe='')}"
    else:
        userinfo = f"{email}:{password}"

    path = f"/{project}" if project else ""
    return f"ragnerock://{userinfo}@{hostname}{port}{path}"
