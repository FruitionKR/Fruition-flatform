#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"

source "$ROOT_DIR/scripts/lib/runtime.sh"

log() {
  printf '[front-down] %s\n' "$*"
}

stop_frontend() {
  runtime_stop "frontend" "front-up.sh" "프론트엔드" "front-down"
}

stop_frontend
