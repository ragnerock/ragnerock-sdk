"""Result wrapper for annotation SQL queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


class QueryResult:
    """Result of ``session.query(...)``.

    Rows are held eagerly in memory. Access them via :attr:`data` (a list of
    column-keyed dicts), via :meth:`to_dict`, or convert to a DataFrame with
    :meth:`to_pandas`. Iterate rows directly by iterating :attr:`data`, and
    use ``len(result)`` to get the row count.

    Attributes:
        columns (list[str]): Column names in the result set, in server order.
        data (list[dict[str, Any]]): Rows as a list of dicts keyed by column
            name. Iterate this attribute to walk rows.
        row_count (int): Number of rows returned.
        query_time_ms (int | None): Server-reported execution time in
            milliseconds, if available.

    Example::

        result = session.query("SELECT id, name FROM annotations LIMIT 10")
        for row in result.data:
            print(row["name"])
        df = result.to_pandas()
    """

    def __init__(
        self,
        *,
        columns: list[str],
        data: list[dict[str, Any]],
        row_count: int,
        query_time_ms: int | None = None,
    ) -> None:
        """Initialize a query result.

        Args:
            columns (list[str]): Column names in server order.
            data (list[dict[str, Any]]): Rows as a list of dicts keyed by
                column name.
            row_count (int): Number of rows in ``data``.
            query_time_ms (int | None): Server-reported execution time in
                milliseconds, if the server included it.
        """
        self.columns = columns
        self.data = data
        self.row_count = row_count
        self.query_time_ms = query_time_ms

    def to_dict(self) -> list[dict[str, Any]]:
        """Return the rows as a list of column-keyed dicts.

        Returns:
            list[dict[str, Any]]: The same list of row dicts held by
            :attr:`data`.
        """
        return self.data

    def to_pandas(self) -> pd.DataFrame:
        """Convert the result to a pandas DataFrame.

        Returns:
            pd.DataFrame: A DataFrame whose column order matches
            :attr:`columns`.

        Raises:
            ImportError: If ``pandas`` is not installed. Install the optional
                extra with ``pip install 'ragnerock[pandas]'``.
        """
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
