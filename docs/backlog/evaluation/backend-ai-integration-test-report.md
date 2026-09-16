# Backend–AI 통합 테스트 최신 증거 보고서

판정 기준일: 2026-08-14 (Asia/Seoul)

기준 계획: `docs/backlog/evaluation/backend-ai-integration-test-plan.md` §12~§20

보고서 갱신 시점 HEAD는 `bae5d8eb507f8c7b2e7ee7cdb90db8f65213d066`이고, 최신 기능 증거
기준 commit은 `3fb4fc3c2817ec3a0c2acf798599f9d040ead83f`다. 증거 기준 commit은 갱신
시점 HEAD의 ancestor이지만, 그 이후 변경까지 이 보고서가 자동으로 검증하는 것은 아니다.

외부 증거 bundle은 `back-ai-e2e-clean2/`이며 이 장비에서는
`<local-downloads>/back-ai-e2e-clean2`에 보존했다. 62개 `REPORT.md`와 raw
artifact를 포함하지만 Git에는 추적하지 않는다. 아래 경로는 이 bundle root 기준 상대 경로다.

## 1. 최종 결론

최신 natural-run evidence를 가장 좁은 실행 계약으로 재판정한 결과는 다음과 같다.

| 판정 | 개수 | 의미 |
|---|---:|---|
| `PROVEN PASS` | 35 | 명시된 transport·저장·상태·경계까지 증거로 확인 |
| `PRODUCT DEFECT` | 0 | 최신 증거에서 재현된 결정적 코드·계약 결함 없음 |
| `LLM_QUALITY DEFERRED` | 16 | 시스템 경계는 도달했지만 모델 route·plan·action·답변 품질 미달 |
| `HARNESS NOT COUNTED` | 18 | fixture·auth·공개 fault seam 부족으로 제품 판정 불가 |
| `MISSING` | 8 | 요구된 실행 또는 최종 증거 없음 |
| `RUNTIME RESOLVED` | 1 | runtime drift는 해소됐지만 관련 기능 pass는 별도 증거 필요 |

위 숫자는 coverage audit의 개별 requirement row 집계다. 아래 기능별 표는 관련 row를 읽기 쉽게
묶거나 보조 증거를 분리한 요약이므로 표의 행 수를 다시 합산하지 않는다.

따라서 실행된 좁은 계약에는 결정적 제품 결함이 남지 않았다. 그러나 `MISSING`과
`HARNESS NOT COUNTED`가 있으므로 Wave 2~4 전체 통과를 주장하지 않는다. LLM 품질로 분류한
항목도 기능 성공으로 세지 않는다.

## 2. 증거 우선순위와 supersession

| 우선순위 | 보고서 | 용도 |
|---:|---|---|
| 1 | `natural-3fb4-v2/coverage-audit/REPORT.md` (01:00) | 기능별 live E2E 최종 matrix |
| 2 | `natural-3fb4-v2/targeted-regression/REPORT.md` (01:03) | 최신 집중 자동 회귀 결과 |
| 3 | `natural-3fb4-v2/final-runtime-deploy/REPORT.md` (01:12) | 마지막 runtime class/source/health 확인 |
| 제외 | `natural-3fb4-v2/precommit-audit/REPORT.md` (01:12) | 구버전 Query FAIL을 인용한 stale 판정 |

다음 보고서는 명시적으로 이전 결과를 대체한다.

- `natural-3fb4-v2/revalidate-query-context-v2/REPORT.md`가
  `natural-3fb4-v2/revalidate-query-context/REPORT.md`의
  pending/failed pair 누출 FAIL을 대체한다.
- `natural-3fb4-v2/revalidate-agent-create-artifact-v2/REPORT.md`가 같은 이름의 이전
  보고서를 대체한다.
- `natural-3fb4-v2/fix-head-runtime-deploy-v2/REPORT.md`가 최초 deploy 보고서의 false
  negative를 대체한다.
- `natural-3fb4-v2/`의 raw-only `wave2-ingest`, `query-lint`, `tools-agent`,
  `skill-markdown` lane은 이전 `retest-*` 보고서보다 늦은 실행 증거다.
