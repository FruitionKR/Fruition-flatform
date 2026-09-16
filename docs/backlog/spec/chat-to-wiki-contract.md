# 채팅 Wiki page화 계약

이 문서는 backend가 직렬화한 채팅 Markdown을 기존 ingest pipeline에 넣어 Wiki graph 검색 대상으로 만드는 흐름과 입출력 계약을 정리한다.

일반 문서 ingest는 기존 `POST /pipeline/runs` 계약을 유지한다. 채팅 Wiki page화는 별도 `POST /chat-wiki/runs` 계약을 사용한다. 최종 출력은 기존 ingest output과 동일하게 유지하되, ingest에 들어가기 전 채팅 전용 입력 해석과 source reference 보존을 추가한다.

## 1. 핵심 결정

- 기존 ingest pipeline은 재사용한다.
- 채팅 입력은 누적 대상 source page를 특정하는 `document_id`로 받는다.
- `document_id`는 source page 선택 key이며, 이번 실행 입력 Markdown을 뜻하지 않는다.
- 기존 source page가 있는 `full` 누적에서 backend가 신규 chat Q&A를 Markdown으로 직렬화한 경우 `input_markdown`으로 넘긴다.
- `input_markdown`이 없을 때만 pipeline이 `document_id`로 저장된 Markdown을 읽는다.
- 전체 선택(`full`)에서는 이미 저장된 채팅 문답 제외를 backend가 처리한다.
- 일부 선택(`partial`)에서는 이미 저장된 문답도 선택 구간의 일부로 다시 독립 source page화할 수 있다.
- 채팅 Wiki page화는 일반 문서 ingest API와 분리된 `/chat-wiki/runs`를 사용한다.
- 채팅 전용 입력에는 `document_id`와 `selection_mode`가 필수다.
- 채팅 원문 링크는 `session_id`와 `pair_id`로 특정한다.
- 개별 user/assistant message id는 원문 링크 식별 계약에 사용하지 않는다.
- 채팅 원문 링크 단위는 문답 1쌍이며, 이 단위는 `session_id + pair_id`로 이미 특정된다.
- 전체 선택(`full`)은 기존 chat source page에 누적한다.
- 일부 선택(`partial`)은 chat prompt로 새 독립 source page를 만든다.
- `llmPipeline` ingest는 같은 source page 내부에 축적된 section/mention 근거만 새 core에 누적한다.
- `llmPipeline` ingest는 다른 source page나 active cluster의 외부 evidence를 새 core에 병합하지 않는다.
- 최종 응답 형식은 기존 `PipelineRunOut`과 manifest 구조를 유지한다.

## 2. 현재 ingest 입력 구조

현재 `llmPipeline`의 일반 ingest endpoint는 backend가 먼저 생성한 문서의 `document_id`를 받는다.

```text
POST /pipeline/runs

document_id
```

현재 Spring 문서 처리 흐름은 보통 아래처럼 `document_id`만 전달한다.

```json
{
  "document_id": "document_1",
  "log_callback_url": "http://backend:8080/api/documents/document_1/pipeline-events/callback"
}
```

채팅 Wiki page화는 source page를 특정하는 `document_id`를 `POST /chat-wiki/runs`로 전달한다. backend가 이미 처리된 pair를 제외한 Markdown을 직접 넘기는 경우 `input_markdown`을 함께 전달한다.

`document_id`와 `input_markdown`의 역할은 분리한다.

```text
document_id
  -> 누적 대상 source page slug
  -> 기존 source_extraction_artifact 조회 key
  -> 최종 wiki_pages(source) 저장 key

input_markdown
  -> 이번 pipeline 실행에서 새로 읽을 chat Q&A Markdown
  -> 기존 source page가 있는 full 누적에서 backend가 이미 처리된 pair를 제외한 신규 pair Markdown
```

## 3. 채팅 입력 계약

채팅용 요청은 최소 아래 값을 가진다.

```text
POST /chat-wiki/runs
```

