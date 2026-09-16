# ADR: 파이프라인의 backend 소유 테이블 직접 쓰기와 채팅 완료 후처리

- Status: Accepted (단기안 B 구현 완료, 중기안 C-poll 후속)
- Date: 2026-07-10
- 관련 문서: `docs/spec/chat-to-wiki-contract.md`, `docs/Fruition_MVP_Erd.md`
- 관련 코드: `chat/service/ChatWikiExportReconciler`, `document/service/DocumentService`(`doRequestProcessing`가 `origin=chat_export`면 chat endpoint로 라우팅), `document/repository/DocumentProcessingRequester`(endpoint 분기), `document/domain/Document`, llmPipeline `finish_pipeline_run`(완료 `status='completed'`), `postgres_wiki_ingestion_repository.py`(실패 `status='failed'` 직접쓰기), 실행 endpoint `POST /pipeline/runs`(일반)·`POST /chat-wiki/runs`(채팅), 상태조회 `GET /pipeline/runs/{run_id}`

## Context

`documents`, `wiki_pages`, `source_blocks`, `document_wiki_links`는 ERD상 **backend(Spring) 소유**다. 그러나 실제로는 **llmPipeline이 이 테이블들에 직접 쓴다**:

- 완료 시 `documents.status = 'completed'` (raw SQL, `finish_pipeline_run`)
- `wiki_pages` / `source_blocks` / `document_wiki_links` 적재

성능(HTTP 왕복 없는 대량 write)과 단순함을 위한 실용적 지름길이었으나 다음 문제를 만든다.

1. **스키마 결합**: 파이프라인이 backend의 `documents` 스키마(컬럼·status enum·CHECK·unique)를 알고 지켜야 한다. backend가 `documents`를 바꿀 때마다(최근 `origin`/`selection_mode`/`pipeline_input_markdown` 추가) 파이프라인이 깨질 위험. 교차-레포 결합.
2. **생명주기 단일 소유자 부재**: `documents.status`를 backend(enqueue 시 `processing`)와 파이프라인(`completed`/`failed`)이 함께 쓴다.
3. **backend 로직 우회**: 완료 전이가 DB에서 backend 몰래 일어나, backend가 그 순간 규칙 적용·파생상태(세션↔wiki 연결) 갱신을 못 한다. → **`ChatWikiExportReconciler`가 "backend가 하지 않은 변경을 뒤늦게 폴링으로 감지"하려고 존재**하는 workaround가 됐다.
4. **동시성/덮어쓰기**: 공유 행, `@Version` 없음, JPA 기본 full-column UPDATE가 파이프라인이 쓴 컬럼을 덮어쓸 수 있다.

reconciler는 `@Scheduled(fixedDelay=3000)`로 완료된 chat_export를 폴링해 세션 연결/문답 마킹을 한다. **B 적용 전에는** `documents`에 관련 인덱스가 없고 완료 문서 전체를 훑어, 매 tick **순차 스캔**했다(소량이면 무해하나 데이터 증가 시 O(전체 문서수)). 이 스캔 문제는 아래 결정의 **B로 이미 해소**했다(`idx_documents_reconcile` + `reconciled_at IS NULL` 조회, `document/domain/Document`·`document/repository/DocumentRepository`). 소유권 문제(1~4)는 남아 있어 본 문서의 주제다.

## Decision Drivers

- 소유권 정합성 (테이블당 단일 writer, 특히 `documents.status`)
- 결합도 (교차-레포 스키마 coupling)
- 상시 효율 (폴링 부하·풀스캔)
- 견고성 (유실 없는 완료 감지 = self-healing)
- 정합성 (`completed`가 세션 연결보다 먼저 보이는 window)
- 변경 비용/리스크 (backend-only vs 파이프라인 동시 변경)

## Considered Options

### A. 현행 유지 (3초 DB 폴링 + 파이프라인 직접 쓰기)
- (+) 추가 작업 없음, self-healing.
- (−) `documents` 풀스캔 상시 부하(무인덱스), 소유권 위반 유지, 정합성 window.

### B. 폴링 최적화 (`reconciled_at` 마커 + `@Index` + `@DynamicUpdate`)
backend-only. `Document`에 `reconciled_at`(null=미처리) + `@Index(origin,status,reconciled_at)` + `@DynamicUpdate`(컬럼 단위 write로 파이프라인 컬럼 미침해). 재생성 시 `reconciled_at` 리셋. 조회를 `...AndReconciledAtIsNull`로.
- (+) **풀스캔 제거**(인덱스 range scan + `reconciled_at`로 미처리분만 조회), self-healing 유지, 최소·저위험, 소유권 충돌은 `@DynamicUpdate`로 관리. (스케줄 쿼리 자체는 3초마다 계속 실행되나, idle이어도 저비용 인덱스 조회 수준.)
- (−) **소유권 위반은 남김**(오히려 backend가 공유 `documents` 행에 write 하나 추가), `completed`↔연결 window 잔존, 지연 최대 3초.

