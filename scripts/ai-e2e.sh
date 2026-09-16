#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${AI_E2E_ENV_FILE:-$ROOT_DIR/infra/.env}"
PDF_FILE="${1:-}"
RUN_KEY="$(date +%Y%m%d%H%M%S)-$$"
OUTPUT_DIR="${AI_E2E_OUTPUT_DIR:-$ROOT_DIR/.tmp/ai-e2e/$RUN_KEY}"
CONVERTER_OUTPUT="$OUTPUT_DIR/converter.md"
PROMOTION_OUTPUT="$OUTPUT_DIR/promotion.md"
FIXTURE_DIR="$ROOT_DIR/../AI/pipeline/examples/ai-e2e"
COMPOSE_FILES=(
  -f "$ROOT_DIR/infra/compose.infra.yml"
  -f "$ROOT_DIR/infra/compose.ai.yml"
  -f "$ROOT_DIR/infra/compose.converter.yml"
  -f "$ROOT_DIR/infra/compose.containerized.yml"
)
COMPOSE=(
  docker compose --env-file "$ENV_FILE"
  -p fruition-ai-e2e
  "${COMPOSE_FILES[@]}"
)
RUNNING_CONTAINERS=(
  fruition-postgresql-dev
  fruition-kafka-dev
  fruition-redis-dev
  fruition-minio-dev
  fruition-document-svc-dev
  fruition-access-svc-dev
  fruition-pipeline-api-dev
  fruition-markitdown
  fruition-ingest-worker-dev
  fruition-query-task-worker-dev
  fruition-agent-task-worker-dev
  fruition-maintenance-task-worker-dev
  fruition-edit-event-consumer-dev
  fruition-pipeline-agent-worker-dev
)

log() {
  printf '[ai-e2e] %s\n' "$*"
}

fail() {
  printf '[ai-e2e] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -n "$PDF_FILE" ]] || fail "사용법: scripts/ai-e2e.sh <PDF>"
[[ -f "$PDF_FILE" ]] || fail "PDF 파일을 찾을 수 없습니다: $PDF_FILE"
[[ -f "$ENV_FILE" ]] || fail "환경변수 파일을 찾을 수 없습니다: $ENV_FILE"
grep -Eq '^GEMINI_API_KEY=.+$' "$ENV_FILE" || fail "GEMINI_API_KEY가 필요합니다."
command -v docker >/dev/null 2>&1 || fail "docker 명령을 찾을 수 없습니다."
command -v curl >/dev/null 2>&1 || fail "curl 명령을 찾을 수 없습니다."
command -v python3 >/dev/null 2>&1 || fail "python3 명령을 찾을 수 없습니다."
docker info >/dev/null 2>&1 || fail "Docker daemon에 연결할 수 없습니다."

mkdir -p "$OUTPUT_DIR"
trap 'set +e; "${COMPOSE[@]}" ps --format json >"$OUTPUT_DIR/compose-ps.json"' EXIT

# 격리된 로컬 E2E에서는 공유 env의 오래된 약한 JWT key를 사용하지 않는다.
export JWT_SECRET="${AI_E2E_JWT_SECRET:-fruition-ai-e2e-jwt-secret-32-bytes-minimum}"

# 고정 container_name 충돌만 해소하고 기존 개발 데이터 볼륨은 보존한다.
docker compose --env-file "$ENV_FILE" \
  -f "$ROOT_DIR/infra/compose.converter.yml" down >/dev/null 2>&1 || true
docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" down >/dev/null 2>&1 || true

log "격리된 E2E 볼륨으로 인프라·백엔드·AI·converter 전체 스택을 시작합니다."
"${COMPOSE[@]}" up -d --build

for _ in $(seq 1 180); do
  pending=""
  for container in "${RUNNING_CONTAINERS[@]}"; do
    state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
    if [[ "$state" != "healthy" && "$state" != "running" ]]; then
      pending="$pending $container($state)"
    fi
  done
  [[ -z "$pending" ]] && break
  sleep 5
done
[[ -z "$pending" ]] || fail "컨테이너 준비 시간 초과:$pending"
curl -fsS http://localhost:8000/health >/dev/null || fail "pipeline-api health 실패"
curl -fsS http://localhost:8010/health >/dev/null || fail "converter health 실패"

log "실제 PDF converter 요청을 실행합니다."
CONVERTER_ENV_FILE="$ENV_FILE" CONVERTER_E2E_SKIP_START=true \
  "$ROOT_DIR/scripts/converter-e2e.sh" "$PDF_FILE" "$CONVERTER_OUTPUT"

log "공개 API로 ingest·query·agent·lint 작업을 실행합니다."
python3 - "$OUTPUT_DIR" "$RUN_KEY" "$FIXTURE_DIR" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


output_dir = Path(sys.argv[1])
run_key = sys.argv[2]
fixture_dir = Path(sys.argv[3])
access_base = "http://localhost:8081"
document_base = "http://localhost:8080"


def request(method, url, payload=None, token=None, headers=None, expected=(200,)):
    body = None if payload is None else json.dumps(payload).encode()
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read().decode()
            if response.status not in expected:
                raise RuntimeError(f"{method} {url}: HTTP {response.status}: {raw}")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url}: HTTP {exc.code}: {detail}") from exc


