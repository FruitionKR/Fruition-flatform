# Agent Markdown 연동 계약

이 문서는 editor가 있는 채팅 화면에서 frontend, Spring backend, `llmPipeline`이 Markdown 편집과 생성을 연동하는 데 필요한 계약만 정의한다.

## 1. 처리 흐름

```text
사용자 입력
  -> frontend가 editor snapshot과 요청을 Spring backend에 전달
  -> Spring backend가 인증·권한·문서 버전을 확인
  -> Spring backend가 POST /agent/turn으로 llmPipeline 호출
  -> llmPipeline이 요청을 분류하고 처리
      chat_answer      -> 일반 채팅 답변
      markdown_edit    -> 기존 Markdown 교체안
      markdown_create  -> 새 Markdown draft
      clarify          -> 추가 입력 요청
      reject           -> 요청 거절
  -> Spring backend가 결과와 문서 식별 정보를 frontend에 반환
  -> frontend가 action에 따라 UI 처리
```

`llmPipeline` 내부의 routing, Markdown 생성·검증과 재시도 방식은 내부 구현이다. 외부에서는 최상위 `action`과 action별 결과 필드만 처리한다.

## 2. Frontend → Spring backend

Frontend는 요청 시점의 editor 상태를 하나의 snapshot으로 고정해 전달한다.

- Public endpoint: `POST /api/workspaces/{workspace_id}/agent/turn`
- 인증: 기존 workspace API와 동일한 Bearer token

```json
{
  "documentId": "document-id",
  "baseVersion": 12,
  "message": "선택한 문장을 자연스럽게 다듬어줘.",
  "conversationContext": {
    "recentConversationSummary": "최근 대화 요약",
    "referenceContext": {}
  },
  "editorSnapshot": {
    "markdown": "# 현재 문서\n\n다듬을 문장",
    "target": {
      "type": "selection",
      "startLine": 3,
      "endLine": 3
    }
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `message` | 예 | 사용자의 현재 요청 |
| `documentId` | 문서 편집 시 | 권한 검사와 저장 대상 확인에 사용하는 문서 ID |
| `baseVersion` | 문서 편집 시 | 요청 snapshot이 기준으로 삼은 저장 문서 버전 |
| `conversationContext` | 아니오 | 멀티턴 문맥과 추가 참고 정보 |
| `conversationContext.recentConversationSummary` | 아니오 | 최근 합의·요구사항을 압축한 요약 |
| `conversationContext.referenceContext` | 아니오 | 요청에 필요한 구조화된 참고 정보 |
| `editorSnapshot` | Markdown 편집 시 | 요청 시점의 저장 전 editor 상태 |
| `editorSnapshot.markdown` | editor snapshot 사용 시 | editor에 표시 중인 전체 Markdown |
| `editorSnapshot.target` | 아니오 | 실제 교체할 line 범위. 생략하면 문서 전체가 대상이 된다. |

`editorSnapshot.target` 규칙:

- `type`은 `selection`, `current_section`, `whole_document` 중 하나다.
- `startLine`과 `endLine`은 1-base, inclusive다.
- `current_section` 범위는 frontend가 계산한다.
- 문자 단위 selection은 지원하지 않는다. 선택한 문자가 포함된 line 전체를 보낸다.
- fence, table, frontmatter처럼 여러 줄로 구성된 Markdown 구조는 일부 line만 선택하지 않는다.

## 3. Spring backend → llmPipeline

Spring backend는 public DTO를 `llmPipeline`의 snake_case 요청으로 변환해 `POST /agent/turn`을 호출한다.

```json
{
  "message": "선택한 문장을 자연스럽게 다듬어줘.",
  "conversation_context": {
    "recent_conversation_summary": "최근 대화 요약",
    "reference_context": {}
  },
  "active_markdown_context": {
    "markdown": "# 현재 문서\n\n다듬을 문장",
    "target": {
      "type": "selection",
      "start_line": 3,
      "end_line": 3
    }
  }
}
```

변환 규칙:

| Backend 요청 | Pipeline 요청 |
| --- | --- |
| `message` | `message` |
| `conversationContext.recentConversationSummary` | `conversation_context.recent_conversation_summary` |
| `conversationContext.referenceContext` | `conversation_context.reference_context` |
| `editorSnapshot.markdown` | `active_markdown_context.markdown` |
| `editorSnapshot.target.type` | `active_markdown_context.target.type` |
| `editorSnapshot.target.startLine` | `active_markdown_context.target.start_line` |
| `editorSnapshot.target.endLine` | `active_markdown_context.target.end_line` |

`documentId`와 `baseVersion`은 Spring backend와 frontend 사이의 권한·동시성 정보이므로 `llmPipeline`에 전달하지 않는다.

## 4. llmPipeline → Spring backend

`llmPipeline`은 다음 공통 형식으로 응답한다. 사용하지 않는 action별 결과 필드는 `null`이다.

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.95,
    "reason": "선택 문장 편집 요청",
    "edit_goal": "cleanup"
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
      "start_line": 2,
      "end_line": 4
    },
    "scope_expanded": true,
    "changed": true,
    "summary": "선택 문장을 자연스럽게 정리했습니다.",
    "replacement_markdown": "문맥을 포함해 다듬어진 문장"
  },
  "generated_markdown": null
}
```

