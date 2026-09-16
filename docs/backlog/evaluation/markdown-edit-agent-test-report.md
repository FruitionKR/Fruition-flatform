# Markdown Edit Agent 테스트 리포트

작성일: 2026-06-28

## 범위

이번 테스트는 `llmPipeline`에 추가한 agent turn / markdown edit 흐름의 동작 계약을 확인했다.

검증 대상:

- `/agent/turn` 응답 구조
- `chat_answer | markdown_edit | clarify | reject` 분기
- Markdown 편집 요청의 `replace` operation 생성
- 선택 영역이 없을 때 clarify 처리
- template 기반 전체 문서 재구성 요청 보류
- 멀티턴에서 애매한 요청을 편집 요청으로 처리할 수 있는 구조

주의:

- 실제 LLM 호출 결과가 아니라 fake router/editor로 코드 경로와 응답 계약을 검증했다.
- 실제 모델 라우팅 품질은 `AGENT_ROUTER_LLM_API_KEY`, `MARKDOWN_EDIT_LLM_API_KEY` 또는 `UPSTAGE_API_KEY`가 설정된 환경에서 추가 확인이 필요하다.

## 자동 테스트 결과

실행 명령:

```bash
cd services/ai/pipeline
.venv/bin/python -m pytest tests/modules/markdown_edit tests/modules/agent -v
```

결과:

```text
tests/modules/markdown_edit/test_generate_markdown_edit.py::GenerateMarkdownEditUseCaseTest::test_rejects_empty_replacement_markdown PASSED
tests/modules/markdown_edit/test_generate_markdown_edit.py::GenerateMarkdownEditUseCaseTest::test_returns_replace_operation_for_requested_target PASSED
tests/modules/agent/test_handle_agent_turn.py::HandleAgentTurnUseCaseTest::test_asks_for_target_when_edit_has_no_markdown_target PASSED
tests/modules/agent/test_handle_agent_turn.py::HandleAgentTurnUseCaseTest::test_defers_template_transform PASSED
tests/modules/agent/test_handle_agent_turn.py::HandleAgentTurnUseCaseTest::test_executes_markdown_edit_action PASSED
tests/modules/agent/test_handle_agent_turn.py::HandleAgentTurnUseCaseTest::test_routes_chat_to_query_use_case PASSED

6 passed in 0.02s
```

전체 `llmPipeline` 테스트:

```bash
cd services/ai/pipeline
.venv/bin/python -m pytest
```

결과:

```text
47 passed in 0.28s
```

## 시나리오 테스트 결과

아래 시나리오는 fake router/editor를 사용해 실제 response schema 변환까지 통과시킨 결과다.

## Replace operation 적용 방식

현재 `llmPipeline`은 원본 파일이나 draft를 직접 수정하지 않는다. 대신 프론트가 적용할 수 있는 명령을 반환한다.

반환되는 핵심 명령:

```json
{
  "operation": "replace",
  "target": {
    "type": "selection",
    "start_line": 4,
    "end_line": 8
  },
  "replacement_markdown": "새 Markdown 내용"
}
```

프론트 적용 규칙:

```text
1. 현재 draft Markdown을 line 단위로 나눈다.
2. target.start_line ~ target.end_line 범위를 제거한다.
3. 같은 위치에 replacement_markdown을 삽입한다.
4. 적용 전/후를 diff 또는 preview로 보여준다.
5. 사용자가 Apply를 누를 때만 draft 상태에 반영한다.
```

주의:

- line number는 1-based다.
- `end_line`은 포함 범위다.
- 저장은 이 단계에서 하지 않는다.
- 실제 저장 API가 생기기 전까지는 프론트 draft에만 반영한다.

### 적용 예시 A. 선택 문단을 표로 변환

원본 Markdown:

```text
1  # Markdown AI Agent
2
3  ## MVP 범위
4  목표는 Markdown 편집 agent를 만드는 것이다.
5  먼저 선택 영역 편집부터 시작한다.
6  전체 문서 template 변환은 보류한다.
7  저장은 나중에 붙인다.
8
9  ## 다음 작업
10 프론트 preview와 diff를 검토한다.
```

operation:

```json
{
  "operation": "replace",
  "target": {
    "type": "selection",
    "start_line": 4,
    "end_line": 7
  },
  "summary": "선택 영역을 표 형식으로 변환했습니다.",
  "replacement_markdown": "| 항목 | 내용 |\n| --- | --- |\n| 목표 | Markdown 편집 agent 구현 |\n| 시작 범위 | 선택 영역 기반 편집 |\n| 보류 | 전체 문서 template 변환 |\n| 저장 | 후속 단계에서 처리 |"
}
```

