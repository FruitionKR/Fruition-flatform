# Markdown 문서 AI 편집

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-07-23
- 구현 계획: [`markdown-document-ai-editing-tasks.md`](./tasks/markdown-document-ai-editing-tasks.md)
- 선행 SDD: [`markdown-document-core.md`](./markdown-document-core.md), [`markdown-document-hierarchy.md`](./markdown-document-hierarchy.md)
- 구현 근거: [`../../spec/markdown-ai-editor-scope.md`](../../spec/markdown-ai-editor-scope.md), [`../../spec/agent-markdown-contract.md`](../../spec/agent-markdown-contract.md)
- 관련 PR:

상태 흐름: `Draft → Approved → In Progress → Verified`

## 2. 배경

`llmPipeline`에는 `/agent/turn` 라우팅, Markdown 편집·생성, 출력 계약 보정, GFM 검증이 구현되어 있다. 현재 frontend Agent panel과 Spring backend 저장 흐름은 편집 제안, diff, 적용, AI 이력 복원까지 연결되지 않았다.

AI는 문서를 직접 저장하지 않는다. 소유자가 diff를 검토하고 적용한 결과만 서버가 저장하며, AI 적용 전후 전체 스냅샷으로 과거 AI 편집 시점을 선택 복원한다.

## 3. 목표

- 현재 열린 Markdown을 인식해 선택 영역·현재 섹션·전체 문서를 편집한다.
- AI 결과의 전체 diff를 적용 전에 제공한다.
- AI 제안의 적용·거절·무효화와 요청 재전송을 안전하게 관리한다.
- AI 적용 전 상태를 선택해 복원할 수 있게 한다.
- 채팅에서 새 Markdown 문서 초안을 만들고 폴더 트리에 생성한다.

## 4. 범위

### 포함

- 기존 채팅 세션 기반 AI 응답
- `selection`, `current_section`, `whole_document`
- `replace`, `insert_after`
- `chat_answer`, `markdown_edit`, `markdown_create`, `clarify`, `reject`
- 편집 제안, diff, 적용, 거절, 무효화
- 요청 범위 밖 변경 경고
- AI 적용 전후 스냅샷과 선택 복원
- 새 Markdown 초안 편집·생성
- 권한, 오류, 보안, 멱등성

### 제외

- 자동 저장과 임시 draft
- `다시 생성` 전용 버튼
- AI 결과 일부 적용
- 일반 수동 편집의 버전 이력
- 실시간 공동편집과 자동 병합
- 토큰 단위 스트리밍
- HTML·MDX 결과

## 5. 요구사항

### 5.1 채팅과 활성 문서

#### REQ-AI001 채팅 세션

- 채팅 세션은 특정 문서에 종속되지 않는다.
- 사용자는 여러 채팅 세션을 생성하고 이전 세션을 다시 열 수 있다.
- 사용자 메시지, AI 답변, 편집 제안, 적용·거절 결과를 기존 채팅 저장 방식으로 보관한다.
- AI 요청에는 최근 메시지와 최대 8,000자의 `conversation_summary`를 전달한다.
- 별도의 `다시 생성` 기능 없이 새 채팅 메시지로 추가 피드백을 전달한다.

#### REQ-AI002 활성 문서

- AI는 요청 시점에 편집기에서 열린 문서 하나만 편집 대상으로 삼는다.
- 요청에는 `document_id`, 현재 Markdown, `base_version`, 선택적 target을 포함한다.
- 이전 문서 대화는 문맥으로 참고할 수 있지만 이전 문서를 수정할 수 없다.
- 활성 문서의 소유자만 해당 문서의 AI 편집을 요청할 수 있다.
- 다른 워크스페이스 멤버는 AI가 적용된 문서를 읽고 이동할 수 있지만 AI 편집 UI와 API를 사용할 수 없다.
- 모든 워크스페이스 멤버는 AI 새 문서 생성을 요청할 수 있으며 생성된 문서의 소유자가 된다.

#### REQ-AI003 문서 전환

- 제안은 생성 당시 `document_id`와 `base_version`에 연결한다.
- 미적용 제안이 있는 상태에서 다른 문서를 열면 제안을 `INVALIDATED`로 변경한다.
- 원래 문서를 다시 열어도 제안을 재활성화하지 않는다.
- 무효화된 제안과 diff는 채팅 기록에서 조회할 수 있다.

### 5.2 AI 편집 생성

