# 현재 Evaluator 평가 지표

## 1. 평가 철학

현재 evaluator는 정답 concept 목록을 맞히는 평가가 아니다. 여기서 evaluator는 Pipeline 결과를 사람이 읽듯이 검토하고 점수와 피드백을 JSON으로 반환하는 LLM judge를 말한다.

현재 코드 기준 evaluator는 두 지점에서 LLM Pipeline의 결과를 평가한다.

```text
원문이 source block과 semantic structure로 근거 손실 없이 변환되었는가?
생성된 concept, relation, observation, evidence unit이 source evidence에 근거하는가?
Query Engine이 사용한 evidence와 citation이 최종 답변을 실제로 지지하는가?
```

여기서 source block은 원문을 근거 단위로 나눈 조각이고, semantic structure는 원문에서 뽑은 concept, relation, observation, evidence unit을 검색과 답변에 쓰기 좋게 정리한 구조다. source evidence는 외부 지식이나 추측이 아니라 원문에서 확인할 수 있는 근거를 뜻한다.

평가는 독립 metric runner가 아니라 LLM judge prompt와 일부 코드 guard로 수행된다. metric runner는 점수를 계산하는 별도 실행기를 뜻하고, 현재 코드는 그런 별도 실행기 없이 prompt가 평가 JSON을 반환한다. guard는 LLM judge 결과만 믿지 않고 코드에서 추가로 적용하는 방어 규칙이다. Wiki 생성 평가는 `llmPipeline/run_lab.py`의 evaluation loop에서 실행되고, Query Answer 평가는 `QueryAnswerEvaluator`가 답변 생성 뒤 실행한다.

## 2. 평가 대상

### 2.1 Wiki 생성

원문 문서가 검색과 답변에 쓰기 좋은 구조로 잘 변환되었는지 평가한다.

- source block: 원문을 근거 단위로 나눈 텍스트 조각
- concept ledger: 문서에서 핵심 개념으로 관리할 concept 목록
- category: concept나 결과를 묶는 상위 분류
- section candidate: core concept로 승격하기에는 약하지만 섹션이나 하위 주제로 볼 수 있는 후보
- mention: 원문에 등장한 표현이나 참조
- observation: 원문에서 뽑은 관찰 가능한 사실 단위
- evidence unit: 검색, 즉 retrieval에 직접 쓰기 좋은 한 가지 주장 중심의 근거 단위
- warning: 정규화나 구조화 중 발견된 주의사항

현재 Wiki 생성 evaluator 입력은 `document`, `source_blocks`, `normalized`이다. `document`는 원본 문서이고, `source_blocks`는 원문을 나눈 근거 조각 목록이다. `normalized`는 LLM이 뽑은 중간 결과를 코드가 정리해 다음 단계에 넘길 수 있게 만든 구조화 결과이며, `semantic_notes`, `concept_ledger`, `categories`, `section_candidates`, `mentions`, `observations`, `evidence_units`, `warnings`가 포함된다.

### 2.2 Query Answer

생성된 wiki 구조와 검색 결과가 실제 질문에 답하는 데 도움이 되는지 평가한다.

- related pages: 질문과 관련 있다고 검색된 내부 Wiki page 목록
- evidence snippets: 답변에 사용된 근거 문장이나 문단 조각
- final answer: 사용자에게 반환된 최종 답변
- citation: 답변 문장이 어떤 근거를 참조하는지 표시한 것
- unsupported question handling: 근거가 부족한 질문에서 억지로 답하지 않고 처리하는 방식
- web fallback route: 내부 근거로 답하기 어려울 때 외부 검색으로 넘기는 처리 방향

현재 Query Answer evaluator 입력은 `question`, `resolved_retrieval_question`, `answer`, `stop_reason`, `web_search_available`, `related_pages`, `evidence_snippets`이다. `question`은 사용자 원 질문이고, `resolved_retrieval_question`은 검색에 맞게 정리된 질문이다. `stop_reason`은 답변 생성이 왜 멈췄는지 나타내는 값이고, `web_search_available`은 현재 외부 검색을 사용할 수 있는지 나타낸다.

