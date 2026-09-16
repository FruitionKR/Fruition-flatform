#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
ENV_FILE="$INFRA_DIR/.env"
ENV_EXAMPLE="$INFRA_DIR/.env.example"
COMPOSE_FILE="$INFRA_DIR/compose.infra.yml"
RUNTIME_DIR="$ROOT_DIR/.runtime"
DOCUMENT_PID=""
ACCESS_PID=""

source "$ROOT_DIR/scripts/lib/runtime.sh"

log() {
  printf '[back-up] %s\n' "$*"
}

fail() {
  printf '[back-up] ERROR: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "'$1' 명령을 찾을 수 없습니다. docs/script.md의 요구사항을 확인하세요."
}

cleanup() {
  if [[ -n "${ACCESS_PID:-}" ]] && kill -0 "$ACCESS_PID" >/dev/null 2>&1; then
    kill "$ACCESS_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${DOCUMENT_PID:-}" ]] && kill -0 "$DOCUMENT_PID" >/dev/null 2>&1; then
    kill "$DOCUMENT_PID" >/dev/null 2>&1 || true
  fi
  runtime_unregister "backend"
}

shutdown() {
  trap - INT TERM EXIT
  cleanup
  exit 0
}

ensure_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    return
  fi

  [[ -f "$ENV_EXAMPLE" ]] || fail "환경변수 예시 파일이 없습니다: $ENV_EXAMPLE"
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  log "infra/.env가 없어 infra/.env.example에서 복사했습니다."
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

wait_for_postgres() {
  local status

  for _ in $(seq 1 60); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' fruition-postgresql-dev 2>/dev/null || true)"
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      log "PostgreSQL 컨테이너 상태 확인: $status"
      return
    fi
    sleep 1
  done

  fail "PostgreSQL 컨테이너가 준비되지 않았습니다."
}

wait_for_service() {
  local url="$1"
  local label="$2"
  local pid="$3"

  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "$label 응답 확인: $url"
      return
    fi

    kill -0 "$pid" >/dev/null 2>&1 || fail "$label 프로세스가 시작 중 종료되었습니다."
    sleep 1
  done

  fail "$label 응답을 확인하지 못했습니다: $url"
}

main() {
  need_cmd curl
  ensure_env_file
  ensure_docker

  if runtime_is_running "backend" "back-up.sh"; then
    if curl -fsS "http://localhost:8082/actuator/health" >/dev/null 2>&1 \
      && curl -fsS "http://localhost:8083/actuator/health" >/dev/null 2>&1; then
      log "이 프로젝트가 관리하는 백엔드가 이미 실행 중입니다."
      return
    fi
    fail "관리 중인 백엔드 supervisor는 실행 중이지만 서비스 health check가 실패했습니다."
  fi

  # 8082·8083은 actuator 전용 관리 포트다 (application.properties의 management.server.port).
  if runtime_port_in_use 8080 || runtime_port_in_use 8081 \
    || runtime_port_in_use 8082 || runtime_port_in_use 8083; then
    fail "8080·8081·8082·8083 중 한 포트를 다른 프로세스가 사용 중입니다. 해당 프로세스를 먼저 종료하세요."
  fi

  local java21_home
  java21_home="$(find_java21_home)" || fail "Java 21을 찾지 못했습니다. JAVA_HOME_21을 지정하거나 JDK 21을 설치하세요."

  log "PostgreSQL과 MinIO를 시작합니다."
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d
  wait_for_postgres

  runtime_register "backend" "back-up.sh" || fail "백엔드 supervisor 상태를 등록하지 못했습니다."
  trap shutdown INT TERM
  trap cleanup EXIT

  # flyway migration은 document-svc가 소유하므로 document-svc를 먼저 띄운다.
  log "document-svc를 시작합니다. Java 21: $java21_home"
  (
    cd "$ROOT_DIR/../Document"
    SERVICE_ENV_FILE="$ENV_FILE" JAVA_HOME="$java21_home" ./gradlew bootRun -Porg.gradle.java.installations.paths="$java21_home"
  ) &
  DOCUMENT_PID="$!"

  wait_for_service "http://localhost:8082/actuator/health" "document-svc" "$DOCUMENT_PID"

  log "access-svc를 시작합니다. Java 21: $java21_home"
  (
    cd "$ROOT_DIR/../Access"
    SERVICE_ENV_FILE="$ENV_FILE" JAVA_HOME="$java21_home" ./gradlew bootRun -Porg.gradle.java.installations.paths="$java21_home"
  ) &
  ACCESS_PID="$!"

  wait_for_service "http://localhost:8083/actuator/health" "access-svc" "$ACCESS_PID"
  log "종료하려면 Ctrl-C를 누르거나 scripts/back-down.sh를 실행하세요."
  wait "$DOCUMENT_PID" "$ACCESS_PID"
}

main "$@"
