# Markdown AI 편집 도우미 구현 범위

## 1. 목적

이 문서는 Fruition의 문서 편집 도우미가 block editor를 구현하지 않고, 일반 Markdown과 renderer plugin을 기준으로 제공할 수 있는 기능 범위를 정의한다.

목표는 Notion의 block 구조를 복제하는 것이 아니다. 사용자가 선택 영역, 현재 섹션 또는 문서 전체를 자연어로 편집하고, 결과를 검토한 뒤 적용하는 문서 AI 경험을 제공하는 것이 목표다.

사용자가 직접 편집하는 Obsidian식 Markdown editor 프로토타입은 이 문서의 범위가 아니다. 해당 UI와 local mock 저장 계약은 `docs/spec/note-editor-prototype.md`를 따른다.

## 2. 결론

현재 `llmPipeline`에는 다음 기능의 생성 로직과 응답 계약이 이미 있다.

- 선택 영역, 현재 섹션, 문서 전체 교체
- 요약과 축약
- 문체와 어조 변경
- 번역
- 문장과 Markdown 정리
- 표, checklist, 회의록 변환
- 대화 context를 이용한 새 Markdown 문서 생성

현재 프론트에는 `react-markdown`과 `remark-gfm` 기반 renderer가 있으므로 CommonMark와 GFM 문법 대부분을 표시할 수 있다. 다만 현재 `MarkdownViewer`가 Markdown을 자체적으로 분할한 뒤 조각별로 렌더링하므로, 중첩 목록과 각주처럼 구조 또는 문서 전체 문맥이 필요한 문법은 renderer plugin을 추가하기 전에 분할 로직을 보완해야 한다.

따라서 구현 우선순위는 다음과 같다.

1. 편집 도우미와 editor의 preview/apply 흐름을 연결한다.
2. 현재 Markdown 분할 과정에서 원문 구조가 손상되지 않게 한다.
3. CommonMark와 GFM을 안정적인 기본 지원 범위로 확정한다.
4. 필요할 때 수식, code highlighting, Mermaid renderer를 선택적으로 추가한다.

## 3. 현재 구현 상태

### 3.1 llmPipeline

`POST /agent/turn`은 사용자의 발화를 다음 action으로 분류한다.

| Action | 역할 |
| --- | --- |
| `chat_answer` | 기존 query pipeline으로 답변 생성 |
| `markdown_edit` | 기존 Markdown 일부 또는 전체의 편집 결과 생성 |
| `markdown_create` | 대화나 reference context로 새 Markdown 생성 |
| `clarify` | 편집 대상 또는 추가 정보 요청 |
| `reject` | 지원하지 않는 요청 거절 |

현재 편집 operation은 `replace`와 `insert_after`다.

일반적인 문서 전체 편집과 원문 구조 보존형 cleanup은 `replace` 범위에 포함한다. `insert_after`는 현재 섹션 아래에 새 Markdown을 추가할 때만 사용하고, 외부 template 기반 전체 구조 재구성은 보류한다.

```json
{
  "operation": "replace",
  "requested_target": {
    "type": "selection",
    "start_line": 3,
    "end_line": 5
  },
  "actual_target": {
    "type": "selection",
    "start_line": 2,
    "end_line": 6
  },
  "scope_expanded": true,
  "changed": true,
  "summary": "선택 영역을 짧게 정리했습니다.",
  "replacement_markdown": "교체할 Markdown"
}
```

`requested_target`은 사용자가 요청한 범위이고 `actual_target`은 실제 교체 범위다. `actual_target`은 `requested_target`을 포함하며, Markdown 구조 보존을 위해 범위가 확장되면 `scope_expanded=true`다. 결과가 원문과 같으면 `changed=false`다.

관련 계약은 `docs/spec/agent-markdown-contract.md`의 `기존 문서 편집` 절에서 확인할 수 있다.

현재 prompt에 명시된 편집 mode는 다음과 같다.

| Edit goal | 현재 역할 |
| --- | --- |
| `shorten` | 요약, 축약, 간결화 |
| `style_change` | 문체와 어조 변경 |
| `translate` | 번역 |
| `cleanup` | 문장과 Markdown 정리 |
| `bullet_list` | 일반 bullet과 중첩 bullet 목록 생성 |
| `checklist` | Markdown task list 생성 |
| `convert_format` | 표, 회의록 등 형식 변환 |
| `template_transform` | 전체 template 변환을 보류하고 좁은 범위만 편집 |
| `create_from_chat` | 대화 context로 새 문서 생성 |

### 3.2 프론트 renderer

현재 `frontend/app/_components/MarkdownViewer.tsx`는 다음 구성을 사용한다.

- `react-markdown`
- `remark-gfm`
- `remark-math` + `rehype-katex`
- 프로젝트 전용 Wiki link와 citation token plugin
- fenced code block용 custom `pre` component
- YAML frontmatter를 접힌 Metadata 영역으로 표시하는 별도 처리

