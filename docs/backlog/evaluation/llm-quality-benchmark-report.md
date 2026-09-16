# 기능별 설명 및 LLM 품질 벤치마크

평가일: 2026-08-16 (Asia/Seoul)

최초 평가 기준 commit은 `bae5d8eb507f8c7b2e7ee7cdb90db8f65213d066`이다. Query 검색 개선이
포함된 working tree에서 실행했으므로 동일 commit의 clean checkout 결과로 확대 해석하지 않는다.
Web 전환 수정 후의 표적 재평가는 `c3660fcc`에서 별도로 실행했다.

## 1. 결론

CI 통과는 API 계약, 상태 전이, 저장, 권한, 복원처럼 결정적인 동작의 정확성을 설명하는 데
적합하다. 반면 모델이 핵심 내용을 보존했는지, 올바른 근거를 찾았는지, 적절한 도구와 인자를
선택했는지는 별도의 LLM 품질 벤치마크가 필요하다. 이번 평가는 두 종류의 증거를 분리했다.

| 기능 | 이번 품질 결과 | 해석 |
| --- | ---: | --- |
| 문서 업로드·관리 | 결정적 동작은 기존 통합 증거로 확인 | Markdown 자체는 LLM 평가 대상이 아니며 PDF 변환만 별도 품질 대상 |
| PDF→Markdown | 과거 사람 전수 평가 414/445, 93.03% | 4개 PDF·30페이지 결과이며 이번 working tree에서 재실행한 값은 아님 |
| Ingest | 합성 문서 9/9, 장문 3/3 | 실제 1,189줄 프로젝트 문서까지 핵심 내용·근거·내장 evaluator 검사 |
| Query 검색 | held-out MRR 0.8976, Hit@1 0.8378 | 현재 raw dense query가 rewrite보다 우수 |
| Query 근거 선택 | Evidence Recall@5 0.8333, CitationReady@5 0.8000 | 정답 근거 그룹을 모두 확보하지 못한 질의가 20% |
| Query 최종 답변 | 최초 15/18, Web 재평가 6/6 | 최초 Wiki 지원 12/12·근거 부족 3/3·Web 0/3, 수정 후 두 종류 Web 질문 6/6 |
| Lint 승격 페이지 | 9/9, 100% | 작은 합성 평가셋의 필수 사실·허용 근거 검사 |
| 문서 편집·관리 Agent | 콘텐츠 47/57, 관리 plan 20/21 | GFM 보존과 workspace 도구·인자를 나눠 평가 |
| Skill 작성 | 새 표현 28/32, 87.50% | 문서 생성·고정 양식·폴더 정리 경계에서 두 판단기 불일치 4건 |
| Log·복원 | LLM 품질 대상 아님 | 기존 E2E에서 기록·복원·stale·멱등 계약을 확인 |

가장 먼저 개선할 영역은 Skill의 작업 유형 경계와 Markdown 편집의 inline code·Mermaid 처리다.
Query의 Web 전환은 표적 재평가를 통과했지만 질문 종류를 더 늘려야 한다. Agent와 Lint의 수치는 높지만 평가셋이 작으므로
release 수준 정확도라고 부르지 않는다.

### 1.1 비개발자용 기능별 설명과 평가 결과

아래 설명은 발표 자료나 기능 소개서에 그대로 사용할 수 있도록 작성했다. 여기서 정확도는
프로그램이 실행되는지만 확인한 값이 아니라, AI가 실제로 적절한 내용을 만들거나 선택했는지를
여러 번 확인한 결과다. 다만 평가에 사용한 문서와 질문 수가 아직 많지 않으므로, 모든 상황에서
같은 결과를 보장하는 수치로 해석하면 안 된다.

#### 문서 생성·편집·업로드

사용자는 Markdown 문서를 새로 작성하거나 기존 문서를 수정할 수 있으며, 작성된 파일을 서비스에
업로드해 보관할 수 있다. 문서는 폴더별로 정리할 수 있고 이름 변경, 이동, 삭제, 이전 버전 확인과
복원을 지원한다. PDF 파일을 업로드하면 내용을 Markdown 문서로 변환해 활용할 수도 있다.

**평가 결과:** 문서 저장, 이동, 삭제, 버전 관리처럼 정해진 규칙에 따라 동작하는 기능은 자동
테스트와 서비스 전체 흐름 테스트로 확인했다. PDF 변환은 과거에 실제 PDF 4개, 총 30페이지를
사람이 원본과 직접 비교했다. 평가한 445개 내용 단위 중 414개가 완전하게 복원되거나 사소한 표기
차이만 보여 93.03%를 기록했다. 다만 표와 수식은 70개 중 55개만 원본을 다시 보지 않고 사용할 수
있는 수준이었으므로, 숫자와 수식이 중요한 문서는 원본 확인이 필요하다. 이 PDF 수치는 이번
평가에서 다시 실행한 값이 아니라 기존 전수 평가 결과다.