## 3. MVP 필수 지표

현재 코드 기준 evaluator가 직접 반환하거나 사용하는 점수 지표는 아래 8개다.

| 영역 | 지표 | 값 형태 | 보는 것 |
| --- | --- | --- | --- |
| Wiki Generation | `source_excerpt_fidelity` | Judge score, 1~5 | 원문을 나눈 source block이 원문 근거를 의미 손실 없이 보존하는가 |
| Wiki Generation | `concept_groundedness` | Judge score, 1~5 | 핵심 개념인 core concept와 설명이 원문 근거에서 도출 가능한가 |
| Wiki Generation | `relation_faithfulness` | Judge score, 0~1 | relation이 source/page 내용으로 설명 가능한가 |
| Wiki Generation | `evidence_relevance` | Judge score, 0~1 | observation/evidence unit이 검색에 유용한 근거 단위인가 |
| Wiki Generation | `overall` | Judge score, 0~1 | Wiki 생성 결과의 종합 품질 |
| Query Answer | `evidence_relevance` | Judge score, 0~1 | 답변에 사용된 evidence snippet이 질문과 맞는가 |
| Query Answer | `citation_evidence_alignment` | Judge score, 0~1 또는 null | 답변 citation이 해당 claim, 즉 사실 주장을 실제로 지지하는가 |
| Query Answer | `unsupported_refusal_accuracy` | Judge score, 0~1 또는 null | 근거 부족 답변의 refusal, 즉 답변 제한이 타당한가 |

기존 설계 문서의 `source_faithfulness`, `source_coverage`는 현재 evaluator 반환 스키마에는 없다. Source page summary/key points 단위의 별도 평가도 현재 코드 기준으로는 직접 수행하지 않는다.

점수 지표는 아니지만 evaluator가 반환하거나 코드가 후속 처리에 사용하는 필드는 아래와 같다.

| 영역 | 필드 | 값 형태 | 쓰임 |
| --- | --- | --- | --- |
| Wiki Generation | `passed` | Boolean, true/false | Wiki 생성 평가 통과 여부 |
| Wiki Generation | `retry_recommended` | Boolean, true/false | 원문에서 의미 구조를 다시 뽑는 semantic extraction 재시도 여부 |
| Wiki Generation | `issues` | List, 목록 | retry, 자동 보정, 실패 원인 진단에 사용할 issue 목록 |
| Wiki Generation | `retry_feedback` | Text | 다음 semantic extraction 시도에 붙일 evaluator feedback |
| Wiki Generation | `repair_operations` | List, 목록 | 자동 보정이 수행된 경우 보정 내역 |
| Query Answer | `route` | Enum, 정해진 값 중 하나 | 내부 답변 유지, 외부 검색 전환, 근거 부족 처리 방향 결정 |
| Query Answer | `reason` | Text | evaluator 판단 이유 |
| Query Answer | `feedback` | Text | 답변 또는 retrieval 개선을 위한 피드백 |
| Query Answer | `web_query` | Text 또는 null | web fallback 또는 web augmentation에 사용할 검색 query |

## 4. 지표 정의

### 4.1 source_excerpt_fidelity

원문에서 분리된 source block, 즉 원문을 근거 단위로 자른 텍스트 조각이 실제 원문 내용을 충실하게 보존했는지 평가한다.

이 지표가 답하는 질문:

```text
source block이 원문 근거를 의미 손실 없이 담고 있는가?
```

평가 방법:

- `document`와 `source_blocks`를 함께 제공한다. `document`는 원본 문서이고, `source_blocks`는 그 문서를 나눈 근거 조각이다.
- source block이 원문 근거를 보존하는지 LLM judge가 1~5점으로 평가한다.
- 평가 결과는 Wiki 생성 evaluator의 `scores.source_excerpt_fidelity`로 반환된다.

점수 기준:

| 점수 | 기준 |
| --- | --- |
| 5 | 원문 근거가 의미 손실 없이 보존된다. |
| 4 | 사소한 포맷 손실은 있으나 의미는 보존된다. |
| 3 | 핵심 의미는 남아 있지만 일부 문맥이나 구조가 손실됐다. |
| 2 | source block 품질이 다음 단계의 evidence 해석에 영향을 준다. |
| 1 | 원문 근거로 쓰기 어렵다. |

### 4.2 concept_groundedness

Core concept, 즉 문서에서 핵심 개념으로 관리할 항목이 source evidence에서 도출 가능하고 retrieval에 재사용 가능한지 평가한다. 여기서 retrieval은 질문에 답하기 위해 관련 Wiki page와 evidence를 검색하는 과정을 뜻한다.

이 지표가 답하는 질문:

```text
이 concept는 원문 근거에서 나온 핵심 개념인가?
```

평가 방법:

- `concept_ledger`, `section_candidates`, `mentions`, `evidence_units`를 함께 본다. `concept_ledger`는 core concept 목록이고, `section_candidates`와 `mentions`는 아직 핵심 개념으로 보기 어려운 후보나 단순 언급이다.
- core concept가 과하게 쪼개졌거나, 섹션 후보 또는 단순 언급 수준 항목이 core concept로 잘못 승격됐는지 확인한다.
- 평가 결과는 Wiki 생성 evaluator의 `scores.concept_groundedness`로 반환된다.

점수 기준:

| 점수 | 기준 |
| --- | --- |
| 5 | core concept가 source evidence에 잘 근거하고 검색에 재사용 가능하다. |
| 4 | 대부분 타당하며 사소한 분류 오류만 있다. |
| 3 | 핵심 concept는 남아 있지만 일부 과분할 또는 승격 오류가 있다. |
| 2 | concept 구조가 source evidence와 약하게만 연결된다. |
| 1 | concept 구조가 근거에서 도출됐다고 보기 어렵다. |

### 4.3 relation_faithfulness

Relation, 즉 concept끼리의 연결이 source evidence나 page 내용으로 설명 가능한지 평가한다.

이 지표가 답하는 질문:

```text
생성된 relation은 근거로 설명 가능한 연결인가?
```

평가 방법:

- Wiki 생성 evaluator가 `normalized` 구조 안의 relation 성격을 평가한다. `normalized`는 원문에서 뽑은 의미 정보를 코드가 정리한 최종 구조화 결과다.
- 관계가 원문 근거보다 과장됐거나 기계적으로 붙은 연결이면 감점한다.
- 평가 결과는 Wiki 생성 evaluator의 `scores.relation_faithfulness`로 반환된다.

계산:

```text
relation_faithfulness = judge가 판단한 relation 근거성 점수
```

현재 코드는 relation별 deterministic pass rate를 별도로 계산하지 않는다.

### 4.4 evidence_relevance

Wiki 생성과 Query Answer 양쪽에서 쓰이지만 평가 대상이 다르다.

이 지표가 답하는 질문:

```text
evidence가 다음 단계의 검색 또는 현재 질문 해결에 실제로 유용한가?
```

Wiki 생성 평가 방법:

- `observations`와 `evidence_units`가 깨지거나 중복된 chunk artifact가 아닌지 본다. chunk artifact는 문서를 자르는 과정에서 생긴 어색한 조각, 중복, 문맥이 끊긴 문장을 뜻한다.
- evidence claim이 atomic하고 직접 source block에 연결됐는지 본다. atomic하다는 것은 한 근거 단위가 너무 많은 주장을 한꺼번에 담지 않고 하나의 명확한 주장에 가깝다는 뜻이다.
- 평가 결과는 Wiki 생성 evaluator의 `scores.evidence_relevance`로 반환된다.

Query Answer 평가 방법:

- `question`, `related_pages`, `evidence_snippets`, `answer`를 함께 본다. `related_pages`는 검색된 내부 Wiki page이고, `evidence_snippets`는 답변에 실제 사용된 근거 조각이다.
- 답변에 실제 사용된 evidence snippet이 질문의 핵심 의도나 필요한 하위 질문을 지원하는지 본다.
- 평가 결과는 Query Answer evaluator의 `evidence_relevance`로 반환된다.

계산:

```text
evidence_relevance = judge가 판단한 evidence 관련성 점수
```

현재 코드는 관련 snippet 수를 직접 세어 ratio를 계산하지 않고, LLM judge가 0~1 점수를 반환한다.

### 4.5 overall

Wiki 생성 결과의 종합 품질을 평가한다.

이 지표가 답하는 질문:

```text
생성된 의미 구조가 전체적으로 질문 검색과 답변 생성에 쓸 수 있는가?
```

평가 방법:

- Wiki 생성 evaluator가 `source_excerpt_fidelity`, `concept_groundedness`, `relation_faithfulness`, `evidence_relevance`와 diagnostic issue를 종합한다. diagnostic issue는 실패 원인을 설명하는 진단 항목이다.
- 코드 guard에서 medium/high issue가 남으면 `passed`를 false로 바꾸고, `overall`이 숫자일 때 최대 0.74로 낮춘다. medium/high issue는 심각도가 중간 이상인 문제를 뜻한다.

계산:

```text
overall = judge가 판단한 Wiki 생성 종합 점수
```

### 4.6 citation_evidence_alignment

답변 문장에 붙은 citation marker, 즉 근거 표시가 실제로 해당 claim을 지지하는 evidence를 가리키는지 평가한다. claim은 답변 안의 사실 주장을 뜻한다.

이 지표가 답하는 질문:

```text
답변의 citation이 해당 claim을 실제로 지지하는 근거를 가리키는가?
```

평가 방법:

- Query Answer evaluator가 `answer`와 `evidence_snippets`를 비교한다.
- 문장이 citation한 evidence, 즉 인용한 근거 조각이 해당 문장을 지지하지 않으면 감점한다.
- 평가 결과는 `citation_evidence_alignment`로 반환된다.
- 값이 없으면 `null`로 정규화될 수 있다.

계산:

```text
citation_evidence_alignment = judge가 판단한 citation-claim 정합성 점수
```

현재 코드는 claim 단위 denominator를 직접 계산하지 않고, LLM judge가 0~1 점수를 반환한다.

### 4.7 unsupported_refusal_accuracy

근거가 부족한 질문에서 억지로 답하지 않고 근거 부족을 말하는지 평가한다. refusal은 근거 부족, 안전 문제, 답변 불가 사유를 밝히며 답변을 제한하는 응답을 뜻한다.

이 지표가 답하는 질문:

```text
근거가 부족한 답변에서 시스템이 모르는 것을 안다고 말하지 않는가?
```

평가 방법:

- Query Answer evaluator가 답변이 refusal이거나 evidence 부족을 말하는 경우 그 refusal이 맞는지 판단한다.
- retrieved evidence, 즉 검색된 내부 근거가 부족하고 web search도 사용할 수 없거나 부적절하면 `unsupported` route를 선택할 수 있다.
- web search가 가능하고 외부 공개 정보로 답할 수 있으면 `unsupported` 대신 `web_fallback`을 선택할 수 있다.
- 평가 결과는 `unsupported_refusal_accuracy`로 반환된다.
- 해당 없는 답변에서는 `null`이 될 수 있다.

계산:

```text
unsupported_refusal_accuracy = judge가 판단한 refusal 타당성 점수
```

### 4.8 route

Query Answer evaluator가 답변 후속 처리를 위해 선택하는 제어 필드다. route는 평가 뒤에 답변을 그대로 쓸지, 외부 검색으로 넘길지, 근거 부족으로 처리할지 정하는 방향 값이다. 점수 지표는 아니지만 현재 evaluator 출력에서 Query Engine 동작에 직접 영향을 주므로 함께 기록한다.

