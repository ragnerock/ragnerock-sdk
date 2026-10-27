"""Agent tool endpoints (``/api/agent-tools/...``)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _body, _Section

PROBE_TIMEOUT_SECONDS = 150.0
"""Read timeout for calls that make the server contact a third-party server.

Creating or updating an MCP tool reads the server's tool list, and a route
test waits on the route's own timeout, so these calls need more headroom than
the client default.
"""


class AgentToolKind(StrEnum):
    """The kinds of agent tool."""

    SYSTEM = "system"
    """A built-in tool, present in every project. Only its switches can change."""

    MCP = "mcp"
    """A remote MCP server."""

    REST = "rest"
    """A REST API described by a base URL and routes."""


class McpTransport(StrEnum):
    """MCP transports. Only Streamable HTTP is accepted."""

    STREAMABLE_HTTP = "streamable_http"
    SSE = "sse"
    """The legacy SSE transport, which the server rejects with guidance."""


class McpAuthMode(StrEnum):
    """How an MCP tool authenticates to its server."""

    NONE = "none"
    """Send the configured headers and nothing else."""

    OAUTH = "oauth"
    """The server signs users in; see :meth:`_ToolsSection.oauth_start`."""


class McpConnector(StrEnum):
    """Catalog connectors an MCP tool can be created from.

    The catalog is defined by the server; :meth:`_ToolsSection.list_connectors`
    lists what a deployment offers, and any string it returns is accepted
    wherever a connector is.
    """

    LINEAR = "linear"
    PENDO = "pendo"
    GRAFANA = "grafana"
    DATADOG = "datadog"
    ATLASSIAN = "atlassian"
    GITHUB = "github"
    ASANA = "asana"
    SLACK = "slack"
    NOTION = "notion"
    GONG = "gong"


class McpOAuthStartOutcome(StrEnum):
    """What a sign-in start decided."""

    REDIRECT = "redirect"
    """Open ``authorization_url`` in a browser to sign in."""

    CREDENTIALS_REQUIRED = "credentials_required"
    """Register a client with the provider, then start again with its id."""


class AgentToolFunction(_ApiModel):
    """One LLM-callable function a tool exposes.

    Attributes:
        name (str): The full function name, ``<slug>__<segment>`` for MCP and
            REST tools.
        description (str | None): What the model is told the function does.
        source (str | None): ``"system"``, ``"mcp_discovered"``, or
            ``"rest_route"``.
        surfaces (list[str]): Where it can run: ``"notebook"``, ``"workflow"``.
        read_only_hint (bool | None): The MCP server's own read-only hint.
        destructive_hint (bool | None): The MCP server's own destructive hint.
        warnings (list[str]): Problems noticed when the function was read.
        parameters (dict[str, Any] | None): The function's parameter schema.
    """

    name: str
    description: str | None = None
    source: str | None = None
    surfaces: list[str] = []
    read_only_hint: bool | None = None
    destructive_hint: bool | None = None
    warnings: list[str] = []
    parameters: dict[str, Any] | None = None


class McpConnectorBinding(_ApiModel):
    """The catalog connector an MCP tool was created from, and its settings."""

    connector: str
    parameters: dict[str, str] = {}


class McpOAuthStatus(_ApiModel):
    """An MCP tool's sign-in connection. Never carries a token or secret.

    Attributes:
        status (str): ``"connected"``, ``"needs_reauth"``, or ``"disconnected"``.
        issuer (str | None): The authorization server signed in to.
        scopes (list[str]): Granted scopes.
        required_scopes (list[str]): Scopes the server asked for and lacks.
        authorized_at (datetime | None): When the sign-in completed.
        last_error (str | None): Why the connection last failed.
    """

    status: str
    issuer: str | None = None
    scopes: list[str] = []
    required_scopes: list[str] = []
    authorized_at: datetime | None = None
    last_error: str | None = None


class McpToolConfigResponse(_ApiModel):
    """An MCP tool's configuration. Secret header values are masked.

    Attributes:
        url (str | None): The server URL.
        transport (str | None): A :class:`McpTransport` value.
        auth (str | None): A :class:`McpAuthMode` value.
        headers (list[dict[str, Any]]): Configured headers: ``name``,
            ``is_secret``, ``value`` (non-secret only) and ``value_masked``
            (secret only).
        timeout_seconds (int | None): Per-call timeout override.
        discovered_at (datetime | None): When the tool list was last read.
        discovery_warnings (list[str]): Problems found reading the tool list.
        oauth (McpOAuthStatus | None): The sign-in connection, for an OAuth tool.
        connector (McpConnectorBinding | None): The catalog connector, for a
            tool created from one.
    """

    url: str | None = None
    transport: str | None = None
    auth: str | None = None
    headers: list[dict[str, Any]] = []
    timeout_seconds: int | None = None
    discovered_at: datetime | None = None
    discovery_warnings: list[str] = []
    oauth: McpOAuthStatus | None = None
    connector: McpConnectorBinding | None = None


class RestToolConfigResponse(_ApiModel):
    """A REST tool's configuration. Secret header values are masked.

    Attributes:
        base_url (str | None): Scheme, host, and path prefix.
        headers (list[dict[str, Any]]): Configured headers, as on
            :class:`McpToolConfigResponse`.
        routes (list[dict[str, Any]]): The routes, one per function.
    """

    base_url: str | None = None
    headers: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []


class AgentToolResponse(_ApiModel):
    """An agent tool: a built-in, MCP, or REST entry in a project's tool list.

    Attributes:
        id (UUID): The tool's id.
        project_id (UUID | None): Owning project.
        skill_id (UUID | None): The skill that owns the tool, or ``None`` for a
            shared project tool.
        kind (str | None): An :class:`AgentToolKind` value.
        name (str): Display name.
        slug (str | None): Immutable id and function-name prefix.
        description (str | None): What the tool is for.
        is_available (bool | None): Project-level master switch.
        notebook_enabled (bool | None): Whether the notebook agent may use it.
        system_key (str | None): The built-in tool's key; ``None`` otherwise.
        functions (list[AgentToolFunction]): The functions the tool exposes.
        mcp (McpToolConfigResponse | None): Configuration, for an MCP tool.
        rest (RestToolConfigResponse | None): Configuration, for a REST tool.
        operator_count (int | None): How many agents select the tool.
        last_error (str | None): The last discovery failure, in plain language.
        unavailable_reason (str | None): Why a listed tool still cannot run.
    """

    id: UUID
    project_id: UUID | None = None
    skill_id: UUID | None = None
    kind: str | None = None
    name: str
    slug: str | None = None
    description: str | None = None
    is_available: bool | None = None
    notebook_enabled: bool | None = None
    system_key: str | None = None
    functions: list[AgentToolFunction] = []
    mcp: McpToolConfigResponse | None = None
    rest: RestToolConfigResponse | None = None
    operator_count: int | None = None
    last_error: str | None = None
    unavailable_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentToolList(_ApiModel):
    """Paginated list response for agent tools.

    Attributes:
        tools (list[AgentToolResponse]): This page of tools.
        total (int): Total matching tools.
        skip (int): Offset of this page.
        limit (int): Page size.
        agent_tools_enabled (bool): ``False`` when the deployment has agent
            tools turned off: tools still list, but no agent uses them and
            edits are refused.
        oauth_available (bool): Whether MCP tools can sign in on this
            deployment.
    """

    tools: list[AgentToolResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 0
    agent_tools_enabled: bool = True
    oauth_available: bool = False


class AgentToolDeleteResponse(_ApiModel):
    """Result of an agent-tool deletion.

    Attributes:
        id (UUID): The deleted tool's id.
        operator_count (int): How many agents were unlinked from the tool.
    """

    id: UUID
    operator_count: int = 0


class McpConnectorInfo(_ApiModel):
    """One catalog connector.

    Attributes:
        connector (str): The connector's key, e.g. ``"datadog"``.
        name (str | None): Display name.
        description (str | None): What the connector is for.
        keywords (list[str]): Search keywords.
        docs_url (str | None): The vendor's documentation.
        parameters (list[dict[str, Any]]): Settings the connector takes
            (``key``, ``label``, ``kind``, and ``choices`` or ``suffix``).
        prerequisites (list[dict[str, Any]]): Steps needed before sign-in works.
        post_connect (dict[str, Any] | None): A step to take after signing in,
            such as installing an app on repositories.
        availability (str | None): ``"available"`` or why it is not:
            ``"disabled"``, ``"sign_in_not_configured"``,
            ``"app_not_configured"``.
        unavailable_reason (str | None): Explanation when not available.
    """

    connector: str
    name: str | None = None
    description: str | None = None
    keywords: list[str] = []
    docs_url: str | None = None
    parameters: list[dict[str, Any]] = []
    prerequisites: list[dict[str, Any]] = []
    post_connect: dict[str, Any] | None = None
    availability: str | None = None
    unavailable_reason: str | None = None


class McpConnectorList(_ApiModel):
    """The connector catalog, including connectors that are turned off."""

    connectors: list[McpConnectorInfo] = []


class McpDiscoveredFunction(_ApiModel):
    """One function an MCP server reported."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any] = {}
    warnings: list[str] = []