적용 후 Markdown:

```text
1  # Markdown AI Agent
2
3  ## MVP 범위
4  | 항목 | 내용 |
5  | --- | --- |
6  | 목표 | Markdown 편집 agent 구현 |
7  | 시작 범위 | 선택 영역 기반 편집 |
8  | 보류 | 전체 문서 template 변환 |
9  | 저장 | 후속 단계에서 처리 |
10
11 ## 다음 작업
12 프론트 preview와 diff를 검토한다.
```

프론트가 보여줄 수 있는 diff 개념:

```diff
 ## MVP 범위
-목표는 Markdown 편집 agent를 만드는 것이다.
-먼저 선택 영역 편집부터 시작한다.
-전체 문서 template 변환은 보류한다.
-저장은 나중에 붙인다.
+| 항목 | 내용 |
+| --- | --- |
+| 목표 | Markdown 편집 agent 구현 |
+| 시작 범위 | 선택 영역 기반 편집 |
+| 보류 | 전체 문서 template 변환 |
+| 저장 | 후속 단계에서 처리 |

 ## 다음 작업
```

### 적용 예시 B. 선택 문단을 checklist로 변환

원본 Markdown:

```text
1  ## 구현 순서
2  Agent turn API를 만든다.
3  Markdown edit use case를 만든다.
4  프론트 preview와 diff를 연결한다.
5  Apply 전에는 원본을 바꾸지 않는다.
```

operation:

```json
{
  "operation": "replace",
  "target": {
    "type": "selection",
    "start_line": 2,
    "end_line": 5
  },
  "summary": "선택 영역을 TODO checklist로 변환했습니다.",
  "replacement_markdown": "- [ ] Agent turn API 추가\n- [ ] Markdown edit use case 추가\n- [ ] 프론트 preview/diff 연결\n- [ ] Apply 전 원본 불변 유지"
}
```

적용 후 Markdown:

```text
1  ## 구현 순서
2  - [ ] Agent turn API 추가
3  - [ ] Markdown edit use case 추가
4  - [ ] 프론트 preview/diff 연결
5  - [ ] Apply 전 원본 불변 유지
```

### 적용 예시 C. 애매한 멀티턴 요청

대화 맥락:

```text
사용자: 이 문단 너무 장황하지?
assistant: 핵심이 반복돼서 줄일 수 있습니다.
사용자: 그럼 그렇게 해줘
```

프론트가 `conversation_context.recent_conversation_summary`와 현재 선택 영역을 함께 보내면, agent는 아래와 같은 명령을 반환할 수 있다.

operation:

```json
{
  "operation": "replace",
  "target": {
    "type": "selection",
    "start_line": 3,
    "end_line": 5
  },
  "summary": "선택 문단을 간결하게 줄였습니다.",
  "replacement_markdown": "Markdown 편집 기능은 선택 영역 기반 replace operation부터 구현한다."
}
```

원본 Markdown:

```text
1  ## 방향
2
3  Markdown 편집 agent는 다양한 문서 편집 상황을 처리해야 한다.
4  다만 처음부터 전체 문서 재구성까지 포함하면 범위가 커진다.
5  그래서 선택 영역 기반 replace operation부터 구현하는 것이 좋다.
6
7  ## 보류
8  template 변환은 나중에 다룬다.
```

적용 후 Markdown:

```text
1  ## 방향
2
3  Markdown 편집 기능은 선택 영역 기반 replace operation부터 구현한다.
4
5  ## 보류
6  template 변환은 나중에 다룬다.
```

### 적용하지 않는 예시. Target 없음

편집 요청이지만 프론트가 선택 영역이나 현재 섹션 정보를 보내지 않으면 `llmPipeline`은 operation을 만들지 않는다.

응답:

```json
{
  "action": "clarify",
  "message": "수정할 Markdown 범위를 선택한 뒤 다시 요청해 주세요.",
  "chat": null,
  "edit": null
}
```

프론트 처리:

```text
1. 문서를 수정하지 않는다.
2. 사용자에게 선택 영역 또는 현재 섹션 지정이 필요하다고 표시한다.
3. 사용자가 범위를 선택한 뒤 같은 요청을 다시 보낼 수 있게 한다.
```

### 1. 표 변환

입력:

```text
이 부분을 표로 바꿔줘
```

