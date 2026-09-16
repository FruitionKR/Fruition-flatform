# Query/Ingest Spring 및 Frontend 작업 목록

## 목적

llmPipeline의 최신 query/ingest 흐름을 제품 화면과 Spring API에서 안정적으로 사용할 수 있게 만드는 작업 목록이다.
핵심은 답변 자체보다 `어떤 문서와 어떤 근거를 사용했는지`를 사용자가 확인할 수 있게 하는 것이다.

## 기준 플로우

제품에서 맞춰야 할 기준 흐름은 다음과 같다.

1. 사용자가 문서를 업로드한다.
2. Spring이 문서를 저장하고 안정적인 `document_id`를 만든다.
3. Spring이 `document_id`와 원문 내용을 pipeline run에 전달한다.
4. pipeline이 source block, source page, concept page, embedding unit을 만든다.
5. Spring/Frontend는 pipeline run 상태와 ingest 결과를 조회한다.
6. 사용자가 질문한다.
7. pipeline query는 source/concept page를 찾고, page 내부 unit 중 질문과 맞는 evidence를 선택한다.
8. 내부 근거가 부족하거나 외부 공개 지식이 필요한 경우 evaluator/web search가 web evidence를 보강한다.
9. 최종 응답은 answer, citation, evidence, related page, source block을 함께 내려준다.
10. Frontend는 citation 클릭으로 evidence와 원문 block을 확인하게 한다.

이 흐름에서 Spring/Frontend가 하면 안 되는 일은 pipeline의 scoring/evidence 선택 로직을 재구현하는 것이다.
Spring/Frontend는 pipeline이 준 구조화 결과를 손실 없이 저장하고 보여주는 쪽을 우선한다.

## 현재 Pipeline 계약에서 확인된 사실

이번 코드 변경 기준으로 Spring/Frontend가 알아야 할 실제 계약은 다음과 같다.

### Pipeline run request

`POST /pipeline/runs` 입력은 셋 중 하나만 허용된다.

- `document_id`
- `input_markdown`
- `input_path`

추가 입력:

- `input_name`
- `wiki_evaluator_system_prompt`
- `wiki_evaluation_loop`
- `max_eval_attempts`
- `save_debug_json`
- `log_callback_url`
- `wait`

중요 변경:

- `input_markdown`과 `input_path`도 pipeline 내부에서 `documents` row를 생성한다.
- `document_id` 입력은 object storage에서 markdown/text를 읽어오지만, 더 이상 `runs/_api_inputs/*.md` 임시 파일을 만들지 않는다.
- `wait=false`면 응답의 `manifest`는 `null`이고, 백그라운드 완료 후 `GET /pipeline/runs/{runId}`로 확인해야 한다.
- `wait=true`면 요청 응답에는 메모리 manifest가 포함될 수 있지만, DB에 저장되는 `pipeline_runs.manifest`는 markdown 본문과 source block 원문이 제거된 축소 manifest다.

### Pipeline run response

현재 `PipelineRunOut`:

```json
{
  "run_id": "...",
  "status": "running | succeeded",
  "manifest": null,
  "output_dir": "runs/api_...",
  "log_path": "runs/api_.../pipeline.log"
}
```

주의:

- `output_dir`와 `log_path`는 아직 응답에 남아 있지만, 제품 기능이 중간 JSON/MD 파일에 의존하면 안 된다.
- 기본 실행에서 유지되는 파일은 `pipeline.log`뿐이다.
- `source_blocks.json`, `normalized.json`, `wiki/links.json`, `review_report.md`, `manifest.json`, `wiki/*.md`는 기본 생성 대상이 아니다.
- debug raw 파일은 `save_debug_json=true`에서만 생성된다.

### Query request

현재 `POST /query` request:

```json
{
  "question": "질문",
  "request_id": "optional-client-request-id",
  "log_callback_url": "optional-callback-url",
  "recent_conversation_summary": "optional-summary",
  "reference_context": {}
}
```

### Query response

현재 pipeline `QueryResponse`는 다음 필드만 직접 반환한다.

- `answer`
- `related_pages[]`
  - `id`
  - `page_type`
  - `title`
  - `slug`
  - `relevance_score`
  - `role`
  - `depth`
- `evidence_snippets[]`
  - `rank`
  - `source_document_id`
  - `source_block_ids`
  - `text`
- `graph_context`
- `traversal_paths[]`

주의:

- `retrieval_summary`는 domain 객체에는 있지만 HTTP response에는 아직 포함되지 않는다.
- `QueryEvaluation` 결과도 HTTP response에는 아직 포함되지 않는다.
- `evidence_snippets`에는 현재 `page_id`, `page_type`, `page_title`, `score`가 직접 없다.
- Frontend에서 evidence의 page/source를 안정적으로 표시하려면 Spring이 `source_document_id`와 `source_block_ids`로 보강 조회하거나, pipeline response 확장이 필요하다.

