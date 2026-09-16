# 현행 아키텍처

## 1. 서비스 경계 (전부 독립 배포 단위)

```text
frontend (Next.js, Vercel)
  │ /api/* 경로 기반 rewrite (next.config.mjs)
  ├─ /api/auth/*, /api/workspaces, /api/workspaces/{id} ─▶ access-svc
  └─ 그 외 ───────────────────────────────────────────▶ document-svc

services/
├─ access-svc/     Spring, :8081  로그인·OAuth·세션·워크스페이스·멤버·권한 projection 소유
├─ document-svc/   Spring, :8080  문서·채팅·Wiki·query, Flyway(스키마) 소유, stateless
├─ java-shared/    라이브러리 모듈  JWT(발급·검증)·공통 예외·Idempotency (앱 아님)
└─ ai-svc/
   ├─ pipeline/    FastAPI, 내부 전용  동기 query·agent·lint + GET /documents (LLM·임베딩)
   ├─ ingest-worker  Kafka consumer   ai.ingest.command 소비 → 문서/Wiki ingest
   ├─ edit-event-consumer  Kafka consumer  document.edit.event 소비 → 파생물 stale 추적 (ai_db)
   └─ converter/   FastAPI, 내부 전용  PDF→Markdown 변환 (document-svc 변환 큐 경유)

상태 계층: PostgreSQL(access_db·core_db 분리) · MongoDB(문서 편집 원본) · Redis · Kafka · MinIO/S3
          (AWS: Access RDS + Core RDS · MongoDB Atlas · ElastiCache · Strimzi Kafka · S3)
```

코드 경계는 컴파일러가 강제한다: `document-svc`(fruition.core)는 `fruition.access`를 import하지 않고, `access-svc`는 `fruition.core`를 import하지 않는다. 두 앱은 서로의 DB repository를 직접 쓰지 않고 내부 API·Redis projection으로만 연결한다.

## 2. 서비스 간 통신

| 방향 | 방식 | 용도 |
|---|---|---|
| document → access | `GET /internal/authz/workspaces/{wid}/users/{uid}`, `GET /internal/users/{uid}` (X-Internal-Token) | 권한·표시명 조회 (캐시 miss 시) |
| access → document | `POST /internal/workspaces/{wid}/initial-note` (X-Internal-Token, best-effort, 커밋 후 호출) | 새 워크스페이스 초기 노트 |
| document → ai-svc | Kafka `ai.ingest.command` (key=workspace_id) | 비동기 ingest |
| document → ai-svc | HTTP + X-Internal-Token | 동기 query·agent·lint |
| document → converter | HTTP (내부 전용, 큐 worker 경유) | PDF→Markdown 변환 (read timeout 900s) |
| ai-svc → document | HTTP 콜백 + X-Internal-Token | 진행 heartbeat·결과 통지 |
| 사용자 인증 | 각 앱이 JWT(iss·aud, HS256 공유 시크릿) 로컬 검증 | access 호출 없이 검증 |

## 3. 권한 인가 (핵심 설계)

document-svc는 workspace 멤버십을 DB에서 직접 읽지 않는다:

```text
요청 → document-svc guard.requireMember(wid, uid)
  1. Redis authz:role:{wid}:{uid} 조회 (TTL 300s)
     · hit(OWNER/MEMBER/NONE) → 즉시 판정
  2. miss → access-svc GET /internal/authz/... (connect 2s/read 3s)
     · 결과를 TTL 300s로 캐시 후 판정
  3. HTTP 실패 → WorkspaceNotFoundException (fail-closed, 404)
```

access-svc는 멤버십 변경 시 projection을 write-through/무효화한다(생성 시 put, 삭제·복구 시 evict). 이 구조 덕에 **access-svc가 죽어도 캐시 warm 상태의 문서 기능은 계속 동작한다**(TTL 내). 실검증은 [`verification.md`](verification.md) 참조.

## 4. 데이터 소유

