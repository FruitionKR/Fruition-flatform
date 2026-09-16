# API 계약

이 문서는 Fruition의 공개 API와 서비스 간 내부 API를 사람 기준으로 설명한다. 기계가 읽는 원본 계약은 `Access/api-specs/openapi.yaml`, `Document/api-specs/openapi.yaml`, `AI/pipeline/api-specs/openapi.yaml`이며, 충돌할 경우 실행 코드와 생성된 OpenAPI를 우선한다.

- Gateway 공개 API: 117개 (`/api/**`)
- 서비스 내부·운영 API: 58개
- 전체 operation 수: 175
- 인증 기본값: 사용자 API는 Bearer access token, 내부 API는 서비스 토큰을 사용한다.
- 공통 오류 형식은 서비스에 따라 `ErrorResponse` 또는 FastAPI validation 응답을 사용한다.
- AI에게 넘기는 대화 맥락은 서버가 세션에서 읽어 조립한다. 클라이언트는 어떤 문답을 쓸지만 `selected_pair_ids`로 고르고, 비우면 세션의 최근 완결 문답을 쓴다. 이 세션에 속하지 않은 ID는 무시한다.
- Java 서비스(access-svc·document-svc)는 개별 매핑이 없는 예외도 `ErrorResponse`로 응답한다. Spring이 상태 코드를 담아 던진 예외(없는 경로의 `404` 등)는 그 상태를 유지하며 `REQUEST_FAILED`, 그 밖의 예상치 못한 예외는 `500 INTERNAL_ERROR`를 쓴다.
- 각 API는 동일한 10개 항목을 유지한다. 해당 사항이 없더라도 항목을 생략하지 않는다.
- `AI/pipeline/api-specs/openapi.yaml`은 선택 기능을 포함한 전체 계약을 보여주기 위해
  `AGENT_SKILLS_ENABLED=true`, `SKILL_API_ENABLED=true` 프로필로 생성한다. 실제 ai-svc가
  노출하는 API는 런타임 feature flag에 따라 이 명세의 일부일 수 있다.

- Gateway 라우팅: 인증과 워크스페이스 자체 CRUD·휴지통·복구는 access-svc(:8081),
  그 밖의 `/api/**`는 document-svc(:8080)로 전달한다. ai-svc는 Gateway에서 직접 노출하지 않는다.
- 인증: `Authorization: Bearer <access JWT(HS256, 기본 900s)>`. refresh는 opaque 토큰(DB에 sha256 해시만 저장, rotation).
- MFA(TOTP)를 켠 사용자는 `POST /api/auth/login`이 토큰 대신 `mfa_required`와 1회용 `mfa_token`을 돌려주고, `POST /api/auth/login/mfa`가 코드 검증 후 토큰을 발급한다. 켜지 않은 사용자의 응답은 그대로다.
- 사용자 API는 authenticated다. health·OpenAPI만 permitAll이다. `/internal/**`는 원칙적으로 `X-Internal-Token`을 검증하고, Agent worker가 document-svc의 Tool을 호출하는 `/internal/agent/tools/**`와 Skill 참조 read는 `X-Agent-Service-Token`을 검증한다.
- 내부 인증 헤더는 런타임에서 필수다. OpenAPI에는 인증 코드가 누락 요청을 직접 `401`로 처리할 수 있도록 nullable parameter로 표현되지만, 이 문서에서는 `필수(인증 계층 검증)`로 표기한다.
- 에러 envelope: `{ "error": { "code", "message", "details" } }`. 검증 실패는 400 `INVALID_REQUEST` + field details. 예외→코드 전체 매핑은 원문 참조.
- `Idempotency-Key`가 적용된 API는 1~255자 키를 사용한다. 실행 선점 lease는 15분이고, 완료 응답은 완료 시점부터 24시간 유지한다. 같은 사용자·endpoint·키의 같은 요청이 완료되면 저장된 응답을 재생하고, 다른 payload는 409 `IDEMPOTENCY_CONFLICT`, lease 내 처리 중인 동시 요청은 409 `IDEMPOTENCY_IN_PROGRESS`로 거절한다. 실행이 실패하거나 lease가 만료되면 같은 키로 재시도할 수 있다.
- ID 형식: `user_`/`doc_`/`session_`/`query_`/`agent_`/`op_` + UUID/난수.
- LLM은 `openai/gpt-5-nano`, `gemini/gemini-3.1-flash-lite`, `claude/claude-sonnet-5` 조합만 지원한다. 요청에서 둘을 함께 생략하는 공통 기본값은 `openai/gpt-5-nano`이고, 새 workspace의 `ingest_lint` 기본값은 `gemini/gemini-3.1-flash-lite`다. `provider`와 `model`은 항상 함께 생략하거나 함께 전달해야 하며, 다른 조합은 요청 검증 오류다.
- provider별 base URL은 `openai=https://api.openai.com/v1`, `gemini=https://generativelanguage.googleapis.com/v1beta/openai`, `claude=https://api.anthropic.com/v1`로 고정한다.
- Ingest·Lint·PDF 변환·Skill author/publish/update는 workspace AI 모델 설정의 `provider`·`model` snapshot, Query·Markdown Agent·Agent 경로는 사용자/API 요청 또는 chat/request 설정의 snapshot을 사용한다. provider/model은 사용자 설정·API·DB·Kafka payload에서 전달하며 env override는 없다. API key는 ai-svc와 converter의 secret env에 있는 `OPENAI_API_KEY`·`GEMINI_API_KEY`·`ANTHROPIC_API_KEY` 중 선택 provider의 값만 읽는다.
- Skill author 응답의 `capabilities`·`allowed_tools`는 사용자가 검토한 초안 권한이며 publish 요청에 그대로 전달한다. publish는 지침을 다시 보안 검사·분류하고 capability가 달라지거나 Tool 권한이 확대되면 저장하지 않는다.
- API key는 backend 요청·Kafka command/event·application log에 포함하지 않는다. 기존 AI 작업 로그의 조회/결과 API는 LLM 설정을 받지 않는다. 실제 provider 호출 전에는 선택 provider key가 필요하지만 mock 통합 테스트에는 key가 필요 없다.
- `allow_web_search`가 `true`일 때만 Tavily adapter를 구성하고 web route를 허용한다. `false`이면 내부 문서가 뒷받침하는 범위만 답하고 부족한 범위를 명시하며, 내부 근거가 전혀 없을 때만 unsupported로 처리한다.
- 원문: docs/backlog/spec/api/00-common.md