최상위 `action`이 실제 처리 결과이며 frontend의 유일한 분기 기준이다. `route`는 내부 routing 결과를 확인하기 위한 진단 정보이므로 Spring backend는 그대로 전달하되 frontend 동작 결정에 사용하지 않는다.

최상위 응답 필드:

| 필드 | 타입 | nullable | 사용 action | 설명 |
| --- | --- | --- | --- | --- |
| `action` | enum string | 아니오 | 전체 | 실제 처리 결과. `chat_answer`, `markdown_edit`, `markdown_create`, `clarify`, `reject` 중 하나 |
| `route` | object | 아니오 | 전체 | 내부 routing 결과와 진단 정보 |
| `message` | string | 예 | `clarify`, `reject` | 사용자에게 표시할 안내 |
| `chat` | object | 예 | `chat_answer` | 일반 채팅 답변 |
| `edit` | object | 예 | `markdown_edit` | 기존 Markdown 교체안 |
| `generated_markdown` | object | 예 | `markdown_create` | 새 Markdown draft |

### 4.1 `route`

| 필드 | 타입 | nullable | 설명 |
| --- | --- | --- | --- |
| `route.action` | enum string | 아니오 | router가 판정한 action |
| `route.confidence` | number | 아니오 | routing confidence. 0.0 이상 1.0 이하 |
| `route.reason` | string | 아니오 | routing 판단에 대한 진단 정보 |
| `route.edit_goal` | string | 예 | 내부 편집·생성 전략 힌트 |

`route.action`은 routing 이후 실행 조건에 따라 최상위 `action`과 다를 수 있다. Spring backend와 frontend는 최상위 `action`을 기준으로 처리한다.

### 4.2 `chat`

`action == "chat_answer"`일 때 `chat`은 기존 Query 응답 전체를 포함한다.

| 필드 | 타입 | nullable | 설명 |
| --- | --- | --- | --- |
| `chat.answer` | string | 아니오 | 사용자에게 표시할 답변 |
| `chat.related_pages` | `RelatedPage[]` | 아니오 | 답변과 관련된 page 목록 |
| `chat.evidence_snippets` | `EvidenceSnippet[]` | 아니오 | 답변 근거 snippet 목록 |
| `chat.graph_context` | `GraphContext` | 아니오 | 조회한 graph node와 edge |
| `chat.traversal_paths` | `TraversalPath[]` | 아니오 | graph 탐색 경로 목록 |

`RelatedPage`:

| 필드 | 타입 |
| --- | --- |
| `id` | string |
| `page_type` | string |
| `title` | string |
| `slug` | string |
| `relevance_score` | number |
| `role` | string |
| `depth` | integer |

`EvidenceSnippet`:

| 필드 | 타입 |
| --- | --- |
| `rank` | integer |
| `source_document_id` | string |
| `source_block_ids` | `string[]` |
| `source_refs` | `SourceReference[]` |
| `text` | string |

`SourceReference`:

| 필드 | 타입 |
| --- | --- |
| `source_document_id` | string |
| `source_block_id` | string |

`GraphContext`:

| 필드 | 타입 |
| --- | --- |
| `nodes` | `RelatedPage[]` |
| `edges` | `TraversalEdge[]` |

`TraversalEdge`:

| 필드 | 타입 |
| --- | --- |
| `from_page_id` | string |
| `to_page_id` | string |
| `link_type` | string |
| `role` | string |
| `score` | number |

