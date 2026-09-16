# Markdown 문서 편집 Core

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-07-23
- 구현 계획: [`markdown-document-core-tasks.md`](./tasks/markdown-document-core-tasks.md)
- 목표 ERD: [`markdown-document-erd.md`](./markdown-document-erd.md)
- 관련 PR:

상태 흐름: `Draft → Approved → In Progress → Verified`

## 2. 배경

현재 `Document`는 PDF와 Markdown 업로드 파일, 초기 Markdown 노트를 하나의 식별 체계에서 관리한다. 저장 모델은 유지하되 탐색 UI는 폴더가 유일한 컨테이너인 단일 파일탐색기식 폴더 트리로 관리한다. 계층 상세는 [`markdown-document-hierarchy.md`](./markdown-document-hierarchy.md)에서 정의한다.

업로드 원본은 재처리와 원본 조회의 기준이므로 변경하지 않는다. 사용자는 직접 만든 Markdown, 업로드한 Markdown, PDF 등에서 변환된 Markdown을 같은 편집기로 수정한다.

## 3. 목표

- 기존 `Document`를 업로드 파일과 Markdown 편집 문서의 통합 식별자로 유지한다.
- Markdown 문서를 직접 생성하고 저장 버튼 또는 `Cmd/Ctrl+S`로 전체 본문을 수동 저장한다.
- 변환이 필요한 원본은 파서가 Markdown을 생성한 뒤 편집 가능하게 한다.
- 이름 변경, 복제, 소프트 삭제·복구, 검색·정렬, Markdown 내보내기를 제공한다.
- 버전 번호로 오래된 편집이 최신 내용을 덮어쓰지 못하게 한다.
- 요구사항과 인수 조건을 자동·통합 테스트에 추적한다.

## 4. 범위

### 포함

- 단일 폴더 트리 탐색과 문서 상세 조회
- Markdown 직접 생성 및 Markdown 파일 업로드 즉시 편집
- PDF 등 원본의 Markdown 변환 완료 후 편집
- 전체 본문 저장, 이름 변경, 복제
- 폴더·문서 이름 검색. 계층과 공용 정렬은 [`markdown-document-hierarchy.md`](./markdown-document-hierarchy.md)에서 정의한다.
- 소프트 삭제, 휴지통, 복구
- Markdown 원문 내보내기. 이미지 bundle 상세는 [`markdown-document-assets.md`](./markdown-document-assets.md)에서 정의한다.
- 문서 소유자 CRUD·워크스페이스 멤버 읽기 권한과 낙관적 잠금

### 제외

- 버전 이력 조회·과거 버전 복원
- 이미지 업로드·접근 권한·정리 정책의 상세 설계
- 공유 링크의 생성·만료·해제. 상세는 [`markdown-document-sharing.md`](./markdown-document-sharing.md)에서 정의한다.
- AI 편집, diff, 적용
- PDF·HTML 내보내기
- 파이프라인 재처리 결과와 사용자 편집본의 병합
- 영구 삭제 정책
- 목록 cursor 페이지네이션(후속 SDD `markdown-document-pagination.md`)
- 폴더 트리 계층의 상세 설계

## 5. 요구사항

### 5.1 생성과 변환

#### REQ-001 Markdown 직접 생성

워크스페이스 멤버는 표시 이름과 5MB 이하의 Markdown 본문으로 문서를 생성할 수 있어야 한다.

- Given: 인증된 사용자가 워크스페이스 멤버이다.
- When: `display_name`과 `markdown`으로 생성을 요청한다.
- Then: `text/markdown`, `completed`, version `1`인 `Document`와 편집 상태를 생성한다.
- Then: 생성한 사용자를 문서 소유자로 기록한다.
- Then: `source_uri`와 `source_document_id`는 `null`이다.
- Then: 빈 문자열 본문은 허용하고 `null`은 거절한다.
- Then: 새 문서는 선택한 페이지 부모의 가장 뒤에 배치하고, 부모가 없으면 페이지 최상위의 가장 뒤에 배치한다.
- Then: 신규 워크스페이스 초기 노트도 이 경로로 생성한다(기본 Markdown, `source_uri=null`, edit_state version `1`, MinIO 저장 없음). 기존 `createInitialNote`의 MinIO 저장 방식은 이 경로로 재배선한다.

