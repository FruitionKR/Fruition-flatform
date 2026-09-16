# Changelog — Frontend

React 프론트엔드 변경 이력입니다. 날짜 역순으로 기록합니다.

---

## 2026-08-07

### feat: PDF 원본 "Markdown으로 변환" 액션

- 문서 사이드바 우클릭 컨텍스트 메뉴에 "Markdown으로 변환" 추가 — PDF 원본
  (`mimeType: application/pdf`)에만 노출, 업로드/처리 중이면 비활성.
- `convertDocumentToMarkdown` API(202, Idempotency-Key uuid) 호출 후 기존 목록
  재동기화로 새 문서가 '변환 중' 상태로 표시(별도 폴링 미추가 — 기존 갱신 경로 재사용).

### feat: 문서 저장 계약을 base_revision·revision_write_id로 전환

- 노트 저장(`saveNoteDraft`)이 backend MongoDB 전환 계약에 맞춰 `base_revision` +
  `revision_write_id`(crypto.randomUUID)를 전송한다. 재시도 멱등 처리 기반.
- 편집 기준 버전을 상세 응답의 `edit_revision` 우선으로 사용(`current_version` 폴백).

## 2026-08-06

### feat: access token silent refresh

- `apiFetch`가 401을 만나면 저장된 refresh token으로 `POST /api/auth/refresh` 재발급을
  1회 시도하고 원요청을 재시도한다. 동시 401은 재발급 요청 하나를 공유한다.
  재발급까지 실패한 경우에만 로그인 필요 에러를 던진다. `/api/auth/**` 자체의 401
  (비밀번호 오류 등)은 재발급 대상이 아니다.
- `auth.ts`의 refresh 미구현 TODO 제거, `getRefreshToken` 추가.

### feat: 문서 버전 이력을 서버 API로 전환

- `features/document-history`를 localStorage 스냅샷에서 Backend 버전 API 연동으로 재작성했다.
  `GET /versions` 목록, `GET /diff` 서버 diff, `POST /versions/{v}/restore` 비파괴 복원을 사용한다.
- 미장착 상태였던 `HistoryPanel`을 `SourcePreviewPanel` 문서 옵션 메뉴의 "버전 기록"으로
  연결했고, 복원 성공 시 본문·버전을 다시 불러와 에디터를 갱신한다. 복원 409는 자동
  재시도 없이 목록 갱신 후 재비교를 안내한다.
- AI 편집 직전 localStorage 캡처(`useSnapshots`)와 클라이언트 diff(`lineDiff`)를 제거했다.
  서버 저장이 이전 버전 스냅샷을 이미 남기므로 중복이다.
- 계약 문서: `docs/spec/document-version-history.md`. 테스트: `tests/markdownVersionDiff.test.mjs`.

---

## 2026-07-30

### fix: 비동기 설정·AI 저장·채팅 편입 선택 경합 수정

- 경로 변경으로 폐기된 사용자 설정 요청의 실패 응답이 새 요청의 `preferencesReady`를
  앞당기지 않도록 cleanup 상태를 확인한다.
- 저장 중 AI 결과와 후속 사용자 편집이 대기열에서 합쳐질 때 `source=agent`를 보존해 승인
  스냅샷이 누락되지 않도록 한다.
- AI 저장이 비충돌 오류로 실패해도 대기 중인 최신 본문 또는 다음 저장 후보에 `source=agent`를
  유지해 재시도 성공 시 승인 스냅샷이 생성되도록 한다.
- 채팅 편입 문서가 프로젝트 트리에 병합된 뒤 트리 항목으로 선택해 문서 본문, 사이드바 선택,
  breadcrumb가 같은 문서를 가리키도록 한다.
- 채팅 편입 후 문서 목록 갱신 실패를 성공으로 처리하지 않고 호출부까지 전파하며, 서버 편입
  성공과 목록 갱신 실패를 분리해 중복 편입 대신 새로고침 안내를 표시한다.
- 검증: `npm run test:markdown` 52건, `npm run test:user-preferences` 4건,
  `npx tsc --noEmit`, `npm run lint`, `npm run build`, `npm audit --omit=dev`를 통과했다.

## 2026-07-28

### feat: AI 편집 스냅샷과 채팅 문서 편입 저장 연결

- AI 편집 결과를 적용하면 문서 저장 요청의 `source=agent`를 함께 전송하고, 일반 자동 저장과
  구분해 즉시 저장한다. 백엔드는 이 요청을 `document_content_versions`에 기록하므로 AI 편집
  승인 시점이 서버 스냅샷으로 영속화된다.
- 채팅 문서 편입 성공 응답의 `exportDocumentId`를 기준으로 워크스페이스 문서 목록을 새로
  불러오고, 저장된 편입 문서를 자동으로 선택해 연다.
- 로컬 전체 스택에서 AI 저장 후 서버 version 스냅샷 생성과 채팅 편입 문서의 사이드바 노출,
  자동 선택, Markdown 본문 표시를 확인했다.

### feat: 브라우저 사용자별 개인 설정 구현

- 설정 임시 목업을 실제 개인 설정 화면으로 교체했다. Motion, 문서 Font, 기본 편집 모드,
  Markdown 줄 바꿈·줄 번호·현재 줄 강조, Graph 기본 노드 표시, 문서 처리 완료·실패·Browser
  알림을 한 화면에서 변경할 수 있다.
- 공통 설정은 인증 사용자 ID별, Graph 기본 표시는 사용자+workspace별 `localStorage`에 자동
  저장한다. backend API가 없어 현재 같은 브라우저에서만 유지되며, 계정 식별 실패 시 사용자 간
  혼합을 막기 위해 공용 키에 저장하지 않는다.
- Motion 줄이기는 CSS 전환·애니메이션, 채팅 smooth scroll, Graph 물리·hover 애니메이션에
  적용한다. 문서 Font는 Markdown 렌더와 WYSIWYG 본문에 적용하고 코드 글꼴은 유지한다.
- 기본 편집 모드는 `마지막 사용 모드 / WYSIWYG / Markdown`으로 연결하고, Markdown 표시 옵션을
  CodeMirror 설정에 반영했다.
- Graph 필터를 사용자 기본값과 양방향 연결하고 모든 노드 종류를 동시에 끄지 못하게 했다.
- 선택된 문서가 있는 Graph에서도 포인터 hover가 클릭 없이 즉시 반응하도록 외부 선택과 hover
  상태를 분리했다. Markdown 줄 번호는 현재 커서 줄만 회색 `|`로 표시하고 기본 gutter 세로선을
  제거했다.
- 워크스페이스 목록 호출 실패 시 빈 오류 문장 대신 화면 중앙 오류 카드, 상세 메시지, 재시도,
  로그인 화면 이동을 제공한다. 재시도는 세션을 유지한 채 워크스페이스 준비 요청을 다시 실행한다.
- 문서 상태 polling에서 `uploaded/processing → completed/failed` 전이를 감지해 앱 안 알림을
  표시한다. 숨겨진 탭에서도 처리 중 polling을 유지하며, Browser 알림은 사용자 권한이 있고 탭이
  보이지 않을 때만 사용한다.
- 문서 업로드에 backend 계약의 `Idempotency-Key`를 추가했다. Markdown 편집본은 문서 상세
  `markdown/current_version`에서 읽고, 저장은 `multipart/form-data`의 `markdown/base_version`으로
  전송해 production 문서 API와 맞췄다. 직접 생성 노트는 원본보다 편집본을 먼저 읽는다.
- FSD 이동 전 `frontend/app/_lib/*`를 가리키던 Markdown 테스트 import를 현재 `src` 경로로
  갱신했다. production `postcss` override는 보안 패치 버전 `8.5.24`로 올렸다.
- 계정 동기화·AI 답변 설정·앱 종료 후 push 알림은 frontend에서 동작하는 것처럼 노출하지 않고
  `docs/issue/backend/2026-07-28.md`, `docs/issue/ai/2026-07-28.md`에 후속 계약으로 분리했다.
- 검증: `npm run lint`, `npm exec tsc -- --noEmit --incremental false`, `npm run test:markdown`
  47건, `npm run test:user-preferences` 4건, `npm run build`, `npm audit --omit=dev`를 통과했다.
  로컬 전체 스택에서 회원가입·설정 reload 복원·Graph 필터·Markdown 업로드/조회/자동 저장을
  Playwright로 확인했다.

## 2026-07-24

### feat: 채팅 편집 시 선택한 문답을 편집 맥락으로 전송

- 마크다운 편집(agent/turn) 요청에 사용자가 선택한 채팅 문답(pair)을 `conversationContext.recentConversationSummary`로 실어 보내도록 배선. backend·pipeline은 이미 `recent_conversation_summary`를 소비하나 frontend가 미전송이던 gap을 채움.
- 기존 문답 선택 체크박스(`selectedPairIds`, 채팅→위키 편입용)를 편집 맥락에도 공용으로 사용. 선택이 없으면 필드 자체를 생략(현행 무회귀).
- `AgentTurnRequest`에 옵셔널 `conversationContext` 추가, `buildSelectedConversationSummary`(선택 문답 전사·4000자 상한) 헬퍼 추가, `<details>` 라벨을 "채팅 선택 (편집 맥락·편입 공용)"으로 조정. (`markdownAgent.ts`, `shared/lib/messages.ts`, `AgentPanel.tsx`)

### feat: 사이드바 문서 처리 뱃지 라벨/툴팁 개선

- 사이드바 문서 트리의 `stalled` 상태 뱃지 라벨을 "지연" → "작업 중"으로 변경하고, tooltip 문구도 "처리 지연: {stage}"/"처리가 지연되고 있습니다." → "작업 중: {stage}"/"작업 중입니다."로 맞춤. (`TreeNodeStatus.tsx`)
- 네이티브 `title` 속성 tooltip을 커스텀 tooltip으로 교체. hover 0.2초 후 노출(`setTimeout`). 사이드바 스크롤 컨테이너(`.sidebar-content`의 `overflow` 클리핑)를 피하려 `createPortal`로 `document.body`에 `position: fixed` 렌더하고, 뱃지 `getBoundingClientRect` 기준으로 위 중앙에 배치. (`TreeNodeStatus.tsx`, `DocumentSidebar.module.css`의 `.tree-tooltip`)
- tooltip에 업로드 시각(`uploadedAt`) 기준 경과 시간을 함께 표시("업로드 후 N분/시간/일 경과"). 렌더 시점 정적 계산이라 사이드바 리렌더 때 갱신됨. 백엔드가 stalled 시작 시각을 주지 않아 `uploadedAt`을 기준으로 사용. 모든 처리 뱃지(처리 중/작업 중/실패)에 적용. (`TreeNodeStatus.tsx`, `TreeNode.tsx`에서 `uploadedAt` 전달)
- 접근성: portal tooltip은 hover 전용이라, 뱃지 `<small>`에 `aria-label`로 동일 문구(상태 + 경과시간)를 부여해 스크린리더 노출 유지.

### refactor: 미사용 문서 점검(document lint) 기능 제거

- PR #111 리뷰 반영. "AI 문서 점검" 버튼 제거로 트리거가 사라져 도달 불가가 된 lint 배선을 전 구간 정리.
- 제거: `SourcePreviewPanel`의 `onRequestLint` prop과 write-only가 된 `activeEditContext` state, `HomeWorkspace`의 `requestDocumentLint`·`lintRequest` state·`lintRequestIdRef`, `AgentPanel`의 `lintRequest` prop·`handledLintRequestIdRef`·전송 effect.
- 유지: `needsReview`/`noteEditStates`는 사이드바 트리 상태 배지(`TreeNodeStatus`)에서 계속 사용되므로 건드리지 않음.

### fix: 채팅 세션 목록 스크롤 복원 및 행 옵션 메뉴 portal 처리

- PR #111 리뷰 반영. 행 옵션 메뉴가 잘리지 않게 `.chat-session-list`를 `overflow: visible`로 뒀던 탓에 세션이 많으면 목록 스크롤이 사라지고 dropdown(`max-height: 320px`) 밖으로 흘러넘치던 문제 수정.
- `.chat-session-list`를 `overflow-y: auto`로 되돌려 스크롤 복원. 행 옵션 메뉴는 `createPortal`로 `document.body`에 `position: fixed`로 띄워(버튼 rect 기준 좌표) 스크롤 컨테이너 클리핑을 피함. 메뉴 `onMouseDown` 전파를 막아 목록이 먼저 닫히지 않게 하고, 목록이 닫히면 메뉴도 함께 정리.

### feat: 워크스페이스 생성 로딩 오버레이 추가

- 전체화면 `LoadingOverlay`(신규, `shared/ui`) 추가. `SidebarWorkspaceHeader`(생성 중)와 `WorkspacesPage`(자동 프로비저닝 중)에 배선.

### fix: 편집기 undo·스크롤바·문서 점검 버튼 정리

- undo 수정: Milkdown 프로그램적 전체 교체를 `addToHistory:false` 트랜잭션으로 바꿔 cmd+z 한 번에 문서 전체가 사라지던 문제 해결(`NoteEditor.tsx`, `replaceAll` → `editorViewCtx/parserCtx/Slice` 직접 dispatch).
- 스크롤바 다크 처리: 전역 `base.css` 스크롤바 규칙이 해시된 CSS Module class에 안 붙던 문제를 `SourcePreviewPanel.module.css`에 직접 지정해 해결. 스크롤 컨테이너를 패널 전체 폭으로 두고 본문은 padding 중앙 정렬 → 세로 스크롤바가 항상 패널 맨 오른쪽(에이전트 패널 접힘/펼침 무관).
- 제목 스크롤: 제목(heading)을 스크롤 컨테이너 내부로 이동해 본문과 함께 스크롤(Obsidian식). 제목-본문 사이 "AI 문서 점검" 버튼 제거(`renameError`만 조건부 유지).

