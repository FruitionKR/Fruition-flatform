# Fruition MVP API Contract

## 1. 기준

- MVP 목표: 파일명을 몰라도 개념이나 질문만으로 관련 Wiki page와 원본 근거를 찾을 수 있는지 검증
- 이메일/비밀번호 로그인 + Google/Naver/Kakao OAuth 로그인 지원
- 유저는 여러 워크스페이스를 가질 수 있음 (회원가입/최초 OAuth 로그인 시 기본 워크스페이스 1개 자동 생성)
- 워크스페이스는 지금은 유저 1명만 소속되는 구조(공유 기능은 아직 없음)
- 원본 파일은 Object Storage에 저장
- 서비스 관리 정보는 PostgreSQL에 저장
- 그래프 node는 `wiki_pages`
- 그래프 edge는 `wiki_page_links`
- 원본 파일은 그래프 node가 아니며, `source page`가 원본 문서를 대표

이전(로그인 없음, 단일 기본 workspace) 기준 계약은 `docs/backlog/Fruition_MVP_API_Contract.md` 참고.

## 2. 공통 규칙

### Base URL

```text
/api
```

### 인증

현재 Spring Security 설정 기준 인증 필수 경로는 다음과 같다.

- `GET /api/auth/me`
- `/api/workspaces/**`

위 경로는 `Authorization` 헤더에 access token이 필요하다.

```text
Authorization: Bearer {access_token}
```

