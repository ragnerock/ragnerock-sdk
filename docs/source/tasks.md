# Tasks

A task defines how annotations are generated: an output JSON schema plus a producer. [Agents](agents.md) wire tasks into a graph, one task per node. A task's `name` also becomes a queryable table in `session.query(...)`.

The producer is set by `task_kind` (a `TaskKind`):

| Kind | Produces annotations from | Required field |
| --- | --- | --- |
| `LLM` (default) | an LLM prompt | `generation_prompt` |
| `CODE` | a Python snippet defining `main()`, run in a sandbox | `code_source` |
| `MANUAL` | nothing — annotations are supplied by hand | — |
| `OUTPUT` | an agent output; managed through the agent's outputs, never directly | — |

## Creating

```python
from ragnerock import ChunkType, Task

invoice_extract = Task(
    name="invoice_extract",
    description="Pull total, vendor, and due date from invoices",
    jsonschema={
        "type": "object",
        "properties": {
            "total": {"type": "number"},
            "vendor": {"type": "string"},
            "due_date": {"type": "string", "format": "date"},
        },
        "required": ["total", "vendor"],
    },
    generation_prompt="Extract the invoice total, vendor name, and due date...",
    chunk_type=ChunkType.DOCUMENT,
)
session.add(invoice_extract)
session.commit()
```

A code task carries Python instead of a prompt. The server security-reviews the snippet when it's saved; never put credentials in it.

```python
from ragnerock import TaskKind

ticker_extract = Task(
    name="ticker_extract",
    task_kind=TaskKind.CODE,
    jsonschema={"type": "object", "properties": {"tickers": {"type": "array"}}},
    code_source=(
        "def main(content: str) -> dict:\n"
        "    return {'tickers': sorted({w for w in content.split() if w.isupper()})}\n"
    ),
    chunk_type=ChunkType.PARAGRAPH,
)
```

LLM tasks can also pin a model (`ai_config_id`, `model_name`) and use skills and tools (`skill_ids`, `tool_ids`); see [Platform APIs](platform.md) for managing those. Tabular tasks (`ChunkType.ROW` / `SHEET`) can narrow the columns they see with `input_columns`.

## Getting

```python
my_task = session.get(Task, id="...")
my_task = session.get(Task, name="...")
```

## Listing

```python
tasks = session.list(Task).all()
```

## Updating

```python
my_task.generation_prompt = "... refined prompt ..."
session.update(my_task)
session.commit()
```

## Deleting

```python
session.delete(my_task)
session.commit()
```

Deleting a task also deletes its annotations on the server.
