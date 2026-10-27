# Platform APIs

The [Session](sessions.md) models documents, annotations, operators, workflows, and jobs. Everything else on the platform — agent tools and skills, notebooks and assignments, search, endpoints, ingest sources, provider configs — is available on the low-level {class}`~ragnerock.client.RagnerockClient`, one *section* per API area:

```python
from ragnerock import Session, create_client, create_engine

engine = create_engine("ragnerock://token:rgnk_...@api.ragnerock.com/my_project")
client = engine.client            # shares the engine's connection and credentials
project_id = engine.project_id    # resolves the project (authenticates if needed)

# Or, for account-level work with no project:
client = create_client("ragnerock://token:rgnk_...@api.ragnerock.com")
```

Methods take path ids positionally and everything else by keyword, and return lenient response models: the commonly used fields are typed, and any other field the server returns is still available as an attribute. Errors raise the usual {doc}`SDK exceptions <errors>`. Requests that return `429` are retried automatically.

To manage configuration declaratively — skills, agents, workflows, endpoints, ingest configs, provider configs — prefer [GitOps manifests](gitops.md). The client is for scripting, inspection, and runtime operations.

## Agents, skills, and tools

Operators are called *agents* in the app. Beyond the session's {class}`~ragnerock.Operator`, agents can load **skills** (instruction packages) and call **tools** (MCP servers, catalog connectors, REST APIs).

```python
skill = client.skills.create(
    project_id=project_id,
    name="earnings_call_tone",
    description="How to judge sentiment in earnings-call language.",
    body="# Earnings-call tone\n\nTreat hedged phrasing as negative...",
)

tool = client.tools.create_mcp(
    project_id=project_id,
    name="Filings search",
    description="Search SEC filings by company and form type.",
    url="https://mcp.example.com/mcp",
)
functions = client.tools.discover(tool.id)      # list the functions it exposes

for t in client.tools.list(project_id).tools:
    print(t.name, t.kind)
```

Give an LLM operator access with `skill_ids` / `tool_ids` (see [Operators](operators.md)). `client.tools` also covers catalog connectors (`list_connectors`, `create_connector`), REST tools (`create_rest`, `test_rest_route`), OAuth sign-in for MCP servers (`oauth_start`, `oauth_disconnect`), and pasting an MCP client config (`parse_mcp_config`).

## Notebooks and assignments

A **notebook** is a conversation with an agent; `stream_input` sends a message and yields the response events as they arrive.

```python
nb = client.notebooks.open_conversation(project_id=project_id, agent_id=agent.id)
for event in client.notebooks.stream_input(
    nb.id, content="Summarize Q3 guidance", cell_type="message"
):
    print(event)   # one dict per streamed event
```

`client.cells` and `client.artifacts` read and edit a notebook's cells and the artifacts (tables, plots, citations) produced in it.

An **assignment** gives an agent a task to work on asynchronously; follow it with `stream`, and answer any questions it asks:

```python
from datetime import UTC, datetime, timedelta

a = client.assignments.create(
    project_id,
    agent_id=agent.id,
    task="Compare revenue guidance across the last four 10-Qs.",
    deadline=datetime.now(UTC) + timedelta(hours=2),
)
for event in client.assignments.stream(project_id, a.id):
    if event.kind == "status":
        print(event.assignment.status)

for q in client.assignments.questions().questions:
    client.assignments.answer(project_id, q.id, answer="Use fiscal quarters.")
```

## Search

```python
from ragnerock.client import ContentType

hits = client.search.search(
    project_id=project_id,
    query="revenue guidance",
    content_types=ContentType.DOCUMENTS | ContentType.CHUNKS,
)
for hit in hits.results:
    print(hit.score, hit.title, hit.content_preview)
```

Pass `regex=True` to match a case-insensitive regular expression instead of ranking by relevance.

## Workflows: schedules, inputs, outputs, and change requests

The session builds a workflow's node graph; `client.workflows` manages the rest:

| Method | Purpose |
| --- | --- |
| `set_schedule`, `clear_schedule`, `resume_schedule`, `schedule_preview` | Recurring runs from a crontab ({class}`~ragnerock.WorkflowSchedule`). |
| `set_resources`, `test_fetch` | Named inputs — files, or data pulled from a tool call or a web fetch (build them with `tool_call_resource` / `web_fetch_resource`). |
| `set_sinks` | Outputs: where results are delivered. |
| `run_now` | Run a workflow that has no file inputs. |
| `test_condition` | Evaluate a node's condition against sample upstream output. |
| `change_requests` | Review, approve, or reject changes proposed by `CHANGE_REQUEST` agents. |

