#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
FRONTEND_DIR="$ROOT_DIR/../frontend"
PIPELINE_DIR="$ROOT_DIR/../AI/pipeline"
ENV_FILE="$INFRA_DIR/.env"
ENV_EXAMPLE="$INFRA_DIR/.env.example"

WITH_PYTHON=false

log() {
  printf '[bootstrap] %s\n' "$*"
}

fail() {
  printf '[bootstrap] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'INFO'
Usage: ./scripts/bootstrap.sh [--with-python]

새 개발 환경에서 필요한 프로젝트 의존성을 준비합니다.

Options:
  --with-python  AI/pipeline/.venv를 만들고 AI/pipeline/requirements.txt를 설치합니다.
  -h, --help     도움말을 출력합니다.
INFO
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --with-python)
        WITH_PYTHON=true
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "알 수 없는 옵션입니다: $1"
        ;;
    esac
    shift
  done
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "'$1' 명령을 찾을 수 없습니다. docs/script.md의 요구사항을 확인하세요."
}

major_version() {
  printf '%s\n' "$1" | sed -E 's/^v?([0-9]+).*/\1/'
}

need_major_at_least() {
  local name="$1"
  local current="$2"
  local minimum="$3"
  local major

  major="$(major_version "$current")"
  [[ "$major" =~ ^[0-9]+$ ]] || fail "$name 버전을 확인하지 못했습니다: $current"
  (( major >= minimum )) || fail "$name $minimum 이상이 필요합니다. 현재 버전: $current"
}

java_home_version() {
  local home="$1"
  [[ -x "$home/bin/java" ]] || return 1
  "$home/bin/java" -version 2>&1 | head -n 1 | grep -Eq 'version "21\.|openjdk version "21\.'
}

find_java21_home() {
  local candidate

  for candidate in "${JAVA_HOME_21:-}" "${JAVA_HOME:-}"; do
    if [[ -n "$candidate" ]] && java_home_version "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  if command -v /usr/libexec/java_home >/dev/null 2>&1; then
    candidate="$(/usr/libexec/java_home -v 21 2>/dev/null || true)"
    if [[ -n "$candidate" ]] && java_home_version "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  local common_paths=(
    "/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
    "/usr/local/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
    "/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home"
    "/usr/lib/jvm/temurin-21-jdk-amd64"
    "/usr/lib/jvm/java-21-openjdk"
    "/usr/lib/jvm/java-21-openjdk-amd64"
  )

  for candidate in "${common_paths[@]}"; do
    if [[ -d "$candidate" ]] && java_home_version "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

ensure_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    return
  fi

  [[ -f "$ENV_EXAMPLE" ]] || fail "환경변수 예시 파일이 없습니다: $ENV_EXAMPLE"
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  log "infra/.env가 없어 infra/.env.example에서 복사했습니다. LLM 기능을 쓰려면 API 키를 채워야 합니다."
}

check_system_requirements() {
  need_cmd curl
  need_cmd docker
  docker compose version >/dev/null 2>&1 || fail "'docker compose'를 사용할 수 없습니다. Docker Compose CLI plugin을 설치하세요."

  need_cmd node
  need_cmd npm
  need_major_at_least "Node.js" "$(node -v)" 20
  need_major_at_least "npm" "$(npm -v)" 10
  find_java21_home >/dev/null || fail "Java 21을 찾지 못했습니다. JAVA_HOME_21을 지정하거나 JDK 21을 설치하세요."
}

install_frontend_deps() {
  local lock_file="$FRONTEND_DIR/package-lock.json"
  local package_file="$FRONTEND_DIR/package.json"
  local installed_lock="$FRONTEND_DIR/node_modules/.package-lock.json"

  [[ -f "$package_file" ]] || fail "프론트엔드 package.json을 찾을 수 없습니다: $package_file"

  if [[ ! -d "$FRONTEND_DIR/node_modules" || ! -f "$installed_lock" || "$package_file" -nt "$installed_lock" || "$lock_file" -nt "$installed_lock" ]]; then
    log "프론트엔드 의존성을 설치합니다."
    (cd "$FRONTEND_DIR" && npm install)
    log "프론트엔드 의존성 취약점을 안전 범위에서 자동 수정합니다."
    (cd "$FRONTEND_DIR" && npm audit fix) || log "자동 수정되지 않은 취약점이 있습니다. npm audit 결과를 확인하세요."
    return
  fi

  log "프론트엔드 의존성이 이미 준비되어 있습니다."
}

install_python_deps() {
  local venv_dir="$PIPELINE_DIR/.venv"
  local pip_bin="$venv_dir/bin/pip"
  local requirements_file="$PIPELINE_DIR/requirements.txt"
  local stamp_file="$venv_dir/.requirements.stamp"

  [[ -f "$requirements_file" ]] || fail "Python requirements 파일을 찾을 수 없습니다: $requirements_file"
  need_cmd python3

  if [[ ! -x "$pip_bin" ]]; then
    log "llmPipeline Python 가상환경을 생성합니다."
    python3 -m venv "$venv_dir"
  fi

  if [[ ! -f "$stamp_file" || "$requirements_file" -nt "$stamp_file" ]]; then
    log "llmPipeline Python 의존성을 설치합니다."
    "$pip_bin" install -r "$requirements_file"
    touch "$stamp_file"
    return
  fi

  log "llmPipeline Python 의존성이 이미 준비되어 있습니다."
}

main() {
  parse_args "$@"
  check_system_requirements
  ensure_env_file
  install_frontend_deps

  if [[ "$WITH_PYTHON" == true ]]; then
    install_python_deps
  fi

  log "개발 환경 준비가 끝났습니다."
}

main "$@"
