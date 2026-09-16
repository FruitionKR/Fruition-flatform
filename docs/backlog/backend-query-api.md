# 이전 자료

이 문서는 Spring Query API 구현 전 단계의 백로그 스펙입니다.
현재 구현과 최신 API 계약은 `docs/backend-llmpipeline-integration.md`와
`docs/Fruition_MVP_API_Contract.md`를 기준으로 확인합니다.

---

# Spring Boot 백엔드 Query API 구현 Spec

## 공통

- Base path: `/api/query`
- Controller: `fruition.query.controller.QueryController`
- Service: `fruition.query.service.QueryService`

---

## POST /api/query — 자연어 질의응답

### Request

```json
{
  "question": "Self-Attention이 뭐야?"
}
```

### 처리 흐름

1. `PipelineQueryRequester`로 FastAPI `POST {QUERY_ENDPOINT}` 호출 (타임아웃: `QUERY_TIMEOUT_SECONDS`, 기본 30초)
2. pipeline 응답 수신
3. `QueryService.query()` 내에서 user/assistant `ChatMessage` 두 건을 `saveAll`로 한 트랜잭션에 저장
4. `evidence_snippets`에서 `page_id`가 있는 항목만 `ChatMessageReference`로 변환하여 저장
5. `QueryResponse`로 변환 후 반환

### Pipeline → QueryResponse 필드 매핑

| pipeline 필드 | QueryResponse 필드 | 비고 |
| --- | --- | --- |
| `answer` | `assistant_message.content` | 그대로 |
| `related_pages[]` | `related_pages[]` | `role`, `depth` 포함하여 그대로 전달 |
| `evidence_snippets[]` | `evidence_snippets[]` | 그대로 전달 |
| `graph_context` | `graph_context` | 그대로 전달 |
| `traversal_paths[]` | `traversal_paths[]` | 그대로 전달 |

### Response 200

```json
{
  "user_message": {
    "id": "chat_user_<uuid>",
    "role": "user",
    "content": "Self-Attention이 뭐야?",
    "status": "completed",
    "created_at": "2026-06-04T10:05:00Z"
  },
  "assistant_message": {
    "id": "chat_assistant_<uuid>",
    "role": "assistant",
    "content": "Self-Attention은 입력 토큰들이 서로 어떤 관계를 갖는지 계산하는 메커니즘이에요. [1]",
    "status": "completed",
    "created_at": "2026-06-04T10:05:03Z"
  },
  "related_pages": [
    {
      "id": "wp_concept_456",
      "page_type": "concept",
      "title": "Self-Attention",
      "slug": "self-attention",
      "relevance_score": 0.95,
      "role": "concept",
      "depth": 1
    }
  ],
  "evidence_snippets": [
    {
      "page_id": "wp_source_123",
      "page_type": "source",
      "page_title": "lecture_01",
      "page_slug": "lecture-01",
      "page_url": "wiki/sources/lecture-01.md",
      "page_role": "source",
      "text": "Self-attention computes relationships between tokens.",
      "score": 0.91,
      "rank": 1,
      "paragraph_index": 2,
      "sentence_index": 0
    }
  ],
  "graph_context": {
    "nodes": [...],
    "edges": [...]
  },
  "traversal_paths": [
    {
      "path_id": "path_01",
      "role": "primary",
      "used_for_answer": true,
      "score": 0.91,
      "stop_reason": "relative_score_cutoff",
      "nodes": ["wp_source_123", "wp_concept_456"],
      "edges": [...]
    }
  ]
}
```

- 답변 본문의 `[N]` 표식은 `evidence_snippets[].rank`와 대응
- pipeline이 `no_relevant_seed` 상태면 고정 unsupported 답변 반환 (graph 탐색 없음)

### 실패

| 조건 | HTTP | error code |
| --- | --- | --- |
| `question` 비어 있거나 null | 400 | `INVALID_REQUEST` |
| pipeline 타임아웃 (30초 초과) | 503 | `PIPELINE_TIMEOUT` |
| pipeline 4xx 응답 | 502 | `PIPELINE_ERROR` |
| pipeline 5xx 응답 | 503 | `PIPELINE_UNAVAILABLE` |

### 환경변수

| 키 | 기본값 | 설명 |
| --- | --- | --- |
| `QUERY_ENDPOINT` | `http://localhost:8000/query` | FastAPI pipeline 주소 |
| `QUERY_TIMEOUT_SECONDS` | `30` | HTTP 읽기 타임아웃 |

### 관련 클래스

- `QueryController.query()`
- `QueryService.query()`
- `PipelineQueryRequester` — `RestClient` 기반 HTTP 클라이언트
- `PipelineQueryResponse` — pipeline 응답 역직렬화 DTO
- `QueryResponse`, `QueryResponse.MessageSummary`
- `PipelineQueryException` — pipeline 오류 전파 예외
- `ChatMessageRepository.saveAll()`
- `ChatMessageReferenceRepository.saveAll()`

### ChatMessageReference 저장 매핑

`evidence_snippets` 중 `page_id != null`인 항목만 저장.

| ChatMessageReference 필드 | pipeline evidence_snippet 필드 |
| --- | --- |
| `messageId` | assistantMessageId |
| `referenceType` | `page_type` |
| `wikiPageId` | `page_id` |
| `pageRole` | `page_role` |
| `relevanceScore` | `score` |
| `rank` | `rank` |
| `paragraphIndex` | `paragraph_index` |
| `sentenceIndex` | `sentence_index` |
| `quote` | `text` |
