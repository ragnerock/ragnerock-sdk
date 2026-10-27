"""Tests for :mod:`ragnerock.timestamps`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel

from ragnerock.timestamps import UtcDatetime


class _Model(BaseModel):
    at: UtcDatetime = None


class TestUtcDatetime:
    def test_z_suffix_parses_as_aware_utc(self):
        assert _Model(at="2026-04-16T12:00:00Z").at == datetime(
            2026, 4, 16, 12, tzinfo=UTC
        )

    def test_offset_is_normalized_to_utc(self):
        value = _Model(at="2026-04-16T14:00:00+02:00").at
        assert value is not None
        assert value.tzinfo is UTC
        assert value.hour == 12

    def test_naive_value_is_assumed_utc(self):
        value = _Model(at=datetime(2026, 4, 16, 12)).at
        assert value == datetime(2026, 4, 16, 12, tzinfo=UTC)

    @pytest.mark.parametrize("raw", [None, ""])
    def test_empty_values_become_none(self, raw):
        assert _Model(at=raw).at is None

    def test_aware_non_utc_datetime_is_converted(self):
        est = timezone(timedelta(hours=-5))
        value = _Model(at=datetime(2026, 4, 16, 7, tzinfo=est)).at
        assert value == datetime(2026, 4, 16, 12, tzinfo=UTC)
        assert value is not None and value.tzinfo is UTC