- `precommit-audit`은 23:33 구버전 Query 보고서를 blocker로 사용했지만, 00:17 `v2`가 같은
  pending/failed pair를 fresh public run·Kafka·DB로 통과시켰으므로 최종 blocker로 채택하지 않는다.

## 3. 판정 규칙

- HTTP `200`/`202`, route JSON 또는 unit test만으로 DB mutation, Kafka event, callback,
  persisted content까지 통과했다고 승격하지 않는다.
- 동일 case의 새 보고서는 이전 보고서를 자동 대체하지 않는다. 같은 계약을 더 강한 증거로
  재검증했을 때만 supersede한다.
- 모델이 route·plan·action·답변을 잘못 선택했지만 transport와 persistence 계약이 정상인 경우
  `LLM_QUALITY DEFERRED`로 분류한다.
- 지원되는 public seam이 없는 callback 재전달·provider failure는 실행을 꾸미지 않고
  `MISSING` 또는 `HARNESS NOT COUNTED`로 남긴다.
- PASS는 해당 행의 좁은 계약에만 적용하며 기능 전체 성공을 뜻하지 않는다.

## 4. 기능별 최신 판정

### 4.1 Ingest와 chat ingest

최신 증거: `natural-3fb4-v2/wave2-ingest/`, `retest-3fb4/wave2-ingest/REPORT.md`.

| Case | 최신 판정 | 확인 범위 또는 제한 |
|---|---|---|
| I-DOC-01 | `HARNESS NOT COUNTED` | alpha fixture가 `INVALID_IDEMPOTENCY_KEY`; 다른 최초 ingest 성공을 이 case 전체 증거로 섞지 않음 |
| I-DOC-02 요청 중복 거부 | `PROVEN PASS` | 동일 처리 중 재요청 `409 DOCUMENT_ALREADY_PROCESSING` |
| I-DOC-02 저장소·callback 중복 방지 | `MISSING` | contribution/link/embedding 및 duplicate callback/event 독립 재전달 미실행 |
| I-CHAT-P-01 | `PROVEN PASS` | partial Wiki linkage와 반복 export `skipped` 확인 |
| I-CHAT-F-01 | `PROVEN PASS` | full document·operation·Wiki linkage 확인 |
| I-CHAT-F-02 | `MISSING` | auth refresh 후 `401`로 delta 누적 계약 미증명 |
| I-RE-01 | `PROVEN PASS` | OLD→NEW 편집, reingest, 최신 marker와 `needs_reingest` 확인 |
| I-RE-02 | `PROVEN PASS` | 연속 A→B→C operation과 최신 C graph 확인 |
| I-RACE-01 | `PROVEN PASS` | stale ingest 무변경 종료와 최신 문서 `needs_reingest=true` 확인 |
| I-ERR public 경계 | `PROVEN PASS` | missing/deleted/cross-workspace/invalid model의 관측된 400/404/409 |
| I-ERR worker/provider/callback | `MISSING` | malformed command, provider failure, duplicate callback을 주입하지 않음 |

### 4.2 Query와 web search

최신 증거: `natural-3fb4-v2/revalidate-query-context-v2/REPORT.md`,
`natural-3fb4-v2/query-q03-llm-indexed/REPORT.md`,
`natural-3fb4-v2/query-q03-llm-fresh/REPORT.md`, `natural-3fb4-v2/query-lint/`.

| Case | 최신 판정 | 확인 범위 또는 제한 |
|---|---|---|
| Q-01 | `PROVEN PASS` | internal evidence 사용, web OFF, 내부 reference만 관측 |
| Q-02 | `PROVEN PASS` | 동일 질문 web ON, web route/result 실행 |
| Q-03 | `LLM_QUALITY DEFERRED` | internal+web retrieval과 Tavily 실행은 PASS; 최신 버전·설치 명령 종합 실패 |
| Q-04 | `PROVEN PASS` | 내부 근거 없음, web 미실행, evidence-limited 응답 |
| Q-05 | `HARNESS NOT COUNTED` | 안전한 public Tavily fault seam 없이 failure 실행 안 함 |
| Q-06 | `PROVEN PASS` | 동시 ON/OFF session snapshot 격리 |
| Q-07 | `PROVEN PASS` | completed pair만 포함, pending/failed pair 전체 제외, 최신 6개 순서와 session/workspace 격리 |
| Q-08 | `PROVEN PASS` | blank/non-boolean/partial model/foreign session 및 sync/async 경계 |

