# Manifests

The CLI accepts Kubernetes-style YAML manifests for every writable resource. This page documents the schema for each `kind` and how `ragnerock apply` reconciles them with server state.

## General shape

Every manifest document follows the same layout:

```yaml
apiVersion: v1
kind: <ResourceKind>
metadata:
  name: <string>
spec:
  # kind-specific body
```

Notes:

- `apiVersion`, `kind`, and `metadata.key` are all required for all resources
* `v1` is the only currently accepted `apiVersion` value.
* Multi-doc YAML streams (separated by `---`) are supported

## Apply order

When you apply a multi-doc manifest, documents are committed in a fixed dependency order so that later ones can reference names created by earlier ones:

```
DocumentGroup → Operator → Document → Workflow → Annotation
```

## Per-kind schemas

### `DocumentGroup`

**Example**

```yaml
apiVersion: v1
kind: DocumentGroup
metadata:
  name: quarterly-reports
spec: {}
```

### `Operator`

**Example**

```yaml
apiVersion: v1
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

**Spec Fields**

| Key                 | Description                                                                                            | Required | Type   | Default |
| ------------------- | ------------------------------------------------------------------------------------------------------ | -------- | ------ | ------- |
| `jsonschema`        | JSON Schema constraining the annotation payload                                                        | Yes      | `dict` |         |
| `generation_prompt` | LLM prompt used at annotation time                                                                     | Yes      | `str`  |         |
| `chunk_type`        | One of `DOCUMENT`, `PAGE`, `SECTION`, `PARAGRAPH`, `SENTENCE` (case-insensitive)                       | Yes      | `str`  |         |
| `description`       | Description of the operator                                                                            | No       | `str`  | `""`    |
| `batch_size`        | Override for the number of documents to batch when processing the operator. Use `0` for server default | No       | `int`  | `0`     |
| `multi_annotation`  | Does the operator produce more than one annotation per invocation                                      | No       | `bool` | `False` |

### `Document`

```yaml
apiVersion: v1
kind: Document
metadata:
  name: q3-report.pdf
spec:
  file_path: ./reports/q3.pdf    # OR source_url for images only
  group: quarterly-reports        # by name; resolved at apply time
  file_type: PDF
  metadata:
    quarter: Q3
    year: 2024
```

**Spec Fields**

| Key          | Description                                                                                                | Required | Type   | Default   |
| ------------ | ---------------------------------------------------------------------------------------------------------- | -------- | ------ | --------- |
| `file_path`  | Local path to file to upload at commit time, cannot be used in conjunction with `source_url`               | Yes      | `str`  |           |
| `source_url` | URL to pull an image from, cannot be used in conjunction with `file_path`                                  | Yes      | `str`  |           |
| `group`      | Name of the group to place the document into                                                               | No       | `str`  | `Default` |
| `file_type`  | Document type, one of `PLAINTEXT`, `MARKDOWN`, `PDF`, `DOCX`, `XLSX`, `CSV`, `IPYNB`, `JPG`, `JPEG`, `PNG` | Yes      | `str`  | `""`      |
| `metadata`   | Arbitrary key/value map to include in the documents table                                                  | No       | `dict` | `{}`      |

### `Workflow`

```yaml
apiVersion: v1
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

**Spec Fields**

| Key                  | Description                                                             | Required | Type   | Default   |
| -------------------- | ----------------------------------------------------------------------- | -------- | ------ | --------- |
| `description`        | Description of the workflow in question                                 | No       | `str`  |           |
| `is_active`          | Is the workflow allows to process documents                             | No       | `bool` | `True`    |
| `auto_run_on_upload` | Automatically run any uploaded documents through the workflow if active | No       | `bool` | `True`    |

`spec.nodes` is a list of node declarations with the following fields:

| Key                  | Description                                                             | Required | Type   | Default   |
| -------------------- | ----------------------------------------------------------------------- | -------- | ------ | --------- |
| `name`               | Manifest-local alias used for edge wiring                       | Yes | `str` | |
| `operator`           | Name of the pre-existing operator to include in the workflow    | Yes | `str` | |
| `condition`          | Conditionals to gate node execution behind                      | No  | `dict` | `{}` |
| `persist`            | Should annotations be persisted to the database                 | No | `bool` | `True` |
| `on_error`           | Behavior in the event the node fails, `FAIL_JOB` or `SKIP_NODE` | `str` | `FAIL_JOB` |
| `max_retries`        | Max number of times to retry a job on a node                    | `int` | `0` |

Conditional statements are formatted as nested objects detailing the upstream node, its annotation field, and the condition that must match in order for the node to execute. These are formatted as

```yaml
condition:
  <upstream node name>:
    <upstream node annotation property>: 

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
apiVersion: v1
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
apiVersion: v1
kind: DocumentGroup
metadata: { name: quarterly-reports }
spec: {}
---
apiVersion: v1
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
apiVersion: v1
kind: Document
metadata: { name: q3-report.pdf }
spec:
  file_path: ./reports/q3.pdf
  group: quarterly-reports
---
apiVersion: v1
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
