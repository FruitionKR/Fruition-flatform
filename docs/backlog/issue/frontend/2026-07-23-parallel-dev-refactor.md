# 2026-07-23 Frontend 병렬 개발 리팩토링 계획

PR #101(문서 탐색·Markdown Agent 편집)과 PR #102(이메일 인증 연동)가 병합 시
`frontend/app/_lib/api.ts` 한 파일에서 충돌했다. 여러 Frontend 기능을 동시에
개발할 때 반복될 구조적 병목을 제거하기 위한 리팩토링 계획을 남긴다.

관련 기록: `docs/changelog/frontend.md`의 PR #101·#102 항목, `docs/issue/frontend/2026-07-23.md`.

## 1. 진단: 충돌 원인

컴포넌트는 이미 feature 폴더로 세로 분리되어 있어 충돌하지 않는다
(`_components/agent-panel/`, `document-sidebar/`, `note-editor/`, `graph/`, `home-workspace/`).

문제는 **모든 기능이 공유하는 두 개의 God 파일**이다.

| 파일 | 크기 | import하는 파일 수 | 문제 |
| --- | --- | --- | --- |
| `frontend/app/_lib/api.ts` | 443줄 | 19 | auth·workspace·chat·note·document·wiki·agent·export 8개 도메인이 한 파일 |
| `frontend/app/_lib/types.ts` | 282줄 | 35 | 모든 도메인 타입이 한 파일 |

어떤 기능을 건드리든 이 두 파일을 열게 되므로 병렬 브랜치 간 merge conflict가 구조적으로 발생한다.

## 2. 목표

- `api.ts`·`types.ts`를 도메인별 파일로 분리해 서로 다른 기능이 서로 다른 파일을 편집하도록 만든다.
- 기존 import 경로(19+35개)는 **한 줄도 수정하지 않는다** — 배럴(re-export) 유지 방식.
- 검증: `npm run lint`, `npm exec tsc -- --noEmit`, `npm run build`, `npm run test:markdown` 모두 통과.

## 3. api.ts 도메인 분리 (실제 함수 매핑)

기존 `_lib/api.ts` → `_lib/api/` 폴더로 분해. 기존 `_lib/api.ts`는 배럴로 남긴다.

```
_lib/api/client.ts    ← authFetch 헬퍼 + 에러추출 헬퍼 + 공통 상수 (base, 거의 안 바뀜)
_lib/api/auth.ts      ← loginWithEmail, getOAuthAuthorizationUrl, exchangeOAuthCode,
                         requestEmailVerification, confirmEmailVerification,
                         signupWithEmail, resetPasswordWithVerification, fetchMe   [PR102]
_lib/api/workspace.ts ← fetchWorkspaces, createWorkspace
_lib/api/chat.ts      ← fetchChatSessions, fetchCurrentChatSessionId,
                         clearSessionCache, fetchChatMessages
_lib/api/document.ts  ← uploadDocumentFile, deleteDocument, renameDocument,
                         fetchDocumentBlocks, fetchDocumentOriginal   [PR101]
_lib/api/note.ts      ← fetchNoteDraft, saveNoteDraft, NoteContentConflictError   [PR101]
_lib/api/wiki.ts      ← fetchBackendData, queryWiki, fetchWikiPage
_lib/api/agent.ts     ← requestAgentTurn   [PR101]
_lib/api/export.ts    ← fetchChatWikiExportPreview, exportChatWiki
```

배럴 (`_lib/api.ts`):

```ts
export * from './api/client'
export * from './api/auth'
export * from './api/workspace'
export * from './api/chat'
export * from './api/document'
export * from './api/note'
export * from './api/wiki'
export * from './api/agent'
export * from './api/export'
```

→ PR101은 document/note/agent, PR102는 auth 파일만 편집 → 같은 파일 충돌 0.

## 4. types.ts 도메인 분리

동일 원리. `_lib/types.ts` → `_lib/types/` 폴더로 분해 후 배럴 유지.

```
_lib/types/tree.ts      ← TreeItem, Project, DropPosition, DropTarget,
                           ContextMenuState, EditingState, FileDropTarget,
                           UploadPickerTarget, DocumentStatus, NoteSaveStatus, NoteEditState
_lib/types/auth.ts      ← UserMeResponse
_lib/types/workspace.ts ← WorkspaceResponse, WorkspaceListResponse
_lib/types/chat.ts      ← ChatSessionResponse, ChatSessionListResponse
_lib/types/document.ts  ← DocumentUploadResponse, DocumentItemResponse,
                           DocumentListResponse, NoteContentResponse
_lib/types/wiki.ts      ← WikiGraphNode/Edge/Response, BackendData,
                           QueryRelatedPageResponse 등 나머지 wiki/query 타입
```

배럴 (`_lib/types.ts`)은 `export * from './types/*'` 로 유지.

## 5. 실행 단계 (검증 포함)

1. `_lib/api/client.ts` 추출 (authFetch·에러헬퍼·상수) → verify: tsc 통과
2. 도메인별 `_lib/api/<domain>.ts` 생성, `client` import → verify: tsc 통과
3. `_lib/api.ts`를 배럴로 교체 → verify: lint + tsc + build 통과
4. `_lib/types/*` 동일 분리, `_lib/types.ts` 배럴 교체 → verify: tsc 통과
5. 전체 검증: `npm run lint`, `npm exec tsc -- --noEmit`, `npm run build`, `npm run test:markdown`

각 단계는 순수 이동(코드 로직 변경 없음)이므로 리스크 최소.

## 6. 병렬 개발 워크플로우 (분리 이후)

기능당 독립 브랜치 + git worktree로 동시 작업.

```bash
git worktree add ../local-pilot-auth   feat/<auth-feature>
git worktree add ../local-pilot-note   feat/<note-feature>
```

- feature별 담당 파일: `_components/<feature>/`, `_lib/api/<domain>.ts`, `_lib/types/<domain>.ts`
- 배럴 파일(`api.ts`·`types.ts`)은 새 도메인 추가 시에만 한 줄 추가 → 충돌 나도 add/add 라 해결 자명
- `client.ts`(공통 base)는 안정적이라 거의 안 바뀜 → 공통 모듈로 유지

## 7. 남은 판단

- 완전 분리(배럴 제거)는 추후 import 경로 정리가 필요하면 별도 이슈로.
- backend/`api.ts`에 해당하는 서버 측 공통 모듈 분리는 이 계획 범위 밖(Frontend 한정).
