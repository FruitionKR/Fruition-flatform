#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/docker-compose.swagger.yml"
SWAGGER_UI_PORT="${SWAGGER_UI_PORT:-8090}"

log() {
  printf '[swagger-up] %s\n' "$*"
}

fail() {
  printf '[swagger-up] ERROR: %s\n' "$*" >&2
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
  command -v curl >/dev/null 2>&1 || fail "'curl' 명령을 찾을 수 없습니다."
  configure_docker_host
  docker info >/dev/null 2>&1 || fail "Docker daemon에 연결할 수 없습니다."

  [[ -f "$ROOT_DIR/../Document/api-specs/openapi.yaml" ]] \
    || fail "api-specs 명세가 없습니다. Document에서 ./gradlew test -DupdateOpenApiSnapshot=true 를 먼저 실행하세요."

  log "통합 Swagger UI를 시작합니다."
  SWAGGER_UI_PORT="$SWAGGER_UI_PORT" docker compose -f "$COMPOSE_FILE" up -d

  for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$SWAGGER_UI_PORT/" >/dev/null 2>&1; then
      log "실행 완료: http://localhost:$SWAGGER_UI_PORT"
      return
    fi
    sleep 1
  done

  fail "Swagger UI 응답을 확인하지 못했습니다: http://localhost:$SWAGGER_UI_PORT"
}

main "$@"
