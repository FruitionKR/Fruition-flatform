# Wiki Graph Query Engine Spec

## 1. 목적

이 문서는 Fruition MVP에서 Wiki 기반 자연어 질의를 구현하기 위한 Python AI service spec이다.

목표는 일반 raw chunk RAG가 아니라, 이미 생성된 `source page`, `concept page`, `wiki_page_links`를 이용해 질문과 관련된 Wiki graph subgraph를 찾고, 그 경로를 근거로 답변을 생성하는 것이다.

참고 문서:

- `docs/python_convention.md`
- `docs/Fruition_MVP_API_Contract.md`

`Fruition_MVP_API_Contract.md`의 `/api/query`는 기존 계약 참고용이다. 현재 `llmPipeline` FastAPI endpoint는 `POST /query`이며, Spring backend가 proxy endpoint를 만들면 외부 경로는 달라질 수 있다.

## 2. 핵심 방향

Query Engine은 아래 세 단계를 담당한다.

```text
질문
  -> source/concept hybrid retrieval
  -> Wiki graph traversal
  -> context build + LLM answer generation
```

Fruition은 이미 `llmPipeline`을 통해 지식 구조화를 수행한다.

```text
raw document
  -> source page
  -> concept page
  -> source_mentions_concept
  -> concept_related_to
```

따라서 Query Engine은 GraphRAG 전체를 새로 만드는 것이 아니라, 이미 만들어진 Wiki graph 위에서 검색, 탐색, 맥락 구성, 답변 생성을 수행한다.

## 3. 아키텍처 규칙

Python service는 `docs/python_convention.md`를 따른다.

필수 규칙:

- `app/modules/query/`를 bounded context로 사용한다.
- FastAPI route는 얇게 유지한다.
- LLM, embedding model, DB, Object Storage 접근은 `infrastructure/`에 둔다.
- `application/`은 포트와 use case orchestration만 가진다.
- `domain/`은 순수 값 객체, 엔티티, 점수 계산 규칙, 예외만 가진다.
- heavy model은 app startup에서 한 번만 로드한다.
- route에서 embedding model이나 LLM을 직접 호출하지 않는다.

## 4. 추천 폴더 구조

```text
app/
└─ modules/
   └─ query/
      ├─ __init__.py
      ├─ domain/
      │  ├─ __init__.py
      │  ├─ entities.py
      │  ├─ value_objects.py
      │  ├─ scoring.py
      │  └─ exceptions.py
      ├─ application/
      │  ├─ __init__.py
      │  ├─ ports.py
      │  ├─ answer_query.py
      │  ├─ build_query_context.py
      │  └─ traverse_wiki_graph.py
      ├─ infrastructure/
      │  ├─ __init__.py
      │  ├─ bge_m3_embedding_model.py
      │  ├─ postgres_wiki_repository.py
      │  ├─ minio_wiki_markdown_reader.py
      │  ├─ bm25_searcher.py
      │  └─ llm_answer_generator.py
      └─ interfaces/
         └─ http/
            ├─ __init__.py
            ├─ routes.py
            ├─ schemas.py
            └─ dependencies.py
```

파일명은 `snake_case.py`, 클래스명은 `PascalCase`를 사용한다.

## 5. 데이터 전제

Query Engine은 최소 아래 데이터를 사용한다.

### `wiki_pages`

- `id`
- `page_type`: `source`, `concept`
- `title`
- `slug`
- `summary`
- `markdown_uri`
- `status`

### `wiki_page_links`

지원 edge type:

```text
source_mentions_concept
concept_related_to
```

`concept_contrasts_with`는 계약상 존재할 수 있으나 MVP Query Engine의 기본 traversal 대상에서는 제외한다.

### Object Storage

`markdown_uri`는 `s3://fruition-storage/wiki/...` 형식을 권장한다. 실제 backend는 MinIO 같은 S3-compatible storage를 사용할 수 있다.

## 6. Retrieval 정책

### 6.1 기본 원칙

질의의 기본 seed는 `source page`다.

단, 검색 단계에서는 `concept page`도 함께 본다. concept은 시작점 자체가 아니라 `focus_concept_hint`로 사용한다.

```text
질문
  -> source retrieval top N
  -> concept retrieval top M
  -> 강한 concept match가 있으면 연결 source를 seed에 추가
  -> source-first graph traversal
```

이 정책은 아래 이유 때문에 필요하다.

