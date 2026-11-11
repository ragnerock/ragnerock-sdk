"""Task resource."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from ragnerock.resources.base import OptionalDateTime, _Resource
from ragnerock.resources.chunk import ChunkType


class TaskKind(StrEnum):
    """How a task produces its output. Always explicit on the wire."""

    LLM = "LLM"
    """An LLM annotation driven by ``generation_prompt``."""

    CODE = "CODE"
    """A Python snippet (``code_source``) run in a sandbox."""

    MANUAL = "MANUAL"
    """No automated producer; annotations are supplied by hand."""

    OUTPUT = "OUTPUT"
    """An agent output's own task. Managed through the agent's outputs,
    never directly."""


class Task(_Resource):
    """An annotation task: an output schema plus how to produce it.

    Tasks define how annotations are generated. Their ``name`` becomes a
    queryable table on :meth:`~ragnerock.session.Session.query`, and their
    ``jsonschema`` constrains the :class:`~ragnerock.resources.annotation.Annotation`
    payloads the task emits.

    ``task_kind`` selects the producer and decides which other fields
    apply: an :attr:`TaskKind.LLM` task needs ``generation_prompt``, a
    :attr:`TaskKind.CODE` task needs ``code_source``, and so on.
    """

    id: UUID | None = None
    project_id: UUID | None = None
    name: str | None = None
    description: str | None = None
    task_kind: TaskKind = TaskKind.LLM
    jsonschema: dict[str, Any] | None = None
    output_schema_id: UUID | None = None
    schema_name: str | None = None
    generation_prompt: str | None = None
    chunk_type: ChunkType | None = None
    batch_size: int | None = None
    input_columns: list[str] | None = None
    multi_annotation: bool = False
    code_source: str | None = None
    network_access: bool = False
    code_timeout_seconds: int | None = None
    ai_config_id: UUID | None = None
    model_name: str | None = None
    skill_ids: list[UUID] | None = None
    tool_ids: list[UUID] | None = None
    is_snapshot: bool = False
    warnings: list[str] = []
    created_at: OptionalDateTime = None
    updated_at: OptionalDateTime = None
