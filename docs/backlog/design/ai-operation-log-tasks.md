# AI 작업 로그 저장·조회·복구 작업 계획

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-07-31
- 설계 문서: [`ai-operation-log.md`](./ai-operation-log.md)
- 상세 근거: [`ai-operation-log-detail.md`](./ai-operation-log-detail.md)
- 담당: Backend (TASK-001~009), AI/llmPipeline (TASK-101~106)

## 2. 실행 원칙

- 각 TASK의 실패 테스트 또는 재현 절차를 구현보다 먼저 작성한다.
- 각 완료 조건을 통과한 뒤 다음 TASK로 이동한다.
- 기존 문서 편집·업로드·Wiki 동작의 회귀를 함께 검증한다.
- 요청과 무관한 리팩터링은 포함하지 않는다.
- llmPipeline이 완료되기 전에도 Backend TASK는 mock 콜백으로 검증한다. 실제 연동은 TASK-009에서 확인한다.

## 3. 확정 사항

| 항목 | 값 |
|---|---|
| Backend 패키지 | `fruition.aihistory`. 클래스는 `Operation*` · `Restore*` (`Ai` 접두어 생략) |
| Wiki 이력 테이블 | `fruition.wiki` 도메인에 배치 |
| 본문 저장 | RDS text + `markdown_key`로 object 위치 병기 |
| 저장소 쓰기 | llmPipeline만. Backend는 읽기만 |
| 복구 범위 | 선택 없음. 지목한 작업과 그 이후 같은 문서의 작업을 전부 취소한다 |
| 화면 버전 | `revision`. 기여 수는 `contribution_count`로 병기 |

## 4. 작업 계획 — Backend

### TASK-001 로그 스키마 추가 (F1)

- 관련 설계: §3.1, §3.2, §3.5
- 변경 대상:
  - `backend/src/main/resources/db/migration/V15__add_ai_operation_logs.sql`
  - 신규 `fruition/aihistory/domain/**`, `fruition/aihistory/repository/**`
- 작업:
  - `ai_operation_logs` 생성 — `operation_id` PK, `workspace_id`·`user_id` FK, `operation_type`, `target_document_id`, `status`, `summary`, `changed_resource_count`, `restored_from`, `restore_manifest`(jsonb), `payload_hash`, `created_at`, `completed_at`
  - `ai_operation_changes` 생성 — `id` PK(identity), `operation_id` FK CASCADE, `resource_type`, `resource_id`(FK 없음), `before_revision`, `after_revision`, `change_type`, `change_summary`, `additions`, `deletions`
  - `document_content_versions.operation_id` 추가 (FK → `ai_operation_logs`, ON DELETE SET NULL)
  - 인덱스: `(workspace_id, operation_type, created_at DESC)`, `(target_document_id, created_at)`, `(operation_id)`, `(resource_id, id)`
  - 멱등 UNIQUE: `(operation_id, resource_type, resource_id, change_type)`
  - enum 4종 — `OperationType`, `OperationStatus`, `ChangeType`, `ResourceType`
- 완료 조건:
  - [ ] Flyway migration 검증 통과
  - [ ] 같은 `operation_id` 2회 insert 시 제약 위반
  - [ ] 같은 작업·리소스·변경유형 2회 insert 시 제약 위반
  - [ ] `ddl-auto=validate` 통과

### TASK-002 Wiki revision·기여 스키마 추가 (F2)

- 관련 설계: §3.3, §3.4
- 선행: TASK-001 (FK 참조)
- 변경 대상:
  - `V16__add_wiki_page_versions.sql`
  - 신규 `fruition/wiki/domain/WikiPageVersion.java`, `WikiPageContribution.java`와 repository
- 작업:
  - `wiki_page_versions` 생성 — `(page_id, revision)` PK, `contribution_count`, `markdown`, `markdown_key`, `content_hash`, `operation_id`, `created_by`, `created_at`
  - `wiki_page_contributions` 생성 — `(page_id, ingest_operation_id)` PK, `source_document_id`, `sequence_revision`, `object_key`, `active`, `deactivated_by`, `created_at`
  - 인덱스: `(page_id, revision DESC)`, `(page_id, active, sequence_revision)`
  - `wiki_pages`는 변경하지 않는다. 채번은 `max(revision)`으로 얻고, 재조립 실패는 `ai_operation_changes.rebuild_failed`로 남긴다