#### REQ-AI004 편집 범위

- target type은 `selection`, `current_section`, `whole_document`다.
- 범위는 1부터 시작하고 양 끝 줄을 포함한다.
- MVP는 글자 단위 선택을 지원하지 않는다.
- target이 없고 활성 Markdown이 있으면 전체 문서를 대상으로 해석한다.
- Markdown 구조 일부만 잘라 정상 결과를 만들 수 없는 요청은 pipeline이 `422`로 거절한다.

#### REQ-AI005 편집 연산

- `replace`는 실제 대상 범위를 replacement Markdown으로 교체한다.
- `insert_after`는 실제 대상의 마지막 줄 다음에 Markdown을 삽입한다.
- 삽입 위치가 불명확하면 `clarify`를 반환한다.
- AI는 편집 결과와 변경 요약을 반환한다.

#### REQ-AI006 요청 범위 확장

- `requested_target`은 사용자가 요청한 범위다.
- `actual_target`은 AI가 실제로 변경하려는 범위다.
- `actual_target`은 `requested_target`을 포함해야 한다.
- actual target이 요청 범위를 벗어나도 제안을 자동 거절하지 않는다.
- 전체 문서 후보와 diff를 생성하고 `scope_expanded=true`를 표시한다.
- 프론트엔드는 범위 확장 경고를 표시한다.
- 사용자는 전체 변경을 적용하거나 거절하며 일부 적용은 지원하지 않는다.

기존 pipeline의 “응답 target은 요청 target과 일치해야 한다” 검증은 actual target을 검증하는 계약으로 변경한다. 실제 범위가 문서 밖이거나 Markdown 구조를 깨뜨려 후보를 만들 수 없으면 계약 오류로 처리한다.

#### REQ-AI007 응답 계약 오류

- JSON 파싱 실패, 필수 필드 누락, 미지원 action·operation·target, 유효하지 않은 범위, replacement 누락, HTML·MDX 결과는 계약 오류다.
- pipeline은 내부 계약 보정을 최대 1회 시도한다.
- 재실패 시 외부 API는 `422 AI_EDIT_GENERATION_FAILED`를 반환한다.
- 내부 prompt, 잘못된 모델 원문, 스택 트레이스를 노출하지 않는다.
- 오류 시 문서, 버전, 제안, AI 스냅샷을 변경하지 않는다.

#### REQ-AI008 변경 사항 없음

- 생성한 전체 문서 후보가 현재 Markdown과 같으면 `changed=false`를 반환한다.
- 적용 버튼을 비활성화한다.
- 문서 저장, 버전 증가, 제안 적용, 스냅샷 생성을 수행하지 않는다.

### 5.3 편집 제안

#### REQ-AI009 제안 저장

`markdown_edit` 결과는 저장 전에 `ai_edit_proposals`에 보관한다.

| 상태 | 의미 |
|---|---|
| `PROPOSED` | 사용자 결정을 기다림 |
| `APPLIED` | 문서에 적용됨 |
| `REJECTED` | 사용자가 거절함 |
| `INVALIDATED` | 문서·버전·대화 변경으로 적용 불가 |
| `FAILED` | 계약 오류. 오류 기록만 존재하고 적용 가능한 후보는 없음 |

제안은 채팅·메시지, 문서·버전, 지시문, 요청·실제 범위, 연산, 변경 전후 전체 Markdown, 요약, 범위 확장 여부, 상태 시각을 저장한다.

#### REQ-AI010 제안 무효화

시간 기반 만료는 두지 않는다. 다음 경우 `PROPOSED`를 `INVALIDATED`로 변경한다.

- 사용자가 다른 문서를 엶
- 대상 문서의 `current_version`이 변경됨
- 같은 채팅에서 같은 문서의 새 편집 제안이 생성됨
- 채팅 세션이 삭제됨

문서 전환 시 frontend는 제안 무효화 API를 호출한다. 적용 API도 현재 상태와 버전을 다시 검사한다.

#### REQ-AI011 diff와 결정

- frontend는 변경 전후 전체 Markdown으로 line diff를 표시한다.
- `scope_expanded=true`이면 별도 경고를 표시한다.
- 사용자는 `적용` 또는 `거절`을 선택한다.
- `거절`하면 제안 상태만 변경하고 문서·버전·스냅샷을 변경하지 않는다.

### 5.4 적용과 충돌