#### REQ-002 Markdown 업로드 즉시 편집

- Given: 유효한 Markdown 파일을 업로드한다.
- When: 업로드 원문을 검증한다.
- Then: 별도의 불변 원본 항목을 만들지 않고 업로드 원문으로 version `1`의 편집 가능한 페이지를 생성한다.
- Then: 파이프라인 처리 완료를 기다리지 않고 `editable=true`를 반환한다.

#### REQ-003 변환 원본 편집 활성화

- Given: PDF 등 변환이 필요한 파일이 업로드되어 있다.
- When: 파서가 Markdown을 생성하고 `converted_markdown_uri`와 checksum을 callback한다.
- Then: 백엔드는 checksum과 UTF-8 5MB 제한을 검증하고 편집 가능한 Markdown 페이지와 최초 편집 상태를 생성한다.
- Then: 편집 페이지는 원본 `Document.id`를 `source_document_id`로 참조하며 원본과 별도 ID·수명주기를 가진다.
- Then: 생성 위치는 hierarchy SDD의 `converted_page_parent_id` 규칙을 따른다.
- Then: 변환 실패 시 편집 페이지를 만들지 않고 원본에 `failed` 상태를 표시한다.

#### REQ-004 내용 중복 허용과 요청 멱등성

- 동일한 workspace와 계층 위치에 파일명과 내용이 모두 같은 문서 생성을 허용한다.
- 제목·파일명·내용 hash에는 문서 생성을 막는 unique 제약을 두지 않는다.
- 기존 V5의 UNIQUE `(workspace_id, content_hash)`(제약명 `uq_documents_workspace_content_hash`)를 제거하고 대체 content unique index를 만들지 않는다.
- 생성·업로드·복제 요청은 `Idempotency-Key`를 필수로 받아 동일 요청의 재실행만 방지한다.
- 같은 사용자·endpoint·키의 24시간 내 재요청은 최초 생성 결과를 반환한다.
- 새로운 키의 요청은 제목과 내용이 같아도 새 `Document.id`를 생성한다.

### 5.2 조회·검색·정렬

#### REQ-005 탐색 목록 조회

- 탐색 목록은 단일 폴더 트리로 hierarchy SDD의 지연 조회 API를 사용한다.
- 저장 모델과 문서 상세 API는 기존 `Document.id`를 공통 식별자로 유지한다.
- 항목에는 `id`, 항목 종류, `filename`, `display_name`, `file_type`, `mime_type`, 처리 상태, `editable`, `current_version`, 원본 참조, 생성·수정 시각을 포함한다.
- 본문과 소프트 삭제 문서는 일반 목록에서 제외한다.
- 채팅 Wiki page화 export 문서(`origin='chat_export'`)도 저장된 워크스페이스 문서로 목록과 이름 검색에 포함한다.
- 변환 중·실패 문서도 처리 상태와 함께 표시한다.
- 기존 `{ "documents": [...] }` 전체 목록 응답은 hierarchy 탐색 API 전환 기간에만 호환용으로 유지한다. 신규 frontend는 hierarchy SDD의 navigation API를 사용한다.

#### REQ-006 상세 조회

- 활성 문서 상세에 현재 전체 Markdown과 `current_version`을 반환한다.
- 편집 상태가 없는 변환 중·실패 문서는 원본 및 처리 메타데이터만 반환한다.
- 다른 워크스페이스 또는 삭제 문서는 일반 상세 API에서 `404 Not Found`로 처리한다.

#### REQ-006a 레거시 원본 API의 직접 생성 문서 처리

- `/original`: `source_uri`가 있으면 기존대로 MinIO 원본을 스트리밍한다. `source_uri`가 `null`인 직접 생성 문서는 편집 상태의 현재 Markdown을 `text/markdown`으로 반환한다. 편집 상태도 없으면 `404`.
- `/blocks`: 파이프라인 source block이 없는 직접 생성 문서는 `200`에 빈 목록(`blocks: []`)을 반환한다.
- 두 API는 기존 업로드·파이프라인 문서에서 회귀 없이 동작해야 한다.
- 현재 구현은 `/blocks`의 빈 목록만 충족한다. `/original`은 `source_uri=null`이면 `404 DOCUMENT_ORIGINAL_NOT_FOUND`를 반환하며 후속 backend 이슈로 관리한다.

