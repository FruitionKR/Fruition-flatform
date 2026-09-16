# Markdown 문서 편집 Core 작업 계획

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-07-23
- 기능 SDD: [`markdown-document-core.md`](../markdown-document-core.md)

## 2. 실행 원칙

- 각 TASK의 실패 테스트 또는 재현 절차를 구현보다 먼저 작성한다.
- 각 완료 조건을 통과한 뒤 다음 TASK로 이동한다.
- 기존 업로드·파이프라인·Wiki 동작의 회귀를 함께 검증한다.
- 요청과 무관한 리팩터링은 포함하지 않는다.

## 3. 작업 계획

### TASK-001 편집 문서 데이터 모델 추가

- 관련 요구사항: `REQ-001`~`REQ-004`, `REQ-005`~`REQ-008`
- 변경 대상:
  - `backend/src/main/resources/db/migration/V9__add_document_editing_core.sql`
  - `document/domain/Document.java`
  - 신규 `DocumentEditState`, `SourceFolder`, `IdempotencyRecord`와 repository
- 작업:
  - 기존 `documents.user_id`를 문서 소유자로 유지하고 `display_name`, 정규화 파일명, 원본 참조, 현재 해시, `current_version`, 수정·삭제 필드 추가
  - `document_role`(`EDITABLE`, `ORIGINAL`), `parent_document_id`, `source_folder_id`, `sort_order`, `delete_operation_id` 추가
  - hierarchy의 DB 기반인 `source_folders`와 self-reference를 생성하되 폴더 API는 hierarchy TASK에서 구현 (2026-07-25 개정: 파일탐색기식 단일 폴더 트리로 통일. `source_folders`→`folders`, `documents.source_folder_id`→`folder_id`, `parent_document_id`·역할별 check constraint 제거는 후속 migration V11에서 반영)
  - 역할에 맞지 않는 부모 사용과 두 부모 필드의 동시 사용을 막는 check constraint 추가
  - `source_uri`, 원본 `content_hash` nullable 전환
  - V5 제약 `uq_documents_workspace_content_hash` DROP
  - 파일명·내용 기반 대체 unique index를 만들지 않음
  - `Document.java`의 `@UniqueConstraint(uq_documents_workspace_content_hash)` 제거(ddl-auto=validate 정합성)
  - `document_edit_states`(버전 없이 본문·해시·시각) 추가
  - 사용자·endpoint·키 범위의 24시간 응답을 저장하는 `idempotency_records` 추가
  - Flyway backfill: 파일명에서 `display_name` 생성, 기존 Markdown은 `EDITABLE`, 나머지는 `ORIGINAL`, 부모는 최상위, workspace·역할별 순서, `current_version=1`, `current_content_hash=content_hash`
  - 편집 상태는 최초 조회·저장 시 lazy 생성
- 완료 조건:
  - [x] Flyway migration 검증 통과
  - [x] 같은 파일명·내용 문서 2건 생성 허용
  - [x] 기존 데이터 손실 없음
  - [x] 기존 문서의 `display_name`, `document_role`, 최상위 위치와 역할별 순서 backfill 검증
  - [x] `EDITABLE`의 원본 폴더 지정과 `ORIGINAL`의 부모 문서 지정을 DB가 거절
  - [x] `source_folders` self-reference와 workspace 관계 테스트 통과
  - [x] 기존 markdown 업로드 문서가 마이그레이션 후 최초 조회 시 편집 가능해짐(lazy edit_state)
  - [x] 같은 멱등성 키 재요청에서 문서가 한 건만 생성됨
  - [x] 같은 멱등성 키에 다른 요청 본문을 보내면 충돌
  - [x] 기존 `user_id` 소유권 유지와 신규 문서 생성자 소유권 검증
  - [x] 편집 상태 1:1과 self-reference 제약 테스트 통과
  - [x] 기존 업로드·조회 테스트 통과

### TASK-002 파일명·본문 규칙 구현

- 관련 요구사항: `REQ-004`, `REQ-012`, `REQ-014`
- 변경 대상: `DocumentService`의 단일 책임 함수 또는 재사용이 확인될 때만 별도 value object
- 작업:
  - 표시 이름·확장자 정규화
  - 금지 문자·255자 검증
  - UTF-8 5MB 검증
  - SHA-256과 동일 본문 no-op 판정
- 완료 조건:
  - [x] PDF·Markdown 확장자 유지 테스트 통과
  - [x] 한글 UTF-8 경계값 테스트 통과
  - [x] 빈 본문 허용, `null` 거절 테스트 통과
  - [x] 동일 제목·내용 문서 생성 허용 테스트 통과