이 지표가 답하는 질문:

```text
현재 답변은 내부 evidence로 충분한가, 아니면 web fallback이나 unsupported 처리가 필요한가?
```

평가 방법:

- 답변과 evidence를 먼저 읽은 뒤 route를 고른다.
- 허용 route는 `internal_supported`, `web_fallback`, `internal_web_augmented`, `unsupported`다.
- 허용되지 않은 route가 반환되면 코드에서 `internal_supported`로 정규화한다.
- `internal_web_augmented`나 `web_fallback`에서는 `web_query`를 반환할 수 있다.

Route 기준:

| route | 기준 |
| --- | --- |
| `internal_supported` | 답변이 검색된 내부 Wiki evidence로 충분히 지지된다. |
| `web_fallback` | 검색된 내부 Wiki evidence가 핵심 답변을 지지하지 못하고, 외부 검색으로 답해야 한다. |
| `internal_web_augmented` | 내부 Wiki evidence가 주제를 식별하거나 일부 답하지만 최신 정보, 구현 방법, 외부 도구 정보가 추가로 필요하다. |
| `unsupported` | 현재 evidence와 적절한 web search로도 안전하게 답할 수 없다. |

### 4.9 passed

Wiki 생성 evaluator가 반환하는 통과 여부다. 이 값은 현재 구조화 결과를 다음 단계에 넘길 수 있는지 판단하는 Boolean 값이다.

이 필드가 답하는 질문:

```text
정규화된 의미 구조를 다음 단계에 그대로 써도 되는가?
```

평가 방법:

- Wiki 생성 evaluator prompt의 통과 기준을 만족하면 `true`가 될 수 있다.
- `run_lab.py`의 guard에서 medium/high issue가 남아 있으면 `false`로 바뀐다.
- `passed`가 `true`이면 evaluation loop는 추가 retry 없이 종료될 수 있다.

현재 통과 기준은 `source_excerpt_fidelity >= 4`, `concept_groundedness >= 4`, `relation_faithfulness >= 0.75`, `evidence_relevance >= 0.75`, high severity issue 없음, medium/high observation issue 없음이다. observation issue는 원문에서 뽑은 사실 단위가 중복되거나 깨졌거나 source reference가 빠진 문제를 뜻한다.

### 4.10 retry_recommended

Wiki 생성 결과를 다시 생성할지 결정하는 제어 필드다. 다시 생성한다는 것은 원문에서 concept, observation, evidence 후보를 뽑는 semantic extraction 단계를 한 번 더 실행한다는 뜻이다.

이 필드가 답하는 질문:

```text
evaluator feedback을 반영해 원문 의미 추출을 다시 실행해야 하는가?
```

평가 방법:

- Wiki 생성 evaluator가 직접 반환한다.
- 반환값이 없으면 코드에서 `not passed`를 기본값으로 사용한다.
- `run_lab.py`의 guard에서 medium/high issue가 있으면 `true`로 바뀐다.
- `retry_recommended`가 `true`이고 최대 시도 횟수에 도달하지 않았으면 `retry_feedback`을 semantic prompt에 붙여 재시도한다. semantic prompt는 원문에서 의미 구조를 뽑도록 LLM에 주는 system prompt다.

### 4.11 issues

Wiki 생성 evaluator가 반환하는 진단 issue 목록이다. issue는 evaluator가 발견한 구체적인 문제 하나를 뜻한다.

이 필드가 답하는 질문:

```text
어떤 구조적 문제가 평가 실패나 retry의 직접 원인인가?
```

평가 방법:

- 각 issue는 `metric`, `type`, `severity`, `target`, `reason`, `feedback`을 포함한다. `target`은 문제가 발생한 concept slug나 block id 같은 대상 식별자다.
- `severity`는 문제의 심각도이며 `low`, `medium`, `high` 중 하나다.
- medium/high issue가 남으면 코드 guard가 `passed = false`, `retry_recommended = true`로 바꾼다.
- `duplicate_observation`, `broken_observation`, `observation_missing_ref`는 일부 자동 보정 대상이다.