### C-push. 완료 콜백 (파이프라인이 backend로 push)
파이프라인이 산출물 커밋 후 `documents.status` 직접쓰기 대신 **완료 콜백** 호출. backend 핸들러가 status 전이 + chat 후처리를 한 트랜잭션으로. 유실 대비 **저빈도 backstop 폴러** 유지.
- (+) `documents.status` 소유권 해결, 상시 폴링 제거, `completed`↔연결 원자화, 지연↓.
- (−) 파이프라인 **동시 변경**(status 제거 + 콜백 엔드포인트/재시도/at-least-once/멱등), 순서 계약(commit-before-callback), **콜백 유실 시 stuck → backstop 폴링이 결국 다시 필요**, wiki 산출물 직접쓰기는 남음.

### C-poll. backend가 파이프라인 run status를 pull ★신규
파이프라인은 `documents.status`(완료·**실패 모두**)를 안 쓰고, backend가 **자기 DB의 processing 문서**(pipeline_run_id 보유)를 골라 **`GET /pipeline/runs/{run_id}`**(이미 존재)를 폴링. run 상태에 따라 backend가 `documents.status`를 직접 전이한다.
- (+) `documents.status` 소유권 해결 **+ self-healing 유지**(C-push의 유실 문제 없음), **push 인프라 불필요**(콜백/재시도/멱등 없이 status 쓰기만 제거). in-flight run이 없으면 pipeline 호출 0(단 processing 조회는 주기 실행).
- (−) **backend→pipeline HTTP 폴링**(in-flight run 수만큼, DB 폴링보다 비싸나 소량), pipeline HTTP API 의존, 지연 = 폴 간격, wiki 산출물 직접쓰기는 남음.
- 순서 보장: 파이프라인이 **산출물 커밋 후** run을 `succeeded`로 표시(자기 테이블 안이라 지키기 쉬움).
- **실패/예외 정책 (전환 시 필수)** — 성공만이 아니라 아래를 모두 다뤄야 한다:
  - `succeeded` → source_blocks/links 읽어 chat 후처리 + `status=completed`.
  - `failed` → `status=failed` + error 기록. **파이프라인이 현재 `postgres_wiki_ingestion_repository.py:326`에서 `status='failed'`도 직접 쓰므로, 이 직접쓰기 제거도 함께** 해야 소유권이 회수된다.
  - **조회 실패**(pipeline API down/타임아웃) → 전이하지 않고 다음 tick 재시도(self-healing).
  - **장기 running/stuck** → 시작 후 임계시간 초과 시 stalled 판정/실패 처리 정책 필요(현 `processing_updated_at` 기반 stalled 감지와 정합).
  - **`pipeline_run_id=null`**(아직 실행 요청 전/실패) → 폴링 대상에서 제외.
  - 채팅은 run이 `/chat-wiki/runs`로 생성되므로 해당 run_id를 폴링(엔드포인트 분기 반영).

### D. Single-writer (파이프라인이 모든 산출물을 backend API로 전달)
파이프라인이 wiki_pages/source_blocks/links/완료를 backend API로 넘기고 **backend가 유일 writer**.
- (+) 소유권 완전 정리, 결합 제거.
- (−) 변경 규모 큼, 대량 write를 HTTP로 옮기는 성능/설계 부담.

## 비교표

| | documents 소유권 | 견고성 | 파이프라인 변경 | 상시 비용 | 정합성 window |
|---|---|---|---|---|---|
| A 현행 | ❌ 위반 | self-healing | 없음 | DB 풀스캔 | 있음 |
| B 마커+인덱스 | ❌ 위반(관리) | self-healing | 없음(backend-only) | 3초마다 저비용 인덱스 조회(풀스캔 제거) | 있음 |
| C-push 콜백 | ✅ 해결 | 유실 위험 → backstop 필요 | 큼(status 제거+콜백/재시도) | 상시폴 제거+backstop | 없음 |
| **C-poll pull** | ✅ 해결 | **self-healing** | 중(status 제거만, 콜백 불필요) | processing 조회 주기 실행 + in-flight run당 HTTP GET(in-flight 없으면 pipeline 호출 0) | 없음 |
| D single-writer | ✅ 완전 | self-healing | 매우 큼 | API 경유 | 없음 |

## Decision

**단계적으로 간다.**

- **단기 (지금)**: **B** 채택. backend-only로 폴링을 저렴+안전하게 만들고, 파이프라인 직접쓰기는 **"알려진 부채"로 문서화하고 수용**한다.
- **중기 (소유권 회수 시)**: **C-poll**. `documents.status` 소유권을 backend로 되찾되, push 인프라·유실 리스크 없이 self-healing을 유지한다. 파이프라인은 `documents.status` 직접쓰기 제거 + "산출물 커밋 후 run succeeded" 순서만 지키면 된다. (C-push는 같은 소유권 이점을 얻으면서 유실 대비 backstop이 결국 필요하고 push 인프라가 더 크므로 **C-poll을 우선**한다.)
- **장기**: **D**는 소유권 완전 정리가 실제로 필요해질 때(결합이 반복 마찰을 일으키거나 wiki 산출물 소유까지 회수해야 할 때) 재평가.

