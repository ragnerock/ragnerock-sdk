#! /usr/bin/env bash

# Usage: ./scripts/ci/format.sh

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $HERE/helpers/logger.sh

set -eo pipefail

uv sync --all-packages

_log "INFO" "Formatting repo"

_log "DEBUG" "Formatting Python code"

uv run ruff format --exit-non-zero-on-format

_log "SUCCESS" "Repository formatting finished"