### Query event callback

`request_id`와 `log_callback_url`을 주면 pipeline은 query 진행 이벤트를 callback으로 보낼 수 있다.
Spring은 이 이벤트를 저장하고 Frontend는 디버그/진행 상태 화면에서 볼 수 있어야 한다.

주요 event stage:

- `query_started`
- `query_contextualized`
- `query_rewritten`
- `wiki_loaded`
- `retrieval_markdown_loaded`
- `retrieval_scored`
- `seeds_selected`
- `graph_traversed`
- `markdown_loaded`
- `context_built`
- `answer_generated`
- `query_evaluated`
- `query_evaluation_failed`
- `web_search_started`
- `web_search_failed`
- `web_search_empty`
- `web_search_answer_generated`

Frontend 표시 우선순위:

- 기본 화면에는 최종 answer/evidence만 표시한다.
- 상세/디버그 화면에는 event timeline을 표시한다.
- 멀티턴 디버깅에는 `query_contextualized.contextual_question`이 특히 중요하다.

## 현재 Spring 코드와 DB 대조 결과

이 섹션은 2026-06-28 현재 코드 기준으로 문서의 작업 목록을 다시 대조한 결과다.

### 이미 구현된 Spring 기능

- 문서 업로드 후 Spring `documents.id`를 pipeline `document_id`로 전달한다.
  - `DocumentService.upload()`가 `documents` row를 저장한다.
  - transaction commit 이후 `DocumentProcessingRequester`가 `POST /pipeline/runs`에 `{"document_id": "..."}`를 보낸다.
- 원문 block 조회 API가 있다.
  - `GET /api/documents/{document_id}/blocks`
  - `source_blocks`는 pipeline이 적재하고 Spring은 조회한다.
- Query 응답의 기본 필드는 Spring 응답에 포함된다.
  - `answer`
  - `related_pages`
  - `evidence_snippets`
  - `graph_context`
  - `traversal_paths`
- Query 결과 저장 일부가 구현되어 있다.
  - `chat_messages`에 user/assistant 메시지를 저장한다.
  - `chat_message_references`에 `evidence_snippets` 기반 source block reference를 저장한다.
  - `chat_message_related_pages`에 `related_pages`를 저장한다.
- 비동기 query run과 SSE callback endpoint가 있다.
  - `POST /api/query/runs`
  - `GET /api/query/runs/{requestId}`
  - `GET /api/query/runs/{requestId}/events`
  - `POST /api/query/runs/{requestId}/events/callback`

### 현재 Spring 코드에서 부족한 부분

- `DocumentProcessingRequester`는 pipeline 응답의 `run_id`를 로그로만 남기고 Spring DB에 저장하지 않는다.
  - 따라서 Spring API만으로 문서와 pipeline run을 안정적으로 연결하기 어렵다.
- `QueryRunStore`와 `QueryEventBroker`는 메모리 기반이다.
  - 서버 재시작, TTL 만료 후에는 query run 상태와 event timeline을 복원할 수 없다.
  - 제품 데이터로 쓰려면 DB 테이블이 필요하다.
- Spring `QueryRequest`는 현재 `question`만 받는다.
  - pipeline `/query`는 `recent_conversation_summary`, `reference_context`, `request_id`, `log_callback_url`을 받을 수 있지만, 일반 `POST /api/query` 경로에서는 멀티턴 context가 전달되지 않는다.
  - 비동기 query run 경로도 `QueryRunService.start(question)`만 받아 context를 저장하거나 전달하지 않는다.
- `PipelineQueryRequester.QueryPayload`는 `question`, `request_id`, `log_callback_url`만 보낸다.
  - pipeline이 원하는 `recent_conversation_summary`, `reference_context`를 Spring에서 만들더라도 현재 requester로는 전달할 수 없다.
- Query evaluator 결과는 Spring 응답이나 DB에 직접 저장되지 않는다.
  - pipeline은 `query_evaluated` event로 `route`, `evidence_relevance`, `reason`, `web_query`를 보낼 수 있다.
  - Spring은 현재 event를 SSE로 중계하지만 영속 저장하지 않으므로 query 상세 화면에서 안정적으로 복원할 수 없다.
- `retrieval_summary`는 pipeline HTTP response에 없고 Spring DTO에도 없다.
  - 화면에서 `used_source_count`, `used_concept_count`, `stop_reason` 같은 값을 요구하면 pipeline response 확장 또는 event 기반 조립이 필요하다.
