# Operators

Operators define how annotations are generated: a JSON schema + an LLM prompt. Their `name` also becomes a queryable table in `session.query(...)`.

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
