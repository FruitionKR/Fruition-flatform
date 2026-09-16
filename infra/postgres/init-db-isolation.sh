#!/usr/bin/env bash
set -Eeuo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/db-isolation-config.bash"

create_role() {
  local role="$1"
  local password="$2"

  admin_psql --dbname postgres --set=ON_ERROR_STOP=1 \
    --set=role="$role" --set=password="$password" <<'SQL'
-- PostgreSQL 16의 CREATEROLE 관리자는 생성 role의 소유권 작업을 위해 SET/INHERIT가 필요하다.
SET createrole_self_grant = 'inherit,set';
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L', :'role', :'password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role')
\gexec
SELECT format('ALTER ROLE %I WITH LOGIN NOCREATEDB NOCREATEROLE PASSWORD %L', :'role', :'password')
\gexec
SQL
}

create_database() {
  local database="$1"
  local migration_role="$2"
  local runtime_role="$3"

  admin_psql --dbname postgres --set=ON_ERROR_STOP=1 \
    --set=database="$database" --set=migration_role="$migration_role" --set=runtime_role="$runtime_role" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'database', :'migration_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database')
\gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'database', :'migration_role')
\gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'database')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database', :'migration_role')
\gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM %I', :'database', :'runtime_role')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database', :'runtime_role')
\gexec
SQL

  admin_psql --dbname "$database" --set=ON_ERROR_STOP=1 \
    --set=migration_role="$migration_role" --set=runtime_role="$runtime_role" <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SELECT format('ALTER SCHEMA public OWNER TO %I', :'migration_role')
\gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA public TO %I', :'migration_role')
\gexec
SELECT format('REVOKE ALL ON SCHEMA public FROM %I', :'runtime_role')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'runtime_role')
\gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'runtime_role')
\gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO %I', :'runtime_role')
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'migration_role', :'runtime_role')
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I', :'migration_role', :'runtime_role')
\gexec
SQL
}

# 상속 권한은 직접 GRANT 회수로 제거되지 않는다. 기존 membership은 변경 전에 거부한다.
for service in "${services[@]}"; do
  for kind in RUNTIME MIGRATION; do
    role_variable="${service}_DB_${kind}_USER"
    membership="$(admin_psql --dbname postgres --tuples-only --no-align --set=role="${!role_variable}" <<'SQL'
SELECT EXISTS (SELECT 1 FROM pg_roles r WHERE r.rolname = :'role' AND (r.rolsuper OR r.rolreplication OR r.rolbypassrls OR EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = r.oid)));
SQL
)"
    [[ "$membership" == f ]] || fail "${!role_variable}의 기존 관리자 권한 또는 role membership을 먼저 해소해야 합니다."
  done
done

for service in "${services[@]}"; do
  for kind in RUNTIME MIGRATION; do
    role_variable="${service}_DB_${kind}_USER"
    password_variable="${service}_DB_${kind}_PASSWORD"
    create_role "${!role_variable}" "${!password_variable}"
  done
done

for service in "${services[@]}"; do
  database_variable="${service}_DB_NAME"
  migration_variable="${service}_DB_MIGRATION_USER"
  runtime_variable="${service}_DB_RUNTIME_USER"
  create_database "${!database_variable}" "${!migration_variable}" "${!runtime_variable}"
  # 이전에 부여한 교차 접근도 선택한 서비스 경계 안에서 회수한다.
  for other in "${services[@]}"; do
    [[ "$other" != "$service" ]] || continue
    for kind in RUNTIME MIGRATION; do
      role_variable="${other}_DB_${kind}_USER"
      admin_psql --dbname postgres --set=database="${!database_variable}" --set=role="${!role_variable}" <<'SQL'
SELECT format('REVOKE ALL ON DATABASE %I FROM %I', :'database', :'role')
\gexec
SQL
      admin_psql --dbname "${!database_variable}" --set=migration_role="${!migration_variable}" --set=role="${!role_variable}" <<'SQL'
SELECT format('REVOKE ALL ON SCHEMA public FROM %I', :'role')
\gexec
SELECT format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', :'role')
\gexec
SELECT format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', :'role')
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON TABLES FROM %I', :'migration_role', :'role')
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', :'migration_role', :'role')
\gexec
SQL
    done
  done
done

printf '[db-init] %s 대상 DB와 runtime/migration 계정 구성을 완료했습니다.\n' "$DB_ISOLATION_TARGET"
