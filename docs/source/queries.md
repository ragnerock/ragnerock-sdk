# Queries

`session.query(sql)` runs SQL over annotations produced by your [tasks](tasks.md).

## Tables available

| Table | What it holds |
|---|---|
| `documents` / `document` | Document metadata (id, name, file_type, document_folder_id, created_at, …). |
| `chunks` / `documentchunk` | Chunk content and offsets. |
| *`{task_name}`* | One row per annotation produced by that task, columns matching the task's JSON schema. |
| `_reviews` | Review decisions on annotations; `task_id` names the task whose output was reviewed. |

So a task named `invoice_extract` with a schema `{"total": number, "vendor": string}` becomes a queryable table:

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
result.truncated          # True if more rows matched than `limit` returned
```

Task tables (and `_reviews`) also carry a hidden `provenance_id` column: the run provenance behind each annotation, recording what the producing run pinned when it was created. It isn't returned by `SELECT *`, but you can select or filter on it by name. Before the 3.0 rename this column was called `run_id`; see [Migrating to 3.0](migration.md#sql-names) for the other SQL names that changed.

Pass `include_provenance=True` to also get, for each row, the documents, chunks, or annotations it was derived from, on `result.provenance`:

```python
result = session.query("SELECT vendor, total FROM invoice_extract", include_provenance=True)
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

## Saved queries

Save a query to the project to reuse it (and share it in the app) through the low-level client:

```python
saved = engine.client.queries.create(
    engine.project_id,
    name="Top vendors",
    query_sql="SELECT vendor, SUM(total) FROM invoice_extract GROUP BY vendor",
)
for q in engine.client.queries.list(project_ids=str(engine.project_id)).queries:
    print(q.name)
```
