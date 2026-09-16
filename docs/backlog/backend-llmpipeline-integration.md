# Backend와 llmPipeline Query 연결

이 문서는 현재 구현 기준으로 Spring Boot backend와 Python `llmPipeline`의 Query API 연결 방식을 정리한다.
이전 구현 과정 기록은 `docs/backlog/backend-llmpipeline-integration.md`에 보관한다.

## 연결 원칙

프론트엔드는 `llmPipeline`을 직접 호출하지 않는다.
오른쪽 채팅 영역은 Spring backend의 `POST /api/query`만 호출하고, Spring이 FastAPI `POST /query`를 중계한다.

```text
Frontend
  -> POST /api/query
  -> Spring QueryService
  -> POST {QUERY_ENDPOINT}
  -> llmPipeline FastAPI /query
  -> Spring 응답 반환 + chat_messages 저장
```

이 구조를 유지해야 하는 이유는 다음과 같다.

- Spring이 `chat_messages`에 user/assistant 메시지를 저장한다.
- Spring이 `chat_message_references`에 답변 근거 `evidence_snippets`를 저장한다.
- 프론트엔드는 Spring API 계약만 바라보면 된다.
- FastAPI 내부 주소와 실행 방식이 바뀌어도 프론트 계약은 유지된다.

## 엔드포인트 분리

문서 처리와 자연어 질의는 서로 다른 FastAPI endpoint를 사용한다.

| 목적 | Spring 설정 | 기본값 | FastAPI endpoint |
| --- | --- | --- | --- |
| 문서 업로드 후 Wiki 생성 | `PROCESSING_ENDPOINT` | `http://localhost:8000/pipeline/runs` | `POST /pipeline/runs` |
| Wiki 기반 자연어 질의 | `QUERY_ENDPOINT` | `http://localhost:8000/query` | `POST /query` |

문서 처리 요청은 `document_id`만 전달한다.

```json
{
  "document_id": "doc_123"
}
```

질의 요청은 기본적으로 사용자 질문을 전달한다.
멀티턴 질의 정확도를 높이려면 backend가 최근 대화 요약과 참조 맥락을 함께 전달한다.

```json
{
  "question": "LLM Wiki가 뭐야?"
}
```

멀티턴 context를 포함하는 요청 예:

```json
{
  "question": "그거는 일반 RAG랑 뭐가 달라?",
  "recent_conversation_summary": "사용자는 LLM Wiki가 RAG와 어떻게 다른지, 채팅 원문을 Wiki source/concept 구조로 저장하는 방식과 함께 논의 중이다.",
  "reference_context": {
    "active_topic": {
      "canonical": "LLM Wiki",
      "aliases": ["Persistent Wiki", "지속적 Wiki"]
    },
    "recent_concepts": ["LLM Wiki", "RAG", "source page", "concept page"],
    "referents": {
      "그거": {
        "canonical": "LLM Wiki",
        "aliases": ["Persistent Wiki", "지속적 Wiki"]
      }
    }
  }
}
```

1차 연동에서는 프론트엔드가 이 구조를 직접 만들지 않는다.
Spring backend가 저장된 `chat_messages`와 최근 질의 응답을 바탕으로 `recent_conversation_summary`, `reference_context`를 구성해 `llmPipeline`에 전달한다.
프론트엔드는 기존처럼 `POST /api/query`를 호출하고, context 생성 책임은 backend에 둔다.

## 현재 응답 계약

Spring `POST /api/query`는 FastAPI `/query` 응답을 현재 API 계약에 맞춰 반환한다.

주요 응답 필드는 다음과 같다.

| 필드 | 용도 |
| --- | --- |
| `user_message` | 저장된 사용자 질문 메시지 |
| `assistant_message` | 저장된 답변 메시지 |
| `related_pages` | 탐색에 사용된 Wiki page 목록 |
| `evidence_snippets` | 답변 문장 근거. `rank`는 답변의 `[N]` 표식과 대응 |
| `graph_context` | 그래프 하이라이트용 node/edge |
| `traversal_paths` | 답변 생성에 사용한 탐색 경로 |

이전 `source_references`, `highlighted_paths` 중심 응답은 사용하지 않는다.

## 영속화 정책

현재 단계에서는 `related_pages` 영속화를 보류한다.

- `POST /api/query` 응답에는 `related_pages`를 그대로 포함한다.
- `chat_message_references`에는 `evidence_snippets` 기반 근거만 저장한다.
- `GET /api/chat/messages`는 저장된 evidence reference만 복원한다.
- 이전 채팅에서 `related_pages`까지 복원해야 하는 요구가 확정되면 별도 설계를 진행한다.

보류 이유는 `related_pages`가 탐색 결과 목록이고, `evidence_snippets`는 답변 근거 문장이라 데이터 성격이 다르기 때문이다.
같은 테이블에 섞으면 nullable 컬럼이 늘고, 별도 테이블을 만들면 조회 구조가 바뀐다.
현재 목표는 백엔드와 `llmPipeline` Query 연결 검증이므로 영속화 범위를 넓히지 않는다.

## 멀티턴 Query 연동 검토 항목

현재 `llmPipeline`의 `POST /query`는 아래 선택 필드를 받을 수 있다.

| 필드 | 용도 | 생성 주체 |
| --- | --- | --- |
| `recent_conversation_summary` | 직전 대화 흐름 요약. 지시어와 생략된 주제를 해석할 때 사용 | Spring backend |
| `reference_context` | 활성 주제, 최근 concept, 지시어 해소 후보를 담는 구조화 context | Spring backend |

backend에서 추가로 검토할 부분:

- `PipelineQueryRequester` 요청 DTO에 두 필드를 추가한다.
- `QueryService`가 최근 `chat_messages`를 조회해 context를 만들지, 별도 memory/compiler 서비스를 둘지 결정한다.
- context 생성 실패 시에는 기존처럼 `question`만 전달해도 동작해야 한다.
- assistant 응답 저장 시 사용된 context를 별도 저장할지 결정한다. 디버깅과 재현성이 필요하면 최소 요약 문자열은 저장 대상 후보가 된다.
- `reference_context`는 LLM 내부 판단을 돕는 입력이지, 프론트 표시용 계약으로 노출하지 않는다.

frontend에서 추가로 검토할 부분:

- 1차 구현에서는 변경이 없어도 된다.
- UI가 명시적으로 선택한 page/concept를 질문 context로 넘겨야 하는 기능이 생기면, 그때 Spring `POST /api/query` 계약에 별도 필드를 추가한다.
- 프론트가 `reference_context`를 직접 만들게 하면 UI가 LLM memory 구조를 알아야 하므로 1차 범위에서는 피한다.

## Pipeline Run 평가 루프 검토 항목

채팅 원문을 Wiki page로 만들 때는 `run_lab.py`의 LangGraph evaluator/repair loop를 사용한다.
FastAPI `POST /pipeline/runs`, `POST /chat-wiki/runs` 모두 evaluator loop를 기본 활성화하며 필요하면 요청의 `wiki_evaluation_loop=false`로 끌 수 있다.

현재 계약:

- `wiki_evaluation_loop` 기본값은 `true`다.
- `max_eval_attempts` 기본값은 `2`다. evaluator 결과에 따라 LLM 호출 비용과 실행시간이 늘어날 수 있다.
- evaluator `issues`는 반드시 재생성·재평가하고, 통과 가능한 선택 제안은 `warnings`로 분리한다.
- concept/evidence/source block target을 source block으로 해석할 수 있으면 target block과 앞뒤 block, 기존 target 항목, evaluator feedback만 LLM에 전달해 `replace/remove/add` patch를 생성한다.
- patch는 evaluator가 지정한 기존 항목과 함께 전달된 source anchor만 수정할 수 있다. 적용 후 전체 semantic note를 다시 정규화하고 평가한다.
- patch 호출·계약 검증에 실패하면 해당 block을 포함한 packet 재생성으로 fallback하고, 모든 target을 해석할 수 없으면 전체 packet을 재생성한다.
- target과 무관한 semantic note와 의미 항목은 이전 결과를 그대로 유지한다.
- 시도별 `generation_evaluations`는 pipeline manifest와 DB run manifest에 저장한다.
- 재시도 평가에는 `retry_mode`를 기록하고 targeted patch 성공 시 `applied_patch_operations`도 함께 저장해 평가 반영 방식을 추적할 수 있게 한다.
- 최종 actionable issue가 남으면 page 생성·저장 계약은 유지하되 manifest의 `generation_evaluation_status`를 `unresolved`로 저장한다. 평가 비활성화는 `disabled`, 통과는 `passed`다.
- `json_mode=true`가 채팅 source/concept 생성 품질에 필요한지 확인한다.
- evaluator prompt 경로를 외부 설정으로 열지, 고정 prompt를 사용할지 결정한다.
- `save_debug_json=true`이면 evaluation/repair 결과를 별도 debug artifact로도 저장한다.

## 로컬 실행

`infra/.env`를 준비한다.

```sh
cp infra/.env.example infra/.env
```

Query 연결에 필요한 주요 값은 다음과 같다.

```env
PROCESSING_ENDPOINT=http://localhost:8000/pipeline/runs
QUERY_ENDPOINT=http://localhost:8000/query
QUERY_TIMEOUT_SECONDS=30
QUERY_EMBEDDING_MODE=text-only
LLM_PROVIDER=openai
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=gpt-4.1-mini
```

로컬에서 pipeline까지 함께 실행한다.

```sh
docker compose --env-file infra/.env -f infra/compose.infra.yml -f infra/compose.ai.yml up -d --build
```

Spring backend는 호스트 기준 `localhost:8000`으로 pipeline을 호출한다.
`pipeline-api` 컨테이너 내부에서는 PostgreSQL과 MinIO를 각각 `postgresql`, `minio` 서비스명으로 호출한다.

## 검증 순서

1. FastAPI 상태 확인

```sh
curl http://localhost:8000/health
```

2. FastAPI Query 직접 확인

```sh
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"LLM Wiki가 뭐야?"}'
```

3. Spring Query 중계 확인

```sh
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"LLM Wiki가 뭐야?"}'
```

4. 채팅 저장 확인

```sh
curl http://localhost:8080/api/chat/messages
```

성공 기준:

- Spring `POST /api/query`가 200을 반환한다.
- 응답에 `assistant_message`, `related_pages`, `evidence_snippets`, `graph_context`, `traversal_paths`가 포함된다.
- `GET /api/chat/messages`에 user/assistant 메시지가 저장된다.
- assistant 메시지의 `references`에는 `evidence_snippets` 기반 reference가 포함된다.

## 남은 결정

- 이전 채팅 기록에서 `related_pages`까지 복원할지 결정해야 한다.
- 복원이 필요하면 `chat_message_references`에 섞을지, `chat_message_related_pages` 같은 별도 테이블로 분리할지 정한다.
- `markdown_uri`는 아직 pipeline 컨테이너 내부 경로 의존 이슈가 남아 있어, 이후 MinIO `wiki/` prefix 저장으로 정리한다.
