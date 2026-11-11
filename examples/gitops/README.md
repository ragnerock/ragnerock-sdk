# GitOps example manifests

An internally consistent set of Ragnerock GitOps manifests (`apiVersion:
ragnerock.com/v1alpha2`): a project, secrets, provider configs, a role and a
policy with their assignments, schemas, a skill, tasks, an agent, an endpoint,
and an ingest config. Apply the whole folder with the CLI:

```bash
# fromEnv secrets are read from your shell — set them first:
export GEMINI_EMBED_KEY="AIza...REPLACE_ME"

export RAGNEROCK_HOST=api.ragnerock.com
export RAGNEROCK_API_TOKEN=rgnk_...

ragnerock apply -f examples/gitops --dry-run   # preview the upload offline (values elided)
ragnerock apply -f examples/gitops --plan      # validate against your account, then roll back
ragnerock apply -f examples/gitops             # apply
```

Only documents whose `apiVersion` is in the `ragnerock.com/` group are applied,
so manifests can live anywhere in a repository alongside unrelated YAML. A
document still on the retired `ragnerock.com/v1alpha1` is refused before
anything is uploaded; see "Migrating to 3.0" in the SDK docs for what changed.

Files are numbered by **apply rank** for readability only: the server sorts
every document by rank before applying, so file names and order don't affect
the result. One kind per file (a few files carry two or three closely related
objects).

| File | Kind(s) | Rank | Scope |
| --- | --- | --- | --- |
| `00-secrets.yaml` | `Secret` ×3 | 15 | account |
| `10-project.yaml` | `Project` | 10 | account |
| `20-ai-config.yaml` | `AIProviderConfig` ×2 | 20 | account |
| `20-blob-config.yaml` | `BlobProviderConfig` | 20 | account |
| `20-db-config.yaml` | `DBProviderConfig` ×2 (BigQuery, Postgres) | 20 | account |
| `30-role.yaml` | `Role` | 30 | account |
| `32-role-assignment.yaml` | `RoleAssignment` | 32 | account |
| `40-policy.yaml` | `Policy` | 40 | account |
| `42-policy-assignment.yaml` | `PolicyAssignment` | 42 | account |
| `50-schema.yaml` | `Schema` ×3 (two output schemas, one memory schema) | 50 | project |
| `55-skill.yaml` | `Skill` | 55 | project |
| `60-task.yaml` | `Task` ×2 (LLM and code) | 60 | project |
| `70-agent.yaml` | `Agent` | 70 | project |
| `90-endpoint.yaml` | `Endpoint` | 90 | project |
| `95-ingest-config.yaml` | `IngestConfig` | 95 | project |

## Before a real apply

- **Project.** Project-scoped kinds name their project with the
  `ragnerock.com/project: alpha_research` annotation, and `10-project.yaml`
  creates that project. To use one you already have, change the annotation (and
  drop `10-project.yaml`), or drop the annotation to target the account's
  `Default` project.
- **People and teams.** The project `owner`, the `RoleAssignment` members, and
  the `PolicyAssignment` principals use `example.com` addresses and a `research`
  team. Replace them with users and teams in your account.
- **Placeholders.** Values marked `REPLACE_ME` (API keys, the GCP project, the
  Azure vault URL) and the AWS secret id, buckets, and IP allow-list are
  placeholders. They apply as-is, but the credentials won't work until you
  substitute real ones.
- **Cloud secret managers.** `00-secrets.yaml` reads from GCP Secret Manager,
  AWS Secrets Manager, and Azure Key Vault. Install the matching extras
  (`pip install 'ragnerock[gcp,aws,azure]'`) and authenticate with each
  provider's usual tooling, or delete the blocks you don't use. `--dry-run`
  checks the references without fetching them.
- **Permissions.** The applying user needs `create` on each kind's IAM noun to
  add an object, and `update` to change one that already exists.

## Secret sources

All six sources resolve on your machine (or CI runner) and are sealed to the
instance's public key before upload; nothing recoverable crosses the wire.

| Source | Example key | Value comes from |
| --- | --- | --- |
| `stringData` | `llm_credentials.anthropicApiKey` | inline plaintext |
| `data` | `db_credentials.credentials.json` | inline base64 |
| `fromEnv` | `llm_credentials.geminiEmbedKey` | an environment variable |
| `fromGcpSecretManager` | `db_credentials.pgDsn` | GCP Secret Manager |
| `fromAwsSecretsManager` | `blob_credentials.aws` | AWS Secrets Manager |
| `fromAzureKeyVault` | `llm_credentials.openaiApiKey` | Azure Key Vault (via `jsonField`) |

Configs reference secrets by `secretKeyRef: {name, key}`, including across
files and from project-scoped kinds to account-scoped secrets
(`95-ingest-config.yaml` uses the account-scoped `blob_credentials`).

## Notes

- **Tasks and agents.** A `Task` does the work: an LLM task (a
  `generationPrompt`, optionally a `model` block and `skills`) or a code task
  (`taskKind: code` plus a `codeSource` snippet). `taskKind` is explicit (absent
  means `llm`), and the two payloads are mutually exclusive. An `Agent` wires
  tasks into a DAG: each node names its task with `task:`, and `onError` is
  `retry`, `skip_node`, or `fail_run`.
- **`Task.template`** is omitted. Set it only if a matching `TaskTemplate`
  already exists, or apply fails resolving the reference.
- **Endpoints** deploy an agent (`sourceAgent`), and `returnFields` name the
  producing task (`task:`), not a node.
- **Bindings are always separate documents.** A `Role` or `Policy` never
  carries its own members or principals; `32-role-assignment.yaml` and
  `42-policy-assignment.yaml` hold the grants, and a `spec` that inlines them is
  rejected. Assignments are additive: applying one never removes a binding it
  omits.
- **Policy resources** are `<noun>/*`, `<noun>/<project>/<id>` (either part may
  be `*`), or `*`. The nouns are the API's: `task`, `agent`, `run`,
  `documentfolder`, and so on.
- **`Schema.isMemory`** targets a different namespace, not just a different
  flag: the schema becomes one of the project's `mem_*` memory tables. It is
  import-only (export never emits memory schemas), takes no folder, may only
  gain optional fields once it holds records, and needs `create` on the
  `memory` noun on top of `schema`.

See the [GitOps guide](../../docs/source/gitops.md) for the full reference.
