"""Wire enums for API areas the session layer doesn't model.

Client methods accept either these members or their plain string values.
Enums tied to a session resource (``ChunkType``, ``OperatorKind``,
``DocumentStatus``, ...) live with that resource in :mod:`ragnerock.resources`.
"""

from __future__ import annotations

from enum import StrEnum


class AIProviderType(StrEnum):
    """LLM providers an AI provider config can point at."""

    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    GROK = "grok"
    ORACLE = "oracle"


class EmbeddingModelType(StrEnum):
    """Embedding providers the account's embedding config can point at."""

    GEMINI = "gemini"
    ORACLE = "oracle"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"


class IngestSourceType(StrEnum):
    """Kinds of ingest source."""

    WEB_SCRAPE = "WEB_SCRAPE"
    """Crawl or fetch web pages."""

    S3 = "S3"
    """Sync objects from an S3-compatible bucket."""

    SQL = "SQL"
    """Materialize the result of a SQL query as a document table."""


class IngestRunStatus(StrEnum):
    """Lifecycle of one ingest run."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    APPLYING = "APPLYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IngestRunTrigger(StrEnum):
    """What started an ingest run."""

    MANUAL = "MANUAL"
    SCHEDULE = "SCHEDULE"


class CompatFormat(StrEnum):
    """Client wire format served by a model-compatibility endpoint."""

    OPENAI = "OPENAI"
    ANTHROPIC = "ANTHROPIC"
    GEMINI = "GEMINI"
