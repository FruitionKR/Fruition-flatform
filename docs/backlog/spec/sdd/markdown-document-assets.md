# Markdown 문서 이미지 자산

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-07-23
- 선행 SDD: [`markdown-document-core.md`](./markdown-document-core.md)
- 구현 계획: [`markdown-document-assets-tasks.md`](./tasks/markdown-document-assets-tasks.md)

상태 흐름: `Draft → Approved → In Progress → Verified`

## 2. 배경

사용자는 파일 선택, 드래그 앤 드롭, 클립보드 붙여넣기로 Markdown에 이미지를 첨부한다. 자동 저장과 임시 draft는 제공하지 않으므로 신규 이미지 bytes는 저장 버튼 또는 `Cmd/Ctrl+S`를 누를 때 Markdown 전체와 함께 서버로 전송한다.

업로드 전 preview는 브라우저 Blob URL을 사용한다. 저장 후 이미지는 비공개 MinIO에 보관하고 워크스페이스 멤버만 인증 API로 조회한다.

## 3. 목표

- 수동 문서 저장 한 번으로 Markdown과 신규 이미지를 함께 저장한다.
- PNG·JPEG·WebP·GIF를 이미지당 최대 10MB까지 허용하고 SVG는 제외한다.
- MinIO 정보와 공개 URL을 노출하지 않는다.
- 저장된 Markdown과 이미지 참조를 원자적으로 추적한다.
- 마지막 참조가 제거된 이미지를 7일 후 정리한다.
- 이미지가 포함된 문서를 로컬에서 볼 수 있는 ZIP으로 내보낸다.

## 4. 범위

### 포함

- 파일 선택·드래그 앤 드롭·클립보드 붙여넣기
- multipart 수동 저장과 attachment placeholder 치환
- 실제 이미지 형식·크기·dimension 검증
- 비공개 MinIO 저장과 실패 보상
- 멤버 전용 이미지 조회와 프론트 Blob 표시
- 문서–이미지 참조 추적·복제·소프트 삭제 연동
- 미참조 이미지 7일 정리
- Markdown·이미지 ZIP 내보내기

### 제외

- SVG, 일반 파일 첨부, 이미지 편집·변환·썸네일
- AI 이미지·대체 텍스트
- 외부 이미지 다운로드·프록시
- 공유 링크 이미지 접근. 상세는 [`markdown-document-sharing.md`](./markdown-document-sharing.md)에서 정의한다.
- CDN 공개 배포

## 5. 요구사항

### REQ-001 수동 저장 attachment

- 편집 중 이미지는 `attachment://<uuid>`와 브라우저 Blob으로 표현한다.
- 수동 저장은 `metadata`와 신규 이미지 file part를 `multipart/form-data`로 보낸다.
- 모든 placeholder와 file은 정확히 대응해야 하며 누락·중복·미사용 file이 있으면 전체 요청을 `400`으로 거절한다.
- 이미지가 없는 저장은 file part 없이 같은 endpoint를 사용한다.
- 업로드만으로 별도 asset을 만드는 API는 제공하지 않는다.

### REQ-002 형식과 제한

- PNG·JPEG·WebP·GIF만 허용하고 SVG는 `415 Unsupported Media Type`으로 거절한다.
- 확장자와 요청 MIME만 신뢰하지 않고 file signature와 decoder 성공 여부를 검증한다.
- 이미지당 최대 10MB, 저장당 신규 이미지 최대 20개·합계 100MB, width·height 최대 16,384px를 적용한다.
- 손상·빈 파일은 `400`, 크기 초과는 `413`으로 처리한다.

### REQ-003 원자적 저장과 보상