`react-markdown`은 CommonMark를 지원하고, `remark-gfm`은 autolink literal, strikethrough, table, task list를 추가한다. Footnote는 GFM spec이 아니라 현재 parser stack에서 지원하는 호환 확장으로 분류한다.

현재 `NoteEditor`는 CodeMirror의 Markdown과 selection을 1-base inclusive line target으로 변환해 Agent panel까지 전달한다. selection이 없으면 cursor가 속한 ATX heading section을 `current_section`으로 계산하고, heading이 없으면 `whole_document`를 사용한다. Agent panel은 편집 context가 있으면 `POST /api/workspaces/{workspace_id}/agent/turn`으로 요청 snapshot을 보내고, 없으면 기존 Wiki query 흐름을 사용한다. `markdown_edit` 응답은 line diff와 렌더링 preview에서 Apply/취소/재생성을 제공하고, document·base version·target·현재 buffer가 모두 유효할 때만 editor와 autosave에 반영한다. `markdown_create` 응답은 새 editable Markdown 문서로 저장해 연다. Spring backend의 Agent endpoint는 아직 구현되지 않았다.

## 4. 기본 지원 범위

기본 지원 기준은 `CommonMark + GFM`으로 고정한다. “모든 Markdown”처럼 구현체마다 의미가 달라지는 표현은 사용하지 않는다.

공식 지원 계약은 다음과 같다.

- 저장 원본은 변환하지 않은 raw Markdown 텍스트다.
- 기본 block/inline 문법과 parsing 규칙은 CommonMark를 따른다.
- GFM 확장 중 autolink literal, strikethrough, table, task list를 기본 지원한다.
- Footnote, math, Wiki link, citation과 frontmatter는 GFM 자체가 아니라 Fruition 호환 확장으로 구분한다.
- Raw HTML과 MDX는 공식 지원 범위에서 제외하며 renderer 실행 경로에 포함하지 않는다.

### 4.1 바로 지원할 문법

| 문법 | 예시 | 현재 renderer 기반 | sLLM 생성 적합성 |
| --- | --- | --- | --- |
| 제목 | `# 제목` | 가능 | 높음 |
| 일반 문단 | 일반 텍스트 | 가능 | 높음 |
| 굵게 | `**중요**` | 가능 | 높음 |
| 기울임 | `*강조*` | 가능 | 높음 |
| 취소선 | `~~삭제~~` | 가능 | 높음 |
| 인라인 코드 | `` `code` `` | 가능 | 높음 |
| fenced code block | ` ```python ` | 가능 | 높음 |
| 인용문 | `> 인용` | 가능 | 높음 |
| bullet 목록 | `- 항목` | 가능 | 높음 |
| 번호 목록 | `1. 항목` | 가능 | 높음 |
| task list | `- [ ] 작업` | 가능 | 높음 |
| 링크 | `[이름](../../../../docs/backlog/spec/URL)` | 가능 | 높음 |
| 이미지 URL | `![설명](../../../../docs/backlog/spec/URL)` | 가능 | 높음 |
| 구분선 | `---` | 가능 | 높음 |
| 표 | GFM table | 가능 | 높음 |
| 자동 링크 | `https://example.com` | 가능 | 높음 |
| Wiki link | `[[page]]` | 프로젝트 plugin으로 가능 | 높음 |
| Citation | `[1]` | 프로젝트 plugin으로 가능 | 높음 |
| Frontmatter | `---`로 감싼 metadata | 별도 UI로 가능 | 높음 |

“가능”은 renderer와 현재 회귀 fixture가 해당 문법을 보존한다는 뜻이다. 문서는 전체 parse context에서 처리하고, source block ID는 AST 원문 위치를 기준으로 부여한다.

### 4.2 편집 도우미가 제공할 수 있는 요청

sLLM은 위 문법을 이용해 다음 요청을 처리할 수 있다.

- 중요한 문장을 굵게 표시
- 참고 내용을 인용문으로 변경
- 명령어나 예제를 code block으로 변경
- 작업 항목을 checklist로 변경
- 비교 내용을 표로 변경
- 긴 문단을 bullet 또는 번호 목록으로 변경
- 제목과 하위 제목을 추가해 문서 구조 정리
- 링크, code fence, 표를 유지하면서 문장 정리
- Markdown 문법 오류 수정
- 선택 영역 번역, 축약 또는 어조 변경

이 기능은 새로운 모델보다 prompt 규칙, fixture, 결과 검증이 더 중요하다.

## 5. renderer plugin보다 먼저 보완할 항목

### 5.1 Markdown 분할 구조

현재 `splitMarkdownBlocks()`는 Markdown을 문자열 조각으로 분리하고 각 조각을 별도의 `ReactMarkdown`에 전달한다. 이 구조에는 다음 제약이 있다.

#### 중첩 목록 들여쓰기 손실

목록 항목을 `trim()`해서 수집하므로 다음 구조의 들여쓰기가 손실될 수 있다.

```markdown
- 상위 항목
  - 하위 항목
    - 세부 항목
```