- 완료 조건:
  - [ ] Flyway migration 검증 통과 (V15 → V16 순서)
  - [ ] `revision`이 단조 증가하고 감소하지 않음
  - [ ] `contribution_count`가 감소 가능
  - [ ] 같은 `contribution_count`가 서로 다른 `revision`에 존재해도 구분됨
  - [ ] `active=false` 기여가 후속 계산에서 제외됨

### TASK-003 복구 판정과 미리보기 (F6)

- 관련 설계: §5.1, §5.4, §6
- 선행: TASK-002
- 변경 대상:
  - 신규 `aihistory/service/RestorePlanner.java`, `PreviewTokenSigner.java`
  - 신규 `aihistory/dto/RestorePreviewResponse.java`
  - `aihistory/controller/OperationQueryController.java`(미리보기 endpoint)
- 작업:
  - `mode`별 제외 집합 확정 — `since`(기본), `single`, `document`
  - 판정 쿼리 — 페이지별 `kept_count`, `max_kept_seq`, `min_excluded_seq` 집계
  - 3분기 — 남은 기여 0이면 삭제, `max_kept_seq < min_excluded_seq`이면 복원, 그 외 재조립
  - 목표값 — 복원 목적지는 `min_excluded_seq - 1`, 재조립 `contribution_count`는 `kept_count`
  - `keep_contributions`는 남은 기여를 `sequence_revision` 순으로
  - `preview_token`에 대상 page별 현재 revision·활성 기여 manifest hash·`mode`를 서명
  - lint 대상은 `single`만 허용
  - **테스트를 구현보다 먼저 작성한다**
- 완료 조건:
  - [ ] §5.4 시나리오 11개가 기대값과 일치
  - [ ] `mode` 미지정 시 `since`로 동작
  - [ ] 미리보기와 실행의 `mode`가 다르면 409
  - [ ] 판정 단계에서 본문을 읽지 않음(저장소 접근 0회)

### TASK-004 document_edit 로그 기록 (F3)

- 관련 설계: §1 처리 흐름 ①, §3.1
- 선행: TASK-001
- 변경 대상:
  - `agent/service/AgentTurnService.java`, `agent/dto/AgentTurnResponse.java`
  - `document/controller/DocumentController.java`, `document/service/DocumentService.java`
  - 신규 `aihistory/service/OperationRecorder.java`
- 작업:
  - `AgentTurnService`가 `apply_operation_id`를 발급해 응답에 포함
  - `PUT /documents/{id}/content`가 `apply_operation_id`를 받고, `saveContent`에서 해당 사용자·문서·편집안에 대해 발급된 값인지 검증
  - 검증을 통과한 경우에만 `ai_operation_logs`·`ai_operation_changes` 기록 (저장과 같은 트랜잭션)
  - `document_content_versions.operation_id` 갱신
  - 줄 수 계산 실패는 삼키고 `additions`·`deletions`를 NULL로 저장
  - conflict는 `REQUIRES_NEW`로 분리해 커밋
  - 기존 `source` 파라미터만으로 AI 작업 여부를 판단하지 않는다
- 완료 조건:
  - [ ] AI 편집 1회 적용 = 로그 1건 + 변경내역 1건
  - [ ] 수동 저장과 무변경 저장은 로그를 만들지 않음
  - [ ] `source=agent`만 위조한 요청은 AI 로그를 만들지 못함
  - [ ] `base_version` 불일치 시 문서는 변경되지 않고 `conflict` 로그만 남음
  - [ ] 줄 수 계산 예외가 저장을 실패시키지 않음

### TASK-005 ingest·lint 결과 수신 (F4)

- 관련 설계: §1 처리 흐름 ②, §4.1, §4.2, §4.5, §4.6
- 선행: TASK-001, TASK-002
- 변경 대상:
  - 신규 `aihistory/controller/OperationCallbackController.java`, `aihistory/service/OperationIngestService.java`, `aihistory/dto/OperationResultRequest.java`
  - `security/SecurityConfig.java`
  - `wiki/service/WikiService.java`
  - `document/repository/DocumentProcessingRequester.java`
  - `wikimaintenance/service/WikiMaintenanceService.java`, `wikimaintenance/repository/PipelineWikiMaintenanceRequester.java`
