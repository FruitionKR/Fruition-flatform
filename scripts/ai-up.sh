#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
ENV_FILE="$INFRA_DIR/.env"
ENV_EXAMPLE="$INFRA_DIR/.env.example"
COMPOSE_FILE="$INFRA_DIR/compose.infra.yml"
PIPELINE_COMPOSE_FILE="$INFRA_DIR/compose.ai.yml"
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
  printf '[ai-up] %s\n' "$*"
}

fail() {
  printf '[ai-up] ERROR: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "'$1' 명령을 찾을 수 없습니다."
}

ensure_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    return
  fi

  [[ -f "$ENV_EXAMPLE" ]] || fail "환경변수 예시 파일이 없습니다: $ENV_EXAMPLE"
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  log "infra/.env가 없어 infra/.env.example에서 복사했습니다. LLM 기능을 쓰려면 API 키를 채워야 합니다."
}

ensure_docker() {
  need_cmd docker

  if docker info >/dev/null 2>&1; then
    return
  fi

  local colima_socket="$HOME/.colima/default/docker.sock"
  if [[ -S "$colima_socket" ]]; then
    export DOCKER_HOST="unix://$colima_socket"
    if docker info >/dev/null 2>&1; then
      log "Colima Docker socket을 사용합니다: $colima_socket"
      return
    fi
  fi

  if command -v colima >/dev/null 2>&1; then
    log "Docker daemon에 연결할 수 없어 Colima를 시작합니다."
    colima start
  fi

  if docker info >/dev/null 2>&1; then
    return
  fi

  if [[ -S "$colima_socket" ]]; then
    export DOCKER_HOST="unix://$colima_socket"
  fi

  docker info >/dev/null 2>&1 || fail "Docker daemon에 연결할 수 없습니다."
}

cleanup_stale_pipeline_orphans() {
  local container_ids

  container_ids="$(docker ps -aq \
    --filter "label=com.docker.compose.project=fruition-mvp-dev" \
    --filter "label=com.docker.compose.service=pipeline-api" \
    --filter "status=created" \
    --filter "status=exited" \
    --filter "status=dead")"

  if [[ -z "$container_ids" ]]; then
    return
  fi

  log "중지된 pipeline-api 컨테이너를 정리합니다."
  docker rm $container_ids >/dev/null
}

wait_for_pipeline() {
  for _ in $(seq 1 120); do
    if curl -fsS "http://localhost:8000/health" >/dev/null 2>&1; then
      log "Pipeline API 응답 확인: http://localhost:8000/health"
      return
    fi
    sleep 1
  done

  fail "Pipeline API 응답을 확인하지 못했습니다: http://localhost:8000/health"
}

main() {
  need_cmd curl
  ensure_env_file
  ensure_docker

  curl -fsS "http://localhost:8082/actuator/health" >/dev/null 2>&1 \
    || fail "backend가 실행 중이어야 합니다. scripts/back-up.sh를 먼저 실행하세요."

  cleanup_stale_pipeline_orphans
  log "Pipeline 이미지를 한 번 빌드합니다."
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -f "$PIPELINE_COMPOSE_FILE" build pipeline-api
  log "Pipeline API와 워커를 시작합니다."
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -f "$PIPELINE_COMPOSE_FILE" up -d --no-build "${PIPELINE_SERVICES[@]}"
  wait_for_pipeline
}

main "$@"