중첩 목록을 지원하려면 원본 leading whitespace를 보존해야 한다.

#### 복합 목록 구조 분리

목록 항목 아래의 문단, code block, 인용문 또는 다른 목록은 부모 목록과 별도 segment로 나뉠 수 있다.

````markdown
1. 설치

   ```bash
   npm install
   ```

2. 실행
````

이 구조를 안정적으로 지원하려면 문자열 정규식보다 Markdown AST 기준으로 block을 식별하는 방식이 적합하다.

#### 문서 전체 문맥 손실

각 segment를 별도로 parse하면 다음 기능은 reference와 definition이 서로 다른 parse tree에 놓일 수 있다.

- Footnote reference와 footnote definition
- Reference-style link와 link definition
- 여러 block에 걸친 복합 구조

`remark-gfm`은 footnote 문법을 지원하지만 현재 분할 방식에서는 정상 동작을 보장할 수 없다.

### 5.2 권장 방향

Markdown 전체를 한 번 parse한 AST를 기준으로 렌더링하고, citation highlight에 필요한 block wrapper와 `B0001` 같은 block ID를 AST transform 단계에서 부여하는 방향을 우선 검토한다.

기존 backend block ID 계약 때문에 전체 전환이 어렵다면 최소한 다음을 보장해야 한다.

- 원본 들여쓰기 보존
- list container가 끝날 때까지 하나의 segment로 유지
- code fence로 백틱과 tilde 지원
- H1부터 H6까지 동일한 block 경계 처리
- footnote와 reference definition이 포함된 문서는 하나의 parse context로 유지
- 기존 citation block ID 순서와의 호환성 검증

## 6. renderer plugin 확장 범위

### 6.1 우선 도입 후보

| 기능 | 구현 방식 | sLLM 역할 | 판단 |
| --- | --- | --- | --- |
| Code syntax highlighting | `rehype-starry-night`, `rehype-highlight` 또는 Prism 계열 | 언어가 포함된 code fence 생성 | 권장 |
| 수학 수식 | `remark-math` + `rehype-katex` 또는 MathJax | LaTeX 생성 | 문서 성격에 따라 권장 |
| Heading anchor | heading slug/autolink plugin | 없음 | 선택 |
| 자동 목차 | heading AST 수집 | 목차를 직접 생성하지 않아도 됨 | 선택 |

수식은 기본 Markdown이 아니라 syntax extension이다. KaTeX를 사용할 경우 stylesheet와 수식 오류 처리도 함께 필요하다.

### 6.2 선택 도입 후보

| 기능 | 구현 방식 | sLLM 적합성 | 주의점 |
| --- | --- | --- | --- |
| Mermaid | `mermaid` code fence custom renderer | 중간 | parse 실패 fallback 필요 |
| Emoji shortcode | remark plugin | 높음 | Unicode emoji로 대체 가능 |
| Admonition | `remark-directive` + custom component | 높음 | 범용 Markdown 이식성 저하 |
| 접기/펼치기 | directive + custom component | 높음 | Notion식 block으로 확장되지 않게 제한 |

Mermaid는 Markdown parser plugin만으로 끝나지 않는다. `mermaid` code fence를 감지해 client-side diagram component로 렌더링하고, 유효하지 않은 diagram은 원본 code block으로 표시해야 한다.

### 6.3 제외 권장

| 기능 | 제외 이유 |
| --- | --- |
| Raw HTML | XSS 방어와 sanitize 정책이 추가되고 문서 이식성이 낮아짐 |
| MDX | 임의 component와 expression 실행 범위가 문서 편집 도우미에 과도함 |
| Notion Callout/Column/Synced block 복제 | 일반 Markdown 목표와 맞지 않음 |
| block drag and drop | renderer plugin이 아니라 editor 제품 기능 |
| iframe/embed 자동 생성 | 보안, CSP, 외부 서비스 정책이 필요함 |

Raw HTML을 도입해야 한다면 `rehype-raw`만 추가해서는 안 되며 허용 tag와 attribute를 제한하는 sanitize 정책이 필요하다.

## 7. sLLM과 애플리케이션의 책임 경계

### 7.1 sLLM이 담당할 수 있는 것

- 자연어 편집 의도 분류
- Markdown 본문 생성
- 형식 변환
- 문장 교정, 요약, 번역, 어조 변경
- 표, checklist, 인용문, code fence 생성
- 수식과 Mermaid source 생성
- 기존 링크, 이미지 URL, code fence와 표 보존

### 7.2 renderer가 담당할 것

- Markdown parse와 React element 렌더링
- GFM 문법 처리
- 수식, diagram, code highlighting 표시
- 안전하지 않은 HTML 차단
- 렌더링 실패 fallback

### 7.3 애플리케이션이 담당할 것

- 선택 영역과 현재 문서 전달
- diff와 preview
- Apply, 취소, 재생성
- 문서 저장과 version 충돌 확인
- 이미지와 파일 업로드
- 권한, 댓글, 변경 이력, 공동 편집
- 편집 operation 적용