class McpDiscoverResponse(_ApiModel):
    """An MCP discovery result.

    Attributes:
        functions (list[McpDiscoveredFunction]): What the server reported.
        discovered_at (datetime | None): When it was read.
        warnings (list[str]): Problems found reading it.
        added (list[str]): Function names new since the saved list, when known.
        removed (list[str]): Function names gone since the saved list, when known.
        auth_required (bool): The server asked to be signed in to.
    """

    functions: list[McpDiscoveredFunction] = []
    discovered_at: datetime | None = None
    warnings: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    auth_required: bool = False


class McpOAuthStartResponse(_ApiModel):
    """What a sign-in start decided.

    Attributes:
        outcome (str): An :class:`McpOAuthStartOutcome` value.
        authorization_url (str | None): The URL to open, for ``"redirect"``.
        expires_at (datetime | None): When the pending sign-in lapses.
        issuer (str | None): The authorization server the decision was made
            against.
        redirect_uri (str | None): The callback to register, exactly, with the
            provider when credentials are required.
    """

    outcome: str
    authorization_url: str | None = None
    expires_at: datetime | None = None
    issuer: str | None = None
    redirect_uri: str | None = None


class McpParsedServer(_ApiModel):
    """One usable remote server found in a pasted config."""

    key: str
    url: str | None = None
    transport: str | None = None
    headers: list[dict[str, Any]] = []