#### REQ-007 파일명 검색

- `display_name`과 실제 `filename`의 일부 문자열을 대소문자 구분 없이 검색한다.
- 본문은 검색하지 않는다.
- 검색 결과에도 공용 순서를 적용한다.

#### REQ-008 공용 수동 정렬

- 부모 범위별 공용 정렬, 이동 권한과 생성·복제·복구 위치는 hierarchy SDD를 따른다.
- 검색 결과에서는 순서를 변경할 수 없다.

### 5.3 본문 저장

#### REQ-009 전체 본문 저장

- 자동 저장은 제공하지 않는다. 저장 버튼과 `Cmd/Ctrl+S`만 같은 수동 저장 API를 사용한다.
- 요청은 `multipart/form-data`로 전체 `markdown`, `base_version`, 신규 이미지 attachment를 전달한다. 이미지가 없으면 attachment part를 생략한다.
- 현재 본문, 해시, 버전, 수정 시각을 하나의 DB 트랜잭션에서 갱신한다.
- 업로드 원본과 원본 해시는 변경하지 않는다.
- 미저장 내용은 서버·브라우저 draft로 보관하지 않는다. 문서 이동·새로고침·종료 시 프론트엔드가 이탈 경고를 제공한다.
- 신규 이미지 placeholder 치환과 자산 저장 규칙은 assets SDD를 따른다.

#### REQ-010 변경 없는 저장

- 요청 본문이 현재 본문과 같으면 성공하되 `changed=false`를 반환한다.
- 버전, 수정 시각, 버전 이력을 변경하지 않는다.

#### REQ-011 저장 충돌

- `base_version`과 서버 `current_version`이 다르면 `409 Conflict`를 반환한다.
- 충돌 시 기존 본문, 파일명, 버전을 변경하지 않는다.

#### REQ-012 본문 검증

- 빈 문자열은 허용하고 `null` 또는 필드 누락은 `400 Bad Request`로 처리한다.
- UTF-8 byte 기준 5MB 초과는 `413 Payload Too Large`로 처리한다.

### 5.4 이름 변경

#### REQ-013 표시 이름 변경

- API는 확장자를 제외한 `display_name`과 `base_version`을 받는다.
- PDF는 `.pdf`, Markdown은 `.md` 등 기존 문서 형식의 확장자를 유지한다.
- 본문, 첫 heading, 업로드 원본은 변경하지 않는다.
- 실제 이름이 바뀌면 버전과 수정 시각을 갱신한다.
- 정규화 결과가 현재 이름과 같으면 `changed=false`로 성공한다.
- 같은 부모 아래의 다른 페이지와 동일한 표시 이름도 허용한다.

#### REQ-014 파일명 검증

- 앞뒤 공백을 제거한다.
- 빈 이름, `/`, `\\`, 제어문자, null 문자, `.`, `..`을 허용하지 않는다.
- 확장자를 포함해 최대 255자까지 허용한다.

### 5.5 복제

#### REQ-015 최신 편집본 복제

- 복제는 같은 워크스페이스에서 요청 시점의 최신 Markdown을 사용한다.
- `base_version`을 요구하지 않는다.
- 새 문서는 `text/markdown`, `completed`, version `1`로 시작한다.
- 업로드 문서 복제본은 원본 `Document.id`를 `source_document_id`로 참조한다.
- 원본 파일, 버전 이력, 공유 설정은 복제하지 않고 이미지 URL은 재사용한다.

#### REQ-016 복제본 이름

```text
보고서.pdf → 보고서 복사본.md
보고서 복사본.md → 보고서 복사본 (2).md
```

- 서버는 사용 가능한 다음 번호를 원자적으로 선택한다.
- 접미사로 255자를 초과하면 파일명 본체를 줄인다.
- 복제본은 원본 페이지와 같은 부모의 가장 뒤에 배치한다.

### 5.6 삭제와 복구

#### REQ-017 소프트 삭제

- 문서 소유자만 현재 `base_version`으로 삭제할 수 있다.
- `deleted_at`, `deleted_by`를 기록하고 버전을 증가시킨다.
- 처리 상태, 원본, 편집 본문, 버전 및 이미지는 제거하지 않는다.
- 삭제 문서는 일반 목록·상세·저장·복제·내보내기에서 `404`로 처리한다.

