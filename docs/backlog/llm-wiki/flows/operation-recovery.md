# llmPipeline Wiki operation 로그와 복구 흐름

## 1. 문서 목적

이 문서는 ingest, reingest와 lint가 Wiki를 변경할 때 작업별 산출물을 어떻게
남기고, Backend의 복구 계획에 따라 Concept 본문과 간선을 어떻게 다시 조립하는지
설명한다. 현재 결과 전달은 HTTP callback이 아니라 Kafka 작업 이벤트다.

다음 질문에 답하는 것이 목적이다.

- Source snapshot과 Concept 기여 JSON은 왜 다른가?
- 현재 Wiki를 변경하기 전에 무엇을 operation artifact로 저장하는가?
- reingest에서 이번 작업의 기여가 있는 Concept을 어떻게 구분하는가?
- Kafka 결과 이벤트 중복과 실패를 어떻게 처리하는가?
- restore가 어떤 기여 JSON을 읽어 Concept과 간선을 재조립하는가?
- lint는 어떤 근거로 고아 간선을 제거하는가?
- llmPipeline과 Backend가 각각 어떤 상태를 소유하는가?

주요 기준 코드:

- ingest 기여 생성: `services/ai/pipeline/app/modules/wiki_ingestion/application/concept_contribution.py`
- ingest operation 저장: `services/ai/pipeline/app/modules/wiki_ingestion/infrastructure/operation_artifacts.py`
- lint operation 저장: `services/ai/pipeline/app/modules/wiki_ingestion/infrastructure/lint_operation_artifacts.py`
- Concept 재조립: `services/ai/pipeline/app/modules/wiki_ingestion/infrastructure/concept_contribution_rebuild.py`
- 복구 실행: `services/ai/pipeline/app/modules/wiki_ingestion/application/restore_wiki_pages.py`
- 고아 간선 판정: `services/ai/pipeline/app/modules/wiki_ingestion/domain/orphan_link_lint.py`
- Kafka worker: `services/ai/pipeline/app/workers/ingest_worker.py`, `services/ai/pipeline/app/workers/task_worker.py`
- Backend 결과 반영: `services/backend/document-svc/.../AiTaskResultApplier.java`

## 2. 전체 생명주기

```text
Backend
  ├─ operation_id·run_id 생성, operation을 processing으로 저장
  └─ Kafka command 발행 (`ai.ingest.command` 또는 maintenance command topic)
       │
       ▼
llmPipeline worker
  ├─ ingest/chat: 문서·inline 입력 처리
  ├─ lint: dry-run 또는 write 실행
  └─ restore: Backend manifest 검증 후 Source 복사·Concept 재조립
       │
       ├─ ingest/chat
       │    ├─ 변경된 Wiki와 operation artifact를 저장
       │    └─ `ai.task.event`에 결과 발행
       ├─ lint
       │    ├─ DB/object 변경과 lint artifact를 저장
       │    └─ `ai.task.event`에 결과 발행
       └─ restore
            ├─ Source snapshot 복사·Concept 재조립·link 변화 계산
            └─ `ai.task.event`에 결과 발행

Backend
  ├─ event receipt를 `event_id`로 멱등 처리
  ├─ ingest/lint 결과의 page revision·operation 변경 이력 반영
  ├─ `wiki_page_contributions`의 ingest active 상태 관리
  └─ 복구 시 page별 restore/rebuild/delete 계획 계산
       │
       ▼
복구 command → llmPipeline restore → 결과 event → Backend 적용
```

현재 Wiki는 조회와 서비스에 사용하는 최신 상태다. operation artifact는 특정
작업을 제외하거나 다시 조립할 때 사용하는 불변 재생 기록이다. Backend의
`wiki_page_versions`는 revision을 줄이지 않고 복구도 새 revision을 append하며,
`wiki_page_contributions`는 ingest 기여 row를 지우지 않고 `active=false`로 남긴다.

## 2A. 외부 API 입출력 계약

operation 흐름은 외부 HTTP 요청, Backend가 발행한 Kafka command, llmPipeline이
발행하는 `ai.task.event` 결과로 나뉜다. FastAPI HTTP 응답은 run 등록/실행 결과이고,
Backend가 operation을 확정하는 입력은 event의 `payload`다.
FastAPI 내부 route는 `X-Internal-Token`을 요구하며, token 미설정은 `503`, 불일치는
`401`이다. Pydantic 입력 오류는 token 검증 뒤 `422`로 반환된다.

| 흐름 | 입력 경로 | 즉시 출력 | 후속 결과 |
| --- | --- | --- | --- |
| ingest | `POST /pipeline/runs` 또는 `ai.ingest.command` | `PipelineRunOut` 또는 worker 결과 | `ai.task.event`의 `kind=ingest` |
| reingest | `POST /pipeline/reingest-runs` (HTTP 전용) | `PipelineRunOut` | Kafka command 및 `ai.task.event` 미지원; `GET /pipeline/runs/{run_id}`로 확인 |
| chat Wiki | `POST /chat-wiki/runs` 또는 ingest command | `PipelineRunOut` | `ai.task.event`의 `kind=ingest` |
| lint | maintenance command → worker, 또는 `POST /wiki/maintenance/lint` | `WikiLintOut` | worker 경로는 `kind=lint` event |
| Wiki 복구 | restore command | worker 결과 | ingest는 `kind=restore_ingest`, lint는 `kind=restore_lint`인 `ai.task.event` |

### 2A.1 Ingest 입력

일반 ingest는 Backend가 먼저 저장한 document를 `document_id`로 지정한다.
llmPipeline은 request의 `user_id`, `workspace_id`를 권한 근거로 사용하지 않고
document row에서 실제 scope와 입력 object URI를 읽는다.

```http
POST /pipeline/runs
Content-Type: application/json
```

```json
{
  "document_id": "doc_A",
  "operation_id": "op_ingest_A",
  "provider": "openai",
  "model": "gpt-5-nano",
  "input_name": "design.md",
  "wait": false,
  "source_page_mode": "auto",
  "concept_page_mode": "auto"
}
```

`operation_id`는 작업별 artifact를 만들 때 사용한다. `result_callback_url`은 현재
request schema에 없으며 HTTP callback도 생성하지 않는다. Backend Kafka command는
`run_id`, `document_id`, `user_id`, `workspace_id`, `operation_id`, `provider`, `model`을 요구하고
`wait=true`로 기존 HTTP 실행 경로를 재사용한다.
직접 HTTP `PipelineRunIn`에서는 `operation_id`가 선택이지만, Kafka 결과를 Backend에
적용하는 ingest 경로에서는 생략할 수 없다.

주요 입력 필드:

