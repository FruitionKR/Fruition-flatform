#!/usr/bin/env bash
set -Eeuo pipefail
# 임시 DB만 사용한다. 실제 image와 동일한 bootJar/main 및 Python CLI를 실행한다.
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
java_bin="${JAVA_HOME_21:-/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home}/bin/java"
python_bin="${PIPELINE_PYTHON:-$repo/../AI/pipeline/.venv/bin/python}"
container="fruition-migration-test-$$-${RANDOM}"
redis_container="${container}-redis"
test_dir="$(mktemp -d)"
runtime_pid=""
cleanup() {
  if [[ -n "$runtime_pid" ]]; then kill "$runtime_pid" 2>/dev/null || true; wait "$runtime_pid" 2>/dev/null || true; fi
  docker rm -fv "$container" >/dev/null 2>&1 || true
  docker rm -fv "$redis_container" >/dev/null 2>&1 || true
  rm -rf "$test_dir"
}
trap cleanup EXIT
docker run -d --name "$container" -p 127.0.0.1::5432 -e POSTGRES_PASSWORD=isolated_test_admin \
  -v "$repo/infra/postgres:/work:ro" postgres:16-alpine >/dev/null
ready=false
for attempt in {1..60}; do
  if docker exec "$container" pg_isready -U postgres >/dev/null 2>&1; then ready=true; break; fi
  sleep 1
done
[[ "$ready" == true ]]
port="$(docker port "$container" 5432/tcp | cut -d: -f2)"
docker run -d --name "$redis_container" -p 127.0.0.1::6379 redis:7-alpine >/dev/null
redis_port="$(docker port "$redis_container" 6379/tcp | cut -d: -f2)"
ready=false
for attempt in {1..30}; do
  if docker exec "$redis_container" redis-cli ping 2>/dev/null | rg -q PONG; then ready=true; break; fi
  sleep 1
done
[[ "$ready" == true ]]
env_args=(-e DB_ISOLATION_TARGET=all -e POSTGRES_ADMIN_USER=postgres -e POSTGRES_ADMIN_PASSWORD=isolated_test_admin)
for service in ACCESS CORE AI; do
  lower="$(printf '%s' "$service" | tr '[:upper:]' '[:lower:]')"
  env_args+=(-e "${service}_DB_NAME=${lower}_db" -e "${service}_DB_RUNTIME_USER=${lower}_runtime"
    -e "${service}_DB_RUNTIME_PASSWORD=runtime_test_password" -e "${service}_DB_MIGRATION_USER=${lower}_migration"
    -e "${service}_DB_MIGRATION_PASSWORD=migration_test_password")