이미지 Markdown 생성과 실제 이미지 업로드는 구분해야 한다. sLLM은 `![설명](../../../../docs/backlog/spec/URL)`을 생성할 수 있지만 로컬 파일 업로드와 URL 발급은 애플리케이션 API가 수행해야 한다.

## 8. 편집 operation 확장

CommonMark/GFM 지원과 편집 operation은 별개의 문제다. 현재 `replace`만으로도 문서 편집 MVP는 가능하지만, 이어 쓰기와 여러 위치 수정을 안정적으로 지원하려면 다음 확장을 검토한다.

| Operation | 용도 | 우선순위 |
| --- | --- | --- |
| `replace` | 선택 영역 또는 문서 전체 교체 | 구현됨 |
| `insert_after` | 이어 쓰기, 섹션 아래 내용 추가 | 구현됨 |
| `insert_before` | 문서 앞 요약 또는 안내 추가 | 중간 |
| `delete` | 중복 문단이나 선택 영역 삭제 | 중간 |
| `multi_replace` | 용어 통일, 여러 위치 동시 수정 | 후순위 |

현재는 `replace + insert_after`로 제한한다.

## 9. 단계별 구현 범위

### 1단계: 현재 편집 기능 연결

- [x] editor의 Markdown과 selection/current section 전달
- [x] frontend `/agent/turn` client와 제출 분기
- [ ] Spring backend Agent endpoint와 pipeline proxy
- [x] 원본과 `replacement_markdown` line diff·렌더링 preview 표시
- [x] Apply/취소/최신 snapshot 재생성
- [x] 사용자 승인 후 editor buffer 교체와 autosave 연결
- [x] 적용 전 document·base version·target·현재 buffer 검증
- [x] 요약, 번역, 어조 변경, cleanup, 표, checklist, 회의록 frontend fixture 검증

### 2단계: Markdown 기본 지원 안정화

- [x] CommonMark + GFM을 공식 지원 범위로 선언
- [x] 중첩 목록 들여쓰기 보존
- [x] 목록 안의 code block, 인용문과 하위 목록 지원
- [x] Footnote와 reference-style link 검증
- [x] H1~H6와 백틱/tilde code fence 검증
- [x] 표, task list, link, image 보존 fixture 추가
- [x] sLLM 출력 Markdown parse 검증

### 3단계: 선택적 renderer 확장

- [ ] Code syntax highlighting
- [ ] 문서 요구가 있으면 KaTeX 수식
- [ ] 필요하면 heading anchor와 자동 목차
- [ ] diagram 요구가 확인되면 Mermaid와 parse failure fallback
- [ ] Raw HTML과 MDX는 도입하지 않음

### 4단계: 편집 정확도 확장

- [x] `insert_after` 추가
- [ ] 필요할 때 `insert_before`, `delete` 추가
- [ ] 장문 문서를 section 단위로 분할해 model context 구성
- [ ] 여러 편집 결과 preview와 부분 Apply
- [ ] 사용자 또는 문서 종류별 style guide context 적용
- [ ] 사실 보존, Markdown 구조 보존, latency 평가

## 10. 지원 범위 요약

### 구현 가능하고 권장하는 범위

- CommonMark와 GFM 기반 문서 생성·편집
- 선택 영역, 섹션, 문서 전체의 자연어 편집
- 요약, 번역, 교정, 어조 변경, 구조화
- 표, checklist, 인용문, code block 변환
- 대화 context 기반 새 문서 생성
- 수식과 code highlighting plugin
- 필요성이 확인된 경우 Mermaid

### 구현 가능하지만 애플리케이션 작업이 필요한 범위

- 이미지와 파일 업로드
- 이어 쓰기와 위치 기반 삽입
- 여러 위치 동시 수정
- diff, Apply, 재생성과 부분 적용
- 문서 version 충돌 방지

### 현재 목표에서 제외하는 범위

- Notion식 block editor와 database UI (`docs/spec/note-editor-prototype.md`의 Markdown 원문 편집 UI와는 별도)
- block drag and drop
- Callout, Column, Synced block 복제
- Raw HTML과 MDX 실행
- 데이터베이스, 권한, 댓글과 외부 서비스 조작

## 11. qwen2.5:7b Markdown/GFM 생성 실험

### 11.1 실험 환경

실험일은 2026-07-14이며 로컬 Ollama의 `qwen2.5:7b`를 사용했다.

```text
Endpoint: http://127.0.0.1:11434/v1/chat/completions
Model: qwen2.5:7b
Temperature: 0.2
Flow: AgentTurnRouter -> MarkdownEditor
```

평가 코드는 `llmPipeline/markdown_edit_gfm_lab.py`에 추가했다. 실제 모델을 호출하지 않고 판정 규칙을 검증하는 테스트는 `llmPipeline/tests/modules/markdown_edit/test_markdown_edit_gfm_lab.py`에 있다.

### 11.2 평가 케이스

