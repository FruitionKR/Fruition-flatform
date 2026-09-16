# llmPipeline ↔ Spring Backend API 계약

## 문서 목적

이 문서는 **Spring Backend와 llmPipeline 사이에 현재 구현된 HTTP API와 Spring 연동 검토 대상 API의 계약**을 정리한다.

- 기준일: 2026-08-06
- Source of truth: Spring requester/controller와 llmPipeline FastAPI route/Pydantic schema
- 문서와 코드가 다르면 현재 코드를 우선한다.

다음 정보를 API별로 같은 순서에서 제공한다.

1. Method + Path
2. 언제 호출하는가
3. 필수 인증과 호출 전 Spring 검증
4. Spring이 보내는 값
5. Spring이 받는 값
6. 오류 처리
7. 목록·필터링 여부
8. 예시 요청 / 응답

Notion으로 옮길 때 `##` 기능 제목을 최상위 토글로, `###` endpoint 제목을 하위 토글로 사용한다. `공통 계약`은 접지 않고 페이지 상단에 노출하는 것을 권장한다.

다이어그램은 사용자 여정을 기준으로 작은 흐름만 보여주고, 세부 JSON 계약은 각 API 섹션에서 설명한다. 이 구성은 API diagram에 endpoint, request/response flow, authentication, data structure, dependency, status/error를 포함하고 한 다이어그램에 너무 많은 개념을 넣지 말라는 [Postman API Diagram Guide](https://blog.postman.com/api-diagram-guide/)의 원칙을 따른다.

성공 응답의 더 상세한 field 설명은 [llmpipeline-backend-output-contract.md](llmpipeline-backend-output-contract.md)를 부록으로 참조한다. 단, 해당 부록에는 Spring이 현재 호출하지 않는 llmPipeline 내부 API도 포함되므로 **현재 연결 여부는 이 문서를 우선**한다.

## 전체 연동 현황

### 전체 Integration Diagram

```mermaid
flowchart LR
    SPRING[Spring Backend]

    subgraph PIPELINE[llmPipeline FastAPI]
        INGEST[Document·Chat Ingestion]
        QUERY[Wiki Query]
        AGENT[Markdown Agent]
        SCHEMA[Wiki Schema]
        LINT[Wiki Lint]
        RESTORE[Wiki Restore]
    end

    DB[(PostgreSQL)]
    STORAGE[(MinIO)]
    LLM[External LLM]

    SPRING -->|POST /pipeline/runs| INGEST
    SPRING -->|POST /chat-wiki/runs| INGEST
    SPRING -->|POST /query| QUERY
    SPRING -->|POST /agent/turn| AGENT
    SPRING -->|/wiki-schema/*| SCHEMA
    SPRING -->|POST /wiki/maintenance/lint| LINT
    SPRING -->|POST /wiki/*-restore-runs| RESTORE

    INGEST -. pipeline event callback .-> SPRING
    INGEST -. operation result callback .-> SPRING
    QUERY -. query event callback .-> SPRING

    PIPELINE <--> DB
    PIPELINE <--> STORAGE
    PIPELINE <--> LLM
```

### Backend → llmPipeline API 목록

| 상태 | Method | Path | Spring 호출자 |
| --- | --- | --- | --- |
| 연결됨 | `POST` | `/pipeline/runs` | `DocumentProcessingRequester` |
| 연동 필요 | `POST` | `/pipeline/reingest-runs` | 없음 |
| 운영 연동 선택 | `GET` | `/pipeline/runs/{run_id}` | 없음 |
| 운영 연동 선택 | `GET` | `/pipeline/runs/{run_id}/logs` | 없음 |
| 운영 연동 선택 | `POST` | `/pipeline/runs/{run_id}/result-callback/retry` | 없음 |
| 연결됨 | `POST` | `/chat-wiki/runs` | `DocumentProcessingRequester` |
| 연결됨 | `POST` | `/query` | `PipelineQueryRequester` |
| 부분 연결 | `POST` | `/agent/turn` | `PipelineAgentRequester` |
| 연동 필요 | `POST` | `/skills/author` | 없음 |
| 연동 필요 | `POST` | `/skills/author/publish` | 없음 |
| 연동 필요 | `POST` | `/skills/draft-from-runs/preview` | 없음 |
| 연동 필요 | `POST` | `/skills/preview` | 없음 |
| 연동 필요 | `GET` | `/skills` | 없음 |
| 연동 필요 | `GET` | `/skills/{skill_id}` | 없음 |
| 연동 필요 | `PATCH` | `/skills/{skill_id}` | 없음 |
| 연동 필요 | `POST` | `/skills/{skill_id}/enable` | 없음 |
| 연동 필요 | `POST` | `/skills/{skill_id}/disable` | 없음 |
| 연동 필요 | `GET` | `/agent/runs/{run_id}` | 없음 |
| 연동 필요 | `POST` | `/agent/runs/{run_id}/approve` | 없음 |
| 연동 필요 | `POST` | `/agent/runs/{run_id}/reject` | 없음 |
| 연동 필요 | `POST` | `/agent/runs/{run_id}/cancel` | 없음 |
| 연동 필요 | `POST` | `/agent/runs/{run_id}/revise` | 없음 |
| 연결됨 | `POST` | `/wiki-schema/preview` | `PipelineWikiSchemaRequester` |
| 연결됨 | `POST` | `/wiki-schema/drafts` | `PipelineWikiSchemaRequester` |
| 연결됨 | `POST` | `/wiki-schema/{schema_id}/activate` | `PipelineWikiSchemaRequester` |
| 연결됨 | `GET` | `/wiki-schema/active` | `PipelineWikiSchemaRequester` |
| 연결됨 | `POST` | `/wiki/maintenance/lint` | `PipelineWikiMaintenanceRequester` |
| 연결됨 | `POST` | `/wiki/ingest-restore-runs` | `PipelineRestoreRequester` |
| 연결됨 | `POST` | `/wiki/lint-restore-runs` | `PipelineRestoreRequester` |
| 계약 불일치 | `PATCH` | `/wiki/pages/{wiki_page_id}/rename` | `PipelineWikiPageRequester` |
| 진단용 | `GET` | `/documents/{document_id}` | 없음 |
| 인프라용 | `GET` | `/health` | 없음 |

`PATCH /wiki/pages/{wiki_page_id}/rename`은 Spring에 호출 코드가 있지만 llmPipeline에 FastAPI route가 없다. 따라서 현재 사용 가능한 API가 아니며, `미구현·계약 불일치`에 기록한다.

### llmPipeline → Backend Callback 목록

| 상태 | Method | Path | llmPipeline 호출자 |
| --- | --- | --- | --- |
| 연결됨 | `POST` | `/api/documents/{document_id}/pipeline-events` | `PipelineLog` |
| 연결됨 | `POST` | `/api/query/runs/{request_id}/events/callback` | `HttpQueryEventPublisher` |
| 연결됨 | `POST` | `/api/ai-operations/{operation_id}/result` | `HttpPipelineResultNotifier` |
| Backend route 없음 | `POST` | `/internal/agent/tools/read/{tool_name}` | `BackendToolGateway` |
| Backend route 없음 | `POST` | `/internal/agent/tools/execute/{tool_name}` | `BackendToolGateway` |

### Spring 업무 API가 아닌 llmPipeline API

다음 두 API도 뒤에서 응답 계약을 설명하지만 Spring application service가 사용자 기능을 위해 호출하는 API는 아니다.

- `GET /documents/{document_id}`: llmPipeline이 공유 DB에서 읽은 Document snapshot을 확인하는 진단용 API다. Document 원본의 소유자는 Spring이므로 Spring이 역조회할 필요가 없다.
- `GET /health`: 배포 환경의 health check용 API다. Spring requester가 아니라 Docker/Kubernetes/모니터링 계층이 호출한다.

그 밖에 기존에 제외했던 `/pipeline/reingest-runs`, Pipeline Run 조회·로그·callback 재시도, `/skills/*`, `/agent/runs/*`는 Spring 연동 판단과 구현에 필요하므로 이 문서의 상세 계약에 포함한다.

## 공통 계약

### Base URL과 Content-Type

| 항목 | 현재 값 |
| --- | --- |
| llmPipeline 기본 Base URL | `http://localhost:8000` |
| Request Content-Type | `application/json` |
| Response Content-Type | 기본 `application/json` |
| 문자 인코딩 | UTF-8 |

### Auth 현황

| API | llmPipeline Auth | Spring 헤더 | 현재 판정 |
| --- | --- | --- | --- |
| Ingestion, Query, Schema, Lint, Restore | `X-Internal-Token` 필수 | **현재 미전송** | Spring 호출이 `401`로 실패 |
| `/agent/turn` + `AGENT_SKILLS_ENABLED=false` | `X-Internal-Token` 필수 | **현재 미전송** | Spring 호출이 `401`로 실패 |
| `/agent/turn` + `AGENT_SKILLS_ENABLED=true` | `X-Internal-Token`, `X-Agent-Service-Token` 필수 | **둘 다 현재 미전송** | Spring 호출이 `401` 또는 `503`으로 실패 |
| `/skills/*`, `/agent/runs/*` | `X-Agent-Service-Token` 필수 | Spring requester 없음 | 신규 연동 필요. 기능 flag가 꺼지면 route 자체가 없음 |
| `/documents/{document_id}` | `X-Internal-Token` 필수 | Spring requester 없음 | 운영 진단용 |
| `/health` | 인증 없음 | 해당 없음 | 배포 health check용 |
| 진행·Query callback | llmPipeline이 `X-Internal-Token` 전송 | Spring 검증 없음 | 헤더를 보내지만 아직 인증 경계로 사용하지 않음 |
| Operation result callback | Spring `X-Internal-Token` 필수 | llmPipeline이 `INTERNAL_CALLBACK_TOKEN` 전송 | 양쪽 설정값이 같을 때 연결됨 |
| Agent Tool Gateway | Spring route 없음 | llmPipeline이 `X-Agent-Service-Token` 전송 | 현재 `404`로 실패 |

Auth 항목은 현재 코드를 기술한 것이며, 보안상 권장 상태를 뜻하지 않는다.

### 공통 Error Shape

FastAPI route가 명시적으로 반환하는 오류는 보통 다음 형태다.

```json
{
  "detail": "Document not found"
}
```

Pydantic request validation 실패는 `422 Unprocessable Entity`와 배열 형태 `detail`을 반환한다.

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "document_id"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

Agent의 출력 계약 실패는 코드화된 object를 `detail`에 넣는다.

```json
{
  "detail": {
    "code": "markdown_output_contract_failed",
    "message": "Markdown 편집 결과가 문법 및 보존 조건을 충족하지 못했습니다."
  }
}
```

오류 body 필드 의미:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `detail` | string/object/array | FastAPI가 반환하는 오류 본문이다. 단순 domain 오류는 string, 코드화된 Agent 오류는 object, request validation 오류는 array다. |
| `detail.code` | string | 호출자가 오류 종류를 안정적으로 분기할 때 사용하는 machine-readable 코드다. 현재 주로 Agent 계약 오류에서 제공한다. |
| `detail.message` | string | 사용자 또는 운영 로그에 표시할 수 있는 오류 설명이다. |
| `detail[].type` | string | Pydantic validation 실패 종류다. 예: `missing`, `string_too_short`. |
| `detail[].loc` | array | 오류가 발생한 위치다. `body`, field 이름 등의 순서로 표현한다. |
| `detail[].msg` | string | validation 실패 이유다. |
| `detail[].input` | any | 검증에 실패한 입력값이다. 민감한 값이 포함될 수 있으므로 그대로 사용자 로그에 남기지 않는다. |

### Spring 구현자가 먼저 읽을 계약

이 절은 **Spring에서 llmPipeline 호출 코드를 새로 만들거나 수정할 때 지켜야 하는 구현 목표**다. 아래 기능별 계약은 각 API의 전체 필드와 응답 구조를 설명하고, 이 절은 실제 요청 DTO와 `RestClient`를 구성하는 데 필요한 최소 규칙만 모은다.

문서의 용어는 다음 의미로 사용한다.

| 구분 | Spring 처리 |
| --- | --- |
| 필수 | 항상 값을 만들고 전송한다. 값이 없으면 llmPipeline을 호출하지 않고 Spring 입력 검증에서 막는다. |
| 조건부 | 표에 적힌 조건을 만족할 때만 전송한다. 함께 보내야 하는 필드는 하나의 DTO 생성 규칙으로 묶는다. |
| 선택 | 해당 기능을 실제로 사용할 때만 전송한다. `null`이면 JSON에서 생략한다. |
| llmPipeline 설정 | provider, model, prompt, temperature 같은 실행 세부 값이다. Spring 기능 요구사항이 없으면 보내지 않고 llmPipeline 기본값을 사용한다. |

Spring은 사용자 요청을 그대로 전달하는 단순 proxy가 아니다. Workspace membership, Document 접근 권한, edit lock, 복구 대상 같은 사용자 권한과 업무 규칙을 먼저 검증하고, 검증을 마친 내부 식별자만 llmPipeline에 전달한다. llmPipeline은 내부 서비스 호출자로서 Spring이 전달한 Workspace·User·Page·Operation 식별자를 신뢰한다.

### 모든 Backend → llmPipeline 요청의 공통 구성

#### 필수 헤더

```http
Content-Type: application/json
X-Internal-Token: {INTERNAL_CALLBACK_TOKEN과 같은 공유 시크릿}
```

| 헤더 | 적용 범위 | 규칙 |
| --- | --- | --- |
| `Content-Type: application/json` | body가 있는 모든 요청 | 필수 |
| `X-Internal-Token` | Ingestion, Query, Wiki Schema/Lint/Restore, `/agent/turn`, `/documents/*` | 필수. llmPipeline의 `INTERNAL_CALLBACK_TOKEN`과 값이 같아야 한다. |
| `X-Agent-Service-Token` | `/skills/*`, `/agent/runs/*` | 필수. llmPipeline의 `AGENT_INTERNAL_TOKEN`과 값이 같아야 한다. |
| `X-Agent-Service-Token` | `AGENT_SKILLS_ENABLED=true`인 `/agent/turn` | `X-Internal-Token`에 추가로 필수 |

기능별 개별 요청 예시에서 헤더가 생략되어 있어도 이 공통 헤더 계약을 항상 적용한다.

현재 Spring requester들은 위 내부 인증 헤더를 보내지 않는다. 따라서 기존 requester를 그대로 복사하면 안 되며, 각 `RestClient` 요청에 헤더를 추가해야 한다. 토큰은 request/response log에 출력하지 않는다.

구현 형태는 다음 정도면 충분하다. 별도 HTTP client abstraction은 필요하지 않다.

```java
RestClient restClient = RestClient.builder()
        .requestFactory(requestFactory)
        .defaultHeader("X-Internal-Token", internalToken)
        .build();
```

Agent Skill 기능을 켠 환경은 `/agent/turn` client에 두 token을 모두 추가한다. `/skills/*`, `/agent/runs/*` client는 현재 코드 기준으로 `X-Agent-Service-Token`을 사용한다.

#### URL과 callback URL

| 값 | 예시 | 주의사항 |
| --- | --- | --- |
| Spring에서 호출하는 llmPipeline URL | `http://localhost:8000/query` | Spring 실행 환경에서 접근 가능한 주소여야 한다. |
| llmPipeline이 호출하는 Spring callback URL | `http://host.docker.internal:8080/api/...` | llmPipeline 실행 환경에서 접근 가능한 주소여야 한다. 컨테이너에서 Spring을 호출할 때 `localhost`를 사용하지 않는다. |
| `log_callback_url` | `/pipeline-events`, `/events/callback` | 진행 이벤트용이다. 최종 성공·실패를 확정하지 않는다. |
| `result_callback_url` | `/api/ai-operations/{operation_id}/result` | 최종 작업 결과용이다. `operation_id`와 항상 함께 전송한다. |

callback URL은 사용자 입력으로 받지 않고 Spring의 `app.callback.base-url`과 검증된 ID로 조립한다.

### API 선택과 Spring 최소 입력

| Spring이 하려는 일 | Method + Path | 항상 보낼 필드 | 조건부·선택 필드 | 즉시 응답에서 사용할 값 |
| --- | --- | --- | --- | --- |
| 저장된 일반 Document를 Wiki로 변환 | `POST /pipeline/runs` | `document_id` | `log_callback_url`; `operation_id` + `result_callback_url` | `run_id`, `status` |
| 수정된 일반 Document를 Wiki에 재반영 | `POST /pipeline/reingest-runs` | `document_id`, `input_markdown` | `log_callback_url`; `operation_id` + `result_callback_url` | `run_id`, `status` |
| Pipeline 실행 상태·로그 확인 | `GET /pipeline/runs/{run_id}` 및 `/logs` | path의 `run_id` | 없음 | 상태 JSON 또는 `text/plain` log |
| 실패한 최종 callback 재전송 | `POST /pipeline/runs/{run_id}/result-callback/retry` | path의 `run_id` | 없음 | 재전송한 Operation 결과 payload |
| Chat Document를 Wiki로 변환 | `POST /chat-wiki/runs` | `document_id`, `selection_mode` | `input_markdown`; `log_callback_url`; `operation_id` + `result_callback_url` | `run_id`, `status` |
| Workspace Wiki에 질문 | `POST /query` | `workspace_id`, `question` | `user_id`; 비동기이면 `request_id` + `log_callback_url`; 대화 맥락 필드 | 전체 Query 응답 |
| Skill 자연어 작성 | `POST /skills/author` | Workspace/User, scope, instruction, 선택적 name·authoring_mode | 참조 문서 ID 최대 3개 | Tool이 숨겨진 원문 보존 또는 AI 구체화 미저장 Skill Markdown proposal·차단 issue |
| Skill 관리 | `/skills/*` | endpoint별 Workspace/User와 definition | version ID, 초안 source | `SkillResponse` 또는 preview |
| 현재 Markdown 편집·생성·질문 | `POST /agent/turn` | `message` | Markdown context, conversation context, Workspace/User, `skill_mode`, `skill_id` | `action`에 해당하는 결과 |
| Agent 계획 표시·승인·제어 | `/agent/runs/*` | path의 `run_id`, Workspace/User | approve의 plan version/hash, revise instruction | `AgentRunResponse` |
| Schema 내용 미리보기 | `POST /wiki-schema/preview` | `raw_markdown` | 없음 | preview 전체 |
| Schema draft 저장 | `POST /wiki-schema/drafts` | `raw_markdown`, `workspace_id`, `user_id` | `name` | `wiki_schema.id`, 상태와 preview |
| Schema 활성화 | `POST /wiki-schema/{schema_id}/activate` | path의 `schema_id` | body 없음 | 활성 Schema 전체 |
| 활성 Schema 조회 | `GET /wiki-schema/active` | query의 `workspace_id`, `user_id` | body 없음 | Schema 또는 `null` |
| Wiki lint 실행 | `POST /wiki/maintenance/lint` | `user_id`, `workspace_id` | mutation이면 `operation_id`; 실행 mode | lint 결과 전체 |
| Ingestion 작업 복구 | `POST /wiki/ingest-restore-runs` | `Ingestion 작업 복구`의 복구 지시서 전체 | `deleted_pages` 기본 `[]` | body를 완료 판정에 사용하지 않음 |
| Lint 작업 복구 | `POST /wiki/lint-restore-runs` | `Lint 작업 복구`의 복구 지시서 전체 | `deleted_pages` 기본 `[]` | body를 완료 판정에 사용하지 않음 |

`PATCH /wiki/pages/{wiki_page_id}/rename`은 llmPipeline route가 없으므로 Spring에서 호출 가능한 계약으로 구현하면 안 된다.

### 요청 DTO 구성 규칙

#### Document Ingestion

일반 Document는 Spring DB와 Object Storage에 원문 메타데이터가 이미 저장된 뒤 호출한다. Spring이 원문 Markdown이나 로컬 파일 경로를 보내지 않는다.

```json
{
  "document_id": "doc_123",
  "log_callback_url": "http://backend:8080/api/documents/doc_123/pipeline-events"
}
```

AI Operation 결과까지 추적할 때만 아래 두 필드를 **동시에** 추가한다. 하나만 보내면 `422`다.

```json
{
  "operation_id": "op_123",
  "result_callback_url": "http://backend:8080/api/ai-operations/op_123/result"
}
```

`user_id`, `workspace_id`는 기존 Spring DTO 호환 필드다. llmPipeline은 `document_id`로 조회한 DB Document의 값을 사용하므로 신규 구현의 필수 입력으로 취급하지 않는다.

#### Document Reingestion

Document 수정 후에는 최초 편입 API를 재사용하지 않고 `POST /pipeline/reingest-runs`에 저장 완료된 전체 `input_markdown`을 보낸다. 기존 활성 source page가 없는 Document는 재편입할 수 없다.

```json
{
  "document_id": "doc_123",
  "input_markdown": "# 수정된 제목\n\n수정된 본문입니다."
}
```

#### Chat Ingestion

`selection_mode`는 `full` 또는 `partial`만 허용한다.

- `partial`: 선택한 대화를 독립 Source Page로 생성한다. `input_markdown`을 보내지 않는다.
- `full`: 기존 Chat Source Page에 누적한다. Spring이 중복을 제거한 신규 대화만 직렬화할 때 `input_markdown`을 보낼 수 있다.
- 최초 `full`: 기존 Source Page가 없으므로 `input_markdown`을 보내면 `422`다. llmPipeline이 저장된 전체 Chat export를 읽게 한다.

```json
{
  "document_id": "chatdoc_123",
  "selection_mode": "full",
  "input_markdown": "# Chat Export\n\n[session_1:pair_2]Q : 질문\nA : 답변"
}
```

#### Query

동기 Query의 최소 body는 다음과 같다.

```json
{
  "workspace_id": "ws_123",
  "question": "이 Workspace에서 다루는 핵심 개념은 뭐야?"
}
```

비동기 Query는 Spring이 먼저 `request_id`를 생성하고 callback URL을 조립해 두 필드를 함께 보낸다. `recent_conversation_summary`와 `reference_context`는 Spring이 이전 대화로부터 만든 내부 context이며 프론트가 llmPipeline 형식으로 직접 만들게 하지 않는다.

```json
{
  "workspace_id": "ws_123",
  "question": "그 개념의 근거도 보여줘",
  "request_id": "query_123",
  "log_callback_url": "http://backend:8080/api/query/runs/query_123/events/callback",
  "recent_conversation_summary": "직전 질문에서 robust optimization을 설명했다.",
  "reference_context": {
    "active_concept_ids": ["concept_123"]
  }
}
```

#### Markdown Agent

Spring은 `document_id`와 `base_version`을 llmPipeline에 보내지 않는다. 이 값은 호출 전에 권한·버전·edit lock을 검증하고, 응답의 편집안을 실제 Document에 적용할 때 Spring이 다시 사용한다.

```json
{
  "message": "선택한 문단을 간결하게 바꿔줘",
  "active_markdown_context": {
    "markdown": "# 제목\n\n긴 문단입니다.",
    "target": {
      "type": "selection",
      "start_line": 3,
      "end_line": 3
    }
  }
}
```

target line은 1부터 시작하며 시작·끝 line을 모두 포함한다. `target`을 보내면 `type`, `start_line`, `end_line`을 모두 채운다. 허용 type은 `selection`, `current_section`, `whole_document`다.

#### Agent Skill과 Agent Run

- Spring은 Skill definition 전체를 `/agent/turn`에 넣지 않는다. Skill 관리 API로 먼저 저장·publish·enable하고 Agent 요청에는 `skill_mode`, 필요 시 `skill_id`만 보낸다.
- `skill_mode=auto`는 llmPipeline이 접근 가능한 enabled Skill 후보 중에서 고르게 한다.
- `skill_mode=explicit`은 `skill_id`를 함께 보내며, 없거나 disabled이면 `422`다.
- `skill_mode=off`는 Skill 없이 실행한다.
- mutation action이 `run_id`를 반환하면 `/agent/runs/{run_id}`를 조회한다. plan 승인에는 조회 응답의 `version`과 `operation_hash`를 수정 없이 되돌려 보낸다.

#### Wiki Schema, Lint, Restore

- Schema preview는 저장하지 않으므로 `raw_markdown`만 보낸다.
- Schema draft는 `workspace_id`, `user_id`를 추가하고, 응답의 `wiki_schema.id`를 activate path에 사용한다.
- Active 조회의 scope는 body가 아니라 query parameter로 보낸다.
- Lint에서 `dry_run=false`이면 DB/Object Storage mutation을 추적할 `operation_id`가 필수다.
- Restore의 `rebuild_pages[].keep_contributions` 순서는 페이지 조립 순서이므로 정렬하거나 `Set`으로 바꾸지 않는다.
- Restore HTTP 응답 수신만으로 작업을 완료 처리하지 않는다. 같은 operation의 `result_callback_url` callback이 성공해야 최종 상태를 확정한다.

### 응답과 오류 처리 규칙

1. `POST /pipeline/runs`, `POST /pipeline/reingest-runs`, `POST /chat-wiki/runs`는 기본 `wait=false`다. `200` 응답은 실행 완료가 아니라 접수 성공이며, `status`는 보통 `running`, `manifest`는 `null`이다.
2. Query, Agent, Schema, Lint는 동기 응답 body를 사용한다. `2xx`인데 body가 없으면 정상 결과로 처리하지 않는다.
3. `GET /wiki-schema/active`의 `200 null`만 정상적인 빈 결과다.
4. `401`은 사용자 인증 실패가 아니라 Spring↔llmPipeline 내부 토큰 설정 오류다. 사용자에게 그대로 노출하지 않고 내부 연동 오류로 처리한다.
5. `422`의 `detail`은 string이 아니라 배열 또는 object일 수 있다. Spring DTO 하나로 강제 역직렬화하지 말고 원문 body를 보존해 domain error로 변환한다.
6. timeout과 llmPipeline `5xx`는 재시도 가능성을 가진 연동 실패로 분류한다. 단, mutation 요청을 자동 재시도하려면 `operation_id` 기반 멱등성이 별도로 확인되어야 한다.
7. callback URL, token, 원문 Markdown, 전체 질문은 운영 log에 남기지 않는다. ID, HTTP status, 처리 시간, payload 길이만 기록한다.

Spring 구현 완료 기준:

- 모든 활성 requester가 필요한 내부 인증 헤더를 보낸다.
- DTO의 JSON 이름이 표의 snake_case와 일치한다.
- 조건부 필드 쌍과 Chat/Lint/Restore validation을 호출 전에 검증한다.
- callback URL이 llmPipeline 실행 환경에서 접근 가능하다.
- async 접수와 최종 callback을 서로 다른 상태 전이로 처리한다.
- 성공 body와 `4xx`/`5xx`/timeout을 endpoint 성격에 맞게 검증하는 requester test가 있다.

## 일반 문서 Wiki 변환

### `POST /pipeline/runs`

#### 언제 호출하는가

Spring에 저장된 일반 Document를 Source·Concept Wiki Page로 비동기 변환한다.

#### 필수 인증

- llmPipeline Auth: `X-Internal-Token` 필수
- Spring 전송 헤더: 현재 없음(`401`)

#### 호출 전 Spring 검증

- Spring의 일반 업로드·재처리 API가 사용자 권한과 Document 상태를 검증한 뒤 처리 큐에 등록한다. 실제 llmPipeline 호출은 `DocumentProcessingWorker`가 수행하지만 현재 `X-Internal-Token`을 보내지 않아 llmPipeline에서 `401`로 거절된다.
- llmPipeline은 request의 `user_id`, `workspace_id`를 Wiki 저장 범위의 권위 값으로 사용하지 않고, `document_id`로 조회한 DB Document의 값을 사용한다.

#### Spring이 보내는 값

| 필드 | 타입 | 필수 | Spring 전송 | 설명 |
| --- | --- | --- | --- | --- |
| `document_id` | string | 예 | 예 | 처리할 Document ID |
| `user_id` | string | 아니오 | 예 | 호환용 필드. 실제 범위는 DB Document에서 결정 |
| `workspace_id` | string | 아니오 | 예 | 호환용 필드. 실제 범위는 DB Document에서 결정 |
| `log_callback_url` | string/null | 아니오 | 예 | 단계별 event callback URL |
| `operation_id` | string/null | 조건부 | 기능 flag 활성 시 | AI 작업 로그와 완료 결과를 연결하는 ID다. `result_callback_url`과 함께 보내야 한다. |
| `result_callback_url` | string/null | 조건부 | 기능 flag 활성 시 | 완료·실패 결과 callback URL이다. 진행 event용 `log_callback_url`과 별개다. |

Spring은 llmPipeline이 지원하는 model·prompt·evaluation 세부 설정을 전송하지 않으며 llmPipeline 기본값을 사용한다.
`app.aihistory.ingest-logging-enabled=false`가 기본값이므로 기본 설정에서는 `operation_id`와 `result_callback_url`을 보내지 않는다.

#### Spring이 받는 값

| 필드 | 타입 | Spring 사용 | 설명 |
| --- | --- | --- | --- |
| `run_id` | string | 예 | Pipeline 실행 1건을 식별하는 UUID다. Spring이 Document의 현재 Pipeline Run ID로 기록한다. |
| `status` | string | 로그만 | 현재 실행 상태다. Spring requester가 응답 로그에는 남기지만 Document 상태 결정에는 사용하지 않는다. 기본 비동기 응답은 `running`이다. |
| `manifest` | object/null | 아니오 | 완료 산출물 요약이다. Spring은 `wait=false`만 사용하므로 응답 시점에는 `null`이며 Java response DTO에도 선언하지 않는다. |
| `output_dir` | string | 아니오 | llmPipeline이 실행별 artifact를 저장하는 내부 디렉터리 경로다. Java DTO로 역직렬화하지만 이후 사용하지 않는다. |
| `log_path` | string | 아니오 | llmPipeline의 local Pipeline log 파일 경로다. Java DTO로 역직렬화하지만 이후 사용하지 않는다. |

#### 오류 처리

| Status | 조건 | 예시 `detail` |
| --- | --- | --- |
| `404` | Document가 없음 | `Document not found` |
| `409` | PDF 등에 `extracted_text_uri`가 없음 | `Document needs extracted_text_uri ...` |
| `409` | source URI가 없음 | `Document has no source_uri or extracted_text_uri` |
| `422` | request schema 위반 | Pydantic validation detail |
| `422` | `operation_id`, `result_callback_url` 중 하나만 전송 | Pydantic model validation detail |
| `502` | MinIO 원본 읽기 실패 | `Failed to read document object from storage: ...` |
| `500` | DB run 등록 등 내부 오류 | 예외 메시지 |

Spring `DocumentProcessingRequester`는 이 오류를 세분화한 domain error로 변환하지 않고 `RuntimeException`으로 감싼다.

#### 목록/필터링

해당 없음.

#### 예시 요청

```http
POST /pipeline/runs HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "document_id": "doc_123",
  "user_id": "user_123",
  "workspace_id": "ws_123",
  "log_callback_url": "http://backend:8080/api/documents/doc_123/pipeline-events"
}
```

#### 예시 응답

```json
{
  "run_id": "2f5b7e8a-1c25-4a56-bf4a-7dc8b9c14e8d",
  "status": "running",
  "manifest": null,
  "output_dir": "runs/api_2f5b7e8a-1c25-4a56-bf4a-7dc8b9c14e8d",
  "log_path": "runs/api_2f5b7e8a-1c25-4a56-bf4a-7dc8b9c14e8d/pipeline.log"
}
```

## 일반 문서 Wiki 재편입

### `POST /pipeline/reingest-runs`

#### Spring 연동 판단

**연동 필요.** 이미 Wiki로 변환된 Document 본문이 수정됐을 때 기존 Source Page와 contribution을 기준으로 Wiki를 다시 계산하는 API다. 최초 변환용 `/pipeline/runs`를 다시 호출하면 기존 source context를 이용한 변경 추적이 적용되지 않으므로 수정 후 재처리는 이 endpoint를 사용한다.

#### 필수 인증

- `X-Internal-Token` 필수

#### 호출 전 Spring 검증

- 사용자에게 Document 수정·재처리 권한이 있는지 검증한다.
- Document 저장과 version 확정이 끝난 뒤, 확정된 전체 Markdown을 `input_markdown`으로 보낸다.
- 해당 Document에 성공한 기존 source page가 있어야 한다. 없으면 최초 편입인 `POST /pipeline/runs`를 호출한다.
- 같은 Document의 재편입을 동시에 중복 실행하지 않는다.

#### Spring이 보내는 값

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `document_id` | string | 예 | 다시 Wiki에 반영할 Document ID |
| `input_markdown` | string | 예 | 수정 후 확정된 전체 Markdown. 빈 문자열도 schema상 허용된다. |
| `input_name` | string/null | 아니오 | artifact에 표시할 파일명. 없으면 DB Document의 `filename`을 사용한다. |
| `log_callback_url` | string/null | 아니오 | 단계별 진행 event callback URL |
| `operation_id` | string/null | 조건부 | AI 작업 ID. `result_callback_url`과 항상 함께 보낸다. |
| `result_callback_url` | string/null | 조건부 | 최종 성공·실패 callback URL |
| `wait` | boolean | 아니오 | 기본 `false`. Spring에서는 비동기 처리를 위해 `false`를 사용한다. |

`user_id`, `workspace_id`와 model·prompt 설정 필드는 `/pipeline/runs`와 동일하게 받을 수 있지만, Spring 연동에는 보내지 않는 편이 명확하다. 실제 scope는 `document_id`로 조회한 DB Document에서 결정된다.

#### Spring이 받는 값

`PipelineRunOut`을 반환하며 `/pipeline/runs` 응답과 같다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `run_id` | string | 재편입 실행 ID |
| `status` | string | 기본 비동기 접수 시 `running` |
| `manifest` | object/null | `wait=false`이면 일반적으로 `null` |
| `output_dir` | string | llmPipeline 내부 artifact 디렉터리 |
| `log_path` | string | llmPipeline 내부 log 경로 |

#### 오류 처리

| Status | 조건 | Spring 처리 |
| --- | --- | --- |
| `401` | 내부 token 누락·불일치 | 외부에는 `503`으로 변환하고 내부 연동 설정 오류로 기록 |
| `404` | Document 없음 | 요청 대상 불일치로 처리 |
| `409` | 기존 활성 source page 없음 | 최초 편입 필요 상태로 처리하되 자동 fallback 여부는 Spring 정책으로 결정 |
| `422` | request schema 위반 또는 callback 필드 쌍 불완전 | `400` 또는 내부 계약 오류로 변환 |
| `500` | 실행 등록·기존 source 조회 실패 | 재시도 가능한 내부 오류로 처리 |

#### 예시 요청

```http
POST /pipeline/reingest-runs HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "document_id": "doc_123",
  "input_markdown": "# 수정된 문서\n\n최종 저장된 본문입니다.",
  "log_callback_url": "http://backend:8080/api/documents/doc_123/pipeline-events",
  "operation_id": "op_456",
  "result_callback_url": "http://backend:8080/api/ai-operations/op_456/result"
}
```

#### 예시 성공 응답

```json
{
  "run_id": "92f1476d-697e-4616-a11f-814c5cb883b8",
  "status": "running",
  "manifest": null,
  "output_dir": "runs/api_92f1476d-697e-4616-a11f-814c5cb883b8",
  "log_path": "runs/api_92f1476d-697e-4616-a11f-814c5cb883b8/pipeline.log"
}
```

## Pipeline Run 상태·운영

### 실행 상태 조회 — `GET /pipeline/runs/{run_id}`

#### Spring 연동 판단

**선택 연동.** 정상 흐름은 callback으로 상태를 갱신하되, callback 유실 복구·관리자 화면·수동 진단을 위해 polling fallback으로 사용할 수 있다. 일반 사용자 요청마다 지속 polling하는 용도는 아니다.

#### 요청

- Header: `X-Internal-Token` 필수
- Path: `run_id` 필수
- Body와 query parameter 없음

이 endpoint 자체에는 workspace/user 조건이 없다. Spring이 사용자 요청을 받아 proxy한다면 먼저 해당 run과 Document에 대한 membership을 검증해야 한다.

#### 응답

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | Pipeline Run ID |
| `document_id` | string/null | 처리 대상 Document ID |
| `input_source` | string | 입력 source 식별자. 예: `storage:...`, `inline:...` |
| `output_dir` | string | 내부 artifact 디렉터리 |
| `mode` | string | 실행 mode |
| `status` | string | `running`, `succeeded`, `failed` 등 현재 상태 |
| `manifest` | object/null | 실행 산출물과 callback 전달 상태를 포함할 수 있는 내부 manifest |
| `error` | string/null | 실패 원인 |
| `created_at` | datetime | 생성 시각 |
| `updated_at` | datetime | 마지막 변경 시각 |
| `finished_at` | datetime/null | 종료 시각 |

- `404`: run이 없음, `detail: "Pipeline run not found"`
- `500`: DB 조회 실패

#### 예시 요청

```http
GET /pipeline/runs/92f1476d-697e-4616-a11f-814c5cb883b8 HTTP/1.1
X-Internal-Token: {internal-token}
```

#### 예시 성공 응답

```json
{
  "id": "92f1476d-697e-4616-a11f-814c5cb883b8",
  "document_id": "doc_123",
  "input_source": "inline:document.md",
  "output_dir": "runs/api_92f1476d-697e-4616-a11f-814c5cb883b8",
  "mode": "api",
  "status": "succeeded",
  "manifest": {},
  "error": null,
  "created_at": "2026-08-06T10:00:00+09:00",
  "updated_at": "2026-08-06T10:00:08+09:00",
  "finished_at": "2026-08-06T10:00:08+09:00"
}
```

### 실행 로그 조회 — `GET /pipeline/runs/{run_id}/logs`

#### Spring 연동 판단

**운영자 기능에서만 선택 연동.** 응답은 사용자용 구조화 event가 아니라 llmPipeline의 원문 log다. 일반 진행 UI는 Document/Query callback을 사용하고, 이 API는 관리자 진단 화면이나 장애 조사에서만 사용한다.

#### 요청·응답

- Header: `X-Internal-Token` 필수
- Path: `run_id` 필수
- 성공: `200 text/plain`; body 전체가 log 문자열
- `404`: run이 없음
- `500`: run 조회 또는 log 저장소 읽기 실패

#### 예시 요청

```http
GET /pipeline/runs/92f1476d-697e-4616-a11f-814c5cb883b8/logs HTTP/1.1
X-Internal-Token: {internal-token}
```

#### 예시 성공 응답

```text
[pipeline] source extraction completed
[pipeline] wiki generation completed
```

Spring이 외부 사용자에게 그대로 노출하면 prompt·저장 경로·내부 오류 정보가 포함될 수 있으므로 운영 권한과 log redaction 정책을 적용해야 한다.

### 결과 callback 재시도 — `POST /pipeline/runs/{run_id}/result-callback/retry`

#### Spring 연동 판단

**운영 복구용 선택 연동.** llmPipeline 실행은 끝났지만 Spring의 Operation 결과 callback 전달이 실패해 `manifest.pending_notification`이 남은 경우에만 호출한다. 일반 재처리 API가 아니며 Pipeline 자체를 다시 실행하지 않는다.

#### 요청·응답

- Header: `X-Internal-Token` 필수
- Path: `run_id` 필수
- Body 없음
- 성공: 저장해 둔 callback payload를 Spring에 다시 POST한 뒤, 같은 payload를 `200 application/json`으로 반환
- response shape: 이 문서의 `Operation 최종 결과 — POST /api/ai-operations/{operation_id}/result` request와 동일
- `404`: run 또는 재시도할 pending notification이 없음
- `409`: 이전 callback이 충돌 응답을 받아 자동 재시도가 허용되지 않음

Spring이 이 endpoint를 호출하는 관리 API를 제공한다면 먼저 Operation과 run의 workspace scope를 검증하고, 같은 요청이 중복 실행될 수 있음을 전제로 callback 처리를 멱등하게 유지해야 한다.

#### 예시 요청

```http
POST /pipeline/runs/92f1476d-697e-4616-a11f-814c5cb883b8/result-callback/retry HTTP/1.1
X-Internal-Token: {internal-token}
```

Body는 없다.

#### 예시 성공 응답

이 응답은 새 형식이 아니라, llmPipeline이 저장해 둔 Operation 최종 결과 callback payload를 그대로 반환한다.

```json
{
  "operation_id": "op_456",
  "operation_type": "ingest",
  "status": "succeeded",
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "target_document_id": "doc_123",
  "summary": "Wiki ingest를 완료했습니다.",
  "changed_pages": []
}
```

#### 예시 오류 응답

```http
HTTP/1.1 409 Conflict
Content-Type: application/json
```

```json
{
  "detail": "conflicting callback result cannot be retried"
}
```

## 채팅 Wiki 변환

### `POST /chat-wiki/runs`

#### 언제 호출하는가

Chat Session에서 export한 Markdown을 Wiki Source Page로 생성하거나 기존 full Source Page에 누적한다.

#### 필수 인증

- llmPipeline Auth: `X-Internal-Token` 필수
- Spring 전송 헤더: 현재 없음(`401`)

#### 호출 전 Spring 검증

- Spring `ChatWikiExportService`는 `ChatSessionService.verifyOwnedSession(...)`으로 Session 소유 범위를 검증한다. partial 요청은 `pair_ids`가 비어 있지 않은지 확인한 뒤 일치하는 message만 선택하지만, 요청한 모든 pair ID가 실제로 존재하는지는 별도로 검증하지 않는다.
- 검증·선택된 Markdown으로 `chat_export` Document를 만들고 처리 큐에 등록한 뒤 `DocumentProcessingWorker`가 llmPipeline을 호출한다.
- llmPipeline은 `document_id`로 조회한 DB Document의 User·Workspace를 사용한다.

#### Spring이 보내는 값

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `document_id` | string | 예 | `chat_export` Document ID |
| `user_id` | string | 아니오 | Spring 호환용 전송 필드 |
| `workspace_id` | string | 아니오 | Spring 호환용 전송 필드 |
| `log_callback_url` | string/null | 아니오 | Document pipeline event callback URL |
| `selection_mode` | `full`/`partial` | 예 | full 누적 또는 partial 독립 Source Page |
| `input_markdown` | string/null | 아니오 | 기존 full Source Page에 추가할 신규 pair Markdown |
| `operation_id` | string/null | 조건부 | AI 작업 로그 ID다. `result_callback_url`과 함께 보내야 한다. |
| `result_callback_url` | string/null | 조건부 | 완료·실패 결과를 받을 Spring callback URL이다. |

`input_markdown`은 `selection_mode=full`이고 기존 Source Page가 있을 때만 허용된다. 그 외에는 Document의 MinIO 원본을 읽는다.
두 operation 필드는 일반 Ingestion과 동일하게 `app.aihistory.ingest-logging-enabled=true`일 때만 Spring이 전송한다.

#### Spring이 받는 값

`POST /pipeline/runs`와 같은 `PipelineRunOut` 구조를 사용한다.

#### 오류 처리

| Status | 조건 |
| --- | --- |
| `404` | Document가 없음 |
| `409` | 처리할 source/extracted text가 없음 |
| `422` | `selection_mode` 누락·잘못된 값 |
| `422` | partial에 `input_markdown`을 전송 |
| `422` | 기존 Source Page 없이 full `input_markdown`을 전송 |
| `422` | `operation_id`, `result_callback_url` 중 하나만 전송 |
| `502` | MinIO 읽기 실패 |
| `500` | DB·Pipeline 내부 오류 |

#### 목록/필터링

해당 없음. `selection_mode`는 pagination/filter parameter가 아니라 Source Page 생성 모드다.

#### 예시 요청

```http
POST /chat-wiki/runs HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "document_id": "doc_chat_123",
  "user_id": "user_123",
  "workspace_id": "ws_123",
  "log_callback_url": "http://backend:8080/api/documents/doc_chat_123/pipeline-events",
  "selection_mode": "full",
  "input_markdown": "## User\n\n새 질문\n\n## Assistant\n\n새 답변"
}
```

#### 예시 응답

```json
{
  "run_id": "f3ee3040-3031-420e-bdb0-e75ac7f59875",
  "status": "running",
  "manifest": null,
  "output_dir": "runs/api_f3ee3040-3031-420e-bdb0-e75ac7f59875",
  "log_path": "runs/api_f3ee3040-3031-420e-bdb0-e75ac7f59875/pipeline.log"
}
```

## Wiki 질의

### `POST /query`

#### 언제 호출하는가

Workspace Wiki를 검색·탐색하고 근거가 포함된 답변을 반환한다.

#### 필수 인증

- llmPipeline Auth: `X-Internal-Token` 필수
- Spring 전송 헤더: 현재 없음(`401`)

#### 호출 전 Spring 검증

- Spring `QueryController`가 `ChatSessionService.verifyOwnedSession(workspaceId, userId, sessionId)`으로 Chat Session·Workspace·User 관계를 검증한 뒤 `QueryService` 또는 `QueryRunService`를 호출한다.
- llmPipeline은 request의 `workspace_id`를 신뢰하며 membership을 다시 검증하지 않는다.
- 현재 Spring은 `user_id`와 conversation context를 전송하지 않는다.

#### Spring이 보내는 값

| 필드 | 타입 | llmPipeline 필수 | Spring 전송 | 설명 |
| --- | --- | --- | --- | --- |
| `workspace_id` | string | 예 | 예 | 검색 범위 |
| `question` | string | 예 | 예 | 빈 문자열 불가 |
| `request_id` | string/null | 아니오 | 비동기 Query에서만 | Query Run ID |
| `log_callback_url` | string/null | 아니오 | 비동기 Query에서만 | 진행 event callback URL |
| `user_id` | string/null | 아니오 | 아니오 | 선택 User context |
| `recent_conversation_summary` | string/null | 아니오 | 아니오 | 대화 요약 |
| `reference_context` | object/null | 아니오 | 아니오 | 지시어·개념 context |

#### Spring이 받는 값

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `answer` | string | 근거 표시가 포함된 답변 |
| `related_pages` | array | 검색·탐색한 Page |
| `evidence_snippets` | array | Source Document·Block 근거 |
| `graph_context` | object | UI highlight용 node·edge |
| `traversal_paths` | array | Graph 탐색 경로 |

`related_pages[]`와 `graph_context.nodes[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `id` | string | Wiki Page의 DB 식별자다. |
| `page_type` | string | Page 종류다. 현재 주요 값은 `source`, `concept`다. |
| `title` | string | 사용자에게 표시할 Page 제목이다. |
| `slug` | string | Page를 URL이나 Wiki 내부 참조에서 식별하는 slug다. |
| `relevance_score` | number | 질문과 Page의 관련도 점수다. 높을수록 관련성이 크다. |
| `role` | string | 검색·Graph 탐색에서 Page가 맡은 역할이다. 예: `seed`, `expanded`, `evidence`. |
| `depth` | integer | 시작 Page에서 Graph edge를 몇 번 거쳐 도달했는지 나타내는 깊이다. |

`evidence_snippets[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `rank` | integer | 근거 순번이다. 답변 안의 `[1]` 같은 표식과 연결된다. |
| `source_document_id` | string | 근거가 나온 대표 원본 Document ID다. |
| `source_block_ids` | string array | 답변 근거로 묶인 Source Block ID 목록이다. |
| `source_refs` | array | Document와 Block을 함께 식별하는 세부 근거 목록이다. |
| `source_refs[].source_document_id` | string | 해당 근거 Block이 속한 원본 Document ID다. |
| `source_refs[].source_block_id` | string | 원본 Document 안에서 근거 위치를 식별하는 Block ID다. |
| `text` | string | 답변 생성에 실제로 제공된 원문 또는 요약 근거다. |

`graph_context.edges[]`와 `traversal_paths[].edges[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `from_page_id` | string | Graph edge의 시작 Page ID다. |
| `to_page_id` | string | Graph edge의 도착 Page ID다. |
| `link_type` | string | 두 Page 사이에 저장된 관계 종류다. |
| `role` | string | 이 edge가 탐색이나 답변 생성에서 맡은 역할이다. |
| `score` | number | edge를 탐색 경로로 선택한 관련도 점수다. |

`traversal_paths[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `path_id` | string | 탐색 경로 1건의 식별자다. |
| `role` | string | 해당 경로의 용도다. 예: 답변 근거 경로 또는 후보 경로. |
| `used_for_answer` | boolean | 경로가 최종 답변 context에 실제 포함됐는지 나타낸다. |
| `score` | number | 경로 전체의 관련도 점수다. |
| `stop_reason` | string | 더 탐색하지 않고 중단한 이유다. |
| `nodes` | string array | 경로가 지나간 Page ID를 탐색 순서대로 담는다. |
| `edges` | array | 인접한 node를 연결한 edge 목록이다. 위 edge 필드 계약을 사용한다. |

#### 오류 처리

| Status | llmPipeline 조건 | Spring 변환 |
| --- | --- | --- |
| `400` | Query domain 규칙 위반 | `502 PIPELINE_ERROR` |
| `422` | request schema 위반 | `502 PIPELINE_ERROR` |
| `500` | retrieval·LLM·DB 오류 | `503 PIPELINE_UNAVAILABLE` |
| timeout | Spring read timeout | `503 PIPELINE_TIMEOUT` |

#### 목록/필터링

해당 없음. 검색 결과 개수와 Graph 탐색 한계는 llmPipeline 내부 설정이며 Spring API parameter로 노출되지 않는다.

#### 예시 요청

```http
POST /query HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "workspace_id": "ws_123",
  "question": "Wiki Ingestion은 어떤 순서로 동작해?",
  "request_id": "query_123",
  "log_callback_url": "http://backend:8080/api/query/runs/query_123/events/callback"
}
```

#### 예시 응답

```json
{
  "answer": "원본을 Source Block으로 나눈 뒤 Concept Page를 생성합니다. [1]",
  "related_pages": [
    {
      "id": "page_ingestion",
      "page_type": "concept",
      "title": "Wiki Ingestion",
      "slug": "wiki-ingestion",
      "relevance_score": 0.91,
      "role": "seed",
      "depth": 0
    }
  ],
  "evidence_snippets": [
    {
      "rank": 1,
      "source_document_id": "doc_123",
      "source_block_ids": ["B0001"],
      "source_refs": [
        {
          "source_document_id": "doc_123",
          "source_block_id": "B0001"
        }
      ],
      "text": "원본을 Source Block으로 분할한다."
    }
  ],
  "graph_context": {
    "nodes": [],
    "edges": []
  },
  "traversal_paths": []
}
```

## Agent Skill — Spring 구현 방식 결정 필요

> **결정 필요:** 현재 `/skills/*`와 Skill PostgreSQL repository는 llmPipeline에 구현돼 있고 Spring에는 Skill API가 없다. Skill은 사용자·Workspace 권한, 개인/팀 scope, 생성·조회·version·publish·enable 상태를 관리하므로 다음 중 하나를 구현 전에 확정해야 한다.
>
> 1. Spring이 공개 `/api/workspaces/{workspace_id}/skills/*`를 제공하고 llmPipeline `/skills/*`를 내부 호출하는 proxy 방식
> 2. Spring이 Skill CRUD·조회·권한을 직접 관리하고 llmPipeline은 enabled Skill을 읽어 실행만 담당하는 방식
>
> 아래 `/skills/*` 계약은 **현재 llmPipeline에 실제 구현된 내부 API 기준**이다. 최종 Spring API 계약으로 확정된 상태가 아니며, 관리 주체를 결정한 뒤 공개 path·DTO·저장 책임을 다시 확정해야 한다.

### Spring 연동 범위

**`AGENT_SKILLS_ENABLED=true`로 Agent 기능을 제공하려면 Skill 관리 경계 구현이 필요하다.** 현재 코드대로라면 Spring은 Skill 관리 화면과 권한 경계를 담당하고 llmPipeline `/skills/*`를 내부 호출한다. Spring이 Skill 저장까지 직접 담당하는 안을 선택하면 아래 API 중 CRUD·조회 endpoint의 책임과 경로가 변경될 수 있다.

`POST /agent/turn` 실행 시에는 Skill 전체를 보내지 않는다. Spring은 `workspace_id`, `user_id`, `skill_mode`, 필요 시 `skill_id`만 보내며, llmPipeline이 enabled Skill version을 DB에서 조회해 router와 AgentRun에 적용한다.

#### 공통 인증과 기능 flag

- `X-Agent-Service-Token` 필수
- 값은 llmPipeline `AGENT_INTERNAL_TOKEN`과 같아야 한다.
- `AGENT_SKILLS_ENABLED=false`이면 router 자체가 등록되지 않아 모든 `/skills/*` 요청이 `404`다.
- 현재 코드상 `/skills/*`는 `X-Internal-Token` middleware 대상이 아니다. Spring client를 만들 때는 우선 현재 필수값인 `X-Agent-Service-Token`을 보내고, 두 내부 인증 체계 통일은 별도 설계 변경으로 처리한다.

#### 공통 Skill definition 필드

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `user_id` | string | 예 | 작업 사용자 ID |
| `name` | string | 예 | `/` 뒤에 사용하는 lowercase-hyphen 커맨드 이름 |
| `description` | string | 예 | Skill 선택에 사용하는 설명 |
| `instructions_markdown` | string | 예 | 실행 시 모델에 전달할 Skill instruction |
| `capabilities` | enum array | 예, 최소 1개 | `document-create`, `document-edit`, `folder-organize`, `template` |
| `allowed_tools` | enum array | 아니오 | capability 범위 안에서 실제 허용할 tool. 기본 `[]` |

mutation tool을 허용하면 planning용 `list_root_items`, `list_folder_children`도 `allowed_tools`에 포함해야 한다. capability가 허용하지 않는 tool이나 필수 planning read tool이 빠지면 `400`이다.

#### 공통 `SkillResponse`

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | Skill ID |
| `workspace_id` | string/null | team Skill의 소속 Workspace ID. personal Skill은 `null`이며 계정 전체에서 사용할 수 있다. |
| `scope_type` | `personal`/`team` | 개인 또는 팀 범위 |
| `owner_user_id` | string/null | personal Skill 소유자. team이면 `null` |
| `slug` | string | slash command 등에 쓰는 소문자·숫자·하이픈 식별자 |
| `status` | `enabled`/`disabled` | 자연어 자동 라우팅 후보 포함 여부. `disabled`여도 published `enabled_version`은 명시적 커맨드로 실행할 수 있다. |
| `enabled_version` | object/null | 현재 실행에 사용하는 published version |
| `latest_version` | object/null | 가장 최근에 저장된 published version |

`enabled_version`, `latest_version`의 공통 필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | Skill version ID |
| `version` | integer | 1부터 증가하는 version 번호 |
| `name`, `description` | string | `name`은 커맨드 식별자, `description`은 해당 version 설명 |
| `instructions_markdown` | string | 해당 version의 실행 instruction |
| `capabilities` | string array | capability 목록 |
| `allowed_tools` | string array | 실행 허용 tool 목록 |
| `lint_result` | object | `issues` 배열을 포함하는 안전성 검사 결과 |
| `status` | `draft`/`published`/`rejected` | version 상태 |

### 자연어 Skill 작성 — `POST /skills/author`

짧은 자연어 또는 사용자가 직접 작성한 Markdown을 검토 가능한 Skill 제안으로 반환하며 이 단계에서는 DB에 저장하지 않는다. `authoring_mode=enhance`는 LLM으로 내용을 구체화하고, `authoring_mode=preserve`는 사용자의 `instruction`을 변경하지 않은 채 보안 재검토와 내부 metadata 분석만 수행한다. 차단 화면의 `authoring_mode=regenerate`는 규칙 검사에서 찾은 위험 구간을 서버가 `[보안상 제거됨]`으로 치환한 뒤 LLM이 안전한 흐름으로 다시 작성한다. 의미 기반 위험 구간만 남아 있으면 LLM이 정확한 원문 위치를 먼저 반환하고, 서버가 해당 구간을 제거한 뒤 한 번만 재생성한다. 서로 다른 system prompt를 사용하는 intent 분류기와 검증기가 각각 요청을 판단하고 `skill_kind`·참조 용도·Tool이 모두 일치할 때만 서버가 `skill_kind`를 capability로 고정 변환한다. 고정 템플릿으로 판단한 참조 문서가 하나일 때만 서버가 추출한 Markdown 구조를 고정 출력 템플릿으로 그대로 조립한다. Skill 이름은 `/` 뒤에 사용하는 커맨드 식별자이며 lowercase-hyphen 형식만 허용한다. personal Skill은 최종 게시 시 `workspace_id=null`로 만들고 모든 Workspace에서 소유자에게 노출하며, team Skill만 현재 Workspace에 귀속한다. 사용자는 `capabilities`와 `allowed_tools`를 보내거나 응답으로 받지 않는다. 지원 Agent action에 매핑할 수 없는 요청과 빈 capability는 검토·게시하지 않는다.

| request 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `workspace_id` | string | 예 | 참조 조회와 현재 요청 Workspace. personal Skill 저장 시에는 `null`로 정규화한다. |
| `user_id` | string | 예 | 참조 조회와 Skill 소유 사용자 |
| `scope_type` | `personal`/`team` | 예 | 생성할 Skill 범위 |
| `name` | string/null | 아니오, 최대 63자 | `/` 뒤에 사용할 lowercase-hyphen 커맨드 이름. 없으면 LLM이 커맨드 이름을 제안한다. |
| `description` | string/null | 아니오, 최대 500자 | 보안 재검토 시 그대로 유지할 사용자 검토 설명 |
| `instruction` | string | 예 | `preserve`는 1~30,000자, `enhance`와 `regenerate`는 1~4,000자 |
| `authoring_mode` | `preserve`/`enhance`/`regenerate` | 아니오, 기본 `enhance` | 원문 보존, LLM 구체화 또는 차단 내용 안전 재생성 모드 |
| `reference_document_ids` | string array | 아니오, 최대 3개 | 구조만 참고할 Markdown 문서 ID. 명시적 템플릿 생성은 정확히 1개만 허용한다. |

참조 ID가 있으면 llmPipeline은 AgentRun Tool Gateway가 아닌 `POST /internal/agent/skill-authoring/references/read`로 Workspace·User 권한이 적용된 현재 문서를 조회한다. 자연어 Skill 작성에는 AgentRun이 없으므로 `run_id`를 만들거나 `/internal/agent/tools/read/*`의 run 검증을 우회하지 않는다. 현재 Spring 전용 route가 미구현이므로 참조 있는 요청은 구현 전까지 동작하지 않으며, 참조 없는 요청은 이 제약을 받지 않는다.

#### 참조 문서 내부 조회 — `POST /internal/agent/skill-authoring/references/read`

llmPipeline이 `X-Agent-Service-Token`과 다음 body를 보낸다.

```json
{
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "document_id": "doc_123"
}
```

Spring은 service token과 현재 Workspace membership, Document 소속·read 권한을 검증한 뒤 다음 값만 반환한다.

```json
{
  "markdown": "# 주간 회의록\n\n## 결정 사항"
}
```

이 endpoint는 AgentRun 계획·승인·실행 endpoint가 아니다. `run_id`, `plan_id`, operation 정보와 mutation 권한을 받지 않으며 문서를 변경할 수 없다. 접근할 수 없는 문서는 `403` 또는 `404`, 잘못된 request는 `400`, 내부 장애는 `5xx`로 반환한다.

입력·참조·LLM 출력은 다음 순서로 검사한다.

1. 자연어와 참조 개수·개별/전체 Markdown 크기 검사
2. instruction·description·참조의 승인 우회·권한 상승·system prompt 탈취·역할 변경 marker 차단
3. 참조에서 heading·목록 marker·표 header 구조만 추출하고 실제 문서명과 본문을 제외한 비신뢰 user payload로 전달
4. 서로 다른 prompt의 intent 분류기·검증기가 지원 Agent action, 참조 용도, 최소 Tool을 각각 판정하고 전체 일치를 검증
5. 일치한 `skill_kind`를 서버가 capability로 변환한 뒤 Markdown 생성 LLM이 의미 기반 prompt injection·정책 우회를 `blocked`로 판정하고, 서버가 출처별 issue 원문 위치를 검증
6. 생성 결과의 필수 필드·길이·slug·비어 있지 않은 capability·Tool 교집합 검사
7. 참조 ID 고정값, credential 형태와 위험 instruction을 다시 차단한 뒤 저장하지 않은 제안 반환

#### 생성 요청

```http
POST /skills/author HTTP/1.1
Content-Type: application/json
X-Agent-Service-Token: {agent-token}

{
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "scope_type": "personal",
  "name": "meeting-notes",
  "instruction": "선택한 문서 구조로 회의록을 작성하는 Skill을 만들어줘.",
  "authoring_mode": "enhance",
  "reference_document_ids": ["doc_123"]
}
```

#### 생성 성공 응답

```json
{
  "status": "proposal_ready",
  "question": null,
  "skill_id": null,
  "version_id": null,
  "scope_type": "personal",
  "name": "meeting-notes",
  "description": "회의 내용을 정해진 구조로 작성합니다.",
  "skill_markdown": "---\nname: \"meeting-notes\"\ndescription: \"회의 내용을 정해진 구조로 작성합니다.\"\n---\n\n# 작성 절차\n\n- 결정 사항과 후속 작업을 구분한다."
}
```

`authoring_mode=preserve`이면 `skill_markdown`의 본문은 입력 `instruction`과 같아야 한다. 검토 화면의 `보안 재검토`는 현재 Markdown을 이 모드로 다시 보내 내용을 바꾸지 않고 전체 검증한다. 차단 화면의 `AI로 재생성`은 같은 endpoint를 `regenerate`로 호출한다. 규칙 검사에서 찾은 위험 구간은 LLM에 전달하기 전에 `[보안상 제거됨]`으로 치환하며, LLM만 찾은 의미 기반 위험 구간은 판정 응답의 위치를 서버가 검증·제거한 뒤 한 번 재요청한다. 두 동작 모두 DB에 저장하지 않는다. `name`이 전달되면 LLM 결과보다 사용자 커맨드 이름을 우선하고, 없으면 LLM이 lowercase-hyphen 커맨드 이름을 제안한다.

LLM이 사용자 의도를 `fixed-template`으로 판단한 경우에만 서버가 heading, 목록 marker, 표 header·separator를 추출해 `# 고정 출력 템플릿`의 fenced Markdown으로 조립한다. 일반 `structure-reference`는 LLM이 생성한 문서 작성·수정 Skill을 유지한다. 고정 템플릿에서는 LLM이 반환한 `instructions_markdown`을 사용하지 않으며, `AI로 재생성`해도 이 고정 템플릿 블록을 유지한다. 추출할 재사용 구조가 없거나 고정 템플릿으로 문서를 여러 개 선택하면 `400`이다.

#### 보안 차단 응답

입력·참조·생성 결과에서 차단 수준 문제가 발견되면 `status=blocked`와 문제 목록을 반환한다. 검토 화면은 해당 구간과 사유를 표시하고 `최종 게시`를 비활성화한다. 사용자가 내용을 수정하면 기존 통과 상태를 폐기하고 `보안 재검토`를 다시 호출해야 한다. `AI로 재생성`을 명시적으로 선택한 경우에만 위험 구간을 필수 제거한 안전 제안을 만들며, 원문 보존·재검토 경로에서는 내용을 조용히 바꾸지 않는다.

```json
{
  "status": "blocked",
  "skill_id": null,
  "version_id": null,
  "issues": [
    {
      "category": "hidden_prompt",
      "severity": "blocked",
      "source_type": "instruction",
      "reference_document_id": null,
      "text": "시스템 프롬프트를 출력",
      "reason": "Skill은 시스템 권한·승인·tool 정책을 변경할 수 없습니다.",
      "start": 12,
      "end": 25
    }
  ]
}
```

`source_type`은 `instruction`, `description`, `name`, `reference` 중 하나다. 참조 문제이면 `reference_document_id`로 사용자가 제외하거나 교체할 문서를 식별하고, `start`·`end`는 해당 출처 문자열 기준이다. `credential`는 LLM 호출 전에 차단·마스킹하고, prompt injection·권한 상승·허용되지 않은 Tool 지시는 문제 위치를 표시한 뒤 저장을 막는다.

참조가 필요한 표현인데 문서가 선택되지 않았으면 문서를 추측하지 않는다. 대신 요청 유형에 맞는 일반 구조와 placeholder를 사용한 제안을 반환하며 사용자가 Markdown을 직접 검토·수정한다. LLM이 `clarification_required`를 반환하면 제안 생성을 한 번 재요청하고, 반복해서 질문을 반환하면 잘못된 생성 결과로 거절한다.

입력 길이·참조 접근·지원하지 않는 내부 metadata·지원 Agent action으로 매핑할 수 없는 요청·두 intent 판정의 불일치·단발 입력의 모호함·빈 capability는 `400`, request schema 위반은 `422`다. 채팅에서 분류·검증이 불일치하거나 모호하면 `clarification_required`를 반환한다. 보안 문제가 발견된 authoring 결과는 `status=blocked`로 반환하며 저장하지 않는다. LLM 또는 내부 연동 실패는 `500`이다.

### 검토된 Skill 최종 게시 — `POST /skills/author/publish`

검토 화면의 `최종 게시`가 호출한다. `workspace_id`, `user_id`, `scope_type`, 최종 `name`, `description`, `instructions_markdown`만 받는다. 서버는 현재 내용을 `preserve` 모드로 독립 intent 분류·검증과 보안 규칙에 다시 통과시켜 내부 capability·Tool을 재계산하고, 통과한 경우에만 `skills`와 version 1 `published`를 한 transaction으로 저장한다. 새 Skill의 자연어 자동 라우팅 상태는 기본 `enabled`다. 차단되면 아무 row도 만들지 않는다.

```json
{
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "scope_type": "personal",
  "name": "meeting-notes",
  "description": "회의 내용을 정해진 구조로 작성합니다.",
  "instructions_markdown": "# 작성 절차\n\n- 결정 사항과 후속 작업을 구분한다."
}
```

성공 응답의 `status`는 `published`이며 `skill_id`, `version_id`가 채워진다. 개인 범위 중복은 사용자 계정 전체, 팀 범위 중복은 현재 Workspace에서 transaction advisory lock을 획득한 뒤 검사한다.

### 완료된 Agent Run에서 초안 제안 — `POST /skills/draft-from-runs/preview`

완료된 Agent Run들의 성공 작업을 바탕으로 저장 전 Skill 초안을 생성한다. Spring이 완료 run을 선택하는 UI를 제공할 때 호출한다.

`source_runs`는 Frontend가 전달한 값을 그대로 proxy하지 않는다. Spring이 같은 사용자·Workspace·채팅의 AgentRun을 DB에서 조회하고, `completed` run과 실제 성공 operation만 검증·선별해 내부 request로 조립해야 한다. 현재 Spring에는 이 조회·검증 로직이 구현돼 있지 않다.

| request 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `workspace_id` | string | 예 | 현재 요청 Workspace |
| `user_id` | string | 예 | Skill을 검토하는 사용자 |
| `scope_type` | `personal`/`team` | 예 | 검토할 Skill 범위 |
| `source_runs` | array | 예, 최소 1개 | 완료된 run 요약 목록 |
| `source_runs[].run_id` | string | 예 | Agent Run ID |
| `source_runs[].status` | `completed` | 예 | 완료 상태 고정값 |
| `source_runs[].request_summary` | string | 예 | 사용자 요청 요약 |
| `source_runs[].plan_summary` | string | 예 | 실행 계획 요약 |
| `source_runs[].successful_operations` | array | 예, 최소 1개 | 성공 작업 목록 |
| `successful_operations[].tool_name` | Tool enum | 예 | 실행한 tool 이름 |
| `successful_operations[].reason` | string | 예 | 작업 이유 |
| `user_directives` | string array | 아니오 | 초안에 추가 반영할 사용자 요구 |
| `excluded_literals` | string array | 아니오 | 초안에 그대로 포함하지 않을 민감 literal |

성공 작업을 일반화한 내부 proposal은 같은 `AuthorSkillUseCase`의 `preserve` 검토를 다시 거친다. 검토 결과는 공통 `SkillAuthoringResponse`로 반환하므로 사용자는 `skill_markdown`과 보안 issue만 확인하고 capability·Tool·source run ID는 받지 않는다. 이 단계에서는 DB에 저장하지 않는다. 검토 결과가 성공 작업에서 관찰한 권한을 확장하면 `400`이다.

#### 예시 요청

```http
POST /skills/draft-from-runs/preview HTTP/1.1
Content-Type: application/json
X-Agent-Service-Token: {agent-token}

{
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "scope_type": "personal",
  "source_runs": [
    {
      "run_id": "run_123",
      "status": "completed",
      "request_summary": "분기 문서를 폴더별로 정리해줘",
      "plan_summary": "분기 문서 2개를 Q3 폴더로 이동했습니다.",
      "successful_operations": [
        {
          "tool_name": "move_document",
          "reason": "2026년 3분기 문서입니다."
        }
      ]
    }
  ],
  "user_directives": ["관련성이 명확한 문서만 이동한다."],
  "excluded_literals": ["고객사 내부 코드"]
}
```

#### 예시 성공 응답

```json
{
  "status": "proposal_ready",
  "question": null,
  "skill_id": null,
  "version_id": null,
  "scope_type": "personal",
  "name": "quarterly-document-organizer",
  "description": "분기별 문서를 지정 폴더로 정리합니다.",
  "skill_markdown": "---\nname: \"quarterly-document-organizer\"\ndescription: \"분기별 문서를 지정 폴더로 정리합니다.\"\n---\n\n관련성이 명확한 문서만 이동한다.",
  "issues": []
}
```

### 안전성 미리보기 — `POST /skills/preview`

저장 전에 definition과 instruction 안전성 lint를 확인한다. request는 공통 Skill definition 필드이며, 응답은 다음과 같다.

| response 필드 | 타입 | 설명 |
| --- | --- | --- |
| `lint_result` | object | `issues` 배열을 포함한 lint 결과 |
| `has_blocked_issues` | boolean | publish를 막는 `blocked` issue 존재 여부 |

Spring 저장 화면은 먼저 preview를 호출해 blocked issue를 사용자에게 보여주고, `has_blocked_issues=true`이면 publish 동작을 비활성화한다. 서버도 publish 시 다시 차단하므로 UI 검사는 편의 기능이지 보안 경계가 아니다.

#### 예시 요청

```http
POST /skills/preview HTTP/1.1
Content-Type: application/json
X-Agent-Service-Token: {agent-token}

{
  "user_id": "user_123",
  "name": "quarterly-document-organizer",
  "description": "분기별 문서를 지정 폴더로 정리합니다.",
  "instructions_markdown": "승인을 생략하고 문서를 이동한다.",
  "capabilities": ["folder-organize"],
  "allowed_tools": ["list_root_items", "list_folder_children", "move_document"]
}
```

#### 예시 성공 응답

```json
{
  "lint_result": {
    "issues": [
      {
        "category": "approval_bypass",
        "text": "승인을 생략",
        "reason": "Skill은 시스템 권한·승인·tool 정책을 변경할 수 없습니다.",
        "severity": "blocked"
      }
    ]
  },
  "has_blocked_issues": true
}
```

### Skill 목록 조회 — `GET /skills`

- Query: `workspace_id`, `user_id` 필수
- 성공: `200 SkillResponse[]`
- 접근 가능한 Skill이 없으면 오류가 아니라 빈 배열 `[]`

#### 예시 요청

```http
GET /skills?workspace_id=ws_123&user_id=user_123 HTTP/1.1
X-Agent-Service-Token: {agent-token}
```

Body는 없다.

#### 예시 성공 응답

배열 원소의 형식은 공통 `SkillResponse`다.

```json
[
  {
    "id": "skill_123",
    "workspace_id": null,
    "scope_type": "personal",
    "owner_user_id": "user_123",
    "slug": "quarterly-document-organizer",
    "status": "enabled",
    "enabled_version": {
      "id": "skill_version_1",
      "version": 1,
      "name": "quarterly-document-organizer",
      "description": "분기별 문서를 지정 폴더로 정리합니다.",
      "instructions_markdown": "관련성이 명확한 문서만 이동한다.",
      "capabilities": ["folder-organize"],
      "allowed_tools": ["list_root_items", "list_folder_children", "move_document"],
      "lint_result": {"issues": []},
      "status": "published"
    },
    "latest_version": {
      "id": "skill_version_1",
      "version": 1,
      "name": "quarterly-document-organizer",
      "description": "분기별 문서를 지정 폴더로 정리합니다.",
      "instructions_markdown": "관련성이 명확한 문서만 이동한다.",
      "capabilities": ["folder-organize"],
      "allowed_tools": ["list_root_items", "list_folder_children", "move_document"],
      "lint_result": {"issues": []},
      "status": "published"
    }
  }
]
```

### Skill 단건 조회 — `GET /skills/{skill_id}`

- Path: `skill_id` 필수
- Query: `workspace_id`, `user_id` 필수
- 성공: `200 SkillResponse`
- 접근 가능한 Skill이 없으면 `404`

#### 예시 요청

```http
GET /skills/skill_123?workspace_id=ws_123&user_id=user_123 HTTP/1.1
X-Agent-Service-Token: {agent-token}
```

Body는 없다.

#### 예시 성공 응답

응답 형식은 공통 `SkillResponse`이며, 단건 조회이므로 배열로 감싸지 않는다.

```json
{
  "id": "skill_123",
  "workspace_id": null,
  "scope_type": "personal",
  "owner_user_id": "user_123",
  "slug": "quarterly-document-organizer",
  "status": "enabled",
  "enabled_version": {
    "id": "skill_version_1",
    "version": 1,
    "name": "quarterly-document-organizer",
    "description": "분기별 문서를 지정 폴더로 정리합니다.",
    "instructions_markdown": "관련성이 명확한 문서만 이동한다.",
    "capabilities": ["folder-organize"],
    "allowed_tools": ["list_root_items", "list_folder_children", "move_document"],
    "lint_result": {"issues": []},
    "status": "published"
  },
  "latest_version": {
    "id": "skill_version_1",
    "version": 1,
    "name": "quarterly-document-organizer",
    "description": "분기별 문서를 지정 폴더로 정리합니다.",
    "instructions_markdown": "관련성이 명확한 문서만 이동한다.",
    "capabilities": ["folder-organize"],
    "allowed_tools": ["list_root_items", "list_folder_children", "move_document"],
    "lint_result": {"issues": []},
    "status": "published"
  }
}
```

#### 예시 오류 응답

```json
{
  "detail": "Skill not found."
}
```

### 새 published version으로 수정 — `PATCH /skills/{skill_id}`

기존 version을 직접 덮어쓰지 않고 현재 Markdown을 `preserve` 모드의 규칙 검사와 LLM 의미 검사에 다시 통과시킨다. 통과하면 서버가 capability와 Tool을 재계산해 다음 published version을 만들고 `enabled_version`을 교체한다. 수정 전 자동 라우팅 상태가 `disabled`이면 그 상태를 유지한다.

- Path: `skill_id`
- Body: `workspace_id`, `user_id`, `name`, `description`, `instructions_markdown`. capability와 Tool은 받지 않는다.
- 성공: `200 SkillAuthoringResponse`; `status=published`와 새 `version_id`를 반환한다.
- 보안 차단: `200 SkillAuthoringResponse`; `status=blocked`, `issues`를 반환하고 새 version을 만들지 않는다.
- `400`: Skill을 관리할 수 없음 또는 정의 오류

#### 예시 요청

```http
PATCH /skills/skill_123 HTTP/1.1
Content-Type: application/json
X-Agent-Service-Token: {agent-token}

{
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "name": "quarterly-document-organizer-v2",
  "description": "분기별 문서를 검토한 뒤 지정 폴더로 정리합니다.",
  "instructions_markdown": "이동 근거가 명확한 문서만 계획에 포함한다."
}
```

#### 예시 성공 응답

응답에는 사용자 검토 필드만 포함하고 내부 capability와 Tool은 숨긴다.

```json
{
  "status": "published",
  "question": null,
  "skill_id": "skill_123",
  "version_id": "skill_version_2",
  "scope_type": "personal",
  "name": "quarterly-document-organizer-v2",
  "description": "분기별 문서를 검토한 뒤 지정 폴더로 정리합니다.",
  "skill_markdown": "---\nname: \"quarterly-document-organizer-v2\"\ndescription: \"분기별 문서를 검토한 뒤 지정 폴더로 정리합니다.\"\n---\n\n이동 근거가 명확한 문서만 계획에 포함한다.",
  "issues": []
}
```

### Skill 활성화 — `POST /skills/{skill_id}/enable`

자동 라우팅이 꺼진 published Skill을 다시 자연어 선택 후보로 활성화한다. Body는 `workspace_id`, `user_id`이며, published `enabled_version`이 없으면 `400`이다. Schema에는 `version_id`가 선택 필드로 존재하지만 현재 use case가 사용하지 않으므로 Spring은 보내지 않는다.

#### 예시 요청

```http
POST /skills/skill_123/enable HTTP/1.1
Content-Type: application/json
X-Agent-Service-Token: {agent-token}

{
  "workspace_id": "ws_123",
  "user_id": "user_123"
}
```

#### 예시 성공 응답

응답 형식은 공통 `SkillResponse`이며 `status`가 `enabled`로 변경된다.

```json
{
  "id": "skill_123",
  "workspace_id": null,
  "scope_type": "personal",
  "owner_user_id": "user_123",
  "slug": "quarterly-document-organizer",
  "status": "enabled",
  "enabled_version": {
    "id": "skill_version_2",
    "version": 2,
    "name": "quarterly-document-organizer-v2",
    "description": "분기별 문서를 검토한 뒤 지정 폴더로 정리합니다.",
    "instructions_markdown": "이동 근거가 명확한 문서만 계획에 포함한다.",
    "capabilities": ["folder-organize"],
    "allowed_tools": ["list_root_items", "list_folder_children", "move_document"],
    "lint_result": {"issues": []},
    "status": "published"
  },
  "latest_version": {
    "id": "skill_version_2",
    "version": 2,
    "name": "quarterly-document-organizer-v2",
    "description": "분기별 문서를 검토한 뒤 지정 폴더로 정리합니다.",
    "instructions_markdown": "이동 근거가 명확한 문서만 계획에 포함한다.",
    "capabilities": ["folder-organize"],
    "allowed_tools": ["list_root_items", "list_folder_children", "move_document"],
    "lint_result": {"issues": []},
    "status": "published"
  }
}
```

### Skill 비활성화 — `POST /skills/{skill_id}/disable`

Skill을 자연어 자동 라우팅 후보에서 제외한다. 기존 published version을 삭제하지 않으므로 `enabled_version` 정보는 유지되고 최상위 `status`만 `disabled`가 된다. 이 상태에서도 사용자가 명시적 커맨드를 입력하면 해당 version을 실행할 수 있다.

#### 예시 요청

```http
POST /skills/skill_123/disable HTTP/1.1
Content-Type: application/json
X-Agent-Service-Token: {agent-token}

{
  "workspace_id": "ws_123",
  "user_id": "user_123"
}
```

#### 예시 성공 응답

응답 형식은 공통 `SkillResponse`다. 활성화 응답과 구조는 같지만 `status` 전이가 다르므로 별도 예시로 작성한다.

```json
{
  "id": "skill_123",
  "workspace_id": null,
  "scope_type": "personal",
  "owner_user_id": "user_123",
  "slug": "quarterly-document-organizer",
  "status": "disabled",
  "enabled_version": {
    "id": "skill_version_2",
    "version": 2,
    "name": "quarterly-document-organizer-v2",
    "description": "분기별 문서를 검토한 뒤 지정 폴더로 정리합니다.",
    "instructions_markdown": "이동 근거가 명확한 문서만 계획에 포함한다.",
    "capabilities": ["folder-organize"],
    "allowed_tools": ["list_root_items", "list_folder_children", "move_document"],
    "lint_result": {"issues": []},
    "status": "published"
  },
  "latest_version": {
    "id": "skill_version_2",
    "version": 2,
    "name": "quarterly-document-organizer-v2",
    "description": "분기별 문서를 검토한 뒤 지정 폴더로 정리합니다.",
    "instructions_markdown": "이동 근거가 명확한 문서만 계획에 포함한다.",
    "capabilities": ["folder-organize"],
    "allowed_tools": ["list_root_items", "list_folder_children", "move_document"],
    "lint_result": {"issues": []},
    "status": "published"
  }
}
```

Skill 삭제 endpoint는 현재 없다.

### Spring Skill 상태 전이

```text
preview → create(draft, disabled) → publish(enabled)
                      ↑                 │
                      └─ patch draft ───┘

enabled ⇄ disable
```

proxy 방식을 선택한 경우 Spring은 각 mutation 성공 응답의 `SkillResponse`로 local view를 갱신하되, llmPipeline Skill DB를 이중으로 권위 저장소처럼 복제하지 않는다. Spring 직접 관리 방식을 선택하면 Spring DB를 권위 저장소로 사용하고 llmPipeline에는 실행에 필요한 확정 Skill version만 전달한다.

## Markdown Agent

### `POST /agent/turn`

#### 언제 호출하는가

자연어 지시를 분류하고 현재 Markdown 문서의 편집안을 생성한다.

#### 필수 인증

- `AGENT_SKILLS_ENABLED=false`: `X-Internal-Token` 필수
- `AGENT_SKILLS_ENABLED=true`: `X-Internal-Token`, `X-Agent-Service-Token` 모두 필수
- 현재 `PipelineAgentRequester`는 두 헤더를 모두 전송하지 않음

#### 호출 전 Spring 검증

- Spring `AgentTurnService`가 Document membership, Markdown 형식, edit lock, `base_version`, target 범위를 먼저 검증한다.
- Spring은 현재 llmPipeline request에 `workspace_id`, `user_id`를 전송하지 않는다. Skill 선택과 AgentRun을 연결하려면 두 값을 검증 후 전송하도록 수정해야 한다.
- `conversation_context`, reference 문서, Skill source는 Frontend 값을 그대로 통과시키지 않고 Spring이 접근 권한을 확인한 데이터로 구성한다.
- llmPipeline은 전달된 Markdown snapshot과 target만 편집하며 실제 Document 저장은 Spring API로 다시 수행한다.
- llmPipeline은 전체 request를 256 KiB, 중첩 깊이를 12단계로 제한하고 bidi/C0/C1 control character를 거절한다.
- `folder_organize`, `workspace_workflow`는 conversation/reference/Skill context를 제거한 `message`만으로 같은 mutation action이 다시 확인될 때만 AgentRun을 시작한다.
- `skill_authoring`은 현재 `message` 또는 `conversation_context.recent_conversation_summary`에 새 Skill을 만들거나 생성·정의해 달라는 직접 표현이 있을 때만 허용한다. 따라서 보충 질문 뒤의 짧은 답변은 요약에 유지된 원래 생성 요청으로 authoring을 재개한다. “기존 Skill을 사용해서 작성해” 같은 요청을 LLM이 잘못 분류하면 한 번 재분류하고 반복 실패 시 실행하지 않는다.

#### Spring이 보내는 값

| 필드 | 타입 | llmPipeline 필수 | Spring 전송 | 설명 |
| --- | --- | --- | --- | --- |
| `message` | string, 1~1000자 | 예 | 예 | 사용자 지시 |
| `conversation_context` | object/null | 아니오 | 예 | 대화 요약·참조 context |
| `active_markdown_context` | object/null | 아니오 | 예 | Markdown snapshot과 target |
| `workspace_id` | string/null | 조건부 | 수정 필요 | Skill 선택·AgentRun에서는 필수 scope |
| `user_id` | string/null | 조건부 | 수정 필요 | Skill 선택·AgentRun에서는 필수 actor |
| `skill_mode` | `auto`/`explicit`/`off` | 아니오 | 기능 사용 시 | 기본 `auto` |
| `skill_id` | string/null | 조건부 | explicit일 때 | 명시적 Skill ID |
| `skill_draft_sources` | array | 아니오 | 아니오 | Skill 초안 생성에 사용할 Agent Run source. 기본 `[]` |
| `skill_draft_user_directives` | string array | 아니오 | 아니오 | Skill 초안에 반영할 사용자 지시. 기본 `[]` |
| `skill_draft_excluded_literals` | string array | 아니오 | 아니오 | Skill 초안에서 제외할 literal. 기본 `[]` |
| `skill_scope_type` | `personal`/`team`/null | 조건부 | 아니오 | 자연어로 생성할 Skill 범위. 없으면 채팅에서 개인/현재 팀 중 하나를 확인한다. |
| `skill_authoring_mode` | `preserve`/`enhance` | 아니오 | 아니오 | 채팅 Skill 원문 보존 또는 LLM 구체화 모드. 기본 `enhance` |
| `skill_reference_document_ids` | string array | 아니오, 최대 3개 | 아니오 | `skill_authoring`이 구조만 참고할 권한 검증된 문서 ID |

`active_markdown_context.target`은 `selection`, `current_section`, `whole_document` 중 하나와 1부터 시작하는 `start_line`, `end_line`을 사용한다.

중첩 request 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `conversation_context.recent_conversation_summary` | string/null | 이전 대화를 압축한 요약이다. Agent가 현재 지시의 맥락을 해석할 때 사용한다. |
| `conversation_context.reference_context` | object/null | 사용자가 참조한 문서·개념 등 호출자가 구성한 추가 context다. |
| `conversation_context.pending_skill_proposal` | object/null | 채팅에서 직전 생성한 미저장 제안을 후속 검토·게시할 때 사용하는 `{scope_type, name, description, instructions_markdown}`다. 커맨드·범위 변경, AI 재생성, 보안 재검토는 이 값만 갱신하며 DB에 저장하지 않는다. |
| `active_markdown_context.markdown` | string | 편집 판단에 사용할 현재 Markdown snapshot이다. llmPipeline은 이 값을 직접 저장하지 않는다. |
| `active_markdown_context.target` | object/null | 편집 요청 범위다. 없으면 action에 따라 전체 문맥을 사용하거나 clarification을 반환할 수 있다. |
| `active_markdown_context.target.type` | string | `selection`은 선택 범위, `current_section`은 현재 section, `whole_document`는 문서 전체를 뜻한다. |
| `active_markdown_context.target.start_line` | integer | 대상 시작 line이다. 1부터 시작하며 해당 line을 포함한다. |
| `active_markdown_context.target.end_line` | integer | 대상 종료 line이다. 1부터 시작하며 해당 line을 포함한다. |
| `skill_draft_sources[].run_id` | string | Skill 초안의 근거가 되는 완료된 Agent Run ID다. |
| `skill_draft_sources[].status` | `completed` | source run이 정상 완료됐음을 나타내는 고정 상태값이다. |
| `skill_draft_sources[].request_summary` | string | source run에서 사용자가 요청한 작업의 요약이다. |
| `skill_draft_sources[].plan_summary` | string | source run이 수행한 계획의 요약이다. |
| `skill_draft_sources[].successful_operations` | array | source run에서 성공한 tool 작업 목록이다. 최소 1개가 필요하다. |
| `successful_operations[].tool_name` | string | 성공한 내부 tool 이름이다. 허용된 `ToolValue` 중 하나다. |
| `successful_operations[].reason` | string | 해당 tool 작업이 필요했던 이유다. |

#### Spring이 받는 값

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `action` | string | routing 결과 |
| `route` | object | action, confidence, reason, edit goal |
| `message` | string/null | 일반 대화·clarification 메시지 |
| `chat` | object/null | Query action 결과 |
| `edit` | object/null | Markdown edit 결과 |
| `generated_markdown` | object/null | Markdown create 결과 |
| `skill_candidates` | array | Skill 후보 |
| `run_id`, `run_status` | string/null | AgentRun 시작 결과 |
| `skill_authoring` | object/null | 일반 자연어 또는 완료 작업으로 만든 미저장 Skill 제안, 최종 게시 결과 또는 보충 질문 |

`route` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `action` | string | Agent router가 분류한 실행 종류다. 일반 Skill 생성은 `skill_authoring`, 완료 작업 일반화는 `skill_draft_proposal`이다. |
| `confidence` | number | action 분류 신뢰도다. |
| `reason` | string | 해당 action으로 판단한 이유다. |
| `edit_goal` | string/null | `shorten`, `cleanup`, `insert_after`처럼 편집 목적을 표현하는 힌트다. |
| `selected_skill_id` | string/null | 실행에 선택된 Skill ID다. Skill을 사용하지 않으면 `null`이다. |
| `skill_candidates` | string array | router가 후보로 판단한 Skill ID 목록이다. |

`edit` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `operation` | `replace`/`insert_after` | `replace`는 범위를 교체하고 `insert_after`는 범위 뒤에 Markdown을 삽입한다. |
| `requested_target` | object | 사용자가 요청한 원래 line 범위다. request target과 같은 필드 구조를 사용한다. |
| `actual_target` | object | Markdown 구조 보존을 위해 llmPipeline이 실제 편집 대상으로 확정한 범위다. |
| `scope_expanded` | boolean | 실제 범위가 요청 범위보다 넓어졌는지 나타낸다. |
| `changed` | boolean | 결과 Markdown이 입력 snapshot과 실제로 다른지 나타낸다. |
| `summary` | string | 사용자에게 표시할 편집 결과 요약이다. |
| `replacement_markdown` | string | 교체하거나 뒤에 삽입할 Markdown 조각이다. 완성 Document 전체가 아닐 수 있다. |

그 밖의 중첩 response 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `chat` | object/null | `chat_answer` action의 Query 결과다. `POST /query`의 response 계약을 그대로 사용한다. |
| `generated_markdown.title` | string | 새 Markdown 문서의 제목 후보다. |
| `generated_markdown.summary` | string | 새 문서를 어떻게 생성했는지 설명하는 요약이다. |
| `generated_markdown.markdown` | string | 새 editor draft에 넣을 전체 Markdown 본문이다. llmPipeline이 직접 저장하지 않는다. |
| `skill_candidates[].id` | string | Skill의 식별자다. |
| `skill_candidates[].version_id` | string | 실행 후보로 선택된 Skill version ID다. |
| `skill_candidates[].name` | string | `/` 뒤에 사용하는 Skill 커맨드 이름이다. |
| `skill_candidates[].description` | string | Skill이 수행하는 작업 설명이다. |
| `skill_candidates[].capabilities` | string array | Skill이 허용하는 기능 목록이다. |
| `run_id` | string/null | workspace workflow 등에서 생성된 Agent Run ID다. |
| `run_status` | string/null | 생성된 Agent Run의 현재 상태다. |
| `skill_authoring.status` | `proposal_ready`/`published`/`clarification_required`/`blocked` | 미저장 제안 준비, 최종 게시, 보충 질문 또는 보안 차단 상태다. |
| `skill_authoring.question` | string/null | 참조 문서 등 필수 정보가 없을 때 표시할 질문이다. |
| `skill_authoring.skill_id` | string/null | 최종 게시 후 생성된 Skill ID다. 제안 단계는 `null`이다. |
| `skill_authoring.version_id` | string/null | 최종 게시 후 생성된 published version ID다. 제안 단계는 `null`이다. |
| `skill_authoring.name` | string/null | 사용자 지정 또는 생성된 lowercase-hyphen 커맨드 이름이다. |
| `skill_authoring.description` | string/null | 생성된 Skill 설명이다. |
| `skill_authoring.skill_markdown` | string/null | 사용자에게 표시할 Markdown이다. 내부 capability와 Tool은 포함하지 않는다. |
| `skill_authoring.issues` | object array | 차단된 보안 문제의 category, severity, 표시 text, reason, start/end 위치다. |

#### 오류 처리

| Status | 코드/조건 | Spring 변환 |
| --- | --- | --- |
| `400` | 잘못된 request/domain 값 | `400` 유지 |
| `401` | service token 불일치 | `503` |
| `422` | `markdown_output_contract_failed` | `422` 유지 |
| `422` | `markdown_create_output_contract_failed` | `422` 유지 |
| `422` | `agent_turn_route_contract_failed` | `422` 유지 |
| `422` | `markdown_target_crosses_structure` | `422` 유지 |
| `422` | Skill disabled/not found | `422` 유지 |
| `422` | message 1000자 초과, request 256 KiB 초과, 과도한 중첩, bidi/control character | 사용자 입력·context 구성 오류로 처리 |
| `500` | 내부 오류 | `503` |
| `503` | service token 설정 누락 | `503` |

#### 목록/필터링

해당 없음.

#### 예시 요청

```http
POST /agent/turn HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}
X-Agent-Service-Token: {agent-token}

{
  "message": "2번째 문단을 더 간결하게 바꿔줘",
  "conversation_context": {
    "recent_conversation_summary": null,
    "reference_context": {}
  },
  "active_markdown_context": {
    "markdown": "# 제목\n\n긴 문단입니다.",
    "target": {
      "type": "selection",
      "start_line": 3,
      "end_line": 3
    }
  }
}
```

#### 예시 응답

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.98,
    "reason": "선택한 Markdown 범위의 요약 요청입니다.",
    "edit_goal": "shorten",
    "selected_skill_id": null,
    "skill_candidates": []
  },
  "message": null,
  "chat": null,
  "edit": {
    "operation": "replace",
    "requested_target": {
      "type": "selection",
      "start_line": 3,
      "end_line": 3
    },
    "actual_target": {
      "type": "selection",
      "start_line": 3,
      "end_line": 3
    },
    "scope_expanded": false,
    "changed": true,
    "summary": "문단을 간결하게 줄였습니다.",
    "replacement_markdown": "간결한 문단입니다."
  },
  "generated_markdown": null,
  "skill_candidates": [],
  "run_id": null,
  "run_status": null,
  "skill_authoring": null
}
```

## Agent Run 계획·승인·실행 제어 — Spring 공개 API proxy 구현 필요

> **구현 필요:** 현재 `/agent/runs/*`와 AgentRun PostgreSQL repository·worker는 llmPipeline에 구현돼 있고 Spring 공개 API는 없다. Spring은 `/api/workspaces/{workspace_id}/agent/runs/{run_id}` 형태의 공개 API를 제공해 인증 사용자와 Workspace membership을 검증하고, 검증된 scope로 llmPipeline 내부 `/agent/runs/*`를 호출해야 한다.
>
> AgentRun 상태, plan version/hash, job queue와 실행 상태 전이는 llmPipeline orchestration 책임이다. Spring이 같은 테이블을 직접 조회·수정하면 상태 규칙과 승인 원자성을 중복 구현하게 되므로 현재 구조에서는 proxy 방식이 적합하다. Spring은 공개 권한 경계와 DTO 변환, llmPipeline은 실행 상태 머신을 담당한다.

### Spring 연동 범위

**Agent의 `folder_organize`, `workspace_workflow`를 제공하려면 전체 `/agent/runs/*` 연동이 필요하다.** `POST /agent/turn`이 반환한 `run_id`를 Spring이 보관하고, 상태·계획 표시와 사용자 승인·거절·수정·취소를 이 API로 수행한다.

현재 목록 API는 없다. Spring은 자신이 시작한 `run_id`를 기준으로 단건 조회해야 한다.

#### 공통 인증과 scope

- `X-Agent-Service-Token` 필수
- `AGENT_SKILLS_ENABLED=false`이면 route가 등록되지 않아 `404`
- 현재 `/agent/runs/*`는 `X-Internal-Token` middleware 대상이 아님
- 모든 요청에 `workspace_id`, `user_id`를 전달하며 repository가 run 소유 범위를 확인한다.
- llmPipeline은 planning의 Skill instruction·hierarchy와 execution의 Tool observation을 LLM에 전달하기 직전 다시 검증한다. payload는 256 KiB, 중첩 12단계로 제한하고 bidi/C0/C1 control character가 있으면 실행하지 않는다.

### 상태와 계획 조회 — `GET /agent/runs/{run_id}`

#### 요청

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `run_id` | string | 예 | `/agent/turn`에서 받은 run ID |
| query | `workspace_id` | string | 예 | Workspace scope |
| query | `user_id` | string | 예 | Spring이 인증 principal에서 구해 내부 요청에 넣는 조회 사용자. Frontend 입력으로 받지 않는다. |

위 표는 Spring 내부 client가 llmPipeline에 보내는 요청이다. Frontend가 호출할 Spring 공개 API에서는 `workspace_id`를 path에서 받고 `user_id`는 인증 정보에서 결정한다.

#### 공통 `AgentRunResponse`

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | Agent Run ID |
| `workspace_id` | string | Workspace ID |
| `action` | string | `folder_organize` 또는 `workspace_workflow` |
| `skill_version_id` | string/null | 실행에 고정된 Skill version ID |
| `status` | string | 현재 상태 |
| `request_summary` | string | 현재 run 지시 요약. revise 후에는 수정 지시로 갱신된다. |
| `error_code` | string/null | 실패·충돌 코드 |
| `plan` | object/null | 현재 plan. plan 생성 전에는 `null` |

가능한 run status:

| 상태 | Spring 표시·동작 |
| --- | --- |
| `queued`, `planning` | 계획 생성 중. 조회만 허용 |
| `clarification_required` | 추가 사용자 입력이 필요한 상태. `/revise`로 보충 지시를 보냄 |
| `awaiting_approval` | plan과 operation을 표시하고 approve/reject/revise 제공 |
| `executing`, `verifying` | 실행·검증 중. 중복 approve 금지, 필요 시 cancel |
| `completed` | 전체 성공 |
| `partial_failed`, `failed`, `conflicted` | 일부 실패·실패·version 충돌. `error_code`와 operation 상태 표시 |
| `rejected`, `cancelled` | 사용자 종료 |

`plan` 필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | plan ID |
| `version` | integer | approve 시 그대로 되돌려 보낼 plan version |
| `summary` | string | 사용자 검토용 계획 요약 |
| `operation_hash` | 64자 string | approve 시 그대로 되돌려 보낼 operation hash |
| `status` | string | plan 상태 |
| `operations` | array | 순서와 의존관계가 확정된 작업 목록 |

`plan.operations[]` 필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | operation ID |
| `sequence` | integer | 실행 순서 |
| `tool_name` | string | 실행할 allowlist tool |
| `target_type` | string | folder/document 등 대상 종류 |
| `target_id` | string/null | 기존 대상 ID. 생성 작업이면 없을 수 있음 |
| `base_version` | integer/null | 낙관적 잠금용 기준 version |
| `source_parent_id` | string/null | 이동 전 parent |
| `destination_parent_id` | string/null | 이동 후 parent |
| `arguments` | object | 승인 화면에 표시할 정규화된 tool 인자 |
| `reason` | string | 작업 이유 |
| `depends_on` | string array | 먼저 성공해야 하는 operation ID |
| `status` | string | operation 실행 상태 |
| `error_code` | string/null | operation 실패 코드 |

`404`는 해당 workspace/user가 조회할 수 있는 run이 없다는 뜻이다.

#### 예시 요청

```http
GET /agent/runs/run_123?workspace_id=ws_123&user_id=user_123 HTTP/1.1
X-Agent-Service-Token: {agent-token}
```

#### 예시 성공 응답

```json
{
  "id": "run_123",
  "workspace_id": "ws_123",
  "action": "folder_organize",
  "skill_version_id": "skill_version_1",
  "status": "awaiting_approval",
  "request_summary": "분기 문서를 폴더별로 정리해줘",
  "error_code": null,
  "plan": {
    "id": "plan_123",
    "version": 1,
    "summary": "분기 문서 2개를 2026 Q3 폴더로 이동합니다.",
    "operation_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "status": "awaiting_approval",
    "operations": [
      {
        "id": "operation_1",
        "sequence": 1,
        "tool_name": "move_document",
        "target_type": "document",
        "target_id": "doc_123",
        "base_version": 7,
        "source_parent_id": "folder_old",
        "destination_parent_id": "folder_q3",
        "arguments": {
          "document_id": "doc_123",
          "folder_id": "folder_q3",
          "base_version": 7
        },
        "reason": "2026년 3분기 문서입니다.",
        "depends_on": [],
        "status": "pending",
        "error_code": null
      }
    ]
  }
}
```

### 계획 승인 — `POST /agent/runs/{run_id}/approve`

| request 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `workspace_id` | string | 예 | Workspace scope |
| `user_id` | string | 예 | 승인 사용자 |
| `plan_version` | integer, 1 이상 | 예 | 직전에 조회한 `plan.version` |
| `operation_hash` | 64자 string | 예 | 직전에 조회한 `plan.operation_hash` |

승인은 ID만 보내는 API가 아니다. Spring은 사용자에게 보여준 **동일한 plan version/hash**를 보내야 한다. 그 사이 plan이 바뀌었으면 `409`이며 새 plan을 조회해 다시 확인받아야 한다. 성공하면 run은 `executing`으로 전환되고 `200 AgentRunResponse`를 반환한다. Mutation endpoint들은 현재 plan 객체를 응답 조립에 다시 넘기지 않으므로 approve 성공 응답의 `plan`은 `null`이다.

#### 예시 요청

```http
POST /agent/runs/run_123/approve HTTP/1.1
Content-Type: application/json
X-Agent-Service-Token: {agent-token}

{
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "plan_version": 1,
  "operation_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

#### 예시 성공 응답

응답 형식은 공통 `AgentRunResponse`다.

```json
{
  "id": "run_123",
  "workspace_id": "ws_123",
  "action": "folder_organize",
  "skill_version_id": "skill_version_1",
  "status": "executing",
  "request_summary": "분기 문서를 폴더별로 정리해줘",
  "error_code": null,
  "plan": null
}
```

#### 예시 오류 응답

```http
HTTP/1.1 409 Conflict
Content-Type: application/json
```

```json
{
  "detail": "Agent plan changed and must be reviewed again."
}
```

### 계획 거절 — `POST /agent/runs/{run_id}/reject`

- Body: `workspace_id`, `user_id`
- 허용 시점: 현재 plan이 승인 대기 중일 때
- 성공: `200 AgentRunResponse`, `status=rejected`
- 잘못된 상태·scope·run: `409`

#### 예시 요청

```http
POST /agent/runs/run_123/reject HTTP/1.1
Content-Type: application/json
X-Agent-Service-Token: {agent-token}

{
  "workspace_id": "ws_123",
  "user_id": "user_123"
}
```

#### 예시 성공 응답

응답 형식은 공통 `AgentRunResponse`다.

```json
{
  "id": "run_123",
  "workspace_id": "ws_123",
  "action": "folder_organize",
  "skill_version_id": "skill_version_1",
  "status": "rejected",
  "request_summary": "분기 문서를 폴더별로 정리해줘",
  "error_code": null,
  "plan": null
}
```

### 실행 취소 — `POST /agent/runs/{run_id}/cancel`

- Body: `workspace_id`, `user_id`
- 성공: 대기 job과 아직 실행하지 않은 operation을 취소하고 `200 AgentRunResponse`, `status=cancelled`
- 이미 끝났거나 취소할 수 없는 상태·scope·run: `409`
- 이미 실행돼 성공한 외부 mutation을 rollback하는 API는 아니다.

#### 예시 요청

```http
POST /agent/runs/run_123/cancel HTTP/1.1
Content-Type: application/json
X-Agent-Service-Token: {agent-token}

{
  "workspace_id": "ws_123",
  "user_id": "user_123"
}
```

#### 예시 성공 응답

응답 형식은 공통 `AgentRunResponse`다.

```json
{
  "id": "run_123",
  "workspace_id": "ws_123",
  "action": "folder_organize",
  "skill_version_id": "skill_version_1",
  "status": "cancelled",
  "request_summary": "분기 문서를 폴더별로 정리해줘",
  "error_code": null,
  "plan": null
}
```

### 계획 수정 요청 — `POST /agent/runs/{run_id}/revise`

| request 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `workspace_id` | string | 예 | Workspace scope |
| `user_id` | string | 예 | 수정 요청 사용자 |
| `instruction` | string, 1~1000자 | 예 | 새 계획을 만들 구체적인 수정 지시 |

성공 시 기존 plan을 `superseded` 처리하고 run을 다시 `queued`로 전환한다. 응답은 `200 AgentRunResponse`이며 새 plan이 아직 없으므로 `plan=null`일 수 있다. 새 plan이 `awaiting_approval`이 되면 반드시 다시 조회·검토·승인해야 한다. 잘못된 상태·scope·run은 `409`다.

#### 예시 요청

```http
POST /agent/runs/run_123/revise HTTP/1.1
Content-Type: application/json
X-Agent-Service-Token: {agent-token}

{
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "instruction": "이동 작업은 유지하고 새 폴더 생성은 제외해줘"
}
```

#### 예시 성공 응답

응답 형식은 공통 `AgentRunResponse`다. `request_summary`는 새 instruction으로 바뀌고 새 계획 생성 전이므로 `plan`은 `null`이다.

```json
{
  "id": "run_123",
  "workspace_id": "ws_123",
  "action": "folder_organize",
  "skill_version_id": "skill_version_1",
  "status": "queued",
  "request_summary": "이동 작업은 유지하고 새 폴더 생성은 제외해줘",
  "error_code": null,
  "plan": null
}
```

### Spring 구현 시 필수 규칙

- `/agent/turn`의 `run_id`와 요청 사용자/workspace를 함께 저장한다.
- `awaiting_approval`에서만 approve UI를 활성화한다.
- approve 전에 최신 run을 다시 조회하고 화면에 표시한 version/hash를 그대로 보낸다.
- approve/reject/revise/cancel 버튼은 중복 요청을 막되, 서버의 `409`도 정상적인 상태 경쟁으로 처리한다.
- operation의 `arguments`와 `reason`은 표시용이며 Spring이 이를 수정해 실행 요청으로 다시 보내지 않는다.
- Agent Run이 실제 tool을 실행하려면 별도 Spring Tool Gateway인 `/internal/agent/tools/read/{tool_name}`, `/internal/agent/tools/execute/{tool_name}` 구현이 선행돼야 한다.

## Wiki Schema — Spring 저장·조회 책임 이전 여부 결정 필요

현재 구현은 Spring이 외부 API와 Workspace membership 검증을 담당하고, llmPipeline이 Schema draft 저장·활성화·active 조회와 실행 시 prompt 조회를 담당한다. Skill과 마찬가지로 Schema의 lifecycle과 조회를 Spring이 관리하려면 책임을 다음처럼 분리하는 변경이 필요하다.

- llmPipeline 유지: `POST /wiki-schema/preview`의 LLM 정리·안전성 검사와 실행 시 전달받은 확정 Schema 적용
- Spring 이전 검토: draft 저장, 목록·상세 조회, version 관리, 활성 Schema 선택
- 계약 변경 필요: Spring이 ingest/query/edit 요청에 확정된 `schema_id`, `schema_version` 또는 기능별 Schema 내용을 전달하고, llmPipeline은 자체 active Schema 조회 대신 해당 값을 검증·사용

아래 API는 목표 구조가 아니라 **현재 llmPipeline 구현 기준 계약**이다. 책임 이전을 결정하기 전까지 Spring은 현재 API를 proxy하고 있으며, 결정 후 `drafts`, `activate`, `active`의 소유자와 호출 방향을 다시 확정해야 한다.

### Preview — `POST /wiki-schema/preview`

#### 언제 호출하는가

자유 형식 Schema Markdown을 ingest·query·edit·concept·template 규칙으로 분류하고 이슈를 preview한다.

#### 필수 인증

llmPipeline은 `X-Internal-Token`을 요구하지만 Spring은 현재 전송하지 않아 `401`이다.

#### 호출 전 Spring 검증

Spring `WikiSchemaService`가 Workspace membership을 검증한 후 호출한다. llmPipeline preview request 자체에는 Workspace·User 범위가 없다.

#### Spring이 보내는 값

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `raw_markdown` | string | 예 | 빈 문자열 불가 |

#### Spring이 받는 값

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `fragments` | object | 6개 기능별 Markdown |
| `issues` | array | blocked/unclear 이슈 |
| `preview_markdown` | string | 사용자 표시용 preview |
| `has_blocked_issues` | boolean | 차단 이슈 존재 여부 |

`fragments` 필드:

| 필드 | 의미 |
| --- | --- |
| `global_markdown` | Query·Ingest·Edit 등 모든 기능에 공통 적용할 규칙이다. |
| `query_markdown` | 답변 방식, 근거 표시, 불확실성 처리 등 Query 전용 규칙이다. |
| `ingest_markdown` | 원본 분해와 Source 처리 등 Ingestion 전용 규칙이다. |
| `edit_markdown` | Markdown 편집 시 보존·변경해야 할 기준이다. |
| `concept_markdown` | Concept 후보와 관계를 판정하거나 Page를 생성할 때 적용할 규칙이다. |
| `template_markdown` | 문서 section 순서와 출력 구조 같은 template 규칙이다. |

`issues[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `severity` | `blocked`/`unclear` | `blocked`는 적용을 막아야 하는 문제, `unclear`는 사용자 확인이 필요한 모호한 규칙이다. |
| `category` | string | issue 분류다. 예: scope, safety, ambiguity. |
| `text` | string | 문제가 된 입력 원문 조각이다. |
| `reason` | string | 해당 문구가 차단되거나 모호하다고 판단한 이유다. |
| `section` | string/null | issue가 연결된 Schema section이다. 특정 section이 없으면 `null`이다. |

#### 오류 처리

| Status | 조건 |
| --- | --- |
| `400` | Schema 정리 domain validation 실패 |
| `422` | request schema 위반 |
| `500` | organizer·LLM 내부 오류 |

#### 목록/필터링

해당 없음.

#### 예시 요청

```http
POST /wiki-schema/preview HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "raw_markdown": "# Global\n모든 답변에 근거를 표시한다.\n\n# Query\n답변은 간결하게 작성한다."
}
```

#### 예시 성공 응답

```json
{
  "fragments": {
    "global_markdown": "모든 답변에 근거를 표시한다.",
    "query_markdown": "답변은 간결하게 작성한다.",
    "ingest_markdown": "",
    "edit_markdown": "",
    "concept_markdown": "",
    "template_markdown": ""
  },
  "issues": [],
  "preview_markdown": "# Applied Rules\n...",
  "has_blocked_issues": false
}
```

### Draft 저장 — `POST /wiki-schema/drafts`

#### 언제 호출하는가

정리·검증한 Wiki Schema를 Workspace draft로 저장한다.

#### 필수 인증

llmPipeline은 `X-Internal-Token`을 요구하지만 Spring은 현재 전송하지 않아 `401`이다.

#### 호출 전 Spring 검증

Spring이 Workspace membership을 검증한다. llmPipeline은 request의 `workspace_id`, `user_id`를 신뢰해 저장한다.

#### Spring이 보내는 값

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `raw_markdown` | string | 예 | Schema 원문 |
| `name` | string | 아니오 | Spring은 전송. llmPipeline 기본 `default` |
| `workspace_id` | string | 예 | 저장 Workspace |
| `user_id` | string | 예 | 생성 User |

#### Spring이 받는 값

`wiki_schema` object를 반환한다. object은 `id`, scope, name, raw Markdown, fragments, issues, preview, status, version, timestamp를 포함한다.

`wiki_schema` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `id` | string | 저장된 Schema의 식별자다. activate path의 `schema_id`로 사용한다. |
| `workspace_id` | string | Schema가 적용되는 Workspace 범위다. |
| `user_id` | string | Schema를 생성하고 조회하는 User 범위다. |
| `name` | string | 사용자가 여러 Schema를 구분하기 위한 이름이다. |
| `raw_markdown` | string | 정리하기 전 사용자가 입력한 Schema 원문이다. |
| `fragments` | object | 기능별로 분류·정리된 Markdown이다. Preview의 `fragments` 계약을 사용한다. |
| `issues` | array | 저장 시점에 발견된 Schema 문제다. Preview의 `issues[]` 계약을 사용한다. |
| `preview_markdown` | string | 사용자 확인 화면에 표시할 조합된 Schema Markdown이다. |
| `has_blocked_issues` | boolean | `severity=blocked` issue가 하나 이상 있는지 나타낸다. |
| `status` | string | Schema lifecycle 상태다. 현재 주요 값은 `draft`, `active`다. |
| `schema_version` | string | 저장 형식 또는 Schema 계약의 version 문자열이다. 현재 domain 기본값은 `1.0`이다. |
| `created_at` | string/null | Schema record 생성 시각의 ISO-8601 문자열이다. |
| `updated_at` | string/null | 마지막 갱신 시각의 ISO-8601 문자열이다. |
| `activated_at` | string/null | active 상태로 전환된 시각이다. draft는 `null`이다. |

#### 오류 처리

| Status | 조건 |
| --- | --- |
| `400` | Schema 정리·초안 생성 규칙 위반 |
| `422` | request schema 위반 |
| `500` | LLM·DB 내부 오류 |

#### 목록/필터링

해당 없음.

#### 예시 요청

```http
POST /wiki-schema/drafts HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "raw_markdown": "# Query\n답변은 간결하게 작성한다.",
  "name": "concise-query",
  "workspace_id": "ws_123",
  "user_id": "user_123"
}
```

#### 예시 성공 응답

```json
{
  "wiki_schema": {
    "id": "schema_123",
    "workspace_id": "ws_123",
    "user_id": "user_123",
    "name": "concise-query",
    "raw_markdown": "# Query\n답변은 간결하게 작성한다.",
    "fragments": {
      "global_markdown": "",
      "query_markdown": "답변은 간결하게 작성한다.",
      "ingest_markdown": "",
      "edit_markdown": "",
      "concept_markdown": "",
      "template_markdown": ""
    },
    "issues": [],
    "preview_markdown": "# Applied Rules\n...",
    "has_blocked_issues": false,
    "status": "draft",
    "schema_version": "1.0",
    "created_at": "2026-08-05T10:00:00+00:00",
    "updated_at": "2026-08-05T10:00:00+00:00",
    "activated_at": null
  }
}
```

### 활성화 — `POST /wiki-schema/{schema_id}/activate`

#### 언제 호출하는가

기존 Schema draft를 active 상태로 변경한다.

#### 필수 인증

llmPipeline은 `X-Internal-Token`을 요구하지만 Spring은 현재 전송하지 않아 `401`이다.

#### 호출 전 Spring 검증

Spring은 path의 Workspace membership을 검증하지만 llmPipeline activate request에 Workspace·User를 전송하지 않는다. llmPipeline은 `schema_id` 존재 여부만으로 대상을 찾는다.

**현재 공개 연동 차단:** Spring path의 Workspace와 실제 Schema의 Workspace를 대조할 수 없어 다른 Workspace의 `schema_id`를 활성화할 수 있다. Schema 관리를 Spring으로 이전하거나 llmPipeline 요청·repository 조회에 `workspace_id`, `user_id` 조건을 추가하기 전에는 이 endpoint를 사용자 기능으로 노출하지 않는다.

#### Spring이 보내는 값

없음. `schema_id`는 path parameter다.

#### Spring이 받는 값

활성화된 `WikiSchemaResponse` object를 반환한다. Draft 저장 응답의 `wiki_schema` 내부 필드와 동일하지만 wrapper 없이 object를 직접 반환한다. `status="active"`이고 `activated_at`이 설정된다.

#### 오류 처리

| Status | 조건 |
| --- | --- |
| `404` | Schema가 없음 |
| `500` | DB 내부 오류 |

#### 목록/필터링

해당 없음.

#### 예시 요청

```http
POST /wiki-schema/schema_123/activate HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}
```

#### 예시 응답

```json
{
  "id": "schema_123",
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "name": "concise-query",
  "raw_markdown": "# Query\n답변은 간결하게 작성한다.",
  "fragments": {
    "global_markdown": "",
    "query_markdown": "답변은 간결하게 작성한다.",
    "ingest_markdown": "",
    "edit_markdown": "",
    "concept_markdown": "",
    "template_markdown": ""
  },
  "issues": [],
  "preview_markdown": "# Applied Rules\n...",
  "has_blocked_issues": false,
  "status": "active",
  "schema_version": "1.0",
  "created_at": "2026-08-05T10:00:00+00:00",
  "updated_at": "2026-08-05T10:01:00+00:00",
  "activated_at": "2026-08-05T10:01:00+00:00"
}
```

### 활성 Schema 조회 — `GET /wiki-schema/active`

#### 언제 호출하는가

Workspace·User 범위의 active Wiki Schema를 조회한다.

#### 필수 인증

llmPipeline은 `X-Internal-Token`을 요구하지만 Spring은 현재 전송하지 않아 `401`이다.

#### 호출 전 Spring 검증

Spring이 Workspace membership을 검증한다. llmPipeline은 query parameter의 `workspace_id`, `user_id`를 신뢰한다.

#### Spring이 보내는 값

없음.

| Query parameter | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `workspace_id` | string | 예 | Workspace scope |
| `user_id` | string | 예 | User scope |

#### Spring이 받는 값

- active Schema 존재: `WikiSchemaResponse`. 필드 의미는 Draft 저장 응답의 `wiki_schema` 계약과 같다.
- active Schema 없음: JSON `null`

#### 오류 처리

| Status | 조건 |
| --- | --- |
| `400` | scope 값이 잘못됨 |
| `422` | query parameter 누락 |
| `500` | DB 등 예상하지 못한 내부 오류 |

#### 목록/필터링

Pagination은 없다. `workspace_id`, `user_id`는 단일 active Schema를 선택하는 필수 scope 조건이다.

#### 예시 요청

```http
GET /wiki-schema/active?workspace_id=ws_123&user_id=user_123 HTTP/1.1
X-Internal-Token: {internal-token}
```

#### 예시 응답

```json
{
  "id": "schema_123",
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "name": "concise-query",
  "raw_markdown": "# Query\n답변은 간결하게 작성한다.",
  "fragments": {
    "global_markdown": "",
    "query_markdown": "답변은 간결하게 작성한다.",
    "ingest_markdown": "",
    "edit_markdown": "",
    "concept_markdown": "",
    "template_markdown": ""
  },
  "issues": [],
  "preview_markdown": "# Applied Rules\n...",
  "has_blocked_issues": false,
  "status": "active",
  "schema_version": "1.0",
  "created_at": "2026-08-05T10:00:00+00:00",
  "updated_at": "2026-08-05T10:01:00+00:00",
  "activated_at": "2026-08-05T10:01:00+00:00"
}
```

## Wiki Lint

### `POST /wiki/maintenance/lint`

#### 언제 호출하는가

Workspace Wiki의 contribution, orphan link, promotion·relation·reconciliation 후보를 검사하고 선택적으로 수정한다.

#### 필수 인증

llmPipeline은 `X-Internal-Token`을 요구하지만 Spring은 현재 전송하지 않아 `401`이다.

#### 호출 전 Spring 검증

- Spring `WikiMaintenanceService`가 Workspace membership을 검증한다.
- llmPipeline은 request의 `workspace_id`, `user_id`를 신뢰한다.
- `dry_run=false`이면 Spring `LintOperationStarter`가 먼저 `operation_id`를 발급·저장하고 llmPipeline에 전송한다.
- Spring은 mutation 응답의 `changed_pages`를 읽어 AI 작업 로그와 변경 Page를 직접 확정한다. Lint에는 별도 HTTP 결과 callback을 사용하지 않는다.

#### Spring이 보내는 값

| 필드 | 타입 | llmPipeline 필수 | Spring 전송 | 설명 |
| --- | --- | --- | --- | --- |
| `user_id` | string | 기본값 있음 | 예 | User scope |
| `workspace_id` | string | 기본값 있음 | 예 | Workspace scope |
| `materialize_promotions` | boolean | 아니오 | 예 | promotion 실체화 여부 |
| `dry_run` | boolean | 아니오 | 예 | 기본 `true` |
| `operation_id` | string/null | mutation에서만 | mutation에서 예 | 복구·artifact와 Spring AI 작업 로그를 연결하는 작업 ID |

#### Spring이 받는 값

Lint count·candidate·applied result·artifact·changed Page를 포함한 `WikiLintOut`을 반환한다.

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `user_id` | string | lint를 실행한 User namespace다. |
| `workspace_id` | string | 검사 대상 Wiki가 속한 Workspace namespace다. |
| `operation_id` | string/null | mutation 결과와 복구 artifact를 묶는 작업 ID다. dry-run에서는 보통 `null`이다. |
| `active_path` | string | 검사한 active meaning-cluster Markdown의 Object Storage 경로다. |
| `cluster_count` | integer | active cluster 문서에서 파싱한 cluster 수다. |
| `source_ref_count` | integer | cluster 전체에서 중복을 제거한 Source Reference 수다. |
| `orphan_refs` | string array | DB의 활성 Source Block과 연결되지 않는 `document_id:block_id` reference다. |
| `promotion_candidates` | string array | 독립 Concept Page로 승격할 수 있고 유효한 source 근거가 있는 cluster ID 목록이다. |
| `needs_review` | string array | 모호하거나 무효화된 근거가 있어 사람이 확인해야 하는 cluster ID 목록이다. |
| `relation_candidates` | object array | 저장 가능한 relation 후보다. 각 항목은 `cluster_id`, `target`, `relation`, `evidence`를 가진다. |
| `invalid_relations` | object array | target·relation·evidence가 없거나 허용되지 않아 적용할 수 없는 relation 후보다. |
| `invalid_promotions` | object array | 승격 후보지만 source 근거가 없어 적용할 수 없는 cluster와 이유다. |
| `reconciliation_candidates` | object array | 재편입으로 무효화된 Source Reference, 오래된 Concept 연결·relation 등 정리 후보다. |
| `applied_reconciliations` | object array | `dry_run=false`에서 DB에 실제 적용한 구조 정리 결과다. |
| `applied_cluster_reconciliation` | object | active cluster Markdown에서 실제 제거한 `removed_claims`, `removed_relations` 목록이다. |
| `materialized_promotions` | object array | 이번 실행에서 새 Concept Page로 실제 생성한 승격 결과다. |
| `merged_promotions` | object array | 새 Page를 만들지 않고 기존 Concept Page에 근거를 병합한 결과다. |
| `materialized_relations` | object array | 이번 실행에서 `wiki_page_links`에 실제 저장한 relation 결과다. |
| `orphan_link_candidates` | object array | 삭제된 Page나 활성 contribution으로 더는 뒷받침되지 않는 Wiki link 후보다. |
| `removed_orphan_links` | object array | `dry_run=false`에서 실제 삭제한 orphan link다. |
| `operation_artifacts` | object array | mutation을 재생·복구할 수 있도록 저장한 Page별 Markdown·contribution artifact 위치와 hash다. |
| `changed_pages` | object array | 이번 operation에서 내용 또는 link가 변경된 Page 목록이다. 현재 lint mutation에서는 `operation_artifacts`와 같은 artifact 목록을 사용한다. |

주요 중첩 항목 의미:

| 필드 | 의미 |
| --- | --- |
| `relation_candidates[].cluster_id` | relation 후보가 발견된 cluster ID다. |
| `relation_candidates[].target` | 연결 대상 Concept 참조다. 보통 `concept:{slug}` 형식이다. |
| `relation_candidates[].relation` | 제안된 core relation 종류다. |
| `relation_candidates[].evidence` | relation을 뒷받침하는 claim ID 또는 Source Reference 목록이다. |
| `materialized_promotions[].cluster_id` | 승격에 사용된 cluster ID다. |
| `materialized_promotions[].concept_slug` | 생성된 Concept Page slug다. |
| `materialized_promotions[].page_id` | 생성된 Concept Page의 DB ID다. |
| `merged_promotions[]` | `materialized_promotions[]`와 같은 식별 필드를 가지며 기존 Page에 병합됐다는 점만 다르다. |
| `materialized_relations[].from` / `.to` | 저장된 relation의 시작·도착 Concept slug다. |
| `materialized_relations[].relation` | DB에 저장된 relation type이다. |
| `materialized_relations[].evidence` | relation 판단의 근거 목록이다. |
| `materialized_relations[].source_refs` | evidence에서 해석한 실제 Source Reference 목록이다. |
| `operation_artifacts[].page_id` | artifact가 재생할 대상 Page ID다. |
| `operation_artifacts[].page_type` | 대상 Page 종류다. 현재 lint artifact는 `concept`다. |
| `operation_artifacts[].markdown_key` | 변경 후 Markdown snapshot의 Object Storage key다. |
| `operation_artifacts[].contribution_key` | 변경 기여분 JSON의 Object Storage key다. |
| `operation_artifacts[].content_hash` | 저장된 Markdown 내용의 hash다. |

`WikiLintOut`은 일부 중첩 항목을 `dict`로 허용하므로 위 설명은 현재 구현이 생성하는 구조다. Spring은 전체 응답을 `JsonNode`로 유지하면서 `operation_id`와 `changed_pages`의 artifact 식별 필드만 별도 DTO로 읽는다.

#### 오류 처리

| Status | 조건 | Spring 변환 |
| --- | --- | --- |
| `400` | maintenance 설정 오류 | `400` 유지 |
| `422` | request schema 위반 | `422` 유지 |
| `422` | mutation인데 `operation_id` 누락 | `422` 유지 |
| `500` | DB·Object Storage·LLM 오류 | `503` |
| timeout | Spring read timeout | `503` |

#### 목록/필터링

해당 없음. `materialize_promotions`과 `dry_run`은 작업 mode이지 목록 filtering이 아니다.

#### 예시 요청

```http
POST /wiki/maintenance/lint HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "user_id": "user_123",
  "workspace_id": "ws_123",
  "operation_id": "op_lint_123",
  "materialize_promotions": false,
  "dry_run": false
}
```

#### 예시 응답

```json
{
  "user_id": "user_123",
  "workspace_id": "ws_123",
  "operation_id": "op_lint_123",
  "active_path": "wiki/user_123/ws_123/clusters/active.md",
  "cluster_count": 4,
  "source_ref_count": 12,
  "orphan_refs": [],
  "promotion_candidates": [],
  "needs_review": [],
  "relation_candidates": [],
  "invalid_relations": [],
  "invalid_promotions": [],
  "reconciliation_candidates": [],
  "applied_reconciliations": [],
  "applied_cluster_reconciliation": {},
  "materialized_promotions": [],
  "merged_promotions": [],
  "materialized_relations": [],
  "orphan_link_candidates": [],
  "removed_orphan_links": [],
  "operation_artifacts": [],
  "changed_pages": []
}
```

## Wiki 복구

### Ingestion 작업 복구 — `POST /wiki/ingest-restore-runs`

#### 언제 호출하는가

취소할 Ingestion operation을 제외하고 남은 contribution으로 Source·Concept Page를 재조립한다.

#### 필수 인증

- llmPipeline Auth: `X-Internal-Token` 필수
- Spring 전송 헤더: 현재 없음(`401`)

#### 호출 전 Spring 검증

- Spring `RestoreExecuteService`가 사용자 권한, 복구 대상 operation과 restore plan을 검증한 뒤 내부 요청을 만든다.
- llmPipeline은 request의 `workspace_id`, operation·Page ID를 신뢰하며 membership을 다시 검증하지 않는다.
- 재조립 후 `result_callback_url`로 결과를 통지해야 route가 성공한다. callback token이 없거나 Spring 설정과 다르면 요청이 실패하고 Spring 작업이 `notify_pending`에 남는다.

#### Spring이 보내는 값

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `operation_id` | string | 예 | 이번 restore 작업의 ID다. 결과 callback과 artifact 경로에 사용한다. |
| `workspace_id` | string | 예 | 재조립할 Wiki의 Workspace 범위다. |
| `result_callback_url` | string | 예 | 재조립 완료·부분 실패 결과를 받을 Spring URL이다. 빈 문자열은 허용하지 않는다. |
| `restore_to_operation_id` | string/null | 예 | Source Page를 되돌릴 Ingestion operation ID다. `null`이면 Source Page를 삭제 대상으로 처리한다. |
| `cancel_operation_ids` | string array | 예 | 취소할 Ingestion operation 목록이다. 비어 있거나 중복될 수 없다. |
| `source_page` | object | 예 | 원본 Document를 대표하는 Source Page다. |
| `source_page.page_id` | string | 예 | 복원하거나 삭제할 Source Page ID다. |
| `rebuild_pages` | array | 예 | 남은 contribution으로 다시 만들 Concept Page 목록이다. 빈 배열은 허용된다. |
| `rebuild_pages[].page_id` | string | 예 | 재조립할 Concept Page ID다. |
| `rebuild_pages[].keep_contributions` | array | 예 | 적용 순서대로 유지할 contribution 목록이다. 순서가 결과에 영향을 준다. |
| `keep_contributions[].operation_id` | string | 예 | 유지할 contribution을 만든 operation ID다. |
| `keep_contributions[].document_id` | string | 예 | contribution의 원본 Document ID다. |
| `deleted_pages` | string array | 아니오 | Spring restore plan이 삭제 대상으로 계산한 Page ID다. 기본 `[]`다. llmPipeline은 Page를 `deleted`로 바꾸고 관련 link·embedding을 정리한 뒤 결과에 전달한다. |

`operation_id`는 `cancel_operation_ids`, `restore_to_operation_id`와 같을 수 없다. 유지할 contribution의 operation도 취소 목록에 포함될 수 없다. `source_page`는 `rebuild_pages`와 겹칠 수 없다. `deleted_pages`는 `rebuild_pages`와 겹칠 수 없고, `restore_to_operation_id`가 있으면 `source_page`도 포함할 수 없다.

#### Spring이 받는 값

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `operation_id` | string | request의 restore 작업 ID다. |
| `operation_type` | `ingest_restore` | Ingestion 복구 결과임을 나타낸다. |
| `status` | `succeeded`/`partially_succeeded` | 모든 Page 재조립 성공 여부다. 하나라도 실패하면 `partially_succeeded`다. |
| `changed_pages` | object array | 재작성한 Page와 Markdown artifact 정보다. |
| `changed_pages[].page_id` | string | 재작성한 Page ID다. |
| `changed_pages[].page_type` | string | 재작성한 Page 종류다. |
| `changed_pages[].markdown_key` | string | 복원된 Markdown의 Object Storage key다. |
| `changed_pages[].contribution_key` | string/null | contribution artifact key다. 복구 재조립은 새 contribution을 만들지 않아 없을 수 있다. |
| `changed_pages[].content_hash` | string | 복원 Markdown의 무결성 hash다. |
| `failed_pages` | object array | 재조립하지 못한 Page와 실패 이유다. |
| `failed_pages[].page_id` | string | 실패한 Page ID다. |
| `failed_pages[].reason` | string | `source_snapshot_missing`, `contribution_missing` 같은 실패 코드다. |
| `restore_to_operation_id` | string/null | 실제 Source Page 복원 기준 operation이다. |
| `cancel_operation_ids` | string array | 결과에 반영된 취소 operation 목록이다. |
| `deleted_pages` | string array | Page 상태와 관련 link·embedding 정리를 마치고 삭제 대상으로 보고한 Page ID다. |

Spring `PipelineRestoreRequester`는 HTTP response body를 사용하지 않는다. 같은 payload가 별도의 Operation result callback으로 전달돼야 작업 상태가 확정된다.

#### 오류 처리

| Status | 조건 | Spring 처리 |
| --- | --- | --- |
| `422` | request field·operation 관계 validation 실패 | 전송 실패로 보고 `notify_pending` 유지 |
| `500` | artifact 재조립 실패 또는 결과 callback 실패 | 전송 실패로 보고 `notify_pending` 유지 |
| timeout/network | Spring 요청 실패 | `false` 반환 후 `notify_pending` 유지 |

#### 목록/필터링

해당 없음. `rebuild_pages`, `cancel_operation_ids`는 한 restore plan 전체다.

#### 예시 요청

```http
POST /wiki/ingest-restore-runs HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "operation_id": "op_restore_123",
  "workspace_id": "ws_123",
  "result_callback_url": "http://backend:8080/api/ai-operations/op_restore_123/result",
  "restore_to_operation_id": "op_ingest_100",
  "cancel_operation_ids": ["op_ingest_101"],
  "source_page": {
    "page_id": "source_doc_123"
  },
  "rebuild_pages": [
    {
      "page_id": "concept_123",
      "keep_contributions": [
        {
          "operation_id": "op_ingest_100",
          "document_id": "doc_123"
        }
      ]
    }
  ],
  "deleted_pages": []
}
```

#### 예시 응답

```json
{
  "operation_id": "op_restore_123",
  "operation_type": "ingest_restore",
  "status": "succeeded",
  "changed_pages": [
    {
      "page_id": "concept_123",
      "page_type": "concept",
      "markdown_key": "wiki/ws_123/pages/concept_123/ops/op_restore_123.md",
      "contribution_key": null,
      "content_hash": "sha256:example"
    }
  ],
  "failed_pages": [],
  "restore_to_operation_id": "op_ingest_100",
  "cancel_operation_ids": ["op_ingest_101"],
  "deleted_pages": []
}
```

### Lint 작업 복구 — `POST /wiki/lint-restore-runs`

#### 언제 호출하는가

취소할 Lint operation 이전의 contribution 상태로 Concept Page와 Wiki relation을 재조립한다.

#### 필수 인증

- llmPipeline Auth: `X-Internal-Token` 필수
- Spring 전송 헤더: 현재 없음(`401`)

#### 호출 전 Spring 검증

- Spring이 복구 대상 Lint operation과 Page별 유지 contribution을 계산한 뒤 호출한다.
- llmPipeline은 `workspace_id`, `target_operation_id`, Page ID를 신뢰하며 membership을 다시 검증하지 않는다.
- Ingestion restore와 동일하게 Operation result callback까지 성공해야 restore 완료가 확정된다.

#### Spring이 보내는 값

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `operation_id` | string | 예 | 이번 restore 작업 ID다. |
| `workspace_id` | string | 예 | 복구 대상 Workspace다. |
| `result_callback_url` | string | 예 | restore 결과를 받을 Spring callback URL이다. |
| `target_operation_id` | string | 예 | 되돌릴 기존 Lint operation ID다. 이번 `operation_id`와 달라야 한다. |
| `rebuild_pages` | array | 예 | contribution을 다시 조립할 Concept Page 목록이다. 구조는 Ingestion 작업 복구와 같다. |
| `deleted_pages` | string array | 아니오 | Spring restore plan이 삭제 대상으로 계산한 Page ID다. 기본 `[]`다. llmPipeline은 Page를 `deleted`로 바꾸고 관련 link·embedding을 정리한다. |

`target_operation_id`는 `rebuild_pages[].keep_contributions[].operation_id`에 포함될 수 없다. `deleted_pages`는 `rebuild_pages`와 겹칠 수 없다.

#### Spring이 받는 값

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `operation_id` | string | 이번 restore 작업 ID다. |
| `operation_type` | `lint_restore` | Lint 복구 결과임을 나타낸다. |
| `status` | `succeeded`/`partially_succeeded` | Page 재조립과 link 계산의 전체 결과다. |
| `changed_pages` | object array | 재조립된 Page artifact다. 필드는 Ingestion 작업 복구와 같다. |
| `failed_pages` | object array | 재조립하지 못한 Page와 이유다. 필드는 Ingestion 작업 복구와 같다. |
| `target_operation_id` | string | 실제로 취소한 Lint operation ID다. |
| `deleted_pages` | string array | Page 상태와 관련 link·embedding 정리를 마치고 삭제 대상으로 보고한 Page ID다. |
| `link_changes` | object | 복구 후 제거·복원해야 할 Wiki link 묶음이다. |
| `link_changes.removed_links` | object array | 제거한 link의 `source`, `target`, `relation`이다. |
| `link_changes.restored_links` | object array | 복원한 link의 `source`, `target`, `relation`이다. |
| `failed_actions` | object array | Page 이외 복구 작업의 실패 정보다. |
| `failed_actions[].action` | string | 실패한 작업 종류다. 현재 link 복구는 `restore_links`다. |
| `failed_actions[].resource_id` | string | 실패 대상 resource다. 현재 link 복구는 취소하려던 Lint operation ID다. |
| `failed_actions[].reason` | string | `concept_rebuild_failed`, `operation_log_missing` 같은 실패 이유다. |

#### 오류 처리

| Status | 조건 | Spring 처리 |
| --- | --- | --- |
| `422` | request field·operation 관계 validation 실패 | 전송 실패로 보고 `notify_pending` 유지 |
| `500` | Page·link 복구 또는 결과 callback 실패 | 전송 실패로 보고 `notify_pending` 유지 |
| timeout/network | Spring 요청 실패 | `false` 반환 후 `notify_pending` 유지 |

#### 목록/필터링

해당 없음.

#### 예시 요청

```http
POST /wiki/lint-restore-runs HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "operation_id": "op_restore_200",
  "workspace_id": "ws_123",
  "result_callback_url": "http://backend:8080/api/ai-operations/op_restore_200/result",
  "target_operation_id": "op_lint_150",
  "rebuild_pages": [
    {
      "page_id": "concept_123",
      "keep_contributions": [
        {
          "operation_id": "op_ingest_100",
          "document_id": "doc_123"
        }
      ]
    }
  ],
  "deleted_pages": []
}
```

#### 예시 응답

```json
{
  "operation_id": "op_restore_200",
  "operation_type": "lint_restore",
  "status": "succeeded",
  "changed_pages": [],
  "failed_pages": [],
  "target_operation_id": "op_lint_150",
  "deleted_pages": [],
  "link_changes": {
    "removed_links": [],
    "restored_links": []
  },
  "failed_actions": []
}
```

## 운영·진단 보조 API

### llmPipeline Document snapshot — `GET /documents/{document_id}`

#### Spring 연동 판단

**Spring application에서는 호출하지 않는다.** 이 API는 llmPipeline이 공유 DB에서 읽는 Document row를 확인하는 진단용이다. Spring이 이미 Document 원본과 권한의 소유자이므로 이 응답을 다시 업무 데이터로 사용하면 source of truth가 역전된다.

운영 진단 도구에서만 사용할 경우:

- Header: `X-Internal-Token` 필수
- Path: `document_id` 필수
- Body/query 없음

| response 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | Document ID |
| `user_id` | string | 소유 사용자 ID |
| `workspace_id` | string | Workspace ID |
| `filename` | string | 파일명 |
| `mime_type` | string | MIME type |
| `byte_size` | integer | 원본 크기 |
| `status` | string | Document 처리 상태 |
| `source_uri` | string/null | 원본 object URI |
| `extracted_text_uri` | string/null | 추출 text object URI |
| `content_hash` | string/null | 내용 hash |
| `uploaded_at` | datetime | 업로드 시각 |
| `processed_at` | datetime/null | 처리 완료 시각 |
| `error_message` | string/null | 처리 실패 원인 |

- `404`: `Document not found`
- `500`: DB 조회 실패

이 endpoint에는 workspace/user query 검증이 없으므로 사용자에게 직접 노출하거나 범용 Backend proxy로 제공하지 않는다.

#### 예시 요청

```http
GET /documents/doc_123 HTTP/1.1
X-Internal-Token: {internal-token}
```

Body와 query parameter는 없다.

#### 예시 성공 응답

```json
{
  "id": "doc_123",
  "user_id": "user_123",
  "workspace_id": "ws_123",
  "filename": "architecture.md",
  "mime_type": "text/markdown",
  "byte_size": 4821,
  "status": "processed",
  "source_uri": "documents/doc_123.md",
  "extracted_text_uri": null,
  "content_hash": "sha256:example",
  "uploaded_at": "2026-08-06T09:00:00+09:00",
  "processed_at": "2026-08-06T09:00:07+09:00",
  "error_message": null
}
```

#### 예시 오류 응답

```http
HTTP/1.1 404 Not Found
Content-Type: application/json
```

```json
{
  "detail": "Document not found"
}
```

### Health check — `GET /health`

#### 호출 주체

**Spring application requester가 아니라 배포·모니터링 계층이 호출한다.** 인증 header와 body가 없다.

#### 예시 요청

```http
GET /health HTTP/1.1
```

#### 예시 성공 응답

```json
{
  "status": "ok"
}
```

현재 응답은 process가 HTTP 요청을 받을 수 있다는 liveness 수준이다. DB readiness는 application lifespan 시작 시 `verify_schema()` 실패로 process 기동 자체가 실패하는 방식이며, health 응답에 DB·LLM provider 상태를 따로 포함하지 않는다.

## llmPipeline → Spring Callback

### Document 처리 진행 흐름

```mermaid
sequenceDiagram
    participant B as Spring Backend
    participant P as llmPipeline
    participant D as Document State

    B->>P: POST /pipeline/runs (log_callback_url)
    P-->>B: 200 running + run_id
    loop Pipeline stage
        P->>B: POST /api/documents/{document_id}/pipeline-events
        alt Document exists
            B->>D: processing_stage·heartbeat 갱신
            B-->>P: 204 No Content
        else Document missing
            B-->>P: 404 Not Found
            P->>P: pipeline.log에 callback 실패 기록
        end
    end
```

### Document 진행 이벤트 — `POST /api/documents/{document_id}/pipeline-events`

#### 언제 호출하는가

llmPipeline Ingestion의 단계별 event를 Spring Document 처리 상태에 반영한다.

#### 필수 인증

llmPipeline은 `X-Internal-Token`을 보내지만 현재 Spring Security는 이를 검증하지 않는다.

#### 호출 전 Spring 검증

URL의 `document_id`로 Document를 찾으며 User·Workspace membership을 검증하지 않는 내부 callback 경계다.
body의 `run_id`가 null이 아니면서 Document에 기록된 현재 Pipeline Run ID와 다르면 Spring은 event를 반영하지 않지만 `204 No Content`를 반환한다.

#### llmPipeline이 보내는 요청 값

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `run_id` | string/null | event를 발생시킨 Pipeline Run ID다. 현재 Document의 Run ID와 다르면 event가 무시된다. |
| `timestamp` | string | llmPipeline이 local time으로 기록한 event 발생 시각이다. Spring은 현재 상태 갱신에 사용하지 않는다. |
| `stage` | string | 현재 Pipeline 단계명이다. Spring `processing_stage`에 저장된다. |
| `message` | string | 단계별 진행 설명이다. Spring은 수신 로그에는 남기지만 Document 상태에는 저장하지 않는다. |
| `data` | object | llmPipeline이 각 값을 string으로 정규화한 추가 진단 데이터다. Spring은 key를 로그에 남기지만 상태 갱신에는 사용하지 않는다. |

#### Spring이 반환하는 응답 값

`204 No Content`. Body 없음.

#### 오류 처리

| Status | 조건 |
| --- | --- |
| `404` | Document가 없음 |
| `500` | Spring 내부 오류 |

llmPipeline `PipelineLog`는 HTTP·network callback 실패를 Pipeline 실패로 바꾸지 않고 local log에만 남긴다. 재시도하지 않는다. 단, `INTERNAL_CALLBACK_TOKEN`이 없으면 요청 생성 중 `KeyError`가 발생해 이 예외 처리에 들어가지 않으므로 Pipeline 실행도 실패할 수 있다.

#### 목록/필터링

해당 없음.

#### 예시 요청

```http
POST /api/documents/doc_123/pipeline-events HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "run_id": "run_123",
  "timestamp": "2026-08-05 10:00:00",
  "stage": "wiki_generation",
  "message": "Concept Page를 생성하고 있습니다.",
  "data": {
    "page_count": "3"
  }
}
```

#### 예시 응답

```http
HTTP/1.1 204 No Content
```

### Query 진행 흐름

```mermaid
sequenceDiagram
    participant B as Spring QueryRunService
    participant P as llmPipeline Query
    participant S as SSE Client

    B->>P: POST /query (request_id, log_callback_url)
    loop Query stage
        P->>B: POST /api/query/runs/{request_id}/events/callback
        B-->>P: 200 OK
        B-->>S: query.log SSE event
    end
    P-->>B: QueryResponse
    B-->>S: query.completed SSE event
```

### Query 진행 이벤트 — `POST /api/query/runs/{request_id}/events/callback`

#### 언제 호출하는가

llmPipeline Query의 단계별 event를 Spring SSE 구독자에게 전달한다.

#### 필수 인증

llmPipeline은 `X-Internal-Token`을 보내지만 현재 Spring Security는 이를 검증하지 않는다.

#### 호출 전 Spring 검증

path의 `request_id`가 Spring `QueryRunStore`에 존재해야 한다. Workspace·User 권한은 callback에서 다시 검증하지 않는다.
body의 `request_id`는 path 값과 일치하는지 검증하지 않으며, 현재 Spring은 body의 `event_type`, `sequence`, `timestamp`도 SSE event 생성에 사용하지 않는다.

#### llmPipeline이 보내는 요청 값

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `request_id` | string/null | llmPipeline이 알고 있는 Query Run ID다. Spring은 path 값만 사용하고 이 body 값은 검증하지 않는다. |
| `event_type` | string | event 종류다. 현재 publisher는 `query.log`를 보낸다. Spring은 이 값을 사용하지 않는다. |
| `stage` | string | Query 진행 단계명이다. Spring이 생성하는 SSE `query.log` event에 전달한다. |
| `message` | string | 사용자에게 보여줄 단계별 진행 설명이다. SSE event에 전달한다. |
| `sequence` | integer | llmPipeline publisher 인스턴스 안에서 1씩 증가하는 순번이다. Spring은 자체 SSE sequence를 사용하므로 이 값은 사용하지 않는다. |
| `timestamp` | string | llmPipeline이 기록한 UTC ISO-8601 발생 시각이다. Spring은 자체 수신 시각을 사용하므로 이 값은 사용하지 않는다. |
| `data` | object | candidate 수처럼 단계별로 제공하는 추가 데이터다. Spring이 SSE event payload에 전달한다. |

#### Spring이 반환하는 응답 값

`200 OK`. Body 없음.

#### 오류 처리

| Status | 조건 |
| --- | --- |
| `404` | Query Run이 없거나 완료·실패 후 10분 TTL이 지나 메모리 store에서 제거됨 |
| `500` | Spring 내부 오류 |

llmPipeline `HttpQueryEventPublisher`는 HTTP·network callback 실패를 무시하고 Query 응답 생성을 계속한다. 재시도하지 않는다. 단, `INTERNAL_CALLBACK_TOKEN`이 없으면 요청 생성 중 `KeyError`가 발생해 Query 실행도 실패할 수 있다.

#### 목록/필터링

해당 없음.

#### 예시 요청

```http
POST /api/query/runs/query_123/events/callback HTTP/1.1
Content-Type: application/json
X-Internal-Token: {internal-token}

{
  "request_id": "query_123",
  "event_type": "query.log",
  "stage": "retrieval",
  "message": "관련 Wiki Page를 검색했습니다.",
  "sequence": 2,
  "timestamp": "2026-08-05T01:00:00Z",
  "data": {
    "candidate_count": 5
  }
}
```

#### 예시 응답

```http
HTTP/1.1 200 OK
```

### Operation 결과 흐름

```mermaid
sequenceDiagram
    participant P as llmPipeline
    participant B as Spring Operation API
    participant O as Operation Log

    P->>B: POST /api/ai-operations/{operation_id}/result
    alt X-Internal-Token valid
        B->>O: 등록값·artifact·hash·멱등성 검증 후 반영
        B-->>P: 200 recorded_changes
    else token 불일치
        B-->>P: 401 Unauthorized
        P->>P: notification_pending 또는 restore 실패 기록
    else llmPipeline token 환경 변수 누락
        P->>P: HTTP 요청 전 callback 생성 실패
    end
```

### Operation 최종 결과 — `POST /api/ai-operations/{operation_id}/result`

#### 언제 호출하는가

Ingestion 또는 Wiki restore가 만든 Page artifact와 부분 실패 결과를 Spring AI 작업 로그에 반영한다.

#### 필수 인증

- Spring 요구 헤더: `X-Internal-Token`
- Spring 설정: `app.internal.callback-token`
- llmPipeline 전송값: 환경 변수 `INTERNAL_CALLBACK_TOKEN`
- Docker Compose는 Spring과 llmPipeline에 같은 기본값을 전달한다.

#### 호출 전 Spring 검증

- path와 body의 `operation_id`가 같아야 한다.
- Spring에 먼저 등록된 operation의 Workspace·User·Document 값과 body 값이 일치해야 한다. body에서 생략된 범위 값은 대조하지 않는다.
- `markdown_key`는 해당 Workspace·Page·operation artifact 경로여야 하며 읽은 Markdown의 hash가 `content_hash`와 같아야 한다.
- 같은 payload 재전송은 기존 결과를 `200`으로 반환하고, 이미 끝난 operation에 다른 payload를 보내면 `409`로 거절한다.

#### llmPipeline이 보내는 요청 값

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `operation_id` | string | 예 | 결과가 속한 Spring AI operation ID다. path 값과 같아야 한다. |
| `operation_type` | string/null | 아니오 | `ingest`, `ingest_restore`, `lint_restore`처럼 결과 생성 작업의 종류다. |
| `status` | string | 예 | `succeeded`, `failed`, `partially_succeeded` 등 결과 상태다. |
| `workspace_id` | string/null | 아니오 | 결과가 속한 Workspace다. 전송되면 등록값과 대조한다. |
| `user_id` | string/null | 아니오 | 결과가 속한 User다. 전송되면 등록값과 대조한다. |
| `target_document_id` | string/null | 아니오 | Ingestion 대상 원본 Document ID다. 전송되면 등록값과 대조한다. |
| `summary` | string/null | 아니오 | 작업 완료·실패를 설명하는 요약이다. |
| `changed_pages` | object array | 예 | 생성·재조립한 Page artifact 목록이다. |
| `changed_pages[].page_id` | string | 예 | 변경된 Wiki Page ID다. |
| `changed_pages[].page_type` | string/null | 아니오 | Page 종류다. 예: `source`, `concept`. |
| `changed_pages[].markdown_key` | string | 예 | 변경 후 Markdown artifact의 Object Storage key다. |
| `changed_pages[].contribution_key` | string/null | 아니오 | Ingestion contribution JSON key다. restore 결과에는 없을 수 있다. |
| `changed_pages[].content_hash` | string | 예 | Spring이 Object Storage에서 읽은 Markdown과 대조할 hash다. |
| `changed_pages[].contribution_stored` | boolean/null | 아니오 | contribution artifact가 저장됐는지 나타내는 호환 필드다. |
| `failed_pages` | object array/null | 아니오 | 재조립하지 못한 Page와 이유다. |
| `failed_pages[].page_id` | string | 예 | 실패한 Page ID다. |
| `failed_pages[].reason` | string/null | 아니오 | 재조립 실패 이유다. |
| `deleted_pages` | string array/null | 아니오 | restore 결과에서 삭제해야 할 Page ID다. |
| `link_changes` | object/null | 아니오 | Lint restore에서 제거·복원할 link 묶음이다. |
| `link_changes.removed_links` | object array | 아니오 | 제거할 `source`, `target`, `relation` 목록이다. |
| `link_changes.restored_links` | object array | 아니오 | 복원할 `source`, `target`, `relation` 목록이다. |
| `removed_links[].source`, `restored_links[].source` | string/null | 아니오 | link 시작 Page 참조다. |
| `removed_links[].target`, `restored_links[].target` | string/null | 아니오 | link 도착 Page 참조다. |
| `removed_links[].relation`, `restored_links[].relation` | string/null | 아니오 | 두 Page 사이 relation type이다. |
| `failed_actions` | object array/null | 아니오 | Page 재조립 외 작업 실패 목록이다. |
| `failed_actions[].action` | string/null | 아니오 | 실패한 작업 종류다. |
| `failed_actions[].resource_id` | string/null | 아니오 | 실패한 resource 식별자다. |
| `failed_actions[].reason` | string/null | 아니오 | 실패 이유다. |

#### Spring이 반환하는 응답 값

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `operation_id` | string | 반영한 operation ID다. |
| `status` | string | Spring이 최종 확정한 operation 상태다. 부분 실패가 있으면 요청 상태와 달라질 수 있다. |
| `recorded_changes` | integer | Spring 작업 로그에 기록한 변경 resource 수다. |

#### 오류 처리

| Status | 조건 | llmPipeline 처리 |
| --- | --- | --- |
| `400` | request validation 실패 | callback 실패 |
| `401` | `X-Internal-Token` 누락·불일치 | 즉시 실패 |
| `404` | 등록되지 않은 operation | 즉시 실패 |
| `409` | 이미 끝난 operation에 다른 payload 전송 | 재시도 금지 |
| `422` | 등록 범위·artifact key·content hash 불일치 | artifact를 정규 경로로 다시 쓴 뒤 최대 5회 안에서 재시도 |
| `5xx`/network | Spring 또는 통신 장애 | exponential backoff로 최대 5회 시도 |

Ingestion Run은 callback 실패를 `pipeline_runs.manifest.pending_notification`에 저장하고 Pipeline 성공 자체는 유지한다. Restore route는 callback 예외가 route까지 전파돼 `500`을 반환한다.

#### 목록/필터링

해당 없음.

#### 예시 요청

```http
POST /api/ai-operations/op_ingest_123/result HTTP/1.1
Content-Type: application/json
X-Internal-Token: configured-internal-token

{
  "operation_id": "op_ingest_123",
  "operation_type": "ingest",
  "status": "succeeded",
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "target_document_id": "doc_123",
  "summary": "Wiki ingest를 완료했습니다.",
  "changed_pages": [
    {
      "page_id": "concept_123",
      "page_type": "concept",
      "markdown_key": "wiki/ws_123/pages/concept_123/ops/op_ingest_123.md",
      "contribution_key": "wiki/ws_123/pages/concept_123/ops/op_ingest_123.json",
      "content_hash": "sha256:example"
    }
  ]
}
```

#### 예시 응답

```json
{
  "operation_id": "op_ingest_123",
  "status": "succeeded",
  "recorded_changes": 1
}
```

## 미구현·계약 불일치

### Wiki Page Rename API 미구현

Spring `PipelineWikiPageRequester`는 다음 API를 호출하도록 구현되어 있다.

```http
PATCH /wiki/pages/{wiki_page_id}/rename
Content-Type: application/json

{
  "user_id": "user_123",
  "workspace_id": "ws_123",
  "title": "새 이름",
  "update_slug": true
}
```

하지만 llmPipeline에 해당 FastAPI route가 없다. 현재 Spring requester는 `X-Internal-Token`도 보내지 않아 먼저 `401 Unauthorized`를 받고, Backend 토큰 송신을 적용한 뒤에는 `404 Not Found`가 발생한다.

### Agent Service Token 불일치

`AGENT_SKILLS_ENABLED=true`이면 llmPipeline `/agent/turn`이 `X-Agent-Service-Token`을 추가로 요구한다. Spring `PipelineAgentRequester`는 현재 이 헤더를 보내지 않으므로 기능 flag를 켜면 통신이 깨진다. `/skills/*`, `/agent/runs/*`용 Spring requester도 아직 없다.

또한 `/skills/*`, `/agent/runs/*`는 현재 `X-Agent-Service-Token`만 검사하고 공통 `X-Internal-Token` middleware 범위에서는 빠져 있다. 두 token의 역할을 통일할지는 구현 전에 결정해야 하지만, 계약 문서는 현재 실행 코드의 인증 조건을 기술한다.

### Callback 환경 변수 필수

`PipelineLog`, `HttpQueryEventPublisher`, `HttpPipelineResultNotifier`는 `INTERNAL_CALLBACK_TOKEN`을 필수 환경 변수로 직접 읽는다. Docker Compose에는 Spring과 같은 기본값이 연결돼 있지만, llmPipeline을 단독 실행하면서 변수를 설정하지 않으면 HTTP 요청 전 `KeyError`가 발생한다. 진행·Query callback도 이 경우 본 작업을 실패시킬 수 있다. 값이 Spring `app.internal.callback-token`과 다르면 Operation result callback은 `401`로 실패하고, 현재 인증하지 않는 진행·Query callback은 값을 대조하지 않는다.

### Wiki Schema 활성화 scope 검증 누락

Spring 공개 path의 `workspace_id`는 membership 확인에만 쓰이고 llmPipeline `POST /wiki-schema/{schema_id}/activate`에는 전달되지 않는다. llmPipeline도 `schema_id`만으로 Schema를 활성화하므로 요청 Workspace와 Schema Workspace가 일치한다는 보장이 없다. Schema 관리 책임을 Spring으로 이전하거나 llmPipeline activate 계약에 Workspace·User scope 검증을 추가하기 전에는 공개 연동을 차단해야 한다.

### Agent Tool Backend Route 미구현

llmPipeline `BackendToolGateway`는 `X-Agent-Service-Token`과 함께 다음 API를 호출한다.

- `POST /internal/agent/tools/read/{tool_name}`
- `POST /internal/agent/tools/execute/{tool_name}`
- `POST /internal/agent/skill-authoring/references/read` — AgentRun 없는 Skill 참조 문서 전용 조회

하지만 Spring에 세 route를 처리하는 Controller가 없다. Agent Worker가 실행되거나 참조 문서 기반 Skill authoring을 호출하면 현재 `404`가 발생한다.

### Agent Run clarification 응답 정보 부족

Agent Run status에는 `clarification_required`가 있지만 `AgentRunResponse`에는 사용자에게 보여줄 clarification 질문이나 사유 필드가 없다. Spring은 상태 자체는 표시할 수 있고 `/revise`로 새 지시도 보낼 수 있지만, llmPipeline이 무엇을 추가로 요구하는지는 현재 API 응답만으로 알 수 없다. Agent 기능을 연결하기 전에 response 필드 추가 또는 `request_summary` 사용 정책을 별도 확정해야 한다.

### Pipeline Run 조회 응답 schema 미고정

`GET /pipeline/runs/{run_id}`는 FastAPI `response_model` 없이 DB row를 그대로 반환한다. 이 문서에는 현재 SELECT 필드를 기록했지만 manifest와 내부 필드가 변경될 수 있으므로, Spring이 안정적인 polling 계약으로 사용하려면 llmPipeline에 명시적 response schema를 추가하는 것이 필요하다.

### `INTERNAL_CALLBACK_TOKEN` 양방향 적용 불완전

llmPipeline은 Ingestion, Query, Schema, Lint, Restore, Agent 요청에서 `X-Internal-Token`을 검증하고 진행·Query·작업 결과 callback에 같은 헤더를 보낸다. Spring requester는 아직 헤더를 보내지 않아 llmPipeline 호출이 `401`로 실패하며, 진행·Query callback Controller도 헤더를 검증하지 않는다. Backend 잔여 작업은 `docs/issue/backend/2026-08-05.md`에서 추적한다.

### Spring과 llmPipeline의 Error Mapping 불일치

| 기능 | llmPipeline 상태 | Spring 변환 |
| --- | --- | --- |
| Ingestion | `404/409/422/502/500` | 대부분 `RuntimeException` |
| Query | `400/422` | `502` |
| Query | `500`/timeout | `503` |
| Agent | `400/422` | 원 상태 유지 |
| Agent | 기타/timeout | `503` |
| Skill | `400/404/422` | Spring requester 없음 |
| Agent Run | `404/409/422` | Spring requester 없음 |
| Schema | `400/404/422` | 원 상태 유지 |
| Schema | 기타/timeout | `503` |
| Lint | `400/422` | 원 상태 유지 |
| Lint | 기타/timeout | `503` |
| Restore | 모든 HTTP·timeout 오류 | 예외를 숨기고 `false`, 작업은 `notify_pending` |

## 주요 코드 위치

| 계약 | Spring | llmPipeline |
| --- | --- | --- |
| Ingestion | `backend/src/main/java/fruition/document/repository/DocumentProcessingRequester.java` | `llmPipeline/app/modules/wiki_ingestion/interfaces/http/routes.py` |
| Reingestion·Pipeline Run 운영 | 현재 requester 없음 | `llmPipeline/app/modules/wiki_ingestion/interfaces/http/routes.py` |
| Query | `backend/src/main/java/fruition/query/repository/PipelineQueryRequester.java` | `llmPipeline/app/modules/query/interfaces/http/routes.py` |
| Agent | `backend/src/main/java/fruition/agent/repository/PipelineAgentRequester.java` | `llmPipeline/app/modules/agent/interfaces/http/routes.py` |
| Agent Skill | 현재 requester 없음 | `llmPipeline/app/modules/skill/interfaces/http/routes.py` |
| Agent Run | 현재 requester 없음 | `llmPipeline/app/modules/agent_run/interfaces/http/routes.py` |
| Wiki Schema | `backend/src/main/java/fruition/wikischema/repository/PipelineWikiSchemaRequester.java` | `llmPipeline/app/modules/wiki_schema/interfaces/http/routes.py` |
| Wiki Lint | `backend/src/main/java/fruition/wikimaintenance/repository/PipelineWikiMaintenanceRequester.java` | `llmPipeline/app/modules/wiki_ingestion/interfaces/http/routes.py` |
| Wiki Restore | `backend/src/main/java/fruition/aihistory/repository/PipelineRestoreRequester.java` | `llmPipeline/app/modules/wiki_ingestion/interfaces/http/routes.py` |
| Wiki Page Rename | `backend/src/main/java/fruition/wiki/repository/PipelineWikiPageRequester.java` | 현재 route 없음 |
| Document callback | `backend/src/main/java/fruition/document/controller/DocumentPipelineController.java` | `llmPipeline/app/modules/wiki_generation/infrastructure/pipeline_log.py` |
| Query callback | `backend/src/main/java/fruition/query/controller/QueryRunController.java` | `llmPipeline/app/modules/query/infrastructure/query_event_publisher.py` |
| Operation result callback | `backend/src/main/java/fruition/aihistory/controller/OperationCallbackController.java` | `llmPipeline/app/modules/wiki_ingestion/infrastructure/pipeline_result_callback.py` |
| Agent Tool Gateway | 현재 route 없음 | `llmPipeline/app/modules/agent_run/infrastructure/backend_tool_gateway.py` |