```python
client.workflows.set_schedule(wf.id, cron="0 6 * * 1-5", timezone="America/New_York")
print(client.workflows.schedule_preview(cron="0 6 * * 1-5").fires)
```

Files that workflow outputs produce are **workflow artifacts**:

```python
page = client.workflow_artifacts.list(project_id, workflow_id=wf.id)
for art in page.artifacts:
    client.workflow_artifacts.download(art.id, f"./out/{art.id}")
df = client.workflow_artifacts.to_dataframe(page.artifacts[0].id)   # needs pandas
```

`client.jobs` adds batch runs (`create_runs_from_manifest` takes a JSONL file of run inputs), `run_all_ingest`, and output delivery status (`sink_deliveries`, `retry_sink_deliveries`).

## Endpoints

An **endpoint** serves a workflow (or a model-compatible API) over HTTP. Creating one returns its API key — the only time the key is shown.

```python
import time

ep = client.endpoints.create(project_id, name="sentiment_api", workflow_id=wf.id)
api_key = ep.api_key

task = client.endpoints.submit(ep.id, api_key=api_key, file_path="./call.pdf")
result = client.endpoints.poll(ep.id, task.task_id, api_key=api_key)
while result.status == "processing":
    time.sleep(2)
    result = client.endpoints.poll(ep.id, task.task_id, api_key=api_key)
print(result.result)
```

`get_stats`, `list_executions`, `redeploy`, and `regenerate_key` manage a deployed endpoint; `mcp_url` and `compat_base_url` give the URLs to point MCP clients or OpenAI / Anthropic / Gemini SDKs at.

## Ingest sources

Ingest configs pull documents into a project on a schedule — from S3, the web, or a SQL query.

```python
cfg = client.ingest_sources.create_config(
    project_id,
    name="filings_s3_sync",
    source={"source_type": "S3", "bucket": "my-filings", "prefix": "raw/", "region": "us-east-1"},
    cron="0 2 * * *",
)
run = client.ingest_sources.trigger(project_id, cfg.id)
print(client.ingest_sources.get_run(project_id, run.id).status)
```

`preview_sql` runs a SQL source's query without ingesting, and `list`, `list_runs`, `list_entries`, and `list_versions` inspect what a source has pulled.

## Documents, annotations, and queries

The session covers the common paths; the client adds:

- `client.documents`: richer listing filters (`statuses`, `filters`, sorting), per-document metadata (`get_metadata`, `delete_metadata_key`), and what the last ingest changed (`get_ingest_change`).
- `client.annotations`: edit history (`list_revisions`, `restore`) and schema-wide listings (`list_hydrated_by_schema`, `list_documents_with_schema_annotations`).
- `client.queries`: [saved queries](queries.md#saved-queries).

## Provider configuration

Account administrators can bring their own AI providers, embedding and image-summary models, databases, and blob storage. These are account-level, so `create_client` (no project) is enough.

```python
for cfg in client.ai_configs.list().configs:
    print(cfg.config_name, cfg.provider_type, cfg.status)

client.embedding_config.get()
client.db_configs.health(db_config_id)
client.web_access.set_policy(web_fetch_enabled=True, web_search_enabled=False)
```

| Section | Covers |
| --- | --- |
| `ai_configs` | LLM provider configs, their status, and which ones a user may select. |
| `embedding_config`, `image_summary_config` | The account's embedding and image-summary providers. |
| `db_configs` | Bring-your-own databases (PostgreSQL, BigQuery, Snowflake, Databricks, Oracle, Db2): create, validate, activate, health. |
| `blob_configs` | Bring-your-own object storage (GCS, S3, Azure, Oracle). |
| `web_access` | Whether agents may fetch and search the web, and the search provider key. |

Credentials passed to these methods are sent once and never returned; responses carry masked hints. In GitOps manifests, reference a `Secret` instead (see [Secrets](gitops.md#secrets)).

## Reference

See {mod}`ragnerock.client` for every section, method, and response model.