| 필드 | 필수·기본값 | 결정 주체 | 의미와 빈 값 처리 |
| --- | --- | --- | --- |
| `document_id` | 필수 | Backend | 처리할 document id다. 이 row가 없거나 비활성이면 실행하지 않는다. |
| `operation_id` | 선택 | Backend | 작업별 object key와 결과 payload의 operation 식별자다. 없으면 operation artifact를 만들지 않는다. |
| `input_name` | 선택, 기본 `null` | Backend | log와 실행 입력에 표시할 파일명이다. 비어 있으면 document filename 또는 `inline.md`를 사용한다. |
| `wait` | 선택, 기본 `false` | Backend | `false`는 background 등록 후 즉시 반환하고 `true`는 완료까지 HTTP 요청을 유지한다. |
| `source_page_mode` | 선택, 기본 `auto` | Backend | `auto`, `skeleton`, `section-polish` 중 Source Page 생성 전략이다. |
| `concept_page_mode` | 선택, 기본 `auto` | Backend | `auto`, `api`, `full-llm`, `skeleton`, `section-polish` 중 Concept Page 생성 전략이다. |
| `user_id` | 선택, 기본 `null` | 호환 입력 | request 값은 저장 scope의 권한 근거가 아니다. 실제 값은 document row에서 다시 읽는다. |
| `workspace_id` | 선택, 기본 `null` | 호환 입력 | request 값은 저장 scope의 권한 근거가 아니다. 실제 값은 document row에서 다시 읽는다. |
| `provider` | 필수 | Backend/배포 설정 | `openai`, `gemini`, `claude` 중 하나다. |
| `model` | 필수 | Backend/배포 설정 | provider에 허용된 model이어야 한다. |
| `log_callback_url` | 선택 | Backend | pipeline log 이벤트를 받을 URL이다. 결과 callback URL이 아니다. |

일반 ingest의 Markdown 본문은 request body로 받지 않는다. `document_id`로 조회한
document의 object storage URI에서 읽는다.

### 2A.2 Reingest 입력

reingest는 같은 document의 최신 전체 Markdown을 `input_markdown`으로 받는다.
이전 Source Page와 source block은 `document_id`로 llmPipeline이 조회한다.

```http
POST /pipeline/reingest-runs
Content-Type: application/json
```

```json
{
  "document_id": "doc_A",
  "operation_id": "op_reingest_B",
  "provider": "openai",
  "model": "gpt-5-nano",
  "input_markdown": "# 수정된 문서\n\n새 본문",
  "input_name": "design.md",
  "wait": false
}
```

`input_markdown`은 필수다. llmPipeline은 새 Markdown과 기존 source block을 비교하고
added/modified block만 다시 의미 추출한다. 출력 `changed_pages`에는 유지된 전체
Wiki가 아니라 이번 reingest가 실제로 기여한 Source·Concept만 들어간다.

reingest 추가 필드:

| 필드 | 필수·기본값 | 결정 주체 | 의미와 빈 값 처리 |
| --- | --- | --- | --- |
| `input_markdown` | 필수 | Backend | document의 최신 전체 Markdown이다. 빈 문자열이면 모든 기존 source block을 제거하는 reingest로 해석할 수 있다. |
| `input_name` | 선택, 기본 `null` | Backend | 비어 있으면 기존 document filename, 그것도 없으면 `{document_id}.md`를 사용한다. |

### 2A.3 Ingest와 reingest의 즉시 출력

두 endpoint는 같은 `PipelineRunOut`을 반환한다.

`wait=false`이면 background 실행을 등록한 직후 다음처럼 반환한다.

```json
{
  "run_id": "run_123",
  "status": "running",
  "manifest": null,
  "output_dir": "runs/api_run_123",
  "log_path": "runs/api_run_123/pipeline.log"
}
```

이 응답은 ingest 성공을 의미하지 않는다. 이후 성공 또는 실패는
`GET /pipeline/runs/{run_id}` 또는 worker가 발행한 `ai.task.event`에서 확인한다.

`wait=true`이면 실행이 끝난 뒤 다음처럼 runtime manifest를 포함한다.

```json
{
  "run_id": "run_123",
  "status": "succeeded",
  "manifest": {
    "operation_id": "op_ingest_A",
    "source_page": {},
    "concept_pages": [],
    "operation_artifacts": []
  },
  "output_dir": "runs/api_run_123",
  "log_path": "runs/api_run_123/pipeline.log"
}
```

`wait=true`여도 HTTP callback은 보내지 않는다. HTTP response의 runtime manifest는
실행 결과이며, ingest worker가 만드는 event payload의 `changed_pages`는 Backend가
operation artifact를 읽어 revision을 등록할 목록이다.

`PipelineRunOut` 필드:

| 필드 | 생성 주체 | 의미와 빈 값 처리 |
| --- | --- | --- |
| `run_id` | llmPipeline | 실행 등록 시 만든 UUID다. run 조회와 Kafka event 멱등 식별에 사용한다. |
| `status` | llmPipeline | 즉시 응답은 `running`, 완료 응답은 `succeeded` 또는 저장된 실패 상태다. |
| `manifest` | llmPipeline | runtime 산출물 묶음이다. `wait=false` 즉시 응답에서는 `null`이고, 동기 성공 시 객체다. |
| `output_dir` | llmPipeline | pipeline log와 로컬 실행 artifact의 논리 디렉터리다. 요청 `out`이 없으면 run id로 생성한다. |
| `log_path` | llmPipeline | 해당 run의 pipeline log 경로다. |

예시 manifest 필드:

| 필드 | 의미 |
| --- | --- |
| `operation_id` | 이 manifest를 만든 Backend operation id다. operation 없이 실행하면 `null`일 수 있다. |
| `source_page` | 조립된 Source Page metadata와 runtime Markdown이다. 저장 manifest에서는 본문이 제거될 수 있다. |
| `concept_pages` | 생성·유지된 Concept Page runtime 결과다. 결과 event의 변경 목록과 동일하다고 가정하면 안 된다. |
| `operation_artifacts` | 이번 operation에서 실제로 저장된 Source·Concept artifact 목록이다. ingest event의 `changed_pages` 원본이다. |

### 2A.4 Ingest 결과 Kafka event

ingest worker는 결과를 `ai.task.event` topic에 발행한다. Backend는 `event_id`를
`ai_task_result_receipts`에 기록해 같은 event 재전달을 한 번만 반영한다.

```json
{
  "event_id": "ingest:run_123:succeeded",
  "run_id": "run_123",
  "kind": "ingest",
  "status": "succeeded",
  "workspace_id": "ws_1",
  "user_id": "user_1",
  "operation_id": "op_ingest_A",
  "request": {"document_id": "doc_A", "operation_id": "op_ingest_A"},
  "payload": {
    "operation_id": "op_ingest_A",
    "operation_type": "ingest",
    "status": "succeeded",
    "workspace_id": "ws_1",
    "user_id": "user_1",
    "target_document_id": "doc_A",
    "summary": "Wiki ingest를 완료했습니다.",
    "changed_pages": []
  },
  "error": null
}
```

`payload`의 `changed_pages`에는 본문이 아니라 object key와 hash만 들어간다.
Source artifact에는 `contribution_key`가 없고 Concept artifact에는 존재한다.

