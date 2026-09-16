# llmPipeline Query 흐름

## 1. 문서 목적

이 문서는 현재 `llmPipeline` Query Engine이 사용자 질문을 받을 때 다음 과정을 어떻게 수행하는지 설명한다.

- 질문과 대화 context를 어떻게 검색 질의로 바꾸는가?
- source/concept page 후보를 어떻게 찾고 점수화하는가?
- Wiki graph를 어떤 규칙으로 탐색하는가?
- 어떤 근거를 LLM 답변 context로 선택하는가?
- 답변 prompt와 evaluator prompt는 어떻게 구성되는가?
- evaluator 결과에 따라 retry, web fallback, unsupported를 어떻게 결정하는가?
- 최종 응답에는 어떤 결과가 포함되는가?

현재 코드 구현을 기준으로 하며, 주요 기준 코드는 다음과 같다.

- HTTP 진입점: `services/ai/pipeline/app/modules/query/interfaces/http/routes.py`
- 전체 orchestration: `services/ai/pipeline/app/modules/query/application/answer_query.py`
- page scoring: `services/ai/pipeline/app/modules/query/application/query_page_scorer.py`
- graph traversal: `services/ai/pipeline/app/modules/query/application/traverse_wiki_graph.py`
- evidence 선택: `services/ai/pipeline/app/modules/query/application/evidence_selector.py`
- 답변 조립: `services/ai/pipeline/app/modules/query/application/query_answer_assembler.py`
- evaluator graph: `services/ai/pipeline/app/modules/query/infrastructure/query_evaluator_graph.py`

## 2. 한눈에 보는 전체 흐름

```text
POST /query
  │
  ▼
요청 모델·내부 인증 검증
  │
  ▼
대화 context로 질문 보강
  │
  ▼
Rule-based query rewrite
  │
  ▼
PostgreSQL candidate page 조회
  ├─ metadata / full-text 후보
  ├─ embedding unit full-text 후보
  └─ 선택적으로 semantic page embedding 후보
  │
  ▼
graph link 확장 및 Wiki Markdown 로드
  │
  ▼
source / concept page 점수화
  ├─ configured embedding/text search
  ├─ title/slug/alias 직접 일치
  └─ source 구조 section 가중치
  │
  ▼
seed source / focus concept 선택
  │
  ▼
Wiki graph traversal
  │
  ▼
관련 page Markdown + embedding unit 로드
  │
  ▼
evidence snippet 선택
  │
  ▼
LLM answer context 조립
  │
  ▼
LLM 답변 생성
  │
  ▼
citation marker 사용 evidence 추출·번호 정리
  │
  ▼
선택적 LLM evaluator
  ├─ internal_supported ───────────────┐
  ├─ revise_answer -> retry            │
  ├─ web_fallback -> web 검색          │
  ├─ internal_web_augmented -> 병합    │
  └─ unsupported -> 근거 부족 응답     │
  │                                   │
  └───────────────────────────────────┘
  │
  ▼
answer + related_pages + evidence_snippets
       + graph_context + traversal_paths
```

Query는 ingest 결과인 `wiki_pages`, `wiki_page_links`, `wiki_embedding_units`와 MinIO Markdown을 함께 사용한다.

## 3. HTTP 요청과 질문 Context 보강

**역할과 입력**

`question`, `recent_conversation_summary`, `recent_messages`에서 생략된 대상을 보강하고 검색 표현을 만든다.

HTTP 진입점은 `POST /query`이며 요청 계약은 다음과 같다.

```json
{
  "workspace_id": "workspace-id",
  "user_id": "user-id",
  "question": "그 방식은 일반 RAG와 무엇이 달라?",
  "provider": "openai",
  "model": "gpt-5-nano",
  "allow_web_search": false,
  "recent_conversation_summary": "직전에는 Persistent Wiki를 설명했다.",
  "recent_messages": [],
  "reference_context": {"active_topic": "Persistent Wiki"},
  "output_language": "ko",
  "response_length": "balanced"
}
```

