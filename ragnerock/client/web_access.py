"""Web access policy and search provider endpoints (``/api/web-access/...``)."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from ragnerock.client._base import _ApiModel, _body, _patch_body, _Section
from ragnerock.errors import NotFoundError
from ragnerock.timestamps import UtcDatetime


class WebSearchProviderType(StrEnum):
    """Web search vendors a workspace can configure."""

    BRAVE = "brave"


class WebAccessPolicyResponse(_ApiModel):
    """The workspace's web access policy.

    Attributes:
        account_id (UUID | None): The workspace's account.
        web_fetch_enabled (bool): Whether agents may retrieve web pages.
        web_search_enabled (bool): Whether agents may search the web.
        web_search_daily_cap (int | None): Saved cap on billed searches per
            rolling day; ``None`` uses the deployment default.
        effective_web_search_daily_cap (int | None): The cap actually in
            force.
        updated_at (datetime | None): Last change; ``None`` if never saved.
    """

    account_id: UUID | None = None
    web_fetch_enabled: bool = False
    web_search_enabled: bool = False
    web_search_daily_cap: int | None = None
    effective_web_search_daily_cap: int | None = None
    updated_at: UtcDatetime = None


class WebSearchProviderResponse(_ApiModel):
    """The workspace's search provider. The key itself is never returned.

    Attributes:
        id (UUID): Provider config id.
        provider (str | None): A :class:`WebSearchProviderType` value.
        api_key_hint (str | None): Masked hint of the stored key.
        is_validated (bool): Whether the key has passed a test.
        last_validated_at (datetime | None): When it last passed.
        last_error (str | None): Why the last test failed, if it did.
        created_at (datetime | None): When the provider was configured.
        updated_at (datetime | None): Last change.
    """

    id: UUID
    provider: str | None = None
    api_key_hint: str | None = None
    is_validated: bool = False
    last_validated_at: UtcDatetime = None
    last_error: str | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None


class WebSearchResult(_ApiModel):
    """One result returned by the search provider.

    Every field is third-party text; treat it as untrusted.
    """

    title: str | None = None
    url: str | None = None
    snippet: str = ""
    site: str | None = None
    published: UtcDatetime = None


class WebSearchProviderTestResponse(_ApiModel):
    """Outcome of a test query. The key is never echoed back.

    Attributes:
        ok (bool): Whether the query succeeded.
        result_count (int): How many results came back.
        results (list[WebSearchResult]): A small preview of them.
        latency_ms (int | None): How long the query took.
        error (str | None): Why it failed, if it did.
    """

    ok: bool = False
    result_count: int = 0
    results: list[WebSearchResult] = []
    latency_ms: int | None = None
    error: str | None = None


class _WebAccessSection(_Section):
    """The workspace's web-fetch/search policy and search provider.

    The policy is an account-administrator switch for whether agents may reach
    the open web at all. A project editor still has to turn the tool on for a
    project before agents there can use it.
    """

    def get_policy(self) -> WebAccessPolicyResponse:
        """Fetch the workspace's web access policy.

        Calls ``GET /api/web-access/policy``. A workspace that has never saved
        one reads back as everything off.

        Returns:
            WebAccessPolicyResponse: The policy.
        """
        response = self._parent._request("GET", "/api/web-access/policy")
        return WebAccessPolicyResponse.model_validate(response.json())

    def set_policy(
        self,
        *,
        web_fetch_enabled: bool,
        web_search_enabled: bool,
        web_search_daily_cap: int | None = None,
    ) -> WebAccessPolicyResponse:
        """Replace the workspace's web access policy.

        Calls ``PUT /api/web-access/policy``. The policy is replaced whole,
        so ``web_search_daily_cap=None`` means "the deployment default", not
        "leave unchanged".

        Args:
            web_fetch_enabled (bool): Whether agents may retrieve web pages.
            web_search_enabled (bool): Whether agents may search the web.
            web_search_daily_cap (int | None): Billed searches per rolling day
                (at least 1), or ``None`` for the deployment default.

        Returns:
            WebAccessPolicyResponse: The saved policy.
        """
        body = _patch_body(
            web_fetch_enabled=web_fetch_enabled,
            web_search_enabled=web_search_enabled,
            web_search_daily_cap=web_search_daily_cap,
        )
        response = self._parent._request(
            "PUT", "/api/web-access/policy", json_body=body
        )
        return WebAccessPolicyResponse.model_validate(response.json())

    def get_search_provider(self) -> WebSearchProviderResponse | None:
        """Fetch the workspace's search provider, with the key masked.

        Calls ``GET /api/web-access/search-provider``.

        Returns:
            WebSearchProviderResponse | None: The provider, or ``None`` when
            none is configured.
        """
        try:
            response = self._parent._request("GET", "/api/web-access/search-provider")
        except NotFoundError:
            return None
        return WebSearchProviderResponse.model_validate(response.json())

    def set_search_provider(
        self, *, provider: str, api_key: str | None = None
    ) -> WebSearchProviderResponse:
        """Configure the workspace's search provider, or replace its key.

        Calls ``PUT /api/web-access/search-provider``.

        Args:
            provider (str): A :class:`WebSearchProviderType` value.
            api_key (str | None): The vendor API key. Required the first
                time; omit it to keep the stored key, which is allowed only
                while ``provider`` is unchanged. To remove the key, use
                :meth:`delete_search_provider`.

        Returns:
            WebSearchProviderResponse: The saved provider, with the key masked.
        """
        body = _body(provider=provider, api_key=api_key)
        response = self._parent._request(
            "PUT", "/api/web-access/search-provider", json_body=body
        )
        return WebSearchProviderResponse.model_validate(response.json())

    def delete_search_provider(self) -> None:
        """Remove the workspace's search provider and its key.

        Calls ``DELETE /api/web-access/search-provider``. The policy is left
        alone; web search simply stops working in every project that has it
        on, and agents there carry on without it.
        """
        self._parent._request("DELETE", "/api/web-access/search-provider")

    def test_search_provider(
        self,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        query: str = "ragnerock",
    ) -> WebSearchProviderTestResponse:
        """Run one real query against the stored key, or a candidate one.

        Calls ``POST /api/web-access/search-provider/test``. Pass both
        ``provider`` and ``api_key`` to try a key before saving it, or
        neither to test the stored one. The test is audited but counts
        against no daily cap.

        Args:
            provider (str | None): A candidate :class:`WebSearchProviderType`
                value.
            api_key (str | None): The candidate key.
            query (str): What to search for.

        Returns:
            WebSearchProviderTestResponse: What came back. Failures carry a
            short explanation rather than the vendor's response.

        Raises:
            ValueError: If only one of ``provider`` and ``api_key`` is given.
        """
        if (provider is None) != (api_key is None):
            raise ValueError(
                "Pass both provider and api_key to test a new key, or neither "
                "to test the stored one."
            )
        body = _body(provider=provider, api_key=api_key, query=query)
        response = self._parent._request(
            "POST", "/api/web-access/search-provider/test", json_body=body
        )
        return WebSearchProviderTestResponse.model_validate(response.json())