- 작업:
  - llmPipeline 호출 **전에** `ai_operation_logs`를 `processing`으로 커밋하고, 호출 실패는 별도 트랜잭션으로 `failed` 기록
  - `POST /api/ai-operations/{operation_id}/result` 수신 — 내부 토큰·서명 검증을 통과하기 전에는 객체를 읽지 않음
  - `payload_hash` 비교 — terminal 상태이며 같으면 200, 다르면 409
  - 콜백 body의 workspace·user·document는 등록값과 일치 여부만 확인하고 권한 근거로 쓰지 않음
  - `markdown_key`·`contribution_key` 검증 — bucket은 환경 설정 고정, prefix가 `wiki/{workspace_id}/pages/{page_id}/ops/{operation_id}.(md|json)`인지 정확 확인
  - 본문 읽기와 `content_hash` 대조는 트랜잭션 밖
  - 트랜잭션 안: `wiki_pages` 행 `FOR UPDATE` → `revision = max+1` → `wiki_page_contributions` insert → active 수 집계 → `wiki_page_versions` insert → `wiki_pages.markdown_uri` 이동 → `ai_operation_changes` insert
  - `content_hash`가 직전 버전과 같으면 건너뛴다
  - lint는 기여를 만들지 않고 `contribution_count`를 올리지 않는다
  - `DocumentProcessingRequester`와 lint 요청에 `operation_id`·`result_callback_url` 추가
- 완료 조건:
  - [ ] 요청 실패 시 `status=failed`
  - [ ] 같은 payload 재전송 시 로그·변경내역이 1건 유지
  - [ ] 다른 payload가 같은 `operation_id`로 오면 409
  - [ ] hash 불일치·prefix 위반 시 422이고 DB가 변경되지 않음
  - [ ] 인증되지 않은 콜백은 객체 읽기 전에 401
  - [ ] 같은 페이지 콜백 2개 동시 수신 시 revision 중복 없음, `markdown_uri`는 더 큰 revision을 가리킴
  - [ ] 부분 실패 시에도 생성된 페이지가 기록됨

### TASK-006 조회 API (F5)

- 관련 설계: §6
- 선행: TASK-004, TASK-005
- 변경 대상:
  - 신규 `aihistory/controller/OperationQueryController.java`, `aihistory/dto/**`
  - `wiki/controller/WikiController.java`
  - `document/service/MarkdownDiffService.java`
- 작업:
  - `GET /api/workspaces/{ws}/ai-operation-logs` — `type`·`status`·`cursor`·`size` 필터
  - `GET /api/workspaces/{ws}/ai-operation-logs/{operation_id}` — 변경내역 포함. `revision`과 `contribution_count` 병기
  - `GET /api/workspaces/{ws}/wiki/pages/{page_id}/diff?from=&to=` — 두 revision을 읽어 그 자리에서 계산
  - `MarkdownDiffService`의 응답 타입을 리소스 중립 record로 분리하고, 기존 `DocumentContentDiffResponse`는 어댑터로 유지
- 완료 조건:
  - [ ] 기존 `GET /documents/{id}/diff` 응답 스키마 무변경
  - [ ] 목록·상세 응답 생성 중 diff 계산 0회
  - [ ] 타 워크스페이스 로그 조회 시 404
  - [ ] 페이지 diff는 요청당 1회만 계산

### TASK-007 복구 실행 (F7)

- 관련 설계: §5.2
- 선행: TASK-003
- 변경 대상:
  - 신규 `aihistory/service/RestoreExecuteService.java`, `aihistory/service/RestoreApplier.java`,
    `aihistory/service/RestoreOperationLifecycle.java`, `aihistory/repository/PipelineRestoreRequester.java`
  - `aihistory/controller/OperationQueryController.java`(실행 endpoint)
- 작업:
  - `POST .../ai-operation-logs/{operation_id}/restore` — body에 `preview_token` 필수
  - `preview_token` 재검증. 대상 revision이나 활성 기여가 달라졌으면 409
  - ingest 되돌리기는 Wiki만 되돌린다. 문서 본문은 건드리지 않는다
  - `ai_operation_logs`에 `restore` 작업을 `applying`으로 별도 트랜잭션에 먼저 커밋하고 `restore_manifest` 보관
  - 트랜잭션: 대상 `wiki_pages`를 `page_id` 순서로 `FOR UPDATE` → 제외 기여 `active=false`·`deactivated_by` 갱신 → 복원·삭제·위임 처리
  - 복원은 되돌릴 revision의 `markdown`과 `markdown_key`를 재사용하고 `markdown_uri`만 이동. **저장소에 쓰지 않는다**
  - 삭제는 `wiki_pages.status='deleted'` 소프트 삭제, 링크 정리
  - 위임은 `ai_operation_changes`에 `delegated`만 기록
  - 재조립 대상이 있으면 지시서 전송 후 `rebuilding`, 없으면 `succeeded`
  - 전송 실패는 예외를 올리지 않고 `notify_pending`으로 남긴다
  - 중간 실패 시 `applying`에 두고 같은 `restore_manifest`로 재시도한다
