# llmPipeline Wiki lint 흐름

## 1. 문서 목적

여기서 `lint`는 Markdown 문법 검사가 아니라 active meaning cluster와 Wiki
구조를 점검하고, 선택적으로 변경을 반영하는 maintenance API다.

```text
POST /wiki/maintenance/lint
```

주요 구현은 다음과 같다.

- HTTP 계약·예외 매핑: `services/ai/pipeline/app/modules/wiki_ingestion/interfaces/http/routes.py`, `schemas.py`
- 실행 orchestration: `services/ai/pipeline/app/modules/wiki_ingestion/infrastructure/wiki_maintenance.py`
- 검사·materialization: `services/ai/pipeline/app/modules/wiki_ingestion/infrastructure/postgres_wiki_ingestion_repository.py`
- active cluster parser: `services/ai/pipeline/app/modules/wiki_ingestion/infrastructure/active_cluster_markdown.py`
- reingest reconciliation: `services/ai/pipeline/app/modules/wiki_ingestion/infrastructure/source_contribution_reconciliation.py`
- promotion page 조립: `services/ai/pipeline/app/modules/wiki_ingestion/infrastructure/promotion_concept_page.py`

## 2. HTTP 입력과 mode 분기

요청 body는 `user_id`(`local-user`), `workspace_id`(`local-workspace`),
`operation_id`, `materialize_promotions`(`false`), `dry_run`(`true`),
`provider`, `model`을 사용한다. `provider`와 `model`은 필수이며 선택 가능한
조합은 아래와 같다.

| provider | model | API key 환경변수 |
| --- | --- | --- |
| `openai` | `gpt-5-nano` | `OPENAI_API_KEY` |
| `gemini` | `gemini-3.1-flash-lite` | `GEMINI_API_KEY` |
| `claude` | `claude-sonnet-5` | `ANTHROPIC_API_KEY` |

`dry_run=false`이면 `operation_id`가 비어 있을 수 없다. 요청 검증과
provider/model 선택 오류는 FastAPI validation 오류로 처리되고, 실행 중
`WikiMaintenanceConfigurationError`는 `400`으로, 그 밖의 repository·MinIO·LLM
오류는 내부 상세를 숨긴 `500`으로 반환된다.

mode는 다음처럼 해석한다.

| 조건 | 검사·변경 |
| --- | --- |
| `dry_run=true` | active cluster, reingest 후보, orphan ref/link, promotion/relation 후보 계산만 수행. LLM 호출·DB 변경·operation artifact·lint log·active/archive object 저장 없음 |
| `dry_run=false`, promotion off | reconciliation, orphan link 제거, operation artifact·일일 lint log·active/archive object 저장 |
| `dry_run=false`, promotion on | 위 작업과 promotion LLM 호출, concept merge/create, relation materialization |

`materialize_promotions=true`여도 dry-run이면 promotion generator를 만들지 않으므로
LLM을 호출하지 않는다. `WikiLintOut`은 저장된 Markdown 전문이나 내부 trace가
아니라 검사·변경 요약을 반환한다.

## 3. 전체 orchestration

```text
POST /wiki/maintenance/lint
  │
  ├─ WikiLintIn 검증 → WikiMaintenanceCommand
  ├─ MinIO active cluster 읽기
  ├─ 최신 성공 pipeline run과 과거 manifest에서 reconciliation 후보 조회
  ├─ active cluster parse 및 orphan ref 검사
  ├─ orphan Wiki link 검사
  │
  ├─ dry_run=true
  │    └─ 결과 반환
  │
  └─ dry_run=false: PostgreSQL transaction
       ├─ reconciliation·cluster invalidation 적용
       ├─ promotion merge/create와 relation materialization
       ├─ orphan link 제거
       ├─ lint operation Markdown/기여 JSON 저장
       ├─ 일일 lint log append
       ├─ active/archive object 저장
       └─ DB commit
```