결과:

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.91,
    "reason": "선택 영역에 대한 편집 요청입니다.",
    "edit_goal": "other"
  },
  "message": null,
  "chat": null,
  "edit": {
    "operation": "replace",
    "target": {
      "type": "selection",
      "start_line": 4,
      "end_line": 8
    },
    "summary": "선택 영역을 표 형식으로 변환했습니다.",
    "replacement_markdown": "| 항목 | 내용 |\n| --- | --- |\n| 목표 | Markdown 편집 기능 구현 |\n| 범위 | 선택 영역 기반 replace operation |"
  }
}
```

판단:

- `markdown_edit`으로 분기됐다.
- `replace` operation만 반환했다.
- target line range가 입력 그대로 보존됐다.

### 2. TODO checklist 변환

입력:

```text
TODO checklist로 바꿔줘
```

결과:

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.9,
    "reason": "체크리스트 형식 변환 요청입니다.",
    "edit_goal": "checklist"
  },
  "message": null,
  "chat": null,
  "edit": {
    "operation": "replace",
    "target": {
      "type": "selection",
      "start_line": 4,
      "end_line": 8
    },
    "summary": "선택 영역을 TODO checklist로 변환했습니다.",
    "replacement_markdown": "- [ ] Agent turn API 연결\n- [ ] Markdown edit preview 확인\n- [ ] Apply/Reject UX 검토"
  }
}
```

판단:

- 체크리스트 형식 편집도 동일한 `replace` 계약으로 처리 가능하다.

### 3. 간결화

입력:

```text
너무 장황해. 짧게 줄여줘
```

결과:

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.88,
    "reason": "선택 영역 축약 요청입니다.",
    "edit_goal": "shorten"
  },
  "message": null,
  "chat": null,
  "edit": {
    "operation": "replace",
    "target": {
      "type": "selection",
      "start_line": 4,
      "end_line": 8
    },
    "summary": "선택 문단을 간결하게 줄였습니다.",
    "replacement_markdown": "Markdown 편집 기능은 선택 영역 기반 replace operation부터 구현한다."
  }
}
```

판단:

- `shorten` 계열 편집도 동일한 흐름으로 처리된다.

### 4. 영어 번역 / 문체 변경

입력:

```text
영어 초록 스타일로 바꿔줘
```

결과:

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.86,
    "reason": "선택 영역 번역/문체 변경 요청입니다.",
    "edit_goal": "translate"
  },
  "message": null,
  "chat": null,
  "edit": {
    "operation": "replace",
    "target": {
      "type": "selection",
      "start_line": 4,
      "end_line": 8
    },
    "summary": "선택 문단을 영어로 번역했습니다.",
    "replacement_markdown": "Start with scoped Markdown edits based on the current selection, and defer full-document template transformation."
  }
}
```

판단:

- 번역/문체 변경도 selection 기반 편집으로 처리 가능하다.

### 5. 회의록 형식 변환

입력:

```text
회의록 형식으로 정리해줘
```

결과:

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.89,
    "reason": "선택 영역 형식 변경 요청입니다.",
    "edit_goal": "convert_format"
  },
  "message": null,
  "chat": null,
  "edit": {
    "operation": "replace",
    "target": {
      "type": "selection",
      "start_line": 4,
      "end_line": 8
    },
    "summary": "선택 문단을 회의록 형식으로 정리했습니다.",
    "replacement_markdown": "## 회의록\n\n- 논의 사항: Markdown 편집 agent 범위\n- 결정 사항: 선택 영역 기반 편집부터 진행\n- 보류 사항: template 기반 전체 문서 재구성"
  }
}
```

판단:

- 형식 변환은 `convert_format` 계열 edit goal로 다룰 수 있다.

### 6. 표현 다듬기

입력:

```text
말이 좀 어색한데 자연스럽게 다듬어줘
```

결과:

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.82,
    "reason": "선택 영역 문장 개선 요청입니다.",
    "edit_goal": "cleanup"
  },
  "message": null,
  "chat": null,
  "edit": {
    "operation": "replace",
    "target": {
      "type": "selection",
      "start_line": 4,
      "end_line": 8
    },
    "summary": "선택 문장의 표현을 자연스럽게 다듬었습니다.",
    "replacement_markdown": "Markdown 편집 기능은 선택 영역을 기준으로 먼저 구현하고, 전체 문서 template 변환은 후속 작업으로 분리한다."
  }
}
```

판단:

- 표현 개선처럼 가벼운 rewrite도 MVP 범위에 잘 맞는다.

### 7. 멀티턴 애매한 요청

이전 대화 요약:

```text
사용자는 선택 문단이 장황하다고 했고, assistant는 간결하게 줄일 수 있다고 답했다.
```

입력:

```text
그럼 그렇게 해줘
```

