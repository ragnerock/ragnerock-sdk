#! /usr/bin/env bash

# Usage: ./scripts/run-cli-tests.sh
#
# Smoke tests for the `ragnerock` CLI. Assumes credentials are already
# exported in the environment (RAGNEROCK_CONNECTION_STRING, or the split
# RAGNEROCK_HOST / _EMAIL / _PASSWORD / _PROJECT quartet). Creates a
# throwaway operator named with a timestamped prefix and cleans up at the
# end so repeated runs don't collide.

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $HERE/helpers/logger.sh

set -eo pipefail

if [[ -z "${RAGNEROCK_CONNECTION_STRING}" ]] && [[ -z "${RAGNEROCK_HOST}" ]]; then
  _log "FATAL" "CLI smoke tests require RAGNEROCK_CONNECTION_STRING or the split RAGNEROCK_{HOST,EMAIL,PASSWORD,PROJECT} vars to be exported"
fi

PREFIX="cli-smoke-$$-$(date +%s)"
OP_NAME="${PREFIX}-op"

cleanup() {
  _log "INFO" "Cleaning up ${OP_NAME}"
  uv run ragnerock delete op "${OP_NAME}" 2>/dev/null || true
}
trap cleanup EXIT

_log "INFO" "ragnerock version"
uv run ragnerock version
_log "SUCCESS" "version resolved"

_log "INFO" "ragnerock get doc -o name (listing sanity)"
uv run ragnerock get doc -o name >/dev/null
_log "SUCCESS" "get doc -o name returned"

_log "INFO" "ragnerock apply via STDIN heredoc"
uv run ragnerock apply -f - <<EOF
kind: Operator
metadata:
  name: ${OP_NAME}
spec:
  description: "CLI smoke test operator"
  jsonschema:
    type: object
    properties:
      label: { type: string }
  generation_prompt: "Return a label"
  chunk_type: PARAGRAPH
EOF
_log "SUCCESS" "apply via STDIN succeeded"

_log "INFO" "ragnerock get op -o yaml | ragnerock apply -f -  (round-trip)"
uv run ragnerock get op "${OP_NAME}" -o yaml | uv run ragnerock apply -f -
_log "SUCCESS" "round-trip succeeded"

_log "INFO" "ragnerock describe op -o json"
uv run ragnerock describe op "${OP_NAME}" -o json | head -5 >/dev/null
_log "SUCCESS" "describe -o json succeeded"

_log "INFO" "ragnerock delete op"
uv run ragnerock delete op "${OP_NAME}"
trap - EXIT  # cleanup already ran successfully
_log "SUCCESS" "CLI smoke tests passed"
