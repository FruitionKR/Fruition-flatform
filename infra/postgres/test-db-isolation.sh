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
  # AI 대상이면 converter 전용 role이 하나 더 생긴다.
  roles=$((expected * 2))
  bad_inputs=()
  if [[ " ${selected[*]} " == *' AI '* ]]; then
    env_args+=(-e AI_DB_CONVERTER_USER=ai_converter -e AI_DB_CONVERTER_PASSWORD=converter_test_password)
    roles=$((roles + 1))
    bad_inputs=('AI_DB_CONVERTER_PASSWORD=' 'AI_DB_CONVERTER_USER=ai_runtime')
  fi
  # 설정 오류는 psql을 호출하기 전에 실패해야 한다. 관리자 암호도 틀리게 주어 DB 접속 실패와 구별한다.
  for bad in 'DB_ISOLATION_TARGET=wrong' "${selected[0]}_DB_RUNTIME_PASSWORD=" "${selected[0]}_DB_NAME=postgres" "${selected[0]}_DB_RUNTIME_USER=bootstrap" "${selected[0]}_DB_MIGRATION_USER=$(printf '%s' "${selected[0]}" | tr '[:upper:]' '[:lower:]')_runtime" ${bad_inputs[@]+"${bad_inputs[@]}"}; do
    if output="$(docker exec "${env_args[@]}" -e POSTGRES_ADMIN_PASSWORD=wrong -e "$bad" "$container" bash /work/init-db-isolation.sh 2>&1)"; then
      printf '잘못된 입력이 성공했습니다: %s\n' "$bad" >&2; exit 1
    fi
    [[ "$output" == *'[db-isolation] ERROR:'* ]] || { printf '%s\n' "$output"; exit 1; }
  done
  [[ "$(docker exec "$container" psql -U postgres -Atc "SELECT count(*) FROM pg_database WHERE datname NOT IN ('postgres','template0','template1')")" == 0 ]]
  for repeat in 1 2; do
    docker exec "${env_args[@]}" "$container" bash /work/init-db-isolation.sh >/dev/null
    docker exec "${env_args[@]}" "$container" bash /work/validate-db-isolation.sh
    if [[ "$repeat" == 1 && "$roles" != "$((expected * 2))" ]]; then
      # AI 스키마 적용(ai_schema.sql + AI_DB_CONVERTER_ROLE 부여)을 흉내 내 두 번째 init이 원장 권한을 지우지 않는지와 원장 검증을 확인한다.
      docker exec -e PGPASSWORD=migration_test_password "$container" psql -h 127.0.0.1 -U ai_migration -d ai_db -v ON_ERROR_STOP=1 -c "CREATE TABLE ai_model_usage (id uuid PRIMARY KEY, run_id text NOT NULL, workspace_id text NOT NULL, user_id text NOT NULL, kind text NOT NULL, provider text NOT NULL, requested_model text NOT NULL, model text NOT NULL, status text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz); GRANT INSERT, UPDATE (status, finished_at) ON ai_model_usage TO ai_converter; GRANT SELECT (id, status, finished_at) ON ai_model_usage TO ai_converter;" >/dev/null
    fi
  done
  count="$(docker exec "$container" psql -U postgres -Atc "SELECT count(*) FROM pg_database WHERE datname NOT IN ('postgres','template0','template1')")"
  [[ "$count" == "$expected" ]]
  count="$(docker exec "$container" psql -U postgres -Atc "SELECT count(*) FROM pg_roles WHERE rolname NOT IN ('postgres', 'bootstrap') AND rolname NOT LIKE 'pg_%'")"
  [[ "$count" == "$roles" ]]
  printf '[db-isolation-test] %s 생성 범위·반복 실행·권한 검증 PASS\n' "$target"
  cleanup
done
