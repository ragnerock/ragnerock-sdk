"""AI provider, embedding, and image-summary config endpoints."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from ragnerock.client._base import UNSET, _ApiModel, _body, _patch_body, _Section
from ragnerock.errors import NotFoundError
from ragnerock.timestamps import UtcDatetime

AI_CONFIG_VALIDATE_TIMEOUT = 90.0
"""Read timeout, in seconds, for calls that test a provider before saving.

Creating or updating a provider config (and changing its status) makes the
server call the provider live, which can take far longer than an ordinary
request.
"""


class AIConfigStatus(StrEnum):
    """Lifecycle status of an AI provider config."""

    DEFAULT = "default"
    """Used by every operator and agent that doesn't pick a config. At most one
    per account."""

    ACTIVE = "active"
    """Available for individual operators to select."""

    DISABLED = "disabled"
    """Stored, but neither usable nor selectable."""


class RegenerationStatus(StrEnum):
    """Lifecycle status of an account-wide embedding regeneration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SUPERSEDED = "superseded"


# -- AI provider configs -------------------------------------------------------


class AIConfigDetail(_ApiModel):
    """A stored AI provider config. The API key itself is never returned.

    Attributes:
        id (UUID): Config id.
        config_name (str | None): Friendly name.
        provider_type (str | None): An
            :class:`~ragnerock.enums.AIProviderType` value.
        endpoint_url (str | None): Provider endpoint.
        api_key_masked (str | None): Masked hint of the stored key.
        model_name (str | None): Model the config calls, if pinned.
        status (str | None): An :class:`AIConfigStatus` value.
        fallback_to_ragnerock (bool): Whether failed calls fall back to
            Ragnerock's own models.
        fallback_ai_config_id (UUID | None): Config to fail over to.
        fallback_config_name (str | None): Name of the fail-over config.
        timeout_seconds (int | None): Per-request provider timeout.
        provider_options (dict[str, Any] | None): Stored generation options;
            ``None`` means the provider's defaults.
        max_requests_per_minute (int | None): Rate limit, if any.
        max_tokens_per_day (int | None): Daily token limit, if any.
        referencing_operator_count (int): Operators bound to this config.
    """

    id: UUID
    config_name: str | None = None
    provider_type: str | None = None
    endpoint_url: str | None = None
    api_key_masked: str | None = None
    model_name: str | None = None
    status: str | None = None
    fallback_to_ragnerock: bool = False
    fallback_ai_config_id: UUID | None = None
    fallback_config_name: str | None = None
    timeout_seconds: int | None = None
    provider_options: dict[str, Any] | None = None
    max_requests_per_minute: int | None = None
    max_tokens_per_day: int | None = None
    referencing_operator_count: int = 0


class ListAIConfigsResponse(_ApiModel):
    """The account's AI provider configs."""

    configs: list[AIConfigDetail] = []
    total: int = 0
    skip: int = 0
    limit: int = 0


class CreateAIConfigResponse(_ApiModel):
    """Result of creating an AI provider config."""

    id: UUID
    config_name: str | None = None
    message: str | None = None


class UpdateAIConfigResponse(_ApiModel):
    """Result of updating an AI provider config."""

    id: UUID
    message: str | None = None


class SetAIConfigStatusResponse(_ApiModel):
    """Result of a status transition.

    The ``*_referencing`` counts are filled in when disabling, so callers can
    warn about what will stop working.

    Attributes:
        id (UUID): Config id.
        status (str | None): The new :class:`AIConfigStatus` value.
        message (str | None): Human-readable outcome.
        operators_referencing (int | None): Operators bound to the config.
        snapshots_referencing (int | None): Of those, how many are copies
            held by published endpoints.
        fallbacks_referencing (int | None): Configs that fail over to this
            one.
    """

    id: UUID
    status: str | None = None
    message: str | None = None
    operators_referencing: int | None = None
    snapshots_referencing: int | None = None
    fallbacks_referencing: int | None = None