promotion을 materialize하는 write에서는 먼저 후보를 읽어 LLM 입력을 준비한 뒤
concept persistence lock을 획득하고 active cluster와 reconciliation 후보를 다시
읽는다. 따라서 실제 merge/create와 relation materialization은 fresh snapshot을
기준으로 한다.

## 4. Active cluster parse와 판정

`parse_active_cluster_lint()`는 `## cluster: <id>` section만 읽는다.

- `representative:`를 concept title 후보로 읽는다.
- `### Evidence Claims` 아래 `- claim_...:` 또는 `- ev_...:` 항목에서 claim id,
  text, 정규화한 claim, source ref, `cluster_decision`을 읽는다.
- `### Core Relation Candidates` 아래 `target`, `relation`, `evidence`, `reason`을
  읽는다. 허용 type은 `part_of`, `child_of`, `uses_or_depends_on`,
  `contrasts_with`, `supports_or_enables`, `related_evidence`다.
- `### Promotion` 아래 `status`와 `source_refs`를 읽는다.
- source ref 형식은 정규식 `[A-Za-z0-9_.-]+:B\d{4}`다. 동일 ref는 한 번만 센다.

관계에 target·허용 relation·evidence 중 하나라도 없으면 `invalid_relations`에
`missing` 원인과 함께 남고 materialize하지 않는다. `related_evidence`는 후보로
읽지만 DB edge로 materialize하지 않는다.

검사 결과는 다음 필드로 반환된다.

- `cluster_count`, `source_ref_count`: parse된 cluster와 고유 ref 수
- `orphan_refs`: `source_blocks`에 존재하지 않는 global ref
- `promotion_candidates`: `status=candidate`이고 `source_refs`가 있으며, reingest로
  invalidated된 ref에 의존하면서 현재 claim signature와 불일치하는 blocked cluster는
  제외한다.
- `needs_review`: `status=needs_review`, claim decision이 `needs_review`이거나,
  invalidated된 ref에 의존하면서 현재 claim signature와 불일치하는 blocked cluster
- `relation_candidates`, `invalid_relations`, `invalid_promotions`: 유효·무효 후보

promotion candidate의 source ref가 실제 `source_blocks`에 없는 경우에는
`orphan_refs`로 별도 보고된다. parser의 ref 형식 검증과 source-block 존재 검사는
별도이며, 형식이 맞아도 block이 없을 수 있다. 따라서 candidate가 자동으로 정상
materialize된다는 뜻도 아니다.

## 5. Reingest reconciliation

`list_reconciliation_candidates()`는 workspace 범위의 성공한 `pipeline_runs`에서
문서별 최신 run, 이전 manifest, 현재 `document_wiki_links`의 concept slug를
비교한다. 최신 manifest의 `source_block_changes.invalidated_block_ids`가 있어야
후보가 된다. 후보에는 다음이 포함된다.

- `invalidated_source_refs`: `document_id:B0001` 형식의 무효화 ref
- `stale_concept_slugs`: 이전에는 연결됐지만 최신 contribution에는 없는 concept
- `stale_relations`: 이전 contribution에는 있었지만 최신 contribution에는 없는 link
- `claim_signatures`, `relation_signatures`를 사용할 수 있는지 여부

구조 reconciliation을 적용하면 stale `document_wiki_links`를 삭제하고, 그 문서가
생성한 stale concept의 `wiki_embedding_units`를 삭제한다. stale relation은 다른
active document의 relation key가 지지하면 보존하고, 그렇지 않을 때만
`wiki_page_links`에서 삭제한다. 처리한 pipeline run manifest에는
`structural_reconciled_at`을 기록해 반복 적용하지 않는다.

active cluster의 claim/relation은 contribution에 저장된 현재 signature와 비교해
무효화된 ref에만 의존하고 최신 signature에 없는 항목을 제거한다. 일부 relation
evidence만 stale이면 남은 evidence만 보존한다. signature가 없는 legacy
contribution은 자동 제거하지 않고 review 대상으로 남긴다. promotion branch에서는
이 reconciliation과 active Markdown 재조립이 lock 이후 fresh read로 수행된다.

