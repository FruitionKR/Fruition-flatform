# AI pipeline ingest 흐름

## 1. 문서 목적

이 문서는 현재 `services/ai/pipeline`이 문서나 선택된 채팅 pair를 ingest할 때 다음 질문에 한 번에 답하기 위한 기준 문서다.

- 어떤 실행 유형이 있는가?
- 각 단계는 무엇을 입력받고 어떤 출력을 만드는가?
- LLM 출력과 pipeline 계산 결과는 어떻게 조립되는가?
- 어떤 프롬프트가 어떤 조건에서 사용되는가?
- 최종 결과는 어디에 어떤 형태로 저장되는가?

설명은 현재 코드 구현을 기준으로 한다. 초기 설계 의도는 과거 의사록의 다음 원칙과 이어진다.

> LLM은 의미 판단을 담당하고, pipeline 코드는 검증·정규화·계산·조립·저장을 담당한다.

다만 현재 구현은 초기 의사록 이후 evaluator/patch loop, reingest, meaning cluster, DB·object storage 저장까지 확장되었다. 따라서 과거 의사록의 단계명이나 JSONL 중심 설명보다 현재 코드를 우선한다.

주요 기준 코드:

- 실행 진입점: `services/ai/pipeline/app/modules/wiki_ingestion/interfaces/http/routes.py`
- 실행 orchestration: `services/ai/pipeline/run_lab.py`
- 의미 생성·평가 graph: `services/ai/pipeline/app/modules/wiki_generation/infrastructure/wiki_generation_evaluator_graph.py`
- 정규화: `services/ai/pipeline/app/modules/wiki_generation/infrastructure/normalize.py`
- page 조립: `services/ai/pipeline/app/modules/wiki_generation/infrastructure/assemble.py`
- 영속화: `services/ai/pipeline/app/modules/wiki_ingestion/infrastructure/postgres_wiki_output_persistence.py`

## 2. 한눈에 보는 전체 흐름

```text
API 진입
  ├─ POST /pipeline/runs
  │    └─ 전체 block → 일반 semantic extraction
  │
  ├─ POST /pipeline/reingest-runs
  │    └─ block diff → added/modified packet → 일반 semantic extraction
  │
  └─ POST /chat-wiki/runs
       └─ partial → 전달된 선택 pair block → chat semantic extraction
                         │
                         ▼
              공통 Semantic Normalization
  │
  ▼
LLM evaluator
  ├─ 통과 ───────────────────────────────┐
  └─ 실패                               │
       ├─ 명확한 규칙 보정               │
       ├─ targeted semantic patch        │
       ├─ 관련 packet 재생성             │
       └─ 전체 재생성                    │
             └─ 최대 시도까지 반복 ─────┘
  │
  ▼
LLM concept resolution + pipeline 적용
  │
  ├─ 일반 / reingest / chat partial
  │    └─ skeleton 또는 section polish
  │
  ▼
Source page / Concept page pipeline Markdown 조립
  │
  ▼
pipeline page link 생성
  │
  ▼
LLM concept-update judge / meaning-cluster judge
  │
  ▼
Runtime manifest 반환
  │
  ▼
PostgreSQL + S3 호환 object storage 영속화
  │
  ▼
Embedding job 시작
```

핵심은 LLM이 최종 Markdown 전체를 한 번에 쓰지 않는다는 점이다. 기본 설정에서는 LLM이 의미 구조와 source page의 summary/key points 일부만 만들고, Markdown의 frontmatter·섹션·citation·link는 pipeline이 조립한다.

## 3. API 진입과 실행 분기

**무엇을 하는가**

HTTP 요청을 내부 `PipelineRunCommand`로 바꾸고 run id, 실행 mode와 page 생성 전략을 확정한다.

**구현 위치**

- `services/ai/pipeline/app/modules/wiki_ingestion/interfaces/http/routes.py`
- `services/ai/pipeline/app/modules/wiki_ingestion/interfaces/http/schemas.py`
- `services/ai/pipeline/app/modules/wiki_ingestion/application/run_pipeline.py`
- `services/ai/pipeline/run_lab.py`

**입력**

- `user_id`, `workspace_id`, `document_id`
- 일반 ingest: `document_id`로 조회한 `extracted_text_uri` 또는 Markdown/text `source_uri`
- reingest/chat: 요청 body의 inline Markdown
- `mode`, provider, model
- `source_page_mode`, `concept_page_mode`
- reingest/chat 여부와 기존 context

실행 유형은 이 단계에서 다음처럼 확정된다.

| 유형 | Endpoint | 추가 입력 | 이후 단계의 차이 |
| --- | --- | --- | --- |
| 일반 ingest | `POST /pipeline/runs` | Spring이 생성한 `document_id` | 전체 block을 새로 추출 |
| reingest | `POST /pipeline/reingest-runs` | 최신 전체 Markdown + 이전 성공 run | block diff 후 추가·수정분만 재추출 |
| chat | `POST /chat-wiki/runs` | `selection_mode=partial` + `input_markdown` + `input_blocks` | 선택 pair를 독립 source로 처리 |

**입력 처리 규칙**

