#! /usr/bin/env bash

# Usage: ENVIRONMENT=<your environment> PROJECT_ID=<your GCP project> ./scripts/ci/run-integration-tests.sh
# If not set, the following defaults will be set:
# ENVIRONMENT=dev
# PROJECT_ID=ragnerock-testing

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $HERE/../helpers/logger.sh

set -eo pipefail
if [[ -z "${PROJECT_ID}" ]]; then
  _log "DEBUG" "Falling back to default PROJECT_ID value"
  export PROJECT_ID=ragnerock-testing
fi
if [[ -z "${ENVIRONMENT}" ]]; then
  _log "DEBUG" "Falling back to default ENVIRONMENT value"
  export ENVIRONMENT=dev
fi

secret_environment="$ENVIRONMENT"
if [[ "$ENVIRONMENT" == "manual" ]] || [[ "$ENVIRONMENT" == "local" ]]; then
  secret_environment="dev"
fi

export GEMINI_API_KEY="$(gcloud secrets versions access latest --secret="$secret_environment-gemini-api-key" --project="$PROJECT_ID")"
export XAI_API_KEY="$(gcloud secrets versions access latest --secret="grok-api-key" --project="$PROJECT_ID")"
export RAGNEROCK_ACCESS_KEY="$(gcloud secrets versions access latest --secret="$secret_environment-access-key" --project="$PROJECT_ID")"
export CLOUDFLARE_API_TOKEN="$(gcloud secrets versions access latest --secret="$secret_environment-gemini-api-key" --project="$PROJECT_ID")"
export RAGNEROCK_API_HOST="https://api-$ENVIRONMENT.ragnerock.com"
export CLOUDFLARE_ACCOUNT_ID=398eb55bbb9962ca0692941d5ac12e3b

case $ENVIRONMENT in
  local)
    export RAGNEROCK_ACCESS_KEY='your-secret-key-for-access-codes'
    export RAGNEROCK_API_HOST="http://localhost:8080"
    export BYODB_TEST_CONNECTION_STRING="postgresql://user:password@user-postgres:5432/user"
    ;;
  dev)
    ;;
  manual)
    ;;
  production)
    export RAGNEROCK_API_HOST="https://api.ragnerock.com"
    ;;
  *)
    echo "Invalid environment: $ENVIRONMENT"
    exit 1
    ;;
esac

if [[ "$ENVIRONMENT" != "local" ]]; then
  export EPHEMERAL_TEST_BLOB_CREDENTIALS="$(gcloud secrets versions access latest --secret="$PROJECT_ID-test-blob-credentials" --project="$PROJECT_ID")"
  export EPHEMERAL_TEST_BLOB_PROVIDER="gcs"
  export EPHEMERAL_TEST_BLOB_BUCKET="$PROJECT_ID-test-blob-storage"
  export EPHEMERAL_TEST_BLOB_REGION="us-central1"
fi

_log "INFO" "Running integration tests against $RAGNEROCK_API_HOST"

uv run pytest tests/integration -m "integration or slow or ephemeral" -v -rs