event/payload 주요 필드:

| 필드 | 생성 주체 | 의미와 빈 값 처리 |
| --- | --- | --- |
| `event_id` | worker | `kind:run_id:status` 형식의 receipt 멱등 키다. |
| `request` | worker | 원 command에서 secret top-level field를 제거한 요청이다. Backend 대조에 사용한다. |
| `operation_id` | command/payload | Backend operation과 artifact key를 식별한다. |
| `operation_type` | worker | ingest·reingest·chat Wiki 모두 `ingest`다. |
| `status` | worker | pipeline 처리 결과다. callback 전달 성공 여부가 아니다. |
| `workspace_id`, `user_id` | document row/command | Backend 등록값과 대조하며 새 권한 근거로 신뢰하지 않는다. |
| `target_document_id` | command | ingest 대상 document다. |
| `summary` | llmPipeline | 성공 요약 또는 실패 원인 문자열이다. 성공 여부 판정은 `status`를 사용한다. |
| `changed_pages` | worker payload | 이번 operation이 기록한 page artifact다. 실패하거나 변경 page가 없으면 빈 배열이다. |

`changed_pages[]` 필드:

| 필드 | 필수 | 의미 |
| --- | --- | --- |
| `page_id` | 필수 | Backend Wiki page id다. object key와 revision을 이 page에 연결한다. |
| `page_type` | ingest event에서 필수 | `source` 또는 `concept`이다. Source snapshot과 Concept contribution 처리를 구분한다. |
| `markdown_key` | 필수 | llmPipeline이 저장한 operation Markdown의 bucket 내부 key다. bucket 이름은 보내지 않는다. |
| `contribution_key` | Concept만 필수 | Concept 재조립용 JSON key다. Source snapshot에는 없다. |
| `content_hash` | 필수 | Markdown UTF-8 byte 기준 `sha256:` hash다. Backend가 잘린 쓰기나 다른 본문을 검증한다. |

pipeline 실패 예시:

```json
{
  "operation_id": "op_ingest_A",
  "operation_type": "ingest",
  "status": "failed",
  "workspace_id": "ws_1",
  "user_id": "user_1",
  "target_document_id": "doc_A",
  "summary": "실패 원인",
  "changed_pages": []
}
```

실패 event도 `status=failed`와 빈 `changed_pages`를 payload에 담아 Backend가
operation을 계속 `processing`으로 남기지 않게 한다. worker가 terminal run을
재전달받으면 저장된 run 결과를 다시 event로 만들며, Backend receipt가 최종 중복을
막는다.

### 2A.5 Lint 입력과 출력

직접 HTTP를 호출하면 lint는 요청 안에서 동기 실행된다. Backend 경로는 maintenance
command를 worker가 처리하고 `ai.task.event`의 `kind=lint`로 결과를 전달한다.

dry-run 입력:

```json
{
  "user_id": "user_1",
  "workspace_id": "ws_1",
  "provider": "openai",
  "model": "gpt-5-nano",
  "dry_run": true,
  "materialize_promotions": false
}
```

실제 적용 입력:

```json
{
  "user_id": "user_1",
  "workspace_id": "ws_1",
  "operation_id": "op_lint_A",
  "provider": "openai",
  "model": "gpt-5-nano",
  "dry_run": false,
  "materialize_promotions": true
}
```

`dry_run=false`일 때는 `operation_id`가 필수다. 누락하면 schema 검증에서 422가
반환된다. promotion을 실제 생성할 때만 provider/model 계열 설정을 사용한다.

lint 입력 필드:

| 필드 | 필수·기본값 | 결정 주체 | 의미와 빈 값 처리 |
| --- | --- | --- | --- |
| `user_id` | 선택, 기본 `local-user` | Backend | lint할 사용자 scope다. ingest 호환 필드와 달리 lint DB 조회에 직접 사용한다. |
| `workspace_id` | 선택, 기본 `local-workspace` | Backend | lint할 workspace scope다. |
| `operation_id` | write mode 필수 | Backend | lint Markdown·JSON artifact의 operation id다. lint는 `wiki_page_contributions` row를 만들지 않는다. dry-run에서는 `null`이어도 된다. |
| `dry_run` | 선택, 기본 `true` | Backend | `true`이면 후보만 계산하고 DB와 object storage를 변경하지 않는다. |
| `materialize_promotions` | 선택, 기본 `false` | Backend | write mode에서 promotion candidate를 실제 Concept으로 만들지 결정한다. dry-run에서는 `true`여도 적용하지 않는다. |
| provider/model 계열 | promotion 시 선택 | 배포 설정 또는 Backend | 신규 promotion Concept을 생성하는 LLM 설정이다. promotion을 만들지 않으면 사용하지 않는다. |

출력 예시:

```json
{
  "user_id": "user_1",
  "workspace_id": "ws_1",
  "operation_id": "op_lint_A",
  "active_path": "wiki/user_1/ws_1/clusters/active.md",
  "cluster_count": 2,
  "source_ref_count": 4,
  "orphan_refs": [],
  "promotion_candidates": [],
  "needs_review": [],
  "relation_candidates": [],
  "invalid_relations": [],
  "invalid_promotions": [],
  "reconciliation_candidates": [],
  "applied_reconciliations": [],
  "applied_cluster_reconciliation": {
    "removed_claims": [],
    "removed_relations": []
  },
  "materialized_promotions": [],
  "merged_promotions": [],
  "materialized_relations": [],
  "orphan_link_candidates": [],
  "removed_orphan_links": [],
  "operation_artifacts": [],
  "changed_pages": []
}
```

dry-run의 `operation_artifacts`, `changed_pages`, `removed_orphan_links`는 비어 있다.
write mode의 `changed_pages`는 `operation_artifacts`와 같은 목록이다. 직접 HTTP
호출자는 response를 처리하고, Backend worker 경로는 같은 결과를 event payload로
반영한다. lint artifact는 복구 시 link action을 재생하는 입력이지만
`wiki_page_contributions`의 active 상태 판정에는 포함되지 않는다.

`WikiLintOut` 필드:

