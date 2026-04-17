"""Result wrapper for annotation SQL queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


class QueryResult:
    """Result of ``session.query(...)``.

    Attributes:
        columns: Column names in the result set.
        data: Rows as a list of dicts (one per row).
        row_count: Number of rows returned.
        query_time_ms: Server-reported execution time, if available.
    """

    def __init__(
        self,
        *,
        columns: list[str],
        data: list[dict[str, Any]],
        row_count: int,
        query_time_ms: int | None = None,
    ) -> None:
        self.columns = columns
        self.data = data
        self.row_count = row_count
        self.query_time_ms = query_time_ms

    def to_dict(self) -> list[dict[str, Any]]:
        """Return the results as a list of dicts (one per row)."""
        return self.data

    def to_pandas(self) -> pd.DataFrame:
        """Convert to a pandas DataFrame. Requires ``pandas`` to be installed."""
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas is required for QueryResult.to_pandas(). "
                "Install it with: pip install 'ragnerock[pandas]'"
            ) from e
        return pd.DataFrame(self.data, columns=self.columns)

    def __len__(self) -> int:
        return self.row_count

    def __repr__(self) -> str:
        return (
            f"QueryResult(columns={self.columns!r}, "
            f"row_count={self.row_count}, "
            f"query_time_ms={self.query_time_ms})"
        )