`workspace_id`, `question`, `provider`, `model`, `allow_web_search`는 필수다. `user_id`는 HTTP에서는 선택이고, `recent_messages`는 최대 6개이며 각 메시지는 `user`/`assistant` 역할과 1~4,000자 content를 가진다. `output_language`는 `ko`·`en`·`document`, `response_length`는 `concise`·`balanced`·`detailed`만 허용된다.

Pipeline API는 내부 `X-Internal-Token` 인증을 거치며, 요청 검증 실패는 `422`, `QueryError`는 `400`, 그 밖의 처리 예외는 `500`으로 반환한다. 인증 누락·불일치는 `401`, 내부 인증 미설정은 `503`이다.

구현은 `services/ai/pipeline/app/modules/query/interfaces/http/{routes,schemas}.py`, `conversation_context_resolver.py`, `rule_based_query_rewriter.py`, `answer_query.py`에 있다.

**Context 보강 규칙**

대화 context가 없으면 원 질문을 유지한다. `reference_context.referents`에서 질문에 포함된 marker의 값을 먼저 붙이고, 나머지 reference 값, 누적 summary, 최근 메시지(`사용자:`·`어시스턴트:` 라벨)를 붙인 뒤 원 질문을 마지막에 둔다. referent가 매칭되지 않으면 evidence 선택용 질문은 원 질문을 사용한다.

**출력과 다음 단계**

contextualized question은 검색 및 page scoring에 사용하고, evidence 선택에는 referent가 매칭된 경우에만 `매칭된 대상 + 원 질문`을 사용한다. 최근 메시지가 6개이면 설정된 conversation summarizer가 누적 summary를 갱신해 `updated_conversation_summary`로 반환할 수 있으며, summarizer 실패나 빈 결과는 응답을 중단하지 않는다.

rule-based rewrite는 영문·숫자·한글·`_.-` 토큰을 소문자화하고 조사와 stopword를 제거해 최대 8개 keyword를 만든다. keyword가 있으면 공백으로 합친 retrieval query를, 없으면 원 질문을 사용한다. rewrite 결과는 `original_question`, `retrieval_query`, `keywords`뿐이며 별도 web query 필드는 없다.

## 4. Candidate Page 조회와 본문 로드

**역할과 입력**

`workspace_id`, rewrite의 `retrieval_query`로 active `source`·`concept` page를 PostgreSQL에서 조회하고, page의 `markdown_uri`를 통해 MinIO Markdown을 읽는다.

**조회·점수화 규칙**

`workspace_id`가 검색 범위를 결정한다. 기본 후보 상한은 source 15개, concept 10개이며 candidate pool multiplier 4가 적용되어 초기 DB 조회는 각각 최대 60개·40개까지 넓힌다. DB lexical 후보는 title/slug/summary metadata와 embedding unit text의 full-text 검색을 합치고, embedding mode가 `text-only`·`bm25`·`lexical`이 아니면 원 질문을 page embedding 검색에도 사용한다. active 상태·workspace·page type·embedding model/dimension/status 조건을 모두 적용한다.

초기 후보에서 시작해 기본 최대 depth 3, link 200개까지 workspace 범위의 연결 page를 추가로 읽는다. scoring은 configured embedding/text search를 사용하며 현재 `AnswerQueryUseCase` 기본 호출은 embedding weight 0.8이라 embedding과 BM25 결과를 함께 반영한다. embedding이 text search와 같은 경우에는 BM25 결과가 된다. source page는 `Categories`·`Core Concepts`·`Section Candidates`·`Mentions` section을 각각 0.10·0.20·0.25·0.15 가중치로 추가 반영한다. concept title·slug·Markdown aliases가 질문과 직접 일치하면 직접 일치 후보로 보강한다.

구현은 `postgres_wiki_repository.py`, `stored_wiki_page_embedding_search.py`, `query_page_scorer.py`, `minio_wiki_markdown_reader.py`에 있다.

**출력과 다음 단계**