- access token은 JWT(HS256), 짧은 만료 시간(기본 900초)을 가진다.
- 만료되면 `POST /api/auth/refresh`로 재발급받는다.
- 인증이 없거나 유효하지 않으면 `401 Unauthorized`를 반환한다.
- `/api/auth/signup`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout`, `/api/auth/oauth/exchange`, `/oauth2/**`는 인증 없이 호출한다.
- `/api/documents/{document_id}/status`, `/api/documents/{document_id}/pipeline-events`, `/api/query/runs/**`는 내부 콜백/비동기 run 조회용 flat 경로이며 현재 보안 설정상 인증 없이 접근 가능하다.

### 워크스페이스 소유권

`/api/workspaces/{workspace_id}/**` 하위 API는 요청자가 해당 워크스페이스에 접근 권한이 있는지 항상 확인한다. 접근 권한이 없으면(다른 사용자의 워크스페이스이거나 존재하지 않으면) `404 Not Found`(`WORKSPACE_NOT_FOUND`)를 반환한다. 403 대신 404를 쓰는 이유는 워크스페이스 존재 여부 자체를 노출하지 않기 위함이다.

### CORS

`/api/**`는 `app.cors.allowed-origins` 설정값(기본 `http://localhost:3000`)에 등록된 origin의 fetch/XHR 요청을 허용한다.

### 공통 응답 형식

성공 응답은 API별 data 형식을 그대로 반환한다.

실패 응답:

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "문서를 찾을 수 없습니다."
  }
}
```

### 공통 에러 응답

#### 400 Bad Request

요청 값이 잘못된 경우.

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "요청 형식이 올바르지 않습니다.",
    "details": [
      {
        "field": "question",
        "reason": "질문은 비어 있을 수 없습니다."
      }
    ]
  }
}
```

#### 401 Unauthorized

인증이 없거나 유효하지 않은 경우.

```json
{
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "이메일 또는 비밀번호가 올바르지 않습니다."
  }
}
```

#### 404 Not Found

요청한 리소스가 없거나 접근 권한이 없는 경우.

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "문서를 찾을 수 없습니다."
  }
}
```

#### 409 Conflict

이미 같은 리소스가 존재하거나 현재 상태에서 처리할 수 없는 경우.

```json
{
  "error": {
    "code": "DOCUMENT_ALREADY_EXISTS",
    "message": "이미 업로드된 문서입니다."
  }
}
```

#### 415 Unsupported Media Type

지원하지 않는 파일 형식인 경우.

```json
{
  "error": {
    "code": "UNSUPPORTED_FILE_TYPE",
    "message": "PDF 또는 Markdown 파일만 업로드할 수 있습니다."
  }
}
```

#### 500 Internal Server Error

서버 내부 오류가 발생한 경우.

```json
{
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "서버 처리 중 오류가 발생했습니다."
  }
}
```

#### 502 / 503 (Query pipeline)

질의 파이프라인이 요청을 거부하거나(502) 응답하지 못하는 경우(503). "7. Query API"의 에러 코드 표 참고.

### optional 필드 규칙

아직 값이 생성되지 않았거나 해당 상태에서 필요 없는 값은 응답에서 생략할 수 있다.

예:

```text
extracted_text_uri
- 문서 업로드 직후에는 아직 텍스트 추출 전이므로 생략 가능
- 처리 완료 후에는 sources/documents/{document_id}/extracted.txt

processed_at
- 처리 중에는 생략 가능
- completed 또는 failed 상태가 되면 처리 종료 시각

error_message
- 정상 처리 중이거나 성공이면 생략
- failed 상태이면 실패 사유
```

프론트는 `status`를 기준으로 화면을 분기하고, optional 필드는 없을 수 있다고 처리한다.

### 공통 Enum

#### document status

```text
uploaded
processing
completed
failed
```

#### wiki page type

```text
source
concept
```

#### wiki page status

```text
draft
active
failed
```

#### chat role

```text
user
assistant
```

#### chat message status

```text
completed
failed
```

#### query run status

```text
pending
running
succeeded
failed
```

#### link type

```text
source_mentions_concept
concept_related_to
concept_contrasts_with
source_related_to
```

#### document wiki relation type

```text
source_of
extracted_concept
```

#### workspace member role

```text
owner
member
```

멤버 초대/제거 기능은 아직 없어서, 지금은 워크스페이스마다 `owner` role인 유저 1명만 존재한다.

## 3. Object Storage 경로 규칙

```text
sources/documents/{document_id}/original
sources/documents/{document_id}/extracted.txt
wiki/{user_id}/{workspace_id}/sources/{document_slug}.md
wiki/{user_id}/{workspace_id}/concepts/{concept_slug}.md
wiki/{user_id}/{workspace_id}/clusters/active.md
wiki/{user_id}/{workspace_id}/logs/{yyyy-mm-dd}.md
```

## 4. API 목록

```text
# Auth (인증 불필요)
POST   /api/auth/signup
POST   /api/auth/login
POST   /api/auth/refresh
POST   /api/auth/logout
POST   /api/auth/oauth/exchange
GET    /oauth2/authorization/{provider}     # google | naver | kakao, Spring Security 관리

# Auth (인증 필요)
GET    /api/auth/me

# Workspaces
POST   /api/workspaces
GET    /api/workspaces
PATCH  /api/workspaces/{workspace_id}
DELETE /api/workspaces/{workspace_id}

# Documents (workspace 하위)
POST   /api/workspaces/{workspace_id}/documents
GET    /api/workspaces/{workspace_id}/documents
GET    /api/workspaces/{workspace_id}/documents/{document_id}
GET    /api/workspaces/{workspace_id}/documents/{document_id}/original
GET    /api/workspaces/{workspace_id}/documents/{document_id}/blocks
PATCH  /api/workspaces/{workspace_id}/documents/{document_id}/rename
DELETE /api/workspaces/{workspace_id}/documents/{document_id}

# Wiki (workspace 하위)
GET    /api/workspaces/{workspace_id}/wiki/graph
GET    /api/workspaces/{workspace_id}/wiki/pages/{wiki_page_id}
PATCH  /api/workspaces/{workspace_id}/wiki/pages/{wiki_page_id}/rename

# Chat Sessions (workspace 하위)
POST   /api/workspaces/{workspace_id}/chat/sessions
GET    /api/workspaces/{workspace_id}/chat/sessions
DELETE /api/workspaces/{workspace_id}/chat/sessions/{session_id}
GET    /api/workspaces/{workspace_id}/chat/sessions/{session_id}/messages
POST   /api/workspaces/{workspace_id}/chat/sessions/{session_id}/wiki           # 채팅 Wiki page화 export
POST   /api/workspaces/{workspace_id}/chat/sessions/{session_id}/wiki/preview   # [임시] 직렬화 Markdown 미리보기

# Query (workspace + session 하위)
POST   /api/workspaces/{workspace_id}/chat/sessions/{session_id}/query
POST   /api/workspaces/{workspace_id}/chat/sessions/{session_id}/query/runs

# Query Run (비동기 진행상황 조회 — 인증 없이 request_id로 접근)
GET    /api/query/runs/{request_id}
GET    /api/query/runs/{request_id}/events            # Server-Sent Events
POST   /api/query/runs/{request_id}/events/callback    # llmPipeline 전용 콜백
```

## 5. Auth API

### 5.1 이메일 회원가입

```http
POST /api/auth/signup
Content-Type: application/json
```

Request:

```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

| field | type | required | description |
| --- | --- | --- | --- |
| `email` | string | O | 이메일 형식 검증 |
| `password` | string | O | 8~72자 |

Response (`201`):

```json
{
  "id": "user_1f9a74af",
  "email": "user@example.com",
  "display_name": "use",
  "created_at": "2026-07-03T10:00:00Z"
}
```

처리 규칙:

- `display_name`은 이메일 앞 3글자로 자동 생성한다.
- 가입과 동시에 기본 워크스페이스(`"{display_name}의 워크스페이스"`)를 트랜잭션으로 함께 생성한다. 워크스페이스 생성이 실패하면 회원가입 자체가 롤백된다.
- 이 API는 토큰을 발급하지 않는다. 가입 직후 `POST /api/auth/login`을 호출해야 한다.

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `DUPLICATE_EMAIL` | 409 | 이미 가입된 이메일이다. |

### 5.2 로그인

```http
POST /api/auth/login
Content-Type: application/json
```

Request:

```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

Response (`200`):

```json
{
  "access_token": "eyJhbGciOiJIUzM4NCJ9...",
  "refresh_token": "3CMO2JGusOn8MAoK942ISt51y0YKhj56s4RypT7fmbs",
  "token_type": "Bearer",
  "expires_in": 900
}
```

| field | description |
| --- | --- |
| `access_token` | JWT. `Authorization: Bearer {access_token}` 헤더로 사용 |
| `refresh_token` | opaque 문자열. DB에는 SHA-256 해시로만 저장 |
| `expires_in` | access token 만료까지 남은 초 |

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `INVALID_CREDENTIALS` | 401 | 이메일 또는 비밀번호가 일치하지 않는다. |

### 5.3 토큰 재발급

```http
POST /api/auth/refresh
Content-Type: application/json
```

Request:

```json
{
  "refresh_token": "3CMO2JGusOn8MAoK942ISt51y0YKhj56s4RypT7fmbs"
}
```

Response (`200`): `5.2`와 동일한 형식. 새 `access_token`/`refresh_token`을 발급하고 기존 refresh token은 즉시 폐기한다(rotation).

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `INVALID_REFRESH_TOKEN` | 401 | 존재하지 않거나 만료·폐기된 refresh token이다. |

### 5.4 로그아웃

```http
POST /api/auth/logout
Content-Type: application/json
```

Request: `5.3`과 동일한 `refresh_token` body.

Response: `204 No Content`. 해당 refresh token을 폐기한다.

### 5.5 OAuth 로그인

```http
GET /oauth2/authorization/{provider}
```

`{provider}`는 `google` | `naver` | `kakao`. Spring Security가 처리하는 브라우저 리다이렉트 흐름이며, 백엔드 커스텀 컨트롤러가 아니다.

흐름:

1. 프론트가 브라우저를 `GET /oauth2/authorization/{provider}`로 이동시킨다.
2. provider 로그인 완료 후 백엔드 콜백(`/login/oauth2/code/{provider}`)으로 돌아온다.
3. 백엔드가 유저를 조회/생성(최초 로그인이면 `users` + 기본 워크스페이스 자동 생성 + `user_oauth_accounts` 연결)하고, 1회용 `code`를 발급해 `app.oauth.frontend-redirect-uri`(기본 `http://localhost:3000/oauth/callback`)로 `?code=...`를 붙여 리다이렉트한다.
4. 프론트는 `code`를 즉시 `POST /api/auth/oauth/exchange`로 교환한다.

`code`는 1회용이며 발급 후 60초가 지나면 만료된다.

### 5.6 OAuth code 교환

```http
POST /api/auth/oauth/exchange
Content-Type: application/json
```

Request:

```json
{
  "code": "2huvMgw0MJrCLVooov4W7Y1asSA4LMC6OSjRbVE4yyM"
}
```

Response (`200`): `5.2`와 동일한 `LoginResponse` 형식.

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `INVALID_OAUTH_CODE` | 401 | code가 없거나, 이미 소비됐거나, 만료됐다. |
| `OAUTH_EMAIL_NOT_PROVIDED` | 400 | provider가 이메일을 제공하지 않았다(예: Kakao 이메일 동의항목 미승인). |

### 5.7 내 정보 조회

```http
GET /api/auth/me
Authorization: Bearer {access_token}
```

Response (`200`):

```json
{
  "id": "user_1f9a74af",
  "email": "user@example.com",
  "display_name": "use",
  "created_at": "2026-07-03T10:00:00Z"
}
```

## 6. Workspace API

### 6.1 워크스페이스 생성

```http
POST /api/workspaces
Authorization: Bearer {access_token}
Content-Type: application/json
```

Request:

```json
{
  "name": "팀 워크스페이스"
}
```

Response (`201`):

```json
{
  "id": "ws_eb2c741a",
  "name": "팀 워크스페이스",
  "created_at": "2026-07-03T10:00:00Z",
  "updated_at": "2026-07-03T10:00:00Z"
}
```

### 6.2 워크스페이스 목록 조회

```http
GET /api/workspaces
Authorization: Bearer {access_token}
```

Response (`200`):

```json
{
  "workspaces": [
    {
      "id": "ws_eb2c741a",
      "name": "won의 워크스페이스",
      "created_at": "2026-07-03T10:00:00Z",
      "updated_at": "2026-07-03T10:00:00Z"
    }
  ]
}
```

요청자가 속한(현재는 소유한) 워크스페이스만 반환한다.

### 6.3 워크스페이스 이름 변경

```http
PATCH /api/workspaces/{workspace_id}
Authorization: Bearer {access_token}
Content-Type: application/json
```

Request:

```json
{
  "name": "새 이름"
}
```

Response (`200`): `6.1`과 동일한 형식.

### 6.4 워크스페이스 삭제

```http
DELETE /api/workspaces/{workspace_id}
Authorization: Bearer {access_token}
```

Response: `204 No Content`.

처리 규칙:

- 소속 `documents`, `chat_sessions`(및 그 하위 메시지/참조/관련페이지)를 함께 삭제한다.
- 소속 문서는 애플리케이션 레벨에서 삭제되며, 문서 삭제 로직을 통해 source Wiki page와 관련 링크, Object Storage 원본도 정리한다.
- concept Wiki page는 여러 문서가 공유할 수 있으므로 문서 삭제 과정에서 함께 삭제하지 않는다.

주요 error code (6.3, 6.4 공통):

| code | HTTP status | description |
| --- | --- | --- |
| `WORKSPACE_NOT_FOUND` | 404 | 워크스페이스가 없거나 요청자 소유가 아니다. |

## 7. Documents API

모든 endpoint는 `Authorization` 헤더가 필요하고, `{workspace_id}`에 대한 접근 권한을 검증한다.

### 7.1 문서 업로드

```http
POST /api/workspaces/{workspace_id}/documents
Authorization: Bearer {access_token}
Content-Type: multipart/form-data
```

Request:

```text
file: PDF 또는 Markdown 파일
```

Response (`201`):

```json
{
  "id": "doc_24ec7500",
  "filename": "lecture_01.pdf",
  "mime_type": "application/pdf",
  "byte_size": 1024000,
  "status": "processing",
  "source_uri": "sources/documents/doc_24ec7500/original",
  "uploaded_at": "2026-07-03T10:00:00Z"
}
```

처리 규칙:

- API는 원본 파일 저장과 `documents` 레코드 생성 후 즉시 응답한다.
- 문서 텍스트 추출과 Wiki 생성은 백그라운드에서 처리한다.
- 처리 중 상태는 `processing`이다.
- 성공 시 `completed`, 실패 시 `failed`로 갱신한다.

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | 파일이 없거나 비어 있다. |
| `WORKSPACE_NOT_FOUND` | 404 | 워크스페이스가 없거나 요청자 소유가 아니다. |
| `DOCUMENT_ALREADY_EXISTS` | 409 | 같은 workspace에 동일 content hash 문서가 이미 있다. |
| `UNSUPPORTED_FILE_TYPE` | 415 | PDF/Markdown이 아니다. |

### 7.2 문서 목록 조회

```http
GET /api/workspaces/{workspace_id}/documents
Authorization: Bearer {access_token}
```

Response (`200`):

```json
{
  "documents": [
    {
      "id": "doc_24ec7500",
      "filename": "lecture_01.pdf",
      "mime_type": "application/pdf",
      "byte_size": 1024000,
      "status": "completed",
      "source_uri": "sources/documents/doc_24ec7500/original",
      "extracted_text_uri": "sources/documents/doc_24ec7500/extracted.txt",
      "uploaded_at": "2026-07-03T10:00:00Z",
      "processed_at": "2026-07-03T10:01:20Z",
      "processing_stage": "5. Source Page 생성"
    }
  ]
}
```

`processing_stage`는 파이프라인 heartbeat가 보내는 현재/마지막 처리 단계 라벨이다(진행 표시용). 값이 없으면 응답에서 생략된다(`NON_NULL`). 채팅 export 문서(`origin=chat_export`)는 이 목록에서 제외된다.

사용처:

- 왼쪽 사이드바의 원본 파일 flat list
- 문서 처리 상태 polling (`status` + `processing_stage`로 진행 단계 표시)

### 7.3 문서 상세 조회

```http
GET /api/workspaces/{workspace_id}/documents/{document_id}
Authorization: Bearer {access_token}
```

Response (`200`):

```json
{
  "id": "doc_24ec7500",
  "filename": "lecture_01.pdf",
  "mime_type": "application/pdf",
  "byte_size": 1024000,
  "status": "completed",
  "source_uri": "sources/documents/doc_24ec7500/original",
  "extracted_text_uri": "sources/documents/doc_24ec7500/extracted.txt",
  "uploaded_at": "2026-07-03T10:00:00Z",
  "processed_at": "2026-07-03T10:01:20Z",
  "processing_stage": "5. Source Page 생성",
  "wiki_pages": [
    {
      "id": "wiki_page_11111111-1111-1111-1111-111111111111",
      "page_type": "source",
      "title": "lecture_01",
      "slug": "lecture-01",
      "relation_type": "source_of",
      "confidence": 1.0
    },
    {
      "id": "wiki_page_22222222-2222-2222-2222-222222222222",
      "page_type": "concept",
      "title": "Self-Attention",
      "slug": "self-attention",
      "relation_type": "extracted_concept",
      "confidence": 0.92
    }
  ]
}
```

### 7.4 원본 파일 스트리밍

```http
GET /api/workspaces/{workspace_id}/documents/{document_id}/original
Authorization: Bearer {access_token}
```

Response: 원본 파일 바이너리 스트림. PDF·text/* 계열은 `Content-Disposition: inline`, 그 외는 `attachment`.

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `DOCUMENT_NOT_FOUND` | 404 | 문서 ID가 없다. |
| `DOCUMENT_ORIGINAL_NOT_FOUND` | 404 | DB에 문서 레코드는 있으나 Object Storage 원본이 없다. |
| `WORKSPACE_NOT_FOUND` | 404 | 워크스페이스가 없거나 요청자 소유가 아니다. |

### 7.5 원본 문서 block 목록 조회

```http
GET /api/workspaces/{workspace_id}/documents/{document_id}/blocks
Authorization: Bearer {access_token}
```

Response (`200`):

```json
{
  "document_id": "doc_24ec7500",
  "blocks": [
    { "block_id": "B0005", "text": "원본 문서의 다섯 번째 block 본문" },
    { "block_id": "B0006", "text": "원본 문서의 여섯 번째 block 본문" }
  ]
}
```

처리 규칙:

- `block_id` 오름차순으로 조회한다.
- block이 없어도 200과 빈 배열을 반환한다.
- 답변 citation `[n]` 클릭 시 `evidence_snippets[].source_document_id` + `source_block_ids`로 이 API를 호출해 원본 block을 하이라이트한다.

### 7.6 문서 이름 변경

```http
PATCH /api/workspaces/{workspace_id}/documents/{document_id}/rename
Authorization: Bearer {access_token}
Content-Type: application/json
```

Request:

```json
{
  "filename": "lecture_01_renamed.pdf",
  "sync_source_title": false
}
```

| field | type | required | description |
| --- | --- | --- | --- |
| `filename` | string | O | 1~255자, `/`, `\`, NULL 문자 금지 |
| `sync_source_title` | boolean | X | 대응 source page가 있으면 title도 함께 변경. 기본값 `false` |

Response (`200`):

```json
{
  "id": "doc_24ec7500",
  "filename": "lecture_01_renamed.pdf",
  "previous_filename": "lecture_01.pdf",
  "source_uri": "sources/documents/doc_24ec7500/original",
  "status": "completed",
  "renamed_at": "2026-07-03T10:20:00Z",
  "source_page": {
    "id": "wiki_page_11111111-1111-1111-1111-111111111111",
    "title": "lecture_01",
    "renamed": false
  }
}
```

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `DOCUMENT_NOT_FOUND` | 404 | 문서 ID가 없다. |
| `INVALID_DOCUMENT_FILENAME` | 400 | 이름이 비어 있거나 허용되지 않는 문자를 포함한다. |

### 7.7 문서 삭제

```http
DELETE /api/workspaces/{workspace_id}/documents/{document_id}
Authorization: Bearer {access_token}
```

Response: `204 No Content`. 연결된 source Wiki 페이지와 Object Storage 오브젝트를 함께 삭제한다. concept Wiki 페이지는 삭제되지 않는다(다른 문서에서도 참조될 수 있으므로).

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `DOCUMENT_NOT_FOUND` | 404 | 문서 ID가 없다. |
| `WORKSPACE_NOT_FOUND` | 404 | 워크스페이스가 없거나 요청자 소유가 아니다. |

### 7.8 llmPipeline 전용 콜백 (프론트 미사용)

```text
PATCH /api/documents/{document_id}/status
POST  /api/documents/{document_id}/pipeline-events
```

문서 처리 상태 갱신과 진행 이벤트 수신용으로 llmPipeline이 호출하는 flat 경로다. 프론트는 직접 호출하지 않는다.

`PATCH /api/documents/{document_id}/status` payload:

```json
{
  "status": "completed",
  "extracted_text_uri": "sources/documents/doc_24ec7500/extracted.txt",
  "processed_at": "2026-07-03T10:01:20Z",
  "error_message": null
}
```

`POST /api/documents/{document_id}/pipeline-events` payload:

```json
{
  "run_id": "51ef53b4-7f84-4cec-9f3c-125239e4b4f2",
  "timestamp": "2026-07-11 08:18:14",
  "stage": "4. 정규화",
  "message": "의미 노트를 concept ledger와 evidence unit으로 정규화했습니다.",
  "data": {
    "core concept 수": "3",
    "근거 수": "3"
  }
}
```

처리 규칙:

- `run_id`가 문서의 `pipeline_run_id`와 다르면 이벤트를 무시한다.
- `stage`는 `documents.processing_stage`에 저장되어 문서 목록/상세 응답의 `processing_stage`로 내려간다.
- `message`, `timestamp`, `data`는 현재 진행 로그 관측용으로 수신하지만 문서 응답 DTO에는 저장하지 않는다.

## 8. Wiki API

Wiki API는 workspace-scoped 경로를 사용한다. 모든 요청은 `{workspace_id}`에 대한 멤버십을 확인하고, 조회/변경 대상도 해당 workspace 안의 `wiki_pages`로 제한한다. 다른 workspace의 Wiki page ID로 상세 조회나 이름 변경을 요청하면 `404 WIKI_PAGE_NOT_FOUND`가 반환된다.

`wiki_page_id`는 `wiki_page_{uuid}` 형태의 opaque ID다. page 의미는 ID 문자열이 아니라 `page_type`, `slug`, `source_document` 필드로 판단한다.

`wiki_page_links`에는 `workspace_id` 컬럼이 없으므로 graph 조회 시 먼저 해당 workspace의 page id 집합을 만들고, from/to 양 끝점이 모두 그 집합에 포함된 link만 응답한다.

### 8.1 Wiki graph 조회

```http
GET /api/workspaces/{workspace_id}/wiki/graph
Authorization: Bearer {access_token}
```

Response (`200`):

```json
{
  "nodes": [
    {
      "id": "wiki_page_11111111-1111-1111-1111-111111111111",
      "page_type": "source",
      "title": "lecture_01",
      "slug": "lecture-01",
      "summary": "Transformer 강의자료 요약입니다.",
      "status": "active",
      "source_document": { "id": "doc_24ec7500", "filename": "lecture_01.pdf" }
    },
    {
      "id": "wiki_page_22222222-2222-2222-2222-222222222222",
      "page_type": "concept",
      "title": "Self-Attention",
      "slug": "self-attention",
      "summary": "토큰 간 관계를 계산하는 Transformer의 핵심 메커니즘입니다.",
      "status": "active"
    }
  ],
  "edges": [
    {
      "from_page_id": "wiki_page_11111111-1111-1111-1111-111111111111",
      "to_page_id": "wiki_page_22222222-2222-2222-2222-222222222222",
      "link_type": "source_mentions_concept",
      "label": "mentions",
      "confidence": 0.92
    }
  ]
}
```

사용처:

- 중앙 Wiki graph 렌더링
- 답변 후 관련 node/path highlight

### 8.2 Wiki page 상세 조회

```http
GET /api/workspaces/{workspace_id}/wiki/pages/{wiki_page_id}
Authorization: Bearer {access_token}
```

Response (`200`):

```json
{
  "id": "wiki_page_22222222-2222-2222-2222-222222222222",
  "page_type": "concept",
  "title": "Self-Attention",
  "slug": "self-attention",
  "summary": "토큰 간 관계를 계산하는 Transformer의 핵심 메커니즘입니다.",
  "markdown_uri": "wiki/user_1f9a74af/ws_abc123/concepts/self-attention.md",
  "markdown": "# Self-Attention\n\n## Definition\n...",
  "status": "active",
  "created_at": "2026-07-03T10:01:10Z",
  "updated_at": "2026-07-03T10:01:20Z",
  "source_documents": [
    {
      "id": "doc_24ec7500",
      "filename": "lecture_01.pdf",
      "source_uri": "sources/documents/doc_24ec7500/original",
      "relation_type": "extracted_concept",
      "confidence": 0.92
    }
  ],
  "related_pages": [
    {
      "id": "wiki_page_33333333-3333-3333-3333-333333333333",
      "page_type": "concept",
      "title": "Transformer",
      "slug": "transformer",
      "link_type": "concept_related_to",
      "label": "related",
      "confidence": 0.81
    }
  ]
}
```

source page 상세의 경우 `source_documents`에는 대응되는 원본 문서 1개가 들어간다.

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `WIKI_PAGE_NOT_FOUND` | 404 | Wiki page ID가 존재하지 않는다. |

### 8.3 Wiki page 이름 변경

```http
PATCH /api/workspaces/{workspace_id}/wiki/pages/{wiki_page_id}/rename
Authorization: Bearer {access_token}
Content-Type: application/json
```

Request:

```json
{
  "title": "Self-Attention 개념 정리",
  "update_slug": false
}
```

Response (`200`):

```json
{
  "id": "wiki_page_22222222-2222-2222-2222-222222222222",
  "page_type": "concept",
  "title": "Self-Attention 개념 정리",
  "previous_title": "Self-Attention",
  "slug": "self-attention",
  "previous_slug": "self-attention",
  "slug_updated": false,
  "updated_at": "2026-07-03T10:25:00Z"
}
```

처리 규칙:

- `update_slug=false`이면 기존 slug와 markdown URI를 유지한다.
- `update_slug=true`이면 title 기반으로 slug를 재생성하고 page id는 유지한다.
- source page 이름 변경은 원본 문서 이름 변경과 독립적으로 허용한다. 함께 바꾸려면 `PATCH /api/workspaces/{workspace_id}/documents/{document_id}/rename`의 `sync_source_title`을 사용한다.

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `WIKI_PAGE_NOT_FOUND` | 404 | Wiki page ID가 없다. |
| `INVALID_WIKI_PAGE_TITLE` | 400 | 제목이 비어 있거나 너무 길다. |
| `WIKI_PAGE_SLUG_CONFLICT` | 409 | `update_slug=true`이고 재생성된 slug가 이미 존재한다. |

## 9. Chat Session API

채팅은 워크스페이스마다 여러 개의 세션으로 나뉜다(워크스페이스당 최대 10개). 세션은 지금은 그 세션을 만든 유저만 접근 가능하다.

### 9.1 채팅 세션 생성

```http
POST /api/workspaces/{workspace_id}/chat/sessions
Authorization: Bearer {access_token}
Content-Type: application/json
```

Request (body는 없어도 됨, 빈 객체 허용):

```json
{
  "title": null
}
```

Response (`201`):

```json
{
  "id": "session_201c9afe",
  "title": null,
  "created_at": "2026-07-03T10:00:00Z",
  "last_message_at": "2026-07-03T10:00:00Z"
}
```

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `WORKSPACE_NOT_FOUND` | 404 | 워크스페이스가 없거나 요청자 소유가 아니다. |
| `CHAT_SESSION_LIMIT_EXCEEDED` | 409 | 워크스페이스당 세션 10개 제한을 초과했다. |

### 9.2 채팅 세션 목록 조회

```http
GET /api/workspaces/{workspace_id}/chat/sessions
Authorization: Bearer {access_token}
```

Response (`200`):

```json
{
  "sessions": [
    {
      "id": "session_201c9afe",
      "title": "Self-Attention 질문",
      "created_at": "2026-07-03T10:00:00Z",
      "last_message_at": "2026-07-03T10:05:03Z"
    }
  ]
}
```

`last_message_at` 내림차순으로 정렬된다.

### 9.3 채팅 세션 삭제

```http
DELETE /api/workspaces/{workspace_id}/chat/sessions/{session_id}
Authorization: Bearer {access_token}
```

Response: `204 No Content`. 세션 삭제 시 소속 `chat_messages`/`chat_message_references`/`chat_message_related_pages`가 DB FK `ON DELETE CASCADE`로 함께 삭제된다.

주요 error code (9.3, 9.4 공통):

| code | HTTP status | description |
| --- | --- | --- |
| `CHAT_SESSION_NOT_FOUND` | 404 | 세션 ID가 없다. |
| `WORKSPACE_NOT_FOUND` | 404 | 워크스페이스가 없거나 요청자 소유가 아니다. |

### 9.4 채팅 메시지 기록 조회

```http
GET /api/workspaces/{workspace_id}/chat/sessions/{session_id}/messages
Authorization: Bearer {access_token}
```

Response (`200`):

```json
{
  "messages": [
    {
      "id": "chat_user_66f884a8-5fed-407c-9351-c00c79dbf6e7",
      "pair_id": "3f1c8e02-7a4b-4c1d-9e55-2b6f0a1c8d10",
      "role": "user",
      "content": "Self-Attention이 뭐야?",
      "status": "completed",
      "created_at": "2026-07-03T10:05:00Z",
      "related_pages": [],
      "references": [],
      "wiki_page_id": null,
      "partial_wiki_page_ids": []
    },
    {
      "id": "chat_assistant_f06bb7ca-b0fb-4770-8276-39f543934ee6",
      "pair_id": "3f1c8e02-7a4b-4c1d-9e55-2b6f0a1c8d10",
      "role": "assistant",
      "content": "Self-Attention은 입력 토큰들이 서로 어떤 관계를 갖는지 계산하는 Transformer의 핵심 메커니즘이에요. [1]",
      "status": "completed",
      "created_at": "2026-07-03T10:05:03Z",
      "related_pages": [
        {
          "wiki_page_id": "wiki_page_22222222-2222-2222-2222-222222222222",
          "page_type": "concept",
          "title": "Self-Attention",
          "slug": "self-attention",
          "relevance_score": 0.88,
          "role": "focus_concept",
          "depth": 1,
          "rank": 2
        }
      ],
      "references": [
        {
          "id": 1,
          "reference_type": "source_block",
          "rank": 1,
          "source_document_id": "doc_24ec7500",
          "source_block_ids": ["B0005", "B0006"],
          "text": "Self-attention computes relationships between tokens."
        }
      ],
      "wiki_page_id": "wiki_page_44444444-4444-4444-4444-444444444444",
      "partial_wiki_page_ids": []
    }
  ]
}
```

세션 안의 메시지를 생성 순서대로 반환한다. 실패한 assistant 메시지는 `status: "failed"`이고 `error_message`가 포함된다.

- `pair_id`: user-assistant 한 쌍이 공유하는 id. 채팅 Wiki page화의 문답 선택 단위다.
- `wiki_page_id`: 이 문답이 세션의 정식(full) Wiki 페이지에 편입됐으면 그 페이지 id, 아니면 `null`.
- `partial_wiki_page_ids`: 이 문답이 편입된 partial 발췌 Wiki 페이지 id 목록(1:N). 없으면 `[]`.

### 9.5 채팅 Wiki page화 (export)

```http
POST /api/workspaces/{workspace_id}/chat/sessions/{session_id}/wiki
Authorization: Bearer {access_token}
Content-Type: application/json
```

세션(full) 또는 선택한 문답(partial)을 Markdown 문서로 직렬화해 문서 ingestion 파이프라인에 넣는다. 실제 Wiki 생성은 파이프라인이 비동기로 수행하므로 요청은 즉시 `202`로 응답한다.

Request:

```json
{ "selection_mode": "full" }
```

또는

```json
{ "selection_mode": "partial", "pair_ids": ["3f1c8e02-7a4b-4c1d-9e55-2b6f0a1c8d10"] }
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `selection_mode` | string | `full`(세션 전체) \| `partial`(선택 문답). 필수 |
| `pair_ids` | string[] | partial일 때 위키화할 문답(pair) id 목록. full이면 무시 |

Response (`202`):

```json
{ "exportDocumentId": "chatdoc_abc123", "status": "processing" }
```

| 필드 | 설명 |
|---|---|
| `exportDocumentId` | 생성(또는 중복 시 기존) export 문서 id |
| `status` | `processing`(새로 등록) \| `skipped`(동일 content가 이미 존재) |

동작:

- **full**: 아직 편입되지 않은 문답만 파이프라인에 보낸다(이미 편입된 문답은 `messages[].wiki_page_id`로 표시됨). 완료 후 세션이 정식 source Wiki 페이지에 연결된다.
- **full 재생성**: 이미 위키가 연결된 세션을 다시 full로 export하면 기존 export 문서를 재사용해 원본을 세션 전체로 갱신하고, 추가된 문답만 재처리한다. (파이프라인의 inline 입력 지원이 전제 — 후속작업. `docs/backlog/issue-2026-07-09.md` "llmPipeline 후속 작업" 참고)
- **partial**: 선택한 문답으로 독립 발췌 페이지를 만든다. 문답↔페이지 멤버십은 `messages[].partial_wiki_page_ids`로 노출된다(1:N).

에러:

- `400 INVALID_CHAT_WIKI_EXPORT_REQUEST`: `selection_mode`가 없거나 `full`/`partial`이 아님, 또는 partial인데 `pair_ids`가 빔.
- `400 EMPTY_CHAT_WIKI_EXPORT`: 위키화할 완료된 문답이 없음(예: full 재-export인데 추가된 문답이 없음).

#### 9.5.1 [임시] 직렬화 Markdown 미리보기

```http
POST /api/workspaces/{workspace_id}/chat/sessions/{session_id}/wiki/preview
Authorization: Bearer {access_token}
```

세션을 파이프라인 입력용 Markdown으로 직렬화한 결과만 `text/plain`으로 반환한다(저장·파이프라인 호출 없음).

## 10. Query API

질문 1건은 항상 특정 워크스페이스의 특정 채팅 세션에 속한다.

### 10.1 Wiki 기반 자연어 질의 (동기)

```http
POST /api/workspaces/{workspace_id}/chat/sessions/{session_id}/query
Authorization: Bearer {access_token}
Content-Type: application/json
```

Request:

```json
{
  "question": "Self-Attention이 뭐야?"
}
```

Response (`200`):

```json
{
  "user_message": {
    "id": "chat_user_66f884a8-5fed-407c-9351-c00c79dbf6e7",
    "role": "user",
    "content": "Self-Attention이 뭐야?",
    "status": "completed",
    "created_at": "2026-07-03T10:05:00Z"
  },
  "assistant_message": {
    "id": "chat_assistant_f06bb7ca-b0fb-4770-8276-39f543934ee6",
    "role": "assistant",
    "content": "Self-Attention은 입력 토큰들이 서로 어떤 관계를 갖는지 계산하는 Transformer의 핵심 메커니즘이에요. [1]",
    "status": "completed",
    "created_at": "2026-07-03T10:05:03Z"
  },
  "related_pages": [
    {
      "id": "wiki_page_22222222-2222-2222-2222-222222222222",
      "page_type": "concept",
      "title": "Self-Attention",
      "slug": "self-attention",
      "relevance_score": 0.95,
      "role": "focus_concept",
      "depth": 1
    },
    {
      "id": "wiki_page_11111111-1111-1111-1111-111111111111",
      "page_type": "source",
      "title": "lecture_01",
      "slug": "lecture-01",
      "relevance_score": 0.87,
      "role": "seed_source",
      "depth": 0
    }
  ],
  "evidence_snippets": [
    {
      "rank": 1,
      "source_document_id": "doc_24ec7500",
      "source_block_ids": ["B0005", "B0006"],
      "text": "Self-attention computes relationships between tokens."
    }
  ],
  "graph_context": {
    "nodes": [
      {
        "id": "wiki_page_11111111-1111-1111-1111-111111111111",
        "page_type": "source",
        "title": "lecture_01",
        "slug": "lecture-01",
        "relevance_score": 0.87,
        "role": "seed_source",
        "depth": 0
      }
    ],
    "edges": [
      {
        "from_page_id": "wiki_page_11111111-1111-1111-1111-111111111111",
        "to_page_id": "wiki_page_22222222-2222-2222-2222-222222222222",
        "link_type": "source_mentions_concept",
        "role": "forward",
        "score": 0.88
      }
    ]
  },
  "traversal_paths": [
    {
      "path_id": "path_1",
      "role": "primary_answer_path",
      "used_for_answer": true,
      "score": 0.91,
      "stop_reason": "answer_context_selected",
      "nodes": [
        "wiki_page_11111111-1111-1111-1111-111111111111",
        "wiki_page_22222222-2222-2222-2222-222222222222"
      ],
      "edges": [
        {
          "from_page_id": "wiki_page_11111111-1111-1111-1111-111111111111",
          "to_page_id": "wiki_page_22222222-2222-2222-2222-222222222222",
          "link_type": "source_mentions_concept",
          "role": "forward",
          "score": 0.88
        }
      ]
    }
  ]
}
```

Response fields:

| field | description |
| --- | --- |
| `user_message` | 저장된 사용자 메시지 요약 |
| `assistant_message` | 저장된 어시스턴트 메시지 요약. 답변 본문에는 `[1]`, `[2]` 형태의 evidence rank 표식이 포함될 수 있다. |
| `related_pages` | 탐색에 사용된 Wiki page 목록. `role`은 탐색 중 page의 역할, `depth`는 그래프 탐색 깊이 |
| `evidence_snippets` | 답변 근거로 사용된 원본 문서 block 단위 snippet. `rank`는 답변 본문의 `[N]` 표식과 대응하며, `source_document_id` + `source_block_ids`로 `GET /api/workspaces/{workspace_id}/documents/{document_id}/blocks`를 호출해 원본 block을 가져올 수 있다. |
| `graph_context` | 탐색 중 방문한 nodes와 edges. 그래프 하이라이트 렌더링에 사용한다. |
| `traversal_paths` | 탐색 경로 목록. `used_for_answer=true`인 path가 실제 답변 생성에 사용된 경로다. |

처리 규칙:

- 세션이 워크스페이스 소속이고 요청자 소유인지 먼저 검증한다.
- QueryEngine은 `wiki_pages`에서 질문과 유사도가 높은 page를 탐색 시작점으로 선택한다.
- LLM은 Wiki page와 evidence snippet을 바탕으로 답변을 생성한다. 근거가 없으면 unsupported 고정 응답을 반환한다.
- 응답은 pipeline 처리가 끝날 때까지 동기로 대기한다. 오래 걸리는 질의는 10.2의 비동기 API를 사용한다.

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | 질문이 비어 있다. |
| `WORKSPACE_NOT_FOUND` | 404 | 워크스페이스가 없거나 요청자 소유가 아니다. |
| `CHAT_SESSION_NOT_FOUND` | 404 | 세션이 없거나 요청자 소유가 아니다. |
| `PIPELINE_ERROR` | 502 | 파이프라인이 요청을 거부했다. |
| `PIPELINE_TIMEOUT` \| `PIPELINE_UNAVAILABLE` | 503 | 파이프라인 응답 시간 초과 또는 사용 불가. |

### 10.2 Wiki 기반 자연어 질의 (비동기)

```http
POST /api/workspaces/{workspace_id}/chat/sessions/{session_id}/query/runs
Authorization: Bearer {access_token}
Content-Type: application/json
```

Request: `10.1`과 동일한 `{"question": "..."}`.

Response (`202`):

```json
{
  "request_id": "query_a1b2c3d4",
  "status": "pending"
}
```

진행 상황은 `GET /api/query/runs/{request_id}/events`(SSE)로 구독하거나, `GET /api/query/runs/{request_id}`로 polling한다.

주요 error code: `10.1`과 동일(단, 파이프라인 관련 502/503은 run 상태(`failed`)로 반영되고 이 API 자체는 202로 응답한다).

### 10.3 Query Run 상태 조회

```http
GET /api/query/runs/{request_id}
```

Response (`200`):

```json
{
  "request_id": "query_a1b2c3d4",
  "status": "completed",
  "result": { "...": "10.1 Response와 동일한 QueryResponse 형식" }
}
```

`status`가 `pending`/`running`이면 `result`는 생략된다. `failed`이면 `error` 필드에 실패 사유가 담긴다.

주요 error code:

| code | HTTP status | description |
| --- | --- | --- |
| `QUERY_RUN_NOT_FOUND` | 404 | request_id가 없다. |

### 10.4 Query Run 이벤트 구독 (SSE)

```http
GET /api/query/runs/{request_id}/events
Accept: text/event-stream
```

파이프라인 진행 로그를 실시간 스트리밍한다. 프론트는 이걸로 "탐색 중..." 같은 진행 상태 UI를 그릴 수 있다.

SSE event:

```text
event: query.log
data: {
  "request_id": "query_a1b2c3d4",
  "sequence": 1,
  "received_at": "2026-07-13T10:00:00Z",
  "stage": "retrieval",
  "message": "관련 Wiki page를 검색했습니다.",
  "data": { "page_count": 3 }
}

event: query.completed
data: { "request_id": "query_a1b2c3d4", "status": "completed" }

event: query.failed
data: { "request_id": "query_a1b2c3d4", "status": "failed", "error": "..." }
```

처리 규칙:

- 이벤트는 backend `QueryEventBroker`가 request_id별 in-memory buffer에 최대 200개까지 보관한다.
- 구독 시 이미 buffer에 쌓인 이벤트를 먼저 전송한 뒤 새 이벤트를 이어서 전송한다.
- `query.completed` 또는 `query.failed` 전송 후 emitter를 닫는다.

### 10.5 Query Run 콜백 (llmPipeline 전용, 프론트 미사용)

```http
POST /api/query/runs/{request_id}/events/callback
```

llmPipeline이 진행 이벤트를 push하는 내부 endpoint다. 프론트는 직접 호출하지 않는다.

Request:

```json
{
  "event_type": "query.log",
  "request_id": "query_a1b2c3d4",
  "sequence": 1,
  "timestamp": "2026-07-13T10:00:00Z",
  "stage": "retrieval",
  "message": "관련 Wiki page를 검색했습니다.",
  "data": {
    "page_count": 3
  }
}
```

처리 규칙:

- path의 `{request_id}`로 run 존재 여부를 확인한다. body의 `request_id`는 forward-compatible 필드이며 현재 dispatch 기준은 path variable이다.
- backend는 callback body의 `sequence`/`timestamp`를 그대로 쓰지 않고, run 단위 `sequence`와 `received_at`을 새로 부여해 SSE `query.log` 이벤트로 발행한다.
- callback은 진행 로그만 받는다. 완료/실패 이벤트는 backend가 pipeline 호출 결과에 따라 `query.completed`/`query.failed`로 직접 발행한다.

## 11. 프론트 화면 매핑

### 로그인/온보딩

사용 API:

```text
POST /api/auth/signup
POST /api/auth/login
GET  /oauth2/authorization/{provider}
POST /api/auth/oauth/exchange
GET  /api/auth/me
```

표시 데이터:

```text
email
display_name
access_token / refresh_token 저장 (localStorage 등, 프론트 구현 필요)
```

### 워크스페이스 선택

사용 API:

```text
GET  /api/workspaces
POST /api/workspaces
PATCH /api/workspaces/{workspace_id}
DELETE /api/workspaces/{workspace_id}
```

표시 데이터:

```text
workspace 목록, 현재 선택된 workspace_id (프론트 상태로 관리)
```

### 왼쪽 사이드바 (문서)

사용 API:

```text
GET    /api/workspaces/{workspace_id}/documents
POST   /api/workspaces/{workspace_id}/documents
GET    /api/workspaces/{workspace_id}/documents/{document_id}/original
PATCH  /api/workspaces/{workspace_id}/documents/{document_id}/rename
DELETE /api/workspaces/{workspace_id}/documents/{document_id}
```

표시 데이터:

```text
filename
status
error_message
```

### 중앙 Wiki graph

사용 API:

```text
GET   /api/workspaces/{workspace_id}/wiki/graph
GET   /api/workspaces/{workspace_id}/wiki/pages/{wiki_page_id}
PATCH /api/workspaces/{workspace_id}/wiki/pages/{wiki_page_id}/rename
```

표시 데이터:

```text
nodes = wiki_pages
edges = wiki_page_links
selected page detail
```

### 오른쪽 채팅

사용 API:

```text
POST   /api/workspaces/{workspace_id}/chat/sessions
GET    /api/workspaces/{workspace_id}/chat/sessions
DELETE /api/workspaces/{workspace_id}/chat/sessions/{session_id}
GET    /api/workspaces/{workspace_id}/chat/sessions/{session_id}/messages
POST   /api/workspaces/{workspace_id}/chat/sessions/{session_id}/query
```

표시 데이터:

```text
session 목록/선택
question
answer (with [N] evidence markers)
related_pages
evidence_snippets
graph_context (그래프 하이라이트용)
traversal_paths
```

## 12. MVP 제외

아래 기능은 아직 API에 포함하지 않는다.

- 워크스페이스 멤버 초대/제거 (팀 협업/공유). 설계는 `docs/spec/workspace-sharing-design.md` 참고 (미구현)
- 폴더형 파일 트리
- 작업 큐/재시도 API
- 사용자 정의 Wiki guideline API
- 승인/롤백 API
- 벡터 검색 API
- query answer 또는 synthesis page 승격 API
- graph node 좌표 저장 API

## 13. 알려진 이슈

- **채팅 세션의 유저별 프라이빗 처리 미적용**: 지금은 워크스페이스 멤버가 1명(owner)뿐이라 드러나지 않지만, 조회 로직이 `workspace_id`만 확인하고 세션 소유자(`user_id`)는 확인하지 않는다. 워크스페이스 공유 기능이 들어가기 전에 고쳐야 한다.
