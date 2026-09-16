#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONVERTER_ENV_FILE="${CONVERTER_ENV_FILE:-$ROOT_DIR/infra/.env}"
COMPOSE_FILE="$ROOT_DIR/infra/compose.converter.yml"
PDF_FILE="${1:-}"
OUTPUT_FILE="${2:-}"
RESPONSE_FILE=""

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
if ! docker compose --env-file "$CONVERTER_ENV_FILE" -f "$COMPOSE_FILE" config --quiet >/dev/null 2>&1; then
  fail "환경변수 파일 또는 Compose 구성 해석에 실패했습니다."
fi
if ! docker compose --env-file "$CONVERTER_ENV_FILE" -f "$COMPOSE_FILE" config --format json 2>/dev/null |
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
cleanup_stale_converter

if [[ -z "$OUTPUT_FILE" ]]; then
  OUTPUT_FILE="$ROOT_DIR/.tmp/converter-e2e/$(basename "${PDF_FILE%.*}").md"
fi
SUMMARY_FILE="${OUTPUT_FILE%.md}.summary.json"
RESPONSE_FILE="$(mktemp "${TMPDIR:-/tmp}/converter-e2e.XXXXXX.json")"

if [[ "${CONVERTER_E2E_SKIP_START:-false}" != "true" ]]; then
  log "병합 코드로 converter 이미지를 빌드하고 시작합니다."
  docker compose --env-file "$CONVERTER_ENV_FILE" -f "$COMPOSE_FILE" \
    up -d --build markitdown
fi

for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8010/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS http://localhost:8010/health >/dev/null \
  || fail "converter health 응답을 확인하지 못했습니다."

log "Gemini로 PDF를 변환합니다: $PDF_FILE"
if ! curl --fail-with-body --silent --show-error --max-time 900 \
  -X POST http://localhost:8010/convert \
  -F "file=@${PDF_FILE};type=application/pdf" \
  -F 'provider=gemini' \
  -F 'model=gemini-3.1-flash-lite' \
  -o "$RESPONSE_FILE"; then
  sed -n '1,80p' "$RESPONSE_FILE" >&2
  fail "converter 요청이 실패했습니다."
fi

mkdir -p "$(dirname "$OUTPUT_FILE")"
python3 - "$RESPONSE_FILE" "$OUTPUT_FILE" "$SUMMARY_FILE" <<'PY'
import json
import sys
from pathlib import Path

response_file, output_file, summary_file = map(Path, sys.argv[1:])
payload = json.loads(response_file.read_text(encoding="utf-8"))
markdown = str(payload.get("markdown") or "")
process_log = str(payload.get("process_log") or "")
if not markdown.strip():
    raise SystemExit("converter가 빈 Markdown을 반환했습니다.")
if "자동 복원 실패" in markdown:
    raise SystemExit("최종 Markdown에 자동 복원 실패 marker가 남았습니다.")
if "Cannot find module './index.js'" in process_log:
    raise SystemExit("AnyDoc package-relative 실행 경로가 깨졌습니다.")

summary = payload.get("repair_summary") or {}
output_file.write_text(markdown, encoding="utf-8")
summary_file.write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"markdown_chars={len(markdown)}")
print(f"repair_calls={summary.get('calls', 0)}")
print(f"markdown={output_file}")
print(f"summary={summary_file}")
PY

log "E2E 변환을 완료했습니다. converter는 http://localhost:8010에서 계속 실행 중입니다."
