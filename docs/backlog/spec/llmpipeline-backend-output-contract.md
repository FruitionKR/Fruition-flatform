# llmPipeline 백엔드 최종 출력 JSON 계약

이 문서는 `llmPipeline` FastAPI가 Spring backend로 돌려주는 성공 응답 JSON 구조를 기능별로 정리한다.
대상 기능은 `ingest`, `query`, `markdown_edit`, `markdown_create`, `schema`, `lint`다.

여기서 말하는 "최종 출력"은 LLM 내부 중간 산출물이 아니라, backend가 HTTP 응답 body로 받는 JSON이다.
FastAPI 공통 실패 응답은 보통 `{"detail": "에러 메시지"}` 형태다. `/agent/turn`의 Markdown 출력 계약 실패는 backend가 분기할 수 있도록 `detail.code`와 `detail.message`를 가진다. 이 문서는 성공 응답을 중심으로 설명한다.

## 1. Ingest

문서를 Wiki source/concept page로 변환하는 기능이다.
backend는 `POST /pipeline/runs`로 실행을 요청하고, 필요하면 `GET /pipeline/runs/{run_id}`로 완료 결과를 조회한다.

### 1.1 실행 요청 응답

`wait=false`가 기본값이므로, 일반적으로 요청 직후에는 실행 예약 결과만 반환된다.

```json
{
  "run_id": "2f5b7e8a-1c25-4a56-bf4a-7dc8b9c14e8d",
  "status": "running",
  "manifest": null,
  "output_dir": "runs/api_2f5b7e8a-1c25-4a56-bf4a-7dc8b9c14e8d",
  "log_path": "runs/api_2f5b7e8a-1c25-4a56-bf4a-7dc8b9c14e8d/pipeline.log"
}
```

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `run_id` | string | pipeline 실행 1건을 식별하는 UUID다. 이후 상태 조회와 로그 조회에 사용한다. |
| `status` | string | 현재 실행 상태다. 실행 직후에는 보통 `running`, `wait=true` 완료 응답이면 `succeeded`다. |
| `manifest` | object 또는 null | 완료 산출물 요약이다. 비동기 실행 직후에는 아직 없으므로 `null`이다. |
| `output_dir` | string | pipeline 산출물이 저장되는 실행별 디렉터리 경로다. |
| `log_path` | string | pipeline 진행 로그 파일 경로다. |

### 1.2 완료 조회 응답

`GET /pipeline/runs/{run_id}`는 DB에 저장된 실행 row를 그대로 반환한다.
실패하면 `status="failed"`와 `error`가 채워지고, 성공하면 `status="succeeded"`와 `manifest`가 채워진다.
주의할 점은 `POST /pipeline/runs`를 `wait=true`로 호출했을 때의 즉시 응답이다.
이 경우 `manifest`는 `run_pipeline()`이 반환한 원본 manifest라서 `source_blocks`, `normalized`, page별 `markdown` 같은 큰 중간 산출물을 포함할 수 있다.
반면 `GET /pipeline/runs/{run_id}`의 `manifest`는 DB 저장 전에 축약되어 큰 본문 필드가 제거된다.

