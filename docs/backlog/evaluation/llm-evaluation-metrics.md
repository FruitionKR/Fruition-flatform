# LLM Pipeline 평가 지표

## 1. 평가 철학

이 평가는 정답 concept 목록을 맞히는 평가가 아니다.

현재 LLM Pipeline은 원문 문서를 `source page`, `concept page`, `wiki graph`로 구조화하고, Query Engine은 이 구조를 바탕으로 답변을 생성한다. 따라서 최소 평가는 아래 질문에 답하면 된다.

```text
원문을 근거 손실 없이 구조화했는가?
생성된 concept와 relation이 source evidence에 근거하는가?
그 구조가 실제 질의응답에 도움이 되는가?
```

초기에는 지표를 많이 두지 않는다. 지표가 많으면 평가 비용이 커지고, 어떤 문제가 실제 회귀인지 판단하기 어렵다. MVP에서는 핵심 회귀를 잡는 필수 지표만 사용하고, 나머지는 문제가 반복될 때 진단 지표로 추가한다.

## 2. 평가 대상

### 2.1 Wiki 생성

원문 문서가 다음 구조로 잘 변환되었는지 평가한다.

- source block
- source page summary/key points
- concept page
- graph relation

### 2.2 Query Answer

생성된 wiki 구조가 실제 질문에 답하는 데 도움이 되는지 평가한다.

- retrieved evidence
- final answer
- citation
- unsupported question handling

## 3. MVP 필수 지표

MVP에서는 아래 8개만 본다.

| 영역 | 지표 | 값 형태 | 보는 것 |
| --- | --- | --- | --- |
| Source Block | `source_excerpt_fidelity` | Judge score, 1~5 | source block이 원문을 의미 손실 없이 발췌했는가 |
| Source Page | `source_faithfulness` | Judge score, 1~5 | summary/key points가 원문 근거를 벗어나지 않는가 |
| Source Page | `source_coverage` | Ratio, 0~1 | source page가 원문의 핵심 주제를 빠뜨리지 않았는가 |
| Concept Page | `concept_groundedness` | Judge score, 1~5 | concept 설명이 source evidence에서 도출 가능한가 |
| Graph Relation | `relation_faithfulness` | Pass rate, 0~1 | graph edge가 source/page 내용으로 설명 가능한가 |
| Query Answer | `evidence_relevance` | Ratio, 0~1 | retrieved evidence가 질문 해결에 실제로 관련 있는가 |
| Query Answer | `citation_evidence_alignment` | Ratio, 0~1 | 답변 citation이 claim을 지지하는 evidence를 가리키는가 |
| Query Answer | `unsupported_refusal_accuracy` | Accuracy, 0~1 | 근거 부족 질문에서 억지로 답하지 않는가 |

## 4. 지표 정의

### 4.1 source_excerpt_fidelity

원문에서 분리된 source block이 실제 원문 내용을 충실하게 발췌했는지 평가한다.

이 지표가 답하는 질문:

```text
원문에서 source block을 제대로 잘라 왔는가?
```

평가 방법:

- 원본 문서의 해당 문단과 생성된 source block text를 비교한다.
- 문장이 중간에서 잘렸는지, 표/목록/문단 구조가 의미를 바꿀 정도로 깨졌는지 확인한다.
- 원문에 없는 문장이 섞였거나 중요한 조건이 빠져 의미가 바뀌면 감점한다.

점수 기준:

| 점수 | 기준 |
| --- | --- |
| 5 | 원문 구간을 의미 손실 없이 정확히 발췌했다. |
| 4 | 사소한 포맷 손실은 있으나 의미는 보존된다. |
| 3 | 핵심 의미는 남아 있지만 일부 문맥이나 구조가 손실됐다. |
| 2 | 발췌 범위가 부정확해 근거 해석에 영향을 준다. |
| 1 | 원문과 다른 내용이거나 근거로 쓰기 어렵다. |

### 4.2 source_faithfulness

Source page의 summary와 key points가 원문 source block에 충실한지 평가한다.

이 지표가 답하는 질문:

```text
원문은 그런 내용이 아닌데, source page가 그럴듯한 설명을 근거처럼 달아두지 않았는가?
```

평가 방법:

- 원문 block과 source page summary/key points를 함께 제공한다.
- 각 설명이 원문에서 직접 지지되는지 1~5점으로 평가한다.
- 외부 지식으로 맞아 보이더라도 원문에서 지지되지 않으면 감점한다.

