#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${1:-}"
if [[ -n "$CONFIG_FILE" ]]; then
  [[ -f "$CONFIG_FILE" ]] || { printf '[mcp-test-up] config not found: %s\n' "$CONFIG_FILE" >&2; exit 1; }
  set -a
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
  set +a
fi

PROJECT="${MCP_TEST_PROJECT:-fruition-mcp-test}"
RUNTIME_DIR="${MCP_TEST_RUNTIME_DIR:-/tmp/fruition-mcp-test}"
ENV_FILE="$RUNTIME_DIR/.env"
ORIGIN="${MCP_TEST_ORIGIN:-https://localhost:58443}"
ACCESS_REPO="${MCP_TEST_ACCESS_DIR:-$ROOT_DIR/../Fruition-access}"
DOCUMENT_REPO="${MCP_TEST_DOCUMENT_DIR:-$ROOT_DIR/../Fruition-document}"
AI_PIPELINE_DIR="${MCP_TEST_AI_PIPELINE_DIR:-$ROOT_DIR/../Fruition-ai/pipeline}"
FRONTEND_DIR="${MCP_TEST_FRONTEND_DIR:-$ROOT_DIR/../Fruition-frontend/web}"
GRADLE_CACHE_SEED="${MCP_TEST_GRADLE_CACHE_SEED:-/tmp/fruition-mcp-supervision/i1-i3-local-auth-read-integration-gradle-home}"
COMPOSE=(docker compose --env-file "$ENV_FILE" -p "$PROJECT"
  -f "$ROOT_DIR/infra/compose.infra.yml"
  -f "$ROOT_DIR/infra/compose.ai.yml"
  -f "$ROOT_DIR/infra/compose.containerized.yml"
  -f "$ROOT_DIR/infra/compose.mcp-test.yml")