### feat: 채팅 세션 옵션 메뉴 추가 및 새 세션 제목 통일

- 새 세션 fallback 제목을 헤더와 동일한 "새 채팅"으로 통일(불일치 버그).
- 세션 행에 Fruition 로고(임시 SVG) + 옵션 메뉴(원본 문서로 생성 / 삭제) 추가. `deleteChatSession` 프론트 API 추가(기존 백엔드 DELETE 사용), 원본 문서화는 기존 `wiki-export` 재사용.
- composer placeholder를 문서 열림 여부와 무관하게 항상 "AI 에이전트에게 무엇이든 물어보세요."로 고정.
- 주의: 당시 채팅→원본문서 편입의 wiki 생성 단계는 프론트 무관한 파이프라인 설정 문제로 실패했다. 해결 기록은 `docs/backlog/issue-2026-07-25.md`의 `AI/Pipeline — Multi-provider 설정과 Claude Messages API 지원`을 참고한다.

### feat: 로그·설정 임시 목업 페이지 추가

- 로그/설정 페이지 임시 목업 컴포넌트 추가(`features/logs-mockup`, `features/settings-mockup`). rail 뷰 배선은 `HomeWorkspace` 변경에서 함께 처리.

### fix: 노트 사라짐 버그 수정 및 그래프 필터 인셋 조정

- 노트 사라짐 버그: `<main onClick={clearTreeGraphSelection}>`이 자식에서 버블된 클릭까지 선택 해제해, 사이드바 여백·폴더 헤더 오클릭 시 편집기가 비던 문제를 `event.target === event.currentTarget` 가드로 해결(`HomeWorkspace`).
- `HomeWorkspace`에 로그/설정 목업 rail 뷰 배선 및 메인 편집기 "변경 기록" 버튼 제거(orphan import/state 정리).
- 그래프 필터: Figma(node 599:5832) 실측 반영해 필터칩·캔버스 인셋 20→24px.

---

## 2026-07-23

### refactor: 전역 CSS를 CSS Module로 하이브리드 전환

**변경된 내용**

- 슬라이스별 스타일 격리를 위해 전역 className 스타일시트를 CSS Module로 전환했다(하이브리드 전략).
  - 스코프(module): `schema-manage`, `graph`, `document-sidebar`, `rail-navigation`, `document-search`, `agent-chat`(agent-panel 7개 서브 css 병합), `source-preview`, `note-editing`, `landing`, `document-history`. 클래스명은 kebab 유지, TSX는 `styles["kebab"]` 접근.
  - 전역 유지(app 레이어, `src/app/styles/`): 디자인 토큰(`base.css` `:root`), 워크스페이스 루트 상태 클래스(`workspace`, `is-*`), 레이아웃 앵커(`agent-panel-shell.css`의 `.agent-panel`), 그리고 여러 슬라이스가 공유하는 **콘텐츠 어휘**(`markdown.css`) 및 cross-component 폼/오버레이 어휘(`auth.css`, `modal.css`).
- cross-component 상태 반응은 `:global(.workspace.is-X) .localClass` 패턴으로 유지. 서드파티 DOM 클래스(milkdown `.milkdown/.ProseMirror`, codemirror `.cm-*`, 공용 `.svg-icon`)는 `:global()`로 참조.
- CSS Module의 pure-selector 제약(로컬 클래스 없는 순수 전역 셀렉터 불가)에 따라 레이아웃 앵커 자기 규칙은 전역 파일로 분리.

**설계 판단**

- 이 프로젝트는 전역 className 방식이고 Next App Router는 전역 CSS를 layout에서만 import 허용한다. 따라서 "모든 클래스 스코프"(순수 방식)는 cross-component 조정 클래스를 깨뜨리므로, 조정/공유 어휘는 전역으로 남기고 컴포넌트 내부 시각 스타일만 스코프하는 하이브리드가 정답.

**검증**

- 각 슬라이스 그룹 전환 후 dev 서버에서 스크린샷 회귀(홈·규칙·그래프·랜딩)로 baseline 대비 시각 동일 확인. CSS Module pure 위반은 dev 빌드가 즉시 검출(tsc는 못 잡음)해 전역 분리로 해결.
- 최종 `next build` 성공(9개 라우트 프리렌더, 전 CSS Module 컴파일 통과).

### refactor: 프론트엔드 폴더 구조를 Feature-Sliced Design으로 전환

**변경된 내용**

- 공식 FSD 스펙(레이어→슬라이스→세그먼트, 하위 레이어로만 import)에 맞춰 147개 파일을 `frontend/src/` 아래 6개 레이어로 재배치했다.
  - `shared`(api/client, lib, ui, types), `entities`(document·chat·wiki·schema·workspace·user·graph·tree), `features`(agent-chat·note-editing·schema-manage·document-history·document-search·document-upload·wiki-export), `widgets`(workspace·document-sidebar·graph·agent-panel·source-preview·rail-navigation·top-bar), `views`(landing·home·login·workspaces·auth), `app`(providers, styles).
- Next.js app router 충돌은 공식 가이드대로 처리: FSD는 `src/`에 두고, Next `app/**/page.tsx`는 `@/views/*`를 re-export 하는 얇은 라우팅 껍데기로만 유지.
- **FSD `pages` 레이어는 `views`로 명명**: Next.js가 `src/pages/`를 레거시 Pages Router로 인식해 app router와 라우트가 충돌하므로, 공식 권장대로 레이어명을 `views`로 사용한다.
- 전역 스타일은 `app` 레이어(`src/app/styles/`)로 이관. (프로젝트가 전역 className 방식이고 Next는 전역 CSS를 layout에서만 import 허용하므로, 슬라이스별 CSS Module 콜로케이트 대신 app 레이어 집約이 맞다.)
- `tsconfig.json`에 `@/*` → `./src/*` alias 도입. 슬라이스별 `index.ts` public API 추가. 임시 배럴(`_lib/api·types·tree`) shim을 단계적으로 제거하고 모든 참조를 canonical alias로 연결.
- 단계(shared→entities→features→widgets→views/app→styles)로 나눠 각 단계 커밋 + `tsc --noEmit` green 검증.

**검증**

- 각 단계 `tsc --noEmit` exit 0. 최종 `next build` 성공(9개 라우트 전부 컴파일·프리렌더).

**남은 작업(선택)**

- 파일명 kebab-case 정규화는 보류: 컴포넌트 파일은 React 관례상 PascalCase가 일반적이라 약 100개 일괄 개명은 이득 대비 변경·리스크가 커 권장하지 않음(필요 시 별도 진행).

### feat: 규칙·그래프·채팅 패널 Figma 정합 정리

**변경된 내용**