점수 기준:

| 점수 | 기준 |
| --- | --- |
| 5 | 모든 핵심 설명이 원문 block에서 직접 지지된다. |
| 4 | 대부분 지지되며 사소한 표현 확장만 있다. |
| 3 | 큰 방향은 맞지만 일부 중요한 설명의 근거가 약하다. |
| 2 | 원문과 부분적으로만 관련 있다. |
| 1 | 원문에서 도출하기 어렵다. |

### 4.3 source_coverage

Source page가 원문의 핵심 내용을 충분히 담았는지 평가한다.

이 지표가 답하는 질문:

```text
source page가 원문에서 중요한 내용을 빠뜨리지 않았는가?
```

평가 방법:

- 안정된 평가셋에서는 사람이 `required_source_topics`를 미리 정의한다.
- `required_source_topics`가 없으면 AI Judge가 원문에서 핵심 주제 3~7개를 추출하되, 초기에는 사람 샘플 검수로 기준을 보정한다.
- source page가 핵심 주제를 얼마나 포함하는지 계산한다.

계산:

```text
source_coverage = 포함된 핵심 주제 수 / 전체 핵심 주제 수
```

분모가 0이면 N/A로 기록하고 aggregate에서 제외한다.

### 4.4 concept_groundedness

Concept title, definition, key points가 source evidence에서 도출 가능한지 평가한다.

이 지표가 답하는 질문:

```text
이 concept 설명은 실제 source evidence에서 나온 말인가?
```

평가 방법:

- concept와 연결된 source block을 함께 제공한다.
- Judge는 외부 지식을 사용하지 않고 evidence만 기준으로 판단한다.
- definition/key point별 unsupported claim을 함께 반환한다.

점수 기준:

| 점수 | 기준 |
| --- | --- |
| 5 | concept의 모든 설명이 source evidence로 직접 지지된다. |
| 4 | 대부분 지지되며 사소한 표현 확장만 있다. |
| 3 | concept 자체는 타당하지만 일부 설명의 근거가 약하다. |
| 2 | evidence와 관련은 있으나 concept로 구조화하기에는 약하다. |
| 1 | evidence에서 도출하기 어렵다. |

### 4.5 relation_faithfulness

Graph edge가 source evidence나 page 내용으로 설명 가능한지 평가한다.

이 지표가 답하는 질문:

```text
이 graph relation은 source나 page 내용으로 설명 가능한 연결인가?
```

평가 방법:

- edge의 from node, to node, relation type, 관련 evidence를 함께 제공한다.
- Judge는 binary pass/fail과 이유를 반환한다.

Pass 조건:

```text
1. 두 노드가 의미적으로 관련 있다.
2. 연결 이유가 source evidence 또는 page 내용으로 설명 가능하다.
3. 관계 유형이 근거보다 과장되지 않았다.
4. 너무 넓은 범용 concept에 기계적으로 붙어서 생긴 관계가 아니다.
```

계산:

```text
relation_faithfulness = pass한 relation 수 / 전체 relation 수
```

분모가 0이면 N/A로 기록하고 aggregate에서 제외한다.

### 4.6 evidence_relevance

Query 수행 시 retrieved evidence가 질문에 실제로 관련 있는지 평가한다.

이 지표가 답하는 질문:

```text
Query가 가져온 evidence가 질문을 푸는 데 실제로 필요한 근거인가?
```

평가 방법:

- 질문, retrieved source/concept, evidence snippets를 함께 본다.
- 각 evidence snippet이 질문의 핵심 의도나 필요한 하위 질문을 직접 지원하는지 판단한다.
- 같은 문서에서 나온 내용이라도 질문 해결에 쓰이지 않는 배경 설명이면 실패로 본다.
- supported 질문에서 retrieved evidence가 0개이면 0점으로 본다.
- unsupported 질문에서 evidence가 없는 것은 이 지표가 아니라 `unsupported_refusal_accuracy`에서 판단한다.

계산:

```text
evidence_relevance = 질문과 관련 있는 evidence snippet 수 / 전체 evidence snippet 수
```

분모가 0이고 supported 질문이면 0점, unsupported 질문이면 N/A로 기록한다.

### 4.7 citation_evidence_alignment

답변 문장에 붙은 citation marker가 실제로 해당 claim을 지지하는 evidence를 가리키는지 평가한다.

이 지표가 답하는 질문:

