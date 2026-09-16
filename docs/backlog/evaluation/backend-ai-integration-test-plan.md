# Backend–AI 정밀 통합 테스트 계획

## 1. 문서 목적

현재 진행 중인 작업이 병합된 뒤 Backend와 AI 사이의 실제 통신과 주요 기능을 정밀 통합 테스트한다.

단순히 API가 `200`을 반환하는지만 보지 않고 다음 전체 흐름을 확인한다.

```text
Backend 요청
→ HTTP 또는 Kafka 명령
→ AI pipeline/worker 처리
→ LLM provider 호출
→ AI 결과 저장
→ task event/callback
→ Backend 상태·문서·Wiki·작업 로그 반영
```

이 문서는 실행 전 계획이다. 아직 테스트를 실행하거나 제품 코드를 수정하지 않는다.

## 2. 테스트 목표

다음을 성공·예외 양쪽에서 검증한다.

- 일반 문서 최초 ingest
- 채팅 `partial`/`full` ingest
- 채팅 `full` export의 delta 재생성
- 문서 수정 후 reingest
- Query 및 웹 검색 ON/OFF
- Query 멀티턴과 session 격리
- Lint dry-run/apply/no-op
- Skill 생성·분류·게시·활성화·사용
- Tool 등록·권한·승인·실행
- Markdown Agent 생성·편집·멀티턴
- AI 작업 Log
- `document_edit`, `ingest`, `lint`, `restore` 작업의 preview 및 restore
- OpenAI 전체 매트릭스와 Gemini·Anthropic 호환 smoke

## 3. 실행 범위와 제한

### 3.1 실행 시 허용할 작업

- 저장소와 설정 읽기
- Backend/AI 관련 기존 테스트 실행
- 로컬 Docker 서비스 기동
- 격리된 테스트 workspace, 문서, 채팅 session, Skill 생성
- 실제 LLM provider와 Tavily 호출
- 테스트를 위해 생성한 런타임 데이터의 안전한 정리
- 최종 테스트 보고서 1개 작성

### 3.2 별도 승인 없이 하지 않을 작업

- production/test 코드 수정
- 새 테스트 코드나 테스트 도구 파일 추가
- 발견한 문제 수정
- Git commit, push, PR 생성
- Docker volume 전체 삭제
- 기존 사용자 데이터 삭제
- API key나 내부 token 출력
- `main` 병합

문제가 발견되면 수정하지 않고 원인, 수정 위치, 최소 수정안, 재검증 방법을 최종 보고서에 기록한다.

## 4. 실행 원칙

- 저장소의 `AGENTS.md`를 우선 적용한다.
- 기존 Gradle/pytest 테스트와 기존 E2E 도구를 먼저 재사용한다.
- 직접 DB 변경은 하지 않는다. 필요한 상태 확인만 read-only로 수행한다.
- API로 확인 가능한 결과는 API를 우선 사용한다.
- 새 의존성이나 별도 테스트 프레임워크를 만들지 않는다.
- 병렬 작업 간 workspace, document, session, Skill ID를 공유하지 않는다.
- 단일 시나리오 안의 `생성 → 실행 → 확인 → 복구` 순서는 유지한다.
- 네트워크 timeout이나 명시적인 rate limit만 1회 통제 재시도한다.
- 최초 실패 결과를 삭제하거나 숨기지 않는다.
- 재시도 후 성공하면 원인에 따라 `FLAKY`로 기록한다.

## 5. Provider와 모델

현재 저장소가 지원하는 저비용·고속 모델 조합을 고정한다.

| Provider | 모델 | Reasoning | 적용 범위 |
|---|---|---|---|
| OpenAI | `gpt-5-nano` | `minimal` | 전체 기능·예외·멀티턴·복구 매트릭스 |
| Gemini | `gemini-2.5-flash-lite` | `low` | 핵심 호환 smoke |
| Anthropic | `claude-3-5-haiku-20241022` | extended thinking 없음 | 핵심 호환 smoke |

