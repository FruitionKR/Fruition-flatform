# Markdown 노트 편집기 프론트엔드 프로토타입 사양

> **이전 자료 안내 (2026-08-06)**: 이 문서는 local mock 저장을 전제로 한 프로토타입 사양이다. 문서 본문 저장·버전은 backend에 영속화되었고, 버전 이력·비교·복원의 현재 계약은 [문서 버전 이력·복원](../../../docs/spec/document-version-history.md)을 따른다.

## 1. 목적

사이드바에서 만든 `새 노트`를 Obsidian처럼 Markdown 원문으로 편집한다. 편집 화면과 미리보기의 여백·타이포그래피는 Notion 문서처럼 구성하되 Notion block이나 데이터베이스 기능은 구현하지 않는다.

이번 단계는 frontend 사용성 검증이 목적이다. production 문서 저장, MinIO 갱신, DB version 관리, Wiki 재처리는 구현하지 않고 local profile에서만 동작하는 메모리 mock으로 저장 계약을 대체한다.

## 2. 결정 사항

- 편집기는 CodeMirror 6를 사용한다.
- Markdown 문법을 보존하는 원문 편집과 렌더링 결과를 확인하는 미리보기 모드를 제공한다.
- Next.js App Router에서는 client component를 `dynamic(..., { ssr: false })`로 불러온다.
- 편집 대상은 원본 Markdown 첫 부분에 `<!-- fruition-note: ... -->` 식별자가 있는 새 노트로 제한한다.
- 일반 업로드 Markdown, PDF, Wiki source/concept page는 기존 읽기 전용 화면을 유지한다.
- 내부 식별 주석은 editor에 표시하지 않고 저장할 때 원문 앞에 다시 결합한다.
- preview는 기존 `MarkdownViewer`를 재사용하고 LaTeX는 `remark-math`, `rehype-katex`, KaTeX로 렌더링한다.
- 편집과 저장 사이에 block 변환을 두지 않아 사용자가 작성한 Markdown 원문을 그대로 보존한다.

## 3. 범위

### 포함

- 새 노트 Markdown 불러오기
- CodeMirror 기반 Markdown 원문 편집
- 편집/미리보기 모드 전환
- heading, list, checklist, quote, code fence, link, GFM table 등 Markdown 문법
- inline math `$...$`와 display math `$$...$$` 미리보기
- 800ms debounce 자동 저장
- 저장 상태 표시: `불러오는 중`, `편집됨`, `저장 중`, `저장됨`, `저장 실패`, `충돌`
- local backend mock의 version 충돌 처리

### 제외

- production DB migration과 MinIO 원본 교체
- backend workspace 소유권 재검증 로직
- Wiki/source block 재생성 및 graph 반영
- 문서 이력과 공동 편집
- 이미지·첨부 파일 업로드
- Notion database, property, board, calendar, gallery
- slash command, block side menu, drag handle, block 단위 변환
- AI 편집 결과의 diff, Apply/Reject
- 기존 외부 Markdown의 WYSIWYG 변환

AI 편집 도우미의 별도 계약은 `docs/spec/agent-markdown-contract.md`와 `docs/spec/markdown-ai-editor-scope.md`를 따른다.

## 4. local backend mock 계약

mock controller는 Spring `local` profile에서만 등록한다. 데이터는 `(workspace_id, document_id)`를 key로 한 메모리 map에 저장하며 backend 재시작 시 사라진다.

### 4.1 저장된 draft 조회

```http
GET /api/workspaces/{workspace_id}/documents/{document_id}/content
Authorization: Bearer {access_token}
```

저장된 draft가 있으면 `200`을 반환한다.

```json
{
  "document_id": "doc_example",
  "markdown": "<!-- fruition-note: note-example -->\n# 새 문서\n",
  "content_version": 1,
  "updated_at": "2026-07-21T12:00:00Z"
}
```

draft가 없으면 `404`를 반환한다. frontend는 기존 `GET .../original` 결과와 `content_version=0`을 초기값으로 사용한다.

### 4.2 draft 저장

```http
PUT /api/workspaces/{workspace_id}/documents/{document_id}/content
Authorization: Bearer {access_token}
Content-Type: application/json
```

```json
{
  "markdown": "<!-- fruition-note: note-example -->\n# 변경된 문서\n",
  "expected_content_version": 0
}
```