## curl 예시 실행

아래 예시는 서비스별 base URL 변수를 쓴다. 붙여넣기 전에 로컬 기준으로 한 번 정의한다.

```sh
export ACCESS=http://localhost:8081    # access-svc: /api/auth/*, /api/workspaces
export DOCUMENT=http://localhost:8080  # document-svc: 그 외 사용자 API
export PIPELINE=http://localhost:8000  # ai-svc pipeline: 내부 전용
```

프론트엔드는 `/api/*` 경로 기반 rewrite로 두 backend에 나눠 보낸다(`frontend/next.config.mjs`).
`/api/auth/*`, 워크스페이스 자체 CRUD·휴지통·복구, 멤버·초대 관리(`/api/workspaces/{id}/members`,
`/api/workspaces/{id}/invitations`, `/api/invitations/*`)는 access-svc, 그 밖의 워크스페이스 하위 기능은 document-svc가 받는다.

## 문서 읽는 법

1. 아래 서비스 목차에서 실제 요청을 받는 서비스를 선택한다.
2. 서비스 README에서 도메인을 선택한다.
3. 도메인 문서 상단의 요약으로 입력·출력·조건·주요 오류를 확인한다.
4. 전체 JSON·권한 규칙·curl·구현 위치가 필요하면 같은 파일의 상세 계약을 읽는다.

## 서비스 목차

| 서비스 | Gateway `/api/**` | 내부·운영 | 합계 | 역할 |
|---|---:|---:|---:|---|
| [access-svc](https://github.com/FruitionKR/Fruition-access/blob/main/docs/api/README.md) | 37 | 4 | 41 | 인증·프로필과 워크스페이스·멤버·초대 관리 |
| [document-svc](https://github.com/FruitionKR/Fruition-document/blob/main/docs/api/README.md) | 80 | 9 | 89 | 문서 저장과 사용자용 AI·Wiki·Agent Gateway |
| [ai-svc](https://github.com/FruitionKR/Fruition-ai/blob/main/docs/api/README.md) | 0 | 45 | 45 | 내부 Query·Agent·Wiki·Skill pipeline |

공통 [AI 작업 취소·복구 계약](ai-task-cancellation.md)은 Python과 업무 DB 복구 완료를 함께 확인한다.

## Gateway에서 AI까지

클라이언트는 AI 기능에 대해 document-svc의 공개 API를 호출한다. document-svc가 사용자 인증·워크스페이스
권한과 저장 책임을 처리한 뒤 작업 성격에 따라 ai-svc로 전달한다.

| 공개 기능 | document-svc 이후 전달 방식 |
|---|---|
| 문서·채팅 Wiki ingest | Kafka `ai.ingest.command` |
| Agent turn | Kafka `ai.agent.command` |
| 비동기 Query | Kafka `ai.query.command` |
| Wiki lint·복구 | Kafka `ai.maintenance.command` |
| 동기 Query | Kafka `ai.query.command` 후 완료 대기 |
| Agent 계획 조회·승인·거절·취소·수정 | 내부 HTTP `/agent/runs/**` |
| Skill·Wiki 조회/수정·Wiki Schema | 내부 HTTP |

ai-svc 문서의 요청 body는 서비스 간 계약이다. 사용자가 보내는 body와 같지 않으며,
Backend가 `workspace_id`, `user_id`, AI 모델, 대화·문서 snapshot 등을 검증해 추가한다.