- source page는 원본 근거와 연결 concept을 함께 갖고 있어 안정적인 시작점이다.
- 사용자가 `qmd`, `Obsidian Web Clipper`, `RAG`처럼 특정 concept 이름을 직접 말하면 concept retrieval이 더 정확할 수 있다.
- concept direct match를 무시하면 특정 개념 질의에서 source seed가 흔들릴 수 있다.

### 6.2 Source representation text

source embedding은 원문 전체나 제목만 사용하지 않는다. 아래 필드를 합친 검색용 projection text를 사용한다.

```text
Title: {source title}
Summary: {source summary}
Key Points:
{source page key points}
Extracted Concepts:
{connected concept titles}
```

### 6.3 Concept representation text

concept embedding은 제목만 사용하지 않는다.

```text
Title: {concept title}
Aliases: {aliases if available}
Definition: {definition}
Key Points:
{key points}
Related Concepts:
{related concept titles}
Sources:
{connected source titles}
```

### 6.4 Hybrid score

embedding 유사도와 keyword 일치도를 함께 사용한다. 정확한 문서명·Concept명·
고유명사 검색이 semantic 유사도에 묻히지 않도록 keyword 비중을 40%로 둔다.

권장 source score:

```text
source_retrieval_score =
  0.60 * embedding_similarity
+ 0.40 * bm25_score
```

정확한 title·slug·Concept명 일치는 hybrid 계산 뒤 별도 name match 보정도
적용한다. 한국어 우회 표현의 semantic 검색과 정확한 keyword 검색을 함께
회귀 테스트하고, 운영 평가 없이 한쪽 비중을 추가로 높이지 않는다.

Concept hint score:

```text
concept_hint_score =
  0.60 * concept_embedding_similarity
+ 0.40 * concept_bm25_score
```

`concept_hint_score >= 0.45`이면 해당 concept과 연결된 source를 seed 후보에
추가한다. 이는 keyword가 없는 semantic-only Concept도 embedding similarity
0.75부터 기존과 동일하게 통과시키기 위한 60:40 가중치 기준값이다. threshold는
평가 결과에 따라 조정한다.

후보 생성은 Workspace 전체 저장 page embedding의 exact cosine Top-K와
keyword Top-K를 독립적으로 구한 뒤 합친다. 반환 후보와 Markdown 로드는
bounded로 유지한다. 전역 비교 비용은 현재 검색 정확성을 위한 의도된
동작이며, 실제 사용자 지연이나 운영 지표로 병목이 확인될 때 별도 성능
이슈에서 index 필요성을 평가한다.

## 7. Graph traversal 정책

### 7.1 Traversal 대상 edge

기본 traversal edge:

```text
source -> concept: source_mentions_concept
concept -> concept: concept_related_to
concept -> source: source_mentions_concept 역방향
```

프론트에 보여줄 때는 방향을 원본 edge 방향으로 보존한다. 내부 traversal은 역방향 탐색을 허용한다.

### 7.2 Source-source edge

`source_related_to`는 Wiki 원본 link로 생성하거나 저장하지 않는다. 현재 Query
Engine에도 관련 Source 전용 소비 계약이 없으므로 Source-source 파생 관계를
미리 materialize하지 않는다.

관련 Source 기능이 필요해지면 소비 endpoint, 결과 상한, 정렬 기준을 먼저
정의하고 명시적인 Source→Concept link에서 요청 시 계산한다.

### 7.3 Traversal budget

기본값:

```text
relative_score_floor = 0.95
frontier_limit = 8
max_depth = 3
```

`max_depth`는 seed node를 depth 0으로 보고 해당 깊이에 도달한 node의 후속 frontier 확장을 중단한다.

멈춤 조건:

- 다음 후보가 최초 최고 seed score의 `relative_score_floor`를 넘지 못한다.
- 다음 frontier가 없다.
- 설정한 `max_depth`에서 확장 가능한 후속 frontier가 남아 있다.
- 시작 seed의 점수가 0 이하라 관련 seed가 없다고 판단한다.

현재 구현의 대표 `stop_reason`:

```text
no_relevant_seed
no_frontier
relative_score_floor
max_depth
concept_direct_match
query_evaluator_unsupported
query_evaluator_internal_supported
query_evaluator_unresolved
internal_web_augmented
web_fallback
```

## 8. Context Builder 정책

LLM에는 전체 후보를 넣지 않는다.

