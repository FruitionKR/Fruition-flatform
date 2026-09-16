# 두 실행 스크립트가 공유하는 입력 검증. 검증을 마치기 전에는 DB를 변경하지 않는다.
fail() {
  printf '[db-isolation] ERROR: %s\n' "$*" >&2
  exit 1
}

validate_identifier() {
  [[ "$1" =~ ^[a-z_][a-z0-9_]*$ && ${#1} -le 63 ]] || fail "$2 값은 63자 이하 PostgreSQL 식별자여야 합니다."
  [[ "$1" != pg_* ]] || fail "$2 값에 예약 접두사 pg_를 사용할 수 없습니다."
}

DB_ISOLATION_TARGET="${DB_ISOLATION_TARGET:-all}"
case "$DB_ISOLATION_TARGET" in
  all) services=(ACCESS CORE AI) ;;
  access) services=(ACCESS) ;;
  core) services=(CORE AI) ;;
  *) fail "DB_ISOLATION_TARGET은 all/access/core 중 하나여야 합니다." ;;
esac

POSTGRES_ADMIN_USER="${POSTGRES_ADMIN_USER:-${POSTGRES_USER:-}}"
[[ -n "$POSTGRES_ADMIN_USER" ]] || fail "POSTGRES_ADMIN_USER(초기 컨테이너에서는 POSTGRES_USER)가 필요합니다."
export PGPASSWORD="${POSTGRES_ADMIN_PASSWORD:-${POSTGRES_PASSWORD:-${PGPASSWORD:-}}}"
export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-10}"
# PGHOST/PGPORT/PGSSLMODE/PGSSLROOTCERT/PGPASSFILE은 libpq가 그대로 사용한다.

seen_databases='|postgres|template0|template1|'
seen_roles="|$POSTGRES_ADMIN_USER|"
for service in "${services[@]}"; do
  for suffix in NAME RUNTIME_USER MIGRATION_USER RUNTIME_PASSWORD MIGRATION_PASSWORD; do
    variable_name="${service}_DB_${suffix}"
    value="${!variable_name:-}"
    [[ -n "$value" ]] || fail "$variable_name 값이 필요합니다."
    case "$suffix" in
      NAME)
        validate_identifier "$value" "$variable_name"
        [[ "$seen_databases" != *"|$value|"* ]] || fail "DB 이름은 중복되거나 관리 DB 이름일 수 없습니다."
        seen_databases+="$value|"
        ;;
      *_USER)
        validate_identifier "$value" "$variable_name"
        [[ "$seen_roles" != *"|$value|"* ]] || fail "서비스 role은 서로 다르고 관리자와 달라야 합니다."
        seen_roles+="$value|"
        ;;
    esac
  done
done

admin_psql() {
  psql -X --username "$POSTGRES_ADMIN_USER" --set=ON_ERROR_STOP=1 "$@"
}