class McpParseConfigResponse(_ApiModel):
    """The usable servers in a pasted config, and why the others were skipped."""

    servers: list[McpParsedServer] = []
    warnings: list[str] = []


class RestRouteTestResponse(_ApiModel):
    """The outcome of a REST route test. Header values are never echoed back.

    Attributes:
        ok (bool): Whether the call succeeded.
        status_code (int | None): The HTTP status, if a response came back.
        request_url (str | None): The bound URL, including the query string.
        duration_ms (int | None): Elapsed time.
        response_preview (str | None): The text the model would have seen.
        error (str | None): Why the call failed.
    """

    ok: bool = False
    status_code: int | None = None
    request_url: str | None = None
    duration_ms: int | None = None
    response_preview: str | None = None
    error: str | None = None


class _ToolsSection(_Section):
    """Agent tools: MCP servers, connectors, and REST APIs agents can call.

    Every project has built-in ``system`` tools plus the ``mcp`` and ``rest``
    tools you add. Attach them to LLM agents through the ``tool_ids`` argument
    of ``client.operators.create`` / ``client.operators.update``. A tool created
    with ``skill_id`` belongs to that skill instead and reaches only the agents
    that enable the skill.

    A tool's ``slug`` is its immutable id and the prefix of every function the
    model sees (``crm__get_customer``); it is derived from the name when
    omitted. Headers are dicts of the form ``{"name": ..., "value": ...,
    "is_secret": ...}``. Secret values are encrypted server-side and only ever
    come back masked; on an update or a probe with ``tool_id``, a secret header
    sent with ``"value": None`` keeps its stored value.
    """

    def list(
        self, project_id: UUID, *, skip: int = 0, limit: int = 100
    ) -> AgentToolList:
        """List a project's tools.

        Calls ``GET /api/agent-tools/``. Built-in tools come first, then the
        project's own tools by name. A web tool the workspace has turned off is
        left out.

        Args:
            project_id (UUID): Project whose tools to list.
            skip (int): Offset into the result set.
            limit (int): Maximum number of results per page.

        Returns:
            AgentToolList: A page of tools plus the total count.
        """
        response = self._parent._request(
            "GET",
            "/api/agent-tools/",
            params={"project_id": str(project_id), "skip": skip, "limit": limit},
        )
        return AgentToolList.model_validate(response.json())

    def get(self, tool_id: UUID) -> AgentToolResponse:
        """Fetch a single tool, with its secret headers masked.

        Calls ``GET /api/agent-tools/{tool_id}``.

        Args:
            tool_id (UUID): Tool to fetch.

        Returns:
            AgentToolResponse: The tool.

        Raises:
            NotFoundError: If no tool has that id.
        """
        response = self._parent._request("GET", f"/api/agent-tools/{tool_id}")
        return AgentToolResponse.model_validate(response.json())

    def create_mcp(
        self,
        *,
        project_id: UUID,
        name: str,
        description: str,
        url: str,
        skill_id: UUID | None = None,
        slug: str | None = None,
        transport: str = McpTransport.STREAMABLE_HTTP,
        auth: str = McpAuthMode.NONE,
        headers: list[dict[str, Any]] | None = None,
        timeout_seconds: int | None = None,
        is_available: bool = True,
        notebook_enabled: bool = False,
    ) -> AgentToolResponse:
        """Create an MCP tool from a remote server's URL.

        Calls ``POST /api/agent-tools/``. The server reads the tool list once,
        before saving, and pins it: agents see the list as it was at save time.
        A server that cannot be reached still produces a tool, with the failure
        on ``last_error``; :meth:`discover` retries it.

        Args:
            project_id (UUID): Owning project.
            name (str): Display name; unique (case-insensitive) among the
                project's tools.
            description (str): What the tool is for.
            url (str): The server's Streamable HTTP endpoint.
            skill_id (UUID | None): Nest the tool under this skill, so only
                agents that enable the skill can call it. Immutable afterwards.
            slug (str | None): Immutable id and function-name prefix; derived
                from ``name`` when omitted.
            transport (str): An :class:`McpTransport` value.
            auth (str): An :class:`McpAuthMode` value. With ``"oauth"`` the tool
                is created without a connection and reaches no agent until
                someone signs in through :meth:`oauth_start`.
            headers (list[dict[str, Any]] | None): Request headers, each with a
                value. Mark credentials ``"is_secret": True``. An OAuth tool may
                not set ``Authorization``.
            timeout_seconds (int | None): Per-call timeout override.
            is_available (bool): Project-level master switch.
            notebook_enabled (bool): Whether the notebook agent may use it.

        Returns:
            AgentToolResponse: The created tool, including the functions found.
            An OAuth tool has none until it is connected.
        """
        payload = _body(
            kind=AgentToolKind.MCP,
            source="custom",
            project_id=project_id,
            skill_id=skill_id,
            name=name,
            slug=slug,
            description=description,
            is_available=is_available,
            notebook_enabled=notebook_enabled,
            mcp=_body(
                url=url,
                transport=transport,
                headers=headers or [],
                timeout_seconds=timeout_seconds,
                auth=auth,
            ),
        )
        response = self._parent._request(
            "POST",
            "/api/agent-tools/",
            json_body=payload,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        return AgentToolResponse.model_validate(response.json())

    def list_connectors(self, project_id: UUID) -> McpConnectorList:
        """List the connector catalog available on this deployment.

        Calls ``GET /api/agent-tools/connectors``. Every connector is listed,
        with whether it can be connected here and, if not, why.

        Args:
            project_id (UUID): The project a tool would be added to.

        Returns:
            McpConnectorList: The catalog.
        """
        response = self._parent._request(
            "GET",
            "/api/agent-tools/connectors",
            params={"project_id": str(project_id)},
        )
        return McpConnectorList.model_validate(response.json())

    def create_connector(
        self,
        *,
        project_id: UUID,
        connector: str,
        skill_id: UUID | None = None,
        name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
        parameters: Mapping[str, str] | None = None,
        timeout_seconds: int | None = None,
        is_available: bool = True,
        notebook_enabled: bool = False,
    ) -> AgentToolResponse:
        """Add an MCP tool from the connector catalog.

        Calls ``POST /api/agent-tools/``. The server URL, headers, and sign-in
        come from the connector. The tool is created without a connection:
        call :meth:`oauth_start` and open the returned URL to sign in.

        When ``name`` or ``description`` is omitted, the connector's own is
        used, which costs one :meth:`list_connectors` call first.

        Args:
            project_id (UUID): Project to add the tool to.
            connector (str): An :class:`McpConnector` value, e.g. ``"github"``.
            skill_id (UUID | None): Nest the tool under this skill, so only
                agents that enable the skill can call it. Immutable afterwards.
            name (str | None): Display name; the connector's name when omitted.
                Names are unique in a project, so a second tool from the same
                connector needs its own.
            slug (str | None): Immutable id; derived from the name when omitted.
            description (str | None): What the tool is for; the connector's
                description when omitted.
            parameters (Mapping[str, str] | None): The connector's settings,
                e.g. ``{"site": "datadoghq.eu"}``. :meth:`list_connectors`
                lists each connector's settings and allowed values.
            timeout_seconds (int | None): Per-call timeout override.
            is_available (bool): Project-level master switch.
            notebook_enabled (bool): Whether the notebook agent may use it.

        Returns:
            AgentToolResponse: The created tool, not yet connected.

        Raises:
            ValueError: If ``name`` or ``description`` is omitted and the
                catalog has no such connector.
        """
        if name is None or description is None:
            entry = next(
                (
                    info
                    for info in self.list_connectors(project_id).connectors
                    if info.connector == connector
                ),
                None,
            )
            if entry is None:
                raise ValueError(
                    f"This deployment's catalog has no {str(connector)!r} "
                    "connector; pass name and description yourself."
                )
            name = entry.name if name is None else name
            description = entry.description if description is None else description
        payload = _body(
            kind=AgentToolKind.MCP,
            source="connector",
            project_id=project_id,
            skill_id=skill_id,
            name=name,
            slug=slug,
            description=description,
            is_available=is_available,
            notebook_enabled=notebook_enabled,
            connector={"connector": connector, "parameters": dict(parameters or {})},
            timeout_seconds=timeout_seconds,
        )
        response = self._parent._request(
            "POST",
            "/api/agent-tools/",
            json_body=payload,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        return AgentToolResponse.model_validate(response.json())

    def create_rest(
        self,
        *,
        project_id: UUID,
        name: str,
        description: str,
        base_url: str,
        routes: list[dict[str, Any]],
        skill_id: UUID | None = None,
        slug: str | None = None,
        headers: list[dict[str, Any]] | None = None,
        is_available: bool = True,
        notebook_enabled: bool = False,
    ) -> AgentToolResponse:
        """Create a REST tool from a base URL and its routes.

        Calls ``POST /api/agent-tools/``. Each route becomes one function named
        ``<slug>__<function_name>``. A route is a dict with ``function_name``,
        ``description``, ``method``, ``path`` (may contain ``{placeholders}``),
        optional ``params`` (``path`` and ``query`` parameter lists and a
        ``body_schema``), optional ``timeout_seconds``, and a required
        ``read_only`` flag stating whether calling it changes anything on the
        server.

        Args:
            project_id (UUID): Owning project.
            name (str): Display name; unique (case-insensitive) among the
                project's tools.
            description (str): What the API is for.
            base_url (str): Scheme, host, and any path prefix. No query string
                or credentials.
            routes (list[dict[str, Any]]): One or more routes.
            skill_id (UUID | None): Nest the tool under this skill, so only
                agents that enable the skill can call it. Immutable afterwards.
            slug (str | None): Immutable id and function-name prefix; derived
                from ``name`` when omitted.
            headers (list[dict[str, Any]] | None): Request headers, each with a
                value. Mark credentials ``"is_secret": True``.
            is_available (bool): Project-level master switch.
            notebook_enabled (bool): Whether the notebook agent may use it.

        Returns:
            AgentToolResponse: The created tool and its route functions.
        """
        payload = _body(
            kind=AgentToolKind.REST,
            project_id=project_id,
            skill_id=skill_id,
            name=name,
            slug=slug,
            description=description,
            is_available=is_available,
            notebook_enabled=notebook_enabled,
            rest={"base_url": base_url, "headers": headers or [], "routes": routes},
        )
        response = self._parent._request("POST", "/api/agent-tools/", json_body=payload)
        return AgentToolResponse.model_validate(response.json())

    def update(
        self,
        tool_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        is_available: bool | None = None,
        notebook_enabled: bool | None = None,
        mcp: dict[str, Any] | None = None,
        rest: dict[str, Any] | None = None,
        connector: dict[str, Any] | None = None,
    ) -> AgentToolResponse:
        """Partially update a tool; omitted fields are left unchanged.

        Calls ``PUT /api/agent-tools/{tool_id}``. Only the arguments passed as
        non-``None`` are sent. The kind, slug, and owning skill are immutable,
        and a built-in tool accepts only the two switches.

        The config dicts carry only the keys to change. In ``mcp`` those are
        ``url``, ``transport``, ``headers``, ``timeout_seconds`` (``None``
        clears the override) and ``auth``; in ``rest``, ``base_url``,
        ``headers`` and ``routes``; in ``connector``, ``parameters`` and
        ``timeout_seconds``. ``headers`` and ``routes`` replace the whole list:
        leave a header out to remove it, or send a secret one with
        ``"value": None`` to keep its stored value. Moving a tool to another
        scheme, host, or port while keeping a stored secret is refused.

        Changing an MCP server's URL, transport, or headers re-reads its tool
        list, so this call can take as long as :meth:`discover`.

        Args:
            tool_id (UUID): Tool to update.
            name (str | None): New display name.
            description (str | None): New description.
            is_available (bool | None): New availability.
            notebook_enabled (bool | None): New notebook exposure.
            mcp (dict[str, Any] | None): MCP configuration changes. Custom MCP
                tools only.
            rest (dict[str, Any] | None): REST configuration changes. REST tools
                only.
            connector (dict[str, Any] | None): Setting or timeout changes for a
                tool created from the catalog. Settings that move the tool to
                another account or site disconnect it.

        Returns:
            AgentToolResponse: The updated tool.
        """
        payload = _body(
            name=name,
            description=description,
            is_available=is_available,
            notebook_enabled=notebook_enabled,
            mcp=mcp,
            rest=rest,
            connector=connector,
        )
        response = self._parent._request(
            "PUT",
            f"/api/agent-tools/{tool_id}",
            json_body=payload,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        return AgentToolResponse.model_validate(response.json())

    def delete(self, tool_id: UUID) -> AgentToolDeleteResponse:
        """Delete a tool, unlinking it from every agent that selected it.

        Calls ``DELETE /api/agent-tools/{tool_id}``. Deployed endpoints whose
        workflow used the tool run without it from their next run on.

        Args:
            tool_id (UUID): Tool to delete.

        Returns:
            AgentToolDeleteResponse: The deleted id and how many agents were
            unlinked.
        """
        response = self._parent._request("DELETE", f"/api/agent-tools/{tool_id}")
        return AgentToolDeleteResponse.model_validate(response.json())

    def discover(self, tool_id: UUID) -> McpDiscoverResponse:
        """Re-read a saved MCP server's tools and pin the new list.

        Calls ``POST /api/agent-tools/{tool_id}/discover``. The response names
        what was ``added`` and ``removed``, since a refresh changes what every
        linked agent sees. A failure keeps the previous list and says why.

        Args:
            tool_id (UUID): MCP tool to refresh.

        Returns:
            McpDiscoverResponse: The pinned functions and the diff.
        """
        response = self._parent._request(
            "POST",
            f"/api/agent-tools/{tool_id}/discover",
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        return McpDiscoverResponse.model_validate(response.json())

    def oauth_start(
        self,
        tool_id: UUID,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> McpOAuthStartResponse:
        """Begin a sign-in for an MCP server that authenticates its users.

        Calls ``POST /api/agent-tools/{tool_id}/oauth/start``. There are two
        outcomes:

        - ``"redirect"``: open ``authorization_url`` in a browser. It is good
          for one attempt and expires. The provider returns to Ragnerock,
          which completes the sign-in; there is no headless path.
        - ``"credentials_required"``: the provider does not register clients
          automatically. Create one in its developer console with
          ``redirect_uri`` registered exactly as returned, then call this again
          with its ``client_id`` (and ``client_secret``, if it issued one).
          They are stored encrypted and reused for later sign-ins.

        Args:
            tool_id (UUID): MCP tool to connect; its ``auth`` must be ``"oauth"``.
            client_id (str | None): A client id from the provider's console.
            client_secret (str | None): Its secret, for confidential clients.

        Returns:
            McpOAuthStartResponse: The outcome and the URL to open or the
            redirect URI to register.
        """
        response = self._parent._request(
            "POST",
            f"/api/agent-tools/{tool_id}/oauth/start",
            json_body=_body(client_id=client_id, client_secret=client_secret),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        return McpOAuthStartResponse.model_validate(response.json())

    def oauth_disconnect(self, tool_id: UUID) -> AgentToolResponse:
        """Discard an MCP tool's sign-in, revoking it at the provider first.

        Calls ``DELETE /api/agent-tools/{tool_id}/oauth``. The discovered
        functions stay on the tool, so connecting again puts it straight back
        to work; meanwhile no agent uses it.

        Args:
            tool_id (UUID): The connected MCP tool.

        Returns:
            AgentToolResponse: The tool, now disconnected.
        """
        response = self._parent._request(
            "DELETE",
            f"/api/agent-tools/{tool_id}/oauth",
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        return AgentToolResponse.model_validate(response.json())

    def parse_mcp_config(
        self, config: dict[str, Any], *, project_id: UUID
    ) -> McpParseConfigResponse:
        """Normalize a pasted ``mcpServers`` config into usable servers.

        Calls ``POST /api/agent-tools/mcp/parse-config``. Nothing is created and
        no server is contacted. Local (stdio) entries, the legacy SSE
        transport, and values still holding a ``${VAR}`` placeholder are
        skipped with a warning naming each one.

        Args:
            config (dict[str, Any]): The parsed config object, in the
                ``mcpServers``, ``servers``, or bare-mapping form.
            project_id (UUID): The project the servers would be added to.

        Returns:
            McpParseConfigResponse: The usable servers and the warnings for
            everything skipped.
        """
        response = self._parent._request(
            "POST",
            "/api/agent-tools/mcp/parse-config",
            json_body=_body(project_id=project_id, config=config),
        )
        return McpParseConfigResponse.model_validate(response.json())

    def preview_mcp_discovery(
        self,
        *,
        project_id: UUID,
        slug: str,
        mcp: dict[str, Any],
        tool_id: UUID | None = None,
    ) -> McpDiscoverResponse:
        """Read an MCP server's tools without saving anything.

        Calls ``POST /api/agent-tools/mcp/discover``. Pass ``tool_id`` to
        resolve secret headers sent with ``"value": None`` against that tool's
        stored values (only while the URL keeps the saved tool's scheme, host,
        and port) and to get the ``added`` / ``removed`` diff.

        Args:
            project_id (UUID): The project the tool would belong to.
            slug (str): The slug the functions would be named under.
            mcp (dict[str, Any]): The server configuration, as on
                :meth:`create_mcp`: ``url``, ``auth``, and optionally
                ``transport``, ``headers`` and ``timeout_seconds``.
            tool_id (UUID | None): An existing tool to resolve kept secrets
                against and to diff the result against.

        Returns:
            McpDiscoverResponse: What the server reported.
        """
        response = self._parent._request(
            "POST",
            "/api/agent-tools/mcp/discover",
            json_body=_body(project_id=project_id, tool_id=tool_id, slug=slug, mcp=mcp),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        return McpDiscoverResponse.model_validate(response.json())

    def test_rest_route(
        self,
        *,
        project_id: UUID,
        base_url: str,
        route: dict[str, Any],
        arguments: dict[str, Any],
        headers: list[dict[str, Any]] | None = None,
        tool_id: UUID | None = None,
    ) -> RestRouteTestResponse:
        """Call one REST route against its server and report what came back.

        Calls ``POST /api/agent-tools/rest/test``. The preview is the text the
        model would have seen. Header values are never echoed back. Pass
        ``tool_id`` to resolve secret headers sent with ``"value": None``
        against that tool's stored values, which works only while the base URL
        keeps the saved tool's scheme, host, and port.

        Args:
            project_id (UUID): The project the tool belongs to.
            base_url (str): The server's base URL.
            route (dict[str, Any]): The route to call, as on :meth:`create_rest`.
            arguments (dict[str, Any]): The flat arguments the model would pass:
                path, query, and body values in one mapping.
            headers (list[dict[str, Any]] | None): Headers to send.
            tool_id (UUID | None): An existing tool to resolve kept secrets
                against.

        Returns:
            RestRouteTestResponse: The status, bound URL, elapsed time, and
            response preview.
        """
        payload = _body(
            project_id=project_id,
            tool_id=tool_id,
            base_url=base_url,
            headers=headers or [],
            route=route,
            arguments=arguments,
        )
        response = self._parent._request(
            "POST",
            "/api/agent-tools/rest/test",
            json_body=payload,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        return RestRouteTestResponse.model_validate(response.json())
