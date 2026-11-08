#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${MCP_TEST_RUNTIME_DIR:-/tmp/fruition-mcp-test}"
ENV_FILE="$RUNTIME_DIR/.env"
[[ -f "$ENV_FILE" ]] || { printf '[mcp-test-frontend] environment not found: %s\n' "$ENV_FILE" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

SOURCE_DIR="${MCP_TEST_FRONTEND_DIR:-$ROOT_DIR/../Fruition-frontend/web}"
DEPENDENCIES_DIR="${MCP_TEST_FRONTEND_DEPENDENCIES_DIR:-/tmp/fruition-mcp-supervision/upstream-integration/frontend-candidate/web/node_modules}"
FIXTURE_DIR="$RUNTIME_DIR/frontend/web"
PID_FILE="$RUNTIME_DIR/frontend.pid"
LOG_FILE="$RUNTIME_DIR/frontend.log"
PORT="${MCP_TEST_FRONTEND_PORT:-58300}"
NODE_BIN="$(command -v node || true)"

log() { printf '[mcp-test-frontend] %s\n' "$*"; }
fail() { printf '[mcp-test-frontend] ERROR: %s\n' "$*" >&2; exit 1; }
responds() { curl -sS --max-time 2 -o /dev/null "http://127.0.0.1:$PORT/mcp/authorize" 2>/dev/null; }
running_pid() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid command
  pid="$(<"$PID_FILE")"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$command" == *"$FIXTURE_DIR/node_modules/next/dist/bin/next"* ]] || return 1
  printf '%s' "$pid"
}

start() {
  local pid node_version next_version
  if pid="$(running_pid)"; then
    responds || fail "owned frontend PID $pid is running but port $PORT does not respond"
    log "already running on http://127.0.0.1:$PORT (PID $pid)"
    return
  fi
  rm -f "$PID_FILE"
  responds && fail "port $PORT is already serving an unowned process"
  [[ -n "$NODE_BIN" ]] || fail "cached host Node is unavailable"
  node_version="$($NODE_BIN -p 'process.versions.node')"
  [[ "${node_version%%.*}" == "26" ]] || fail "local fixture requires the validated Node 26 runtime, found $node_version"
  [[ -d "$SOURCE_DIR" ]] || fail "frontend source is absent: $SOURCE_DIR"
  [[ -f "$DEPENDENCIES_DIR/next/package.json" ]] || fail "cached frontend dependencies are absent: $DEPENDENCIES_DIR"
  next_version="$($NODE_BIN -p 'require(process.argv[1] + "/next/package.json").version' "$DEPENDENCIES_DIR")"
  [[ "$next_version" == "15.5.28" ]] || fail "validated Next 15.5.28 cache is required, found $next_version"
  command -v rsync >/dev/null 2>&1 || fail "rsync is unavailable"

  install -d -m 700 "$FIXTURE_DIR"
  rsync -a --delete --exclude node_modules --exclude .next "$SOURCE_DIR/" "$FIXTURE_DIR/"
  if [[ -L "$FIXTURE_DIR/node_modules" ]]; then
    [[ "$(readlink "$FIXTURE_DIR/node_modules")" == "$DEPENDENCIES_DIR" ]] || fail "fixture dependency link points elsewhere"
  elif [[ -e "$FIXTURE_DIR/node_modules" ]]; then
    fail "fixture node_modules exists but is not the expected cached dependency link"
  else
    ln -s "$DEPENDENCIES_DIR" "$FIXTURE_DIR/node_modules"
  fi

  log "starting task-local copy with Node $node_version / Next $next_version"
  cd "$FIXTURE_DIR"
  nohup env \
    ACCESS_URL="http://127.0.0.1:${MCP_TEST_ACCESS_PORT:-58081}" \
    BACKEND_URL="http://127.0.0.1:${MCP_TEST_DOCUMENT_PORT:-58080}" \
    NEXT_TELEMETRY_DISABLED=1 \
    "$NODE_BIN" "$FIXTURE_DIR/node_modules/next/dist/bin/next" dev \
      --hostname 127.0.0.1 --port "$PORT" \
      >"$LOG_FILE" 2>&1 </dev/null &
  pid=$!
  cd "$ROOT_DIR"
  printf '%s\n' "$pid" >"$PID_FILE"
  chmod 600 "$PID_FILE" "$LOG_FILE"
  for _ in $(seq 1 90); do
    if responds; then
      log "ready on http://127.0.0.1:$PORT (PID $pid)"
      return
    fi
    kill -0 "$pid" >/dev/null 2>&1 || fail "frontend exited during startup; inspect $LOG_FILE"
    sleep 1
  done
  fail "frontend did not become ready; inspect $LOG_FILE"
}

stop() {
  local pid
  if ! pid="$(running_pid)"; then
    rm -f "$PID_FILE"
    log "no owned frontend process is running"
    return
  fi
  kill "$pid"
  for _ in $(seq 1 30); do
    kill -0 "$pid" >/dev/null 2>&1 || { rm -f "$PID_FILE"; log "stopped PID $pid"; return; }
    sleep 1
  done
  fail "frontend PID $pid did not stop"
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  *) fail "usage: $0 [start|stop]" ;;
esac
