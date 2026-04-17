# Annotations

Annotations are JSON payloads produced by operators, attached to a document, chunk, or page.

## Creating

Annotations require an operator and at least one attachment point (`document_id`, `chunk_id`, or `page_id`):

```python
from ragnerock import Annotation

a = Annotation(
    operator_id=operator.id,
    document_id=doc.id,
    data={"total": 1234.56, "vendor": "Acme Corp"},
    confidence_score=0.92,
)
session.add(a)
session.commit()
# a.root_id is now populated
```

## Getting

```python
a = session.get(Annotation, id=root_id)
```

## Listing

Annotations are always listed relative to something: a document, a chunk, or an operator.

```python
# All annotations on a document
session.list(Annotation, document_id=doc.id).all()

# Filtered to a single operator, by name
session.list(Annotation, document_id=doc.id, operator_name="invoice_extract").all()

# All annotations on a chunk
session.list(Annotation, chunk_id=chunk.id).all()

# All annotations a given operator has produced
session.list(Annotation, operator_id=op.id).all()
```

Also available as shortcut methods on the parent resource:

```python
doc.list(Annotation).all()
chunk.list(Annotation).all()
operator.list(Annotation).all()
operator.list(Annotation, document=doc).all()
```

## Hydrated listings

When you want the full annotation `data` blob (not just `root_id`s), pass `hydrated=True`:

```python
session.list(Annotation, operator_id=op.id, hydrated=True).all()
```

This hits `/api/annotations/operator/{id}/hydrated`, which batch-fetches annotation data efficiently.

## Updating

```python
a.data = {"total": 1300.00, "vendor": "Acme Corp"}
a.confidence_score = 0.95
session.update(a)
session.commit()
```

## Deleting

```python
session.delete(a)
session.commit()
```