Context Builder는 selected subgraph만 압축한다.

포함 대상:

- seed source page summary/key points
- focus concept definition/key points
- supporting source page summary/key points
- selected traversal paths
- source references

제외 대상:

- 점수가 낮은 후보
- 중복 source
- hub concept만으로 연결된 약한 경로
- selected path에 포함되지 않은 주변 노드

## 9. LLM 호출 정책

기본 질의는 LLM 1회 호출을 목표로 한다.

```text
retrieval + traversal + context build: deterministic code
answer generation: LLM 1회
```

예외적으로 seed confidence가 낮거나 후보가 과도하게 모호하면 query rewrite를 위해 LLM 1회를 추가할 수 있다.

```text
if seed_confidence < threshold:
    LLM query rewrite
    retrieval 재실행
LLM answer generation
```

LLM은 그래프를 직접 탐색하지 않는다. LLM은 선택된 context를 바탕으로 답변을 생성한다.

## 10. Application ports

`application/ports.py`에는 외부 의존성을 모두 Protocol로 정의한다.

예시:

```python
from typing import Protocol


class WikiRepositoryPort(Protocol):
    def list_active_pages(self) -> list["WikiPageRecord"]:
        ...

    def list_active_links(self) -> list["WikiPageLinkRecord"]:
        ...


class WikiMarkdownReaderPort(Protocol):
    def read_markdown(self, markdown_uri: str) -> str:
        ...


class EmbeddingModelPort(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]:
        ...


class TextSearchPort(Protocol):
    def score(self, query: str, documents: list[str]) -> list[float]:
        ...


class AnswerGeneratorPort(Protocol):
    def generate_answer(self, context: "QueryContext") -> "GeneratedAnswer":
        ...
```

실제 구현은 `infrastructure/`에 둔다.

## 11. Use case 흐름

`AnswerQueryUseCase.execute(question: str)`는 아래 순서를 따른다.

```text
1. Question value object 검증
2. conversation_context가 있으면 검색용 질문 보강
3. query rewrite 실행
4. active wiki page/link 로드
5. 검색용 Markdown 본문 로드
6. source/concept 후보 점수 계산
7. direct concept match와 focus concept 선택
8. concept -> source backtracking으로 seed 보강
9. graph traversal 실행
10. 관련 page Markdown과 embedding unit 로드
11. evidence snippet 선택
12. answer context 구성
13. LLM answer generation
14. evaluator가 있으면 internal/revise/web/unsupported route 판단
15. revise_answer이면 feedback을 반영해 제한 횟수 안에서 답변 재생성·재평가
16. revise_answer가 끝까지 해결되지 않으면 검증되지 않은 답변 대신 unsupported 답변 반환
17. Query response 반환
```

FastAPI route는 이 use case만 호출한다.

## 12. HTTP API

현재 `llmPipeline` FastAPI endpoint는 `POST /query`다. Spring backend가 `/api/query` 같은 public endpoint를 유지해야 한다면 adapter/proxy에서 request/response를 변환한다.

Spring backend 책임:

- 사용자 인증과 workspace/project 접근 권한을 검증한다.
- 사용자가 접근할 수 있는 Wiki page만 query 대상이 되도록 scope를 보장한다.
- 채팅 메시지 저장, conversation id 관리, public API response shape는 backend 정책으로 정한다.
- 진행 로그가 필요하면 `request_id`와 `log_callback_url`을 전달하고 callback endpoint를 제공한다.

`llmPipeline` 책임:

- 전달받은 질문과 context로 Wiki graph 검색, evidence 선택, 답변 생성을 수행한다.
- 진행 로그 callback은 best-effort로 호출한다. callback 실패는 query 실패로 전파하지 않는다.
- query 결과를 저장하지 않는다.

### Request

```json
{
  "question": "LLM Wiki가 일반 RAG와 뭐가 달라?",
  "request_id": "chat-message-123",
  "log_callback_url": "http://spring-backend/internal/query-events"
}
```

멀티턴 질문에서 지시어나 생략된 주제를 해소해야 하면 backend가 선택 context를 함께 전달할 수 있다.

