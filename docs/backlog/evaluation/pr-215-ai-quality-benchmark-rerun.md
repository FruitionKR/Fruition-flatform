# PR #215 인공지능 품질 벤치마크 최종 재평가 보고서

## 쉬운 용어표

| 이 보고서의 표현 | 뜻 |
| --- | --- |
| 시험 입력(fixture) | 벤치마크에 넣은 고정 문서나 질문 |
| 구조화된 표식(marker) | `FALCON-QUEUE`처럼 반드시 보존되어야 하는 식별 문자열 |
| 원문 블록(ref) | `B0001`처럼 입력 문서의 근거 위치를 가리키는 표식 |
| 답변 경로(route) | 내부 근거 답변, 근거 부족 종료, 웹 전환 중 실제로 선택된 경로 |
| 답변 근거(evidence) | 모델에게 실제로 주입한 문서·웹 정보 |
| 근거 검색(retrieval) | 후보를 찾고 방문하여 답변에 사용한 과정 |
| 인용(citation) | 답변 끝의 `[1]` 같은 근거 표시 |
| 자동 점검(guard) | 표식, 주제, 원문 블록, 경로 같은 계약을 검사하는 규칙 |
| 사람 의미 검토 | 키워드가 아니라 질문의 의미와 근거 지지를 사람이 다시 판정한 것 |
| 근거 부족(unsupported) | 답할 근거가 없어 답변하지 않는 경로이며, 항상 실패를 뜻하지는 않음 |
| 웹 전환(web fallback) | 내부 근거가 없을 때 웹 검색으로 전환하는 경로 |
| 결과 보존 재실행(capture rerun) | 답변·근거·실행 추적을 저장한 별도 재실행 |

## 목차

