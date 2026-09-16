# Document API

현재 Spring Boot backend 구현을 기준으로 Markdown 편집 문서와 업로드 원본의 API 계약을 정의한다. 공통 인증과 `ErrorResponse`는 [`00-common.md`](00-common.md)를 따른다.

## 1. 공통 규칙

### 인증과 권한

- `/api/workspaces/{workspace_id}/documents/**`는 JWT 인증과 활성 workspace 멤버십이 필요하다.
- 활성 workspace 멤버는 문서 목록·상세·원본·block·휴지통·Markdown 내보내기를 조회할 수 있다.
- 문서를 생성하거나 업로드한 사용자가 문서 소유자가 된다.
- 문서 소유자만 본문 저장, 이름 변경, 복제, 삭제, 복구를 수행할 수 있다.
- 비소유 멤버의 변경 요청은 `403 DOCUMENT_WRITE_FORBIDDEN`으로 처리한다.
- 삭제 workspace, 다른 workspace 또는 접근할 수 없는 문서는 정보 노출을 막기 위해 `404`로 처리한다.
- 문서 이동 API와 workspace 멤버 이동 권한은 아직 구현되지 않았으며 hierarchy 후속 task에서 정의한다.

### 문서 역할과 상태

| 값 | 의미 |
|---|---|
| `document_role=EDITABLE` | 편집 가능한 Markdown 페이지 |
| `document_role=ORIGINAL` | 변환 전 읽기 전용 원본 자료 |
| `status=uploaded` | 업로드되었지만 현재 backend에서 변환하지 않는 원본 |
| `status=processing` | Wiki pipeline 처리 중 |
| `status=completed` | 편집 또는 처리가 완료됨 |
| `status=failed` | pipeline 처리 실패 |

Markdown MIME 또는 `.md`/`.markdown` 파일은 `EDITABLE`, PDF는 `ORIGINAL`로 생성된다. 현재 사용자 업로드 API가 허용하는 형식은 PDF와 Markdown뿐이다.

### 멱등성과 version

- 생성, 업로드, 복제, 삭제, 복구에는 `Idempotency-Key`가 필요하다.
- 키는 1~128자의 출력 가능한 ASCII여야 한다.
- 같은 사용자·endpoint·키와 같은 요청은 최초 응답을 재생한다.
- 같은 키를 다른 요청에 재사용하면 `409 IDEMPOTENCY_KEY_REUSED`를 반환한다.
- 본문 저장, 이름 변경, 삭제, 복구는 `base_version`으로 낙관적 잠금을 적용한다.
- 오래된 version은 `409 DOCUMENT_VERSION_CONFLICT`를 반환하며 문서를 변경하지 않는다.

### 주요 오류

| HTTP | code | 조건 |
|---|---|---|
| `400` | `INVALID_REQUEST` | 파일 누락 등 잘못된 요청 |
| `400` | `INVALID_IDEMPOTENCY_KEY` | 누락되거나 유효하지 않은 멱등 키 |
| `400` | `INVALID_DOCUMENT_FILENAME` | 표시 이름 또는 `base_version`이 유효하지 않음 |
| `400` | `INVALID_DOCUMENT_VERSION` | multipart `base_version`이 1 이상의 정수가 아님 |
| `400` | `INVALID_MARKDOWN_CONTENT` | Markdown이 `null`이거나 편집할 수 없는 문서 |
| `400` | `INVALID_DOCUMENT_ASSET` | placeholder·multipart part 대응이 올바르지 않거나 이미지가 손상됨 |
| `403` | `DOCUMENT_WRITE_FORBIDDEN` | 문서 소유자가 아닌 멤버의 변경 |
| `404` | `WORKSPACE_NOT_FOUND` | 활성 workspace 멤버십 없음 |
| `404` | `DOCUMENT_NOT_FOUND` | 활성 문서 또는 요구되는 편집 상태 없음 |
| `404` | `DOCUMENT_ORIGINAL_NOT_FOUND` | 원본 스트림을 찾을 수 없음 |
| `404` | `DOCUMENT_ASSET_NOT_FOUND` | 비멤버·다른 workspace·없는 관리 이미지 |
| `409` | `DOCUMENT_VERSION_CONFLICT` | `base_version` 불일치 |
| `409` | `IDEMPOTENCY_KEY_REUSED` | 멱등 키를 다른 요청에 재사용 |
| `413` | `MARKDOWN_CONTENT_TOO_LARGE` | UTF-8 Markdown이 5MB 초과 |
| `413` | `DOCUMENT_ASSET_TOO_LARGE` | 이미지당 10MB, 저장당 20개·100MB 또는 dimension 제한 초과 |
| `415` | `UNSUPPORTED_FILE_TYPE` | PDF 또는 Markdown이 아닌 업로드 |
| `415` | `UNSUPPORTED_DOCUMENT_ASSET` | PNG·JPEG·WebP·GIF가 아닌 이미지 |
| `422` | `DOCUMENT_ASSET_EXPORT_FAILED` | ZIP asset 누락·조회 실패 또는 100개·100MB 초과 |

