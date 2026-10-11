#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/compose.infra.yml"
PIPELINE_COMPOSE_FILE="$ROOT_DIR/infra/compose.ai.yml"
RUNTIME_DIR="$ROOT_DIR/.runtime"

REMOVE_VOLUMES="false"

source "$ROOT_DIR/scripts/lib/runtime.sh"

log() {
  printf '[dev-down] %s\n' "$*"
}

fail() {
  printf '[dev-down] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage: scripts/dev-down.sh [--volumes]

Options:
  --volumes   PostgreSQL, MinIO, pipeline 로컬 볼륨과 project orphan 볼륨을 삭제합니다.
  -h, --help  도움말을 출력합니다.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --volumes)
      REMOVE_VOLUMES="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "알 수 없는 옵션입니다: $1"
      ;;
  esac
done

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "'$1' 명령을 찾을 수 없습니다."
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

stop_managed_processes() {
  runtime_stop "dev" "dev-up.sh" "통합 개발 환경" "dev-down"
  runtime_stop "frontend" "front-up.sh" "프론트엔드" "dev-down"
  runtime_stop "backend" "back-up.sh" "백엔드" "dev-down"
}

down_infra() {
  local args=(-f "$COMPOSE_FILE" -f "$PIPELINE_COMPOSE_FILE" down --remove-orphans)

  if [[ "$REMOVE_VOLUMES" == "true" ]]; then
    args+=(-v)
  fi

  if docker info >/dev/null 2>&1; then
    log "PostgreSQL, MinIO, pipeline API 컨테이너를 종료합니다."
    docker compose "${args[@]}"
  else
    log "Docker daemon에 연결할 수 없어 인프라 종료는 건너뜁니다."
  fi
}

remove_project_orphan_volumes() {
  local volume

  [[ "$REMOVE_VOLUMES" == "true" ]] || return 0
  while IFS= read -r volume; do
    [[ -n "$volume" ]] || continue
    log "project orphan 볼륨 삭제: $volume"
    docker volume rm "$volume" >/dev/null
  done < <(docker volume ls -q --filter "label=com.docker.compose.project=fruition-mvp-dev")
}

main() {
  need_cmd docker

  configure_docker_host
  # 컨테이너를 지우기 전에 수집을 멈춘다. 쌓인 logs/는 지우지 않는다.
  "$ROOT_DIR/scripts/logs-up.sh" stop || true
  stop_managed_processes
  down_infra
  if docker info >/dev/null 2>&1; then
    remove_project_orphan_volumes
  fi

  if [[ "$REMOVE_VOLUMES" == "true" ]]; then
    log "전체 종료 완료: 앱 프로세스와 인프라 컨테이너, 로컬 볼륨을 정리했습니다."
  else
    log "전체 종료 완료: 앱 프로세스와 인프라 컨테이너를 정리했습니다. 로컬 볼륨은 유지됩니다."
  fi
}

main "$@"