#### Ingest

Ingest는 사용자가 선택한 Markdown 문서를 AI가 읽고, 문서에 포함된 주요 개념과 사실, 개념 사이의
관계를 Wiki에 정리하는 기능이다. 단순히 문서를 복사하는 것이 아니라, 나중에 검색과 질문 답변에
사용할 수 있도록 내용을 작은 근거 단위로 나누고 관련된 Wiki 항목끼리 연결한다. 정리된 내용에는
원문의 어느 부분에서 가져왔는지 확인할 수 있는 근거 정보도 함께 남긴다.

**평가 결과:** 실제 프로젝트에서 사용하는 1,189줄 분량의 설계 문서를 3번 실행했다. 원문을
181개 구간으로 나누고 AI가 한 번에 읽을 수 있는 크기에 맞춰 7개 묶음으로 처리했다. 문서 앞부분의
Wiki 편입·최신화 기능부터 중간의 Markdown 편집·작업 복구, 뒷부분의 질문 답변·Skill·기능 연결까지
주요 내용 7개가 남았는지, 존재하지 않는 원문 위치를 근거로 사용하지 않았는지, 자체 품질 검사를
통과했는지를 확인한 결과 3번 모두 통과했다. 원문의 의미와 핵심 개념 보존에 대한 AI 자체 평가는
5점 만점에 평균 4.67점이었다. 실행마다 개념은 20~23개, 근거는 43~50개로 달라져 핵심 내용은
유지했지만 세부 정리 형태까지 항상 같지는 않았다. 한 종류의 장문과 AI 자체 평가를 사용한
결과이므로 다른 형식의 장문과 사람의 직접 확인을 추가해야 한다.

#### Query와 Web 검색

Query는 사용자의 질문과 관련된 Wiki 내용을 찾아 근거와 함께 답변하는 기능이다. 답변에 사용된
내용이 어디에서 왔는지 확인할 수 있도록 인용 번호를 제공한다. Wiki만으로 답하기 어려운 질문은
사용자가 Web 검색을 허용한 경우 외부 정보를 검색해 보완할 수 있다. Web에서 찾은 내용은 답변에만
사용하며 자동으로 Wiki에 저장하지 않는다.

**평가 결과:** 먼저 Wiki 검색 능력은 77개 Wiki 항목과 120개 질문으로 확인했다. 별도로 분리해 둔
37개 질문에서 가장 먼저 보여 준 결과가 정답인 비율은 83.78%였고, 필요한 Wiki 항목을 상위 10개
안에서 찾은 비율은 90.99%였다. 관련 페이지를 찾은 뒤 실제 답변에 필요한 근거까지 모두 준비한
비율은 80%였다.

최초 최종 답변 평가는 6개 질문을 각각 3번씩, 총 18번 실행했다. Wiki에 답이 있는 질문은 12번 모두 필요한
내용과 인용을 포함했다. Wiki에 없는 사내 연차 규정 질문도 3번 모두 정보가 없다는 점을 밝혀
내용을 지어내지 않았다. 당시 현재 날씨 질문은 Web 검색을 허용했는데도 3번 모두 외부 검색으로
전환하지 못해 전체 15/18, 83.33%였다. 원인은 AI 평가 기준이 안전한 근거 부족 안내까지 먼저
재작성하도록 요구해 Web 전환 판단에 도달하지 못한 것이었다. 평가 순서를 고친 뒤 현재 날씨와
최신 기술 변경점 질문을 각각 3번씩 실제 서비스 흐름으로 다시 실행했고, 6번 모두 Web 검색을
수행해 Web 결과만 답변 근거로 사용했다. 전체 18건을 다시 실행한 값은 아니므로 최초 전체 수치와
표적 재평가 결과를 구분해 제시한다.

#### Lint

Lint는 원본 문서가 수정되거나 삭제됐을 때 Wiki에 남아 있는 내용을 다시 확인해 최신 상태로
유지하는 기능이다. 더 이상 원문에서 확인할 수 없는 내용은 제거하고, 새로 추가된 근거는 기존 Wiki
항목에 반영한다. 여러 문서에서 반복해서 등장하는 중요한 내용은 별도의 Wiki 항목으로 정리할 수
있으며, 어떤 내용이 변경됐는지도 기록한다.