## 2. 사용자 API

기본 경로는 `/api/workspaces/{workspace_id}/documents`이다.

### 2.1 문서 업로드

`POST /api/workspaces/{workspace_id}/documents`

- Header: `Idempotency-Key`
- Content-Type: `multipart/form-data`
- Part: `file`
- 허용: `application/pdf`, `text/markdown`, `text/x-markdown`, `.md`, `.markdown`
- Markdown은 즉시 편집 상태를 만들고 기존 Wiki pipeline 처리 큐를 등록한다.
- PDF는 불변 원본만 저장하며 현재 변환 pipeline을 실행하지 않는다.
- 성공: `201 DocumentUploadResponse`

```json
{
  "id": "doc_...",
  "filename": "회의록.md",
  "mime_type": "text/markdown",
  "byte_size": 128,
  "status": "processing",
  "source_uri": "sources/documents/doc_.../original",
  "uploaded_at": "2026-07-25T00:00:00Z",
  "editable": true,
  "current_version": 1,
  "document_role": "EDITABLE"
}
```

업로드 내용이 같아도 새 `Idempotency-Key`라면 별도 문서 생성을 허용한다.

### 2.2 Markdown 직접 생성

`POST /api/workspaces/{workspace_id}/documents/markdown`

- Header: `Idempotency-Key`
- Content-Type: `application/json`

```json
{
  "display_name": "새 문서",
  "markdown": "# 본문"
}
```

- `display_name`에는 확장자를 넣지 않는다.
- `markdown`은 빈 문자열을 허용하지만 `null`은 허용하지 않는다.
- 성공 시 `text/markdown`, `completed`, `EDITABLE`, version `1`인 문서를 반환한다.
- 직접 생성 문서의 `source_uri`는 `null`이다.
- 성공: `201 DocumentUploadResponse`

### 2.3 평면 목록과 검색

`GET /api/workspaces/{workspace_id}/documents?query={filename}`

- 활성 문서만 반환한다.
- `query`는 `filename`과 `display_name`의 대소문자 무시 부분 검색이다.
- 본문은 검색하지 않는다.
- 채팅에서 편입해 생성한 `chat_export` 문서도 반환한다.
- 계층 navigation API 도입 전 호환용 평면 목록이다.

`DocumentListResponse`의 항목은 다음 필드를 사용한다.

```text
id, filename, mime_type, byte_size, status, source_uri,
extracted_text_uri, uploaded_at, processed_at, error_message,
pipeline_run_id, processing_state, processing_stage,
area, item_kind, display_name, file_type, document_role,
editable, current_version, source_document_id, updated_at
```

### 2.4 상세 조회

`GET /api/workspaces/{workspace_id}/documents/{document_id}`

- 활성 문서 메타데이터와 연결된 `wiki_pages`를 반환한다.
- 편집 상태가 있으면 최신 전체 `markdown`을 반환한다.
- `current_version`은 이후 저장·이름 변경 요청의 `base_version`으로 사용한다.
- 삭제 문서는 `404 DOCUMENT_NOT_FOUND`로 처리한다.

응답은 목록 항목의 필드에 `wiki_pages`와 `markdown`을 추가한 `DocumentDetailResponse`다.

### 2.5 원본 조회

`GET /api/workspaces/{workspace_id}/documents/{document_id}/original`

- 업로드 원본은 MinIO의 `source_uri`를 스트리밍한다.
- `text/*`와 PDF는 `inline`, 그 외 형식은 `attachment`로 반환한다.
- 직접 생성 Markdown처럼 `source_uri`가 없는 문서는 `404 DOCUMENT_ORIGINAL_NOT_FOUND`다.
- 편집 가능한 최신 Markdown 다운로드에는 `/export`를 사용한다.

