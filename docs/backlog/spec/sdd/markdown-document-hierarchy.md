# Markdown 문서 폴더 트리

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-07-23
- 개정일: 2026-07-25 — 페이지·원본 이원 계층을 파일탐색기식 단일 폴더 트리로 통일
- 구현 계획: [`markdown-document-hierarchy-tasks.md`](./tasks/markdown-document-hierarchy-tasks.md)
- 선행 SDD: [`markdown-document-core.md`](./markdown-document-core.md)
- 목표 ERD: [`markdown-document-erd.md`](./markdown-document-erd.md)
- 관련 PR:

상태 흐름: `Draft → Approved → In Progress → Verified`

## 2. 배경

사용자는 편집 가능한 Markdown 문서와 PDF·DOCX·PPTX 등 불변 원본을 하나의 파일탐색기식 폴더 트리에서 함께 정리한다. 폴더가 유일한 컨테이너이고, 문서는 폴더 안의 leaf 항목이다. 문서 종류(편집 가능한 Markdown / 불변 원본)는 아이콘과 여는 방식으로 구분하되 트리 배치 규칙은 동일하다.

기존 `documents` 통합 식별자는 유지한다. 문서를 종류별 테이블로 분리하지 않고, 모든 문서는 `folder_id`로 폴더에 속한다. 이전 설계의 Notion식 페이지 중첩(문서가 다른 문서를 자식으로 갖는 구조)은 사용하지 않는다.

## 3. 목표

- 폴더로 문서를 계층 정리하는 단일 파일탐색기식 트리를 제공한다.
- 폴더와 문서의 생성 위치, 이동, 혼합 순서 변경 규칙을 명확히 한다.
- 지연 조회와 breadcrumb로 깊은 폴더 계층을 탐색한다.
- 폴더 순환, 오래된 이동 요청, 요청 재전송을 안전하게 처리한다.
- 편집 가능 문서와 불변 원본의 수명주기 차이(변환 원본↔편집본 독립)를 유지한다.

## 4. 범위

### 포함

- 폴더와 하위 폴더
- 문서(EDITABLE·ORIGINAL)의 폴더 배치
- 폴더·문서의 생성 위치, 이동, 혼합 순서 변경
- 폴더 지연 조회
- breadcrumb와 이름 검색
- 폴더 트리 단위 소프트 삭제·복구
- 계층 쓰기 API의 낙관적 잠금과 멱등성

### 제외

- 문서가 다른 문서를 자식으로 갖는 페이지 중첩(Notion식)
- 실시간 공동편집
- 개인별 정렬
- 문서 링크·backlink·database
- 계층 cursor 페이지네이션

## 5. 용어

| 용어 | 정의 |
|---|---|
| 폴더 | 하위 폴더와 문서를 담는 유일한 컨테이너 |
| 문서 | `documents`의 항목. 편집 가능한 Markdown(`EDITABLE`) 또는 불변 원본(`ORIGINAL`). 자식을 갖지 않는 leaf |
| 형제 항목 | 같은 부모 폴더(또는 최상위)를 가진 폴더·문서 |
| 최상위 | 부모 폴더가 없는 위치. 폴더는 `parent_folder_id`, 문서는 `folder_id`가 `null` |

## 6. 요구사항

### 6.1 트리 구성

#### REQ-H001 단일 폴더 트리

- 탐색 UI와 API는 워크스페이스마다 하나의 폴더 트리를 제공한다.
- 폴더는 하위 폴더와 문서를 담는 유일한 컨테이너다.
- 문서는 자식을 갖지 않는 leaf이며, 다른 문서 아래로 이동할 수 없다.
- 편집 가능한 Markdown과 불변 원본은 같은 트리에서 종류만 구분해 표시한다.

#### REQ-H002 문서 생성·업로드·복제 위치

- 직접 생성·업로드·복제·AI 생성 시 대상 폴더를 선택할 수 있다.
- 폴더를 선택하지 않으면 최상위의 가장 뒤에 생성한다.
- 업로드한 `.md`는 불변 원본을 별도로 남기지 않고 즉시 편집 가능한 문서로 생성한다.
- 새 항목은 선택한 폴더의 형제 목록 가장 뒤에 추가한다.
- AI 생성 위치의 상세 규칙은 [`markdown-document-ai-editing.md`](./markdown-document-ai-editing.md)를 따른다.