#### REQ-018 휴지통과 복구

- 삭제 문서는 휴지통 API에서 조회한다.
- 복구는 삭제 문서의 `base_version`을 검증한다.
- 복구 시 삭제 정보를 제거하고 버전을 증가시킨다.
- 트리·개별 복구 위치는 hierarchy SDD를 따르며 동일 파일명·내용은 복구를 막지 않는다.

### 5.7 내보내기

#### REQ-019 Markdown 내보내기

- 활성 문서의 요청 시점 최신 Markdown을 UTF-8로 내보낸다.
- 이미지가 없으면 현재 표시 이름을 사용하는 `.md`를 반환한다.
- `base_version`을 요구하지 않고 문서 상태를 변경하지 않는다.

#### REQ-020 이미지 bundle

- 이미지 attachment 저장, 참조 추적, 멤버 전용 조회와 ZIP bundle은 [`markdown-document-assets.md`](./markdown-document-assets.md)에서 정의한다.
- core 구현은 이미지가 없는 문서의 UTF-8 `.md` 내보내기만 독립적으로 완료할 수 있어야 한다.

### 5.8 권한

#### REQ-021 문서 소유권

- 모든 워크스페이스 멤버는 문서를 생성할 수 있으며 생성자가 문서 소유자가 된다.
- 문서 소유자만 본문 저장, 이름 변경, 복제, 삭제·복구, AI 편집을 수행한다.
- 워크스페이스 멤버는 workspace 안의 활성 문서를 읽고 내보낼 수 있다.
- 문서의 계층 이동과 순서 변경은 소유권과 분리하며 모든 워크스페이스 멤버에게 허용한다.
- 이동은 본문과 소유자를 변경하지 않지만 `current_version`을 증가시킨다.
- 문서·workspace 소유권 이전과 member 제거 규칙은 [`markdown-document-sharing.md`](./markdown-document-sharing.md)를 따른다.
- workspace 밖 사용자에게는 문서 존재 여부를 노출하지 않고 `404`를 반환한다.

## 6. 설계

### 데이터 모델

`documents`에 다음 필드를 추가한다.

| 필드 | 설명 |
|---|---|
| `display_name` | 확장자를 제외하고 사용자에게 표시하는 이름 |
| `normalized_filename` | 검색용 정규화 파일명 |
| 기존 `user_id` | 문서 내용 CRUD와 AI 편집 권한을 가진 생성자. 문서 소유자로 사용 |
| `source_document_id` | 복제본 또는 변환 편집본의 원본 문서 self-reference |
| `current_content_hash` | 현재 편집 내용 또는 업로드 내용 해시 |
| `current_version` | 문서 수명주기 낙관적 잠금 버전. 생성 시 `1`, rename·본문저장·삭제·복구 시 증가 |
| `document_role` | 문서 역할. 편집 문서는 `EDITABLE`, 불변 원본은 `ORIGINAL`. 트리 배치가 아닌 동작만 구분 |
| `folder_id` | 문서가 속한 폴더. 최상위면 `null` |
| `sort_order` | 현재 부모 폴더 범위 안의 공용 순서 |
| `updated_at` | 마지막 변경 시각 |
| `deleted_at`, `deleted_by`, `delete_operation_id` | 소프트 삭제와 트리 복구 정보 |

직접 생성 Markdown을 위해 기존 `source_uri`와 원본 `content_hash`는 nullable로 변경한다. 기존 `content_hash`는 업로드 원본의 불변 해시로 유지한다.

`origin`은 `upload`, `direct`, `conversion`, `chat_export`, `ai_create`처럼 문서가 생성된 경로를 나타낸다. `document_role`은 생성 경로와 독립적으로 문서의 역할을 나타낸다. 업로드 Markdown은 `origin=upload`, `document_role=EDITABLE`이고 업로드 PDF는 `origin=upload`, `document_role=ORIGINAL`이다.

`EDITABLE`과 `ORIGINAL`은 모두 `folder_id`로 폴더에 배치하며 배치 규칙은 같다. `folder_id=null`이면 최상위다. 문서는 leaf이므로 다른 문서의 부모가 될 수 없고, 계층 컨테이너는 폴더뿐이다. 폴더와 문서의 workspace 일치는 서비스에서 검증한다.

