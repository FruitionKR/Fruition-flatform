# Markdown 문서 AI 편집 작업 계획

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-07-23
- 기능 SDD: [`markdown-document-ai-editing.md`](../markdown-document-ai-editing.md)

## 2. 실행 원칙

- 실제 저장은 Spring backend만 수행한다.
- 실패 테스트를 먼저 작성하고 각 상태 전이를 독립적으로 검증한다.
- 현재 llmPipeline 계약과 fixture를 확장하며 별도 편집 엔진을 중복 구현하지 않는다.
- 일반 수동 저장에는 AI snapshot을 만들지 않는다.

## 3. 작업 계획

### TASK-AI001 pipeline actual target 계약

- 관련 요구사항: `REQ-AI004`~`REQ-AI008`
- 작업:
  - 응답에 requested/actual target 구분
  - 요청 범위 밖 actual target 허용
  - 문서 밖 범위와 구조 손상 검증 유지
  - 계약 보정 1회와 모델 원문을 숨기는 내부 오류 응답
- 현재 구현 근거:
  - 응답이 `requested_target`, `actual_target`, `scope_expanded`, `changed`를 구분한다.
  - actual target은 requested target을 포함한 채 bounded editable context 안에서 확장할 수 있고 원본 전체 문서 기준 경계와 Markdown 구조를 다시 검증한다.
  - `selection`, `current_section`, `whole_document` 범위와 `replace`, `insert_after` 연산 단위 테스트가 존재한다.
  - raw HTML과 MDX import/export·component·expression 결과를 계약 오류로 거절한다.
  - 일부 범위만 지정한 `whole_document`와 `insert_after`의 잘못된 target type도 계약 오류로 보정한다.
  - JSON 파싱 실패와 필수 action 누락·미지원 action을 router·편집·source-range·생성 경로에서 안전한 계약 실패로 바꿔 1회 보정한다.
  - 편집·source-range·생성 응답의 필수 문자열 필드는 객체·배열을 문자열로 강제 변환하지 않고 계약 오류로 보정한다.
  - 범위 확장 시 actual target 안의 link·image·table·code 등 보호 구조를 다시 검증한다.
  - CRLF 문서에서도 actual target 원문과 table 보호 조각의 줄 구분자를 그대로 유지해 유효한 결과를 계약 오류로 오판하지 않는다.
  - replacement의 원문 공백을 보존해 동일한 전체 문서 결과를 `changed=false`로 판정한다.
  - 계약 보정은 1회만 수행하며 재실패 응답은 모델 원문과 내부 예외를 노출하지 않는다.
  - pipeline 내부 오류 코드는 유지하며 Spring이 외부 `AI_EDIT_GENERATION_FAILED`로 정규화할 수 있게 내부 상세를 노출하지 않는다.
  - Agent router 재실패도 내부 action과 모델 원문을 숨기는 `422 agent_turn_route_contract_failed`로 반환한다.
  - 2026-07-24 기준 llmPipeline 전체 테스트가 `463 passed, 43 subtests passed`로 통과했다.
- 완료 조건:
  - [x] `selection`, `current_section`, `whole_document` fixture 통과
  - [x] `replace`, `insert_after` fixture 통과
  - [x] 범위 확장 결과가 정상 응답됨
  - [x] 문서 밖·구조 손상·HTML·MDX 결과 거절
  - [x] 재실패 시 모델 원문 미노출

### TASK-AI002 proposal·snapshot 데이터 모델

- 관련 요구사항: `REQ-AI009`, `REQ-AI015`~`REQ-AI017`, `REQ-AI023`
- 작업:
  - proposal 상태와 전이 제약
  - AI 편집·복원 snapshot 테이블
  - 채팅·문서 FK와 삭제 정책
  - 멱등성 결과 저장
