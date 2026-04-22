"""Operator resource."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragnerock.resources.base import OptionalDateTime, _Resource
from ragnerock.resources.chunk import ChunkType


class Operator(_Resource):
    """An annotation operator: a JSON schema + LLM prompt that produces annotations.

    Operators define how annotations are generated. Their ``name`` becomes a
    queryable table on :meth:`~ragnerock.session.Session.query`, and their
    ``jsonschema`` constrains the :class:`~ragnerock.resources.annotation.Annotation`
    payloads the operator emits.
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
    created_at: OptionalDateTime = None