모든 pipeline route는 `X-Internal-Token`을 요구한다. 입력 schema와 provider/model을 검증한다. `source_page_mode=auto`는 `api`/`generic-chat`에서 `section-polish`, `concept_page_mode=auto`는 `skeleton`으로 해석된다. Chat Wiki는 `selection_mode=partial`만 허용하고 `input_blocks`와 `input_markdown`을 모두 요구한다.

주요 기본값은 `max_packet_chars=7000`, `overlap_blocks=1`, `wiki_evaluation_loop=true`, `max_eval_attempts=2`, `wait=false`, `save_debug_json=false`다. `user_id`, `workspace_id`는 선택 호환 필드이며 route는 document row의 값과 다르면 `409`를 반환한다. 저장 namespace는 document row의 user/workspace다.

**출력과 다음 단계**

`PipelineRunCommand`와 실행 metadata를 만들고 Markdown block 추출로 넘긴다. run은 먼저 `pipeline_runs`에 등록된다. 이후 document 조회·actor 검증·입력 object 조회가 실패하면 HTTP 오류가 반환될 수 있으므로 등록된 run의 정리 여부를 별도로 확인해야 한다.

`wait=false`는 `running` 상태와 `run_id`, `output_dir`, `log_path`를 즉시 반환하고 background task를 실행한다. `wait=true`는 완료 후 runtime manifest까지 `PipelineRunOut.manifest`에 담는다. `GET /pipeline/runs/{run_id}`는 저장 manifest를, `/logs`는 pipeline log를 반환한다.

## 4. 공통 Markdown block 추출

**무엇을 하는가**

원본 Markdown을 LLM 근거와 citation이 추적할 수 있는 최소 단위로 나눈다.

**입력**

원본 Markdown, `document_id`, block id 생성 context를 받는다.

**Block 생성 규칙**

heading, paragraph, list, code block 같은 Markdown 구조 경계를 보존해야 하며 각 block에는 안정적인 `source_block_id`가 필요하다.

구현은 `MarkdownBlockExtractor`와 `run_lab._extract_pipeline_source()`가 담당한다. 일반 문서는 LLM용 `B0001` 형태의 짧은 anchor를 사용하며, extractor의 `source_reference_id`는 `ref_<hash>_md_bNNNN` 형태의 안정적인 source id다. 일반 문서의 normalizer와 DB contract는 `block_id`로 `Bxxxx`를 검증·저장하고, 전역 citation/display ref가 필요할 때만 `document_id:Bxxxx` 형태로 확장한다. Chat은 schema가 허용하는 임의의 nonempty `block_id`를 그대로 보존할 수 있다.

**출력 예시**

```json
{
  "source_blocks": [
    {
      "document_id": "doc_123",
      "block_id": "B0012",
      "source_reference_id": "ref_ab12cd34_md_b0012",
      "block_type": "paragraph",
      "text": "Persistent Wiki는 출처 block을 유지한다.",
      "section_path": ["설계", "근거 관리"]
    }
  ]
}
```

**pipeline 처리와 다음 단계**

block 순서와 원문을 저장 가능한 구조로 정규화한다. 일반 ingest/chat은 packet 구성으로, reingest는 먼저 이전 block과 비교하는 단계로 넘긴다. 이후 모든 `source_refs`는 이 목록에 실제로 존재해야 한다.

`save_debug_json=true`이면 `document.json`, `block_map.json`을 남긴다.

## 5. Reingest 전용 block 비교

**무엇을 하는가**

reingest일 때 새 block과 이전 block을 비교해 LLM이 다시 읽어야 할 범위를 줄인다. 일반 ingest에서는 이 단계를 건너뛴다.

**입력**

새 `source_blocks[]`, 이전 실행의 block과 source contribution을 받는다.

구현은 `services/ai/pipeline/app/modules/wiki_ingestion/domain/source_block_changes.py`에 있다. 새 block은 기존 최대 `Bxxxx` 다음 번호를 받고, 내용이 같은 moved block은 기존 id를 재사용한다.

**비교 규칙**

비교 결과는 `added`, `modified`, `unchanged`, `moved`, `deleted` 중 하나여야 한다. 동일한 block이 위치만 바뀌면 기존 block id를 유지한다.

**출력과 사용**

| 상태 | 다음 semantic packet 포함 | 기존 의미 처리 |
| --- | --- | --- |
| `added` | 포함 | 새 의미 추가 |
| `modified` | 포함 | 이전 의미 대체 후보 |
| `unchanged` | 제외 | 기존 의미 유지 |
| `moved` | 제외 | 기존 의미와 block id 유지 |
| `deleted` | 제외 | stale contribution 후보 |

추가·수정 block만 packet 구성으로 넘기고, unchanged 의미와 deleted 기여 정보는 나중의 병합·reconciliation에 사용한다.

manifest의 `source_block_changes`에는 `unchanged_block_ids`, `moved_block_ids`, `added_block_ids`, `modified_block_ids`, `deleted_block_ids`, `invalidated_block_ids`가 남는다. 추가·수정 block이 없으면 semantic extraction과 concept resolution을 생략하고 기존 active context로 page를 다시 조립할 수 있다.

## 6. 공통 Semantic Packet 구성

**무엇을 하는가**

source block을 모델 context 제한 안의 묶음으로 만든다. 의미가 경계에서 끊기지 않도록 기본적으로 인접 packet에 block 하나를 겹친다.

구현은 `SemanticPacketBuilder`가 담당한다.

**입력**

