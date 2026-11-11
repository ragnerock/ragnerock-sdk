# Platform APIs

The [Session](sessions.md) models documents, annotations, tasks, agents, and runs. Everything else on the platform — tools and skills, notebooks and assignments, search, endpoints, ingest sources, provider configs — is available on the low-level {class}`~ragnerock.client.RagnerockClient`, one *section* per API area:

```python
from ragnerock import Session, create_client, create_engine

engine = create_engine("ragnerock://token:rgnk_...@api.ragnerock.com/my_project")
client = engine.client            # shares the engine's connection and credentials
project_id = engine.project_id    # resolves the project (authenticates if needed)

# Or, for account-level work with no project:
client = create_client("ragnerock://token:rgnk_...@api.ragnerock.com")
```

Methods take path ids positionally and everything else by keyword, and return lenient response models: the commonly used fields are typed, and any other field the server returns is still available as an attribute. Errors raise the usual {doc}`SDK exceptions <errors>`. Requests that return `429` are retried automatically.

To manage configuration declaratively — skills, tasks, agents, endpoints, ingest configs, provider configs — prefer [GitOps manifests](gitops.md). The client is for scripting, inspection, and runtime operations.

## Skills and tools

Beyond the session's {class}`~ragnerock.resources.task.Task`, an LLM task can load **skills** (instruction packages) and call **tools** (MCP servers, catalog connectors, REST APIs).

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

Give an LLM task access with `skill_ids` / `tool_ids` (see [Tasks](tasks.md)). Pass `task_enabled=False` when creating or updating a tool to keep it off tasks. `client.tools` also covers catalog connectors (`list_connectors`, `create_connector`), REST tools (`create_rest`, `test_rest_route`), OAuth sign-in for MCP servers (`oauth_start`, `oauth_disconnect`), and pasting an MCP client config (`parse_mcp_config`).

## Notebooks and assignments

A **notebook** is a conversation with a task; `stream_input` sends a message and yields the response events as they arrive.

```python
nb = client.notebooks.open_conversation(project_id=project_id, task_id=my_task.id)
for event in client.notebooks.stream_input(
    nb.id, content="Summarize Q3 guidance", cell_type="message"
):
    print(event)   # one dict per streamed event
```

`client.cells` and `client.artifacts` read and edit a notebook's cells and the artifacts (tables, plots, citations) produced in it.

An **assignment** gives a task instructions to work on asynchronously; follow it with `stream`, and answer any questions it asks:

```python
from datetime import UTC, datetime, timedelta

a = client.assignments.create(
    project_id,
    task_id=my_task.id,
    instructions="Compare revenue guidance across the last four 10-Qs.",
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

## Agents: schedules, inputs, outputs, and change requests

The session builds an agent's node graph; `client.agents` manages the rest:

| Method | Purpose |
| --- | --- |
| `set_schedule`, `clear_schedule`, `resume_schedule`, `schedule_preview` | Recurring runs from a crontab ({class}`~ragnerock.resources.agent.AgentSchedule`). |
| `set_inputs`, `test_fetch` | Named inputs — files, or data pulled from a tool call or a web fetch (build them with `tool_call_input` / `web_fetch_input`). |
| `set_outputs` | Outputs: where results are delivered (notifications, email, artifacts, change requests). |
| `run_now` | Run an agent whose inputs are all fetched, or that has none. |
| `test_condition` | Evaluate a node's condition against sample upstream output. |
| `change_requests` | Review, approve, reject, or backfill the change requests an agent's change-request outputs open. |
| `draft_changes`, `keep_draft_changes`, `refresh_draft_changes` | Inspect a draft of an agent, and keep or refresh the shared tasks it changes. |

```python
client.agents.set_schedule(my_agent.id, cron="0 6 * * 1-5", timezone="America/New_York")
print(client.agents.schedule_preview(cron="0 6 * * 1-5").fires)
```

Files that an agent's artifact outputs produce are **output artifacts**:

```python
page = client.output_artifacts.list(project_id, agent_id=my_agent.id)
for art in page.artifacts:
    client.output_artifacts.download(art.id, f"./out/{art.id}")
df = client.output_artifacts.to_dataframe(page.artifacts[0].id)   # needs pandas
```

### Runs and output deliveries

`client.runs` lists, inspects, and controls runs beyond the session's {class}`~ragnerock.resources.run.Run`:

| Method | Purpose |
| --- | --- |
| `create` | Start runs: fan out agents over documents (`agent_ids=`, `document_ids=`), or bind inputs explicitly (`agent_id=`, `runs=`). |
| `create_from_manifest` | Batch runs from a JSONL file of run inputs. |
| `run_all_ingest` | Run an agent over everything its ingest input has pulled. |
| `cancel`, `retry`, `rerun` | Stop a run, retry a failed one, or run a succeeded one again as a new run. |
| `output_deliveries`, `retry_output_deliveries` | See whether a run's outputs were delivered, and retry the ones that failed. |

`create`, `rerun`, and `agents.run_now` return the new `run_ids`, with matching `provenance_ids` that record what each run pinned when it was created.

## Endpoints

An **endpoint** serves an agent (or a model-compatible API) over HTTP. Creating one returns its API key — the only time the key is shown.

```python
import time

ep = client.endpoints.create(project_id, name="sentiment_api", agent_id=my_agent.id)
api_key = ep.api_key

task = client.endpoints.submit(ep.id, api_key=api_key, file_path="./call.pdf")
result = client.endpoints.poll(ep.id, task.task_id, api_key=api_key)
while result.status == "processing":
    time.sleep(2)
    result = client.endpoints.poll(ep.id, task.task_id, api_key=api_key)
print(result.result)
```

The public endpoint contract is unchanged in 3.0: a submission still returns a `task_id` (an execution, not a {class}`~ragnerock.resources.task.Task`), and results still carry `ragnerock_metadata.workflow_id`. `get_stats`, `list_executions`, `redeploy`, and `regenerate_key` manage a deployed endpoint; `mcp_url` and `compat_base_url` give the URLs to point MCP clients or OpenAI / Anthropic / Gemini SDKs at.

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

- `client.documents`: richer listing filters (`statuses`, `filters`, sorting), documents by folder (`list_by_document_folder`), per-document metadata (`get_metadata`, `delete_metadata_key`), and what the last ingest changed (`get_ingest_change`).
- `client.document_folders`: create, rename, and delete [document folders](documents.md#document-folders).
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
| `web_access` | Whether the account may fetch and search the web, and the search provider key. |

Credentials passed to these methods are sent once and never returned; responses carry masked hints. In GitOps manifests, reference a `Secret` instead (see [Secrets](gitops.md#secrets)).

## Reference

See {mod}`ragnerock.client` for every section, method, and response model.
