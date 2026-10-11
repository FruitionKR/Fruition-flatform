#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONVERTER_ENV_FILE="${CONVERTER_ENV_FILE:-$ROOT_DIR/infra/.env}"
COMPOSE_FILES=(
  -f "$ROOT_DIR/infra/compose.infra.yml"
  -f "$ROOT_DIR/infra/compose.ai.yml"
  -f "$ROOT_DIR/infra/compose.converter.yml"
)
PDF_FILE="${1:-}"
OUTPUT_FILE="${2:-}"
RESPONSE_FILE=""
# converter worker(fruition-markitdown)는 HTTP 포트가 없다. MinIO에 원본을 올리고 Kafka command를 발행한 뒤 결과 event를 기다린다.
CONVERTER_CONTAINER=fruition-markitdown
KAFKA_CONTAINER=fruition-kafka-dev
KAFKA_BOOTSTRAP=kafka:19092
KAFKA_BIN=/opt/kafka/bin
CONVERT_TOPIC="${CONVERT_COMMAND_TOPIC:-ai.convert.command}"
EVENT_TOPIC="${AI_TASK_EVENT_TOPIC:-ai.task.event}"
WAIT_SECONDS="${CONVERTER_E2E_WAIT_SECONDS:-900}"

log() {
  printf '[converter-e2e] %s\n' "$*"
}

fail() {
  printf '[converter-e2e] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$RESPONSE_FILE" ]]; then
    rm -f "$RESPONSE_FILE"
  fi
}

cleanup_stale_converter() {
  local status

  status="$(docker inspect -f '{{.State.Status}}' fruition-markitdown 2>/dev/null || true)"
  case "$status" in
    created|exited|dead)
      log "중지된 fruition-markitdown 컨테이너를 정리합니다."
      docker rm fruition-markitdown >/dev/null
      ;;
  esac
}

trap cleanup EXIT

[[ -n "$PDF_FILE" ]] || fail "사용법: scripts/converter-e2e.sh <PDF> [출력.md]"
[[ -f "$PDF_FILE" ]] || fail "PDF 파일을 찾을 수 없습니다: $PDF_FILE"
[[ -f "$CONVERTER_ENV_FILE" ]] || fail "환경변수 파일을 찾을 수 없습니다: $CONVERTER_ENV_FILE"
command -v docker >/dev/null 2>&1 || fail "docker 명령을 찾을 수 없습니다."
command -v curl >/dev/null 2>&1 || fail "curl 명령을 찾을 수 없습니다."
command -v python3 >/dev/null 2>&1 || fail "python3 명령을 찾을 수 없습니다."
if ! docker compose --env-file "$CONVERTER_ENV_FILE" "${COMPOSE_FILES[@]}" config --quiet >/dev/null 2>&1; then
  fail "환경변수 파일 또는 Compose 구성 해석에 실패했습니다."
fi
if ! docker compose --env-file "$CONVERTER_ENV_FILE" "${COMPOSE_FILES[@]}" config --format json 2>/dev/null |
  python3 -c '
import json
import sys

try:
    value = json.load(sys.stdin).get("services", {}).get("markitdown", {}).get("environment", {}).get("GEMINI_API_KEY")
except (json.JSONDecodeError, AttributeError, TypeError):
    raise SystemExit(1)

raise SystemExit(0 if isinstance(value, str) and value.strip() else 1)
'; then
  fail "markitdown service에 비어 있지 않은 GEMINI_API_KEY가 필요합니다."
fi
docker info >/dev/null 2>&1 || fail "Docker daemon에 연결할 수 없습니다."
for container in "$KAFKA_CONTAINER" fruition-minio-dev fruition-postgresql-dev; do
  [[ "$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || true)" == running ]] \
    || fail "$container 컨테이너가 실행 중이어야 합니다. 인프라(compose.infra.yml)를 먼저 시작하세요."
done
cleanup_stale_converter

if [[ -z "$OUTPUT_FILE" ]]; then
  OUTPUT_FILE="$ROOT_DIR/.tmp/converter-e2e/$(basename "${PDF_FILE%.*}").md"
fi
RESPONSE_FILE="$(mktemp "${TMPDIR:-/tmp}/converter-e2e.XXXXXX.json")"

if [[ "${CONVERTER_E2E_SKIP_START:-false}" != "true" ]]; then
  log "병합 코드로 converter worker 이미지를 빌드하고 시작합니다."
  docker compose --env-file "$CONVERTER_ENV_FILE" "${COMPOSE_FILES[@]}" \
    up -d --build --no-deps markitdown
fi

# worker가 consumer로 붙을 때까지 기다린다(기동 로그 확인).
for _ in $(seq 1 60); do
  if docker logs "$CONVERTER_CONTAINER" 2>&1 | grep -q "converter worker 기동"; then
    break
  fi
  sleep 1
done
docker logs "$CONVERTER_CONTAINER" 2>&1 | grep -q "converter worker 기동" \
  || fail "converter worker 기동 로그를 확인하지 못했습니다."

