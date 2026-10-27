"""The :class:`RagnerockClient` transport and its endpoint-section accessors."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx

from ragnerock.client._base import _drop_none, _parse_retry_after
from ragnerock.client.annotations import _AnnotationsSection
from ragnerock.client.auth import _AuthSection
from ragnerock.client.chunks import _ChunksSection
from ragnerock.client.documents import _DocumentsSection
from ragnerock.client.groups import _GroupsSection
from ragnerock.client.jobs import _JobsSection
from ragnerock.client.operators import _OperatorsSection
from ragnerock.client.pages import _PagesSection
from ragnerock.client.projects import _ProjectsSection
from ragnerock.client.queries import _QueriesSection
from ragnerock.client.workflows import _WorkflowsSection
from ragnerock.errors import raise_for_status

_DEFAULT_MAX_RATE_LIMIT_RETRIES = 5
_DEFAULT_RATE_LIMIT_BACKOFF = 1.0
_MAX_RATE_LIMIT_BACKOFF = 60.0
_DEFAULT_TIMEOUT = 30.0

# Sentinel distinguishing "use the client default timeout" from ``None``
# (which httpx interprets as "no timeout at all").
_DEFAULT: Any = object()


class RagnerockClient:
    """Low-level HTTP client for the Ragnerock API.

    Every endpoint is exposed as a method on a *section* property, e.g.
    ``client.documents.get(...)`` or ``client.workflows.set_schedule(...)``.
    Sections are cheap views over the same pooled connection.

    Args:
        host (str): Base URL of the API (e.g. ``https://api.ragnerock.com``).
        auth_token (str | None): Optional pre-existing bearer token. If
            ``None``, the caller must log in via ``client.auth.login(...)``
            before calling protected endpoints.
        max_rate_limit_retries (int): How many times to retry a request that
            comes back ``429 Too Many Requests`` before surfacing
            :class:`~ragnerock.errors.RateLimitError`. ``0`` disables retries.
        rate_limit_backoff (float): Base seconds to wait between rate-limit
            retries when the server omits ``Retry-After``. Doubles on each
            attempt, capped at 60s.
        timeout (float): Default per-request timeout in seconds. A few slow
            endpoints (provider validation, tool probes, GitOps apply) use a
            longer timeout of their own.
    """

    def __init__(
        self,
        *,
        host: str,
        auth_token: str | None = None,
        max_rate_limit_retries: int = _DEFAULT_MAX_RATE_LIMIT_RETRIES,
        rate_limit_backoff: float = _DEFAULT_RATE_LIMIT_BACKOFF,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """Build a client bound to ``host``.

        Args:
            host (str): Base URL of the API. A trailing slash is trimmed.
            auth_token (str | None): Optional pre-existing bearer token. When provided,
                it's set as the ``Authorization`` header immediately;
                otherwise the caller must call ``client.auth.login(...)``
                before any protected endpoint.
            max_rate_limit_retries (int): How many extra attempts to make on a
                429 response before raising. Defaults to 5.
            rate_limit_backoff (float): Initial backoff in seconds used when
                the server's ``Retry-After`` header is absent. Each retry
                doubles the wait, capped at 60s.
            timeout (float): Default per-request timeout in seconds.
        """
        self._host = host.rstrip("/")
        self._auth_token = auth_token
        self._client = httpx.Client(base_url=self._host, timeout=timeout)
        self._max_rate_limit_retries = max_rate_limit_retries
        self._rate_limit_backoff = rate_limit_backoff
        if auth_token is not None:
            self._client.headers["Authorization"] = f"Bearer {auth_token}"

    @property
    def host(self) -> str:
        """The base URL this client talks to, without a trailing slash.

        Returns:
            str: The API base URL.
        """
        return self._host

    @property
    def auth_token(self) -> str | None:
        """The bearer token currently attached to outgoing requests.

        Returns:
            str | None: The token, or ``None`` if the client is not
            authenticated.
        """
        return self._auth_token

    @auth_token.setter
    def auth_token(self, value: str | None) -> None:
        """Swap the bearer token and update the default Authorization header.

        Passing ``None`` clears the header, putting the client back in an
        unauthenticated state.

        Args:
            value (str | None): The new bearer token, or ``None`` to clear.
        """
        self._auth_token = value
        if value is None:
            self._client.headers.pop("Authorization", None)
        else:
            self._client.headers["Authorization"] = f"Bearer {value}"

    def _build_kwargs(
        self,
        *,
        params: dict[str, Any] | None,
        json_body: Any,
        data: dict[str, Any] | None,
        files: dict[str, Any] | None,
        headers: dict[str, str] | None,
        timeout: Any,
    ) -> dict[str, Any]:
        """Assemble the keyword arguments for an httpx request.

        Args:
            params (dict[str, Any] | None): Query-string parameters; ``None``
                values are dropped.
            json_body (Any): Request body to serialize as JSON.
            data (dict[str, Any] | None): Form fields; ``None`` values are dropped.
            files (dict[str, Any] | None): Multipart file parts.
            headers (dict[str, str] | None): Per-request headers, merged over
                (and able to override) the client defaults.
            timeout (Any): Per-request timeout, or :data:`_DEFAULT` for the
                client default.

        Returns:
            dict[str, Any]: Keyword arguments for :meth:`httpx.Client.request`.
        """
        kwargs: dict[str, Any] = {}
        if params is not None:
            kwargs["params"] = _drop_none(params)
        if json_body is not None:
            kwargs["json"] = json_body
        if data is not None:
            kwargs["data"] = _drop_none(data)
        if files is not None:
            kwargs["files"] = files
        if headers is not None:
            kwargs["headers"] = headers
        if timeout is not _DEFAULT:
            kwargs["timeout"] = timeout
        return kwargs

    def _rate_limit_wait(self, response: httpx.Response, attempt: int) -> float:
        """Return how long to sleep before retrying a 429.

        Args:
            response (httpx.Response): The 429 response.
            attempt (int): Zero-based retry attempt number.

        Returns:
            float: Seconds to wait — ``Retry-After`` when the server sent one,
            otherwise exponential backoff capped at 60s.
        """
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        if retry_after is not None:
            return retry_after
        return min(self._rate_limit_backoff * (2**attempt), _MAX_RATE_LIMIT_BACKOFF)

    @staticmethod
    def _raise_for_response(response: httpx.Response) -> None:
        """Raise the matching SDK error for a 4xx/5xx response.

        The response body must already be read.

        Args:
            response (httpx.Response): A completed response.

        Raises:
            RagnerockError: Or a subclass, for any status >= 400.
        """
        if response.status_code < 400:
            return
        retry_after = (
            _parse_retry_after(response.headers.get("Retry-After"))
            if response.status_code == 429
            else None
        )
        raise_for_status(response.status_code, response.text, retry_after=retry_after)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: Any = _DEFAULT,
    ) -> httpx.Response:
        """Issue an HTTP request and raise SDK errors on non-2xx responses.

        Centralizes ``None``-filtering for query strings and form bodies, and
        converts any 4xx/5xx into the matching
        :class:`~ragnerock.errors.RagnerockError` subclass via
        :func:`~ragnerock.errors.raise_for_status`.

        On ``429 Too Many Requests`` the call is automatically retried up to
        ``max_rate_limit_retries`` times. Each retry sleeps for the duration
        given by the server's ``Retry-After`` header when present, falling
        back to exponential backoff (``rate_limit_backoff`` doubled per
        attempt, capped at 60s). Only when the budget is exhausted does the
        429 surface as :class:`~ragnerock.errors.RateLimitError`.

        Args:
            method (str): HTTP verb (``GET``, ``POST``, ``PUT``, ``PATCH``, ``DELETE``).
            path (str): Path relative to the client's base URL.
            params (dict[str, Any] | None): Query-string parameters. ``None``
                values are dropped.
            json_body (Any): Request body to serialize as JSON.
            data (dict[str, Any] | None): Form-urlencoded or multipart body
                fields. ``None`` values are dropped.
            files (dict[str, Any] | None): Multipart file parts, passed
                straight through to httpx.
            headers (dict[str, str] | None): Extra headers for this request
                only. An ``Authorization`` entry replaces the client's token.
            timeout (Any): Timeout in seconds for this request, overriding the
                client default. ``None`` disables the timeout.

        Returns:
            httpx.Response: The underlying :class:`httpx.Response` for 2xx/3xx
            replies.

        Raises:
            RagnerockError: Or a subclass, for any response with status >= 400.
        """
        kwargs = self._build_kwargs(
            params=params,
            json_body=json_body,
            data=data,
            files=files,
            headers=headers,
            timeout=timeout,
        )
        attempt = 0
        while True:
            response = self._client.request(method, path, **kwargs)
            if response.status_code != 429 or attempt >= self._max_rate_limit_retries:
                break
            time.sleep(self._rate_limit_wait(response, attempt))
            attempt += 1

        self._raise_for_response(response)
        return response

    @contextmanager
    def _stream(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        timeout: Any = _DEFAULT,
    ) -> Iterator[httpx.Response]:
        """Open a streaming request, yielding the response once it is healthy.

        Rate-limit retries happen before anything is yielded, and a 4xx/5xx
        is read in full and raised as the matching SDK error, so the caller
        only ever iterates a successful body.

        Args:
            method (str): HTTP verb.
            path (str): Path relative to the client's base URL.
            params (dict[str, Any] | None): Query-string parameters. ``None``
                values are dropped.
            json_body (Any): Request body to serialize as JSON.
            headers (dict[str, str] | None): Extra headers for this request.
            timeout (Any): Timeout override; ``None`` disables it, which suits
                long-lived event streams.

        Yields:
            httpx.Response: The open streaming response.

        Raises:
            RagnerockError: Or a subclass, for any response with status >= 400.
        """
        kwargs = self._build_kwargs(
            params=params,
            json_body=json_body,
            data=None,
            files=None,
            headers=headers,
            timeout=timeout,
        )
        attempt = 0
        while True:
            with self._client.stream(method, path, **kwargs) as response:
                if (
                    response.status_code != 429
                    or attempt >= self._max_rate_limit_retries
                ):
                    if response.status_code >= 400:
                        response.read()
                        self._raise_for_response(response)
                    yield response
                    return
                response.read()
                wait = self._rate_limit_wait(response, attempt)
            time.sleep(wait)
            attempt += 1

    def close(self) -> None:
        """Close the underlying HTTP connection pool.

        Safe to call multiple times. Using the client as a context manager is
        usually preferable.
        """
        self._client.close()

    def __enter__(self) -> RagnerockClient:
        """Return ``self`` so the client can be used as a context manager."""
        return self

    def __exit__(self, *_: Any) -> None:
        """Close the underlying HTTP connection pool on context exit."""
        self.close()

    # -- data plane ---------------------------------------------------------

    @property
    def auth(self) -> _AuthSection:
        """Endpoints for authentication (``/api/auth/...``)."""
        return _AuthSection(self)

    @property
    def projects(self) -> _ProjectsSection:
        """Endpoints for project lookup (``/api/projects/...``)."""
        return _ProjectsSection(self)

    @property
    def documents(self) -> _DocumentsSection:
        """Endpoints for document CRUD, metadata, and content download."""
        return _DocumentsSection(self)

    @property
    def groups(self) -> _GroupsSection:
        """Endpoints for document-group CRUD scoped by project."""
        return _GroupsSection(self)

    @property
    def chunks(self) -> _ChunksSection:
        """Endpoints for chunk CRUD."""
        return _ChunksSection(self)

    @property
    def pages(self) -> _PagesSection:
        """Read-only endpoints for extracted document pages."""
        return _PagesSection(self)

    @property
    def annotations(self) -> _AnnotationsSection:
        """Endpoints for annotation CRUD, revisions, and scoped listing."""
        return _AnnotationsSection(self)

    @property
    def operators(self) -> _OperatorsSection:
        """Endpoints for operator (agent) CRUD."""
        return _OperatorsSection(self)

    @property
    def workflows(self) -> _WorkflowsSection:
        """Endpoints for workflows: CRUD, nodes, schedules, sinks, change requests."""
        return _WorkflowsSection(self)

    @property
    def jobs(self) -> _JobsSection:
        """Endpoints for job creation, inspection, and lifecycle actions."""
        return _JobsSection(self)

    @property
    def queries(self) -> _QueriesSection:
        """Endpoints for annotation SQL queries and saved queries."""
        return _QueriesSection(self)
