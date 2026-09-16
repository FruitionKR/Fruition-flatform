# Markdown 문서 공유

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-07-23
- 구현 계획: [`markdown-document-sharing-tasks.md`](./tasks/markdown-document-sharing-tasks.md)
- 선행 SDD: [`markdown-document-core.md`](./markdown-document-core.md), [`markdown-document-assets.md`](./markdown-document-assets.md)
- 관련 PR:

상태 흐름: `Draft → Approved → In Progress → Verified`

## 2. 배경

현재 workspace membership은 owner/member role을 저장하지만, 이메일 초대·문서 guest·로그인 없는 웹 공유는 구현되어 있지 않다. 문서 내용 CRUD는 문서 소유자만 수행하고 workspace member는 읽기와 계층 이동을 수행한다.

공유 기능은 Notion의 멤버·guest·웹 링크 구분을 기본으로 하되, MVP의 웹 링크와 guest는 문서 하나만 읽을 수 있게 제한한다. 같은 폴더의 다른 문서, 원본 자료, AI 이력은 자동으로 공개하지 않는다.

## 3. 목표

- 이메일로 workspace member와 문서 guest를 안전하게 초대한다.
- 사용자 제거와 문서·workspace 소유권 이전을 원자적으로 처리한다.
- 로그인 없는 읽기 전용 웹 공유 링크를 제공한다.
- 공개 문서가 참조하는 이미지만 안전하게 표시한다.
- 초대·공유 변경을 감사 가능하게 기록한다.

## 4. 범위

### 포함

- workspace member 이메일 초대·수락·재전송·취소·제거
- 특정 문서 guest 이메일 초대·수락·재전송·취소·제거
- 문서와 workspace 소유권 이전
- 로그인 없는 문서 하나의 웹 공유
- 웹 공유 만료·해제·token 재발급
- 공유 문서의 참조 이미지 조회
- 이메일 outbox, rate limit, 감사 로그
- 공개 Markdown의 XSS 방어

### 제외

- guest 댓글·편집·AI·문서 이동
- 웹 방문자의 댓글·편집·AI·복제·Markdown 다운로드
- 폴더 내 다른 문서 자동 공유
- 원본 자료 외부 공유
- 비밀번호 보호 링크
- 검색엔진 색인
- 공개 페이지 analytics·custom domain
- 여러 활성 웹 링크와 링크별 권한

## 5. 용어

| 용어 | 정의 |
|---|---|
| member | workspace 전체 문서를 읽고 이동하며 자신의 문서를 생성·CRUD하는 사용자 |
| guest | 초대받은 문서 하나만 읽는 로그인 사용자 |
| 웹 공유 | 로그인 없이 불투명 token으로 문서 하나를 읽는 공개 방식 |
| 문서 소유자 | 문서 내용 CRUD·AI 편집·guest·웹 공유를 관리하는 `documents.user_id` |
| workspace 소유자 | member 관리와 workspace 소유권을 관리하는 owner role 사용자 |

## 6. 요구사항

### 6.1 workspace member 공유

#### REQ-S001 member 초대

- workspace 소유자만 이메일로 member를 초대할 수 있다.
- 초대 이메일은 정규화해 같은 workspace의 대기 초대를 중복 생성하지 않는다.
- 이미 member인 이메일은 `409 MEMBER_ALREADY_EXISTS`로 거절한다.
- 초대 token은 7일간 유효한 일회성 난수다.
- 기존 사용자는 로그인 후, 미가입자는 회원가입·로그인 후 수락한다.
- 로그인 계정 이메일과 초대 이메일이 일치해야 한다.

#### REQ-S002 member 권한

- 초대를 수락한 사용자는 `ROLE_MEMBER`가 된다.
- member는 workspace의 활성 문서와 원본 자료를 읽을 수 있다.
- member는 다른 사용자의 문서와 원본을 이동·정렬할 수 있다.
- member는 문서를 생성하고 생성한 문서의 소유자가 된다.
- 다른 사용자가 소유한 문서의 본문·이름·소유권·AI 상태는 변경할 수 없다.

#### REQ-S003 member 초대 관리

- `PENDING` 초대만 재전송·취소할 수 있다.
- 재전송은 이전 미사용 token을 폐기하고 새 7일 token을 발급한다.
- 수락·취소·만료된 token은 다시 사용할 수 없다.
- 초대 수락은 멱등 처리하여 membership을 중복 생성하지 않는다.

### 6.2 문서 guest