- Spring은 현재 JPA `ddl-auto=update`에 의존한다.
  - 개발 환경에서는 컬럼/테이블이 자동 생성될 수 있지만, 운영/공유 DB에서는 Flyway/Liquibase 같은 명시적 migration이 필요하다.

### pipeline 코드가 요구하는 DB

pipeline `init_db()`와 query repository 기준으로 아래 테이블은 ingest/query가 실제로 사용한다.

| 테이블 | 사용 주체 | 현재 용도 | Spring 작업 |
| --- | --- | --- | --- |
| `documents` | Spring + pipeline | 업로드 문서, inline/input path 문서 추적 | 기존 Spring entity와 pipeline insert 컬럼이 계속 호환되어야 함 |
| `source_blocks` | pipeline write, Spring read | citation 원문 block 조회 | 이미 조회 API 있음. 운영 migration 필요 |
| `wiki_pages` | pipeline write, Spring read | source/concept page | 기존 Spring entity와 pipeline upsert 계약 유지 |
| `document_wiki_links` | pipeline write, Spring read | 문서와 source/concept page 연결 | `GET /api/documents/{id}`에서 이미 사용 |
| `wiki_page_links` | pipeline write, Spring read | graph edge | graph/query 조회에서 사용 |
| `pipeline_runs` | pipeline write, Spring read 필요 | ingest run 상태, 축소 manifest, error | Spring 조회 API와 문서 연결 저장 필요 |
| `wiki_page_embeddings` | pipeline embedding job write | page 단위 dense embedding 상태 | 운영 migration 필요 |
| `wiki_embedding_vectors` | pipeline write/query read | canonical representation dedupe, vector 저장 또는 pending 상태 | 운영 migration 필요 |
| `wiki_embedding_units` | pipeline write/query read, Spring read 필요 | page 내부 evidence 후보와 source block refs | 운영 migration 및 조회 API 필요 |
| `chat_messages` | Spring write/read | user/assistant 메시지 | 이미 구현 |
| `chat_message_references` | Spring write/read | 답변 citation/evidence source block reference | 이미 구현 |
| `chat_message_related_pages` | Spring write/read | 답변과 관련 page 목록 | 이미 구현 |

추가로 제품 기능을 위해 Spring이 만들어야 하는 DB 후보는 아래와 같다.

| 테이블 또는 저장 위치 | 필요한 이유 | 최소 필드 |
| --- | --- | --- |
| `query_runs` | 비동기 query 상태를 서버 재시작 후에도 복원 | `request_id`, `status`, `question`, `result_json`, `error_message`, `created_at`, `started_at`, `completed_at` |
| `query_events` | event timeline, evaluator route, web search, contextualized question 복원 | `id`, `request_id`, `sequence`, `stage`, `message`, `data_json`, `received_at` |
| `query_contexts` 또는 `query_runs` 컬럼 | 멀티턴 context와 재현성 보존 | `request_id`, `thread_id`, `original_question`, `recent_conversation_summary`, `reference_context_json` |
| `query_evaluations` 또는 `query_events`에서 파생 저장 | query 상세 화면에서 evaluator 결과를 빠르게 표시 | `request_id`, `route`, `evidence_relevance`, `citation_evidence_alignment`, `unsupported_refusal_accuracy`, `reason`, `feedback`, `web_query` |

1차 구현에서는 `query_events.data_json`에 원본 event를 저장하고, `query_evaluated` stage에서 evaluator 값을 읽어 query 상세 응답에 조립해도 된다. 다만 검색/필터링이 필요해지면 `query_evaluations`처럼 분리하는 편이 낫다.

## 멀티턴 Query 기준

현재 pipeline query API는 멀티턴 자체를 message history 전체로 받지 않는다.
대신 Spring/Frontend가 대화 상태를 요약하고 참조 컨텍스트를 만들어 `POST /query`에 함께 전달하는 구조다.

pipeline request 필드:

```json
{
  "question": "그거랑 RAG 차이는?",
  "recent_conversation_summary": "사용자는 Persistent Wiki와 RAG의 차이를 이어서 묻고 있다.",
  "reference_context": {
    "active_topic": {
      "canonical": "Persistent Wiki",
      "aliases": ["지속적 위키"]
    },
    "recent_concepts": ["Persistent Wiki", "RAG"],
    "referents": {
      "그거": {
        "canonical": "Persistent Wiki",
        "aliases": ["지속적 위키"]
      }
    }
  }
}
```

pipeline 내부 동작:

- `question`은 사용자가 실제로 입력한 원문 질문으로 유지한다.
- `recent_conversation_summary`와 `reference_context`를 이용해 검색용 질문을 보강한다.
- `referents`에 질문 속 표현이 들어 있으면 해당 값을 우선 검색어에 넣는다.
  - 예: `그거` → `Persistent Wiki`, `지속적 위키`
- 답변 context에는 원 질문과 보강된 검색 질문이 분리되어 들어간다.
  - `# User Question`
  - `# Resolved Retrieval Question`
- evidence 선택은 보강된 검색 질문을 사용하되, 최종 답변은 원 질문에 답하는 형태로 생성한다.

중요한 설계 기준:

- Frontend가 매 턴의 raw message 전체를 그대로 pipeline에 넘기는 방식이 아니다.
- Spring이 대화 thread 상태를 보고 요약과 참조 해소 결과를 만들어 pipeline에 넘긴다.
- pipeline은 reference context를 신뢰하되, 최종 evidence/citation은 source/concept/web 근거에서 다시 선택한다.
- 멀티턴 보강은 내부 검색과 web 보강 모두에 영향을 준다. 예를 들어 `그거를 쿠버네티스 오퍼레이터로 배포하려면 어떻게 해?`는 `그거 = Persistent Wiki / LLM Wiki`가 풀린 뒤 `internal_web_augmented` route로 갈 수 있다.

## Spring Boot 작업

### 1. Pipeline run 생성 계약 정리

Spring은 문서 업로드 후 pipeline에 안정적인 `document_id`를 전달해야 한다.

필요 작업:

- [완료] Markdown 업로드 후 Spring `documents.id`를 pipeline `document_id`로 전달한다.
- [완료] pipeline run 응답의 `run_id`를 `documents.pipeline_run_id`에 저장한다. (commit `263a935`)
- inline text, local path, uploaded file ingest가 같은 추적 모델을 쓰도록 정리한다.
- `input_markdown` 또는 `input_path`를 직접 호출하는 내부/관리자 기능이 있다면, pipeline이 생성한 `api-inline-{run_id}` 또는 `api-file-{run_id}` document id를 Spring에서도 추적할지 결정한다.
- [완료] `wait=false` 기본 흐름에서는 `manifest`가 없다는 전제로 callback 기반 상태 갱신을 구현한다. `POST /api/documents/{id}/pipeline-events`로 heartbeat 수신. (commit `263a935`)
- `wait=true` 응답의 full manifest를 제품 저장소에 그대로 저장하지 않는다. markdown 본문과 source block 원문은 DB/object storage에 이미 저장되며, manifest는 디버그/관리 정보로만 취급한다.

검증 기준:

- 업로드한 문서 1개가 pipeline에서 source page 1개 이상으로 저장된다.
- `run_id`로 처리 상태를 조회할 수 있다.
- `input_markdown`으로 실행해도 별도 임시 파일 없이 `documents`, `wiki_pages`, `source_blocks`, `wiki_embedding_units`가 생성된다.

### 1-1. 멀티턴 Query context 생성

Spring은 채팅 thread의 최근 상태를 pipeline request에 맞는 `recent_conversation_summary`와 `reference_context`로 변환해야 한다.

필요 작업:

- chat thread 단위로 최근 대화 요약을 저장하거나 즉시 생성한다.
- 현재 활성 주제, 최근 concept, 대명사/지시어 referent를 추출한다.
- Spring `QueryRequest`에 최소 `thread_id`를 추가하거나, 비동기 query run 생성 API에서 thread id를 받는다.
- `PipelineQueryRequester.QueryPayload`에 `recent_conversation_summary`, `reference_context`를 추가한다.
- `QueryService.query()`와 `QueryRunService.start()`가 context payload를 받아 pipeline에 전달하도록 확장한다.
- `POST /query` 호출 시 다음 필드를 함께 전달한다.
  - `question`
  - `recent_conversation_summary`
  - `reference_context`
  - `request_id`
  - `log_callback_url`
- 사용자 원문 질문과 pipeline에 넘긴 context payload를 함께 저장한다.
- pipeline 응답에는 현재 resolved retrieval question이 별도 response field로 내려오지 않으므로, 1차 구현에서는 request payload를 Spring query log에 보존한다.

권장 `reference_context` 구조:

```json
{
  "active_topic": {
    "canonical": "Persistent Wiki",
    "aliases": ["지속적 위키", "LLM Wiki"]
  },
  "recent_concepts": ["Persistent Wiki", "RAG"],
  "referents": {
    "그거": {
      "canonical": "Persistent Wiki",
      "aliases": ["지속적 위키"]
    }
  }
}
```

검증 기준:

- 사용자가 `그거랑 RAG 차이는?`처럼 후속 질문을 보내면 Spring이 `그거`를 `Persistent Wiki`로 해소해 pipeline에 전달한다.
- pipeline event 중 `query_contextualized`가 발생하면 Spring log 화면에서 보강된 검색 질문을 확인할 수 있다.
- 같은 질문이라도 context가 다른 thread에서는 다른 referent가 전달될 수 있어야 한다.
- context가 없거나 확신이 낮으면 `reference_context`를 억지로 채우지 않고 단일턴 질문으로 보낸다.

### 2. Ingest 상태와 로그 API

프론트가 처리 중/성공/실패/경고를 볼 수 있어야 한다.

필요 작업:

- [완료] `pipeline_run_id` — `documents` 컬럼 추가, `DocumentListResponse`/`DocumentDetailResponse` 포함 (commit `263a935`)
- [완료] `processing_started_at` — `documents` 컬럼 추가 (commit `263a935`)
- [완료] `processing_updated_at` — `documents` 컬럼 추가, `POST /api/documents/{id}/pipeline-events` callback으로 갱신 (commit `263a935`)
- [완료] `processing_state` (`starting`/`running`/`stalled`) — `pipeline_run_id` 없으면 `starting`, 60초 이상 heartbeat 없으면 `stalled`. `DocumentProcessingState` enum 추가, 응답 포함 (commit `263a935`)
- `processed_at`
- `error_message`
- warning 또는 failed file 목록
- `pipeline_runs.manifest` 축소본
  - `source_page` metadata
  - `concept_pages` metadata
  - `links`
  - `pipeline_log`
  - `warnings`
- `save_debug_json` 사용 여부
- Spring에서 `pipeline_runs`를 조회하는 API를 추가한다.
  - pipeline DB에는 이미 `pipeline_runs` 테이블이 있다.
  - Spring이 같은 DB를 읽는다면 JPA entity 또는 JDBC 조회 DTO가 필요하다.
- [완료] `DocumentProcessingRequester`가 받은 `run_id`를 문서 상세 응답에서 확인할 수 있게 저장한다. (commit `263a935`)
- callback event 저장 테이블을 query event와 분리할지 공용 event 테이블로 둘지 결정한다. (미결)

권장 endpoint:

- [완료] `GET /api/documents/{documentId}` — `pipeline_run_id`, `processing_state` 포함 (commit `263a935`)
- [완료] `POST /api/documents/{documentId}/pipeline-events` — heartbeat callback 신규 추가 (commit `263a935`)
- [완료] `DELETE /api/documents/{documentId}` — 문서·MinIO 오브젝트·queue 항목 삭제 (commit `9c8d262`)
- `GET /api/pipeline/runs/{runId}`
- `GET /api/pipeline/runs/{runId}/logs`
- `GET /api/pipeline/runs/{runId}/events`

검증 기준:

- ingest 실패 문서와 실패 사유가 화면에 전달된다.
- cleaned replacement를 썼다면 원본과 정리본의 연결 정보를 볼 수 있다.
- 기본 실행 후 run 폴더에 JSON/MD 산출물이 없어도 Spring 화면이 정상 표시된다.
- `pipeline.log` 또는 callback event만으로 진행 상태를 표시할 수 있다.

### 3. Query 응답 DTO 저장/확장

pipeline query 응답의 evidence 정보를 Spring 응답에서 손실 없이 내려야 한다.

현재 pipeline에서 그대로 받아 저장해야 하는 필드:

- `answer`
- `related_pages[]`
  - `id`
  - `page_type`
  - `title`
  - `slug`
  - `relevance_score`
  - `role`
  - `depth`
- `evidence_snippets[]`
  - `rank`
  - `source_document_id`
  - `source_block_ids`
  - `text`
- `graph_context`
- `traversal_paths[]`
- 멀티턴 디버깅을 위해 Spring 자체 응답 또는 query log에는 다음 값을 보존한다.
  - `original_question`
  - `recent_conversation_summary`
  - `reference_context`
  - `contextualized_question` 또는 pipeline event의 `query_contextualized.contextual_question`

현재 Spring 코드 상태:

- `answer`, `related_pages`, `evidence_snippets`, `graph_context`, `traversal_paths`는 `QueryResponse`로 반환한다.
- `chat_message_references`에는 `source_document_id`, `source_block_ids`, `text`, `rank` 기반 reference를 저장한다.
- `chat_message_related_pages`에는 `related_pages`를 저장한다.
- 멀티턴 context, contextualized question, evaluator 결과는 아직 DB에 저장하지 않는다.

제품 표시를 위해 Spring에서 보강하거나 pipeline에 추가 요청해야 하는 필드:

