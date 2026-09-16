#!/usr/bin/env bash
set -Eeuo pipefail

# 워커 컨테이너 로그를 호스트 파일로 모은다.
# 컨테이너 로그는 docker가 컨테이너 안에 들고 있어서, dev-down.sh로 컨테이너를 지우면
# 함께 사라진다. 재기동 뒤에도 이전 에러를 확인하려면 호스트로 빼내야 한다.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
LOGS_DIR="$ROOT_DIR/logs"
ENV_FILE="$INFRA_DIR/.env"
COMPOSE_FILE="$INFRA_DIR/compose.infra.yml"
PIPELINE_COMPOSE_FILE="$INFRA_DIR/compose.ai.yml"

TARGET="$LOGS_DIR/workers.log"
PID_FILE="$LOGS_DIR/.logs-up.pid"
MAX_BYTES=$((100 * 1024 * 1024))

log() {
  printf '[logs-up] %s\n' "$*"
}

fail() {
  printf '[logs-up] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage: scripts/logs-up.sh [start|stop|status]

  start   (기본) 워커 로그 수집을 백그라운드로 시작한다. logs/workers.log에 쌓인다.
  stop    수집을 중단한다. 이미 쌓인 파일은 지우지 않는다.
  status  수집 중인지, 파일이 얼마나 쌓였는지 출력한다.
USAGE
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

running_pid() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  printf '%s' "$pid"
}

# 파일이 상한을 넘으면 .1로 밀어두고 새로 시작한다. 세대는 하나만 남긴다.
rotate_if_needed() {
  [[ -f "$TARGET" ]] || return 0
  local size
  size="$(wc -c < "$TARGET" | tr -d ' ')"
  if (( size >= MAX_BYTES )); then
    mv "$TARGET" "$TARGET.1"
    log "상한(100MB) 초과로 이전 로그를 workers.log.1로 옮겼습니다."
  fi
}

start() {
  need_docker
  mkdir -p "$LOGS_DIR"

  if pid="$(running_pid)"; then
    log "이미 수집 중입니다. PID $pid"
    return
  fi

  rotate_if_needed

  # --since 0m: 수집 시작 이전 로그는 건너뛴다. 재시작할 때마다 전체가 중복 append되는 것을 막는다.
  # --no-color: 파일에 ANSI escape가 섞이지 않게 한다.
  nohup docker compose --env-file "$ENV_FILE" \
    -f "$COMPOSE_FILE" -f "$PIPELINE_COMPOSE_FILE" \
    logs --follow --no-color --timestamps --since 0m \
    >> "$TARGET" 2>&1 &

  echo $! > "$PID_FILE"
  log "수집을 시작했습니다. PID $(cat "$PID_FILE") → $TARGET"
}

stop() {
  if ! pid="$(running_pid)"; then
    log "수집 중이 아닙니다."
    rm -f "$PID_FILE"
    return
  fi
  kill "$pid" >/dev/null 2>&1 || true
  rm -f "$PID_FILE"
  log "수집을 중단했습니다. 쌓인 로그는 $TARGET 에 그대로 있습니다."
}

status() {
  if pid="$(running_pid)"; then
    log "수집 중입니다. PID $pid"
  else
    log "수집 중이 아닙니다."
  fi
  if [[ -f "$TARGET" ]]; then
    log "$TARGET ($(du -h "$TARGET" | cut -f1), $(wc -l < "$TARGET" | tr -d ' ')줄)"
  else
    log "아직 수집된 로그가 없습니다."
  fi
}

need_docker() {
  command -v docker >/dev/null 2>&1 || fail "'docker' 명령을 찾을 수 없습니다."
  configure_docker_host
  docker info >/dev/null 2>&1 || fail "Docker daemon에 연결할 수 없습니다."
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  -h|--help) usage ;;
  *) fail "알 수 없는 인자입니다: $1" ;;
esac