- [전체 결과 요약](#전체-결과-요약)
- [결론](#결론)
- [평가 공통 조건](#평가-공통-조건)
- [편입(Ingest)](#편입ingest)
- [질의(Query)](#질의query)
- [문서·폴더 관리 계획(Agent)](#문서폴더-관리-계획agent)
- [작업 자동화 Skill 라우팅·분류](#작업-자동화-skill-라우팅분류)
- [실제 Skill 적용](#실제-skill-적용)
- [실제 Skill 적용 후속 Live 재실행](#실제-skill-적용-후속-live-재실행)
- [실제 저장 Skill E2E 수정](#실제-저장-skill-e2e-수정)
- [변경 이력 복원·재실행(Log)](#변경-이력-복원재실행log)
- [품질 점검 승격(Lint)](#품질-점검-승격lint)
- [MeaningClusterJudge 18회 입력·expected·실제 판정](#meaningclusterjudge-18회-입력expected실제-판정)
- [검증된 고도화 후보](#검증된-고도화-후보)
- [최종 판단과 한계](#최종-판단과-한계)

## 전체 결과 요약

| 실험 | 실제 평가 입력 | 실제 결과 | 판정 범위 |
| --- | --- | --- | --- |
| 완료된 AI 관련 suite | PR #224 관련 AI 테스트 | **404 passed, 79 subtests passed** | 전체 관련 suite 실행 결과 |
| 직접 변경 범위 | PR #224에서 직접 변경한 경로 | **102 passed, 4 subtests passed** | 직접 변경 테스트 범위 |
| Query 전체 `tests/modules/query` | 모델 재사용·저장 벡터·조사·hybrid·facet·관계 탐색 회귀 테스트 | **141 passed, 19 subtests passed** | 최신 통합 Query 회귀 suite |
| 짧은 문서 편입 | 3개 문서 × 3회 | **9/9** | 표식 3개와 유효 원문 블록 보존 |
| 장문 문서 편입 | 1개 문서 × 3회 | **3/3** | 7개 주제명 존재와 유효 원문 블록 |
| 새 편입 문장 재실행 | 자연스러운 한국어 줄글 3개 × 3회 | 자동 평가 9/9, 원문 참조 9/9, 기계 guard 9/9, 독립 의미 판정 당시 7/9, 직접 `concept_related_slugs` 생성 0/9 관찰(핵심 의미 실패 아님) | 의미 품질과 구조 계약을 분리; description·`evidence_related_slugs`의 관계 후보와 최종 Markdown 렌더링은 별도 미캡처 |
| 질의 검색 | 실제 질문 18개, 대상 문서 묶음 6개 | MRR/Hit@1/Recall@3 측정 | 검색 평가만 해당 |
| 질의 근거 회수 | 77쪽, 답변 가능 25개, 무응답 5개, 사실 묶음 30개 | Hybrid75: 0.9000/0.8800/0.2000, Dense100: 0.9333/0.9200/0.2000 | 근거 회수 지표만 해당 |
| Query 수정 후 진단 | `index.md`·`log.md` 질문 repeat=1 및 전체 6개 | `index.md`·`log.md` **1/1**, 전체 **6/6** | 수정 후 진단; 기존 보존 실행과 별도 |
| Query 교차언어 제품 E2E | 영문 문서→한국어 질문 1건, 한국어 문서→영문 질문 1건 | 기대 page·citation **2/2** | 답변 생성만 deterministic fake; 저장·HTTP·검색·인용은 실제 경로 |
| Query 실제 hybrid·facet 회귀 | lexical+dense 2문서 fixture, distinct facet 2문서 fixture | hybrid가 dense 오순위 교정; facet 문서·citation **2/2** | 고정 fixture 결과; 운영 가중치·generator facet 누락은 미검증 |
| Agent 작업 계획 | 실제 지시 7개 × 3회 = 21회 | **21/21** | 도구·핵심 인자·승인 대기 |
| Skill 라우팅·분류 | 실제 지시 32개 × 1회 | **32/32** | 지원·범위 밖·모호성 및 작업 유형 |
| 실제 Skill 적용(기존 기록) | 3개 fixture × 3회 | 형식·라우팅·도구 계약 **9/9** | 문서 생성·편집·폴더 정리의 기존 표면 계약 기록 |
| 실제 Skill 적용 후속 Live 재실행 | A 온보딩 3회, B 폴더 계획 3회 | A strict **1/3**, route **3/3**, grounding **2/3**; B **3/3** | 현재 온보딩의 엄격한 출력·근거·폴더 계획 계약 |
| 실제 저장 Skill E2E | 동일 요청 no-Skill/stored-Skill 각 1회 | publish/readback 일치, marker 차이, 승인·`create_document`·영속 저장 통과 | 생성은 deterministic fake; repository·API·승인·저장은 실제 경로 |
| 별도 고정 템플릿 Skill | 1개 fixture × 3회 | **3/3** | 입력 근거 기반 결정 보존, 구조·라우팅·helper 계약 |
| Skill 1열 표 구조 | 유효한 1열 표와 음성 경계 | **112 passed, 2 subtests passed** | helper 구조 보존 회귀 테스트; live 생성 평가 아님 |
| Log AI guard | Log 관련 AI guard | **29/29** | 최종 guard 결과 |
| Log Backend focused | PR #224 최종 조합 HEAD `778e2ca0` | **204/204 (204 tests, failures 0, errors 0, BUILD SUCCESSFUL in 20s)** | Java 21 직접 실행 |
| Log 표시 이름 snapshot 통합 | 변경 2건+중복 삭제 ID, PostgreSQL rename+soft-delete | unique 3 ID 1회 조회·3건 저장; `Old Doc`·`Old Page` 보존 | 새 production defect 없음; 커밋된 회귀 artifact와 full HTTP는 아님 |
| Lint 승격 | production 점검 1회 + 기존 promotion page 3개 × 3회 + MeaningClusterJudge 6개 fixture × 3회 | 기존 promotion page 표면 계약 **9/9**, core selection 미시험; MeaningClusterJudge 평가 expected 기준 10/18 | 표면 계약, cluster match/target, promotion 경계를 분리 |
| Lint 기존 typed relation 탐색·embedding | pre-LIMIT 혼합 관계 조회, 승격·병합 변경 ID | whitelist 선필터 후 limit 통과; 예약·worker 회귀 포함 `wiki_ingestion` **169 passed, 1 skipped** | generic/untyped Related Concepts는 표시 전용; BGE-M3 1GiB 배포 한계는 미해결 |

## 결론

현재 결과는 표식·장문 구조 계약, Agent 계획, Skill 라우팅·분류를 충족했고, 자연스러운 줄글 편입에는 독립 의미 판정 당시 7/9(운영 설정 승인 줄글의 독립 실행 1·2회 판정 실패)가 기록됐다. 직접 `concept_related_slugs` 생성 0/9는 핵심 의미 실패가 아니며 description·`evidence_related_slugs`의 관계 후보와 최종 Markdown 미캡처를 함께 봐야 한다. 완료된 AI 관련 suite는 **404 passed, 79 subtests passed**, 직접 변경 범위는 **102 passed, 4 subtests passed**, 최신 Query 전체는 **141 passed, 19 subtests passed**다. Query는 복합 조사 1회 제거, 실제 BM25+dense 오순위 교정, distinct facet 두 근거·인용 보존을 고정 fixture에서 통과했고 교차언어 제품 E2E도 page·citation **2/2**였지만, generator의 facet 누락 감지나 운영 corpus 전체의 hybrid 가중치까지 증명하지 않는다. 실제 Skill 적용의 기존 표면 계약 9/9와 후속 live A strict 1/3·route 3/3·grounding 2/3, B 3/3은 그대로 분리한다. 추가 persisted E2E는 같은 요청에서 stored-Skill marker 차이와 실제 publish·Backend/Pipeline readback·명시적 승인·`create_document`·version/revision 1 영속 저장을 확인했지만 답변 생성은 deterministic fake였다. Log 표시 이름 snapshot 통합 검증에서는 새 production defect가 없었고 `Old Doc`·`Old Page`가 유지됐지만 저장소에 커밋된 exact regression과 full HTTP 검증은 남아 있다. Lint는 기존 typed relation 7개를 limit 전에 필터링하고 `graph_link_limit=1` mutation을 통과했으며, generic/untyped `Related Concepts`는 제품 결정에 따라 표시 전용으로 유지한다. 승격·병합 page ID는 Lint DB commit 전에 `pending`으로 예약되고 worker 시작 실패를 삼켜도 예약이 남으며, maintenance worker 기동 시 `pending/failed`를 회수해 최대 3회 재시도한다. 다만 BGE-M3의 1GiB 초과 메모리와 semantic live retrieval은 해결하거나 증명하지 않았다. 기존 promotion page 9회와 MeaningClusterJudge 18회의 계약 한계도 그대로다. 따라서 PR #215 제품 전체 통과가 아니라, 각 fixture와 실제 경로에서 확인한 범위만 통과로 판정한다.

## 평가 공통 조건

- 편입과 Lint promotion page·MeaningClusterJudge 평가는 `openai/gpt-5-nano`를 사용했고, 반복별 seed는 노출되지 않았다. Skill 실제 적용도 `gpt-5-nano`를 사용했지만 production API가 seed를 노출하지 않았다.
- Agent는 7개 지시를 3회씩, Skill 라우팅·분류는 32개 지시를 1회, 기존 실제 Skill 적용은 3개 fixture를 3회씩 실행했다. 별도 저장 Skill E2E는 동일 요청을 no-Skill/stored-Skill로 각 1회 실행했다. 각 실험에서 확인 가능한 모델·라우팅·반복 조건만 해당 실험 결과로 해석한다.
- 편입·질의·Log·Lint는 복구한 실행 도구를 현재 코드 경로에 연결해 평가했고, Lint는 production dry-run과 기존 promotion page 생성 및 MeaningClusterJudge live 평가를 별도로 실행했다.
- 실행마다 고정 난수값(seed)이 노출되지 않았다. 같은 입력에서도 답변·근거 경로·자동 판정이 달라질 수 있으므로 반복 결과는 관찰값이다.

# 편입(Ingest)

## 무엇을 시험했나

편입은 새 원문을 읽어 위키 산출물을 만드는 흐름을 시험했다. 짧은 문서는 개념을 풍부하게 추출하는 평가가 아니라, 고정된 구조화 표식 3개와 유효한 원문 블록을 보존하는 실험이다. 장문 문서는 7개 주제명이 산출물에 존재하는지 확인하는 실험이다.

## 실제 평가 입력

### 짧은 입력 3개

#### 주문 이벤트를 순서대로 처리하는 메시지 전달 시스템

```markdown
# 메시지 전달 시스템

## Falcon Queue
Falcon Queue(`FALCON-QUEUE`)는 주문 이벤트를 순서대로 받는 메시지 큐다.
각 이벤트는 처리 전에 Orchid Ledger로 전달된다.

## Orchid Ledger
Orchid Ledger(`ORCHID-LEDGER`)는 받은 이벤트 ID와 처리 상태를 영구 기록한다.
같은 이벤트 ID가 다시 들어오면 기존 기록을 반환해 중복 처리를 막는다.

## Quartz Receipt
Quartz Receipt(`QUARTZ-RECEIPT`)는 Orchid Ledger의 기록이 성공한 뒤 발급된다.
소비자는 이 receipt를 확인한 뒤에만 이벤트 처리를 완료한다.
```

기대 표식은 `FALCON-QUEUE`, `ORCHID-LEDGER`, `QUARTZ-RECEIPT`이다.

#### 운영 설정 변경 승인 정책

```markdown
# 변경 승인 정책
## Saffron Gate
Saffron Gate(`SAFFRON-GATE`)는 운영 설정 변경 요청을 승인 대기 상태로 둔다.
승인되지 않은 요청은 Indigo Permit을 받을 수 없다.
## Indigo Permit
Indigo Permit(`INDIGO-PERMIT`)은 승인자와 승인 시각을 포함하는 일회성 허가다.
허가가 사용되면 같은 값으로 설정을 다시 변경할 수 없다.
## Cobalt Audit
Cobalt Audit(`COBALT-AUDIT`)은 요청, 승인, 적용 결과를 수정 불가능한 순서로 기록한다.
Saffron Gate와 Indigo Permit의 모든 상태 전이는 이 감사 기록에 남는다.
```

기대 표식은 `SAFFRON-GATE`, `INDIGO-PERMIT`, `COBALT-AUDIT`이다.

#### 센서 측정·보정·경보 흐름

```markdown
# 센서 경보 흐름
## Nimbus Sensor
Nimbus Sensor(`NIMBUS-SENSOR`)는 10초마다 온도를 측정한다.
측정값은 보정 전 원본 값과 함께 Ember Calibrator로 전달된다.
## Ember Calibrator
Ember Calibrator(`EMBER-CALIBRATOR`)는 장비별 offset을 적용해 보정 온도를 계산한다.
보정 온도가 80도를 넘으면 Harbor Alert에 위험 신호를 보낸다.
## Harbor Alert
Harbor Alert(`HARBOR-ALERT`)는 연속 두 번의 위험 신호가 들어와야 담당자에게 알림을 보낸다.
한 번만 들어온 위험 신호는 30초 뒤 만료된다.
```

기대 표식은 `NIMBUS-SENSOR`, `EMBER-CALIBRATOR`, `HARBOR-ALERT`이다.

### 장문 입력

휴대 가능한 입력 식별 정보는 파일 이름 `agentic-architecture.md`, 1,189줄, 52,819바이트, SHA-256 `144002955367ab780ea01d6f0b7247160f93ab43e9217520ba15f75ea59849b7`, 원문 블록 181개다. 기대 주제는 `Wiki ingest`, `Wiki lint`, `Markdown Editor`, `Operation Recovery`, `Query`, `Skill Authoring`, `Artifact` 7개다.

## 기대 동작

- 짧은 입력은 각 문서의 표식 3개를 모두 보존하고, 참조한 원문 블록이 해당 실행 입력의 `B0001`~`B0007` 범위 안에 있어야 한다.
- 장문 입력은 7개 주제명이 모두 존재하고, 참조한 원문 블록이 181개 블록 안에 있어야 한다.
- 최종 평가기는 성공 상태여야 한다.

## 실제 결과

### 짧은 입력 9회

`표식`과 `원문 블록`은 각각 보존된 표식 수와 관찰된 참조 블록을 뜻한다. `개념/근거 수`는 진단용 관찰값이며 통과 기준이 아니다.

| 입력 | 회차 | 표식 | 원문 블록 | 평가기 | 개념/근거 수 | 결과 |
| --- | ---: | ---: | --- | --- | ---: | --- |
| 메시지 전달 | 1 | 3/3 | B0005, B0007 | 통과 | 1/5 | 통과 |
| 메시지 전달 | 2 | 3/3 | B0001, B0002, B0003 | 통과 | 3/4 | 통과 |
| 메시지 전달 | 3 | 3/3 | B0003 | 통과 | 3/3 | 통과 |
| 변경 승인 | 1 | 3/3 | B0001 | 통과 | 3/6 | 통과 |
| 변경 승인 | 2 | 3/3 | B0001, B0003, B0004 | 통과 | 3/5 | 통과 |
| 변경 승인 | 3 | 3/3 | B0001 | 통과 | 3/5 | 통과 |
| 센서 경보 | 1 | 3/3 | B0002–B0007 | 통과 | 1/4 | 통과 |
| 센서 경보 | 2 | 3/3 | B0002–B0007 | 통과 | 1/4 | 통과 |
| 센서 경보 | 3 | 3/3 | B0001–B0003 | 통과 | 3/4 | 통과 |

세 원문의 전문과 9회 결과는 모두 위 표와 입력 블록으로 보존했다.

### 장문 입력 3회

| 회차 | 7개 주제명 | 참조·평가기 | 개념/근거 수 | 결과 |
| ---: | --- | --- | ---: | --- |
| 1 | 7/7 모두 존재 | 181개 블록 안의 유효 참조, 통과 | 21/41 | 통과 |
| 2 | 7/7 모두 존재 | 181개 블록 안의 유효 참조, 통과 | 23/46 | 통과 |
| 3 | 7/7 모두 존재 | 181개 블록 안의 유효 참조, 통과 | 21/40 | 통과 |

## 왜 그렇게 판정했나

짧은 입력 9회와 장문 입력 3회 모두 표식·주제명, 원문 블록 범위, 최종 평가기 상태를 자동 점검해 통과했다. 장문 3회차의 평가기 재시도는 최종 통과 전에 한 번 더 확인한 것이므로 실패로 세지 않았다.

## 이 실험이 증명하지 못하는 것

짧은 입력의 개념/근거 수는 풍부한 개념 추출 품질을 증명하지 않는다. 장문 입력은 7개 주제명 존재만 확인하므로 주제별 설명의 정확성이나 완전성을 증명하지 않는다.

### 새 줄글 편입 9회

실제 평가셋은 제목·목록·표식·고유명사 없이 주문 처리 줄글 (`orders`), 운영 설정 승인 줄글 (`approvals`), 센서 경보 줄글 (`sensors`)을 각각 세 문단으로 설명한 자연스러운 한국어 문서 3개다. 평가 입력 3개 각각을 seed 미지정 상태로 서로 독립적인 호출 3회씩 실행했으며, 1·2·3회차는 처리 단계나 보정 단계가 아니다. 주문 문서의 기대 개념은 순서를 지키는 전달, 중복을 막는 기록, 완료 확인이고, 승인 문서는 승인 대기·한 번만 쓰는 허가·바꿀 수 없는 감사 기록, 센서 문서는 주기적 측정·장비별 보정·연속 위험 경보다. 각 문서에서 기대한 개념들이 원문에 맞게 추출되고, 문단 안에 드러난 순서·대기·허가·측정·보정·경보의 관계를 실제 결과가 보존하는지를 독립적으로 판정했다. 이 절에서 캡처한 출력은 정규화된 concept/evidence 후보이며 최종 승격된 Wiki Markdown 페이지가 아니다. 따라서 최종 Markdown으로 렌더링된 관계는 캡처하지 않았고, description과 `evidence_related_slugs`에 포함된 관계 후보 및 직접 `concept_related_slugs` 생성 관찰을 구분해 읽어야 한다.

1회차는 자동 평가 3/3, 원문 참조 3/3, 기계 guard 3/3, 독립 의미 개념 2/3이었다. 주문과 센서는 핵심 개념을 보존했지만 승인 결과는 허가와 감사 기록은 잡아도 승인 대기 의미가 약해 당시 독립 의미 판정에서 실패했다. 직접 `concept_related_slugs` 생성은 0/3으로 관찰됐으나 핵심 의미 실패를 뜻하지 않으며, description·`evidence_related_slugs`의 관계 후보와 최종 Markdown 관계 렌더링은 캡처하지 않았다. 2회차도 자동 평가 3/3, 원문 참조 3/3, 기계 guard 3/3, 독립 의미 개념 2/3이었다. 주문과 센서는 기대 개념을 충족했지만 승인 문서는 승인 대기와 한 번만 쓰는 허가의 구분이 불완전해 당시 독립 의미 판정에서 실패했다. 직접 `concept_related_slugs` 생성은 0/3으로 관찰됐으나 같은 한계가 적용된다.

3회차는 자동 평가 3/3, 원문 참조 3/3, 기계 guard 3/3, 독립 의미 개념 3/3이었다. 직접 `concept_related_slugs` 생성은 0/3으로 관찰됐으나 핵심 의미 실패가 아니며, description·`evidence_related_slugs`의 관계 후보와 최종 Markdown 관계 렌더링은 캡처하지 않았다. 전체는 자동 평가 9/9, 원문 참조 9/9, 기계 guard 9/9, 독립 의미 판정 당시 7/9(주문 3/3, 승인 1/3, 센서 3/3), 직접 `concept_related_slugs` 생성 0/9 관찰이다. 이 7/9는 운영 설정 승인 줄글의 독립 실행 1·2회에 대한 당시 판정만을 뜻한다. 캡처된 `concept_related_slugs` 직접 출력은 0/9였다. production semantic extraction prompt는 relation을 출력하지 말라고 하고 backend가 후처리로 링크를 조립한다. 이번 실험은 최종 승격 Wiki Markdown과 backend 후처리 링크 결과를 캡처하지 않았으므로 0/9를 관계 기능 실패로 읽을 수 없다. description과 `evidence_related_slugs`에는 관계 후보가 있었다. production prompt는 canonical workflow 하나로 개념을 묶는 것을 허용하고 과도한 분할을 피하도록 하며 gold concept 목록 일치는 제품 계약이 아니므로, 개념 수만으로 실패를 판정한 부분은 평가 한계다. 기존 표식 보존·장문 주제명 확인 실험은 별도 구조 계약으로 남기며, 이 결과와 합쳐 의미 품질 통과로 해석하지 않는다.

#### 3개 입력 × 독립 실행 3회 독자용 요약

아래 표의 후보 수와 이름은 정규화된 concept/evidence 후보를 읽기 쉽게 요약한 것이다. 이는 최종 승격된 Wiki Markdown 페이지나 그 관계 렌더링 결과가 아니다.

| 평가 입력 | 회차 | 원문에서 기대한 핵심 | 실제 생성된 concept 후보 | 놓치거나 합친 의미 | 판정과 이유 |
| --- | ---: | --- | --- | --- | --- |
| 주문 처리 줄글 (`orders`) | 1 | 순서를 지키는 전달; 중복을 막는 기록; 완료 확인 | `DeliveryQueue`; `CompletionToken`; `IdempotentRecorder` | 세 의미가 각각 별도 후보로 생성되어 놓치거나 합친 의미 없음 | 통과 — 당시 독립 의미 판정에서 세 핵심 개념과 순서·의존 관계가 원문 근거에 나타남 |
| 주문 처리 줄글 (`orders`) | 2 | 순서를 지키는 전달; 중복을 막는 기록; 완료 확인 | `Delivery Queue (order-preserving)`; `Deduplication Logging`; `Completion Acknowledgement Token` | 세 의미가 각각 별도 후보로 생성되어 놓치거나 합친 의미 없음 | 통과 — 당시 독립 의미 판정에서 세 핵심 개념과 순서·의존 관계가 원문 근거에 나타남 |
| 주문 처리 줄글 (`orders`) | 3 | 순서를 지키는 전달; 중복을 막는 기록; 완료 확인 | `Delivery Queue`; `Deduplication Log`; `Completion Token` | 세 의미가 각각 별도 후보로 생성되어 놓치거나 합친 의미 없음 | 통과 — 당시 독립 의미 판정에서 세 핵심 개념과 순서·의존 관계가 원문 근거에 나타남 |
| 운영 설정 승인 줄글 (`approvals`) | 1 | 승인 대기; 한 번만 쓰는 허가; 바꿀 수 없는 감사 기록 | `Approval workflow with one-time permit` | 승인 대기와 일회용 허가를 하나의 workflow 후보로 합쳤고, 불변 감사 기록이 독립 후보로 나오지 않음 | 실패 — 당시 독립 의미 판정에서 불변 감사 기록이 누락됨 |
| 운영 설정 승인 줄글 (`approvals`) | 2 | 승인 대기; 한 번만 쓰는 허가; 바꿀 수 없는 감사 기록 | `Change Request Approval Workflow` | 승인 대기·일회용 허가·감사 연결을 하나의 workflow 후보로 합쳤고, 불변 감사 기록이 독립 후보로 나오지 않음 | 실패 — 당시 독립 의미 판정에서 불변 감사 기록이 누락됨 |
| 운영 설정 승인 줄글 (`approvals`) | 3 | 승인 대기; 한 번만 쓰는 허가; 바꿀 수 없는 감사 기록 | `Approval Workflow`; `Single-use Permit`; `Immutable Audit Trail` | 세 의미가 각각 별도 후보로 생성되어 놓치거나 합친 의미 없음 | 통과 — 당시 독립 의미 판정에서 세 핵심 개념과 순서·의존 관계가 원문 근거에 나타남 |
| 센서 경보 줄글 (`sensors`) | 1 | 주기적 측정; 장비별 보정; 연속 위험 경보 | `Per-device calibration 적용으로 보정된 온도`; `연속 경보 규칙`; `원래 측정값의 보관` | 주기적 측정은 별도 후보가 아니라 원래 측정값 보관 근거에 포함되고, 보정·연속 경보는 별도 후보로 생성됨 | 통과 — 당시 독립 의미 판정에서 측정·보정·연속 위험 경보의 의미와 근거가 확인됨 |
| 센서 경보 줄글 (`sensors`) | 2 | 주기적 측정; 장비별 보정; 연속 위험 경보 | `Consecutive alert rule for risk signals`; `Temperature calibration with original-value retention` | 장비별 보정과 원래 값 보관을 하나의 후보로 합쳤고, 주기적 측정은 별도 후보 없이 근거에 나타남 | 통과 — 당시 독립 의미 판정에서 핵심 의미가 원문 근거에 남고, workflow-like 병합은 허용 범위임 |
| 센서 경보 줄글 (`sensors`) | 3 | 주기적 측정; 장비별 보정; 연속 위험 경보 | `Calibration-adjusted temperature`; `Consecutive-signal alert policy`; `Original value storage`; `Transient vs persistent high temperature differentiation` | 주기적 측정은 근거에 있고 별도 후보로 나뉘지 않았으며, 일시·지속 고온 구분은 추가 후보로 분리됨 | 통과 — 당시 독립 의미 판정에서 핵심 의미와 근거가 확인되고 추가 분리는 실패가 아님 |

#### 회차별 실제 출력·근거·판정

각 행은 실제 normalized concept title/description, relation, evidence excerpt/ref, evaluator score/retry, source ref validity, mechanical guard, 독립 의미 판정과 rationale을 포함한다.

##### 주문 처리 줄글 (`orders`) — 독립 실행 1회

- model: `openai/gpt-5-nano`; seed: **명시되지 않음**; artifact: `[원시 산출물]`
- 실제 concept title/description: DeliveryQueue — 주문 흐름에서 발생한 사건들을 같은 순서로 처리하기 위해 보존하는 대기 큐(전달 대기열) 개념.; CompletionToken — 완료를 확인하는 증표를 발급하고 소비자가 이를 확인한 경우에만 주문이 종료된다고 간주하는 메커니즘.; IdempotentRecorder — 동일 식별자로 중복된 작업 생성을 방지하기 위해 상태와 식별자를 기록하고 재도착 시 기존 기록을 재활용하는 메커니즘.
- 실제 relation: `{"concept_related_slugs": [[], [], []], "evidence_related_slugs": [["delivery-queue"], ["idempotent-record"], ["completion-token"], ["completion-token"], ["delivery-queue", "completion-token"]], "links": []}`
- 실제 evidence excerpt/ref: 주문이 들어오면 같은 순서로 처리하기 위해 전달 대기열에 삽입한다. [<document>:B0001]; 같은 식별자가 재도착하면 새 작업을 만들지 않고 이미 남아 있는 기록을 돌려준다. [<document>:B0002]; 처리가 성공적으로 기록되면 완료 확인 증표를 발급한다. [<document>:B0003]; 소비자는 증표를 확인한 경우에만 주문 사건을 끝난 것으로 간주한다. [<document>:B0003]; 전달 순서, 중복 방지 기록, 완료 확인은 앞뒤 관계를 이루며 어느 단계가 실패했는지도 추적할 수 있다. [<document>:B0001, <document>:B0003]
- source refs: `<document>:B0001, <document>:B0002, <document>:B0003`; validity: **True**; used blocks: `B0001, B0002, B0003`
- evaluator: status=`passed`, scores=`{"source_excerpt_fidelity": 5.0, "concept_groundedness": 5.0, "relation_faithfulness": 1.0, "evidence_relevance": 1.0, "overall": 1.0}`, retry=0
- mechanical guard: `pass`; forbidden syntax={"markdown_heading": false, "markdown_list": false, "markdown_table": false, "backtick": false, "english_proper_name": false, "all_caps_marker": false}; marker guard=`disabled; semantic gold used`
- independent semantic judgment: **pass**; rationale: 핵심 개념 3개가 각각 원문 의미에 맞는 표현과 근거에 나타났고, 개념 간 순서·의존 관계와 source evidence가 확인되며 evaluator도 통과했다.

##### 주문 처리 줄글 (`orders`) — 독립 실행 2회

- model: `openai/gpt-5-nano`; seed: **명시되지 않음**; artifact: `[원시 산출물]`
- 실제 concept title/description: Delivery Queue (order-preserving) — 처리자들이 사건을 순서대로 처리하기 위하여 사용되는 큐로, 앞선 사건이 끝나기 전에는 뒤의 사건을 넘기지 않는다.; Deduplication Logging — 받은 사건의 식별자와 처리 상태를 중복 없이 기록하여 같은 주문의 중복 반영을 방지한다.; Completion Acknowledgement Token — 처리 성공 후 발급되는 증표로, 소비자가 이를 확인한 경우에만 주문이 최종적으로 종료된 것으로 간주한다.
- 실제 relation: `{"concept_related_slugs": [[], [], []], "evidence_related_slugs": [["delivery-queue-order-preserving"], ["deduplication-logging"], ["deduplication-logging"], ["completion-ack-token"]], "links": []}`
- 실제 evidence excerpt/ref: 주문은 전달 대기열에 순서를 보존하며 처리자들이 같은 순서로 사건을 받아야 한다. [<document>:B0001]; 처리자는 받은 사건의 식별자와 현재 처리 상태를 중복 없이 기록한다. [<document>:B0002]; 같은 식별자가 다시 도착하면 새 작업을 만들지 않고 이미 남아 있는 기록을 돌려주어 한 주문이 두 번 반영되는 일을 막는다. [<document>:B0002]; 기록이 성공한 뒤에는 처리 완료를 확인하는 증표를 발급하고, 소비자는 그 증표를 확인한 경우에만 주문 사건을 끝난 것으로 간주한다. [<document>:B0003]
- source refs: `<document>:B0001, <document>:B0002, <document>:B0003`; validity: **True**; used blocks: `B0001, B0002, B0003`
- evaluator: status=`passed`, scores=`{"source_excerpt_fidelity": 5.0, "concept_groundedness": 5.0, "relation_faithfulness": 1.0, "evidence_relevance": 1.0, "overall": 1.0}`, retry=0
- mechanical guard: `pass`; forbidden syntax={"markdown_heading": false, "markdown_list": false, "markdown_table": false, "backtick": false, "english_proper_name": false, "all_caps_marker": false}; marker guard=`disabled; semantic gold used`
- independent semantic judgment: **pass**; rationale: 핵심 개념 3개가 각각 원문 의미에 맞는 표현과 근거에 나타났고, 개념 간 순서·의존 관계와 source evidence가 확인되며 evaluator도 통과했다.

##### 주문 처리 줄글 (`orders`) — 독립 실행 3회

- model: `openai/gpt-5-nano`; seed: **명시되지 않음**; artifact: `[원시 산출물]`
- 실제 concept title/description: Delivery Queue — 주문이 들어오면 여러 처리자가 같은 순서로 처리해야 하므로 순서를 보존하는 전달 대기열에 넣고, 앞선 사건이 끝나기 전에는 뒤의 사건을 넘기지 않으며 누락 여부를 확인할 수 있어야 한다.; Deduplication Log — 처리자는 받은 사건의 식별자와 현재 처리 상태를 중복 없이 기록하고, 같은 식별자가 재도착하면 새 작업을 만들지 않고 이미 남아 있는 기록을 돌려준다.; Completion Token — 기록이 성공한 뒤에는 처리 완료를 확인하는 증표를 발급하고, 소비자는 그 증표를 확인한 경우에만 주문 사건을 끝난 것으로 간주한다.
- 실제 relation: `{"concept_related_slugs": [[], [], []], "evidence_related_slugs": [["delivery-queue"], ["deduplication-log"], ["completion-token"]], "links": []}`
- 실제 evidence excerpt/ref: 전달 대기열은 주문의 순서를 보존하고 앞선 작업이 완료되기 전에는 뒤의 작업을 넘기지 않도록 한다. [<document>:B0001]; 처리자는 받은 사건의 식별자와 현재 처리 상태를 중복 없이 기록하며, 재도착 시 새 작업을 만들지 않고 기존 기록을 반환한다. [<document>:B0002]; 기록이 성공한 뒤에는 완료를 확인하는 증표가 발급되고, 소비자는 이를 확인해 주문을 완료로 간주한다. [<document>:B0003]
- source refs: `<document>:B0001, <document>:B0002, <document>:B0003`; validity: **True**; used blocks: `B0001, B0002, B0003`
- evaluator: status=`passed`, scores=`{"source_excerpt_fidelity": 5.0, "concept_groundedness": 5.0, "relation_faithfulness": 1.0, "evidence_relevance": 1.0, "overall": 1.0}`, retry=0
- mechanical guard: `pass`; forbidden syntax={"markdown_heading": false, "markdown_list": false, "markdown_table": false, "backtick": false, "english_proper_name": false, "all_caps_marker": false}; marker guard=`disabled; semantic gold used`
- independent semantic judgment: **pass**; rationale: 핵심 개념 3개가 각각 원문 의미에 맞는 표현과 근거에 나타났고, 개념 간 순서·의존 관계와 source evidence가 확인되며 evaluator도 통과했다.

##### 운영 설정 승인 줄글 (`approvals`) — 독립 실행 1회

- model: `openai/gpt-5-nano`; seed: **명시되지 않음**; artifact: `[원시 산출물]`
- 실제 concept title/description: Approval workflow with one-time permit — 요청이 즉시 적용되지 않고 승인 대기 상태로 유지되며, 한 번만 사용할 수 있는 허가가 발급되어 실제 변경이 이루어지고, 모든 상태 변화가 감사 로그로 추적되는 제어 흐름.
- 실제 relation: `{"concept_related_slugs": [[]], "evidence_related_slugs": [["approval-workflow-one-time-permit"], ["approval-workflow-one-time-permit"], ["approval-workflow-one-time-permit"], ["approval-workflow-one-time-permit"], ["approval-workflow-one-time-permit"]], "links": []}`
- 실제 evidence excerpt/ref: 요청은 승인 대기 상태로 두는 정책이 있다 [<document>:B0001]; 승인은 요청자와 승인 시각을 포함한 한 번만 쓸 수 있는 허가를 발급한다 [<document>:B0002]; 허가가 실제 변경에 사용된 뒤에는 같은 값을 다시 사용해 설정을 바꿀 수 없으므로 중복 적용이 차단된다 [<document>:B0002]; 감사 기록은 대기, 허가 발급, 허가 사용, 적용 결과를 연결한다 [<document>:B0003]; 누가 언제 무엇을 승인했는지와 같은 허가 재사용 여부를 확인할 수 있다 [<document>:B0003]
- source refs: `<document>:B0001, <document>:B0002, <document>:B0003`; validity: **True**; used blocks: `B0001, B0002, B0003`
- evaluator: status=`passed`, scores=`{"source_excerpt_fidelity": 5.0, "concept_groundedness": 5.0, "relation_faithfulness": 1.0, "evidence_relevance": 1.0, "overall": 1.0}`, retry=0
- mechanical guard: `pass`; forbidden syntax={"markdown_heading": false, "markdown_list": false, "markdown_table": false, "backtick": false, "english_proper_name": false, "all_caps_marker": false}; marker guard=`disabled; semantic gold used`
- independent semantic judgment: **fail**; rationale: 독립 의미 검토에서 누락된 항목이 있어 핵심 개념·관계·근거를 모두 충족하지 못했다: 불변 감사 기록

##### 운영 설정 승인 줄글 (`approvals`) — 독립 실행 2회

- model: `openai/gpt-5-nano`; seed: **명시되지 않음**; artifact: `[원시 산출물]`
- 실제 concept title/description: Change Request Approval Workflow — 요청이 제시되면 대기 상태로 남고, 승인이 되면 허가가 발급되며, 허가를 사용해 실제 변경이 수행되고 그 결과가 감사 로그에 기록되어 전체 흐름이 연결된다.
- 실제 relation: `{"concept_related_slugs": [[]], "evidence_related_slugs": [["change-request-approval-workflow"], ["change-request-approval-workflow"], ["change-request-approval-workflow"]], "links": []}`
- 실제 evidence excerpt/ref: 요청은 승인 대기 상태로 두고, 승인 여부와 적용 여부를 분리해 관리한다. [<document>:B0001]; 승인은 한 번만 사용되는 허가를 발급하며, 실제 변경에 사용된 뒤에는 재사용이 불가능하다. [<document>:B0002]; 감사 기록은 대기, 허가 발급, 허가 사용, 적용 결과를 연결해 누가 언제 무엇을 승인했는지 추적할 수 있다. [<document>:B0003]
- source refs: `<document>:B0001, <document>:B0002, <document>:B0003`; validity: **True**; used blocks: `B0001, B0002, B0003`
- evaluator: status=`passed`, scores=`{"source_excerpt_fidelity": 5.0, "concept_groundedness": 4.0, "relation_faithfulness": 1.0, "evidence_relevance": 1.0, "overall": 1.0}`, retry=0
- mechanical guard: `pass`; forbidden syntax={"markdown_heading": false, "markdown_list": false, "markdown_table": false, "backtick": false, "english_proper_name": false, "all_caps_marker": false}; marker guard=`disabled; semantic gold used`
- independent semantic judgment: **fail**; rationale: 독립 의미 검토에서 누락된 항목이 있어 핵심 개념·관계·근거를 모두 충족하지 못했다: 불변 감사 기록

##### 운영 설정 승인 줄글 (`approvals`) — 독립 실행 3회

- model: `openai/gpt-5-nano`; seed: **명시되지 않음**; artifact: `[원시 산출물]`
- 실제 concept title/description: Approval Workflow — 운영 설정 변경 요청이 승인 대기 → 허가 발급 → 허가 사용 → 적용 결과로 진행되는 제어 흐름.; Single-use Permit — 요청별로 발급되며 한 번만 사용할 수 있는 허가를 통해 변경 권한을 부여한다.; Immutable Audit Trail — 요청 도입 시점부터 적용 결과에 이르는 상태 변화를 불변의 감사 로그에 순서대로 기록한다.
- 실제 relation: `{"concept_related_slugs": [[], [], []], "evidence_related_slugs": [["approval-workflow", "single-use-permit"], ["single-use-permit", "approval-workflow"], ["immutable-audit-trail", "approval-workflow"]], "links": []}`
- 실제 evidence excerpt/ref: 변경 요청은 승인 대기 상태로 두고 즉시 적용하지 않는다. [<document>:B0001]; 발급되는 허가는 한 번만 사용할 수 있으며, 재사용이 차단된다. [<document>:B0002]; 감사 기록은 요청 도입 시점부터 승인 및 적용까지의 상태 변화를 순서대로 남겨 추적 가능하게 한다. [<document>:B0003]
- source refs: `<document>:B0001, <document>:B0002, <document>:B0003`; validity: **True**; used blocks: `B0001, B0002, B0003`
- evaluator: status=`passed`, scores=`{"source_excerpt_fidelity": 5.0, "concept_groundedness": 5.0, "relation_faithfulness": 1.0, "evidence_relevance": 1.0, "overall": 1.0}`, retry=0
- mechanical guard: `pass`; forbidden syntax={"markdown_heading": false, "markdown_list": false, "markdown_table": false, "backtick": false, "english_proper_name": false, "all_caps_marker": false}; marker guard=`disabled; semantic gold used`
- independent semantic judgment: **pass**; rationale: 핵심 개념 3개가 각각 원문 의미에 맞는 표현과 근거에 나타났고, 개념 간 순서·의존 관계와 source evidence가 확인되며 evaluator도 통과했다.

##### 센서 경보 줄글 (`sensors`) — 독립 실행 1회

- model: `openai/gpt-5-nano`; seed: **명시되지 않음**; artifact: `[원시 산출물]`
- 실제 concept title/description: Per-device calibration 적용으로 보정된 온도 — 원래 측정값은 장비별 보정값을 적용하는 계산 단계에 전달되어 보정된 온도가 만들어진다.; 연속 경보 규칙 — 위험 신호가 연속으로 두 번 들어온 경우에만 담당자에게 경보를 알린다.; 원래 측정값의 보관 — 측정 시의 원래 값은 보정 전 값으로 함께 보관된다.
- 실제 relation: `{"concept_related_slugs": [[], [], []], "evidence_related_slugs": [["per-device-calibration"], ["calibrated-temperature", "risk-signal"], ["consecutive-risk-alert"], ["signal-cache-expiry"], ["raw-value-storage"]], "links": []}`
- 실제 evidence excerpt/ref: 원래 측정값은 장비별 보정값을 적용하는 계산 단계로 전달되어 보정된 온도가 만들어진다. [<document>:B0001, <document>:B0002]; 보정된 온도가 위험 기준을 넘으면 위험 신호를 보내지만 한 번의 튐으로 바로 연락하지 않고 다음 측정에서도 같은 상태인지 확인한다. [<document>:B0002]; 위험 신호가 연속으로 두 번 들어온 경우에만 담당자에게 경보를 알린다. [<document>:B0003]; 한 번만 들어온 신호는 잠시 보관했다가 정해진 시간이 지나면 없애므로 일시적 측정 오류와 지속되는 고온 상태를 구분한다. [<document>:B0003]; 측정 시의 원래 값은 보정 전 값으로 함께 보관된다. [<document>:B0001]
- source refs: `<document>:B0001, <document>:B0002, <document>:B0003`; validity: **True**; used blocks: `B0001, B0002, B0003`
- evaluator: status=`passed`, scores=`{"source_excerpt_fidelity": 5.0, "concept_groundedness": 5.0, "relation_faithfulness": 1.0, "evidence_relevance": 1.0, "overall": 1.0}`, retry=0
- mechanical guard: `pass`; forbidden syntax={"markdown_heading": false, "markdown_list": false, "markdown_table": false, "backtick": false, "english_proper_name": false, "all_caps_marker": false}; marker guard=`disabled; semantic gold used`
- independent semantic judgment: **pass**; rationale: 핵심 개념 3개가 각각 원문 의미에 맞는 표현과 근거에 나타났고, 개념 간 순서·의존 관계와 source evidence가 확인되며 evaluator도 통과했다.

##### 센서 경보 줄글 (`sensors`) — 독립 실행 2회

- model: `openai/gpt-5-nano`; seed: **명시되지 않음**; artifact: `[원시 산출물]`
- 실제 concept title/description: Consecutive alert rule for risk signals — 위험 신호가 연속으로 두 번 들어온 경우에만 담당자에게 경보를 알리는 규칙.; Temperature calibration with original-value retention — 설비의 온도 측정에서 원래 값(보정 전 값)을 보관하고, 장비별 편차를 적용하여 보정된 온도를 생성하는 프로세스.
- 실제 relation: `{"concept_related_slugs": [[], []], "evidence_related_slugs": [["temperature-calibration-original-value"], ["temperature-calibration-original-value", "consecutive-alert-rule"], ["consecutive-alert-rule"]], "links": []}`
- 실제 evidence excerpt/ref: 원래 값은 보정값 적용 계산 단계로 전달된다. [<document>:B0001]; 보정된 온도가 위험 기준을 넘으면 위험 신호를 보낸다. [<document>:B0002]; 위험 신호가 연속으로 두 번 들어온 경우에만 경보를 알린다. [<document>:B0003]
- source refs: `<document>:B0001, <document>:B0002, <document>:B0003`; validity: **True**; used blocks: `B0001, B0002, B0003`
- evaluator: status=`passed`, scores=`{"source_excerpt_fidelity": 5.0, "concept_groundedness": 5.0, "relation_faithfulness": 1.0, "evidence_relevance": 1.0, "overall": 1.0}`, retry=0
- mechanical guard: `pass`; forbidden syntax={"markdown_heading": false, "markdown_list": false, "markdown_table": false, "backtick": false, "english_proper_name": false, "all_caps_marker": false}; marker guard=`disabled; semantic gold used`
- independent semantic judgment: **pass**; rationale: 핵심 개념 3개가 각각 원문 의미에 맞는 표현과 근거에 나타났고, 개념 간 순서·의존 관계와 source evidence가 확인되며 evaluator도 통과했다.

##### 센서 경보 줄글 (`sensors`) — 독립 실행 3회

- model: `openai/gpt-5-nano`; seed: **명시되지 않음**; artifact: `[원시 산출물]`
- 실제 concept title/description: Calibration-adjusted temperature — 장비별 보정값을 적용해 계산된 온도 값.; Consecutive-signal alert policy — 위험 신호가 연속으로 두 번 들어오면 담당자에게 경보를 알린다.; Original value storage — 측정 시 보정되기 전 원래 값도 함께 보관한다.; Transient vs persistent high temperature differentiation — 일시적 측정 오류와 지속되는 고온 상태를 구별하기 위해 신호 보관과 재측정을 통해 판단한다.
- 실제 relation: `{"concept_related_slugs": [[], [], [], []], "evidence_related_slugs": [["original-value-storage", "calibrated-temperature"], ["original-value-storage", "calibrated-temperature"], ["calibrated-temperature"], ["calibrated-temperature"], ["consecutive-signal-alert"], ["transient-vs-persistent-high-temperature", "consecutive-signal-alert"]], "links": []}`
- 실제 evidence excerpt/ref: 설비의 온도는 일정 간격으로 반복 측정된다. [<document>:B0001]; 원래 값은 보정값 적용 계산 단계로 전달된다. [<document>:B0001]; 계산 단계에서 편차를 더하거나 빼서 보정된 온도를 만든다. [<document>:B0002]; 보정된 값이 위험 기준을 넘으면 위험 신호를 보낸다. [<document>:B0002]; 위험 신호가 연속으로 두 번 들어온 경우에만 담당자에게 경보를 알린다. [<document>:B0003]; 한 번의 신호는 일정 시간 경과 후 삭제되어 일시적 측정 오류와 지속되는 고온 상태를 구별할 수 있다. [<document>:B0003]
- source refs: `<document>:B0001, <document>:B0002, <document>:B0003`; validity: **True**; used blocks: `B0001, B0002, B0003`
- evaluator: status=`passed`, scores=`{"source_excerpt_fidelity": 5.0, "concept_groundedness": 5.0, "relation_faithfulness": 1.0, "evidence_relevance": 1.0, "overall": 1.0}`, retry=0
- mechanical guard: `pass`; forbidden syntax={"markdown_heading": false, "markdown_list": false, "markdown_table": false, "backtick": false, "english_proper_name": false, "all_caps_marker": false}; marker guard=`disabled; semantic gold used`
- independent semantic judgment: **pass**; rationale: 핵심 개념 3개가 각각 원문 의미에 맞는 표현과 근거에 나타났고, 개념 간 순서·의존 관계와 source evidence가 확인되며 evaluator도 통과했다.

#### 회차별 판정 한계

gpt-5-nano 호출에 seed가 없으므로 표현·개념 수·evidence 수의 변동은 관찰값이다. 운영 설정 승인 줄글의 독립 실행 1·2회는 승인 대기·일회성 허가·감사 연결은 추출했지만 감사 기록의 불변성과 순서 보존을 독립 의미 검토에서 확인하지 못해 실제 의미 실패로 남겼다; 기계 guard와 evaluator만으로 이를 pass로 올리지 않았다.

Artifacts: `[원시 산출물]`, `[원시 산출물]`.
# 질의(Query)

## 무엇을 시험했나

질의는 서로 다른 세 묶음으로 분리했다.

1. **검색 평가**: 실제 질문 18개와 대상 문서 묶음 6개로 후보 검색 순서를 측정했다.
2. **근거 회수 평가**: 근거 문서 77쪽, 답변 가능 질문 25개, 답변 불가 질문 5개, 사실 묶음 30개로 정답 근거와 인용 준비 상태를 측정했다.
3. **답변 스트레스 평가**: 실제 질문 6개를 3회씩 실행해 답변의 변동성, 근거 부족 처리, 웹 전환, 의미 충족을 확인했다.

### Query 한국어 조사 검색 수정

#### 수정 전

- pre-fix `index.md`·`log.md` live index/log 결과: **0/3**
- 해당 결과 보존 실행: **13/18**
- BM25가 `index.md`·`log.md`와 조사 결합형 `index.md는`·`log.md는`을 서로 다른 토큰으로 처리해 검색 점수가 0이 되는 조사 토큰 문제
- 복합 조사 회귀 fixture에서 `문서에서는`을 `문서에서`까지만 줄였고, 기대한 정확 토큰 `문서`를 만들지 못해 exact `문서` 검색을 놓쳤다.
- 불완전 테스트 환경: **102 passed**, **5개 collection 실패**

#### 수정 후

- [PR #223](https://github.com/FruitionKR/local-pilot/pull/223)에서 한국어 조사 토큰화를 수정
- live `index.md`·`log.md`: **1/1**, 전체: **6/6**
- 복합 조사 평가셋은 `문서에서는`, 짧은 토큰 `나에서는`·`가에서는`, 그리고 exact `문서`다. 기대 동작은 긴 명사 뒤의 복합 조사를 한 번만 제거해 `문서에서는`을 `문서`로 만들고, 과도한 절단을 막기 위해 짧은 두 토큰은 그대로 두는 것이다.
- 실제 결과는 `문서에서는` → `문서`, `나에서는` → `나에서는`, `가에서는` → `가에서는`이었다. 한 토큰에서 suffix를 한 번만 제거했고 exact `문서` 검색도 맞아 **통과**했다.
- 이 fixture는 지정한 조사와 길이 경계를 검증한 회귀 테스트이며, 모든 한국어 형태소 분석이나 띄어쓰기 변형을 증명하지 않는다.
- Query 전체 `tests/modules/query`: **141 passed, 19 subtests passed**

## 실제 평가 입력

| 평가 묶음 | 입력 |
| --- | --- |
| 검색 | 질문 18개, 대상 문서 묶음 6개; BM25·임베딩·혼합·순위 결합 방식 |
| 근거 회수 | 77쪽, 답변 가능 25개, 무응답 5개, 사실 묶음 30개 |
| 스트레스 검색 | 120개 사례: 답변 가능 110개, 무응답 10개, 개발 73개, 테스트 37개 |
| 답변 스트레스 | `index.md`와 `log.md` 역할, 세 계층, 편입·질의·점검 흐름, 유지보수 역할, 근거 없는 휴가 규정, 서울 날씨의 6개 실제 질문 × 3회 |

## 기대 동작

- 검색은 정답 문서가 높은 순위에 오르는지 측정한다.
- 근거 회수는 사실 묶음을 상위 결과에서 찾고 답변에 쓸 수 있는 인용을 준비한다. 근거가 없는 질문은 억지로 답하지 않으며, 날씨 질문은 웹으로 전환한다.
- 답변은 기대 경로·인용·필수 의미를 모두 충족해야 사람 판정에서 통과한다. 자동 키워드 점검과 사람 의미 판정은 별도로 기록한다.

## 실제 결과

### Production BGE-M3 교차언어 실측

production `BgeM3EmbeddingSearch`의 기본 모델 `BAAI/bge-m3`로 서로 겹치지 않는 제품 주제 fixture 6행을 실측했다. 이는 모델 수준의 dense 검색 결과이며 full DB candidate 검색, stored embedding 경로, 답변 생성까지 포함한 Query end-to-end 결과가 아니다.

| # | 방향 | 질문 입력 | 문서 집합(정답; distractor) | 기대 정답·top-1 | matched | 최고 distractor | margin |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: |
| 1 | 영문 문서 → 한국어 질문 | 결제 중복 청구를 막기 위해 요청 키를 어떻게 사용하나요? | `en_idempotency`(중복 결제/idempotency key); `en_sensor_calibration`, `en_approval_audit` | `en_idempotency` · `en_idempotency` | 0.633651 | 0.399998 | 0.233653 |
| 2 | 영문 문서 → 한국어 질문 | 센서 원시 측정값을 보정하고 경보 임계값을 설정하는 방법은? | `en_sensor_calibration`(센서 보정/경보); `en_idempotency`, `en_approval_audit` | `en_sensor_calibration` · `en_sensor_calibration` | 0.635345 | 0.386809 | 0.248536 |
| 3 | 영문 문서 → 한국어 질문 | 승인 감사 기록에 승인자와 결정 시각을 어떻게 남기나요? | `en_approval_audit`(승인자/시각/사유); `en_idempotency`, `en_sensor_calibration` | `en_approval_audit` · `en_approval_audit` | 0.641172 | 0.409780 | 0.231392 |
| 4 | 한국어 문서 → 영문 질문 | How can I restore a document to an earlier version? | `ko_document_restore`(이전 버전 복원/현재 내용 보존); `ko_api_rate_limit`, `ko_access_review` | `ko_document_restore` · `ko_document_restore` | 0.650449 | 0.427685 | 0.222765 |
| 5 | 한국어 문서 → 영문 질문 | What should a client do after exceeding the API request limit? | `ko_api_rate_limit`(요청 한도/Retry-After); `ko_document_restore`, `ko_access_review` | `ko_api_rate_limit` · `ko_api_rate_limit` | 0.691750 | 0.451794 | 0.239956 |
| 6 | 한국어 문서 → 영문 질문 | How do we periodically check and revoke unnecessary workspace permissions? | `ko_access_review`(권한 주기 검토/회수); `ko_document_restore`, `ko_api_rate_limit` | `ko_access_review` · `ko_access_review` | 0.674396 | 0.487023 | 0.187373 |

영문 문서→한국어 질문은 top-1 **3/3**, 평균 margin **0.237860**이고 한국어 문서→영문 질문도 top-1 **3/3**, 평균 margin **0.216698**이었다. `RuleBasedQueryRewriter`는 `결제 중복 청구를 막기 위해 요청 키를 어떻게 사용하나요?`를 `결제 중복 청구 막기 위해 요청 키를 사용하나요`처럼 같은 언어의 토큰만 정제하고, `How can I restore a document to an earlier version?`를 `how can restore document earlier version`처럼 정제할 뿐 번역하지 않는다. 코드에서 환경변수가 없을 때의 fallback은 `bge-m3`지만, Compose와 Kubernetes ConfigMap의 배포 기본값은 `QUERY_EMBEDDING_MODE=text-only`이므로 배포 기본 경로는 BGE-M3가 아닌 BM25 text-only이며 이 한계를 별도로 기록한다.

### Query 교차언어 제품 경로 수정

#### 수정 전

- 앞의 6행 실측은 BGE-M3 모델 수준 dense 검색으로, DB·MinIO 저장부터 HTTP Query 응답과 citation까지 이어지는 제품 경로를 검증하지 않았다.
- 저장 벡터가 없는 후보의 fallback에서 같은 BGE-M3 weights가 두 번 load됐고, 저장 벡터 요소가 NaN·`+Inf`·`-Inf`인 경우의 fallback 경계도 회귀 테스트로 고정되지 않았다.

#### 수정 후

영문 문서→한국어 질문 1건과 한국어 문서→영문 질문 1건을 실제 제품 경로로 실행했다. 기대 조건은 각 질문이 반대 언어의 정답 page를 선택하고 해당 block citation을 반환하는 것이다. 실제 4-page 평가셋은 다음과 같다.

| page | 제목 | summary | 본문 |
| --- | --- | --- | --- |
| `doc-en` | Idempotent event processing | Duplicate delivery protection for payment events. | Every event carries a unique idempotency key. Consumers store each key and ignore duplicate deliveries, preventing a payment from being applied twice. `[B0001]` |
| `doc-ko` | 문서 복원 검증 | 삭제 문서를 안전하게 복원하기 위한 검증 절차. | 문서를 복원할 때 잠금 조회에서 대상 문서가 요청한 작업 공간에 속하는지와 삭제 상태인지 함께 검증한다. `[B0002]` |
| `doc-sensor` | Sensor calibration schedule | - | Temperature sensors are calibrated once every quarter against a reference probe. `[B0003]` |
| `doc-plant` | 사무실 식물 관리 | - | 창가의 식물에는 매주 월요일 오전에 물을 준다. `[B0004]` |

embedding build 결과는 target **4**, embedded **4**, skipped **0**, failed **0**이었다.

안전한 raw stdout은 다음과 같다.

```text
embedding_build {'target_count': 4, 'embedded_count': 4, 'skipped_count': 0, 'failed_count': 0}
en-doc-ko-query {'top_page': 'source:doc-en', 'refs': [{'source_document_id': 'doc-en', 'source_block_id': 'B0001'}], 'passed': True}
ko-doc-en-query {'top_page': 'source:doc-ko', 'refs': [{'source_document_id': 'doc-ko', 'source_block_id': 'B0002'}], 'passed': True}
11.11 real 4.57 user 1.04 sys
1228472320 maximum resident set size
```

| 방향·질문 원문 | 기대 정답 page / citation | 실제 page / citation | 결과 |
| --- | --- | --- | --- |
| 영문 문서 → 한국어 질문: `이벤트가 중복 전달되어도 결제가 두 번 처리되지 않게 하는 방법은 무엇인가?` | `source:doc-en` / `doc-en:B0001` | `source:doc-en` / `doc-en:B0001` | 통과 |
| 한국어 문서 → 영문 질문: `What must be verified under a lock before restoring a deleted document?` | `source:doc-ko` / `doc-ko:B0002` | `source:doc-ko` / `doc-ko:B0002` | 통과 |

답변 문장 생성만 결과를 고정하기 위한 deterministic fake를 사용했다. DB·MinIO·embedding 저장·HTTP 요청·retrieval·citation 조립은 실제 경로를 사용했으므로, 이 **2/2**는 반대 언어 검색 결과가 저장된 page와 block citation까지 연결되는지를 검증한다.

저장 벡터가 누락된 후보의 검색에는 query에 이미 사용한 동일 모델을 재사용해 한 요청의 weights load를 **2회에서 1회**로 줄였다. 저장된 벡터 요소가 NaN·`+Inf`·`-Inf`이면 해당 문서를 기존 fallback 경로로 처리한다. 최신 Query 전체 결과는 **141 passed, 19 subtests passed**이며 모델 재사용·비정상 벡터 fallback, 복합 조사, hybrid, distinct facet, 관계 탐색 회귀를 포함한다. 위 교차언어 제품 E2E **2/2**는 별도 실행 결과다.

#### 남은 조건

- BGE-M3 실측 최대 RSS는 **1,228,472,320 bytes(약 1,171.6MiB)**로 Kubernetes의 **1GiB** 메모리 제한을 넘었다.
- 따라서 Compose·Kubernetes의 `QUERY_EMBEDDING_MODE=text-only` 기본값은 변경하지 않았다. 배포 메모리 조건을 해결하고 실제 답변 모델까지 포함한 운영 E2E를 통과한 뒤 전환해야 한다.
- 이번 2건은 한영 양방향 제품 경로의 최소 검증이며, 모든 언어·문서·질문 조합이나 생성 답변 품질의 제품 전체 통과를 뜻하지 않는다.
- 전체 command/script는 로컬 Codex session JSONL에만 있으며 DB·MinIO credential과 test token을 포함하므로 보고서나 저장소에 복사하지 않았다. 저장소 안에는 이 실행을 그대로 재현하는 runner나 artifact가 없어, 위 fixture·안전한 stdout·실행 경계만으로 provenance를 확인해야 한다.

### Query 실제 hybrid 검색 증거 수정

#### 수정 전

최초 fixture의 평가셋은 target과 distractor 두 문서였다. 기대 동작은 BM25와 dense를 함께 쓴 결과가 dense 단독의 오순위를 바로잡는 것이었지만, 실제 production BM25 점수는 `[0, 0]`이었고 최종 점수도 target **0.64**, distractor **0.76**으로 distractor가 남았다. lexical 신호가 전혀 없고 정답도 바뀌지 않았으므로 이 실행은 hybrid 이득의 증거로는 **무효**다.

#### 수정 후

수정 fixture의 질문은 `정확한검색어가 뭐야`이고 실제 rewrite는 `정확한검색어`다. 평가셋은 `doc_target`과 dense 유사도가 더 높은 distractor 두 문서이며, 기대 동작은 target에만 있는 exact lexical token이 BM25에 반영되어 dense 오순위를 hybrid가 뒤집고 target block을 근거와 인용으로 반환하는 것이다.

실제 BM25 점수는 target/distractor `[1, 0]`, dense 점수는 target **0.80**·distractor **0.95**, hybrid 점수는 target **0.84**·distractor **0.76**이었다. 최종 선택은 `doc_target`이고 evidence와 citation은 모두 `doc_target:B0001`이어서 **통과**했다. 이 결과는 점수가 고정된 2문서 회귀 fixture에서 lexical+dense 결합이 실제로 순위를 바꾼다는 증거이며, 운영 corpus 전체의 최적 가중치나 일반적인 hybrid 우월성을 증명하지 않는다.

### Query distinct facet 근거 보존 수정

#### 수정 전

복합 질문의 distinct facet마다 별도 citable evidence를 남기는 고정 fixture가 없어, 한 facet의 근거가 선택되거나 generator가 다른 facet을 빠뜨리는 경우를 구분할 수 없었다.

#### 수정 후

평가 질문은 `설정과 장애 대응은 무엇인가?`이고 평가셋은 설정 근거 `doc-config:B0001`과 장애 대응 근거 `doc-incident:B0002`다. 기대 동작은 서로 다른 두 facet의 문서를 모두 선택하고 두 block을 모두 citation으로 남기는 것이다. 실제 결과는 두 문서가 모두 선택되고 `doc-config:B0001`, `doc-incident:B0002`가 모두 인용되어 **통과**했다.

이 fixture는 selector와 citation 조립이 두 facet의 근거를 보존함을 검증한다. assembler는 generator가 선택된 facet 하나를 답변 본문에서 누락했는지 독립적으로 판정하지 않으므로, 생성 답변의 모든 facet 서술까지 통과했다고 확대하지 않는다.

### 검색 평가

| 방식 | 평균 순위(MRR) | 1위 적중률 | 상위 3개 재현율 |
| --- | ---: | ---: | ---: |
| BM25 | 0.8056 | 0.6667 | 1.0000 |
| 저장 임베딩 | 0.9352 | 0.8889 | 1.0000 |
| 혼합 60 | 0.8333 | 0.7222 | 1.0000 |
| 순위 결합 | 0.9074 | 0.8333 | 1.0000 |

### 근거 회수 평가

| 방식 | 근거 재현율@5 | 인용 준비율@5 | 무응답 오탐률@0.45 |
| --- | ---: | ---: | ---: |
| Hybrid75 | 0.9000 | 0.8800 | 0.2000 |
| Dense100 | 0.9333 | 0.9200 | 0.2000 |

추가로 페이지 재현율은 상위 10개에서 1.0000(30/30 사실 묶음), 상위 8개에서 0.9667(29/30 사실 묶음)이었다.

### 스트레스 검색 평가

스트레스 검색은 전체 120개 사례(답변 가능 110개, 무응답 10개)를 개발 73개와 테스트 37개로 나눠 측정했다. 아래 지표는 답변 가능한 사례에서의 평균 순위, 1위 적중률, 상위 10개 재현율, 상위 5개 순위 품질이다.

| 방식 | 평균 순위 | 1위 적중률 | 상위 10개 재현율 | 상위 5개 품질 |
| --- | ---: | ---: | ---: | ---: |
| BM25 원문 | 0.7682 | 0.7000 | 0.7623 | 0.6452 |
| BM25 재작성 | 0.7518 | 0.6909 | 0.7383 | 0.6311 |
| Dense 원문 | 0.9129 | 0.8636 | 0.9047 | 0.8301 |
| Dense 재작성 | 0.8446 | 0.7727 | 0.8668 | 0.7649 |
| 혼합 60 재작성 | 0.7755 | 0.7091 | 0.8103 | 0.6732 |
| 혼합 60 원문·Dense | 0.7795 | 0.7091 | 0.8156 | 0.6877 |
| 재작성 순위 결합 | 0.7899 | 0.7091 | 0.8077 | 0.7104 |
| 원문·Dense 순위 결합 | 0.8297 | 0.7636 | 0.8267 | 0.7284 |

테스트 37개만 따로 보면 Dense 원문의 평균 순위/1위 적중률/상위 10개 재현율/상위 5개 품질은 **0.8976/0.8378/0.9099/0.8222**였고, 원문·Dense 순위 결합은 **0.8394/0.7568/0.8806/0.7475**였다. 나머지 테스트 지표는 BM25 원문 **0.7684/0.7027/0.7860/0.6477**, BM25 재작성 **0.7658/0.7027/0.7838/0.6607**, Dense 재작성 **0.8243/0.7568/0.8806/0.7361**, 혼합 60 재작성 **0.7772/0.7027/0.8378/0.6919**, 혼합 60 원문·Dense **0.7785/0.7027/0.8604/0.7098**, 재작성 순위 결합 **0.7826/0.6757/0.8491/0.7174**였다.

Dense 원문의 범주별 지표(평균 순위/1위 적중률/상위 10개 재현율/상위 5개 품질)는 정확 일치 **1.0000/1.0000/0.9722/0.9658**, 바꿔 말하기 **0.9722/0.9444/0.9074/0.8476**, 복합 질문 **0.9630/0.9444/0.8472/0.7823**, 긴 꼬리 질문 **0.7595/0.6667/0.8009/0.6605**, 잡음 혼합 **1.0000/1.0000/0.9815/0.9619**, 대조 질문 **0.6917/0.5000/0.9000/0.7393**, 다단계 질문 **0.9000/0.8000/0.9350/0.7993**였다.

무응답 10개에 대한 점수 분포는 Dense 원문이 평균 0.4387, 최솟값 0.3986, 90백분위 0.4598, 최댓값 0.4781, 임계값 0.45에서 거절률 0.6000이었다. Dense 재작성은 평균 0.4204, 최솟값 0.3512, 90백분위 0.4596, 최댓값 0.4609, 같은 임계값에서 거절률 0.8000이었다.

### 답변 스트레스 평가 집계

초기 실행과 결과 보존 실행은 같은 모델과 3회 반복을 썼지만 고정 난수값이 없어 서로 다른 관찰값이며, 유리한 답변만 골라 섞지 않았다. 아래 상세는 수정 전 결과 보존 실행 18회의 raw 답변만 기록한다.

| 질문 | 실제 주입 근거 요약 | 기대 동작 | 3회 실제 결과 | 자동 판정 | 사람 판정·이유 |
| --- | --- | --- | --- | --- | --- |
| `index.md`와 `log.md` 역할 | B0022의 카탈로그 근거와 B0023의 추가 전용 기록 근거를 합친 관찰 단위 | 내부 답변, 인용, 카탈로그와 추가 전용 기록의 두 역할 | 3회 모두 검색 중단·근거 부족 종료 | 실패 | 검색·정규화 결함으로 있는 두 근거를 활용하지 못함 |
| 세 계층 | B0013~B0015: 원자료·위키·스키마와 각 역할 | 내부 답변과 인용, 세 계층 설명 | 3회 모두 세 계층 설명 | 3/3 | **3/3** — 근거와 의미가 일치 |
| 편입·질의·점검 전체 흐름 | B0017~B0019 등: 세 단계와 인덱스·로그·교차참조 | 내부 답변과 인용, 세 단계의 순환 흐름 | 3회 모두 세 단계와 유지 흐름 설명 | 3/3 | **3/3** — 근거에 맞는 순환 흐름 설명 |
| 자동 요약기와 사람 검토자의 유지보수 역할 | B0028~B0030 등: 자동화·교차참조·사람의 큐레이션 | 내부 답변과 인용, 자동 요약기와 사람 검토자의 역할 | 1회 사람 검토 역할 누락, 2회 통과, 3회 사람 검토 역할 누락 | 1/3 | **1/3** — 2회는 의미 충족; 1·3회는 사람의 큐레이션·분석이 빠진 실제 의미 실패 |
| 사내 연차 휴가 승인 규정 | B0001: 관련 규정이 없음을 보여주는 근거 | 근거 부족으로 종료, 규정 창작 금지 | 3회 모두 근거 부족으로 종료 | 3/3 | **3/3** — 없는 사내 규정을 지어내지 않음 |
| 서울 현재 날씨 | 웹 결과 1개: 현재 상태·기온·습도·구름·바람 | 웹 전환, 실제 날씨 수치와 인용 | 3회 모두 흐림·약 27°C·습도 84% 등 답변 | 3/3 | **3/3** — 웹 근거와 경로가 일치 |

질의 스트레스 실패는 `index.md`와 `log.md` 역할 3회, 유지보수 역할 2회로 평문 집계하면 총 5회다. 자동 점검의 키워드 오탐 누락은 0회이며, 5회 모두 실제 의미 실패였다.

### 질문별 실행 상세

아래 답변은 실행 결과의 전체 답변을 그대로 보존했다. `[n]` 인용 표식과 답변 안의 인용 표식은 원문 그대로다. 근거 문장은 긴 영어 원문 대신 실제 사용된 내용을 한국어로 짧게 요약하고, 원문 블록 번호만 남겼다.

#### 수정 후 live 출력 — 한국어 조사 토큰화 수정(PR #223)

수정 후 live 출력은 아래 raw evidence로 보존한다.

`index.md`와 `log.md` 질문의 실제 답변은 다음과 같다.

```text
index.md는 페이지 목록과 한 줄 요약, 메타데이터를 포함한 카탈로그이다. [1]

또한 index.md는 위키의 카탈로그 역할을 하며 페이지를 카테고리별로 정리하고 매_ingest 시 업데이트된다. [2]

log.md는 시간 순으로 발생 내역을 append-only로 기록하며 ingests, queries, lint 등 이벤트를 추적한다. [3]

이 두 파일은 LLM 중심의 지속적 업데이트가 가능한 위키 운영 구조에서 핵심 도구로 작동한다. [4]
```

이 답변의 evidence는 `B0022 index catalog`, `B0022 category/update`, `B0023 log append-only`, `B0022+B0023+B0028 종합`이며 `stop_reason=relative_score_floor`였다.

#### 수정 전 보존 실행 raw 답변 18회

##### `index.md`와 `log.md`는 각각 어떤 역할이야?

**기대 동작**: 내부 근거 답변, 인용, 카탈로그와 추가 전용 기록의 두 의미.

**실제 사용 근거**: Ingest(원문을 위키로 편입하는 단계)와 저장에서는 B0022가 `index.md` 근거, B0023이 `log.md` 근거로 들어갔고, 두 근거를 합친 관찰 단위를 만들었다. 별도 단계 추적에서는 B0022와 B0023을 선택했다. 결과 보존 재실행의 최종 answer JSON에는 B0022만 남아 있어 최종 JSON만으로는 이 중간 선택을 확인할 수 없다.

실패 원인은 근거가 없어서가 아니다. Query(질의)의 페이지 BM25 검색에서 질의 토큰 `index.md`·`log.md`와 문서 토큰 `index.md` · `log.md`가 한국어 조사의 영향으로 맞지 않아 페이지 점수가 0이 됐고, `no_relevant_seed`(관련 시작 문서 없음)와 낮은 관련성으로 탐색이 중단됐다. 이후 평가 정책이 답변을 unsupported(근거 부족)로 덮어써 있는 두 근거를 활용하지 못했다.

**1회 실행 추적**: 답변 경로 근거 부족, 종료 사유 평가기의 근거 부족 종료, 인용 표식 `[1]`, 웹 요청·실행 `아니오/아니오`, 결과 수 0, 주입 근거 1개, 검색 후보 원자료/개념 6/6, 방문·반환 6/6, 사용 원자료/개념 6/0, 최대 깊이 0.

```text
제공된 근거에서 질문에 직접 답할 내용을 찾지 못했습니다. 가장 가까운 근거도 질문 주제를 직접 설명하지 않습니다. [1]
```

자동 판정은 실패했고, 사람 판정도 실패했다. 실제 답변은 거절문일 뿐이며 질문의 두 역할을 모두 빠뜨렸으므로 키워드 표현만 놓친 경우가 아니다.

**2회 실행 추적**: 1회와 같은 답변, 경로, 종료 사유, 인용 표식, 웹 실행, 근거 수, 검색 수치였다.

```text
제공된 근거에서 질문에 직접 답할 내용을 찾지 못했습니다. 가장 가까운 근거도 질문 주제를 직접 설명하지 않습니다. [1]
```

자동 판정과 사람 판정은 모두 실패다. 0/3은 근거 부재가 아니라 검색·정규화 결함 때문에 있는 B0022·B0023 근거를 활용하지 못한 결과다.

**3회 실행 추적**: 1·2회와 같은 답변, 경로, 종료 사유, 인용 표식, 웹 실행, 근거 수, 검색 수치였다.

```text
제공된 근거에서 질문에 직접 답할 내용을 찾지 못했습니다. 가장 가까운 근거도 질문 주제를 직접 설명하지 않습니다. [1]
```

자동 판정과 사람 판정은 모두 실패다. 세 회차 모두 같은 필수 의미가 누락됐다.

##### 이 Wiki 시스템의 세 계층을 알려줘.

**기대 동작**: 내부 근거 답변, 인용, 원자료·위키·스키마 세 계층.

**실제 사용 근거**: 1회는 B0013~B0015의 세 계층 요약을 사용했고, 2·3회는 같은 블록과 각 계층의 역할 설명을 추가로 사용했다.

**1회 실행 추적**: 답변 경로 내부 지원, 종료 사유 탐색 종료, 인용 표식 `[1]`, 웹 요청·실행 `아니오/아니오`, 결과 수 0, 주입 근거 1개, 검색 후보·방문 6/6, 사용 원자료/개념 2/4, 최대 깊이 0.

```text
이 Wiki 시스템의 세 계층은 Raw sources, the wiki, the schema로 구성된다. [1]
```

자동·사람 판정 모두 통과다. 세 계층이 명시되고 인용과 내부 경로가 근거와 일치한다.

**2회 실행 추적**: 경로 내부 지원, 종료 사유 탐색 종료, 인용 표식 `[1][2][3][4]`, 웹 미실행, 주입 근거 4개, 검색 후보·방문 6/6, 사용 원자료/개념 2/4, 최대 깊이 0.

```text
세 계층은 원자료(Raw sources), 위키, 그리고 스키마이다. [1]

원자료는 불변의 원천으로 간주되며, LLM은 이를 읽기만 하고 수정하지 않는다. [2]

위키는 LLM이 생성한 마크다운 파일의 디렉토리로서 요약, 엔티티 페이지, 콘셉트 페이지 등을 포함하며 상호참조를 유지한다. [3]

스키마는 위키의 구조와 규칙을 정의하는 문서로, Ingest, Query, Lint 같은 워크플로를 안내한다. [4]
```

자동·사람 판정 모두 통과다. 세 계층의 이름과 역할이 주입 근거에 맞는다.

**3회 실행 추적**: 2회와 같은 경로·종료 사유·인용 표식·검색 수치였다.

```text
이 Wiki 시스템의 세 계층은 Raw sources, The wiki, The schema로 구성된다. [1]

Raw sources는 원자료의 모음으로 불변이며, LLM은 이를 읽고 수정하지 않는다. [2]

The wiki는 LLM이 생성하고 관리하는 레이어로, 요약·엔티티 페이지·주제 요약 등을 포함해 새 소스 수신 시 페이지를 생성·갱신하고 교차참조를 유지한다. [3]

The schema는 위키의 구조와 규칙을 담은 구성 파일로, 인제스트(Ingest), 쿼리(Query), 린트(Lint) 같은 워크플로우를 안내한다. [4]
```

자동·사람 판정 모두 통과다.

##### 지식을 편입하고 답변하고 최신 상태로 유지하는 전체 흐름을 설명해줘.

**기대 동작**: 내부 근거 답변, 인용, 편입·질의·점검 세 단계.

**실제 사용 근거**: 세 회차 모두 B0017~B0019를 중심으로 세 단계의 흐름을 사용했다. 1·2회는 13개, 3회는 10개의 근거를 사용했으며, B0013~B0015와 B0022~B0023 등으로 계층·인덱스·로그 역할도 보강했다.

**1회 실행 추적**: 경로 내부 지원, 종료 사유 관련 점수 하한, 인용 표식 `[1],[2],[3],[4],[3],[4],[5],[5],[6],[7],[8],[9],[10],[11],[12],[13]`, 웹 미실행, 주입 근거 13개, 검색 후보 6/6, 방문·반환 5/5, 사용 원자료/개념 2/3, 최대 깊이 1.

```text
- 지식을 편입하고 최신 상태로 유지하는 흐름은 Ingest → Query → Lint의 순환 구조로 시작됩니다 [1].
- 위키는 원자료, 위키, 스키마의 3계층으로 구성됩니다 [2].
- Ingest 단계에서 새 소스를 원자료 수집에 투입하고 LLM이 처리하도록 지시합니다 [3].
- LLM은 소스를 읽고 핵심 정보를 위키에 통합하며 엔티티 페이지와 주제 요약을 갱신하고 필요 시 모순을 확인합니다 [4].
- Ingest는 하나의 소스가 여러 위키 페이지에 영향을 줄 수 있으며 10-15 페이지를 갱신하는 경우가 있습니다 [3].
- 새 데이터가 기존 주장과 충돌하는지 확인하고 누적형 구조로 저장합니다 [4].
- Query 단계에서 LLM은 위키에서 관련 페이지를 찾아 읽고 인용과 함께 답을 합성합니다 [5].
- 생성된 답은 마크다운 페이지, 비교 표, 슬라이드 등 형태로 위키에 다시 저장될 수 있습니다 [5].
- 위키의 건강을 유지하기 위해 Lint를 주기적으로 수행합니다 [6].
- 발생한 사건은 log.md에 시간 순으로 기록됩니다 [7].
- index.md는 모든 페이지를 한 줄 요약과 메타데이터로 목록화하고 매 입력마다 업데이트됩니다 [8].
- Ingest 흐름은 위키 간의 교차참조를 최신 상태로 유지하도록 설계되어 있습니다 [9].
- 위키의 핵심은 원자료를 읽고 핵심 정보를 추출해 위키에 통합하며, 새 소스가 들어올 때마다 관계를 갱신하는 누적형 구조입니다 [10].
- 위키의 운영 원리와 3계층은 다양한 맥락에서 응용 가능성을 보여줍니다 [11].
- 도구 측면에서 qmd 같은 로컬 검색 엔진과 Obsidian 같은 생산성 도구를 활용해 검색과 관리 부담을 낮춥니다 [12][13].
```

자동·사람 판정 모두 통과다. 세 단계와 계층·인덱스·로그의 관계가 주입 근거와 맞는다.

**2회 실행 추적**: 경로 내부 지원, 종료 사유 관련 점수 하한, 인용 표식 `[1],[2],[3],[3],[4],[5],[6],[6],[6],[7],[8],[9],[10],[11],[12],[13],[4]`, 웹 미실행, 주입 근거 13개, 검색 후보 6/6, 방문·반환 5/5, 사용 원자료/개념 2/3, 최대 깊이 1.

```text
- 주된 운영 흐름은 Ingest, Query, Lint로 구성된다. [1]
- Ingest 단계에서 소스를 원자료로 투입하고 요약/링크를 갱신한다. [2]
- LLM은 소스를 읽고 핵심 정보를 추출해 위키에 통합하며 기존 주장과의 관계를 갱신한다. [3]
- 새 소스가 기존 주장과 충돌하는지 확인하고 업데이트한다. [3]
- 위키의 세 가지 계층은 Raw sources, 위키, 스키마로 구성된다. [4]
- 위키 운영의 핵심은 지속적이고 누적되는 구조이며, Ingest/Query/Lint 흐름을 통해 이를 유지한다. [5]
- Query 단계에서 질문하면 LLM이 관련 페이지를 찾아 읽고 인용과 함께 답을 합성한다. [6]
- 생성된 답변은 필요 시 마크다운 페이지나 표, 슬라이드 등 다양한 형식으로 표현될 수 있다. [6]
- 좋은 답은 위키에 새 페이지로 기록될 수 있다. [6]
- Lint 단계에서 LLM이 위키를 건강 검진하고 모순, 구식, 고립 페이지 등을 점검한다. [7]
- 로그(log.md)는 시간 순으로 사건을 기록한다. [8]
- index.md는 모든 페이지를 목록화하고 매 입력마다 업데이트된다. [9]
- 로컬 도구나 자동화로 생산성을 높일 수 있다. 예: qmd 같은 로컬 검색 엔진을 활용하고 Obsidian, Dataview, Marp 같은 도구가 보조한다. [10]
- LLM은 다수의 파일을 한 번에 다뤄 비용을 낮춘다. [11]
- Ingest 흐름의 예시를 보면 소스를 하나씩 투입하고 요약/링크를 갱신하며 엔티티 페이지를 업데이트하고 로그에 남긴다. 한 소스는 10-15 wiki 페이지에 영향을 준다. [12]
- 다양한 활용 맥락으로 개인 목표, 연구, 독서, 비즈니스 등으로 확장 가능하다. [13]
- 세 가지 계층과 운영 흐름은 Raw sources, the wiki, the schema의 상호작용으로 작동한다. [4]
```

자동·사람 판정 모두 통과다.

**3회 실행 추적**: 경로 내부 지원, 종료 사유 관련 점수 하한, 인용 표식 `[1],[2],[3],[3],[3],[4],[5],[6],[2],[7],[8],[4],[9],[10]`, 웹 미실행, 주입 근거 10개, 검색 후보 6/6, 방문·반환 5/5, 사용 원자료/개념 2/3, 최대 깊이 1.

```text
지식 위키는 원자료를 읽고 핵심 정보를 추출해 위키에 통합하며, 새 소스가 들어올 때 기존 내용과의 관계를 갱신하는 누적형 구조다. [1]

운영 흐름은 Ingest, Query, Lint의 3단계로 구성되어 지식을 지속적으로 축적하고 건강을 유지한다. [2]

Ingest 단계에서 새 소스를 원자료 수집에 넣고 LLM에 처리 지시를 내려, LLM이 소스를 읽고 요약 페이지를 작성하며 인덱스를 갱신하고 관련 엔티티나 개념 페이지를 업데이트하고 로그에 항목을 남긴다. [3]

하나의 소스가 최대 10-15개 위키 페이지에 영향을 미친다. [3]

Ingest는 한 개씩 수동으로 진행하거나 필요에 따라 다수 소스를 묶어 배치 인제스트하는 방식으로 운영될 수 있다. [3]

Query 단계에서 LLM은 위키에서 관련 페이지를 찾아 읽고 인용과 함께 답을 합성하며, 필요하면 그 결과를 새로운 페이지로 위키에 저장한다. [4]

Lint 단계는 위키 건강을 점검하고 모순, 누락, 불충분한 교차참조 등을 발견해 개선 방향을 제시한다. [5]

위키는 Raw sources, 위키, 스키마의 3계층 구조이며 이들 간의 상호작용은 Ingest, Query, Lint 흐름으로 촉진된다. [6][2]

index.md는 모든 페이지를 목록화하고 한 줄 요약과 메타데이터를 제공하며 매 입력마다 업데이트된다. [7]

log.md는 발생한 사건을 시간 순으로 기록하는 append-only 로그로, 마지막 항목을 쉽게 추출할 수 있도록 일정 형식을 따른다. [8]

답변 형식은 상황에 따라 마크다운, 비교 표, 슬라이드, 차트 등으로 제시되며, 그 결과물은 필요 시 새로운 위키 페이지로 남겨 지속적으로 축적된다. [4]

또한 LLM 기반 자동화가 저장된 페이지 간의 교차참조를 항상 최신 상태로 유지하는 핵심 원리이다. [9]

위키 운영의 핵심 목표는 지속적이고 누적되는 지식 위키를 구축하는 것이다. [10]
```

자동·사람 판정 모두 통과다.

##### Wiki 유지보수에서 LLM과 사람은 각각 무슨 역할을 해?

**기대 동작**: 내부 근거 답변, 인용, 교차참조 유지·사람·큐레이션 또는 분석.

**실제 사용 근거**: 1회는 B0022·B0023·B0028 등 7개 근거, 2회는 5개, 3회는 6개를 사용했다. 모두 LLM 자동화와 교차참조를 설명했지만 사람의 큐레이션·분석 내용은 2회에만 주입됐다.

**1회 실행 추적**: 경로 내부 지원, 종료 사유 관련 점수 하한, 인용 표식 `[1],[2],[3],[4],[5],[6],[7]`, 웹 미실행, 주입 근거 7개, 검색 후보 6/6, 방문·반환 4/4, 사용 원자료/개념 1/3, 최대 깊이 0.

```text
- LLM은 위키의 지속적 업데이트를 주도한다. [1]

- LLM은 자동화를 통해 저장된 페이지 간의 교차참조를 항상 최신 상태로 유지하는 핵심 원리이다. [2]

- 운영 흐름은 Ingest, Query, Lint로 구성된다. [3]

- index.md는 카탈로그 형식으로 모든 페이지를 목록화하고, 한 줄 요약과 메타데이터를 제공하며 매 입력마다 업데이트된다. [4]

- log.md는 시간 순으로 발생 내역을 기록하는 append-only 로그이며, 일정 형식(prefix)을 사용하면 마지막 항목을 추출하기 쉽다. [5]

- 위키는 Raw sources, the wiki, the schema의 세 가지 계층으로 구성된다. [6]

- LLM은 다수의 파일을 한 번에 다뤄 유지 비용을 낮춘다. [7]
```

자동·사람 판정 모두 실패다. LLM 쪽 설명은 근거가 있지만 사람의 큐레이션·분석 역할이 빠졌다.

**2회 실행 추적**: 경로 내부 지원, 종료 사유 관련 점수 하한, 인용 표식 `[1],[2],[3],[4],[5]`, 웹 미실행, 주입 근거 5개, 검색 후보 6/6, 방문·반환 4/4, 사용 원자료/개념 1/3, 최대 깊이 0.

```text
LLM은 위키 유지보수의 자동화를 담당하고, 저장된 페이지 간의 교차참조를 항상 최신 상태로 유지한다. [1]

LLM 중심의 지속적 업데이트 구조에서 index.md와 log.md를 핵심 도구로 삼아 페이지 탐색과 변경 이력을 효과적으로 관리한다. [2]

사람은 큐레이션을 담당하고 LLM의 자동화와 협업한다. [3]

운영 흐름은 Ingest, Query, Lint로 구성되며, 원자료-위키-스키마의 다층 구조에서 서로 상호작용한다. [4][5]
```

자동·사람 판정 모두 통과다. LLM의 자동화·교차참조와 사람의 큐레이션이 모두 명시됐다.

**3회 실행 추적**: 경로 내부 지원, 종료 사유 관련 점수 하한, 인용 표식 `[1],[1],[2],[3],[4],[5],[6]`, 웹 미실행, 주입 근거 6개, 검색 후보 6/6, 방문·반환 4/4, 사용 원자료/개념 1/3, 최대 깊이 0.

```text
LLM은 위키 유지보수의 핵심으로 자동화된 업데이트를 수행하며, 소스 읽기와 핵심 정보를 추출해 위키를 지속적으로 통합하고 업데이트한다. [1]

이를 통해 저장된 페이지 간의 교차참조를 항상 최신 상태로 유지하는 것이 핵심 원리다. [1]

운영 흐름은 Ingest, Query, Lint로 구성된다. [2]

다수의 파일을 한 번에 다뤄 유지 비용을 낮추는 것도 LLM의 특징이다. [3]

주요 도구로 index.md와 log.md를 사용해 페이지 탐색과 변경 이력을 효과적으로 관리한다. [4]

index.md는 카탈로그 형식으로 모든 페이지를 목록화하고, 한 줄 요약과 메타데이터를 제공하며 매 입력마다 업데이트된다. [5]

log.md는 발생한 사건을 시간 순으로 기록하는 append-only 로그이다. [6]
```

자동·사람 판정 모두 실패다. 사람의 큐레이션·분석을 설명하지 않았으므로 실제 의미 실패다.

##### 우리 회사의 연차 휴가 승인 규정을 알려줘.

**기대 동작**: 근거 부족으로 종료하고 사내 규정을 창작하지 않음.

**실제 사용 근거**: 세 회차 모두 B0001 하나를 사용했으며, 사내 휴가 승인 규정은 포함하지 않았다.

**1회 실행 추적**: 경로 근거 부족, 종료 사유 평가기의 근거 부족 종료, 인용 표식 `[1]`, 웹 미실행, 주입 근거 1개, 검색 후보·방문 6/6, 사용 원자료/개념 6/0, 최대 깊이 0.

```text
제공된 근거에서 질문에 직접 답할 내용을 찾지 못했습니다. 가장 가까운 근거도 질문 주제를 직접 설명하지 않습니다. [1]
```

자동·사람 판정 모두 통과다. 없는 규정을 지어내지 않았다.

**2회 실행 추적**: 1회와 같은 경로, 종료 사유, 인용 표식, 웹 실행, 근거 수, 검색 수치였다.

```text
제공된 근거에서 질문에 직접 답할 내용을 찾지 못했습니다. 가장 가까운 근거도 질문 주제를 직접 설명하지 않습니다. [1]
```

자동·사람 판정 모두 통과다.

**3회 실행 추적**: 1·2회와 같은 경로, 종료 사유, 인용 표식, 웹 실행, 근거 수, 검색 수치였다.

```text
제공된 근거에서 질문에 직접 답할 내용을 찾지 못했습니다. 가장 가까운 근거도 질문 주제를 직접 설명하지 않습니다. [1]
```

자동·사람 판정 모두 통과다.

##### 서울의 현재 날씨를 알려줘.

**기대 동작**: 내부 근거 대신 웹으로 전환하고, 실제 웹 결과의 현재 상태·기온·습도 등을 인용한다.

**실제 사용 근거**: 세 회차 모두 웹 결과 1개를 사용했고, 결과에는 흐림, 약 27°C, 습도 84%, 구름량 80%, 풍속 약 2km/h가 포함됐다.

**1회 실행 추적**: 경로 웹 전환, 종료 사유 웹 검색 전환, 인용 표식 `[1],[1]`, 웹 요청·실행 `예/예`, 결과 5개, 주입 근거 1개, 웹 전환 후 방문·반환 5/5, 최대 깊이 0.

```text
서울의 현재 날씨는 흐림이며 기온은 약 27°C입니다. [1]
습도는 84%, 구름량은 80%, 바람은 시속 2km로 나타납니다. [1]
```

자동·사람 판정 모두 통과다. 웹 경로와 답변 수치가 실제 웹 근거와 일치한다.

**2회 실행 추적**: 경로 웹 전환, 종료 사유 웹 검색 전환, 인용 표식 `[1]`, 웹 요청·실행 `예/예`, 결과 5개, 주입 근거 1개, 웹 전환 후 방문·반환 5/5, 최대 깊이 0.

```text
서울의 현재 날씨는 흐림이며 기온은 약 27°C이고 습도는 약 84%, 구름량은 80%, 풍속은 2 km/h입니다. [1]
```

자동·사람 판정 모두 통과다.

**3회 실행 추적**: 2회와 같은 경로, 종료 사유, 웹 실행, 결과 수, 근거 수, 방문·반환 수였다.

```text
서울의 현재 날씨는 흐림이며 기온은 27°C, 습도는 84%입니다. [1]
```

자동·사람 판정 모두 통과다.

## 왜 그렇게 판정했나

검색 지표와 근거 회수 지표는 각각 검색 순위와 상위 근거의 품질만 측정한다. 18회 답변은 답변 경로·인용·주입 근거 지지 여부·필수 의미를 자동 점검한 뒤 사람이 의미를 다시 읽었다. 18회 모두 빈 답변은 아니었고, 사람 판정은 통과 13회·실패 5회였다. 실패 5회는 모두 실제 의미 누락이며 자동 키워드 점검의 단순 오탐이 아니다. 수정 fixture는 복합 조사 제거 결과, BM25·dense·hybrid의 실제 점수와 최종 target 근거, distinct facet별 선택·citation을 직접 비교해 각각 판정했다.

## 이 실험이 증명하지 못하는 것

검색·근거 지표가 높아도 답변이 질문의 모든 의미를 설명한다는 보장은 없으며, 모델의 일반적인 질의 품질이나 모든 문서·질문에 대한 성능을 증명하지 않는다. 실제 hybrid와 distinct facet은 고정된 소규모 fixture이고, assembler는 generator의 facet 누락을 독립 판정하지 않는다. 날씨 결과는 해당 실행 시점의 웹 응답만 보여준다.

# 문서·폴더 관리 계획(Agent)

## 무엇을 시험했나

Workspace 문서·폴더 관리 지시 7개를 3회씩 실행해 한 번에 하나의 작업을 계획하는지, 대상과 핵심 인자를 보존하는지, 실행 전 승인 대기 상태를 남기는지 확인했다. 도구 이름은 시스템 API 이름을 괄호로 병기했다.

## 실제 평가 입력

아래 7개 지시를 각각 3회 실행했다.

## 기대 동작

각 지시에는 기대 작업 하나, 대상, 이름·폴더·문서·내용 범위 같은 핵심 인자가 있어야 한다. 실제 계획은 그 작업 하나만 포함하고 상태는 승인 대기여야 한다.

## 실제 결과

| 실제 지시 | 기대 작업·핵심 인자 | 실제 도구·상태 | 결과 이유 |
| --- | --- | --- | --- |
| 최상위에 '완료' 폴더를 만들어줘. | 폴더 생성(`create_folder`); 이름 `완료`, 최상위 | 폴더 생성 1건; 승인 대기; 3회 모두 동일 | 도구와 이름·위치가 일치 |
| '진행 중' 폴더 이름을 '작업 중'으로 바꿔줘. | 폴더 이름 변경(`rename_folder`); 대상 `진행 중`, 새 이름 `작업 중` | 폴더 이름 변경 1건; 승인 대기; 3회 모두 동일 | 대상·새 이름·기준 버전이 보존됨 |
| '진행 중' 폴더를 '보관' 폴더 안으로 옮겨줘. | 폴더 이동(`move_folder`); 대상 `진행 중`, 도착 `보관` | 폴더 이동 1건; 승인 대기; 3회 모두 동일 | 대상·도착 위치가 일치 |
| '회의록.md' 문서를 '보관' 폴더로 옮겨줘. | 문서 이동(`move_document`); 대상 `회의록.md`, 도착 `보관` | 문서 이동 1건; 승인 대기; 3회 모두 동일 | 대상·도착 위치·기준 버전이 보존됨 |
| '회의록.md' 이름을 '주간 회의록.md'로 바꿔줘. | 문서 이름 변경(`rename_document`); 대상·새 이름 | 문서 이름 변경 1건; 승인 대기; 3회 모두 동일 | 대상·새 이름이 일치 |
| 준비된 문서 초안을 '새 안내.md'로 최상위에 저장해줘. | 문서 생성(`create_document`); 이름 `새 안내.md`, 최상위, 준비된 내용 산출물 | 문서 생성 1건; 승인 대기; 3회 모두 동일 | 내용 산출물과 대상 위치를 보존함 |
| 준비된 편집안을 '배포 안내.md' 전체에 적용해줘. | 문서 전체 편집(`apply_document_edit`); 대상 `배포 안내.md`, 1~12행, 준비된 편집안 | 전체 편집 1건; 승인 대기; 3회 모두 동일 | 대상·전체 범위·편집 산출물이 일치 |

총 **21/21**이 통과했다.

## 왜 그렇게 판정했나

자동 점검은 실제 작업 목록이 기대 도구와 같은지, 단일 작업일 때 핵심 인자가 같은지 확인했다. 21회 모두 작업 수 1, 기대 도구·인자 일치, 승인 대기 상태였고, 사람 의미 검토도 요청한 단일 문서·폴더 작업을 정확히 나타낸 것으로 판정했다.

## 이 실험이 증명하지 못하는 것

계획 생성만 평가했으므로 실제 저장·이동·이름 변경의 성공, 권한 거부, 동시 수정 충돌, 내용의 최종 품질은 증명하지 않는다.

# 작업 자동화 Skill 라우팅·분류

## 무엇을 시험했나

문서 작성·편집·폴더 정리·양식 작업 24개와 범위 밖·모호한 경계 작업 8개, 총 32개 지시를 분류했다. 원시 JSON과 허용 도구 배열은 반복하지 않고, 실제 지시·기대 분류·실제 분류·판정 이유만 남겼다.

## 실제 평가 입력

실제 입력은 아래 32개 문장이다. 각 문장은 한 번씩 실행했다.

## 기대 동작

지원 작업은 문서 작성, 문서 편집, 폴더 정리, 양식 중 올바른 작업 유형으로 분류해야 한다. 캘린더·이메일·셸·웹·외부 메신저 작업은 범위 밖으로 분류해야 하며, 효과가 모호한 요청은 모호성으로 남기거나 계약에서 허용한 지원 유형만 선택해야 한다.

## 실제 결과

### 지원 작업 24개

| 실제 지시 | 기대 분류 | 실제 분류 | 판정 이유 |
| --- | --- | --- | --- |
| 제품 이름과 핵심 기능을 입력받아 소개 문서를 새로 작성하는 규칙을 저장해줘. | 지원·문서 작성 | 지원·문서 작성 | 새 문서 작성 의도와 일치 |
| 고객 인터뷰 메모를 바탕으로 요약 보고서를 매번 새 문서로 만드는 자동 작업이 필요해. | 지원·문서 작성 | 지원·문서 작성 | 새 문서 작성 의도와 일치 |
| 키워드를 주면 초보자용 FAQ Markdown을 생성하도록 설정해줘. | 지원·문서 작성 | 지원·문서 작성 | 새 문서 작성 의도와 일치 |
| 장애 정보를 입력하면 사후 분석 보고서를 새로 작성하는 반복 작업을 만들고 싶어. | 지원·문서 작성 | 지원·문서 작성 | 새 문서 작성 의도와 일치 |
| 프로젝트 목표를 입력하면 온보딩 안내서를 생성하는 명령을 만들어줘. | 지원·문서 작성 | 지원·문서 작성 | 새 문서 작성 의도와 일치 |
| 행사 정보를 받아 공지문 초안을 새 파일로 만드는 방식을 저장해줘. | 지원·문서 작성 | 지원·문서 작성 | 새 문서 작성 의도와 일치 |
| 현재 문서를 영어로 번역하는 작업을 반복해서 사용할 수 있게 해줘. | 지원·문서 편집 | 지원·문서 편집 | 기존 문서 편집 의도와 일치 |
| 선택한 문단을 핵심 bullet 목록으로 바꾸는 규칙을 만들어줘. | 지원·문서 편집 | 지원·문서 편집 | 기존 문서 편집 의도와 일치 |
| 기존 회의록의 말투를 공식적인 보고서 문체로 바꾸는 작업을 저장해줘. | 지원·문서 편집 | 지원·문서 편집 | 기존 문서 편집 의도와 일치 |
| 열어 둔 문서에서 반복되는 설명을 없애고 짧게 다듬도록 해줘. | 지원·문서 편집 | 지원·문서 편집 | 중복 제거·편집 의도와 일치 |
| 현재 표의 값은 유지하면서 주변 설명을 쉽게 고치는 규칙이 필요해. | 지원·문서 편집 | 지원·문서 편집 | 표 보존 편집 의도와 일치 |
| 기존 문서 내용을 바꾸지 않고 제목 체계만 다시 구성하는 작업을 만들어줘. | 지원·문서 편집 | 지원·문서 편집 | 제목 구조 편집 의도와 일치 |
| 완료된 문서를 보관 폴더로 옮기는 작업을 재사용하고 싶어. | 지원·폴더 정리 | 지원·폴더 정리 | 폴더 이동 의도와 일치 |
| 분기마다 프로젝트 폴더 이름을 같은 규칙으로 변경하도록 해줘. | 지원·폴더 정리 | 지원·폴더 정리 | 폴더 이름 변경 의도와 일치 |
| 여러 곳에 흩어진 회의록을 팀 회의 폴더로 이동하는 규칙을 만들어줘. | 지원·폴더 정리 | 지원·폴더 정리 | 문서 이동·정리 의도와 일치 |
| 연도와 월 폴더를 만들고 문서를 해당 월로 나누는 작업이 필요해. | 지원·폴더 정리 | 지원·폴더 정리 | 폴더 구성·분류 의도와 일치 |
| 문서 이름을 종류와 날짜가 드러나는 형식으로 일괄 정리하도록 해줘. | 지원·폴더 정리 | 지원·폴더 정리 | 이름 정리 의도와 일치 |
| 흩어진 설계 자료를 주제별 폴더로 옮기는 반복 작업을 저장해줘. | 지원·폴더 정리 | 지원·폴더 정리 | 주제별 이동 의도와 일치 |
| 선택한 문서의 제목 단계와 표 배치를 그대로 쓰는 장애 보고서 양식을 만들어줘. | 지원·양식 | 지원·양식 | 참고 구조 보존 양식과 일치 |
| 참고 문서의 항목 순서와 체크 목록을 바꾸지 않는 점검 양식으로 저장해줘. | 지원·양식 | 지원·양식 | 참고 구조 보존 양식과 일치 |
| 선택한 제안서의 절과 표 구성을 고정해서 이후 문서에도 사용하고 싶어. | 지원·양식 | 지원·양식 | 참고 구조 보존 양식과 일치 |
| 참고한 회고 문서의 제목과 목록 배치를 유지하는 양식을 만들어줘. | 지원·양식 | 지원·양식 | 참고 구조 보존 양식과 일치 |
| 현재 주간 보고서의 장 순서를 그대로 재사용할 수 있게 고정해줘. | 지원·양식 | 지원·양식 | 참고 구조 보존 양식과 일치 |
| 선택한 회의 기록의 구조를 변경하지 않는 반복 양식으로 만들어줘. | 지원·양식 | 지원·양식 | 참고 구조 보존 양식과 일치 |

### 범위 밖·모호한 경계 작업 8개

| 실제 지시 | 기대 분류 | 실제 분류 | 판정 이유 |
| --- | --- | --- | --- |
| 참석자들의 캘린더에서 빈 시간을 찾아 회의를 예약하는 자동화를 만들어줘. | 범위 밖 | 범위 밖 | 문서 Skill 범위 밖의 일정 예약 |
| 매주 월요일 고객 목록에 안내 이메일을 발송하는 규칙을 저장해줘. | 범위 밖 | 범위 밖 | 외부 이메일 발송 |
| 배포 서버에서 셸 명령을 실행해 서비스를 재시작하는 작업을 만들어줘. | 범위 밖 | 범위 밖 | 서버 셸 실행 |
| 웹사이트 가격을 수집해서 Slack 채널에 올리는 자동 작업이 필요해. | 범위 밖 | 범위 밖 | 웹 수집·외부 메신저 전송 |
| 팀 자료를 보기 좋게 정리하는 반복 작업을 만들어줘. | 모호 | 모호 | 구체적인 문서 효과가 없음 |
| 보고서를 매번 같은 방식으로 처리하는 규칙을 저장해줘. | 모호 또는 허용된 양식 | 지원·양식 | 모호하지만 계약이 허용한 지원 분류이며, 모호성은 남음 |
| 문서 관리를 자동화하는 규칙을 만들어줘. | 모호 또는 허용된 폴더 정리 | 모호 | 구체적인 문서 효과가 없음 |
| 회의 자료를 준비하는 작업을 저장해줘. | 모호 또는 허용된 문서 작성·편집·양식 | 지원·문서 작성 | 모호하지만 계약이 허용한 지원 분류이며, 모호성은 남음 |

총 **32/32**가 통과했다. 지원 작업은 24/24, 경계 작업은 8/8이었다.

## 왜 그렇게 판정했나

실제 분류가 기대 분류 또는 경계 계약에서 허용한 결과에 포함되는지 확인했다. 범위 밖 4개는 외부 작업을 거절했고, 모호한 4개 중 2개는 모호성으로 남겼으며 2개는 계약이 허용한 지원 유형을 선택했다. 현재 HEAD는 과거의 별도 검증기를 제거했으므로, 과거 동결 기대 30/32와 현재 32/32를 단순 개선으로 비교하지 않는다.

## 이 실험이 증명하지 못하는 것

이 32/32 결과는 Skill 라우팅·분류만 측정했다. 실제 Skill 실행 내용과 실제 문서 출력, 도구 권한, 모호한 요청을 사용자와 재확인하는 상호작용은 아래 실제 Skill 적용 평가에서 별도로 확인했다.

# 실제 Skill 적용

## 무엇을 시험했나

실제 사용자 요청 3개를 각각 3회씩 최종 live 모델로 실행해 선택된 Skill 지시가 실제 출력과 도구 계획에 반영되는지 확인했다. 각 묶음에는 사용자 요청, 적용 Skill 지시, 기대 동작을 다시 적고, 원시 출력 전문과 사람 관찰을 함께 보존했다. 생성은 본문 뒤 3개 항목 요약과 결정 사항을 포함하는지, 편집은 금요일·민지·롤백을 보존하고 한국어 구조로 정리하는지, 폴더 정리는 직접 요청을 폴더 정리로 라우팅하고 승인 대기 계획에서 허용 도구를 순서대로 쓰는지를 평가했다. 별도 고정 템플릿 fixture는 입력에 운영 환경 권한 조건과 첫 주 읽기 권한 제한이라는 결정 근거를 포함하므로 일반 온보딩 생성과 결정 근거성 평가를 분리했다.

## 실제 결과

| 실제 사용자 요청 | Skill 지시 | 기대 동작 | 실제 출력 요약·도구 순서 | 판정 이유 |
| --- | --- | --- | --- | --- |
| 팀 온보딩 절차를 설명하는 문서를 작성해줘. | 본문 뒤 짧은 3개 항목 요약과 별도 결정 사항 섹션을 자연스럽게 포함 | 문서 생성으로 라우팅하고 두 요소를 모두 포함 | `markdown_create`; 온보딩 문서, 3개 항목 요약, 결정 사항 섹션 출력 | 3회 모두 요소를 확인해 **3/3** |
| 이 문서를 정리해줘. | 원문 사실을 추가하지 않고 보존하며 한국어 운영 메모 구조와 간결한 문체로 재구성 | 금요일 배포, 민지 담당, 이전 버전 롤백을 보존 | `markdown_edit`; 3회 모두 금요일·민지·롤백을 보존한 한국어 구조 출력 | 3회 모두 문자열·구조 보존으로 **3/3** |
| 분기 회고 문서를 보관 폴더로 옮긴 뒤 이름을 바꿔줘. | 먼저 보관 폴더로 이동한 뒤 아카이브 접두사를 붙여 이름 변경 | 직접 요청을 `folder_organize`로 라우팅하고 `awaiting_approval` 상태의 승인된 인메모리 계획을 실행 | `move_document` → `rename_document`; 허용 도구만 사용 | 3회 모두 대상·순서·접두사·도구 허용을 확인해 **3/3** |

기존 최종 실모델 기록은 형식·라우팅·도구 계약 **9/9**였지만, 이는 Skill 지시 적용 증거와 관찰된 출력·라우팅·도구 계약을 합친 표면 결과로만 제한한다. 후속 live 재실행에서 일반 온보딩 A는 strict **1/3**, route **3/3**, grounding **2/3**으로 판정했고 폴더 계획 B는 **3/3**이었다. 기존 생성 출력의 형식 계약(3개 이상 요약+결정 사항 section) 3/3 기록은 보존하되 현재 온보딩의 엄격한 품질 3/3으로 확대하지 않는다. 기존 기록에서 1회 `추가 정책·도구 변경 없음`은 입력에 결정 근거가 없으므로 결정 사항처럼 단정할 근거가 없고 일반적 제안으로는 타당하다. 2회의 멘토 배정·기간 조정·보안교육 기록도 일반적인 제안으로는 타당하지만 결정된 정책처럼 표현됐다. 3회의 결정 필요 체크리스트는 일반적으로 타당한 항목이지만 실제 결정값은 아니다. 따라서 일반 온보딩 생성의 기존 표면 형식 통과는 근거 있는 결정 내용의 품질 통과가 아니다. 편집은 세 회차 모두 금요일·민지·이전 버전 롤백을 실제 출력에서 보존했다. 폴더 계획은 세 회차 모두 `awaiting_approval`이었고 실제 기록 게이트웨이 호출 순서는 `move_document` → `rename_document`였다. 3회 summary의 ‘읽기 전용 계획’ 표현은 뒤의 변경 도구 실행과 의미상 어색하다. 최초 실행기의 구성 오류와 중간 1회 direct-intent 오탐은 최종 산출물에 correction history가 보존되지 않아 대화·작업 기록으로만 관찰됐고, 최종 재실행 3/3에서는 재현되지 않았다. 실제 DB·backend·object storage는 쓰지 않았고 승인된 인메모리 plan을 직접 AgentWorker에 주입했으므로 진짜 승인 API·권한·영속 저장 성공은 증명하지 않는다.

## 문서 생성 실제 출력

### 문서 생성 1회 실제 Markdown

**사용자 요청**: 팀 온보딩 절차를 설명하는 문서를 작성해줘.

**적용 Skill 지시**: 생성 문서에는 본문 뒤에 짧은 3개 항목 요약과 별도의 결정 사항 섹션을 자연스럽게 포함한다.

**기대 동작**: 문서 생성으로 라우팅하고 본문 뒤 요약 3개 이상과 별도 결정 사항 section을 포함한다.

```markdown
# 팀 온보딩 절차

목표
- 신규 구성원의 원활한 적응 및 역할 이해도 향상
- 필요한 도구 접근 권한 및 보안 교육 포함
- 팀 문화 및 업무 방식에 대한 빠른 이해

대상
- 신규 입사자, 재배치된 구성원, 협업을 시작하는 외부 인턴 등 온보딩이 필요한 모든 구성원

준비물
- OT 자료, 회사 정책 요약, 도구 접근 안내, 멘토 배정표

온보딩 프로세스 단계

1단계: 오리엔테이션 및 계정 설정
- 회사 소개, 조직 구조, 비전 공유
- 계정 생성 및 접근 권한 부여
- 장비 수령 및 초기 설정 안내

2단계: 팀 및 역할 이해
- 팀 목표, 현재 프로젝트, 기대치 공유
- 주요 커뮤니케이션 채널 소개
- 멘토/버디 배정 및 첫 주 일정 공유

3단계: 도구 및 업무 프로세스 학습
- 도구 사용법 교육(협업툴, 저장소, 이슈 트래킹 등)
- 보안/컴플라이언스 교육
- 샘플 작업으로 실습

4단계: 실전 과제 및 피드백
- 초기 과제 수행 및 결과 리뷰
- 주간 1:1 피드백
- 학습 계획 및 목표 조정

역할별 책임
- 인사/운영: 온보딩 일정 관리, 자원 배치, 정책 안내
- 팀 리더: 목표 공유, 멘토링, 피드백 주도
- 멘토: 신규자 적응 지원, 질문 응대

온보딩 체크리스트 예시
- 계정 및 도구 접근 권한 설정 완료
- OT 자료 및 정책 공유 완료
- 첫 주 피드백 수집 및 2주차 계획 확정

소요 시간 및 일정 예시
- 보통 2주 ~ 4주(조정 가능)
- 주간 체크인, 1:1 미팅, 교육 세션 배치

자주 묻는 질문(FAQ)
- Q: 온보딩 기간은?
- A: 일반적으로 2주에서 4주 사이이며 역할에 따라 다름
- Q: 멘토 배정은?
- A: 팀 리더 및 HR의 협의로 배정

짧은 3개 항목 요약
- 신규 직원의 빠른 적응을 위한 오리엔테이션 및 계정 설정
- 팀 이해도 상승을 위한 역할 설명 및 도구 학습
- 정기 피드백과 체크리스트를 통한 체계적 온보딩 관리

결정 사항
- 현재 추가 정책이나 도구 변경은 없음
```

사람 관찰: 입력에 결정 사항으로 단정할 근거는 없지만, `추가 정책이나 도구 변경은 없음`은 일반적인 제안으로는 타당하다.

### 문서 생성 2회 실제 Markdown

**사용자 요청**: 팀 온보딩 절차를 설명하는 문서를 작성해줘.

**적용 Skill 지시**: 생성 문서에는 본문 뒤에 짧은 3개 항목 요약과 별도의 결정 사항 섹션을 자연스럽게 포함한다.

**기대 동작**: 문서 생성으로 라우팅하고 본문 뒤 요약 3개 이상과 별도 결정 사항 section을 포함한다.

```markdown
# 팀 온보딩 절차 가이드

## 개요

팀 온보딩은 신규 팀원이 빠르게 역할을 이해하고 조직 문화에 적응하도록 돕는 일련의 활동들로 구성됩니다. 본 가이드는 전반적인 흐름과 주요 활동, 체크리스트를 제시합니다.

## 온보딩 준비

- 사전 준비 사항
  - 사원 등록 및 시스템 접근 권한 발급: 계정 생성과 도구 접근 권한 설정
  - 오리엔테이션 일정 공유: 회사 정책, 팀 구조, 주요 연락처 안내
  - 멘토/버디 배정: 새로운 구성원이 초기 적응에 도움을 받도록 멘토를 지정

- 자료 및 도구 준비
  - 필요한 자료실 및 문서 위치 안내: 팀의 문서 저장소, 위키 등
  - 초기 작업 공간 구성: 노트북, 소프트웨어 설치, 보안 교육 여부 확인

## 첫날 흐름

1) 환영 및 소개: 팀 구성원 소개, 역할 간략 설명
2) 장비 체크: 노트북/계정 점검 및 사용 방법 안내
3) 보안 및 정책: 보안 교육, 출입/접속 규칙 안내
4) 첫 과제 안내: 짧은 샘플 과제 또는 온보딩 과제 제공

## 1주차 계획

- 역할 이해: 팀의 목표, 주요 프로젝트, 참여 시나리오 정리
- 도구 및 시스템 심화 학습: 프로젝트 관리 도구, 커뮤니케이션 도구 사용법
- 소규모 미션: 실제 작업에 가까운 과제 수행 및 피드백
- 피드백 루프: 주간 체크인으로 문제점 공유 및 개선 계획 수립

## 2주차 계획

- 프로젝트 참여 확대: 실제 업무에 부분적으로 참여
- 문서화 습관 형성: 노트, 위키, 기록 습관 정착
- 문화 적응: 팀 문화와 의사소통 스타일에 익숙해지기

## 체크리스트(샘플)

- 계정 생성 및 접근 권한 부여 여부 확인
- 오리엔테이션 일정 참여 여부
- 멘토 매칭 및 초기 미팅 완료 여부
- 보안 교육 이수 여부
- 초기 과제 수락 및 피드백 반영 여부

## 자주 묻는 질문

- 온보딩 기간은 보통 며칠인가요?
  - 조직마다 다르지만 일반적으로 1~4주 단위의 계획으로 구성됩니다.
- 누가 멘토가 되나요?
  - 팀 리더나 지정된 동료가 멘토로 배정됩니다.
- 필요한 자료는 어디서 찾나요?
  - 팀의 위키/문서 저장소에 정리되어 있습니다.

## 3개 항목 요약

- 새로운 구성원이 빠르게 시스템과 도구에 익숙해지도록 계정 발급과 접근 권한 설정이 선행되어야 합니다.
- 1주차에는 역할 이해와 도구 심화 학습, 피드백 루프를 통해 초기 문제를 해결합니다.
- 2주차 이후에는 실제 프로젝트에 참여를 확대하고 문서화 습관을 정착시키는 것이 핵심입니다.

## 결정 사항

- 결정 사항 1: 멘토 배정 정책은 팀 리더가 결정합니다.
- 결정 사항 2: 온보딩 기간은 팀의 업무량에 따라 조정될 수 있습니다.
- 결정 사항 3: 보안 교육 이수 여부는 필수로 기록됩니다.
```

사람 관찰: 멘토 배정·온보딩 기간 조정·보안교육 기록은 일반적인 제안으로는 타당하지만, 입력에 결정 근거가 없는데 결정된 정책처럼 표현했다.

### 문서 생성 3회 실제 Markdown

**사용자 요청**: 팀 온보딩 절차를 설명하는 문서를 작성해줘.

**적용 Skill 지시**: 생성 문서에는 본문 뒤에 짧은 3개 항목 요약과 별도의 결정 사항 섹션을 자연스럽게 포함한다.

**기대 동작**: 문서 생성으로 라우팅하고 본문 뒤 요약 3개 이상과 별도 결정 사항 section을 포함한다.

```markdown
# 팀 온보딩 절차 설명서

## 개요
이 문서는 신규 팀원이 팀에 합류했을 때 따라야 할 단계, 필요한 자료 및 성공적으로 적응하기 위한 체크리스트를 정리한 가이드입니다. 목표는 역할 이해, 도구 접근 권한 확보, 팀 문화와 협업 방식 이해를 돕는 것입니다.

## 1. 온보딩 목표
- 신규 팀원이 자신의 역할과 책임을 명확히 이해한다.
- 필요한 도구 및 시스템에 접근 권한이 원활하게 제공된다.
- 팀의 업무 방식, 문화, 커뮤니케이션 채널을 숙지한다.
- 초기 작업을 안전하게 수행할 수 있는 기본 지식과 자료를 학습한다.

## 2. 준비 및 시작
- 환영 인사 및 팀 구성원 소개를 포함한 오리엔테이션 일정 수립
- 계정 생성 및 접근 권한 부여 절차 이행
- 자료 공유 공간(예: 문서, 위키, 프로젝트 보드) 접근 권한 설정
- 필요 시 멘토/버팀자 매칭 및 초기 안내 미팅 진행

## 3. 초기 주간 계획
- 첫 주: 역할 이해, 핵심 도구 사용법 습득, 팀 미팅 참여
- 둘째 주: 작은 규모의 실무 작업 시작, 피드백 루프 구축
- 셋째 주 이후: 점진적 업무 난이도 증가 및 독립적 작업 수행

## 4. 역할별 체크리스트
### 신입의 체크리스트
- 필수 문서 및 정책 읽기 완료
- 도구 접근 권한 확인 및 테스트
- 팀 구성원 소개 및 커뮤니케이션 채널 이해
- 멘토와의 1:1 미팅 일정 확보
### 팀 리더/동료의 체크리스트
- 오리엔테이션 일정 관리 및 자료 공유
- 신규 직원의 첫 주 목표 확인 및 피드백 제공
- 멘토링 계획 수립 및 수행
- 초기 작업 배분 및 진척 상황 모니터링

## 5. 도구 및 접근 권한 설정
- 계정 생성 및 보안 정책 안내 수신 확인
- 필요한 도구 및 시스템에 대한 접근 권한 부여
- 초기 보안 교육 이수 및 정책 공유
- 필요 자료의 위치(저장소, 위키, 코딩 저장소) 안내

## 6. 교육 콘텐츠
- 회사의 제품/서비스 이해 및 비즈니스 흐름 파악
- 내부 정책, 규정, 운영 프로세스 학습
- 소스 코드/문서 구조 및 개발 가이드 개요 이해(해당 시)

## 7. 멘토링 및 피드백
- 주간 체크인 및 목표 점검
- 초기 성과 피드백 및 개선 계획 수립
- 피드백 루프를 통한 지속적 학습 문화 조성

## 3개 항목 요약
- 신규 직원의 역할 이해와 도구 접근 권한 확보를 최우선으로 한다.
- 체계적인 일정, 멘토링, 명확한 커뮤니케이션 채널로 빠른 적응을 돕는다.
- 피드백과 학습 자료를 통해 온보딩 프로세스를 지속적으로 개선한다.

## 결정 사항
- 온보딩 기간의 일반적 길이 및 각 단계의 완료 기준
- 담당 멘토/버팀자 선정 및 역할 분담
- 필요 도구 및 시스템 접근 범위와 보안 정책의 적용 방식
- 피드백 주기, 평가 방법, 성공 지표의 정의
- 온보딩 자료의 업데이트 주기 및 책임자
```

사람 관찰: 온보딩 기간·멘토·도구·평가·업데이트를 결정 필요 체크리스트로 제시한 것은 일반적으로 타당하지만, 실제 결정값은 아니다.

## 문서 편집 실제 출력

### 문서 편집 1회 실제 Markdown

**사용자 요청**: 이 문서를 정리해줘.

**적용 Skill 지시**: 원문에 없는 사실을 추가하지 말고 사실을 보존한다. 한국어 운영 메모 구조와 간결한 문체로 재구성한다.

**기대 동작**: 금요일 배포, 민지 담당, 이전 버전 롤백을 보존한 한국어 운영 메모를 출력한다.

```markdown
# 운영 메모

배포는 금요일에 진행합니다.
담당자는 민지입니다.

## 참고
롤백은 이전 버전을 사용합니다.
```

사람 관찰: 금요일·민지·이전 버전 롤백을 모두 보존했고, 원문에 없는 사실을 추가하지 않았다.

### 문서 편집 2회 실제 Markdown

**사용자 요청**: 이 문서를 정리해줘.

**적용 Skill 지시**: 원문에 없는 사실을 추가하지 말고 사실을 보존한다. 한국어 운영 메모 구조와 간결한 문체로 재구성한다.

**기대 동작**: 금요일 배포, 민지 담당, 이전 버전 롤백을 보존한 한국어 운영 메모를 출력한다.

```markdown
# 운영 메모

배포는 금요일에 진행합니다.
담당자는 민지입니다.

## 참고
롤백은 이전 버전을 사용합니다.
```

사람 관찰: 금요일·민지·이전 버전 롤백을 모두 보존했고, 원문에 없는 사실을 추가하지 않았다.

### 문서 편집 3회 실제 Markdown

**사용자 요청**: 이 문서를 정리해줘.

**적용 Skill 지시**: 원문에 없는 사실을 추가하지 말고 사실을 보존한다. 한국어 운영 메모 구조와 간결한 문체로 재구성한다.

**기대 동작**: 금요일 배포, 민지 담당, 이전 버전 롤백을 보존한 한국어 운영 메모를 출력한다.

```markdown
# 운영 메모

배포는 금요일에 실시한다.
담당자: 민지.

## 참고
롤백은 이전 버전을 사용한다.
```

사람 관찰: 표현은 일부 바뀌었지만 금요일·민지·이전 버전 롤백을 모두 보존했고, 원문에 없는 사실을 추가하지 않았다.

## 폴더 정리 실제 계획

### 폴더 정리 1회 실제 계획

**사용자 요청**: 분기 회고 문서를 보관 폴더로 옮긴 뒤 이름을 바꿔줘.

**적용 Skill 지시**: 지정한 문서를 먼저 보관 폴더로 이동한 다음 자연스러운 아카이브 접두사를 붙여 이름을 변경한다.

**기대 동작**: `folder_organize`로 라우팅하고 `awaiting_approval` 상태에서 `move_document` 후 `rename_document` 순서의 계획을 만든다.

```json
{
  "summary": "분기 회고 문서를 보관 폴더로 이동한 뒤 이름에 아카이브 접두사를 추가하는 계획입니다.",
  "status": "awaiting_approval",
  "operations": [
    {
      "sequence": 1,
      "tool_name": "move_document",
      "arguments": {
        "document_id": "doc-q1",
        "folder_id": "archive",
        "position": 0,
        "base_version": 2
      },
      "reason": "분기 회고 문서를 보관 폴더로 이동"
    },
    {
      "sequence": 2,
      "tool_name": "rename_document",
      "arguments": {
        "document_id": "doc-q1",
        "display_name": "아카이브 분기 회고 문서",
        "base_version": {
          "$operation_result": "plan-1-op-1",
          "field": "current_version"
        }
      },
      "reason": "보관 후 문서 이름에 아카이브 접두사를 추가"
    }
  ]
}
```

사람 관찰: `handle_result`는 `awaiting_approval`이었고, 실제 기록 게이트웨이 호출 순서는 `move_document` → `rename_document`였다. `summary`, `status`, `operations`, `arguments`, `display_name`을 모두 보존했다.

### 폴더 정리 2회 실제 계획

**사용자 요청**: 분기 회고 문서를 보관 폴더로 옮긴 뒤 이름을 바꿔줘.

**적용 Skill 지시**: 지정한 문서를 먼저 보관 폴더로 이동한 다음 자연스러운 아카이브 접두사를 붙여 이름을 변경한다.

**기대 동작**: `folder_organize`로 라우팅하고 `awaiting_approval` 상태에서 `move_document` 후 `rename_document` 순서의 계획을 만든다.

```json
{
  "summary": "분기 회고 문서를 보관 폴더로 이동한 뒤 이름에 아카이브 접두사를 붙이는 계획.",
  "status": "awaiting_approval",
  "operations": [
    {
      "sequence": 1,
      "tool_name": "move_document",
      "arguments": {
        "document_id": "doc-q1",
        "folder_id": "archive",
        "position": 0,
        "base_version": 2
      },
      "reason": "분기 회고 문서를 보관 폴더로 옮깁니다."
    },
    {
      "sequence": 2,
      "tool_name": "rename_document",
      "arguments": {
        "document_id": "doc-q1",
        "display_name": "아카이브 분기 회고 문서",
        "base_version": {
          "$operation_result": "plan-2-op-1",
          "field": "current_version"
        }
      },
      "reason": "문서 이름에 아카이브 접두사를 추가합니다."
    }
  ]
}
```

사람 관찰: `handle_result`는 `awaiting_approval`이었고, 실제 기록 게이트웨이 호출 순서는 `move_document` → `rename_document`였다. `summary`, `status`, `operations`, `arguments`, `display_name`을 모두 보존했다.

### 폴더 정리 3회 실제 계획

**사용자 요청**: 분기 회고 문서를 보관 폴더로 옮긴 뒤 이름을 바꿔줘.

**적용 Skill 지시**: 지정한 문서를 먼저 보관 폴더로 이동한 다음 자연스러운 아카이브 접두사를 붙여 이름을 변경한다.

**기대 동작**: `folder_organize`로 라우팅하고 `awaiting_approval` 상태에서 `move_document` 후 `rename_document` 순서의 계획을 만든다.

```json
{
  "summary": "분기 회고 문서를 보관 폴더로 이동한 뒤 이름에 아카이브 접두사를 붙이는 읽기 전용 계획입니다.",
  "status": "awaiting_approval",
  "operations": [
    {
      "sequence": 1,
      "tool_name": "move_document",
      "arguments": {
        "document_id": "doc-q1",
        "folder_id": "archive",
        "position": 0,
        "base_version": 2
      },
      "reason": "분기 회고 문서를 보관 폴더로 이동한다."
    },
    {
      "sequence": 2,
      "tool_name": "rename_document",
      "arguments": {
        "document_id": "doc-q1",
        "display_name": "아카이브 분기 회고 문서",
        "base_version": {
          "$operation_result": "plan-3-op-1",
          "field": "current_version"
        }
      },
      "reason": "이름에 아카이브 접두사를 추가한다."
    }
  ]
}
```

사람 관찰: `handle_result`는 `awaiting_approval`이었고, 실제 기록 게이트웨이 호출 순서는 `move_document` → `rename_document`였다. `summary`의 ‘읽기 전용 계획’ 표현은 뒤의 변경 도구 실행과 의미상 어색하다. `summary`, `status`, `operations`, `arguments`, `display_name`을 모두 보존했다.

생성 판정기의 ‘3개 이상’ 검사와 편집 판정의 문자열 보존·한국어 구조 검사는 실제 의미 품질보다 넓거나 얕을 수 있다. 따라서 기존 **형식·라우팅·도구 계약 9/9**은 Skill 적용·라우팅·계획과 관찰된 출력 계약의 통과이지 제품 전체의 문서 의미 품질이나 실제 외부 저장 성공을 뜻하지 않으며, 후속 live의 A strict 1/3·grounding 2/3 결과와 함께 해석해야 한다.

# 실제 Skill 적용 후속 Live 재실행

## 재실행 범위와 계약

앞선 실제 Skill 적용 기록을 현재 결과로 과대 해석하지 않도록, 같은 계열의 fixture를 실제 `openai/gpt-5-nano` 호출로 다시 실행했다. A는 `팀 온보딩 절차를 설명하는 문서를 작성해줘.` 요청과 `skill-onboarding`의 생성 지시를 적용했다. Skill 지시는 본문 뒤에 `짧은 3개 항목 요약` 3개와 별도의 `결정 사항` section을 포함하고, 입력에 없는 정책·결정은 사실처럼 확정하지 않으며 제안 또는 결정 필요로 표시하는 것이다. 기대 route/output/tool 계약은 `route/action=markdown_create`, `edit_goal=create_from_chat`, `selected_skill_id=skill-onboarding`, `document_operation=create`, `persist=false`, `required_capabilities=[document-create]`와 온보딩 Markdown 본문·요약·결정 사항 section이다.

B는 `분기 회고 문서를 보관 폴더로 옮긴 뒤 이름을 바꿔줘.` 요청과 `skill-folder`의 폴더 정리 지시를 적용했다. Skill 지시는 먼저 보관 폴더로 `move_document`한 뒤 아카이브 접두사를 붙여 `rename_document`하고, 승인 전에는 변경하지 않는 계획을 만드는 것이다. 기대 route/output/tool 계약은 `route.action=folder_organize`, `selected_skill_id=skill-folder`, `retrieval_source=none`, `document_operation=none`, `persist=true`, `required_capabilities=[folder-organize]`, `handle_result.run_status=queued`, plan `status=awaiting_approval`, 그리고 `move_document` → `rename_document` 순서와 두 번째 작업의 `current_version` 의존성이다.

두 fixture 모두 실행 경계는 production router·Markdown editor·plan generator를 사용하되 in-memory stub으로 Skill repository·query·run starter와 기록 gateway를 대체한 것이다. 실제 DB·backend·object storage·승인 API·영속 저장은 호출하지 않았다. 여섯 회차 모두 `correction_history=[]`이며 runner가 내용을 수정·보정하거나 retry를 선택한 회차는 없다.

## 집계와 회차별 판정

| 묶음 | 회차 | route | strict/output | grounding | 계획·도구 계약 | 최종 판정과 실제 이유 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A 온보딩 | 1 | 1/1 | pass | pass | 해당 없음 | 본문 뒤 요약 3개와 `결정 사항`을 두었고, 근거 없는 결정을 확정하지 않고 제안·결정 필요로 표시했다. |
| A 온보딩 | 2 | 1/1 | pass | **fail** | 해당 없음 | 요약 3개와 section은 있었지만 멘토·기간·교육·접근 정책을 결정된 사실처럼 평서로 배치했다. |
| A 온보딩 | 3 | 1/1 | **fail** | pass | 해당 없음 | 요약 3개의 의미와 제안·향후 검토 표시는 통과했지만 Skill fixture의 `결정 사항` section을 `결정 필요`로 바꾸어 엄격한 형식 보존에 실패했다. |
| B 폴더 계획 | 1 | 1/1 | 1/1 | 해당 없음 | pass | `awaiting_approval`, `move_document` → `rename_document`, 대상·목적지·이름·버전 의존성과 승인 후 실행 summary를 모두 충족했다. |
| B 폴더 계획 | 2 | 1/1 | 1/1 | 해당 없음 | pass | `awaiting_approval`, 정확한 도구 순서와 `current_version` 의존성, 승인 전 무변경 summary를 충족했다. |
| B 폴더 계획 | 3 | 1/1 | 1/1 | 해당 없음 | pass | `awaiting_approval`, 정확한 도구 순서와 인자를 충족했고 summary가 승인 후 두 작업 실행을 명시했다. |

따라서 A 집계는 strict **1/3**, route **3/3**, grounding **2/3**이고 B 집계는 **3/3**이다. 이는 기존 일반 Skill 적용의 표면 계약 9/9를 지우지 않으며, 현재 live 온보딩의 엄격한 품질을 3/3으로 부풀리지 않는 후속 세분화다.

## A 온보딩 raw Markdown 전문

### A-1

```text
A-1 raw result (model openai/gpt-5-nano; correction_history=[]):
route/action=markdown_create; confidence=0.0; edit_goal=create_from_chat; selected_skill_id=skill-onboarding; retrieval_source=none; document_operation=create; persist=false; required_capabilities=[document-create].
title: 팀 온보딩 절차 가이드
summary: 새로 합류하는 팀원이 빠르게 업무에 적응할 수 있도록 단계별 온보딩 절차와 체크리스트를 제시하는 문서입니다.

# 팀 온보딩 절차 가이드

이 문서는 신규 입사자 및 팀 구성원이 회사에 빠르게 익숙해지고, 필요한 도구와 프로세스를 이해하여 실무에 원활하게 참여하도록 돕는 표준 온보딩 절차를 제시합니다.

## 1. 대상과 범위
- 신규 입사자, 재배치 직원, 계약직 등 온보딩이 필요한 모든 구성원을 포함합니다.
- 팀 내마다 특화된 부분은 별도 보완 자료로 제공될 수 있습니다.

## 2. 온보딩 목표
- 회사 문화와 운영 방식에 대한 이해
- 필수 도구 및 시스템 접근 권한 확보
- 역할에 필요한 업무 도구 및 지식 습득
- 초기 30일 내 실무 생산성 확보

## 3. 온보딩 흐름 개요
### 3.1 사전 준비
- 채용 확정 시 인사/IT 팀이 계정 생성 및 메일 도메인 등록
- 필요한 자원(노트북, 소프트웨어 라이선스 등) 준비
- 필요한 접근 권한 목록 전달 및 계정 프로비저닝 계획 수립

### 3.2 첫날 일정
- 회사 소개 및 보안 정책 안내
- 팀 소개 및 역할 설명
- 계정 로그인 및 도구 접근 확인
- 안전교육 및 기본 컴플라이언스 교육

### 3.3 1주차 계획
- 주요 도구 학습(이메일, 협업툴, 프로젝트 관리 도구)
- 팀 프로젝트의 작은 미션 수행
- 멘토와의 1:1 체크인 주 1회

### 3.4 30일 목표
- 실제 업무에 필요한 주요 업무 프로세스 습득
- 초기 산출물 품질 및 일정 준수 확인
- 피드백 루프 형성 및 개선사항 도출

### 3.5 도구 및 접근 권한
- 계정 생성 여부 확인
- 필요 권한 목록의 주기적 업데이트
- 보안 정책 준수 및 2단계 인증 설정

### 3.6 멘토링 및 체크인
- 신규 직원당 매주 1회 멘토와 면담
- 문제 상황의 신속한 보고 체계 확립

### 3.7 평가 및 개선
- 30일, 60일, 90일에 걸친 피드백 수집
- 온보딩 자료의 주기적 업데이트

## 4. 역할 및 책임
- HR/인사: 온보딩 일정 관리, 문서 관리, 피드백 수집
- IT: 계정 프로비저닝, 도구 접근 권한 부여, 보안 교육
- 팀 매니저: 역할 배정, 초기 프로젝트 오리엔테이션, 멘토 매칭
- 멘토: 신입의 빠른 적응 지원, 주간 체크인

## 5. 온보딩 체크리스트 예시
- 계정/이메일 발급 및 로그인 확인
- 보안 교육 이수
- 도구 접근 권한 부여
- 팀 소개 및 주요 연락처 공유
- 초기 과제 및 산출물 제출

## 6. 자주 묻는 질문(FAQ)
- Q: 온보딩 기간은 얼마나 걸리나요?
  A: 일반적으로 4주를 기본으로 하되 개인에 따라 차이가 있을 수 있습니다.
- Q: 어떤 도구를 먼저 배우나요?
  A: 팀에서 사용하는 협업툴, 이메일/일정 관리 도구, 프로젝트 관리 도구 순으로 학습합니다.
- Q: 멘토는 어떻게 배정되나요?
  A: 팀 리더와 HR이 협의하여 출발 시점에 매칭합니다.

---

## 짧은 3개 항목 요약
- 목표는 신규 직원의 빠른 적응과 생산성 확보이다.
- 사전 준비부터 첫날, 1주차, 30일 목표까지의 흐름이 명확하게 정의되어 있다.
- 각 역할의 책임과 체크리스트를 통해 체계적인 온보딩을 지원한다.

---

## 결정 사항
현재 결정 사항은 본 문서에 명시되지 않았습니다. 아래는 향후 의사결정이 필요한 제안 항목들.

- 온보딩 기간의 표준화 여부 확정 필요
- 신규 직무 교육 커리큘럼의 기본 구성 확정 필요
- 멘토링 매칭 정책의 구체적 기준 확정 필요
- 각 팀별 체크리스트의 표준화 및 도구 정책 확정 필요
- 신규 채용 시점의 자동 계정 프로비저닝 정책 여부 결정 필요
```

**판정**: route/action pass, 본문 뒤 3개 요약 의미 pass, grounding pass. 기존 Skill fixture의 `짧은 3개 항목 요약`과 `결정 사항`을 유지했고 결정 근거가 없는 항목을 제안·결정 필요로 표시했다.

### A-2

```text
A-2 raw result (model openai/gpt-5-nano; correction_history=[]):
route/action=markdown_create; confidence=0.72; edit_goal=create_from_chat; selected_skill_id=skill-onboarding; retrieval_source=none; document_operation=create; persist=false; required_capabilities=[document-create].
title: 팀 온보딩 절차 가이드
summary: 새로운 팀원이 조직에 빠르게 적응하도록 단계별 온보딩 프로세스를 제시한다.

# 팀 온보딩 절차 가이드

## 개요
신규 팀원이 조직에 빠르게 적응하고 생산성을 높일 수 있도록, 체계적이고 반복 가능한 온보딩 절차를 제시합니다. 본 가이드는 일반적인 팀 구성을 가정하며 필요 시 해당 팀의 상황에 맞게 조정합니다.

## 목적
- 조직 문화와 가치관 이해
- 역할 및 책임 명확화
- 필수 도구 접근 및 업무 프로세스 숙지

## 대상
- 신규 입사자
- 부서 간 이동자
- 재배치자

## 준비물
- 환영 패키지 및 오리엔테이션 일정
- 신규 계정 요청 목록(이메일, 도구, 저장소 등)
- 멘토/버디 매칭 목록

## 단계별 온보딩 절차
### 1단계: 사전 준비
- HR와 팀 리더가 협업하여 환영 이메일 발송
- 계정 생성 및 시스템 접근 권한 요청
- 오리엔테이션 일정 확정 및 안내

### 2단계: 첫날 오리엔테이션 및 환영
- 팀 구성원 소개 및 팀 목표 공유
- 조직 문화, 규범, 커뮤니케이션 채널 안내
- 자신이 수행할 초기 과제의 간단한 소개

### 3단계: 도구 설정 및 계정 구성
- 이메일, Slack/메신저, 협업 도구, 개발 환경 계정 생성
- 접근 권한 점검 및 보안 정책 안내
- 샘플 프로젝트 또는 테스트 프로젝트로 초기 작업 시작

### 4단계: 역할 이해 및 팀 내 위치 확인
- 역할 목표 및 주요 책임 설명
- 팀 내 커뮤니케이션 루틴(주간 미팅, 1:1, 리뷰) 설명
- 초기 성과 지표와 기대치 공유

### 5단계: 초기 교육과 리소스 제공
- 학습 경로, 도큐먼트, 내부 wiki 안내
- 필요한 교육 코스 및 실습 과제 제시
- 멘토와의 주간 체크인 일정 확정

### 6단계: 멘토/버디 배정 및 체크인 루프
- 멘토의 역할과 기대치 명확화
- 주간 체크인 및 피드백 수집
- 문제 해결 및 지원 채널 안내

### 7단계: 피드백 및 30일 점검
- 초기 성과 리뷰 및 피드백 수집
- 추가 교육 필요 여부 판단
- 30일 목표 달성 여부 및 정착도 평가

## 체크리스트 템플릿
- 계정 생성 및 접근 권한 확인
- 오리엔테이션 참석 완료
- 멘토 배정 및 첫 주 체크인 수행
- 초기 과제 및 학습 자료 수령
- 팀 커뮤니케이션 채널 이해 및 사용 시작

## 기대 효과
- 빠른 적응 및 생산성 증가
- 명확한 역할 인식 및 책임 확립
- 건강한 피드백 문화 형성

## 위험 및 주의사항
- 계정 보안 및 접근권한 관리
- 과도한 정보 제공으로 인한 정보 과부하 방지
- 멘토링 시간 관리 및 일정 조정

## 요약
- 신규 팀원이 도구 및 프로세스에 빠르게 익숙해진다.
- 역할과 기대치가 명확히 전달되어 초기 생산성을 높인다.
- 멘토링 및 피드백 루프를 통해 지속적인 적응을 지원한다.

## 결정 사항
- 온보딩 기간의 표준화 여부 및 기간 확정 필요
- 멘토/버디 배정 정책의 기준 및 수 설정 필요
- 초기 교육 커리큘럼의 범위와 승인 여부 결정 필요
- 계정 및 도구 접근 정책의 범위와 적용 시점 결정 필요
```

**판정**: route/action pass, 3개 항목 요약과 `결정 사항` section pass, grounding fail. 멘토·기간·교육·접근 정책은 입력에 결정 근거가 없는데 결정 사항으로 평서 배치되어 결정된 정책처럼 표현됐다.

### A-3

```text
A-3 raw result (model openai/gpt-5-nano; correction_history=[]):
route/action=markdown_create; confidence=0.0; edit_goal=create_from_chat; selected_skill_id=skill-onboarding; retrieval_source=none; document_operation=create; persist=false; required_capabilities=[document-create].
title: 팀 온보딩 절차 가이드
summary: 신규 팀원이 빠르게 역할에 적응하고 생산성을 높이도록 단계별 온보딩 프로세스를 설명한다.

# 팀 온보딩 절차 가이드

개요
- 본 문서는 신규 팀원이 팀에 합류했을 때 필요한 단계별 온보딩 절차를 정리한 가이드입니다. 목적은 빠른 적응과 생산성 확보입니다.

## 1. 목적 및 적용 범위
- 적용 대상: 모든 신규 입사자 및 팀 전환 구성원
- 목표: 팀 문화 이해, 역할 이해, 업무 도구 접근 및 초기 성과 달성

## 2. 온보딩 일정 개요
- Day 0: 환영 인사, 회사/팀 소개, 계정 및 권한 발급
- Week 1: 팀 구조 이해, 역할 및 프로젝트 소개, 초기 학습 과제 배정
- Week 2: 초기 업무 배정 및 첫 피드백 수렴
- Month 1: 정식 산출물 검토 및 추가 교육 계획 수립

## 3. 준비 단계
- 담당자 지정: 멘토/버디, 팀 리더
- 필요한 문서 및 링크 공유: 위키/정책 문서, 보안 가이드, 업무 프로세스 매뉴얼
- 오리엔테이션 일정 확정 및 안내

## 4. 환영 및 오리엔테이션
- 팀 소개 및 회사 문화, 핵심 가치 설명
- 규칙, 정책, 보안 원칙 개요

## 5. 접근 권한 및 도구 설정
- 기본 계정 발급: 이메일, 협업 도구, 저장소 접근
- 보안 정책 안내 및 데이터 취급 원칙 설명
- 초기 학습 자료 및 샘플 프로젝트 제공

## 6. 역할 및 프로젝트 소개
- 팀의 목표, 현재 진행 중인 프로젝트, 역할별 책임 공유
- 초기 업무 예시 및 샘플 태스크 제시

## 7. 멘토/버디 제도
- 1:1 매칭 및 주간 체크인
- 질문 창구 및 빠른 지원 채널 안내

## 8. 피드백 및 평가 일정
- 1주 차 피드백: 자가 평가 및 팀 피드백
- 2주 차 점검: 진도 확인 및 필요 지원 파악
- 4주 차 평가: 온보딩 목표 달성 여부 검토

## 9. 문서 및 자료 저장 위치
- 내부 위키, 정책 매뉴얼, 프로젝트 문서의 위치 안내
- 검색 키워드 및 접근 방법

## 10. 보안 및 정책 준수
- 보안 기본 규칙 및 중요 정책 요약
- 비밀정보 취급 및 접근 권한 관리 원칙

## 11. 이슈 및 지원 채널
- IT/보안 지원 채널 안내
- 팀 리더 및 멘토의 역할 재확인

## 마무리
- 이 문서는 제안된 온보딩 프로세스의 예시이며, 조직별 필요에 따라 조정될 수 있습니다.

---

## 핵심 요약
- 신규 온보딩 일정과 책임자 명확화가 핵심이다.
- 접근 권한 및 도구 설정의 신속한 처리와 자료 위치 안내가 중요하다.
- 멘토링과 피드백의 주기적 관리가 지속적 성공의 열쇠이다.

## 결정 필요
- 본 문서는 제안서이며, 도구 도입이나 정책 변경 등 구체적 결정이 필요한 부분이 있을 수 있다. 결정은 경영진의 검토 후 확정한다.
```

**판정**: route/action pass, 본문 뒤 3개 요약 의미 pass, grounding pass. 제안·향후 검토·확정으로 표시해 근거 없는 결정을 확정하지 않았지만 기존 Skill fixture의 별도 `결정 사항` section을 `결정 필요`로 바꾸어 strict 형식 보존은 fail이다.

## B 폴더 정리 raw plan JSON 전문

### B-1

```text
B-1 raw result (model openai/gpt-5-nano; correction_history=[]):
route: {"action":"folder_organize","confidence":0.92,"reason":"The user requests moving a document to an archive folder and renaming it. The 'quarterly-archive' skill provides folder-organize capabilities and matches the request.","edit_goal":null,"selected_skill_id":"skill-folder","retrieval_source":"none","document_operation":"none","persist":true,"required_capabilities":["folder-organize"]}
handle_result: {"action":"folder_organize","run_id":"run-1","run_status":"queued"}
plan JSON:
{
  "id": "plan-1",
  "run_id": "run-1",
  "version": 1,
  "summary": "현재까지 변경은 없으며, 아래 계획에 따라 문서를 보관 폴더로 옮긴 뒤 이름에 아카이브 접두사를 추가하는 작업은 승인 후에만 실행됩니다.",
  "operation_hash": "18bb4137f61d732335665db0616415eabb8801222713b4df1eea990b49b0ffd8",
  "status": "awaiting_approval",
  "operations": [
    {
      "id": "plan-1-op-1",
      "sequence": 1,
      "tool_name": "move_document",
      "target_type": "document",
      "target_id": "doc-q1",
      "base_version": 2,
      "source_parent_id": "folder-active",
      "destination_parent_id": "archive",
      "arguments": {"document_id":"doc-q1","folder_id":"archive","position":0,"base_version":2},
      "reason": "분기 회고 문서를 보관 폴더로 이동하기 위함.",
      "depends_on": [],
      "status": "pending",
      "error_code": null
    },
    {
      "id": "plan-1-op-2",
      "sequence": 2,
      "tool_name": "rename_document",
      "target_type": "document",
      "target_id": "doc-q1",
      "base_version": 2,
      "source_parent_id": null,
      "destination_parent_id": null,
      "arguments": {"document_id":"doc-q1","display_name":"아카이브 분기 회고 문서","base_version":{"$operation_result":"plan-1-op-1","field":"current_version"}},
      "reason": "아카이브 접두사를 문서 이름에 추가하기 위함.",
      "depends_on": ["plan-1-op-1"],
      "status": "pending",
      "error_code": null
    }
  ]
}
```

**판정**: route/action `folder_organize`, status `awaiting_approval`, `move_document` → `rename_document`, destination/name/ID/base-version dependency 모두 일치한다. summary가 변경 없음과 승인 후 실행을 명시하고 read-only라고 부르지 않아 pass다.

### B-2

```text
B-2 raw result (model openai/gpt-5-nano; correction_history=[]):
route: {"action":"folder_organize","confidence":0.92,"reason":"분기 회고 문서를 보관 폴더로 옮기고 이름을 변경하는 폴더 조직 작업입니다.","edit_goal":null,"selected_skill_id":"skill-folder","retrieval_source":"none","document_operation":"none","persist":true,"required_capabilities":["folder-organize"]}
handle_result: {"action":"folder_organize","run_id":"run-2","run_status":"queued"}
plan JSON:
{
  "id": "plan-2",
  "run_id": "run-2",
  "version": 1,
  "summary": "아직 변경이 반영되지 않았으며, 아래에 나열된 작업은 승인 후에만 실행됩니다.",
  "operation_hash": "59603635087aa15a2e6519bdbcbb9158c356e65756959a59ba1a31abf64a470b",
  "status": "awaiting_approval",
  "operations": [
    {
      "id": "plan-2-op-1",
      "sequence": 1,
      "tool_name": "move_document",
      "target_type": "document",
      "target_id": "doc-q1",
      "base_version": 2,
      "source_parent_id": "folder-active",
      "destination_parent_id": "archive",
      "arguments": {"document_id":"doc-q1","folder_id":"archive","position":0,"base_version":2},
      "reason": "분기 회고 문서를 보관 폴더로 이동합니다.",
      "depends_on": [],
      "status": "pending",
      "error_code": null
    },
    {
      "id": "plan-2-op-2",
      "sequence": 2,
      "tool_name": "rename_document",
      "target_type": "document",
      "target_id": "doc-q1",
      "base_version": 2,
      "source_parent_id": null,
      "destination_parent_id": null,
      "arguments": {"document_id":"doc-q1","display_name":"아카이브 분기 회고 문서","base_version":{"$operation_result":"plan-2-op-1","field":"current_version"}},
      "reason": "이동된 문서의 이름에 아카이브 접두사를 붙여 보관용으로 명확히 표시합니다.",
      "depends_on": ["plan-2-op-1"],
      "status": "pending",
      "error_code": null
    }
  ]
}
```

**판정**: route/action `folder_organize`, status `awaiting_approval`, `move_document` → `rename_document`, destination/name/ID/base-version dependency 모두 일치한다. summary가 변경 없음과 승인 후 실행을 명시하고 read-only라고 부르지 않아 pass다.

### B-3

```text
B-3 raw result (model openai/gpt-5-nano; correction_history=[]):
route: {"action":"folder_organize","confidence":0.85,"reason":"User requested moving a document to an archive folder and renaming it; requires folder-organize capability from an available skill.","edit_goal":null,"selected_skill_id":"skill-folder","retrieval_source":"none","document_operation":"none","persist":true,"required_capabilities":["folder-organize"]}
handle_result: {"action":"folder_organize","run_id":"run-3","run_status":"queued"}
plan JSON:
{
  "id": "plan-3",
  "run_id": "run-3",
  "version": 1,
  "summary": "아직 변경은 적용되지 않았으며 아래의 두 작업은 승인 후에만 실행됩니다.",
  "operation_hash": "a78410ba97e81c998da2ffb99f65f41a1a9acfbfb43118084628373e4297adfc",
  "status": "awaiting_approval",
  "operations": [
    {
      "id": "plan-3-op-1",
      "sequence": 1,
      "tool_name": "move_document",
      "target_type": "document",
      "target_id": "doc-q1",
      "base_version": 2,
      "source_parent_id": "folder-active",
      "destination_parent_id": "archive",
      "arguments": {"document_id":"doc-q1","folder_id":"archive","position":0,"base_version":2},
      "reason": "문서를 보관 폴더로 이동합니다.",
      "depends_on": [],
      "status": "pending",
      "error_code": null
    },
    {
      "id": "plan-3-op-2",
      "sequence": 2,
      "tool_name": "rename_document",
      "target_type": "document",
      "target_id": "doc-q1",
      "base_version": 2,
      "source_parent_id": null,
      "destination_parent_id": null,
      "arguments": {"document_id":"doc-q1","display_name":"아카이브 분기 회고 문서","base_version":{"$operation_result":"plan-3-op-1","field":"current_version"}},
      "reason": "이동한 문서의 이름에 아카이브 접두사를 추가합니다.",
      "depends_on": ["plan-3-op-1"],
      "status": "pending",
      "error_code": null
    }
  ]
}
```

**판정**: route/action `folder_organize`, status `awaiting_approval`, `move_document` → `rename_document`, destination/name/ID/base-version dependency 모두 일치한다. summary가 변경 없음과 승인 후 실행을 명시하고 read-only라고 부르지 않아 pass다.

## 재실행의 해석 한계

이 후속 live는 여섯 raw 결과를 그대로 보존한 in-memory 평가이며, wrapper 오류·runner 내용 보정·retry 선택은 모두 없었다(`correction_history=[]` 6/6). 따라서 A-2의 근거성 실패와 A-3의 strict section 실패는 실제 출력에 대한 판정이고, B 3/3은 계획·라우팅·도구 계약의 통과다. 실제 DB·backend·object storage·승인 persistence가 실행되지 않았으므로 외부 저장 성공이나 실제 승인 권한을 증명하지 않는다.

# 실제 저장 Skill E2E 수정

## 수정 전

기존 Skill live 평가는 in-memory repository·gateway를 사용했으므로, 게시한 Skill을 Backend와 Pipeline이 같은 계약으로 읽고 명시적 승인 뒤 실제 문서를 영속 저장하는 경로는 검증하지 않았다.

## 수정 후

평가셋은 같은 사용자 요청을 no-Skill과 실제 게시한 stored-Skill에 각각 한 번 보낸 두 실행이다. 두 요청의 사용자 메시지는 완전히 같고 `correction_history=[]`도 동일하며, 의도한 차이는 Skill 선택뿐이다. 게시한 Skill의 정확한 instructions는 다음과 같다.

```text
SKILL_MARKER - 팀 온보딩
Skill applied: SKILL_MARKER
새 팀원이 첫날 절차를 따른다.
```

기대 capabilities는 `document-create`, 허용 도구는 `create_document`, `get_document_content`, `get_document_metadata`, `list_folder_children`, `list_root_items`다. 실제 publish가 성공했고 Backend GET과 Pipeline GET에서 instructions·capabilities·허용 도구가 모두 정확히 일치했다.

기대 동작은 no-Skill 문서에는 marker가 없고 stored-Skill 문서에는 정확한 제목·본문 marker가 있으며, 두 실행 모두 명시적 승인 뒤 `create_document`를 한 번 성공시키고 영속 상태를 조회할 수 있는 것이다. 실제 no-Skill 결과의 제목은 `팀 온보딩`, 본문은 `팀 온보딩 절차를 안내한다.`로 marker가 없었다. stored-Skill 결과의 제목은 `SKILL_MARKER - 팀 온보딩`이었고, provider 출력과 Backend content readback은 정확히 첫 줄 `Skill applied: SKILL_MARKER`, 빈 줄, `팀 온보딩 절차를 안내한다.`로 byte-for-byte 일치했다. instructions의 셋째 줄 `새 팀원이 첫날 절차를 따른다.`는 실제 Markdown에 포함되지 않았으므로 그 지시까지 따랐다고 판정하지 않는다.

두 실행 모두 승인 요청을 명시적으로 승인했고 plan은 `approved`, run은 `completed`, `create_document`는 `succeeded`였다. Backend/core의 영속 조회에서는 문서가 version/revision **1**, 일치하는 content hash와 함께 남았고 planning·execution job은 모두 `attempt_count=1`, tool execution도 `attempt=1`로 retry가 없었다. 따라서 실제 repository·API·승인·저장 경로에서 stored-Skill 적용 차이와 내구성 있는 문서 생성을 확인해 **통과**했다.

답변 생성에는 deterministic fake provider를 사용했다. 따라서 실제 모델의 문장 품질이나 비결정성은 증명하지 않지만, Skill 게시·두 서비스 readback·라우팅·승인·`create_document`·영속 조회는 실제 경로다. 비밀정보 검사도 통과했으며 이 보고서에는 일회성 식별자, 로컬 산출물 위치, token·cookie·credential을 싣지 않는다.

# 별도 고정 템플릿 Skill 실험

## 실제 평가 입력

`신규 팀원 온보딩 계획을 작성해줘. 현재 메시지의 근거만 사용해.`라는 요청에 9월 2일 합류, 백엔드 개발자, 플랫폼 리드 멘토, 첫날 보안 교육·저장소와 개발 환경 설정, 첫 주 주문 API 수정·자동 테스트, 운영 환경 권한은 코드 리뷰 후 부여, 첫 주에는 읽기 권한만 제공이라는 사실을 넣고 첫 주 체크리스트 두 항목을 Markdown 체크박스로 작성하도록 했다. 입력 자체에 운영 환경 권한 조건과 첫 주 읽기 권한 제한이라는 결정 근거가 있으므로 결정 근거성은 3/3으로 판정한다.

## 실행 요약

- production `SelectSkillUseCase`, `HandleAgentTurnUseCase`, `GenerateMarkdownDocumentUseCase`, `build_markdown_editor`를 사용해 `openai/gpt-5-nano`로 독립 3회 실행했다.
- 실제 DB/backend/object storage는 사용하지 않았고, Skill repository·query·run starter만 메모리 stub으로 대체했다.
- 결과: 3/3 통과. 모든 회차에서 `routed_action=markdown_create`, `selected_skill_id=skill-template-onboarding`이었다.
- 최초 보정 전 오류는 각 raw JSON의 `correction_history`에 기록했다: `SkillNotFoundError: Skill not found: skill-template-before-fix` → 정확한 explicit Skill ID와 helper 결과로 재실행.

## 고정 템플릿 구조 보존 수정

### 수정 전

별도 고정 템플릿 Skill 실험 당시 Reference Markdown은 요청된 H1 1개, H2 6개와 첫날 번호 목록 2개, 첫 주 체크 목록 2개, 결정 bullet 2개만 포함했다. 당시 `extract_markdown_structure` 결과에서는 체크박스가 일반 목록과 같은 `[item]`으로 바뀌었다.

```markdown
# 신규 팀원 온보딩 계획
## 역할
## 합류일
## 멘토
## 첫날 일정
1. [item]
2. [item]
## 첫 주 체크리스트
- [item]
- [item]
## 결정 사항
- [item]
- [item]
```

`build_reference_template_instructions`의 당시 전체 결과는 `report.json`의 `build_reference_template_instructions_result`에 저장했다. 이 fixture에는 표가 없으므로 당시 live 결과로 표 본문 보존 여부를 판정하지 않았다.

### 수정 후

현재 `extract_markdown_structure`는 체크박스의 구조와 항목 수를 보존하고 완료 상태만 unchecked로 정규화한다. 따라서 같은 Reference Markdown의 첫 주 체크리스트는 다음처럼 추출된다.

```markdown
## 첫 주 체크리스트
- [ ] [item]
- [ ] [item]
```

표는 실제 셀 값을 노출하지 않고 header·separator와 본문 행·열 topology를 placeholder로 보존한다. `test_normalizes_checkbox_state_and_preserves_ordinary_list_structure`, `test_preserves_table_body_topology_without_cell_content`, escaped pipe·fence·outer pipe 변형 회귀 테스트가 이 동작을 확인하며, 관련 AI suite 결과는 **404 passed, 79 subtests passed**다. 별도 고정 템플릿 3회 live 평가는 수정 전 fixture 실행 기록이므로 수정 후 helper의 live 재평가로 확대하지 않는다.

## 1열 Markdown 표 구조 보존 수정

### 수정 전

다음 유효한 1열 표를 `extract_markdown_structure`에 넣으면 구조가 빈 문자열로 추출됐다.

```markdown
| 상태 |
| --- |
| 완료 |
```

### 수정 후

같은 입력에서 header와 separator를 유지하고 실제 본문 값 `완료`는 노출하지 않은 채 1열 body topology를 placeholder로 보존한다.

```markdown
| 상태 |
| --- |
|  |
```

1열 표의 본문 행 보존뿐 아니라 표가 아닌 단독 separator와 일반 pipe 문장을 표로 오인하지 않는 음성 경계도 함께 확인했다. Skill 관련 결과는 **112 passed, 2 subtests passed**다.

### 남은 조건

기존 별도 고정 템플릿 live 3회 fixture에는 표가 없었다. 따라서 이 결과는 helper와 회귀 테스트의 1열 구조 보존을 증명하지만, 1열 표가 포함된 실제 Skill live 생성 품질 전체를 증명하지 않는다.

## 회차별 결과 및 사람 검토

### 1회차

```markdown
# 신규 팀원 온보딩 계획

## 역할
백엔드 개발자

## 합류일
9월 2일

## 멘토
플랫폼 리드

## 첫날 일정
1. 10시 보안 교육
2. 14시 저장소와 개발 환경 설정

## 첫 주 체크리스트
- [ ] 첫 주에 주문 API 작은 수정
- [ ] 첫 주에 자동 테스트 추가

## 결정 사항
- 운영 환경 권한은 코드 리뷰 완료 후 부여
- 첫 주에는 읽기 권한만 제공
```

- 템플릿 구조 준수: 통과. 제목/섹션 순서가 정확하고 추가 H1/H2가 없으며 목록 개수가 각각 2개다.
- 사실 보존: 통과. 9개 입력 사실을 의미상 확인했다.
- 결정 사항 근거성: 통과. 두 결정은 입력 문장의 운영 권한 조건과 읽기 권한 제한을 그대로 반영한다.
- 새로 지어낸 정책/사실: 없음. `첫 주에`는 입력 사실을 문장으로 연결한 표현이다.
- 최종 이유: 모든 자동 guard가 통과했고 원문 예시 사실도 복사되지 않았다. elapsed 47.070초.

### 2회차

```markdown
# 신규 팀원 온보딩 계획

## 역할
백엔드 개발자

## 합류일
9월 2일

## 멘토
플랫폼 리드

## 첫날 일정
1. 10시 보안 교육
2. 14시 저장소와 개발 환경 설정

## 첫 주 체크리스트
- [ ] 주문 API 작은 수정
- [ ] 자동 테스트 추가

## 결정 사항
- 운영 환경 권한은 코드 리뷰 완료 후 부여
- 첫 주에는 읽기 권한만 제공
```

- 템플릿 구조 준수: 통과. 제목/섹션 순서와 2·2·2 목록 topology가 정확하다.
- 사실 보존: 통과. 9개 입력 사실을 의미상 확인했다.
- 결정 사항 근거성: 통과. 결정 bullet 두 개 모두 현재 요청의 직접 근거다.
- 새로 지어낸 정책/사실: 없음.
- 최종 이유: 모든 자동 guard가 통과했고 reference 예시 사실이 없다. elapsed 54.612초.

### 3회차

```markdown
# 신규 팀원 온보딩 계획

## 역할
백엔드 개발자

## 합류일
9월 2일

## 멘토
플랫폼 리드

## 첫날 일정
1. 10시 보안 교육
2. 14시 저장소와 개발 환경 설정

## 첫 주 체크리스트
- [ ] 주문 API에 대한 작은 수정
- [ ] 자동 테스트 추가

## 결정 사항
- 운영 환경 권한은 코드 리뷰 완료 후 부여
- 첫 주에는 읽기 권한만 제공
```

- 템플릿 구조 준수: 통과. 제목/섹션 순서와 모든 목록 개수가 정확하다.
- 사실 보존: 통과. 주문 API 문장에 조사만 추가됐고 9개 입력 사실의 의미는 보존됐다.
- 결정 사항 근거성: 통과. 두 bullet 모두 입력된 결정 근거에서만 작성됐다.
- 새로 지어낸 정책/사실: 없음.
- 최종 이유: 모든 자동 guard가 통과했고 reference 예시 사실이 없다. elapsed 44.350초.

## 자동 판정 항목

각 회차 JSON의 `guards`에 다음을 분리 저장했다: 제목/섹션 정확한 순서, 추가 H1/H2 없음, 첫날 번호 2개, 체크리스트 체크 항목 2개, 결정 bullet 2개, 9개 입력 사실 의미 보존, reference 예시 사실 미복사. 단순 substring 하나가 아니라 heading topology·목록 문법·항목 수를 구조적으로 확인하고, 사실은 항목별 의미 패턴으로 별도 판정했다.

원시 회차 파일: `repeat-1.json`, `repeat-2.json`, `repeat-3.json`
집계 파일: `report.json`

# 변경 이력 복원·재실행(Log)

## 무엇을 시험했나

변경 이력을 기록하고 복원하는 Log 흐름에서 기록 추가, 복원, 오래된 버전 차단, 멱등성, 테스트 격리를 확인했다. 인공지능 쪽 50개와 화면 쪽 25개는 현재 다시 실행할 수 있었던 비교 가능한 일부 집합이다. 원시 산출물에 개별 테스트 이름과 결과가 남아 있지 않아 어떤 개별 케이스였는지는 확인할 수 없다.

### Log 테스트 실행환경 수정

#### 수정 전

- Docker 실행: **195/204**
- Ryuk 환경 실패: **9개**

#### 수정 후

- Java 21 직접 실행: **204/204** (`204 tests, failures 0, errors 0, BUILD SUCCESSFUL in 20s`)
- Log AI guard: **29/29**

### Log 표시 이름 snapshot 통합 회귀 수정

#### 수정 전

표시 이름이 바뀌거나 삭제된 문서·페이지의 변경 이력이 당시 이름을 유지하는지는 단위 수준에서 다뤘지만, 여러 변경을 한 번에 저장하는 실제 PostgreSQL 경로의 고정 회귀 증거는 없었다.

#### 수정 후

첫 평가셋은 변경된 `page-a`, `page-b`와 중복으로 들어온 삭제 ID다. 기대 동작은 ID를 중복 조회하지 않고 변경마다 당시 표시 이름 snapshot을 저장하는 것이다. 실제로 unique ID **3개를 한 번 조회**했고 변경 **3건을 저장**해 **통과**했다.

두 번째 평가셋은 disposable PostgreSQL에서 문서와 페이지 이름을 바꾼 뒤 soft-delete하는 통합 fixture다. 기대 동작은 삭제 뒤에도 기존 Log가 변경 당시 이름을 보존하는 것이다. 실제 조회 결과는 각각 `Old Doc`, `Old Page`로 유지되어 **통과**했다. 이 결과에서 새 production defect는 발견되지 않았다.

한계는 정확한 통합 회귀가 아직 저장소에 커밋된 재현 가능한 artifact가 아니며, 이 검증도 전체 HTTP 요청 경로를 통과한 E2E가 아니라는 점이다.

## 실제 평가 입력

- 인공지능 경로: 기존 raw 보존 50개 테스트.
- 화면 경로: 기존 raw 보존 25개 테스트.
- Backend focused: 최종 PR #224 조합 HEAD `778e2ca0`, Java 21 직접 실행.
- 역사적 정확한 집합은 인공지능 87개, 화면 109개였다.

## 기대 동작

기록·복원·오래된 상태 차단·멱등성·격리가 각 테스트에서 유지되어야 한다.

## 실제 결과

| 경로 | 현재 실행 | 결과 | 역사 비교 |
| --- | ---: | ---: | --- |
| 인공지능 | 50 | **50/50** | 역사적 정확한 집합 87/87과 다른 일부 집합 |
| 화면 | 25 | **25/25** | 역사적 정확한 집합 109/109와 다른 일부 집합 |
| Backend focused | 204 | **204 tests, failures 0, errors 0, BUILD SUCCESSFUL in 20s** | 최종 PR #224 조합 HEAD `778e2ca0`, Java 21 직접 실행 |

## 왜 그렇게 판정했나

기존 raw 보존 실행의 AI 50개와 Frontend 25개는 모두 통과했고, Log AI guard는 **29/29**였다. 원시 산출물에 개별 테스트 이름이 보존되지 않아 각 수치가 어떤 케이스였는지는 확인할 수 없고, 역사적 정확한 집합의 87/87·109/109를 재현했다고 쓰지 않는다. Backend focused는 최종 PR #224 조합 HEAD `778e2ca0`에서 Java 21 직접 실행으로 **204 tests, failures 0, errors 0, BUILD SUCCESSFUL in 20s**였다. 별도 PostgreSQL fixture는 unique ID 조회 수·저장 change 수와 rename·soft-delete 후 snapshot을 직접 읽어 새 결함 없음으로 판정했다.

## 이 실험이 증명하지 못하는 것

역사적 정확한 집합의 현재 동작, 개별 케이스별 기능 범위, 그리고 인공지능·화면·Backend focused 밖의 전체 서비스 범위는 증명하지 않는다. 기존 raw 50/50·25/25와 Backend focused 204/204는 각각 제한된 실행 집합이므로 Log 기능 전체를 증명하지 않는다. 표시 이름 snapshot fixture도 커밋된 exact regression이나 full HTTP E2E가 아니다.

# 품질 점검 승격(Lint)

## 무엇을 시험했나

Lint가 편입 결과의 필수 사실과 허용된 원문 참조를 보존하는지 확인하는 평가다.

## 실제 평가 입력

production `PostgresWikiMaintenance.lint`에 `dry_run=True`로 실제 1회 실행했다. active clusters 19, source refs 15, promotion candidates 0, needs_review 0, relation candidates 14, invalid relations/promotions 0/0, reconciliation candidates/applied 0/0, materialized/merged 0/0, orphan links 0이었다. DB와 object storage 변경은 없었다. 이 dry-run은 현재 corpus 관찰값이며 기존 promotion page 생성 9회 및 MeaningClusterJudge 18회와 별도 판정이다. 기존 promotion page 생성은 정의·핵심 내용·citation·title/slug·구조를 9/9 통과했으며, Related Concepts 문자열은 LLM Wiki의 표현 변동 특성상 실패 기준이 아니다. 이 9회는 core selection 자체를 시험하지 않았지만 실제 Markdown 9개는 아래에 그대로 보존한다.

## 기대 동작

현재 입력과 현재 실행 결과가 있을 때 필수 사실·허용 원문 참조·승격 판정을 확인해야 한다.

## 실제 결과

| 구분 | 실행 수 | 결과 |
| --- | ---: | --- |
| production lint dry-run | 1 | 위 corpus 관찰값, DB/object storage 변경 없음 |
| 기존 promotion page 생성 | 9 | 정의·핵심 내용·citation·title/slug·구조 9/9; Related Concepts 문자열 변동은 실패 기준 아님 |
| MeaningClusterJudge live | 18 | 최초 expected 기준 10/18; 제품 실패율이 아니라 평가 expected와 production contract 불일치 |

### 기존 Lint typed relation의 Query 탐색 수정

#### 수정 전

평가셋은 기존 typed relation과 표시 전용·미지원 관계가 섞이고 `graph_link_limit=1`인 fixture다. 기대 동작은 Query에서 기존 typed relation만 고른 뒤 limit을 적용하는 것이지만, 기존 경로는 PostgreSQL `LIMIT` 또는 InMemory slice를 먼저 적용해 앞의 제외 관계가 자리를 차지하면 뒤의 유효 관계가 굶는 pre-LIMIT starvation이 발생할 수 있었다.

#### 수정 후

기존 typed relation whitelist를 PostgreSQL과 InMemory가 공유하고, 두 구현 모두 whitelist 필터를 먼저 적용한 뒤 `LIMIT`/slice를 적용한다. 탐색 허용 type은 기존 `source_mentions_concept`, `concept_related_to`와 `part_of`, `child_of`, `uses_or_depends_on`, `contrasts_with`, `supports_or_enables`의 **7개**다. generic/untyped `Related Concepts`는 제품 결정에 따라 Markdown 표시 전용으로 남았고 persisted edge로 저장하지 않았다. `related_evidence`, `unknown`도 탐색 대상에서 제외한다.

실제 혼합 fixture에서 `graph_link_limit=1`로 Query 탐색을 실행했을 때 앞의 제외 type이 slot을 차지하지 않았고 whitelist의 기존 typed relation **1개가 선택**되어 **통과**했다. 이 회귀는 탐색 type과 limit 순서를 증명한다. generic/untyped `Related Concepts`는 제품 결정상 표시 전용이므로 persisted typed edge로 materialize하지 않는다.

### Lint 승격·병합 page embedding 갱신 수정

#### 수정 전

평가셋은 Lint가 새 page를 승격하거나 기존 page를 병합해 DB/object storage를 쓴 경우다. 최초 수정 전에는 본문 저장 뒤 query embedding 갱신 요청이 없었다. 기존 수정은 commit 뒤 daemon thread를 시작했지만 `start()` 실패나 process 종료 시 이미 반영된 page의 재처리 대상을 복구할 영속 예약이 없었다.

#### 수정 후

기대 동작은 실제 변경된 promoted/merged page의 unique ID를 Lint DB transaction 안에서 영속 예약하고, commit 뒤 worker에 전달하며, dry-run 또는 변경 없음이면 예약·호출하지 않는 것이다. 실제 회귀에서 중복 ID는 한 번만 `pending`으로 예약됐고, 예약 뒤 worker `start()`가 실패해도 Lint 결과는 유지됐다. maintenance worker는 기동 시 `pending/failed` page를 PostgreSQL advisory lock 아래 회수하고 실패를 최대 3회 재시도한다. 생성 page의 citation은 `document:Bxxxx` 형식을 그대로 보존했다. `wiki_ingestion` 결과는 **169 passed, 1 skipped**로 **통과**했다.

#### 남은 한계

별도 queue table은 추가하지 않고 기존 `wiki_page_embeddings.status`를 재처리 예약으로 재사용했다. 따라서 daemon process가 종료돼도 예약은 남아 다음 maintenance worker 기동에서 회수되지만, 지속적인 별도 queue consumer와 지수 backoff는 없다. BGE-M3가 1GiB를 넘는 메모리를 요구하는 배포 한계도 남는다. 이 회귀는 예약·회수·재시도와 reference 보존을 검증한 것이며, 실제 BGE semantic live retrieval의 성공까지 증명하지 않는다.

## 왜 그렇게 판정했나

기존 promotion page 9회는 core selection을 호출하지 않고 생성 결과의 표면 계약만 확인했다. 따라서 Related Concepts 문자열 변동은 LLM Wiki 특성상 실패 기준이 아니며, 기존의 의미 실패 집계나 relation hint 불일치에 근거한 실패 판정은 적용하지 않는다. MeaningClusterJudge 18회는 production이 `core_concept`를 입력으로 받지 않는 상태에서 실행한 cluster match·target·promotion 경계 평가다. 양성은 cluster match와 target ID가 9/9이고, 비-core 입력의 `promotion_status=none`은 8/9로 현 계약상 정상이며, 1/9 `candidate`는 false promotion 가능성이다. 음성은 `promotion_status=none` 9/9로 promotion 경계만 통과했으며 cluster decision 자체의 품질을 입증하지 않는다. 진짜 core concept miss는 시험되지 않았다. typed relation은 shared whitelist 선필터와 limit 1 mutation으로, embedding은 unique-ID job 호출 수·dry/no-change 무호출·reference 보존으로 각각 별도 통과 판정했다.

## 이 실험이 증명하지 못하는 것

dry-run 관찰값은 실제 수정을 증명하지 않는다. 기존 promotion page 9회는 core selection이나 일반적인 의미 품질을 증명하지 않으며, MeaningClusterJudge 10/18은 제품 실패율이 아니다. `core_concept` 또는 `promotion_eligible=true`인 별도 promotion-stage 입력이 없었으므로 진짜 core concept miss를 평가하지 않았다. 음성 9/9도 cluster decision 품질이나 전체 Lint 품질을 증명하지 않는다. typed relation 회귀는 새 type 자동 추론을, embedding 회귀는 실제 BGE semantic live retrieval이나 1GiB 배포 가능성을 증명하지 않는다.

## Lint 회차별 최종 promotion Markdown 전문(실제 9개 보존)

### back-emf-cluster-current run 1

- 기대 동작: 역기전력 (Back EMF) / `back-emf-cluster-current`; refs: ['doc_motor:B0001', 'doc_motor:B0002']
- 표면 계약 판정: 정의·핵심 내용·citation·title/slug·구조 통과. Related Concepts 문자열은 LLM Wiki 특성상 변동 가능하며 실패 기준이 아니다. 이 실행은 core selection을 시험하지 않았다.
- 실제 Related Concepts: ['back-emf', 'motor-speed']

```markdown
---
type: concept
slug: back-emf-cluster-current
sources: doc_motor
mention_count: 2
importance_score: 0.7
generated_by: llm_promotion_materialization
llm_confidence: 0.88
---

# 역기전력 (Back EMF)

## Definition
역기전력(Back EMF)은 회전하는 전동기 코일에 운동에 의해 유도되는 전압이다. [doc_motor:B0001]

## Why It Matters
Promotion cluster에서 독립 concept 후보로 판단된 항목이다.

## Key Points
- 역기전력은 회전하는 전동기 코일에 유도된다. [doc_motor:B0001]
- 일반적으로 역기전력의 크기는 회전자 속도에 비례하는 경향이 있다. [doc_motor:B0002]

## Aliases
-

## Evidence
- 회전하는 전동기 코일에는 운동에 의해 역기전력이 유도된다. [doc_motor:B0001]
- 이상적인 조건에서 역기전력은 회전자 속도에 비례한다. [doc_motor:B0002]

## Related Concepts
- [[back-emf|back-emf]]
- [[motor-speed|motor-speed]]

## Reference Summary
- display refs: doc_motor:B0001, doc_motor:B0002
- promoted_from: cluster:back-emf-cluster-current

```

### back-emf-cluster-current run 2

- 기대 동작: 역기전력 (Back EMF) / `back-emf-cluster-current`; refs: ['doc_motor:B0001', 'doc_motor:B0002']
- 표면 계약 판정: 정의·핵심 내용·citation·title/slug·구조 통과. Related Concepts 문자열은 LLM Wiki 특성상 변동 가능하며 실패 기준이 아니다. 이 실행은 core selection을 시험하지 않았다.
- 실제 Related Concepts: ['back-emf', 'motor-speed', 'emf-principle']

```markdown
---
type: concept
slug: back-emf-cluster-current
sources: doc_motor
mention_count: 2
importance_score: 0.7
generated_by: llm_promotion_materialization
llm_confidence: 0.85
---

# 역기전력 (Back EMF)

## Definition
역기전력은 회전하는 전동기의 코일에 운동에 의해 유도되는 전압이다. 일반적으로 전동기의 속도가 높아질수록 역기전력의 크기도 커진다. [doc_motor:B0001, doc_motor:B0002]

## Why It Matters
Promotion cluster에서 독립 concept 후보로 판단된 항목이다.

## Key Points
- 역기전력은 회전하는 전동기 코일에 운동에 의해 유도된다. [doc_motor:B0001]
- 역기전력은 일반적으로 회전자 속도에 비례하며 속도가 증가하면 크기가 증가하는 경향이 있다. [doc_motor:B0002]

## Aliases
-

## Evidence
- 회전하는 전동기 코일에는 운동에 의해 역기전력이 유도된다. [doc_motor:B0001]
- 이상적인 조건에서 역기전력은 회전자 속도에 비례한다. [doc_motor:B0002]

## Related Concepts
- [[back-emf|back-emf]]
- [[motor-speed|motor-speed]]
- [[emf-principle|emf-principle]]

## Reference Summary
- display refs: doc_motor:B0001, doc_motor:B0002
- promoted_from: cluster:back-emf-cluster-current

```

### back-emf-cluster-current run 3

- 기대 동작: 역기전력 (Back EMF) / `back-emf-cluster-current`; refs: ['doc_motor:B0001', 'doc_motor:B0002']
- 표면 계약 판정: 정의·핵심 내용·citation·title/slug·구조 통과. Related Concepts 문자열은 LLM Wiki 특성상 변동 가능하며 실패 기준이 아니다. 이 실행은 core selection을 시험하지 않았다.
- 실제 Related Concepts: ['back-emf']

```markdown
---
type: concept
slug: back-emf-cluster-current
sources: doc_motor
mention_count: 2
importance_score: 0.7
generated_by: llm_promotion_materialization
llm_confidence: 0.8
---

# 역기전력 (Back EMF)

## Definition
역기전력(Back EMF)은 회전하는 전동기의 운동으로 코일에 유도되는 전압이다. [doc_motor:B0001]

## Why It Matters
Promotion cluster에서 독립 concept 후보로 판단된 항목이다.

## Key Points
- 전동기 속도가 증가하면 역기전력의 크기도 커지는 경향이 있다. [doc_motor:B0002]

## Aliases
-

## Evidence
- 회전하는 전동기 코일에는 운동에 의해 역기전력이 유도된다. [doc_motor:B0001]
- 이상적인 조건에서 역기전력은 회전자 속도에 비례한다. [doc_motor:B0002]

## Related Concepts
- [[back-emf|back-emf]]

## Reference Summary
- display refs: doc_motor:B0001, doc_motor:B0002
- promoted_from: cluster:back-emf-cluster-current

```

### idempotency-key-cluster-current run 1

- 기대 동작: 멱등성 키 (Idempotency Key) / `idempotency-key-cluster-current`; refs: ['doc_api:B0003', 'doc_api:B0004']
- 표면 계약 판정: 정의·핵심 내용·citation·title/slug·구조 통과. Related Concepts 문자열은 LLM Wiki 특성상 변동 가능하며 실패 기준이 아니다. 이 실행은 core selection을 시험하지 않았다.
- 실제 Related Concepts: ['idempotency-key', 'server-side-idempotency', 'payment-retry']

```markdown
---
type: concept
slug: idempotency-key-cluster-current
sources: doc_api
mention_count: 2
importance_score: 0.7
generated_by: llm_promotion_materialization
llm_confidence: 0.8
---

# 멱등성 키 (Idempotency Key)

## Definition
멱등성 키는 동일한 결제 요청을 재시도해도 한 번만 처리되도록 식별한다. 서버는 이미 처리한 멱등성 키의 결과를 재사용해 중복 부작용을 줄일 수 있다. [doc_api:B0003, doc_api:B0004]

## Why It Matters
Promotion cluster에서 독립 concept 후보로 판단된 항목이다.

## Key Points
- 멱등성 키는 각 결제 요청마다 고유하게 부여되어 재시도를 구분한다. [doc_api:B0003]
- 서버는 완료된 키를 조회해 같은 결과를 반환해 중복 부작용을 줄인다. [doc_api:B0004]

## Aliases
-

## Evidence
- 클라이언트는 결제 요청마다 멱등성 키를 보낸다. [doc_api:B0003]
- 서버는 완료된 키를 조회해 같은 결과를 반환할 수 있다. [doc_api:B0004]

## Related Concepts
- [[idempotency-key|idempotency-key]]
- [[server-side-idempotency|server-side-idempotency]]
- [[payment-retry|payment-retry]]

## Reference Summary
- display refs: doc_api:B0003, doc_api:B0004
- promoted_from: cluster:idempotency-key-cluster-current

```

### idempotency-key-cluster-current run 2

- 기대 동작: 멱등성 키 (Idempotency Key) / `idempotency-key-cluster-current`; refs: ['doc_api:B0003', 'doc_api:B0004']
- 표면 계약 판정: 정의·핵심 내용·citation·title/slug·구조 통과. Related Concepts 문자열은 LLM Wiki 특성상 변동 가능하며 실패 기준이 아니다. 이 실행은 core selection을 시험하지 않았다.
- 실제 Related Concepts: ['idempotency-key', 'payment-api']

```markdown
---
type: concept
slug: idempotency-key-cluster-current
sources: doc_api
mention_count: 2
importance_score: 0.7
generated_by: llm_promotion_materialization
llm_confidence: 0.85
---

# 멱등성 키 (Idempotency Key)

## Definition
멱등성 키(Idempotency Key)는 클라이언트가 결제 요청마다 고유하게 생성해 서버로 전송하는 식별자이다. 같은 멱등성 키를 사용해 재시도된 요청은 중복 처리를 방지하기 위해 한 번만 처리되며, 서버는 이미 처리된 키의 결과를 재사용해 중복 부작용을 줄일 수 있다. [doc_api:B0003, doc_api:B0004]

## Why It Matters
Promotion cluster에서 독립 concept 후보로 판단된 항목이다.

## Key Points
- 클라이언트는 매 결제 요청마다 멱등성 키를 전송한다. [doc_api:B0003]
- 서버는 이미 처리된 멱등성 키의 결과를 재사용해 중복 부작용을 줄일 수 있다. [doc_api:B0004]
- 멱등성 키를 이용하면 재시도 시 동일한 결과를 반환하고 부작용을 최소화한다. [doc_api:B0003, doc_api:B0004]

## Aliases
-

## Evidence
- 클라이언트는 결제 요청마다 멱등성 키를 보낸다. [doc_api:B0003]
- 서버는 완료된 키를 조회해 같은 결과를 반환할 수 있다. [doc_api:B0004]

## Related Concepts
- [[idempotency-key|idempotency-key]]
- [[payment-api|payment-api]]

## Reference Summary
- display refs: doc_api:B0003, doc_api:B0004
- promoted_from: cluster:idempotency-key-cluster-current

```

### idempotency-key-cluster-current run 3

- 기대 동작: 멱등성 키 (Idempotency Key) / `idempotency-key-cluster-current`; refs: ['doc_api:B0003', 'doc_api:B0004']
- 표면 계약 판정: 정의·핵심 내용·citation·title/slug·구조 통과. Related Concepts 문자열은 LLM Wiki 특성상 변동 가능하며 실패 기준이 아니다. 이 실행은 core selection을 시험하지 않았다.
- 실제 Related Concepts: ['idempotency-key', 'payment-idempotency']

```markdown
---
type: concept
slug: idempotency-key-cluster-current
sources: doc_api
mention_count: 2
importance_score: 0.7
generated_by: llm_promotion_materialization
llm_confidence: 0.8
---

# 멱등성 키 (Idempotency Key)

## Definition
멱등성 키(Idempotency Key)는 클라이언트가 각 결제 요청마다 고유한 키를 전송하고, 서버는 이미 처리된 키의 결과를 재사용하거나 완료된 키를 조회해 같은 결과를 반환함으로써 요청의 중복 처리를 보장하는 메커니즘이다. [doc_api:B0003, doc_api:B0004]

## Why It Matters
Promotion cluster에서 독립 concept 후보로 판단된 항목이다.

## Key Points
- 클라이언트는 결제 요청마다 멱등성 키를 전송한다. [doc_api:B0003]
- 서버는 이미 처리된 멱등성 키의 결과를 재사용해 중복 부작용을 줄인다. [doc_api:B0004]
- 완료된 키를 조회해 동일한 결과를 반환할 수 있다. [doc_api:B0004]

## Aliases
-

## Evidence
- 클라이언트는 결제 요청마다 멱등성 키를 보낸다. [doc_api:B0003]
- 서버는 완료된 키를 조회해 같은 결과를 반환할 수 있다. [doc_api:B0004]

## Related Concepts
- [[idempotency-key|idempotency-key]]
- [[payment-idempotency|payment-idempotency]]

## Reference Summary
- display refs: doc_api:B0003, doc_api:B0004
- promoted_from: cluster:idempotency-key-cluster-current

```

### manufacturing-tolerance-cluster-current run 1

- 기대 동작: 제조 공차 (Manufacturing Tolerance) / `manufacturing-tolerance-cluster-current`; refs: ['doc_quality:B0005', 'doc_quality:B0006']
- 표면 계약 판정: 정의·핵심 내용·citation·title/slug·구조 통과. Related Concepts 문자열은 LLM Wiki 특성상 변동 가능하며 실패 기준이 아니다. 이 실행은 core selection을 시험하지 않았다.
- 실제 Related Concepts: ['tolerance-analysis']

```markdown
---
type: concept
slug: manufacturing-tolerance-cluster-current
sources: doc_quality
mention_count: 2
importance_score: 0.7
generated_by: llm_promotion_materialization
llm_confidence: 0.9
---

# 제조 공차 (Manufacturing Tolerance)

## Definition
제조 공차는 도면이 기준 치수 주변에 허용 가능한 치수 변동을 지정하는 허용 한도다. [doc_quality:B0005]

## Why It Matters
Promotion cluster에서 독립 concept 후보로 판단된 항목이다.

## Key Points
- 제조 공차는 부품의 실제 치수가 목표 치수에서 벗어날 수 있는 허용 범위를 정의한다. [doc_quality:B0005]
- 공차 누적은 조립품의 간극과 동작 성능에 영향을 줄 수 있다. [doc_quality:B0006]

## Aliases
-

## Evidence
- 도면은 기준 치수 주변에 허용 가능한 치수 변동을 제조 공차로 지정한다. [doc_quality:B0005]
- 여러 부품의 공차가 누적되면 조립품의 간극과 동작 성능이 달라질 수 있다. [doc_quality:B0006]

## Related Concepts
- [[tolerance-analysis|tolerance-analysis]]

## Reference Summary
- display refs: doc_quality:B0005, doc_quality:B0006
- promoted_from: cluster:manufacturing-tolerance-cluster-current

```

### manufacturing-tolerance-cluster-current run 2

- 기대 동작: 제조 공차 (Manufacturing Tolerance) / `manufacturing-tolerance-cluster-current`; refs: ['doc_quality:B0005', 'doc_quality:B0006']
- 표면 계약 판정: 정의·핵심 내용·citation·title/slug·구조 통과. Related Concepts 문자열은 LLM Wiki 특성상 변동 가능하며 실패 기준이 아니다. 이 실행은 core selection을 시험하지 않았다.
- 실제 Related Concepts: ['tolerance-analysis', 'manufacturing-tolerance']

```markdown
---
type: concept
slug: manufacturing-tolerance-cluster-current
sources: doc_quality
mention_count: 2
importance_score: 0.7
generated_by: llm_promotion_materialization
llm_confidence: 0.8
---

# 제조 공차 (Manufacturing Tolerance)

## Definition
제조 공차는 도면에 표시된 기준 치수 주변에 허용 가능한 치수 변동을 지정하는 오차의 범위이다. [doc_quality:B0005]

## Why It Matters
Promotion cluster에서 독립 concept 후보로 판단된 항목이다.

## Key Points
- 제조 공차는 부품의 실제 치수가 목표 치수에서 벗어날 수 있는 허용 범위를 정의한다. [doc_quality:B0005]
- 공차 누적은 조립품의 간극과 동작 성능에 영향을 줄 수 있다. [doc_quality:B0006]

## Aliases
-

## Evidence
- 도면은 기준 치수 주변에 허용 가능한 치수 변동을 제조 공차로 지정한다. [doc_quality:B0005]
- 여러 부품의 공차가 누적되면 조립품의 간극과 동작 성능이 달라질 수 있다. [doc_quality:B0006]

## Related Concepts
- [[tolerance-analysis|tolerance-analysis]]
- [[manufacturing-tolerance|manufacturing-tolerance]]

## Reference Summary
- display refs: doc_quality:B0005, doc_quality:B0006
- promoted_from: cluster:manufacturing-tolerance-cluster-current

```

### manufacturing-tolerance-cluster-current run 3

- 기대 동작: 제조 공차 (Manufacturing Tolerance) / `manufacturing-tolerance-cluster-current`; refs: ['doc_quality:B0005', 'doc_quality:B0006']
- 표면 계약 판정: 정의·핵심 내용·citation·title/slug·구조 통과. Related Concepts 문자열은 LLM Wiki 특성상 변동 가능하며 실패 기준이 아니다. 이 실행은 core selection을 시험하지 않았다.
- 실제 Related Concepts: ['manufacturing-tolerance', 'tolerance-analysis']

```markdown
---
type: concept
slug: manufacturing-tolerance-cluster-current
sources: doc_quality
mention_count: 2
importance_score: 0.7
generated_by: llm_promotion_materialization
llm_confidence: 0.85
---

# 제조 공차 (Manufacturing Tolerance)

## Definition
제조 공차는 부품의 실제 치수가 목표 치수에서 벗어날 수 있는 허용 범위다. [doc_quality:B0005]

## Why It Matters
Promotion cluster에서 독립 concept 후보로 판단된 항목이다.

## Key Points
- 도면은 기준 치수 주변에 허용 가능한 치수 변동을 제조 공차로 지정한다. [doc_quality:B0005]
- 공차 누적은 조립품의 간극과 동작 성능에 영향을 줄 수 있다. [doc_quality:B0006]

## Aliases
-

## Evidence
- 도면은 기준 치수 주변에 허용 가능한 치수 변동을 제조 공차로 지정한다. [doc_quality:B0005]
- 여러 부품의 공차가 누적되면 조립품의 간극과 동작 성능이 달라질 수 있다. [doc_quality:B0006]

## Related Concepts
- [[manufacturing-tolerance|manufacturing-tolerance]]
- [[tolerance-analysis|tolerance-analysis]]

## Reference Summary
- display refs: doc_quality:B0005, doc_quality:B0006
- promoted_from: cluster:manufacturing-tolerance-cluster-current

```

## MeaningClusterJudge 18회 입력·expected·실제 판정

이번 live 평가는 양성 3개와 음성 3개 fixture를 각 3회씩 같은 입력으로 호출했다. production `MeaningClusterJudge`의 역할은 core concept를 고르는 것이 아니라 incoming evidence claim을 기존 cluster에 합칠지 판단하는 것이므로, 양성 fixture의 `same_cluster`와 target ID는 별도로 확인하고 promotion은 production contract에 맞는지 분리해 해석한다. 아래 표의 `raw → normalized`는 각 회차의 raw LLM decision과 production normalization 결과에서 `decision / target_cluster_id / promotion_status`를 그대로 옮겼다. 음성 expected는 promotion만 `none`이며 `decision`과 target ID는 expected에 포함되지 않았다.

| fixture·고정 입력 목적 | expected (매 회차) | 1회차 실제 raw → normalized | 2회차 실제 raw → normalized | 3회차 실제 raw → normalized | 최초 expected 기준 |
| --- | --- | --- | --- | --- | --- |
| `positive_back_emf` — 입력: `evidence_item` “회전 역기전력”, ref `motor-validation:sec-5`; 기존 `back-emf` cluster와 같은 의미인지와 승격 경계를 확인 | `{"decision":"same_cluster","target_cluster_id":"back-emf","promotion_status":"candidate"}` | `same_cluster / back-emf / none` → `same_cluster / back-emf / none` | `same_cluster / back-emf / none` → `same_cluster / back-emf / none` | `same_cluster / back-emf / none` → `same_cluster / back-emf / none` | 0/3 |
| `positive_idempotency_key` — 입력: `section_candidate` “재시도 멱등 키”, ref `order-api-validation:sec-6`; 기존 `idempotency-key` cluster와 같은 의미인지와 승격 경계를 확인 | `{"decision":"same_cluster","target_cluster_id":"idempotency-key","promotion_status":"candidate"}` | `same_cluster / idempotency-key / none` → `same_cluster / idempotency-key / none` | `same_cluster / idempotency-key / none` → `same_cluster / idempotency-key / none` | `same_cluster / idempotency-key / none` → `same_cluster / idempotency-key / none` | 0/3 |
| `positive_manufacturing_tolerance` — 입력: `mention` “제조 공차 범위”, ref `assembly-audit:sec-8`; 기존 `manufacturing-tolerance` cluster와 같은 의미인지와 승격 경계를 확인 | `{"decision":"same_cluster","target_cluster_id":"manufacturing-tolerance","promotion_status":"candidate"}` | `same_cluster / manufacturing-tolerance / none` → `same_cluster / manufacturing-tolerance / none` | `same_cluster / manufacturing-tolerance / none` → `same_cluster / manufacturing-tolerance / none` | `same_cluster / manufacturing-tolerance / candidate` → `same_cluster / manufacturing-tolerance / candidate` | 1/3 |
| `negative_first_single_claim` — 입력: `evidence_item` “격리 임대 계약”, ref `ops-experiment:sec-9`; 단일 claim·단일 source 새 cluster의 승격 금지 확인 | `{"promotion_status":"none"}` | `new_cluster / isolation-lease-contract / none` → `new_cluster / isolation-lease-contract / none` | `new_cluster / isolated-lease-contract / none` → `new_cluster / isolated-lease-contract / none` | `new_cluster / isolated-lease-contract / none` → `new_cluster / isolated-lease-contract / none` | 3/3 |
| `negative_one_off_tool` — 입력: `mention` “ThermoTrace Pro”, ref `heat-treatment-log:sec-1`; 한 source의 일회성 도구 승격 금지 확인 | `{"promotion_status":"none"}` | `new_cluster / lab-instrument-thermotrace-pro / none` → `new_cluster / lab-instrument-thermotrace-pro / none` | `new_cluster / measurement-instrument / none` → `new_cluster / measurement-instrument / none` | `new_cluster / in-house-temperature-measurement-tools / none` → `new_cluster / in-house-temperature-measurement-tools / none` | 3/3 |
| `negative_isolated_metric` — 입력: `section_candidate` “실험 창 지연률”, ref `prototype-bench:sec-11`; 고립된 단일 parameter/metric 승격 금지 확인 | `{"promotion_status":"none"}` | `new_cluster / experiment-window-latency-rate / none` → `new_cluster / experiment-window-latency-rate / none` | `new_cluster / experiment-window-latency / none` → `new_cluster / experiment-window-latency / none` | `new_cluster / experiment-window-latency-rate / none` → `new_cluster / experiment-window-latency-rate / none` | 3/3 |

따라서 최초 expected 전체 필드 점수는 10/18이다. 그러나 production MeaningClusterJudge는 `core_concept`를 받지 않으므로 양성 cluster match 9/9와 target ID 9/9는 통과했고, 비-core 입력의 `none` 8/9는 현 계약상 정상이다. 양성 `candidate` 1/9는 false promotion 가능성으로 남으며, 음성 `none` 9/9는 promotion 경계만 통과한 결과다. 진짜 core concept miss는 이 18회에서 시험되지 않았고, 별도 promotion-stage fixture가 필요하다.

## 검증된 고도화 후보

아래에는 아직 남은 후속 후보만 기록한다. 기존 Lint typed relation의 Query 탐색, distinct facet fixture, 실제 저장 Skill E2E, Skill checkbox·표 topology, 온보딩 결정 표현과 folder 승인 문구는 완료됐으므로 미해결 후보에서 제거했다. generic/untyped `Related Concepts`는 제품 결정상 표시 전용으로 유지한다.

| 우선순위 | 항목 | 현재 판정과 최소 후속 범위 |
| --- | --- | --- |
| fixture 우선 | Ingest benchmark gold/core fixture | source별 gold facet과 실제 core promotion-stage 입력을 benchmark·evaluator 계약에 명시한다. 일반 ingest의 concept 개수나 prompt를 강제하는 production 결함으로 확대하지 않는다. |
| 평가 인프라 | Log 표시 이름 snapshot 재현 artifact | 현재 PostgreSQL 통합 실행에서 결함은 없었지만, 같은 rename·soft-delete와 unique-ID lookup을 저장소에 커밋된 exact regression으로 남겨 반복 실행 가능하게 할지는 별도 결정한다. full HTTP E2E가 필요할 때만 범위를 넓힌다. |

# 최종 판단과 한계

## 무엇을 시험했나

현재 복구 가능한 입력과 결과를 기준으로 편입, 질의 검색·근거·답변, Agent, Skill, Log, Lint를 분리해 재평가했다.

## 실제 평가 입력

편입은 짧은 3개 문서·장문 1개·자연스러운 줄글 3개다. 질의는 검색 18개·근거 77쪽·답변 스트레스 18회, 복합 조사·실제 hybrid·distinct facet fixture, production BGE-M3 교차언어 6행과 제품 E2E 2건이다. Agent는 21회다. Skill은 라우팅·분류 32회, 기존 일반 적용 9회, 후속 live A/B 각 3회, 동일 요청 no-Skill/stored-Skill 영속 E2E, 고정 템플릿 3회와 1열 표 회귀다. Log는 기존 raw 75회·AI guard 29/29·Backend focused 204 tests와 표시 이름 snapshot PostgreSQL 통합 fixture다. Lint는 dry-run 1회·promotion page 9회·MeaningClusterJudge 18회, typed relation pre-LIMIT mutation과 승격·병합 embedding 회귀다.

## 기대 동작

각 실험은 위에 적은 고유한 통과 조건을 만족해야 하며, 서로 다른 평가 묶음의 수치를 합쳐 하나의 품질 점수로 해석하지 않는다.

## 실제 결과

편입의 구조 계약은 짧은 입력 9/9, 장문 3/3이고 새 줄글은 자동 평가·원문 참조·기계 guard 9/9, 당시 독립 의미 판정 7/9였다. `concept_related_slugs` 0/9는 핵심 의미 실패가 아니며 최종 Markdown 관계는 미캡처다. 완료된 AI 관련 suite는 **404 passed, 79 subtests passed**, 직접 변경 범위는 **102 passed, 4 subtests passed**다. 최신 Query 전체는 **141 passed, 19 subtests passed**다. `문서에서는`은 `문서`로 한 번만 조사 제거됐고 짧은 `나에서는`·`가에서는`은 보존됐다. 실제 hybrid fixture는 BM25 `[1,0]`, dense target/distractor **0.80/0.95**, hybrid **0.84/0.76**으로 `doc_target:B0001`을 선택·인용했다. distinct facet 질문은 `doc-config:B0001`, `doc-incident:B0002`를 모두 선택·인용했다. 교차언어 제품 E2E는 **2/2**였다. Agent는 21/21이다. Skill 라우팅은 32/32, 기존 표면 계약은 9/9, 후속 A는 strict 1/3·route 3/3·grounding 2/3, B는 3/3, 고정 템플릿은 3/3, 1열 표는 **112 passed, 2 subtests passed**다. 실제 저장 Skill E2E는 게시한 instructions·capabilities·도구가 Backend/Pipeline에서 일치했고, 동일 요청의 no-Skill에는 marker가 없고 stored-Skill에는 정확한 제목·본문 marker가 있었다. 명시적 승인 뒤 실제 `create_document`와 Backend/core version/revision 1·hash readback이 성공했으며 planning·execution은 attempt 1로 retry가 없었다. Log는 AI guard **29/29**, Backend focused **204/204**이고 snapshot 통합 fixture도 unique ID 3개 1회 조회·3건 저장, PostgreSQL rename·soft-delete 뒤 `Old Doc`·`Old Page` 보존으로 통과했다. Lint typed relation은 정확한 7개 whitelist를 limit 전에 적용해 `graph_link_limit=1` mutation을 통과했다. 승격·병합 page는 commit 전에 unique ID를 `pending`으로 예약하고 worker 기동 시 `pending/failed`를 회수해 재시도하며 `document:Bxxxx` 참조를 보존했다. `wiki_ingestion`은 **169 passed, 1 skipped**다. 기존 promotion page 9/9와 MeaningClusterJudge 10/18의 계약 한계는 그대로다.

## 왜 그렇게 판정했나

서로 다른 입력과 통과 기준을 합산하지 않았다. Query의 hybrid와 facet 결과는 고정 fixture의 selector·citation 판정이고, 교차언어 E2E는 답변 생성만 fake다. 기존 Skill live와 후속 A/B는 in-memory 경계지만 별도 persisted E2E는 실제 repository·API·승인·저장을 사용했다. deterministic fake provider를 썼으므로 저장 경로와 모델 품질을 분리했다. Lint typed relation은 탐색 whitelist와 mutation, embedding 회귀는 job 요청·reference 보존만 판정했다. MeaningClusterJudge 10/18은 expected와 production contract가 어긋난 점수이고 core concept miss율이 아니다. Log 통합 fixture에서 production 결함은 없었으므로 미커밋 회귀 artifact의 부재만 남은 후보로 분리했다.

## 이 실험이 증명하지 못하는 것

이 보고서는 제품 전체 통과, 모든 문서·질문·한국어 조사 조합, 운영 corpus의 hybrid 우월성, assembler의 generator facet 누락 감지, 실제 답변 모델의 Skill·Query 품질, Kubernetes 1GiB 배포 가능성을 증명하지 않는다. Lint embedding 예약은 process 종료 뒤에도 회수되지만 지속적인 별도 queue consumer와 지수 backoff는 없고, semantic live retrieval은 시험하지 않았다. Log snapshot 검증은 커밋된 exact regression이나 full HTTP E2E가 아니다. 기존 promotion page 9회의 core selection, MeaningClusterJudge의 진짜 core concept miss와 구조화 승격의 일반적 의미 품질도 증명하지 않는다. 줄글의 7/9, 직접 `concept_related_slugs` 0/9, MeaningClusterJudge 10/18과 candidate 1/9은 제한된 fixture·평가 계약의 관찰값이지 PR 전체 품질 보증이 아니다.