### 2.6 원본 block 조회

`GET /api/workspaces/{workspace_id}/documents/{document_id}/blocks`

```json
{
  "document_id": "doc_...",
  "blocks": [
    {"block_id": "B0001", "text": "첫 문단"}
  ]
}
```

source block이 없는 직접 생성 문서는 빈 `blocks` 배열을 반환한다.

### 2.7 Markdown 본문 저장

`PUT /api/workspaces/{workspace_id}/documents/{document_id}/content`

- 소유자 전용
- Content-Type: `multipart/form-data`
- 이미지가 없으면 Part `markdown`과 1 이상의 정수 문자열 Part `base_version`을 사용한다.
- 신규 이미지가 있으면 Part `metadata`에 `{"markdown":"...","base_version":1}` JSON을 보내고,
  각 file part 이름을 `attachment_<uuid>`로 지정한다. Markdown은 `attachment://<uuid>` placeholder를 사용한다.
- 선택 Part `apply_operation_id`는 `POST /agent/turns`가 발급한 적용 표이며 검증 성공 시 AI 편집 로그와 연결한다.
- PNG·JPEG·WebP·GIF만 허용한다. 이미지당 10MB, 저장당 20개·100MB, dimension 16,384px 제한을 적용한다.
- 자동 저장이 아닌 명시적 수동 저장 API다.
- 동일 본문은 `changed=false`이며 version과 수정 시각을 변경하지 않는다.

```json
{
  "document_id": "doc_...",
  "current_version": 2,
  "content_hash": "sha256...",
  "updated_at": "2026-07-25T00:00:00Z",
  "changed": true,
  "markdown": "![diagram](/api/workspaces/ws_.../assets/asset_uuid/content)",
  "attachments": [
    {
      "attachment_id": "attachment_uuid",
      "asset_id": "asset_uuid",
      "content_path": "/api/workspaces/ws_.../assets/asset_uuid/content"
    }
  ]
}
```

본문·asset metadata·reference는 같은 DB transaction에서 반영한다. MinIO 선저장 후 DB 실패나 version
충돌이 발생하면 이번 요청의 신규 object를 보상 삭제한다.

### 2.8 이름 변경

`PATCH /api/workspaces/{workspace_id}/documents/{document_id}/rename`

- 소유자 전용

```json
{
  "display_name": "새 제목",
  "base_version": 1
}
```

- 기존 확장자를 보존하고 `display_name`만 변경한다.
- Markdown 첫 heading, 편집 본문, 업로드 원본, Wiki source title은 변경하지 않는다.
- 동일 이름은 `changed=false`이고 version을 변경하지 않는다.

응답: `id`, `filename`, `display_name`, `current_version`, `updated_at`, `changed`

### 2.9 복제

`POST /api/workspaces/{workspace_id}/documents/{document_id}/duplicate`

- Header: `Idempotency-Key`
- 소유자와 `EDITABLE` 문서 전용
- 최신 Markdown을 새 ID와 version `1`로 복제한다.
- 복제본은 같은 부모의 마지막에 배치한다.
- 이름은 `복사본`, `복사본 (N)` 규칙으로 서버가 결정한다.
- 원본 파일과 공유 설정은 복제하지 않고 `source_document_id`만 기록한다.
- 성공: `201 DocumentDuplicateResponse`

응답: `id`, `filename`, `display_name`, `mime_type`, `byte_size`, `current_version`, `folder_id`, `source_document_id`, `sort_order`

> 배치 필드는 파일탐색기식 통일 모델 기준 `folder_id`다. V11 migration 이전 코드는 `parent_document_id`를 반환한다.

### 2.10 소프트 삭제

`DELETE /api/workspaces/{workspace_id}/documents/{document_id}`

- Header: `Idempotency-Key`
- 소유자 전용

```json
{"base_version": 1}
```

- 원본, 편집 상태, Wiki와 block을 유지하고 문서 삭제 정보와 version만 갱신한다.
- 성공: `200 DocumentLifecycleResponse`

```json
{
  "id": "doc_...",
  "current_version": 2,
  "deleted": true,
  "deleted_at": "2026-07-25T00:00:00Z",
  "sort_order": 3
}
```