```text
답변의 citation이 해당 claim을 실제로 지지하는 근거를 가리키는가?
```

평가 방법:

- 답변을 factual claim 단위로 나눈다.
- 각 claim의 citation marker가 가리키는 evidence를 확인한다.
- factual claim이 있는데 citation이 없으면 실패로 본다.
- citation이 필요한 factual claim이 0개인 refusal 답변은 N/A로 기록하고 aggregate에서 제외한다.

계산:

```text
citation_evidence_alignment = 올바른 citation이 붙은 factual claim 수 / citation이 필요한 factual claim 수
```

### 4.8 unsupported_refusal_accuracy

근거가 부족한 질문에서 억지로 답하지 않고 근거 부족을 말하는지 평가한다.

이 지표가 답하는 질문:

```text
근거가 부족한 질문에서 시스템이 모르는 것을 안다고 말하지 않는가?
```

평가 방법:

- 평가 데이터셋에 `answer_type = unsupported`인 질문을 포함한다.
- 답변이 제공된 evidence 밖 일반 지식으로 단정하면 실패로 본다.
- 단순 refusal 문구 포함 여부만 보지 않고, 답변이 실제로 근거 부족을 인정했는지 Judge 또는 classifier로 판정한다.

계산:

```text
unsupported_refusal_accuracy = 올바르게 근거 부족을 말한 unsupported 질문 수 / 전체 unsupported 질문 수
```

분모가 0이면 N/A로 기록하고 aggregate에서 제외한다.

## 5. MVP 통과 기준

초기 기준은 절대값보다 회귀 감지에 초점을 둔다. 아래 기준은 첫 baseline 이후 조정한다.

| 지표 | 통과 기준 |
| --- | --- |
| `source_excerpt_fidelity` | 평균 4.0 이상 |
| `source_faithfulness` | 평균 4.0 이상 |
| `source_coverage` | 0.80 이상 |
| `concept_groundedness` | 평균 4.0 이상 |
| `relation_faithfulness` | pass rate 0.85 이상 |
| `evidence_relevance` | 0.85 이상 |
| `citation_evidence_alignment` | 0.90 이상 |
| `unsupported_refusal_accuracy` | 0.90 이상 |

N/A 케이스는 해당 지표의 aggregate denominator에서 제외한다. 단, 특정 지표가 N/A만 발생하면 평가셋 설계 문제로 보고 gate를 통과시킨 것으로 간주하지 않는다.

## 6. 추가 지표 원칙

MVP 문서에는 후순위 지표 목록을 유지하지 않는다. 새 지표는 같은 실패가 반복되고, 기존 8개 지표만으로 원인 분리가 안 될 때만 추가한다.

### 6.1 제외한 지표와 이유

아래 지표들은 유용할 수 있지만, MVP에서는 평가 비용과 중복을 줄이기 위해 제외한다.

| 제외 지표 | 제외 이유 |
| --- | --- |
| `source_noise_rate` | `source_faithfulness`와 `source_coverage`로 먼저 근거 이탈과 핵심 누락을 잡는다. 과잉 생성 문제가 반복될 때만 추가한다. |
| `source_noise_breakdown` | 독립 평가가 아니라 `source_noise_rate`의 필드별 집계다. `source_noise_rate`를 쓰지 않는 동안은 필요 없다. |
| `core_concept_selection_quality` | 핵심 concept 선택 문제는 우선 `source_coverage`와 `concept_groundedness`로 간접 확인한다. |
| `unsupported_concept_rate` | `concept_groundedness` 점수 분포로 먼저 확인한다. concept 과잉 생성이 반복될 때만 비율 지표로 분리한다. |
| `concept_specificity` | 너무 넓은 concept 문제가 실제 검색 noise로 나타날 때 추가한다. 초기 gate로 두면 판정 비용이 크다. |
| `concept_redundancy_rate` | merge/alias 로직을 바꿀 때 필요한 회귀 지표다. MVP 기본 품질 확인에는 과하다. |
| `relation_faithfulness_by_edge_type` | 독립 평가가 아니라 `relation_faithfulness`의 edge type별 집계다. 전체 relation 품질이 흔들릴 때만 본다. |
| `graph_coherence` | traversal 전략 평가에 가깝다. MVP에서는 relation 근거성과 query evidence 품질을 먼저 본다. |
| `evidence_coverage` | `required_evidence_units`를 사람이 충분히 정의해야 안정적이다. MVP에서는 `evidence_relevance`와 citation 정합성을 먼저 본다. |
| `answer_relevance` | 답변이 질문을 우회하는 문제가 반복될 때 추가한다. 초기에는 evidence와 citation 품질로 간접 확인한다. |
| `answer_completeness` | completeness 기준을 만들려면 질문별 필수 답변 요소가 필요하다. MVP에서는 누락 문제가 반복될 때만 추가한다. |
| latency/token/cost | 품질 기준이 안정화된 뒤 운영 지표로 추가한다. |