Q-07의 최신 `v2`는 이전 보고서가 재현한 user 반쪽 누출을 같은 base의 current runtime에서
해소했다. 이것이 stale `precommit-audit`의 Query blocker를 최종 판정에서 제외한 직접 근거다.

### 4.3 Lint

최신 증거: `natural-3fb4-v2/query-lint/`, `retest-a749/lint-tools-rerun/REPORT.md`.

| Case | 최신 판정 | 확인 범위 또는 제한 |
|---|---|---|
| L-01 dry-run | `HARNESS NOT COUNTED` | deterministic lint target이 없어 zero change로 proposal 계약을 증명할 수 없음 |
| L-02 apply | `HARNESS NOT COUNTED` | target 부재로 `changed_resource_count=0`; 실제 Wiki diff·restore 미증명 |
| L-03 clean no-op | `PROVEN PASS` | no-change와 semantic mutation 부재 확인 |
| L-04 | `HARNESS NOT COUNTED` | validation 일부는 통과했지만 concurrent terminal과 failure subcase 미완료 |

### 4.4 Tool과 Agent approval

최신 증거: `natural-3fb4-v2/tools-agent/`,
`natural-3fb4-v2/revalidate-agent-create-artifact-v2/REPORT.md`,
`natural-3fb4-v2/agent-autonomous-runtime-enable/REPORT.md`.

| 기능 묶음 | 최신 판정 | 확인 범위 또는 제한 |
|---|---|---|
| 13-tool allowlist·gateway inventory | `PROVEN PASS` | read 6개·mutation 7개 static contract 확인; 실행 전체 pass 의미 아님 |
| `list_root_items`, `list_folder_children`, `search_hierarchy`, `get_breadcrumb`, `get_document_metadata` | `PROVEN PASS` | valid read HTTP 200 |
| `get_document_content`, read invalid/cross-workspace | `HARNESS NOT COUNTED` | 당시 auth seam에서 401/404로 tool 의미까지 도달하지 못함 |
| `create_folder`, `move_folder` | `PROVEN PASS` | read→plan→approval→execute 완료 |
| `rename_folder`, `move_document`, `rename_document` | `LLM_QUALITY DEFERRED` | natural route가 필요한 mutation을 선택·완료하지 못함 |
| `create_document` artifact | `LLM_QUALITY DEFERRED` | artifact/hash/plan/approval까지 정상; 승인 후 re-plan이 실제 mutation 차단 |
| `apply_document_edit` natural route | `LLM_QUALITY DEFERRED` | direct public apply는 성공했지만 natural action selection은 미완료 |
| 정상 approval flow | `PROVEN PASS` | 한 `create_folder` plan/approval path 완료 |
| stale/duplicate approval, revise, cancel, invalid rejection | `PROVEN PASS` | 공개 control·negative 경계 확인 |
| valid rejection·operation log·final navigation | `HARNESS NOT COUNTED` | runtime/auth로 의도한 readback 미완료 |
| Agent runtime deployment | `RUNTIME RESOLVED` | current route·worker·health는 해소; 막혔던 각 기능은 별도 판정 유지 |

### 4.5 Skill

최신 증거: `natural-3fb4-v2/skill-luna-authored-simple/REPORT.md`,
`natural-3fb4-v2/skill-author-400-diag/REPORT.md`,
`natural-3fb4-v2/skill-direct-publish-fresh/REPORT.md`,
`natural-3fb4-v2/skill-db-fixture-e2e/REPORT.md`,
`natural-3fb4-v2/skill-corrected-fresh/REPORT.md`.