RUN_KEY="$(date +%Y%m%d%H%M%S)-$$"
WORKSPACE_ID="ws_converter_e2e"
USER_ID="converter-e2e-user"
DOCUMENT_ID="e2e-$RUN_KEY"
PARENT_RUN_ID="convert:$DOCUMENT_ID"
RUN_ID="$PARENT_RUN_ID:0"
SOURCE_KEY="sources/documents/$DOCUMENT_ID/original"

# converter 컨테이너의 S3 자격과 코드를 그대로 써서 MinIO에 원본을 올린다(stdin으로 PDF 전달).
log "원본 PDF를 MinIO에 올립니다: $SOURCE_KEY"
docker exec -i "$CONVERTER_CONTAINER" python -c '
import sys
from io import BytesIO
from app.modules.wiki_ingestion.infrastructure.object_storage import bucket_name, client

data = sys.stdin.buffer.read()
client().put_object(bucket_name(), sys.argv[1], BytesIO(data), length=len(data), content_type="application/pdf")
' "$SOURCE_KEY" <"$PDF_FILE" || fail "MinIO 업로드에 실패했습니다."

# ai docs/api/tasks.md "PDF 변환 command" 계약. Kafka key는 run_id다.
COMMAND="$(python3 - "$RUN_ID" "$PARENT_RUN_ID" "$WORKSPACE_ID" "$USER_ID" "$DOCUMENT_ID" "$SOURCE_KEY" <<'PY'
import json
import sys

run_id, parent_run_id, workspace_id, user_id, document_id, source_key = sys.argv[1:]
print(json.dumps({
    "run_id": run_id, "parent_run_id": parent_run_id, "kind": "convert_batch",
    "workspace_id": workspace_id, "user_id": user_id, "document_id": document_id,
    "source_key": source_key, "start_page": 0, "page_count": 10,
    "provider": "gemini", "model": "gemini-3.1-flash-lite",
}, ensure_ascii=False))
PY
)"
log "convert_batch command를 발행합니다: run_id=$RUN_ID"
printf '%s|%s\n' "$RUN_ID" "$COMMAND" | docker exec -i "$KAFKA_CONTAINER" \
  "$KAFKA_BIN/kafka-console-producer.sh" --bootstrap-server "$KAFKA_BOOTSTRAP" --topic "$CONVERT_TOPIC" \
  --property parse.key=true --property key.separator='|' >/dev/null \
  || fail "command 발행에 실패했습니다."

# 같은 run_id의 결과 event가 올 때까지 ai.task.event를 처음부터 반복해서 읽는다.
log "결과 event를 기다립니다(최대 ${WAIT_SECONDS}초)."
deadline=$((SECONDS + WAIT_SECONDS))
: >"$RESPONSE_FILE"
while (( SECONDS < deadline )); do
  docker exec "$KAFKA_CONTAINER" "$KAFKA_BIN/kafka-console-consumer.sh" \
    --bootstrap-server "$KAFKA_BOOTSTRAP" --topic "$EVENT_TOPIC" --from-beginning --timeout-ms 5000 2>/dev/null |
    grep -F "\"$RUN_ID\"" >"$RESPONSE_FILE" || true
  [[ -s "$RESPONSE_FILE" ]] && break
  sleep 3
done
[[ -s "$RESPONSE_FILE" ]] || fail "결과 event를 받지 못했습니다: run_id=$RUN_ID"

RESULT_KEY="$(python3 - "$RESPONSE_FILE" "$RUN_ID" <<'PY'
import json
import sys

event = None
for line in open(sys.argv[1], encoding="utf-8"):
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        continue
    if value.get("run_id") == sys.argv[2]:
        event = value
if event is None:
    raise SystemExit("run_id가 일치하는 event가 없습니다.")
if event.get("status") != "succeeded":
    raise SystemExit(f"변환이 실패했습니다: status={event.get('status')} error={event.get('error')}")
print((event.get("payload") or {}).get("result_key") or "")
PY
)" || fail "결과 event 검증에 실패했습니다."
[[ "$RESULT_KEY" == "tmp/convert/$WORKSPACE_ID/$DOCUMENT_ID/0.md" ]] || fail "예상과 다른 result_key입니다: $RESULT_KEY"

mkdir -p "$(dirname "$OUTPUT_FILE")"
docker exec "$CONVERTER_CONTAINER" python -c '
import sys
from app.modules.wiki_ingestion.infrastructure.object_storage import bucket_name, client

response = client().get_object(bucket_name(), sys.argv[1])
try:
    sys.stdout.buffer.write(response.read())
finally:
    response.close()
    response.release_conn()
' "$RESULT_KEY" >"$OUTPUT_FILE" || fail "MinIO에서 result_key를 읽지 못했습니다: $RESULT_KEY"

[[ -s "$OUTPUT_FILE" ]] || fail "converter가 빈 Markdown을 반환했습니다."
if grep -q "자동 복원 실패" "$OUTPUT_FILE"; then
  fail "최종 Markdown에 자동 복원 실패 marker가 남았습니다."
fi

log "markdown_chars=$(wc -m <"$OUTPUT_FILE" | tr -d ' ')"
log "markdown=$OUTPUT_FILE"
log "E2E 변환을 완료했습니다. converter worker는 계속 실행 중입니다."