semantic 대상 `source_blocks[]`, `max_packet_chars`, `overlap_blocks`를 받는다.

**Packet 구성 규칙**

block 본문을 자의적으로 다시 쓰지 않고 packet id와 포함된 block id 목록을 보존한다.

**출력 예시**

```json
{
  "packet_id": "packet-2",
  "source_block_ids": ["doc-1:b11", "doc-1:b12", "doc-1:b13"],
  "text": "[block:doc-1:b11] ...\n[block:doc-1:b12] ..."
}
```

packet은 그대로 semantic extraction의 user prompt가 된다. 겹친 block에서 중복 결과가 생길 수 있으므로 이후 normalization이 이를 합친다.

`save_debug_json=true`이면 `packets/chunk_0001.md`처럼 packet별 입력을 남긴다.

## 7. API별 Semantic Extraction 분기

**무엇을 하는가**

원문 packet에서 Wiki를 만들기 위한 의미 요소를 추출한다. 모델은 최종 Markdown을 쓰지 않고, 근거가 연결된 의미 JSON을 만든다.

**진입 조건과 입력**

semantic packet이 하나 이상 있을 때 packet별로 실행한다. 일반 문서는 `services/ai/pipeline/prompts/semantic_extraction.system.md`, Chat은 `services/ai/pipeline/prompts/chat_semantic_extraction.system.md`를 사용한다. 현재 Chat API에는 full/append 실행이나 `chat_semantic_append.system.md`가 없다.

user prompt에는 다음이 들어간다.

- packet id
- block id가 표시된 원문
- 문서 또는 chat 실행 context

## 7A. 일반 문서와 Reingest Extraction

일반 ingest는 전체 block packet, reingest는 5단계에서 확정한 added/modified block packet만 입력한다. 둘 다 `services/ai/pipeline/prompts/semantic_extraction.system.md`를 사용한다. reingest의 unchanged 의미는 LLM 입력에 반복하지 않고 기존 source artifact와 조립 context에 반영한다.

## 7B. Chat Partial Extraction

선택한 Q&A pair를 독립 source로 처리하며 `services/ai/pipeline/prompts/chat_semantic_extraction.system.md`를 사용한다. `input_blocks`가 block 경계를 확정하고 호출자가 전달한 nonempty `block_id`를 그대로 보존하며, extractor는 Markdown을 다시 쪼개지 않는다. prompt는 chat pair를 `qa_episode`, `follow_up`, `correction`, `decision` 중심의 지식 episode로 읽도록 요구한다.

## 7C. Chat context 경계

현재 Chat partial 실행은 기존 source context를 읽지 않고, 전달된 `input_blocks`만 semantic extraction 입력으로 사용한다. 따라서 기존 source에 누적하거나 append evaluator로 갱신하는 분기는 구현되어 있지 않다.

## 7E. 공통 Prompt 계약과 Semantic 출력

**메시지 조립**

```text
system
  = 실행 분기에 맞는 *.system.md 전문

user
  Stage input: ChunkSemanticExtraction
  chunk_id: chunk_0001
  document_id: doc_123
  SOURCE BLOCKS
    [B0001] ...
    [B0002] ...
```

현재 semantic prompt user payload에는 `chunk_id`, `document_id`, 현재 packet의 `SOURCE BLOCKS`만 들어간다. prompt 파일 안의 “backend”는 최종 계산·조립을 담당하는 pipeline 코드를 뜻한다.

**Prompt에 실제로 들어가는 판단 지시**

```text
SOURCE BLOCKS 전체를 키워드가 아니라 의미로 읽어라.
최종 Wiki page를 작성하지 마라.
term을 category/core_concept/section_candidate/mention 중 정확히 하나로 분류하라.
factual item은 현재 SOURCE BLOCKS의 direct anchor를 반드시 포함하라.
direct anchor를 댈 수 없으면 그 항목을 출력하지 마라.
evidence claim 하나에는 하나의 원자 주장만 넣어라.
ref count, range, relation, 최종 link와 citation 문자열은 계산하지 마라.
설명문이나 Markdown fence 없이 지정된 JSON만 반환하라.
```

분류 지시는 단순 키워드 추출이 아니다.

| 출력 분류 | Prompt 판단 기준 | 이후 효과 |
| --- | --- | --- |
| `category` | 넓은 주제·탐색 label | source metadata |
| `core_concept` | 독립 설명 가능, 중심적, 재사용 가능 | 즉시 concept page 후보 |
| `section_candidate` | 현재 source 설명에는 중요하지만 독립 page 근거는 약함 | meaning cluster·향후 promotion 후보 |
| `mention` | 예시·배경·도구·주변 용어 | source mention과 cluster 후보 |

불확실하면 더 보수적인 분류를 선택하라는 지시 때문에 모든 중요 명사가 concept page로 승격되지 않는다. evidence claim은 하나의 원자 주장만 담고 그 주장을 직접 증명하는 anchor만 사용한다.

**같은 입력이 Prompt 때문에 결과로 바뀌는 과정**

입력:

```text
[B0006] Persistent Wiki는 새 문서가 들어올 때 기존 Wiki를 갱신한다.
[B0007] Obsidian은 이 구조를 설명하기 위한 비교 사례로 언급됐다.
```

prompt가 “중심적이고 재사용 가능한 개념만 core”라고 지시하므로 모델은 두 명사를 동일하게 처리하지 않는다.