Core 첫 migration(V9)은 hierarchy의 DB 기반인 폴더 테이블을 함께 생성했다. 파일탐색기식 단일 폴더 트리로 통일하면서 `source_folders`→`folders`, `documents.source_folder_id`→`folder_id` rename과 `parent_document_id`·역할별 check constraint 제거는 후속 migration(V11)에서 반영한다. V11 이전 코드에는 V9의 구 스키마(`parent_document_id`, 역할별 check constraint)가 남아 있다. 폴더 CRUD·이동·정렬 API는 [`markdown-document-hierarchy.md`](./markdown-document-hierarchy.md)에서 구현한다.

생성·업로드·복제 요청의 24시간 멱등 결과를 저장하는 공통 `idempotency_records`를 추가한다. 식별 범위는 사용자·endpoint·`Idempotency-Key` 조합이며, 같은 키에 다른 요청 본문이 들어오면 충돌로 처리한다. 세부 컬럼과 정리 주기는 목표 ERD 문서에서 관리한다.

`document_edit_states`를 추가한다. 버전은 `documents.current_version`으로 단일화하므로 이 테이블에는 두지 않는다.

```text
document_id       PK, FK → documents.id
markdown          TEXT NOT NULL
content_hash      VARCHAR(64) NOT NULL
created_at        TIMESTAMPTZ NOT NULL
updated_at        TIMESTAMPTZ NOT NULL
```

편집 가능 여부는 `deleted_at == null && edit_state 존재 && (Markdown 또는 status == completed)`로 판단하고 API가 `editable`을 명시한다.

### 편집 상태 생성(lazy)

편집 상태는 Flyway로 일괄 backfill하지 않는다(본문이 MinIO에 있어 SQL로 채울 수 없음). 편집 상태가 없는 기존 Markdown 문서는 최초 상세 조회 또는 최초 저장 시 원문에서 편집 상태를 lazy 생성한다(별도 트랜잭션, version `1`).

Flyway는 기존 문서를 다음과 같이 backfill한다.

- `display_name`: 기존 `filename`의 마지막 확장자를 제거한 값
- `normalized_filename`: 기존 전체 `filename`의 검색 정규화 값
- `document_role`: Markdown MIME 또는 `.md` 문서는 `EDITABLE`, 나머지 업로드 원본은 `ORIGINAL`
- `folder_id`: `null` (모든 기존 문서는 최상위에서 시작)
- `sort_order`: workspace 최상위의 `uploaded_at`, `id` 순서
- `current_version`: `1`
- `current_content_hash`: 기존 `content_hash`

신규 변환 원본은 callback 시 `document_role=EDITABLE`인 별도 Markdown 문서와 편집 상태를 생성한다.

### 저장과 낙관적 잠금

본문 저장·rename·삭제·복구는 모두 `documents.current_version`을 단일 낙관적 잠금 버전으로 사용한다. `document_id`와 `base_version`을 조건으로 `documents`를 갱신하고, 영향받은 행이 없으면 문서 부재와 버전 충돌을 구분한다. 본문 저장은 `documents`(버전·해시·시각)와 `document_edit_states`(본문)를 같은 트랜잭션에서 갱신한다.

`current_version`은 파이프라인이 raw SQL로 쓰는 컬럼(status/processing 계열)과 겹치지 않으므로, `@DynamicUpdate` 하에서 backend가 파이프라인 컬럼을 덮어쓰지 않고 안전하게 증가시킬 수 있다.

### 정렬

부모 범위별 정렬과 이동은 hierarchy SDD를 따른다. core는 `sort_order`를 생성·복제·복구 시 초기화할 수 있는 공통 필드로만 유지한다.

### 변환 계약

파이프라인은 Markdown 본문을 callback JSON에 넣지 않고 MinIO의 `converted_markdown_uri`, checksum, `run_id`를 전달한다. callback은 `X-Pipeline-Token` 서비스 토큰을 필수로 검증하고, 서버 설정값과 constant-time 비교한다. `run_id`는 현재 문서의 `pipeline_run_id`와 일치해야 하며, URI는 설정된 bucket의 `sources/documents/{document_id}/` prefix 내부로 제한한다. checksum 검증을 통과한 결과만 편집 상태로 생성하고 같은 run의 반복 callback은 멱등 처리한다. Wiki 생성 성공 여부는 편집 활성화 조건이 아니다.