### 2.11 휴지통

`GET /api/workspaces/{workspace_id}/documents/trash`

- 모든 활성 workspace 멤버가 조회할 수 있다.
- 삭제 문서를 `deleted_at` 내림차순으로 반환한다.
- 항목: `id`, `filename`, `display_name`, `document_role`, `current_version`, `deleted_at`, `deleted_by`, `delete_operation_id`, `source_document_id`

### 2.12 복구

`POST /api/workspaces/{workspace_id}/documents/{document_id}/restore`

- Header: `Idempotency-Key`
- 문서 소유자 전용

```json
{"base_version": 2}
```

- 문서 역할별 최상위 마지막 위치로 복구한다.
- 동일 파일명과 내용의 활성 문서가 있어도 복구를 허용한다.
- 성공: `200 DocumentLifecycleResponse`, `deleted=false`, `deleted_at=null`
- 부모 트리와 원래 위치 복구는 hierarchy 후속 task 범위다.

### 2.13 Markdown 원문 내보내기

`GET /api/workspaces/{workspace_id}/documents/{document_id}/export`

- 모든 활성 workspace 멤버가 사용할 수 있다.
- 활성 `EDITABLE` 문서의 최신 편집 상태를 UTF-8로 반환한다.
- 관리 이미지 reference가 없으면 `text/markdown;charset=UTF-8`과 현재 `display_name`의 `.md` attachment를 반환한다.
- 관리 이미지가 있으면 `application/zip`과 현재 `display_name`의 `.zip` attachment를 반환한다.
- ZIP에는 `.md`와 `assets/` 이미지가 포함되며 관리 URL은 `./assets/<filename>`으로 치환된다.
- 같은 원본 파일명은 `-2`, `-3` suffix로 충돌을 해소하고 외부 URL은 원문을 유지하며 fetch하지 않는다.
- 이미지 최대 100개·합계 100MB를 적용하고 asset 누락이나 object 조회 실패 시 `422 DOCUMENT_ASSET_EXPORT_FAILED`로 전체 실패한다.
- `base_version`을 요구하지 않고 문서 상태를 변경하지 않는다.
- 원본 자료와 편집 상태가 없는 문서는 `404 DOCUMENT_NOT_FOUND`다.

## 3. Pipeline callback API

기본 경로는 `/api/documents`이며 내부 pipeline이 사용한다.

### 처리 상태 갱신

`PATCH /api/documents/{document_id}/status`

```json
{
  "status": "completed",
  "extracted_text_uri": "sources/documents/doc_.../extracted.md",
  "processed_at": "2026-07-25T00:00:00Z",
  "error_message": null
}
```

- `status`는 필수다.
- 삭제 문서 또는 삭제 workspace의 문서는 갱신하지 않고 `404`를 반환한다.
- callback 인증 강화와 변환 결과 등록은 후속 task 범위다.

### heartbeat

`POST /api/documents/{document_id}/pipeline-events`

```json
{
  "run_id": "run_...",
  "stage": "wiki_generation",
  "message": "처리 중",
  "timestamp": "2026-07-25T00:00:00Z",
  "data": {}
}
```

- 현재 `pipeline_run_id`와 다른 이벤트는 무시한다.
- 활성 문서만 `processing_stage`와 `processing_updated_at`을 갱신한다.
- 존재하지 않거나 삭제된 문서는 `404 DOCUMENT_NOT_FOUND`를 반환한다.

## 4. 구현·검증 위치

- Controller: `backend/src/main/java/fruition/document/controller/DocumentController.java`
- Pipeline callback: `backend/src/main/java/fruition/document/controller/DocumentPipelineController.java`
- Service: `backend/src/main/java/fruition/document/service/DocumentService.java`
- Export: `backend/src/main/java/fruition/document/service/DocumentExportService.java`
- 오류 매핑: `backend/src/main/java/fruition/util/GlobalExceptionHandler.java`
- Controller 계약 테스트: `backend/src/test/java/fruition/document/controller/DocumentControllerTest.java`
- 권한·도메인 테스트: `backend/src/test/java/fruition/document/service/DocumentServiceBlocksTest.java`
- DB 회귀 테스트: `backend/src/test/java/fruition/document/repository/DocumentEditingSchemaIntegrationTest.java`