```json
{
  "core_concepts": [
    {
      "title": "Persistent Wiki",
      "slug_hint": "persistent-wiki",
      "definition": "새 문서를 기존 Wiki에 누적하는 지식 구조",
      "why_page_worthy": "문서 전체의 중심이며 다른 source에서도 재사용 가능",
      "evidence_block_ids": ["B0006"]
    }
  ],
  "mentions": [
    {
      "name": "Obsidian",
      "slug_hint": "obsidian",
      "context": "비교 사례",
      "evidence_block_ids": ["B0007"]
    }
  ],
  "evidence_claims": [
    {
      "claim": "Persistent Wiki는 새 문서가 들어올 때 기존 Wiki를 갱신한다.",
      "anchor_block_ids": ["B0006"],
      "related_concept_hints": ["persistent-wiki"],
      "confidence": 0.94
    }
  ]
}
```

그 결과 `Persistent Wiki`는 concept resolution과 concept page 조립으로 가고, `Obsidian`은 즉시 concept page가 되지 않고 source mention/meaning cluster 후보로 간다. 모델이 `[B9999]`를 만들면 pipeline이 allow-list 밖 ref로 제거한다. 모델은 citation 문구를 쓰지 않았으므로 최종 citation 표기는 pipeline이 일관되게 조립한다.

**모델 출력 계약**

```json
{
  "chunk_id": "chunk_0001",
  "semantic_summary": "이 packet의 원문 preview 요약",
  "key_points": [
    {"text": "검색에 사용할 핵심 내용", "anchor_block_ids": ["B0002"]}
  ],
  "observations": [
    {
      "type": "definition",
      "title": "Persistent Wiki",
      "query_text": null,
      "summary": "근거와 함께 지식을 누적하는 구조",
      "claims": ["source block 근거를 유지한다."],
      "related_concept_hints": ["persistent-wiki"],
      "anchor_block_ids": ["B0012"]
    }
  ],
  "categories": [{"name": "technology"}],
  "core_concepts": [
    {
      "title": "Persistent Wiki",
      "slug_hint": "persistent-wiki",
      "aliases": ["지속적 위키"],
      "definition": "근거와 함께 지식을 누적하는 Wiki 구조",
      "why_page_worthy": "다른 source에서도 재사용 가능한 중심 개념",
      "evidence_block_ids": ["B0012"]
    }
  ],
  "section_candidates": [],
  "mentions": [],
  "evidence_claims": [
    {
      "claim": "Persistent Wiki는 source block 근거를 유지한다.",
      "anchor_block_ids": ["B0012"],
      "related_concept_hints": ["persistent-wiki"],
      "confidence": 0.94
    }
  ],
  "needs_neighbor_context": false,
  "context_problem": null
}
```

`observation.type`은 `source_claim`, `definition`, `comparison`, `example`, `qa_episode`, `follow_up`, `correction`, `decision` 중 하나다. core concept은 독립 설명 가능성·문서 중심성·다른 source에서의 재사용 가능성을 모두 만족해야 한다. 불확실하면 `core_concept → section_candidate → mention` 방향으로 보수적으로 분류한다.

계약상 허용되지 않는 대표 출력은 packet에 없는 ref, 근거 없는 새 사실, JSON 밖의 설명문, 정의 없는 concept, 광범위한 비원자 claim, 필드 타입이 다른 값이다. alias는 검색에 유용한 2~4개 정도만 허용하며 slug 변형을 대량 생성하지 않는다.

**pipeline의 parse·검증**

응답을 JSON으로 parse하고 필드 타입을 맞춘다. 각 ref를 현재 source block allow-list와 대조하고, 잘못된 ref나 빈 항목은 제거한다. 이 단계에서는 packet별 결과를 유지하며 전체 문서 중복 제거는 다음 normalization에서 수행한다.

**출력과 다음 단계**

packet별 semantic artifact와 raw/parse 상태를 만든다. 성공 결과는 normalization으로 넘어가고, parse 실패는 stage retry 또는 실행 실패 정보가 된다. `save_debug_json=true`일 때 packet, prompt와 raw response를 디버깅 artifact로 더 자세히 확인할 수 있다.

실제 prompt 전문과 응답을 별도로 기록하려면 `LLM_PROMPT_LOG_DIR`를 설정한다. `save_debug_json=true`일 때 pipeline 산출물에 raw 응답을 남길 수 있다. LangSmith tracing이 활성화된 경우 evaluator graph node와 하위 chat-completions span도 확인할 수 있다.

## 8. 분기 합류: Semantic Normalization

**무엇을 하는가**

여러 packet의 semantic JSON을 문서 단위의 하나의 의미 구조로 합친다.

**입력**

packet별 semantic artifact, 전체 source block allow-list, reingest이면 기존 source artifact와 block 비교 결과를 받는다.

**Normalization 규칙**

ref가 없는 주장 제거, 중복 항목 병합, 필드별 안정적인 순서와 형태 유지가 규칙이다.

**처리**

- overlap block 때문에 반복된 항목을 합친다.
- 같은 concept 표기와 중복 의미를 정리한다.
- source ref를 deduplicate하고 실제 block 기준으로 다시 검증한다.
- reingest에서는 `source_page_context_normalized()`가 기존 source context와 새 결과를 조립한다.

