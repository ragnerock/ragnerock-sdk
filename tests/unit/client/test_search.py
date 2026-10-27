"""Tests for ``client.search``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from ragnerock.client import RagnerockClient
from ragnerock.client.search import ContentType
from ragnerock.errors import ValidationError
from tests.unit.client.conftest import PROJECT_ID, last_params, last_request, url


def _payload(query: str, **overrides: Any) -> dict[str, Any]:
    """A search response body."""
    body: dict[str, Any] = {
        "results": [],
        "total_results": 0,
        "query": query,
        "content_types_searched": [],
        "skip": 0,
        "limit": 10,
    }
    body.update(overrides)
    return body


def test_defaults_search_everything_without_regex(
    httpx_mock: Any, client: RagnerockClient
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=url("/api/search?query=earnings&limit=10&regex=false&content_types=all"),
        json=_payload("earnings"),
    )
    response = client.search.search(query="earnings")
    assert last_request(httpx_mock).method == "GET"
    assert "project_ids" not in last_params(httpx_mock)
    assert response.results == []
    assert response.query == "earnings"


def test_regex_and_project_are_sent_as_query_params(
    httpx_mock: Any, client: RagnerockClient
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=url(
            "/api/search?query=%5EINV-%5B0-9%5D%2B%24&limit=5&regex=true"
            f"&project_ids={PROJECT_ID}&content_types=all"
        ),
        json=_payload("^INV-[0-9]+$"),
    )
    client.search.search(
        project_id=UUID(PROJECT_ID), query="^INV-[0-9]+$", limit=5, regex=True
    )
    params = last_params(httpx_mock)
    assert params["query"] == "^INV-[0-9]+$"
    assert params["regex"] == "true"
    assert params["project_ids"] == PROJECT_ID


@pytest.mark.parametrize(
    ("content_types", "sent"),
    [
        (ContentType.ALL, "all"),
        (ContentType.DOCUMENTS | ContentType.CHUNKS, "documents,chunks"),
        (
            ContentType.ANNOTATIONS | ContentType.TABULAR_ROWS,
            "annotations,tabular_rows",
        ),
        ("documents|chats", "documents,chats"),
        ("documents,chunks", "documents,chunks"),
        (["chunks", "annotations"], "chunks,annotations"),
    ],
    ids=["all", "flags", "tabular", "pipes", "commas", "list"],
)
def test_content_types_are_sent_comma_separated(
    httpx_mock: Any,
    client: RagnerockClient,
    content_types: ContentType | str | list[str],
    sent: str,
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=url(f"/api/search?query=q&limit=10&regex=false&content_types={sent}"),
        json=_payload("q"),
    )
    client.search.search(query="q", content_types=content_types)
    assert last_params(httpx_mock)["content_types"] == sent


def test_results_parse(httpx_mock: Any, client: RagnerockClient) -> None:
    item_id = "00000000-0000-0000-0000-000000000201"
    httpx_mock.add_response(
        method="GET",
        url=url("/api/search?query=revenue&limit=10&regex=false&content_types=all"),
        json=_payload(
            "revenue",
            results=[
                {
                    "content_type": ContentType.CHUNKS.value,
                    "item_id": item_id,
                    "score": 0.82,
                    "source": "semantic",
                    "title": "q1-report",
                    "content_preview": "Revenue grew 12%...",
                    "metadata": {"document_id": "00000000-0000-0000-0000-000000000101"},
                }
            ],
            total_results=1,
            content_types_searched=["documents", "chunks"],
        ),
    )
    response = client.search.search(query="revenue")
    (hit,) = response.results
    assert hit.item_id == UUID(item_id)
    assert hit.content_type == ContentType.CHUNKS.value
    assert hit.score == 0.82
    assert hit.source == "semantic"
    assert hit.metadata == {"document_id": "00000000-0000-0000-0000-000000000101"}
    assert response.total_results == 1
    assert response.content_types_searched == ["documents", "chunks"]


def test_an_unusable_pattern_raises_validation_error(
    httpx_mock: Any, client: RagnerockClient
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=url(
            "/api/search?query=%28a%2B%29%5C1&limit=10&regex=true&content_types=all"
        ),
        status_code=422,
        json={"detail": "Invalid regex pattern: back-references are not supported"},
    )
    with pytest.raises(ValidationError, match="back-references"):
        client.search.search(query=r"(a+)\1", regex=True)