임의로 더 최신 모델로 바꾸지 않는다. 병합 후 model catalog가 변경됐다면 Backend catalog와 AI allowlist 양쪽에서 지원하는 각 provider의 최저비용·고속 모델을 확인한다. 변경 이유와 실제 사용 모델은 보고서에 기록한다.

### 5.1 대표 Provider

`openai/gpt-5-nano`로 전체 테스트 매트릭스를 실행한다.

### 5.2 보조 Provider

Gemini와 Anthropic은 전체 매트릭스를 반복하지 않고 다음 핵심 경로를 각각 1회 이상 확인한다.

- 일반 문서 ingest
- 내부 근거 Query
- Skill 생성 및 최소 Tool 사용
- Markdown Agent 생성 또는 편집
- provider/model snapshot과 structured output 파싱

웹 검색 ON/OFF 전체 매트릭스는 대표 Provider에서만 수행한다.

## 6. 환경변수와 비밀값

`infra/.env`에서 값 자체를 출력하지 않고 설정 여부만 확인한다.

필수 또는 조건부 키:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`
- `TAVILY_API_KEY`

선택 키:

- `LANGSMITH_API_KEY`

다음 내부 token도 값을 출력하지 않고 Backend와 AI 설정의 일치 여부만 확인한다.

- `INTERNAL_CALLBACK_TOKEN`
- `AGENT_INTERNAL_TOKEN`

## 7. 시작 조건

다음 조건이 충족된 뒤 시작한다.

1. 현재 진행 중인 작업이 병합되어 있다.
2. 테스트 기준 Git commit SHA를 고정할 수 있다.
3. 작업 트리에 테스트와 충돌할 미병합 변경이 없다.
4. `infra/.env`에 필요한 Provider 키가 설정되어 있다.
5. Docker와 Java 21을 사용할 수 있다.
6. Backend와 AI 서비스를 로컬에서 실행할 수 있다.

조건이 충족되지 않으면 임의로 우회하지 않고 정확한 차단 원인을 보고한다.

## 8. 테스트 데이터 격리

실행마다 고유한 run prefix를 만든다.

```text
back-ai-e2e-<run-id>
```

다음 기능은 각각 별도 workspace를 사용한다.

- 일반 ingest
- 채팅 ingest
- reingest
- Query
- Lint
- Skill 문서 생성
- Skill 문서 수정
- Skill 폴더 정리
- Skill template
- Markdown Agent
- Tool
- Log/restore
- Provider smoke

각 테스트 문서에는 검색과 중복 여부를 판별할 수 있는 고유 marker를 넣는다.

```text
E2E_INGEST_ALPHA_<run-id>
E2E_REINGEST_OLD_<run-id>
E2E_REINGEST_NEW_<run-id>
E2E_QUERY_INTERNAL_<run-id>
```

테스트 완료 후 생성한 fixture만 정확히 정리한다. 기존 데이터나 Docker volume은 삭제하지 않는다. API로 안전한 정리가 불가능하면 직접 SQL 삭제하지 않고 남은 fixture ID를 보고서에 기록한다.

## 9. 병렬 실행 구조

가능하면 `orca-agent-team`과 Orca orchestration으로 테스트를 병렬화한다.

- Coordinator는 계획, 의존성, 결과 통합만 담당한다.
- 각 lane은 테스트 기능 하나만 담당한다.
- 각 lane에는 테스트 수행자와 읽기 전용 검증자를 둔다.
- 실제 동시 lane 수는 실행 시 사용할 수 있는 슬롯에 따라 정한다.
- 별도 worktree가 필요하지 않으면 현재 worktree에서 실행하되 런타임 fixture를 분리한다.
- 완료된 lane의 증거는 검증자가 독립적으로 확인한다.
- 검증자가 발견한 문제는 수정하지 않고 보고서 항목으로 넘긴다.

### Wave 0: 사전 점검

- Git 기준
- 환경변수 설정 여부
- 서비스 health
- topic/worker 연결
- fixture 계약

### Wave 1: 기존 자동 테스트

- Backend 관련 Gradle 테스트
- AI 관련 pytest
- Provider 연결 확인

### Wave 2: 기능 테스트

- 일반 ingest/reingest
- 채팅 `partial`/`full` ingest
- Query 웹 검색 ON/OFF
- Lint
- Tool 계약
- Skill 분류별 테스트
- Markdown Agent

### Wave 3: Log/restore

- document edit restore
- ingest/reingest restore
- lint restore
- mixed/partial/stale/idempotency

### Wave 4: 보조 Provider

- Gemini smoke
- Anthropic smoke

### Wave 5: 결과 통합

- 수행 결과 수집
- 읽기 전용 검증
- 모순된 결과 재검증
- 단일 Markdown 보고서 작성

## 10. 사전 점검

### 10.1 기준 기록

다음을 기록한다.

- Git branch
- commit SHA
- 실행 시각과 timezone
- OS와 Docker 환경
- Backend/AI 주요 설정
- 대표 Provider/model
- 보조 Provider/model
- tracing 활성 여부

비밀값은 마스킹한다.

### 10.2 서비스 상태

다음을 확인한다.

- document-svc
- access-svc
- pipeline API
- ingest worker
- query task worker
- agent task worker
- maintenance task worker
- edit event consumer
- PostgreSQL
- MongoDB
- Kafka
- Redis
- MinIO

### 10.3 통신 경로

다음 topic과 내부 통신이 실제로 연결되어 있는지 확인한다.

- `ai.ingest.command`
- `ai.query.command`
- `ai.agent.command`
- `ai.maintenance.command`
- `ai.task.event`
- `document.edit.event`
- Backend의 Pipeline HTTP client
- AI의 Backend 내부 API 호출
- callback/internal token 검증

## 11. 기존 자동 테스트

### 11.1 Backend

관련 Gradle 테스트 범위:

- Query controller/service/requester/run/event
- ingest command outbox와 operation 반영
- Lint operation
- Skill controller/service/requester/reference
- Agent turn/tool/controller/gateway
- Chat session 및 chat export
- Operation log
- restore preview/apply/rebuild
- idempotency 및 callback result apply

### 11.2 AI

관련 pytest 범위:

- `wiki_ingestion`
- `query`
- `skill`
- `agent`
- `agent_run`
- `markdown_edit`
- `wiki_generation`
- pipeline log
- Provider E2E
- task worker
- callback/event contract

Backend와 AI 자동 테스트는 가능한 경우 병렬 실행한다. 자동 테스트 실패가 있어도 전체 실행을 즉시 중단하지 않는다. E2E 결과를 왜곡하는 핵심 실패인지 판단하고 독립적으로 실행 가능한 lane은 계속 진행한다.

## 12. Ingest 테스트

### I-DOC-01 일반 문서 최초 ingest

1. ./services/ai/pipeline/examples/llm-wiki.md 문서를 준비한다.
2. Backend를 통해 ingest를 요청한다.
3. Backend가 ingest 명령을 생성했는지 확인한다.
4. Kafka 명령의 document, workspace, provider, model snapshot을 확인한다.
5. ingest worker가 명령을 소비했는지 확인한다.
6. AI pipeline 완료를 기다린다.
7. Backend processing 상태가 완료되는지 확인한다.
8. Wiki page, link, embedding, contribution이 생성되는지 확인한다.
9. Query에서 고유 marker가 검색되는지 확인한다.
10. operation log와 실제 변경 내역이 일치하는지 확인한다.

### I-DOC-02 중복 명령

동일 document/revision ingest 명령을 중복 전달하여 다음을 확인한다.

- operation 중복 생성 방지
- Wiki contribution 중복 방지
- link/embedding 중복 방지
- callback/task event 중복 적용 방지

### I-CHAT-P-01 partial 채팅 ingest

1. 한 session에 여러 문답을 생성한다.
2. 일부 pair만 `partial`로 export한다.
3. 선택한 문답만 pipeline 입력에 포함되는지 확인한다.
4. 생성된 Wiki page와 pair membership을 확인한다.
5. 선택하지 않은 문답이 포함되지 않는지 확인한다.
6. 같은 pair를 다시 export했을 때 중복 membership이 생기지 않는지 확인한다.

### I-CHAT-F-01 full 채팅 최초 ingest

1. 여러 턴의 session을 생성한다.
2. 전체 session을 `full`로 export한다.
3. 전체 Markdown 저장본을 확인한다.
4. `selection_mode=full` 전달을 확인한다.
5. 각 문답과 full Wiki page 연결을 확인한다.
6. Query가 채팅 내용을 근거로 답하는지 확인한다.

### I-CHAT-F-02 full 채팅 delta 재생성

1. 기존 full export 이후 새로운 문답을 추가한다.
2. 동일 export 문서를 재사용해 full 재생성을 실행한다.
3. 저장된 원본 Markdown이 전체 session으로 갱신되는지 확인한다.
4. AI pipeline에는 신규 delta만 inline으로 전달되는지 확인한다.
5. 기존 문답이 중복 contribution으로 추가되지 않는지 확인한다.
6. 신규 문답만 Wiki 결과에 누적되는지 확인한다.

### I-RE-01 문서 편집 후 reingest

1. `OLD` marker를 포함한 문서를 최초 ingest한다.
2. 문서를 수정해 `OLD`를 제거하고 `NEW` marker를 추가한다.
3. 목록/API에서 `needs_reingest=true`인지 확인한다.
4. reingest를 실행한다.
5. 최신 source revision과 content hash가 전달되는지 확인한다.
6. 완료 후 `needs_reingest=false`인지 확인한다.
7. Query에서 `NEW`가 검색되는지 확인한다.
8. `OLD`가 더 이상 현재 근거로 사용되지 않는지 확인한다.
9. 이전 contribution/link/embedding 정리 여부를 확인한다.
10. reingest operation log를 확인한다.

### I-RE-02 연속 reingest

```text
A ingest → B edit/reingest → C edit/reingest
```

다음을 확인한다.

- 각 revision과 operation 연결
- 최신 C만 현재 상태로 노출
- A/B 잔여 contribution과 embedding 중복 방지
- operation 순서와 log 정확성

### I-RACE-01 ingest 중 재수정

1. ingest를 시작한다.
2. 완료 전에 문서를 다시 수정한다.
3. 오래된 결과가 최신 revision을 정상 완료로 덮어쓰지 않는지 확인한다.
4. 최신 문서에 `needs_reingest`가 유지되는지 확인한다.
5. stale callback 처리 결과를 확인한다.

### I-ERR 예외

- 존재하지 않는 문서
- 삭제된 문서
- 다른 workspace 문서
- 잘못된 Provider/model
- worker 또는 Provider 실패
- malformed command
- 중복 callback
- 처리 중 동일 문서 재요청

실패 시 partial Wiki 저장이나 거짓 성공 상태가 없어야 한다.

## 13. Query 및 웹 검색 토글

같은 workspace, 같은 내부 문서, 같은 질문으로 `allow_web_search=false/true`를 비교한다.

답변 문구만 비교하지 않고 다음 구조적 증거를 확인한다.

- Backend 요청값
- Query run snapshot
- 채팅 메시지 snapshot
- Kafka command
- AI request context
- Query event
- stop reason
- source/reference role
- 실제 Tavily 호출 여부

### Q-01 내부 근거 + 웹 검색 OFF

- `allow_web_search=false`
- 내부 Wiki 근거만 사용
- Tavily 호출 없음
- `web_search_started` 이벤트 없음
- `web_search_result` 출처 없음
- 내부 근거 범위 이상을 추측하지 않음

### Q-02 동일 질문 + 웹 검색 ON

- `allow_web_search=true`
- 실제 Tavily 호출 발생
- `web_search_started` 및 완료 이벤트 확인
- 웹 source/reference 포함
- `web_search_fallback` 또는 적절한 web route 확인

### Q-03 내부 근거 + 외부 보강

내부 문서로 대상은 식별되지만 외부 사용법이나 최신 정보가 필요한 질문을 사용한다.

기대 결과:

- `internal_web_augmented`
- 내부 출처와 웹 출처 모두 포함
- 어느 주장에 어떤 출처가 사용됐는지 구분 가능

### Q-04 내부 근거 없음 + OFF

- 웹 호출 없음
- `unsupported` 또는 근거 부족을 명시한 답변
- 외부 사실을 근거 없이 생성하지 않음

### Q-05 Tavily 실패

- 실패 이벤트 기록
- 웹 결과를 조작해 생성하지 않음
- 내부 근거가 있으면 제한된 내부 답변
- 내부 근거도 없으면 명확한 실패 또는 `unsupported`

### Q-06 snapshot 격리

웹 검색 ON/OFF Query를 동시에 실행한다.

- 각 run과 메시지에 정확한 boolean 저장
- Kafka command 간 값 혼합 없음
- 한 요청의 web adapter가 다른 요청에 재사용되지 않음

### Q-07 멀티턴

1. 첫 질문에서 대상을 명시한다.
2. 후속 질문에서는 “그것”, “두 번째 방법”처럼 대명사를 사용한다.
3. 같은 session에서 앞선 문맥이 반영되는지 확인한다.
4. 새 session에서는 이전 문맥이 유출되지 않는지 확인한다.
5. recent message 제한을 넘는 대화에서도 계약된 범위만 전달되는지 확인한다.

### Q-08 요청 예외

- blank question
- boolean이 아닌 `allow_web_search`
- Provider/model 한쪽만 전달
- 존재하지 않는 session
- 다른 workspace session
- sync/async API의 오류 계약 차이

## 14. Lint 테스트

### L-01 dry-run

의도적으로 orphan link나 lint 대상 Wiki 상태를 만든다.

- dry-run 결과 확인
- 실제 Wiki 변경 없음
- 발견 항목과 제안 변경 확인

### L-02 apply

- lint operation 생성
- maintenance command 발행
- AI 결과 수신
- Wiki page 변경
- change diff
- operation log 완료
- Query 결과 반영

### L-03 clean no-op

- 정상 완료
- 변경 count 0
- 불필요한 operation change 생성 없음

### L-04 예외

- 동시에 같은 workspace lint 실행
- 잘못된 workspace
- Provider 실패
- callback 실패
- operation ID 불일치
- 부분 처리 실패

실패 시 적용된 변경과 log 상태가 일치해야 한다.

## 15. Tool 존재 및 계약 확인

현재 AI 계약의 13개 Tool을 전부 확인한다.

### 읽기 Tool

- `list_root_items`
- `list_folder_children`
- `search_hierarchy`
- `get_breadcrumb`
- `get_document_metadata`
- `get_document_content`

### 변경 Tool

- `create_folder`
- `rename_folder`
- `move_folder`
- `move_document`
- `rename_document`
- `create_document`
- `apply_document_edit`

각 Tool에 대해 다음을 확인한다.

1. AI schema allowlist에 존재
2. Backend gateway 구현 존재
3. endpoint 또는 dispatcher 등록
4. 요청/응답 schema 일치
5. workspace authorization 동작
6. 정상 호출 가능
7. 잘못된 인자 거부
8. 다른 workspace 접근 거부

변경 Tool은 isolated workspace에서 실제로 한 번씩 실행한다.

## 16. Agent Tool 승인 흐름

### 정상 흐름

```text
사용자 요청
→ Agent route
→ read Tool
→ mutation plan
→ 사용자 승인 대기
→ approved operation 선택
→ Backend Tool 실행
→ 결과 저장
→ operation 완료
```

검증 항목:

- 계획에 허용된 Tool만 등장
- mutation 전에 필요한 read Tool 실행
- 승인 전 mutation 없음
- 승인된 operation ID만 실행
- LLM이 mutation 인자를 다시 만들어 바꾸지 않음
- 동일 operation은 한 번만 실행
- 완료 결과가 실제 문서/폴더 상태와 일치

### 예외

- 미승인 mutation
- 승인 후 Tool 이름 변조
- 승인 후 인자 변조
- 허용되지 않은 Tool
- 다른 workspace resource
- 이미 완료된 operation 재실행
- plan과 실제 상태가 달라진 경우
- Tool 도중 일부 실패

## 17. Skill 테스트

### 17.1 공통 생성 흐름

각 Skill 분류에서 다음을 확인한다.

1. 자연어 요구 입력
2. intent 분류
3. capability 결정
4. 최소 `allowed_tools` 결정
5. security lint
6. proposal 생성
7. 사용자의 게시 승인
8. Skill/version 저장
9. enable 상태
10. 관련 Agent 요청에서 자동 선택
11. 계획 생성
12. Tool 승인
13. 실제 수행
14. 결과 확인

### S-CREATE `document-create`

기대 Tool 범위:

- planning read Tool
- document read Tool
- `create_document`

Skill을 생성한 뒤 실제 Markdown 문서를 생성한다.

### S-EDIT `document-edit`

기대 Tool 범위:

- planning read Tool
- document read Tool
- `apply_document_edit`

기존 문서를 읽고 승인된 편집을 실제 적용한다.

### S-FOLDER `folder-organize`

실제로 다음을 수행한다.

- 폴더 생성
- 폴더 이름 변경
- 폴더 이동
- 문서 이동
- 문서 이름 변경

### S-TEMPLATE `template`

- 참조 내용을 그대로 복사하지 않고 구조를 사용
- `template` capability 부여
- 문서 생성 또는 편집에 적절히 선택
- `create_document` 또는 `apply_document_edit` 사용
- 참조 문서 권한 확인
- 현재 구현이 명시적으로 지원하지 않는 full transform은 성공으로 꾸미지 않고 기대된 clarification인지 확인

### S-MULTITURN

- 분류가 모호하면 clarification
- 사용자의 짧은 후속 답변이 원래 Skill 작성 요청과 연결
- proposal 수정 요청
- 보안 재검토 요청
- 최종 게시 승인

### S-DRAFT

완료된 Agent 작업으로 Skill draft를 제안한다.

- 성공한 operation만 근거로 사용
- 실패하거나 실행되지 않은 Tool을 권한으로 추가하지 않음
- 특정 문서명, ID, 사용자 데이터가 일반화됨
- credential, prompt, shell, SQL, HTTP 지침이 포함되지 않음

### S-ERR

- unsupported/ambiguous 분류가 Tool 권한을 얻지 않음
- capability와 맞지 않는 Tool 거부
- mutation Tool에 planning read Tool이 빠진 경우 거부
- unsafe instruction 차단
- disabled Skill 미선택
- 유사 Skill이 여러 개면 clarification
- 다른 workspace reference 차단
- 승인 payload 변조 차단

## 18. Markdown Agent 테스트

### M-01 새 문서 생성

- 대화 내용으로 Markdown 생성
- heading, paragraph, list 구조 확인
- 저장된 문서 원문 확인
- version 및 operation 확인

### M-02 선택 영역 편집

선택한 source range만 변경되고 나머지 문서는 보존되는지 확인한다.

### M-03 현재 section 편집

현재 section만 바뀌고 다른 heading 영역은 유지되는지 확인한다.

### M-04 문서 전체 편집

명시적인 전체 편집 요청일 때만 전체 문서를 변경하는지 확인한다.

### M-05 insert-after

현재 section 뒤에 내용을 추가하고 heading/code fence 구조가 깨지지 않는지 확인한다.

### M-06 멀티턴

```text
사용자: 이 부분을 체크리스트로 바꾸는 게 좋겠어
Agent: ...
사용자: 그렇게 해줘
```

후속 메시지가 합의된 편집으로 route되는지 확인한다. 새 session에서는 이전 편집 합의가 유출되지 않아야 한다.

### M-07 Skill 적용

`document-create`, `document-edit`, `template` Skill을 각각 Markdown 요청에 적용하고 선택된 Skill과 결과를 확인한다.

### 18.1 GFM 보존

다음을 포함하는 입력을 사용한다.

- heading
- link
- table
- fenced code block
- task list
- footnote
- blockquote
- inline code

편집 전후 Markdown을 비교해 구문 손상을 확인한다.

### M-ERR

- 활성 문서 없음
- target 없음
- 구조 경계를 넘는 source range
- version conflict
- 다른 workspace 문서
- 승인 전 apply
- prompt injection이 포함된 문서 본문
- 허용되지 않은 Tool 요청

## 19. Log 및 Restore 테스트

대상 작업 유형:

- `document_edit`
- `ingest`
- `lint`
- `restore`

각 operation에서 다음을 확인한다.

- list API
- detail API
- status
- target resource
- change count
- before/after version
- diff
- error message
- task/run/operation ID 연결
- 실제 데이터 상태와 log 일치

### R-DOC-01 문서 AI 편집 복구

1. 문서 AI 편집
2. operation log 확인
3. restore preview
4. restore 실행
5. 편집 전 내용으로 새 revision 생성 확인
6. 기존 version 이력 보존 확인
7. restore operation log 확인

### R-INGEST-01 reingest 복구

```text
ingest A → edit/reingest B → B restore
```

검증 항목:

- B contribution 비활성화 또는 제거
- Wiki page가 A 기준으로 복구
- link/embedding 정리
- Query가 A 내용을 다시 사용
- B 내용은 현재 근거에서 제외

### R-INGEST-02 연속 작업 범위 복구

```text
A → B → C
```

B를 복구했을 때 B와 그 이후 같은 문서의 C 영향이 계약대로 함께 처리되는지 확인한다. 다른 문서의 operation은 영향을 받지 않아야 한다.

### R-LINT-01 Lint 복구

- lint 전 Wiki 상태
- lint 후 변경
- restore preview
- restore 후 원상태
- change diff 및 operation log

### R-MIXED-01 Ingest와 Lint 혼합

ingest 이후 lint가 실행된 상태에서 복구 범위가 원문 contribution과 lint 변경을 혼동하지 않는지 확인한다.

### R-MULTI-01 여러 Wiki page

하나의 operation이 여러 page를 생성·수정·삭제했을 때 모든 page가 일관되게 복구되는지 확인한다.

### R-PARTIAL-01 부분 성공

`partially_succeeded` 또는 rebuild 단계가 발생하는 시나리오에서 다음을 확인한다.

- 성공 page
- 실패 page
- manifest
- callback
- 최종 operation 상태
- 재시도 가능성

### R-STALE-01 오래된 preview

1. restore preview 생성
2. 대상 문서나 Wiki 상태 변경
3. 기존 preview로 restore 시도
4. stale/TOCTOU 오류 확인
5. 부분 복구가 발생하지 않았는지 확인

### R-IDEMP-01 중복 callback/event

동일 restore 결과나 task event를 재전달해도 한 번만 반영되는지 확인한다.

### R-ERR

- restore operation 자체 재복구
- 없는 operation
- 다른 workspace operation
- 권한 없는 사용자
- 실패 중인 operation
- preview token 변조
- malformed restore manifest
- 복구 중 Provider/worker 실패

## 20. 보조 Provider Smoke

대표 Provider 전체 테스트가 끝난 뒤 Gemini와 Anthropic smoke를 병렬 실행한다.

각 Provider에서:

1. 고유 문서 ingest
2. 내부 근거 Query
3. 간단한 `document-create` 또는 `document-edit` Skill 생성
4. 최소 read Tool 및 mutation Tool 1회
5. Markdown 생성 또는 편집
6. Provider/model snapshot 확인
7. structured output 파싱 오류 여부 확인

## 21. 판정 기준

- `PASS`: 기대 상태와 증거가 모두 일치
- `FAIL`: 제품 동작 또는 계약 위반
- `FLAKY`: 동일 입력이 최초 실패 후 통제 재시도에서 성공
- `BLOCKED`: 환경, 외부 Provider, 권한 문제로 실행 불가
- `NOT RUN`: 의존 실패 등으로 실행하지 못함

`BLOCKED`, `FLAKY`, `NOT RUN`을 성공으로 합산하지 않는다. 기능 전체 `PASS`는 해당 기능의 필수 정상·예외 시나리오가 모두 검증됐을 때만 부여한다.

## 22. 증거 수집

각 시나리오마다 다음을 기록한다.

- 시나리오 ID
- 목적
- 선행 조건
- 입력
- 기대 결과
- 실제 결과
- HTTP status와 주요 response
- task ID
- run ID
- operation ID
- document/session/workspace ID
- Provider/model
- Kafka command/event 상관관계
- Backend 상태
- AI 상태
- Query event와 stop reason
- source/reference
- 관련 service log
- 실행 시간
- 재시도 여부
- 최종 판정

API key, Authorization header, 내부 token, 개인정보는 반드시 마스킹한다.

## 23. Markdown 산출물

Markdown Agent 및 Skill이 만든 Markdown은 최종 보고서 안에서 직접 볼 수 있어야 한다.

각 관련 시나리오에 다음을 fenced block으로 포함한다.

- 입력 Markdown
- AI가 반환한 Markdown
- Backend에 실제 저장된 Markdown
- 편집 전후 diff
- GFM 보존 결과

성공 여부만 적고 실제 Markdown을 생략하지 않는다.

## 24. 실패 분석

각 실패에는 다음을 반드시 작성한다.

1. 증상
2. 재현 절차
3. 최초 실패 시각
4. 기대 결과
5. 실제 결과
6. 발생 계층
7. 확인된 직접 원인
8. 근본 원인 추정
9. 관련 코드 파일 또는 호출 경계
10. 최소 수정 방향
11. 수정 시 영향 범위
12. 수정 후 재실행할 시나리오

원인이 확인되지 않았으면 추정을 사실처럼 쓰지 않고 추가 조사 필요 항목으로 표시한다.

발생 계층은 다음 중 하나 이상으로 분류한다.

- Backend validation
- Backend state/outbox
- HTTP transport
- Kafka publish/consume
- AI routing
- LLM Provider
- structured output parsing
- AI persistence
- task event/callback
- Backend result apply
- authorization
- test environment

## 25. 최종 보고서

다음 파일 하나만 작성한다.

```text
docs/backlog/evaluation/backend-ai-integration-test-report.md
```

다른 날짜형 issue/changelog 문서는 만들지 않는다.

보고서 구조:

1. 테스트 요약
2. 기준 commit 및 환경
3. Provider/model
4. 서비스 상태
5. 자동 테스트 결과
6. 전체 시나리오 결과표
7. Ingest 결과
8. Query 웹 검색 ON/OFF 결과
9. Lint 결과
10. Tool 존재·실행 결과
11. Skill 분류별 결과
12. Markdown Agent 결과
13. 멀티턴 결과
14. Log 및 Restore 결과
15. Provider별 smoke 결과
16. Markdown 입력·출력·저장본
17. 실패·불안정·차단 항목
18. 원인과 수정 제안
19. 재검증 목록
20. 남은 fixture 및 정리 상태

## 26. 전체 완료 조건

- 일반 문서 최초 ingest 성공
- 채팅 `partial`/`full` ingest 성공
- full chat delta 재생성 성공
- 문서 수정 후 reingest 성공
- 오래된 ingest 결과가 최신 revision을 덮어쓰지 않음
- Query 웹 검색 OFF에서 실제 외부 호출이 없음
- Query 웹 검색 ON에서 실제 Tavily 호출과 웹 출처가 확인됨
- Query 멀티턴과 session 격리 확인
- Lint dry-run/apply/no-op/실패 확인
- 13개 Tool 등록과 Backend 호출 가능 여부 확인
- mutation Tool 승인·권한·멱등성 확인
- 네 가지 Skill capability가 각각 생성·선택·수행됨
- Markdown Agent 생성·편집·멀티턴·GFM 보존 확인
- `document_edit`, `ingest`, `lint`, `restore` Log 확인
- 여러 Restore 시나리오에서 실제 데이터가 복구됨
- OpenAI 전체 매트릭스 완료
- Gemini와 Anthropic 핵심 smoke 완료
- 모든 Markdown 산출물을 보고서에서 직접 확인 가능
- 실패마다 원인, 수정 방향, 재검증 시나리오 기록
- 최종 보고서 한 파일 작성

## 27. 예상 소요 시간

병렬 실행 기준:

- 정상적인 경우: 6~8시간
- Provider timeout이나 실패 분석이 많은 경우: 1~2일
- 문제 수정과 재검증은 이번 범위에 포함하지 않음

각 Wave가 끝날 때 진행 상황을 공유한다. 테스트가 진행 중일 때 60분 이상 상태 업데이트 없이 방치하지 않는다.