### TASK-003 상세·검색과 탐색 전환 구현

- 관련 요구사항: `REQ-005`~`REQ-008`
- 변경 대상: `DocumentController`, `DocumentService`, `DocumentRepository`, 목록·상세 DTO
- 작업:
  - 기존 호환 목록 응답에 표시 이름, 형식, 편집 가능 여부, 버전 추가
  - 삭제 문서 제외와 변환 상태 표시
  - 호환 목록의 파일명 검색 연결
  - hierarchy navigation API는 `markdown-document-hierarchy-tasks.md`의 `TASK-H005`에서 구현
- 완료 조건:
  - [x] 페이지와 원본 자료가 구분되어 표시됨
  - [x] 검색이 본문을 대상으로 하지 않음
  - [x] 외부 워크스페이스와 삭제 문서가 노출되지 않음
  - [x] chat_export 문서가 저장된 워크스페이스 문서로 통합 목록과 이름 검색에 노출됨

### TASK-004 Markdown 직접 생성·업로드 구현

- 관련 요구사항: `REQ-001`, `REQ-002`, `REQ-004`
- 변경 대상: `DocumentController`, `DocumentService`, 생성 DTO, 업로드 처리
- 작업:
  - `POST /documents/markdown`
  - 직접 생성 문서와 version `1` 편집 상태 저장
  - Markdown 업로드 원문으로 편집 상태 즉시 생성
  - `Idempotency-Key` 기반 생성 재실행 방지와 역할별 최상위 마지막 위치 배치
  - 선택적 부모·원본 폴더 위치 연동은 hierarchy `TASK-H004`에서 구현
  - `DocumentService.createInitialNote`를 직접 생성 경로로 재배선(워크스페이스 생성 호출부 포함)
- 완료 조건:
  - [x] 빈 Markdown 직접 생성 가능
  - [x] 5MB 초과 요청 거절
  - [x] Markdown 업로드 직후 `editable=true`
  - [x] 직접 생성 문서의 `source_uri`가 `null`
  - [x] 신규 워크스페이스 초기 노트가 직접 생성 문서(source_uri=null)로 만들어짐
  - [x] 동일한 키의 재요청에서 기존 생성 결과 반환
  - [x] DB 또는 MinIO 실패 시 불완전한 상태가 남지 않음

### TASK-005 PDF 변환 결과 편집본 등록

> 현재 MVP에서는 PDF 변환을 구현하지 않기로 결정해 후속 작업으로 보류한다. 현재 backend는 PDF를 불변 `ORIGINAL`로만 저장한다.

- 관련 요구사항: `REQ-003`
- 변경 대상: pipeline callback DTO·controller·service와 변환 결과 계약
- 작업:
  - `converted_markdown_uri`, checksum 계약 추가
  - `X-Pipeline-Token`, `run_id`, bucket·document prefix 검증과 멱등 처리
  - 변환 Markdown 조회·checksum·5MB 검증
  - 원본을 참조하는 별도 Markdown 페이지와 최초 편집 상태 생성
  - Wiki 생성과 편집 활성화 분리
- 완료 조건:
  - [ ] 처리 중에는 목록에 표시되지만 편집 불가
  - [ ] 완료 후 원본 자료와 별도 페이지 편집본 조회 가능
  - [ ] checksum 불일치·크기 초과 시 편집 상태 미생성
  - [ ] 인증 실패·run 불일치·허용 prefix 밖 URI 요청 거절
  - [ ] 원본 PDF 불변

### TASK-006 본문 저장·이름 변경 구현

- 관련 요구사항: `REQ-009`~`REQ-014`
- 변경 대상: `DocumentController`, `DocumentService`, 저장·이름 DTO, 충돌 예외
- 작업:
  - 저장 버튼·`Cmd/Ctrl+S` 기반 multipart 전체 Markdown 수동 저장
  - 신규 이미지 attachment 처리는 assets SDD와 연동
  - `base_version` 조건부 갱신
  - 동일 본문 no-op
  - 형식별 확장자를 유지하는 이름 변경
- 완료 조건:
  - [x] 정상 변경 시 버전 1 증가
  - [x] 동일 본문·이름은 버전과 시각 유지
  - [x] 오래된 버전은 `409 Conflict`
  - [x] 동일한 이름의 다른 페이지가 있어도 이름 변경 허용
  - [x] 본문 heading과 원본 파일 불변