| 필드 | 의미와 빈 값 처리 |
| --- | --- | --- |
| `user_id`, `workspace_id` | 실제 lint 조회·변경 scope다. |
| `operation_id` | write mode의 lint operation id다. dry-run이면 `null`일 수 있다. |
| `active_path` | 검사한 active meaning cluster Markdown의 object key다. |
| `cluster_count` | active Markdown에서 정상 parse한 cluster 수다. |
| `source_ref_count` | cluster들이 참조한 중복 제거 source ref 수다. |
| `orphan_refs` | 현재 `source_blocks`에서 찾지 못한 `doc_id:block_id` 목록이다. page link 고아 판정과 다른 개념이다. |
| `promotion_candidates` | 근거가 있고 자동 승격 조건을 만족한 cluster id다. 실제 생성 여부는 `materialize_promotions`와 write mode에 달려 있다. |
| `needs_review` | 자동 적용하지 않고 사람 또는 후속 판단이 필요한 cluster id다. 없으면 빈 배열이다. |
| `relation_candidates` | active cluster에서 읽은 relation 후보와 근거다. DB에 저장됐다는 뜻은 아니다. |
| `invalid_relations` | relation type, target 또는 evidence 계약을 통과하지 못한 후보다. |
| `invalid_promotions` | promotion 표시는 있지만 필수 source ref 등이 부족한 cluster와 원인이다. |
| `reconciliation_candidates` | reingest 결과로 stale해진 document–concept, relation, block 구조 후보다. dry-run에서도 반환한다. |
| `applied_reconciliations` | write mode에서 실제 DB 구조 정리를 적용한 결과다. dry-run이면 빈 배열이다. |
| `applied_cluster_reconciliation` | active cluster Markdown에서 제거한 stale claim과 relation을 각각 `removed_claims`, `removed_relations`에 담는다. |
| `materialized_promotions` | write mode에서 새 Concept으로 만든 cluster와 page id다. |
| `merged_promotions` | 새 page 대신 기존 Concept에 evidence를 합친 cluster와 page id다. |
| `materialized_relations` | 검증 후 실제 `wiki_page_links`에 upsert한 relation이다. |
| `orphan_link_candidates` | 삭제 page endpoint 또는 활성 기여 부재 때문에 고아로 판정한 현재 Wiki 간선이다. dry-run에서도 후보를 반환한다. |
| `removed_orphan_links` | write mode에서 실제 삭제한 고아 간선이다. dry-run이면 빈 배열이다. |
| `operation_artifacts` | write mode가 저장한 lint operation `.md`·`.json` metadata다. 변경이 없거나 dry-run이면 빈 배열이다. |
| `changed_pages` | Backend 소비용 alias이며 현재 `operation_artifacts`와 같은 배열이다. |

### 2A.6 Operation 취소 API 입력과 출력

복구는 과거 operation을 다시 활성화하는 기능이 아니라 현재 상태를 과거 restore
point로 되돌리는 기능이다. 사용자는 Backend의
`GET /api/workspaces/{workspace_id}/ai-operation-logs/{operation_id}/restore-preview`
후 `POST .../{operation_id}/restore`에 preview token을 보낸다. Backend는 계획을
재검증하고 Kafka restore command를 발행한다. ingest 복구는 지목한 ingest와 같은
document의 이후 ingest를 함께 제외하고, lint 복구는 지정한 lint 하나만 제외한다.
`keep_contributions`는 Backend가 활성 ingest contribution만 sequence 순서로
만들며, lint contribution을 포함하지 않는다.

#### Ingest·reingest 취소

```http
POST /wiki/ingest-restore-runs
Content-Type: application/json
```

```json
{
  "operation_id": "op_restore_A",
  "restore_to_operation_id": "op_reingest_A2",
  "cancel_operation_ids": ["op_reingest_A3", "op_reingest_A4", "op_reingest_A5"],
  "workspace_id": "ws_1",
  "source_page": {
    "page_id": "page_source_A",
    "document_id": "doc_A"
  },
  "rebuild_pages": [
    {
      "page_id": "page_concept_C2",
      "keep_contributions": [
        {"operation_id": "op_ingest_A", "document_id": "doc_A"}
      ]
    }
  ],
  "deleted_pages": []
}
```

이 복구 입력 예시는 reingest를 Kafka command로 재실행한다는 뜻이 아니다.
`POST /pipeline/reingest-runs`는 `input_markdown`을 받는 HTTP 전용 경로이며
`ai.task.event`를 발행하지 않는다. Kafka `kind=document` ingest 경로는
`input_markdown`을 전달하지 않으므로 reingest를 지원하지 않는다.

| 필드 | 의미와 빈 값 처리 |
| --- | --- |
| `operation_id` | 이번 취소를 기록할 새 restore operation id다. |
| `restore_to_operation_id` | 복귀할 Source version의 ingest 또는 reingest operation id다. 새 restore `operation_id`와 달라야 하며 해당 operation의 기여는 `keep_contributions`에 포함할 수 있다. 이전 Source가 없는 상태로 돌아가면 `null`이다. |
| `cancel_operation_ids` | restore point 이후 취소할 operation id를 순서대로 담는다. 비어 있거나 중복될 수 없으며 restore operation과 restore point를 포함할 수 없다. |
| `workspace_id` | Source snapshot과 Concept contribution key를 계산할 workspace다. |
| `source_page.page_id` | restore point의 Source snapshot을 복사할 Source Page id다. 읽을 operation은 `restore_to_operation_id`다. |
| `rebuild_pages` | restore point와 현재 상태의 Concept 합집합 중 다시 조립할 page다. 남은 기여가 없는 page는 넣지 않고 `deleted_pages`에 넣는다. |
| `keep_contributions` | 취소 대상을 제외하고 남길 ingest 기여다. 배열 순서가 재생 순서다. lint artifact는 별도 link action 재생에 사용한다. |
| `keep_contributions[].operation_id` | 읽을 Concept `{operation_id}.json`을 지정한다. |
| `keep_contributions[].document_id` | 기여 출처인 원문 document id다. Backend는 ingest 결과의 `contribution_key`가 등록된 workspace·page·operation prefix와 일치할 때만 저장한다. |
| `deleted_pages` | 남은 활성 기여가 없어 Backend가 삭제 처리할 page id다. 기본값은 빈 배열이다. |

llmPipeline은 restore point의 Source `.md`를 읽어 restore operation의 새 `.md`로
복사하고, Concept은 남은 JSON을 조립한다. restore point가 `null`이면 Source page id도
`deleted_pages`에 추가한다.

```json
{
  "operation_id": "op_restore_A",
  "restore_to_operation_id": "op_reingest_A2",
  "cancel_operation_ids": ["op_reingest_A3", "op_reingest_A4", "op_reingest_A5"],
  "operation_type": "ingest_restore",
  "status": "succeeded",
  "changed_pages": [
    {
      "page_id": "page_source_A",
      "page_type": "source",
      "markdown_key": "wiki/ws_1/pages/page_source_A/ops/op_restore_A.md",
      "content_hash": "sha256:..."
    },
    {
      "page_id": "page_concept_C2",
      "page_type": "concept",
      "markdown_key": "wiki/ws_1/pages/page_concept_C2/ops/op_restore_A.md",
      "content_hash": "sha256:...",
      "supported_links": []
    }
  ],
  "failed_pages": [],
  "deleted_pages": []
}
```

#### Lint 취소

```http
POST /wiki/lint-restore-runs
Content-Type: application/json
```

lint 입력은 공통 restore 필드와 단일 `target_operation_id`를 사용하며
`restore_to_operation_id`, `cancel_operation_ids`, `source_page`는 받지 않는다.
Backend는 취소할 lint가 영향을 준 모든 Concept을 `rebuild_pages` 또는
`deleted_pages` 중 하나에 포함해야 한다.