## 6. Promotion과 concept materialization

### 6.1 기존 concept merge

promotion cluster id와 같은 active concept slug가 이미 있으면 LLM을 호출하지 않고,
검증된 claim/ref를 기존 `## Evidence`에 append한다. 같은 evidence line은 중복하지
않으며, 변경된 Markdown은 embedding unit도 갱신한다. 결과는 `merged_promotions`에
기록한다.

### 6.2 신규 concept 생성

기존 slug가 없고 candidate가 blocked되지 않았으며 ref가 있는 claim이 있으면
promotion 전용 LLM 호출을 수행한다. user payload는 `cluster`(id, representative,
promotion 상태, claims, relations), `source_blocks`(global `ref`와 원문),
`allowed_anchor_refs`로 구성된다. active Wiki schema 전체를 prompt에 자동 주입하지
않는다.

기본 system prompt는
`services/ai/pipeline/prompts/concept_page_generation.system.md`이며, promotion
stage suffix가 다음을 추가한다.

- 제공된 evidence만 사용한다.
- `allowed_anchor_refs`에 있는 global ref 또는 block id만 citation에 사용한다.
- 최종 Markdown이나 frontmatter가 아니라 JSON draft만 반환한다.

현재 JSON 계약은 다음 필드다.

```json
{
  "title": "string",
  "definition": {"text": "string", "anchor_block_ids": ["B0001"]},
  "key_points": [{"text": "string", "anchor_block_ids": ["B0001"]}],
  "evidence": [{"text": "string", "anchor_block_ids": ["B0001"]}],
  "related_concept_hints": ["canonical-slug"],
  "confidence": 0.0
}
```

`build_promotion_concept_page()`가 slug, frontmatter, Definition, Why It Matters,
Key Points, Aliases, Evidence, Related Concepts, Reference Summary를 조립한다.
페이지 title은 cluster representative를 우선하고 slug는 draft slug 또는 cluster
id를 사용한다. allow-list 밖 anchor는 제거하며, 유효한 evidence가 하나도 없으면
cluster claim을 fallback으로 쓴다. 모델이 반환한 related hint는 Markdown 링크로
조립될 수 있지만 그것만으로 DB relation을 만들지는 않는다.

신규 concept은 `wiki_pages`에 upsert하고 Markdown을 operation object에 저장할
대상으로 지정하며, Markdown에서 추출한 `wiki_embedding_units`와
`wiki_embedding_vectors`를 `pending`으로 만든다. 실제 vector 계산과
`wiki_page_embeddings` 완료/실패 기록은 별도 embedding job의 책임이다.
LLM/provider/저장소 오류는 정상 materialization으로 기록하지 않고 실행 실패로
전파한다. 다만 promotion concept JSON draft는 누락 필드를 기본값/fallback으로
조립하므로 모든 JSON 계약 누락이 실행 실패로 전파되는 것은 아니다.

## 7. Relation materialization

promotion 전후의 concept id를 완성한 뒤 cluster relation을 한 번만 처리한다.
`part_of`, `child_of`, `uses_or_depends_on`, `contrasts_with`,
`supports_or_enables`만 materialize 대상이다.

각 relation은 source cluster concept와 target concept가 모두 active로 존재하고,
서로 다른 page이며, evidence가 직접 global ref이거나 claim id를 통해 source ref로
해석되어야 한다. 조건을 통과한 edge만 `wiki_page_links`에 upsert하고
`materialized_relations`에 기록한다. target page가 없거나 evidence가 해석되지
않으면 저장하지 않는다. 동일 source/target/type은 한 번만 처리한다.

## 8. Orphan link 판정