```json
{
  "document_id": "chat_document_1",
  "selection_mode": "full",
  "input_markdown": "# Chat Export\n\n[chat_session_1:pair_3]Q : 새 질문\nA : 새 답변",
  "log_callback_url": "http://backend:8080/api/chat-wiki/runs/{run_id}/pipeline-events/callback"
}
```

필드 의미:

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `document_id` | 예 | 누적 대상 chat source page를 특정하는 stable id. 이번 입력 본문이 아니라 source page 선택 key다. |
| `selection_mode` | 예 | `full`이면 전체 선택, `partial`이면 일부 선택 |
| `input_markdown` | 선택 | 기존 source page가 있는 `full` 누적에서 backend가 중복 필터링해 직렬화한 신규 pair Markdown. 없으면 `document_id`로 저장된 문서를 읽는다. |
| `log_callback_url` | 예 | 기존 문서 처리처럼 pipeline event를 backend에 전달할 callback URL |
| `input_name` | 선택 | 실행 로그와 임시 document filename에 사용할 이름 |
| `wait` | 선택 | 기존 실행 API와 같은 비동기/동기 실행 옵션 |

`POST /pipeline/runs`는 일반 문서 ingest 전용이다. 채팅 요청에서 `selection_mode`가 빠진 상태는 유효하지 않으며, `selection_mode`가 포함된 요청도 `/pipeline/runs`가 아니라 `/chat-wiki/runs`로 보내야 한다.

`session_id`와 `pair_id`는 top-level request 필드로 받지 않는다. backend가 직렬화한 각 문답 앞의 `[session_id:pair_id]` prefix를 canonical source ref로 사용한다.

## 4. Markdown 직렬화 규칙

backend는 채팅을 Markdown으로 직렬화할 때 문답 1쌍을 하나의 단위로 만든다. 각 문답 앞에는 원본 채팅을 바로 특정할 수 있는 `[session_id:pair_id]` prefix를 붙인다.

권장 형식:

```markdown
# Chat Export

[chat_session_1:pair_1]Q : LangSmith 연결은 어디서 봐?
A : traces 화면에서 run을 확인합니다.


[chat_session_1:pair_2]Q : 실패한 run은 어떻게 봐?
A : error filter를 적용해서 확인합니다.
```

규칙:

- `[session_id:pair_id]`는 문답 1쌍을 특정하는 canonical source ref다.
- `pair_id`는 같은 `session_id` 안에서 문답 1쌍을 특정해야 한다.
- `Q :`에는 user 발화를 넣고, `A :`에는 assistant 응답을 넣는다.
- user 발화와 assistant 응답을 모두 포함한다.
- 문답 순서를 보존한다.
- 개별 user/assistant message id는 넣지 않는다.
- 문답 1쌍 안에는 빈 줄을 넣지 않는다.
- 문답과 문답 사이는 빈 줄로 구분한다.
- credential, token, private key, 민감 URL은 backend에서 마스킹한 뒤 넘긴다.

## 5. Source Reference 계약

일반 문서는 pipeline이 Markdown을 보고 source block을 나누고, 원문 위치를 `document_id + block_id`로 특정한다.

채팅은 다르다. 채팅은 원문 링크 단위가 이미 `session_id + pair_id`로 특정된다. 따라서 채팅에서는 일반 문서용 block anchor를 만들지 않고, `session_id + pair_id`를 처음부터 끝까지 source reference로 사용한다.

채팅 source reference는 아래 논리 구조를 가진다.

```json
{
  "type": "chat_pair",
  "session_id": "chat_session_1",
  "pair_id": "pair_1"
}
```

pipeline은 외부 query 링크용 ref로 아래 값을 보존해야 한다.

```json
{
  "type": "chat_pair",
  "session_id": "chat_session_1",
  "pair_id": "pair_1"
}
```

핵심은 query 응답에서 이 두 값을 잃지 않는 것이다.

```text
session_id + pair_id -> 원본 채팅 문답 1쌍
```

## 6. 처리 플로우

### 6.1 일반 문서