| Case | 최신 판정 | 확인 범위 또는 제한 |
|---|---|---|
| S-CREATE | `LLM_QUALITY DEFERRED` | author/publish 경계 도달 후 model safety/plan route가 완전한 Tool 실행 차단 |
| S-EDIT | `LLM_QUALITY DEFERRED` | benign author 요청이 malformed model JSON 계약으로 400; natural action 선택 실패 |
| S-FOLDER | `LLM_QUALITY DEFERRED` | explicit DTO→Kafka→worker envelope는 도달; folder route·다섯 mutation 미완료 |
| S-TEMPLATE | `LLM_QUALITY DEFERRED` | reference 제공 후 model author/action 결과가 완전한 실행을 만들지 못함 |
| S-MULTITURN | `LLM_QUALITY DEFERRED` | proposal revision→security review→publish cycle 미완료 |
| S-DRAFT | `HARNESS NOT COUNTED` | 적합한 completed Agent run 선택·draft 실행 미성립 |
| S-ERR | `PROVEN PASS` | unsafe preview·invalid name 등 관측된 안전 경계 |

이전 direct-publish 보고서의 public DTO `skill_mode`/`skill_id` gap은 이후 DB fixture 실행에서
outer DTO→Kafka→worker까지 도달한 증거로 supersede한다. 다만 model route가 Skill 실행 경로를
선택하지 않아 selected version, approval, 실제 rename은 여전히 통과로 세지 않는다.

### 4.6 Markdown Agent

최신 증거: `natural-3fb4-v2/skill-markdown/`,
`natural-3fb4-v2/revalidate-r-doc-current/REPORT.md`,
`natural-3fb4-v2/skill-direct-publish-fresh/REPORT.md`.

| Case | 최신 판정 | 확인 범위 또는 제한 |
|---|---|---|
| M-01~M-06 | `HARNESS NOT COUNTED` | route output 일부는 있으나 최종 saved content/version/diff 또는 isolation 증거 부족 |
| M-07 | `MISSING` | enabled/published Skill을 실제 선택·적용한 실행 없음 |
| GFM preservation | `LLM_QUALITY DEFERRED` | model route/action이 applied diff 이전에 실패 |
| M-ERR | `PROVEN PASS` | no active doc, invalid range, version conflict, foreign doc 경계 |
| direct non-Skill Markdown apply | `PROVEN PASS` | target 문장만 revision 1→2로 변경되고 operation log/diff 확인 |
| R-DOC current natural flow | `LLM_QUALITY DEFERRED` | fresh public Agent terminal이 `agent_turn_failed`; save·restore 결과를 만들지 않음 |

### 4.7 Log와 Restore

최신 증거: `natural-3fb4-v2/log-restore-fresh/REPORT.md`,
`natural-3fb4-v2/revalidate-restore-summary/REPORT.md`,
`natural-3fb4-v2/revalidate-r-doc-current/REPORT.md`.

| Case | 최신 판정 | 확인 범위 또는 제한 |
|---|---|---|
| R-DOC-01 | `LLM_QUALITY DEFERRED` | current natural Agent가 edit 결과 전에 실패; save/apply/restore 미실행 |
| R-INGEST-01 | `PROVEN PASS` | B preview와 restore, page change, source immutability 확인 |
| R-INGEST-02 | `PROVEN PASS` | A→B→C same-document restore와 unrelated document 격리 |
| R-LINT-01 | `HARNESS NOT COUNTED` | deterministic lint target 없음 |
| R-MIXED-01 | `HARNESS NOT COUNTED` | lint zero-change로 mixed restore target 미성립 |
| R-MULTI-01 | `PROVEN PASS` | 복수 Wiki page restore/rebuild/delete 기록과 최종 상태 확인 |
| R-PARTIAL-01 | `HARNESS NOT COUNTED` | 지원되는 deterministic partial/provider failure seam 없음 |
| R-STALE-01 | `PROVEN PASS` | 상태 변경 후 이전 preview 재사용 `409 RESTORE_PREVIEW_STALE`, mutation 없음 |
| R-IDEMP-01 request | `PROVEN PASS` | 동일 preview token 재요청이 두 번째 restore operation을 만들지 않음 |
| R-IDEMP-01 callback/event | `MISSING` | public callback injection 없음 |
| R-ERR public 경계 | `PROVEN PASS` | missing/foreign/unauthorized/restore-of-restore/tamper/malformed |
| R-ERR provider/worker failure | `MISSING` | controlled provider/worker failure 미실행 |

Restore summary의 최신 실제 값은 두 restored page와 한 deleted page, 즉
`changed_resource_count=3`이며 public detail과 DB change record가 일치한다.