### TASK-007 최신 편집본 복제 구현

- 관련 요구사항: `REQ-015`, `REQ-016`
- 변경 대상: `DocumentController`, `DocumentService`, 복제 DTO
- 작업:
  - 최신 Markdown으로 새 `Document`와 편집 상태 생성
  - `복사본 (N)` 이름 선택
  - 원본 참조와 같은 부모의 마지막 배치
- 완료 조건:
  - [x] 편집 가능한 Markdown 문서와 변환 편집본을 `.md`로 복제
  - [x] 새 ID와 version `1`
  - [x] 원본 파일·이력·공유 설정 미복제
  - [x] 동일 멱등성 키의 동시 복제에서 한 건만 생성

### TASK-008 소프트 삭제·휴지통·복구 구현

- 관련 요구사항: `REQ-017`, `REQ-018`
- 변경 대상: `DocumentController`, `DocumentService`, `DocumentRepository`, 삭제·복구 DTO
- 작업:
  - 기존 사용자 삭제를 소프트 삭제로 변경
  - 휴지통과 복구 API
  - hierarchy SDD에 따른 트리·개별 복구 위치 처리
  - 워크스페이스 전체 삭제용 내부 물리 삭제는 유지
- 완료 조건:
  - [x] 삭제 문서가 일반 API에서 제외됨
  - [x] 원본·본문·버전·Wiki·block 유지
  - [x] 복구 후 기존 본문 유지
  - [x] 동일 이름·내용 문서가 있어도 복구 허용

### TASK-009 Markdown 원문 내보내기

- 관련 요구사항: `REQ-019`
- 변경 대상: `DocumentController`, 신규 `DocumentExportService`
- 작업:
  - 이미지 없는 문서의 UTF-8 `.md` 스트리밍
  - 이미지 bundle은 assets SDD TASK-008로 위임
- 완료 조건:
  - [x] UTF-8 Markdown과 한글 파일명 다운로드
  - [x] 내보내기가 문서를 변경하지 않음

### TASK-010 API 계약·회귀 검증

- 관련 요구사항: 전체 core 요구사항
- 변경 대상: `docs/spec/api/document.md`, OpenAPI annotation, API 통합 테스트
- 작업:
  - API·오류 계약 갱신
  - 요구사항–인수 조건–테스트 추적표 완성
  - 소유자 CRUD·멤버 읽기 권한 matrix 검증
  - 멤버 이동 권한 검증은 hierarchy 후속 task로 이관
  - 업로드·파이프라인·Wiki 회귀 테스트
- 완료 조건:
  - [x] 모든 요구사항이 테스트 또는 명시적인 후속 task와 연결됨
  - [x] API 문서와 DTO 일치
  - [x] 다른 멤버의 내용 수정·삭제는 거절됨
  - [x] 멤버 이동 허용은 hierarchy 후속 task에 연결됨
  - [x] 전체 백엔드 테스트 통과
  - [x] `git diff --check` 통과

## 4. 실행 순서

```text
TASK-001 → TASK-002 → TASK-003 → TASK-004
                            └──→ TASK-005
TASK-004/005 → TASK-006 → TASK-007 → TASK-008 → TASK-009
전체 완료 → TASK-010
```

신규 이미지를 포함한 multipart 저장과 ZIP 내보내기는 [`markdown-document-assets-tasks.md`](./markdown-document-assets-tasks.md)의 선행 TASK를 완료한 뒤 통합한다.

## 5. 검증 명령

```sh
cd backend
./gradlew test
./gradlew flywayValidate
```

Repository 통합 테스트는 기존 Testcontainers 구성을 사용한다.

## 6. 후속 SDD

- `markdown-document-pagination.md`: 목록 cursor 페이지네이션, 응답 형태 전환, 프론트 목록 소비 재배선
- 범용 버전 이력은 보류하고 AI 전·후 snapshot은 AI editing SDD에서 정의
- [`markdown-document-assets.md`](../markdown-document-assets.md): 이미지 attachment, 권한, 참조 수명주기
- [`markdown-document-hierarchy.md`](../markdown-document-hierarchy.md): 단일 폴더 트리(폴더 컨테이너·문서 leaf), 이동·정렬 (2026-07-25 파일탐색기식으로 통일)
- [`markdown-document-sharing.md`](../markdown-document-sharing.md): member·guest·웹 공유, 소유권 이전
- [`markdown-document-ai-editing.md`](../markdown-document-ai-editing.md): AI 편집, Markdown 검증, diff·적용·선택 복원
