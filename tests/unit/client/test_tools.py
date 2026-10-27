"""Tests for the agent tools section (``client.tools``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from ragnerock.client import RagnerockClient
from ragnerock.client.tools import (
    PROBE_TIMEOUT_SECONDS,
    AgentToolDeleteResponse,
    AgentToolKind,
    AgentToolList,
    AgentToolResponse,
    McpAuthMode,
    McpConnector,
    McpConnectorList,
    McpDiscoverResponse,
    McpOAuthStartOutcome,
    McpOAuthStartResponse,
    McpParseConfigResponse,
    McpTransport,
    RestRouteTestResponse,
)
from tests.unit.client.conftest import (
    PROJECT_ID,
    last_json,
    last_params,
    last_request,
    url,
)

TOOL_ID = "00000000-0000-0000-0000-0000000000b1"
SKILL_ID = "00000000-0000-0000-0000-0000000000a1"
NOW = "2026-09-04T00:00:00Z"


def _route(**overrides: Any) -> dict[str, Any]:
    """Build a REST route dict."""
    route: dict[str, Any] = {
        "function_name": "get_customer",
        "description": "Fetch one customer by id.",
        "method": "GET",
        "path": "/customers/{customer_id}",
        "read_only": True,
        "params": {"path": [{"name": "customer_id", "description": "CRM id"}]},
    }
    route.update(overrides)
    return route


def _tool(**overrides: Any) -> dict[str, Any]:
    """Build an agent tool payload as the server returns it."""
    payload: dict[str, Any] = {
        "id": TOOL_ID,
        "project_id": PROJECT_ID,
        "skill_id": None,
        "kind": "rest",
        "name": "CRM API",
        "slug": "crm",
        "description": "Customer records",
        "is_available": True,
        "notebook_enabled": False,
        "system_key": None,
        "surfaces": ["notebook", "workflow"],
        "functions": [
            {
                "name": "crm__get_customer",
                "description": "Fetch one customer by id.",
                "source": "rest_route",
                "surfaces": ["notebook", "workflow"],
            }
        ],
        "operator_count": 0,
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload.update(overrides)
    return payload


def _mcp_config(**overrides: Any) -> dict[str, Any]:
    """Build an MCP config response block."""
    config: dict[str, Any] = {
        "url": "https://mcp.example.com/mcp",
        "transport": "streamable_http",
        "headers": [],
        "timeout_seconds": None,
        "discovered_at": NOW,
        "discovery_warnings": [],
        "auth": "none",
    }
    config.update(overrides)
    return config


_CATALOG: dict[str, Any] = {
    "connectors": [
        {
            "connector": "datadog",
            "name": "Datadog",
            "description": "Monitors, logs, metrics, and incidents in Datadog.",
            "keywords": ["monitoring"],
            "docs_url": "https://docs.datadoghq.com/mcp_server/",
            "parameters": [
                {
                    "key": "site",
                    "label": "site",
                    "kind": "choice",
                    "choices": [{"value": "datadoghq.eu", "label": "EU"}],
                }
            ],
            "prerequisites": [
                {
                    "text": "A Datadog administrator must add this address.",
                    "copy_value": "https://app.example.com/oauth/callback",
                    "requires_admin": True,
                }
            ],
            "post_connect": None,
            "availability": "available",
            "unavailable_reason": None,
        }
    ]
}


def _connector_tool() -> dict[str, Any]:
    return _tool(
        kind="mcp",
        slug="datadog",
        name="Datadog",
        functions=[],
        mcp=_mcp_config(
            url="https://mcp.datadoghq.eu/v1/mcp",
            discovered_at=None,
            auth="oauth",
            oauth={"status": "disconnected", "scopes": [], "required_scopes": []},
            connector={"connector": "datadog", "parameters": {"site": "datadoghq.eu"}},
        ),
    )


def _read_timeout(httpx_mock) -> float:
    """Return the read timeout the last request was sent with."""
    return last_request(httpx_mock).extensions["timeout"]["read"]


class TestList:
    def test_sends_project_and_paging(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/agent-tools/?project_id={PROJECT_ID}&skip=0&limit=50"),
            json={
                "tools": [_tool()],
                "total": 1,
                "skip": 0,
                "limit": 50,
                "agent_tools_enabled": True,
                "oauth_available": True,
            },
        )

        result = client.tools.list(UUID(PROJECT_ID), limit=50)

        assert last_params(httpx_mock) == {
            "project_id": PROJECT_ID,
            "skip": "0",
            "limit": "50",
        }
        assert last_request(httpx_mock).headers["Authorization"] == "Bearer rgnk_test"
        assert isinstance(result, AgentToolList)
        assert result.total == 1
        assert result.oauth_available is True
        assert result.tools[0].slug == "crm"
        assert result.tools[0].kind == AgentToolKind.REST
        assert result.tools[0].functions[0].name == "crm__get_customer"


class TestGet:
    def test_parses_masked_headers(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/agent-tools/{TOOL_ID}"),
            json=_tool(
                rest={
                    "base_url": "https://api.example.com/v1",
                    "headers": [
                        {
                            "name": "Authorization",
                            "is_secret": True,
                            "value": None,
                            "value_masked": "••3f9a",
                        }
                    ],
                    "routes": [_route()],
                }
            ),
        )

        result = client.tools.get(UUID(TOOL_ID))

        assert isinstance(result, AgentToolResponse)
        assert result.rest is not None
        assert result.rest.base_url == "https://api.example.com/v1"
        assert result.rest.headers[0]["value"] is None
        assert result.rest.routes[0]["function_name"] == "get_customer"


class TestCreateMcp:
    def test_body_and_probe_timeout(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="POST",
            url=url("/api/agent-tools/"),
            json=_tool(
                kind="mcp",
                slug="linear",
                name="Linear",
                mcp=_mcp_config(timeout_seconds=45),
            ),
        )

        result = client.tools.create_mcp(
            project_id=UUID(PROJECT_ID),
            name="Linear",
            description="Issue tracker",
            url="https://mcp.example.com/mcp",
            slug="linear",
            timeout_seconds=45,
            notebook_enabled=True,
        )

        assert last_json(httpx_mock) == {
            "kind": "mcp",
            # A server described here, as opposed to a catalog connector.
            "source": "custom",
            "project_id": PROJECT_ID,
            "name": "Linear",
            "slug": "linear",
            "description": "Issue tracker",
            "is_available": True,
            "notebook_enabled": True,
            "mcp": {
                "url": "https://mcp.example.com/mcp",
                "transport": "streamable_http",
                "headers": [],
                "timeout_seconds": 45,
                # Stated explicitly; the server never infers the mode.
                "auth": "none",
            },
        }
        # Creating an MCP tool reads the server's tool list server-side.
        assert _read_timeout(httpx_mock) == PROBE_TIMEOUT_SECONDS
        assert result.mcp is not None
        assert result.mcp.transport == McpTransport.STREAMABLE_HTTP
        assert result.mcp.timeout_seconds == 45

    def test_secret_headers_and_skill(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="POST",
            url=url("/api/agent-tools/"),
            json=_tool(kind="mcp", skill_id=SKILL_ID, mcp=_mcp_config()),
        )

        result = client.tools.create_mcp(
            project_id=UUID(PROJECT_ID),
            name="Linear",
            description="Issue tracker",
            url="https://mcp.example.com/mcp",
            skill_id=UUID(SKILL_ID),
            headers=[{"name": "X-Api-Key", "value": "k", "is_secret": True}],
        )

        body = last_json(httpx_mock)
        assert body["skill_id"] == SKILL_ID
        assert "slug" not in body
        assert body["mcp"]["headers"] == [
            {"name": "X-Api-Key", "value": "k", "is_secret": True}
        ]
        assert "timeout_seconds" not in body["mcp"]
        assert result.skill_id == UUID(SKILL_ID)

    def test_can_ask_for_a_sign_in(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="POST",
            url=url("/api/agent-tools/"),
            json=_tool(
                kind="mcp",
                functions=[],
                mcp=_mcp_config(
                    discovered_at=None,
                    auth="oauth",
                    oauth={
                        "status": "disconnected",
                        "scopes": [],
                        "required_scopes": [],
                    },
                ),
            ),
        )

        result = client.tools.create_mcp(
            project_id=UUID(PROJECT_ID),
            name="Linear",
            description="Issue tracker",
            url="https://mcp.example.com/mcp",
            auth=McpAuthMode.OAUTH,
        )

        assert last_json(httpx_mock)["mcp"]["auth"] == "oauth"
        assert result.mcp is not None
        assert result.mcp.auth == McpAuthMode.OAUTH
        # Nobody has signed in yet, so the tool reaches no agent.
        assert result.mcp.oauth is not None
        assert result.mcp.oauth.status == "disconnected"
        assert result.functions == []


class TestConnectors:
    def test_the_catalog_parses(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/agent-tools/connectors?project_id={PROJECT_ID}"),
            json=_CATALOG,
        )

        catalog = client.tools.list_connectors(UUID(PROJECT_ID))

        assert last_params(httpx_mock) == {"project_id": PROJECT_ID}
        assert isinstance(catalog, McpConnectorList)
        entry = catalog.connectors[0]
        assert entry.connector == McpConnector.DATADOG
        assert entry.availability == "available"
        assert entry.prerequisites[0]["requires_admin"] is True

    def test_create_fills_name_and_description_from_the_catalog(
        self, httpx_mock, client: RagnerockClient
    ):
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/agent-tools/connectors?project_id={PROJECT_ID}"),
            json=_CATALOG,
        )
        httpx_mock.add_response(
            method="POST", url=url("/api/agent-tools/"), json=_connector_tool()
        )

        result = client.tools.create_connector(
            project_id=UUID(PROJECT_ID),
            connector=McpConnector.DATADOG,
            parameters={"site": "datadoghq.eu"},
        )

        assert [r.method for r in httpx_mock.get_requests()] == ["GET", "POST"]
        # Nothing about the server is sent: the connector decides it.
        assert last_json(httpx_mock) == {
            "kind": "mcp",
            "source": "connector",
            "project_id": PROJECT_ID,
            "name": "Datadog",
            "description": "Monitors, logs, metrics, and incidents in Datadog.",
            "is_available": True,
            "notebook_enabled": False,
            "connector": {
                "connector": "datadog",
                "parameters": {"site": "datadoghq.eu"},
            },
        }
        assert _read_timeout(httpx_mock) == PROBE_TIMEOUT_SECONDS
        assert result.mcp is not None
        assert result.mcp.connector is not None
        assert result.mcp.connector.connector == McpConnector.DATADOG
        assert result.mcp.connector.parameters == {"site": "datadoghq.eu"}

    def test_create_skips_the_catalog_when_named(
        self, httpx_mock, client: RagnerockClient
    ):
        httpx_mock.add_response(
            method="POST", url=url("/api/agent-tools/"), json=_connector_tool()
        )

        client.tools.create_connector(
            project_id=UUID(PROJECT_ID),
            connector="datadog",
            skill_id=UUID(SKILL_ID),
            name="EU Datadog",
            description="Production monitors.",
            timeout_seconds=30,
        )

        assert len(httpx_mock.get_requests()) == 1
        body = last_json(httpx_mock)
        assert body["skill_id"] == SKILL_ID
        assert body["name"] == "EU Datadog"
        assert body["timeout_seconds"] == 30
        # A connector without settings still sends an empty mapping.
        assert body["connector"] == {"connector": "datadog", "parameters": {}}

    def test_create_refuses_a_connector_the_catalog_lacks(
        self, httpx_mock, client: RagnerockClient
    ):
        httpx_mock.add_response(
            method="GET",
            url=url(f"/api/agent-tools/connectors?project_id={PROJECT_ID}"),
            json=_CATALOG,
        )

        with pytest.raises(ValueError, match="no 'gong' connector"):
            client.tools.create_connector(
                project_id=UUID(PROJECT_ID), connector=McpConnector.GONG
            )

        assert [r.method for r in httpx_mock.get_requests()] == ["GET"]


class TestCreateRest:
    def test_body_carries_the_kind_and_routes(
        self, httpx_mock, client: RagnerockClient
    ):
        httpx_mock.add_response(
            method="POST", url=url("/api/agent-tools/"), json=_tool()
        )

        result = client.tools.create_rest(
            project_id=UUID(PROJECT_ID),
            name="CRM API",
            description="Customer records",
            base_url="https://api.example.com/v1",
            routes=[_route()],
            headers=[{"name": "Authorization", "value": "Bearer x", "is_secret": True}],
        )

        body = last_json(httpx_mock)
        assert body["kind"] == "rest"
        assert body["project_id"] == PROJECT_ID
        # Omitted: the server derives it from the name.
        assert "slug" not in body
        assert body["notebook_enabled"] is False
        assert body["rest"] == {
            "base_url": "https://api.example.com/v1",
            "headers": [
                {"name": "Authorization", "value": "Bearer x", "is_secret": True}
            ],
            "routes": [_route()],
        }
        assert result.functions[0].source == "rest_route"

    def test_uses_the_default_timeout(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="POST", url=url("/api/agent-tools/"), json=_tool()
        )

        client.tools.create_rest(
            project_id=UUID(PROJECT_ID),
            name="CRM API",
            description="Customer records",
            base_url="https://api.example.com/v1",
            routes=[_route()],
        )

        assert last_json(httpx_mock)["rest"]["headers"] == []
        assert _read_timeout(httpx_mock) < PROBE_TIMEOUT_SECONDS


class TestUpdate:
    def _body(self, httpx_mock, client: RagnerockClient, **kwargs: Any) -> Any:
        httpx_mock.add_response(
            method="PUT", url=url(f"/api/agent-tools/{TOOL_ID}"), json=_tool()
        )
        client.tools.update(UUID(TOOL_ID), **kwargs)
        assert _read_timeout(httpx_mock) == PROBE_TIMEOUT_SECONDS
        return last_json(httpx_mock)

    def test_omitted_fields_are_absent(self, httpx_mock, client: RagnerockClient):
        """A null for any field would be refused by the server."""
        assert self._body(httpx_mock, client, name="Renamed") == {"name": "Renamed"}

    def test_false_switches_are_sent(self, httpx_mock, client: RagnerockClient):
        body = self._body(
            httpx_mock, client, is_available=False, notebook_enabled=False
        )
        assert body == {"is_available": False, "notebook_enabled": False}

    def test_config_block_is_sent_as_given(self, httpx_mock, client: RagnerockClient):
        body = self._body(
            httpx_mock,
            client,
            rest={"base_url": "https://api.example.com/v2", "routes": [_route()]},
        )
        assert list(body) == ["rest"]
        assert body["rest"]["base_url"] == "https://api.example.com/v2"
        assert body["rest"]["routes"][0]["read_only"] is True
        # An omitted header list leaves the stored headers alone.
        assert "headers" not in body["rest"]

    def test_kept_secret_header_sends_a_null_value(
        self, httpx_mock, client: RagnerockClient
    ):
        """An explicit ``"value": None`` keeps the stored secret."""
        body = self._body(
            httpx_mock,
            client,
            mcp={
                "headers": [{"name": "Authorization", "value": None, "is_secret": True}]
            },
        )
        assert body == {
            "mcp": {
                "headers": [{"name": "Authorization", "value": None, "is_secret": True}]
            }
        }

    def test_null_timeout_clears_the_override(
        self, httpx_mock, client: RagnerockClient
    ):
        body = self._body(httpx_mock, client, mcp={"timeout_seconds": None})
        assert body == {"mcp": {"timeout_seconds": None}}

    def test_sends_connector_settings(self, httpx_mock, client: RagnerockClient):
        body = self._body(
            httpx_mock, client, connector={"parameters": {"site": "datadoghq.com"}}
        )
        assert body == {"connector": {"parameters": {"site": "datadoghq.com"}}}


class TestDelete:
    def test_reports_unlinked_agents(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/agent-tools/{TOOL_ID}"),
            json={"id": TOOL_ID, "operator_count": 3},
        )

        result = client.tools.delete(UUID(TOOL_ID))

        assert last_request(httpx_mock).method == "DELETE"
        assert isinstance(result, AgentToolDeleteResponse)
        assert result.id == UUID(TOOL_ID)
        assert result.operator_count == 3


class TestOAuth:
    _REDIRECT: dict[str, Any] = {
        "outcome": "redirect",
        "authorization_url": "https://mcp.example.com/authorize?client_id=abc",
        "expires_at": "2026-09-04T00:10:00Z",
        "issuer": "https://mcp.example.com",
        "redirect_uri": "https://app.ragnerock.test/oauth/callback",
    }

    def test_start_sends_no_credentials_on_the_first_attempt(
        self, httpx_mock, client: RagnerockClient
    ):
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/agent-tools/{TOOL_ID}/oauth/start"),
            json=self._REDIRECT,
        )

        result = client.tools.oauth_start(UUID(TOOL_ID))

        assert last_json(httpx_mock) == {}
        # Discovery, registration, and the URL build all happen in this call.
        assert _read_timeout(httpx_mock) == PROBE_TIMEOUT_SECONDS
        assert isinstance(result, McpOAuthStartResponse)
        assert result.outcome == McpOAuthStartOutcome.REDIRECT
        assert result.authorization_url is not None
        assert result.expires_at is not None

    def test_start_carries_console_credentials_on_the_second(
        self, httpx_mock, client: RagnerockClient
    ):
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/agent-tools/{TOOL_ID}/oauth/start"),
            json=self._REDIRECT,
        )

        client.tools.oauth_start(UUID(TOOL_ID), client_id="mine", client_secret="shh")

        assert last_json(httpx_mock) == {"client_id": "mine", "client_secret": "shh"}

    def test_start_reports_that_credentials_are_needed(
        self, httpx_mock, client: RagnerockClient
    ):
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/agent-tools/{TOOL_ID}/oauth/start"),
            json={
                "outcome": "credentials_required",
                "authorization_url": None,
                "expires_at": None,
                "issuer": "https://mcp.example.com",
                "redirect_uri": "https://app.ragnerock.test/oauth/callback",
            },
        )

        result = client.tools.oauth_start(UUID(TOOL_ID))

        assert result.outcome == McpOAuthStartOutcome.CREDENTIALS_REQUIRED
        assert result.authorization_url is None
        assert result.redirect_uri is not None
        assert result.redirect_uri.endswith("/oauth/callback")

    def test_disconnect_keeps_the_pinned_functions(
        self, httpx_mock, client: RagnerockClient
    ):
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/agent-tools/{TOOL_ID}/oauth"),
            json=_tool(
                kind="mcp",
                mcp=_mcp_config(
                    auth="oauth",
                    oauth={
                        "status": "disconnected",
                        "issuer": "https://mcp.example.com",
                        "scopes": [],
                        "required_scopes": [],
                    },
                ),
            ),
        )

        result = client.tools.oauth_disconnect(UUID(TOOL_ID))

        request = last_request(httpx_mock)
        assert request.method == "DELETE"
        assert request.content == b""
        assert _read_timeout(httpx_mock) == PROBE_TIMEOUT_SECONDS
        assert result.mcp is not None
        assert result.mcp.oauth is not None
        assert result.mcp.oauth.status == "disconnected"
        assert result.mcp.oauth.issuer == "https://mcp.example.com"
        # What the server offers did not change, so the list stays pinned.
        assert result.functions != []


class TestProbes:
    def test_discover_posts_without_a_body(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="POST",
            url=url(f"/api/agent-tools/{TOOL_ID}/discover"),
            json={
                "functions": [
                    {
                        "name": "linear__create_issue",
                        "description": "Create an issue.",
                        "input_schema": {"type": "object"},
                        "warnings": [],
                    }
                ],
                "discovered_at": NOW,
                "warnings": [],
                "added": ["linear__create_issue"],
                "removed": [],
            },
        )

        result = client.tools.discover(UUID(TOOL_ID))

        assert last_request(httpx_mock).content == b""
        assert _read_timeout(httpx_mock) == PROBE_TIMEOUT_SECONDS
        assert isinstance(result, McpDiscoverResponse)
        assert result.added == ["linear__create_issue"]
        assert result.functions[0].input_schema == {"type": "object"}
        assert result.auth_required is False

    def test_parse_mcp_config_wraps_the_paste(
        self, httpx_mock, client: RagnerockClient
    ):
        httpx_mock.add_response(
            method="POST",
            url=url("/api/agent-tools/mcp/parse-config"),
            json={
                "servers": [
                    {
                        "key": "linear",
                        "url": "https://mcp.example.com/mcp",
                        "transport": "streamable_http",
                        "headers": [],
                    }
                ],
                "warnings": ["Skipped 'local': it is a local (stdio) server."],
            },
        )
        config = {
            "mcpServers": {
                "linear": {"url": "https://mcp.example.com/mcp"},
                "local": {"command": "npx"},
            }
        }

        result = client.tools.parse_mcp_config(config, project_id=UUID(PROJECT_ID))

        assert last_json(httpx_mock) == {"project_id": PROJECT_ID, "config": config}
        assert isinstance(result, McpParseConfigResponse)
        assert result.servers[0].key == "linear"
        assert "stdio" in result.warnings[0]

    def test_preview_discovery_carries_the_tool_for_kept_secrets(
        self, httpx_mock, client: RagnerockClient
    ):
        httpx_mock.add_response(
            method="POST",
            url=url("/api/agent-tools/mcp/discover"),
            json={
                "functions": [],
                "discovered_at": NOW,
                "warnings": [],
                "added": [],
                "removed": ["linear__old"],
                "auth_required": True,
            },
        )

        result = client.tools.preview_mcp_discovery(
            project_id=UUID(PROJECT_ID),
            slug="linear",
            mcp={"url": "https://mcp.example.com/mcp", "auth": "none"},
            tool_id=UUID(TOOL_ID),
        )

        assert last_json(httpx_mock) == {
            "project_id": PROJECT_ID,
            "tool_id": TOOL_ID,
            "slug": "linear",
            "mcp": {"url": "https://mcp.example.com/mcp", "auth": "none"},
        }
        assert _read_timeout(httpx_mock) == PROBE_TIMEOUT_SECONDS
        assert result.removed == ["linear__old"]
        assert result.auth_required is True

    def test_route_test_sends_flat_arguments(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="POST",
            url=url("/api/agent-tools/rest/test"),
            json={
                "ok": True,
                "status_code": 200,
                "request_url": "https://api.example.com/v1/customers/42",
                "duration_ms": 87,
                "response_preview": '{"id": "42"}',
                "error": None,
            },
        )

        result = client.tools.test_rest_route(
            project_id=UUID(PROJECT_ID),
            base_url="https://api.example.com/v1",
            route=_route(),
            arguments={"customer_id": "42"},
        )

        assert last_json(httpx_mock) == {
            "project_id": PROJECT_ID,
            "base_url": "https://api.example.com/v1",
            "headers": [],
            "route": _route(),
            "arguments": {"customer_id": "42"},
        }
        assert _read_timeout(httpx_mock) == PROBE_TIMEOUT_SECONDS
        assert isinstance(result, RestRouteTestResponse)
        assert result.ok is True
        assert result.request_url is not None
        assert result.request_url.endswith("/customers/42")

    def test_route_test_with_a_saved_tool(self, httpx_mock, client: RagnerockClient):
        httpx_mock.add_response(
            method="POST",
            url=url("/api/agent-tools/rest/test"),
            json={
                "ok": False,
                "status_code": 401,
                "request_url": "https://api.example.com/v1/customers/42",
                "duration_ms": 12,
                "response_preview": "",
                "error": "Unauthorized",
            },
        )

        result = client.tools.test_rest_route(
            project_id=UUID(PROJECT_ID),
            base_url="https://api.example.com/v1",
            route=_route(),
            arguments={},
            headers=[{"name": "Authorization", "value": None, "is_secret": True}],
            tool_id=UUID(TOOL_ID),
        )

        body = last_json(httpx_mock)
        assert body["tool_id"] == TOOL_ID
        assert body["arguments"] == {}
        assert body["headers"] == [
            {"name": "Authorization", "value": None, "is_secret": True}
        ]
        assert result.ok is False
        assert result.status_code == 401
        assert result.error == "Unauthorized"