### 주요 결정

- `DEC-001`: 기존 `Document`를 통합 식별자로 유지한다.
- `DEC-002`: 현재 편집 Markdown과 버전을 PostgreSQL에 저장한다.
- `DEC-003`: MinIO 업로드 원본은 불변으로 유지한다.
- `DEC-004`: 파서 결과를 최초 편집본으로 직접 사용한다.
- `DEC-005`: 파이프라인 상태와 소프트 삭제 상태를 분리한다.
- `DEC-006`: 낙관적 잠금 버전은 `documents.current_version` 하나로 통일한다. 편집 상태 유무와 무관하게 모든 문서 수준 연산(rename·본문저장·삭제·복구)이 같은 버전을 쓴다.
- `DEC-007`: 동일한 제목·파일명·내용의 문서를 허용하고 동일 쓰기 요청만 멱등성 키로 방지한다.
- `DEC-008`: 저장 모델은 통합 `Document`를 유지하고, 탐색은 폴더가 유일한 컨테이너인 단일 파일탐색기식 폴더 트리로 통일한다. 문서는 leaf이며 `document_role`은 배치가 아닌 편집 가능 여부만 구분한다(2026-07-25 개정).

## 7. API

| Method | Endpoint | 역할 |
|---|---|---|
| `GET` | `/api/workspaces/{workspace_id}/documents` | 전환 기간 호환용 평면 목록 |
| `GET` | `/api/workspaces/{workspace_id}/documents/{document_id}` | 상세와 현재 편집 상태 조회 |
| `POST` | `/api/workspaces/{workspace_id}/documents/markdown` | Markdown 직접 생성 |
| `PUT` | `/api/workspaces/{workspace_id}/documents/{document_id}/content` | multipart 전체 Markdown·신규 이미지 수동 저장 |
| `PATCH` | `/api/workspaces/{workspace_id}/documents/{document_id}/rename` | 표시 이름 변경 |
| `POST` | `/api/workspaces/{workspace_id}/documents/{document_id}/duplicate` | 최신 편집본 복제 |
| `DELETE` | `/api/workspaces/{workspace_id}/documents/{document_id}` | 소프트 삭제 |
| `GET` | `/api/workspaces/{workspace_id}/documents/trash` | 삭제 문서 목록 |
| `POST` | `/api/workspaces/{workspace_id}/documents/{document_id}/restore` | 삭제 문서 복구 |
| `GET` | `/api/workspaces/{workspace_id}/documents/{document_id}/export` | Markdown 또는 bundle 내보내기 |

기존 `original`, `blocks`, pipeline callback API는 유지한다. 탐색·이동 API는 [`markdown-document-hierarchy.md`](./markdown-document-hierarchy.md)에서 정의한다.

## 8. 검증

| 영역 | 검증 방법 | 결과 |
|---|---|---|
| DB migration과 제약 | Testcontainers Repository 통합 테스트 | Pass |
| 파일명·본문 규칙 | 도메인/서비스 단위 테스트 | Pass |
| 생성·조회·저장 API | Controller·서비스 테스트 | Pass |
| 낙관적 잠금 | Repository 통합 테스트 | Pass |
| 변환 결과 등록 | MinIO·callback 통합 테스트 | Deferred — Core TASK-005 |
| 삭제·복구 | 서비스·Repository 통합 테스트 | Pass |
| Markdown 원문 내보내기 | API 통합 테스트 | Pass |

### 8.1 요구사항 추적표

