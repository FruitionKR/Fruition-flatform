# Feature Spec: Document Upload API

## 1. 목적

사용자가 PDF 또는 Markdown 문서를 업로드하면,
서버는 원본 파일을 저장하고 문서 관리 정보를 DB에 기록한 뒤,
문서 처리 상태를 processing으로 반환한다.

이 API는 이후 텍스트 추출, Source Page 생성, Concept Page 생성으로 이어지는 Build Workflow의 시작점이다.

## 2. 배경

Fruition MVP는 원본 파일을 직접 그래프 노드로 사용하지 않는다.
원본 파일은 sources/에 raw source로 저장하고,
이후 LLM이 생성한 Source Page와 Concept Page가 Wiki Graph의 node가 된다.

따라서 문서 업로드 API는 단순 파일 저장 API가 아니라,
원본 문서를 지식화 파이프라인에 등록하는 진입점이다.

## 3. 사용자 시나리오

사용자는 왼쪽 사이드바에서 PDF 또는 Markdown 파일을 업로드한다.

업로드가 성공하면 프론트는 응답으로 받은 document id와 status를 사용해
문서 목록에 해당 문서를 processing 상태로 표시한다.

이후 프론트는 `GET /api/workspaces/{workspace_id}/documents`를 polling하여 completed 또는 failed 상태를 확인한다.

## 4. API 계약

### Request

```
POST /api/workspaces/{workspace_id}/documents
Authorization: Bearer {access_token}
Content-Type: multipart/form-data
```

field:
- file: PDF 또는 Markdown 파일

### Success Response

```
201 Created
```

```json
{
  "id": "doc_123",
  "filename": "lecture_01.pdf",
  "mime_type": "application/pdf",
  "byte_size": 1024000,
  "status": "uploaded",
  "source_uri": "sources/documents/doc_123/original",
  "uploaded_at": "2026-06-04T10:00:00Z"
}
```

## 5. 처리 규칙

1. file이 없으면 400 INVALID_REQUEST를 반환한다.
2. file이 비어 있으면 400 INVALID_REQUEST를 반환한다.
3. PDF 또는 Markdown이 아니면 415 UNSUPPORTED_FILE_TYPE을 반환한다.
4. 파일 저장 경로는 `sources/documents/{document_id}/original` 형식을 따른다.
5. 원본 파일 저장에 성공하면 documents 레코드를 생성한다.
6. documents.status는 파일 종류와 관계없이 uploaded로 저장한다.
7. content_hash를 기준으로 이미 같은 파일이 존재하면 409 DOCUMENT_ALREADY_EXISTS를 반환한다.
8. 업로드 API는 처리 큐나 llmPipeline을 호출하지 않는다.
9. 편집 가능한 Markdown은 사용자가 `POST /api/workspaces/{workspace_id}/documents/{document_id}/ingest`를 명시적으로 호출할 때 Wiki 처리를 시작한다.
10. PDF 등 읽기 전용 원본은 업로드 시 저장만 한다.
11. 인증되지 않은 요청은 401을 반환한다.
12. 사용자가 속하지 않은 workspace 요청은 404 WORKSPACE_NOT_FOUND를 반환한다.

## 6. 실패 응답

### 400 Bad Request

- file field가 없는 경우
- 파일 크기가 0인 경우

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "파일이 없거나 비어 있습니다."
  }
}
```

### 409 Conflict

- 같은 content_hash의 문서가 이미 존재하는 경우

```json
{
  "error": {
    "code": "DOCUMENT_ALREADY_EXISTS",
    "message": "이미 업로드된 문서입니다."
  }
}
```

### 415 Unsupported Media Type

- PDF 또는 Markdown이 아닌 경우

```json
{
  "error": {
    "code": "UNSUPPORTED_FILE_TYPE",
    "message": "PDF 또는 Markdown 파일만 업로드할 수 있습니다."
  }
}
```

### 500 Internal Server Error

- 파일 저장 실패
- DB 저장 실패
- 알 수 없는 서버 오류

```json
{
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "서버 처리 중 오류가 발생했습니다."
  }
}
```

## 7. Acceptance Criteria

- 사용자는 PDF 파일을 업로드할 수 있다.
- 사용자는 Markdown 파일을 업로드할 수 있다.
- 업로드 성공 시 status는 uploaded다.
- 업로드 성공 시 source_uri는 `sources/documents/{document_id}/original` 형식이다.
- 업로드 성공 시 documents 레코드가 생성된다.
- 지원하지 않는 파일 형식은 415를 반환한다.
- 빈 파일은 400을 반환한다.
- 동일한 파일을 다시 업로드하면 409를 반환한다.
- API 응답에는 workspace_id, content_hash 같은 내부 필드가 노출되지 않는다.
- 업로드 API는 LLM 호출을 직접 수행하지 않는다.
- 인증된 workspace 멤버만 문서를 업로드하고 목록을 조회할 수 있다.

## 8. 테스트 관점

### Controller Test

- multipart/form-data 요청을 정상 처리한다.
- file이 없으면 400을 반환한다.
- 지원하지 않는 Content-Type이면 415를 반환한다.
- 성공 응답 JSON 구조가 API Contract와 일치한다.
- 인증되지 않은 요청은 401을 반환한다.
- 사용자가 속하지 않은 workspace 요청은 404를 반환한다.

### Service Test

- 원본 파일을 FileStorage에 저장한다.
- Document 엔티티를 processing 상태로 저장한다.
- content_hash 중복 시 예외를 발생시킨다.
- 저장 성공 후 DocumentProcessingRequester를 호출한다.
- FileStorage 저장 실패 시 DB row를 만들지 않는다.

### Repository Test

- content_hash로 중복 문서를 조회할 수 있다.
- document status enum이 정상 저장된다.

## 9. Out of Scope

- PDF 텍스트 추출 구현
- Markdown 본문 파싱
- LLM Wiki Builder 구현
- Source Page / Concept Page 생성
- wiki_pages, wiki_page_links 저장
- 작업 큐 / 재시도 API
- S3 실서비스 연동

## 10. 열린 질문

- MVP에서 파일 최대 크기를 몇 MB로 제한할 것인가?
- Markdown MIME type은 text/markdown만 허용할 것인가, 확장자 .md도 허용할 것인가?
- 중복 기준은 content_hash만 볼 것인가, filename + byte_size도 함께 볼 것인가?
- 파일 저장 실패 후 DB 저장이 이미 된 경우 보상 처리를 어떻게 할 것인가?