#### REQ-S004 guest 초대

- 문서 소유자는 자신이 소유한 문서에 이메일로 guest를 초대할 수 있다.
- workspace 소유자는 모든 문서의 guest를 제거할 수 있다.
- 일반 member는 다른 사용자 소유 문서에 guest를 초대할 수 없다.
- 같은 문서와 이메일에 `PENDING` 초대 또는 활성 guest 접근이 있으면 중복 생성하지 않는다.
- guest 초대도 7일 일회성 token과 로그인 이메일 일치를 요구한다.

#### REQ-S005 guest 접근

- guest는 초대받은 활성 문서 하나만 읽을 수 있다.
- 같은 폴더의 다른 문서, 원본 자료, AI 이력, 다른 내부 문서는 자동으로 공개하지 않는다.
- guest는 생성·편집·복제·삭제·복구·이동·내보내기·AI 기능을 수행할 수 없다.
- 문서 안의 내부 링크는 guest에게 별도 접근 권한이 있을 때만 열린다.

#### REQ-S006 guest 제거

- 문서 소유자 또는 workspace 소유자가 guest 접근을 제거할 수 있다.
- 제거 완료 후 다음 API 요청부터 접근을 차단한다.
- guest의 미사용 초대 token도 함께 폐기한다.
- 재초대는 새로운 접근과 token을 생성하며 과거 접근을 자동 복원하지 않는다.

### 6.3 초대 전달

#### REQ-S007 초대 상태

초대 상태는 다음과 같다.

```text
PENDING ──수락──> ACCEPTED
   ├────취소────> CANCELED
   └────만료────> EXPIRED
```

- 만료는 token 검증 시점에 즉시 판정한다.
- 이메일 전달 상태는 `PENDING`, `SENT`, `FAILED`로 별도 관리한다.
- 이메일 전송 성공만으로 권한을 부여하지 않는다.

#### REQ-S008 이메일 outbox

- 초대와 이메일 outbox를 하나의 DB 트랜잭션에서 생성한다.
- worker가 이메일을 비동기로 전송한다.
- 일시 실패는 지수 backoff로 재시도한다.
- 최종 실패 시 초대는 `PENDING`, 전달 상태는 `FAILED`로 유지한다.
- 초대한 사용자는 전달 실패 초대를 재전송할 수 있다.

### 6.4 소유권과 제거

#### REQ-S009 문서 소유권 이전

- 현재 문서 소유자 또는 workspace 소유자가 소유권을 이전할 수 있다.
- 대상은 같은 workspace의 `ACCEPTED` member여야 한다.
- guest와 대기 사용자는 대상이 될 수 없다.
- 이전 즉시 기존 소유자는 일반 member 권한만 가진다.
- 미적용 AI 제안은 모두 `INVALIDATED`로 변경한다.
- 적용된 AI 이력, guest 접근, 웹 공유는 유지한다.
- 문서 본문과 `current_version`은 변경하지 않는다.

#### REQ-S010 member 제거

- workspace 소유자만 member를 제거할 수 있다.
- 제거 대상이 소유한 모든 문서는 workspace 소유자에게 자동 이전한다.
- 문서의 guest 접근과 웹 공유는 유지한다.
- 문서 이전과 membership 제거는 하나의 트랜잭션으로 처리한다.
- 일부 문서만 이전된 상태로 제거를 완료하지 않는다.
- 제거 후 다음 API 요청부터 접근을 차단하고 미사용 member 초대를 폐기한다.

#### REQ-S011 workspace 소유권 이전

- workspace 소유자는 다른 `ACCEPTED` member에게 workspace 소유권을 이전할 수 있다.
- 마지막 workspace 소유자는 소유권 이전 없이 탈퇴할 수 없다.
- 이전 후 기존 소유자는 일반 member가 된다.
- owner/member role 변경은 하나의 트랜잭션으로 처리한다.

### 6.5 웹 공유

#### REQ-S012 웹 공유 활성화

- 문서 소유자만 자신의 활성 문서에 웹 공유를 활성화할 수 있다.
- 링크를 가진 방문자는 로그인하지 않고 문서 하나를 읽을 수 있다.
- 같은 폴더의 다른 문서와 원본 자료는 자동 공개하지 않는다.
- 문서당 `ACTIVE` 웹 공유는 최대 하나다.
- 활성 상태에서 링크를 다시 조회하면 같은 URL을 반환한다.
- 공개 페이지는 snapshot이 아니라 최신 저장본을 표시한다.
- editor의 미저장 내용은 표시하지 않는다.

