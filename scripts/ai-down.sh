#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/compose.infra.yml"
PIPELINE_COMPOSE_FILE="$ROOT_DIR/infra/compose.ai.yml"
PIPELINE_SERVICES=(
  pipeline-api
  ingest-worker
  query-task-worker
  agent-task-worker
  maintenance-task-worker
  edit-event-consumer
  pipeline-agent-worker
)

log() {
  printf '[ai-down] %s\n' "$*"
}

fail() {
  printf '[ai-down] ERROR: %s\n' "$*" >&2
  exit 1
}

configure_docker_host() {
  if docker info >/dev/null 2>&1; then
    return
  fi

  local colima_socket="$HOME/.colima/default/docker.sock"
  if [[ -S "$colima_socket" ]]; then
    export DOCKER_HOST="unix://$colima_socket"
  fi
}

main() {
  command -v docker >/dev/null 2>&1 || fail "'docker' 명령을 찾을 수 없습니다."
  configure_docker_host
  docker info >/dev/null 2>&1 || fail "Docker daemon에 연결할 수 없습니다."

  log "Pipeline API와 워커 컨테이너를 종료합니다."
  docker compose -f "$COMPOSE_FILE" -f "$PIPELINE_COMPOSE_FILE" stop "${PIPELINE_SERVICES[@]}"
  log "Pipeline API와 워커 종료를 완료했습니다. PostgreSQL, MinIO와 로컬 볼륨은 유지됩니다."
}

main "$@"
