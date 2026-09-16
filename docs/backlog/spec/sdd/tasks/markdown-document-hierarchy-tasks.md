# Markdown 문서 폴더 트리 작업 계획

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-07-23
- 개정일: 2026-07-25 — 페이지·원본 이원 계층을 파일탐색기식 단일 폴더 트리로 통일
- 기능 SDD: [`markdown-document-hierarchy.md`](../markdown-document-hierarchy.md)

## 2. 실행 원칙

- 각 TASK의 실패 테스트를 구현보다 먼저 작성한다.
- 폴더는 유일한 컨테이너이고 문서는 leaf라는 규칙을 모든 TASK에서 유지한다.
- 기존 `documents`와 업로드·변환 계약을 유지한다.
- 각 완료 조건을 통과한 뒤 다음 TASK로 이동한다.

## 3. 작업 계획

### TASK-H001 데이터 모델과 migration

- 관련 요구사항: `REQ-H001`, `REQ-H004`, `REQ-H013`
- 작업:
  - 후속 migration(V11)으로 `source_folders`→`folders` rename, `documents.source_folder_id`→`folder_id` rename
  - `documents.parent_document_id` 컬럼과 관련 FK 제거
  - 역할별 부모 check constraint(`EDITABLE→source_folder_id IS NULL` 등) 제거
  - 기존 문서를 모두 최상위(`folder_id=null`)로 두는 backfill 재검증
  - 부모 폴더 범위별 `sort_order` 조회·잠금 쿼리 추가
- 완료 조건:
  - [ ] migration·entity mapping 검증 통과
  - [ ] 기존 문서가 최상위로 backfill됨
  - [ ] 동일 이름과 동일 내용에 unique 제약이 없음
  - [ ] `parent_document_id` 참조가 코드·스키마에서 제거됨
  - [ ] 다른 workspace 폴더 지정 거절

### TASK-H002 폴더 repository·서비스

- 관련 요구사항: `REQ-H004`, `REQ-H005`, `REQ-H013`
- 작업:
  - 폴더 생성·이름 변경
  - 폴더·문서 혼합 직계 자식 조회와 `has_children`
  - 폴더 이동과 형제 정렬
  - recursive CTE 폴더 순환 검사
  - `folders.current_version`과 멱등성 처리
- 완료 조건:
  - [ ] 같은 이름 폴더 생성 허용
  - [ ] 폴더와 문서의 혼합 순서 유지
  - [ ] 폴더 순환 이동 `409`
  - [ ] 오래된 버전 폴더 이동 `409`
  - [ ] 같은 키 재요청 no-op

### TASK-H003 문서 배치·이동 서비스

- 관련 요구사항: `REQ-H001`, `REQ-H005`, `REQ-H013`
- 작업:
  - 문서 이동(`folder_id` 변경)과 혼합 정렬
  - 문서를 부모로 지정하거나 문서 아래로 이동하는 요청 거절
  - `documents.current_version` 충돌 검사와 멱등성
- 완료 조건:
  - [ ] 최상위↔폴더 문서 이동 테스트
  - [ ] 문서를 부모로 지정 시 `400`
  - [ ] 오래된 버전 문서 이동 `409`
  - [ ] 같은 키 재요청 no-op

### TASK-H004 생성·업로드·변환 위치 연동

- 관련 요구사항: `REQ-H002`, `REQ-H003`
- 작업:
  - Markdown 생성·업로드·복제에 선택적 `folder_id` 추가
  - 원본 업로드에 원본과 변환 편집본의 선택적 `folder_id` 추가
  - `.md` 업로드를 `document_role=EDITABLE`로 직접 생성
  - 위치 미선택 시 최상위 마지막에 생성
- 완료 조건:
  - [ ] `.md` 업로드가 불변 원본을 남기지 않음
  - [ ] 선택한 폴더의 마지막에 항목 생성
  - [ ] 변환 원본과 편집본의 참조 유지
  - [ ] 원본과 편집본의 폴더 위치가 독립적임

### TASK-H005 탐색·breadcrumb·검색 API

- 관련 요구사항: `REQ-H006`~`REQ-H008`
- 작업:
  - 최상위 탐색 API(`navigation`)
  - 폴더 직계 자식 지연 조회 API
  - breadcrumb와 평면 검색 결과
- 완료 조건:
  - [ ] 최초 응답에 하위 트리 본문이 포함되지 않음
  - [ ] 동일 이름 결과가 breadcrumb로 구분됨
  - [ ] 본문 검색 제외
  - [ ] 삭제 트리 검색 제외

### TASK-H006 계층 삭제·복구

- 관련 요구사항: `REQ-H009`~`REQ-H011`
- 작업:
  - `delete_operation_id` 기반 폴더 트리 소프트 삭제
  - 전체·개별 복구와 원래 위치 복원
  - 문서 개별 삭제·복구
  - 원본·편집본 독립 삭제
- 완료 조건:
  - [ ] 폴더 트리 전체 삭제·복구
  - [ ] 개별 복구가 최상위 마지막에 배치됨
  - [ ] 문서 leaf 개별 삭제·복구
  - [ ] 원본 삭제가 편집본을 삭제하지 않음

### TASK-H007 frontend 폴더 트리

- 관련 요구사항: `REQ-H001`, `REQ-H005`~`REQ-H008`
- 작업:
  - 단일 폴더 트리 UI(폴더·문서 혼합)
  - 펼침 시 직계 자식 조회
  - 드래그 preview와 서버 이동 요청
  - breadcrumb·검색 결과 표시
- 완료 조건:
  - [ ] 문서를 다른 문서 위로 드롭 차단
  - [ ] 폴더 순환 대상 드롭 차단
  - [ ] 서버 실패 시 기존 UI 순서 복구
  - [ ] 모든 멤버에게 이동 UI 제공, 문서 내용 CRUD는 소유자에게만 노출
  - [ ] 내용 있는 폴더 삭제는 워크스페이스 소유자에게만 노출

### TASK-H008 계약·회귀 검증

- 관련 요구사항: 전체 계층 요구사항
- 작업:
  - Core TASK-010에서 이관된 비소유 workspace 멤버의 문서 이동 허용 검증
  - API 문서와 오류 계약 갱신
  - Testcontainers 동시 이동·삭제 테스트
  - 기존 업로드·변환·편집 회귀 테스트
- 완료 조건:
  - [ ] 요구사항–테스트 추적 완료
  - [ ] 전체 backend·frontend 테스트 통과
  - [ ] `git diff --check` 통과

## 4. 실행 순서

```text
TASK-H001 → TASK-H002 ─┬→ TASK-H004 → TASK-H005 → TASK-H007
                       ├→ TASK-H003 ─┤
                       └→ TASK-H006 ─┘
전체 완료 → TASK-H008
```

## 5. 검증 명령

```sh
cd backend
./gradlew test
./gradlew flywayValidate

cd ../frontend
npm test
```
