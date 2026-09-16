#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/docker-compose.swagger.yml"

log() {
  printf '[swagger-down] %s\n' "$*"
}

fail() {
  printf '[swagger-down] ERROR: %s\n' "$*" >&2
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

  log "통합 Swagger UI를 종료합니다."
  docker compose -f "$COMPOSE_FILE" down
}

main "$@"