결과:

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.72,
    "reason": "최근 대화에서 선택 문단을 줄이자는 맥락이 있습니다.",
    "edit_goal": "shorten"
  },
  "message": null,
  "chat": null,
  "edit": {
    "operation": "replace",
    "target": {
      "type": "selection",
      "start_line": 4,
      "end_line": 8
    },
    "summary": "선택 영역을 요청에 맞게 수정했습니다.",
    "replacement_markdown": "현재 선택 영역을 요청 의도에 맞게 정리했습니다."
  }
}
```

판단:

- 멀티턴에서 애매한 발화를 `conversation_context`로 보강할 수 있는 구조다.
- 실제 모델 테스트에서는 이 케이스가 가장 중요하다.
- 모델이 `chat_answer`로 잘못 분류할 가능성이 있어 라우터 prompt와 평가셋 보강이 필요하다.

### 8. 편집 요청이지만 target 없음

입력:

```text
이 부분을 표로 바꿔줘
```

상태:

```text
active_markdown_context 없음
```

결과:

```json
{
  "action": "clarify",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.77,
    "reason": "편집 요청이지만 활성 선택 영역이 없습니다.",
    "edit_goal": "convert_format"
  },
  "message": "수정할 Markdown 범위를 선택한 뒤 다시 요청해 주세요.",
  "chat": null,
  "edit": null
}
```

판단:

- target이 없으면 edit을 실행하지 않는다.
- 프론트는 이 응답을 보고 selection/current_section 선택을 유도할 수 있다.

### 9. Template 변환 보류

입력:

```text
전체 문서를 회사 template에 맞춰줘
```

결과:

```json
{
  "action": "clarify",
  "route": {
    "action": "clarify",
    "confidence": 1.0,
    "reason": "template/full-document transform is deferred",
    "edit_goal": "template_transform"
  },
  "message": "현재는 선택 영역이나 현재 섹션 단위 편집만 지원합니다. template 기반 전체 문서 재구성은 이후 단계에서 다루겠습니다.",
  "chat": null,
  "edit": null
}
```

판단:

- 이번 MVP 범위에서 제외한 template 기반 전체 문서 재구성을 실행하지 않는다.
- 나중에 `template_transform` action을 추가할 자리는 남아 있다.

## 현재 결론

현재 구조는 편집 기능 MVP에 필요한 기본 계약을 충족한다.

확인된 점:

- 편집 요청은 `markdown_edit`으로 표현 가능하다.
- 다양한 편집 유형을 모두 `replace` operation 하나로 수용할 수 있다.
- target이 없으면 안전하게 `clarify`로 돌아간다.
- template/전체 문서 재구성은 보류된다.
- 멀티턴 애매한 발화도 구조적으로 처리 가능하다.

남은 리스크:

- 실제 LLM router가 애매한 멀티턴 요청을 안정적으로 `markdown_edit`으로 분류하는지 아직 검증하지 않았다.
- 실제 LLM editor가 `replacement_markdown`에서 원문 의미를 훼손하지 않는지 아직 검증하지 않았다.
- Markdown table, code fence, citation/link 보존 품질은 실제 모델 평가셋이 필요하다.

## 다음 검증 제안

실제 모델을 연결한 뒤 아래 케이스를 평가셋으로 고정하는 것이 좋다.

```text
1. “이 부분을 표로 바꿔줘”
2. “TODO checklist로 바꿔줘”
3. “너무 장황해. 짧게 줄여줘”
4. “영어 초록 스타일로 바꿔줘”
5. “회의록 형식으로 정리해줘”
6. “말이 좀 어색한데 자연스럽게 다듬어줘”
7. “그럼 그렇게 해줘”
8. “아까 말한 방식으로 바꿔줘”
9. “이 문서를 회사 template에 맞춰줘”
10. “전체 구조를 원문 PDF처럼 다시 만들어줘”
```

특히 7, 8번은 멀티턴 라우팅 품질을 보는 핵심 케이스다.

## Synthetic eval set 설계

사용자가 실제 예시를 미리 정의하지 않아도 prompt 품질을 볼 수 있도록 아래 범주를 고정 평가셋으로 둔다.

| 범주 | 예시 요청 | 기대 동작 | 실패 기준 |
| --- | --- | --- | --- |
| 명확한 축약 | `너무 장황해. 짧게 줄여줘` | 핵심 의미와 제약을 보존하며 짧게 rewrite | 의미 삭제, 메타 설명만 반환 |
| 명확한 구조 변환 | `표로 바꿔줘` | 원문 정보 기반 Markdown table 생성 | 빈 표, 원문에 없는 항목 추가 |
| Checklist 변환 | `TODO checklist로 바꿔줘` | 모든 항목이 `- [ ]` task list 문법 사용 | 일반 bullet, `TODO` 단어만 추가 |
| 회의록 변환 | `회의록 형식으로 정리해줘` | `논의 사항`, `결정 사항`, `보류 사항`, `다음 작업` 중 원문으로 채울 수 있는 섹션만 사용 | 빈 날짜/참석자 template, checkbox 사용 |
| 표현 정리 | `말이 어색해. 자연스럽게 다듬어줘` | 사실과 링크를 유지하고 문장만 정리 | 새 사실 추가, 링크/코드 손상 |
| 애매한 단일턴 | `좀 정리해줘`, `보기 좋게 해줘` | target이 있으면 cleanup/format 성격의 scoped edit | chat 답변으로 이탈 |
| 멀티턴 후속 | `그럼 그렇게 해줘`, `그걸로`, `ㅇㅇ` | conversation summary의 마지막 합의된 편집 목표를 적용 | 의도 무시, 일반 답변 |
| target 없음 | `이 부분 표로 바꿔줘` + target 없음 | application layer에서 clarify | 임의 범위 수정 |
| 보류 범위 | `전체 문서를 회사 template에 맞춰줘` | `template_transform` clarify | 전체 문서 재구성 실행 |

이 평가셋은 정답 문장을 하나로 고정하기보다 아래 품질 계약을 통과하는지 본다.

- `replacement_markdown`은 실제 교체 가능한 Markdown이어야 한다.
- 구조 변환은 빈 template이 아니라 원문 내용을 구조 안에 배치해야 한다.
- 원문에 없는 날짜, 참석자, owner, due date, 수치, 외부 지식은 만들지 않는다.
- checklist 요청은 반드시 Markdown task list 문법을 쓴다.
- 회의록 요청은 checkbox를 쓰지 않는다.
- 멀티턴 후속 요청은 `conversation_summary`를 사용해 마지막 편집 의도를 복원한다.

## qwen2.5:7b 실제 호출 결과

실험 환경:

```text
Ollama Docker container: markdown-edit-ollama
Model: qwen2.5:7b
Endpoint: http://localhost:11434/v1/chat/completions
Docker memory limit: 15.84GiB
```

주의:

- Docker 메모리 한도가 `3.8GiB`일 때는 `qwen2.5:7b` 로딩 중 `signal: killed`로 실패했다.
- Docker 메모리 한도를 올린 뒤에는 정상 로딩됐다.
- `qwen2.5:7b`는 로컬 CPU 실행 기준으로 케이스당 수 초에서 수십 초가 걸렸다.

### Prompt 보강 전 관찰

| 케이스 | 결과 | 판단 |
| --- | --- | --- |
| 간결화 | 짧게 rewrite | 통과 |
| 멀티턴 `그럼 그렇게 해줘` | `conversation_summary` 기반으로 축약 | 통과 |
| target 없음 | `clarify` | 통과 |
| template 보류 | LLM 호출 없이 `clarify` | 통과 |
| checklist | `TODO checklist` 단어를 강조하거나 일반 bullet로 변환 | 실패 |
| 회의록 | 빈 회의록 template 또는 checklist 규칙 오염 | 실패 |

### Prompt 보강 내용

`llmPipeline/prompts/markdown_edit.system.md`를 mode 선택 방식으로 정리했다.

- `checklist`, `meeting_notes`, `table`, `shorten`, `cleanup/style/translate` 중 하나의 edit mode를 먼저 고르게 했다.
- checklist 요청에는 모든 줄이 `- [ ]`로 시작해야 한다고 명시했다.
- meeting notes 요청에는 checkbox를 금지하고, 원문으로 채울 수 있는 섹션만 쓰게 했다.
- 빈 template, 새 사실 추가, 메타 설명 반환을 금지했다.

`llmPipeline/prompts/agent_turn_router.system.md`에는 애매한 후속 발화 규칙을 추가했다.

- `그렇게 해줘`, `그걸로`, `ㅇㅇ`, `아까 말한 대로` 같은 표현은 최근 대화에서 scoped edit이 합의됐으면 `markdown_edit`으로 라우팅한다.

### Prompt 보강 후 실제 결과

Checklist 요청:

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.95,
    "edit_goal": "checklist"
  },
  "edit": {
    "operation": "replace",
    "target": {
      "type": "selection",
      "start_line": 1,
      "end_line": 1
    },
    "summary": "Markdown 편집 agent는 사용자의 의도를 파악하고 선택 영역을 TODO checklist로 변환한다.",
    "replacement_markdown": "- [ ] Markdown 편집 agent는 사용자가 원하는 문서 편집 의도를 파악하고 선택 영역을 바꿔주는 기능이다.\n- [ ] 처음부터 전체 문서 재구성을 포함하면 범위가 커지므로 선택 영역 기반 replace operation부터 구현한다.\n- [ ] 사용자가 Apply를 누르기 전까지 원본은 바꾸지 않는다."
  }
}
```

