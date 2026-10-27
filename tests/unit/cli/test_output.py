"""Tests for CLI output formatters."""

from __future__ import annotations

import io
import json
from uuid import UUID

import yaml

from ragnerock.cli.output import OutputFormat, render
from ragnerock.cli.resources import resolve_kind
from ragnerock.resources import ChunkType, Operator


def _sample_operator() -> Operator:
    return Operator(
        id=UUID("00000000-0000-0000-0000-000000000601"),
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
        name="sentiment",
        description="Classify sentiment",
        jsonschema={"type": "object"},
        generation_prompt="Classify...",
        chunk_type=ChunkType.PARAGRAPH,
        batch_size=16,
        multi_annotation=False,
    )


def test_json_output_is_valid_json_array() -> None:
    spec = resolve_kind("operator")
    stream = io.StringIO()
    render([_sample_operator()], spec, OutputFormat.JSON, stream=stream)
    parsed = json.loads(stream.getvalue())
    assert isinstance(parsed, list)
    assert parsed[0]["name"] == "sentiment"


def test_yaml_output_is_a_plain_field_dump() -> None:
    spec = resolve_kind("operator")
    stream = io.StringIO()
    render([_sample_operator()], spec, OutputFormat.YAML, stream=stream)
    doc = yaml.safe_load(stream.getvalue())
    assert "apiVersion" not in doc
    assert doc["name"] == "sentiment"
    assert doc["generation_prompt"] == "Classify..."
    assert doc["operator_kind"] == "LLM"


def test_yaml_multiple_items_emits_multi_doc() -> None:
    spec = resolve_kind("operator")
    a = _sample_operator()
    b = _sample_operator()
    b.name = "other"
    stream = io.StringIO()
    render([a, b], spec, OutputFormat.YAML, stream=stream)
    docs = list(yaml.safe_load_all(stream.getvalue()))
    assert [d["name"] for d in docs] == ["sentiment", "other"]


def test_name_format_prints_one_per_line() -> None:
    spec = resolve_kind("operator")
    a = _sample_operator()
    b = _sample_operator()
    b.name = "other"
    stream = io.StringIO()
    render([a, b], spec, OutputFormat.NAME, stream=stream)
    assert stream.getvalue().splitlines() == ["sentiment", "other"]


def test_table_empty_shows_placeholder() -> None:
    spec = resolve_kind("operator")
    stream = io.StringIO()
    render([], spec, OutputFormat.TABLE, stream=stream)
    assert "No Operator resources" in stream.getvalue()
