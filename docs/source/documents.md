# Documents

## Listing

```python
docs = session.list(Document).all()
for doc in session.list(Document):
    print(doc.name)
```

## Getting

```python
doc = session.get(Document, id="...")
doc = session.get(Document, name="...")
```

Both return `None` on miss instead of a `NotFoundError`.

## Uploading

Provide either a local `file_path` or a remote `source_url`:

```python
# From a local file
doc = Document(file_path="./report.pdf", name="q1-report")
session.add(doc)
session.commit()
# doc.id, doc.storage_path, doc.created_at, doc.filesize are now populated

# From a URL (server fetches it -- images _only_)
doc = Document(source_url="https://example.com/report.pdf", name="q1-report")
session.add(doc)
session.commit()
```

Optional fields on create: `document_folder_id`, `file_type`, `metadata`.

## Updating

Mutate the resource, then stage and commit:

```python
doc.name = "renamed.pdf"
doc.document_folder_id = other_folder.id
session.update(doc)
session.commit()
```

## Deleting

```python
session.delete(doc)
session.commit()
```

## Downloading content

```python
data: bytes = doc.content()
```

## Document folders

Document folders are project-scoped named collections of documents. A document belongs to at most one, through its `document_folder_id`:

```python
from ragnerock import DocumentFolder

folder = DocumentFolder(name="Q1 contracts")
session.add(folder)
session.commit()

# List all document folders
folders = session.list(DocumentFolder).all()

# List documents in a folder
docs = folder.list(Document).all()

# Get a single folder, by id or name
folder = session.get(DocumentFolder, id=my_folder_id)
folder = session.get(DocumentFolder, name="Q1 contracts")

# Move a document into a folder
doc.document_folder_id = folder.id
session.update(doc)
session.commit()
```

A `DocumentFolder`'s own `folder_id` is something else: the folder it is filed under in the project's folder tree in the app.

## Chunks

```python
from ragnerock import Chunk, ChunkType

chunks = doc.list(Chunk).all()
chunks = session.list(Chunk, document_id=doc.id).all()

one = session.get(Chunk, id="...")
```

Each chunk carries its text (`content`), its position in the document (`document_offset`), its scope (`chunk_type`), optional character offsets into the extracted text (`start_char_idx`, `end_char_idx`), and the `page_id` it was parsed from.

`ChunkType` values: `DOCUMENT`, `PAGE`, `PARAGRAPH`, `SENTENCE` for documents, and `SHEET`, `ROW`, `ROW_WINDOW` for tabular sources (spreadsheets, CSVs, SQL ingest tables).

To create a chunk by hand:

```python
chunk = Chunk(
    document_id=doc.id,
    content="Revenue grew 12% year over year.",
    document_offset=4,
    chunk_type=ChunkType.PARAGRAPH,
)
session.add(chunk)
session.commit()
```

## Pages

```python
from ragnerock import Page

pages = doc.list(Page).all()     # in page-number order
page = session.get(Page, id="...")
print(page.page_number, page.content)
```

Attempting `session.add(page)` / `update` / `delete` raises exceptions as they are read-only.

## Processing status

`doc.status` reports where the server is with a document: `PENDING`, `PROCESSING`, `READY`, or `ERROR` (and `FETCHING` / `NOT_FETCHED` for documents an ingest source pulls). For stage-by-stage progress, fetch the document's latest [run](runs.md):

```python
from ragnerock import DocumentStatus

session.refresh(doc)
if doc.status is not DocumentStatus.READY:
    run = doc.latest_run()
    print(run.phase, run.current_stage_name, run.current_stage_subtasks_completed)
```