#### REQ-H003 변환 편집본 위치

- 원본 업로드 시 원본과 변환 편집본의 생성 폴더를 선택할 수 있다.
- 위치를 선택하지 않으면 최상위의 가장 뒤에 생성한다.
- 원본 폴더 위치를 편집본 위치로 자동 복제하지 않는다.
- 원본과 편집본은 계층이 아닌 `source_document_id` 참조 관계로 연결한다.

### 6.2 폴더와 문서 배치

#### REQ-H004 폴더

- 모든 워크스페이스 멤버는 최상위 또는 다른 폴더 아래에 폴더를 생성할 수 있다.
- 폴더는 제한 없는 깊이로 중첩할 수 있다.
- 동일한 부모 아래에서도 동일한 폴더 이름을 허용한다.
- 폴더와 문서는 ID와 breadcrumb로 구분한다.
- 같은 생성 요청의 재실행만 `Idempotency-Key`로 방지한다.

#### REQ-H005 이동과 정렬

- 모든 워크스페이스 멤버는 문서를 다른 폴더 또는 최상위로 이동할 수 있다.
- 모든 워크스페이스 멤버는 폴더를 다른 폴더 또는 최상위로 이동할 수 있다.
- 폴더를 자기 자신이나 자신의 하위 폴더로 이동할 수 없다.
- 문서는 자식을 가질 수 없고 폴더나 문서의 부모가 될 수 없다.
- 폴더와 문서는 같은 부모 안에서 하나의 혼합 순서로 정렬한다.
- 같은 부모 아래의 순서는 워크스페이스 전체에 공유한다.
- 이동 요청은 대상 부모 폴더, 대상 형제 위치, 대상 항목의 `base_version`, `Idempotency-Key`를 포함한다.
- 이동과 정렬은 문서 본문과 소유자를 변경하지 않고 대상 항목의 `current_version`을 증가시킨다.
- 검색 결과에서는 이동과 정렬을 수행할 수 없다.
- 펼침·접힘 상태는 사용자 UI 상태이며 공용 정렬을 변경하지 않는다.

### 6.3 조회와 검색

#### REQ-H006 지연 조회

- 최초 조회는 최상위 항목(폴더·문서)만 반환한다.
- 폴더를 펼칠 때 해당 폴더의 직계 자식만 조회한다.
- 각 폴더는 `has_children`을 포함한다.
- 폴더 자식 응답에는 하위 폴더와 문서를 공용 순서로 섞어 반환한다.

#### REQ-H007 breadcrumb

- 폴더 상세와 문서 상세는 최상위부터 현재 항목까지의 breadcrumb를 반환한다.
- 검색 결과에도 항목 종류와 breadcrumb를 포함한다.
- 동일한 이름의 결과는 breadcrumb와 ID로 구분한다.

#### REQ-H008 검색

- 검색은 문서 표시 이름·파일명과 폴더 이름을 대상으로 한다.
- 본문은 검색하지 않는다.
- 검색 결과는 평면 결과로 반환하고 계층 이동 기능을 제공하지 않는다.
- 소프트 삭제 항목과 그 하위 항목은 일반 검색에서 제외한다.

### 6.4 삭제와 복구

#### REQ-H009 폴더 트리 삭제

- 폴더를 삭제하면 모든 하위 폴더와 포함 문서를 같은 삭제 작업 ID로 소프트 삭제한다.
- 삭제 전 전체 트리의 부모와 순서 정보를 보관한다.
- 트리 복구는 원래 부모와 순서를 복원한다.
- 하위 폴더나 문서를 개별 복구하면 최상위의 가장 뒤에 배치한다.
- 복구 대상의 원래 부모 폴더가 삭제 상태이면 그 아래로 자동 복구하지 않는다.

#### REQ-H010 문서 삭제

- 문서는 leaf이므로 개별 소프트 삭제·복구한다.
- 문서 개별 복구는 최상위의 가장 뒤에 배치한다.

#### REQ-H011 원본·편집본 독립 수명주기

- 변환 편집본을 삭제해도 원본은 유지한다.
- 원본을 삭제해도 변환 편집본은 유지한다.
- 휴지통에서는 삭제된 상대 항목과의 연결을 표시할 수 있다.
- 복구하면 기존 연결 관계를 다시 조회할 수 있다.
- 어느 한쪽을 영구 삭제할 때만 해당 연결을 제거한다.