#### REQ-S013 웹 공유 만료와 해제

- 기본 만료 값은 `null`이며 만료 없음이다.
- 소유자는 미래의 특정 날짜·시각을 만료 시점으로 지정·변경할 수 있다.
- 만료 시각이 지나면 요청 시점에 즉시 접근을 거절한다.
- 소유자는 웹 공유를 즉시 해제할 수 있다.
- 문서 소프트 삭제 시 웹 공유를 비활성화한다.
- 문서를 복구해도 자동으로 재활성화하지 않는다.

#### REQ-S014 token 재발급

- 명시적 재발급은 기존 공유를 `REVOKED`로 만들고 새 token을 발급한다.
- 해제·만료 후 재활성화할 때도 새 token을 발급한다.
- 이전 token은 다시 유효해지지 않는다.
- token 원문은 DB와 애플리케이션 로그에 저장하지 않고 hash만 저장한다.

#### REQ-S015 공개 권한

- 방문자는 댓글·편집·AI·이동·복제·Markdown 다운로드를 수행할 수 없다.
- 공개 페이지에는 `noindex`, `nofollow`를 적용한다.
- 존재하지 않음·만료·해제·삭제 링크는 같은 접근 불가 화면으로 표시한다.

### 6.6 공개 이미지와 보안

#### REQ-S016 공개 이미지

- 로그인 guest는 자신에게 공유된 문서의 최신 저장본에서 참조하는 이미지만 인증 API로 조회할 수 있다.
- 공개 문서의 최신 저장본에서 실제 참조하는 이미지만 표시한다.
- 내부 asset API와 object storage URL을 방문자에게 노출하지 않는다.
- 공유 token, document, asset 참조 관계를 매 요청 검증한다.
- 다른 문서의 이미지와 현재 본문에서 제거된 이미지는 같은 token으로도 조회할 수 없다.
- 웹 공유가 만료·해제·비활성화되면 이미지 접근도 즉시 차단한다.
- 응답에 `X-Content-Type-Options: nosniff`를 적용한다.

#### REQ-S017 공개 renderer 보안

- 공개 페이지는 읽기 전용 Markdown renderer를 사용한다.
- raw HTML과 MDX를 실행하지 않는다.
- `javascript:` 등 위험한 URL scheme을 차단한다.
- 외부 링크에 안전한 `rel` 속성을 적용한다.
- `Content-Security-Policy`와 `Referrer-Policy: no-referrer`를 적용한다.
- gateway와 access log에서 초대 수락·공유 URL 경로의 token 부분을 마스킹한다.
- Markdown 원문은 저장 시 변경하지 않고 렌더링 경계에서 방어한다.

#### REQ-S018 cache

- 문서 저장 성공 후 다음 공개 요청부터 최신 본문을 반환한다.
- 공개 HTML은 `Cache-Control: private, no-store`를 사용한다.
- 공개 이미지도 공유 상태와 현재 본문 참조를 매 요청 검증한다.
- MVP에서는 CDN 공개 cache를 사용하지 않는다.

### 6.7 요청 제한과 감사

#### REQ-S019 rate limit

- 초대 생성·재전송은 사용자당 시간당 20회다.
- 같은 이메일 재전송은 1분에 1회다.
- 웹 공유 생성·재발급은 문서당 시간당 10회다.
- 공개 문서 조회는 IP당 분당 120회다.
- 공개 이미지는 IP와 공유 token당 분당 300회다.
- 제한 초과는 `429 SHARING_RATE_LIMITED`와 `Retry-After`를 반환한다.

#### REQ-S020 감사 로그

다음 작업의 실행 사용자, 대상 사용자·문서·workspace, 시각, 결과, 오류 코드, 요청 ID를 기록한다.

- member·guest 초대, 수락, 재전송, 취소, 만료, 제거
- 문서·workspace 소유권 이전
- 웹 공유 활성화, 만료 변경, 해제, 재발급

token 원문, Markdown, 이메일 본문은 기록하지 않는다. workspace 소유자만 감사 로그를 조회하며 변경·삭제 API는 제공하지 않는다.

## 7. 설계

### 7.1 초대 데이터

`workspace_invitations`

```text
id, workspace_id, email_normalized, role
status, token_hash, expires_at
invited_by, accepted_user_id, accepted_at, canceled_at
delivery_status, created_at, updated_at
```