```json
{
  "id": "2f5b7e8a-1c25-4a56-bf4a-7dc8b9c14e8d",
  "document_id": "doc_123",
  "input_source": "storage:sources/documents/doc_123/extracted.md",
  "output_dir": "runs/api_2f5b7e8a-1c25-4a56-bf4a-7dc8b9c14e8d",
  "mode": "api",
  "status": "succeeded",
  "manifest": {
    "input": "paper.md",
    "out": "runs/api_2f5b7e8a-1c25-4a56-bf4a-7dc8b9c14e8d",
    "mode": "api",
    "user_id": "local-user",
    "workspace_id": "local-workspace",
    "source_page_mode": "section-polish",
    "concept_page_mode": "skeleton",
    "document_id": "doc_123",
    "source_document_id": "doc_123",
    "source_page": {
      "slug": "doc_123",
      "title": "문서 제목",
      "markdown_path": "runs/api_x/wiki/sources/doc_123.md"
    },
    "source_extraction_artifact": {},
    "concept_pages": [
      {
        "slug": "robust-optimization",
        "title": "Robust Optimization",
        "markdown_path": "runs/api_x/wiki/concepts/robust-optimization.md"
      }
    ],
    "links": [
      {
        "source": "source:doc_123",
        "target": "concept:robust-optimization",
        "relation": "source_mentions_concept",
        "label": "mentions",
        "confidence": 0.9
      }
    ],
    "meaning_clusters": {
      "active_path": "wiki/local-user/local-workspace/clusters/active.md",
      "log_path": "wiki/local-user/local-workspace/logs/2026-07-03.md",
      "active_uri": "s3://bucket/wiki/local-user/local-workspace/clusters/active.md",
      "log_uri": "s3://bucket/wiki/local-user/local-workspace/logs/2026-07-03.md",
      "maintenance_summary": {
        "promotion_candidates": [
          {
            "cluster_id": "robust-optimization",
            "representative": "Robust Optimization",
            "source_refs": ["doc_123:B0003"],
            "reason": "LLM cluster judge 판단"
          }
        ],
        "relation_candidates": [
          {
            "cluster_id": "taguchi-method",
            "target": "concept:robust-optimization",
            "relation": "uses_or_depends_on",
            "evidence": ["claim_doc_123_001"]
          }
        ],
        "lint_action_available": true
      }
    },
    "maintenance_summary": {
      "promotion_candidates": [
        {
          "cluster_id": "robust-optimization",
          "representative": "Robust Optimization",
          "source_refs": ["doc_123:B0003"],
          "reason": "LLM cluster judge 판단"
        }
      ],
      "relation_candidates": [
        {
          "cluster_id": "taguchi-method",
          "target": "concept:robust-optimization",
          "relation": "uses_or_depends_on",
          "evidence": ["claim_doc_123_001"]
        }
      ],
      "lint_action_available": true
    },
    "pipeline_log": "runs/api_x/pipeline.log",
    "log_callback_url": null,
    "save_debug_json": false,
    "warnings": []
  },
  "error": null,
  "created_at": "2026-07-03T10:00:00+09:00",
  "finished_at": "2026-07-03T10:01:30+09:00"
}
```

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `id` | string | `run_id`와 같은 pipeline 실행 id다. |
| `document_id` | string 또는 null | 이 실행이 처리한 backend 문서 id다. inline/file 입력이면 pipeline이 임시 id를 만든다. |
| `input_source` | string | 입력이 어디서 왔는지 나타낸다. 예: `storage:...`, `inline:...`, 로컬 파일 경로. |
| `output_dir` | string | 실행 산출물 디렉터리다. |
| `mode` | string | LLM 호출 모드다. 현재 주요 값은 `api`, `generic-chat`이다. |
| `status` | string | 실행 상태다. `running`, `succeeded`, `failed`를 기대할 수 있다. |
| `manifest` | object 또는 null | 성공 시 pipeline 산출물 요약이다. 실행 중이거나 실패한 경우 없을 수 있다. |
| `error` | string 또는 null | 실패 시 에러 요약이다. 성공하면 `null`이다. |
| `created_at` | string | 실행 row 생성 시각이다. DB timestamp가 JSON으로 직렬화된다. |
| `finished_at` | string 또는 null | 실행 완료 또는 실패 시각이다. 실행 중이면 `null`이다. |

`manifest` 주요 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `input` | string | pipeline이 처리한 입력 이름 또는 경로다. |
| `out` | string | 산출물 저장 디렉터리다. |
| `user_id`, `workspace_id` | string | Wiki page와 cluster artifact가 속한 사용자/workspace 범위다. |
| `source_page_mode`, `concept_page_mode` | string | source page와 concept page 생성 방식이다. |
| `document_id` | string | pipeline 내부 document id다. |
| `source_document_id` | string 또는 null | backend 원본 문서 id다. source block ref의 document 부분으로 쓰인다. |
| `source_page` | object | 생성된 source page 요약이다. `wait=true` 즉시 응답에는 `markdown`이 포함될 수 있고, DB 저장용 manifest에서는 Markdown 본문이 제거된다. |
| `source_extraction_artifact` | object | source page 생성에 사용된 추출 artifact다. |
| `concept_pages` | array | 생성된 concept page 요약 목록이다. `wait=true` 즉시 응답에는 page별 `markdown`이 포함될 수 있고, DB 저장용 manifest에서는 Markdown 본문이 제거된다. |
| `links` | array | source/concept page 사이 graph edge 후보 목록이다. |
| `meaning_clusters` | object | active cluster/log artifact 경로와 maintenance 요약이다. `wait=true` 즉시 응답에는 `active_markdown`, `log_markdown`, `clusters`가 포함될 수 있고, DB 저장용 manifest에서는 이 큰 본문 필드들이 제거된다. |
| `maintenance_summary` | object | promotion/relation 후보 등 유지보수 요약이다. |
| `pipeline_log` | string | pipeline 로그 파일 경로다. |
| `log_callback_url` | string 또는 null | pipeline log event를 callback으로 보낸 URL이다. |
| `save_debug_json` | boolean | debug JSON 저장 여부다. |
| `warnings` | array | pipeline 중 발생한 비치명 경고 목록이다. |

### 1.3 Ingest 후 제안 필드

ingest 후 사람이 검토하거나 lint에서 후속 처리할 수 있는 제안은 `proposal`이라는 별도 태그가 아니라 `maintenance_summary` 아래 후보 필드로 표현된다.