```json
{
  "operation_id": "op_restore_L",
  "target_operation_id": "op_lint_B",
  "workspace_id": "ws_1",
  "rebuild_pages": [
    {
      "page_id": "page_concept_C2",
      "keep_contributions": [
        {"operation_id": "op_ingest_A", "document_id": "doc_A"}
      ]
    }
  ],
  "deleted_pages": []
}
```

llmPipeline은 대상 lint JSON의 `added_links`, `removed_links` action을 재생하고,
Backend가 `keep_contributions`로 지정한 JSON을 `replay_supported_links`로 재생한
최종 지원 집합과 비교한다. 다른
활성 ingest artifact도 지지하는 간선은 제거하지 않고, 남은 artifact가 지지하는
경우에만 과거 제거 간선을 복원 대상으로 반환한다.

```json
{
  "operation_id": "op_restore_L",
  "target_operation_id": "op_lint_B",
  "operation_type": "lint_restore",
  "status": "succeeded",
  "changed_pages": [],
  "failed_pages": [],
  "deleted_pages": [],
  "link_changes": {
    "removed_links": [],
    "restored_links": []
  },
  "failed_actions": []
}
```

| 결과 필드 | 의미와 빈 값 처리 |
| --- | --- |
| `operation_type` | ingest 취소는 `ingest_restore`, lint 취소는 `lint_restore`다. |
| `restore_to_operation_id` | ingest 취소 결과가 복귀한 Source version operation id다. Source가 없던 상태면 `null`이다. |
| `cancel_operation_ids` | ingest 취소 결과에서 비활성화해야 할 restore point 이후 operation 목록이다. |
| `target_operation_id` | lint 취소 결과에서 비활성화해야 할 단일 lint operation id다. |
| `status` | page 또는 lint action 실패가 없으면 `succeeded`, 하나라도 있으면 `partially_succeeded`다. |
| `changed_pages` | 새 restore operation key에 저장한 Source snapshot과 재조립 Concept이다. |
| `failed_pages` | Source snapshot 부재는 `source_snapshot_missing`, Concept 기여 부재·손상은 `contribution_missing`이다. |
| `deleted_pages` | Backend가 삭제 처리할 page다. llmPipeline이 이 배열만으로 DB page를 삭제하지 않는다. |
| `link_changes.removed_links` | 취소한 lint가 추가했고 이제 다른 활성 기여가 지지하지 않는 간선이다. |
| `link_changes.restored_links` | 취소한 lint가 제거했지만 `replay_supported_links` 결과 남은 활성 기여가 다시 지원하는 간선이다. |
| `failed_actions` | 대상 lint JSON이 없으면 `operation_log_missing`, Concept 재조립 실패로 지원 집합을 확정할 수 없으면 `concept_rebuild_failed`다. 이때 `link_changes`는 빈 배열이다. |

ingest restore와 lint restore 결과는 각각 `ai.task.event`의 `kind=restore_ingest`와
`kind=restore_lint` payload다.
Backend는 event receipt를 먼저 기록하고, 성공 event에서 restore manifest를 다시
읽어 contribution 상태를 잠근 뒤 결과의 revision·page·link 변경을 반영한다.
llmPipeline이 실패한 page는 `failed_pages`에 남고 전체 상태는
`partially_succeeded`가 될 수 있다.

### 2A.7 Kafka 재전달과 멱등 처리

HTTP result callback retry endpoint와 `pending_notification`은 현재 operation
계약에 없다. Kafka producer는 event를 재전달할 수 있고, worker는 terminal
`pipeline_runs`를 다시 처리하지 않으며, Backend는 `ai_task_result_receipts`의
`event_id` unique 처리로 중복을 버린다. Backend 적용 중 일시 오류는 Kafka 소비
재시도 대상이다. worker의 stale contribution manifest 검증은 `ValueError`로 pipeline
failed event를 발행하고 Backend `RestoreOperationLifecycle.fail`이 restore를
`failed`로 확정한다.

### 2A.8 내부 데이터 전달

외부 request는 다음 경계를 거쳐 저장과 Kafka event payload로 바뀐다.

```text
HTTP JSON
  → Pydantic input schema
  → application command
  → run_lab runtime manifest
  → contribution JSON + operation artifact
  → PostgreSQL/current Wiki 반영
  → HTTP response 또는 `ai.task.event`
```

| 단계 | 주요 입력 | 주요 출력 |
| --- | --- | --- |
| HTTP schema | Backend JSON | 검증된 `PipelineRunIn`, `WikiLintIn`, `IngestOperationRestoreIn`, `LintOperationRestoreIn` |
| command 조립 | schema + document row | 실제 user/workspace와 기존 Wiki context가 들어간 command |
| pipeline | Markdown, source block, 기존 Concept index | Source·Concept page, link, meaning cluster, contribution |
| persistence | runtime manifest | operation `.md`·`.json`, 현재 Wiki와 DB 변경 |
| event 조립 | command + `operation_artifacts` | Backend가 읽을 `changed_pages`와 상태 |
| operation 취소 | Backend restore point·취소 목록, Source page, `keep_contributions` | 복구 Markdown, hash, `supported_links`, lint `link_changes` |

## 3. 식별자와 참조 형식

서로 다른 목적의 식별자를 혼동하지 않아야 한다.

| 값 | 예시 | 역할 |
| --- | --- | --- |
| Wiki page id | `page_c2` | Backend가 관리하는 Source·Concept page 식별자 |
| Source page ref | `source:doc_A` | Wiki page link의 Source endpoint |
| Concept page ref | `concept:back-emf` | Wiki page link의 Concept endpoint |
| Source evidence ref | `doc_A:B0003` | 주장과 간선을 지지하는 원문 block |
| Evidence id | `op_ingest_A:claim_001` | 작업 사이에서 충돌하지 않는 evidence 식별자 |
| Operation id | `op_ingest_A` | 한 번의 ingest, lint 또는 restore 작업 |

`doc_id:block_id`는 page link의 endpoint가 아니다. Concept 간 관계의 endpoint는
`concept:slug`이고 `doc_id:block_id`는 그 관계를 지지하는 원문 근거다.

```json
{
  "source": "concept:back-emf",
  "target": "concept:motor-efficiency",
  "relation": "affects",
  "evidence": ["doc_A:B0003"]
}
```

기여 JSON을 만들 때 짧은 `B0003` ref는 `doc_A:B0003`으로 전역화하고, claim id는
`operation_id` prefix를 붙인다. 여러 문서와 여러 작업의 기여를 한 Concept에
합쳐도 ref와 evidence id가 충돌하지 않게 하기 위한 규칙이다.

## 4. 작업별 object storage 계약

object storage는 `minio.Minio` adapter가 `S3_ENDPOINT`, `S3_BUCKET`, access/secret
설정으로 읽고 쓴다. 문서의 key는 bucket 이름을 제외한 object name이다.

### 4.1 Source Page

Source Page는 원문 문서와 1:1로 종속된다. 여러 문서의 의미 기여를 합성하지 않고
작업별 전체 Markdown snapshot만 저장한다.

