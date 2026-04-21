"""Resolve an :class:`~ragnerock.engine.Engine` from environment variables.

Two supported forms, tried in this order:

1. ``RAGNEROCK_CONNECTION_STRING`` — full ``ragnerock://...`` DSN.
2. Split vars: ``RAGNEROCK_HOST``, ``RAGNEROCK_EMAIL``, ``RAGNEROCK_PASSWORD``,
   ``RAGNEROCK_PROJECT``.

If neither form is complete, :func:`build_engine` raises :class:`ConfigError`.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from ragnerock.engine import Engine, create_engine

CONNECTION_STRING_VAR = "RAGNEROCK_CONNECTION_STRING"
HOST_VAR = "RAGNEROCK_HOST"
EMAIL_VAR = "RAGNEROCK_EMAIL"
PASSWORD_VAR = "RAGNEROCK_PASSWORD"
PROJECT_VAR = "RAGNEROCK_PROJECT"

_SPLIT_VARS = (HOST_VAR, EMAIL_VAR, PASSWORD_VAR, PROJECT_VAR)


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

    missing = [v for v in _SPLIT_VARS if not source.get(v)]
    if missing:
        raise ConfigError(
            "Missing Ragnerock configuration. Set "
            f"{CONNECTION_STRING_VAR}, or all of: {', '.join(_SPLIT_VARS)}. "
            f"Missing: {', '.join(missing)}."
        )

    host = source[HOST_VAR]
    email = source[EMAIL_VAR]
    password = source[PASSWORD_VAR]
    project = source[PROJECT_VAR]

    conn = _assemble_connection_string(host, email, password, project)
    try:
        return create_engine(conn)
    except ValueError as e:
        raise ConfigError(f"Invalid configuration from split vars: {e}") from e


def _assemble_connection_string(
    host: str, email: str, password: str, project: str
) -> str:
    """Build a ``ragnerock://`` DSN from split parts.

    Host may be given bare (``api.ragnerock.com``) or as a full URL
    (``https://api.ragnerock.com``). The scheme and any port are preserved.
    Values are not percent-encoded — :func:`urllib.parse.urlparse` returns
    userinfo fields unchanged, so encoding here would round-trip into the
    stored credentials and break authentication.
    """
    parsed = urlparse(host if "://" in host else f"https://{host}")
    hostname = parsed.hostname or host
    port = f":{parsed.port}" if parsed.port else ""

    return f"ragnerock://{email}:{password}@{hostname}{port}/{project}"
