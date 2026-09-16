# 프론트엔드 Feature-Sliced Design 마이그레이션 매핑안 (검토용)

> 상태: **적용 완료** (`next build` 검증). 실제 구현 시 변경점: FSD `pages` 레이어는 Next.js `pages/`(레거시 Pages Router) 충돌 때문에 **`views`로 명명**했다. 전역 스타일은 슬라이스 콜로케이트 대신 `src/app/styles/`(app 레이어)로 이관했다(Next 전역 CSS 제약). 아래 계획서의 `pages`는 실제로는 `views`로 읽는다.
> 기준: [feature-sliced.design](https://feature-sliced.design) 공식 스펙 (레이어 → 슬라이스 → 세그먼트, 하위 레이어로만 import, 슬라이스별 `index.ts` public API).

## 1. 결정 사항 (합의됨)

- **Next.js 통합**: FSD 트리는 `frontend/src/` 아래에 두고, Next `frontend/app/`는 `src/pages/*`를 re-export 하는 얇은 라우팅 껍데기로만 유지 (공식 FSD-Next 가이드).
- **진행 방식**: 현 UI 작업 커밋 후(완료: `feat/figma-workspace-ui`), path alias 추가 → 레이어별로 이동+빌드 검증 반복.
- **경계 결정**: 이 문서로 먼저 검토 → 승인 후 이동.

## 2. FSD 레이어 규칙 요약

| 레이어 | 역할 | 슬라이스 | 이 프로젝트에서 |
|---|---|---|---|
| `app` | 앱 초기화, providers, 전역 스타일 | 없음 | providers, root layout, globals/base css |
| `pages` | 라우트 화면 조립 | 있음 | home, login, workspaces, auth flow |
| `widgets` | 독립적 합성 UI 블록 | 있음 | workspace, document-sidebar, graph, agent-panel, source-preview, rail-navigation, top-bar |
| `features` | 사용자 상호작용/동작 | 있음 | agent-chat, note-editing, schema-manage, document-history, document-search, document-upload, wiki-export |
| `entities` | 업무 도메인 데이터+모델 | 있음 | document, chat, wiki, schema, workspace, user, graph, tree |
| `shared` | 재사용 유틸/UI, 업무 로직 없음 | 없음 | api client, ui(SvgIcon 등), lib(classNames/errors/markdown), types |

세그먼트: `ui` / `model` / `api` / `lib` / `config`. import는 항상 하위 레이어로만.

## 3. 목표 디렉터리 구조

```
frontend/
├─ app/                              # Next 라우팅 전용(얇게)
│  ├─ layout.tsx                     # → src/app root 조합 re-export
│  ├─ page.tsx                       # → src/pages 랜딩
│  ├─ home/page.tsx                  # → src/pages/home
│  ├─ login/page.tsx                 # → src/pages/login
│  ├─ workspaces/page.tsx            # → src/pages/workspaces
│  └─ (auth)/...                     # → src/pages/auth-* re-export
└─ src/
   ├─ app/
   │  ├─ providers.tsx
   │  ├─ layout/                     # root layout 본체
   │  └─ styles/                     # globals.css, base.css
   ├─ pages/
   │  ├─ home/                       # workspace 위젯 조립
   │  ├─ login/
   │  ├─ workspaces/
   │  └─ auth/                       # signup, verify, forgot, reset + (auth) layout
   ├─ widgets/
   │  ├─ workspace/                  # 홈 전체 조립(구 HomeWorkspace)
   │  ├─ document-sidebar/
   │  ├─ graph/
   │  ├─ agent-panel/
   │  ├─ source-preview/
   │  ├─ rail-navigation/
   │  └─ top-bar/
   ├─ features/
   │  ├─ agent-chat/
   │  ├─ note-editing/
   │  ├─ schema-manage/
   │  ├─ document-history/
   │  ├─ document-search/
   │  ├─ document-upload/
   │  └─ wiki-export/
   ├─ entities/
   │  ├─ document/  chat/  wiki/  schema/
   │  ├─ workspace/ user/  graph/  tree/
   └─ shared/
      ├─ api/        # client.ts (base fetch)
      ├─ ui/         # SvgIcon, MarkdownViewer, modals(공용)
      ├─ lib/        # classNames, errors, markdown 파싱 유틸
      └─ types/      # 공용 타입
```

## 4. 파일별 매핑 (147개)

### shared
| 현재 | → FSD |
|---|---|
| `_lib/api/client.ts` | `shared/api/client.ts` |
| `_lib/classNames.ts` | `shared/lib/class-names.ts` |
| `_lib/errors.ts` | `shared/lib/errors.ts` |
| `_lib/markdownSegments.ts` | `shared/lib/markdown/segments.ts` |
| `_lib/markdownSourceBlocks.ts` | `shared/lib/markdown/source-blocks.ts` |
| `_lib/messages.ts` | `shared/lib/messages.ts` |
| `_lib/types/shared.ts` | `shared/types/index.ts` |
| `_components/SvgIcon.tsx` | `shared/ui/svg-icon/` |
| `_components/MarkdownViewer.tsx` | `shared/ui/markdown-viewer/` |
| `_components/modals/DeleteConfirmModal.tsx` | `shared/ui/modals/` (범용 확인 모달) |

### entities
| 현재 | → FSD |
|---|---|
| `_lib/api/document.ts`, `_lib/types/document.ts`, `_lib/note.ts` | `entities/document/{api,model}` |
| `_lib/api/chat.ts`, `_lib/types/chat.ts` | `entities/chat/{api,model}` |
| `_lib/api/wiki.ts`, `_lib/types/wiki.ts` | `entities/wiki/{api,model}` |
| `_lib/api/schema.ts`, `_lib/types/schema.ts` | `entities/schema/{api,model}` |
| `_lib/api/workspace.ts`, `_lib/types/workspace.ts`, `_hooks/useWorkspaceName.ts` | `entities/workspace/{api,model}` |
| `_lib/api/auth.ts`, `_lib/auth.ts`, `_lib/types/auth.ts` | `entities/user/{api,model}` |
| `_lib/graph.ts`, `_components/graph/{graphColors,graphGeometry,graphPhysics,graphDrawing}.ts` | `entities/graph/{model,lib}` |
| `_lib/tree/*`, `_lib/tree.ts`, `_lib/types/tree.ts` | `entities/tree/{model,lib}` |
| `_lib/types.ts`, `_lib/api.ts` (배럴 re-export) | 슬라이스 `index.ts`로 대체 후 삭제 |

### features
| 현재 | → FSD |
|---|---|
| `_components/agent-panel/{AgentBody,AgentComposer,AgentHeader,AgentResultCard,StatusList,MarkdownCreatePreview,MarkdownEditPreview}.tsx` | `features/agent-chat/ui` |
| `_components/agent-panel/{useChatThread,useSmoothScroll}.ts`, `agentData.ts`, `agentFormatters.ts` | `features/agent-chat/{model,lib}` |
| `_lib/api/agent.ts`, `_lib/markdownAgent.ts`, `_lib/markdownEditContext.ts` | `features/agent-chat/{api,lib}` |
| `_components/note-editor/*` | `features/note-editing/ui`, `useNoteAutosave` → model |
| `_components/schema/{SchemaEditorForm,SchemaList,SchemaPreviewCard}.tsx` | `features/schema-manage/ui` |
| `_components/history/*` | `features/document-history/{ui,model,lib}` |
| `_components/search/DocumentSearch.tsx` | `features/document-search/ui` |
| `_hooks/useDocumentUpload.ts`, `_components/modals/UploadErrorModal.tsx` | `features/document-upload/{model,ui}` |
| `_components/modals/WikiExportConfirmCard.tsx`, `_lib/api/export.ts` | `features/wiki-export/{ui,api}` |

### widgets
| 현재 | → FSD |
|---|---|
| `_components/home-workspace/HomeWorkspace.tsx`, `useResizeHandle.ts` | `widgets/workspace/{ui,model}` |
| `_components/document-sidebar/*` (15개: DocumentSidebar, ProjectSection, SidebarTree, TreeNode 등 + dragDrop/useTreeNodeDragDrop/useFileDropZone/types) | `widgets/document-sidebar/{ui,model,lib}` |
| `_components/graph/{Graph,GraphCanvas,GraphFilterChips,GraphEmptyState}.tsx` + `{graphCache,useGraphAnimation,useGraphCanvas,useGraphPointer}` | `widgets/graph/{ui,model}` |
| `_components/agent-panel/AgentPanel.tsx` | `widgets/agent-panel/ui` (내부에서 features/agent-chat 사용) |
| `_components/SourcePreviewPanel.tsx` | `widgets/source-preview/ui` |
| `_components/RailNavigation.tsx` | `widgets/rail-navigation/ui` |
| `_components/TopBar.tsx` | `widgets/top-bar/ui` |
| `_hooks/{useBackendData,useProjectTree,useTreeSelection}.ts` | `widgets/workspace/model` (화면 조립 상태) |

### pages / app
| 현재 | → FSD |
|---|---|
| `app/home/page.tsx` | `pages/home` (+ `app/home/page.tsx` re-export) |
| `app/login/page.tsx` | `pages/login` |
| `app/workspaces/page.tsx` | `pages/workspaces` |
| `app/page.tsx` | `pages/landing` |
| `app/(auth)/*` (layout, signup, verify, forgot, reset, AuthControls, AuthFlowContext, useDevelopmentVerificationCode, useExpiryCountdown) | `pages/auth/*` |
| `app/layout.tsx`, `app/providers.tsx` | `src/app/` |
| `_styles/{globals,base,landing}.css` | `src/app/styles/` |

### styles (슬라이스 ui 세그먼트로 콜로케이트)
| 현재 | → FSD |
|---|---|
| `_styles/schema.css` | `features/schema-manage/ui/` |
| `_styles/agent-panel/*` (7개) | `features/agent-chat/ui/` + `widgets/agent-panel/ui/` |
| `_styles/graph/*`, `graph.css` | `widgets/graph/ui/` |
| `_styles/document-sidebar/*`, `document-sidebar.css` | `widgets/document-sidebar/ui/` |
| `_styles/source-preview.css` | `widgets/source-preview/ui/` |
| `_styles/workspace.css`, `rail.css`, `responsive.css` | `widgets/workspace|rail-navigation/ui/` |
| `_styles/history.css` | `features/document-history/ui/` |
| `_styles/modal.css` | `shared/ui/modals/` |
| `_styles/auth.css` | `pages/auth/` |

## 5. 판단이 갈리는 지점 (사용자 확인 필요)

1. **HomeWorkspace = widget vs page**: 화면 전체를 조립하므로 page로 볼 수도 있음. 제안: `widgets/workspace`(합성) + `pages/home`(얇게 조립). ← 이대로 진행할지?
2. **agent-panel 분리**: 껍데기 패널(`widgets/agent-panel`)과 채팅 로직(`features/agent-chat`) 분리 제안. 한 슬라이스로 합칠지?
3. **graph 분리**: 렌더 위젯(`widgets/graph`) vs 데이터/물리 모델(`entities/graph`) 분리 제안. 과분할이면 `widgets/graph` 하나로 통합 가능.
4. **tree**: `entities/tree`로 둘지, sidebar 위젯 내부 lib로 둘지.
5. **CSS 전략**: 현재 `globals.css`가 전부 @import. 콜로케이트하면 각 슬라이스가 자기 css를 import하도록 바꿔야 함(작업량 증가). 대안: 스타일은 당분간 `src/app/styles/`에 그대로 두고 구조만 이동(1차), 콜로케이트는 2차. ← 추천: 1차엔 CSS 이동 최소화.

## 6. 마이그레이션 순서 (bottom-up, 단계별 빌드 검증)

각 단계 후 `tsc --noEmit` + `next build`(또는 dev HMR) 통과 확인.

1. **준비**: `tsconfig.json`에 `baseUrl` + `@/*` → `src/*` alias 추가. `src/` 생성.
2. **shared** 이동 → import 갱신 → 검증.
3. **entities** 이동 (api/types/model) → 검증.
4. **features** 이동 → 검증.
5. **widgets** 이동 → 검증.
6. **pages** 이동 + Next `app/` re-export 껍데기 작성 → 검증.
7. **app** 레이어(providers/layout/styles) 정리 → 최종 `next build`.
8. 배럴(`_lib/api.ts`, `_lib/types.ts`, `_lib/tree.ts`) 제거, 슬라이스 `index.ts` public API 정리.

## 7. 리스크 / 되돌림

- 단계마다 별도 커밋 → 문제 시 해당 단계만 revert.
- 상대경로 대량 변경은 alias 도입으로 최소화(깊은 `../../..` 제거).
- Next route group `(auth)`·`layout.tsx`·`page.tsx`는 파일 위치가 라우팅에 직결 → `app/`엔 반드시 재-export 껍데기 유지.