ranked source/concept pages와 본문을 만든다. source seed는 최고 점수에서 0.02 이내인 page를, focus concept은 최고 점수가 기본 threshold 0.45 이상일 때 최고 점수에서 0.001 이내인 page를 선택한다. 본문을 읽지 못한 page는 metadata 후보로 남지만 해당 page의 본문 기반 evidence는 만들 수 없다.

page별 결과에는 id, `page_type`, title, slug, relevance score와 역할이 붙는다. MinIO 본문을 읽지 못한 후보는 근거 생성에 그대로 사용할 수 없으며 검색 metadata와 답변 evidence를 구분한다.

## 5. Graph Traversal과 Evidence 선택

**역할과 입력**

seed page, `wiki_page_links`, page Markdown, `wiki_embedding_units`에서 답변 근거를 고른다.

**Traversal·Evidence 규칙**

graph adjacency는 `source_mentions_concept`, `concept_related_to`만 따라간다. DB link 확장 단계에서는 `source_related_to`도 제외한다. traversal은 최고 seed score의 0.95 이상인 다음 후보만 최대 depth 3, frontier 8까지 확장하고, node score·link confidence·depth penalty로 path score를 계산한다. `no_relevant_seed`, `no_frontier`, `relative_score_floor`, `max_depth`가 traversal stop reason이 될 수 있다.

seed는 score가 높은 source이고 focus concept은 score threshold를 넘은 concept이다. 직접 concept match가 있고 source score가 낮으면 해당 concept에 연결된 source를 seed에 추가하며, 직접 concept page는 graph path가 없어도 related page/path에 보강할 수 있다. 반환 path는 기본 최대 5개로 줄인다.

evidence는 반환 related page 앞 8개를 대상으로 한다. 내부 page에 저장된 `wiki_embedding_units`가 있으면 unit의 `source_document_id`·`source_block_ids`·text를 사용하고, 없으면 Markdown의 source reference를 파싱한다. 각 page의 상위 점수에서 0.85 이상인 후보와 page coverage를 조합하며, source reference가 없는 text는 evidence가 되지 않는다. web page는 검색 결과의 snippet을 `source_block_id=web`인 evidence로 사용한다.

**출력 예시**

```json
{
  "evidence": [
    {
      "rank": 1,
      "page_slug": "persistent-wiki",
      "source_document_id": "doc-1",
      "source_block_ids": ["B0012"],
      "source_refs": [
        {"source_document_id": "doc-1", "source_block_id": "B0012"}
      ],
      "text": "새 문서의 개념을 기존 페이지와 병합한다."
    }
  ],
  "traversal_paths": [
    ["source-doc-1", "persistent-wiki"]
  ]
}
```

선택된 evidence, related page와 path를 answer context 조립으로 넘긴다. citation marker의 rank는 이 단계에서 생성된 evidence 목록의 순번이며, 영속 source block id가 아니다.

evidence selector는 embedding/text search와 page score·unit weight·구조화된 source reference를 함께 사용한다. citation marker `[1]`은 prompt에 전달되는 rank이며 source block id와 구분된다.

## 6. Answer Context와 Prompt 조립

**역할과 입력**

질문, page context와 evidence rank label을 포함한 answer context를 모델 prompt로 만든다. citation marker `[1]`, `[2]`는 모델 출력 규칙이지 evidence text에 미리 삽입되는 값은 아니다.

**system prompt의 핵심 내용**

- 제공된 Wiki context만 사용한다.
- 근거가 있는 문장에 해당 evidence marker를 붙인다.
- context에 없는 사실은 추측하지 않고 근거 부족을 밝힌다.
- marker와 출처를 임의로 만들지 않는다.
- active Wiki schema의 Query fragment를 따른다.

user prompt에는 원 질문/보강 질문, 관련 page 요약과 번호가 붙은 evidence가 들어간다.

구현은 `services/ai/pipeline/app/modules/query/application/answer_context_formatter.py`, `query_chat_answer_generator.py`에 있다. context에는 관련 page 최대 8개와 path 최대 5개가 들어가며, 900자 제한은 page summary가 아니라 각 evidence text excerpt에만 적용된다. LLM wrapper에는 active Wiki schema의 `query` fragment가 실제 주입되며, `output_language`·`response_length`가 있으면 response preference도 추가된다.

