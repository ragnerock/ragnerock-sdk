# Command-line interface

`pip install ragnerock` installs a `ragnerock` executable — a kubectl-style CLI for inspecting resources, applying [GitOps manifests](gitops.md), and running agents. It wraps the same [Session](sessions.md) and [GitOps](gitops.md) APIs you'd use from Python.

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
ragnerock get agents -o name | xargs -I{} ragnerock describe agent {}
```

Pass `NAME` to fetch exactly one:

```bash
ragnerock get task sentiment -o yaml
```

Additionally, use `--filter` to filter the resulting resources by resource values:

```bash
ragnerock get chunk --filter document=00000000-0000-0000-0000-000000000101
ragnerock get annotation --filter task=00000000-0000-0000-0000-000000000202
ragnerock get annotation --filter document=00000000-0000-0000-0000-000000000101 --filter task-name=sentiment
```

Filter keys `document`, `chunk`, and `task` take ids; `task-name` takes a task's name and is combined with `document`.

### `describe`
Get full details for one resource

```
ragnerock describe <kind> <NAME> [-o table|json|yaml|name]
```

By default describe outputs are formatted as YAML, however JSON is also available

```bash
ragnerock describe task sentiment                   # yaml, default
ragnerock describe task sentiment -o json           # explicit override
```

### `apply`

Apply GitOps manifests

```
ragnerock apply -f PATH [-f PATH ...] [--dry-run | --plan] [--no-seal]
  [--sealing-public-key PEM|@FILE] [-o table|json|yaml]
```

Uploads every Ragnerock manifest (`apiVersion: ragnerock.com/v1alpha2`) found across the sources in one request; the server upserts each object by name and reports what changed. Each `-f` may be a file, a directory (walked recursively for `*.yaml` / `*.yml`, skipping hidden entries), or `-` for STDIN. Non-Ragnerock YAML is ignored, so pointing `-f` at a whole repository is fine. `Secret` values are resolved locally and sealed to the instance's key before upload.

```bash
ragnerock apply -f manifests/ --dry-run   # what would be uploaded (offline, values elided)
ragnerock apply -f manifests/ --plan      # what would change (validated, then rolled back)
ragnerock apply -f manifests/             # apply
```

A document still on the retired `ragnerock.com/v1alpha1` is refused before anything is uploaded, even with `--dry-run`; see [Migrating to 3.0](migration.md#migrating-to-30).

`apply` never deletes. Exit codes: `0` when every object applied, `1` when the report shows a failure or the manifests can't be prepared (including a `v1alpha1` document), `2` for a server or network error. See [GitOps manifests](gitops.md) for kinds, secrets, sealing, and CI usage.

### `delete`

Remove a resource

```
ragnerock delete <kind> <NAME>
```

Deletes one `Document`, `DocumentFolder`, `Task`, or `Agent` by name:

```bash
ragnerock delete task sentiment
ragnerock delete agent ingest
ragnerock delete folder q3-filings
```

### `run`

Run an agent

```
ragnerock run <agent-name> --documents NAME[,NAME...] \
  [--wait] [--poll-interval 2] [--timeout 300]
```

Looks up the agent and documents by name, calls `session.run(...)`, and prints the first run's id (`run/<id> started`).

You can optionally pass `--wait` to block until the run reaches a terminal state:

```bash
ragnerock run ingest --documents q3-report.pdf --wait --timeout 600
```

Exit codes for `--wait`:

| code | Meaning                     |
| ---- | --------------------------- |
| `0`  | Run succeeded               |
| `1`  | Agent or document not found |
| `2`  | Run failed or timed out     |

### `query`

Run annotation SQL

```
ragnerock query "SELECT ..." [-o table|json] [--limit N]
```

```bash
ragnerock query "SELECT document_id, label FROM sentiment LIMIT 20"
ragnerock query "SELECT COUNT(*) FROM sentiment WHERE label = 'negative'" -o json
```

Tables are named after slugified task names. For example, the task `Document Properties` is normalized to `document_properties` in queries.

### `version`

Display the current CLI version.

```bash
ragnerock version
```

## Resource kinds

| CLI name | Aliases | Notes |
| --- | --- | --- |
| `Document` | `doc`, `docs`, `document`, `documents` | |
| `DocumentFolder` | `folder`, `folders`, `documentfolder`, `documentfolders`, `document-folder`, `document-folders` | |
| `Task` | `task`, `tasks` | |
| `Agent` | `agent`, `agents` | |
| `Annotation` | `anno`, `annos`, `annotation`, `annotations` | Requires `--filter document=...`, `--filter chunk=...`, or `--filter task=...` when listing. |
| `Chunk` | `chunk`, `chunks` | Read-only. Requires `--filter document=...` when listing; no name lookup. |
| `Page` | `page`, `pages` | Read-only. Requires `--filter document=...`; no name lookup. |
| `Run` | `run`, `runs` | Read-only. Created via `ragnerock run`. |

Read-only kinds for the rest of the platform. Look them up by name (or `title`, `config_name`, `file_name`, `slug`) or by id; manage them with [GitOps manifests](gitops.md) or the [Platform APIs](platform.md).

| CLI name | Aliases | Scope |
| --- | --- | --- |
| `Project` | `project`, `projects`, `proj` | account |
| `Skill` | `skill`, `skills` | project |
| `Tool` | `tool`, `tools` | project |
| `Endpoint` | `endpoint`, `endpoints`, `ep`, `eps` | project |
| `Notebook` | `notebook`, `notebooks`, `nb`, `nbs` | project |
| `SavedQuery` | `savedquery`, `savedqueries`, `saved-query`, `saved-queries`, `sq` | project |
| `OutputArtifact` | `artifact`, `artifacts`, `outputartifact`, `outputartifacts`, `output-artifact`, `output-artifacts` | project |
| `IngestSource` | `ingestsource`, `ingestsources`, `ingest-source`, `ingest-sources` | project |
| `IngestConfig` | `ingestconfig`, `ingestconfigs`, `ingest-config`, `ingest-configs` | project |
| `AIConfig` | `aiconfig`, `aiconfigs`, `ai-config`, `ai-configs` | account |
| `DBConfig` | `dbconfig`, `dbconfigs`, `db-config`, `db-configs` | account |
| `BlobConfig` | `blobconfig`, `blobconfigs`, `blob-config`, `blob-configs` | account |

```bash
ragnerock get endpoints
ragnerock describe skill earnings_call_tone
ragnerock get ai-configs -o json
```

Matching is case-insensitive. The 2.x kinds and aliases (`Operator`/`op`, `Workflow`/`wf`, `Job`, `DocumentGroup`/`grp`, `WorkflowArtifact`, `agent-tool`) were removed in 3.0; see [Migrating to 3.0](migration.md#migrating-to-30).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | User / lookup error — missing env var, unknown kind, resource not found, invalid or retired (`v1alpha1`) manifest, failed apply. |
| 2 | Server or runtime error — failed run, timeout, unexpected API response. |
