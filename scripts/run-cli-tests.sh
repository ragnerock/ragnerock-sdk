#! /usr/bin/env bash

# Usage: ./scripts/run-cli-tests.sh
#
# Matrix smoke tests for the `ragnerock` CLI. Exercises every top-level
# command (version, get, describe, apply, delete, run, query) against every
# resource kind registered in ragnerock.cli.resources (Document,
# DocumentGroup, Operator, Workflow, Annotation, Chunk, Page, Job) in every
# supported output format. Assumes credentials are already exported in the
# environment (RAGNEROCK_CONNECTION_STRING, or the split RAGNEROCK_HOST /
# _EMAIL / _PASSWORD / _PROJECT quartet). Creates throwaway resources named
# with a timestamped prefix and cleans up at the end so repeated runs don't
# collide.

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $HERE/helpers/logger.sh

set -eo pipefail

if [[ -z "${RAGNEROCK_CONNECTION_STRING}" ]] && [[ -z "${RAGNEROCK_HOST}" ]]; then
  _log "FATAL" "CLI smoke tests require RAGNEROCK_CONNECTION_STRING or the split RAGNEROCK_{HOST,EMAIL,PASSWORD,PROJECT} vars to be exported"
fi

PREFIX="cli-smoke-$$-$(date +%s)"
GRP_NAME="${PREFIX}-grp"
OP1_NAME="${PREFIX}-op1"
OP2_NAME="${PREFIX}-op2"
WF_NAME="${PREFIX}-wf"
DOC_NAME="${PREFIX}-doc-stdin"
DOC_DIR_NAME="${PREFIX}-doc-dir"

TMP_DIR="$(mktemp -d)"
MANIFEST_DIR="${TMP_DIR}/manifests"
mkdir -p "${MANIFEST_DIR}"
TXT_FILE="${TMP_DIR}/sample.txt"
printf 'Ragnerock CLI matrix smoke test.\nParagraph two lives here.\n' > "${TXT_FILE}"

# Output formats shared by `get` and `describe`.
OUTPUT_FORMATS=(table yaml json name)

# Every kind registered in ragnerock.cli.resources. Uses a mix of canonical
# names and aliases so both resolution paths are exercised.
READABLE_KINDS=(doc documentgroup op workflow annotation chunk page job)