`TraversalPath`:

| 필드 | 타입 |
| --- | --- |
| `path_id` | string |
| `role` | string |
| `used_for_answer` | boolean |
| `score` | number |
| `stop_reason` | string |
| `nodes` | `string[]` |
| `edges` | `TraversalEdge[]` |

### 4.3 `edit`

`action == "markdown_edit"`일 때 `edit`은 기존 Markdown의 편집 대상 범위와 교체하거나 삽입할 조각을 포함한다.

| 필드 | 타입 | nullable | 설명 |
| --- | --- | --- | --- |
| `edit.operation` | enum string | 아니오 | `replace` 또는 `insert_after` |
| `edit.requested_target` | object | 아니오 | 사용자가 요청한 line 범위 |
| `edit.actual_target` | object | 아니오 | 실제 교체 또는 삽입 기준이 되는 line 범위 |
| `edit.requested_target.type`, `edit.actual_target.type` | enum string | 아니오 | `selection`, `current_section`, `whole_document` 중 하나 |
| `edit.requested_target.start_line`, `edit.actual_target.start_line` | integer | 아니오 | 1-base 대상 시작 line |
| `edit.requested_target.end_line`, `edit.actual_target.end_line` | integer | 아니오 | 1-base, inclusive 대상 종료 line |
| `edit.scope_expanded` | boolean | 아니오 | `actual_target`이 `requested_target`을 벗어나면 `true` |
| `edit.changed` | boolean | 아니오 | 편집 결과가 요청 당시 Markdown과 다르면 `true` |
| `edit.summary` | string | 아니오 | 사용자에게 표시할 편집 결과 요약 |
| `edit.replacement_markdown` | string | 아니오 | `actual_target`을 대체하거나 그 뒤에 삽입할 Markdown 조각 |

- `replace`의 `replacement_markdown`은 문서 전체가 아니라 `actual_target` 범위를 대체할 조각이다.
- `insert_after`는 `current_section` target에만 사용하며, `replacement_markdown`은 `actual_target` 뒤에 삽입할 새 Markdown만 포함한다.
- 요청에 target이 없으면 `llmPipeline`은 전체 문서를 `whole_document`의 `requested_target`과 `actual_target`으로 반환한다.
- `actual_target`은 `requested_target`을 포함한 채 Markdown 구조를 보존하기 위해 bounded editable context 안에서만 확장할 수 있다.
- 이 응답만으로 문서를 자동 저장하지 않는다.

### 4.4 `generated_markdown`

`action == "markdown_create"`일 때 `generated_markdown`은 기존 문서와 분리된 새 draft를 포함한다.

```json
{
  "title": "Agent 설계 메모",
  "summary": "대화 내용을 Markdown 문서로 정리했습니다.",
  "markdown": "# Agent 설계 메모\n\n- 편집과 생성을 분리한다."
}
```

| 필드 | 타입 | nullable | 설명 |
| --- | --- | --- | --- |
| `generated_markdown.title` | string | 아니오 | 새 문서 제목 후보 |
| `generated_markdown.summary` | string | 아니오 | 사용자에게 표시할 생성 결과 요약 |
| `generated_markdown.markdown` | string | 아니오 | 새 editor buffer에 넣을 Markdown 본문 |

생성 결과는 기존 문서를 교체하지 않는 새 draft다. 저장과 Wiki ingestion은 별도 backend API로 처리한다.

`llmPipeline`은 `title`, `summary`, `markdown` 필수 필드를 검증한다. 첫 생성 결과가 계약을 충족하지 않으면 실패 이유를 포함해 한 번 재시도하고, 두 번째 결과도 실패하면 `markdown_create_output_contract_failed`를 반환한다.

### 4.5 `message`

`action == "clarify"` 또는 `action == "reject"`일 때 `message`는 사용자에게 표시할 문자열이다. 이 경우 `chat`, `edit`, `generated_markdown`은 `null`이다.

## 5. Spring backend → Frontend

Spring backend는 pipeline 결과에 요청 당시 문서 정보와 correlation ID를 붙여 반환한다.