| Case | 확인 대상 |
| --- | --- |
| `emphasis_quote` | 굵게와 blockquote 생성, 원문 사실 보존 |
| `nested_list` | 일반 중첩 bullet과 들여쓰기, checkbox 비사용 |
| `preserve_code_link` | bash code fence와 링크 보존 |
| `footnote` | Footnote reference와 definition 보존 |
| `table` | GFM table과 원문 값 보존 |
| `task_list` | 모든 작업의 `- [ ]` 변환 |

### 11.3 baseline과 보강 결과

초기 editor 직접 호출은 6개 중 5개가 통과했다. 실패로 표시된 footnote 케이스는 `smoke test`를 `스모크 테스트`로 바꾼 것을 evaluator가 정보 누락으로 판정한 문제였으므로 동등 표현을 허용하도록 evaluator를 수정했다.

재검토 과정에서 실제 불안정성이 두 가지 확인됐다.

1. 일반 중첩 bullet 요청이 간헐적으로 task list로 생성됐다.
2. Footnote가 간헐적으로 inline link로 변환됐다.

일반 목록과 checklist의 prompt 규칙만 강화했을 때 중첩 목록은 반복 3회 중 1회 다시 task list로 생성됐다. prompt 금지 문장만 추가하는 방식으로는 안정성이 부족했다.

이에 일반 목록을 독립 `edit_goal=bullet_list`로 분리했다. router는 plain bullet 또는 nested list 요청을 `bullet_list`로, TODO·checkbox·checklist 요청만 `checklist`로 분류한다. 또한 Markdown 구조를 명시적으로 요구하는 table, blockquote, heading, code block 요청은 `style_change`가 아니라 `convert_format`으로 분류하도록 경계를 명확히 했다.

Footnote는 reference와 definition을 그대로 유지하고 inline link로 바꾸지 않는 규칙을 editor prompt에 추가했다.

### 11.4 최종 결과

최종 router→editor 전체 흐름은 6개 중 6개가 통과했다.

| Case | Route edit goal | 결과 | 실행 시간 |
| --- | --- | --- | ---: |
| `emphasis_quote` | `convert_format` | 통과 | 2.35초 |
| `nested_list` | `bullet_list` | 통과 | 2.70초 |
| `preserve_code_link` | `style_change` | 통과 | 2.92초 |
| `footnote` | `style_change` | 통과 | 2.81초 |
| `table` | `convert_format` | 통과 | 2.73초 |
| `task_list` | `checklist` | 통과 | 2.23초 |

추가 반복 검증 결과:

- Footnote 보존: 3/3 통과
- `bullet_list` editor 직접 호출: 3/3 통과
- 굵게와 blockquote router→editor: 3/3 통과

이 결과는 짧은 fixture에서 sLLM이 Markdown/GFM을 생성하고 보존할 수 있는지를 확인한 것이다. 장문 문서, 여러 구조가 섞인 문서, renderer의 실제 DOM 출력은 아직 검증하지 않았다. 특히 `MarkdownViewer.splitMarkdownBlocks()`의 중첩 목록과 문서 전체 reference 문맥 문제는 별도 프론트 작업으로 남아 있다.

재현 명령:

```bash
cd llmPipeline
.venv/bin/python markdown_edit_gfm_lab.py --with-router
```

특정 case만 실행할 수 있다.

```bash
.venv/bin/python markdown_edit_gfm_lab.py --case footnote --with-router
```

### 11.5 단일 prompt 전체 기능 확장 실험

기본 6개 이후 평가 범위를 17개로 확장했다.

- 제목, 굵게, 기울임, 취소선
- 번호 목록과 inline code
- 이미지 Markdown과 구분선 보존
- Frontmatter 보존
- 회의록, 번역, 축약
- Display math와 Mermaid source
- Frontmatter, heading, link, footnote, code fence, table이 섞인 문서 보존

Renderer가 자동으로 담당하는 syntax highlighting, heading anchor, 실제 KaTeX/Mermaid 렌더링은 sLLM prompt와 평가 대상에서 제외했다. 수식과 Mermaid는 renderer가 처리할 수 있는 source 문법 생성까지만 평가했다.

모든 sLLM 규칙을 기능별 prompt로 분리하지 않고 하나의 `markdown_edit.system.md`에 넣었다.

```text
Editor prompt: 5,308 chars, 5,364 UTF-8 bytes
Router prompt: 2,758 chars, 2,790 UTF-8 bytes
두 prompt는 서로 다른 LLM 호출에서 사용됨
```

확장 전 prompt로 17개를 한 번 실행한 baseline은 8/17 통과였다. 단일 prompt에 번호 목록, blockquote, inline style, frontmatter, 구조 보존, 수식, Mermaid, 번역과 축약 규칙을 추가한 뒤 17개를 3회씩 실행했다.

최종 결과는 33/51, 64.7% 통과였다.

