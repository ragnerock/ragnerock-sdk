# GitOps manifests

Ragnerock configuration — projects, secrets, AI and storage provider configs, roles and policies, schemas, skills, tasks, agents, endpoints, and ingest configs — can be declared as YAML and applied from the command line or from Python. Keep the manifests in a repository and apply them in CI, and every change to your Ragnerock setup is reviewed, versioned, and reproducible.

```bash
ragnerock apply -f manifests/
```

Apply is an **upsert by name**: objects that don't exist yet are created, existing ones are updated to match the manifest, and objects that already match report `unchanged`. Objects absent from the manifests are **never deleted** — use [`ragnerock delete`](cli.md#delete) or the UI to remove them.

## Manifest shape

Every manifest is a YAML document in the `ragnerock.com/` API group. The current version is `ragnerock.com/v1alpha2`:

```yaml
apiVersion: ragnerock.com/v1alpha2
kind: Task
metadata:
  name: earnings_sentiment
  annotations:
    ragnerock.com/project: alpha_research   # project-scoped kinds only
    ragnerock.com/folder: tasks             # optional
spec:
  description: "Extracts sentiment from earnings calls"
  generationPrompt: "Classify the sentiment of this earnings call excerpt."
  chunkType: paragraph
  schema: sentiment_score
```

- `metadata.name` is the object's identity: it's how apply decides between create and update.
- Project-scoped kinds name their project with the `ragnerock.com/project` annotation. Omit it to target the account's `Default` project.
- `spec` fields are camelCase. The server validates each kind's `spec` and reports problems per object.

Only documents whose `apiVersion` starts with `ragnerock.com/` are applied, so manifests can sit anywhere in a repository alongside CI configs, Kubernetes manifests, and other YAML — point `apply` at the repository root if you like.

A document still on the retired `ragnerock.com/v1alpha1` is refused on the client, before anything is uploaded (so `--dry-run` refuses it too). The error names the file and the document's position in it, counting from zero:

```text
GitOpsError: manifests/agents.yaml: document[0]: This manifest uses apiVersion v1alpha1; export it again from Ragnerock to get v1alpha2. (Suggestion: In v1alpha2, a `Task` is what v1alpha1 called an `Agent`, and an `Agent` is what it called a `Workflow`; several spec fields were renamed too. See 'Migrating to 3.0' in the SDK documentation.)
```

