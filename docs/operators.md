# Operators

Operators define how annotations are generated: a JSON schema + an LLM prompt. Their `name` also becomes a queryable table in `session.query(...)`.

## Creating

```python
from ragnerock import Operator, ChunkType

op = Operator(
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
session.add(op)
session.commit()
```

## Getting

```python
op = session.get(Operator, id="...")
op = session.get(Operator, name="invoice_extract")
```

The API has no get-by-name endpoint, so `get(Operator, name=...)` lists and filters client-side.

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