현재 issue type:

| issue type | 의미 |
| --- | --- |
| `over_fragmented_concept` | concept가 지나치게 잘게 분리됐다. |
| `vague_umbrella_concept` | 너무 넓고 모호한 umbrella concept가 생성됐다. |
| `section_or_mention_should_not_be_core` | section candidate나 mention 수준 항목이 core concept로 승격됐다. |
| `source_block_too_coarse` | source block이 너무 커서 근거 단위로 쓰기 어렵다. |
| `evidence_too_broad` | evidence가 한 가지 명확한 주장으로 보기 어렵게 넓다. |
| `missing_ref` | 필요한 source reference가 빠졌다. |
| `duplicate_observation` | observation이 중복됐다. |
| `broken_observation` | observation이 깨졌거나 문서 분할 과정에서 생긴 어색한 조각에 가깝다. |
| `observation_missing_ref` | observation에 직접 source reference가 없다. |

### 4.12 retry_feedback

Wiki 생성 evaluator가 반환하는 재시도용 피드백이다. 다음 semantic extraction에서 무엇을 바꿔야 하는지 LLM에 다시 알려주는 짧은 지시문이다.

이 필드가 답하는 질문:

```text
다음 semantic extraction 시도에서 무엇을 고쳐야 하는가?
```

평가 방법:

- Wiki 생성 evaluator가 한국어로 간결한 재생성 지시를 반환한다.
- 코드 guard가 issue feedback을 합쳐 `retry_feedback`을 재구성할 수 있다.
- 재시도 시 기존 semantic system prompt 뒤에 `Evaluator feedback for retry`라는 제목으로 붙는다.

### 4.13 repair_operations

자동 보정이 수행된 경우 보정 내역을 기록하는 필드다. 자동 보정은 LLM을 다시 부르기 전에 코드가 명확한 observation 문제를 직접 고치는 작업이다.

이 필드가 답하는 질문:

```text
evaluator issue를 바탕으로 어떤 observation 보정을 수행했는가?
```

평가 방법:

- evaluator prompt가 직접 요구하는 기본 반환 필드는 아니다.
- `run_lab.py`가 repair 가능한 observation issue를 처리한 뒤 repair evaluation 결과에 추가한다.
- 대상 issue는 `duplicate_observation`, `broken_observation`, `observation_missing_ref`다.

### 4.14 reason

Query Answer evaluator가 반환하는 판단 이유다.

이 필드가 답하는 질문:

```text
왜 이 route와 점수를 선택했는가?
```

평가 방법:

- Query Answer evaluator가 한국어 이유를 반환한다.
- 코드에서는 없으면 빈 문자열로 정규화한다.
- 현재 event의 `query_evaluated` payload에 포함된다.

### 4.15 feedback

Query Answer evaluator가 반환하는 개선 피드백이다.

이 필드가 답하는 질문:

```text
답변, evidence 선택, citation, fallback 판단에서 무엇을 고쳐야 하는가?
```

평가 방법:

- Query Answer evaluator가 한국어 actionable feedback을 반환한다.
- 코드에서는 없으면 빈 문자열로 정규화한다.
- 현재 코드 기준 별도 repair loop에는 직접 사용하지 않는다.

### 4.16 web_query

Query Answer evaluator가 web 검색이 필요하다고 판단할 때 반환하는 검색 query다. 내부 Wiki 근거만으로 답하기 어렵지만 외부 공개 정보로 보완할 수 있을 때 사용한다.

이 필드가 답하는 질문:

```text
내부 evidence만으로 부족할 때 어떤 외부 질문으로 검색해야 하는가?
```

평가 방법:

- `internal_web_augmented`에서는 누락된 외부/current/implementation facet을 query로 만든다.
- `web_fallback`에서는 사용자 질문의 핵심 외부 질문을 query로 만든다.
- `internal_supported` 또는 `unsupported`에서는 `null`로 둔다.
- 코드에서는 빈 문자열을 `null`로 정규화하고, 값이 있으면 web search용 query rewrite에 사용한다.