```text
POST /pipeline/runs
  -> backend가 먼저 생성한 document_id 수신
  -> document_id로 저장된 Markdown 로드
  -> 일반 source block splitter 실행
  -> 일반 문서 semantic extraction prompt 사용
  -> source page/concept page/link 생성
  -> 기존 output 반환
```

### 6.2 채팅 전체 선택 - 기존 source page 있음

`selection_mode = full`

```text
backend가 document_id로 누적 대상 chat source page를 결정
  -> backend가 이미 저장된 pair를 제외하고 신규 pair만 Markdown으로 직렬화
  -> POST /chat-wiki/runs
  -> document_id + selection_mode=full + input_markdown + log_callback_url 전달
  -> pipeline이 document_id로 기존 source page/artifact 조회
  -> pipeline이 input_markdown을 이번 실행 입력으로 우선 사용
  -> input_markdown이 없으면 pipeline이 document_id로 저장된 채팅 Markdown을 fallback 로드
  -> pipeline이 [session_id:pair_id] prefix를 source ref로 보존
  -> chat append prompt 사용
  -> concept page는 현재 입력 근거와 같은 source page 내부 누적 근거로 생성
  -> source page의 key points/observations/categories/core/section/mention은 기존 항목 선행 + 새 항목으로 append draft 생성
  -> source accumulation evaluator가 의미 중복을 평가하고 refs를 병합한 구조화 결과 반환
  -> source page summary는 기존 source page 문맥과 새 대화를 함께 본 전체 요약으로 재작성
  -> 기존 ingest output 반환
```

중복 제거 기준:

```text
same session_id AND same pair_id
```

이 중복 제거는 backend 요청 생성 단계에서 끝낸다. `llmPipeline`은 전달받은 `input_markdown` 또는 `document_id`의 채팅 Markdown을 이미 처리 대상이라고 보고, 별도 중복 제외 흐름 없이 append prompt를 실행한다.

기존 source page가 있는 `full`에서는 `input_markdown`이 권장 입력이다. 전체 원문을 다시 넣을 수도 있지만, 이미 처리된 pair가 다시 추출될 수 있으므로 backend가 신규 pair만 넘기는 쪽을 기본 계약으로 본다.

### 6.3 채팅 일부 선택

`selection_mode = partial`

```text
backend가 document_id로 partial source page 저장 key를 결정
  -> backend가 선택된 문답을 저장된 Markdown 문서로 준비
  -> POST /chat-wiki/runs
  -> document_id + selection_mode=partial + log_callback_url 전달
  -> pipeline이 document_id로 저장된 채팅 Markdown을 로드
  -> pipeline이 [session_id:pair_id] prefix를 source ref로 보존
  -> 기존 source page에 붙이지 않음
  -> 선택된 pair 묶음을 새 독립 source page로 생성
  -> chat prompt 사용
  -> 기존 ingest output 반환
```

일부 선택은 사용자가 특정 범위를 독립적인 지식 단위로 선택했다는 신호로 본다.
따라서 `partial`에서는 같은 pair가 기존 chat source page에 이미 포함되어 있어도 backend가 자동 제외하지 않는다.
같은 partial export 요청 자체를 재실행하지 않기 위한 멱등성 처리는 backend가 별도 작업 id나 content hash로 다룰 수 있지만, pair 중복 제외와는 분리한다.

### 6.4 채팅 최초 full

`selection_mode = full`이지만 아직 기존 source page가 없는 경우다.

```text
backend가 document_id로 앞으로 누적할 chat source page key를 결정
  -> backend가 처리 대상 pair를 저장된 Markdown 문서로 준비
  -> POST /chat-wiki/runs
  -> document_id + selection_mode=full + log_callback_url 전달
  -> pipeline이 document_id로 기존 source page/artifact 조회
  -> 기존 source page가 없으므로 chat prompt 사용
  -> pipeline이 document_id로 저장된 채팅 Markdown을 로드
  -> 새 source page와 concept page 생성
  -> 생성된 source page slug는 document_id로 저장
```

최초 full은 누적할 기존 source page가 없으므로 partial과 같은 chat semantic extraction prompt를 사용한다. 차이는 저장 의도다. 최초 full에서 만들어진 source page는 이후 같은 `document_id`의 full 요청이 누적할 대상이 된다.