log() { printf '[mcp-test-up] %s\n' "$*"; }
fail() { printf '[mcp-test-up] ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "required cached tool is unavailable: $1"; }
secret_hex() { openssl rand -hex "$1"; }
pem_one_line() {
  awk 'NR == 1 { head=$0; next } /^-----END/ { tail=$0; next } { body=body $0 } END { print head body tail }' "$1"
}

for tool in docker openssl python3 awk sed cp find node rsync; do need "$tool"; done
docker info >/dev/null 2>&1 || fail "Docker is not available"
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || fail "invalid MCP_TEST_PROJECT"
for directory in "$ACCESS_REPO" "$DOCUMENT_REPO" "$AI_PIPELINE_DIR" "$FRONTEND_DIR"; do
  [[ -d "$directory" ]] || fail "required checkout is absent: $directory"
done
docker image inspect gradle:8.14-jdk21 >/dev/null 2>&1 || fail "cached gradle:8.14-jdk21 image is absent"
docker image inspect fruition-pipeline-dev:local >/dev/null 2>&1 || fail "cached fruition-pipeline-dev:local image is absent"
docker image inspect python:3.12-slim-trixie >/dev/null 2>&1 || fail "cached python:3.12-slim-trixie image is absent"
docker image inspect fruition-mvp-dev-access-svc:latest >/dev/null 2>&1 || fail "cached access runtime image is absent"
docker image inspect fruition-mvp-dev-document-svc:latest >/dev/null 2>&1 || fail "cached document runtime image is absent"
[[ -d "$GRADLE_CACHE_SEED/caches" ]] || fail "cached Gradle dependencies are absent: $GRADLE_CACHE_SEED"

install -d -m 700 "$RUNTIME_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  python3 - "$ORIGIN" "${MCP_TEST_REAL_CLIENT_ID:-}" <<'PY'
import sys
from urllib.parse import urlsplit

origin = urlsplit(sys.argv[1])
if origin.scheme != "https" or not origin.hostname or origin.username or origin.password or origin.path not in ("", "/") or origin.query or origin.fragment:
    raise SystemExit("MCP_TEST_ORIGIN must be a canonical HTTPS origin")
if sys.argv[2]:
    client = urlsplit(sys.argv[2])
    if client.scheme != "https" or not client.hostname or client.username or client.password or client.path in ("", "/") or client.fragment:
        raise SystemExit("MCP_TEST_REAL_CLIENT_ID must be an exact HTTPS CIMD URL")
PY

  log "generating task-local RSA/TLS keys and service credentials"
  umask 077
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$RUNTIME_DIR/jwt-private.pem" >/dev/null 2>&1
  openssl pkey -in "$RUNTIME_DIR/jwt-private.pem" -pubout -out "$RUNTIME_DIR/jwt-public.pem" >/dev/null 2>&1
  openssl req -x509 -newkey rsa:2048 -nodes -days 14 -sha256 \
    -subj '/CN=Fruition MCP isolated test CA' \
    -keyout "$RUNTIME_DIR/tls-ca.key" -out "$RUNTIME_DIR/tls-ca.crt" >/dev/null 2>&1
  openssl req -newkey rsa:2048 -nodes -sha256 -subj '/CN=mcp-test-gateway' \
    -addext 'subjectAltName=DNS:mcp-test-gateway,DNS:localhost,IP:127.0.0.1' \
    -keyout "$RUNTIME_DIR/tls.key" -out "$RUNTIME_DIR/tls.csr" >/dev/null 2>&1
  openssl x509 -req -days 14 -sha256 -copy_extensions copy \
    -in "$RUNTIME_DIR/tls.csr" -CA "$RUNTIME_DIR/tls-ca.crt" -CAkey "$RUNTIME_DIR/tls-ca.key" \
    -CAcreateserial -out "$RUNTIME_DIR/tls.crt" >/dev/null 2>&1

  truststore_password="$(secret_hex 24)"
  docker run --rm --user "$(id -u):$(id -g)" -v "$RUNTIME_DIR:/runtime" gradle:8.14-jdk21 \
    keytool -importcert -noprompt -alias mcp-test-ca -file /runtime/tls-ca.crt \
    -keystore /runtime/truststore.p12 -storetype PKCS12 -storepass "$truststore_password" >/dev/null

  postgres_password="$(secret_hex 24)"
  access_runtime_password="$(secret_hex 24)"
  access_migration_password="$(secret_hex 24)"
  core_runtime_password="$(secret_hex 24)"
  core_migration_password="$(secret_hex 24)"
  ai_runtime_password="$(secret_hex 24)"
  ai_migration_password="$(secret_hex 24)"
  ai_converter_password="$(secret_hex 24)"
  s3_access_key="mcp$(secret_hex 8)"
  s3_secret_key="$(secret_hex 24)"
  mfa_key="$(openssl rand -base64 32 | tr -d '\n')"
  internal_token="$(secret_hex 32)"
  agent_token="$(secret_hex 32)"
  document_cursor="$(secret_hex 32)"
  ai_cursor="$(secret_hex 32)"
  public_key="$(pem_one_line "$RUNTIME_DIR/jwt-public.pem")"
  private_key="$(pem_one_line "$RUNTIME_DIR/jwt-private.pem")"
  origin="${ORIGIN%/}"

  cat >"$ENV_FILE" <<EOF
MCP_TEST_PROJECT=$PROJECT
MCP_TEST_RUNTIME_DIR=$RUNTIME_DIR
MCP_TEST_ROOT_DIR=$ROOT_DIR
MCP_TEST_ACCESS_DIR=$ACCESS_REPO
MCP_TEST_DOCUMENT_DIR=$DOCUMENT_REPO
MCP_TEST_AI_PIPELINE_DIR=$AI_PIPELINE_DIR
MCP_TEST_FRONTEND_DIR=$FRONTEND_DIR
MCP_TEST_FRONTEND_DEPENDENCIES_DIR=${MCP_TEST_FRONTEND_DEPENDENCIES_DIR:-/tmp/fruition-mcp-supervision/upstream-integration/frontend-candidate/web/node_modules}
MCP_TEST_ORIGIN=$origin
MCP_TEST_RESOURCE_URI=$origin/mcp
MCP_TEST_CLIENT_ID=$origin/client-metadata
MCP_TEST_CLIENT_REDIRECT_URI=${MCP_TEST_CLIENT_REDIRECT_URI:-http://127.0.0.1/callback}
MCP_TEST_REAL_CLIENT_ID=${MCP_TEST_REAL_CLIENT_ID:-}
MCP_TEST_JWT_KEY_ID=mcp-test-1
MCP_TEST_JWT_PUBLIC_KEY='$public_key'
MCP_TEST_JWT_PRIVATE_KEY='$private_key'
MCP_TEST_TRUSTSTORE_PASSWORD=$truststore_password
MCP_TEST_DOCUMENT_CURSOR_SECRET=$document_cursor
MCP_TEST_AI_CURSOR_SECRET=$ai_cursor
MCP_TEST_POSTGRES_PORT=${MCP_TEST_POSTGRES_PORT:-55490}
MCP_TEST_REDIS_PORT=${MCP_TEST_REDIS_PORT:-56380}
MCP_TEST_KAFKA_PORT=${MCP_TEST_KAFKA_PORT:-59092}
MCP_TEST_MINIO_PORT=${MCP_TEST_MINIO_PORT:-59050}
MCP_TEST_MINIO_CONSOLE_PORT=${MCP_TEST_MINIO_CONSOLE_PORT:-59051}
MCP_TEST_PIPELINE_PORT=${MCP_TEST_PIPELINE_PORT:-58000}
MCP_TEST_DOCUMENT_PORT=${MCP_TEST_DOCUMENT_PORT:-58080}
MCP_TEST_ACCESS_PORT=${MCP_TEST_ACCESS_PORT:-58081}
MCP_TEST_FRONTEND_PORT=${MCP_TEST_FRONTEND_PORT:-58300}
MCP_TEST_GATEWAY_HTTP_PORT=${MCP_TEST_GATEWAY_HTTP_PORT:-58480}
MCP_TEST_GATEWAY_HTTPS_PORT=${MCP_TEST_GATEWAY_HTTPS_PORT:-58443}
POSTGRES_PORT=${MCP_TEST_POSTGRES_PORT:-55490}
REDIS_PORT=${MCP_TEST_REDIS_PORT:-56380}
KAFKA_PORT=${MCP_TEST_KAFKA_PORT:-59092}
PIPELINE_API_PORT=${MCP_TEST_PIPELINE_PORT:-58000}
BACKEND_PORT=${MCP_TEST_DOCUMENT_PORT:-58080}
ACCESS_PORT=${MCP_TEST_ACCESS_PORT:-58081}
POSTGRES_ADMIN_USER=fruition_admin
POSTGRES_ADMIN_PASSWORD=$postgres_password
ACCESS_DB_NAME=access_db
ACCESS_DB_RUNTIME_USER=access_runtime
ACCESS_DB_RUNTIME_PASSWORD=$access_runtime_password
ACCESS_DB_MIGRATION_USER=access_migration
ACCESS_DB_MIGRATION_PASSWORD=$access_migration_password
CORE_DB_NAME=core_db
CORE_DB_RUNTIME_USER=core_runtime
CORE_DB_RUNTIME_PASSWORD=$core_runtime_password
CORE_DB_MIGRATION_USER=core_migration
CORE_DB_MIGRATION_PASSWORD=$core_migration_password
AI_DB_NAME=ai_db
AI_DB_RUNTIME_USER=ai_runtime
AI_DB_RUNTIME_PASSWORD=$ai_runtime_password
AI_DB_MIGRATION_USER=ai_migration
AI_DB_MIGRATION_PASSWORD=$ai_migration_password
AI_DB_CONVERTER_USER=ai_converter
AI_DB_CONVERTER_PASSWORD=$ai_converter_password
S3_BUCKET=fruition-mcp-test
S3_ACCESS_KEY=$s3_access_key
S3_SECRET_KEY=$s3_secret_key
MFA_ENCRYPTION_KEY=$mfa_key
INTERNAL_CALLBACK_TOKEN=$internal_token
AGENT_INTERNAL_TOKEN=$agent_token
RESTORE_PREVIEW_TOKEN_SECRET=$(secret_hex 32)
LEGAL_CONSENT_REQUIRED=false
LOCAL_ANALYTICS_ENABLED=false
OPENAI_API_KEY=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
TAVILY_API_KEY=
TYPESAFE_API_KEY=
EOF
  chmod 600 "$ENV_FILE" "$RUNTIME_DIR"/*.pem "$RUNTIME_DIR"/*.key "$RUNTIME_DIR/truststore.p12"
else
  log "reusing existing private environment: $ENV_FILE"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ ! -d "$RUNTIME_DIR/gradle-home/caches" ]]; then
  log "copying the existing cached Gradle home into task-local storage"
  install -d -m 700 "$RUNTIME_DIR/gradle-home"
  cp -R "$GRADLE_CACHE_SEED/." "$RUNTIME_DIR/gradle-home/"
fi

cat >"$RUNTIME_DIR/isolation.init.gradle" <<'EOF'
allprojects {
    layout.buildDirectory.set(file(System.getenv("MCP_TEST_BUILD_DIR") + "/" + project.name))
    configurations.configureEach {
        exclude group: "org.springframework.boot", module: "spring-boot-devtools"
    }
}
EOF
chmod 600 "$RUNTIME_DIR/isolation.init.gradle"

build_java_image() {
  local name="$1" repo="$2" base_image="$3" target_image="$4"
  local build_dir="$RUNTIME_DIR/build/$name"
  install -d -m 700 "$build_dir" "$RUNTIME_DIR/project-cache/$name"
  log "compiling current $name checkout with cached dependencies only"
  docker run --rm --user "$(id -u):$(id -g)" \
    -e GRADLE_USER_HOME=/gradle-home -e MCP_TEST_BUILD_DIR="/runtime/build/$name" \
    -v "$repo:/work:ro" -v "$RUNTIME_DIR:/runtime" -v "$RUNTIME_DIR/gradle-home:/gradle-home" \
    gradle:8.14-jdk21 gradle -p /work --offline --no-daemon \
    --project-cache-dir "/runtime/project-cache/$name" -I /runtime/isolation.init.gradle bootJar -x test
  local jar
  jar="$(find "$build_dir" -type f -path '*/libs/*.jar' ! -name '*-plain.jar' -print -quit)"
  [[ -n "$jar" ]] || fail "$name boot jar was not produced"
  install -d -m 700 "$RUNTIME_DIR/image-context/$name"
  cp "$jar" "$RUNTIME_DIR/image-context/$name/app.jar"
  docker build --pull=false --network=none --build-arg "BASE_IMAGE=$base_image" \
    -f "$ROOT_DIR/infra/mcp-test-java.Dockerfile" -t "$target_image" "$RUNTIME_DIR/image-context/$name"
}

build_java_image access "$ACCESS_REPO" fruition-mvp-dev-access-svc:latest fruition-mcp-test-access:local
build_java_image document "$DOCUMENT_REPO" fruition-mvp-dev-document-svc:latest fruition-mcp-test-document:local

log "starting isolated infrastructure, current AI source, and Java services"
"${COMPOSE[@]}" up -d --no-build postgresql redis kafka kafka-init minio minio-init \
  pipeline-api document-svc access-svc

wait_url() {
  local url="$1" label="$2"
  for _ in $(seq 1 180); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then return; fi
    sleep 1
  done
  fail "$label did not become ready: $url"
}
wait_url "http://127.0.0.1:$MCP_TEST_PIPELINE_PORT/health" pipeline-api
wait_url "http://127.0.0.1:$MCP_TEST_ACCESS_PORT/.well-known/oauth-authorization-server" access-svc

log "starting the task-local frontend with the validated cached runtime"
MCP_TEST_RUNTIME_DIR="$RUNTIME_DIR" "$ROOT_DIR/scripts/mcp-test-frontend.sh" start

log "starting same-origin local TLS gateway"
"${COMPOSE[@]}" up -d --no-build mcp-test-gateway
for _ in $(seq 1 60); do
  if curl -fsS --cacert "$RUNTIME_DIR/tls-ca.crt" \
      -H "Host: ${MCP_TEST_ORIGIN#https://}" \
      "https://localhost:$MCP_TEST_GATEWAY_HTTPS_PORT/.well-known/oauth-protected-resource/mcp" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

terms_version="$(sed -n 's/^app\.legal\.terms-version=${LEGAL_TERMS_VERSION:\([^}]*\)}.*/\1/p' "$ACCESS_REPO/src/main/resources/application.properties")"
[[ -n "$terms_version" ]] || fail "could not resolve the current terms version"
python3 "$ROOT_DIR/scripts/mcp-test-seed.py" \
  --runtime-dir "$RUNTIME_DIR" \
  --access-url "http://127.0.0.1:$MCP_TEST_ACCESS_PORT" \
  --document-url "http://127.0.0.1:$MCP_TEST_DOCUMENT_PORT" \
  --gateway-url "https://localhost:$MCP_TEST_GATEWAY_HTTPS_PORT" \
  --origin "$MCP_TEST_ORIGIN" --resource "$MCP_TEST_RESOURCE_URI" \
  --client-id "$MCP_TEST_CLIENT_ID" --real-client-id "${MCP_TEST_REAL_CLIENT_ID:-}" \
  --access-container fruition-mcp-test-access \
  --postgres-container fruition-mcp-test-postgresql \
  --terms-version "$terms_version"

"${COMPOSE[@]}" ps
log "ready: $MCP_TEST_ORIGIN (local CA: $RUNTIME_DIR/tls-ca.crt)"
log "MCP resource: $MCP_TEST_RESOURCE_URI"
log "credentials: $RUNTIME_DIR/credentials.json (mode 600; path only, do not share)"