**평가 결과:** 오래된 내용과 연결을 제거하는 기능은 정해진 규칙으로 동작하므로 자동 테스트로
확인했다. AI가 새로운 Wiki 항목을 작성하는 부분은 서로 다른 주제 3개를 각각 3번씩 생성해 총
9번 평가했다. 반드시 포함해야 하는 사실을 유지하고 허용된 원문 근거만 사용했는지 확인한 결과
9번 모두 통과했다. 다만 짧은 예시를 사용한 소규모 평가이므로, 여러 장문 문서가 서로 모순되는
상황까지 100% 정확하다고 의미하지는 않는다.

#### 문서 편집·관리 Agent

문서 편집·관리 Agent는 사용자의 채팅 요청을 이해해 문서 내용과 폴더 구조를 대신 정리하는
기능이다. 하나의 Agent 안에서 두 종류의 작업을 수행한다.

- **문서 내용 작업:** 새 문서를 작성하거나 기존 문서의 선택 영역 또는 전체 내용을 요약, 번역,
  재구성한다. AI가 만든 수정안은 즉시 저장하지 않고 사용자가 먼저 확인한 뒤 적용한다. 수정하지
  말아야 할 제목, 목록, 표, 코드, 링크, 수식 등의 Markdown 구조도 최대한 보존한다.
- **문서·폴더 관리:** 문서와 폴더를 만들거나 이름을 변경하고 다른 위치로 이동한다. Agent가 현재
  문서 구조를 확인해 작업 계획을 만든 뒤 사용자의 승인을 받아 실행한다.

**평가 결과:** 문서 내용 작업은 표, 목록, 코드, 링크, 수식 등 19가지 편집 상황을 각각 3번씩
평가해 47/57, 82.46%가 통과했다. 일반적인 표·번역·축약·수식 보존은 안정적이었지만, 문장 안의
짧은 코드 표현과 Mermaid 다이어그램은 3번 모두 평가 기준을 만족하지 못했다. 목록과 제목 형식도
일부 실행에서 흔들렸다.

문서·폴더 관리 작업은 생성, 이름 변경, 이동, 준비된 문서 적용 등 7가지 요청을 각각 3번씩
평가해 20/21, 95.24%가 통과했다. 실패한 한 번은 사용자가 문서를 최상위 위치에 저장해 달라고
했지만 AI가 기존 폴더 안을 선택한 경우였다. 따라서 Agent는 어떤 작업 도구를 선택했는지만 볼 것이
아니라 대상 문서와 저장 위치까지 정확한지 확인해야 한다.

#### Skill

Skill은 자주 반복하는 문서 작업 방식을 저장해 다시 사용할 수 있게 하는 기능이다. 예를 들어
“회의록을 항상 같은 형식으로 작성하기”, “긴 문장을 간결하게 바꾸기”, “문서를 주제별 폴더로
정리하기” 같은 작업 규칙을 Skill로 만들 수 있다. 사용자는 AI가 작성한 Skill의 이름, 설명, 동작
지침과 사용할 수 있는 작업 범위를 확인한 뒤 게시한다.

**평가 결과:** 최초 소규모 평가의 문제를 수정한 뒤에는 준비된 요청 18/18이 통과했지만, 특정
예시에만 맞춘 결과인지 확인하기 위해 프롬프트에 없는 새로운 표현 32건을 별도로 평가했다. 정상
작업은 21/24, 비지원·모호 요청은 7/8로 전체 28/32, 87.5%가 통과했다. 문서 편집과 고정 양식은
각각 6/6, 문서 생성은 4/6, 폴더 정리는 5/6이었다. 실패 4건은 모두 두 판단 과정이 서로 다른 작업
유형을 선택한 경우였고, 이를 각각 3번 다시 실행해도 7/12만 통과했다. 따라서 테스트 문장을
하드코딩한 결과는 아니지만, 문서 생성·고정 양식·폴더 정리의 경계 판단은 아직 안정적이지 않다.

#### Log와 복원

Log는 Ingest, Query, Lint, Agent가 언제 어떤 작업을 수행했고 무엇이 변경됐는지 보여 주는
기능이다. 사용자는 변경 전후 내용을 확인하고 필요한 경우 이전 상태의 내용을 바탕으로 복원할 수
있다. 복원하더라도 작업 기록을 지우거나 과거 시점으로 시간을 되돌리지 않고, 복원 작업 자체를 새
기록으로 남긴다.

**평가 결과:** Log와 복원은 AI가 답을 생성하는 기능이 아니므로 LLM 정확도로 평가하지 않았다.
대신 실제 서비스 흐름에서 여러 Wiki 페이지 복원, 오래된 복원 요청 차단, 같은 요청의 중복 실행
방지, 다른 문서와 작업 공간에 영향을 주지 않는지를 확인했다. 주요 복원 흐름은 통과했지만, Lint
결과 복원과 의도적으로 외부 AI 오류를 발생시키는 일부 예외 상황은 아직 충분한 실제 실행 증거가
없다.

#### 종합 해석