이유: 효율 문제(풀스캔)는 B가 최소 비용으로 해결하고 self-healing을 유지한다. 소유권 위반이라는 **근본 문제**는 C 계열이 해결하며, 그중 **C-poll이 self-healing·저인프라 측면에서 C-push보다 우수**하다. MVP 단계에서는 B로 급한 불을 끄고 C-poll을 계획된 후속으로 둔다.

## Consequences

**긍정**
- B: 상시 폴링 부하 제거, 동시성 위험은 `@DynamicUpdate`로 컬럼 단위 소유 분리. backend-only·저위험.
- C-poll로의 경로가 명확 — 이미 있는 `GET /pipeline/runs/{run_id}`를 재사용하고, 파이프라인은 status 쓰기 제거만 하면 되므로 전환 비용이 C-push보다 작다.

**부정 / 주의**
- B는 소유권 위반을 남기므로 `documents` 스키마 변경 시 파이프라인 영향 검토가 계속 필요하다.
- B 마이그레이션: 컬럼 추가 시 기존 문서는 `reconciled_at=NULL`이지만, reconcile 쿼리가 **`origin='chat_export' AND status='completed'`로 한정**되므로 재처리 대상도 그 문서들뿐이다(그 외 일반 업로드·미완 문서는 스캔 대상 아님). 재처리는 멱등이라 무해. timestamp(null=pending)로 boolean-default 함정 회피.
- C-poll 전환: 파이프라인의 `documents.status` 직접쓰기 제거와 **동시 릴리스** 필요(어긋나면 완료가 아무 데서도 안 됨). "산출물 커밋 후 run succeeded" 순서 준수. backend는 processing 문서마다 pipeline HTTP GET을 폴링하므로 pipeline API 가용성에 의존.

## 후속 작업

### 완료
- [x] **(B) 구현 완료 (2026-07-10)** — `Document.reconciledAt` + `@Index(idx_documents_reconcile: origin,status,reconciled_at)` + `@DynamicUpdate` + 재생성 시 `reconciledAt` 리셋, reconciler 쿼리를 `findAllByOriginAndStatusAndReconciledAtIsNull`로 변경. (인덱스·컬럼은 `ddl-auto=update`로 재시작 시 생성; 기존 `origin=chat_export AND status=completed` 문서만 `reconciled_at=NULL`이라 재시작 후 1회 재-reconcile되나 멱등이라 무해.)

### 중기 전환 (C-poll) — 파이프라인·backend 동시 릴리스

**공통 (C-poll·C-push 모두 — 소유권 회수의 핵심)**
- [ ] (llmPipeline) `documents.status` **직접쓰기 제거**: 완료 `finish_pipeline_run`의 `status='completed'` + 실패 `postgres_wiki_ingestion_repository.py:326`의 `status='failed'`.
- [ ] (llmPipeline) `documents` 생명주기 컬럼(`processed_at`/`error_message`)도 안 씀.
- [ ] (llmPipeline) 유지: wiki_pages/source_blocks/links 적재, `[session:pair]` prefix, stage heartbeat.
- [ ] (llmPipeline) 순서: **산출물 커밋 후**에 완료를 알림.
- [ ] (backend) **완료 핸들러 신설** — status 전이 + chat 후처리를 한 트랜잭션으로. reconciler의 parse/link/mark 로직을 공유 서비스로 추출해 재사용.
- [ ] (backend) **일반 업로드도** backend가 status 전이(완료/실패). 완료 핸들러는 generic(상태 flip + chat_export면 bookkeeping).
- [ ] (backend) 실패 경로: `status=failed` + `error_message`를 backend가 기록.

**C-poll 전용**
- [ ] (llmPipeline) `pipeline_runs.status`를 terminal(`succeeded`/`failed`)로 정확히 유지, `GET /pipeline/runs/{run_id}` 응답에 status + error 노출. (채팅 run도 동일 조회)
- [ ] (backend) **run 상태 폴러(@Scheduled)** — `status=processing AND pipeline_run_id IS NOT NULL` 문서 → `GET /pipeline/runs/{run_id}`. 분기: succeeded→완료핸들러 / failed→실패 / running→skip / 조회실패→재시도 / stuck→stalled / run_id=null→제외.
- [ ] (backend) pipeline 상태조회 HTTP client(타임아웃).
- [ ] (backend) **`(status, pipeline_run_id)` 인덱스** 추가(폴러 조회는 origin 무관 `status=processing`이라 기존 `idx_documents_reconcile`로 부적합).
- [ ] (backend) B의 `reconciled_at` 마커·3초 reconciler **정리**(완료 감지가 폴러로 이동해 대부분 불필요).

**대안 C-push 선택 시 (참고)**
- [ ] (llmPipeline) 위 공통 + 완료 **콜백 POST**(`{run_id,status,error}`) + 재시도(backoff)/at-least-once/멱등(run_id).
- [ ] (backend) **완료 콜백 엔드포인트** + 멱등 핸들러(run_id 가드) + **backstop 폴러(~60s)**("`source_of` 링크 있는데 status=processing" 회수).

### 문서
- [ ] 파이프라인 직접쓰기 = 알려진 부채임을 `docs/spec/chat-to-wiki-contract.md`(또는 통합 문서)에 명시.