## 5. MVP 통과 기준

현재 Wiki 생성 evaluator prompt의 통과 기준은 아래와 같다.

| 지표 | 통과 기준 |
| --- | --- |
| `source_excerpt_fidelity` | 4 이상 |
| `concept_groundedness` | 4 이상 |
| `relation_faithfulness` | 0.75 이상 |
| `evidence_relevance` | 0.75 이상 |
| diagnostic issue | medium/high `duplicate_observation`, `broken_observation`, `observation_missing_ref`가 남지 않아야 함 |
| diagnostic issue | high severity issue가 없어야 함 |

`llmPipeline/run_lab.py`의 guard는 medium/high issue가 있으면 `passed = false`, `retry_recommended = true`로 바꾸고, `overall`을 최대 0.74로 낮춘다.

Query Answer evaluator에는 현재 코드상 별도 pass/fail gate가 없다. 평가 결과는 `query_evaluated` event로 발행되고, `web_query`가 있으면 web 검색용 query rewrite에 사용된다.

## 6. 추가 지표 원칙

현재 evaluator는 필수 지표 외에 diagnostic issue type을 함께 반환한다. 이 issue들은 새 aggregate metric이라기보다 retry와 자동 보정을 위한 진단 정보다.

### 6.1 제외한 지표와 이유

아래 지표들은 기존 설계 문서에는 있거나 파생 가능하지만, 현재 코드 기준 evaluator가 직접 반환하지 않는다.

| 제외 지표 | 제외 이유 |
| --- | --- |
| `source_faithfulness` | 현재 Wiki 생성 evaluator 반환 스키마에 없다. Source page summary/key points 단위 평가도 별도로 실행하지 않는다. |
| `source_coverage` | 현재 평가셋의 `required_source_topics` 기반 coverage 계산이 구현되어 있지 않다. |
| relation별 pass rate | 현재 `relation_faithfulness`는 judge 점수로 받으며 relation별 deterministic denominator를 계산하지 않는다. |
| claim별 citation ratio | 현재 `citation_evidence_alignment`는 judge 점수로 받으며 claim별 ratio를 코드에서 계산하지 않는다. |
| aggregate report metric | 현재 Query Answer evaluator 결과는 event와 route 판단에 쓰이며 별도 aggregate report로 계산하지 않는다. |

현재 Wiki 생성 evaluator가 반환할 수 있는 diagnostic issue type은 4.11에 정리한다.

### 6.2 추가 기준

새 지표를 추가하려면 아래를 먼저 정해야 한다.

- prompt 반환 스키마에 포함할지, 코드에서 deterministic하게 계산할지 정한다.
- retry gate로 쓸지, 진단 리포트로만 쓸지 정한다.
- 분모가 필요한 지표라면 분모 0 처리 기준을 정한다.
- 기존 `issues`로 충분히 표현되는 문제인지 확인한다.

## 7. 평가 데이터셋

현재 Wiki 생성 평가는 별도 JSONL dataset runner가 아니라 `run_lab.py` 실행 중 생성된 document와 normalized output을 바로 judge에 전달한다.

### 7.1 Wiki 생성 평가 데이터

현재 Wiki 생성 evaluator payload는 아래 형태다.

```json
{
  "document": {},
  "source_blocks": [
    {
      "block_id": "source-block-id",
      "text": "source block text"
    }
  ],
  "normalized": {
    "semantic_notes": [],
    "concept_ledger": [],
    "categories": [],
    "section_candidates": [],
    "mentions": [],
    "observations": [],
    "evidence_units": [],
    "warnings": []
  }
}
```

현재 evaluator 반환값은 아래 형태다.