- `retrieval_summary`
  - domain에는 있지만 HTTP response에 아직 없음
  - `used_source_count`, `used_concept_count`, `stop_reason`을 화면에 보여주려면 response 확장 필요
- `evaluation`
  - evaluator route, evidence relevance, web query는 event에는 남지만 response에는 아직 없음
  - query 결과 상세 화면에 보여주려면 Spring event log에서 조립하거나 pipeline response 확장 필요
- evidence별 page metadata
  - 현재 `evidence_snippets`에는 `page_id`, `page_type`, `page_title`, `score`가 없음
  - `source_document_id + source_block_ids`로 source block을 찾아 page metadata를 보강해야 함
- web evidence 식별자
  - related page의 `page_type=web` 또는 `id=web:*`를 기준으로 표시
  - evidence snippet만으로 내부/web 타입을 안정적으로 구분하려면 response 확장 검토 필요

검증 기준:

- 답변의 `[N]` citation을 클릭하면 `evidence_snippets.rank == N`인 근거를 찾을 수 있다.
- source와 concept 근거가 둘 다 내려온다.
- 후속 질문 결과에서 원문 질문과 참조 해소에 사용된 context를 함께 추적할 수 있다.
- web 보강 결과에서 내부 evidence와 web evidence를 구분해서 표시할 수 있다.
- `stop_reason`과 evaluator route를 query 상세/디버그 화면에서 확인할 수 있다.

### 4. Source block 조회 API

citation이 가리키는 원문 위치를 열 수 있어야 한다.

권장 endpoint:

- `GET /api/documents/{documentId}/blocks?ids=B0001,B0002`
- `GET /api/wiki/pages/{pageId}`
- `GET /api/wiki/units?sourceDocumentId={documentId}`
- `GET /api/wiki/units?pageId={pageId}`
- `GET /api/wiki/pages/{pageId}/markdown`

검증 기준:

- evidence의 `source_block_ids`로 원문 블록을 조회할 수 있다.
- 프론트가 해당 블록을 highlight할 수 있다.
- concept evidence인 경우에도 `source_document_id`와 `source_block_ids`를 통해 원 source block으로 돌아갈 수 있다.
- `wiki_embedding_units`를 조회해 어떤 unit이 evidence 후보였는지 확인할 수 있다.

### 5. DB migration 정리

pipeline이 만든 신규 테이블을 운영 DB에서 재현 가능하게 해야 한다.

필요 테이블:

- `pipeline_runs`
- `wiki_page_embeddings`
- `wiki_embedding_vectors`
- `wiki_embedding_units`
- `query_runs`
- `query_events`
- `query_contexts` 또는 `query_runs`의 context 컬럼
- 필요 시 `query_evaluations`

필요 작업:

- Spring이 DB schema를 소유한다면 Flyway/Liquibase migration을 추가한다.
  - 현재 `spring.jpa.hibernate.ddl-auto=update`는 개발 편의로만 취급한다.
  - 운영/공유 DB에서는 JPA 자동 변경 대신 migration 파일로 재현해야 한다.
- pipeline이 schema를 소유한다면 Spring 문서에 조회 전용 계약을 명시한다.
- pipeline `init_db()`가 만든 테이블 정의를 Spring migration과 맞춘다.
- `pipeline_runs`는 Spring에서 문서 처리 상태 조회에 필요하다.
- `wiki_page_embeddings`는 page 단위 embedding job 상태 확인에 필요하다.
- canonical representation dedupe 기준인 `embedding_model + representation_hash` unique 정책을 유지한다.
- `wiki_embedding_units.page_id` index를 유지한다.
- `wiki_embedding_units.embedding_vector_id` index를 유지한다.
- `wiki_embedding_units.source_document_id` 기준 조회가 필요하면 Spring migration에서 추가 index를 검토한다.
- `wiki_embedding_vectors.embedding_vector`는 nullable이다. dense vector가 아직 없더라도 row가 생성되는 상태를 정상으로 취급한다.
- `wiki_embedding_vectors.status='pending'`은 오류가 아니라 vector 생성 전 canonical text 저장 상태다.
- `query_runs.request_id`는 unique해야 한다.
- `query_events`는 `request_id + sequence` 또는 `request_id + received_at + stage`로 정렬 가능해야 한다.
- `query_events.data_json`은 `jsonb`로 저장해 `query_contextualized`, `query_evaluated`, `web_search_*` event를 원본 손실 없이 보존한다.
- `reference_context`는 고정 컬럼으로 쪼개기보다 1차에서는 `jsonb`로 저장한다.

검증 기준:

- 깨끗한 DB에서 migration 후 ingest/query가 성공한다.
- 같은 representation text가 여러 page에서 반복되어도 vector row는 중복 생성되지 않고 unit link만 추가된다.
- Spring 재시작 후에도 query run 상태와 event timeline을 조회할 수 있다.
- `query_evaluated` event의 route와 `web_query`를 query 상세 화면에서 복원할 수 있다.

### 6. Web search 및 evaluator 설정 노출

web search는 fallback만이 아니라 내부 근거와 외부 지식이 함께 필요한 질문에서 보강으로 쓰인다.

필요 작업:

- 환경변수 또는 설정 테이블로 evaluator/web search mode를 관리한다.
- 운영에서 web search off/on 상태가 명확히 보이게 한다.
- web evidence가 answer/evidence 응답에 포함되는지 확인한다.
- 다음 환경변수를 배포 설정에 반영한다.
  - `QUERY_EVALUATOR_MODE`
  - `QUERY_EVALUATOR_PROMPT`
  - `QUERY_EVALUATOR_MODEL`
  - `QUERY_EVALUATOR_TIMEOUT_SECONDS`
  - `QUERY_EVALUATOR_MAX_TOKENS`
  - `QUERY_WEB_SEARCH_MODE`
  - `QUERY_WEB_SEARCH_MAX_RESULTS`
  - `QUERY_WEB_SEARCH_TIMEOUT_SECONDS`
  - `QUERY_WEB_SEARCH_API_KEY` 또는 `TAVILY_API_KEY`
  - `QUERY_MIN_INTERNAL_RELEVANCE_SCORE`
- evaluator가 `web_fallback` 또는 `internal_web_augmented`를 반환하면 Spring query log에 route와 `web_query`를 저장한다.

검증 기준:

- 내부 문서에 일부 근거가 있고 외부 공개 지식이 필요한 질문에서 `internal_web_augmented` 성격의 응답을 확인할 수 있다.
- web search off 상태에서는 evaluator가 web route를 요구해도 시스템이 실패하지 않고 내부 근거 기반 응답 또는 unsupported로 남는다.

### 7. Query event 저장

query callback event는 단순 로그가 아니라 멀티턴/웹보강/평가 디버깅에 필요한 제품 데이터다.

필요 작업:

- Spring이 `request_id`를 생성해 `POST /query`에 전달한다.
- Spring이 `log_callback_url`을 제공하고 event를 저장한다.
  - 현재 코드는 SSE 중계와 메모리 버퍼까지만 제공한다.
  - 제품 기능으로 쓰려면 `query_events` 같은 DB 저장소가 필요하다.
- event 저장 모델은 최소 다음 필드를 가진다.
  - `request_id`
  - `sequence`
  - `stage`
  - `message`
  - `data_json`
  - `received_at`
- 같은 request 안에서 stage 순서를 유지한다.
- query response와 event log를 같은 request id로 연결한다.
- `query_evaluated` event는 evaluator 결과 저장의 1차 source로 취급한다.
- `query_contextualized` event는 멀티턴 참조 해소 디버깅의 1차 source로 취급한다.

검증 기준:

- `query_contextualized`, `query_evaluated`, `web_search_started`, `web_search_answer_generated` 이벤트를 query 상세 화면에서 확인할 수 있다.
- evaluator 실패 이벤트가 있어도 최종 query 자체가 무조건 실패로 표시되지 않는다.
- 서버를 재시작해도 완료된 query run의 event timeline을 다시 조회할 수 있다.

## Frontend 작업

### 1. Query 결과 화면

사용자가 답변과 근거 연결을 바로 확인해야 한다.

필요 UI:

- 답변 본문
- citation marker 클릭
- evidence panel
- related source/concept 목록
- source 문서 열기
- concept page 열기
- stop reason / route / web 사용 여부를 보여주는 상세 정보 영역
- pipeline event timeline을 여는 디버그 drawer

검증 기준:

- `[1]`을 클릭하면 rank 1 evidence가 선택된다.
- evidence text, page title, source block id가 함께 보인다.
- citation이 없는 답변이면 evidence panel을 억지로 연결하지 않고 “답변에 인용된 근거 없음” 상태를 보여준다.

### 1-1. 멀티턴 질문 UX

Frontend는 사용자가 후속 질문을 자연스럽게 입력할 수 있게 하되, pipeline에 필요한 context는 Spring이 만들 수 있도록 충분한 thread 정보를 유지해야 한다.

필요 UI/동작:

