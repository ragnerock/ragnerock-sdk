# Queries

`session.query(sql)` runs SQL over annotations produced by your operators.

## Tables available

| Table | What it holds |
|---|---|
| `documents` / `document` | Document metadata (id, name, file_type, created_at, …). |
| `chunks` / `documentchunk` | Chunk content and offsets. |
| *`{operator_name}`* | One row per annotation produced by that operator, columns matching the operator's JSON schema. |

So an operator named `invoice_extract` with a schema `{"total": number, "vendor": string}` becomes a queryable table:

```sql
SELECT vendor, SUM(total) AS total_owed
FROM invoice_extract
GROUP BY vendor
ORDER BY total_owed DESC
```

## Running a query

```python
result = session.query("SELECT vendor, total FROM invoice_extract WHERE total > 1000")

result.row_count          # int
result.columns            # ['vendor', 'total']
result.to_dict()          # [{'vendor': 'Acme', 'total': 1234.56}, ...]
result.query_time_ms      # int or None
```

### To pandas

```python
df = result.to_pandas()
```

Requires the optional `pandas` extra:

```bash
pip install 'ragnerock[pandas]'
```

If pandas isn't installed, `to_pandas()` raises `ImportError`.

## Limits

```python
result = session.query("SELECT * FROM invoice_extract", limit=5000)
```

Default limit is `1000` with a max of `500000`.

## Errors

Query failures raise `QueryError`, which carries a structured `error_code` when the API provides one:

```python
from ragnerock import QueryError

try:
    result = session.query("SELEKT * FROM invoice_extract")
except QueryError as e:
    print(e.error_code)   # e.g. "SYNTAX_ERROR"
    print(e.suggestion)   # e.g. "Did you mean SELECT?"
```

See [errors.md](errors.md) for the full error hierarchy.