현재 결과만 보면 Ingest, Lint, 문서·폴더 관리 계획은 준비된 평가 예시에서 높은 성공률을 보였다.
Markdown 내용 편집은 대부분 동작하지만 특정 문법 보존을 개선해야 한다. Query의 Web 전환은 수정
후 표적 재평가 6/6을 통과했지만 더 다양한 외부 질문으로 확인해야 한다. Skill 작성은 새로운 표현에서 87.5%로, 기본 유형은
대체로 구분하지만 비슷한 작업 유형 사이에서 흔들렸다. 따라서 “모든 기능이 정확하다”고 설명하기보다,
**기본 동작은 자동 테스트로 확인했고 AI 품질은 기능별로 차이가 있으며, 현재 개선 우선순위는
Skill의 유형 경계와 일부 Markdown 구조 보존**이라고 설명하는 것이 정확하다.

## 2. 평가 원칙

### 2.1 결정적 동작과 LLM 품질을 분리한다

- 업로드, 저장, 버전 증가, 권한, operation log, restore, 중복 요청 방지는 자동 테스트와 E2E로
  검증한다.
- 의미 추출, 답변, 근거 선택, 편집 결과, plan, Skill 작성, Lint 페이지 생성은 실제 모델을
  호출해 gold condition과 비교한다.
- HTTP 성공이나 CI 성공을 LLM 정답률로 바꾸지 않는다.
- LLM judge 점수만 사용하지 않고 marker, reference, tool argument 같은 코드 기반 guard를 함께
  사용한다.

### 2.2 실행 조건

- Provider/model: OpenAI `gpt-5-nano`
- 반복: 기본 3회
- Ingest: 새 합성 Markdown 3개와 실제 프로젝트 장문 1개(1,189줄)
- Query 검색: concept page 77개, 질의 120개
- Query 근거: answerable 25개, no-answer 5개
- Query 답변: 한 workspace의 gold 질의 6개 × 3회
- Markdown 편집: GFM·편집 의도 19개 × 3회
- Agent: 문서·폴더 operation 7개 × 3회
- Skill: 기존 정상·경계 6종 반복 평가와 프롬프트 미사용 표현 32종 별도 평가
- Lint: promotion cluster 3개 × 3회

이번 수치는 단일 모델 baseline이다. 기존 보고서에서 Gemini와 Anthropic의 transport·저장 경계는
통과했지만, 두 provider의 동일 gold set 품질 비교는 아직 없다.

## 3. 기능별 상세 설명과 정확성

### 3.1 문서 생성·편집·업로드

사용자는 Markdown 문서를 새로 만들거나 파일을 업로드하고, 폴더 구조에서 이름 변경·이동·삭제를
수행한다. 편집 가능한 문서는 현재 Markdown, revision, content hash를 함께 관리하며 저장 충돌을
막는다. 프론트엔드는 Markdown/WYSIWYG 편집과 자동 저장을 제공하고, Agent가 만든 편집안도 같은
문서 저장 경계를 통과한다.

이 기능의 Markdown 업로드 자체는 LLM 품질 문제가 아니다. 기존 통합 보고서의 문서 생성·직접
편집·version·복원 증거와 CI를 동작 정확성 근거로 사용한다. PDF 변환만 원본 내용 보존 품질이
별도로 필요하다.

PDF 변환은 두 개의 기존 실험 결과를 구분해 읽어야 한다.

- 현재 ADR이 채택한 AnyDoc crop-first 기본 경로: 4개 PDF의 445 block 중 400개, 89.89%.
- local evaluator까지 포함해 사람이 원본과 전수 대조한 경로: 445 block 중 완전·경미 414개,
  93.03%. 부분 복원 31개, 미복원 0개이며 표·수식은 55/70개가 원본 확인 없이 재사용 가능한
  수준이었다.

두 값은 평가 경로가 다르며 이번 작업에서 새로 재현한 값이 아니다. 자세한 기준은
[PDF→Markdown 가이드](../pdf-to-markdown-guide.md)와
[ADR 0015](../../../../AI/docs/adr/0015-markdown-converter.md)에 있다.

### 3.2 Ingest

Ingest는 선택한 Markdown을 source block으로 나누고, LLM이 concept, relation, observation,
evidence unit을 추출하도록 한다. 정규화 이후 기존 Wiki concept와 canonical slug를 맞추고,
source/concept page와 link를 만든다. 생성 evaluator가 원문 보존, 개념 근거성, 관계 충실도,
근거 유용성을 평가하고 필요하면 추출을 재시도한다.

이번 gold set은 서로 겹치지 않는 고유 marker 9개를 세 문서에 배치했다. 각 실행은 다음을 모두
만족해야 통과한다.