실제 system prompt는 코드의 `QUERY_ANSWER_SYSTEM_PROMPT`에 active schema fragment를 덧붙여 만든다. 핵심 계약은 다음과 같다.

- 사용자에게 보여줄 conversational answer body만 반환한다.
- context에 있는 evidence rank 번호만 `[1]`, `[2]` citation으로 사용한다.
- evidence를 사용한 모든 factual sentence 끝에 citation을 붙인다.
- score, path id, page id, URL과 내부 link type을 노출하지 않는다.
- evidence에 직접 정의나 설명이 없으면 정확한 답이 충분히 지원되지 않는다고 말한다.
- evidence에 없는 예시·비유·외부 지식을 만들지 않는다.

대표 messages:

```text
system:
  Wiki context에 근거해 답한다.
  제공되지 않은 사실은 추측하지 않는다.
  근거 문장에는 [1], [2]를 사용한다.

user:
  resolved question: ...
  mode-specific answer policy: ...
  related page context: ...
  evidence:
    ## Evidence 1
    새 문서의 개념을 기존 페이지와 병합한다.
```

answer context의 page/graph 정보는 주제를 이해시키는 보조 context이고, factual citation의 직접 근거는 rank가 붙은 evidence snippet이다. 이 구분 때문에 모델이 관련 page 이름만 보고 근거 없는 세부사항을 확장해서는 안 된다.

**출력 계약과 다음 단계**

모델은 자연어 답변을 반환한다. page JSON이나 새로운 Wiki artifact를 만드는 단계가 아니다. citation을 모델이 누락해도 현재 assembler가 자동 주입하지 않으며, raw answer는 사용된 marker 추출·번호 정리 단계로 넘어간다.

**Prompt가 답변 범위를 결정하는 예시**

전달된 evidence:

```text
[1] Persistent Wiki는 신규 문서의 개념을 기존 concept page와 병합한다.
[2] 각 설명은 원본 source block reference를 유지한다.
```

prompt는 `외부 지식 금지`, `factual sentence마다 evidence rank citation`, `근거 없는 예시 금지`를 요구한다. 따라서 기대 모델 출력은 다음 범위다.

```text
Persistent Wiki는 새 문서를 독립 chunk로만 조회하지 않고 기존 concept page에 병합합니다. [1]
또한 설명을 원본 source block까지 추적할 수 있습니다. [2]
```

“항상 실시간 동기화된다”는 문장은 context에 없으므로 추가하면 계약 위반이다. “일반 RAG보다 무조건 정확하다” 역시 evidence가 없으면 출력할 수 없다. Query Engine은 모델이 반환한 `[1]`, `[2]`를 실제 snippet과 연결해 응답에 넣는다.

## 7. 기본 답변 생성과 Citation 검증

**역할과 입력**

raw answer의 `[숫자]` marker를 이번 답변 context의 evidence map과 대조한다.

**Citation 검증 규칙**

존재하지 않는 marker는 삭제하고, 처음 사용된 유효 marker 순서로 evidence와 citation 번호를 다시 매긴다. 모델이 marker를 하나도 사용하지 않으면 응답 `evidence_snippets`는 빈 목록이 된다. citation을 자동으로 추가하거나 source block 내용을 수정하지 않는다.

**출력**

정리된 `answer`와 사용된 `evidence_snippets`를 만든다. `related_pages`, `graph_context`, `traversal_paths`는 retrieval 결과를 그대로 유지한다. evaluator가 비활성이면 별도 평가 없이 다음 route 적용으로 넘어가며, Wiki 데이터는 수정하지 않는다.

답변에 실제로 사용된 marker를 추출해 evidence와 다시 연결한다. 모델이 없는 `[9]`를 만들면 해당 marker만 제거하고, `[3]`을 사용했으면 반환 시 `[1]`로 정리할 수 있다. `evidence_snippets`는 page 요약이 아니라 source document/block까지 내려가는 근거다.