#### REQ-AI012 제안 적용

- 적용 요청은 `proposal_id`, `base_version`, `Idempotency-Key`를 포함한다.
- 소유자이며 제안 상태가 `PROPOSED`이고 버전이 일치할 때만 적용한다.
- 변경 전 스냅샷, 문서 본문·버전, 변경 후 스냅샷, 제안 상태를 한 트랜잭션에서 저장한다.
- 적용은 일반 수동 저장을 기다리지 않고 즉시 서버에 저장한다.
- 적용 성공 시 `current_version`을 1 증가시킨다.

#### REQ-AI013 충돌

- 공동편집은 지원하지 않지만 같은 소유자의 여러 탭·기기 충돌을 막기 위해 `base_version`을 유지한다.
- 버전이 다르면 `409 DOCUMENT_VERSION_CONFLICT`로 적용을 거절한다.
- 자동 병합이나 rebase를 수행하지 않는다.
- 최신 문서를 불러온 뒤 새 채팅 메시지로 다시 요청한다.

#### REQ-AI014 멱등 적용

- 같은 사용자·endpoint·`Idempotency-Key`의 24시간 내 재요청은 최초 결과를 반환한다.
- 같은 `proposal_id`는 한 번만 적용할 수 있다.
- 다른 키로 적용 완료 제안을 다시 요청하면 `409 AI_PROPOSAL_NOT_APPLICABLE`을 반환한다.
- `insert_after`가 요청 재전송으로 두 번 삽입되어서는 안 된다.

### 5.5 AI 이력과 복원

#### REQ-AI015 AI 스냅샷

- AI 적용마다 전체 본문의 `AI_EDIT_BEFORE`와 `AI_EDIT_APPLIED` 스냅샷을 생성한다.
- 일반 수동 편집은 스냅샷이나 범용 버전 이력을 생성하지 않는다.
- 이력에는 적용 시각, 변경 요약, 적용 전후 diff를 제공한다.
- 적용된 제안과 스냅샷은 채팅 세션을 삭제해도 유지한다.

#### REQ-AI016 선택 복원

- 소유자는 적용된 AI 편집 이력 중 원하는 항목을 선택한다.
- 복원 전 현재 문서와 선택한 `AI_EDIT_BEFORE` 전체 본문의 diff를 표시한다.
- 선택한 시점 이후 변경이 있으면 이후 직접 수정과 AI 편집도 사라진다는 경고를 표시한다.
- 사용자의 재확인 후 선택 스냅샷의 전체 본문을 즉시 저장한다.
- 복원 요청은 `base_version`과 `Idempotency-Key`를 포함한다.
- 복원 성공 시 `current_version`을 1 증가시킨다.

#### REQ-AI017 복원 이력

- 복원 직전과 복원 결과의 전체 스냅샷을 별도 AI 복원 이력으로 기록한다.
- 사용자는 복원 이력을 선택해 복원 직전 상태로 다시 복구할 수 있다.
- 복원 재요청은 멱등 처리한다.
- 버전이 다르면 현재 문서를 변경하지 않고 `409`를 반환한다.

### 5.6 새 문서 생성

#### REQ-AI018 새 문서 초안

- `markdown_create`는 제목, 요약, Markdown 본문을 반환한다.
- 초안은 자동 저장하지 않는다.
- 사용자는 제목과 본문을 직접 수정할 수 있다.
- `취소`하면 초안을 폐기한다.
- 별도 `다시 생성` 버튼 없이 새 채팅 메시지로 후속 요청한다.

#### REQ-AI019 새 문서 저장

- `문서 생성`을 누르면 사용자가 최종 수정한 제목과 본문을 저장한다.
- 현재 열린 페이지와 같은 부모 위치를 기본 생성 위치로 제안한다.
- 사용자는 다른 페이지 아래 또는 페이지 최상위를 선택할 수 있다.
- 새 페이지는 선택한 위치의 가장 뒤에 생성한다.
- 동일 제목·동일 내용 페이지를 허용한다.
- 생성 요청은 `Idempotency-Key`로 동일 요청 재실행만 방지한다.
- 생성 초안은 AI 편집 이력으로 기록하지 않는다.

### 5.7 제한과 보안

#### REQ-AI020 입력 제한

