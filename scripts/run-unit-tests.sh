#! /usr/bin/env bash

# Usage: ./scripts/ci/run-unit-tests.sh

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $HERE/helpers/logger.sh

set -eo pipefail

_log "INFO" "Running unit tests"

uv run pytest -v .
