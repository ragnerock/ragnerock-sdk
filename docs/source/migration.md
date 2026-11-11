# Migration guides

## Migrating to 3.0

Ragnerock renamed its vocabulary across the product, the REST API, and GitOps, so that the API uses the same words as the app. Version 3.0 of the SDK follows. It is a clean break: the old names are gone, with no deprecated aliases in Python or the CLI.

**2.x SDKs cannot talk to the renamed API.** The old routes no longer exist, and the server refuses `ragnerock.com/v1alpha1` manifests. Upgrade to 3.0 and update your code, manifests, and SQL with the tables below.

### The new words

| 2.x | 3.0 |
| --- | --- |
| workflow (a DAG of nodes) | **agent** |
| operator (what a node runs; called an "agent" in v1alpha1 GitOps and the app) | **task** |
| job (one execution against one document) | **run** |
| workflow run (what a run pinned when it was created) | **run provenance**, `provenance_id` |
| document group | **document folder** |
| workflow resources / sinks | agent **inputs** / **outputs** |
| workflow artifacts | **output artifacts** |
| agent tools | **tools** |
| halt | **pause** |

"Agent" changes meaning: in v1alpha1 manifests (and the app's old wording) an agent was what is now a task, and in 3.0 an agent is what was a workflow. If you rename with search and replace, rename agent → task *before* workflow → agent, or the two merge.

### GitOps manifests

Manifests move to `apiVersion: ragnerock.com/v1alpha2`. `ragnerock apply` (and {func}`~ragnerock.gitops.discovery.load_manifests`) refuses a `v1alpha1` document before anything is uploaded, even on `--dry-run`, with the server's message, the file name, and the document's index:

```text
GitOpsError: manifests/agents.yaml: document[0]: This manifest uses apiVersion v1alpha1; export it again from Ragnerock to get v1alpha2. (Suggestion: In v1alpha2, a `Task` is what v1alpha1 called an `Agent`, and an `Agent` is what it called a `Workflow`; ...)
```

The quickest fix is to export the objects again from Ragnerock, which now exports `v1alpha2`. To update manifests by hand:

| v1alpha1 | v1alpha2 |
| --- | --- |
| `apiVersion: ragnerock.com/v1alpha1` | `apiVersion: ragnerock.com/v1alpha2` |
| `kind: Agent` | `kind: Task` |
| `kind: Workflow` | `kind: Agent` |

The other kinds keep their names. Spec fields that changed:

| Kind (v1alpha2) | v1alpha1 field | v1alpha2 field |
| --- | --- | --- |
| `Task` | `operatorKind` | `taskKind` |
| `Task` | `template` names an `OperatorTemplate` | `template` names a `TaskTemplate` |
| `Task` | `tools: [list_operators]` | `tools: [list_task_tables]` (the system tool's new slug) |
| `Task` | `notificationTemplate`, `messageTemplate`, `changeRequestPrompt`, `changeRequestSignal` | removed |
| `Agent` | `resources` | `inputs` |
| `Agent` | `sinks` | `outputs` |
| `Agent` | `nodes[].agent` | `nodes[].task` |
| `Agent` | `nodes[].context[].resource` | `nodes[].context[].input` |
| `Agent` | `onError: fail_job` (nodes and outputs) | `onError: fail_run` |
| `Tool` | `workflowEnabled` | `taskEnabled` |
| `Tool` | `systemKey: list_operators` | `systemKey: list_task_tables` |
| `Endpoint` | `sourceWorkflow` | `sourceAgent` |
| `Endpoint` | `returnFields[].agent` | `returnFields[].task` |
| `Endpoint` | `autoArchiveJobs` | `autoArchiveRuns` |
| `Project` | `autoArchiveSucceededJobsAfterDays` | `autoArchiveSucceededRunsAfterDays` |
| `Policy` | `resources` with the old IAM nouns | the new nouns (below) |

Unchanged: a node condition's `operator` key (the comparison, as in `operator: "=="`), `nodes[].target`, the keys inside each input and output, `skip_node` and `retry`, and every other kind's spec.

`examples/gitops/` now also covers `Project`, `Role`, `RoleAssignment`, `Policy`, and `PolicyAssignment`.

#### IAM nouns

Policy `resources` (in manifests and through the API) use the new nouns. The server rewrote its stored policies; update the ones in your repository. Only a resource's first `/`-segment is a noun, and it is matched exactly: `agent_assignment/*` becomes `assignment/*`, not `agent…`.

| 2.x noun | 3.0 noun | Scope |
| --- | --- | --- |
| `operator` | `task` | project |
| `workflow` | `agent` | project |
| `job` | `run` | project |
| `documentgroup` | `documentfolder` | project |
| `agent_assignment` | `assignment` | project |
| `agent_control` | `pause_control` | account |
| `email_sinks` | `email_outputs` | account |

`*`, `project/…`, `resource_folder`, `tool`, and the other nouns are unchanged.

### Python: classes and resources

Top-level exports from `ragnerock`, and their modules:

| 2.x | 3.0 |
| --- | --- |
| `Workflow`, `WorkflowNode`, `WorkflowSchedule` (`ragnerock.resources.workflow`) | `Agent`, `AgentNode`, `AgentSchedule` (`ragnerock.resources.agent`) |
| `Operator`, `OperatorKind` (`ragnerock.resources.operator`) | `Task`, `TaskKind` (`ragnerock.resources.task`) |
| `Job`, `JobStatus`, `JobType` (`ragnerock.resources.job`) | `Run`, `RunStatus`, `RunKind` (`ragnerock.resources.run`); `RunKind` keeps the values `AUTOMATIC=1`, `MANUAL=2` |
| `DocumentGroup` | `DocumentFolder` |

Resource fields and methods:

| Resource | 2.x | 3.0 |
| --- | --- | --- |
| `Task` | `operator_kind` | `task_kind` |
| `Task` | `notification_template`, `change_request_prompt`, `change_request_signal` | removed |
| `Agent` | `resources`, `sinks` | `inputs`, `outputs` |
| `Agent` | `add_node(operator=...)` | `add_node(task=...)` |
| `AgentNode` | `workflow_id`, `operator_id`, `operator_name` | `agent_id`, `task_id`, `task_name` |
| `AgentNode` | `target_resource_id`, `context_resource_ids` | `target_input_id`, `context_input_ids` |
| `AgentNode` | `on_error="FAIL_JOB"` | `on_error="FAIL_RUN"` |
| `Run` | `job_type` (`JobType`) | `kind` (`RunKind`) |
| `Run` | `workflow_ids` | `agent_ids` |
| `Document` | `group_id` | `document_folder_id` |
| `Document` | `job()` | `latest_run()` |
| `Annotation` | `operator_id`, `operator_name`, `.operator` | `task_id`, `task_name`, `.task` |

Session calls:

| 2.x | 3.0 |
| --- | --- |
| `session.run(workflow, documents=[...])` returns a `Job` | `session.run(agent, documents=[...])` returns a `Run` |
| `session.get(WorkflowNode, ..., workflow_id=..., workflow_name=...)` | `session.get(AgentNode, ..., agent_id=..., agent_name=...)` |
| `session.list(Annotation, operator_id=..., operator_name=...)` | `session.list(Annotation, task_id=..., task_name=...)` |
| `doc.list(Annotation, operator=...)` | `doc.list(Annotation, task=...)` |
| `operator.list(Annotation, ...)` | `task.list(Annotation, ...)` |

### Low-level client

Sections, their modules, and their (private) section classes:

| 2.x | 3.0 |
| --- | --- |
| `client.workflows` (`ragnerock.client.workflows`, `_WorkflowsSection`) | `client.agents` (`ragnerock.client.agents`, `_AgentsSection`) |
| `client.workflows.change_requests` (`_WorkflowChangeRequestsSection`) | `client.agents.change_requests` (`_AgentChangeRequestsSection`) |
| `client.operators` (`ragnerock.client.operators`, `_OperatorsSection`) | `client.tasks` (`ragnerock.client.tasks`, `_TasksSection`) |
| `client.jobs` (`ragnerock.client.jobs`, `_JobsSection`) | `client.runs` (`ragnerock.client.runs`, `_RunsSection`) |
| `client.groups` (`ragnerock.client.groups`, `_GroupsSection`) | `client.document_folders` (`ragnerock.client.document_folders`, `_DocumentFoldersSection`) |
| `client.workflow_artifacts` (`ragnerock.client.workflow_artifacts`, `_WorkflowArtifactsSection`) | `client.output_artifacts` (`ragnerock.client.output_artifacts`, `_OutputArtifactsSection`) |

`client.tools`, `client.assignments`, and `client.notebooks` keep their names. Across every section, a `workflow_id` parameter is now `agent_id`, `operator_id` is `task_id`, `job_id` is `run_id`, and `group_id` (a document group) is `document_folder_id`. Other method and parameter changes:

| Section | 2.x | 3.0 |
| --- | --- | --- |
| `agents` | `create(resources=...)` | `create(inputs=...)` |
| `agents` | `set_resources(id, resources=...)`, `set_sinks(id, sinks=...)` | `set_inputs(id, inputs=...)`, `set_outputs(id, outputs=...)` |
| `agents` | `update_node(target_resource_id=, clear_target_resource=, context_resource_ids=)` | `update_node(target_input_id=, clear_target_input=, context_input_ids=)` |
| `ragnerock.client.agents` | `tool_call_resource()`, `web_fetch_resource()` | `tool_call_input()`, `web_fetch_input()` |
| `runs` | `create_manual(workflow_ids=, workflow_id=, ...)` | `create(agent_ids=, agent_id=, ...)`; `group_id=` is unchanged (a batch key, not a folder) |
| `runs` | `create_runs_from_manifest(workflow_id, ...)` | `create_from_manifest(agent_id, ...)` |
| `runs` | `run_all_ingest(workflow_id, resource_id)` | `run_all_ingest(agent_id, input_id)` |
| `runs` | `sink_deliveries(id)`, `retry_sink_deliveries(id, sink_id)` | `output_deliveries(id)`, `retry_output_deliveries(id, output_id)` |
| `output_artifacts` | `list(workflow_id=, sink_id=, run_id=)` | `list(agent_id=, output_id=, provenance_id=)` |
| `annotations` | `list_by_operator`, `list_hydrated_by_operator` | `list_by_task`, `list_hydrated_by_task` |
| `annotations` | `list_by_document_and_operator_id`, `list_by_document_and_operator_name` | `list_by_document_and_task_id`, `list_by_document_and_task_name` |
| `annotations` | `operator_name=` filters | `task_name=` |
| `assignments` | `create(agent_id=, task=)`, `dispatch(agent_id=, task=)` | `create(task_id=, instructions=)`, `dispatch(task_id=, instructions=)` |
| `assignments` | `list_for_agent(...)`, `threads(agent_id=)` | `list_for_task(...)`, `threads(task_id=)` |
| `documents` | `list_by_group`, `get_job` | `list_by_document_folder`, `get_run` |
| `documents` | `list(group_id=, ungrouped=)` | `list(document_folder_id=, unfiled=)` |
| `ingest_sources` | `list_config_workflows`, `list_workflow_link_notices`, `link_workflow_notice`, `dismiss_workflow_notice` | `list_config_agents`, `list_agent_link_notices`, `link_agent_notice`, `dismiss_agent_notice` |
| `notebooks` | `create`, `open_conversation`, `list` take `agent_id=` | take `task_id=` |
| `endpoints` | `create(workflow_id=, endpoint_type=EndpointType.WORKFLOW, auto_archive_jobs=)` | `create(agent_id=, endpoint_type=EndpointType.AGENT, auto_archive_runs=)` |
| `endpoints` | `update(auto_archive_jobs=)` | `update(auto_archive_runs=)` |
| `ai_configs` | `create`/`update(agent_turn_token_budget=)` | `loop_turn_token_budget=` |

Response models follow the same words. The main renames:

| Module | 2.x | 3.0 |
| --- | --- | --- |
| `agents` | `WorkflowResponse`, `WorkflowListResponse.workflows`, `WorkflowNodeInfo`, `WorkflowNodeResponse` | `AgentResponse`, `AgentListResponse.agents`, `AgentNodeInfo`, `AgentNodeResponse` |
| `agents` | `WorkflowResourceInfo`, `WorkflowSinkInfo`, `ResourceTestFetchResponse` | `AgentInputInfo`, `AgentOutputInfo`, `InputTestFetchResponse` |
| `agents` | `ApproveChangeRequestResponse.operators_created`, `operators_updated`, `orphaned_operators`, `operator_version_ids` | `tasks_created`, `tasks_updated`, `orphaned_tasks`, `task_version_ids` |
| `agents` | `ChangeRequestResponse.trigger_operator_id`, `trigger_operator_name` | `trigger_task_id`, `trigger_task_name` |
| `tasks` | `OperatorResponse`, `OperatorListResponse.operators` | `TaskResponse`, `TaskListResponse.tasks` |
| `runs` | `JobResponse`, `JobListResponse.jobs`, `JobActionResponse.job_id` | `RunResponse`, `RunListResponse.runs`, `RunActionResponse.run_id` |
| `runs` | `JobResponse.job_type`, `workflow_ids`, `run` | `RunResponse.kind`, `agent_ids`, `provenance` |
| `runs` | `SinkDeliveryInfo`, `SinkDeliveryGroup`, `JobSinkDeliveriesResponse`, `SinkDeliveryRetryResponse` (`sink_*` fields) | `OutputDeliveryInfo`, `OutputDeliveryGroup`, `RunOutputDeliveriesResponse`, `OutputDeliveryRetryResponse` (`output_*` fields) |
| `document_folders` | `DocumentGroupResponse`, `DocumentGroupListResponse.groups` | `DocumentFolderResponse`, `DocumentFolderListResponse.document_folders` |
| `output_artifacts` | `WorkflowArtifactInfo`, `WorkflowArtifactList` | `OutputArtifactInfo`, `OutputArtifactList` |
| `tools` | `AgentToolKind`, `AgentToolFunction`, `AgentToolResponse`, `AgentToolList`, `AgentToolDeleteResponse` | `ToolKind`, `ToolFunction`, `ToolResponse`, `ToolList`, `ToolDeleteResponse` |
| `tools` | `operator_count`, `AgentToolList.agent_tools_enabled` | `task_count`, `ToolList.tools_enabled` |
| `assignments` | `AgentAssignmentListResponse`, `AgentThread`, `AgentThreadListResponse` | `TaskAssignmentListResponse`, `TaskThread`, `TaskThreadListResponse` |
| `assignments` | `AgentQuestionStatus`, `AgentQuestionResponse`, `AgentQuestionListResponse` | `AssignmentQuestionStatus`, `AssignmentQuestionResponse`, `AssignmentQuestionListResponse` |
| `ingest` | `IngestConfigWorkflowRef`, `IngestWorkflowLinkNoticeResponse` | `IngestConfigAgentRef`, `IngestAgentLinkNoticeResponse` |
| `endpoints` | `EndpointResponse.workflow_id`, `source_workflow_id`, `resources`, `auto_archive_jobs` | `agent_id`, `source_agent_id`, `inputs`, `auto_archive_runs` |
| `skills` | `operator_count` | `task_count` |
| `projects` | `auto_archive_succeeded_jobs_after_days` | `auto_archive_succeeded_runs_after_days` |
| `ai_configs` | `operators_referencing`; `jobs_total`, `jobs_completed`, `jobs_failed` | `tasks_referencing`; `runs_total`, `runs_completed`, `runs_failed` |

Fields named `agent_id` / `agent_name` that meant a task (on notebooks, assignments, and assignment questions) are now `task_id` / `task_name`, and annotations' `operator_id` / `operator_name` are `task_id` / `task_name`. Fields named `group_id` that meant a document group (`DocumentResponse`, and `document_group_id` on ingest configs) are now `document_folder_id`.

#### Fields that changed meaning

In 2.x, `run_id` meant a *workflow run*, and `job_id` meant the run itself. In 3.0 the workflow run is the **run provenance** (`provenance_id`), which frees `run_id` for the run. Where a model carried both, rename `run_id` to `provenance_id` first, then `job_id` to `run_id`:

| Model | 2.x | 3.0 |
| --- | --- | --- |
| `CreateManualJobsResponse` → `CreateManualRunsResponse` (`runs.create`, `agents.run_now`, `runs.rerun`) | `job_ids`, `run_ids` | `run_ids`, `provenance_ids` |
| `ChangeRequestDocumentResponse` | `job_id`, `run_id`, `backfill_job_id`, `backfill_run_id` | `run_id`, `provenance_id`, `backfill_run_id`, `backfill_provenance_id` |
| `BackfillChangeRequestResponse` | `job_ids`, `run_ids` | `run_ids`, `provenance_ids` |
| `WorkflowArtifactInfo` → `OutputArtifactInfo` | `job_id`, `run_id` | `run_id`, `provenance_id` |
| `workflow_artifacts.list` → `output_artifacts.list` | `run_id=` | `provenance_id=` |
| `JobResponse` → `RunResponse` | `run` | `provenance` |

So `response.run_ids[0]` is now a run you can `session.get(Run, id=...)`, where in 2.x it was a workflow run.

#### Enum and wire values

| Where | 2.x | 3.0 |
| --- | --- | --- |
| Node and output `on_error` | `"FAIL_JOB"` | `"FAIL_RUN"` |
| `EndpointType` | `WORKFLOW = "WORKFLOW"` | `AGENT = "AGENT"` |
| `AssignmentStatus` | `HALTED = "halted"` | `PAUSED = "paused"` |
| `ArtifactType` | `OPERATORS = "operators"`, `WORKFLOW_PROPOSAL = "workflow_proposal"`, `WORKFLOW = "workflow"` | `TASKS = "tasks"`, `AGENT_PROPOSAL = "agent_proposal"`, `AGENT = "agent"` |
| `ToolFunction.surfaces` | `"workflow"` | `"task"` |
| `NotebookResponse.visibility` | `"agent_transcript"` | `"task_transcript"` |
| `NotebookResponse.model_source` | `"agent"` | `"task"` |
| `AnnotationRevisionResponse.source` | `"operator"` | `"task"` |

### SQL names

Table names are unchanged (a task's table is still named after the task). Some columns were renamed:

| Table | 2.x | 3.0 |
| --- | --- | --- |
| `_reviews` | `operator_id` | `task_id` |
| every task table, memory table (`mem_*`), and `_reviews` | hidden `run_id` | hidden `provenance_id` |
| `documents` | `group_id` | `document_folder_id` |
| `harness_sessions` | `agent_id`, `workflow_run_id` | `task_id`, `provenance_id` |
| tool logs (`tool_<slug>`) | `agent_id`, `agent_name`; `source = 'workflow'` | `task_id`, `task_name`; `source = 'run'` |

Saved queries stored in Ragnerock were rewritten on the server. SQL in your own code, passed to `session.query(...)` or `ragnerock query`, needs the same changes. Comparison operators and `GROUP BY` are, of course, unaffected.

### CLI

| 2.x kind and aliases | 3.0 kind and aliases |
| --- | --- |
| `Workflow`: `workflow`, `workflows`, `wf`, `wfs` | `Agent`: `agent`, `agents` |
| `Operator`: `operator`, `operators`, `op`, `ops` | `Task`: `task`, `tasks` |
| `Job`: `job`, `jobs` | `Run`: `run`, `runs` |
| `DocumentGroup`: `documentgroup(s)`, `group(s)`, `grp` | `DocumentFolder`: `documentfolder(s)`, `document-folder(s)`, `folder(s)` |
| `WorkflowArtifact`: `workflowartifact(s)`, `workflow-artifact(s)`, `artifact(s)` | `OutputArtifact`: `outputartifact(s)`, `output-artifact(s)`, `artifact(s)` |
| `Tool`: `tool(s)`, `agenttool(s)`, `agent-tool(s)` | `Tool`: `tool`, `tools` |

The old kinds and aliases are gone; `ragnerock get wf` is now an unknown kind. Also:

- `ragnerock run <agent>` runs an agent and prints `run/<id>`; `--wait` exits `2` when the run fails.
- `ragnerock get annotation --filter operator=<id>` is `--filter task=<id>`, and `operator-name=` is `task-name=`.
- `ragnerock delete` accepts `Document`, `DocumentFolder`, `Task`, and `Agent`.
- Column headers follow: `FOLDER` (was `GROUP`), `TASK` (was `OPERATOR`), the skill column `TASKS` (was `AGENTS`), and artifacts' `AGENT` and `OUTPUT` (was `WORKFLOW`).

### Removed

The server dropped these, so the SDK did too:

- `TaskKind.MESSAGE` and `TaskKind.CHANGE_REQUEST` (were `OperatorKind`). `TaskKind` is `LLM`, `CODE`, `MANUAL`, or `OUTPUT`. Change requests now come from an agent's change-request outputs.
- `notification_template`, `change_request_prompt`, and `change_request_signal`, on `Task`, `tasks.create` / `tasks.update`, and `TaskResponse`.
- `EndpointExecutionResponse.task_id`, which duplicated `id`.
- `AIConfigDetail.referencing_operator_count`.

### What did not change

- **The public endpoint REST contract is frozen**, because your callers depend on it: `POST /api/endpoints/{id}` and `GET /api/endpoints/{id}/{task_id}`, so `client.endpoints.submit(...)`, `poll(endpoint_id, task_id)`, `EndpointSubmitResponse.task_id`, the `EndpointTask*` models, `ragnerock_metadata.workflow_id` (the id of the agent that ran), and error codes such as `workflow_execution_failed` and `agents_halted`. There, "task" means one execution.
- `runs.create(group_id=...)` is a batch key, not a document folder.
- Ingest runs: `IngestRun*` models and their `run_id`s.
- Condition comparators (`ComparisonOp`, the `"operator"` key in a condition) and document filters (`FilterOperator`).
- `DocumentFolder.folder_id` and `DocumentFolderResponse.folder_id`: the folder the document folder is filed under in the app's folder tree.
- The `ragnerock.resources` package name, and `tools`, `skills`, `assignments`, and `notebooks`.

### New in 3.0

- `client.runs.rerun(run_id)` runs a succeeded run again as a new run.
- `client.agents.draft_changes`, `keep_draft_changes`, and `refresh_draft_changes` inspect a draft of an agent and keep or refresh its changes to shared tasks.
- `task_enabled=` on `client.tools.create_mcp`, `create_connector`, `create_rest`, and `update`.
- {data}`ragnerock.gitops.discovery.API_VERSION` and {data}`ragnerock.gitops.discovery.RETIRED_API_VERSIONS`, exported from `ragnerock.gitops`, and the client-side `v1alpha1` refusal.
- GitOps examples for `Project`, `Role`, `RoleAssignment`, `Policy`, and `PolicyAssignment`.

## Migrating to 2.0

Version 2.0 brings the SDK in line with the current Ragnerock API, replaces the CLI's manifest format with [GitOps manifests](gitops.md), and adds client support for most of the platform (see [Platform APIs](platform.md)). This page lists what changed and what to do about it.

### CLI: `apply` now uses GitOps manifests

`ragnerock apply -f` uploads GitOps manifests (`apiVersion: ragnerock.com/v1alpha1`) for server-side apply. The 1.x client-side format (`apiVersion: v1`, snake_case `spec`) is no longer accepted — documents in that format are now skipped as non-Ragnerock YAML.

| 1.x manifest kind | 2.0 equivalent |
| --- | --- |
| `Operator` | A `Schema` (the `jsonSchema`) plus an `Agent` that references it (`generationPrompt`, `chunkType`, ...). |
| `Workflow` | `Workflow`, with nodes naming their `agent` and wiring upstream nodes with `dependsOn`. |
| `Document`, `DocumentGroup`, `Annotation` | Not configuration — create them with the [Session API](sessions.md), or ingest documents with an `IngestConfig`. |

See [`examples/gitops/`](https://github.com/ragnerock/ragnerock-sdk/tree/main/examples/gitops) for working manifests of every kind.

Also in the CLI:

- **`ragnerock delete -f` is removed.** GitOps apply never deletes; use `ragnerock delete <kind> <name>`.
- **`ragnerock get -o yaml` prints a plain field dump** rather than a manifest, since it no longer round-trips into `apply`.
- **`apply` doesn't need a project.** `RAGNEROCK_PROJECT` (or a `/project` path in the connection string) is optional for it; project-scoped manifests name their project with the `ragnerock.com/project` annotation.

### Chunks

The chunk shape now matches the API:

- **`ChunkType` values are renumbered** to match the server: `DOCUMENT=0`, `PAGE=1`, `PARAGRAPH=2`, `SENTENCE=3`, plus the tabular scopes `ROW=4`, `ROW_WINDOW=5`, `SHEET=6`. `SECTION` is gone. Code that uses the names (`ChunkType.PARAGRAPH`) needs no change; code that stored or sent raw integers does. In 1.x, an operator created with `ChunkType.PARAGRAPH` was actually sent as `ROW` — check the scope of operators created with 1.x.
- **`Chunk` fields:** `start_index` / `end_index` are now `start_char_idx` / `end_char_idx`; new fields `document_offset` and `page_id`; `metadata` and `created_at` are removed (the API never returned them).
- **Creating a chunk** requires `content`, `document_offset`, and `chunk_type`; `client.chunks.create(...)` takes the same fields.

### Operators

- Operators carry an explicit **`operator_kind`** (`OperatorKind.LLM` by default), which the API now requires. `CODE` operators supply `code_source` instead of `generation_prompt`.
- `client.operators.create(...)` takes `chunk_type` and `operator_kind`; `jsonschema` and `generation_prompt` are optional (a schema can be linked with `output_schema_id`).
- `client.operators.update(...)`: for `batch_size`, `input_columns`, `code_timeout_seconds`, `ai_config_id`, `model_name`, and `change_request_signal`, omitting the argument leaves the field unchanged and passing `None` clears it.

### Workflows

- **Defaults match the server:** `Workflow.auto_run_on_upload` defaults to `False` (was `True`), and `WorkflowNode.on_error` / `add_node(on_error=...)` default to `"SKIP_NODE"` (was `"FAIL_JOB"`). Pass the old values explicitly to keep the 1.x behavior for new workflows.
- `Workflow.execution_order` is a list of node-id strings.
- Nodes loaded with a workflow now carry `workflow_id` and are bound to the session, so they can be wired with `>>` and committed (in 1.x this raised).

### Other changes

- **Timestamps** on resources are timezone-aware UTC `datetime`s. Comparisons against naive datetimes need `tzinfo=UTC`.
- **`Job.cancel()` / `Job.retry()`** re-fetch the job afterwards, so `status` reflects the server's state.
- **`Page.metadata`** is removed (the API never returned it); `Page.created_at` is added.
- **Document metadata** updates are sent in the encoding the API expects; no code change needed.
- **`ragnerock.client` is now a package.** `from ragnerock.client import RagnerockClient` and the response models import as before; internal helpers moved to `ragnerock.client._base`.
- **Dependencies:** `cryptography` is now required (for sealing GitOps secrets). Cloud secret-manager support is in the optional extras `gcp`, `aws`, and `azure`.

### What's new

- [GitOps apply](gitops.md) from the CLI and from Python (`ragnerock.gitops`), with client-side secret resolution and sealing.
- {func}`~ragnerock.create_client` for account-level calls that need no project.
- [Platform APIs](platform.md) on the low-level client: skills, agent tools, notebooks, assignments, search, endpoints, workflow schedules / sinks / change requests / artifacts, ingest sources, saved queries, AI / embedding / image-summary / database / blob provider configs, and web access.
- `OperatorKind`, `DocumentStatus`, `WorkflowSchedule`; `Document.status` and `Document.job()`; lazy `Annotation.document` / `.chunk` / `.page` / `.operator`; `doc.list(Annotation, operator=...)`.
- `QueryResult.truncated` and `session.query(..., include_provenance=True)`.
- New read-only CLI kinds for `ragnerock get` / `describe` (see [CLI](cli.md#resource-kinds)).
