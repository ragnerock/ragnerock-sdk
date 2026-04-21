#! /usr/bin/env bash

# Usage: ./scripts/ci/check.sh

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $HERE/helpers/logger.sh

set -eo pipefail

_log "INFO" "Generating documentation"

_log "DEBUG" "Removing existing doc build"

rm -rf docs/build || true

_log "DEBUG" "Building sphyinx docs"

uv sync --all-packages
uv run sphinx-build -c docs/source -b html docs/source docs/build

_log "SUCCESS" "Documentation generation done"