class SelectableAIConfig(_ApiModel):
    """A config an operator may be bound to (no endpoint or key details)."""

    id: UUID
    config_name: str | None = None
    provider_type: str | None = None
    model_name: str | None = None
    status: str | None = None
    supports_reasoning_effort: bool = False


class ListSelectableAIConfigsResponse(_ApiModel):
    """Configs an operator may be bound to, default first."""

    configs: list[SelectableAIConfig] = []


# -- embedding config ----------------------------------------------------------


class EmbeddingConfigDetail(_ApiModel):
    """The account's own embedding provider. The key itself is never returned.

    Attributes:
        embedding_type (str | None): An
            :class:`~ragnerock.enums.EmbeddingModelType` value.
        endpoint (str | None): Provider endpoint.
        model (str | None): Provider model identifier.
        dimensions (int | None): Output vector size.
        api_key_masked (str | None): Masked hint of the stored key.
        updated_at (datetime | None): Last change.
    """

    embedding_type: str | None = None
    endpoint: str | None = None
    model: str | None = None
    dimensions: int | None = None
    api_key_masked: str | None = None
    updated_at: UtcDatetime = None


class EmbeddingConfigResponse(_ApiModel):
    """The account's embedding config.

    Attributes:
        config (EmbeddingConfigDetail | None): The account's own provider, or
            ``None`` when it uses Ragnerock's embeddings.
        account_has_embeddings (bool): Whether embedded documents exist, in
            which case a change needs ``regenerate_embeddings=True``.
    """

    config: EmbeddingConfigDetail | None = None
    account_has_embeddings: bool = False


class EmbeddingConfigChangeResponse(_ApiModel):
    """Result of saving or removing the embedding config.

    Attributes:
        message (str | None): Human-readable outcome.
        regeneration_id (UUID | None): Set when the change started an
            embedding regeneration.
    """

    message: str | None = None
    regeneration_id: UUID | None = None


class RegenerationDetail(_ApiModel):
    """Progress of an account-wide embedding regeneration.

    Attributes:
        id (UUID): Regeneration id.
        status (str | None): A :class:`RegenerationStatus` value.
        old_embedding_type (str | None): Provider family being replaced.
        old_embedding_model (str | None): Model being replaced.
        old_embedding_dimensions (int | None): Vector size being replaced.
        new_embedding_type (str | None): Provider family being moved to.
        new_embedding_model (str | None): Model being moved to.
        new_embedding_dimensions (int | None): Vector size being moved to.
        jobs_total (int): Re-embedding jobs started.
        jobs_completed (int): Jobs finished successfully.
        jobs_failed (int): Jobs that failed.
        error_message (str | None): Why the regeneration failed, if it did.
        created_at (datetime | None): When it started.
        updated_at (datetime | None): Last progress update.
        completed_at (datetime | None): When it finished.
    """

    id: UUID
    status: str | None = None
    old_embedding_type: str | None = None
    old_embedding_model: str | None = None
    old_embedding_dimensions: int | None = None
    new_embedding_type: str | None = None
    new_embedding_model: str | None = None
    new_embedding_dimensions: int | None = None
    jobs_total: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    error_message: str | None = None
    created_at: UtcDatetime = None
    updated_at: UtcDatetime = None
    completed_at: UtcDatetime = None


# -- image summary config ------------------------------------------------------


class ImageSummaryConfigDetail(_ApiModel):
    """The account's own image-summary provider. The key is never returned.

    Attributes:
        provider_type (str | None): An
            :class:`~ragnerock.enums.AIProviderType` value.
        endpoint (str | None): Provider endpoint.
        model (str | None): Vision model identifier.
        api_key_masked (str | None): Masked hint of the stored key.
        updated_at (datetime | None): Last change.
    """

    provider_type: str | None = None
    endpoint: str | None = None
    model: str | None = None
    api_key_masked: str | None = None
    updated_at: UtcDatetime = None


class ImageSummaryConfigResponse(_ApiModel):
    """The account's image-summary config.

    Attributes:
        config (ImageSummaryConfigDetail | None): The account's own provider,
            or ``None`` when it uses Ragnerock's.
    """

    config: ImageSummaryConfigDetail | None = None