1. 멤버십·편집 가능 상태·`base_version`을 사전 확인한다.
2. placeholder, 이미지, 기존 관리 asset 참조를 검증한다.
3. 신규 이미지를 MinIO에 저장한다.
4. placeholder를 관리 이미지 API 경로로 치환한다.
5. `base_version`을 다시 조건부 검사하고 본문·버전·asset row·reference를 DB 트랜잭션으로 저장한다.
6. 충돌·DB 실패 시 이번 요청의 MinIO object를 보상 삭제한다.

저장이 모두 성공한 경우에만 치환된 Markdown과 새 버전을 반환한다.

### REQ-004 이미지 메타데이터

`document_assets`는 asset ID, workspace, 업로더, 원본 파일명, 검증된 MIME, 크기, width·height, SHA-256, storage key, 생성 시각과 미참조 시각을 저장한다. storage key와 bucket은 사용자 응답·로그에 노출하지 않는다.

### REQ-005 내부 인증 조회

- `GET /api/workspaces/{workspace_id}/assets/{asset_id}/content`는 워크스페이스 멤버만 호출할 수 있다.
- 비멤버·다른 workspace asset은 `404`로 처리한다.
- 문서 guest의 참조 이미지와 웹 공유 이미지는 이 endpoint를 사용하지 않고 [`markdown-document-sharing.md`](./markdown-document-sharing.md)의 문서 범위 endpoint를 사용한다.
- 응답은 검증된 MIME, `Content-Length`, `nosniff`, private cache와 ETag를 사용한다.
- 현재 Bearer 인증 구조에서 renderer는 JWT fetch로 Blob을 받아 object URL로 표시하고 사용 후 revoke한다.

### REQ-006 참조 검증과 추적

- 저장 Markdown을 GFM parser로 분석해 관리 asset ID를 추출한다.
- 모든 asset이 현재 workspace에 속하는지 batch 검증하고 하나라도 실패하면 저장 전체를 거절한다.
- 본문·버전·`document_asset_references` 추가·제거를 같은 DB 트랜잭션에서 처리한다.
- 같은 asset을 여러 번 사용해도 reference row는 하나다.
- 외부 `http`·`https` 이미지는 관리 asset으로 등록하거나 fetch하지 않는다.

### REQ-007 미참조 이미지 정리

- 마지막 reference가 제거되면 `unreferenced_since`를 기록한다.
- 7일 이내 재참조되면 삭제 대상에서 제외한다.
- 7일 이상 미참조인 asset은 worker가 MinIO 삭제 성공 후 DB에서 삭제한다.
- MinIO 실패 시 DB row를 유지해 재시도한다.

### REQ-008 삭제와 복제

- 소프트 삭제 문서의 reference는 유지하고 이미지를 정리하지 않는다.
- 복구 시 기존 reference를 그대로 사용한다.
- 문서 복제는 reference만 복사하며 asset row와 MinIO object를 복사하지 않는다.

### REQ-009 ZIP 내보내기

- 관리 이미지가 없으면 UTF-8 `.md`를 반환한다.
- 관리 이미지가 있으면 `.md`와 `assets/`를 포함한 ZIP을 반환한다.
- 관리 URL을 `./assets/<filename>`으로 치환하고 같은 asset은 한 번만 포함한다.
- 외부 URL은 원문 그대로 유지하고 fetch하지 않는다.
- asset 누락 시 불완전한 ZIP을 반환하지 않는다.
- 이미지 최대 100개·합계 100MB를 적용한다.

## 6. 설계

### 데이터 모델

```text
document_assets
- id PK
- workspace_id FK
- uploaded_by FK nullable
- original_filename, content_type, byte_size
- width, height, content_hash
- storage_key UNIQUE
- unreferenced_since, created_at

document_asset_references
- document_id FK
- asset_id FK
- created_at
- PK(document_id, asset_id)
```

reference가 남은 asset 삭제는 FK로 차단한다. `uploaded_by`는 사용자 탈퇴 시 `SET NULL`이다.

### Multipart 계약

```http
PUT /api/workspaces/{workspace_id}/documents/{document_id}/content
Content-Type: multipart/form-data
```