**출력과 다음 단계**

문서 단위 `normalized` artifact를 만든다. 이것이 evaluator, concept resolution, source/concept page 조립이 공유하는 기준 입력이다. 모델의 packet JSON을 page 단계가 직접 소비하지 않는 이유가 이 normalization 경계다.

대표 normalized 구조에는 source summary/key points/observations, category ledger, concept ledger, section/mention 후보, evidence units가 들어간다. pipeline은 짧은 anchor를 document 범위의 reference로 복원하고 concept slug, mention count, display refs, evidence id를 계산한다. LLM은 이 계산값을 직접 만들지 않는다.

## 9. Wiki Generation Evaluator와 Targeted Patch

**무엇을 하는가**

normalized 결과가 원문 근거를 빠뜨리거나 잘못 분류했는지 검사하고, 문제 필드만 보정한다.

**입력과 prompt**

기본 `wiki_evaluation_loop=true`일 때 실행한다.

- evaluator system prompt: `services/ai/pipeline/prompts/wiki_generation_evaluator.system.md`
- evaluator user prompt: source blocks, normalized artifact, 평가 시도 번호
- patch system prompt: `services/ai/pipeline/prompts/wiki_generation_patch.system.md`
- patch user prompt: evaluator issue, 수정 허용 field, 관련 block과 현재 값

evaluator prompt는 completeness, grounding, 분류 일관성을 검사하고 pass/fail과 구체적인 issue를 JSON으로 반환하도록 한다. patch prompt는 전체 artifact를 다시 쓰지 말고 issue가 지정한 editable target만 반환하도록 제한한다.

**Prompt가 보정 범위를 결정하는 방식**

```text
Evaluator:
  factual item에 direct ref가 없으면 high-severity missing_ref로 판정하라.
  broad evidence, over-fragmented concept, 잘못 승격된 section/mention을 issue로 만들어라.
  issue가 하나라도 있으면 passed=false로 반환하라.

Targeted patch:
  supplied issues만 고쳐라.
  editable_targets에 없는 항목은 수정하지 마라.
  source_blocks에 있는 anchor만 사용하라.
  broad claim을 나눌 때 replace 하나에 여러 atomic item을 넣어라.
```

예를 들어 모델의 `“문서를 처리하고 Wiki와 검색과 유지보수를 수행한다” [B1,B2,B3]`가 너무 넓으면 evaluator가 `evidence_too_broad`를 반환한다. patch prompt의 editable target이 해당 evidence 하나뿐이므로 모델은 unrelated concept을 다시 쓰지 않고 `문서를 Wiki로 변환한다 [B1]`, `Wiki 근거를 검색한다 [B2]`처럼 그 항목만 분리한다. pipeline은 patch operation을 원본 normalized에 적용한 뒤 재평가한다.

evaluator user payload의 핵심 구조:

```json
{
  "attempt": 1,
  "source_blocks": [{"anchor": "B0001", "text": "..."}],
  "normalized": {
    "source": {},
    "concept_ledger": [],
    "evidence_units": []
  }
}
```

patch user payload에는 `issues`, `editable_targets`, issue 주변 `source_blocks`가 들어간다. system prompt는 이 목록을 “수정 가능한 전체 범위”로 취급하므로 unrelated item을 다시 쓰면 계약 위반이다.

**evaluator 출력 계약 예시**

```json
{
  "scores": {
    "source_excerpt_fidelity": 4,
    "concept_groundedness": 3,
    "relation_faithfulness": 0.8,
    "evidence_relevance": 0.9,
    "overall": 0.82
  },
  "passed": false,
  "retry_recommended": true,
  "issues": [
    {
      "metric": "concept_groundedness",
      "type": "evidence_too_broad",
      "severity": "high",
      "target": ["ev_0001"],
      "reason": "여러 기능을 한 claim에 포함했다.",
      "feedback": "직접 근거별 원자 claim으로 분리한다."
    }
  ],
  "warnings": [],
  "retry_feedback": "ev_0001만 직접 근거별로 분리한다."
}
```

통과 기준은 `source_excerpt_fidelity >= 4`, `concept_groundedness >= 4`, `relation_faithfulness >= 0.75`, `evidence_relevance >= 0.75`, blocking issue 없음이다. 필수 수정은 `issues`, 선택 개선은 `warnings`에 둔다.

targeted patch 출력은 `replace`, `remove`, `add` operation 배열이다. 각 operation은 정확한 `chunk_id`, collection, index와 replacement items를 지정한다. broad evidence를 나눌 때는 하나의 `replace`에 여러 원자 item을 넣고, core concept을 강등할 때는 core에서 `remove`하고 section/mention에 `add`한다.

**pipeline 처리와 다음 단계**

pass이면 normalized를 그대로 concept resolution로 넘긴다. fail이면 issue별 patch 결과를 기존 normalized의 허용 field에만 병합하고 다시 평가한다. 기본 최대 생성 시도는 2회다. 끝까지 남은 issue가 있어도 유효한 normalized 결과가 있으면 page 조립이 계속될 수 있으며 unresolved issue는 runtime/debug 정보에 남는다.

## 10. Concept Resolution

**무엇을 하는가**

추출된 concept이 기존 Wiki concept과 같은 대상인지, 새 page가 필요한지, 버려야 하는지를 결정한다.