| 분류 | 기능 | 반복 결과 |
| --- | --- | ---: |
| 안정 | 굵게+인용문 | 3/3 |
| 안정 | 중첩 bullet | 3/3 |
| 안정 | Code fence+링크 보존 | 3/3 |
| 안정 | 표 | 3/3 |
| 안정 | Checklist | 3/3 |
| 안정 | 제목+인라인 style | 3/3 |
| 안정 | Inline code | 3/3 |
| 안정 | 회의록 | 3/3 |
| 안정 | 번역 | 3/3 |
| 불안정 | Footnote 보존 | 1/3 |
| 불안정 | 축약 | 2/3 |
| 불안정 | Mermaid source | 1/3 |
| 불안정 | 혼합 Markdown 보존 | 2/3 |
| 실패 | 번호 목록 | 0/3 |
| 실패 | 이미지 alt text+구분선 보존 | 0/3 |
| 실패 | 단순 Frontmatter 보존 | 0/3 |
| 실패 | Code fence 없는 display math | 0/3 |

기능별 평균 실행 시간은 약 1.8~3.5초였고, 반복 평가의 최대 실행 시간은 3.73초였다.

주요 실패 형태:

- 번호 목록을 `1.`이 아니라 `- 1.` 또는 일반 bullet로 생성
- 이미지 URL은 유지하지만 alt text를 제거
- Frontmatter의 닫는 `---`를 제거
- `$$` 수식을 Markdown code fence 안에 넣어 KaTeX 대상에서 제외
- Cleanup 요청에 원문에 없던 bullet marker 추가
- 단순 Mermaid 흐름에 조건 분기를 추가
- Table cell의 `ready` 같은 literal 값을 번역

결론:

1. 모든 기능 규칙을 하나의 prompt에 넣는 것은 prompt 크기와 context 관점에서는 가능하다.
2. 현재 5.3K 문자 prompt는 32K context의 주된 소비자가 아니다. 긴 문서 본문이 더 큰 비중을 차지한다.
3. 그러나 `qwen2.5:7b`에서는 단일 prompt만으로 전체 기능을 안정적으로 보장할 수 없다.
4. 실패 대부분은 context 초과가 아니라 exact syntax와 verbatim 보존 지시를 따르지 않는 문제다.
5. Prompt를 더 길게 만드는 대신 protected structure masking/restoration, format별 deterministic validator, 제한적 retry 또는 명확한 format subtype이 필요하다.
6. 위 정확성 보강 후 장문 context 실험과 selection context slicing을 진행한다.

반복 재현 명령:

```bash
cd llmPipeline
.venv/bin/python markdown_edit_gfm_lab.py --with-router --repeat 3 --failures-only
```

### 11.6 문법 계약 보강

단일 prompt 실험에서 확인된 exact syntax 무시를 prompt 문장만으로 해결하지 않고 편집 adapter에 출력 계약을 추가했다.

- `cleanup`, `style_change` 요청에서는 frontmatter, code fence, GFM table, link, image, footnote definition, divider를 보호 token으로 치환한 뒤 모델 결과에 원문을 복원한다.
- 보호 token의 누락·중복, checklist·일반 bullet·번호 목록·blockquote·회의록 section·display math·Mermaid 문법을 deterministic validator로 검사한다.
- 첫 출력이 계약을 어기면 이전 출력과 실패 이유를 전달해 한 번만 재시도한다.
- 두 번째 출력도 실패하면 잘못된 Markdown을 반환하지 않고 `MarkdownOutputContractError`로 종료한다.
- 위치가 확정적인 frontmatter와 footnote definition 줄바꿈, 명확한 footnote marker 오타, display math 외부 code fence는 의미 추론 없이 결정적으로 복구한다.

구현 위치:

- 보호·복원·검증: `llmPipeline/app/modules/markdown_edit/domain/markdown_output_contract.py`
- 편집과 제한적 retry: `llmPipeline/app/modules/markdown_edit/infrastructure/chat_completions_markdown_editor.py`
- 회귀 테스트: `llmPipeline/tests/modules/markdown_edit/test_markdown_output_contract.py`, `test_chat_completions_markdown_editor.py`

첫 전체 재평가는 45/51을 기록했다. 이후 실패 원인이 확인된 각주, 다중 필드 frontmatter, 회의록 section, display math를 보정한 집중 재평가는 12/12 통과했다. 최종 전체 재평가는 50/51, 98.0%를 기록했다. 유일한 실패는 인라인 style 요청을 `style_change`로 routing한 한 번의 출력에서 대상어를 중국어로 바꾸고 굵게·기울임 문법을 누락한 경우였다. 제목·굵게·기울임·취소선 validator를 추가한 뒤 해당 case 집중 재평가는 3/3 통과했다.

Prompt 크기는 editor 5,476자, router 2,758자다. 따라서 이번 결과도 context 길이보다 sLLM의 문법 준수와 literal 보존이 우선 문제라는 기존 결론을 유지한다. 보호·검증은 이 문제를 줄이지만, 일반 사실 보존과 장문 context slicing은 다음 단계로 남는다.

### 11.7 Source-range 보존형 편집