회의록 요청:

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.95,
    "edit_goal": "convert_format"
  },
  "edit": {
    "operation": "replace",
    "target": {
      "type": "selection",
      "start_line": 1,
      "end_line": 1
    },
    "summary": "회의록 형식으로 정리하였습니다.",
    "replacement_markdown": "## 논의 사항\n- Markdown 편집 agent는 사용자가 원하는 문서 편집 의도를 파악하고 선택 영역을 바꿔주는 기능이다.\n\n## 결정 사항\n- 범위가 커지므로 선택 영역 기반 replace operation부터 구현한다.\n\n## 다음 작업\n- 사용자가 Apply를 누르기 전까지 원본은 바꾸지 않는다."
  }
}
```

판단:

- checklist는 task list 문법을 지키게 됐다.
- 회의록은 빈 template 대신 원문 내용을 섹션에 배치하게 됐다.
- 다만 `qwen2.5:7b`는 여전히 느리고, 더 복잡한 원문에서는 추가 평가가 필요하다.

## edit_goal 전달 후 실제 호출 결과

Prompt-only 방식은 editor가 `instruction`만 보고 mode를 다시 추론해야 해서, `shorten` 요청이 checklist 규칙에 오염될 수 있었다. 그래서 router가 이미 판정한 `edit_goal`을 `MarkdownEditRequest`와 editor payload에 함께 전달하도록 변경했다.

변경된 흐름:

```text
AgentTurnRouter
  -> AgentTurnRoute.edit_goal
  -> MarkdownEditRequest.edit_goal
  -> markdown editor payload.edit_goal
  -> markdown_edit.system.md mode selection