```json
{
  "scores": {
    "source_excerpt_fidelity": 1,
    "concept_groundedness": 1,
    "relation_faithfulness": 0.0,
    "evidence_relevance": 0.0,
    "overall": 0.0
  },
  "passed": false,
  "retry_recommended": true,
  "issues": [
    {
      "metric": "concept_groundedness",
      "type": "over_fragmented_concept",
      "severity": "low | medium | high",
      "target": ["slug-or-block-id"],
      "reason": "Korean reason",
      "feedback": "Korean actionable feedback"
    }
  ],
  "retry_feedback": "Korean concise instructions for regenerating semantic extraction"
}
```

### 7.2 Query 평가 데이터

현재 Query Answer evaluator payload는 아래 형태다.

```json
{
  "question": "사용자 원 질문",
  "resolved_retrieval_question": "검색용으로 정리된 질문",
  "answer": "근거 표시가 포함된 최종 답변",
  "stop_reason": "answer stop reason",
  "web_search_available": false,
  "related_pages": [
    {
      "id": "page-id",
      "page_type": "page-type",
      "title": "page title",
      "role": "검색 결과에서의 역할",
      "score": 0.0,
      "summary": "page summary"
    }
  ],
  "evidence_snippets": [
    {
      "rank": 1,
      "source_document_id": "source-document-id",
      "source_block_ids": ["source-block-id"],
      "text": "evidence snippet text"
    }
  ]
}
```

현재 evaluator 반환값은 아래 형태다.

```json
{
  "route": "internal_supported",
  "evidence_relevance": 0.0,
  "citation_evidence_alignment": 0.0,
  "unsupported_refusal_accuracy": null,
  "reason": "Korean reason",
  "feedback": "Korean actionable feedback",
  "web_query": null
}
```

반환값 정규화 기준:

| 필드 | 정규화 |
| --- | --- |
| `route` | 허용 route가 아니면 `internal_supported`로 바꾼다. |
| `evidence_relevance` | 0~1 범위로 clamp하고, 없으면 0.0을 사용한다. |
| `citation_evidence_alignment` | 값이 있으면 0~1 범위로 clamp하고, 없으면 null을 사용한다. |
| `unsupported_refusal_accuracy` | 값이 있으면 0~1 범위로 clamp하고, 없으면 null을 사용한다. |
| `reason` | 없으면 빈 문자열을 사용한다. |
| `feedback` | 없으면 빈 문자열을 사용한다. |
| `web_query` | 빈 문자열이면 null로 바꾼다. |

## 8. 코드 자동화 방향

현재 구현 위치:

```text
llmPipeline/prompts/wiki_generation_evaluator.system.md
llmPipeline/prompts/query_answer_evaluator.system.md
llmPipeline/run_lab.py
llmPipeline/app/modules/query/infrastructure/query_answer_evaluator.py
llmPipeline/app/modules/query/domain/entities.py
llmPipeline/app/modules/query/application/answer_query.py
```

현재 실행 흐름:

```text
Wiki generation
  -> semantic extraction, 원문 의미 추출
  -> normalize, 추출 결과 정규화
  -> wiki_generation_evaluator prompt 호출
  -> issue 기반 guard, 코드 방어 규칙 적용
  -> repair 가능한 observation issue 자동 보정
  -> retry_feedback으로 semantic extraction, 원문 의미 추출 재시도

Query answer
  -> retrieval, 관련 근거 검색
  -> answer generation, 답변 생성
  -> query_answer_evaluator prompt 호출
  -> route/evidence/citation/refusal 평가
  -> web_query가 있으면 web search query rewrite에 사용
```

## 9. 우선순위

1. Wiki 생성에서는 source block이 원문 근거를 충실하게 보존하는지 본다.
2. Core concept가 원문 근거에 기반하고 과분할되지 않았는지 본다.
3. Relation과 evidence unit이 검색에 유용한 근거 구조인지 본다.
4. Observation 중복, 깨짐, source reference 누락 같은 재시도 가능한 문제를 우선 잡는다.
5. Query에서는 사용된 evidence가 질문과 맞는지, citation이 claim을 지지하는지, unsupported/web fallback route가 맞는지 본다.