### 6.5 권한과 일관성

#### REQ-H012 권한

- 문서 생성자는 해당 문서의 소유자가 되며 문서 내용 CRUD는 소유자만 수행한다.
- 모든 워크스페이스 멤버는 읽기 가능한 문서를 이동하고 같은 부모 안에서 순서를 변경할 수 있다.
- 모든 워크스페이스 멤버는 폴더를 생성·이름 변경·이동할 수 있다.
- 모든 워크스페이스 멤버는 빈 폴더를 삭제할 수 있다.
- 내용이 있는 폴더는 워크스페이스 소유자만 삭제할 수 있다.
- 문서 파일은 해당 문서 소유자만 삭제·복구할 수 있다.
- 이동과 정렬은 문서 본문·소유자를 변경하지 않는다.
- Spring backend가 workspace 멤버십, 항목 읽기 권한, 문서 소유권을 작업별로 검증한다.

#### REQ-H013 낙관적 잠금과 멱등성

- 문서 이동·삭제·복구는 `documents.current_version`으로 충돌을 검사한다.
- 폴더 이동·이름 변경·삭제·복구는 `folders.current_version`으로 충돌을 검사한다.
- 생성·이동·정렬·삭제·복구 요청은 `Idempotency-Key`를 사용한다.
- 같은 사용자·endpoint·키의 24시간 내 재요청은 최초 결과를 반환한다.
- 오래된 버전의 이동·삭제·복구는 `409 Conflict`를 반환한다.

## 7. 설계

### 7.1 데이터 모델

기존 `documents`에 다음 필드를 사용한다.

| 필드 | 설명 |
|---|---|
| `folder_id` | 문서가 속한 폴더. 최상위면 `null` |
| `sort_order` | 현재 부모 범위 안의 공용 순서 |
| `document_role` | 문서 역할. 편집 가능 Markdown은 `EDITABLE`, 불변 원본은 `ORIGINAL`. 배치가 아닌 동작만 구분 |
| `source_document_id` | 변환본·복제본의 원본 참조 |
| `delete_operation_id` | 트리 삭제·복구 작업 식별자 |

`origin`은 문서의 생성 경로를, `document_role`은 편집 가능 여부를 나타낸다. 두 역할 모두 `folder_id`로 폴더에 배치하며 배치 규칙은 같다. `parent_document_id` 기반 페이지 중첩은 사용하지 않는다.

기존 Markdown은 `EDITABLE`, 나머지 업로드 원본은 `ORIGINAL`로 backfill하고, 모두 최상위(`folder_id=null`)에 두며 workspace별 `uploaded_at`, `id` 순서로 `sort_order`를 부여한다.

`folders`를 사용한다(기존 `source_folders`의 일반화).

```text
id                 UUID PK
workspace_id       VARCHAR(255) NOT NULL
parent_folder_id   UUID NULL
name               VARCHAR(255) NOT NULL
sort_order         BIGINT NOT NULL
current_version    BIGINT NOT NULL DEFAULT 1
deleted_at         TIMESTAMPTZ NULL
deleted_by         VARCHAR(255) NULL
delete_operation_id UUID NULL
created_at         TIMESTAMPTZ NOT NULL
updated_at         TIMESTAMPTZ NOT NULL
```

이름에는 unique 제약을 두지 않는다. 부모 FK는 같은 workspace에 속하는지 서비스와 repository 쿼리에서 검증한다.

### 7.2 순환 방지

폴더 이동 트랜잭션은 recursive CTE로 대상 부모 폴더의 조상 경로를 조회한다. 이동 폴더 자신이 조상 경로에 있으면 `409 HIERARCHY_CYCLE`로 거절한다. 문서는 leaf이므로 순환 대상이 아니며, 문서를 부모로 지정하는 요청은 `400 INVALID_HIERARCHY_REQUEST`로 거절한다. 프론트엔드의 드롭 차단은 보조 검증이며 서버 검증을 대체하지 않는다.

### 7.3 정렬

정렬은 부모 폴더 범위별 `sort_order`로 관리한다. 폴더와 문서는 같은 부모 안에서 하나의 정렬 범위를 공유한다. 이동 요청의 `position`은 대상 부모의 폴더·문서 혼합 목록에서 0-based 목표 인덱스이며, 생략하면 맨 뒤에 배치한다. 이동 트랜잭션은 대상 부모의 형제(폴더·문서)를 비관적 잠금으로 잠그고 `sort_order`를 재배열한다. 이동 대상 항목만 `current_version`을 검사·증가시키고, 나머지 형제는 순서만 조정한다.