- 완료 조건:
  - [ ] 유효하지 않은 상태 전이 DB/서비스 차단
  - [ ] 적용된 snapshot이 채팅 삭제 후 유지됨
  - [ ] 문서 영구 삭제 시 관련 데이터 정리
  - [ ] 일반 저장에서 snapshot 미생성

### TASK-AI003 Spring agent turn orchestration

- 관련 요구사항: `REQ-AI001`~`REQ-AI010`, `REQ-AI020`~`REQ-AI022`
- 작업:
  - 소유자·활성 문서·입력 크기 검증
  - 채팅 저장과 60초 llmPipeline 호출
  - actual target으로 전체 후보 생성
  - proposal과 변경 없음 응답 저장
  - pipeline 오류의 외부 오류 코드 정규화
- 완료 조건:
  - [ ] 문서 소유자가 아닌 멤버의 해당 문서 AI 편집 `403`
  - [ ] 입력 제한 경계 테스트
  - [ ] timeout·연결 실패 시 문서 불변
  - [ ] 변경 없음에서 proposal 적용 상태·snapshot 미생성
  - [ ] 로그에 Markdown·모델 원문 없음

### TASK-AI004 제안 적용·거절·무효화

- 관련 요구사항: `REQ-AI010`~`REQ-AI014`
- 작업:
  - proposal 조회·적용·거절·무효화 API
  - 버전 조건부 문서 저장
  - 전후 snapshot과 상태의 단일 트랜잭션
  - `Idempotency-Key` 24시간 처리
- 완료 조건:
  - [ ] 적용 성공 시 버전 1 증가
  - [ ] 거절·무효화 시 문서 불변
  - [ ] 오래된 버전 `409`
  - [ ] 같은 제안·키 재요청이 기존 결과 반환
  - [ ] 다른 키로 중복 적용 차단

### TASK-AI005 AI 이력·선택 복원

- 관련 요구사항: `REQ-AI015`~`REQ-AI017`
- 작업:
  - 적용·복원 이력과 diff 조회
  - 선택 snapshot 복원 preview
  - 재확인 후 복원 트랜잭션
  - 복원 전후 snapshot과 멱등성
- 완료 조건:
  - [ ] 직접 수정 후 과거 AI 이전 상태 복원
  - [ ] 이후 변경 손실 경고 정보 반환
  - [ ] 복원 직전 상태 재복구
  - [ ] 오래된 복원 요청 `409`
  - [ ] 같은 키 복원 재요청 no-op

### TASK-AI006 AI 새 문서 생성

- 관련 요구사항: `REQ-AI018`, `REQ-AI019`
- 작업:
  - AI 초안 저장·수정·취소
  - 폴더 위치 선택
  - 최종 제목·본문으로 멱등 생성
- 현재 llmPipeline 구현 근거:
  - `markdown_create`가 제목, 요약, Markdown 본문을 반환하며 기존 문서를 저장하거나 교체하지 않는다.
  - 생성 결과의 필수 필드와 Markdown 문법을 검증하고 실패 이유를 포함해 1회 보정한다.
  - 대화 요약과 reference context를 비신뢰 source data로 취급하며 system prompt와 분리해 전달한다.
- llmPipeline 범위 완료 조건:
  - [x] `markdown_create` 제목·요약·Markdown 응답 계약
  - [x] 생성 결과 계약 검증·1회 보정·재실패 내부 오류
  - [x] 생성 context prompt injection 회귀 테스트
- 완료 조건:
  - [ ] 초안 생성만으로 문서 미생성
  - [ ] 수정된 제목·본문 저장
  - [ ] 동일 제목·동일 내용 생성 허용
  - [ ] 같은 키 재요청에서 문서 한 건만 생성
  - [ ] 선택한 부모의 가장 뒤에 생성

### TASK-AI007 frontend 채팅·diff

- 관련 요구사항: `REQ-AI001`~`REQ-AI014`, `REQ-AI018`
- 작업:
  - 활성 editor snapshot과 line target 생성
  - action별 채팅 UI
  - 전체 line diff·범위 확장 경고
  - 적용·거절과 문서 전환 무효화
  - `다시 생성` 버튼 없이 후속 메시지 입력