- chat thread id를 모든 query 요청에 포함한다.
- 사용자가 `그거`, `이거`, `그 방식`, `앞에서 말한 것` 같은 후속 질문을 입력해도 같은 thread의 맥락으로 Spring에 전달한다.
- 답변 화면에는 기본적으로 자연스러운 답변만 보여주고, 디버그/상세 보기에서 참조 해소 정보를 확인할 수 있게 한다.
  - 원 질문
  - active topic
  - referent mapping
  - pipeline event의 `query_contextualized.contextual_question`
- 사용자가 참조 해소가 틀렸다고 느낄 때 다음 질문에서 주제를 명시하거나 thread topic을 바꿀 수 있는 UX를 제공한다.

검증 기준:

- `Persistent Wiki가 뭐야?` 다음에 `그거랑 RAG 차이는?`를 물으면 같은 thread에서는 Persistent Wiki 기준 답변이 나온다.
- 새 thread에서 같은 `그거랑 RAG 차이는?` 질문을 보내면 context 부족 상태로 처리되거나 사용자가 주제를 명확히 입력하도록 유도된다.
- 멀티턴으로 web 보강이 발생한 경우에도 citation/evidence panel은 내부 근거와 web 근거를 구분해서 보여준다.

### 2. Evidence viewer

근거 snippet만으로 부족할 때 원문 위치를 확인할 수 있어야 한다.

필요 UI:

- source document viewer
- block id highlight
- concept/source page 전환
- source block과 concept unit의 차이 표시
- web evidence 표시
  - title
  - url
  - snippet/content
  - internal evidence와 다른 badge

검증 기준:

- 같은 답변에서 source evidence와 concept evidence를 구분해서 볼 수 있다.
- `internal_web_augmented` 답변에서 내부 Wiki 근거와 web 근거가 서로 다른 출처로 표시된다.

### 3. Ingest run dashboard

문서 처리 상태와 실패 원인을 사용자가 확인해야 한다.

필요 UI:

- 파일 업로드 상태
- pipeline run status
- source page 생성 수
- concept page 생성 수
- unit 생성 수
- 실패 문서 목록
- cleaned replacement 사용 여부
- 기본 산출물 미생성 상태 표시
  - JSON/MD 파일이 없어도 정상임을 전제로 표시
  - `save_debug_json=true`일 때만 debug artifact 링크 표시
- object storage markdown 링크 또는 page viewer 진입점
- pipeline log viewer

검증 기준:

- 12개 문서 ingest 시 성공/실패/보정 결과를 한 화면에서 확인할 수 있다.
- `source_blocks.json`이나 `manifest.json` 파일이 없어도 dashboard가 깨지지 않는다.

### 4. Query experiment report export

현재 수동으로 만든 실험 md를 UI에서도 재현할 수 있어야 한다.

필요 UI:

- 질문 목록 입력
- 실행 결과 저장
- markdown export
- raw JSON download
- 사용 source 문서 수 표시
- evidence count 표시
- 멀티턴 query set 지원
  - thread context
  - recent conversation summary
  - reference context
  - resolved/contextualized question
- evaluator route와 web query 표시

검증 기준:

- 같은 질문 세트를 실행하면 문답, evidence, related pages, evaluator 결과가 md로 저장된다.
- 싱글턴/멀티턴/내부근거/외부근거/내부+외부보강 케이스가 한 리포트에서 구분된다.

### 5. Error/Warning 상태

깨진 문서나 parser 실패를 단순 실패로만 보여주면 원인 파악이 어렵다.

필요 UI:

- invalid JSON
- NUL/control char
- OCR/glyph corruption
- web search disabled
- citation 없음
- evaluator 재시도 실패
- web search empty
- query evaluator failed
- no relevant seed
- concept direct match
- query evaluator unsupported

검증 기준:

- 실패 원인이 사용자에게 노출되고, 재업로드 또는 cleaned markdown 사용 판단이 가능하다.
- query 자체는 성공했지만 evaluator/web 보강만 실패한 경우를 전체 실패와 구분한다.

## 공통 수용 기준

- 답변 본문, citation, evidence, 원문 블록이 서로 추적 가능해야 한다.
- source와 concept이 모두 query evidence 후보로 취급되어야 한다.
- web search가 사용된 경우 내부 근거와 web 근거를 구분해서 보여줘야 한다.
- ingest 실패 문서는 왜 실패했는지와 어떤 보정으로 성공했는지가 남아야 한다.
- Spring/Front는 pipeline 내부 scoring 로직을 재구현하지 않고, pipeline 응답을 손실 없이 표시하는 방향을 우선한다.
- 멀티턴 질문은 raw message history 전달이 아니라 Spring이 만든 요약/참조 컨텍스트 전달 방식으로 처리한다.
- pipeline response에 없는 값은 Spring event log나 보강 조회로 조립하고, 필요하면 pipeline response 확장 이슈로 분리한다.