```json
{
  "question": "그거는 일반 RAG랑 뭐가 달라?",
  "recent_conversation_summary": "사용자는 LLM Wiki와 RAG의 차이, 그리고 채팅 원문을 Wiki source/concept 구조로 저장하는 방식을 논의 중이다.",
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

필드 의미:

| 필드 | 필수 여부 | 설명 |
| --- | --- | --- |
| `question` | 필수 | 사용자의 현재 질문 |
| `request_id` | 선택 | callback event와 backend 요청을 연결할 id |
| `log_callback_url` | 선택 | query 진행 이벤트를 받을 backend callback URL |
| `recent_conversation_summary` | 선택 | 최근 대화 흐름 요약. 생략된 주제와 지시어를 해석하는 데 사용 |
| `reference_context` | 선택 | 활성 주제, 최근 concept, 지시어 해소 후보를 담는 구조화 context |

`reference_context`는 고정 DB schema가 아니라 Query Engine 입력 hint다.
backend는 저장된 채팅 이력을 바탕으로 이 값을 만들고, 값이 없으면 기존 single-turn 질의처럼 동작한다.

### Response

```json
{
  "answer": "LLM Wiki는 raw chunk를 매번 다시 검색하는 방식이 아니라, 문서를 source page와 concept page로 미리 구조화해 지속적인 Wiki graph를 질의하는 방식입니다.",
  "related_pages": [
    {
      "id": "source:doc_123",
      "page_type": "source",
      "title": "LLM Wiki와 RAG 비교",
      "slug": "llm-wiki-rag",
      "relevance_score": 0.92,
      "role": "seed_source",
      "depth": 0
    },
    {
      "id": "concept:rag",
      "page_type": "concept",
      "title": "RAG",
      "slug": "rag",
      "relevance_score": 0.88,
      "role": "focus_concept",
      "depth": 1
    }
  ],
  "evidence_snippets": [
    {
      "rank": 1,
      "source_document_id": "doc_123",
      "source_block_ids": ["block_7"],
      "text": "LLM Wiki는 문서를 미리 source page와 concept page로 컴파일한다."
    }
  ],
  "graph_context": {
    "nodes": [
      {
        "id": "source:doc_123",
        "page_type": "source",
        "title": "LLM Wiki와 RAG 비교",
        "slug": "llm-wiki-rag",
        "relevance_score": 0.92,
        "role": "seed_source",
        "depth": 0
      },
      {
        "id": "concept:rag",
        "page_type": "concept",
        "title": "RAG",
        "slug": "rag",
        "relevance_score": 0.88,
        "role": "focus_concept",
        "depth": 1
      },
      {
        "id": "concept:llm-wiki",
        "page_type": "concept",
        "title": "LLM Wiki",
        "slug": "llm-wiki",
        "relevance_score": 0.91,
        "role": "focus_concept",
        "depth": 1
      }
    ],
    "edges": [
      {
        "from_page_id": "source:doc_123",
        "to_page_id": "concept:rag",
        "link_type": "source_mentions_concept",
        "role": "seed_to_focus",
        "score": 0.88
      },
      {
        "from_page_id": "concept:rag",
        "to_page_id": "concept:llm-wiki",
        "link_type": "concept_related_to",
        "role": "context_expansion",
        "score": 0.84
      }
    ]
  },
  "traversal_paths": [
    {
      "path_id": "path_1",
      "role": "primary_answer_path",
      "used_for_answer": true,
      "score": 0.91,
      "stop_reason": "answer_context_selected",
      "nodes": [
        "source:doc_123",
        "concept:llm-wiki",
        "concept:rag"
      ],
      "edges": [
        {
          "from_page_id": "source:doc_123",
          "to_page_id": "concept:llm-wiki",
          "link_type": "source_mentions_concept",
          "role": "seed_to_focus",
          "score": 0.9
        },
        {
          "from_page_id": "concept:llm-wiki",
          "to_page_id": "concept:rag",
          "link_type": "concept_related_to",
          "role": "context_expansion",
          "score": 0.84
        }
      ]
    }
  ]
}
```

현재 HTTP response model에는 `retrieval_summary`가 포함되지 않는다. 내부 domain object에는 존재하지만, frontend/backend 계약으로 사용하려면 별도 schema 확장이 필요하다.

### Query log callback

`log_callback_url`이 있으면 `llmPipeline`은 query 진행 중 callback URL로 이벤트를 보낸다.

```json
{
  "request_id": "chat-message-123",
  "event_type": "query.log",
  "stage": "retrieval_scored",
  "message": "source/concept 후보 점수를 계산했습니다.",
  "sequence": 4,
  "timestamp": "2026-07-01T00:00:00Z",
  "data": {
    "source_count": 15,
    "concept_count": 10
  }
}
```

callback 실패, timeout, 네트워크 오류는 query 실패로 처리하지 않는다.

### 기존 `highlighted_paths` 처리

`highlighted_paths`는 edge 단일 목록처럼 동작하므로 더 이상 핵심 응답 필드로 사용하지 않는다.

프론트는 다음 필드를 사용한다.

- `graph_context.nodes`
- `graph_context.edges`
- `traversal_paths`

`highlighted_paths`가 필요하면 backend adapter에서 `traversal_paths.edges`를 flatten해 backward-compatible field로 생성할 수 있다.

## 13. Scoring role

Graph node role:

```text
seed_source
supporting_source
focus_concept
related_context
```

Graph edge role:

```text
seed_to_focus
source_to_source
context_expansion
```

Path role:

```text
primary_answer_path
candidate_path
```

역할 값은 UI label보다 디버깅과 graph 해석용 metadata에 가깝다. 제품 UI 문구는 backend/frontend에서 별도 매핑한다.

## 14. 테스트 기준

Unit test는 real BGE-M3나 real LLM을 로드하지 않는다.

테스트 전략:

- application use case는 fake ports로 테스트한다.
- graph traversal은 deterministic test data로 테스트한다.
- HTTP route는 FastAPI `TestClient`와 fake dependency로 테스트한다.
- real embedding 성능 평가는 `experiments/`나 별도 evaluation script로 분리한다.

권장 평가 지표:

```text
source Recall@3
source MRR
concept Recall@5
selected path sanity check
```

초기 실험 기준:

```text
source vector retrieval은 BGE-M3에서 강하게 동작했다.
hybrid는 BM25 weight가 과하면 vector 정답을 흐릴 수 있다.
graph traversal은 source retrieval을 대체하기보다 concept/path context 보강에 사용한다.
```

## 15. 구현 시 주의사항

- Query Engine MVP에서 vector DB는 필수로 두지 않는다. 작은 데이터셋에서는 PostgreSQL row + in-memory embedding cache로 시작할 수 있다.
- embedding cache는 page `updated_at` 또는 representation hash로 invalidation한다.
- BGE-M3 같은 heavy embedding model은 startup에서 한 번 로드한다.
- LLM answer generator는 selected context 밖의 내용을 단정하지 않는다.
- graph traversal 결과와 answer context는 분리한다. 탐색 후보 전체를 LLM에 넣지 않는다.
- source-source edge는 저장 단계에서 threshold로 정제하고, query 단계에서는 relevance decay로 확장을 제한한다.

## 16. 구현 우선순위

1. `app/modules/query/` skeleton 생성
2. fake repository 기반 graph traversal unit test
3. source/concept representation builder
4. in-memory BGE-M3 embedding adapter
5. BM25 searcher
6. source retrieval + concept hint + backtracking
7. graph traversal + path selection
8. LLM answer generator port와 fake 구현
9. HTTP `POST /query`
10. real LLM adapter 연결

MVP에서 가장 먼저 검증할 것은 답변 문장 품질보다 아래 흐름이다.

```text
question
  -> seed sources
  -> focus concepts
  -> traversal_paths
  -> graph_context
```

## 17. 구현 계획 체크리스트

AI agent나 backend/frontend 작업자가 계획을 세울 때는 아래 순서로 나누는 것이 안전하다.

1. public API 결정: frontend가 Spring backend를 호출할지, 내부 도구가 `llmPipeline`을 직접 호출할지 정한다.
2. scope 보장: query 대상 Wiki page가 사용자 workspace/project 범위로 제한되는지 확인한다.
3. request adapter: `question`, `request_id`, `log_callback_url`, `recent_conversation_summary`, `reference_context` 매핑을 구현한다.
4. response adapter: `answer`, `related_pages`, `evidence_snippets`, `graph_context`, `traversal_paths`를 제품 채팅 응답 구조로 감싼다.
5. callback endpoint: 진행 로그가 필요할 때만 backend internal callback을 만들고, 순서 보장은 `sequence`로 처리한다.
6. 저장 정책: query 응답 저장은 backend가 처리한다. `llmPipeline` 응답은 저장 결과가 아니다.
7. UI 표시: 답변 본문, 근거 snippet, 관련 page, graph/path 표시를 분리해 단계적으로 붙인다.