1. 세 marker가 정규화 결과에 남아 있다.
2. 모든 `*_reference_ids`가 실제 source block ID에 속한다.
3. 내장 Wiki generation evaluator의 최종 상태가 `passed`다.

9/9가 통과했고 evaluator 평균은 `source_excerpt_fidelity=5.0`,
`concept_groundedness=5.0`, `relation_faithfulness=1.0`, `evidence_relevance=1.0`,
`overall=1.0`이었다. 다만 같은 입력에서도 concept 수는 3~4개, evidence unit 수는 3~6개로
달라졌다. 핵심 내용과 근거는 보존했지만 구조가 완전히 결정적이지는 않다.

짧은 합성 문서만으로 장문 품질을 설명할 수 없으므로 실제 프로젝트의
`agentic-architecture.md`도 추가로 평가했다. 이 문서는 1,189줄, 52,819바이트이며 181개 source
block과 7개 LLM 입력 packet으로 처리됐다. 문서 앞·중간·뒤에 있는 `Wiki Ingest`, `Wiki Lint`,
`Markdown Editor`, `Operation Recovery`, `Query`, `Skill Authoring`, `Artifact 연결`이 정규화
결과에 남는지와 모든 근거 ID의 원문 존재 여부를 3회 확인했다.

장문 3/3이 통과했고 evaluator 평균은 `source_excerpt_fidelity=4.6667`,
`concept_groundedness=4.6667`, `relation_faithfulness=1.0`, `evidence_relevance=1.0`,
`overall=1.0`이었다. 실행별 concept 수는 23, 22, 20개였고 evidence unit은 50, 43, 46개였다.
핵심 주제와 근거는 유지했지만 추출 구조와 evaluator 점수는 실행마다 달랐다. 한 종류의 장문을
내장 evaluator와 marker로 평가한 결과이므로 서로 다른 형식의 장문과 독립적인 사람 평가가
추가로 필요하다.

Evaluator 점수는 모델이 생성 결과를 다시 평가한 값이므로, 완벽한 점수가 나오더라도 독립적인
사람 평가와 같지 않다. 현재 metric 정의는
[현재 Evaluator 평가 지표](current-evaluator-metrics.md)에 있다.

### 3.3 Query와 선택적 Web 검색

Query는 질문을 검색용으로 정리하고 Wiki page 후보를 찾은 뒤, graph traversal과 evidence
selection으로 답변 context를 만든다. 답변은 `[n]` citation marker를 사용하며 evaluator가 근거
관련성, citation 정합성, unsupported 처리와 web route를 판단한다. Web 검색은 사용자가 허용하고
내부 근거가 부족할 때만 실행해야 한다.

#### 검색 품질

77개 concept page와 120개 질의 중 answerable 110개, no-answer 10개를 평가했다. answerable의
매 3번째 항목 37개를 held-out으로 분리했다.

| 방법 | 범위 | MRR | Hit@1 | Recall@10 | nDCG@5 |
| --- | --- | ---: | ---: | ---: | ---: |
| DenseRaw | 전체 110 | 0.9129 | 0.8636 | 0.9047 | 0.8301 |
| DenseRewrite | 전체 110 | 0.8446 | 0.7727 | 0.8668 | 0.7649 |
| DenseRaw | held-out 37 | 0.8976 | 0.8378 | 0.9099 | 0.8222 |
| DenseRewrite | held-out 37 | 0.8243 | 0.7568 | 0.8806 | 0.7361 |

현재 데이터에서는 rule-based rewrite가 dense retrieval을 악화시켰다. working tree의 Query 변경은
embedding에는 원 질문을 쓰고, 최종 page score를 dense 중심으로 두는 방향이며 이번 결과가 그
근거다. no-answer 10개에서 threshold 0.45 기준 DenseRaw reject rate는 0.60으로, 검색 점수만으로
unsupported를 안정적으로 구분하기에는 부족하다.

#### 근거 선택 품질

| 지표 | 결과 |
| --- | ---: |
| Page Recall@10 | 1.0000 (30/30 fact groups) |
| Page Recall@8 | 0.9667 (29/30 fact groups) |
| Evidence Recall@5 | 0.8333 |
| CitationReady@5 | 0.8000 |
| NoAnswerFalsePositive@0.45 | 0.2000 |

페이지 후보는 거의 찾지만 최종 5개 근거가 필요한 fact group을 모두 포함하는 비율은 더 낮다.
즉, “관련 페이지를 찾았다”와 “답변 가능한 근거를 모두 모았다”를 같은 성공으로 보면 안 된다.

#### 최종 답변·web route 품질

실제 `AnswerQueryUseCase`를 호출해 한 workspace의 지원 질문 4개, unsupported 질문 1개, web
fallback 질문 1개를 각각 3회 실행했다.