Re-export the objects from Ragnerock, or update the manifests by hand with the tables in [Migrating to 3.0](migration.md#gitops-manifests). Any other version is passed through for the server to judge. Both versions are exported as constants: {data}`~ragnerock.gitops.discovery.API_VERSION` and {data}`~ragnerock.gitops.discovery.RETIRED_API_VERSIONS` (also importable from `ragnerock.gitops`).

### Kinds

| Kind | Scope | What it declares |
| --- | --- | --- |
| `Project` | account | A project, its owner, and how long succeeded runs are kept before they're archived (`autoArchiveSucceededRunsAfterDays`). |
| `Secret` | account | Credentials, referenced by other kinds via `secretKeyRef`. See [Secrets](#secrets). |
| `AIProviderConfig` | account | A bring-your-own LLM provider (and optional embedding model). |
| `BlobProviderConfig` | account | Bring-your-own object storage. |
| `DBProviderConfig` | account | Bring-your-own database (BigQuery, PostgreSQL, …). |
| `WebAccessConfig` | account | Whether the account may fetch and search the web, and its search-provider credential. |
| `Role` | account | A named role. Its members are bound by a `RoleAssignment`. |
| `RoleAssignment` | account | The users (`members`) and `teams` in a role. Additive. |
| `Policy` | account | `permissions` (IAM verbs) on `resources` (IAM nouns, e.g. `task/*`). Its principals are bound by a `PolicyAssignment`. |
| `PolicyAssignment` | account | The `role:`, `team:`, and `user:` principals a policy grants to. Additive. |
| `Schema` | project | An output schema tasks write to, or (`isMemory: true`) a memory schema. |
| `Skill` | project | An instruction package tasks load on demand. |
| `Tool` | project | A tool tasks and notebooks can call; `taskEnabled` controls whether tasks may use it. |
| `Task` | project | An LLM task (`generationPrompt`) or a code task (`taskKind: code` + `codeSource`). |
| `Agent` | project | A DAG of task nodes (`nodes[].task`), with conditions, retries, decorators, `inputs`, and `outputs`. |
| `Endpoint` | project | A deployed agent (`sourceAgent`) served over HTTP. |
| `IngestConfig` | project | A recurring ingest source (e.g. an S3 sync). |

[`examples/gitops/`](https://github.com/ragnerock/ragnerock-sdk/tree/main/examples/gitops) has a complete, internally consistent set covering every kind above except `Tool` and `WebAccessConfig`.

A `Policy`'s `resources` are `<noun>/*`, `<noun>/<project>/<id>` (either part may be `*`), or `*`. The nouns are the API's: `document`, `documentfolder`, `task`, `agent`, `run`, `annotation`, `schema`, and so on.

### Ordering and references

All documents found across every `-f` source are uploaded **together, in one request**. The server sorts them by kind before applying (the project, secrets and provider configs, roles and policies, then schemas, skills, tasks, agents, endpoints, and ingest configs), so file names and document order don't matter. References resolve across files: a `secretKeyRef` in `configs.yaml` finds a `Secret` declared in `secrets.yaml`, and an agent node's `task` finds a `Task` declared anywhere in the set.

## Secrets

A `Secret` holds key/value credentials. Write each value from one of six sources:

| Source | Value comes from |
| --- | --- |
| `stringData` | inline plaintext in the manifest |
| `data` | inline base64 in the manifest |
| `fromEnv` | an environment variable of the process running `apply` |
| `fromGcpSecretManager` | GCP Secret Manager |
| `fromAwsSecretsManager` | AWS Secrets Manager |
| `fromAzureKeyVault` | Azure Key Vault |

```yaml
apiVersion: ragnerock.com/v1alpha2
kind: Secret
metadata:
  name: llm_credentials
spec:
  fromEnv:
    anthropicApiKey: ANTHROPIC_API_KEY
  fromGcpSecretManager:
    geminiKey:
      secret: gemini-api-key          # short ID, or projects/<p>/secrets/<s>[/versions/<v>]
      project: my-gcp-project         # optional; defaults to the ADC project
      version: latest                 # optional
  fromAwsSecretsManager:
    pgDsn:
      secretId: prod/warehouse-dsn    # name or ARN
      region: us-east-1               # optional
      jsonField: dsn                  # optional: pull one field out of a JSON secret
  fromAzureKeyVault:
    openaiApiKey:
      vaultUrl: https://my-vault.vault.azure.net
      secret: openai-key
```

Other kinds reference a secret key by name — never by value:

```yaml
apiKey:
  secretKeyRef:
    name: llm_credentials
    key: anthropicApiKey
```

**Every source is resolved on the client**, by `ragnerock apply`, using the environment and cloud identity of the machine running it. The server resolves none of them (and rejects a manifest that still carries one), so a manifest can never make the server read a secret with *its* identity. A key may come from only one source, and a referenced environment variable that is unset fails the run before anything is sent.

### Cloud secret managers

The cloud SDKs are optional. Install the extras you need:

```bash
pip install 'ragnerock[gcp]'      # GCP Secret Manager
pip install 'ragnerock[aws]'      # AWS Secrets Manager
pip install 'ragnerock[azure]'    # Azure Key Vault
```

Authenticate with each provider's usual tooling first — `gcloud auth application-default login`, an AWS profile, `az login`, or in CI the provider's login action (`google-github-actions/auth`, `aws-actions/configure-aws-credentials`, `azure/login`). Two keys that name the same remote secret cost one API call.

### Sealing

Before upload, every resolved value is **sealed** — encrypted to a public key that only the target instance can open — so the request body carries no recoverable plaintext. Sealing is automatic: `apply` fetches the key from the instance and prints its fingerprint.

```text
Sealing secrets to key sha256:3f1c… (fetched from the instance).
```

To also defend against an intermediary that terminates TLS, **pin** the key instead of fetching it over the connection it protects. Fetch it once (`GET /api/gitops/sealing-key`, or `client.gitops.sealing_key()`), store it, and pass it in:

```bash
ragnerock apply -f manifests/ --sealing-public-key @sealing-key.pem
# or
export RAGNEROCK_SEALING_PUBLIC_KEY="$(cat sealing-key.pem)"
```

A pinned key is never reconciled against what the server says.

`--no-seal` uploads values as plaintext. Use it only against an instance with no sealing key configured — `apply` fails rather than silently downgrading, and warns when sealing is off and secrets are present. A manifest set with no secret values never needs a sealing key.

## Previewing changes

Two rehearsal modes answer different questions:

`--dry-run` — *what would be uploaded?* Entirely offline: no server, no credentials, no cloud calls. Prints the manifest exactly as it would be uploaded, with every secret value elided. Cloud references are parsed but not fetched, and `fromEnv` variables must still be set.

```bash
ragnerock apply -f manifests/ --dry-run
```

`--plan` — *what would change?* Uploads to your real account, has the server validate everything and report what it would create or update, then rolls the whole apply back. Because it runs against the account, it catches problems a dry run can't: a task referencing a schema that doesn't exist, a model binding that won't resolve, a permission you lack.

```bash
ragnerock apply -f manifests/ --plan
```

## Reading the report

```text
  Secret            llm_credentials      created
  AIProviderConfig  anthropic_primary    unchanged
  Task              earnings_sentiment   updated
      ⚠ model binding 'anthropic_primary' did not resolve in this account
  Agent             filing_pipeline      error
      ↳ node 'recheck': task 'missing_task' does not exist

FAILED — 2 changed, 1 warning(s), 4 object(s)
```

- Each object reports `created`, `updated`, `unchanged`, or `error`, with errors (`↳`) and warnings (`⚠`) beneath it.
- **Warnings** mean the object applied but something about it will bite at run time — read them. They don't fail the apply.
- The exit code is `0` when the report is OK and `1` when anything failed. A server or network error exits `2`.
- `-o json` or `-o yaml` prints the full report for scripting.

An `Endpoint` created by apply gets a server-generated API key that is never returned in the report; rotate it from the endpoint's page (or `client.endpoints.regenerate_key(...)`) to get one.

The token's user needs `create` permission on each kind's IAM noun to add an object, and `update` to change an existing one.

## Running in CI

```yaml
# .github/workflows/ragnerock.yml
name: Apply Ragnerock config
on:
  pull_request:
  push:
    branches: [main]

jobs:
  apply:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write   # for cloud secret managers via OIDC
    env:
      RAGNEROCK_HOST: api.ragnerock.com
      RAGNEROCK_API_TOKEN: ${{ secrets.RAGNEROCK_API_TOKEN }}
      RAGNEROCK_SEALING_PUBLIC_KEY: ${{ vars.RAGNEROCK_SEALING_PUBLIC_KEY }}
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}   # every fromEnv var
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - run: pip install 'ragnerock[gcp]'
      - run: ragnerock apply -f manifests/ --plan
        if: github.event_name == 'pull_request'
      - run: ragnerock apply -f manifests/
        if: github.ref == 'refs/heads/main'
```

Under GitHub Actions, `apply` registers every resolved secret value (and each line of multi-line values) for log masking before anything else can print it, and raises each per-object warning as an annotation on the Actions summary page. Finding no Ragnerock manifests is a clean no-op, so the job is safe to run on every push.

## From Python

The CLI wraps `ragnerock.gitops`; use it directly for custom pipelines.

```python
from ragnerock import create_client
from ragnerock.gitops import apply_manifests

client = create_client("ragnerock://token:rgnk_...@api.ragnerock.com")
report = apply_manifests(client, ["manifests/"], plan=True)

for result in report.results:
    print(result.kind, result.name, result.action, result.warnings)
assert report.ok
```

{func}`~ragnerock.create_client` accepts the same connection strings as {func}`~ragnerock.create_engine`, but the project is optional. To inspect the upload first, load and prepare it yourself:

```python
from ragnerock.gitops import load_manifests, prepare_manifest, render_dry_run

manifests = load_manifests(["manifests/"])
print(render_dry_run(manifests).to_yaml())          # offline, values elided

prepared = prepare_manifest(manifests, client=client)
report = client.gitops.apply(prepared.to_yaml(), dry_run=True)
```

See {mod}`ragnerock.gitops` for the full API.
