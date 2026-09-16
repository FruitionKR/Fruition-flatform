#!/usr/bin/env bash
set -Eeuo pipefail
# 실행마다 새 컨테이너만 만들고 정리한다. 개발 DB·볼륨을 사용하지 않는다.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
container="fruition-db-isolation-test-$$-${RANDOM}"
cleanup() { docker rm -fv "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT

for target in access core all; do
  docker run -d --name "$container" -e POSTGRES_PASSWORD=isolated_test_admin \
    -v "$script_dir:/work:ro" postgres:16-alpine >/dev/null
  ready=false
  for attempt in {1..60}; do
    if docker exec "$container" pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1; then ready=true; break; fi
    sleep 1
  done
  [[ "$ready" == true ]] || { docker logs "$container"; exit 1; }
  docker exec "$container" psql -U postgres -c "CREATE ROLE bootstrap LOGIN CREATEDB CREATEROLE PASSWORD 'isolated_test_admin';" >/dev/null
  env_args=(-e DB_ISOLATION_TARGET="$target" -e PGHOST=127.0.0.1 -e PGPORT=5432 -e POSTGRES_ADMIN_USER=bootstrap -e POSTGRES_ADMIN_PASSWORD=isolated_test_admin)
  case "$target" in access) selected=(ACCESS); expected=1 ;; core) selected=(CORE AI); expected=2 ;; all) selected=(ACCESS CORE AI); expected=3 ;; esac
  for service in "${selected[@]}"; do
    lower="$(printf '%s' "$service" | tr '[:upper:]' '[:lower:]')"
    env_args+=(-e "${service}_DB_NAME=${lower}_db" -e "${service}_DB_RUNTIME_USER=${lower}_runtime" -e "${service}_DB_RUNTIME_PASSWORD=runtime_test_password" -e "${service}_DB_MIGRATION_USER=${lower}_migration" -e "${service}_DB_MIGRATION_PASSWORD=migration_test_password")
  done
  # 설정 오류는 psql을 호출하기 전에 실패해야 한다. 관리자 암호도 틀리게 주어 DB 접속 실패와 구별한다.
  for bad in 'DB_ISOLATION_TARGET=wrong' "${selected[0]}_DB_RUNTIME_PASSWORD=" "${selected[0]}_DB_NAME=postgres" "${selected[0]}_DB_RUNTIME_USER=bootstrap" "${selected[0]}_DB_MIGRATION_USER=$(printf '%s' "${selected[0]}" | tr '[:upper:]' '[:lower:]')_runtime"; do
    if output="$(docker exec "${env_args[@]}" -e POSTGRES_ADMIN_PASSWORD=wrong -e "$bad" "$container" bash /work/init-db-isolation.sh 2>&1)"; then
      printf '잘못된 입력이 성공했습니다: %s\n' "$bad" >&2; exit 1
    fi
    [[ "$output" == *'[db-isolation] ERROR:'* ]] || { printf '%s\n' "$output"; exit 1; }
  done
  [[ "$(docker exec "$container" psql -U postgres -Atc "SELECT count(*) FROM pg_database WHERE datname NOT IN ('postgres','template0','template1')")" == 0 ]]
  for repeat in 1 2; do
    docker exec "${env_args[@]}" "$container" bash /work/init-db-isolation.sh >/dev/null
    docker exec "${env_args[@]}" "$container" bash /work/validate-db-isolation.sh
  done
  count="$(docker exec "$container" psql -U postgres -Atc "SELECT count(*) FROM pg_database WHERE datname NOT IN ('postgres','template0','template1')")"
  [[ "$count" == "$expected" ]]
  count="$(docker exec "$container" psql -U postgres -Atc "SELECT count(*) FROM pg_roles WHERE rolname NOT IN ('postgres', 'bootstrap') AND rolname NOT LIKE 'pg_%'")"
  [[ "$count" == "$((expected * 2))" ]]
  printf '[db-isolation-test] %s 생성 범위·반복 실행·권한 검증 PASS\n' "$target"
  cleanup
done