| 요구사항 | 검증 테스트 또는 후속 task | 상태 |
|---|---|---|
| `REQ-001` Markdown 직접 생성 | `createMarkdown_emptyBody_createsEditableDocument`, `createInitialNote_savesDirectMarkdownWithoutMinio` | Pass |
| `REQ-002` Markdown 업로드 | `uploadMarkdown_createsEditStateImmediately` | Pass |
| `REQ-003` 변환 원본 편집 | Core `TASK-005 PDF 변환 결과 편집본 등록` | Deferred |
| `REQ-004` 중복·멱등성 | `documents_allowSameContentAndEnforceRoleParentRules`, `createMarkdown_sameIdempotencyRequest_replaysExistingDocument`, `duplicate_sameIdempotencyKeyConcurrently_createsOneDocument` | Pass |
| `REQ-005` 탐색 목록 | `findAll_mapsPageAndSourceMetadata`, `visibleListAndSearchExcludeDeletedChatExportAndOtherWorkspaceDocuments` | Pass |
| `REQ-006` 상세 조회 | `findById_existingMarkdown_initializesEditState`, `workspaceMember_readsButCannotMutateOtherOwnersDocument` | Pass |
| `REQ-006a` 레거시 원본 API | `blocks_noBlocks_returnsEmptyList`; 직접 생성 문서 `/original`은 backend 후속 이슈 | Partial |
| `REQ-007` 파일명 검색 | `findAll_withQuery_usesFilenameSearch`, `list_withQuery_passesFilenameSearchQuery` | Pass |
| `REQ-008` 공용 정렬·이동 | hierarchy `TASK-H002`, `TASK-H003`, `TASK-H008` | Deferred |
| `REQ-009` 전체 본문 저장 | `saveContent_changed_updatesContentAndVersion`, `saveContent_multipartPassesMarkdownAndBaseVersion` | Pass |
| `REQ-010` 변경 없는 저장 | `saveContent_sameMarkdown_returnsNoOp` | Pass |
| `REQ-011` 저장 충돌 | `saveContent_rejectsStaleVersionAndNonOwner`, `conditionalUpdates_allowOnlyCurrentBaseVersion` | Pass |
| `REQ-012` 본문 검증 | `DocumentEditingRulesTest.markdown_*` | Pass |
| `REQ-013` 표시 이름 변경 | `rename_changesOnlyNotionStylePageTitle`, `rename_sameNameNoOpAndStaleVersionConflict` | Pass |
| `REQ-014` 파일명 검증 | `DocumentEditingRulesTest.rename_*` | Pass |
| `REQ-015` 최신 편집본 복제 | `duplicate_copiesLatestMarkdownAtEndOfSameParent` | Pass |
| `REQ-016` 복제본 이름 | `duplicateFilename_selectsNextNumberAndTruncatesBase` | Pass |
| `REQ-017` 소프트 삭제 | `delete_softDeletesWithoutRemovingDocumentData`, `documentSoftDeleteAndRestore_preservesOriginalAndEditingState` | Pass |
| `REQ-018` 휴지통·복구 | `trash_returnsDeletedDocuments`, `restore_deletedDocumentAtEndOfRoot` | Pass |
| `REQ-019` Markdown 내보내기 | `export_returnsUtf8MarkdownWithEncodedKoreanFilename`, `markdownExport_readsLatestEditStateWithoutChangingDocument` | Pass |
| `REQ-020` 이미지 bundle | assets `TASK-008 ZIP 내보내기` | Deferred |
| `REQ-021` 문서 소유권 | `workspaceMember_readsButCannotMutateOtherOwnersDocument`, `duplicate_rejectsOriginalAndNonOwner`, `DocumentExportServiceTest` | Pass |

```sh
cd backend
./gradlew test
./gradlew flywayValidate
```

## 9. 미결정 사항

- 파이프라인 재처리 결과와 사용자 편집본의 병합·교체 정책
- Unicode 파일명 정규화 수준
- 영구 삭제 보존 기간과 실행 주체
- 대용량 Markdown bundle의 동기 생성 상한

## 10. 결과

- 검증일:
- 최종 상태: Pending
- 남은 문제: 위 미결정 사항 및 후속 SDD
- 후속 작업:
  - `markdown-document-pagination.md` — 목록 cursor 페이지네이션(응답 형태 breaking change, 프론트 동시 전환)
  - [`markdown-document-assets.md`](./markdown-document-assets.md)
  - [`markdown-document-hierarchy.md`](./markdown-document-hierarchy.md)
  - [`markdown-document-sharing.md`](./markdown-document-sharing.md)
  - [`markdown-document-ai-editing.md`](./markdown-document-ai-editing.md) — AI 전·후 snapshot과 선택 복원 포함