**입력과 prompt**

`services/ai/pipeline/prompts/concept_resolution.system.md`에 incoming concept, 기존 concept 후보, alias/slug 정보와 근거 ref를 전달한다.

정확한 prompt decision은 `merge_into`, `link_to`, `create_new`다. user payload는 다음 세 묶음으로 구성된다.

```text
INCOMING CONCEPTS
  신규 normalized concept ledger

EXISTING CONCEPT INDEX
  workspace의 기존 slug/title/aliases/summary

MISSING RELATED CONCEPT HINTS
  evidence에는 나오지만 incoming ledger에는 없는 hint
```

system prompt는 철자보다 의미를 비교하고, 같은 의미일 때만 merge하며, 관련 있지만 다른 의미는 link, 합칠 때 의미가 사라지면 create하도록 지시한다. `canonical_slug`와 `link_targets`는 입력에 존재하는 slug만 사용할 수 있다.

**Prompt가 중복 Page 생성을 막는 방식**

```text
incoming:
  title=Persistent Wiki
  slug=persistent-wiki

existing:
  title=지속적 위키
  slug=persistent-knowledge-wiki
  aliases=[Persistent Wiki]

지시:
  철자가 아니라 의미를 비교하라.
  동의어일 때만 merge_into를 사용하라.
  입력에 없는 slug를 만들지 마라.
```

모델이 `merge_into`, `canonical_slug=persistent-knowledge-wiki`, `alias_to_add=Persistent Wiki`를 반환하면 pipeline은 신규 page를 만들지 않고 기존 page에 evidence와 alias를 합친다. 두 개념이 관련만 있고 정의가 다르면 `link_to` 결과가 되어 page identity는 유지되고 관계 후보만 생긴다.

**출력 계약 예시**

```json
{
  "resolutions": [
    {
      "incoming_slug": "persistent-knowledge-wiki",
      "decision": "merge_into",
      "canonical_slug": "persistent-wiki",
      "alias_to_add": "Persistent Knowledge Wiki",
      "link_targets": [],
      "confidence": 0.93,
      "reason": "정의와 근거 문맥이 동일한 개념이다."
    }
  ],
  "hint_resolutions": []
}
```

**pipeline 검증과 다음 단계**

허용 decision은 `merge_into`, `link_to`, `create_new`다. missing related hint에는 `merge_into_current`, `merge_into_existing`, `related_only`, `promote_new_concept`, `unresolved`를 사용한다. 존재하지 않는 target slug와 incoming/index에 없는 임의 slug를 거부한다. 최종 concept 집합은 concept별 evidence 선택과 page 조립으로 넘어간다.

## 11. Source Page 조립 분기

**무엇을 하는가**

normalized 의미를 원문을 대표하는 source page Markdown으로 만든다.

**입력**

normalized artifact, source blocks, 문서 metadata, 기존 source page와 `source_page_mode`를 받는다.

실행 유형별 page 입력은 다음과 같다.

| 유형 | page 조립 기준 |
| --- | --- |
| 일반 ingest | 새 normalized 전체 |
| reingest | 기존 source context + 추가·수정 normalized − 삭제 기여 |
| chat | `input_blocks`로 전달된 선택 pair의 normalized |

## 11A. 일반·Reingest·Chat Partial Source Page

`source_page_mode=skeleton`이면 LLM 없이 normalized artifact를 고정 section에 배치한다. 기본 API의 `auto`는 `section-polish`로 해석되며 `services/ai/pipeline/prompts/section_polish.system.md`에 section 이름, draft body, 관련 evidence와 source block을 보낸다.

section-polish user payload:

```text
section: source_summary_and_key_points
existing source context: ...
draft title/text/items: ...
validated evidence claims: ...
SOURCE BLOCKS:
  [B0001] ...
```

system prompt는 요청 section만 반환하고, 전체 page·frontmatter·citation·link를 만들지 않으며, evidence claim을 Evidence section처럼 복사하지 않도록 한다. `source_summary_and_key_points`는 이전 요약 뒤에 문장을 붙이는 방식이 아니라 전체 source를 대표하는 하나의 summary로 다시 작성한다.

예를 들어 draft summary가 거칠더라도 prompt가 전체 page 작성을 금지했기 때문에 모델 출력은 `section/title/text/items/anchor_block_ids` JSON에 머문다. pipeline은 이 결과를 `Summary`와 `Key Points`에만 넣고, `Observations`, `Core Concepts`, citation과 frontmatter는 normalized artifact로 별도 조립한다.

section polish는 전체 page가 아니라 지정 section의 `section`, `title`, `text`, `anchor_block_ids`, `items`, `related_concept_hints`, `confidence`만 반환한다. frontmatter, Evidence, link와 citation을 직접 쓰지 않는다.

일반 ingest는 새 normalized 전체, reingest는 기존 source context와 신규 normalized를 조립한 결과, chat은 선택 pair의 normalized만 사용한다. Chat 결과는 기존 source에 누적하지 않고 독립 source page가 된다.

## 11B. 공통 Markdown 조립과 출력

**pipeline 조립**

frontmatter와 `Summary`, `Key Points`, `Observations`, `Categories`, `Core Concepts`, `Section Candidates`, `Mentions` 같은 고정 구조는 pipeline이 소유한다. 모델 section을 검증한 뒤 citation marker와 Wiki link를 붙인다.