## 8. Query Evaluator 분기

**역할과 입력**

evaluator가 활성화됐을 때 질문, 검증된 답변, evidence와 retrieval 정보를 평가한다.

**prompt의 핵심 내용**

답변의 질문 충족도, 내부 근거 충실도와 추가 검색 필요성을 검사하고 다음 route 중 하나만 JSON으로 반환하도록 요구한다.

```json
{
  "route": "revise_answer",
  "evidence_relevance": 0.8,
  "citation_evidence_alignment": 0.5,
  "unsupported_refusal_accuracy": null,
  "reason": "질문에는 답했지만 일부 citation이 주장을 직접 지원하지 않는다.",
  "feedback": "지원되지 않는 문장을 제거하고 [2] 근거로 다시 작성한다.",
  "warnings": [],
  "web_query": null
}
```

허용 route는 `internal_supported`, `revise_answer`, `web_fallback`, `internal_web_augmented`, `unsupported`다.

system prompt는 `services/ai/pipeline/prompts/query_answer_evaluator.system.md`다. user payload에는 원 question, resolved retrieval question, answer, stop reason, web availability, 상위 related pages와 evidence snippets가 들어간다. 단순 문체 취향이 아니라 answerability, groundedness, citation alignment와 내부 근거로 수정 가능한지를 판정한다.

route별 prompt 규칙:

| route | 선택 조건 | `feedback` / `web_query` |
| --- | --- | --- |
| `internal_supported` | 답변과 citation이 내부 근거로 충분함 | feedback은 빈 문자열, web query는 null |
| `revise_answer` | 같은 내부 evidence로 답변을 고칠 수 있음 | 실행 가능한 수정 feedback |
| `web_fallback` | 내부 근거가 핵심 답을 지원하지 않으며 public web 검색이 적절함 | 질문의 핵심 external query |
| `internal_web_augmented` | 내부 근거가 주제를 식별·부분 지원하지만 최신/구현 정보가 부족함 | 부족한 외부 facet query |
| `unsupported` | 내부와 적절한 web 모두 안전하게 답할 수 없음 | web query는 null |

prompt는 “web이 더 자세할 것 같다”는 이유만으로 web route를 고르지 못하게 한다. 내부 근거가 충분하면 `internal_supported`, 같은 근거로 수정 가능하면 `revise_answer`가 우선이다.

**Evaluator Prompt가 다음 Flow를 바꾸는 예시**

첫 답변이 “Persistent Wiki는 실시간으로 동기화됩니다. [1]”인데 `[1]`이 concept 병합만 설명한다면 evaluator는 citation alignment를 낮추고 `revise_answer`를 선택한다. 같은 evidence에서 고칠 수 있기 때문에 web search로 보내지 않는다. feedback이 answer prompt에 추가되고 두 번째 답변은 실시간 주장을 제거한다.

반대로 질문이 “2026년 현재 제품 가격은?”이고 내부 evidence가 제품 구조만 설명한다면, prompt의 “current external facet” 규칙에 따라 `internal_web_augmented`와 가격 검색용 `web_query`가 나올 수 있다. 이 JSON route가 9단계에서 내부+web context를 사용할지 직접 결정한다.

**Query Engine 처리와 다음 단계**

route schema를 검증한다. `internal_supported`는 현재 답변을 확정하고, `revise_answer`는 feedback을 answer prompt에 추가해 다시 답변 생성 단계로 보낸다. web route는 web evidence 단계로, `unsupported`는 근거 부족 응답으로 간다.

evaluator graph는 현재 attempt와 마지막 evaluation을 유지한다. `revise_answer`이고 feedback이 있으며 최대 시도 전이면 feedback을 answer context에 붙여 재생성한다. 기본 최대 시도는 `QUERY_EVALUATOR_MAX_ATTEMPTS=2`이며, 최대 시도를 초과하면 재작성하지 않고 unsupported/제한 응답으로 종료한다. evaluator 예외는 `query_evaluation_failed` 진행 event를 남기고 evaluation 없이 진행하되, low internal relevance이면 `unsupported`로 전환하고 그렇지 않으면 내부 답변 경로를 계속한다. `QUERY_EVALUATOR_MODE` 기본값은 `web`이고, web adapter/API key가 없으면 evaluator가 구성되지 않는다(`llm` 모드는 web 없이도 API key가 있으면 구성 가능).