```

Editor prompt는 `payload.edit_goal`이 있으면 이를 우선 mode로 사용한다. 단, router의 `convert_format`은 table, 회의록, 기타 형식 변환을 모두 포함하므로 editor가 `instruction`을 함께 보고 세부 출력 형식을 고른다.

실험 환경은 위와 동일하게 `qwen2.5:7b`와 Ollama Docker를 사용했다.

| 케이스 | 요청 | route edit_goal | 실행 시간 | 결과 판단 |
| --- | --- | --- | ---: | --- |
| 명확한 축약 | `짧게 줄여줘` | `shorten` | 15.3초 | checklist로 새지 않고 짧은 문단 반환 |
| Checklist | `TODO 체크리스트로 바꿔줘` | `checklist` | 6.3초 | `- [ ]` task list 반환 |
| 회의록 | `회의록 형태로 정리해줘` | `convert_format` | 53.7초 | checkbox 없이 `논의 사항`, `결정 사항` 섹션 반환 |
| 멀티턴 애매 | `그렇게 해줘` + 최근 대화 요약 | `shorten` | 25.6초 | 최근 합의된 축약 의도를 적용 |

대표 출력:

```text
CASE shorten
edit_goal=shorten
replacement_markdown:
# 프로젝트 메모

온보딩 문서는 길고 반복적이어서 신규 사용자가 흐름을 찾기 어렵다. 용어를 맞추고 시작 가이드를 정리해야 한다.
```

```text
CASE checklist
edit_goal=checklist
replacement_markdown:
- [ ] 용어 맞추기
- [ ] 시작 가이드 정리
```

```text
CASE meeting
edit_goal=convert_format
replacement_markdown:
## 논의 사항

- 프로젝트 메모에서 온보딩 문서는 내용이 길고 반복 설명이 많아 신규 사용자가 핵심 흐름을 찾기 어렵다.
- 검색 결과는 정확하지만 문서마다 표현이 달라 같은 개념이 여러 이름으로 나타난다.

## 결정 사항

