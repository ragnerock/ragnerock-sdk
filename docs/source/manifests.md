# Manifests

The CLI accepts Kubernetes-style YAML manifests for every writable resource. This page documents the schema for each `kind` and how `ragnerock apply` reconciles them with server state.

## General shape

Every manifest document follows the same three-section layout:

```yaml
kind: <ResourceKind>
metadata:
  name: <string>        # required; this is the apply key
  # additional metadata may appear here
spec:
  # kind-specific body
```

Notes:

* No `apiVersion` — the API is single-versioned today, so it is intentionally omitted. It may be added later without breaking existing manifests.
* Multi-doc YAML streams (separated by `---`) are supported everywhere — files, `-f file.yaml`, and `-f -` (STDIN).
* Any field under `spec` that is a valid field on the underlying Pydantic resource class is forwarded directly; unknown fields are ignored.

## Apply order

When you apply a multi-doc manifest, documents are committed in a fixed dependency order so that later ones can reference names created by earlier ones:

```
DocumentGroup → Operator → Document → Workflow → Annotation
```

Within each stratum, declaration order is preserved. Each document produces a separate `session.commit()`, so a failure in document *N* leaves documents *0..N-1* applied server-side.

## Idempotence

`apply` looks up each resource by `metadata.name`:

* No match → `session.add(...)` is staged for a create.
* Match → fields from `spec` are copied onto the existing instance and `session.update(...)` is staged.
* Fields you **don't** include in `spec` are left untouched on the server.

`ragnerock get <kind> <name> -o yaml` emits a manifest that flows unchanged through `apply -f -`, so the common edit flow is:

```bash
ragnerock get wf ingest -o yaml > ingest.yaml
$EDITOR ingest.yaml
ragnerock apply -f ingest.yaml
```

## Per-kind schemas

### `DocumentGroup`

```yaml
kind: DocumentGroup
metadata:
  name: quarterly-reports
spec: {}
```

Groups are named buckets. The only required field is `metadata.name`.

Backed by [DocumentGroup](api/resources.md).

### `Operator`

```yaml
kind: Operator
metadata:
  name: sentiment-classifier
spec:
  description: "Classify sentiment of document paragraphs"
  jsonschema:
    type: object
    properties:
      sentiment:
        type: string
        enum: [positive, negative, neutral]
  generation_prompt: "Classify the sentiment..."
  chunk_type: PARAGRAPH          # enum name; see ChunkType
  batch_size: 16
  multi_annotation: false
```

| Field | Required | Notes |
|---|---|---|
| `jsonschema` | yes (on create) | JSON Schema constraining the annotation payload. |
| `generation_prompt` | yes (on create) | LLM prompt used at annotation time. |
| `chunk_type` | yes (on create) | One of `DOCUMENT`, `PAGE`, `SECTION`, `PARAGRAPH`, `SENTENCE`. Case-insensitive. |
| `description` | no | Free-form. |
| `batch_size` | no | Integer. |
| `multi_annotation` | no | Boolean. Defaults to `false`. |

### `Document`

```yaml
kind: Document
metadata:
  name: q3-report.pdf
spec:
  file_path: ./reports/q3.pdf    # OR source_url
  group: quarterly-reports        # by name; resolved at apply time
  file_type: PDF
  metadata:
    quarter: Q3
    year: 2024
```

| Field | Required | Notes |
|---|---|---|
| `file_path` *or* `source_url` | yes (on create) | Exactly one. `file_path` is a local path uploaded at commit time; `source_url` is a URL the server fetches. |
| `group` | no | Group **name**. The CLI resolves it to `group_id` by looking up a `DocumentGroup` in the current project. |
| `file_type` | no | One of `PLAINTEXT`, `MARKDOWN`, `PDF`, `DOCX`, `XLSX`, `CSV`, `IPYNB`, `JPG`, `JPEG`, `PNG`. Inferred from the file when omitted. |
| `metadata` | no | Arbitrary key/value map. |