```text
wiki/{workspace_id}/pages/{source_page_id}/ops/{operation_id}.md
```

Source 복구는 Concept처럼 JSON 조각을 합치지 않는다. Backend가 직전 활성
operation의 snapshot을 선택하고, llmPipeline이 그 `.md`를 restore operation의
새 불변 key로 복사한다.

### 4.2 Concept Page

Concept는 여러 문서의 ingest 기여를 합성하므로 Markdown과 ingest 기여 JSON을
함께 저장한다. lint는 별도 `.json` artifact로 본문·간선 action을 남기지만
`wiki_page_contributions`에는 row를 만들지 않는다.

```text
wiki/{workspace_id}/pages/{concept_page_id}/ops/{operation_id}.md
wiki/{workspace_id}/pages/{concept_page_id}/ops/{operation_id}.json
```

| 파일 | 내용 |
| --- | --- |
| `.md` | 해당 operation이 반영된 Concept 전체 Markdown |
| `.json` | 해당 operation이 Concept에 기여한 재조립 입력 |

기여 JSON의 주요 필드는 다음과 같다.

```json
{
  "schema_version": 1,
  "operation_id": "op_ingest_A",
  "document_id": "doc_A",
  "page_id": "page_c2",
  "concept": {
    "slug": "back-emf",
    "title": "Back EMF",
    "source_document_ids": ["doc_A"],
    "evidence_claim_ids": ["op_ingest_A:claim_001"]
  },
  "evidence_units": [],
  "source_blocks": [],
  "source_key_points": [],
  "links": []
}
```

기여 JSON 상위 필드:

| 필드 | 생성 주체 | 의미와 빈 값 처리 |
| --- | --- | --- |
| `schema_version` | llmPipeline | 기여 JSON 계약 버전이다. 현재 값은 `1`이다. |
| `operation_id` | Backend 입력을 llmPipeline이 기록 | 이 기여를 만든 ingest 또는 reingest 작업 id다. object key의 operation id와 일치해야 한다. |
| `document_id` | llmPipeline | 기여의 원문 document id다. ref 전역화와 출처 병합에 사용한다. |
| `page_id` | llmPipeline persistence | 이 기여가 속한 Concept Wiki page id다. 복구 요청의 `page_id`와 일치하지 않으면 해당 page 복구를 실패시킨다. |
| `concept` | llmPipeline | 해당 operation이 추출하거나 갱신한 Concept metadata다. 복수 기여를 조립할 때 같은 `slug`인지 확인한 뒤 병합한다. |
| `evidence_units` | llmPipeline | 이 operation이 Concept에 제공한 주장과 근거다. 없으면 빈 배열이다. |
| `source_blocks` | llmPipeline | `evidence_units`가 참조하는 원문 block의 operation 시점 사본이다. 없으면 빈 배열이다. |
| `source_key_points` | llmPipeline | Concept 본문 조립에 사용할 원문 핵심 포인트다. 없으면 빈 배열이다. |
| `links` | llmPipeline | ingest가 이 Concept에 대해 지지한 page link다. restore와 lint 고아 간선 판정에서 지원 집합에 추가한다. 없으면 빈 배열이다. |

`concept` 필드:

| 필드 | 의미와 빈 값 처리 |
| --- | --- |
| `slug` | Concept의 안정적인 의미 식별자다. 같은 page의 모든 기여는 같은 slug여야 한다. |
| `title` | 조립할 Concept Page의 표시 제목이다. 뒤 작업의 비어 있지 않은 값이 병합 결과에 반영될 수 있다. |
| `definition` | 이 operation이 제공한 정의다. 빈 문자열이면 기존의 비어 있지 않은 정의를 지우지 않는다. |
| `anchor_reference_ids` | Concept을 직접 뒷받침하는 `doc_id:block_id` 목록이다. 없으면 빈 배열로 취급한다. |
| `source_document_ids` | Concept 근거를 제공한 document id 목록이다. 복구 시 중복을 제거해 합친다. |
| `evidence_claim_ids` | `evidence_units[].evidence_id` 참조 목록이다. ingest에서는 operation id prefix를 붙여 충돌을 막는다. |

추출 결과에 따라 `concept`에는 `aliases`, `mention_reference_ids`,
`display_reference_ids` 같은 추가 metadata가 들어갈 수 있다. 복구기는 이 배열들도
기여 순서대로 중복 제거해 병합한다.

근거와 원문 필드:

| 경로 | 의미와 빈 값 처리 |
| --- | --- |
| `evidence_units[].evidence_id` | 작업 사이에서 겹치지 않는 주장 id다. ingest에서는 `{operation_id}:` prefix가 붙는다. |
| `evidence_units[].claim` | 원문에서 추출하거나 lint가 추가한 주장 본문이다. |
| `evidence_units[].anchor_reference_ids` | 주장을 지지하는 `doc_id:block_id` 목록이다. 근거가 없으면 빈 배열이다. |
| `evidence_units[].related_concept_slugs` | 이 주장이 연결되는 Concept slug 목록이다. |
| `evidence_units[].source_document_id` | 주장의 출처 document id다. lint 자체 판단처럼 직접 출처가 없으면 빈 문자열일 수 있다. |
| `source_blocks[].document_id` | 원문 block이 속한 document id다. |
| `source_blocks[].block_id` | document 안의 block id다. 전역 ref는 두 값을 `document_id:block_id`로 조합한다. |
| `source_blocks[].text` | 해당 operation이 근거로 사용한 원문 block 본문이다. |
| `source_key_points[].text` | Concept Page에 반영할 핵심 포인트 본문이다. |
| `source_key_points[].anchor_reference_ids` | 핵심 포인트를 지지하는 `doc_id:block_id` 목록이다. |

`links[]`의 공통 필드:

| 필드 | 의미와 빈 값 처리 |
| --- | --- |
| `source` | 간선 출발 endpoint다. `source:{document_id}` 또는 `concept:{slug}` 형식이다. |
| `target` | 간선 도착 endpoint다. Concept 관계는 `concept:{slug}`를 사용한다. |
| `relation` | 두 endpoint 사이의 관계 type이다. |
| `evidence` | 관계를 지지하는 `doc_id:block_id` 목록이다. 관계 종류에 따라 없거나 빈 배열일 수 있다. |

Kafka event payload 또는 lint 응답의 `changed_pages`에는 본문을 직접 넣지 않고
key와 hash만 넣는다.

```json
{
  "page_id": "page_c2",
  "page_type": "concept",
  "markdown_key": "wiki/ws/pages/page_c2/ops/op_ingest_A.md",
  "contribution_key": "wiki/ws/pages/page_c2/ops/op_ingest_A.json",
  "content_hash": "sha256:..."
}
```

llmPipeline은 version 또는 revision 번호를 만들지 않는다. Backend가 event payload와
operation 순서를 검증한 뒤 revision, current state와 ingest contribution 활성 여부를
관리한다.