```json
metadata = {
  "markdown": "![diagram](../../../../../docs/backlog/spec/sdd/attachment:/<uuid>)",
  "base_version": 3
}
```

각 file part 이름은 `attachment_<uuid>`를 사용한다. 성공 응답은 최종 관리 URL로 치환된 Markdown, `current_version`, attachment–asset 매핑을 반환한다.

### 저장 일관성

MinIO와 PostgreSQL은 단일 트랜잭션이 아니므로 object 선저장 후 DB 조건부 갱신과 보상 삭제를 사용한다. 사전 버전 확인 뒤에도 경쟁 저장이 가능하므로 DB 갱신 시 `base_version`을 다시 검사한다.

### 이미지 표시

관리 경로를 일반 `<img src>`로 요청하지 않는다. 프론트는 JWT fetch → Blob → object URL을 사용하며 asset ID·ETag 단위로 중복 fetch를 줄이고 문서 전환 시 revoke한다.

### 정리 worker

하루 한 번, batch 100개를 `FOR UPDATE SKIP LOCKED`로 처리한다. 조건은 `unreferenced_since <= now - 7일`이고 reference가 없는 asset이다. DB row 없는 보상 실패 object도 7일 후 별도 정리한다.

### ZIP

응답 중간 실패를 피하기 위해 ZIP을 임시 파일로 완성·검증한 뒤 다운로드한다. 성공·실패 후 임시 파일을 삭제한다.

### 주요 결정

- `DEC-001`: 신규 이미지 bytes를 수동 문서 저장 multipart에 포함한다.
- `DEC-002`: 저장 전 preview는 브라우저 Blob을 사용하고 draft를 만들지 않는다.
- `DEC-003`: 비공개 MinIO와 인증 API를 사용한다.
- `DEC-004`: DB reference로 asset 수명주기를 추적한다.
- `DEC-005`: 미참조 asset을 7일 보관한다.
- `DEC-006`: SVG를 MVP에서 제외한다.
- `DEC-007`: ZIP을 완성한 뒤 응답한다.

## 7. API

| Method | Endpoint | 역할 |
|---|---|---|
| `PUT` | `/api/workspaces/{workspace_id}/documents/{document_id}/content` | Markdown·신규 이미지 수동 저장 |
| `GET` | `/api/workspaces/{workspace_id}/assets/{asset_id}/content` | 멤버 전용 이미지 조회 |
| `GET` | `/api/workspaces/{workspace_id}/documents/{document_id}/export` | `.md` 또는 이미지 ZIP 내보내기 |

## 8. 검증

| 영역 | 검증 방법 | 결과 |
|---|---|---|
| schema·reference | Testcontainers 통합 테스트 | Pass |
| 이미지 형식·크기 | 단위·악성 fixture 테스트 | Pass |
| multipart 저장 | Controller·service 테스트 | Pass |
| MinIO 보상 | storage coordinator·orphan 테스트 | Pass |
| 멤버 권한 | service·API header 테스트 | Pass |
| 7일 정리 | worker·PostgreSQL schema 테스트 | Pass |
| ZIP | 실제 압축·경로 검증 | Pass |
| Blob 표시 | 프론트 컴포넌트 테스트 | Pending |

## 9. 미결정 사항

- 이미지 검증은 Java ImageIO와 WebP 구조 검증을 사용한다.
- GFM parser는 CommonMark를 사용한다.
- 임시 ZIP은 시스템 임시 경로에서 완성 후 삭제하며 이미지 100개·합계 100MB를 제한한다.
- asset 실패 지표와 알림 기준

## 10. 결과

- 검증일: 2026-08-05
- 최종 상태: Backend Complete, Frontend Blob 표시 Pending
- 후속 작업: Frontend JWT Blob renderer와 [`markdown-document-sharing.md`](./markdown-document-sharing.md)의 token 기반 공개 이미지 접근 계약