- 완료 조건:
  - [x] 복원 revision의 `markdown_key`가 되돌릴 대상과 동일
  - [x] 복구 중 Backend가 저장소에 쓰지 않음
  - [x] 삭제된 페이지의 `wiki_page_versions`·`wiki_page_contributions`가 유지됨
  - [x] 미리보기 이후 대상이 변경되면 409이고 revision이 생성되지 않음
  - [x] 통지 실패 시 `notify_pending` 유지 후 재시도 가능
  - [x] 행 잠금이 실제로 동작 — `WikiPageLockIntegrationTest` (Testcontainers)
- 남은 항목:
  - `applying` 상태 동안 같은 문서의 새 ingest 차단 (미구현)
  - `notify_pending` 재전송 (미구현. 지금은 수동 재시도)

### TASK-008 재조립 결과 수신 (F8)

- 관련 설계: §4.4, §5.2 ⑦
- 선행: TASK-005, TASK-007
- 변경 대상: `aihistory/service/OperationIngestService.java`,
  신규 `aihistory/service/RestoreRebuildApplier.java`, `aihistory/service/WikiLineCounter.java`
- 작업:
  - 기존 restore 작업의 `rebuilding` 단계를 완료하는 분기 추가
  - 멱등 기준은 `(operation_id, page_id, result_phase='rebuild')`.
    성공분은 `content_hash` 일치로, 실패분은 `(operation_id, page_id, rebuild_failed)` 존재 여부로 판정한다
  - `contribution_count`는 `restore_manifest`에서 조회하고 재계산하지 않는다
  - 지시서에 `rebuild`로 없는 페이지가 결과에 오면 거절한다
  - 성공분은 `revision = max+1`로 적재하고 `rebuilt` 기록
  - `failed_pages`는 `rebuild_failed`로 기록하고 사유를 `change_summary`에 남긴다
  - 전량 성공은 `succeeded`, 일부 실패는 `partially_succeeded`
  - `delegated` 행은 갱신하지 않는다
- 완료 조건:
  - [x] `contribution_count`가 지시서 값과 일치
  - [x] 페이지별 재전송이 멱등이고, 다른 payload는 409
  - [ ] 허용 상태가 `rebuilding`이 아니면 409
  - [ ] 실패 페이지가 `rebuild_failed`로 남고 본문이 변경되지 않음

### TASK-009 스펙 문서와 연동 검증 (F9)

- 선행: TASK-006, TASK-008, TASK-103
- 변경 대상:
  - 신규 `docs/spec/api/ai-operation-log.md`
  - `docs/spec/api/00-common.md`
  - `docs/changelog/backend.md`
- 작업:
  - API 스펙 작성 — 경로·요청·응답·예외 매핑
  - 전역 예외 핸들러 표에 신규 예외 추가
  - llmPipeline 실제 연동으로 ingest → 조회 → 복구 → 재조립 E2E 확인
- 완료 조건:
  - [x] 문서의 경로·예외가 실제 컨트롤러와 일치
  - [ ] 실제 ingest 1회가 로그·버전·기여·변경내역에 모두 반영됨 — **llmPipeline TASK-101~103 대기**
  - [ ] 실제 복구 1회가 미리보기 예상과 일치 — **llmPipeline TASK-104 대기**

## 5. 작업 계획 — llmPipeline

Backend와 독립적으로 착수한다. **TASK-102가 가장 급하다** — ingest 시점에 기여 조각을 남기지 않으면 그 기간에 쌓인 데이터는 어떤 방법으로도 복구할 수 없다.

### TASK-101 요청 스키마 확장

- 변경 대상: `llmPipeline/app/modules/wiki_ingestion/interfaces/http/schemas.py`
- 작업: `_PipelineRunBase`에 `operation_id`, `result_callback_url` 추가
- 완료 조건:
  - [ ] `extra="forbid"` 상태에서 Backend 요청이 422 없이 수용됨
  - [ ] 두 값이 실행 전 구간에 전달됨

### TASK-102 본문 key 체계 변경과 기여 조각 저장

- 변경 대상:
  - `postgres_wiki_output_persistence.py:97,162,337`
  - `postgres_wiki_ingestion_repository.py:621,691`