- 사용자 메시지는 최대 4,000자다.
- 활성 Markdown은 최대 200,000자다.
- `conversation_summary`는 최대 8,000자다.
- 제한 초과는 `413 AI_CONTEXT_TOO_LARGE`다.
- 전체 문서가 제한을 넘으면 선택 영역 또는 현재 섹션 편집만 허용한다.
- AI 제한은 문서 저장 가능 크기를 변경하지 않는다.

#### REQ-AI021 시간 초과와 가용성

- 동기식 `POST /agent/turn` 전체 제한 시간은 60초다.
- 시간 초과는 `504 AI_RESPONSE_TIMEOUT`, 연결 실패는 `503 AI_SERVICE_UNAVAILABLE`이다.
- Spring backend는 전체 AI 요청을 자동 재실행하지 않는다.
- 실패 시 원문, 버전, 제안 상태를 변경하지 않는다.

#### REQ-AI022 보안 경계

- Markdown과 채팅 내용은 신뢰할 수 없는 사용자 데이터로 취급한다.
- 본문 안의 지시문을 system instruction으로 실행하지 않는다.
- llmPipeline은 workspace 접근·문서 저장 권한을 갖지 않는다.
- Spring backend만 권한과 실제 저장을 수행한다.
- 기본 로그에는 전체 Markdown이나 모델 원문 대신 요청 ID, 문서 ID, 문자 수, action, 오류 코드만 기록한다.

### 5.8 보존

#### REQ-AI023 보존과 삭제

- 채팅과 AI 이력은 관련 문서와 채팅이 존재하는 동안 보관한다.
- 채팅 세션 삭제 시 메시지와 미적용 제안을 소프트 삭제한다.
- 적용된 제안과 AI 스냅샷은 복원을 위해 유지한다.
- 문서 소프트 삭제 시 AI 이력을 조회할 수 없다.
- 문서 복구 시 AI 이력을 다시 조회할 수 있다.
- 문서 영구 삭제 시 관련 제안, 스냅샷, 채팅 연결 정보를 영구 삭제한다.

## 6. 설계

### 6.1 책임 경계

```text
Frontend
  → 활성 editor snapshot·target·message 전송
Spring backend
  → 인증·소유자 권한·버전 확인
  → 채팅 저장 및 llmPipeline 호출
llmPipeline POST /agent/turn
  → action 분류·Markdown 제안 생성·계약 검증
Spring backend
  → 전체 후보 구성·proposal 저장
Frontend
  → diff·경고·적용/거절
Spring backend
  → 적용·스냅샷·복원 트랜잭션
```

Spring backend는 `document_id`와 `base_version`을 llmPipeline에 전달하지 않는다. pipeline은 Markdown 제안만 생성하고 저장하지 않는다.

### 6.2 데이터 모델

`ai_edit_proposals`

```text
id, workspace_id, chat_session_id, message_id
document_id, base_version, instruction
operation, requested_target, actual_target
before_markdown, after_markdown, summary
scope_expanded, status
created_at, applied_at, rejected_at, invalidated_at
```

`ai_document_snapshots`

```text
id, document_id, proposal_id, restore_operation_id
snapshot_type
document_version
markdown, content_hash
created_by, created_at
```

`snapshot_type`은 `AI_EDIT_BEFORE`, `AI_EDIT_APPLIED`, `AI_RESTORE_BEFORE`, `AI_RESTORE_APPLIED`다.

전체 Markdown 중복 저장은 AI 적용·복원 시점에만 발생한다. 일반 수동 저장에는 snapshot을 만들지 않는다.

### 6.3 proposal 생성

Spring backend는 pipeline의 `actual_target`과 `replacement_markdown`을 현재 snapshot에 적용해 `after_markdown`을 만든다. `replace`와 `insert_after`는 서버의 동일한 Markdown line-range 모듈을 사용한다. 후보 생성 실패 시 proposal을 적용 가능한 상태로 저장하지 않는다.

### 6.4 트랜잭션

적용과 복원은 각각 다음 변경을 단일 DB 트랜잭션으로 처리한다.

- `documents.current_version` 조건부 증가
- `document_edit_states` 전체 본문과 hash 갱신
- 전후 snapshot 생성
- proposal 또는 restore 상태 갱신
- 멱등성 결과 저장

## 7. API