## 7. Prompt 분기

채팅은 기존 ingest를 재사용하되, `full` 누적 처리에만 별도 append prompt를 사용한다.
`partial`은 선택된 채팅 문답을 새 문서처럼 처리하지만, 일반 문서 prompt가 아니라 채팅 전용 prompt를 사용한다.
일반 문서, 채팅 최초/partial, 채팅 full append는 서로 다른 prompt로 분리한다.

`full` append prompt:

```text
기존 chat source page와 새 채팅 문답을 함께 보고,
기존 source page markdown은 용어와 문맥 유지를 위한 배경으로만 사용한다.
출력 evidence와 anchor_block_ids는 현재 새 문답 SOURCE BLOCKS에서만 가져온다.
semantic extraction 출력은 현재 새 문답 근거만 포함한다.
같은 source page에 이미 있던 section/mention 근거의 누적 병합은 코드가 처리한다.
source accumulation evaluator는 append draft를 평가해 의미적으로 같은 key point/observation/category를 병합하고 refs를 합친다.
source page summary는 기존 요약에 새 요약을 append하지 않고 전체 source page 기준으로 다시 쓴다.
```

`partial` chat prompt:

```text
선택된 채팅 문답만 기준으로 독립적인 source page를 만든다.
기존 같은 session의 source page에 의존하지 않는다.
채팅 Q&A 흐름을 보존하는 observation과 source ref 규칙을 사용한다.
```

## 8. 출력 계약

채팅 Wiki page화의 HTTP 응답은 기존 pipeline 응답과 같은 형태를 유지한다.

```json
{
  "run_id": "uuid",
  "status": "running",
  "manifest": null,
  "output_dir": "runs/api_uuid",
  "log_path": "runs/api_uuid/pipeline.log"
}
```

`wait=true`로 완료까지 기다리는 경우에도 manifest 구조는 기존 ingest manifest를 유지한다.

```json
{
  "run_id": "uuid",
  "status": "succeeded",
  "manifest": {
    "input": "inline.md",
    "out": "runs/api_uuid",
    "source_page": {},
    "concept_pages": [],
    "links": [],
    "warnings": []
  },
  "output_dir": "runs/api_uuid",
  "log_path": "runs/api_uuid/pipeline.log"
}
```

채팅 전용 추가 정보가 필요하면 manifest 안에 기존 구조를 깨지 않는 보조 필드로 둔다.

```json
{
  "chat_wiki": {
    "selection_mode": "full",
    "appended_pair_ids": ["pair_3"],
    "skipped_pair_ids": ["pair_1", "pair_2"]
  }
}
```

## 9. Query 원문 링크 태그

Query 응답에서 일반 문서 근거와 채팅 근거를 구분해야 한다. 채팅 근거는 파일 line이나 문서 block 링크가 아니라 원본 채팅 문답으로 이동해야 하기 때문이다.

채팅 evidence/source reference는 `session_id + pair_id`를 바로 내려준다. backend/frontend는 추가로 source block을 조회하지 않고 이 두 값으로 원본 문답 링크를 만든다.

```json
{
  "type": "chat_pair",
  "session_id": "chat_session_1",
  "pair_id": "pair_1"
}
```

일반 문서 근거는 기존처럼 문서와 block을 참조한다.

```json
{
  "type": "document_block",
  "source_document_id": "document_1",
  "source_block_id": "B0001"
}
```

채팅 query 링크 처리:

```text
query evidence 반환
  -> type=chat_pair 확인
  -> backend가 session_id + pair_id로 채팅 문답 조회
  -> frontend가 해당 원문 대화 위치로 이동
```

권장 응답 조각:

```json
{
  "evidence_snippets": [
    {
      "text": "LangSmith traces 화면에서 run을 확인한다는 문답",
      "source_ref": {
        "type": "chat_pair",
        "session_id": "chat_session_1",
        "pair_id": "pair_1"
      }
    }
  ]
}
```

## 10. Backend 책임