| 분류 | 통과 | 판정 조건 |
| --- | ---: | --- |
| Wiki 지원 질문 | 12/12 | 필수 의미 포함, citation 존재, citation 번호 유효, web 미실행 |
| Wiki 근거 부족 | 3/3 | 문서가 질문을 다루지 않음을 밝히고 web을 실행하지 않음 |
| Web fallback | 0/3 | 허용된 web 검색을 실제 실행 |
| 전체 | 15/18 (83.33%) | 위 조건의 합계 |

초기 refusal guard는 “정보가 없다” 같은 고정 표현만 인정해, “제공된 문서는 다른 주제에 초점을
둔다”는 안전한 제한 답변을 실패로 잘못 셌다. 해당 표현군을 보강하고 unsupported 3개 응답 원문을
다시 판정한 결과는 3/3이다.

근거 부족 질문은 관련 문서가 없음을 3회 모두 밝혔지만, 답변과 무관한 evidence를 1~3개 함께
반환했다. Web 허용 질문에서는 evaluator가 이 안전한 제한 안내를 `revise_answer` 대상으로 먼저
판정해 web route에 도달하지 못했다. Web route가 답변을 외부 근거로 다시 생성한다는 점을 반영해
`web_fallback`과 `internal_web_augmented`를 내부 답변 재작성보다 먼저 판단하도록 수정했다.

수정 후에는 기존 현재 날씨 질문과 프로젝트 사용 맥락에 더 가까운 최신 FastAPI 변경점 질문을
각각 3번씩 실행했다. evaluator 단독 판정 6/6이 `web_fallback`이었고, 실제 `AnswerQueryUseCase` 전체
경로도 6/6에서 Web 검색을 실행했다. 모든 결과의 `stop_reason`은 `web_search_fallback`이었으며,
반환된 근거의 page type은 전부 `web`이었다. 이 결과는 Web 전환의 표적 재평가이며 최초 18건 전체를
다시 실행한 결과는 아니다.

### 3.4 Lint

Lint는 편집·삭제된 source block이 지지하던 contribution과 link를 다시 계산한다. 더 이상 근거가
없는 내용은 제거하고, 새 evidence cluster가 승격 기준을 만족하면 concept page를 만들거나 기존
페이지에 통합한다. dry-run은 proposal만 만들고 apply는 operation artifact와 변경 로그를 남긴다.

stale contribution 제거, link 정리, restore는 결정적 로직이므로 기존 테스트와 통합 증거로 본다.
이번 LLM 평가는 promotion page 생성만 대상으로 삼았다. 세 cluster를 각 3회 생성해 대표 개념,
필수 사실, 허용된 source ref만 사용했는지 확인했고 9/9가 통과했다.

이는 작은 합성 cluster에서의 100%다. 실제 장문, 모순, 다중 문서 병합과 promotion 적용 후 Wiki
diff까지 포함한 정확도는 아직 측정하지 않았다.

### 3.5 문서 편집·관리 Agent

사용자는 Markdown/WYSIWYG 편집기를 직접 사용하거나 채팅으로 문서 내용과 workspace 구조의
변경을 요청할 수 있다. 제품 관점에서는 하나의 문서 편집·관리 Agent이고, 내부 실행만 콘텐츠
작업과 workspace 작업으로 나뉜다.

#### 콘텐츠 생성·편집

Agent router는 생성과 편집을 구분하고 edit goal을 정한다. 선택 영역·현재 section·전체 문서의
편집 결과를 바로 저장하지 않고 검토 가능한 replacement artifact로 만들며, 적용 시 base version과
대상 범위를 확인해 문서 revision으로 저장한다.

실제 모델에 GFM 및 편집 의도 19종을 3회씩 실행한 결과는 47/57, 82.46%다.

| 결과 | 케이스 |
| --- | --- |
| 3/3 | 강조·인용, 중첩 목록, 코드·링크 보존, footnote, table, 이미지·구분선, frontmatter, 회의록 구조화, 번역, 축약, 구조 보존 번역, anchor 보존 축약, 수식, 혼합 구조 보존 |
| 부분 통과 | task list 2/3, heading inline style 1/3, numbered list 2/3 |
| 0/3 | inline code, Mermaid |

대표 실패는 literal `\\n` 출력, router의 edit goal 오판, inline code 요구 불충족이다. Mermaid는
모델이 `graph TD`를 생성했지만 benchmark가 `flowchart`를 요구한 사례가 있어, 이 항목은 제품
실패와 평가 계약 과엄격 가능성을 함께 재검토해야 한다.

#### Workspace 문서·폴더 관리

