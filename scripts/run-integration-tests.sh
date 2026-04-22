#! /usr/bin/env bash

# Usage: ENVIRONMENT=<your environment> PROJECT_ID=<your GCP project> ./scripts/ci/run-integration-tests.sh
# If not set, the following defaults will be set:
# ENVIRONMENT=dev
# PROJECT_ID=ragnerock-testing

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $HERE/helpers/logger.sh

set -eo pipefail
if [[ -z "${RAGNEROCK_CONNECTION_STRING}" ]]; then
  _log "FATAL" "Integration tests require a Ragnerock connection string of format 'ragnerock://<username>:<password>@<host>/<project>'"
fi

_log "INFO" "Running integration tests"

uv run pytest tests/integration -v -rs