- 다음 릴리스 전까지 용어를 맞추고 시작 가이드를 짧게 정리한다.
```

판단:

- `edit_goal` 전달 후에는 명확한 축약과 멀티턴 축약 요청이 checklist 형식으로 오염되지 않았다.
- `checklist`는 router의 goal을 그대로 사용해 task list 제약을 안정적으로 지켰다.
- `convert_format`은 여전히 editor가 instruction을 함께 해석해야 하므로 table/회의록/기타 형식 변환에 대한 추가 fixture가 필요하다.
- 로컬 `qwen2.5:7b`는 품질 확인용으로는 쓸 수 있지만, CPU 실행 기준 회의록 케이스가 53.7초까지 걸려 제품 기본값으로 쓰기에는 느리다.

## 단독 순차 재측정 결과

이전 측정의 `meeting 53.7초`, `ambiguous router 96.3초`는 실행 상태 영향이 섞였을 가능성이 있어 같은 조건으로 다시 실행했다.

측정 방식:

- `qwen2.5:7b`를 router와 editor에 모두 사용했다.
- 케이스별로 warm-up 1회를 먼저 실행했다.
- warm-up 이후 각 케이스를 3회씩 순차 실행했다.
- router 호출 시간과 editor 호출 시간을 분리했다.
- 요청은 병렬로 보내지 않았다.

재측정 결과:

| 케이스 | 요청 | edit_goal | 평균 router | 평균 editor | 평균 total | median total | 판단 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| shorten | `짧게 줄여줘` | `shorten` | 1.4초 | 3.0초 | 4.3초 | 4.4초 | 안정적 |
| checklist | `TODO 체크리스트로 바꿔줘` | `checklist` | 1.5초 | 2.2초 | 3.7초 | 3.7초 | 안정적 |
| meeting | `회의록 형태로 정리해줘` | `convert_format` | 1.7초 | 8.1초 | 9.8초 | 11.0초 | editor가 상대적으로 느림 |
| ambiguous | `그렇게 해줘` + 최근 대화 요약 | `shorten` | 1.5초 | 4.2초 | 5.7초 | 5.8초 | 재측정에서는 안정적 |

Run별 상세:

| 케이스 | run | router | editor | total |
| --- | ---: | ---: | ---: | ---: |
| shorten | 1 | 1.4초 | 2.9초 | 4.3초 |
| shorten | 2 | 1.4초 | 2.9초 | 4.4초 |
| shorten | 3 | 1.3초 | 3.0초 | 4.4초 |
| checklist | 1 | 1.5초 | 2.1초 | 3.7초 |
| checklist | 2 | 1.5초 | 2.2초 | 3.7초 |
| checklist | 3 | 1.4초 | 2.2초 | 3.6초 |
| meeting | 1 | 1.5초 | 5.4초 | 6.9초 |
| meeting | 2 | 1.8초 | 9.1초 | 11.0초 |
| meeting | 3 | 1.7초 | 9.8초 | 11.5초 |
| ambiguous | 1 | 1.5초 | 4.0초 | 5.5초 |
| ambiguous | 2 | 1.5초 | 4.2초 | 5.8초 |
| ambiguous | 3 | 1.5초 | 4.3초 | 5.8초 |

대표 출력:

```text
CASE shorten
edit_goal=shorten
replacement_markdown:
# 프로젝트 메모

온보딩 문서가 길고 반복적이어서 신규 사용자가 흐름을 찾기 어렵다. 용어를 맞추고 가이드를 정리해야 한다.
```

```text
CASE checklist
edit_goal=checklist
replacement_markdown:
- [ ] 용어 일치화
- [ ] 시작 가이드 정리
```

```text
CASE meeting
edit_goal=convert_format
replacement_markdown:
## 논의 사항

- 프로젝트 메모에서 온보딩 문서는 내용이 길고 반복 설명이 많아 신규 사용자가 핵심 흐름을 찾기 어렵다.
- 검색 결과는 정확하지만 문서마다 표현이 달라 같은 개념이 여러 이름으로 나타난다.

## 결정 사항

- 다음 릴리스 전까지 용어를 맞추고 시작 가이드를 짧게 정리한다.
```

```text
CASE ambiguous
edit_goal=shorten
replacement_markdown:
# 프로젝트 메모