자율 Agent는 사용자의 자연어 요청과 현재 hierarchy를 받아 문서·폴더 operation plan을 만든다.
읽기 도구로 대상과 version을 확인하고, 변경 도구는 승인 전 계획에 고정한다. 문서 생성·편집은
모델이 본문을 operation argument에 직접 넣지 않고 사전에 만든 content artifact를 참조한다.

폴더 생성·이름 변경·이동, 문서 이동·이름 변경, artifact 문서 생성·편집 적용 7종을 각 3회
실행했다. 도구명뿐 아니라 대상 ID, 목적지 ID, 이름, artifact ID, target을 함께 확인한 결과
20/21, 95.24%였다.

실패 1건은 “최상위에 저장” 요청에서 `folder_id=None` 대신 `folder-active`를 선택했다. 도구명만
검사한 초기 평가에서는 이 실행이 통과했으므로, Agent 평가는 반드시 핵심 argument까지 비교해야
한다.

이 수치는 plan 생성 정확도다. public API에서 hierarchy 조회, 승인, gateway 실행, 최종 저장까지의
자연어 E2E 성공률은 기존 통합 보고서의 별도 판정을 유지한다.

### 3.6 Skill

Skill은 반복 작업을 이름, 설명, 실행 지침, capability, 허용 도구 집합으로 저장한다. 작성기는
사용자 요청을 분류한 뒤 별도 verifier로 다시 확인하고, 참고 문서 사용 방식과 안전한 도구 범위를
정한다. proposal을 검토·게시하면 version이 생성되고 Agent router의 명시 호출 또는 자동 후보로
사용할 수 있다.

`document-create`, `document-edit`, `folder-organize`, 고정 template을 각 3회 평가하고, 지원하지
않는 Slack 전송과 작업 의미가 모호한 요청도 각 3회 평가했다.

| capability | 통과 | 주요 실패 |
| --- | ---: | --- |
| document-create | 3/3 | 없음 |
| document-edit | 3/3 | 없음 |
| folder-organize | 3/3 | 없음 |
| fixed-template | 3/3 | 없음 |
| 정상 요청 합계 | 12/12 (100%) | 수정 후 세 차례 연속 12/12, 마지막은 프롬프트 예시와 다른 문장 사용 |
| 비지원·모호 요청 | 6/6 (100%) | Slack 전송 차단 3/3, 일관된 폴더 정리 제안 3/3 |

최초 6/12는 두 원인이 섞인 결과였다. 고정 template의 `instructions_markdown`은 서버가 참고 문서
구조를 결정적으로 붙이기 위해 의도적으로 비우지만 benchmark가 이를 실패로 잘못 처리했다. 또한
classifier와 verifier가 Skill 생성이라는 meta 요청을 Skill이 수행할 실제 문서 작업과 혼동했다.
평가기를 제품 계약에 맞추고 두 프롬프트에 실제 작업을 분류하라는 경계 예시와 올바른 JSON null
형식을 명시했다. 수정 직후 정상 요청 12/12, 경계 요청 4/6이었고 null 형식까지 바로잡은 다음
실행은 18/18이었다. 프롬프트 예시를 평가 문장과 다른 표현으로 바꾼 독립 실행에서도 정상 요청은
12/12, Slack 차단은 3/3이었다. 다만 모호한 “문서를 정리” 요청은 추가 질문 대신 두 판단기가 모두
`folder-organize`를 선택했다. Skill은 즉시 실행되지 않고 사용자가 제안을 검토한 뒤 게시하므로,
이 항목은 반드시 `ambiguous`여야 한다는 내부 상태 기준보다 두 판단기의 일치, 허용 도구의 안전성,
검토 가능한 결과를 제품 수준 성공 조건으로 삼았다. 독립 실행의 원시 결과를 이 기준으로 다시
판정한 최종 결과는 18/18이다.

이 결과가 준비된 요청에만 맞은 것인지 확인하기 위해 프롬프트 예시에 사용하지 않은 32개 표현을
별도로 만들었다. 이 평가는 방금 개선한 작업 유형 판단의 일반화를 보기 위해 classifier와 verifier만
호출했으며 Skill 본문 생성은 포함하지 않았다.

| 새로운 표현 분류 | 통과 | 실패 |
| --- | ---: | --- |
| document-create | 4/6 | onboarding을 template으로 판정, announcement에서 verifier 불일치 |
| document-edit | 6/6 | 없음 |
| folder-organize | 5/6 | topic organize에서 verifier가 document-create 선택 |
| fixed-template | 6/6 | 없음 |
| 정상 작업 합계 | 21/24 (87.50%) | 두 판단기 불일치 3건 |
| 비지원·모호 요청 | 7/8 (87.50%) | document management에서 classifier/verifier 불일치 |
| 전체 | 28/32 (87.50%) | 실패 4건 |

