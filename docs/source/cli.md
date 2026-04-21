# Command-line interface

`pip install ragnerock` installs a `ragnerock` executable — a kubectl-style CLI for inspecting resources, applying YAML manifests, and running workflows. It wraps the same [Session](sessions.md) API you'd use from Python; anything you can do from the SDK you can do from the shell.

## Installation

```bash
pip install ragnerock
ragnerock --help
```

The CLI ships in the main package; no extras are required.

## Configuration

The CLI reads credentials from environment variables. Two equivalent forms:

**Full connection string**

```bash
export RAGNEROCK_CONNECTION_STRING="ragnerock://you@example.com:pass@api.ragnerock.com/my_project"
```

**Split variables**

| Variable | Purpose |
|---|---|
| `RAGNEROCK_HOST` | Host or full URL (`api.ragnerock.com` or `https://api.ragnerock.com`). Bare hosts default to `https://`. |
| `RAGNEROCK_EMAIL` | Account email. |
| `RAGNEROCK_PASSWORD` | Account password. |
| `RAGNEROCK_PROJECT` | Project name to scope every command to. |

`RAGNEROCK_CONNECTION_STRING` will always overwrite the split variables if set.

```bash
# CI example
export RAGNEROCK_HOST=api.ragnerock.com
export RAGNEROCK_EMAIL="ci@example.com"
export RAGNEROCK_PASSWORD="$RAGNEROCK_CI_PASSWORD"
export RAGNEROCK_PROJECT=ci-sandbox
```

## Commands

### `get`

List resources or fetch one by name

```
ragnerock get <kind> [NAME] [-o table|json|yaml|name] [--filter k=v ...]
```

Omit `NAME` to list every resource of that kind in the current project:

```bash
ragnerock get doc
ragnerock get workflows -o name | xargs -I{} ragnerock describe wf {}
```

Pass `NAME` to fetch exactly one:

```bash
ragnerock get op sentiment -o yaml
```

Additionally, use `--filter` to filter the resulting resources by resource values:

```bash
ragnerock get chunk --filter document=00000000-0000-0000-0000-000000000101
ragnerock get annotation --filter operator=sentiment-classifier
```

### `describe`
Get full details for one resource

```
ragnerock describe <kind> <NAME> [-o table|json|yaml|name]
```

By default describe outputs are formatted as YAML, however JSON is also available

```bash
ragnerock describe op sentiment                     # yaml, default
ragnerock describe op sentiment -o json             # explicit override
```

### `apply`

Create or update resources from a manifest

```
ragnerock apply -f FILE [-f FILE ...]
```

`-f` is repeatable in the event you want to apply multiple sources. Each source may be a file path, a directory, or `-` to read from STDIN. Directory sources are walked recursively and every `*.yaml` / `*.yml` file beneath the directory is loaded in sorted order; hidden entries (dotfiles, `.git/`, …) and non-YAML files are silently skipped. Files, directories, and `-` may be freely mixed across repeated `-f` flags.

```bash
# heredoc
ragnerock apply -f - <<'EOF'
apiVersion: v1
kind: Operator
metadata: { name: sentiment }
spec:
  jsonschema: { type: object, properties: { label: { type: string } } }
  generation_prompt: "Classify..."
  chunk_type: PARAGRAPH
EOF

# round-trip — no-op update
ragnerock get op sentiment -o yaml | ragnerock apply -f -

# multi-file
ragnerock apply -f operators.yaml -f workflows.yaml

# directory tree
ragnerock apply -f manifests/
```

`apply` is idempotent: new resources (no existing match on `metadata.name`) are created, existing ones are updated in place. Across multi-doc manifests, documents are committed in dependency order: `DocumentGroup → Operator → Document → Workflow → Annotation`. See [Manifests](manifests.md) for the full schema.

### `delete`

Remove a resource

```
ragnerock delete <kind> <NAME>
ragnerock delete -f FILE [-f FILE ...]
```

Either pass `<kind> <NAME>`, or pass one or more manifests (including `-` for STDIN) and every resource they declare is subsequently deleted by name:

```bash
ragnerock delete op sentiment
ragnerock delete -f operators.yaml
```

### `run`

Execute a workflow

```
ragnerock run <workflow-name> --documents NAME[,NAME...] \
  [--wait] [--poll-interval 2] [--timeout 300]
```

Looks up the workflow and documents by name, calls `session.run(...)`, and prints the resulting job id

You can optionally pass `--wait` to block until the job reaches a terminal state:

```bash
ragnerock run ingest --documents q3-report.pdf --wait --timeout 600
```

Exit codes for `--wait`:

| code | Meaning                        |
| ---- | ------------------------------ |
| `0`  | Job succeeded                  |
| `1`  | Workflow or document not found |
| `2`  | Job failed or timed out        |

### `query`

Run annotation SQL

```
ragnerock query "SELECT ..." [-o table|json] [--limit N]
```

```bash
ragnerock query "SELECT document_id, label FROM sentiment LIMIT 20"
ragnerock query "SELECT COUNT(*) FROM sentiment WHERE label = 'negative'" -o json
```

Tables uses slugified operator names as their names. For example, the operator `Document Properties` is normalized to `document_properties` in queries.

### `version`

Display the current CLI version.

```bash
ragnerock version
```

## Resource kinds

| CLI name | Aliases | Notes |
| --------------- | ------------------------------------------------------------| --- |
| `Document`      | `doc`, `docs`, `document`, `documents`                      |     |
| `DocumentGroup` | `grp`, `group`, `groups`, `documentgroup`, `documentgroups` |     |
| `Operator`      | `op`, `ops`, `operator`, `operators`                        |     |
| `Workflow`      | `wf`, `wfs`, `workflow`, `workflows`                        |     |
| `Annotation`    | `anno`, `annos`, `annotation`, `annotations`                | Requires `--filter document=...`, `--filter chunk=...`, or `--filter operator=...` when listing. |
| `Chunk`         | `chunk`, `chunks`                                           | Read-only. Requires `--filter document=...` when listing; no name lookup. |
| `Page`          | `page`, `pages`                                             | Read-only. Requires `--filter document=...`; no name lookup. |
| `Job`           | `job`, `jobs`                                               | Read-only. Created via `ragnerock run`. |

Matching is case-insensitive.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | User / lookup error — missing env var, unknown kind, resource not found, malformed manifest. |
| 2 | Server or runtime error — failed job, timeout, unexpected API response. |