`lint_orphan_wiki_links()`는 현재 concept page가 source인 link와 그 page의
contribution JSON을 읽는다. 모든 managed contribution과 `active=true` contribution을
operation 순서로 재생한다.

- endpoint page가 비활성이면 `endpoint_deleted`
- operation log가 관리한 link인데 active contribution이 더 이상 지지하지 않으면
  `no_active_support`
- operation log가 한 번도 관리하지 않은 legacy link는 보존

active replay는 ingest의 `links`, lint의 `added_links`와 `removed_links`를 순서대로
적용한다. dry-run은 `orphan_link_candidates`만 반환하고, write mode는 후보를
`wiki_page_links`에서 제거하여 `removed_orphan_links`에 기록한다.

## 9. Operation artifact와 저장 순서

write mode에서 변경된 concept page마다 다음 object를 저장한다. link만 바뀐
concept도 현재 Markdown을 읽어 artifact를 만든다.

```text
wiki/{workspace_id}/pages/{page_id}/ops/{operation_id}.md
wiki/{workspace_id}/pages/{page_id}/ops/{operation_id}.json
```

lint 기여 JSON에는 `artifact_type=lint`, `content_action=create|append_evidence|none`,
concept/evidence 정보와 `added_links`, `removed_links`가 들어간다. content action이
없고 link 변경도 없으면 replay 가능한 lint artifact가 아니므로 저장하지 않는다.
이 JSON은 `POST /wiki/lint-restore-runs`가 ingest/lint contribution을 operation
순서로 재생할 때 사용한다.

일일 log는 아래 key에 append한다.

```text
wiki/{user_id}/{workspace_id}/logs/{YYYY-MM-DD}.md
```

promotion으로 소비된 cluster의 active section은
`wiki/{user_id}/{workspace_id}/clusters/active.md`에서 제거되고
`clusters/archived.md`에 `promoted_to` 또는 `merged_to` 정보와 함께 append된다.

실제 write 순서는 다음과 같다.

```text
1. PostgreSQL transaction 시작
2. reconciliation·relation·orphan link DB 변경 (아직 미커밋)
3. lint operation .md/.json 저장
4. 일일 lint log append
5. active.md/archive object 저장
6. PostgreSQL commit
```

operation artifact나 log 이후 오류가 나면 DB transaction은 rollback되고, 이미
추적된 lint operation object는 삭제를 시도한다. PostgreSQL과 MinIO는 하나의 원자
transaction이 아니므로 object side effect와 DB commit을 완전히 동일시하면 안 된다.
dry-run에는 위 write가 없다.

## 10. 응답과 확인 지점

`WikiLintOut`은 `user_id`, `workspace_id`, write mode의 `operation_id`,
`active_path`, cluster/ref count, orphan/invalid/review/candidate 목록,
`reconciliation_candidates`, `applied_reconciliations`,
`applied_cluster_reconciliation`, `merged_promotions`,
`materialized_promotions`, `materialized_relations`,
`orphan_link_candidates`, `removed_orphan_links`, `operation_artifacts`,
`changed_pages`를 반환한다.

정상 여부는 HTTP status만으로 판단하지 말고 `applied_*`, materialized 목록,
removed 목록과 artifact key를 함께 확인해야 한다. 특히 `orphan_refs`와 reingest
`invalidated_source_refs`는 서로 다른 판정이다.

관련 확인 테스트:

- `services/ai/pipeline/tests/modules/wiki_ingestion/test_wiki_maintenance_routes.py`
- `services/ai/pipeline/tests/modules/wiki_ingestion/test_concept_index.py`
- `services/ai/pipeline/tests/modules/wiki_ingestion/test_source_contribution_reconciliation.py`
- `services/ai/pipeline/tests/modules/wiki_ingestion/test_orphan_link_lint.py`
- `services/ai/pipeline/tests/modules/wiki_ingestion/test_lint_operation_artifacts.py`
- `services/ai/pipeline/tests/modules/wiki_ingestion/test_restore_wiki_pages.py`