실패 4건을 각각 3번 더 실행한 결과는 7/12였다. announcement는 3/3으로 첫 실패가 일시적이었지만,
onboarding은 1/3, topic organize는 2/3, ambiguous document management는 1/3이었다. 선택적 재실행은
전체 정확도 계산에 합치지 않고 실패의 반복성만 판단하는 데 사용했다. 결과적으로 기존 18/18은
준비된 소규모 범위에서는 재현됐지만 새로운 표현 전체로 일반화되지는 않았다. 주요 잔여 문제는
`document-create`, `template`, `folder-organize` 경계에서 두 판단기가 서로 다른 capability를 고르는
것이다. 작성된 Skill의 실제 Agent 작업 성공률과 다른 모델 비교도 별도 평가가 필요하다.

### 3.7 Log와 복원

Operation log는 Ingest, Query, Lint, Agent의 상태, 변경 resource, 오류와 산출물을 기록한다.
복원은 이전 operation의 불변 snapshot과 contribution을 이용해 새 restore operation을 만들며,
문서 revision을 과거 번호로 되감지 않는다. stale preview, 중복 restore token, workspace 격리를
검사한다.

이 영역에는 생성형 정답이 없으므로 LLM benchmark를 만들지 않았다. 기존 최신 통합 보고서에서
Ingest restore, 다중 page restore, stale preview, request 멱등성, 공개 오류 경계를 확인했다.
Lint target 부재와 callback/provider failure처럼 아직 증명되지 않은 항목도 그대로 남아 있다.

## 4. 실패가 보여 준 우선순위

1. **Skill 유형 경계**: 문서 생성·고정 양식·폴더 정리의 판정 기준을 분명히 하고 classifier와
   verifier가 같은 요청에 다른 capability를 선택하는 문제를 줄여야 한다.
2. **Markdown 편집**: inline code와 literal newline 회귀를 수정하고 Mermaid 허용 문법과 benchmark
   기대값을 일치시켜야 한다.
3. **Query 일반화 확인**: 수정 후 두 종류의 외부 질문은 6/6 통과했지만, 뉴스·표준·제품 정보 등
   더 다양한 공개 정보 질문과 최초 18건 전체를 다시 실행해야 한다.
4. **Agent 인자**: root destination, target ID, base version처럼 도구 실행 결과를 바꾸는 인자를
   지속적으로 gold set에 포함해야 한다.
5. **평가 독립성**: Ingest의 내장 evaluator 점수를 그대로 신뢰하지 말고 실제 프로젝트 장문의
   주요 사실을 사람이 직접 대조하는 gold set을 추가해야 한다.

## 5. 평가 자료 보존 범위

이번 LLM 품질 평가는 일회성 로컬 실행으로 수행했으며 평가 전용 Python 도구는 제품 저장소에
추가하지 않았다. 이 보고서는 모델, 입력 분류, 반복 횟수, 판정 조건, 최종 수치를 보존하지만 실행
코드와 원본 응답 전체를 보존하지 않으므로 동일 수치의 완전한 재현을 보장하지 않는다. 제품 코드의
결정적 회귀는 기존 Query·Skill 단위 테스트로 계속 확인하고, LLM 품질 수치를 공식 품질 기준으로
운영하려면 별도의 버전 관리된 평가 저장소나 CI 전용 평가 환경이 필요하다.

## 6. 근거와 제한

- 기능 상태와 결정적 E2E 범위는
  [Backend–AI 통합 테스트 보고서](backend-ai-integration-test-report.md)를 기준으로 한다.
- 외부 `agentic-architecture.md`는 Agent·Task·Artifact·Quality Gate를 구분하고 Ingest, Lint,
  Markdown Editor, Recovery, Query, Skill 흐름을 설명하는 데 유용하다. 다만 외부 다운로드 경로의
  설계 문서이므로 현재 코드와 통합 증거보다 우선하지 않는다. 특히 callback과 일부 runtime/API
  설명은 최신 public E2E에서 증명된 범위와 따로 읽어야 한다.
- 합성 gold set은 회귀를 빠르게 찾기 위한 baseline이며 실제 사용자 문서 분포를 대표하지 않는다.
- 키워드·구조 guard는 명백한 누락을 잡지만 의미가 미묘하게 틀린 답변까지 모두 판정하지 못한다.
- LLM judge는 생성 모델과 오류 상관관계가 있을 수 있다. 사람이 검수한 blind set이 추가되기
  전에는 production accuracy 또는 release sign-off로 사용하지 않는다.
- 이번에 새로 실행한 품질 비교는 OpenAI 한 모델뿐이다.

현재 결론은 **기능 설명에 붙일 수 있는 비교 baseline은 마련됐지만, Query route·Skill·일부
Markdown 편집은 개선 전 품질 통과로 표기하면 안 된다**는 것이다.