## 5. Ingest와 reingest 저장 순서

ingest 영속화는 다음 순서를 사용한다.

```text
1. Source·Concept page id 확보                 PostgreSQL transaction
2. source_blocks와 현재 Source·Concept 반영      PostgreSQL + current object
3. page link, embedding units, meaning cluster 반영
4. operation Markdown·기여 JSON 저장            불변 key, DB 반영 뒤
5. `pipeline_runs` manifest/status 저장 및 DB commit
6. embedding job 시작
7. ingest worker가 `ai.task.event` 결과 발행
```

Page id 확보와 이후 DB 변경은 같은 PostgreSQL transaction 안에서 실행된다.
operation artifact 저장 실패는 run을 실패시키며 DB transaction도 함께 실패시킨다.
다만 object storage와 PostgreSQL은 원자적이지 않아 current object나 artifact의
미참조 object가 남을 수 있다.

operation artifact는 DB 변경 뒤 마지막 저장 단계다. 따라서 이후 DB 작업이
실패하면 object storage와 DB 사이에 불일치가 생길 수 있으며, artifact를 먼저
써서 현재 Wiki object 갱신을 보호한다는 보장은 현재 계약이 아니다.

### 5.1 reingest 대상 제한

reingest가 기존 Concept을 결과에 유지했다고 해서 모두 이번 operation의 기여는
아니다. 다음 Concept만 이번 operation artifact에 포함한다.

1. 이번 실행에서 새로 생성한 Concept
2. 이번 실행의 기여 JSON이 실제로 만들어진 Concept
3. `same_concept` 결정으로 새 evidence가 추가된 기존 Concept

이전 실행에서 만들어졌고 이번에는 그대로 유지된 Concept은 제외한다. 이렇게 해야
이번 작업이 만들지 않은 기여 JSON을 요구하지 않고, operation 로그가 실제 변경분과
일치한다.

## 6. Ingest 결과 event와 재전달

성공 event의 핵심 payload는 다음과 같다.

```json
{
  "operation_id": "op_ingest_A",
  "operation_type": "ingest",
  "status": "succeeded",
  "workspace_id": "ws",
  "user_id": "user_1",
  "target_document_id": "doc_A",
  "summary": "Wiki ingest를 완료했습니다.",
  "changed_pages": []
}
```

pipeline 자체가 실패해도 `status=failed`, 실패 summary와 빈 `changed_pages`를
event payload로 발행한다. Backend는 이를 `AiTaskResultApplier.applyIngest`에서
operation과 document 상태에 반영한다. Kafka consumer 재전달은 정상 경로이며,
Backend는 `ai_task_result_receipts(event_id, run_id, task_kind)`로 중복을 제거한다.
결과 payload의 operation id·scope·target document가 등록값과 다르면 Backend가
거부하고, Markdown·기여 object key의 workspace·page·operation prefix 또는 본문 hash가
다르면 422 계약 오류로 거부한다. 같은 확정 payload를 다시 받으면 기존 결과를 반환하고 다른
payload는 409 충돌이다.

## 7. Operation 취소와 Concept 페이지 재조립

외부 복구 진입점은 작업 유형별로 분리한다.

```text
POST /wiki/ingest-restore-runs
POST /wiki/lint-restore-runs
```

ingest 취소 command는 `restore_to_operation_id`와 제외할 ingest suffix를 함께
처리한다. lint 취소 command는 `target_operation_id` 하나를 처리한다. Backend는
미리보기에서 취소 대상을 제외한 활성 ingest 상태와 operation 순서로 page마다
남길 기여 목록을 만들고, stale 검증 후 기여를 비활성화한 다음 restore command를
발행한다.

```json
{
  "operation_id": "op_restore_1",
  "restore_to_operation_id": "op_ingest_A2",
  "cancel_operation_ids": ["op_reingest_A3", "op_reingest_A4", "op_reingest_A5"],
  "workspace_id": "ws",
  "source_page": {
    "page_id": "page_source_1",
    "document_id": "doc_A"
  },
  "rebuild_pages": [
    {
      "page_id": "page_c2",
      "keep_contributions": [
        {"operation_id": "op_ingest_A", "document_id": "doc_A"}
      ]
    }
  ],
  "deleted_pages": []
}
```

ingest 취소는 먼저 restore point의 Source snapshot을 restore operation의 새 key로
복사한다. restore point와 현재 상태의 Concept 합집합을 영향 범위로 삼으며, 남은
기여가 있는 page는 재조립하고 없는 page는 삭제 대상으로 반환한다. lint 취소에는
Source 단계가 없다. 두 흐름은 영향받은 각 Concept Page를 다음 순서로 재조립한다.

1. `page_id + operation_id`로 기여 JSON key 계산
2. `keep_contributions` 순서대로 JSON 로드
3. JSON의 `operation_id`, `page_id`가 요청과 일치하는지 검증
4. Concept metadata와 전역 evidence 병합
5. source key point 병합
6. ingest와 lint의 link action을 `replay_supported_links` 규칙으로 재생
7. `ConceptPageAssembler`로 Markdown 재생성
8. restore operation의 새 `.md` key에 저장
9. hash와 최종 지원 간선 반환

결과 예시:

```json
{
  "operation_id": "op_restore_1",
  "restore_to_operation_id": "op_ingest_A2",
  "cancel_operation_ids": ["op_reingest_A3", "op_reingest_A4", "op_reingest_A5"],
  "operation_type": "ingest_restore",
  "status": "succeeded",
  "changed_pages": [
    {
      "page_id": "page_c2",
      "page_type": "concept",
      "markdown_key": "wiki/ws/pages/page_c2/ops/op_restore_1.md",
      "content_hash": "sha256:...",
      "supported_links": []
    }
  ],
  "failed_pages": []
}
```

한 페이지의 JSON이 없거나 손상되어도 다른 페이지 복구를 중단하지 않는다. 해당
페이지를 `failed_pages`에 `reason=contribution_missing`으로 넣고 전체 상태를
`partially_succeeded`로 반환한다.

lint 취소는 대상 lint JSON의 link action과 재조립 결과의 `supported_links`를
비교해 `link_changes`를 계산한다. Concept 재조립이 실패하면 불완전한 지원 집합으로
간선을 추측하지 않고 `concept_rebuild_failed`를 반환한다.

restore point와 취소 suffix 선택, 취소 대상 비활성화, 삭제 page 처리와 복구 결과에
따른 revision/current pointer 변경은 Backend 범위다. llmPipeline은 선택된 Source
snapshot 복사, 남은 Concept 기여 재조립과 lint 간선 변경 계산을 담당한다.
llmPipeline은 restore 결과를 current `wiki_pages`에 반영하면서 해당 page의 embedding
unit을 삭제·재생성하고, restore 뒤 embedding job을 시작한다. 삭제 page는 link,
document link, embedding unit/vector를 정리하고 `status=deleted`로 바꾼다.

## 8. Lint operation 로그