## 9. Web Fallback·Internal Web Augmentation

**역할과 입력**

내부 근거가 부족하고 web 사용이 허용될 때 질문 또는 evaluator 보완 query로 web 결과를 얻는다.

**Answer Prompt 추가 구성**

검색 자체는 설정된 Tavily provider를 사용한다(`QUERY_WEB_SEARCH_MAX_RESULTS` 기본 5, timeout 기본 20초). 검색 결과는 title, URL, snippet과 score를 가진 `web` page/evidence context로 변환한 뒤 6단계의 answer system prompt를 다시 사용한다.

`web_fallback` user context에는 내부 Wiki가 핵심 답을 지원하지 않는다는 mode policy와 web evidence를 넣는다. `internal_web_augmented`에는 내부 evidence, web evidence와 “내부에서 지원하는 부분과 외부에서 보충하는 부분을 구분하라”는 policy를 함께 넣는다. 모델은 검색 결과 밖의 사실을 추가하지 않고, URL·검색 metadata를 내부 Wiki page id처럼 표현하지 않아야 한다.

evaluator가 반환한 `web_query`가 있으면 그 값을 검색어로 사용하고, 없으면 rewrite의 `retrieval_query`를 사용한다. web answer 역시 사용자에게 보여줄 본문만 반환하며 검색 trace나 score를 노출하지 않는다.

따라서 web 검색 결과가 세 개 들어왔다고 해서 세 결과를 요약하는 것이 목적이 아니다. answer prompt는 질문에 필요한 claim만 선택하고 제공된 web snippet으로 지원되는 문장만 만들도록 한다. `internal_web_augmented`에서는 내부 Wiki의 개념 설명과 web의 최신 사실을 각각 해당 evidence에 연결하며, web 사실을 기존 Wiki source block이 지원한 것처럼 표시하지 않는다.

**출력과 다음 단계**

보강 context를 answer 생성에 다시 전달한다. web 결과는 `web:<URL hash>` page로 메모리에서만 다루며 Wiki DB/MinIO에 저장하지 않는다. 검색 결과가 비거나 provider 예외가 나면 `web_search_executed=true`, `result_count=0`, 각각 `error_code=null` 또는 `web_search_failed`를 기록하고 web route를 완료하지 못한다.

`web_fallback`은 내부 근거가 핵심 답을 지원하지 않을 때 web 중심으로 답한다. `internal_web_augmented`는 내부 Wiki가 주제를 식별·부분 지원하고 최신·외부·구현 정보만 부족할 때 내부와 web context를 함께 사용한다. evaluator가 없어도 내부 relevance가 기본 threshold 0.5 미만이고 web adapter가 있으면 선행 fallback이 실행될 수 있다. 단, 요청 `allow_web_search=false`이면 evaluator와 fallback 모두 web을 사용할 수 없다.

## 10. 분기 합류: 최종 QueryResponse

**역할과 입력**

최종 answer와 retrieval/graph artifact를 HTTP 응답 계약으로 조립한다.

**응답 조립 규칙**

응답의 citation marker는 사용된 `evidence_snippets.rank`와 연결되며, 모델이 사용하지 않은 evidence는 최종 `evidence_snippets`에서 빠진다. 내부 `retrieval_summary`와 evaluator raw JSON은 HTTP 응답에 포함하지 않는다.

**최종 출력**