- 규칙(스킬) 화면(`SchemaWorkspace`): 라이트 하드코딩 색상을 셸 다크 팔레트(#0a0a0a/#1e1e1e/#4f4f4f/#f0f0f0)로 교체하고, `position: absolute` + `inset` 좌측 오프셋을 적용해 왼쪽 사이드바에 가려지던 문제를 해결한다. (`_styles/schema.css`)
- 그래프 뷰 상단 GNB(`.graph-topbar`) 제거: Figma 그래프 시안(node 599-4903)에 없는 "마지막 편집" 라벨·패널 토글·옵션 메뉴를 삭제한다. 패널 재열기는 `GraphFilterChips`가 담당하므로 기능 손실 없음. `GraphOptionsMenu`(레이아웃 초기화)도 함께 삭제. `.graph-stage` top을 0으로 조정. (`HomeWorkspace.tsx`, `_styles/graph/stage.css`, `GraphOptionsMenu.tsx` 삭제)
- 채팅 패널 자동 닫힘 제거: 문서를 열면 오른쪽 채팅 패널을 강제로 닫던 로직을 삭제해, Figma 편집기 시안(node 426-2115)처럼 문서와 채팅 패널이 함께 열리도록 한다. 레이아웃은 기존 예약 폭(우측 360px)을 그대로 사용. (`HomeWorkspace.tsx`)
- 그래프 뷰 채팅 패널 스타일 통일: 그래프 전용으로 떠있는 둥근 카드(radius 32, 여백 inset)로 override하던 CSS를 제거해, 편집기 화면과 동일한 전체높이 우측 밀착 패널(360px)로 맞춘다. `.graph-stage` 우측 예약폭도 428→360으로 정렬. (`_styles/agent-panel/shell.css`, `_styles/graph/stage.css`, `_styles/responsive.css`)

**검증**

- `tsc --noEmit` 통과. Playwright 런타임으로 규칙 화면 겹침 해소, 그래프 GNB 제거, 문서+채팅 공존, 편집기·그래프 채팅 패널 픽셀 일치(left 1152/width 360/radius 0) 확인.

### fix: 채팅 세션 전환 상태 누수·중복 로드 정리 (PR #107 리뷰 반영)

**변경된 내용**

- `AgentPanel`: 세션 전환 시 `selectedPairIds`를 초기화한다. 이전 세션에서 고른 부분 편입(pair) 선택이 남아, 전환 후 export가 다른 세션의 `pair_id`로 나가던 문제를 막는다.
- `useChatThread`: 세션 전환 이펙트에 `cancelled` 가드를 추가해 빠른 전환 시 이전 세션 응답이 뒤늦게 반영되는 stale 렌더를 방지한다. 또한 `getSessionContext`로 확정 세션을 비교(`loadedSessionRef`)해, 마운트 시 `null`→현재 세션 확정으로 발생하던 메시지 중복 GET을 제거한다.

**검증**

- `npm exec tsc -- --noEmit`, `npm run lint`, `npm run build` 통과.

### feat: 그래프·채팅 배선(세션 전환·SSE 진행·부분 편입·필터/메뉴 동작)

**배경**

- 그래프·채팅(agent-panel) 리디자인 화면의 미연결·no-op 지점을 실제 동작으로 배선한다(stream3 그래프+채팅).

**변경된 내용**

- 다중 세션 전환 배선: `chat.ts`에 선택 세션 override(`setActiveChatSession`)를 추가해 `getSessionContext` 기반 messages·query·export가 선택 세션을 대상으로 하도록 하고, `AgentHeader` 세션 항목 클릭을 `onSelectSession`으로 연결, `AgentPanel`이 active 세션을 보유해 `useChatThread`가 전환 시 해당 세션 메시지로 교체한다.
- Query 진행 SSE 전환: `wiki.ts`에 `runQueryStream`(POST `/query/runs` → GET `/api/query/runs/{id}/events` SSE fetch 스트림 → GET run 상태로 최종 결과) 추가, `useChatThread`가 실시간 단계(`query.log`)를 수집하고 `AgentBody`/`StatusList`가 `setTimeout` 가짜 연출 대신 실제 단계를 표시한다.
- 채팅→문서 부분 편입: `exportChatWiki(pairIds)`가 선택이 있으면 `selection_mode:"partial"`+`pair_ids`, 없으면 `full`을 전송하고, `AgentPanel`에 문답(pair) 선택 UI를 추가했다(미리보기는 백엔드가 full만 지원해 전체 표시).
- no-op 정리: `GraphFilterChips` 실제 필터 토글(raw/source/concept 표시 on/off), graph-topbar `패널 보기`(Agent 패널 토글)·`그래프 옵션` 메뉴(레이아웃 초기화, 신규 `GraphOptionsMenu`), `AgentHeader ⋯` 메뉴(새 채팅) 동작 연결.

**검증**

- `npm exec tsc -- --noEmit`, `npm run lint`, `npm run build` 통과.
- 브라우저 구동 확인: 세션 전환(제목·active 이동), FilterChips 토글(노드 숨김/empty state), `패널 보기` 토글, `그래프 옵션`·`⋯` 메뉴 표시.
- **미검증(외부 블로커)**: Query SSE·부분 편입 end-to-end는 Upstage LLM API 키 정지(403 insufficient credit)로 파이프라인이 정지 상태라 실동작 확인 불가. LLM 키 복구 후 별도 테스트 필요.

### fix: 비밀번호 입력 눈 아이콘 표시/숨김 토글 동작 복구

**변경 배경**

- 로그인·회원가입·비밀번호 재설정의 비밀번호 입력 눈 아이콘이 클릭해도 원본이 보이지 않았다.
- 원인은 두 겹이었다: `AuthControls.tsx`의 눈 아이콘이 onClick·상태 없는 정적 `<Image>`였고, `auth.css`의 `.auth-password-icon`에 `pointer-events: none`이 걸려 클릭 자체가 막혀 있었다.

**변경된 내용**

- `AuthControls.tsx`의 `AuthField`에 `useState` 기반 표시/숨김 토글을 추가했다(`"use client"` 명시). 눈 아이콘을 `<button>`으로 바꿔 클릭 시 input `type`을 `password`↔`text`로 전환하고, 상태에 따라 아이콘과 `aria-label`(비밀번호 표시/숨기기)·`aria-pressed`를 갱신한다.
- `auth.css`에서 토글 버튼(`.auth-password-toggle`)을 클릭 가능하도록 위치·`pointer-events`·`cursor`를 분리 정의하고, `.auth-password-icon`은 크기만 담당하도록 정리했다.
- 표시 상태용 뜬눈 아이콘 `svg/auth/auth-password-visible.svg`를 추가했다(기존엔 감은눈만 존재).

**검증**

- `npm run lint` / `tsc --noEmit` / `npm run build` 통과.
- 로컬(`/login`) 브라우저에서 클릭 시 `type=password`→`text`로 원본 노출·아이콘/`aria` 전환, 재클릭 시 복귀 확인.

### docs: 로그인 "아이디 찾기" 비활성 사유 주석 추가

**변경된 내용**

- `login/page.tsx`의 "아이디 찾기" 버튼에 비활성 유지 사유를 코드 주석으로 명시했다. 이 서비스는 이메일=아이디이며 이메일 외 고유 2차 식별자(전화번호 등)를 수집하지 않아 아이디/이메일 조회 기능이 성립하지 않는다.
- 동작 변경 없음(주석만). 인증 4흐름(로그인·회원가입·비밀번호 찾기·재설정) 화면↔API 정합성을 코드로 재검증했고 `lint`/`tsc --noEmit`/`build` 모두 통과했다.
- 라이브 4흐름 브라우저 검증(Backend 기동 필요)과 가입 후 자동 로그인 실패 UX는 `docs/issue/frontend/2026-07-23.md` §11로 이관했다.

### fix: 문서명 검색 접근성·결과 잘림 표시 개선 (PR #104 리뷰 반영)

**변경된 내용**

- `DocumentSearch`의 검색 결과에서 키보드 탐색을 지원하지 않는 `role="listbox"`/`role="option"`/`aria-selected`를 제거했다. 결과 항목은 `<button>`이라 Tab·Enter로 접근되며, 컨테이너는 `role="group"`으로 라벨만 유지한다.
- 매칭이 `MAX_RESULTS`(8)를 초과하면 조용히 잘리던 문제를 개선해, "외 N개 더 있습니다. 검색어를 좁혀 주세요." 안내를 노출한다. `document-sidebar/search.css`에 `.sidebar-search-more` 스타일 추가.

**검증**

- `npm run lint`, `npm exec tsc -- --noEmit`, `npm run build` 통과.

### feat: 문서 처리 상태 뱃지 강화 (stream2 P1, 이슈 #2)

**변경 배경**

- 백엔드 문서 목록 응답은 `processing_state`(starting/running/stalled/completed/failed)와 `processing_stage`(파이프라인 진행 단계 문자열)를 내려주지만 프론트 타입·트리에서 소비하지 않아, 사이드바 뱃지가 처리 중/실패를 구분하지 않고 "Modify ⋯" 단일 표기만 했다.

**추가/변경된 내용**

- `DocumentItemResponse`에 `processing_state`/`processing_stage`, `TreeItem`에 `processingState`/`processingStage`를 추가하고 `DocumentProcessingState` 타입을 정의했다.
- `tree/sync.ts`가 두 필드를 트리에 전파하고 동등성 비교에 포함시켜, 3초 폴링 갱신이 뱃지에 반영되도록 했다.
- `TreeNodeStatus`를 상태별 뱃지로 개편했다: **처리 중 / 지연(stalled) / 실패** (우선순위 failed > stalled > processing). 진행 단계(stage) 문자열은 뱃지 tooltip으로 노출한다. 기존 "Modify ⋯"(영문) 표기를 한글화했다.
- 스타일: `tree-row.css`에 `.tree-status.stalled` 주황 경고 톤 추가, 처리 중/실패 톤 유지.

**검증**

- `npm run lint`, `npm exec tsc -- --noEmit`, `npm run build`, `npm run test:markdown`(46건) 통과.
- 상태 전이(업로드→처리 중→완료/실패, 지연 감지) 실제 표시는 전체 스택(Next dev + Spring + 파이프라인) 기동이 필요해 브라우저 검증은 후속으로 남긴다.

### feat: 워크스페이스 삭제 확인 모달 + 문서명 검색 (stream2 P0)

**변경 배경**

- 사이드바 컨텍스트 메뉴의 삭제가 확인 없이 즉시 서버 삭제되어 실수로 문서/폴더를 잃을 위험이 있었다.
- 전역/문서 검색이 없어(`TopBar` 검색바는 미렌더 dead code) 문서가 많아지면 트리에서 직접 찾아야 했다.

**추가/변경된 내용**

- 삭제 확인 모달(`_components/modals/DeleteConfirmModal.tsx`) 추가. `useProjectTree.deleteContextTarget`을 즉시 삭제에서 확인 모달 열기로 변경하고 `confirmDelete`/`cancelDelete`/`deleteConfirm` 상태를 도입했다. 취소 시 서버 호출이 발생하지 않고, 확인 시에만 기존 삭제·재동기화 로직을 실행한다. 폴더/문서에 따라 문구를 구분한다.
- 사이드바 문서명 검색(`_components/search/DocumentSearch.tsx`) 추가. 트리를 평탄화해 문서/노트 라벨을 클라이언트 필터링하고, 결과 클릭 시 해당 문서를 연다. `DocumentSidebar` 헤더 하단에 마운트했다.
- 스타일: `modal.css`에 취소/삭제 2버튼 액션 줄, `document-sidebar/search.css` 신규 추가.
- 공유 파일 `HomeWorkspace.tsx`는 모달 렌더 한 줄만 최소 편집했다.

**검증**

- `npm run lint`, `npm exec tsc -- --noEmit`, `npm run build`, `npm run test:markdown`(46건) 통과.
- 전문 검색(내용 기반)은 백엔드 검색 API 유무 확인 후 별도 상호참조 이슈로 남긴다(현재 1차 문서명 필터만).

### feat: 문서 변경 기록(스냅샷 diff/롤백) + 스킬(스키마) 임시 UI (stream4)

**변경된 내용**

- **로그(스냅샷/diff/롤백, 클라이언트측)**
  - `_components/history/` 신규: `snapshotStore.ts`(문서별 스냅샷, 메모리+localStorage, 최근 30건), `useSnapshots.ts`(훅), `lineDiff.ts`(LCS diff), `HistoryPanel.tsx`(목록 + snapshot↔현재 `+/−` diff + 롤백).
  - `markdownAgent.ts`의 `lineDiff`는 export되지 않고 수정 금지(스트림3 공유)라, 동일 LCS를 `history/lineDiff.ts`에 재구현하고 `MarkdownDiffLine` 타입만 재사용했다.
  - `HomeWorkspace.tsx` 최소 편집: AgentPanel에 넘기는 편집 컨텍스트를 wrap해 AI 편집 적용 직전 원본을 "AI 편집 전" 스냅샷으로 남기고, 롤백 시 "롤백 전" 현재 본문도 남긴 뒤 `applyMarkdown`으로 복원한다. 홈 문서 화면에 "변경 기록" 오버레이 패널을 추가했다.
- **스킬(스키마) 임시 UI (목업 데이터)**
  - `_lib/types/schema.ts`, `_lib/api/schema.ts` 신규. `schema.ts`는 llmPipeline `wiki_schema` 계약을 흉내낸 **클라이언트 목업**(preview/draft/activate/list/active, localStorage 저장, 인젝션·비밀정보 issue 규칙)이다. Java 프록시 완료 시 함수 본문만 `apiFetch`로 교체.
  - `_components/schema/` 신규: `SchemaWorkspace`(컨테이너), `SchemaEditorForm`(name + markdown), `SchemaPreviewCard`(정리 조각 + SchemaIssue 경고 + activate), `SchemaList`(활성/draft 배지 + 활성화). rail "규칙" 뷰에 마운트.
  - `_styles/history.css`, `_styles/schema.css` 신규 + `globals.css` @import, `_lib/api.ts`·`_lib/types.ts` 배럴에 schema re-export 1줄씩.
- 검증: `tsc --noEmit`, `next lint`, `next build`, `test:markdown`(46 pass) 통과.
- 서버 배선(본문 영속화·wiki-schema Java 프록시·agent 스키마 주입)은 `docs/issue/backend/2026-07-23.md`, `docs/backlog/issue-2026-07-25.md`의 `AI/Pipeline — 활성 wiki-schema를 agent turn에 주입`, `docs/issue/frontend/2026-07-23.md`(항목 10)를 참조한다.

### refactor: `_lib` God 파일을 도메인 모듈로 분할

**변경된 내용**

- `_lib/api.ts`(443줄)를 도메인별 파일(`api/client·auth·workspace·chat·document·note·wiki·agent·export.ts`)로 분리하고, 기존 `_lib/api` import 경로는 배럴(re-export)로 유지했다.
- `_lib/types.ts`(282줄)를 `types/tree·auth·workspace·document·wiki·chat.ts`로, `_lib/tree.ts`(369줄)를 `tree/guards·queries·mutations·sync.ts`로 분리하고 각각 배럴로 유지했다.
- 코드 로직 변경 없는 순수 이동이며, importer(api 19·types 35·tree 10) 파일은 수정하지 않았다.
- 목적: 여러 프론트 기능을 병렬 개발할 때 한 파일에 집중되던 merge conflict를 줄이고, 도메인별 코드 탐색을 쉽게 한다.

**검증**

- `npm exec tsc -- --noEmit`, `npm run lint`, `npm run test:markdown`(46건), `npm run build` 통과.

**참고**

- `markdownAgent.ts` 분할은 raw-node `--experimental-strip-types` 유닛테스트와 tsc(bundler) 확장자 요구가 충돌해 단일 파일로 유지했다.
- 계획 문서: `docs/issue/frontend/2026-07-23-parallel-dev-refactor.md`.

### feat: Markdown 문서 편집 경험 개선

**변경된 내용**

- Markdown 문서를 Milkdown 기반 WYSIWYG 편집기로 열고 옵션 메뉴에서 Markdown 원문 편집 모드로 전환할 수 있게 했다.
- 문서 제목을 확장자 없이 편집하고 기존 `.md` 또는 `.markdown` 확장자를 유지한 채 Backend rename API에 반영한다.
- 자동 저장 상태와 충돌·실패를 문서 상단에 표시하고, 수정 또는 AI 점검 대기 상태를 사이드바 문서 행에 표시한다.
- 저장이 완료된 변경 문서만 AI 문서 점검을 요청할 수 있도록 편집 상태와 Agent context를 연결했다.
- Agent 입력창과 문서 미리보기 레이아웃을 새 편집 흐름에 맞게 보정했다.

**검증 결과**

- `npm run lint`, `npm exec tsc -- --noEmit`, `npm run build` 통과.
- `npm run test:markdown` 46건 통과.

**남은 주의사항**

- Backend는 업로드 직후 pipeline을 자동 실행하므로 수동·일괄 Ingest UI는 포함하지 않았다.
- 업로드와 Ingest 분리 및 편집 Markdown 재처리는 `docs/issue/backend/2026-07-23.md`의 `4. 문서 업로드와 Ingest 분리 및 편집 Markdown 재처리`에 남겼다.

## 2026-07-22

### fix: 인증 route 분리와 이메일 검증 API 연결

**변경된 내용**

- query 기반 인증 화면을 `/login`, `/signup`, `/signup/verify`, `/forgot-password`, `/reset-password` route로 분리했다.
- 회원가입을 인증번호 발급 → 번호 확인 → `verification_token` 포함 가입 → 로그인 순서로 연결하고, 닉네임을 `display_name`으로 전달한다.
- 비밀번호 재설정을 인증번호 발급·확인 후 1회용 token으로 변경하도록 연결했다.
- 개발 환경에서는 인증번호 `9700` 입력을 감지해 확인 버튼 없이 검증 API를 호출한다. production build에서는 자동 감지를 비활성화한다.
- 비밀번호와 인증 token은 URL이나 브라우저 저장소에 남기지 않고 인증 route 공통 layout의 메모리 상태로만 전달한다.
- 기존 `/login?view=...` 주소는 대응하는 새 route로 이동해 이전 링크와의 호환성을 유지한다.

**검증 결과**

- ESLint, `npx tsc --noEmit --incremental false`, `npm run build`, `npm run test:markdown` 45건 통과.
- Playwright API mock으로 회원가입 발급·`9700` 자동 검증·가입·로그인 요청 순서와 독립 route 이동을 확인했다.

### feat: Figma 기준 문서 탐색·편집·채팅 연동 개선

**변경된 내용**

- 왼쪽 사이드바를 항상 유지하고 프로젝트·폴더·노트의 폰트와 행 배치, 아이콘, hover, 생성 메뉴를 Figma 기준으로 정리했다.
- 프로젝트 사이에서 문서와 하위 폴더를 이동할 수 있게 하고, 프로젝트 헤더 drop line과 workspace별 `localStorage` 임시 트리 복원을 추가했다.
- 최초 진입과 홈 재선택 시 사이드바의 첫 번째 노트를 자동으로 열고, 업로드 중 이동한 문서도 실제 업로드 응답으로 올바르게 갱신한다.
- Markdown 문서는 미리보기로 열고 `편집`을 선택해야 CodeMirror로 전환한다. 편집 전후 내용이 다르고 자동 저장이 끝난 경우에만 문서 전체 `Lint 요청`을 Agent로 전달한다.
- 채팅 제목을 클릭하면 Figma `513:11045` 기준 검색·세션 드롭다운이 열리며, 활성 세션과 일반 세션 아이콘을 구분한다.
- `채팅을 문서로 편입` 미리보기·수락 버튼을 기존 Backend/AI chat export 흐름에 연결하고 완료 후 문서·Wiki 데이터를 새로고침한다.
- 브라우저 검증 중 발견된 편집 툴바와 문서 편입 확인 카드의 pointer layer 충돌을 수정했다.

**검증 결과**

- ESLint, `npx tsc --noEmit`, `npm run test:markdown` 45건 통과.
- Playwright API mock으로 기본 미리보기 → 편집·저장 → Lint diff 검토, 채팅 세션 드롭다운, 채팅 문서 편입 수락·완료 흐름을 확인했다.

**남은 주의사항**

- 폴더 트리는 Backend API가 없어 현재 workspace별 `localStorage`에 임시 저장한다. production 영속화 작업은 `docs/issue/backend/2026-07-22.md`에 유지한다.

### fix: 노트 편집기 컨텍스트 발행과 draft 조회 최적화

**변경된 내용**

- `NoteEditor`가 키 입력·selection마다 `useEffect`와 `onUpdate` 두 경로로 편집 컨텍스트를 중복 발행하던 것을 `onUpdate` 한 경로로 정리해 입력당 상위 리렌더를 1회로 줄였다.
- 저장 완료로 `baseVersion`(content_version)이 바뀔 때만 컨텍스트를 재발행하도록 남겨 baseVersion 정확성을 유지했다.
- `SourcePreviewPanel`이 Markdown 파일을 열 때 원본을 먼저 읽어 note marker를 확인하고, marker가 없는 일반 Markdown은 draft를 조회하지 않아 불필요한 404 요청을 제거했다.

**검증 결과**

- `npm run lint`, `npx tsc --noEmit`, `npm run test:markdown` 45건 통과.

## 2026-07-21

### feat: Figma 기준 Markdown 편집 화면 개편

**변경된 내용**

- Figma `512:10833`을 기준으로 문서 진입 시 사이드바와 Agent panel을 접고, 48px breadcrumb GNB와 900px 문서 본문을 사용하는 전체 화면 편집 레이아웃으로 변경했다.
- 실제 상위 폴더명과 마지막 편집일을 표시하고, 상단 동작 버튼으로 AI 편집 도우미를 다시 열 수 있게 했다.
- AI 편집 결과는 우하단 320px 수락/취소 카드로 표시하고, 본문을 펼치면 line diff, 렌더링 preview와 재생성을 확인할 수 있게 했다.
- `fruition-note`뿐 아니라 Backend가 생성하는 `fruition-workspace` marker도 편집 본문에서 분리해 CodeMirror 편집기로 연다.
- 720px 이하에서는 편집 여백과 제목 크기를 줄이고 AI 검토 카드를 화면 좌우 16px에 맞춘다.

**검증 결과**

- Playwright로 1024×1080과 390×844 viewport, AI 검토 카드의 축약·상세·취소 상태를 확인했다.
- `npm run lint`, `npx tsc --noEmit`, `npm run test:markdown` 45건 통과.
- Spring Agent endpoint가 아직 없어 AI 검토 상태는 network mock으로 검증했다.

### feat: Markdown AI 편집 검토와 안전 적용 완성

**변경된 내용**

- `markdown_edit` 응답의 document, base version, operation과 target을 요청 snapshot과 검증한 뒤 line diff와 렌더링 preview를 표시한다.
- Apply 직전에 현재 editor Markdown을 요청 원문과 다시 비교하고, 일치할 때만 buffer를 한 번 교체한 뒤 기존 autosave에 전달한다.
- 취소와 최신 snapshot 기반 재생성을 지원하며, 요청 후 사용자가 문서를 수정한 stale 결과는 적용하지 않는다.
- `markdown_create` 결과를 preview한 뒤 editable Markdown 파일로 저장하고 새 문서로 연다.
- 요약, 번역, 문체 변경, Markdown 정리, 표, checklist, 회의록 replacement fixture를 추가했다.

**검증 결과**

- `npm run test:markdown` 42건, `npm run lint`, `npm run build` 통과.

### feat: Markdown Agent turn 요청 연결

**변경된 내용**

- Agent panel에서 편집 중인 Markdown context가 있으면 기존 Wiki query 대신 `POST /api/workspaces/{workspace_id}/agent/turn`을 호출한다.
- 요청 시점의 `documentId`, 최신 `baseVersion`, message, editor snapshot을 하나의 DTO로 고정한다.
- Agent 응답은 원문에 적용하지 않고 결과 요약만 표시하며, 400/422 detail message를 실패 안내에 사용한다.
- Spring backend endpoint는 아직 없으므로 실제 pipeline 연동은 backend 이슈로 유지한다.

**검증 결과**

- `npm run test:markdown` 29건, `npm run lint`, `npm run build` 통과.

### feat: Markdown editor AI 대상 snapshot 전달

**변경된 내용**

- CodeMirror의 현재 Markdown과 문자 selection을 AI 편집용 1-base inclusive line target으로 변환한다.
- selection이 없으면 cursor가 속한 ATX heading section을 계산하고, heading이 없으면 문서 전체를 대상으로 사용한다.
- code fence와 frontmatter 내부의 heading 표시는 section 경계에서 제외한다.
- editor snapshot을 `NoteEditor`에서 `HomeWorkspace`를 거쳐 Agent panel까지 전달하고 composer에서 활성 대상 범위를 안내한다.
- 실제 `/agent/turn` 호출과 diff 적용은 후속 원자 기능으로 유지한다.

**검증 결과**

- `npm run test:markdown` 26건, `npm run lint`, `npm run build` 통과.

### fix: Markdown 제목과 code fence 경계 보존

**변경된 내용**

- H1부터 H6까지 각 ATX heading을 독립된 source block으로 식별한다.
- backtick과 tilde fence를 모두 지원하고, 닫힘 fence가 열림과 같은 문자이면서 같은 길이 이상일 때만 code block을 종료한다.
- 닫히지 않은 code fence는 임의의 닫힘 문법을 추가하지 않고 원문 그대로 보존한다.
- 제목과 code fence의 block 분할, 실제 HTML 렌더링과 source block ID를 검증하는 회귀 테스트 6건을 추가했다.

**검증 결과**

- `npm run test:markdown` 15건, `npm run lint`, `npm run build` 통과.

### fix: Markdown 문서 전체 참조 문맥 보존

**변경된 내용**

- Markdown segment별 개별 렌더링을 문서 전체 단일 parse 방식으로 변경해 footnote와 reference-style link의 reference/definition을 같은 문맥에서 처리한다.
- 원문 line 범위를 AST 출력에 매핑해 기존 `B0001` 형식의 source block ID와 citation highlight 동작을 유지한다.
- frontmatter는 기존 Metadata UI로 분리해 표시하되, 본문 line 위치가 바뀌지 않도록 빈 줄로 치환한 뒤 렌더링한다.
- footnote, reference-style link, frontmatter line 범위를 검증하는 회귀 테스트 3건을 추가했다.

**검증 결과**

- `npm run test:markdown` 9건, `npm run lint`, `npm run build` 통과.

### fix: 복합 Markdown 목록의 preview 문맥 보존

**변경된 내용**

- 목록 항목에 속한 code block, 인용문과 여러 줄 본문을 목록과 같은 Markdown segment로 유지한다.
- 목록 항목 사이의 빈 줄은 보존하되, 들여쓰지 않은 일반 문단에서는 목록 segment를 종료한다.
- 복합 목록과 목록 밖 문단 경계를 검증하는 회귀 테스트 3건을 추가했다.

**검증 결과**

- `npm run test:markdown` 6건, `npm run lint`, `npm run build` 통과.

### fix: 중첩 Markdown 목록 미리보기 구조 보존

**변경된 내용**

- Markdown block 분할 과정에서 목록 행의 leading whitespace를 제거하지 않도록 수정했다.
- 순서·비순서·체크리스트가 중첩된 목록을 하나의 parse context로 유지한다.
- 분할 로직을 순수 모듈로 분리하고 중첩 목록 회귀 테스트 3건을 추가했다.

**검증 결과**

- `npm run test:markdown`, `npm run lint`, `npm run build` 통과.
- 목록 안의 code block·인용문·여러 줄 본문 보존은 후속 작업으로 남아 있다.

### fix: Next.js 보안 패치와 React 19 적용

**변경된 내용**

- Next.js를 `14.2.35`에서 보안 패치가 포함된 `15.5.20`으로 올리고 `eslint-config-next` 버전을 맞췄다.
- React와 React DOM을 `19.2.7`, 타입 패키지를 React 19 계열로 갱신했다.
- Next.js가 사용하는 PostCSS를 `8.5.10`으로 override해 기존 XSS advisory를 제거했다.
- React 19의 nullable ref 타입에 맞춰 문서 업로드 input ref prop 선언을 보정했다.

**검증 결과**

- `npm audit`, `npm audit --omit=dev` 모두 취약점 0건.
- `npm run lint`, `npm run build` 통과.
- 브라우저에서 로그인, backend rewrite, 이미지 화면, Markdown 자동 저장·복원, LaTeX 미리보기를 확인했다.
- `next lint`는 Next 15에서 동작하지만 Next 16에서 제거될 예정이므로 추후 ESLint CLI 전환이 필요하다.

### feat: 새 노트용 Markdown 편집기 프로토타입 추가

**변경된 내용**

- `fruition-note` 식별 주석이 있는 새 노트만 CodeMirror 원문 편집기로 열고, 일반 Markdown·PDF·Wiki는 기존 읽기 전용 화면을 유지한다.
- Obsidian처럼 Markdown 문법을 직접 편집하고, Notion 문서 스타일의 미리보기로 전환할 수 있다.
- GFM과 LaTeX 미리보기를 지원하며 Notion database·property·board와 block 전용 UI는 포함하지 않는다.
- 마지막 입력 800ms 후 local mock API에 자동 저장하고 `편집됨`, `저장 중`, `저장됨`, `저장 실패`, `충돌` 상태를 표시한다.
- version 충돌 시 자동 재시도를 중단하고 현재 editor buffer를 유지한다.

**검증 및 주의사항**

- `npm run build` 통과.
- editor와 저장 사이에 block 변환을 두지 않아 Markdown 원문을 그대로 유지한다.
- 저장은 local profile의 메모리 mock이며 backend 재시작 시 사라진다. production 저장 후속 작업은 `docs/issue/backend/2026-07-21.md`에 남겨두었다.

### fix: 사이드바 메뉴 hover 박스 제거

- 홈·그래프·규칙·로그·설정 및 프로젝트 추가 버튼의 hover 배경을 제거했다.
- hover에서는 아이콘 색상만 변경하고, 현재 선택된 메뉴의 pill 배경과 키보드 `focus-visible` outline은 유지한다.
- `npm run build` 통과.

### fix: 폴더 행 정렬을 업로드 문서와 통일

- 폴더의 글꼴·행 높이·패딩은 기존 업로드 문서와 동일한 `.tree-row` 스타일을 유지했다.
- 폴더 앞에 업로드 문서 아이콘과 같은 `18px` 공간을 확보하고, 자식이 있을 때만 중앙에 펼침 화살표를 표시한다.
- 빈 폴더에는 박스 아이콘을 표시하지 않으면서 문서명과 폴더명의 시작 위치를 맞췄다.
- `npm run build` 통과.

### feat: 사이드바 새 노트 생성 기능 추가

**변경된 내용**

- 프로젝트·폴더 우클릭 메뉴를 `새 폴더`, `새 노트`, `이름 변경`, `삭제` 순서로 정리했다.
- `새 노트` 선택 시 고유 식별 주석과 `# 새 문서` 제목을 가진 `새 문서.md`를 생성해 기존 문서 업로드 API로 저장한다.
- 폴더에서 생성한 노트는 해당 폴더 아래에 배치하고, 프로젝트·파일에서 생성하면 프로젝트 루트에 배치한다.

**검증 및 주의사항**

- `npm run build` 통과.
- 노트 본문을 다시 저장하는 API는 아직 없어 편집기 연동은 후속 backend 계약이 필요하다. `docs/issue/backend/2026-07-21.md`의 `2. 노트 본문 저장 API 부재`에 기록했다.

### fix: 인증 정보 URL 노출과 중복 이메일 가입 흐름 교정

**배경**

- 인증 폼이 React handler 연결 전에 기본 `GET`으로 제출되면 이메일과 비밀번호가 URL query에 노출될 수 있었다.
- 회원가입 `인증 요청`은 서버 중복 검사 없이 인증 화면으로 이동해, 이미 가입된 이메일도 다음 단계로 진입했다.

**변경된 내용**

- 모든 인증 폼에 `method="post"`를 명시해 기본 제출에서도 자격 증명이 URL에 붙지 않도록 했다.
- `인증 요청` 시 `POST /api/auth/signup` 응답을 먼저 확인하고, 성공한 경우에만 인증 화면으로 이동한다. `409 DUPLICATE_EMAIL`은 현재 화면에 오류로 표시한다.
- 임시 인증번호 통과 후에는 중복 `signup` 호출 없이 로그인만 수행한다.

**검증 및 주의사항**

- 브라우저에서 로그인 실패 후 URL이 `/login`으로 유지되고, 중복 이메일 인증 요청이 `?view=signup`에 머물며 오류를 표시하는 것을 확인했다.
- `npm run lint`, `npx tsc --noEmit --incremental false`, `npm run build` 통과.
- 실제 이메일 인증 API가 없어 인증 요청 시 계정이 먼저 생성되는 임시 우회다. 후속 backend 계약과 완료 조건은 `docs/issue/backend/2026-07-21.md`에 기록했다.

### fix: 채팅 위키 내보내기 selection_mode 값 교정 및 워크스페이스 이름 중복 조회 제거

**배경**

- PR #89 코드리뷰 지적: `exportChatWiki`가 `selection_mode: "all"`을 보내는데 백엔드는 `full`/`partial`만 허용하고 그 외 값은 400으로 거부해, 채팅 위키 내보내기가 항상 실패했다.
- `useWorkspaceName`이 `AgentHeader`와 `SidebarWorkspaceHeader`에서 각각 호출되어 홈 진입 시 `GET /api/workspaces`가 중복 호출됐다.

**변경된 내용**

- `api.ts` — `exportChatWiki` 요청 body의 `selection_mode`를 `"all"`에서 `"full"`(세션 전체)로 교정. `pair_ids: []`는 full에서 무시된다.
- `useWorkspaceName.ts` — 진행 중인 `fetchWorkspaces` Promise를 모듈 스코프에서 공유해 이름 조회의 중복 호출을 제거. 워크스페이스 전환·생성은 전체 페이지 리로드를 하므로 캐시는 자연히 초기화된다.

**검증**

- `tsc --noEmit` 통과.

## 2026-07-20

### feat: 프로젝트 관리와 그래프 사이드바 사용성 개선

**변경 배경**

- 프로젝트는 추가만 가능하고 삭제할 수 없었으며, 프로젝트가 하나여도 파일 드롭 영역이 프로젝트 섹션으로 제한되어 있었다.
- 그래프 상단의 임시 breadcrumb 문구와 Agent 패널 축소 시 오른쪽에 붙는 복원 버튼을 정리할 필요가 있었다.

**변경된 내용**

- 프로젝트 우클릭 메뉴에서 프로젝트를 삭제할 수 있도록 로컬 프로젝트 상태 삭제를 연결했다.
- 프로젝트가 하나면 왼쪽 사이드바 전체를 해당 프로젝트의 파일 드롭 영역으로 사용하도록 변경했다.
- 그래프 왼쪽 상단 breadcrumb를 제거하고, Agent 패널 축소 상태의 복원 버튼에 오른쪽 여백 `20px`를 적용했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.
- `npm run build` 통과.

### feat: 문서 삭제·이름 변경을 백엔드 API에 연결

- 기존에는 사이드바 트리의 문서 삭제/이름 변경이 로컬 React 상태만 바꾸고 서버에 반영되지 않아 새로고침 시 원복되던 문제 수정
- `api.ts`에 `deleteDocument`(`DELETE /api/workspaces/{workspace_id}/documents/{document_id}`), `renameDocument`(`PATCH .../documents/{document_id}/rename`) 추가
- `useProjectTree`의 `deleteContextTarget`·`commitEditing`에서 대상 트리 아이템에 `documentId`가 있으면 실제 문서로 간주해 API를 호출하도록 배선
- 성공·실패 모두 `refreshBackendData`로 서버 상태와 재동기화. 삭제 실패 시 문서가 트리에 다시 나타나고, 이름 변경 실패 시 이전 이름으로 원복
- `useProjectTree`가 `useBackendData`보다 먼저 생성되는 순서 문제로 `refreshBackendData`는 `refreshRef`(ref)로 주입
- 빈 문서 생성은 백엔드에 대응 endpoint가 없어 미구현. 백엔드 이슈로 기록: `docs/issue/backend/2026-07-20.md` 이슈 1

## 2026-07-20

### feat: 홈/그래프 화면 분리 및 워크스페이스·문서 추가 hover 인터랙션 (Figma 426:2115 / 500:6597 / 500:6692)

**변경 배경**

- 메인(홈) 화면이 항상 그래프를 렌더해 그래프 메뉴가 무의미했다. Figma 시안 기준으로 홈은 Obsidian처럼 최근 문서를 열람하는 화면, 그래프는 메뉴 선택 시에만 보이도록 분리한다.
- 워크스페이스 전환과 채팅 세션 선택, 문서 추가(+) 진입점을 hover 인터랙션으로 시안(500:6597 / 513:11057 / 500:6692)에 맞춘다.

**추가/변경된 내용**

- `HomeWorkspace.tsx`: `<Graph>`를 `activeView === "graph"`일 때만 렌더. 홈 진입 시 `uploaded_at` 최신 문서를 자동 선택해 문서 뷰로 여는 로직 추가(최초 1회, 기존 선택/해제 시 유지). 홈=문서 뷰(문서 없으면 빈 화면), 그래프=그래프, 나머지 메뉴=빈 화면. Agent 패널은 홈·그래프 양쪽 유지. 문서 메인 상태에 `is-document-main` 클래스 부여.
- `SourcePreviewPanel.tsx`: `fillMain` prop 추가. 홈 메인 문서 뷰에서 고정폭/리사이즈 대신 사이드바~Agent 패널 사이 영역을 채운다.
- `source-preview.css`: `.source-preview-panel.is-main` 영역 채움 규칙(에이전트 접힘 대응).
- `SidebarWorkspaceHeader.tsx` + `chrome.css`: 워크스페이스 헤더 hover 드롭다운. 항목 클릭 시 `setSelectedWorkspaceId` 후 새로고침으로 전환, "새 워크스페이스"는 `createWorkspace` 후 전환.
- `AgentHeader.tsx` + `agent-panel/shell.css`: 채팅 세션 드롭다운을 hover로 열고 시안 513:11057 스타일로 보정.
- `project-section.css`: 첫 프로젝트 헤더의 + 버튼을 라운드 박스 안에 배치하고, 폴더 행 hover/focus 시에만 나타나도록 변경.

**검증 결과**

- `tsc --noEmit` 통과.
- 브라우저에서 홈→빈 화면(문서 0건), 그래프 메뉴→`.graph-stage` 렌더, 워크스페이스/채팅 hover 드롭다운, +버튼 hover 표시를 확인했다.

**주의사항**

- 최근 문서 자동 열람과 `is-main` 영역 채움 레이아웃은 로그인+문서 보유 상태에서의 실물 확인이 남아 있다(검증 세션이 로그아웃/문서 0건 상태였음).

### feat: Figma 시안 기반 메인 화면 개편 (사이드바/프로필/채팅 패널) 및 모달 2종 추가

**변경 배경**

- Figma 시안(426:2115, 512:10781) 기준으로 메인 화면의 사이드바, 프로필, 채팅 패널 구조가 변경되어 프론트엔드를 맞췄다.
- 미지원 파일 업로드 시 아무 피드백 없이 무시되던 문제와, 채팅 내용을 위키 문서로 내보내는 흐름의 UI가 없던 문제를 함께 해결했다.

**추가/변경된 내용**

- 사이드바 개편: 워크스페이스 헤더(아바타+이름), 가로 아이콘 메뉴 줄(기존 RailNavigation 대체), 파일 트리 타입 배지(PDF/MD/TXT)와 "Modify" 상태 태그, "채팅 시작" 버튼, 프로필 푸터(display_name/온라인/로그아웃) 추가. 기존 TopBar 렌더 제거.
- 사이드바 메뉴바를 시안(404:5256)에 맞춰 보정: 두 번째 항목을 "공유"에서 "그래프"로 변경(`RailView` id `share`→`graph`), 메뉴 버튼을 캡슐형(pill) 라운드로 조정.
- 채팅 패널 개편: 우측 풀하이트 360px 컬럼, 세션 제목 헤더 + "채팅 검색" 세션 드롭다운(`GET /api/workspaces/{id}/chat/sessions`), 답변 작성 중 점 애니메이션, 컴포저 재작성([+]/[↑] 버튼).
- 업로드 에러 모달: 미지원 파일 드롭/선택 시 "지원하지 않는 파일입니다" 모달 표시. 지원 확장자에 `.txt` 추가.
- 위키 내보내기 확인 팝업: `POST …/wiki/preview` 미리보기 → 수락 시 `POST …/wiki` 호출하는 취소/수락 카드와 트리거 버튼 추가.
- wiki API 경로 버그 수정: `/api/wiki/graph`, `/api/wiki/pages/{id}` → workspace 스코프 경로로 교체(404 해소).
- 신규 API 함수: `fetchMe`, `fetchChatSessions`, `fetchChatWikiExportPreview`, `exportChatWiki`.

**검증 결과 / 남은 주의사항**

- `tsc --noEmit`, `eslint` 통과. 브라우저에서 업로드 에러 모달 표시/닫힘, 세션 드롭다운 열림/필터, 메인 레이아웃 렌더 확인.
- 위키 내보내기 수락 흐름은 어시스턴트 답변이 있어야 노출되어 LLM 질의 포함 E2E는 미수행.
- TopBar.tsx와 workspace.css의 구 topbar 스타일은 미사용 상태로 보존됨.

## 2026-07-17

### feat: 로그인/회원가입 화면 개편 및 소셜 로그인 UI 추가

**변경 배경**

- 임시 로그인 화면을 정식 디자인 기반의 인증 플로우(로그인, 회원가입, 인증번호 확인, 비밀번호 찾기/재설정)로 개편했다.
- Google/Naver/Kakao 소셜 로그인 진입 UI와 OAuth code 교환 흐름이 필요했다.

**추가 및 변경된 내용**

- `frontend/app/login/page.tsx`를 `view` query param 기반 다중 화면(login, signup, signup-verification, forgot-password, reset-password)으로 개편했다.
- `frontend/app/login/AuthControls.tsx`에 `AuthField`, `AuthError`, `AuthSubmitButton`, `SocialLoginButtons` 컴포넌트를 추가했다.
- `frontend/app/login/useVerificationRequest.ts`에 인증 요청 타이머(5분)와 로컬 임시 인증 코드 판정 훅을 추가했다.
- `frontend/app/_lib/api.ts`에 `OAuthProvider` 타입, `getOAuthAuthorizationUrl`, `exchangeOAuthCode`(POST `/api/auth/oauth/exchange`)를 추가했다.
- `frontend/app/workspaces/page.tsx`를 워크스페이스 선택 화면에서 첫 워크스페이스 자동 선택(없으면 `나의 워크스페이스` 자동 생성) 후 홈으로 이동하는 흐름으로 변경했다.
- `frontend/svg/`에 소셜 로고(google, naver, kakao)와 인증 화면용 아이콘(error-circle, password-hidden)을 추가하고 `frontend/app/_styles/auth.css`를 새 디자인에 맞게 갱신했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.

**주의사항**

- 인증번호는 백엔드 연동 전으로, 개발 환경에서만 임시 코드 `9700`으로 통과한다 (`NODE_ENV !== "production"` 조건).
- 소셜 로그인은 백엔드 `/oauth2/authorization/{provider}` 및 `/api/auth/oauth/exchange` 구현이 필요하다.

---

## 2026-07-05

### feat: 로그인/워크스페이스 플로우 추가 및 프론트 데이터 계층 개편

**변경 배경**

- 백엔드 인증/워크스페이스 API 계약에 맞춘 임시 로그인·워크스페이스 선택 흐름이 필요했다.
- 수동 fetch 상태 관리, 자체 물리엔진, 수제 마크다운 파서를 검증된 라이브러리(React Query, d3-force, react-markdown)로 교체했다.

**추가 및 변경된 내용**

- `/login`, `/workspaces` 페이지와 `_lib/auth.ts` 토큰/워크스페이스 저장 헬퍼 추가 (임시 UI, Figma 시안 도입 시 교체 대상). `page.tsx`에 토큰/워크스페이스 가드 추가.
- `providers.tsx`에 React Query Provider 구성, `useBackendData`를 `useQuery` 기반으로 전환 (processing/uploaded 문서가 있을 때만 3초 폴링, `refetchOnWindowFocus` 비활성).
- `api.ts`: Bearer 토큰을 부착하는 `apiFetch`, 워크스페이스 스코프 endpoint, chat session 캐시와 `clearSessionCache()` 추가. 에러 처리를 `parseJsonOrThrow`로 통일해 백엔드 에러 메시지를 보존.
- graph 물리엔진을 d3-force로 교체하고 wheel 줌/드래그 pan/터치 핀치를 d3-zoom으로 전환.
- `MarkdownViewer`를 react-markdown + remark-gfm 기반으로 재구성, wikilink(`[[...]]`)/citation(`[1,2]`) 커스텀 remark 플러그인 추가.
- 코드 리뷰 반영: `scheduleGraphCacheWrite` 안정 참조화(RAF 루프 재시작·캐시 서명 stale 버그 수정), signup/login 에러 메시지 분리, workspaces fetch cleanup, remark 플러그인 mdast 타입 적용, 미사용 `graphNodeKind` 제거.

**검증 결과**

- `npx tsc --noEmit`, `npm run lint`, `npm run build` 통과.
- 코드 리뷰(보안/graph/api 3개 관점) 지적 사항 HIGH·MEDIUM 반영 완료.

**주의사항**

- 토큰을 localStorage에 저장한다(XSS 시 탈취 가능한 알려진 트레이드오프). 정식 도입 시 httpOnly 쿠키 전환 필요.
- refresh token 갱신 흐름 미구현 — access token 만료 시 재로그인이 필요하다.

## 2026-07-04

### refactor: graph 캔버스 모듈 정리

**변경 배경**

- `graphPhysics`에 모든 분기가 14를 반환하는 dead if-체인이 있었고, link마다 `nodes.find()`를 도는 O(L×N) 탐색이 있었다.
- `useGraphCanvas`가 초기화 시 localStorage cache를 3회 파싱했고, render 중 ref 할당(side-effect)이 있었다.

**변경된 내용**

- `graphPhysics`: `FIXED_NODE_SIZE` 단일 상수화, node Map 1회 생성으로 O(1) 조회 전환, `PAIR_DISTANCE` 상수 추출.
- `graphGeometry`: 거리 영향도 if-체인을 `DISTANCE_INFLUENCE` lookup 배열로 교체(값 동일).
- `graphCache`: `JSON.parse` 결과를 `unknown`으로 받아 기존 필드 검사로 좁히도록 변경.
- `useGraphCanvas`: cache 1회 읽기로 통합, render 중 ref 할당을 `useLayoutEffect`로 이동, 무의미한 `clampZoom` wrapper 제거, layout 버전 문자열 상수화.
- `useGraphPointer`: 버튼 마스크 상수화, 드래그 ref 2개를 단일 `nodeDragRef`로 병합, `startPanning`→`handlePointerDown` rename.
- `graphDrawing`: DPR resize를 `ensureCanvasSize`로, hover 연산을 `computeLinkedHoverAmounts`로 추출, Figma 유래 marker 수치 상수화, gradient 색상을 `hexToRgb(GRAPH_COLORS.hoverNode)`로 파생.
- `useGraphAnimation`: 프레임/tick 매직 넘버 상수화.

**검증 결과**

- `npx tsc --noEmit`, `npm run lint`, `npm run build` 통과.

### refactor: document-sidebar와 _hooks 정리

**변경 배경**

- `onSelectGraphNode` 인자 타입이 두 파일에 인라인으로 복제되어 있었고, drag/drop 판정 로직과 매직 넘버가 중복·산재했다.
- `useTreeSelection`의 연동 state 4개가 별개 useState로 관리되어 항상 함께 갱신되는 관계가 코드에 드러나지 않았다.

**변경된 내용**

- `types.ts`에 `SelectableTreeItem` 타입 추출, `DocumentSidebar` 인라인 타입 교체.
- `dragDrop.ts` drop 임계값(0.28/0.72)·offscreen 좌표 상수화, `TreeNode` 들여쓰기 상수화.
- `useTreeNodeDragDrop`의 중복 wiki 드롭 판정을 `resolveWikiDropTarget` 헬퍼로 통합.
- `ProjectSection` className을 `cx()` 헬퍼로 통일.
- `useProjectTree` 반환 객체의 인라인 화살표 함수 5개를 명명 함수로 전환, 변수명 일관화.
- `useTreeSelection` state 4개를 단일 객체 state로 병합(반환 API 동일).
- `useDocumentUpload` ref 타입 정리, 병렬 배열 인덱스 패턴을 쌍(zip) 기반 반복으로 교체.

**검증 결과**

- `npx tsc --noEmit`, `npm run lint`, `npm run build` 통과.

### refactor: agent-panel과 루트 컴포넌트 정리

**변경 배경**

- `AgentBody` 내부에 55줄 인라인 렌더 함수와 순수 헬퍼 4개가 컴포넌트 안에 섞여 있었고, `MarkdownViewer`는 100줄 파싱 루프가 컴포넌트 본문에서 실행됐다.
- `SvgIcon`에 가짜 `as StaticImageData` cast, `SourcePreviewPanel`에 dead 별칭 변수, `useSmoothScroll`에 미사용 반환값이 있었고, `HomeWorkspace`의 resize 핸들러 4개가 로직을 중복했다.

**변경된 내용**

- `AgentBody`: answer 단계 상수화(`STAGE_*`), 순수 헬퍼 모듈 레벨 이동, `AssistantThread` 컴포넌트 분리, 중복 StatusList JSX 통합.
- `useChatThread`: `buildNextActiveTurn`/`toRelatedPageMessage` 순수 함수 추출.
- `MarkdownViewer`: 파싱 루프를 `parseMarkdownBlocks` 모듈 함수로 추출, `CITATION_COLOR_COUNT` 상수화.
- `SvgIcon`: 인라인 아이콘 3종을 renderer map으로 처리해 unsafe cast 제거.
- `HomeWorkspace`: resize 로직을 `useResizeHandle` 훅(신규 파일)으로 추출해 2회 인스턴스화.
- `useSmoothScroll` 미사용 `animationRef` 반환 제거, `SourcePreviewPanel` dead 변수 제거, `StatusList` button `type="button"` 명시, `AgentResultCard`/`agentFormatters` capitalize 중복 통합, `RailNavigation` 특수 케이스를 `isLarge` 데이터 필드로 전환.

**검증 결과**

- `npx tsc --noEmit`, `npm run lint`, `npm run build` 통과.

### refactor: _styles 색상 토큰화와 중복 규칙 통합

**변경 배경**

- `--yellow` 변수가 있음에도 `#ffc117` 리터럴이 8곳에 반복되었고, `#8a8a8a`/`#3a3a3a`는 변수 없이 산재했다.
- 동일한 스크롤바 스타일 블록이 3개 파일에 복붙되어 있었고, `--dark` dead 변수와 no-op override 규칙이 남아 있었다.

**변경된 내용**

- `base.css`에 `--subdued`(#8a8a8a), `--line-soft`(#3a3a3a) 토큰 추가, 미사용 `--dark` 제거.
- `#ffc117`→`var(--yellow)`, `#8a8a8a`→`var(--subdued)`, `#3a3a3a`→`var(--line-soft)` 전면 교체.
- `.agent-body`/`.sidebar-content`/`.source-preview-content` 스크롤바 규칙을 `base.css` 공통 블록으로 통합.
- `results.css`의 no-op `.result-card b.raw/.source/.concept` override 제거.
- 렌더 결과 변화 없음(값 동일).

**검증 결과**

- 하드코딩 색상 잔여 없음(grep 확인), `npx tsc --noEmit` 통과.

### refactor: _lib 모듈 dead code 제거와 중복 통합

**변경 배경**

- `_lib/tree.ts`에 호출처가 없는 `buildWikiTreeGroups`(57줄)가 남아 있었고, 동일한 재귀 트리 순회 패턴이 5개 함수에 반복되어 있었다.
- `graph.ts`에 `NODE_PREFIX` 상수가 있음에도 `"raw:"`, `"source:"` 리터럴이 인라인으로 흩어져 있었고, `api.ts`의 에러 메시지 일부가 `ERROR_MESSAGES` 상수를 거치지 않았다.

**변경된 내용**

- `tree.ts`: dead 함수 `buildWikiTreeGroups` 삭제, 재귀 순회를 `mapTreeItemById` 헬퍼로 통합, wiki 그룹 ID를 상수로 추출, `raw:` 리터럴을 `makeRawId`로 대체.
- `graph.ts`: `makeRawId` 헬퍼 추가, `buildGraphFromBackend` 내부 리터럴을 `NODE_PREFIX`/`makeSourceId`/`makeRawId`로 통일.
- `api.ts`: `fetchBackendData`/`fetchWikiPage` 인라인 에러 문자열을 `ERROR_MESSAGES`로 이동, `fetchWikiPage`도 `parseErrorResponse`를 사용하도록 통일.
- `types.ts`: `QueryRelatedPageResponse`/`ChatMessageRelatedPageResponse` 공통 필드를 `RelatedPageBase`로 추출.
- 동작 변경 없음(순수 정리). export 시그니처는 `makeRawId` 추가 외 변화 없음.

**검증 결과**

- `npx tsc --noEmit` 통과.

## 2026-06-26

### fix: 원문 패널에서 자료관리 클릭 시 그래프 노드 선택 표시 해제

**변경 배경**

- 원문 미리보기가 열린 상태에서 그래프가 아닌 자료관리 영역을 클릭하면 `focusedGraphNodeId`는 해제되지만 그래프 내부 클릭 표시(`selectedNodeIdRef`)가 남아 노드가 계속 선택된 것처럼 보였다.

**변경된 내용**

- `useGraphCanvas`의 focus 동기화 effect가 `focusedNodeId`가 없거나 유효하지 않을 때 `setSelectedNode(null)`로 내부 클릭 표시도 해제하도록 수정했다(기존에는 focus 설정만 동기화).

**검증 결과**

- `npm run build`(타입체크 포함), `npm run lint` 통과.

### refactor: 프론트엔드 중복 로직 공통 유틸로 통합

**변경 배경**

- 동일한 로직(에러 메시지 추출, 조건부 className 합성, 그래프 색상/거리 계산, 드래그 leave 판정)이 여러 파일에 복붙되어 있어 재사용성과 일관성이 떨어졌다.

**변경된 내용**

- `_lib/errors.ts`의 `getErrorMessage`로 `error instanceof Error` 패턴 6곳을 통합했다.
- `_lib/classNames.ts`의 `cx`로 `filter(Boolean).join(" ")` className 합성 3곳을 통합했다.
- `AgentBody`에 섞여 있던 순수 포맷 함수 4개를 `agentFormatters.ts`로 추출했다.
- 그래프 색상 유틸(`hexToRgb`, `mixHexColor`)을 `graphColors.ts`로 모으고, `Math.hypot(dx, dy) || 0.01` 거리 계산을 `graphGeometry.safeDistance`로 통합했다.
- 드래그 leave 판정 중복을 `dragDrop.isPointerLeavingElement`로 통합했다.
- 동작 변경 없이 추출/이동만 수행했고, 구조 변경(Context 도입·훅 시그니처 재설계·타입 통합)은 범위에서 제외했다.

**검증 결과**

- `npm run build`(타입체크 포함), `npm run lint` 통과.

### feat: query citation 원문 block 하이라이트 개선

**변경 배경**

- query 답변의 `[n]` citation을 눌러 원문 근거를 확인할 때 markdown 원문이 일반 텍스트 block 목록처럼 표시되어 원문 구조를 보기 어려웠다.
- 여러 citation 근거를 확인할 때 번호별 구분이 어려웠고, 같은 원본 문서 안의 관련 근거를 한 번에 비교하기 어려웠다.

**변경된 내용**

- 원문 근거 확인 시 원본 markdown을 `MarkdownViewer`로 계속 렌더링하면서 해당 source block만 하이라이트하도록 변경했다.
- 답변 citation 버튼과 원문 block 하이라이트에 rank별 색상 팔레트를 적용했다.
- 한 문장에 `[1, 2]`처럼 여러 citation이 붙은 경우 각각 클릭 가능한 citation 버튼으로 렌더링한다.
- citation 클릭 시 같은 답변에서 같은 원본 문서에 속한 다른 근거 block도 함께 하이라이트해 `[1]`~`[5]` 근거를 색상으로 비교할 수 있게 했다.
- citation 클릭 시 실제 답변에 등장한 선택 rank만 원문 block 하이라이트에 사용하도록 제한했다.
- citation으로 원문을 열 때 자료 관리의 raw 원문 문서 row가 선택 표시되도록 했다.
- 자료 관리 트리에서 generated `Source 문서`/`Concept 문서` 그룹을 숨겼다.
- Figma `v1` title 노드 기준으로 자료 관리 header 상단 padding과 title 여백을 조정했다.
- graph 노드를 실제로 드래그한 뒤에는 클릭 선택 효과가 남지 않도록 했다.

**검증 결과**

- `npm run lint` 통과.

## 2026-06-20

### fix: 그래프 노드 선택 표시와 Markdown code block 여백 조정

**변경 배경**

- 그래프 노드를 드래그한 뒤 시간이 지나면 클릭/선택 이펙트가 사라져 현재 선택 상태를 구분하기 어려웠다.
- Markdown fenced code block의 텍스트가 검은색 블럭의 위쪽과 왼쪽에 너무 붙어 보여 가독성이 떨어졌다.

**변경된 내용**

- 그래프 canvas 내부의 hover 상태와 selected 상태를 분리해, 노드 클릭 또는 드래그 후 선택 마커가 유지되도록 조정했다.
- 외부 `focusedNodeId`가 `null`로 바뀌어도 그래프 내부 선택 상태를 강제로 지우지 않게 했다.
- Markdown code block의 내부 여백과 줄바꿈 스타일을 조정해 텍스트 시작 위치가 자연스럽게 보이도록 했다.
- Markdown code block 끝의 불필요한 빈 줄을 제거하고, 왼쪽 여백을 추가로 보정했다.
- Agent의 "찾은 자료" 카드를 `related_pages` 우선으로 렌더링하고, 현재 graph에 있는 page만 표시하도록 했다.
- 자료 관리 raw 문서 클릭과 graph raw 노드 더블 클릭이 같은 preview open 경로를 사용하도록 통합했다.
- 원본 문서 preview의 세로 스크롤바가 패널 오른쪽 테두리에 붙어 보이도록 조정했다.
- graph 노드 클릭 선택 이펙트가 hover 이펙트와 같은 렌더링 경로를 사용하도록 정리했다.

**검증 결과**

- `npm run lint` 통과.
- `npm run build` 통과.
- `.next` 캐시 삭제 후 `npm run dev`로 `http://localhost:3001` 기동 확인.

## 2026-06-17

### fix: Agent 새 질문 기준 scroll 동작 조정

**변경 배경**

- 오른쪽 Agent 패널에서 새 질문을 보낼 때 답변 생성에 맞춰 화면이 계속 아래로 이동해 ChatGPT 웹의 질문 기준 응답 흐름과 다르게 보였다.

**변경된 내용**

- 질문 전송 직후 임시 질문 박스를 먼저 표시하고, 해당 질문이 패널 상단에서 약 20px 아래에 오도록 scroll 기준을 변경했다.
- 전송 중 질문과 서버 응답 후 assistant 메시지를 하나의 active turn으로 유지해 로딩 블록이 실제 응답 블록으로 교체되며 생기는 layout shift를 줄였다.
- 답변 생성 중에는 기존 상태 목록, 찾은 자료, 답변 본문 구조를 유지한 채 질문 아래 영역에 단계적으로 표시되도록 했다.
- 새 질문이 마지막 항목이어도 상단 정렬이 가능하도록 새 응답 턴 아래에 임시 scroll 여유 공간을 추가하고, 답변 본문 노출 후에는 제거되도록 했다.
- 답변 완료 시 임시 여백 제거로 scroll 높이가 줄어들어도 질문 박스 기준 위치를 paint 전에 다시 보정하도록 했다.
- 서버 응답 후에는 임시 질문을 실제 채팅 기록의 질문으로 교체하고, 새 assistant 응답 animation도 해당 질문 기준 위치를 유지하도록 했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.
- `http://localhost:3001` 응답 `200 OK` 확인.

### fix: 접힌 Agent 패널 복원 버튼을 graph legend에 통합

**변경 배경**

- 오른쪽 Agent 패널을 접었을 때 복원 버튼이 graph filter chip과 분리되어 Figma `v1`의 축소 sidebar legend 구조와 달랐다.

**변경된 내용**

- Agent 패널이 접힌 상태에서는 `원본 raw`, `source page`, `concept page` chip 뒤에 패널 복원 아이콘 버튼이 같은 legend 그룹으로 표시되도록 변경했다.
- graph filter chip과 복원 아이콘 버튼의 간격, 크기, dark theme 색상을 Figma 구조에 맞춰 보정했다.

**검증 결과**

- `npm run lint` 통과.
- `http://localhost:3000` 응답 `200 OK` 확인.

### fix: 자료관리 프로젝트 추가 버튼 동작 수정

**변경 배경**

- 자료관리 header 오른쪽 버튼이 새 프로젝트를 추가하지 않고 첫 번째 프로젝트의 문서 업로드 picker를 열고 있었다.
- 자료관리 목록에 세로 scrollbar가 생길 때 tree 항목 위치가 흔들릴 수 있었다.

**변경된 내용**

- 자료관리 header 오른쪽 버튼을 새 프로젝트 추가 동작에 연결했다.
- 새 프로젝트 추가 직후 프로젝트 이름 편집 상태로 진입하도록 했다.
- 자료관리 scroll 영역에 scrollbar gutter를 예약해 scrollbar 표시 여부와 관계없이 기존 padding 위치가 유지되도록 했다.
- Agent 채팅 기록 최초 로딩 후 가장 최근 메시지가 보이도록 scroll 위치를 하단으로 맞췄다.
- Graph filter의 `source page` chip 아이콘을 `source_page.svg` 자산으로 변경했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.

### refactor: CSS 영역별 세부 파일 분리

**변경 배경**

- `document-sidebar`, `agent-panel`, `graph` CSS가 영역 단위 파일로는 여전히 커서 세부 컴포넌트별 스타일 위치를 찾기 어려웠다.
- Figma 기준 보정이 반복되는 영역을 shell, 상태, 결과, tree, node 등 실제 UI 역할 단위로 더 좁혀 관리할 필요가 있었다.

**변경된 내용**

- `frontend/app/_styles/document-sidebar/` 아래로 shell, project section, tree row, context menu 스타일을 분리했다.
- `frontend/app/_styles/agent-panel/` 아래로 shell, conversation, status, answer, results, composer 스타일을 분리했다.
- `frontend/app/_styles/graph/` 아래로 stage, filters, lines, nodes 스타일을 분리했다.
- dark override도 요청 범위에 맞춰 `dark/document-sidebar/`, `dark/agent-panel/`, `dark/graph/` 하위 파일로 세분화했다.
- 기존 `document-sidebar.css`, `agent-panel.css`, `graph.css`와 dark entry 파일은 import entry로 유지해 cascade 순서를 보존했다.

**검증 결과**

- 분리된 CSS 파일을 순서대로 합친 결과가 직전 entry 파일 내용과 동일함을 확인했다.
- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.
- `http://localhost:3000` 응답 `200 OK` 확인.

### refactor: CSS 파일 구조 분리

**변경 배경**

- `frontend/app/globals.css` 한 파일에 base, workspace, sidebar, graph, Agent panel, dark override 스타일이 모두 들어 있어 Figma 보정 시 변경 범위를 파악하기 어려웠다.

**변경된 내용**

- 전역 CSS entry를 `frontend/app/_styles/globals.css`로 이동하고, `layout.tsx`의 import 경로를 갱신했다.
- 기존 CSS 내용을 base/workspace/rail/document-sidebar/graph/agent-panel/responsive 영역과 dark override 영역으로 분리했다.
- 분리 과정에서 기존 cascade 순서와 CSS 내용을 유지하도록 파일 import 순서를 구성했다.

**검증 결과**

- 분리된 CSS 파일을 순서대로 합친 결과가 기존 `frontend/app/globals.css`와 동일함을 확인했다.
- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.
- `http://localhost:3000` 응답 `200 OK` 확인.

### fix: Agent 패널 Figma 보정과 sidebar tree 안정화

**변경 배경**

- backend polling 시 sidebar tree가 실제 데이터 변경 없이도 새 객체로 교체되어 채팅 답변 표시와 겹칠 때 새로고침처럼 보일 수 있었다.
- Figma `v1`의 Agent 패널 node와 비교했을 때 결과 card badge 색상, body 상단 여백, 패널 하단 간격이 일부 어긋나 있었다.
- 자료 관리 header와 Agent sidebar의 접기/추가 아이콘이 Figma 기준보다 작게 표시됐다.
- 원본문서 preview 유무에 따라 자료 관리 sidebar와 원본문서 패널의 우상단 곡률과 border가 Figma 기준과 어긋나 있었다.

**변경된 내용**

- backend 데이터 merge 결과가 기존 sidebar tree와 같으면 기존 project/tree 참조를 유지하도록 비교 로직을 추가했다.
- Agent 패널의 body 상단 여백, 하단 inset, 결과 card의 file icon과 badge 색상을 Figma dark panel 기준으로 보정했다.
- 자료 관리 header 오른쪽 버튼과 Agent sidebar collapse 버튼 내부 아이콘 크기를 28px 기준으로 보정했다.
- 원본문서 preview가 없을 때는 자료 관리 sidebar 우상단을 둥글게, preview가 있을 때는 원본문서 패널 우상단을 둥글게 표시하도록 보정했다.
- 둥근 모서리 영역의 상단/우측 border가 끊기지 않도록 sidebar와 원본문서 패널 border를 보정했다.
- file icon 렌더링을 inline SVG override 대신 `frontend/svg/file.svg` 자산을 그대로 사용하도록 변경했다.
- Query Agent의 `Source` 결과 card는 `frontend/svg/source.svg` 자산을 사용하도록 분기했다.
- 자료 관리 sidebar의 source 항목도 `frontend/svg/source.svg` 자산을 사용하도록 변경했다.
- 자료 관리 tree에서 `failed`, `completed`, 로딩 상태 chip 표기를 제거했다.
- 자료 관리 heading typography를 Figma 기준의 Pretendard 20px, 600 weight, 120% line-height로 보정했다.
- 자료 관리 sidebar header는 고정하고 tree 영역만 sidebar 내부에서 scroll되도록 구조를 분리했다.
- 자료 관리 header 오른쪽 버튼은 sidebar collapse 대신 기존 자료 추가 picker를 열도록 되돌렸다.
- 자료 관리 header 오른쪽 버튼 내부 아이콘을 버튼 영역과 동일한 28px × 28px로 보정했다.
- graph filter chip padding과 typography를 Figma legend 기준으로 보정했다.
- graph filter의 `source page` chip 아이콘도 `source.svg` 자산을 사용하도록 변경했다.
- graph filter chip 그룹이 graph-stage 오른쪽 끝에 붙도록 위치를 보정했다.
- Agent sidebar collapse 버튼 내부 아이콘을 28px × 28px로 보정했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.
- `http://localhost:3001` 응답 `200 OK` 확인.
- 변경 파일 기준 secret 후보 검색에서 실제 비밀값 없음.

### feat: Agent 응답 연출과 그래프 아이콘 보정

**변경 배경**

- Query Agent 답변이 한 번에 표시되어 Figma 기준의 단계적 응답 흐름과 차이가 있었다.
- raw/source/concept 자료가 sidebar, 결과 card, graph에서 서로 다른 아이콘과 색상 체계로 보여 식별성이 떨어졌다.
- 자료 관리 sidebar를 접고 graph workspace를 넓혀 보는 동작이 필요했다.

**변경된 내용**

- 새 assistant 응답을 상태 목록, 근거 자료, 답변 본문 순서로 단계적으로 노출하고 최신 메시지로 부드럽게 scroll되도록 조정했다.
- raw/source/concept 항목의 file icon 색상과 결과 badge 색상을 통일하고, raw graph node에 `raw.svg` 자산을 적용했다.
- 자료 관리 sidebar 접기/복원 버튼을 추가하고 sidebar 접힘 상태에서 graph와 원문 preview 위치가 남은 workspace를 사용하도록 보정했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.
- 변경 파일 기준 secret 후보 검색에서 실제 비밀값 없음.

### fix: Figma 기준 그래프와 Agent UI 보정

**변경 배경**

- Figma `v1` 화면과 비교했을 때 중앙 검색 바, 왼쪽 rail 아이콘, 오른쪽 Agent 패널, graph node 색상과 hover 전환이 실제 화면과 어긋나 있었다.
- graph hover 시 화면 dimming과 링크 강조가 즉시 바뀌어 마우스를 빠르게 움직이면 화면이 버벅이는 것처럼 보였다.
- Query Agent 채팅 기록 로딩 실패와 질의 처리 실패 상태가 같은 UI로 표시되어 실제 오류 원인을 구분하기 어려웠다.

**변경된 내용**

- Figma 값 기준으로 topbar 검색창, Agent 패널, 좌측 rail 아이콘, source/concept/raw node 색상과 크기를 보정했다.
- `search.svg`, `CollectionOutLine.svg` 등 교체된 SVG 자산을 실제 UI 렌더링 경로에 연결했다.
- Query Agent 답변 UI를 상태 목록, 검색 결과, 답변 본문 영역으로 나누고 채팅 기록 로딩 실패와 질의 실패 표시를 분리했다.
- graph loading node 표현과 연결 수 기반 node 크기 확대를 제거하고, source page를 기준으로 관련 node가 원형 배치되도록 변경했다.
- graph hover 시 node 색상, 화면 dimming, 링크 강조가 노드별 보간값을 따라 천천히 fade in/out 되도록 조정했다.

**검증 결과**

- `npm run build` 통과.
- `http://localhost:3000` 응답 `200 OK` 확인.
- `/api/wiki/graph` 정상 응답 확인.

---

## 2026-06-16

### feat: Query Agent 채팅과 원문 viewer 연동

**변경 배경**

- 로컬 테스트에서 질문 입력 후 Query API 응답, 이전 채팅 기록, 근거 자료 클릭, source/concept 원문 확인 흐름을 한 화면에서 검증할 수 있어야 했다.
- Agent 패널의 정적 목업 상태와 중복 실행 상태 표시가 실제 query 흐름과 맞지 않았다.

**변경된 내용**

- Agent 입력창이 `POST /api/query`를 호출하고, `GET /api/chat/messages`로 이전 질문/답변 기록을 유지해 표시하도록 연결했다.
- assistant 답변을 markdown viewer로 렌더링하고, 문장 단위 가독성을 위해 마침표 뒤 줄바꿈을 보정했다.
- 근거 자료 card 클릭 시 `wiki_page_id` 또는 `document_id` 기반 source page를 원문 viewer로 열도록 연결했다.
- source/concept 원문 preview 패널이 Wiki page 상세 API의 markdown을 GitHub markdown viewer에 가까운 형태로 표시하도록 조정했다.
- 자료 관리 sidebar와 원문 viewer resize handle, 채팅 영역 scrollbar를 다크 워크스페이스 기준으로 보정했다.

**검증 결과**

- `npm run lint` 통과.
- `npm run build` 통과.
- `http://localhost:3000` 응답 `200 OK` 확인.

### feat: 그래프 원본문서 패널 상호작용 보강

**변경 배경**

- Figma `v1`의 다크 워크스페이스 기준으로 graph node 선택 표시, filter chip 위치, 원본문서 overlay 패널 동작을 맞출 필요가 있었다.
- 원본문서 패널이 graph 영역을 덮으면서도 패널 폭 조절에 따라 graph canvas가 남은 영역 기준으로 다시 scale되어야 했다.

**변경된 내용**

- graph canvas node 더블클릭 시 왼쪽 자료 트리 클릭과 동일하게 원본문서 미리보기 패널이 열리도록 연결했다.
- 원본문서 패널 오른쪽 resize handle을 추가하고, 패널 폭 변경 시 graph canvas 영역이 자동으로 재계산되도록 구성했다.
- graph node 선택 marker를 Figma `select.svg` 기준의 radial highlight 표현으로 보정했다.
- graph filter chip을 canvas 오른쪽 위에 배치하고 `processing` chip을 제거했다.
- graph scale, pan clamp, layout cache 버전을 조정해 node가 화면 밖으로 사라지거나 과도하게 뭉쳐 보이는 문제를 완화했다.

**검증 결과**

- `./node_modules/.bin/tsc --noEmit` 통과.
- `http://localhost:3001` 응답 `200 OK` 확인.
- 백엔드가 실행되지 않은 상태에서는 Next proxy가 `localhost:8080` 연결 실패를 기록한다.

### refactor: 홈 화면 렌더링 컴포넌트 분리

**변경 배경**

- `frontend/app/page.tsx`에 topbar, rail, Agent panel, source preview, SVG 렌더링 코드가 함께 있어 화면 단위 수정과 Figma 비교 작업의 변경 범위가 커지고 있었다.

**변경된 내용**

- `frontend/app/_components/` 폴더를 추가하고 `TopBar`, `RailNavigation`, `AgentPanel`, `SourcePreviewPanel`, `SvgIcon`을 분리했다.
- `page.tsx`는 홈 화면 상태 관리와 문서 트리/graph 흐름을 중심으로 남기고, 정적 UI 조각은 개별 컴포넌트 파일에서 관리하도록 정리했다.
- rail 항목과 SVG asset export를 컴포넌트 폴더로 옮겨 sidebar/agent/graph에서 같은 아이콘 렌더러를 재사용하도록 구성했다.

**검증 결과**

- `npm run lint` 통과.
- `npm run build` 통과.

### fix: Agent 패널 상태 표시와 입력창 여백 보정

**변경 배경**

- Figma 오른쪽 채팅 sidebar와 비교했을 때 명령 실행 상태 마커의 완료/진행중/추후 실행 표현이 다르게 보였다.
- Agent 메시지 입력창이 패널 하단 여백 없이 붙어 보여 Figma 기준의 composer 위치와 맞지 않았다.
- `page.tsx`의 홈 화면 JSX가 한 함수에 몰려 있어 Agent/sidebar 영역을 추후 분리하기 어렵게 되어 있었다.

**변경된 내용**

- Agent 상태 목록의 완료 마커를 10px 노란 원형으로, 진행중 마커를 노란 테두리와 어두운 배경의 10px 원형으로 보정했다.
- 추후 실행 상태는 `frontend/svg/Ellipse.svg` 자산을 사용하도록 연결하고, 어두운 sidebar 배경에 맞게 SVG 색상을 조정했다.
- Agent composer 하단 row와 margin을 조정해 입력창 아래 16px 여백을 확보했다.
- 홈 화면 JSX를 `TopBar`, `RailNavigation`, `DocumentSidebar`, `AgentPanel` 등 내부 렌더링 컴포넌트로 1차 분리했다.

**검증 결과**

- `npm run lint` 통과.
- `npm run build` 통과.

### feat: Figma 다크 워크스페이스 화면 반영

**변경 배경**

- Figma `v1`의 홈 그래프 화면과 원본문서 패널이 열린 화면을 기준으로 현재 프론트 화면의 테마, 패널 배치, 그래프/Agent UI를 맞출 필요가 있었다.
- SVG 신규 추출은 후속 작업으로 미루고, 현재 코드와 기존 SVG 자산만으로 수정 가능한 화면 요소를 먼저 반영했다.

**변경된 내용**

- topbar, 좌측 rail, 자료 관리 sidebar, graph canvas, filter chip, Agent panel을 Figma 기준의 다크 테마로 조정했다.
- 좌측 트리 항목 선택 시 Figma의 원본문서 패널 상태처럼 graph 왼쪽에 원본문서 미리보기 패널이 열리도록 추가했다.
- graph canvas 내부 node label, edge, raw/source/progress 색상을 다크 배경에 맞게 보정했다.
- 새 `arrow.svg`를 프로젝트/폴더 접기 아이콘에 적용하고, 변경된 `Frame.svg`가 채팅 전송 버튼에 반영되도록 조정했다.
- 문서 추가 버튼은 프로젝트 제목 영역에 hover 또는 focus가 있을 때만 `switch.svg`로 표시되도록 변경했다.
- 문서 추가 `switch.svg`를 `자료 관리` 헤더 영역으로 옮기고, 헤더 hover 또는 focus 시에만 표시되도록 변경했다.
- `자료 관리` 헤더와 프로젝트 목록 사이 divider를 추가하고, 학교 선택 토글을 새 `toggle.svg`로 교체했다.
- Figma 1920x1080 frame 기준으로 topbar 높이, sidebar divider/list offset, 원본문서 패널 폭과 padding, graph/chip 배치를 보정했다.
- `자료 관리` 헤더 hover 또는 focus 시 표시되는 `switch.svg` 버튼으로 문서 업로드를 실행하도록 정리했다.
- `.project-toggle`과 `.section-title` hover 배경이 사이드바 행 폭을 채우도록 보정했다.
- topbar의 메뉴 아이콘 버튼을 `부산대학교` 프로젝트 약칭인 `부` 배지로 교체했다.
- Figma `workspace` 노드 기준으로 topbar 프로젝트 배지 간격과 `부` 배지 typography를 보정했다.
- 백엔드 API 오류가 발생하면 graph 빈 상태 위치에 오류 메시지를 표시하도록 변경했다.
- graph API 오류 메시지를 실패 상태와 구분되도록 빨간색 계열로 표시했다.
- Figma `legend`와 chat composer 기준으로 filter chip 위치와 Agent 입력창 패딩을 보정했다.
- Figma `process` 노드 기준으로 Agent 상태 목록의 제목, step, 시간 표시 간격을 보정했다.
- Agent 상태 목록 완료 아이콘을 `chat_check.svg`로 교체하고 step 사이 세로 점선을 추가했다.
- Figma chat frame 기준으로 Agent 패널 header/body/composer row 위치를 다시 보정했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.

---

## 2026-06-12

### refactor: 프론트 미사용 목업 자산 정리

**변경 배경**

- 백엔드 API 기반 graph로 전환된 뒤에도 이전 정적 graph 목업 데이터와 계산 helper가 `frontend/app/page.tsx`에 남아 있었다.
- 사용되지 않는 `mvp main.png` 시안 이미지가 프론트 디렉터리에 남아 있었다.
- `.gitignore`에서 `.github/` 전체를 무시해 추후 workflow 추가가 누락될 수 있었다.

**변경된 내용**

- `frontend/app/page.tsx`의 미사용 정적 graph 목업 node/link 데이터와 전용 전역 계산 helper를 제거했다.
- 참조되지 않는 `frontend/mvp main.png` 파일을 삭제했다.
- `.gitignore`에서 `.github/` ignore 규칙을 제거했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.

---

### feat: 문서 선택 유지와 rename API 계약 정리

**변경 배경**

- 왼쪽 트리에서 문서를 클릭한 뒤 마우스를 graph 위로 이동하면 선택 효과가 사라져, 사용자가 어떤 문서를 확인 중인지 유지되지 않았다.
- 문서 이름 변경은 프론트 메모리 상태에만 적용되어 새로고침 또는 API 재조회 후 기존 이름으로 되돌아갔다.
- 실제 영속 rename을 지원하려면 백엔드 API 계약과 이슈 정의가 필요했다.

**추가 및 변경된 내용**

- 왼쪽 트리에서 선택된 문서 row에 선택 상태 스타일을 표시하도록 추가했다.
- graph hover와 외부 선택 상태를 분리해, 마우스 이동이나 pointer leave로 트리 선택 효과가 사라지지 않도록 변경했다.
- 화면의 다른 영역을 클릭하면 트리 선택과 graph focus가 함께 해제되도록 구성했다.
- `docs/backlog/issue-2026-06-11.md`에 문서와 Wiki page rename API 필요성, 원인, 해결 방향을 정리했다.
- `docs/Fruition_MVP_API_Contract.md`에 `PATCH /api/documents/{document_id}/rename`, `PATCH /api/wiki/pages/{wiki_page_id}/rename` 계약을 추가했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.

---

### feat: 문서 트리 클릭 시 graph node 포커스

**변경 배경**

- 왼쪽 문서 트리에서 특정 문서를 클릭했을 때 graph canvas에서 대응되는 raw/source/concept node를 바로 확인할 수 있어야 했다.

**추가 및 변경된 내용**

- 업로드 문서 트리 항목에 `raw:{document_id}` graph node id를 연결했다.
- `Source 문서`, `Concept 문서` 가상 항목에는 백엔드 Wiki graph node id를 연결했다.
- 트리 항목 클릭 시 Graph 컴포넌트가 해당 node를 선택/포커스하도록 외부 focus state를 추가했다.
- source/concept 가상 폴더는 백엔드 graph 데이터가 들어오면 자동으로 펼쳐지도록 변경했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.

---

### fix: raw와 source graph node 1:1 매핑

**변경 배경**

- 원본 파일은 MinIO에 raw 객체로 저장되고, source page는 raw 문서 1개에서 생성되는 1:1 결과물이다.
- 기존 프론트 graph 변환은 source page가 없는 문서를 progress/raw 단일 노드로만 표시해 raw와 source의 관계가 화면에 드러나지 않았다.

**변경된 내용**

- `GET /api/documents`의 모든 문서를 `raw:{document_id}` 노드로 생성하도록 변경했다.
- 각 raw 문서마다 `source:{document_id}` 노드를 항상 생성하고 `raw -> source` edge를 추가했다.
- 백엔드 Wiki graph에 실제 source page가 있으면 해당 source title을 사용하고, 아직 없으면 원본 파일명 기반의 임시 source node로 표시한다.
- 처리 중이거나 실패한 source/raw node에는 로딩 링을 표시해 pipeline 결과가 아직 확정되지 않았음을 보여준다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.

---

### fix: 원본 raw 카운트 기준 수정

**변경 배경**

- DB에는 업로드 문서가 7개 있지만 프론트 graph 상단의 `원본 raw`가 실패 문서 1개만 표시하고 있었다.
- 기존 계산은 graph node의 `kind=raw`만 세고 있어, 업로드 원본 수가 아니라 source page로 승격되지 않은 failed node 수를 보여주는 문제가 있었다.

**변경된 내용**

- graph 상단의 `원본 raw` 카운트를 `GET /api/documents`로 받은 전체 업로드 문서 수 기준으로 표시하도록 변경했다.
- `processing` 카운트도 graph node 종류가 아니라 실제 문서 상태가 `processing` 또는 `uploaded`인 문서 수 기준으로 표시하도록 변경했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.

---

### fix: Source 문서 색상 표시 보정

**변경 배경**

- 사이드바의 source 문서 아이콘이 기본 트리 아이콘 색상인 회색으로 표시되어 graph의 source page 색상과 일관되지 않았다.

**변경된 내용**

- `Source 문서` 하위 항목의 source page 아이콘에 별도 class를 부여하고 노란색으로 표시되도록 스타일을 추가했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.

---

### feat: 프로젝트와 문서 트리 정리 기능 개선

**변경 배경**

- 프로젝트 이름 변경, 문서 업로드 진입점, 우클릭 폴더 생성, 단일 문서 이동, 문서 병합 정리 등 실제 자료 관리에 필요한 기본 조작이 부족했다.
- 백엔드 Wiki graph에서 생성된 source/concept page도 프론트 트리에서 확인할 수 있어야 했다.
- `processing` 문서를 58% 숫자로 고정 표시하면 실제 진행률처럼 보이므로, 처리 중 상태임을 나타내는 로딩 표시로 바꿀 필요가 있었다.

**추가 및 변경된 내용**

- 프로젝트 우클릭 메뉴에서 프로젝트 이름을 변경할 수 있도록 추가했다.
- 프로젝트의 `+` 버튼은 폴더 생성 대신 문서 업로드 파일 선택을 열도록 변경했다.
- 프로젝트 또는 폴더 내부 우클릭 메뉴에서 새 폴더를 추가할 수 있도록 변경했다.
- 단일 문서 파일도 폴더처럼 드래그 이동할 수 있도록 변경했다.
- 문서 이름 변경 시 polling으로 문서 목록을 다시 받아도 사용자가 변경한 이름이 유지되도록 처리했다.
- 문서 파일을 다른 문서 파일 위에 놓으면 `새 문서 묶음` 폴더를 만들고 두 문서를 그 안으로 넣도록 변경했다.
- 백엔드 Wiki graph의 source/concept node를 `Source 문서`, `Concept 문서` 가상 폴더로 사이드바에 표시하도록 추가했다.
- `processing`, `uploaded`, `uploading` 상태 표시는 숫자나 텍스트 대신 회전 로딩 indicator로 변경했다.
- graph canvas의 processing node도 58% 숫자 표시 대신 회전 링으로 표시하도록 변경했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.

---

### feat: 문서 업로드와 Wiki graph 백엔드 연동

**변경 배경**

- 기존 프론트는 프로젝트/폴더 UI와 graph 화면을 정적 목업 데이터로 표시하고 있었다.
- 백엔드에는 문서 업로드, 원본 스토리지 저장, LLM pipeline 처리, Wiki graph 조회 API가 이미 구현되어 있어 프론트만 API 계약에 맞춰 연결해야 했다.
- 프론트 작업 지침에 백엔드, 인프라, AI/LLM pipeline 코드는 수정하지 않고 프론트 코드만 수정한다는 원칙을 명시해야 했다.

**추가 및 변경된 내용**

- `frontend/next.config.mjs`에 `/api/:path*` rewrite를 추가해 프론트 개발 서버에서 Spring backend API를 호출하도록 연결했다.
- `frontend/app/page.tsx`에서 `GET /api/documents`, `GET /api/wiki/graph`, `POST /api/documents`를 사용하도록 변경했다.
- 문서 업로드 후 문서 목록과 Wiki graph를 재조회하고, `processing` 또는 `uploaded` 상태 문서가 있으면 polling하도록 구성했다.
- 백엔드 graph 응답을 캔버스용 `GraphNode`, `GraphLink` 데이터로 변환해 정적 목업 대신 실제 DB 기반 node와 edge를 표시하도록 변경했다.
- OS 파일 드래그 앤 드롭으로 `.pdf`, `.md` 문서를 프로젝트 또는 폴더에 업로드할 수 있도록 구성했다.
- 프로젝트/폴더 트리에서 폴더 추가, 드래그 이동, 중첩, 우클릭 이름 변경/삭제, 파일 드롭 대상 표시를 지원하도록 변경했다.
- 기존 더미 프로젝트/폴더 데이터는 제거하고, 실제 백엔드 문서가 붙는 `업로드 문서` 프로젝트만 초기 표시하도록 정리했다.
- 우측 채팅 사이드바와 workspace 레이아웃에서 화면 폭이 줄어도 가로 스크롤이 생기지 않도록 스타일을 보정했다.
- `frontend/AGENTS.md`, `frontend/CLAUDE.md`에 프론트엔드 작업 시 백엔드/인프라/AI/LLM pipeline 코드를 수정하지 않는다는 지침을 추가했다.

**검증 결과**

- `npm run lint` 통과.
- `./node_modules/.bin/tsc --noEmit` 통과.
- 프론트 개발 서버 proxy 기준 `GET /api/documents`, `GET /api/wiki/graph` 응답을 확인했다.
- 프론트 개발 서버 proxy 기준 `POST /api/documents`로 문서 업로드가 백엔드까지 전달되는 것을 확인했다.
- 업로드된 테스트 문서가 `completed`로 전환되고 Wiki graph API에 source/concept node가 추가되는 것을 확인했다.

**주의사항**

- 로컬 DB에는 이전 실패 검증 과정에서 생성된 `processing` 또는 `failed` 상태 문서가 남아 있다.
- `llm-wiki.md`, 일부 `README.md`, `backend.md`는 `pipeline_runs` 실행 기록이 없어 업로드 당시 pipeline 요청이 생성되지 않은 채 `processing`으로 남은 데이터로 확인했다.
- 실패한 `README.md`는 `ERROR: Missing API key. Set UPSTAGE_API_KEY=... or pass --api-key` 사유로 pipeline 실패 상태가 저장되어 있다.

---

## 2026-06-05 이전

### feat: 옵시디언 스타일 그래프 UI 구현 (`95e26ff`)

**추가된 것**

- Wiki 그래프 화면 초기 구현 (React, D3 기반)
- 옵시디언 스타일 node / edge 렌더링

---

*커밋 단위 이력은 `git log` 로 확인하세요.*