### 4.8 Gemini와 Anthropic

최신 증거: `natural-3fb4-v2/wave4-provider-smoke/REPORT.md`.

| Provider | 최신 판정 | 확인 범위 또는 제한 |
|---|---|---|
| Gemini | integration `PROVEN PASS`, quality deferred | model snapshot, ingest/index, Query source transport, Markdown persistence 통과 |
| Anthropic | integration `PROVEN PASS`, quality deferred | model snapshot, ingest/index, Query source transport, Markdown persistence 통과 |
| 두 provider 답변·Skill author·action selection | `LLM_QUALITY DEFERRED` | answer accuracy와 model action 결과를 integration pass에 포함하지 않음 |
| 두 provider normal approved Skill Tool·direct DB Skill | `MISSING` | executable published Skill과 DB-backed execution 없음 |

이 결과는 8월 12일 보고서의 구형 exact model 404를 대체한다. 최신 실행은
`gemini-3.1-flash-lite`와 `claude-haiku-4-5-20251001`을 사용했으며 두 lane 모두 public
fixture에서 통신·저장 경계를 통과했다.

## 5. 최신 자동 회귀 결과

`natural-3fb4-v2/targeted-regression/REPORT.md`의 적합한 실행 환경 결과다.

| 영역 | 실행 | 결과 |
|---|---|---|
| Backend | Java 21, Gradle 6개 class | 65 tests, failure/error/skip 0 |
| AI pipeline | Python venv, 5개 test file | 83 tests + 13 subtests, failure 0 |
| Diff | `git diff --check` | 통과 |

대상은 Query pair filtering, Query payload, Restore summary, Agent Skill DTO 전달,
Agent artifact persistence다. 이 집중 회귀 결과를 전체 repository test 또는 live E2E 전체 통과로
확장하지 않는다. 8월 12일의 대규모 자동 테스트 수치는 역사 증거이며 최신 변경의 독립 재실행으로
사용하지 않는다.

## 6. Runtime 최종 상태

`fix-head-runtime-deploy-v2`는 변경 Java class와 네 AI container의 source hash·health를 맞췄고,
`final-runtime-deploy`는 마지막 Query/Agent 관련 Java class와 pipeline API/task worker source를 다시
확인했다. health와 Kafka/PostgreSQL 연결성은 통과했다.

이 방식은 runtime worktree class와 container writable layer를 맞춘 검증 환경이다. immutable image
재빌드·배포 검증은 아니므로 release image provenance로 사용하지 않는다.

## 7. 보안·cleanup·증거 제한

- 최신 보고서는 access/refresh/verification token, provider key, password를 raw evidence에 쓰지 않았다.
- 최신 fresh fixture는 가능한 범위에서 public API로 session/document/workspace를 정리했고 exact
  post-delete 상태를 확인했다. append-only receipt와 soft-delete audit row는 보존했다.
- 이전 8월 12일 campaign의 retained fixture와 transient worker transcript credential metadata 노출
  기록은 역사적 보안 항목으로 유지한다. 관련 credential rotation·접근 제한 여부는 이 최신 기능
  재검증이 증명하지 않는다.
- raw artifact bundle은 Git에 없으므로 장기 재현성과 팀 공유를 위해서는 별도 보존 정책이 필요하다.
- 원본 보고서의 절대 `/private/tmp/back-ai-e2e-clean2/...` 링크는 보존 bundle에서 같은 상대 경로로
  찾아야 한다.

## 8. 최종 사용 기준

이 보고서는 최신 evidence base에서 결정적 제품 결함 0이라는 통합 판단과, 각 기능의 실제 coverage
경계를 함께 기록한다. `LLM_QUALITY DEFERRED`, `HARNESS NOT COUNTED`, `MISSING`은 숨기지 않으며
PASS로 승격하지 않는다.

따라서 현재 결과는 승인된 좁은 계약의 integration 판단에는 사용할 수 있지만, 모든 Wave 2~4 기능이
완료됐다는 release sign-off로 사용할 수 없다. 이후 HEAD 변경은 같은 case의 fresh evidence가 있을
때만 이 판정을 갱신한다.

PUBLISHABLE_WITH_LIMITATIONS