done
docker exec "${env_args[@]}" "$container" bash /work/init-db-isolation.sh >"$test_dir/bootstrap.log" 2>&1
cd "$test_dir"
for service in access document; do
  if [[ "$service" == access ]]; then db=ACCESS; app=AccessApplication; else db=CORE; app=DocumentApplication; fi
  lower="$(printf '%s' "$db" | tr '[:upper:]' '[:lower:]')"
  if [[ "$service" == access ]]; then service_dir=Access; else service_dir=Document; fi
  jar="$repo/../$service_dir/build/libs/$service-svc-0.0.1-SNAPSHOT.jar"
  # Missing input must fail before Spring/DB startup.
  if env -i PATH="$PATH" "$java_bin" -jar "$jar" --migrate-only >"$test_dir/missing.log" 2>&1; then
    echo 'migration 필수 입력 누락이 성공으로 처리됨' >&2; exit 1
  fi
  rg -q '필수 migration 설정 누락: POSTGRES_HOST' "$test_dir/missing.log"
  for repeat in 1 2; do
    env -i PATH="$PATH" POSTGRES_HOST=127.0.0.1 POSTGRES_PORT="$port" \
      "${db}_DB_NAME=${lower}_db" "${db}_DB_MIGRATION_USER=${lower}_migration" \
      "${db}_DB_MIGRATION_PASSWORD=migration_test_password" \
      "$java_bin" -jar "$jar" --migrate-only >"$test_dir/$service-migration.log" 2>&1 || {
        cat "$test_dir/$service-migration.log"; exit 1;
      }
  done
  # Runtime receives only its own runtime DB password; not migration/admin or other-service credentials.
  common=(PATH="$PATH" SPRING_PROFILES_ACTIVE=production POSTGRES_HOST=127.0.0.1 POSTGRES_PORT="$port"
    "${db}_DB_RUNTIME_PASSWORD=runtime_test_password" SERVER_PORT=0 MANAGEMENT_PORT=0
    REDIS_HOST=127.0.0.1 REDIS_PORT="$redis_port"
    SPRING_KAFKA_LISTENER_AUTO_STARTUP=false KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:1
    S3_ENDPOINT=http://127.0.0.1:1 ACCESS_INTERNAL_BASE_URL=http://127.0.0.1:1
    DOCUMENT_INTERNAL_BASE_URL=http://127.0.0.1:1
    JWT_SECRET=test-only-jwt-secret-at-least-32-bytes-long INTERNAL_CALLBACK_TOKEN=test-callback)
  if [[ "$service" == access ]]; then
    own=(MFA_ENCRYPTION_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= SPRING_MAIL_HOST=smtp.example.com
      SPRING_MAIL_PORT=587 SPRING_MAIL_USERNAME=test-user SPRING_MAIL_PASSWORD=test-password MAIL_FROM=noreply@example.com
      WORKSPACE_INVITATION_ACCEPT_URL=https://app.example.com/invitations)
  else
    own=(AGENT_INTERNAL_TOKEN=test-agent S3_ACCESS_KEY=test-access S3_SECRET_KEY=test-secret)
  fi
  env -i "${common[@]}" "${own[@]}" "$java_bin" -jar "$jar" >"$test_dir/$service-runtime.log" 2>&1 &
  runtime_pid=$!
  started=false
  for attempt in {1..60}; do
    if rg -q "Started $app" "$test_dir/$service-runtime.log"; then started=true; break; fi
    if ! kill -0 "$runtime_pid" 2>/dev/null; then break; fi
    sleep 1
  done
  if [[ "$started" != true ]]; then cat "$test_dir/$service-runtime.log"; exit 1; fi
  kill "$runtime_pid"; wait "$runtime_pid" 2>/dev/null || true; runtime_pid=""
  printf '[migration-test] %s 실제 migration 2회 + 자기 runtime 계정 Spring 기동 PASS\n' "$service"
done
cd "$repo/../AI/pipeline"
if env -i PATH="$PATH" "$python_bin" -m app.modules.wiki_ingestion.infrastructure.migrate_ai_schema >"$test_dir/ai-missing.log" 2>&1; then
  echo 'AI migration 필수 입력 누락이 성공으로 처리됨' >&2; exit 1
fi
rg -q '필수 migration 설정 누락: AI_DB_MIGRATION_URL' "$test_dir/ai-missing.log"
for repeat in 1 2; do
  env -i PATH="$PATH" AI_DB_MIGRATION_URL="postgresql://ai_migration:migration_test_password@127.0.0.1:$port/ai_db" \
    "$python_bin" -m app.modules.wiki_ingestion.infrastructure.migrate_ai_schema
done
env -i PATH="$PATH" AI_DATABASE_URL="postgresql://ai_runtime:runtime_test_password@127.0.0.1:$port/ai_db" \
  "$python_bin" -c 'from app.modules.wiki_ingestion.infrastructure.postgres_wiki_ingestion_repository import ensure_ai_schema, verify_agent_schema; ensure_ai_schema(); verify_agent_schema()'
docker exec "${env_args[@]}" "$container" bash /work/validate-db-isolation.sh
echo '[migration-test] AI 실제 migration 2회 + runtime Wiki/Agent/checkpoint 검증 + 전체 DB 권한 PASS'
