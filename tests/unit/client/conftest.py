"""Fixtures for low-level client section tests.

Tests drive ``RagnerockClient`` sections directly against ``pytest-httpx``
mocks and assert on the outgoing requests.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from ragnerock.client import RagnerockClient
from tests.unit.conftest import TEST_HOST

PROJECT_ID = "00000000-0000-0000-0000-000000000001"
"""A project id for path parameters."""


@pytest.fixture
def client() -> Iterator[RagnerockClient]:
    """A client authenticated with a static token against the test host."""
    with RagnerockClient(host=TEST_HOST, auth_token="rgnk_test") as c:
        yield c


def url(path: str) -> str:
    """Return the absolute test URL for an API path."""
    return f"{TEST_HOST}{path}"


def last_request(httpx_mock: Any) -> httpx.Request:
    """Return the most recent request the mock received."""
    requests = httpx_mock.get_requests()
    assert requests, "no request was sent"
    return requests[-1]


def last_json(httpx_mock: Any) -> Any:
    """Return the decoded JSON body of the most recent request."""
    return json.loads(last_request(httpx_mock).content)


def last_params(httpx_mock: Any) -> dict[str, str]:
    """Return the query parameters of the most recent request (last value wins)."""
    return dict(last_request(httpx_mock).url.params)
