#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"

source "$ROOT_DIR/scripts/lib/runtime.sh"

log() {
  printf '[back-down] %s\n' "$*"
}

stop_backend() {
  runtime_stop "backend" "back-up.sh" "백엔드" "back-down"
}

stop_backend