**출력과 다음 단계**

source page artifact에는 slug, title, Markdown, source refs와 page metadata가 들어간다. concept page/link 생성과 runtime manifest로 전달된다.

chat은 선택 범위를 독립 source page로 만든다. 기존 active source 누적은 이 route의 계약에 없다.

## 12. Concept Page 조립

**무엇을 하는가**

resolution이 확정한 concept별로 정의와 근거를 가진 page를 만든다.

**입력**

concept card, 선택된 source blocks, relation 후보와 `concept_page_mode`를 받는다. 기존 concept Markdown은 LLM 입력이 아니라 persistence 단계에서 기존 page evidence를 누적할 때 읽는다.

**Mode별 생성 규칙**

기본 `skeleton` mode에서는 pipeline이 definition, aliases, evidence와 related concept을 고정 section에 배치한다. `full-llm`/`api`에서는 아래 LLM prompt 계약을 추가로 적용하고, `section-polish`는 concept section만 다듬는다.

`services/ai/pipeline/prompts/concept_page_generation.system.md`의 user payload에는 concept card, 선택된 evidence claims와 해당 claim을 증명하는 source blocks가 들어간다. 모델은 `definition`, `key_points`, `evidence`, `related_concept_hints` JSON을 반환하며 Markdown 전체·frontmatter·임의 citation을 반환하지 않는다. pipeline은 모델 ref를 concept별 source block allow-list와 다시 대조한다.

모델은 제공된 evidence ref만 사용할 수 있다. pipeline은 allow-list 밖 ref를 제거하고 frontmatter, section 순서와 citation을 직접 만든다.

**출력과 다음 단계**

concept page artifact와 concept별 근거 mapping을 만든다. source page와 함께 link builder로 넘어간다.

최종 Markdown section은 `Definition`, `Why It Matters`, `Key Points`, `Aliases`, `Evidence`, `Related Concepts`, `Reference Summary` 순서를 사용한다. 기본 skeleton에서는 semantic extraction의 definition/evidence를 pipeline이 직접 배치하므로 concept별 writer 호출은 없다.

## 13. Page Link와 Meaning Cluster

**무엇을 하는가**

page 사이의 탐색 edge를 만들고, 아직 바로 page로 승격하지 않을 의미 후보를 active meaning cluster로 누적한다.

**입력과 prompt**

source/concept page, concept resolution, normalized mention/relation 후보를 받는다. 기본 source-to-concept link는 LLM 없이 만든다. concept update와 meaning cluster 후보가 있을 때만 코드 내부 judge prompt가 기존 상태와 신규 후보를 비교한다.

concept-update judge는 section/mention 후보가 기존 concept에 실질적인 새 정의·절차·결정 근거를 추가하는지 판단한다. meaning-cluster judge는 기존 active cluster와 신규 candidate의 의미가 같은지, 별도 cluster인지, 아직 review가 필요한지 제한된 JSON decision으로 반환한다. 두 prompt 모두 최종 page link를 직접 쓰지 않으며 pipeline이 유효한 slug/ref만 적용한다.

judge는 유지·병합·신규 cluster 같은 제한된 decision JSON을 반환한다. pipeline은 유효한 page와 근거가 있는 결과만 적용한다.

**출력과 다음 단계**

`source_mentions_concept` page link, concept update 결과, active cluster 변경과 유지보수 후보를 만든다. `decided_by: "backend"` literal이 남는 artifact에서 `backend`가 의미하는 결정 주체는 pipeline 코드다. 모든 결과는 runtime manifest 조립으로 넘어간다.

## 14. Runtime Manifest와 영속화

**무엇을 하는가**

앞 단계의 artifact를 실행 응답으로 묶고, PostgreSQL transaction 안에서 현재 Wiki와
cluster를 반영한다. operation artifact는 DB 반영 뒤 마지막에 object storage에 쓴다.

**입력**

run metadata, source blocks, normalized, evaluator trace, pages, links, cluster/update 결과를 받는다.

**operation 저장 규칙**

`operation_id`가 있는 실행은 Source·Concept page id와 기존 Concept의 evidence
추가 결과를 확정한 뒤 operation artifact를 저장한다. key 형식은 다음과 같다.

```text
Source:  wiki/{workspace_id}/pages/{page_id}/ops/{operation_id}.md
Concept: wiki/{workspace_id}/pages/{page_id}/ops/{operation_id}.md
         wiki/{workspace_id}/pages/{page_id}/ops/{operation_id}.json
```

Source는 원문 문서와 1:1이므로 전체 Markdown snapshot만 저장한다. Concept는 여러
문서의 기여를 합칠 수 있어 Markdown과 재조립용 기여 JSON을 함께 저장한다.
기여 JSON에는 concept metadata, evidence, source block·key point와 이 작업이
지지하는 page link가 들어간다.

reingest에서는 결과에 남아 있는 모든 Concept이 아니라 이번 실행에서 새로
생성되거나, 기여 JSON이 생성되거나, `same_concept` evidence가 추가된 Concept만
operation artifact에 포함한다. 이전 실행의 결과를 그대로 유지한 Concept을 이번
작업의 변경분으로 기록하지 않는다.

page metadata와 Markdown 본문, link endpoint, source ref의 참조 무결성도 이
단계에서 검증한다.