`dry_run=false`인 lint는 `operation_id`가 필수다. lint가 만든 Concept 변경과
간선 변경은 ingest와 같은 `.md`, `.json` object key에 저장하지만 Backend의
`wiki_page_contributions` row는 만들지 않는다.

lint 기여 JSON은 다음 action을 추가로 가진다.

| 필드 | 값·기본값 | 의미 |
| --- | --- | --- |
| `artifact_type` | `lint` | ingest 기여와 구분해 link action 재생 규칙을 선택한다. |
| `document_id` | `lint:{operation_id}` | 원문 document가 없는 lint artifact의 합성 출처 id다. |
| `content_action` | `create` | lint promotion으로 새 Concept을 생성했음을 나타낸다. |
| `content_action` | `append_evidence` | 기존 Concept에 evidence를 추가했음을 나타낸다. |
| `content_action` | `none` | 본문 변경 없이 간선만 변경했음을 나타낸다. |
| `added_links` | 기본 빈 배열 | lint artifact가 지원 집합에 추가하는 간선이다. 각 원소 구조는 ingest의 `links[]`와 같다. |
| `removed_links` | 기본 빈 배열 | lint artifact가 지원 집합에서 제거하는 간선이다. 각 원소 구조는 ingest의 `links[]`와 같다. |

lint JSON의 나머지 `schema_version`, `operation_id`, `page_id`, `concept`,
`evidence_units`, `source_blocks`, `source_key_points`는 ingest 기여 JSON과 같은 의미다.
lint artifact는 본문 action 또는 link action 중 하나 이상이 있을 때만 저장한다.

본문 변경과 간선 변경이 하나의 lint artifact JSON에 기록되므로 ingest 복구와 lint
복구는 서로 다른 command를 사용하되 같은 Concept 재조립기를 공유한다. Backend는
재조립 대상에 남길 ingest contribution만 전달하고, lint 복구는 대상 lint JSON의
link action을 재생해 `link_changes`를 계산한다.

non-dry-run lint 순서:

```text
1. PostgreSQL transaction 시작
2. reconciliation과 고아 간선 DB 변경 실행       아직 미커밋
3. lint operation Markdown·기여 JSON 저장
4. 일일 lint log 저장
5. active/archive cluster object 반영
6. transaction commit
```

3번 이후 object/log/object 변경이 실패하면 lint transaction의 DB 변경은 rollback된다.
Object storage와 DB의 완전한 원자성은 없으므로 삭제된 orphan object가 남을 수 있지만,
구현은 이미 쓴 lint object key를 예외 시 삭제하도록 시도한다.

## 9. 고아 간선 판정과 제거

고아 간선 lint는 `wiki_page_contributions`의 ingest contribution row를
`sequence_revision` 순서로 읽는다. lint artifact row가 별도로 생성되는 것은 아니다.

- 모든 contribution: 과거 operation 로그로 관리된 적이 있는 간선 판정
- `active=true` contribution: 현재 간선을 지지하는 ingest operation 판정

활성 contribution JSON은 `replay_supported_links`로 operation 순서에 따라 재생한다.

```text
ingest/document artifact `links` → 지원 집합에 추가
lint artifact `removed_links`    → 지원 집합에서 제거
lint artifact `added_links`      → 지원 집합에 추가
```

`orphan_link_lint.find_orphan_links`는 `active_contribution_json`에 이 재생 결과를
사용하고, `managed_contribution_json`에서는 각 artifact의 `links`, `added_links`,
`removed_links`를 모두 관리 간선으로 확인한다.

예를 들어 ingest contribution이 다음과 같으면 최종 지원 집합에는 `A → B`가 남는다.

```text
op-A ingest: A → B 추가
op-B ingest: A → B 추가
```

`op-A`와 `op-B`가 모두 비활성화될 때 최종 지원 집합에서 `A → B`가 사라진다.

현재 DB 간선은 다음 조건 중 하나일 때만 고아 후보가 된다.

1. source 또는 target page가 삭제 상태다.
2. operation 로그가 관리한 간선이지만 활성 기여 재생 결과 아무 작업도 지지하지
   않는다.

기여 로그 도입 전에 만들어져 operation 로그에서 관리된 적이 없는 legacy 간선은
로그가 없다는 이유만으로 삭제하지 않는다. 후보와 실제 삭제 결과는 각각
`orphan_link_candidates`, `removed_orphan_links`에 반환하고 일일 lint log에도
기록한다.

## 10. llmPipeline과 Backend 책임 경계

| llmPipeline | Backend/Flyway |
| --- | --- |
| 기여 JSON 생성과 ref 전역화 | operation 생성과 사용자 권한 검증 |
| operation Markdown·JSON 저장 | `wiki_page_contributions` schema와 row 저장 |
| content hash와 changed_pages 생성 | revision, current pointer, sequence 관리 |
| Kafka 결과 event payload와 content hash 생성 | event receipt·payload·prefix·hash 검증 |
| Source snapshot 복사와 keep contribution 기반 Concept 재조립 | 취소 대상·직전 Source·활성 ingest contribution 결정 |
| lint action과 재조립 지원 집합을 비교해 `link_changes` 계산 | 복구 event의 revision·간선 변경을 DB에 반영 |
| 활성 contribution 기반 고아 간선 계산·삭제 | restore 결과 적용과 page 활성·삭제 상태 확정 |

llmPipeline은 Backend가 Flyway로 제공하는 table을 소비하지만 migration을 생성하지
않는다. 특히 `wiki_page_contributions.active`, `object_key`, `sequence_revision`이
ingest 복구와 고아 간선 lint의 입력이다. lint artifact는 object storage에 있고
Backend operation change가 lint 페이지 변경을 감사한다.

## 11. 실패 경계와 운영상 주의점

- object storage와 PostgreSQL은 하나의 transaction이 아니다. 실패한 DB 작업의
  미참조 operation object가 남을 수 있다.
- operation object는 불변 key다. 복구도 restore operation의 새 key를 사용하며 기존
  operation object를 덮어쓰지 않는다.
- Kafka event consumer 오류는 worker 재전달 대상이며, Backend receipt가 중복을 막는다.
- 동일 operation의 동일 payload는 멱등 처리하고 다른 payload는 409 충돌이다.
- contribution JSON은 Concept 재조립의 입력이다. Backend event 반영이 끝난 뒤에도
  object를 삭제하면 안 된다.
- 활성 기여 기반 Concept 의미 전체 재작성과 embedding의 완전한 원자 갱신은 별도
  후속 범위다. 이 문서의 복구는 Backend가 선택한 기여 목록을 재조립하는 흐름이다.

## 관련 문서

- `docs/backlog/llm-wiki/flows/ingest.md`
- `docs/backlog/llm-wiki/flows/lint.md`
- `docs/api/ai/pipeline.md`
- `docs/api/ai/wiki.md`
- `docs/adr/0012-ai-operation-log-and-rollback.md`
- `docs/adr/0014-wiki-lint-reconciliation.md`