```json
{
  "manifest": {
    "maintenance_summary": {
      "promotion_candidates": [
        {
          "cluster_id": "robust-optimization",
          "representative": "Robust Optimization",
          "source_refs": ["doc_123:B0003"],
          "reason": "LLM cluster judge 판단"
        }
      ],
      "relation_candidates": [
        {
          "cluster_id": "taguchi-method",
          "target": "concept:robust-optimization",
          "relation": "uses_or_depends_on",
          "evidence": ["claim_doc_123_001"]
        }
      ],
      "invalid_candidates": [
        {
          "candidate_id": "cand_001",
          "claim_id": "claim_doc_123_001",
          "term": "제안 후보 용어",
          "slug": "candidate-term",
          "claim": "근거가 부족한 후보 claim",
          "candidate_type": "section",
          "reason": "missing source refs"
        }
      ],
      "invalid_promotions": [
        {
          "cluster_id": "candidate-without-source",
          "representative": "Candidate Without Source",
          "reason": "promotion candidate has no source_refs"
        }
      ],
      "lint_action_available": true
    }
  }
}
```

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `promotion_candidates` | array | 독립 concept page로 승격할 만한 cluster 제안 목록이다. |
| `relation_candidates` | array | 기존 또는 현재 concept와 relation edge로 연결할 만한 제안 목록이다. |
| `invalid_candidates` | array | source ref가 없어 후속 처리할 수 없는 후보 목록이다. |
| `invalid_promotions` | array | 승격 후보였지만 source ref가 없어 승격할 수 없는 cluster 목록이다. |
| `lint_action_available` | boolean | lint/maintenance에서 처리할 후보가 있는지 여부다. |

