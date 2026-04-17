#! /usr/bin/env bash

# Usage: ./scripts/ci/check.sh

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $HERE//helpers/logger.sh

set -eo pipefail

_log "INFO" "Linting repo"

_log "DEBUG" "Checking Python code"

uv sync --all-packages
uv run ruff check --fix --exit-non-zero-on-fix

_log "SUCCESS" "Linting done"