`document_guest_invitations`

```text
id, workspace_id, document_id, email_normalized
status, token_hash, expires_at
invited_by, accepted_user_id, accepted_at, canceled_at
delivery_status, created_at, updated_at
```

`document_guest_access`

```text
document_id, user_id, granted_by, granted_at, revoked_at
```

같은 범위와 이메일의 `PENDING` 초대에는 partial unique index를 둔다. 초대 token hash에는 조회 index를 둔다.

### 7.2 웹 공유 데이터

`document_web_shares`

```text
id, workspace_id, document_id
token_hash, status, expires_at
created_by, created_at, updated_at, revoked_at
```

문서당 `ACTIVE` 공유 하나만 허용하는 partial unique index와 token hash 조회 index를 둔다. 원문 token은 생성 응답과 URL 전달 직후 폐기한다.

### 7.3 이메일 outbox

`sharing_email_outbox`

```text
id, invitation_type, invitation_id
recipient_email, template_type
status, attempt_count, next_attempt_at, last_error_code
created_at, sent_at
```

worker는 잠금 가능한 대기 작업을 batch로 가져와 전송한다. 동일 outbox 작업이 재실행되어도 이메일 전달 상태와 초대 권한을 중복 변경하지 않는다.

### 7.4 감사 로그

`sharing_audit_logs`

```text
id, workspace_id, actor_user_id
target_user_id, document_id
action, result, error_code, request_id, created_at
```

감사 로그는 append-only로 저장한다.

### 7.5 권한 결정 순서

```text
인증 사용자
  → workspace owner인가?
  → workspace member인가?
  → document owner인가?
  → document guest인가?

비인증 사용자
  → 유효한 ACTIVE web share인가?
  → 만료·문서 삭제 여부
  → 요청 asset이 최신 본문에 참조되는가?
```

workspace 밖 사용자와 권한 없는 내부 리소스는 존재 여부를 숨기기 위해 `404`로 처리한다. 인증된 member의 허용되지 않은 공유 변경은 `403`으로 처리한다.

## 8. API

### 8.1 member와 소유권

| Method | Endpoint | 역할 |
|---|---|---|
| `POST` | `/api/workspaces/{workspace_id}/invitations` | member 초대 |
| `GET` | `/api/workspaces/{workspace_id}/invitations` | member 초대 목록 |
| `POST` | `/api/workspaces/{workspace_id}/invitations/{invitation_id}/resend` | member 초대 재전송 |
| `DELETE` | `/api/workspaces/{workspace_id}/invitations/{invitation_id}` | member 초대 취소 |
| `POST` | `/api/invitations/{token}/accept` | 로그인 사용자의 member 초대 수락 |
| `DELETE` | `/api/workspaces/{workspace_id}/members/{user_id}` | member 제거·문서 이전 |
| `POST` | `/api/workspaces/{workspace_id}/ownership-transfer` | workspace 소유권 이전 |
| `POST` | `/api/workspaces/{workspace_id}/documents/{document_id}/ownership-transfer` | 문서 소유권 이전 |

### 8.2 guest

| Method | Endpoint | 역할 |
|---|---|---|
| `POST` | `/api/workspaces/{workspace_id}/documents/{document_id}/guest-invitations` | guest 초대 |
| `GET` | `/api/workspaces/{workspace_id}/documents/{document_id}/guests` | guest·대기 초대 조회 |
| `POST` | `/api/workspaces/{workspace_id}/documents/{document_id}/guest-invitations/{invitation_id}/resend` | guest 초대 재전송 |
| `DELETE` | `/api/workspaces/{workspace_id}/documents/{document_id}/guest-invitations/{invitation_id}` | guest 초대 취소 |
| `POST` | `/api/guest-invitations/{token}/accept` | 로그인 사용자의 guest 초대 수락 |
| `DELETE` | `/api/workspaces/{workspace_id}/documents/{document_id}/guests/{user_id}` | guest 접근 제거 |

### 8.3 웹 공유와 감사

