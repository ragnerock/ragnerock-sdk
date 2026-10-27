"""Tests for the web access policy and search provider section."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from ragnerock.client import RagnerockClient
from ragnerock.client.web_access import WebSearchProviderType
from ragnerock.errors import AuthenticationError, RagnerockError
from tests.unit.client.conftest import last_json, last_request, url

ACCOUNT_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
PROVIDER_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")


def _policy_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "account_id": str(ACCOUNT_ID),
        "web_fetch_enabled": True,
        "web_search_enabled": False,
        "web_search_daily_cap": None,
        "effective_web_search_daily_cap": 5000,
        "updated_at": "2026-09-06T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _provider_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(PROVIDER_ID),
        "account_id": str(ACCOUNT_ID),
        "provider": "brave",
        "api_key_hint": "••••3456",
        "is_validated": True,
        "last_validated_at": "2026-09-06T00:00:00Z",
        "last_error": None,
        "created_at": "2026-09-06T00:00:00Z",
        "updated_at": None,
    }
    payload.update(overrides)
    return payload


class TestPolicy:
    def test_get_parses_the_effective_cap(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET", url=url("/api/web-access/policy"), json=_policy_payload()
        )

        policy = client.web_access.get_policy()

        assert last_request(httpx_mock).method == "GET"
        assert policy.account_id == ACCOUNT_ID
        assert policy.web_fetch_enabled is True
        assert policy.web_search_daily_cap is None
        assert policy.effective_web_search_daily_cap == 5000
        assert policy.updated_at is not None

    def test_set_sends_both_switches_and_the_cap(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url("/api/web-access/policy"),
            json=_policy_payload(
                web_search_enabled=True,
                web_search_daily_cap=100,
                effective_web_search_daily_cap=100,
            ),
        )

        policy = client.web_access.set_policy(
            web_fetch_enabled=True,
            web_search_enabled=True,
            web_search_daily_cap=100,
        )

        assert last_json(httpx_mock) == {
            "web_fetch_enabled": True,
            "web_search_enabled": True,
            "web_search_daily_cap": 100,
        }
        assert policy.effective_web_search_daily_cap == 100

    def test_set_sends_an_omitted_cap_as_null(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        """The policy is replaced whole, so null means the deployment default."""
        httpx_mock.add_response(
            method="PUT", url=url("/api/web-access/policy"), json=_policy_payload()
        )

        client.web_access.set_policy(web_fetch_enabled=True, web_search_enabled=False)

        assert last_json(httpx_mock) == {
            "web_fetch_enabled": True,
            "web_search_enabled": False,
            "web_search_daily_cap": None,
        }


class TestSearchProvider:
    def test_get_parses_a_configured_provider(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/web-access/search-provider"),
            json=_provider_payload(),
        )

        provider = client.web_access.get_search_provider()

        assert provider is not None
        assert provider.id == PROVIDER_ID
        assert provider.provider == WebSearchProviderType.BRAVE
        assert provider.api_key_hint == "••••3456"
        assert provider.updated_at is None

    def test_get_returns_none_when_unconfigured(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        """A missing provider is a normal state, not a failure."""
        httpx_mock.add_response(
            method="GET",
            url=url("/api/web-access/search-provider"),
            status_code=404,
            json={"detail": "No search provider configured"},
        )

        assert client.web_access.get_search_provider() is None

    def test_get_other_errors_still_raise(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/web-access/search-provider"),
            status_code=403,
            json={"detail": "Forbidden"},
        )

        with pytest.raises(AuthenticationError):
            client.web_access.get_search_provider()

    def test_set_sends_the_key_when_given(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url("/api/web-access/search-provider"),
            json=_provider_payload(),
        )

        result = client.web_access.set_search_provider(
            provider=WebSearchProviderType.BRAVE, api_key="BSA-live-abcdef123456"
        )

        assert last_json(httpx_mock) == {
            "provider": "brave",
            "api_key": "BSA-live-abcdef123456",
        }
        assert result.is_validated is True

    def test_set_omits_an_omitted_key(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        """Omission keeps the stored key; an explicit null would be refused."""
        httpx_mock.add_response(
            method="PUT",
            url=url("/api/web-access/search-provider"),
            json=_provider_payload(),
        )

        client.web_access.set_search_provider(provider="brave")

        assert last_json(httpx_mock) == {"provider": "brave"}

    def test_delete_accepts_204(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url("/api/web-access/search-provider"),
            status_code=204,
        )

        assert client.web_access.delete_search_provider() is None
        assert last_request(httpx_mock).method == "DELETE"

    def test_delete_refusal_raises_with_its_status(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url("/api/web-access/search-provider"),
            status_code=403,
            json={"detail": "Only an account administrator can change web access."},
        )

        with pytest.raises(RagnerockError) as caught:
            client.web_access.delete_search_provider()
        assert caught.value.status_code == 403


class TestProbe:
    def test_sends_the_candidate_and_the_query(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/web-access/search-provider/test"),
            json={
                "ok": True,
                "result_count": 1,
                "results": [{"title": "T", "url": "https://x.test/a", "snippet": ""}],
                "latency_ms": 120,
                "error": None,
            },
        )

        result = client.web_access.test_search_provider(
            provider=WebSearchProviderType.BRAVE,
            api_key="BSA-candidate",
            query="ragnerock",
        )

        assert last_json(httpx_mock) == {
            "provider": "brave",
            "api_key": "BSA-candidate",
            "query": "ragnerock",
        }
        assert result.ok is True
        assert result.result_count == 1
        assert result.results[0].url == "https://x.test/a"
        assert result.latency_ms == 120

    def test_testing_the_stored_key_sends_only_the_query(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/web-access/search-provider/test"),
            json={
                "ok": False,
                "result_count": 0,
                "results": [],
                "latency_ms": 80,
                "error": "The provider rejected the key.",
            },
        )

        result = client.web_access.test_search_provider()

        assert last_json(httpx_mock) == {"query": "ragnerock"}
        assert result.ok is False
        assert result.error == "The provider rejected the key."

    @pytest.mark.parametrize(
        "kwargs", [{"provider": "brave"}, {"api_key": "BSA-candidate"}]
    )
    def test_half_a_candidate_is_refused_client_side(
        self, client: RagnerockClient, httpx_mock: Any, kwargs: dict[str, str]
    ) -> None:
        with pytest.raises(ValueError, match="both provider and api_key"):
            client.web_access.test_search_provider(**kwargs)
        assert httpx_mock.get_requests() == []