### `Workflow`

```yaml
kind: Workflow
metadata:
  name: review-pipeline
spec:
  description: "Review pipeline"
  is_active: true
  auto_run_on_upload: false
  nodes:
    - name: extract
      operator: entity-extractor
      on_error: FAIL_JOB
      max_retries: 2
    - name: classify
      operator: sentiment-classifier
      condition:
        extract:
          entities: { "$gt": 0 }
  edges:
    - [extract, classify]
```

Workflow top-level fields (`description`, `is_active`, `auto_run_on_upload`) are forwarded directly to the resource.

`spec.nodes` is a list of node declarations:

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Manifest-local alias used for edge wiring. Not sent to the server. |
| `operator` | yes | Operator **name**. Resolved to `operator_id` at apply time — the referenced operator must exist. |
| `condition` | no | Predicate object. |
| `persist` | no | Defaults to `true`. |
| `on_error` | no | `FAIL_JOB` (default) or `SKIP_NODE`. |
| `max_retries` | no | Integer, defaults to `0`. |

`spec.edges` is a list of directed edges. Each entry may be either a pair:

```yaml
edges:
  - [extract, classify]
```

…or an explicit mapping:

```yaml
edges:
  - from: extract
    to: classify
```

Edge endpoints refer to node aliases (the `name:` field on `spec.nodes[*]`).

**Apply flow for workflows** (good to understand; important for debugging):

1. The workflow itself is upserted first — this assigns an `id` on create.
2. Each `spec.nodes` entry is reconciled by operator name: existing nodes with the same `operator_name` are updated in place; new nodes are added via `workflow.add_node(...)`. Nodes not present in the manifest are left alone (we don't auto-delete to avoid surprising deletions).
3. A second commit wires edges using the `>>` operator on the resolved nodes.

Because step 2 needs operator ids, every operator referenced by a workflow must already exist on the server or appear earlier in the same multi-doc manifest.

### `Annotation`

```yaml
kind: Annotation
metadata:
  name: my-annotation-stub
spec:
  operator: sentiment-classifier    # by name; resolved to operator_id
  document_id: 00000000-0000-0000-0000-000000000101
  data:
    sentiment: positive
  confidence_score: 0.95
```

| Field | Required | Notes |
|---|---|---|
| `operator` (or `operator_id`) | yes | Operator name or UUID. Name is resolved at apply time. |
| `document_id` / `chunk_id` / `page_id` | one of these | Target of the annotation. |
| `data` | yes | Payload; must satisfy the operator's `jsonschema`. |
| `confidence_score` | no | Float between 0 and 1. |

Annotations are usually generated by running a workflow rather than authored by hand. This kind is provided for completeness and for programmatic back-filling.

## Worked example — one file, end to end

```yaml
# pipeline.yaml
kind: DocumentGroup
metadata: { name: quarterly-reports }
spec: {}
---
kind: Operator
metadata: { name: sentiment-classifier }
spec:
  jsonschema:
    type: object
    properties:
      sentiment: { type: string, enum: [positive, negative, neutral] }
  generation_prompt: "Classify the sentiment of this paragraph."
  chunk_type: PARAGRAPH
---
kind: Document
metadata: { name: q3-report.pdf }
spec:
  file_path: ./reports/q3.pdf
  group: quarterly-reports
---
kind: Workflow
metadata: { name: sentiment-pipeline }
spec:
  description: "Sentiment over quarterly reports"
  nodes:
    - name: classify
      operator: sentiment-classifier
  edges: []
```

```bash
ragnerock apply -f pipeline.yaml
ragnerock run sentiment-pipeline --documents q3-report.pdf --wait
ragnerock query "SELECT document_id, sentiment, COUNT(*) AS n FROM sentiment_classifier GROUP BY 1, 2"
```

See [CLI](cli.md) for the full verb reference.
