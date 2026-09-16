# 문서 버전 이력·복원

> 작성일: 2026-08-06
> 대체 문서: `docs/backlog/note-editor-prototype.md`(local mock 전제 프로토타입)의 저장·이력 계약을 대체한다.
> 관련 문서: `docs/spec/sdd/markdown-document-core.md`(저장·버전 백엔드 SDD), `docs/spec/sdd/markdown-document-erd.md`(ERD)

Markdown 문서의 자동저장이 만드는 서버 버전 이력을 Frontend에서 조회·비교·복원하는 계약을 정한다. 이전 구현이 사용하던 localStorage 스냅샷(`fruition.snapshots.v1.*`, 문서당 30건)은 제거하고 서버 이력으로 대체한다.

## 1. 저장·버전 모델 (Backend, 구현 완료)

- 자동저장 `PUT /api/workspaces/{workspace_id}/documents/{document_id}/content`은 `base_version` 낙관적 잠금으로 동작한다. 현재 버전과 다르면 `409 Conflict`.
- 내용이 실제로 바뀐 저장마다 `document_content_versions`(append-only, 전문 스냅샷)에 이전 버전과 새 버전이 기록된다. `documents.current_version`이 현재 버전 카운터다.
- AI 편집 저장(`source=agent`)은 `ai_operation_logs`와 연결된다(`linkOperation`).
- 구현 위치: `services/backend/.../document/service/DocumentService.java`(saveContent, listContentVersions), migration `V12__add_document_content_versions.sql`.

## 2. 버전 API 계약

Base: `/api/workspaces/{workspace_id}/documents/{document_id}`

| Method | Path | 응답 | 용도 |
|---|---|---|---|
| GET | `/versions` | `{document_id, current_version, versions[{version, content_hash, created_by, created_at}]}` (본문 제외, 최신 순) | 버전 목록 |
| GET | `/versions/{version}` | `{..., markdown, ...}` (본문 포함) | 특정 버전 본문 |
| GET | `/diff?from_version=&to_version=` | `{additions, deletions, hunks[{old_start, old_lines, new_start, new_lines, lines[{type: CONTEXT\|DELETE\|ADD, old_line, new_line, content}]}]}` | GitHub 스타일 diff |
| POST | `/versions/{version}/restore` | body `{base_version}` → `DocumentContentSaveResponse{current_version, ...}` | 비파괴 복원(과거 버전을 새 버전으로 저장). `base_version` 불일치 시 409 |

## 3. Frontend 연동 (2026-08-06 구현)

구현 위치: `frontend/src/features/document-history/`

- `api/versions.ts` — 위 API의 fetch 래퍼. 복원 409는 `VersionRestoreConflictError`로 구분한다.
- `lib/versionDiff.ts` — 서버 diff hunk를 렌더링 행으로 평탄화(`flattenDiffHunks`). Frontend는 diff를 자체 계산하지 않는다.
- `ui/HistoryPanel.tsx` — 버전 목록·서버 diff·복원 패널. `SourcePreviewPanel`의 문서 옵션 메뉴 "버전 기록"으로 연다(Markdown 노트 한정).

### 3.1 동작 규칙

- 패널을 열면 `GET /versions`로 목록을 불러오고, 버전을 선택하면 `GET /diff?from_version={선택}&to_version={current_version}`으로 현재 버전과 비교한다.
- 복원은 `POST /versions/{선택}/restore`에 목록 조회로 얻은 `current_version`을 `base_version`으로 보낸다.
  - 성공: 목록을 다시 불러오고, 문서 화면은 본문·버전을 다시 조회해 에디터를 새 버전으로 갱신한다(`SourcePreviewPanel`의 reload).
  - 409: 다른 저장이 먼저 반영된 것이므로 오류를 표시하고 목록을 갱신해 다시 비교하게 한다. 자동 재시도하지 않는다.
- 현재 버전(목록의 `current_version`)은 복원 대상에서 제외한다.
- AI 편집 직전 localStorage 캡처는 제거했다. AI 편집 저장 자체가 이전 버전 스냅샷을 서버에 남기므로 별도 캡처가 필요 없다.

### 3.2 한계

- 자동저장 debounce(800ms) 안에서 저장되지 않은 입력 상태는 버전으로 남지 않는다. 이력 단위는 "저장된 버전"이다.
- AI 편집 복원 전용 흐름(`ai-operation-logs/{id}/restore-preview`·`/restore`)은 이 패널과 별개이며 아직 Frontend 미연동이다. 필요 시 후속 작업으로 다룬다.

## 4. 검증

- 단위 테스트: `frontend/tests/markdownVersionDiff.test.mjs`(diff 평탄화). `npm run test:markdown`.
- 수동 검증: Markdown 노트 편집 → 옵션 메뉴 "버전 기록" → 버전 선택·diff 확인 → 복원 → 에디터 본문·버전 갱신 확인. 두 탭에서 동시 편집 후 복원 시 409 표시 확인.