cleanup() {
  _log "INFO" "Cleaning up smoke-test resources (best effort)"
  uv run ragnerock delete workflow "${WF_NAME}" 2>/dev/null || true
  uv run ragnerock delete doc "${DOC_NAME}" 2>/dev/null || true
  uv run ragnerock delete doc "${DOC_DIR_NAME}" 2>/dev/null || true
  uv run ragnerock delete op "${OP1_NAME}" 2>/dev/null || true
  uv run ragnerock delete op "${OP2_NAME}" 2>/dev/null || true
  uv run ragnerock delete grp "${GRP_NAME}" 2>/dev/null || true
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------
_log "INFO" "ragnerock version"
uv run ragnerock version
_log "SUCCESS" "version resolved"

# ---------------------------------------------------------------------------
# get <kind> (list form) × every output format, for kinds that don't need a
# parent filter. chunk/page/annotation require filters and are covered after
# the apply phase creates something to scope them to.
# ---------------------------------------------------------------------------
for kind in doc documentgroup op workflow job; do
  for fmt in "${OUTPUT_FORMATS[@]}"; do
    _log "INFO" "get ${kind} -o ${fmt}"
    uv run ragnerock get "${kind}" -o "${fmt}" >/dev/null
    _log "SUCCESS" "get ${kind} -o ${fmt}"
  done
done

# ---------------------------------------------------------------------------
# apply via STDIN heredoc — provisions the full resource graph we'll
# exercise below (group, two operators, a document, and a workflow wiring
# the operators together).
# ---------------------------------------------------------------------------
_log "INFO" "apply pipeline manifest via STDIN heredoc"
uv run ragnerock apply -f - <<EOF
apiVersion: v1
kind: DocumentGroup
metadata:
  name: ${GRP_NAME}
spec: {}
---
apiVersion: v1
kind: Operator
metadata:
  name: ${OP1_NAME}
spec:
  description: "CLI matrix smoke op #1"
  jsonschema:
    type: object
    properties:
      label: { type: string }
    required: [label]
  generation_prompt: "Return a label."
  chunk_type: PARAGRAPH
  batch_size: 8
---
apiVersion: v1
kind: Operator
metadata:
  name: ${OP2_NAME}
spec:
  description: "CLI matrix smoke op #2"
  jsonschema:
    type: object
    properties:
      sentiment: { type: string }
    required: [sentiment]
  generation_prompt: "Return a sentiment."
  chunk_type: PARAGRAPH
---
apiVersion: v1
kind: Document
metadata:
  name: ${DOC_NAME}
spec:
  file_path: ${TXT_FILE}
  group: ${GRP_NAME}
  file_type: PLAINTEXT
  metadata:
    source: smoke-test-stdin
---
apiVersion: v1
kind: Workflow
metadata:
  name: ${WF_NAME}
spec:
  description: "CLI matrix smoke workflow"
  is_active: true
  auto_run_on_upload: false
  nodes:
    - operator: ${OP1_NAME}
      on_error: FAIL_JOB
      max_retries: 1
    - operator: ${OP2_NAME}
      persist: true
  edges:
    - [${OP1_NAME}, ${OP2_NAME}]
EOF
_log "SUCCESS" "apply via STDIN succeeded"

# ---------------------------------------------------------------------------
# apply via directory — drops an additional manifest into a temp directory
# and applies the directory as a whole.
# ---------------------------------------------------------------------------
cat > "${MANIFEST_DIR}/doc.yaml" <<EOF
apiVersion: v1
kind: Document
metadata:
  name: ${DOC_DIR_NAME}
spec:
  file_path: ${TXT_FILE}
  group: ${GRP_NAME}
  file_type: PLAINTEXT
  metadata:
    source: smoke-test-dir
EOF
_log "INFO" "apply -f <directory>"
uv run ragnerock apply -f "${MANIFEST_DIR}"
_log "SUCCESS" "apply via directory succeeded"

# ---------------------------------------------------------------------------
# get <kind> <name> + describe <kind> <name> × every output format, for the
# four name-addressable writable kinds. Also round-trip the YAML output
# through `apply -f -` to prove `get -o yaml | apply` is stable.
# ---------------------------------------------------------------------------
WRITABLE_KINDS=(grp op workflow doc)
WRITABLE_NAMES=("${GRP_NAME}" "${OP1_NAME}" "${WF_NAME}" "${DOC_NAME}")

for idx in "${!WRITABLE_KINDS[@]}"; do
  kind="${WRITABLE_KINDS[$idx]}"
  name="${WRITABLE_NAMES[$idx]}"
  for fmt in "${OUTPUT_FORMATS[@]}"; do
    _log "INFO" "get ${kind} ${name} -o ${fmt}"
    uv run ragnerock get "${kind}" "${name}" -o "${fmt}" >/dev/null
    _log "SUCCESS" "get ${kind} ${name} -o ${fmt}"

    _log "INFO" "describe ${kind} ${name} -o ${fmt}"
    uv run ragnerock describe "${kind}" "${name}" -o "${fmt}" >/dev/null
    _log "SUCCESS" "describe ${kind} ${name} -o ${fmt}"
  done
  _log "INFO" "round-trip: get ${kind} ${name} -o yaml | apply -f -"
  uv run ragnerock get "${kind}" "${name}" -o yaml | uv run ragnerock apply -f -
  _log "SUCCESS" "round-trip ${kind}/${name}"
done

# ---------------------------------------------------------------------------
# Resolve the stdin-applied document's UUID so we can scope chunk/page/
# annotation listings to it. `describe -o json` emits a single object with
# an `id` field, which we extract via python.
# ---------------------------------------------------------------------------
DOC_ID="$(uv run ragnerock describe doc "${DOC_NAME}" -o json \
  | python -c 'import sys, json; print(json.load(sys.stdin)[0]["id"])')"
OP1_ID="$(uv run ragnerock describe op "${OP1_NAME}" -o json \
  | python -c 'import sys, json; print(json.load(sys.stdin)[0]["id"])')"
_log "INFO" "resolved document id ${DOC_ID} and operator id ${OP1_ID}"

# ---------------------------------------------------------------------------
# get chunk / get page — both require --filter document=<id>. Exercise all
# output formats; empty result sets are valid here since ingestion may not
# have produced chunks/pages yet.
# ---------------------------------------------------------------------------
for kind in chunk page; do
  for fmt in "${OUTPUT_FORMATS[@]}"; do
    _log "INFO" "get ${kind} -o ${fmt} --filter document=${DOC_ID}"
    uv run ragnerock get "${kind}" -o "${fmt}" --filter "document=${DOC_ID}" >/dev/null
    _log "SUCCESS" "get ${kind} -o ${fmt} --filter document=…"
  done
done

# ---------------------------------------------------------------------------
# get annotation — requires one of document=, chunk=, or operator= as a
# filter. Exercise both the document-scoped and operator-scoped paths.
# ---------------------------------------------------------------------------
for fmt in "${OUTPUT_FORMATS[@]}"; do
  _log "INFO" "get annotation -o ${fmt} --filter document=${DOC_ID}"
  uv run ragnerock get annotation -o "${fmt}" --filter "document=${DOC_ID}" >/dev/null
  _log "SUCCESS" "get annotation -o ${fmt} --filter document=…"

  _log "INFO" "get annotation -o ${fmt} --filter operator=${OP1_ID}"
  uv run ragnerock get annotation -o "${fmt}" --filter "operator=${OP1_ID}" >/dev/null
  _log "SUCCESS" "get annotation -o ${fmt} --filter operator=…"
done

# ---------------------------------------------------------------------------
# query × every output format × --limit
# ---------------------------------------------------------------------------
for fmt in table json; do
  _log "INFO" "query -o ${fmt} --limit 5"
  uv run ragnerock query "SELECT 1 AS one" -o "${fmt}" --limit 5 >/dev/null
  _log "SUCCESS" "query -o ${fmt}"
done

# ---------------------------------------------------------------------------
# run — kicks off the smoke workflow against the stdin-applied document.
# Uses --no-wait to avoid hanging on backend execution; the command itself
# succeeding is what we're exercising here.
# ---------------------------------------------------------------------------
_log "INFO" "run ${WF_NAME} --documents ${DOC_NAME} --no-wait"
uv run ragnerock run "${WF_NAME}" --documents "${DOC_NAME}" --no-wait
_log "SUCCESS" "run (no-wait) started a job"

# ---------------------------------------------------------------------------
# delete -f <file> — uses a minimal manifest that just names the directory-
# applied document so the file-driven delete path is exercised.
# ---------------------------------------------------------------------------
cat > "${MANIFEST_DIR}/delete-doc.yaml" <<EOF
apiVersion: v1
kind: Document
metadata:
  name: ${DOC_DIR_NAME}
spec:
  file_type: PLAINTEXT
EOF
_log "INFO" "delete -f ${MANIFEST_DIR}/delete-doc.yaml"
uv run ragnerock delete -f "${MANIFEST_DIR}/delete-doc.yaml"
_log "SUCCESS" "delete -f (single file) succeeded"

# ---------------------------------------------------------------------------
# delete -f -  (STDIN heredoc variant of delete-from-manifest).
# ---------------------------------------------------------------------------
_log "INFO" "delete -f - (STDIN) for workflow"
uv run ragnerock delete -f - <<EOF
apiVersion: v1
kind: Workflow
metadata:
  name: ${WF_NAME}
spec: {}
EOF
_log "SUCCESS" "delete -f - (STDIN) succeeded"

# ---------------------------------------------------------------------------
# delete <kind> <name> — the positional form, one call per remaining
# writable kind, in dependency order (doc → ops → group).
# ---------------------------------------------------------------------------
_log "INFO" "delete doc ${DOC_NAME}"
uv run ragnerock delete doc "${DOC_NAME}"
_log "SUCCESS" "delete doc"

_log "INFO" "delete op ${OP1_NAME}"
uv run ragnerock delete op "${OP1_NAME}"
_log "SUCCESS" "delete op #1"

_log "INFO" "delete operator ${OP2_NAME}"
uv run ragnerock delete operator "${OP2_NAME}"
_log "SUCCESS" "delete op #2"

_log "INFO" "delete grp ${GRP_NAME}"
uv run ragnerock delete grp "${GRP_NAME}"
_log "SUCCESS" "delete group"

trap - EXIT  # cleanup already ran successfully
rm -rf "${TMP_DIR}"
_log "SUCCESS" "CLI matrix smoke tests passed"
