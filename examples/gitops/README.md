# GitOps example manifests

An internally consistent set of Ragnerock GitOps manifests: secrets, provider
configs, schemas, a skill, agents, a workflow, an endpoint, and an ingest
config. Apply the whole folder with the CLI:

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
so manifests can live anywhere in a repository alongside unrelated YAML. The
server orders documents by kind before applying, so file names and order don't
matter — the numeric prefixes are only for readability.

| File | Kind(s) | Scope |
| --- | --- | --- |
| `00-secrets.yaml` | `Secret` ×3 | account |
| `20-ai-config.yaml` | `AIProviderConfig` ×2 | account |
| `20-blob-config.yaml` | `BlobProviderConfig` | account |
| `20-db-config.yaml` | `DBProviderConfig` ×2 (BigQuery, Postgres) | account |
| `50-schema.yaml` | `Schema` ×3 (two output schemas, one memory schema) | project |
| `55-skill.yaml` | `Skill` | project |
| `60-agent.yaml` | `Agent` ×2 (LLM and code) | project |
| `70-workflow.yaml` | `Workflow` | project |
| `90-endpoint.yaml` | `Endpoint` | project |
| `95-ingest-config.yaml` | `IngestConfig` | project |

## Before a real apply

- **Project.** Project-scoped kinds name their project with the
  `ragnerock.com/project: alpha_research` annotation. Change it to an existing
  project, or drop the annotation to target the account's `Default` project.
- **Placeholders.** Values marked `REPLACE_ME` (API keys, the GCP project, the
  Azure vault URL) and the AWS secret id, buckets, and IP allow-list are
  placeholders. They apply as-is, but the credentials won't work until you
  substitute real ones.
- **Cloud secret managers.** `00-secrets.yaml` reads from GCP Secret Manager,
  AWS Secrets Manager, and Azure Key Vault. Install the matching extras
  (`pip install 'ragnerock[gcp,aws,azure]'`) and authenticate with each
  provider's usual tooling, or delete the blocks you don't use. `--dry-run`
  checks the references without fetching them.

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
files and from project-scoped kinds to account-scoped secrets.

See the [GitOps guide](../../docs/source/gitops.md) for the full reference.