```json
{
  "answer": "Persistent Wiki는 ... [1]",
  "updated_conversation_summary": null,
  "related_pages": [
    {
      "id": "page-id",
      "page_type": "concept",
      "title": "Persistent Wiki",
      "slug": "persistent-wiki",
      "relevance_score": 0.92,
      "role": "focus",
      "depth": 0
    }
  ],
  "evidence_snippets": [
    {
      "rank": 1,
      "source_document_id": "doc-1",
      "source_block_ids": ["B0012"],
      "source_refs": [
        {"source_document_id": "doc-1", "source_block_id": "B0012"}
      ],
      "text": "새 문서의 개념을 기존 페이지와 병합한다."
    }
  ],
  "graph_context": {
    "nodes": [],
    "edges": []
  },
  "traversal_paths": [
    {
      "path_id": "path_1",
      "role": "primary_answer_path",
      "used_for_answer": true,
      "score": 0.88,
      "stop_reason": "no_frontier",
      "nodes": ["source-page-id", "concept-page-id"],
      "edges": []
    }
  ],
  "web_search_requested": false,
  "web_search_executed": false,
  "result_count": 0,
  "error_code": null
}
```

HTTP 응답은 위 `QueryResponse` 필드로 조립된다. web 검색이 실패하면 `error_code=web_search_failed`, adapter가 없으면 low-relevance web 요청의 `error_code=web_search_unavailable`이 될 수 있다. 채팅 메시지와 Query run 저장은 Spring backend 책임이며, Query Engine은 Wiki page/graph를 읽기만 한다.

비동기 Kafka worker에서는 `query_started`, context/rewrite, retrieval, graph, answer/evaluator, web 검색 등의 진행 event를 `ai.task.event`로 발행할 수 있다. 동기 HTTP 경로는 기본 `NoOpQueryEventPublisher`를 사용한다. event publisher 실패는 로그만 남기고 Query 결과를 실패시키지 않는다; worker publisher도 전송 timeout을 5초로 제한한다.

Kafka `ai.query.command`의 query command는 `kind=query`와 `run_id`, `workspace_id`, `user_id`, `session_id`, `question`, `provider`, `model`, `allow_web_search`를 필수로 요구하며 `allow_web_search`는 boolean이어야 한다. `recent_conversation_summary`와 `recent_messages`는 선택 context다. worker는 처리 결과를 `ai.task.event`에 다음 envelope으로 발행한다.

| event | `event_id` / `status` | `payload`와 `error` |
| --- | --- | --- |
| 진행 | `query:{run_id}:progress:{sequence}:{stage}` / `progress` | `payload={"stage": ..., "message": ..., "data": {...}}`, `error=null`; 원 command `request`는 포함하지 않는다. |
| 성공 | `query:{run_id}:succeeded` / `succeeded` | `payload`는 아래 HTTP 최종 출력과 동일한 `QueryResponse` JSON이고 `error=null`이다. |
| 실패 | `query:{run_id}:failed` / `failed` | `payload=null`, `error`는 예외 메시지(최대 1,000자)다. |

모든 결과 event에는 `run_id`, `kind`, `workspace_id`, `user_id`, `operation_id`가 포함되며, 성공·실패 event의 `request`는 secret field를 제거한 원 command다. 따라서 Kafka 성공 결과를 소비할 때는 `payload`를 이 문서 10장의 `QueryResponse` 계약으로 해석하고, `status`와 `event_id`를 처리 결과의 멱등 식별자로 사용한다.

## 운영상 주의점

- Query는 Wiki page, graph와 embedding unit을 읽기만 하며 Wiki를 수정하지 않는다.
- graph traversal은 모든 relation이 아니라 `source_mentions_concept`, `concept_related_to`만 사용한다.
- evaluator는 설정과 web/API key에 따라 구성되지 않을 수 있으며 HTTP 응답에는 evaluator raw JSON 전체가 포함되지 않는다.
- citation은 page 자체가 아니라 선택된 source block evidence를 가리킨다.
- web 보강 결과는 자동으로 Wiki page가 되지 않는다.

## 관련 문서

- `docs/backlog/evaluation/current-evaluator-metrics.md`
- `docs/backlog/evaluation/llm-evaluation-metrics.md`
- `docs/backlog/spec/llmpipeline-backend-output-contract.md`