def wait_status(label, fetch, terminal, timeout):
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        try:
            last = fetch()
        except RuntimeError as exc:
            if "HTTP 404:" in str(exc):
                time.sleep(2)
                continue
            raise
        status = str(last.get("status") or "")
        if status in terminal:
            if status not in {"completed", "succeeded"}:
                raise RuntimeError(f"{label} 실패: {json.dumps(last, ensure_ascii=False)}")
            print(f"{label}={status}", flush=True)
            return last
        time.sleep(2)
    raise TimeoutError(f"{label} 제한 시간 초과: {json.dumps(last, ensure_ascii=False)}")


email = f"ai-e2e-{run_key}@example.com"
password = "ai-e2e-password"
verification = request(
    "POST",
    f"{access_base}/api/auth/email-verifications",
    {"email": email, "purpose": "signup"},
    expected=(202,),
)
confirmed = request(
    "POST",
    f"{access_base}/api/auth/email-verifications/{verification['verification_id']}/confirm",
    {"code": "9700"},
)
request(
    "POST",
    f"{access_base}/api/auth/signup",
    {
        "email": email,
        "password": password,
        "display_name": "AI E2E",
        "verification_token": confirmed["verification_token"],
    },
    expected=(201,),
)
login = request(
    "POST",
    f"{access_base}/api/auth/login",
    {"email": email, "password": password},
)
token = login["access_token"]
workspace = request(
    "POST",
    f"{access_base}/api/workspaces",
    {"name": f"AI E2E {run_key}"},
    token,
    expected=(201,),
)
workspace_id = workspace["id"]
fixtures = []
for fixture_path in sorted(fixture_dir.glob("*.md")):
    markdown = fixture_path.read_text(encoding="utf-8")
    title = next(
        (line[2:].strip() for line in markdown.splitlines() if line.startswith("# ")),
        fixture_path.stem,
    )
    fixtures.append((title, markdown))
if len(fixtures) != 10:
    raise RuntimeError(f"스마트팜 Markdown fixture 10개가 필요합니다: {fixture_dir}")
document_ids = []
ingest_run_ids = []
for index, (display_name, markdown) in enumerate(fixtures, start=1):
    token = request(
        "POST",
        f"{access_base}/api/auth/login",
        {"email": email, "password": password},
    )["access_token"]
    document = request(
        "POST",
        f"{document_base}/api/workspaces/{workspace_id}/documents/markdown",
        {"display_name": display_name, "markdown": markdown},
        token,
        {"Idempotency-Key": f"markdown-{run_key}-{index}"},
        expected=(201,),
    )
    document_id = document["id"]
    document_ids.append(document_id)
    ingest = request(
        "POST",
        f"{document_base}/api/workspaces/{workspace_id}/documents/{document_id}/ingest",
        token=token,
        expected=(202,),
    )
    ingest_run_ids.append(ingest["run_id"])
    wait_status(
        f"ingest_{index}",
        lambda document_id=document_id: request(
            "GET",
            f"{document_base}/api/workspaces/{workspace_id}/documents/{document_id}",
            token=token,
        ),
        {"completed", "failed"},
        900,
    )