| Method | Endpoint | 역할 |
|---|---|---|
| `POST` | `/api/workspaces/{workspace_id}/agent/turn` | 채팅·AI 편집·문서 생성 요청 |
| `GET` | `/api/workspaces/{workspace_id}/ai-edit-proposals/{proposal_id}` | 제안과 diff 조회 |
| `POST` | `/api/workspaces/{workspace_id}/ai-edit-proposals/{proposal_id}/apply` | 제안 즉시 적용 |
| `POST` | `/api/workspaces/{workspace_id}/ai-edit-proposals/{proposal_id}/reject` | 제안 거절 |
| `POST` | `/api/workspaces/{workspace_id}/ai-edit-proposals/{proposal_id}/invalidate` | 문서 전환 시 무효화 |
| `GET` | `/api/workspaces/{workspace_id}/documents/{document_id}/ai-history` | AI 적용·복원 이력 조회 |
| `POST` | `/api/workspaces/{workspace_id}/documents/{document_id}/ai-history/{history_id}/restore` | 선택 상태 복원 |
| `POST` | `/api/workspaces/{workspace_id}/ai-document-drafts/{draft_id}/create` | 수정한 AI 초안을 페이지로 생성 |

`/agent/turn`은 MVP에서 동기식 전체 응답을 반환한다.

## 8. 오류

| HTTP | 코드 | 조건 |
|---:|---|---|
| 400 | `INVALID_AI_EDIT_REQUEST` | 빈 메시지·잘못된 범위 |
| 403 | `AI_EDIT_FORBIDDEN` | 문서 소유자가 아닌 사용자의 편집·적용·복원 요청 |
| 404 | `DOCUMENT_NOT_FOUND` | 문서가 없거나 접근 범위 밖 |
| 409 | `DOCUMENT_VERSION_CONFLICT` | `base_version` 불일치 |
| 409 | `AI_PROPOSAL_NOT_APPLICABLE` | 적용 불가능한 제안 상태 |
| 413 | `AI_CONTEXT_TOO_LARGE` | 입력 제한 초과 |
| 422 | `AI_EDIT_GENERATION_FAILED` | 계약 보정 후에도 제안 생성 실패 |
| 503 | `AI_SERVICE_UNAVAILABLE` | pipeline 연결 실패 |
| 504 | `AI_RESPONSE_TIMEOUT` | 60초 초과 |

pipeline의 `markdown_output_contract_failed`, `markdown_target_crosses_structure` 등 내부 코드는 관측 정보로 보존하되 Spring 외부 계약으로 그대로 노출하지 않는다.

## 9. 인수 조건

- 선택 영역 편집은 적용 전 diff를 표시하고 적용 전에는 문서를 변경하지 않는다.
- 범위 밖 변경은 경고와 전체 diff를 표시하고 사용자가 적용하거나 거절할 수 있다.
- 변경 없는 결과는 저장·버전·snapshot을 만들지 않는다.
- 같은 제안 적용 재요청이 `insert_after`를 중복 삽입하지 않는다.
- 다른 탭에서 저장 후 오래된 제안 적용은 `409`다.
- 과거 AI 편집을 선택하면 현재 문서와 복원본 diff 및 데이터 손실 경고가 표시된다.
- 직접 수정 이후에도 과거 AI 편집 전 상태로 복원할 수 있다.
- 복원을 다시 선택해 복원 직전 상태로 돌아갈 수 있다.
- 문서 소유자가 아닌 멤버에게 해당 문서의 AI 쓰기 UI가 없고 직접 API 요청도 `403`이다.
- AI 새 문서는 선택한 페이지 위치의 가장 뒤에 한 번만 생성된다.
- prompt injection 문구가 있는 Markdown도 저장 권한이나 system prompt를 변경하지 못한다.

## 10. 검증

| 영역 | 검증 방법 |
|---|---|
| router·출력 계약 | llmPipeline 단위 테스트 |
| GFM 구조·actual target | fixture·property 기반 테스트 |
| proposal 상태 전이 | Spring 서비스 단위 테스트 |
| 적용·복원 트랜잭션 | Testcontainers 통합 테스트 |
| 멱등성·낙관적 잠금 | 동시 요청 통합 테스트 |
| diff·경고·권한 UI | frontend component/E2E 테스트 |
| pipeline 연동 | Spring–FastAPI contract test |

## 11. 미결정 사항

- 장기 보관 시 snapshot 압축·object storage 이전 기준
- AI 호출 사용량 제한과 과금 정책
- streaming 응답 도입 시점

## 12. 결과

- 검증일:
- 최종 상태: Pending
- 남은 문제: 위 미결정 사항