```json
{
  "documentId": "document-id",
  "baseVersion": 12,
  "requestId": "correlation-id",
  "result": {
    "action": "markdown_edit",
    "route": {
      "action": "markdown_edit",
      "confidence": 0.95,
      "reason": "선택 문장 편집 요청",
      "edit_goal": "cleanup"
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
        "start_line": 2,
        "end_line": 4
      },
      "scope_expanded": true,
      "changed": true,
      "summary": "선택 문장을 자연스럽게 정리했습니다.",
      "replacement_markdown": "문맥을 포함해 다듬어진 문장"
    },
    "generated_markdown": null
  }
}
```

Spring backend 책임:

- 사용자 인증과 workspace·document 접근 권한을 확인한다.
- 편집할 수 없는 문서 유형은 pipeline 호출 전에 차단한다.
- 요청 당시 `documentId`와 `baseVersion`을 응답에 보존한다.
- pipeline의 내부 오류 detail은 관측 정보로만 보존하고 공개 API 오류 코드로 정규화한다.
- pipeline 응답의 requested target, actual target, replacement를 임의로 보정하지 않는다.
- `markdown_edit` 응답만으로 문서를 저장하지 않는다.
- Apply 이후 별도 저장 API에서 optimistic locking으로 버전 충돌을 확인한다.

## 6. Frontend 처리 책임

Frontend는 `result.action`에 따라 처리한다.

| `action` | Frontend 처리 |
| --- | --- |
| `chat_answer` | `chat`을 기존 채팅 UI에 표시 |
| `markdown_edit` | `actual_target` 원문과 replacement의 diff를 보여주고 Apply/Reject 제공 |
| `markdown_create` | `generated_markdown`을 새 editor draft로 열기 |
| `clarify` | `message`를 표시하고 추가 입력 또는 target 선택 유도 |
| `reject` | `message`를 표시하고 원본 유지 |

`markdown_edit` Apply 조건:

1. `edit.operation`이 `replace` 또는 `insert_after`다.
2. `edit.requested_target`이 요청 snapshot의 target과 일치한다.
3. `edit.actual_target`이 요청 snapshot의 문서 범위 안에 있고 분리할 수 없는 Markdown 구조를 깨뜨리지 않는다.
4. 요청 이후 editor revision 또는 buffer checksum이 바뀌지 않았다.
5. 사용자가 preview에서 Apply를 명시적으로 선택했다.

조건을 만족하면 editor의 line-range API로 `actual_target`을 `replace`하거나 `actual_target` 끝 line 뒤에 `insert_after` transaction을 한 번 수행한다. 이후 저장은 별도 backend 문서 API를 호출한다. 요청 이후 editor가 변경됐다면 적용하지 않고 재요청을 유도한다.

## 7. 오류 처리

| HTTP | 공개 오류 코드 | 조건 | Frontend |
| ---: | --- | --- | --- |
| 400 | `INVALID_AI_EDIT_REQUEST` | 빈 message 또는 잘못된 line 범위 | snapshot과 target 재확인 |
| 422 | `AI_EDIT_GENERATION_FAILED` | 편집·생성 계약 보정 실패 또는 Markdown 구조 오류 | 원본 유지 후 재시도 안내 |
| 503 | `AI_SERVICE_UNAVAILABLE` | pipeline 연결 실패 | 원본 유지 후 재시도 안내 |
| 504 | `AI_RESPONSE_TIMEOUT` | pipeline 응답이 60초를 초과 | 원본 유지 후 재시도 안내 |

오류가 발생하면 frontend는 replacement를 preview하거나 적용하지 않는다.
pipeline의 `agent_turn_route_contract_failed`, `markdown_output_contract_failed`, `markdown_create_output_contract_failed`, `markdown_target_crosses_structure`는 Spring 외부 응답에 그대로 노출하지 않는다.

## 8. 구현 상태

| 구성 요소 | 상태 | 범위 |
| --- | --- | --- |
| `llmPipeline` | 구현됨 | routing, Markdown 편집·생성, 검증과 오류 응답 |
| Spring backend | 구현됨 | 인증·권한, Markdown 문서 확인, DTO 변환, 문서 버전 보존과 400/422 오류 전달 |
| frontend | 구현됨 | editor snapshot, public DTO 호출, action별 preview, diff, Apply/취소/재생성, 새 Markdown draft 저장 |

현재 operation은 `replace`와 `insert_after`를 지원한다. `insert_after`는 `current_section` target이 있을 때만 생성하며, target이 없거나 다른 유형이면 현재 섹션 선택을 요청하는 `clarify`를 반환한다.
