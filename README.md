# ragnerock

Python SDK and CLI for the [Ragnerock](https://ragnerock.com) API.

- A SQLAlchemy-shaped **Session API** for documents, annotations, operators (agents), workflows, jobs, and SQL queries over annotations.
- **GitOps apply** — declare secrets, provider configs, schemas, skills, agents, workflows, endpoints, and ingest configs as YAML, and apply them from the CLI or CI.
- A **low-level client** covering the rest of the platform: agent tools and skills, notebooks and assignments, search, endpoints, ingest sources, saved queries, workflow schedules and change requests, and AI / database / blob provider configs.

```bash
pip install ragnerock
pip install 'ragnerock[pandas]'           # QueryResult.to_pandas()
pip install 'ragnerock[gcp,aws,azure]'    # cloud secret managers for GitOps Secrets
```

## Python

```python
from ragnerock import Document, Session, create_engine

engine = create_engine("ragnerock://token:rgnk_...@api.ragnerock.com/my_project")

with Session(engine) as session:
    doc = Document(file_path="./report.pdf", name="q1-report")
    session.add(doc)
    session.commit()

    result = session.query("SELECT vendor, total FROM invoice_extract WHERE total > 1000")
    df = result.to_pandas()

    # Anything the session doesn't model is on the low-level client
    hits = engine.client.search.search(project_id=engine.project_id, query="revenue guidance")
```

## CLI

```bash
export RAGNEROCK_HOST=api.ragnerock.com
export RAGNEROCK_API_TOKEN=rgnk_...
export RAGNEROCK_PROJECT=my_project

ragnerock get docs                              # list documents
ragnerock apply -f manifests/ --plan            # preview a GitOps apply
ragnerock apply -f manifests/                   # apply it
ragnerock run ingest --documents q1.pdf --wait  # run a workflow
ragnerock query "SELECT COUNT(*) FROM invoice_extract"
```

## Documentation

The user guide and API reference live in [`docs/source/`](docs/source/index.md) — start with [Connecting](docs/source/connecting.md), [Sessions](docs/source/sessions.md), [GitOps manifests](docs/source/gitops.md), and [Platform APIs](docs/source/platform.md). Upgrading from 1.x? See [Migrating to 2.0](docs/source/migration.md). Example manifests are in [`examples/gitops/`](examples/gitops/).

## Development

```bash
uv sync --all-packages
task test-unit     # unit tests
task lint          # ruff
task check         # pyright
task format        # ruff format
task doc           # sphinx (warnings are errors)
```

Licensed under Apache-2.0.