`promotion_candidates[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `cluster_id` | string | 승격 후보 cluster id다. |
| `representative` | string | 사람이 볼 대표 이름이다. |
| `source_refs` | array | 승격 판단의 근거 source ref 목록이다. |
| `reason` | string | 승격 후보로 판단한 이유다. |

`relation_candidates[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `cluster_id` | string | relation 후보가 나온 cluster id다. |
| `target` | string | 연결 대상 concept이다. 보통 `concept:{slug}` 형식이다. |
| `relation` | string | 제안된 관계 종류다. |
| `evidence` | array | relation 판단 근거 claim id 또는 source ref 목록이다. |

## 2. Query

Wiki graph와 source evidence를 기반으로 질문에 답하는 기능이다.
backend는 `POST /query` 응답을 받아 Spring API 응답과 채팅 저장 데이터로 변환한다.

```json
{
  "answer": "질문에 대한 답변입니다. [1]",
  "related_pages": [
    {
      "id": "page_1",
      "page_type": "concept",
      "title": "Robust Optimization",
      "slug": "robust-optimization",
      "relevance_score": 0.87,
      "role": "seed",
      "depth": 0
    }
  ],
  "evidence_snippets": [
    {
      "rank": 1,
      "source_document_id": "doc_123",
      "source_block_ids": ["B0003", "B0004"],
      "source_refs": [
        {
          "source_document_id": "doc_123",
          "source_block_id": "B0003"
        }
      ],
      "text": "답변 근거로 사용된 원문 일부"
    }
  ],
  "graph_context": {
    "nodes": [
      {
        "id": "page_1",
        "page_type": "concept",
        "title": "Robust Optimization",
        "slug": "robust-optimization",
        "relevance_score": 0.87,
        "role": "seed",
        "depth": 0
      }
    ],
    "edges": [
      {
        "from_page_id": "source_page_1",
        "to_page_id": "page_1",
        "link_type": "source_mentions_concept",
        "role": "traversed",
        "score": 0.81
      }
    ]
  },
  "traversal_paths": [
    {
      "path_id": "path_1",
      "role": "answer_path",
      "used_for_answer": true,
      "score": 0.84,
      "stop_reason": "score_floor",
      "nodes": ["source_page_1", "page_1"],
      "edges": [
        {
          "from_page_id": "source_page_1",
          "to_page_id": "page_1",
          "link_type": "source_mentions_concept",
          "role": "traversed",
          "score": 0.81
        }
      ]
    }
  ]
}
```

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `answer` | string | 사용자 질문에 대한 최종 답변이다. 답변 안의 `[1]` 같은 표식은 `evidence_snippets[].rank`와 대응한다. |
| `related_pages` | array | 질문 처리 중 관련 있다고 판단된 Wiki page 목록이다. |
| `evidence_snippets` | array | 답변 생성에 사용한 원문 근거 조각이다. backend는 이 정보를 채팅 reference로 저장할 수 있다. |
| `graph_context` | object | 프론트 graph 하이라이트에 사용할 node/edge 묶음이다. |
| `traversal_paths` | array | graph traversal이 어떤 경로로 진행됐는지 설명하는 디버깅/표시용 경로 목록이다. |

`related_pages[]`와 `graph_context.nodes[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `id` | string | Wiki page id다. |
| `page_type` | string | page 종류다. 보통 `source` 또는 `concept`다. |
| `title` | string | page 제목이다. |
| `slug` | string | page URL/식별용 slug다. |
| `relevance_score` | number | 질문과의 관련도 점수다. 높을수록 관련성이 크다. |
| `role` | string | traversal에서 맡은 역할이다. 예: seed, expanded, evidence 등 구현별 역할값. |
| `depth` | number | 시작점에서 몇 단계 떨어진 page인지 나타낸다. |

`evidence_snippets[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `rank` | number | 근거 번호다. 답변의 `[N]` 표식과 연결된다. |
| `source_document_id` | string | 근거가 나온 대표 원본 문서 id다. 현재 구현 호환용 필드이며, `source_refs`에서 계산할 수 있다. |
| `source_block_ids` | array | 근거로 묶인 대표 source block id 목록이다. 현재 구현 호환용 필드이며, `source_refs`에서 계산할 수 있다. |
| `source_refs` | array | 문서 id와 block id를 쌍으로 가진 세부 reference 목록이다. |
| `text` | string | 답변 근거로 쓰인 원문 또는 요약 snippet이다. |

`graph_context.edges[]`와 `traversal_paths[].edges[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `from_page_id` | string | edge 시작 page id다. |
| `to_page_id` | string | edge 도착 page id다. |
| `link_type` | string | page 사이 원본 관계 종류다. 예: `source_mentions_concept`, `concept_related_to`, `part_of`. `source_related_to` 같은 파생 관계는 포함하지 않는다. |
| `role` | string | 이 edge가 traversal 또는 답변에서 수행한 역할이다. |
| `score` | number | edge 또는 traversal 판단 점수다. |

`traversal_paths[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `path_id` | string | traversal path 식별자다. |
| `role` | string | path 용도다. 답변에 사용된 경로, 후보 경로 등으로 구분한다. |
| `used_for_answer` | boolean | 실제 답변 생성 context에 포함됐는지 여부다. |
| `score` | number | path 전체 점수다. |
| `stop_reason` | string | traversal이 멈춘 이유다. 예: 관련 seed 없음, 점수 기준 미달 등. |
| `nodes` | array | path에 포함된 page id 순서다. |
| `edges` | array | path에 포함된 edge 목록이다. |

## 3. Markdown Agent

Markdown 편집과 새 문서 생성은 모두 `POST /agent/turn`의 action으로 제공한다.

### 3.1 Markdown Edit

Markdown 편집은 독립 endpoint가 아니라 `POST /agent/turn`의 한 action이다.
`action="markdown_edit"`이면 `edit` 필드가 채워지고, backend 또는 frontend는 이 결과를 preview/diff로 보여준 뒤 적용 여부를 결정한다.
`llmPipeline`은 문서를 저장하지 않고, 교체하거나 삽입할 Markdown 조각만 반환한다.

```json
{
  "action": "markdown_edit",
  "route": {
    "action": "markdown_edit",
    "confidence": 0.92,
    "reason": "사용자가 선택 영역을 요약해 달라고 요청함",
    "edit_goal": "shorten"
  },
  "message": null,
  "chat": null,
  "edit": {
    "operation": "replace",
    "requested_target": {
      "type": "selection",
      "start_line": 3,
      "end_line": 8
    },
    "actual_target": {
      "type": "selection",
      "start_line": 2,
      "end_line": 9
    },
    "scope_expanded": true,
    "changed": true,
    "summary": "선택 영역을 더 짧은 설명으로 정리했습니다.",
    "replacement_markdown": "교체될 Markdown 본문"
  },
  "generated_markdown": null
}
```

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `action` | string | 최종 실행 action이다. Markdown 편집이면 `markdown_edit`다. |
| `route` | object | agent router가 어떤 action으로 판단했는지와 이유를 담는다. |
| `message` | string 또는 null | `clarify`, `reject`일 때 사용자에게 보여줄 메시지다. `markdown_edit`에서는 보통 `null`이다. |
| `chat` | object 또는 null | `chat_answer`일 때 query 응답이 들어간다. `markdown_edit`에서는 `null`이다. |
| `edit` | object 또는 null | Markdown 편집 결과다. `markdown_edit`에서 채워진다. |
| `generated_markdown` | object 또는 null | 새 Markdown 생성 결과다. `markdown_edit`에서는 `null`이다. |

`route` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `action` | string | router가 분류한 action이다. |
| `confidence` | number | 분류 신뢰도다. |
| `reason` | string | 왜 이 action으로 판단했는지에 대한 짧은 설명이다. |
| `edit_goal` | string 또는 null | 편집 목적 힌트다. 예: `shorten`, `cleanup`, `translate`, `checklist`, `insert_after`, `create_from_chat`. |

`edit` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `operation` | string | `replace` 또는 `insert_after`다. |
| `requested_target` | object | 사용자가 요청한 line 범위다. |
| `actual_target` | object | 실제 교체 또는 삽입 기준이 되는 line 범위다. |
| `scope_expanded` | boolean | `actual_target`이 `requested_target`을 벗어나면 `true`다. |
| `changed` | boolean | 편집 결과가 요청 당시 Markdown과 다르면 `true`다. |
| `summary` | string | 편집 결과 요약이다. |
| `replacement_markdown` | string | `replace`에서는 `actual_target`을 대체하고, `insert_after`에서는 `actual_target` 뒤에 삽입할 Markdown 조각이다. |

`edit.requested_target`, `edit.actual_target` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `type` | string | 대상 종류다. `selection`, `current_section`, `whole_document` 중 하나다. |
| `start_line` | number | 대상 시작 line이다. 1-base다. |
| `end_line` | number | 대상 종료 line이다. 1-base이며 포함 범위다. |

operation별 계약은 다음과 같다.

- `replace`는 `selection`, `current_section`, `whole_document` target을 지원한다. `replacement_markdown`은 `actual_target` 범위를 대체할 조각이다.
- `insert_after`는 `current_section` target에만 사용한다. `replacement_markdown`은 `actual_target`을 반복하지 않고 해당 섹션 뒤에 추가할 새 Markdown만 포함한다.
- `insert_after` 요청에 `current_section` target이 없으면 `llmPipeline`은 편집 결과를 만들지 않고 `action="clarify"`, `edit=null`과 현재 섹션 선택 안내 `message`를 반환한다.
- `requested_target`은 요청 target과 일치한다. `actual_target`은 `requested_target`을 포함한 채 bounded editable context 안에서 Markdown 구조를 보존하는 범위로 확장할 수 있다.
- 유효하지 않은 `actual_target`과 빈 `replacement_markdown`은 성공 결과로 반환하지 않는다.

### 3.2 Markdown Create

새 Markdown 문서 생성도 `POST /agent/turn`의 action이다. `action="markdown_create"`이면 기존 문서를 교체하지 않는 새 draft가 `generated_markdown`에 채워진다.

```json
{
  "action": "markdown_create",
  "route": {
    "action": "markdown_create",
    "confidence": 0.95,
    "reason": "대화 내용을 새 Markdown 문서로 생성하는 요청",
    "edit_goal": "create_from_chat"
  },
  "message": null,
  "chat": null,
  "edit": null,
  "generated_markdown": {
    "title": "Agent 설계 메모",
    "summary": "대화 내용을 Markdown 문서로 정리했습니다.",
    "markdown": "# Agent 설계 메모\n\n- 편집과 생성을 분리한다."
  }
}
```

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `title` | string | 새 문서 제목 후보다. 비어 있지 않아야 한다. |
| `summary` | string | 사용자에게 보여줄 생성 결과 요약이다. 비어 있지 않아야 한다. |
| `markdown` | string | 새 editor draft에 넣을 Markdown 본문이다. 비어 있지 않아야 한다. |

`llmPipeline`은 첫 생성 결과에서 필수 필드가 비어 있으면 실패 이유를 포함해 한 번 재시도한다. 두 번째 결과도 계약을 만족하지 못하면 성공 응답 대신 아래 422를 반환한다.

### 3.3 Markdown 계약 오류

```json
{
  "detail": {
    "code": "markdown_output_contract_failed",
    "message": "Markdown 편집 결과가 문법 및 보존 조건을 충족하지 못했습니다."
  }
}
```

| HTTP / code | 의미 | backend 처리 |
| --- | --- | --- |
| `422 / agent_turn_route_contract_failed` | 두 번째 분류 결과도 필수 action·confidence·reason 계약을 만족하지 못했다. | action을 임의 추정하지 않고 생성 실패로 정규화한다. |
| `422 / markdown_output_contract_failed` | 두 번째 편집 결과도 Markdown 출력 계약을 만족하지 못했다. | 잘못된 결과를 저장하거나 frontend에 적용안으로 전달하지 않는다. |
| `422 / markdown_create_output_contract_failed` | 두 번째 생성 결과도 `title`, `summary`, `markdown` 필수 계약을 만족하지 못했다. | 새 draft를 만들지 않고 오류를 전달한다. |
| `422 / markdown_target_crosses_structure` | target이 fenced code, table 등 여러 줄 구조의 일부만 포함한다. | target 재선택을 안내하고 원본을 유지한다. |

내부 validator 실패 사유, 보호 token과 잘못된 model 출력은 HTTP 응답에 노출하지 않는다.

## 4. Schema

사용자/workspace별 Wiki schema를 미리보기, 저장, 활성화, 조회하는 기능이다.
endpoint는 `POST /wiki-schema/preview`, `POST /wiki-schema/drafts`, `POST /wiki-schema/{schema_id}/activate`, `GET /wiki-schema/active`다.

### 4.1 Preview 응답

저장하지 않고 사용자의 raw schema를 기능별 fragment로 정리한 결과다.

```json
{
  "fragments": {
    "global_markdown": "- 한국어로 작성한다.",
    "query_markdown": "- 결론을 먼저 제시한다.",
    "ingest_markdown": "- 모터 종류는 concept 후보로 우선 검토한다.",
    "edit_markdown": "- 기존 문장 톤을 보존한다.",
    "concept_markdown": "- 실험 조건과 결과 지표를 concept 관계로 연결한다.",
    "template_markdown": "- 개요, 핵심 포인트, 근거 순서로 작성한다."
  },
  "issues": [
    {
      "severity": "unclear",
      "category": "scope",
      "text": "항상 자세히 작성",
      "reason": "어느 기능에 적용할지 불명확함",
      "section": "global"
    }
  ],
  "preview_markdown": "## 적용될 Schema\n\n### Global\n- 한국어로 작성한다.",
  "has_blocked_issues": false
}
```

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `fragments` | object | raw schema를 기능별로 정리한 sanitized Markdown 조각이다. |
| `issues` | array | schema 입력에서 차단 또는 확인이 필요한 항목 목록이다. |
| `preview_markdown` | string | 사용자에게 보여줄 미리보기 Markdown이다. |
| `has_blocked_issues` | boolean | 저장/활성화 전 반드시 막아야 할 문제가 있는지 여부다. |

`fragments` 필드:

| 필드 | 의미 |
| --- | --- |
| `global_markdown` | 모든 기능에 공통 적용 가능한 언어, 문체, 용어, 작성 기준이다. |
| `query_markdown` | 질문 답변 방식, 근거 제시, 불확실성 처리 기준이다. |
| `ingest_markdown` | 문서 수집/분해, source element 처리 기준이다. |
| `edit_markdown` | Markdown 편집, 보존, 정리 기준이다. |
| `concept_markdown` | concept 후보, 관계, graph/page 생성 기준이다. |
| `template_markdown` | 문서 구조, section 순서, template 기준이다. |

`issues[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `severity` | string | 문제 심각도다. `blocked` 또는 `unclear`다. |
| `category` | string | 문제 분류다. 예: scope, safety, ambiguity. |
| `text` | string | 문제가 된 원문 조각이다. |
| `reason` | string | 문제가 되는 이유다. |
| `section` | string 또는 null | 문제가 연결된 schema section이다. 특정 section이 없으면 `null`일 수 있다. |

### 4.2 Draft 생성 응답

schema를 draft로 저장한 결과다.

```json
{
  "wiki_schema": {
    "id": "schema_123",
    "workspace_id": "ws_123",
    "user_id": "user_123",
    "name": "기본 schema",
    "raw_markdown": "한국어로 답하고 결론 먼저 말해줘.",
    "fragments": {
      "global_markdown": "- 한국어로 작성한다.",
      "query_markdown": "- 결론을 먼저 제시한다.",
      "ingest_markdown": "",
      "edit_markdown": "",
      "concept_markdown": "",
      "template_markdown": ""
    },
    "issues": [],
    "preview_markdown": "## 적용될 Schema\n\n### Global\n- 한국어로 작성한다.",
    "has_blocked_issues": false,
    "status": "draft",
    "schema_version": "1.0",
    "created_at": "2026-07-03T10:00:00+09:00",
    "updated_at": "2026-07-03T10:00:00+09:00",
    "activated_at": null
  }
}
```

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `wiki_schema` | object | 저장된 schema record 전체다. |

`wiki_schema` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `id` | string | schema id다. 활성화 요청에 사용한다. |
| `workspace_id` | string | schema가 적용되는 workspace id다. |
| `user_id` | string | schema 소유 사용자 id다. |
| `name` | string | 사용자가 구분하기 위한 schema 이름이다. |
| `raw_markdown` | string | 사용자가 입력한 원문 schema다. |
| `fragments` | object | 기능별 sanitized Markdown 조각이다. |
| `issues` | array | 저장 시점의 schema issue 목록이다. |
| `preview_markdown` | string | 사용자 확인용 preview Markdown이다. |
| `has_blocked_issues` | boolean | blocked issue 존재 여부다. |
| `status` | string | schema 상태다. `draft` 또는 `active`다. |
| `schema_version` | string | schema 저장 형식 버전이다. |
| `created_at` | string 또는 null | 생성 시각이다. |
| `updated_at` | string 또는 null | 마지막 수정 시각이다. |
| `activated_at` | string 또는 null | active로 전환된 시각이다. draft면 보통 `null`이다. |

### 4.3 Activate 응답

`POST /wiki-schema/{schema_id}/activate`는 활성화된 `wiki_schema` record를 직접 반환한다.
구조는 `draft` 응답의 `wiki_schema` 내부와 같고, 최상위 wrapper가 없다.

```json
{
  "id": "schema_123",
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "name": "기본 schema",
  "raw_markdown": "한국어로 답하고 결론 먼저 말해줘.",
  "fragments": {
    "global_markdown": "- 한국어로 작성한다.",
    "query_markdown": "- 결론을 먼저 제시한다.",
    "ingest_markdown": "",
    "edit_markdown": "",
    "concept_markdown": "",
    "template_markdown": ""
  },
  "issues": [],
  "preview_markdown": "## 적용될 Schema\n\n### Global\n- 한국어로 작성한다.",
  "has_blocked_issues": false,
  "status": "active",
  "schema_version": "1.0",
  "created_at": "2026-07-03T10:00:00+09:00",
  "updated_at": "2026-07-03T10:00:00+09:00",
  "activated_at": "2026-07-03T10:05:00+09:00"
}
```

### 4.4 Active 조회 응답

`GET /wiki-schema/active?workspace_id=...&user_id=...`는 active schema가 있으면 `WikiSchemaResponse`를 반환하고, 없으면 `null`을 반환한다.

```json
null
```

또는:

```json
{
  "id": "schema_123",
  "workspace_id": "ws_123",
  "user_id": "user_123",
  "name": "기본 schema",
  "raw_markdown": "한국어로 답하고 결론 먼저 말해줘.",
  "fragments": {
    "global_markdown": "- 한국어로 작성한다.",
    "query_markdown": "- 결론을 먼저 제시한다.",
    "ingest_markdown": "",
    "edit_markdown": "",
    "concept_markdown": "",
    "template_markdown": ""
  },
  "issues": [],
  "preview_markdown": "## 적용될 Schema\n\n### Global\n- 한국어로 작성한다.",
  "has_blocked_issues": false,
  "status": "active",
  "schema_version": "1.0",
  "created_at": "2026-07-03T10:00:00+09:00",
  "updated_at": "2026-07-03T10:00:00+09:00",
  "activated_at": "2026-07-03T10:05:00+09:00"
}
```

## 5. Lint

Wiki maintenance용 lint 기능이다.
`llmPipeline/app/modules/wiki_ingestion/interfaces/http/routes.py`의 `POST /wiki/maintenance/lint`가 workspace 범위 lint 결과를 반환한다. PostgreSQL과 promotion LLM 실행은 `WikiMaintenancePort`를 통해 infrastructure 경계에서 처리한다.

이 기능은 active meaning cluster 문서를 검사해 다음을 확인한다.

- source block reference가 실제 DB에 존재하는지
- concept 승격 후보가 있는지
- 검토가 필요한 cluster가 있는지
- relation 후보가 유효한지
- 요청 시 승격 후보를 실제 concept page로 materialize했는지

```json
{
  "user_id": "local-user",
  "workspace_id": "local-workspace",
  "active_path": "wiki/local-user/local-workspace/clusters/active.md",
  "orphan_refs": ["doc_123:B9999"],
  "promotion_candidates": ["robust-optimization"],
  "needs_review": ["ambiguous-motor-term"],
  "relation_candidates": [
    {
      "cluster_id": "robust-optimization",
      "target": "concept:taguchi-method",
      "relation": "uses_or_depends_on",
      "evidence": ["claim_001"]
    }
  ],
  "invalid_relations": [
    {
      "cluster_id": "invalid-cluster",
      "target": "",
      "relation": "unknown_relation",
      "evidence": [],
      "reason": "관계 정보가 불완전함",
      "missing": ["target", "relation", "evidence"]
    }
  ],
  "invalid_promotions": [
    {
      "cluster_id": "candidate-without-source",
      "reason": "promotion candidate has no source_refs"
    }
  ],
  "reconciliation_candidates": [
    {
      "pipeline_run_id": "run_789",
      "document_id": "doc_123",
      "invalidated_source_refs": ["doc_123:B0007"],
      "stale_concept_slugs": ["obsolete-concept"],
      "stale_relations": [
        {
          "source": "source:doc_123",
          "target": "concept:obsolete-concept",
          "relation": "source_mentions_concept"
        }
      ],
      "structural_reconciled": false
    }
  ],
  "applied_reconciliations": [],
  "applied_cluster_reconciliation": {
    "removed_claims": [],
    "removed_relations": []
  },
  "materialized_promotions": [
    {
      "cluster_id": "robust-optimization",
      "concept_slug": "robust-optimization",
      "page_id": "page_123"
    }
  ],
  "merged_promotions": [
    {
      "cluster_id": "taguchi-method",
      "concept_slug": "taguchi-method",
      "page_id": "page_456"
    }
  ],
  "materialized_relations": [
    {
      "from": "robust-optimization",
      "to": "taguchi-method",
      "relation": "uses_or_depends_on",
      "evidence": ["claim_001"],
      "source_refs": ["doc_123:B0007"]
    }
  ]
}
```

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `user_id` | string | lint 대상 사용자 namespace다. |
| `workspace_id` | string | lint 대상 workspace namespace다. |
| `active_path` | string | 검사한 active meaning cluster Markdown 경로다. |
| `orphan_refs` | array | `source_blocks` DB에서 찾을 수 없는 source ref 목록이다. |
| `promotion_candidates` | array | concept page로 승격 가능한 cluster id 목록이다. source ref가 있는 candidate만 포함된다. |
| `needs_review` | array | 사람이 확인해야 하는 cluster id 목록이다. cluster 또는 claim decision이 `needs_review`인 경우다. |
| `relation_candidates` | array | 유효한 relation 후보 목록이다. |
| `invalid_relations` | array | target, relation, evidence 중 일부가 없거나 허용되지 않아 materialize할 수 없는 relation 후보 목록이다. |
| `invalid_promotions` | array | 승격 후보로 표시됐지만 source ref가 없어 승격할 수 없는 cluster 목록이다. |
| `reconciliation_candidates` | array | 최신 재편입에서 수정·삭제된 block과 이전 편입 결과를 비교해 찾은 구조 정리 대상이다. |
| `applied_reconciliations` | array | `dry_run=false`에서 오래된 문서-concept 연결·해당 문서의 embedding unit과 다른 활성 문서가 지지하지 않는 relation을 실제 정리한 결과다. |
| `applied_cluster_reconciliation` | object | 최신 재편입 기여분과 비교해 active cluster에서 제거한 이전 claim과 relation 후보다. |
| `materialized_promotions` | array | 이번 lint 실행에서 새 concept page로 실제 승격된 항목이다. `materialize_promotions=true`이고 `dry_run=false`일 때만 생긴다. |
| `merged_promotions` | array | 이미 존재하는 concept에 evidence만 병합된 승격 후보 목록이다. |
| `materialized_relations` | array | 이번 lint 실행에서 실제 `wiki_page_links`로 저장된 relation 목록이다. |

`relation_candidates[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `cluster_id` | string | relation 후보가 나온 cluster id다. |
| `target` | string | 대상 concept이다. 보통 `concept:{slug}` 형식이다. |
| `relation` | string | 관계 종류다. 허용되는 core relation만 유효하다. |
| `evidence` | array | relation 판단 근거 claim id 또는 source ref 목록이다. |

`invalid_relations[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `cluster_id` | string | 문제가 있는 relation이 나온 cluster id다. |
| `target` | string | 파싱된 target 값이다. 없으면 빈 문자열일 수 있다. |
| `relation` | string | 파싱된 relation 값이다. 허용 목록에 없으면 invalid다. |
| `evidence` | array | 파싱된 evidence 목록이다. 비어 있으면 invalid다. |
| `reason` | string | active cluster 문서에 적힌 이유다. 없을 수 있다. |
| `missing` | array | 어떤 필드가 없거나 잘못됐는지 나타낸다. 가능한 값은 `target`, `relation`, `evidence`다. |

`materialized_promotions[]`와 `merged_promotions[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `cluster_id` | string | 승격 또는 병합된 cluster id다. |
| `concept_slug` | string | 생성되었거나 병합된 concept slug다. |
| `page_id` | string | 대상 Wiki page id다. |

`materialized_relations[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `from` | string | relation 시작 concept slug다. |
| `to` | string | relation 대상 concept slug다. |
| `relation` | string | 저장된 relation type이다. |
| `evidence` | array | relation을 뒷받침한 claim id 또는 source ref 목록이다. |
| `source_refs` | array | evidence에서 해석된 실제 source ref 목록이다. 일부 materialize 경로에서는 없을 수 있다. |

`reconciliation_candidates[]` 필드:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `pipeline_run_id` | string | 정리 대상이 발생한 최신 재편입 실행 ID다. |
| `document_id` | string | 재편입된 원본 문서 ID다. |
| `invalidated_source_refs` | array | 수정·삭제로 기존 의미 기여가 무효화된 `document_id:block_id` 목록이다. |
| `stale_concept_slugs` | array | 이전 편입에는 있었지만 최신 편입에는 없는 문서-concept 연결 대상이다. |
| `stale_relations` | array | 이전 편입에는 있었지만 최신 편입에는 없는 relation이다. 다른 활성 문서가 같은 relation을 지지하면 삭제하지 않는다. |
| `structural_reconciled` | boolean | 해당 실행의 구조 정리를 이미 적용했는지 나타낸다. |

무효화된 source ref가 포함된 cluster는 자동 승격 대상에서 제외되고
`needs_review`에 포함된다. `dry_run=false`에서는 최신 재편입 기여분에 없는
이전 claim과 그 claim만 근거로 삼는 relation 후보를 active cluster에서
제거한다. Concept 본문의 정의·근거 문장을 의미에 맞게 다시 쓰는 작업은 별도
의미 정합성 단계가 필요하다.

현재 lint에서 유효한 core relation은 다음 값이다.

```text
part_of
child_of
uses_or_depends_on
contrasts_with
supports_or_enables
related_evidence
```

단, 실제 `wiki_page_links`로 materialize되는 relation은 `related_evidence`를 제외한 core relation이다.