session = request(
    "POST",
    f"{document_base}/api/workspaces/{workspace_id}/chat/sessions",
    {"title": "AI E2E"},
    token,
    expected=(201,),
)
session_id = session["id"]
query = request(
    "POST",
    f"{document_base}/api/workspaces/{workspace_id}/chat/sessions/{session_id}/query/runs",
    {
        "question": "스마트팜 관수 제어에서 센서 데이터는 어떻게 쓰이나요?",
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
        "allow_web_search": False,
    },
    token,
    expected=(202,),
)
query_result = wait_status(
    "query",
    lambda: request("GET", f"{document_base}/api/query/runs/{query['request_id']}", token=token),
    {"completed", "failed"},
    600,
)
agent = request(
    "POST",
    f"{document_base}/api/workspaces/{workspace_id}/agent/turn",
    {
        "session_id": session_id,
        "message": "방금 답변을 한 문장으로 요약해줘.",
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
        "allow_web_search": False,
    },
    token,
    expected=(202,),
)
agent_result = wait_status(
    "agent",
    lambda: request(
        "GET",
        f"{document_base}/api/workspaces/{workspace_id}/agent/turn/{agent['requestId']}",
        token=token,
    ),
    {"completed", "failed"},
    600,
)
lint = request(
    "POST",
    f"{document_base}/api/workspaces/{workspace_id}/wiki/maintenance/lint",
    {"dry_run": False, "materialize_promotions": True},
    token,
    expected=(202,),
)
lint_result = wait_status(
    "lint",
    lambda: request(
        "GET",
        f"{document_base}/api/workspaces/{workspace_id}/wiki/maintenance/runs/{lint['run_id']}",
        token=token,
    ),
    {"succeeded", "failed"},
    900,
)
lint_task_result = (lint_result.get("manifest") or {}).get("task_result") or {}
promotions = [
    *(lint_task_result.get("materialized_promotions") or []),
    *(lint_task_result.get("merged_promotions") or []),
]
promotion_candidates = lint_task_result.get("promotion_candidates") or []
materialized_promotions = lint_task_result.get("materialized_promotions") or []
merged_promotions = lint_task_result.get("merged_promotions") or []

result = {
    "workspace_id": workspace_id,
    "document_ids": document_ids,
    "ingest_run_ids": ingest_run_ids,
    "ingest_status": "completed",
    "query_request_id": query["request_id"],
    "query_status": query_result["status"],
    "agent_request_id": agent["requestId"],
    "agent_status": agent_result["status"],
    "lint_run_id": lint["run_id"],
    "lint_status": lint_result["status"],
    "lint_task_result": lint_task_result,
    "promotion_candidates": promotion_candidates,
    "materialized_promotions": materialized_promotions,
    "merged_promotions": merged_promotions,
    "promotions": promotions,
}
(output_dir / "ai-tasks.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
if not promotions:
    raise RuntimeError("lint 결과에 materialized 또는 merged promotion이 없습니다.")
print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
PY

: >"$PROMOTION_OUTPUT"
while IFS= read -r markdown_key; do
  docker exec fruition-pipeline-api-dev python -c \
    'import sys; from app.modules.wiki_ingestion.infrastructure.object_storage import read_text_object; print(read_text_object(sys.argv[1]))' \
    "$markdown_key" >>"$PROMOTION_OUTPUT"
done < <(
  python3 - "$OUTPUT_DIR/ai-tasks.json" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
page_ids = {item["page_id"] for item in result["promotions"] if item.get("page_id")}
for artifact in result["lint_task_result"].get("operation_artifacts", []):
    if artifact.get("page_id") in page_ids and artifact.get("markdown_key"):
        print(artifact["markdown_key"])
PY
)
grep -Fxq '# 과습 관리' "$PROMOTION_OUTPUT" || fail "과습 관리 promotion 문서를 찾지 못했습니다."

"${COMPOSE[@]}" ps --format json >"$OUTPUT_DIR/compose-ps.json"
log "전체 AI E2E를 완료했습니다: $OUTPUT_DIR"
log "converter Markdown: $CONVERTER_OUTPUT"
log "promotion Markdown: $PROMOTION_OUTPUT"