class ImageSummaryConfigChangeResponse(_ApiModel):
    """Result of saving or removing the image-summary config."""

    message: str | None = None


# -- sections ------------------------------------------------------------------


class _AIConfigsSection(_Section):
    """Bring-your-own AI provider configs (``/api/ai-configs/...``)."""

    def create(
        self,
        *,
        provider_type: str,
        endpoint_url: str,
        api_key: str,
        config_name: str | None = None,
        model_name: str | None = None,
        fallback_to_ragnerock: bool = False,
        fallback_ai_config_id: UUID | None = None,
        timeout_seconds: int = 120,
        max_requests_per_minute: int | None = None,
        max_tokens_per_day: int | None = None,
        agent_turn_token_budget: int | None = None,
        assignment_token_budget: int | None = None,
        assignment_max_turns: int | None = None,
        assignment_max_age_days: int | None = None,
        assignment_retention_days: int | None = None,
        provider_options: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> CreateAIConfigResponse:
        """Create an AI provider config.

        Calls ``POST /api/ai-configs/``. The server tests the provider live
        before saving, so this waits up to :data:`AI_CONFIG_VALIDATE_TIMEOUT`.
        Embeddings and image summaries are configured separately
        (``client.embedding_config`` and ``client.image_summary_config``).

        The budget and assignment overrides take effect only on the account's
        default config; ``None`` inherits the platform defaults.

        Args:
            provider_type (str): An :class:`~ragnerock.enums.AIProviderType`
                value.
            endpoint_url (str): Provider API endpoint.
            api_key (str): Provider API key; stored encrypted.
            config_name (str | None): Friendly name.
            model_name (str | None): Model to call.
            fallback_to_ragnerock (bool): Fall back to Ragnerock's models when
                the provider errors.
            fallback_ai_config_id (UUID | None): Another of the account's
                configs to fail over to. It must not be disabled or form a
                cycle.
            timeout_seconds (int): Per-request provider timeout (10-300).
            max_requests_per_minute (int | None): Rate limit.
            max_tokens_per_day (int | None): Daily token limit.
            agent_turn_token_budget (int | None): Notebook agent's per-turn
                budget, in cost-weighted tokens (at least 1000).
            assignment_token_budget (int | None): What one agent assignment
                may spend, in cost-weighted tokens (at least 1000).
            assignment_max_turns (int | None): Turns one assignment may take.
            assignment_max_age_days (int | None): Days one assignment may run
                (at most 365).
            assignment_retention_days (int | None): Days a finished
                assignment's transcript is kept (at most 3650).
            provider_options (dict[str, Any] | None): Generation options.
                ``"type"`` must name the same provider as ``provider_type``;
                every other key is optional. All providers accept
                ``temperature`` and ``top_p``; Gemini also takes
                ``thinking_level``, ``thinking_budget``, ``safety_threshold``
                and ``top_k``; OpenAI takes ``reasoning_effort``; Anthropic
                takes ``thinking_budget_tokens``, ``top_k`` and
                ``max_output_tokens``; Oracle takes ``max_output_tokens``.
                ``None`` keeps the provider's defaults.
            status (str | None): An :class:`AIConfigStatus` value. Omitted
                means ``"active"``: selectable, but not the account default.

        Returns:
            CreateAIConfigResponse: The new config's id.

        Raises:
            RagnerockError: If the provider test fails or the server rejects
                the settings.
        """
        body = _body(
            provider_type=provider_type,
            endpoint_url=endpoint_url,
            api_key=api_key,
            config_name=config_name,
            model_name=model_name,
            fallback_to_ragnerock=fallback_to_ragnerock,
            fallback_ai_config_id=fallback_ai_config_id,
            timeout_seconds=timeout_seconds,
            max_requests_per_minute=max_requests_per_minute,
            max_tokens_per_day=max_tokens_per_day,
            agent_turn_token_budget=agent_turn_token_budget,
            assignment_token_budget=assignment_token_budget,
            assignment_max_turns=assignment_max_turns,
            assignment_max_age_days=assignment_max_age_days,
            assignment_retention_days=assignment_retention_days,
            provider_options=provider_options,
            status=status,
        )
        response = self._parent._request(
            "POST",
            "/api/ai-configs/",
            json_body=body,
            timeout=AI_CONFIG_VALIDATE_TIMEOUT,
        )
        return CreateAIConfigResponse.model_validate(response.json())

    def list(self) -> ListAIConfigsResponse:
        """List the account's AI provider configs.

        Calls ``GET /api/ai-configs/``.

        Returns:
            ListAIConfigsResponse: Every config, with masked keys.
        """
        response = self._parent._request("GET", "/api/ai-configs/")
        return ListAIConfigsResponse.model_validate(response.json())

    def get(self, config_id: UUID) -> AIConfigDetail:
        """Fetch one AI provider config by id.

        Calls ``GET /api/ai-configs/``. The API has no single-config read, so
        this lists the account's configs and picks the match.

        Args:
            config_id (UUID): Config to fetch.

        Returns:
            AIConfigDetail: The config.

        Raises:
            NotFoundError: If the account has no config with that id.
        """
        for config in self.list().configs:
            if str(config.id) == str(config_id):
                return config
        raise NotFoundError(f"AI config {config_id} not found", status_code=404)

    def update(
        self,
        config_id: UUID,
        *,
        config_name: str | None = None,
        provider_type: str | None = None,
        endpoint_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        fallback_to_ragnerock: bool | None = None,
        timeout_seconds: int | None = None,
        max_requests_per_minute: int | None = None,
        max_tokens_per_day: int | None = None,
        agent_turn_token_budget: int | None = None,
        assignment_token_budget: int | None = None,
        assignment_max_turns: int | None = None,
        assignment_max_age_days: int | None = None,
        assignment_retention_days: int | None = None,
        fallback_ai_config_id: Any = UNSET,
        provider_options: Any = UNSET,
    ) -> UpdateAIConfigResponse:
        """Update an AI provider config; omitted fields are left unchanged.

        Calls ``PUT /api/ai-configs/{config_id}``. The server re-tests the
        provider, so this waits up to :data:`AI_CONFIG_VALIDATE_TIMEOUT`.

        For most fields ``None`` means "leave unchanged", so the budget and
        limit overrides can't be cleared here. ``fallback_ai_config_id`` and
        ``provider_options`` default to :data:`~ragnerock.client.UNSET`
        instead: omit them to leave the stored value alone, or pass ``None``
        to clear it.

        Args:
            config_id (UUID): Config to update.
            config_name (str | None): New friendly name.
            provider_type (str | None): New
                :class:`~ragnerock.enums.AIProviderType` value.
            endpoint_url (str | None): New endpoint.
            api_key (str | None): New API key; stored encrypted.
            model_name (str | None): New model.
            fallback_to_ragnerock (bool | None): New fall-back setting.
            timeout_seconds (int | None): New provider timeout (10-300).
            max_requests_per_minute (int | None): New rate limit.
            max_tokens_per_day (int | None): New daily token limit.
            agent_turn_token_budget (int | None): New per-turn budget.
            assignment_token_budget (int | None): New assignment budget.
            assignment_max_turns (int | None): New assignment turn cap.
            assignment_max_age_days (int | None): New assignment age cap.
            assignment_retention_days (int | None): New transcript retention.
            fallback_ai_config_id (UUID | None): New fail-over config (not
                this one, not disabled, no cycle); ``None`` removes it.
            provider_options (dict[str, Any] | None): New generation options
                (see :meth:`create`); ``None`` restores the provider's
                defaults.

        Returns:
            UpdateAIConfigResponse: The outcome.

        Raises:
            RagnerockError: If the provider test fails or the server rejects
                the settings.
        """
        body = _body(
            config_name=config_name,
            provider_type=provider_type,
            endpoint_url=endpoint_url,
            api_key=api_key,
            model_name=model_name,
            fallback_to_ragnerock=fallback_to_ragnerock,
            timeout_seconds=timeout_seconds,
            max_requests_per_minute=max_requests_per_minute,
            max_tokens_per_day=max_tokens_per_day,
            agent_turn_token_budget=agent_turn_token_budget,
            assignment_token_budget=assignment_token_budget,
            assignment_max_turns=assignment_max_turns,
            assignment_max_age_days=assignment_max_age_days,
            assignment_retention_days=assignment_retention_days,
        )
        body.update(
            _patch_body(
                fallback_ai_config_id=fallback_ai_config_id,
                provider_options=provider_options,
            )
        )
        response = self._parent._request(
            "PUT",
            f"/api/ai-configs/{config_id}",
            json_body=body,
            timeout=AI_CONFIG_VALIDATE_TIMEOUT,
        )
        return UpdateAIConfigResponse.model_validate(response.json())

    def delete(self, config_id: UUID) -> None:
        """Delete an AI provider config.

        Calls ``DELETE /api/ai-configs/{config_id}``.

        Args:
            config_id (UUID): Config to delete.

        Raises:
            RagnerockError: If the server refuses, e.g. because another config
                fails over to this one.
        """
        self._parent._request("DELETE", f"/api/ai-configs/{config_id}")

    def set_status(self, config_id: UUID, *, status: str) -> SetAIConfigStatusResponse:
        """Move a config between ``default``, ``active`` and ``disabled``.

        Calls ``PUT /api/ai-configs/{config_id}/status``. Promoting a config
        to ``default`` demotes the current default to ``active``. Operators
        bound to a disabled config fail at run time until re-pointed; the
        response counts them.

        Args:
            config_id (UUID): Config to transition.
            status (str): Target :class:`AIConfigStatus` value.

        Returns:
            SetAIConfigStatusResponse: The new status, plus reference counts
            when disabling.
        """
        response = self._parent._request(
            "PUT",
            f"/api/ai-configs/{config_id}/status",
            json_body=_body(status=status),
            timeout=AI_CONFIG_VALIDATE_TIMEOUT,
        )
        return SetAIConfigStatusResponse.model_validate(response.json())

    def list_selectable(self) -> ListSelectableAIConfigsResponse:
        """List the configs an operator may be bound to, default first.

        Calls ``GET /api/ai-configs/selectable``. Open to any account member;
        the listing carries no endpoints, key hints or limits.

        Returns:
            ListSelectableAIConfigsResponse: The selectable configs.
        """
        response = self._parent._request("GET", "/api/ai-configs/selectable")
        return ListSelectableAIConfigsResponse.model_validate(response.json())


class _EmbeddingConfigSection(_Section):
    """The account's embedding provider (``/api/embedding-config``).

    One per account. Without one, the account uses Ragnerock's embeddings.
    """

    def get(self) -> EmbeddingConfigResponse:
        """Fetch the account's embedding config.

        Calls ``GET /api/embedding-config``.

        Returns:
            EmbeddingConfigResponse: The config (``config`` is ``None`` for
            Ragnerock's embeddings) and whether the account already has
            embeddings.
        """
        response = self._parent._request("GET", "/api/embedding-config")
        return EmbeddingConfigResponse.model_validate(response.json())

    def put(
        self,
        *,
        embedding_type: str,
        endpoint: str,
        model: str,
        dimensions: int,
        api_key: str | None = None,
        regenerate_embeddings: bool = False,
    ) -> EmbeddingConfigChangeResponse:
        """Create or replace the account's embedding config.

        Calls ``PUT /api/embedding-config``. The server tests the settings
        live before saving, so this waits up to
        :data:`AI_CONFIG_VALIDATE_TIMEOUT`. For Azure OpenAI, ``model`` is the
        deployment name of your embedding model.

        Args:
            embedding_type (str): An
                :class:`~ragnerock.enums.EmbeddingModelType` value.
            endpoint (str): Provider endpoint.
            model (str): Provider model identifier.
            dimensions (int): Output vector size.
            api_key (str | None): Provider key; omit to keep the stored one.
            regenerate_embeddings (bool): Confirm regenerating every existing
                embedding when the change alters the vector space. Required
                once the account has embeddings.

        Returns:
            EmbeddingConfigChangeResponse: The outcome, with the regeneration
            id when one started.

        Raises:
            RagnerockError: If the provider test fails, or the change needs
                ``regenerate_embeddings=True``.
        """
        body = _body(
            embedding_type=embedding_type,
            endpoint=endpoint,
            model=model,
            dimensions=dimensions,
            api_key=api_key,
            regenerate_embeddings=regenerate_embeddings,
        )
        response = self._parent._request(
            "PUT",
            "/api/embedding-config",
            json_body=body,
            timeout=AI_CONFIG_VALIDATE_TIMEOUT,
        )
        return EmbeddingConfigChangeResponse.model_validate(response.json())

    def delete(
        self, *, regenerate_embeddings: bool = False
    ) -> EmbeddingConfigChangeResponse:
        """Return the account to Ragnerock's embeddings.

        Calls ``DELETE /api/embedding-config``. The opt-in travels in a JSON
        body.

        Args:
            regenerate_embeddings (bool): Confirm regenerating every existing
                embedding with Ragnerock's model. Required once the account
                has embeddings.

        Returns:
            EmbeddingConfigChangeResponse: The outcome, with the regeneration
            id when one started.
        """
        response = self._parent._request(
            "DELETE",
            "/api/embedding-config",
            json_body={"regenerate_embeddings": regenerate_embeddings},
        )
        return EmbeddingConfigChangeResponse.model_validate(response.json())

    def latest_regeneration(self) -> RegenerationDetail:
        """Fetch the account's most recent embedding regeneration.

        Calls ``GET /api/embedding-config/regenerations/latest``.

        Returns:
            RegenerationDetail: Its status and progress counters.

        Raises:
            NotFoundError: If the account has never regenerated embeddings.
        """
        response = self._parent._request(
            "GET", "/api/embedding-config/regenerations/latest"
        )
        return RegenerationDetail.model_validate(response.json())


class _ImageSummaryConfigSection(_Section):
    """The account's image-summary provider (``/api/image-summary-config``).

    One per account. Without one, the account uses Ragnerock's summarizer.
    """

    def get(self) -> ImageSummaryConfigResponse:
        """Fetch the account's image-summary config.

        Calls ``GET /api/image-summary-config``.

        Returns:
            ImageSummaryConfigResponse: The config; its ``config`` is ``None``
            when the account uses Ragnerock's summarizer.
        """
        response = self._parent._request("GET", "/api/image-summary-config")
        return ImageSummaryConfigResponse.model_validate(response.json())

    def put(
        self,
        *,
        provider_type: str,
        endpoint: str,
        model: str,
        api_key: str | None = None,
    ) -> ImageSummaryConfigChangeResponse:
        """Create or replace the account's image-summary config.

        Calls ``PUT /api/image-summary-config``. The server tests the settings
        live before saving, so this waits up to
        :data:`AI_CONFIG_VALIDATE_TIMEOUT`.

        Args:
            provider_type (str): A vision-capable
                :class:`~ragnerock.enums.AIProviderType` value (``gemini``,
                ``openai``, ``azure_openai`` or ``anthropic``).
            endpoint (str): Provider endpoint.
            model (str): Vision model identifier.
            api_key (str | None): Provider key; omit to keep the stored one.

        Returns:
            ImageSummaryConfigChangeResponse: The outcome.

        Raises:
            RagnerockError: If the provider test fails.
        """
        body = _body(
            provider_type=provider_type,
            endpoint=endpoint,
            model=model,
            api_key=api_key,
        )
        response = self._parent._request(
            "PUT",
            "/api/image-summary-config",
            json_body=body,
            timeout=AI_CONFIG_VALIDATE_TIMEOUT,
        )
        return ImageSummaryConfigChangeResponse.model_validate(response.json())

    def delete(self) -> ImageSummaryConfigChangeResponse:
        """Return the account to Ragnerock's image summaries.

        Calls ``DELETE /api/image-summary-config``.

        Returns:
            ImageSummaryConfigChangeResponse: The outcome.
        """
        response = self._parent._request("DELETE", "/api/image-summary-config")
        return ImageSummaryConfigChangeResponse.model_validate(response.json())
