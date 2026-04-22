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
    - operator: extract
      on_error: FAIL_JOB
      max_retries: 2
    - operator: classifier
      condition:
        extract.entities:
          $count: { $gt: 0 }
  edges:
    - [extract, classifier]
```

**Spec Fields**

| Key                  | Description                                                             | Required | Type   | Default   |
| -------------------- | ----------------------------------------------------------------------- | -------- | ------ | --------- |
| `description`        | Description of the workflow in question                                 | No       | `str`  |           |
| `is_active`          | Is the workflow allows to process documents                             | No       | `bool` | `True`    |
| `auto_run_on_upload` | Automatically run any uploaded documents through the workflow if active | No       | `bool` | `True`    |

`spec.nodes` is a list of node declarations with the following fields:

| Key                  | Description                                                             | Required | Type   | Default    |
| -------------------- | ----------------------------------------------------------------------- | -------- | ------ | ---------- |
| `operator`           | Name of the pre-existing operator to include in the workflow            | Yes      | `str`  |            |
| `condition`          | Conditionals to gate node execution behind                              | No       | `dict` | `{}`       |
| `persist`            | Should annotations be persisted to the database                         | No       | `bool` | `True`     |
| `on_error`           | Behavior in the event the node fails, `FAIL_JOB` or `SKIP_NODE`         | No       | `str`  | `FAIL_JOB` |
| `max_retries`        | Max number of times to retry a job on a node                            | No       | `int`  | `0`        | 

Conditional statements are formatted as nested objects detailing the upstream node, its annotation field, and the condition that must match in order for the node to execute

The conditional dictionary is modeled after MongoDB's filter setup, this means that the following comparison operators are available:

| Name                     | Key    |
| ------------------------ | ------ |
| Equals                   | `$eq`  |
| Not equal to             | `$ne`  |
| Greater than             | `$gt`  |
| Less than                | `$lt`  |
| Greater than or equal to | `$gte` |
| Less than or equal to    | `$lte` |

You can then use the operators against upstream nodes/properties, for example we may want to check that the `sentiment_score` property of our `extract` node is greater than `0.5`, we can do that like so

```json
{
  "extract.sentiment_score": {
    "$gt": 0.5
  }
}
```

Logical operators are also supported

| Name | Key    |
| ---- | ------ |
| And  | `$and` |
| Or   | `$or`  |
| Not  | `$not` |

`$and` and `$or` logical operators take lists as their value, for example, if we wanted to only execute on annotations with a sentiment score above `0.5` and a confidence greater than or equal to `0.9`, we would do it like follows:

```json
{
  "$and": [
    {
      "extract.sentiment_score" : {
        "$gt": 0.5
      },
      "extract.confidence": {
        "$gte": 0.9
      }
    }
  ]
}
```

`$not` statements take a single condition as their value

```json
{
  "$not": {
    "extract.confidence": {
      "$gte": 0.9
    }
  }
}
```

In the event the property you want to evaluate is a list, the following list operations are available

| Name     | Key         |
| -------- | ----------- |
| Count    | `$count`    |
| Contains | `$contains` |
| Minimum  | `$min`      |
| Maximum  | `$max`      |

If I wanted to construct a conditional to only execute on sentiment scores greater than 0.5 with more than 10 positive values, we can do the following:

```json
{
  "$and": {
    "extract.sentiment_score": {
      "$gt": 0.5
    },
    "extract.positive_values": {
      "$count": {
        "$gt": 10
      }
    }
  }
}
```

`spec.edges` is a list of directed edges. Each entry may be either a pair:

```yaml
edges:
  - [extract, classify]
```

or an explicit mapping:

```yaml
edges:
  - from: extract
    to: classify
```

Edge endpoints refer to node operators (the `operator:` field on `spec.nodes[*]`).

Every operator referenced by a workflow must already exist on the server or appear earlier in the same multi-doc manifest.

## Example Manifest

```yaml
apiVersion: v1
kind: DocumentGroup
metadata:
  name: quarterly-reports
spec: {}
---
apiVersion: v1
kind: Operator
metadata:
  name: sentiment-classifier
spec:
  jsonschema:
    type: object
    properties:
      sentiment: 
        type: string
        enum:
          - positive
          - negative
          - neutral
  generation_prompt: |
    Classify the sentiment of this paragraph.
  chunk_type: PARAGRAPH
---
apiVersion: v1
kind: Document
metadata:
  name: q3-report.pdf
spec:
  file_path: ./reports/q3.pdf
  group: quarterly-reports
---
apiVersion: v1
kind: Workflow
metadata:
  name: sentiment-pipeline
spec:
  auto_run_on_upload: false
  description: |
    Sentiment over quarterly reports
  nodes:
    - operator: sentiment-classifier
  edges: []
```

This example assumes a file located at `./reports/q3.pdf` with the above manifest saved at `manifest.yaml`

```bash
ragnerock apply -f manifest.yaml
ragnerock run sentiment-pipeline --documents q3-report.pdf --wait
ragnerock query "SELECT document_id, sentiment, COUNT(*) AS n FROM sentiment_classifier GROUP BY 1, 2"
```
