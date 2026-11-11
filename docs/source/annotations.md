# Annotations

Annotations are JSON payloads produced by [tasks](tasks.md), attached to a document, chunk, or page. Each annotation records the task that produced it in `task_id` and `task_name`, and `annotation.task` loads that {class}`~ragnerock.resources.task.Task` lazily.

## Getting

```python
a = session.get(Annotation, id=root_id)
```

## Listing

Annotations are always listed relative to something: a document, a chunk, or a task.

```python
# All annotations on a document
session.list(Annotation, document_id=doc.id).all()

# Filtered to a single task, by name
session.list(Annotation, document_id=doc.id, task_name="invoice_extract").all()

# All annotations on a chunk
session.list(Annotation, chunk_id=chunk.id).all()

# All annotations a given task has produced
session.list(Annotation, task_id=my_task.id).all()
```

Also available as shortcut methods on the parent resource:

```python
doc.list(Annotation).all()
doc.list(Annotation, task=my_task).all()      # a Task or a task name
chunk.list(Annotation).all()
my_task.list(Annotation).all()
my_task.list(Annotation, document=doc).all()
```

## Hydrated listings

When you want the full annotation `data` blob (not just `root_id`s), pass `hydrated=True`:

```python
session.list(Annotation, task_id=my_task.id, hydrated=True).all()
```

This hits `/api/annotations/task/{id}/hydrated`, which batch-fetches annotation data efficiently.

## Deleting

```python
session.delete(a)
session.commit()
```