| 영역 | 소유 | 저장소 |
|---|---|---|
| users·oauth·refresh token·workspaces·members·세션 | access-svc | **access_db** (자체 Flyway, access_runtime/migration 계정) |
| 권한 projection·OAuth 교환 코드 | access-svc | Redis |
| 문서 metadata·폴더·채팅·Wiki·operation·버전 스냅샷 | document-svc | **core_db** (Flyway 소유, core_runtime/migration 계정) |
| **문서 본문·편집 revision·write-id·edit outbox** | document-svc | **MongoDB** (`document_edit_states`·`document_edit_writes`·`document_edit_outbox`, 단일 트랜잭션) |
| query run 상태·SSE 이벤트 | document-svc | Redis (list replay + pub/sub) |
| 문서 원본·snapshot | document-svc | S3/MinIO |
| pipeline run·임베딩 | ai-svc | core_db 동거(전환기) — **ai_runtime 별도 계정**, 이전 차단 사유는 `docs/issue/ai/2026-08-07.md` |
| wiki_schemas·문서 파생물 stale 추적(`document_derived_state`) | ai-svc | **ai_db** (python 소유 `ai_schema.sql`, 기동 시 멱등 부트스트랩) |

- DB 계정은 runtime(DML)/migration(DDL) 분리, 타 서비스 DB write 불가 (`infra/postgres/init-db-isolation.sh`, validation 스크립트로 실검증).
- Idempotency 테이블은 각 DB에 서비스별 사본 (java-shared 코드 공유, 테이블 분리).
- 본문 저장은 Mongo 트랜잭션(본문+revision+write-id+outbox) 후 `MongoDocumentEditOutboxPublisher`가 Kafka `document.edit.event`(key=document_id)로 발행 — at-least-once, 문서별 순서 보존.
- AWS는 Access RDS/Core RDS 2 instance + MongoDB Atlas (`infra/terraform`).

## 5. 남은 목표 (문서 대비)

- ~~물리 DB 분할~~ 완료 (access_db/core_db + 계정 격리, AWS Access/Core RDS 2대 — `infra/terraform`)
- ~~MongoDB 문서 편집 원본~~ 완료 (§3.1 — Mongo 트랜잭션 + outbox → Kafka `document.edit.event`)
- ai 테이블 잔여 4개(pipeline_runs·임베딩 3종) core_db 동거 해소 — 검색 CTE·ingest 원자성 재설계 선행 필요, 교차 지점 실측 목록은 `docs/issue/ai/2026-08-07.md` (1단계로 wiki_schemas는 ai_db 이전 완료)
- ~~`document.edit.event` consumer 부재~~ 1단계 완료 — edit-event-consumer가 `document_derived_state`(ai_db)에 stale 추적. 검색 신선도 UI·재ingest 후보 활용은 후속
- ~~Terraform·Secrets Manager~~ IaC 작성 완료 — apply는 AWS 계정 준비 후 (`docs/issue/infra/2026-08-07.md`)

## 6. 조건부 후속 (필수 아님 — 트리거 기준)

당장 필요하지 않고, 아래 시점이 오면 착수한다. 우선순위 논쟁 방지를 위해 트리거를 명시해 둔다.

| 항목 | 필요해지는 시점 (트리거) | 참고 |
|---|---|---|
| RS256 + JWKS | 외부 공개·시크릿 유출 리스크를 진지하게 볼 때. 소규모 초대 사용자 profile에선 HS256 공유 시크릿으로 감 | 목표 문서 §7 |
| query·result Kafka result topic 전환 | HTTP 콜백이 검증된 상태 — pipeline 재시작 중 결과 유실이 실제 문제가 될 때 | 참조 구현 `feat/msa-kafka-publisher-consumers` 브랜치(318b991) 포팅 가능, 목표 문서 §4.3 |
| ai 테이블 4개(pipeline_runs·임베딩 3종) ai_db 이전 | 지금은 계정 격리로 안전 확보됨. AI 부하를 독립 스케일해야 할 때 | 차단 지점 실측 `docs/issue/ai/2026-08-07.md` |
| ~~converter 제품 경로 연결~~ | **완료 (2026-08-07)** — PDF 원본 우클릭 "Markdown으로 변환" → `POST .../convert-markdown`(202) → `document_convert_queue` worker → converter → Mongo 반영. E2E 실검증 | `DocumentConvertWorker`, `ConverterClient` |
| pipeline-runs PVC → S3 아티팩트 이전 | AI Worker Spot 노드 활용(비용 절감)이 필요할 때 — 완료 시 ingest-worker podAffinity 제거 + Spot 노드 분리 활성화 | `k8s/overlays/aws/README.md` 제약 절 |