| Method | Endpoint | 역할 |
|---|---|---|
| `POST` | `/api/workspaces/{workspace_id}/documents/{document_id}/web-share` | 웹 공유 활성화 |
| `GET` | `/api/workspaces/{workspace_id}/documents/{document_id}/web-share` | 공유 상태·URL 조회 |
| `PATCH` | `/api/workspaces/{workspace_id}/documents/{document_id}/web-share` | 만료 시각 변경 |
| `POST` | `/api/workspaces/{workspace_id}/documents/{document_id}/web-share/rotate` | token 재발급 |
| `DELETE` | `/api/workspaces/{workspace_id}/documents/{document_id}/web-share` | 즉시 해제 |
| `GET` | `/shared/documents/{token}` | 로그인 없는 공개 문서 조회 |
| `GET` | `/shared/documents/{token}/assets/{asset_id}` | 공개 문서 참조 이미지 조회 |
| `GET` | `/api/workspaces/{workspace_id}/documents/{document_id}/guest-assets/{asset_id}` | 로그인 guest의 공유 문서 참조 이미지 조회 |
| `GET` | `/api/workspaces/{workspace_id}/sharing-audit-logs` | 공유 감사 로그 조회 |

감사 로그는 최신순 cursor 페이지네이션과 action·결과·시각·대상 필터를 제공한다.

## 9. 오류

| HTTP | 코드 | 조건 |
|---:|---|---|
| 400 | `INVALID_SHARING_REQUEST` | 이메일·만료 시각·대상 오류 |
| 403 | `SHARING_FORBIDDEN` | 초대·제거·이전 권한 없음 |
| 404 | `SHARING_RESOURCE_NOT_FOUND` | 외부 workspace 또는 없는 내부 대상 |
| 409 | `INVITATION_ALREADY_PENDING` | 동일 범위의 대기 초대 |
| 409 | `MEMBER_ALREADY_EXISTS` | 이미 workspace member |
| 409 | `GUEST_ACCESS_ALREADY_EXISTS` | 이미 문서 guest |
| 409 | `OWNERSHIP_TRANSFER_REQUIRED` | workspace 소유자가 이전 없이 탈퇴 |
| 409 | `OWNERSHIP_TRANSFER_TARGET_INVALID` | guest·대기 사용자 등 잘못된 대상 |
| 410 | `INVITATION_NOT_AVAILABLE` | 만료·취소·사용 완료 token |
| 410 | `WEB_SHARE_NOT_AVAILABLE` | 만료·해제·삭제된 공개 링크 |
| 429 | `SHARING_RATE_LIMITED` | 요청 제한 초과 |
| 503 | `EMAIL_DELIVERY_UNAVAILABLE` | 이메일 전달 인프라 상태 확인 불가 |

## 10. 인수 조건

- 다른 이메일 계정으로 초대 token을 수락할 수 없다.
- 같은 초대 token을 두 번 수락해도 membership이나 guest 접근이 중복 생성되지 않는다.
- 이메일 전송 실패에도 초대와 outbox 상태가 일치하고 권한은 부여되지 않는다.
- member 제거와 모든 소유 문서의 이전이 원자적으로 처리된다.
- 일반 member는 다른 사용자의 문서 내용을 수정할 수 없지만 이동할 수 있다.
- 문서당 활성 웹 공유가 하나만 존재한다.
- 재발급 후 이전 token으로 문서와 이미지를 조회할 수 없다.
- 공개 문서에서 참조하지 않는 asset은 유효한 token으로도 조회할 수 없다.
- guest는 공유받은 문서가 참조하는 이미지만 조회할 수 있다.
- 공유 해제·만료·문서 삭제 직후 공개 문서와 이미지 접근이 차단된다.
- 공개 페이지에서 raw HTML·MDX·위험 URL이 실행되지 않는다.
- 애플리케이션·gateway·access log에 token·Markdown·이메일 본문이 남지 않는다.

## 11. 검증

| 영역 | 검증 방법 | 결과 |
|---|---|---|
| 초대 상태·이메일 일치 | 서비스 단위·API 통합 테스트 | Pending |
| outbox 재시도·멱등성 | worker·Testcontainers 통합 테스트 | Pending |
| member 제거·소유권 이전 | 트랜잭션 통합 테스트 | Pending |
| 웹 공유 token·만료 | Security·API 통합 테스트 | Pending |
| 공개 이미지 참조 | asset·공유 통합 테스트 | Pending |
| 공개 renderer XSS | frontend component·E2E 테스트 | Pending |
| rate limit·감사 로그 | API·로그 보안 테스트 | Pending |

## 12. 미결정 사항

- 이메일 발송 provider와 template 디자인
- 초대·공유 데이터의 영구 보존 기간
- guest 댓글 도입 여부
- 공개 페이지 CDN cache 도입 기준

## 13. 결과

- 검증일:
- 최종 상태: Pending
- 남은 문제: 위 미결정 사항