### 6.2 추가 기준

추가 기준:

- 어떤 실패를 잡을지 한 문장으로 설명할 수 있어야 한다.
- 기존 지표와 중복되지 않아야 한다.
- 계산식과 분모 0 처리 기준이 명확해야 한다.
- gate로 쓸지, 진단 리포트로만 쓸지 먼저 정해야 한다.

## 7. 평가 데이터셋

평가 데이터셋은 JSONL로 시작한다.

### 7.1 Wiki 생성 평가 데이터

```json
{
  "case_id": "wiki-001",
  "document_id": "doc_eval_001",
  "source_path": "eval/documents/doc_eval_001.md",
  "evaluation_targets": ["source", "concept", "relation"]
}
```

안정된 회귀 평가셋에서는 `source_coverage` 기준을 고정하기 위해 아래 필드를 추가할 수 있다.

```json
{
  "required_source_topics": ["source page", "concept page", "wiki graph"]
}
```

### 7.2 Query 평가 데이터

```json
{
  "case_id": "query-001",
  "question": "LLM Wiki가 일반 RAG와 뭐가 달라?",
  "answer_type": "supported",
  "expected_topics": ["source page", "concept page", "wiki graph"],
  "must_not_claim": ["evidence에 없는 일반 지식"]
}
```

필드 의미:

| 필드 | 의미 |
| --- | --- |
| `case_id` | 평가 케이스 식별자 |
| `question` | 사용자 질문 |
| `answer_type` | `supported` 또는 `unsupported` |
| `expected_topics` | 답변이나 retrieval이 다뤄야 하는 핵심 주제 힌트 |
| `must_not_claim` | evidence 없이 말하면 안 되는 내용 |

평가 실행 후에는 같은 `case_id`로 raw output을 저장한다. 이 raw output이 `evidence_relevance`, `citation_evidence_alignment`, `unsupported_refusal_accuracy`의 직접 평가 대상이다.

```json
{
  "case_id": "query-001",
  "retrieved_sources": ["source:doc_eval_001"],
  "retrieved_concepts": ["concept:llm_wiki"],
  "evidence_snippets": [
    {
      "source_id": "source:doc_eval_001",
      "text": "LLM Wiki는 source page, concept page, wiki graph를 생성해 Query Answer에 활용한다."
    }
  ],
  "answer": "LLM Wiki는 원문을 source page, concept page, wiki graph로 구조화한 뒤 답변에 활용한다.",
  "citations": [
    {
      "claim": "LLM Wiki는 원문을 source page, concept page, wiki graph로 구조화한다.",
      "source_id": "source:doc_eval_001"
    }
  ]
}
```

## 8. 코드 자동화 방향

권장 구조:

```text
llmPipeline/evals/
  datasets/
    wiki_generation_eval.jsonl
    query_eval.jsonl
  prompts/
    source_excerpt_fidelity_judge.md
    source_faithfulness_judge.md
    source_coverage_judge.md
    concept_groundedness_judge.md
    relation_faithfulness_judge.md
    evidence_relevance_judge.md
    citation_evidence_alignment_judge.md
    unsupported_refusal_accuracy_judge.md
  metrics.py
  judge.py
  run_wiki_eval.py
  run_query_eval.py
  report.py
```

실행 흐름:

```text
eval dataset
  -> pipeline/query 실행
  -> raw outputs 수집
  -> AI Judge 호출
  -> deterministic aggregate 계산
  -> eval_report.md 생성
```

## 9. 우선순위

1. 원문이 source block으로 충실하게 발췌되었는지 본다.
2. Source page가 원문에 충실하고 핵심 내용을 담았는지 본다.
3. Concept가 source evidence에 grounded 되어 있는지 본다.
4. Relation이 source/page 근거로 설명 가능한지 본다.
5. Query에서 evidence, citation, unsupported handling이 맞는지 본다.
