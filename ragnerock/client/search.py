"""Search endpoint (``/api/search``)."""

from __future__ import annotations

from enum import Flag, auto
from typing import Any
from uuid import UUID

from ragnerock.client._base import _ApiModel, _Section


class ContentType(Flag):
    """What a search covers. Combine members with ``|``."""

    DOCUMENTS = auto()
    """Document names and metadata."""

    CHUNKS = auto()
    """Extracted document text."""

    CHATS = auto()
    """Notebook and conversation content."""

    ANNOTATIONS = auto()
    """Annotation values."""

    TABULAR_ROWS = auto()
    """Rows of spreadsheet and table documents."""

    ALL = DOCUMENTS | CHUNKS | CHATS | ANNOTATIONS | TABULAR_ROWS
    """Everything."""


_CONTENT_TYPE_NAMES: tuple[tuple[ContentType, str], ...] = (
    (ContentType.DOCUMENTS, "documents"),
    (ContentType.CHUNKS, "chunks"),
    (ContentType.CHATS, "chats"),
    (ContentType.ANNOTATIONS, "annotations"),
    (ContentType.TABULAR_ROWS, "tabular_rows"),
)


class SearchResults(_ApiModel):
    """One search hit.

    Attributes:
        item_id (UUID): The matching item (document, chunk, cell, ...).
        content_type (int | str | None): The kind of item, as the integer
            value of a :class:`ContentType` member.
        score (float | None): Relevance; unranked in regex mode.
        source (str | None): ``"keyword"`` or ``"semantic"``.
        title (str | None): A display title, such as the document name.
        content_preview (str | None): A snippet of the matching content.
        metadata (dict[str, Any] | None): Extra details about the item.
    """

    item_id: UUID
    content_type: int | str | None = None
    score: float | None = None
    source: str | None = None
    title: str | None = None
    content_preview: str | None = None
    metadata: dict[str, Any] | None = None


class SearchResponse(_ApiModel):
    """The results of a search, with what was searched."""

    results: list[SearchResults] = []
    total_results: int = 0
    query: str | None = None
    content_types_searched: list[str] = []
    skip: int = 0
    limit: int = 0


def _content_types_param(content_types: ContentType | str | list[str]) -> str:
    """Render ``content_types`` as the comma-separated query value.

    Args:
        content_types (ContentType | str | list[str]): A flag combination, a
            string such as ``"documents|chunks"`` or ``"documents,chunks"``,
            or a list of names.

    Returns:
        str: ``"all"`` or a comma-separated list of content type names.
    """
    if isinstance(content_types, ContentType):
        if content_types == ContentType.ALL:
            return "all"
        return ",".join(
            name for member, name in _CONTENT_TYPE_NAMES if member in content_types
        )
    if isinstance(content_types, str):
        return content_types.replace("|", ",")
    if isinstance(content_types, list):
        return ",".join(content_types)
    return "all"


class _SearchSection(_Section):
    """Keyword, semantic, and regex search across one or every project."""

    def search(
        self,
        *,
        project_id: UUID | None = None,
        query: str = "",
        limit: int = 10,
        content_types: ContentType | str | list[str] = ContentType.ALL,
        regex: bool = False,
    ) -> SearchResponse:
        """Search one project, or every project you can access.

        Calls ``GET /api/search``.

        Args:
            project_id (UUID | None): The project to search. ``None`` searches
                every project you have access to.
            query (str): The search text, or the pattern when ``regex`` is set.
            limit (int): Maximum number of results to return.
            content_types (ContentType | str | list[str]): What to search: a
                :class:`ContentType` combination, a string such as
                ``"documents|chunks"``, or a list such as
                ``["documents", "chunks"]``.
            regex (bool): Treat ``query`` as a case-insensitive regular
                expression that can match anywhere in the text. Only pattern
                matches come back, unranked, and semantic search is skipped.
                Back-references are not supported, and on Snowflake,
                Databricks, and Oracle databases neither is repeating a group
                that itself repeats, such as ``(a+)+``.

        Returns:
            SearchResponse: The matching results and the search metadata.

        Raises:
            ValidationError: If ``regex`` is set and ``query`` is not a usable
                pattern.
        """
        response = self._parent._request(
            "GET",
            "/api/search",
            params={
                "query": query,
                "limit": limit,
                "regex": regex,
                "project_ids": str(project_id) if project_id is not None else None,
                "content_types": _content_types_param(content_types),
            },
        )
        return SearchResponse.model_validate(response.json())
