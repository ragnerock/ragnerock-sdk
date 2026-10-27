# Command-line interface

`pip install ragnerock` installs a `ragnerock` executable — a kubectl-style CLI for inspecting resources, applying [GitOps manifests](gitops.md), and running workflows. It wraps the same [Session](sessions.md) and [GitOps](gitops.md) APIs you'd use from Python.

## Installation

```bash
pip install ragnerock
ragnerock --help
```

The CLI ships in the main package. To source GitOps secrets from a cloud secret manager, also install the matching extra (`ragnerock[gcp]`, `ragnerock[aws]`, or `ragnerock[azure]`).

## Configuration

The CLI reads credentials from environment variables. Two equivalent forms:

**Full connection string**

```bash
export RAGNEROCK_CONNECTION_STRING="ragnerock://token:rgnk_...@api.ragnerock.com/my_project"
```

See [Connecting](connecting.md) for every connection-string form.

**Split variables**

| Variable | Purpose |
|---|---|
| `RAGNEROCK_HOST` | Host or full URL (`api.ragnerock.com` or `https://api.ragnerock.com`). Bare hosts default to `https://`. |
| `RAGNEROCK_API_TOKEN` | Personal API token (`rgnk_…`). Use this, or email + password. |
| `RAGNEROCK_EMAIL` | Account email (with `RAGNEROCK_PASSWORD`). |
| `RAGNEROCK_PASSWORD` | Account password. |
| `RAGNEROCK_PROJECT` | Project name to scope every command to. Not needed for `apply`. |
| `RAGNEROCK_SEALING_PUBLIC_KEY` | Optional pinned key for sealing GitOps secrets (see [Sealing](gitops.md#sealing)). |

`RAGNEROCK_CONNECTION_STRING` will always overwrite the split variables if set. `ragnerock apply` is account-level, so it accepts a connection string without a `/project` path, and doesn't require `RAGNEROCK_PROJECT`.

```bash
# CI example
export RAGNEROCK_HOST=api.ragnerock.com
export RAGNEROCK_API_TOKEN="$RAGNEROCK_CI_TOKEN"
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

Apply GitOps manifests

```
ragnerock apply -f PATH [-f PATH ...] [--dry-run | --plan] [--no-seal]
  [--sealing-public-key PEM|@FILE] [-o table|json|yaml]
```

Uploads every Ragnerock manifest (`apiVersion: ragnerock.com/...`) found across the sources in one request; the server upserts each object by name and reports what changed. Each `-f` may be a file, a directory (walked recursively for `*.yaml` / `*.yml`, skipping hidden entries), or `-` for STDIN. Non-Ragnerock YAML is ignored, so pointing `-f` at a whole repository is fine. `Secret` values are resolved locally and sealed to the instance's key before upload.

```bash
ragnerock apply -f manifests/ --dry-run   # what would be uploaded (offline, values elided)
ragnerock apply -f manifests/ --plan      # what would change (validated, then rolled back)
ragnerock apply -f manifests/             # apply
```

`apply` never deletes. Exit codes: `0` when every object applied, `1` when the report shows a failure or the manifests can't be prepared, `2` for a server or network error. See [GitOps manifests](gitops.md) for kinds, secrets, sealing, and CI usage.

### `delete`

Remove a resource

```
ragnerock delete <kind> <NAME>
```

Deletes one `Document`, `DocumentGroup`, `Operator`, or `Workflow` by name:

```bash
ragnerock delete op sentiment
ragnerock delete wf ingest
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
| 1 | User / lookup error — missing env var, unknown kind, resource not found, invalid manifest, failed apply. |
| 2 | Server or runtime error — failed job, timeout, unexpected API response. |