backend는 다음을 책임진다.

- 채팅 메시지 저장과 조회
- 사용자가 선택한 채팅 범위 결정
- `full` 요청에서 이미 저장된 pair 제외
- 선택 범위를 pair 단위 Markdown으로 직렬화
- 각 문답 앞에 `[session_id:pair_id]` prefix 포함
- 민감정보 마스킹
- `document_id`, `selection_mode`, `log_callback_url`을 포함한 pipeline 실행 요청
- 기존 source page가 있는 `full` 누적에서는 신규 pair Markdown을 `input_markdown`으로 포함할 수 있음
- pipeline event callback을 받아 채팅 Wiki page화 진행 상태 갱신
- query 응답의 `chat_pair` source ref를 실제 원문 대화 링크로 변환

backend는 `session_id + pair_id`로 원본 문답을 조회할 수 있어야 한다.

## 11. llmPipeline 책임

`llmPipeline`은 다음을 책임진다.

- `POST /chat-wiki/runs`에서 `document_id`, `selection_mode`, `log_callback_url` 수신
- `document_id`로 backend가 저장한 문서의 `user_id`, `workspace_id`를 조회해 Wiki 저장 범위로 사용
- 기존 source page가 있는 `full` 누적에서만 `input_markdown` 수신 허용
- `input_markdown`이 허용된 경우 신규 pair 입력으로 사용하고, 그 외에는 `document_id`로 저장된 채팅 Markdown 로드
- 채팅 Markdown에서 `[session_id:pair_id]` prefix를 source ref로 보존
- 채팅에서는 `session_id + pair_id`를 query 원문 링크 식별자로 사용
- `full`이면 기존 source page가 있을 때 append prompt 실행
- `full`이지만 기존 source page가 없으면 chat prompt 실행
- `partial`이면 chat prompt로 독립 source page 생성
- 이미 저장된 pair 중복 제외는 수행하지 않음
- 같은 source page의 기존 section/mention이 새 core와 겹치면 해당 근거를 새 core에 누적
- 다른 source page나 active cluster의 evidence는 병합하지 않음
- query 근거로 사용할 수 있도록 `chat_pair` source reference 보존
- 기존 ingest output 형태 유지

`llmPipeline`은 채팅 저장소를 직접 읽지 않는다. 원본 채팅 조회와 실제 링크 생성은 backend가 담당한다.

## 12. 구현 체크리스트

1. 기존 source page가 있는 `full` 요청에서는 backend가 이미 저장된 pair를 제외한다.
2. 기존 source page가 있는 `full` 요청에서는 backend가 신규 pair만 Markdown으로 직렬화해 `input_markdown`으로 보낼 수 있다.
3. 최초 `full` 요청에서는 backend가 처리 대상 pair를 저장된 Markdown 문서로 준비한다.
4. `partial` 요청에서는 backend가 선택된 pair를 저장된 Markdown 문서로 준비한다.
5. 채팅 pipeline 요청에 `document_id`, `selection_mode`, `log_callback_url`을 포함한다.
6. 기존 source page가 있는 `full` 누적에서만 선택적으로 `input_markdown`을 포함한다.
7. backend 직렬화 Markdown에서 각 문답 앞에 `[session_id:pair_id]` prefix를 포함한다.
8. pipeline이 허용된 `input_markdown`은 우선 사용하고, 그 외에는 `document_id`로 저장된 채팅 Markdown을 로드한다.
9. pipeline이 `[session_id:pair_id]`를 query용 `chat_pair` source reference로 보존하게 한다.
10. 일반 문서 prompt, chat prompt, chat append prompt를 분리한다.
11. pipeline은 중복 제외 없이 `selection_mode`에 맞는 prompt를 바로 실행한다.
12. source reference에 `chat_pair` 태그를 보존한다.
13. query evidence 응답에 `type=chat_pair`를 추가한다.
14. backend가 `chat_pair` source ref를 원본 채팅 링크로 변환한다.
15. 일반 문서 ingest output과 채팅 ingest output의 응답 shape이 같은지 확인한다.
