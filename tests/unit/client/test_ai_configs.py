"""Tests for the AI provider, embedding, and image-summary config sections."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from ragnerock.client import UNSET, RagnerockClient
from ragnerock.client.ai_configs import (
    AI_CONFIG_VALIDATE_TIMEOUT,
    AIConfigStatus,
    RegenerationStatus,
)
from ragnerock.enums import AIProviderType, EmbeddingModelType
from ragnerock.errors import NotFoundError, RagnerockError
from tests.unit.client.conftest import last_json, last_request, url

CFG_1 = uuid.UUID("00000000-0000-4000-8000-000000000001")
CFG_2 = uuid.UUID("00000000-0000-4000-8000-000000000002")
REGEN_1 = uuid.UUID("00000000-0000-4000-8000-00000000e001")


def _read_timeout(httpx_mock: Any) -> float | None:
    """Return the read timeout the most recent request was sent with."""
    return last_request(httpx_mock).extensions["timeout"]["read"]


def _config_payload(config_id: uuid.UUID = CFG_1, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(config_id),
        "config_name": "Prod",
        "provider_type": "openai",
        "endpoint_url": "https://api.openai.com/v1",
        "api_key_masked": "sk-...abcd",
        "model_name": "gpt-5",
        "status": "default",
        "fallback_to_ragnerock": False,
        "timeout_seconds": 120,
        "max_requests_per_minute": None,
        "max_tokens_per_day": None,
        "referencing_operator_count": 3,
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def _list_payload(*configs: dict[str, Any]) -> dict[str, Any]:
    return {"configs": list(configs), "total": len(configs), "skip": 0, "limit": 100}


class TestCreate:
    def test_sends_required_fields_and_drops_unset_optionals(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/ai-configs/"),
            json={"id": str(CFG_1), "config_name": None, "message": "created"},
        )

        result = client.ai_configs.create(
            provider_type=AIProviderType.OPENAI,
            endpoint_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        assert last_json(httpx_mock) == {
            "provider_type": "openai",
            "endpoint_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "fallback_to_ragnerock": False,
            "timeout_seconds": 120,
        }
        assert result.id == CFG_1
        assert result.message == "created"

    def test_uses_the_provider_test_timeout(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/ai-configs/"),
            json={"id": str(CFG_1), "message": "created"},
        )

        client.ai_configs.create(
            provider_type="openai", endpoint_url="https://x", api_key="k"
        )

        assert _read_timeout(httpx_mock) == AI_CONFIG_VALIDATE_TIMEOUT

    def test_forwards_optional_settings(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/ai-configs/"),
            json={"id": str(CFG_1), "config_name": "Azure", "message": "created"},
        )

        client.ai_configs.create(
            provider_type="azure_openai",
            endpoint_url="https://resource.openai.azure.com",
            api_key="sk-test",
            config_name="Azure",
            model_name="gpt-4o",
            fallback_ai_config_id=CFG_2,
            assignment_token_budget=400_000,
            assignment_max_turns=12,
            assignment_max_age_days=7,
            assignment_retention_days=90,
            provider_options={"type": "azure_openai", "temperature": 0.2},
            status=AIConfigStatus.DEFAULT,
        )

        body = last_json(httpx_mock)
        assert body["provider_type"] == "azure_openai"
        assert body["model_name"] == "gpt-4o"
        assert body["config_name"] == "Azure"
        assert body["fallback_ai_config_id"] == str(CFG_2)
        assert body["assignment_token_budget"] == 400_000
        assert body["assignment_max_turns"] == 12
        assert body["assignment_max_age_days"] == 7
        assert body["assignment_retention_days"] == 90
        assert body["provider_options"] == {"type": "azure_openai", "temperature": 0.2}
        assert body["status"] == "default"

    def test_rejects_embedding_kwargs(self, client: RagnerockClient) -> None:
        """Embeddings are configured through ``client.embedding_config``."""
        extra: dict[str, Any] = {"embedding_llm_model": "text-embedding-3-small"}
        with pytest.raises(TypeError):
            client.ai_configs.create(
                provider_type="openai",
                endpoint_url="https://api.openai.com/v1",
                api_key="sk-test",
                **extra,
            )

    def test_provider_test_failure_raises(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=url("/api/ai-configs/"),
            status_code=400,
            json={"detail": "Provider rejected the API key"},
        )

        with pytest.raises(RagnerockError, match="rejected the API key"):
            client.ai_configs.create(
                provider_type="openai", endpoint_url="https://x", api_key="bad"
            )


class TestListAndGet:
    def test_list_parses_configs(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/ai-configs/"),
            json=_list_payload(_config_payload(), _config_payload(CFG_2)),
        )

        result = client.ai_configs.list()

        assert last_request(httpx_mock).method == "GET"
        assert [c.id for c in result.configs] == [CFG_1, CFG_2]
        first = result.configs[0]
        assert first.status == AIConfigStatus.DEFAULT
        assert first.provider_type == AIProviderType.OPENAI
        assert first.api_key_masked == "sk-...abcd"
        assert first.referencing_operator_count == 3
        assert result.total == 2

    def test_get_picks_the_matching_config(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/ai-configs/"),
            json=_list_payload(
                _config_payload(), _config_payload(CFG_2, config_name="Backup")
            ),
        )

        config = client.ai_configs.get(CFG_2)

        assert config.id == CFG_2
        assert config.config_name == "Backup"

    def test_get_missing_config_raises_not_found(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/ai-configs/"),
            json=_list_payload(_config_payload()),
        )

        with pytest.raises(NotFoundError):
            client.ai_configs.get(CFG_2)


class TestUpdate:
    def _update(
        self, client: RagnerockClient, httpx_mock: Any, **kwargs: Any
    ) -> dict[str, Any]:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/ai-configs/{CFG_1}"),
            json={"id": str(CFG_1), "message": "updated"},
        )
        result = client.ai_configs.update(CFG_1, **kwargs)
        assert result.id == CFG_1
        assert result.message == "updated"
        assert _read_timeout(httpx_mock) == AI_CONFIG_VALIDATE_TIMEOUT
        return last_json(httpx_mock)

    def test_only_given_fields_are_sent(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        body = self._update(client, httpx_mock, config_name="Renamed")
        assert body == {"config_name": "Renamed"}

    def test_explicit_none_clears_the_fallback(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        body = self._update(client, httpx_mock, fallback_ai_config_id=None)
        assert body == {"fallback_ai_config_id": None}

    def test_fallback_set_sends_the_id(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        body = self._update(client, httpx_mock, fallback_ai_config_id=CFG_2)
        assert body == {"fallback_ai_config_id": str(CFG_2)}

    def test_provider_options_set_and_clear(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        options = {"type": "anthropic", "thinking_budget_tokens": 2048}
        body = self._update(client, httpx_mock, provider_options=options)
        assert body == {"provider_options": options}

        body = self._update(client, httpx_mock, provider_options=None)
        assert body == {"provider_options": None}

    def test_unset_leaves_patch_fields_out(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        body = self._update(
            client,
            httpx_mock,
            model_name="gpt-5",
            fallback_ai_config_id=UNSET,
            provider_options=UNSET,
        )
        assert body == {"model_name": "gpt-5"}

    def test_sends_the_assignment_limits(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        limits = {
            "assignment_token_budget": 400_000,
            "assignment_max_turns": 12,
            "assignment_max_age_days": 7,
            "assignment_retention_days": 90,
        }
        body = self._update(client, httpx_mock, **limits)
        assert body == limits


class TestDeleteAndStatus:
    def test_delete(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/ai-configs/{CFG_1}"),
            json={"message": "deleted"},
        )

        assert client.ai_configs.delete(CFG_1) is None
        assert last_request(httpx_mock).method == "DELETE"

    def test_delete_refusal_raises(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url(f"/api/ai-configs/{CFG_1}"),
            status_code=409,
            json={"detail": "Another config falls back to this one"},
        )

        with pytest.raises(RagnerockError) as caught:
            client.ai_configs.delete(CFG_1)
        assert caught.value.status_code == 409

    def test_set_status_disabled_reports_references(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/ai-configs/{CFG_1}/status"),
            json={
                "id": str(CFG_1),
                "status": "disabled",
                "message": "Config disabled",
                "operators_referencing": 4,
                "snapshots_referencing": 1,
                "fallbacks_referencing": 0,
            },
        )

        result = client.ai_configs.set_status(CFG_1, status=AIConfigStatus.DISABLED)

        assert last_json(httpx_mock) == {"status": "disabled"}
        assert _read_timeout(httpx_mock) == AI_CONFIG_VALIDATE_TIMEOUT
        assert result.status == AIConfigStatus.DISABLED
        assert result.operators_referencing == 4
        assert result.snapshots_referencing == 1

    def test_set_status_accepts_plain_strings(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url(f"/api/ai-configs/{CFG_1}/status"),
            json={"id": str(CFG_1), "status": "default", "message": "ok"},
        )

        client.ai_configs.set_status(CFG_1, status="default")

        assert last_json(httpx_mock) == {"status": "default"}

    def test_list_selectable(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/ai-configs/selectable"),
            json={
                "configs": [
                    {
                        "id": str(CFG_1),
                        "config_name": "Prod",
                        "provider_type": "anthropic",
                        "model_name": "claude",
                        "status": "default",
                        "supports_reasoning_effort": True,
                    }
                ]
            },
        )

        result = client.ai_configs.list_selectable()

        (only,) = result.configs
        assert only.id == CFG_1
        assert only.status == AIConfigStatus.DEFAULT
        assert only.supports_reasoning_effort is True


class TestEmbeddingConfig:
    def test_get_null_config_means_ragnerock_embeddings(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/embedding-config"),
            json={"config": None, "account_has_embeddings": False},
        )

        result = client.embedding_config.get()

        assert result.config is None
        assert result.account_has_embeddings is False

    def test_get_populated_config_parses(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/embedding-config"),
            json={
                "config": {
                    "embedding_type": "azure_openai",
                    "endpoint": "https://resource.openai.azure.com",
                    "model": "my-embedding-deployment",
                    "dimensions": 1536,
                    "api_key_masked": "sk-e...bed1",
                    "updated_at": "2026-09-17T00:00:00Z",
                },
                "account_has_embeddings": True,
            },
        )

        result = client.embedding_config.get()

        assert result.config is not None
        assert result.config.embedding_type == EmbeddingModelType.AZURE_OPENAI
        assert result.config.model == "my-embedding-deployment"
        assert result.config.dimensions == 1536
        assert result.config.updated_at is not None
        assert result.config.updated_at.year == 2026
        assert result.account_has_embeddings is True

    def test_put_sends_settings_key_and_opt_in(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url("/api/embedding-config"),
            json={"message": "Saved", "regeneration_id": str(REGEN_1)},
        )

        result = client.embedding_config.put(
            embedding_type=EmbeddingModelType.OPENAI,
            endpoint="https://api.openai.com/v1",
            model="text-embedding-3-small",
            dimensions=1536,
            api_key="sk-embed",
            regenerate_embeddings=True,
        )

        assert last_json(httpx_mock) == {
            "embedding_type": "openai",
            "endpoint": "https://api.openai.com/v1",
            "model": "text-embedding-3-small",
            "dimensions": 1536,
            "api_key": "sk-embed",
            "regenerate_embeddings": True,
        }
        assert _read_timeout(httpx_mock) == AI_CONFIG_VALIDATE_TIMEOUT
        assert result.message == "Saved"
        assert result.regeneration_id == REGEN_1

    def test_put_omitted_key_keeps_the_stored_one(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url("/api/embedding-config"),
            json={"message": "Saved", "regeneration_id": None},
        )

        result = client.embedding_config.put(
            embedding_type="gemini",
            endpoint="https://generativelanguage.googleapis.com",
            model="gemini-embedding-2",
            dimensions=768,
        )

        body = last_json(httpx_mock)
        assert "api_key" not in body
        assert body["regenerate_embeddings"] is False
        assert result.regeneration_id is None

    def test_put_refusal_raises(self, client: RagnerockClient, httpx_mock: Any) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url("/api/embedding-config"),
            status_code=409,
            json={"detail": "Confirm regenerating embeddings"},
        )

        with pytest.raises(RagnerockError, match="Confirm regenerating"):
            client.embedding_config.put(
                embedding_type="openai",
                endpoint="https://api.openai.com/v1",
                model="text-embedding-3-small",
                dimensions=1536,
            )

    @pytest.mark.parametrize("regenerate", [True, False])
    def test_delete_carries_the_opt_in_in_its_body(
        self, client: RagnerockClient, httpx_mock: Any, regenerate: bool
    ) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url("/api/embedding-config"),
            json={
                "message": "Removed",
                "regeneration_id": str(REGEN_1) if regenerate else None,
            },
        )

        result = client.embedding_config.delete(regenerate_embeddings=regenerate)

        assert last_request(httpx_mock).method == "DELETE"
        assert last_json(httpx_mock) == {"regenerate_embeddings": regenerate}
        assert result.regeneration_id == (REGEN_1 if regenerate else None)

    def test_delete_opt_in_defaults_false(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url("/api/embedding-config"),
            json={"message": "Removed"},
        )

        client.embedding_config.delete()

        assert last_json(httpx_mock) == {"regenerate_embeddings": False}

    def test_latest_regeneration(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/embedding-config/regenerations/latest"),
            json={
                "id": str(REGEN_1),
                "status": "in_progress",
                "old_embedding_model": "gemini-embedding-2",
                "old_embedding_type": "gemini",
                "old_embedding_dimensions": 768,
                "new_embedding_model": "text-embedding-3-small",
                "new_embedding_type": "openai",
                "new_embedding_dimensions": 1536,
                "jobs_total": 10,
                "jobs_completed": 4,
                "jobs_failed": 0,
                "supplemental_rounds": 0,
                "created_at": "2026-09-17T00:00:00Z",
                "updated_at": "2026-09-17T00:05:00Z",
            },
        )

        detail = client.embedding_config.latest_regeneration()

        assert detail.id == REGEN_1
        assert detail.status == RegenerationStatus.IN_PROGRESS
        assert detail.new_embedding_type == EmbeddingModelType.OPENAI
        assert detail.jobs_completed == 4
        assert detail.completed_at is None

    def test_latest_regeneration_none_raises_not_found(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/embedding-config/regenerations/latest"),
            status_code=404,
            json={"detail": "No regeneration"},
        )

        with pytest.raises(NotFoundError):
            client.embedding_config.latest_regeneration()


class TestImageSummaryConfig:
    def test_get_null_config_means_ragnerock_summarizer(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET", url=url("/api/image-summary-config"), json={"config": None}
        )

        assert client.image_summary_config.get().config is None

    def test_get_populated_config_parses(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=url("/api/image-summary-config"),
            json={
                "config": {
                    "provider_type": "anthropic",
                    "endpoint": "https://api.anthropic.com",
                    "model": "claude-vision",
                    "api_key_masked": "sk-a...1234",
                    "updated_at": "2026-09-17T00:00:00Z",
                }
            },
        )

        result = client.image_summary_config.get()

        assert result.config is not None
        assert result.config.provider_type == AIProviderType.ANTHROPIC
        assert result.config.model == "claude-vision"
        assert result.config.api_key_masked == "sk-a...1234"

    def test_put_sends_settings_and_key(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url("/api/image-summary-config"),
            json={"message": "Saved"},
        )

        result = client.image_summary_config.put(
            provider_type=AIProviderType.OPENAI,
            endpoint="https://api.openai.com/v1",
            model="gpt-5.5",
            api_key="sk-vision",
        )

        assert last_json(httpx_mock) == {
            "provider_type": "openai",
            "endpoint": "https://api.openai.com/v1",
            "model": "gpt-5.5",
            "api_key": "sk-vision",
        }
        assert _read_timeout(httpx_mock) == AI_CONFIG_VALIDATE_TIMEOUT
        assert result.message == "Saved"

    def test_put_omitted_key_is_left_out(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=url("/api/image-summary-config"),
            json={"message": "Saved"},
        )

        client.image_summary_config.put(
            provider_type="gemini",
            endpoint="https://generativelanguage.googleapis.com",
            model="gemini-3.5-flash",
        )

        assert "api_key" not in last_json(httpx_mock)

    def test_delete_sends_no_body(
        self, client: RagnerockClient, httpx_mock: Any
    ) -> None:
        httpx_mock.add_response(
            method="DELETE",
            url=url("/api/image-summary-config"),
            json={"message": "Removed"},
        )

        result = client.image_summary_config.delete()

        assert last_request(httpx_mock).content == b""
        assert result.message == "Removed"