### 7.4 삭제 작업

트리 삭제마다 `delete_operation_id`를 발급한다. 전체 복구는 같은 작업 ID에 포함된 항목을 복구하고, 개별 복구는 선택 항목(폴더면 그 활성 하위 트리 포함)을 최상위로 복구한다. 영구 삭제 정책은 core 후속 SDD에서 정의한다.

## 8. API

| Method | Endpoint | 역할 |
|---|---|---|
| `GET` | `/api/workspaces/{workspace_id}/navigation` | 최상위 폴더·문서 조회 |
| `GET` | `/api/workspaces/{workspace_id}/folders/{folder_id}/children` | 폴더의 직계 하위 폴더·문서 조회 |
| `POST` | `/api/workspaces/{workspace_id}/folders` | 폴더 생성 |
| `PATCH` | `/api/workspaces/{workspace_id}/folders/{folder_id}` | 폴더 이름 변경 |
| `PATCH` | `/api/workspaces/{workspace_id}/folders/{folder_id}/position` | 폴더 이동·정렬 |
| `DELETE` | `/api/workspaces/{workspace_id}/folders/{folder_id}` | 폴더 트리 소프트 삭제 |
| `POST` | `/api/workspaces/{workspace_id}/folders/{folder_id}/restore` | 폴더 트리 복구 |
| `PATCH` | `/api/workspaces/{workspace_id}/documents/{document_id}/position` | 문서 이동·정렬 |
| `GET` | `/api/workspaces/{workspace_id}/navigation/search` | 폴더·문서 이름 검색 |

문서 생성·업로드·복제·삭제·복구 API는 core 계약을 유지하고 선택적 `folder_id`를 받는다. 원본 업로드 API는 원본과 변환 편집본의 선택적 `folder_id`를 받는다.

## 9. 오류

| HTTP | 코드 | 조건 |
|---:|---|---|
| 400 | `INVALID_HIERARCHY_REQUEST` | 잘못된 부모·형제 위치, 문서를 부모로 지정 |
| 403 | `HIERARCHY_WRITE_FORBIDDEN` | 멤버가 아닌 사용자 또는 권한 없는 내용 수정·삭제 |
| 404 | `HIERARCHY_ITEM_NOT_FOUND` | 다른 workspace 또는 없는 항목 |
| 409 | `HIERARCHY_VERSION_CONFLICT` | 오래된 버전 |
| 409 | `HIERARCHY_CYCLE` | 폴더를 자기 자신·하위 폴더로 이동 |

## 10. 인수 조건

- 문서를 다른 폴더로 이동하면 새 폴더의 마지막 위치에서 조회된다.
- 폴더를 자신의 하위 폴더 아래로 이동하려 하면 전체 상태가 유지되고 `409`가 반환된다.
- 한 폴더 아래에서 폴더와 문서가 하나의 순서로 조회된다.
- 동일 이름 문서와 폴더를 같은 부모 아래에 각각 생성할 수 있다.
- 폴더 삭제·복구 시 전체 하위 트리와 순서가 복원된다.
- 원본 삭제가 연결된 Markdown 편집본을 삭제하지 않는다.
- 문서를 다른 문서 아래로 이동하려 하면 `400`이 반환된다.
- 워크스페이스 멤버는 다른 멤버 소유 문서를 이동할 수 있지만 본문·이름·소유자는 변경할 수 없다.
- 내용이 있는 폴더를 일반 멤버가 삭제하면 `403`이다.
- 같은 멱등성 키의 이동 재요청이 버전이나 순서를 두 번 변경하지 않는다.

## 11. 미결정 사항

- 계층 cursor 페이지네이션과 한 폴더의 최대 직계 자식 수
- 영구 삭제 보존 기간과 실행 주체
- `source_folders`→`folders`, `documents.source_folder_id`→`folder_id`, `parent_document_id` 제거와 역할별 check constraint 해제를 반영하는 후속 migration(V11) 범위

## 12. 결과

- 검증일:
- 최종 상태: Pending
- 남은 문제: 위 미결정 사항
