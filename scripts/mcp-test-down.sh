#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${MCP_TEST_RUNTIME_DIR:-/tmp/fruition-mcp-test}"
ENV_FILE="$RUNTIME_DIR/.env"
[[ -f "$ENV_FILE" ]] || { printf '[mcp-test-down] environment not found: %s\n' "$ENV_FILE" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

MCP_TEST_RUNTIME_DIR="$RUNTIME_DIR" "$ROOT_DIR/scripts/mcp-test-frontend.sh" stop

docker compose --env-file "$ENV_FILE" -p "$MCP_TEST_PROJECT" \
  -f "$ROOT_DIR/infra/compose.infra.yml" \
  -f "$ROOT_DIR/infra/compose.ai.yml" \
  -f "$ROOT_DIR/infra/compose.containerized.yml" \
  -f "$ROOT_DIR/infra/compose.mcp-test.yml" down

printf '[mcp-test-down] stopped project %s; volumes and credentials were preserved\n' "$MCP_TEST_PROJECT"