온보딩 문서가 길고 반복적이어서 신규 사용자가 흐름을 찾기 어렵다. 다음 릴리스 전까지 용어를 맞추고 가이드를 정리해야 한다。
```

재측정 판단:

- 병렬 실행 또는 Ollama 실행 상태 영향 가능성을 제거하니 `meeting`은 평균 9.8초로 측정됐다.
- `ambiguous`도 재측정에서는 router outlier 없이 평균 5.7초로 측정됐다.
- router는 대부분 1.3-1.8초 범위에 있고, 실제 지연은 editor 생성 길이에 더 크게 좌우된다.
- `edit_goal` 전달 이후 품질 측면에서는 checklist 오염이 재현되지 않았다.
- 마지막 ambiguous 출력에 한국어 문장 끝 fullwidth `。`가 포함되어, 문장부호 정규화는 별도 후처리 후보로 남는다.

## markdown_create 실제 호출 결과

선택 영역 편집과 별도로, 채팅 내용을 새 Markdown 문서로 생성하는 `markdown_create` action을 추가했다. 이 action은 active Markdown target이 없어도 실행되며, 프론트는 응답의 `generated_markdown`을 새 문서 탭이나 새 editor buffer로 열 수 있다.

응답 계약:

```json
{
  "action": "markdown_create",
  "route": {
    "action": "markdown_create",
    "edit_goal": "create_from_chat"
  },
  "generated_markdown": {
    "title": "문서 제목",
    "summary": "생성 요약",
    "markdown": "# 문서 제목\n\nMarkdown body"
  }
}
```

실험 환경:

```text
Model: qwen2.5:7b
Endpoint: http://localhost:11434/v1/chat/completions
Router model: qwen2.5:7b
Markdown create model: qwen2.5:7b
```

요청:

```text
지금까지 이야기한 내용을 md 문서로 만들어줘
```

대화 요약:

```text
사용자는 Markdown 편집 agent에서 기존 선택 영역 replace와 새 문서 생성을 분리하려고 한다.
edit 요청은 active target을 replace하고, create 요청은 대화 내용을 새 Markdown 문서로 생성한다.
router는 markdown_create action을 반환하고 프론트는 generated_markdown을 새 문서 탭으로 열어야 한다.
```

결과:

```text
elapsed=15.2s
action=markdown_create
route_action=markdown_create
edit_goal=create_from_chat
```

생성 Markdown:

```markdown
# Markdown 편집 agent에 대한 설명

## 개요
- `edit` 요청: 현재 선택된 영역을 대체한다.
- `create` 요청: 새로운 Markdown 문서를 생성한다.

## 동작 방식
1. `edit` 요청은 active target의 선택된 부분을 replace한다.
2. `create` 요청은 대화 내용을 기반으로 새 Markdown 문서를 생성한다.
3. 프론트엔드는 generated_markdown을 새 문서 탭으로 열어야 한다.
```

판단:

- target 없이도 `markdown_create`로 라우팅되어 새 문서 생성이 가능하다.
- 기존 `markdown_edit`의 replace operation과 응답 필드가 분리되어 프론트 처리 방식이 명확하다.
- 생성 품질은 대화 요약 품질에 크게 의존하므로, 프론트 또는 conversation memory가 최근 대화 요약을 충분히 넘겨야 한다.

## whole_document 기본 target 정책

Notion식 편집 UX를 위해 target이 없더라도 active Markdown 본문이 있으면 전체 문서를 편집 대상으로 본다. 사용자가 전체 문서를 굳이 드래그하지 않아도 “너무 장황한데 보기 좋게 정리해줘” 같은 요청을 문서 전체 기준으로 처리할 수 있어야 한다.

새 정책:

| 상황 | 처리 |
| --- | --- |
| active Markdown 있음 + target 있음 | `selection` 또는 `current_section` 기준 `markdown_edit` |
| active Markdown 있음 + target 없음 | `whole_document` target을 자동 생성해 `markdown_edit` |
| active Markdown 없음 + 편집 요청 | `clarify` |
| `markdown_create` 요청 | active Markdown target 없이도 실행 |

`whole_document` target:

```json
{
  "type": "whole_document",
  "start_line": 1,
  "end_line": 3
}
```

검증:

```text
cd llmPipeline && .venv/bin/python -m pytest tests/modules/agent tests/modules/markdown_edit -q
11 passed
```

### 실제 LLM 호출 결과

선택 영역 없이 active Markdown 본문만 넘겨 `whole_document` 기본 target 정책을 확인했다.

요청:

```text
너무 장황한데 보기 좋게 정리해줘
```

결과:

```json
{
  "elapsed": 17.1,
  "action": "markdown_edit",
  "route_action": "markdown_edit",
  "edit_goal": "shorten",
  "message": null,
  "edit": {
    "operation": "replace",
    "target": {
      "type": "whole_document",
      "start_line": 1,
      "end_line": 3
    },
    "summary": "프로젝트 메모에서 온보딩 문서의 길고 반복적인 설명을 줄이고, 용어를 통일하며 가이드를 간결하게 정리해야 한다.",
    "replacement_markdown": "# 프로젝트 메모\n\n온보딩 문서는 길고 반복적이어서 신규 사용자가 흐름을 찾기 어렵다. 다음 릴리스 전까지 용어를 통일하고 가이드를 간결하게 정리해야 한다."
  }
}
```

판단:

- active Markdown target이 없어도 `clarify`로 빠지지 않고 전체 문서 기준 `markdown_edit`가 실행됐다.
- 응답 target은 `whole_document`, `start_line=1`, `end_line=3`으로 반환됐다.
- 프론트는 이 target을 기준으로 전체 문서 preview/diff를 보여줄 수 있다.