- 현재 draft가 없으면 version은 `0`이다.
- `expected_content_version`이 현재 version과 같으면 저장하고 version을 1 증가시킨다.
- version이 다르면 `409 Conflict`를 반환하고 기존 draft를 변경하지 않는다.
- mock은 DB, MinIO, pipeline 및 Wiki 관련 데이터를 변경하지 않는다.

## 5. frontend 구조

### 5.1 API 계층

- `fetchNoteDraft(documentId)`: mock draft를 조회하고 없으면 `null`을 반환한다.
- `saveNoteDraft(documentId, markdown, expectedVersion, source?)`: 저장 결과의 새 version을 반환한다.
  AI 편집 결과 적용 시 `source="agent"`를 전달해 서버 버전 스냅샷을 남기고, 일반 자동 저장은
  `source`를 생략한다.
- `409`는 일반 오류와 구분되는 conflict 오류로 변환한다.

### 5.2 editor 초기화

1. raw Markdown 문서를 선택한다.
2. mock draft를 조회한다.
3. draft가 없으면 기존 원본 Markdown을 불러온다.
4. `fruition-note` 주석을 분리한다.
5. 식별 주석이 없으면 기존 `MarkdownViewer`로 렌더링한다.
6. 식별 주석이 있으면 본문만 CodeMirror의 초기 Markdown 값으로 전달한다.

### 5.3 자동 저장

1. editor `onChange`에서 dirty 상태로 전환한다.
2. 마지막 입력 후 800ms 동안 추가 변경이 없으면 Markdown으로 변환한다.
3. 식별 주석과 본문을 결합해 mock 저장 API를 호출한다.
4. 성공하면 응답 version을 다음 저장의 `expected_content_version`으로 사용한다.
5. 저장 도중 추가 입력이 발생하면 성공 직후 최신 내용을 다시 저장한다.
6. `409`가 발생하면 자동 재시도하지 않고 충돌 상태를 표시한다.

### 5.4 상태 UI

- 원본문서 패널 상단에는 파일명과 `Note` badge를 표시한다.
- 편집기 상단에는 `편집`, `미리보기` 전환과 저장 상태를 표시한다.
- 편집기는 문법이 보이는 Obsidian식 원문 화면으로 구성한다.
- 미리보기는 Notion 문서처럼 넓은 여백, 읽기 좋은 행간과 제목 계층을 사용한다.
- 저장 실패·충돌 상태에서는 사용자의 현재 editor buffer를 유지한다.
- 이번 프로토타입은 충돌 해결 UI를 구현하지 않고 다시 열기 안내만 제공한다.

## 6. 구현 순서

1. 이 사양과 관련 이슈 문서를 확정한다.
2. `local` profile의 메모리 mock controller와 controller test를 구현한다.
3. frontend에 CodeMirror와 KaTeX 관련 의존성을 추가한다.
4. mock 조회·저장 API와 conflict 오류 타입을 구현한다.
5. client-only Markdown `NoteEditor`와 자동 저장 hook을 구현한다.
6. `SourcePreviewPanel`에서 새 노트만 editor로 분기한다.
7. 기존 dark UI 안에서 Notion 문서와 유사한 editor·preview·저장 상태를 스타일링한다.
8. backend test와 frontend production build를 실행한다.

## 7. 완료 조건

- `./scripts/dev-up.sh`로 시작한 local 환경에서 mock endpoint가 활성화된다.
- 새 노트를 선택하면 Markdown 원문 editor가 열린다.
- editor에서 작성한 Markdown 문법이 변환 손실 없이 저장된다.
- 미리보기에서 GFM과 LaTeX가 렌더링된다.
- Notion database나 block 전용 UI가 나타나지 않는다.
- 입력을 멈추면 자동 저장 상태가 `저장됨`으로 바뀐다.
- 다른 version으로 저장하면 `충돌`을 표시하고 현재 입력을 유지한다.
- 기존 Markdown·PDF·Wiki 미리보기 동작은 바뀌지 않는다.
- backend test와 `npm run build`가 통과한다.

## 8. production 전환 시 후속 작업

- `documents.content_version`, `content_updated_at` migration
- MinIO 원본의 version 단위 저장과 실패 보상
- upload 중복 검사와 editable note 동일 본문 허용 정책 분리
- workspace 소유권 검증
- Wiki/source block stale 처리와 명시적 재분석 API
- conflict 해결 및 문서 이력 UI