**출력과 저장**

```text
runtime manifest
  - run 정보
  - normalized semantic 결과
  - evaluator/patch 상태
  - pages와 links
  - cluster/update 결과
  - concept_contributions
  - operation_artifacts

PostgreSQL
  - pipeline run과 source block
  - wiki_pages
  - wiki_page_links
  - wiki_embedding_units

로컬 `out` 디렉터리
  - `pipeline.log`
  - `save_debug_json=true`일 때의 debug artifact

S3 호환 object storage
  - 현재 source/concept Markdown
  - 작업별 Source snapshot
  - 작업별 Concept Markdown·기여 JSON
```

source block, 현재 Source·Concept, page link, embedding unit과 meaning cluster를
반영한 뒤 operation artifact를 persistence transaction의 마지막 단계에서 object
storage에 쓴다. 이후 PostgreSQL transaction을 commit하고, commit 뒤 `RunPipelineUseCase`가
embedding job을 시작한다. embedding은 기본 HTTP 경로에서 daemon thread의
best-effort 작업이며, 결과 callback route나 result callback 재시도 계약은 현재
구현에 없다. `log_callback_url`이 있으면 각 pipeline log event를 POST하지만 이는
결과 callback이 아니다.

ingest 또는 reingest operation을 취소할 때는
`POST /wiki/ingest-restore-runs`를 사용한다. Backend는
`restore_to_operation_id` 이후의 `cancel_operation_ids`를 확정하고 restore point와
현재 상태의 Concept 합집합을 전달한다. pipeline은 restore point의 Source
snapshot을 새 restore operation key로 복사하고, 취소 대상을 제외한 활성
ingest·lint 기여로 영향받은 Concept을 다시 조립한다.

runtime manifest는 관찰용 정보를 더 많이 포함할 수 있고, 저장용 축약 manifest는
PostgreSQL `pipeline_runs.manifest`에 저장된다. `pipeline.log`와 debug artifact는
로컬 `out` 디렉터리에 남으며 S3에는 page·operation·cluster·log object가 기록된다. DB 저장, object storage 저장과 후속 embedding 시작은 논리적으로
이어지지만 모든 외부 부작용이 하나의 transaction이라고 가정하면 안 된다.

`PipelineRunOut`은 `run_id`, `status`, 선택적 `manifest`, `output_dir`, `log_path`를 반환한다. runtime manifest의 주요 값은 `source_page`, `source_extraction_artifact`, `source_blocks`, `source_block_changes`, `concept_pages`, `links`, `meaning_clusters`, `maintenance_summary`, `normalized`, `generation_evaluations`, `generation_evaluation_status`, `warnings`다.

| 결과 | PostgreSQL | S3 호환 object storage |
| --- | --- | --- |
| source block | `source_blocks` | 없음 |
| source/concept page metadata | `wiki_pages` | `wiki/{user_id}/{workspace_id}/sources/...`, `concepts/...` |
| document-page/link | `document_wiki_links`, `wiki_page_links` | 없음 |
| embedding 상태 | `wiki_embedding_units`, `wiki_embedding_vectors` | vector는 후속 job |
| active cluster·ingest log | path/summary metadata | `wiki/{user_id}/{workspace_id}/clusters/active.md`, `wiki/{user_id}/{workspace_id}/logs/{date}.md` |
| operation Source snapshot | Backend revision 연동 대상 | `wiki/{workspace_id}/pages/{page_id}/ops/{operation_id}.md` |
| operation Concept 기여 | Backend contribution 연동 대상 | 같은 prefix의 `.md`, `.json` |
| 실행 상태·축약 manifest | `pipeline_runs` | 없음 (`pipeline.log`는 로컬 `out` 파일) |

DB용 manifest에서는 top-level `normalized`, `source_blocks`, page의 `markdown`, cluster 전문처럼 큰 값이 제거된다. 따라서 `wait=true` 즉시 manifest와 `GET /pipeline/runs/{run_id}`의 저장 manifest는 같은 정보량을 보장하지 않는다.

## 운영상 주의점

- 기본 `concept_page_mode=skeleton`에서는 concept 전체 writer LLM을 호출하지 않는다.
- evaluator issue가 최대 시도 뒤에도 남으면 유효한 normalized 결과로 조립을 계속할 수 있으므로 runtime trace를 함께 확인한다.
- `save_debug_json=false`이면 prompt 전문과 raw response가 일반 산출물로 남는다고 가정하지 않는다.
- runtime manifest와 저장용 manifest의 정보량은 다를 수 있다.
- reingest 뒤의 stale cluster·relation 정리는 lint reconciliation 대상이 될 수 있다.
- operation object는 DB transaction 마지막에 쓰이지만 commit 전 외부 object storage
  작업이다. 이후 DB commit이 실패하면 미참조 operation object가 남을 수 있다.

## 관련 문서

- `docs/backlog/evaluation/current-evaluator-metrics.md`
- `docs/backlog/evaluation/llm-evaluation-metrics.md`
- `docs/backlog/evaluation/wiki-schema-prompt-experiment-report.md`
- `docs/backlog/llm-wiki/flows/operation-recovery.md`
- `docs/backlog/spec/llmpipeline-backend-output-contract.md`
- `services/ai/pipeline/README.md`