- 작업:
  - 본문 경로를 `wiki/{user_id}/{workspace_id}/concepts/{slug}.md`에서 `wiki/{workspace_id}/pages/{page_id}/ops/{operation_id}.md`로 변경
  - 작업마다 새 key에 쓰고 기존 object를 덮어쓰지 않는다
  - **`wiki_pages.markdown_uri`를 갱신하지 않는다.** Backend가 검증 후 이동시킨다
  - 기여 조각을 `wiki/{workspace_id}/pages/{page_id}/ops/{operation_id}.json`에 저장한다. 조각만으로 페이지를 재구성할 수 있어야 한다
- 완료 조건:
  - [ ] 같은 페이지를 두 번 처리해도 이전 object가 유지됨
  - [ ] `wiki_pages` 테이블이 llmPipeline에서 갱신되지 않음
  - [ ] 저장한 조각만으로 페이지 재구성이 가능함
  - [ ] slug rename 이후에도 경로가 어긋나지 않음

### TASK-103 결과 콜백

- 변경 대상: 신규 통지 모듈. `pipeline_log.py:60`의 `urllib` 패턴 재사용
- 작업:
  - 완료·실패 시 `result_callback_url`로 POST
  - `changed_pages[]`에 `page_id`, `markdown_key`, `contribution_key`, `content_hash`, `contribution_stored`
  - `target_document_id`를 반드시 포함한다. 없으면 Backend가 복구를 계산할 수 없다
  - 부분 실패여도 이미 생성한 페이지를 담아 보낸다
  - 내부 토큰·서명을 함께 보낸다
  - 422 응답 시 본문을 다시 쓰고 재전송한다
- 완료 조건:
  - [ ] 성공·부분 실패·실패 각각에서 콜백이 발송됨
  - [ ] 안 바뀐 페이지는 `changed_pages`에 포함되지 않음
  - [ ] 재전송 시 동일 payload를 보냄

### TASK-104 재조립 엔드포인트

- 변경 대상: `wiki_ingestion/interfaces/http/routes.py`, 신규 재조립 모듈
- 작업:
  - `POST /wiki/restore-runs` 신설
  - `rebuild_pages[].keep_contributions`를 받은 **순서대로** 조각을 조립해 페이지를 재생성
  - `keep_contributions`가 1개면 LLM 호출 없이 그 조각을 그대로 사용
  - `restored_pages`·`deleted_pages`는 재작성 대상이 아니며 임베딩·링크 정리에만 사용
  - 결과는 TASK-103과 같은 경로로 회신하되 `failed_pages`를 포함
- 완료 조건:
  - [ ] 지정한 조각만 사용하고 제외된 조각을 사용하지 않음
  - [ ] 조각 유실 시 해당 페이지만 `failed_pages`로 보고
  - [ ] `deleted_pages`의 임베딩이 정리됨

### TASK-105 lint 확장

- 변경 대상: `schemas.py`의 `WikiLintIn`, `WikiLintOut`
- 작업: 요청에 `operation_id`, 응답에 `changed_pages` 추가. `contribution_key`는 담지 않는다
- 완료 조건:
  - [ ] `dry_run=true`면 `changed_pages`가 빈 배열
  - [ ] 실제 변경 시 페이지 목록과 `content_hash`가 반환됨

### TASK-106 ingest 직렬 실행 보장

- 작업: 1차 구현에서 같은 workspace의 ingest를 직렬 실행한다. 콜백에 `base_revision`이 없어 병렬 ingest의 의미 충돌을 해결할 수 없다
- 완료 조건:
  - [ ] 같은 workspace의 ingest 2건이 동시에 실행되지 않음

## 6. 순서

```text
Backend      TASK-001 · TASK-002 (병렬)
                 ↓
             TASK-003 (판정 — 먼저 착수 권장)
                 ↓
             TASK-004 · TASK-005
                 ↓
             TASK-006 · TASK-007 → TASK-008
                 ↓
             TASK-009

llmPipeline  TASK-101 → TASK-102 → TASK-103 → TASK-104 · TASK-105 · TASK-106
             (Backend와 독립. TASK-102 최우선)
```

TASK-003은 llmPipeline과 무관한 순수 계산이고 기대값이 §5.4에 확정돼 있어, **테스트를 먼저 쓰고 구현할 수 있는 유일한 TASK**다. 판정이 맞으면 나머지는 배선 작업이므로 먼저 착수하기를 권한다.

## 7. 범위 밖

- 프론트엔드 화면 — 별도 이슈로 관리
- 보존 정책과 로그 삭제 API
- Wiki 간선(link)의 기여 support 모델
- 오래된 로그·기여 정리 배치