Regex 보호 token보다 구조 변경 가능성을 더 줄이기 위해 `cleanup`, 비구조 `style_change`, `translate`에 source-range 편집 경로를 추가했다. 외부 `MarkdownEditResult`는 그대로 유지하지만, 내부 LLM 출력은 전체 Markdown이 아니라 text segment edit 목록이다.

```text
Markdown 원문
  -> CommonMark block/inline token 분석
  -> 편집 가능한 원문 character range 추출
  -> sLLM: [{id, replacement}]
  -> 원문 range를 뒤에서부터 치환
  -> 구조 fingerprint 재검증
```

Parser 선택 과정에서 source byte 위치를 직접 제공하는 `tree-sitter-markdown`을 검토했지만, 공식 설명이 정확성이 중요한 용도에 권장하지 않는다고 명시해 채택하지 않았다. 대신 CommonMark 준수 parser인 `markdown-it-py`로 block과 inline 구조를 판정하고, token content를 원문 cursor에 대조해 character range를 찾는다. inline mapping이 모호하면 source-range 경로를 사용하지 않고 기존 보호·검증 경로로 fallback한다.

`cleanup`과 비구조 `style_change`의 잠금 대상:

- Frontmatter, heading text, code block, table, divider와 HTML
- Link 전체, image, inline code, footnote reference와 definition
- Display math와 한국어 문장 안의 영문 literal
- Markdown marker, URL과 원문 segment 바깥의 모든 문자

`translate`는 URL, Markdown marker, code, frontmatter key, footnote ID를 잠그면서 heading, link label, list/blockquote text, table cell, footnote 본문을 번역 segment로 연다. 목표 언어와 다른 source-language segment ID는 모두 필수 응답으로 검증한다.

사용자가 제목, 굵게, 목록, 표, 인용문, 수식 같은 구조 변경을 명시하면 source-range 경로를 사용하지 않는다. 별도 LLM router를 추가하지 않고 `edit_goal`과 instruction의 구조 변경 표현을 코드로 판정한다.

Source-range 전용 prompt는 최초 867자였으며 번역 필수 segment 규칙 추가 후 1,065자다. 5,594자 전체 Markdown 생성 prompt와 분리했다. 첫 실험에서 두 출력 schema를 하나의 prompt에 넣었을 때 `qwen2.5:7b`가 `edits`를 `replacement_markdown` 아래에 중첩해 0/3 실패했기 때문이다. 코드가 편집 모드에 따라 prompt를 직접 선택하므로 router 정확도에는 의존하지 않는다.

최종 17개 case 3회 평가는 50/51이었다. Source-range가 담당한 code+link, footnote, image+divider, frontmatter, 혼합 Markdown 보존은 모두 3/3 통과했다. 유일한 실패는 기존 `shorten` 경로가 `시작 안내`를 `시작 방법`으로 바꾼 동의 표현을 evaluator가 정보 누락으로 판정한 것으로 Markdown 구조 실패는 아니었다. `shorten`이 요청하지 않은 list marker를 추가하는 문제는 validator 적용 후 차단됐다.

구현 위치:

- Range 추출·치환·fingerprint: `llmPipeline/app/modules/markdown_edit/infrastructure/markdown_source_range.py`
- 전용 prompt: `llmPipeline/prompts/markdown_source_edit.system.md`
- Editor 분기: `llmPipeline/app/modules/markdown_edit/infrastructure/chat_completions_markdown_editor.py`
- 테스트: `llmPipeline/tests/modules/markdown_edit/test_markdown_source_range.py`

### 11.8 Pipeline 내부 범위 확장

선택 영역 안전성, 번역, 축약과 오류 경계를 추가로 보강했다.

#### Target 경계와 context slicing

- `selection`과 `current_section`은 1-base inclusive `start_line~end_line` fragment만 편집 대상으로 전달한다.
- 선택 범위 전후는 `read_only_context`로만 전달하며 replacement에 포함할 수 없다.
- 기본 주변 문맥은 앞뒤 각 20줄이고 `MARKDOWN_EDIT_CONTEXT_LINES`로 조정할 수 있다.
- `target.end_line`이 실제 문서 line 수를 넘으면 LLM을 호출하기 전에 거절한다.
- `whole_document`는 원문을 그대로 편집 범위로 사용한다.

#### 번역과 축약

- 일반 번역과 Markdown 구조가 섞인 번역을 source-range 경로로 처리한다.
- 번역 대상 source-language segment가 누락되거나 replacement에 URL을 생성하면 한 번 재시도한다.
- 축약은 segment 삭제·병합이 필요하므로 생성형 target-fragment 경로를 유지한다.
- 축약에서도 frontmatter, code, table, link, image, footnote와 divider를 보호한다.
- 숫자·단위, URL, 대문자/underscore/camelCase identifier를 literal anchor로 검사한다.
- 한 문장, 길이 감소, 요청하지 않은 list marker 금지 조건을 deterministic validator로 검사한다.
- 일반 동의 표현까지 같은 의미인지 판단하는 별도 LLM evaluator는 추가하지 않았다.

#### 오류 계약

