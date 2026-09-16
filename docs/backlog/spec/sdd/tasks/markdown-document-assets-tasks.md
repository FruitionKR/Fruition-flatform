# Markdown 문서 이미지 자산 작업 계획

## 1. 문서 정보

- 상태: Backend Complete (Frontend Blob 표시 후속)
- 작성일: 2026-07-23
- 기능 SDD: [`markdown-document-assets.md`](../markdown-document-assets.md)

## 2. 실행 원칙

- 실패 테스트를 구현보다 먼저 작성한다.
- MinIO와 DB 실패 경계를 각각 검증한다.
- 이미지 bytes와 storage key를 로그에 남기지 않는다.

## 3. 작업 계획

### TASK-001 Asset 데이터 모델

- 관련 요구사항: `REQ-004`, `REQ-006`~`REQ-008`
- 작업: `document_assets`, `document_asset_references`, FK·정리 인덱스 추가
- 완료 조건:
  - [x] 다대다 참조와 workspace 경계 테스트
  - [x] reference가 남은 asset 삭제 차단

### TASK-002 Multipart 저장 계약

- 관련 요구사항: `REQ-001`, `REQ-003`
- 작업: metadata와 `attachment_<uuid>` file part, 이미지 없는 저장, 치환 응답 구현
- 완료 조건:
  - [x] placeholder 누락·중복·미사용 file 전체 거절
  - [x] 이미지 없는 수동 저장 회귀 통과

### TASK-003 이미지 검증

- 관련 요구사항: `REQ-002`, `REQ-004`
- 작업: signature·decoder·dimension·10MB·20개·100MB 검증
- 완료 조건:
  - [x] MIME 위장·SVG·손상 파일 거절
  - [x] GIF bytes 보존과 WebP dimension 검증

### TASK-004 MinIO와 DB 보상

- 관련 요구사항: `REQ-003`
- 작업: asset key 생성, object 저장, 조건부 DB 갱신, 실패 보상·orphan 기록
- 완료 조건:
  - [x] MinIO 실패 시 DB 무변경
  - [x] 충돌·DB 실패 시 신규 object 삭제

### TASK-005 Reference 동기화

- 관련 요구사항: `REQ-006`, `REQ-008`
- 작업: GFM parser 추출, workspace batch 검증, reference diff, 복제 reference 복사
- 완료 조건:
  - [x] 다른 workspace asset 저장 거절
  - [x] 중복 사용 reference 하나 유지

### TASK-006 이미지 조회·프론트 표시

- 관련 요구사항: `REQ-005`
- 작업: 멤버 전용 stream, private cache·ETag·nosniff, JWT Blob renderer
- 완료 조건:
  - [x] 비멤버 `404`
  - [ ] Blob cache·revoke 컴포넌트 테스트

### TASK-007 미참조 정리

- 관련 요구사항: `REQ-007`, `REQ-008`
- 작업: 7일 worker, `SKIP LOCKED`, MinIO 성공 후 DB 삭제, orphan 정리
- 완료 조건:
  - [x] 재참조·소프트 삭제 asset 유지
  - [x] MinIO 실패 재시도

### TASK-008 ZIP 내보내기

- 관련 요구사항: `REQ-009`
- 작업: URL 상대 경로 치환, 파일명 충돌, 100개·100MB 제한, 임시 ZIP 정리
- 완료 조건:
  - [x] 로컬 Markdown 이미지 표시
  - [x] 외부 URL fetch 없음
  - [x] 누락 asset 불완전 ZIP 미반환

### TASK-009 계약·보안·회귀

- 관련 요구사항: 전체
- 작업: API·OpenAPI·요구사항 추적표와 전체 통합 테스트
- 완료 조건:
  - [x] Markdown 5MB와 이미지 100MB 제한 구분
  - [x] bytes·storage key 로그 미노출
  - [x] 전체 테스트와 `git diff --check` 통과

## 4. 실행 순서

공유 token으로 이미지를 조회하는 endpoint와 공개 권한 검증은 [`markdown-document-sharing-tasks.md`](./markdown-document-sharing-tasks.md)의 `TASK-S007`에서 구현한다. 이 문서는 멤버 전용 asset 저장·조회까지 담당한다.

```text
TASK-001 → TASK-002 → TASK-003 → TASK-004 → TASK-005
                                      └────→ TASK-006
TASK-005/006 → TASK-007 → TASK-008 → TASK-009
```

## 5. 검증 명령

```sh
cd backend
./gradlew test
./gradlew flywayValidate

cd ../frontend
npm run lint
```
