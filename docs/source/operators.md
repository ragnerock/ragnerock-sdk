# Operators

Operators — called *agents* in the Ragnerock app and in [GitOps manifests](gitops.md) — define how annotations are generated: an output JSON schema plus a producer. Their `name` also becomes a queryable table in `session.query(...)`.

The producer is set by `operator_kind` (an `OperatorKind`):

| Kind | Produces annotations from | Required field |
| --- | --- | --- |
| `LLM` (default) | an LLM prompt | `generation_prompt` |
| `CODE` | a Python snippet defining `main()`, run in a sandbox | `code_source` |
| `MESSAGE` | a message template rendered from upstream results | `notification_template` |
| `CHANGE_REQUEST` | a signal that files documents on the workflow's change request | `change_request_prompt` |
| `MANUAL` | nothing — annotations are supplied by hand | — |

## Creating

```python
from ragnerock import Operator, ChunkType

invoice_extract = Operator(
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

A code operator carries Python instead of a prompt. The server security-reviews the snippet when it's saved; never put credentials in it.

```python
from ragnerock import OperatorKind

ticker_extract = Operator(
    name="ticker_extract",
    operator_kind=OperatorKind.CODE,
    jsonschema={"type": "object", "properties": {"tickers": {"type": "array"}}},
    code_source=(
        "def main(content: str) -> dict:\n"
        "    return {'tickers': sorted({w for w in content.split() if w.isupper()})}\n"
    ),
    chunk_type=ChunkType.PARAGRAPH,
)
```

LLM operators can also pin a model (`ai_config_id`, `model_name`) and give the agent skills and tools (`skill_ids`, `tool_ids`); see [Platform APIs](platform.md) for managing those. Tabular operators (`ChunkType.ROW` / `SHEET`) can narrow the columns they see with `input_columns`.

## Getting

```python
my_operator = session.get(Operator, id="...")
my_operator = session.get(Operator, name="...")
```

## Listing

```python
ops = session.list(Operator).all()
```

## Updating

```python
op.generation_prompt = "... refined prompt ..."
session.update(op)
session.commit()
```

## Deleting

```python
session.delete(op)
session.commit()
```

Deleting an operator removes its annotations as well, server-side.
