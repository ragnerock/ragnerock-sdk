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

**Form 1** — full connection string:

```bash
export RAGNEROCK_CONNECTION_STRING="ragnerock://you@example.com:pass@api.ragnerock.com/my_project"
```

**Form 2** — split variables (useful in CI):

| Variable | Purpose |
|---|---|
| `RAGNEROCK_HOST` | Host or full URL (`api.ragnerock.com` or `https://api.ragnerock.com`). Bare hosts default to `https://`. |
| `RAGNEROCK_EMAIL` | Account email. |
| `RAGNEROCK_PASSWORD` | Account password. |
| `RAGNEROCK_PROJECT` | Project name to scope every command to. |

`RAGNEROCK_CONNECTION_STRING`, if set, always wins. If neither form is complete, commands exit with a message listing the missing variables.

```bash
# CI example
export RAGNEROCK_HOST=api.ragnerock.com
export RAGNEROCK_EMAIL="ci@example.com"
export RAGNEROCK_PASSWORD="$RAGNEROCK_CI_PASSWORD"
export RAGNEROCK_PROJECT=ci-sandbox
```

## Commands

### `get` — list resources or fetch one by name

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

Some kinds require a `--filter`:

```bash
ragnerock get chunk --filter document=00000000-0000-0000-0000-000000000101
ragnerock get annotation --filter operator=sentiment-classifier
```

### `describe` — full detail for one resource

```
ragnerock describe <kind> <NAME> [-o table|json|yaml|name]
```

Same flags as `get`; default is `yaml` instead of `table`, which round-trips cleanly into `apply -f -`:

```bash
ragnerock describe op sentiment                     # yaml, default
ragnerock describe op sentiment -o json             # explicit override
```

### `apply` — create or update resources from a manifest

```
ragnerock apply -f FILE [-f FILE ...]
```

`-f` is repeatable. Each source can be a path or `-` to read a multi-doc YAML stream from STDIN — so heredocs and piped output just work:

```bash
# heredoc
ragnerock apply -f - <<'EOF'
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
```

`apply` is idempotent: new resources (no existing match on `metadata.name`) are created, existing ones are updated in place. Across multi-doc manifests, documents are committed in dependency order: `DocumentGroup → Operator → Document → Workflow → Annotation`. See [Manifests](manifests.md) for the full schema.

### `delete` — remove a resource

```
ragnerock delete <kind> <NAME>
ragnerock delete -f FILE [-f FILE ...]
```

Either pass `<kind> <NAME>`, or pass one or more manifests (including `-` for STDIN) and every resource they declare is deleted by name:

```bash
ragnerock delete op sentiment
ragnerock delete -f operators.yaml
```

### `run` — execute a workflow

```
ragnerock run <workflow-name> --documents NAME[,NAME...] \
  [--wait] [--poll-interval 2] [--timeout 300]
```

Looks up the workflow and documents by name, calls `session.run(...)`, and prints the resulting job id. Pass `--wait` to block until the job reaches a terminal state:

```bash
ragnerock run ingest --documents q3-report.pdf --wait --timeout 600
```

Exit codes for `--wait`:

* `0` — job succeeded.
* `1` — workflow or document not found.
* `2` — job failed or timed out.

### `query` — run annotation SQL

```
ragnerock query "SELECT ..." [-o table|json] [--limit N]
```

```bash
ragnerock query "SELECT document_id, label FROM sentiment LIMIT 20"
ragnerock query "SELECT COUNT(*) FROM sentiment WHERE label = 'negative'" -o json
```

Tables use the names of your operators as defined on the server.

### `version`

```bash
ragnerock version
```

Prints the installed `ragnerock` package version.

## Resource kinds

| CLI name | Aliases | Notes |
|---|---|---|
| `Document` | `doc`, `docs`, `document`, `documents` | |
| `DocumentGroup` | `grp`, `group`, `groups`, `documentgroup`, `documentgroups` | |
| `Operator` | `op`, `ops`, `operator`, `operators` | |
| `Workflow` | `wf`, `wfs`, `workflow`, `workflows` | |
| `Annotation` | `anno`, `annos`, `annotation`, `annotations` | Requires `--filter document=...`, `--filter chunk=...`, or `--filter operator=...` when listing. |
| `Chunk` | `chunk`, `chunks` | Read-only. Requires `--filter document=...` when listing; no name lookup. |
| `Page` | `page`, `pages` | Read-only. Requires `--filter document=...`; no name lookup. |
| `Job` | `job`, `jobs` | Read-only. Created via `ragnerock run`. |

Matching is case-insensitive.

## Output formats

| Format | When to use |
|---|---|
| `table` | Default for `get`. Human-friendly, colorized when stdout is a TTY. |
| `json` | Machine-readable. Arrays of `{...}` objects. |
| `yaml` | Default for `describe`. Inverse of the manifest format — pipes straight into `apply -f -`. |
| `name` | One resource name per line, for piping to `xargs` / `while read`. |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | User / lookup error — missing env var, unknown kind, resource not found, malformed manifest. |
| 2 | Server or runtime error — failed job, timeout, unexpected API response. |