- 완료 조건:
  - [ ] preview 전 문서 불변
  - [ ] 다른 문서 전환 시 적용 버튼 비활성화
  - [ ] 변경 없음에서 적용 버튼 비활성화
  - [ ] 문서 소유자가 아닌 멤버에게 해당 문서 AI 쓰기 UI 미노출
  - [ ] 서버 오류 후 editor 원문 유지

### TASK-AI008 frontend 이력·복원·새 문서

- 관련 요구사항: `REQ-AI015`~`REQ-AI019`
- 작업:
  - AI 이력 목록과 적용 전후 diff
  - 복원 preview·경고·재확인
  - AI 문서 초안 편집과 위치 선택
- 완료 조건:
  - [ ] 임의 AI 이력 선택 복원 E2E
  - [ ] 이후 변경 경고 표시
  - [ ] 복원 결과를 다시 복구 가능
  - [ ] 새 문서 위치 선택 E2E

### TASK-AI009 계약·보안·회귀 검증

- 관련 요구사항: 전체 AI 요구사항
- 작업:
  - Spring–FastAPI contract test
  - prompt injection·권한·로그 테스트
  - GFM fixture와 기존 query 회귀 테스트
  - 요구사항–테스트 추적표와 API 문서 갱신
- 현재 llmPipeline 구현 근거:
  - Agent router, 일반 Markdown 재생성, 구조 보존 source-range, 새 Markdown 생성 경로 모두 Markdown·대화 내용을 비신뢰 입력으로 취급하도록 system prompt에 명시했다.
  - prompt injection 문구가 system prompt와 분리된 user payload로만 전달되는 회귀 테스트가 네 경로에 존재한다.
  - 예상하지 못한 Agent 오류 로그에는 예외 원문과 traceback 대신 안정된 오류 코드와 예외 타입만 기록한다.
  - fenced code·table·display math의 모든 생성 가능한 line range를 순회해 구조 일부만 포함하는 actual target을 거절한다.
  - `docs/spec/agent-markdown-contract.md`, `docs/spec/markdown-ai-editor-scope.md`, `docs/spec/llmpipeline-backend-output-contract.md`를 requested/actual target 계약과 동기화했다.
  - bounded context 벤치마크를 포함한 llmPipeline 전체 테스트가 `463 passed, 43 subtests passed`로 통과했다.
- llmPipeline 범위 완료 조건:
  - [x] router·편집·source-range·생성 prompt injection 회귀 테스트
  - [x] router JSON·필수 action 계약 검증·1회 보정·재실패 내부 오류
  - [x] Agent 기본 오류 로그의 Markdown·모델 원문 미노출
  - [x] GFM 구조·actual target 생성형 property 테스트
  - [x] GFM·HTML·MDX 출력 계약 회귀 테스트
  - [x] 기존 `chat_answer`, `clarify`, `reject` 회귀 테스트
  - [x] llmPipeline API 문서와 요구사항 추적 근거 갱신
  - [x] llmPipeline 전체 테스트와 `git diff --check` 통과
- 완료 조건:
  - [x] 기존 `chat_answer`, `clarify`, `reject` 회귀 없음
  - [x] GFM 보호 fixture 통과
  - [ ] 전체 backend·frontend·llmPipeline 테스트 통과
  - [x] `git diff --check` 통과

## 4. 실행 순서

```text
TASK-AI001 ─┐
TASK-AI002 ─┴→ TASK-AI003 → TASK-AI004 → TASK-AI005
                         └→ TASK-AI006
TASK-AI003/004 → TASK-AI007
TASK-AI005/006 → TASK-AI008
전체 완료 → TASK-AI009
```

## 5. 검증 명령

```sh
cd llmPipeline
.venv/bin/python -m pytest

cd ../backend
./gradlew test

cd ../frontend
npm test
```
