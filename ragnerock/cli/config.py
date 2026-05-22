"""Resolve an :class:`~ragnerock.engine.Engine` from environment variables.

Two supported forms, tried in this order:

1. ``RAGNEROCK_CONNECTION_STRING`` — full ``ragnerock://...`` DSN.
2. Split vars: ``RAGNEROCK_HOST``, ``RAGNEROCK_PROJECT``, plus either
   ``RAGNEROCK_API_TOKEN`` (token mode) or both ``RAGNEROCK_EMAIL`` and
   ``RAGNEROCK_PASSWORD`` (email/password mode).

If neither form is complete, :func:`build_engine` raises :class:`ConfigError`.
"""

from __future__ import annotations

import os
from urllib.parse import quote, urlparse

from ragnerock.engine import Engine, create_engine

CONNECTION_STRING_VAR = "RAGNEROCK_CONNECTION_STRING"
HOST_VAR = "RAGNEROCK_HOST"
EMAIL_VAR = "RAGNEROCK_EMAIL"
PASSWORD_VAR = "RAGNEROCK_PASSWORD"
PROJECT_VAR = "RAGNEROCK_PROJECT"
API_TOKEN_VAR = "RAGNEROCK_API_TOKEN"


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


def _missing_message(
    host: str | None,
    project: str | None,
    email: str | None,
    password: str | None,
    token: str | None,
) -> str:
    """Compose a configuration error listing what's missing.

    Lists which split-var pieces aren't set, calling out both the
    email/password and token paths so the user knows either combination is
    acceptable.
    """
    missing: list[str] = []
    if not host:
        missing.append(HOST_VAR)
    if not project:
        missing.append(PROJECT_VAR)
    if not token:
        if not email:
            missing.append(EMAIL_VAR)
        if not password:
            missing.append(PASSWORD_VAR)
    return (
        "Missing Ragnerock configuration. Set "
        f"{CONNECTION_STRING_VAR}, or {HOST_VAR} + {PROJECT_VAR} plus either "
        f"{API_TOKEN_VAR} or both ({EMAIL_VAR}, {PASSWORD_VAR}). "
        f"Missing: {', '.join(missing)}."
    )


def _assemble_connection_string(
    host: str,
    project: str,
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
        project (str): Project name.
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

    return f"ragnerock://{userinfo}@{hostname}{port}/{project}"
