"""Operator resource."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from ragnerock.resources.base import _Resource
from ragnerock.resources.chunk import ChunkType


class Operator(_Resource):
    """An annotation operator: a JSON schema + LLM prompt that produces annotations.

    Operators define how annotations are generated. Their ``name`` becomes a
    queryable table in ``session.query(...)``.

    Attributes:
        id: Server-assigned UUID. ``None`` until committed.
        project_id: Owning project.
        name: Unique identifier used as the query table name.
        description: Human-readable description.
        jsonschema: JSON Schema describing the shape of each annotation.
        generation_prompt: LLM prompt used to produce annotations.
        chunk_type: Scope at which this operator runs (DOCUMENT / PAGE / …).
        batch_size: Batch size for annotation generation, if any.
        multi_annotation: Whether the operator may produce multiple annotations
            per input chunk.
        created_at: Creation timestamp.
    """

    id: UUID | None = None
    project_id: UUID | None = None
    name: str | None = None
    description: str | None = None
    jsonschema: dict[str, Any] | None = None
    generation_prompt: str | None = None
    chunk_type: ChunkType | None = None
    batch_size: int | None = None
    multi_annotation: bool = False
    created_at: datetime | None = None
