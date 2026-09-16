#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/db-isolation-config.bash"

psql_as() {
  local password="$1" user="$2" database="$3"
  shift 3
  PGPASSWORD="$password" psql -X --username "$user" --dbname "$database" --set=ON_ERROR_STOP=1 "$@"
}

# 기존 테이블을 덮어쓰지 않으며, 생성에 성공한 probe만 정리한다.
probe="__db_isolation_$$_${RANDOM}"
created=()
cleanup() {
  for service in "${created[@]}"; do
    local db="${service}_DB_NAME" user="${service}_DB_MIGRATION_USER" password="${service}_DB_MIGRATION_PASSWORD"
    psql_as "${!password}" "${!user}" "${!db}" --command="DROP TABLE public.$probe;" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT

for service in "${services[@]}"; do
  db="${service}_DB_NAME"
  migration="${service}_DB_MIGRATION_USER"
  migration_password="${service}_DB_MIGRATION_PASSWORD"
  runtime="${service}_DB_RUNTIME_USER"
  runtime_password="${service}_DB_RUNTIME_PASSWORD"
  for kind in RUNTIME MIGRATION; do
    role="${service}_DB_${kind}_USER"
    flags="$(admin_psql --dbname postgres --tuples-only --no-align --command="SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member = r.oid) FROM pg_roles r WHERE rolname = '${!role}'")"
    [[ "$flags" == f ]] || fail "${!role} 계정의 관리자 권한 또는 role membership이 발견됐습니다."
  done
  psql_as "${!migration_password}" "${!migration}" "${!db}" --command="CREATE TABLE public.$probe (id serial PRIMARY KEY, value text NOT NULL);" >/dev/null
  created+=("$service")
  psql_as "${!runtime_password}" "${!runtime}" "${!db}" --command="BEGIN; INSERT INTO public.$probe (value) VALUES ('probe'); SELECT * FROM public.$probe; UPDATE public.$probe SET value = 'verified'; DELETE FROM public.$probe; ROLLBACK;" >/dev/null || fail "${!runtime}의 자기 DB DML이 실패했습니다."
  if psql_as "${!runtime_password}" "${!runtime}" "${!db}" --command="BEGIN; CREATE TABLE public.${probe}_ddl (id integer); ROLLBACK;" >/dev/null 2>&1; then
    fail "${!runtime}이 public schema에서 CREATE를 수행했습니다."
  fi
  public_create="$(admin_psql --dbname "${!db}" --tuples-only --no-align --command="SELECT EXISTS (SELECT 1 FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) acl WHERE n.nspname = 'public' AND acl.grantee = 0 AND acl.privilege_type = 'CREATE')")"
  [[ "$public_create" == f ]] || fail "${!db} public schema에 PUBLIC CREATE 권한이 있습니다."
done

for service in "${services[@]}"; do
  for kind in RUNTIME MIGRATION; do
    role="${service}_DB_${kind}_USER"
    password="${service}_DB_${kind}_PASSWORD"
    for other in "${services[@]}"; do
      [[ "$other" != "$service" ]] || continue
      db="${other}_DB_NAME"
      connected="$(admin_psql --dbname postgres --tuples-only --no-align --command="SELECT has_database_privilege('${!role}', '${!db}', 'CONNECT')")"
      [[ "$connected" == f ]] || fail "${!role}에 ${!db} CONNECT 권한이 있습니다."
      for sql in 'SELECT 1' "SELECT * FROM public.$probe" "BEGIN; INSERT INTO public.$probe (value) VALUES ('cross'); ROLLBACK;"; do
        if psql_as "${!password}" "${!role}" "${!db}" --command="$sql" >/dev/null 2>&1; then
          fail "${!role}의 ${!db} 교차 접근이 허용됐습니다."
        fi
      done
    done
  done
done
printf '[db-isolation] %s: 계정 제한, 자기 DB DML·sequence, runtime DDL 거부, 선택 DB 간 CONNECT/read/write 거부 확인\n' "$DB_ISOLATION_TARGET"