두 번째 router 출력도 action 계약을 통과하지 못하면 `/agent/turn`은 HTTP 422와 `agent_turn_route_contract_failed` code를 반환한다. 두 번째 편집 출력이 Markdown 계약을 통과하지 못하면 `markdown_output_contract_failed` code를 반환한다. 내부 token 이름, 실패 세부 내용과 잘못된 model 출력은 응답과 기본 로그에 노출하지 않는다. 성공 응답 계약은 변경하지 않았다.

평가 case는 17개에서 structured translation과 anchor-preserving shortening을 포함한 19개로 늘었다. 당시 `qwen2.5:7b` router→editor 3회 반복 결과는 56/57, 98.2%였다. 18개 case는 모두 3/3 통과했다. 유일한 실패는 축약에서 `시작 안내`를 `시작 방법`으로 바꾼 결과를 exact 문자열 evaluator가 정보 누락으로 본 것으로, Markdown 구조나 literal anchor 위반은 아니었다.

### 11.9 선택 경계, 실제 HTTP E2E와 장문 context 검증

선택 영역이 여러 줄 Markdown 구조의 내부만 자르면 구조를 직렬화하거나 모델에 보내기 전에 거절한다. 현재 분리 불가능한 구조로 다루는 대상은 fenced/indented code block, HTML block, GFM table, frontmatter, 여러 줄 footnote definition과 display math다. 선택 범위가 구조 전체를 포함하는 경우에는 허용한다.

`/agent/turn`의 경계 오류 응답은 HTTP 422와 `markdown_target_crosses_structure` code를 사용하며, 충돌한 구조 종류와 전체 line 범위를 함께 반환한다. 이 판정은 backend나 frontend가 아니라 `llmPipeline` 내부에서 수행한다.

실제 FastAPI `TestClient` 요청에 로컬 `qwen2.5:7b` router와 editor를 연결한 E2E 3건을 추가했다.

| 시나리오 | 결과 |
| --- | ---: |
| 선택 문장만 cleanup하고 주변 context를 replacement에서 제외 | 통과 |
| 전체 문서 번역에서 URL과 code fence 보존 | 통과 |
| code fence 내부 일부만 선택한 요청을 422로 차단 | 통과 |

첫 E2E에서 cleanup 결과에 원문에 없던 한자가 섞이는 문제가 재현됐다. 한국어 `cleanup`, `style_change`, `shorten` 원문에 한자가 없는데 결과에 새 한자가 생기면 계약 실패로 판정하도록 보강했다. 같은 E2E 재실행에서는 첫 출력을 재시도해 정상 한국어로 복구했고 3/3 통과했다.

장문 문서에서는 전체 문서가 아니라 target 한 줄과 앞뒤 각 20줄만 model request payload에 포함되는지 별도 benchmark로 확인했다.

| 문서 크기 | 원문 문자 수 | model request payload | 원문 대비 | 평균 전처리 시간 | p95 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000줄 | 31,999 | 1,786자 | 5.58% | 6.828ms | 7.706ms |
| 5,000줄 | 159,999 | 1,788자 | 1.12% | 33.539ms | 34.366ms |

따라서 선택 편집의 model context는 문서 길이에 비례해 증가하지 않는다. 다만 구조 경계 검사를 위해 전체 문서를 parser가 한 번 읽으므로 애플리케이션 전처리 시간은 문서 길이에 선형으로 증가한다. 5천 줄에서 약 33ms로 현재 실험 범위에서는 병목으로 보이지 않는다.

최종 전체 자동 테스트는 220개와 subtest 28개가 통과했다. 최신 19개 case 3회 Qwen 반복 평가는 55/57이었다. 두 실패 모두 축약 결과의 `시작 방법`을 evaluator가 원문의 exact 문자열 `시작 안내` 누락으로 판단한 경우이며, Markdown 구조·문법·literal anchor 실패는 없었다.

재현 도구:

- 실제 HTTP와 Qwen E2E: `llmPipeline/markdown_agent_http_lab.py`
- 1천/5천 줄 context benchmark: `llmPipeline/markdown_context_benchmark.py`
- 선택 경계 구현: `llmPipeline/app/modules/markdown_edit/infrastructure/markdown_source_range.py`, `validate_markdown_target_boundary`

## 12. 참고 자료

- 프로젝트 계약: `docs/spec/agent-markdown-contract.md`
- Markdown 편집 prompt: `llmPipeline/prompts/markdown_edit.system.md`
- 현재 renderer: `frontend/app/_components/MarkdownViewer.tsx`
- [react-markdown 공식 문서](https://remarkjs.github.io/react-markdown/)
- [remark-gfm 공식 저장소](https://github.com/remarkjs/remark-gfm)
- [remark-math와 rehype-katex 공식 저장소](https://github.com/remarkjs/remark-math)
- [markdown-it-py 공식 문서](https://markdown-it-py.readthedocs.io/)
- [tree-sitter-markdown 공식 저장소](https://github.com/tree-sitter-grammars/tree-sitter-markdown)
