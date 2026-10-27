# Migrating to 2.0

Version 2.0 brings the SDK in line with the current Ragnerock API, replaces the CLI's manifest format with [GitOps manifests](gitops.md), and adds client support for most of the platform (see [Platform APIs](platform.md)). This page lists what changed and what to do about it.

## CLI: `apply` now uses GitOps manifests

`ragnerock apply -f` uploads GitOps manifests (`apiVersion: ragnerock.com/v1alpha1`) for server-side apply. The 1.x client-side format (`apiVersion: v1`, snake_case `spec`) is no longer accepted — documents in that format are now skipped as non-Ragnerock YAML.

| 1.x manifest kind | 2.0 equivalent |
| --- | --- |
| `Operator` | A `Schema` (the `jsonSchema`) plus an `Agent` that references it (`generationPrompt`, `chunkType`, ...). |
| `Workflow` | `Workflow`, with nodes naming their `agent` and wiring upstream nodes with `dependsOn`. |
| `Document`, `DocumentGroup`, `Annotation` | Not configuration — create them with the [Session API](sessions.md), or ingest documents with an `IngestConfig`. |

See [`examples/gitops/`](https://github.com/ragnerock/ragnerock-sdk/tree/main/examples/gitops) for working manifests of every kind.

Also in the CLI:

- **`ragnerock delete -f` is removed.** GitOps apply never deletes; use `ragnerock delete <kind> <name>`.
- **`ragnerock get -o yaml` prints a plain field dump** rather than a manifest, since it no longer round-trips into `apply`.
- **`apply` doesn't need a project.** `RAGNEROCK_PROJECT` (or a `/project` path in the connection string) is optional for it; project-scoped manifests name their project with the `ragnerock.com/project` annotation.

## Chunks

The chunk shape now matches the API:

- **`ChunkType` values are renumbered** to match the server: `DOCUMENT=0`, `PAGE=1`, `PARAGRAPH=2`, `SENTENCE=3`, plus the tabular scopes `ROW=4`, `ROW_WINDOW=5`, `SHEET=6`. `SECTION` is gone. Code that uses the names (`ChunkType.PARAGRAPH`) needs no change; code that stored or sent raw integers does. In 1.x, an operator created with `ChunkType.PARAGRAPH` was actually sent as `ROW` — check the scope of operators created with 1.x.
- **`Chunk` fields:** `start_index` / `end_index` are now `start_char_idx` / `end_char_idx`; new fields `document_offset` and `page_id`; `metadata` and `created_at` are removed (the API never returned them).
- **Creating a chunk** requires `content`, `document_offset`, and `chunk_type`; `client.chunks.create(...)` takes the same fields.

## Operators

- Operators carry an explicit **`operator_kind`** (`OperatorKind.LLM` by default), which the API now requires. `CODE` operators supply `code_source` instead of `generation_prompt`.
- `client.operators.create(...)` takes `chunk_type` and `operator_kind`; `jsonschema` and `generation_prompt` are optional (a schema can be linked with `output_schema_id`).
- `client.operators.update(...)`: for `batch_size`, `input_columns`, `code_timeout_seconds`, `ai_config_id`, `model_name`, and `change_request_signal`, omitting the argument leaves the field unchanged and passing `None` clears it.

## Workflows

- **Defaults match the server:** `Workflow.auto_run_on_upload` defaults to `False` (was `True`), and `WorkflowNode.on_error` / `add_node(on_error=...)` default to `"SKIP_NODE"` (was `"FAIL_JOB"`). Pass the old values explicitly to keep the 1.x behavior for new workflows.
- `Workflow.execution_order` is a list of node-id strings.
- Nodes loaded with a workflow now carry `workflow_id` and are bound to the session, so they can be wired with `>>` and committed (in 1.x this raised).

## Other changes

- **Timestamps** on resources are timezone-aware UTC `datetime`s. Comparisons against naive datetimes need `tzinfo=UTC`.
- **`Job.cancel()` / `Job.retry()`** re-fetch the job afterwards, so `status` reflects the server's state.
- **`Page.metadata`** is removed (the API never returned it); `Page.created_at` is added.
- **Document metadata** updates are sent in the encoding the API expects; no code change needed.
- **`ragnerock.client` is now a package.** `from ragnerock.client import RagnerockClient` and the response models import as before; internal helpers moved to `ragnerock.client._base`.
- **Dependencies:** `cryptography` is now required (for sealing GitOps secrets). Cloud secret-manager support is in the optional extras `gcp`, `aws`, and `azure`.

## What's new

- [GitOps apply](gitops.md) from the CLI and from Python (`ragnerock.gitops`), with client-side secret resolution and sealing.
- {func}`~ragnerock.create_client` for account-level calls that need no project.
- [Platform APIs](platform.md) on the low-level client: skills, agent tools, notebooks, assignments, search, endpoints, workflow schedules / sinks / change requests / artifacts, ingest sources, saved queries, AI / embedding / image-summary / database / blob provider configs, and web access.
- `OperatorKind`, `DocumentStatus`, `WorkflowSchedule`; `Document.status` and `Document.job()`; lazy `Annotation.document` / `.chunk` / `.page` / `.operator`; `doc.list(Annotation, operator=...)`.
- `QueryResult.truncated` and `session.query(..., include_provenance=True)`.
- New read-only CLI kinds for `ragnerock get` / `describe` (see [CLI](cli.md#resource-kinds)).
