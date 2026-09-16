# AI 비동기 전환 PR1~PR4 통합 리뷰 3자 합의안

## 1. 목적과 검토 범위

이 문서는 다음 stacked PR의 누적 변경을 `origin/dev-msa...750357e3` 기준으로 다시 검토한 결과다. 기준 HEAD 뒤에는 이 문서의 정합성만 갱신하는 커밋이 이어진다.

| PR | 제목 | 기준 브랜치 | 커밋 |
|---|---|---|---|
| [#156](https://github.com/FruitionKR/local-pilot/pull/156) | AI command transactional outbox 적용 | `dev-msa` | `a3cebf10`, `25b7b787`, `b81b867f` |
| [#157](https://github.com/FruitionKR/local-pilot/pull/157) | Wiki DB 경계를 내부 API로 분리 | PR #156 | `cf132ccd`, `75bec422` |
| [#158](https://github.com/FruitionKR/local-pilot/pull/158) | Wiki 현재 상태를 ai_db로 이전 | PR #157 | `fe647fbd` |
| [#159](https://github.com/FruitionKR/local-pilot/pull/159) | AI 작업 비동기화와 ingest 병렬 처리 | PR #158 | `0911816c`, `0ef5bc9e`, `13e3a74b`, `750357e3` |

수정자, 감시자, 통합 리뷰어가 누적 195개 변경 파일을 각각 검토하고 이견과 후속 수정까지 대조했다. 최종 재검토 시점에 네 PR은 모두 open·mergeable이고, PR #159의 Backend·Frontend·llmPipeline·Docker Compose CI가 모두 성공했다.

## 2. 결론

합의된 merge 전 필수 13건은 구현·로컬 회귀 검증·누적 diff 재검토·PR CI 확인을 마쳤다. 현재 확인된 merge 전 필수 blocker는 없다.

- merge 전 필수: P0 2건, P1 10건, P2 문서 정합성 1건 구현 완료
- 판단 보류·추가 합의: run polling #5, Concept evidence 경합 #7, 동기 Query 유지 여부 #15
- 최종 배포 전 필수: Agent run/job/plan의 ai_db 이전과 core 권한 회수 1건
- 사용자 판단 사항: PR을 merge할지와 Agent DB 이전의 실행 순서만 판단하면 된다. 최종 소유권 목표 자체는 이미 합의됐다.

이 문서의 합의를 기준으로 PR #159에서 수정했고, 아래 검증 상태를 함께 기록한다.

## 3. Merge 전 필수 합의

### P0 — 기능 시작·결과 자체가 깨지는 결함

#### 1. Maintenance run ID를 UUID 계약에 맞춘다

- 근거: `WikiMaintenanceService.java:57`, `RestoreExecuteService.java:105`, `services/ai/pipeline/db/ai_schema.sql:5`
- 현재 흐름: Spring이 새 `run_id`를 만들고 202 응답, outbox command, AI run 조회에 같은 값을 전달한다. AI가 run ID를 새로 만드는 구조는 아니다.
- 원인: 문자열 컬럼/Redis를 쓰는 Agent·Query의 `agent_...`, `query_...` 식별자 관례를 maintenance에도 적용했지만, maintenance가 저장되는 `pipeline_runs.id`는 ingest와 같은 PostgreSQL `uuid`다. 새 실행이므로 기존 `operation_id`를 run ID로 재사용할 수도 없다.
- 문제: Spring은 `maintenance_<UUID>`를 발급하지만 `pipeline_runs.id`는 PostgreSQL `uuid`다. Lint·Restore는 첫 조회 또는 INSERT부터 실패하고 실패 상태도 기록하지 못한다.
- 합의: Lint·Restore도 prefix 없는 `UUID.randomUUID().toString()`을 사용한다. `pipeline_runs.id`를 `text`로 바꾸지 않는다.
- 검증: 실제 PostgreSQL을 사용해 lint/restore command가 같은 run ID로 생성·조회·종결되는지 확인한다.

#### 2. Restore 결과를 AI의 현재 Wiki 상태에 반영한다

- 근거: `restore_wiki_pages.py:44`, `wiki_page_restore.py:63`, `RestoreRebuildApplier.java:183`
- 문제: AI는 복구 산출물을 별도 object key에 만들고 Spring은 core version만 추가한다. 그러나 Wiki 조회와 Query는 `ai_db.wiki_pages.markdown_uri`를 읽으므로 성공 후에도 복구 전 본문을 반환한다.
- 합의: AI가 성공을 확정하기 전에 복구 본문 URI와 링크를 `ai_db` 현재 상태에 반영하고, 새 content hash 기준 embedding을 재생성한다. Spring은 version/contribution/operation 감사 기록만 소유한다.
- 검증: restore 직후 page 조회와 Query가 복구 본문을 사용하고 embedding hash가 현재 page hash와 일치하는지 확인한다.

### P1 — 원자성·멱등성·경합·운영 계약 결함

#### 3. Restore core 결과 반영을 receipt와 한 트랜잭션으로 묶는다

- 근거: `AiTaskResultApplier.java:92`, `RestoreApplier.java:58`, `RestoreOperationLifecycle.java:61`
- 문제: contribution 비활성화와 `rebuilding` 전이는 커밋됐는데 operation 결과 또는 receipt 저장 전에 죽으면, 재전달이 1차 적용을 반복해 stale conflict에 빠진다. 동시에 같은 event가 들어오면 둘 다 기존 `receiptExists`를 통과할 수도 있다.
- 합의: `applyRestore` 시작에서 receipt를 `INSERT ... ON CONFLICT DO NOTHING`으로 선점한다. 성공 경로의 `RestoreApplier`·`OperationIngestService`·receipt와 실패 경로의 failed 전이·receipt를 각각 동일 Spring transaction에 둔다. 이 경로에서는 `REQUIRES_NEW`로 바깥 트랜잭션을 나누지 않는다. 장애 시 전부 rollback하고 Kafka 재전달로 다시 처리한다.
- 제외: open PR이므로 과거 부분 커밋을 위한 별도 호환 상태 머신은 만들지 않는다.
- 검증: 각 DB write 뒤 강제 종료 지점을 두고 재전달 시 contribution, revision, operation, receipt가 한 번만 확정되는지 확인한다.

#### 4. Query는 run별 첫 terminal 결과만 수용한다

- 근거: `task_worker.py:46,292`, `AiTaskResultApplier.java:172`, `AiTaskResultConsumer.java:45`
- 문제: worker가 event 발행 후 offset commit 전에 죽으면 LLM이 다시 실행된다. core 채팅은 첫 답변인데 Redis/SSE는 두 번째 답변 또는 뒤늦은 실패로 덮일 수 있다.
- 합의: `(run_id, task_kind)` 기준 첫 terminal 결과를 canonical DB 결과로 확정한다. 중복 event는 채팅과 Redis/SSE를 다른 payload로 바꾸지 않는다. 별도 Query run 프레임워크는 만들지 않는다.
- 검증: success→success, success→failed, failed→success 재전달에서 채팅·GET run·SSE terminal 결과가 항상 동일한지 확인한다.

#### 6. 같은 문서의 reingest 시작을 직렬화한다

- 근거: `DocumentService.java:1430`, `DocumentRepository.java:63`
- 문제: 동시 요청 두 건이 모두 processing 이전 상태를 읽으면 같은 revision에 operation/run/outbox가 두 개 생긴다. Kafka 순서만으로는 중복 contribution 등록을 막지 못한다.
- 합의: 기존 `findByIdAndWorkspaceIdForUpdate()`로 문서를 잠근 뒤 processing 검사와 outbox 등록을 같은 트랜잭션에서 수행한다.
- 검증: 같은 문서에 동시 요청을 보내 run·operation·outbox가 하나만 생성되는지 확인한다.

#### 8. 오래된 ingest가 최신 edit hash를 처리한 것으로 기록하지 않게 한다

- 근거: `run_pipeline.py:49`, `postgres_wiki_ingestion_repository.py:620`
- 문제: stale 검사 직후 새 편집이 들어오면 완료 시 `ingested_hash = last_edit_hash`가 되어, 실제로 처리하지 않은 최신 편집까지 처리된 것으로 표시된다.
- 합의: command의 expected source hash와 현재 `last_edit_hash`가 일치할 때만 `ingested_hash = expected_hash`로 조건부 갱신한다. 불일치는 stale/superseded로 남긴다.
- 검증: stale 검사와 완료 사이에 편집을 삽입해 최신 hash가 미처리 상태로 유지되고 후속 ingest가 생성되는지 확인한다.

#### 9. Query의 임의 5분 실패 전이를 제거한다

- 근거: `QueryRunService.java:19,55`, `QueryRunStore.java:69`
- 문제: Kafka 대기나 LLM 실행이 5분을 넘으면 Redis만 failed가 되고 assistant는 pending으로 남는다. 늦은 success는 terminal guard 없이 다시 completed로 바뀐다.
- 합의: `failStuckRuns()`를 제거한다. 이번 범위에서 취소 protocol은 새로 만들지 않고 Redis 보관 TTL만 유지한다.
- 검증: 5분을 넘긴 command가 임의 실패하지 않고 terminal event 도착 시 한 번만 완료되는지 확인한다.

#### 10. Agent apply token과 감사 기록을 같은 PostgreSQL transaction에 둔다

- 근거: `AgentApplyOperationStore.java:36`, `DocumentService.java:1200,1217`
- 문제: token consume이 먼저 auto-commit된 뒤 operation 기록이 실패하면 문서는 바뀌었지만 감사 operation을 재시도로 복구할 수 없다.
- 합의: 성공·conflict 양쪽에서 token consume, operation audit, version link를 같은 PostgreSQL transaction에 둔다. Mongo와 PostgreSQL 사이의 분산 트랜잭션은 만들지 않고 기존 Mongo write receipt 재시도를 사용한다.
- 검증: operation 기록 실패를 주입한 뒤 재시도로 감사 로그와 version link가 복구되는지 확인한다.

#### 11. Lint 최초 polling의 404 계약을 보존한다

- 근거: `WikiMaintenanceService.java:65`, `PipelineRunStatusRequester.java:27`, `wikiLint.ts:35`
- 문제: outbox 발행 직후 AI run이 아직 없을 때 AI의 404가 Spring에서 일반 예외로 바뀌어 frontend의 404 재시도 조건과 맞지 않는다.
- 합의: 미생성 run을 전용 not-found 예외로 매핑해 Spring도 404를 반환한다.
- 검증: outbox 저장 후 worker 생성 전 polling이 404이고, 생성 뒤 같은 URL에서 정상 상태를 반환하는지 확인한다.

#### 12. 완전 실패 ingest operation을 `failed`로 기록한다

- 근거: `ingest_worker.py:74`, `AiTaskResultApplier.java:120`, `OperationApplier.java:77`
- 문제: Wiki 변경 전 실패도 `partially_succeeded`와 변경 0건으로 끝나 문서와 operation 상태가 모순된다.
- 합의: 실패 시 실제 변경 0건이면 `failed`, 하나 이상 반영된 뒤 실패했을 때만 `partially_succeeded`로 기록한다.
- 검증: 0건 실패와 일부 반영 실패를 분리해 operation 상태와 changed count를 확인한다.

#### 13. Cutover rollback에서 두 runtime role의 권한을 복구한다

- 근거: `wiki_db_cutover.py:196,220`, `docs/script.md`
- 문제: write lock은 `core_runtime`과 `ai_runtime` 모두에서 DML을 회수하지만 rollback은 `ai_runtime`만 복구한다. 구버전 Spring으로 되돌리면 Wiki write가 권한 오류로 실패한다.
- 합의: rollback이 두 role의 cutover 이전 table·sequence 권한을 명시적으로 복구하고 두 role 모두 실제 write 검증을 수행한다.
- 제외: 범용 ACL snapshot framework는 만들지 않는다.
- 검증: 권한 축소 후 rollback하고 구버전 core/AI smoke write가 모두 성공하는지 확인한다.

#### 17. Concept cache scope를 현재 DB scope와 맞춘다

- 근거: `postgres_wiki_ingestion_repository.py:692`, `workspace_concept_lock.py:48`, `postgres_wiki_writer.py:154`
- 문제: DB 조회와 unique key는 `(user_id, workspace_id, page_type, slug)`인데 cache key는 workspace만 사용한다. 같은 workspace의 다른 사용자가 첫 사용자의 필터 결과를 재사용할 수 있다.
- 합의: 현재 user+workspace 소유권을 유지하고 Concept cache key에 `user_id`를 포함한다. workspace 단위 short lock은 안전하므로 유지한다.
- 제외: Concept를 workspace canonical로 바꾸는 schema migration은 이번 범위에 포함하지 않는다.
- 검증: 같은 workspace의 두 사용자가 서로 다른 Concept index를 읽고 cache hit에서도 격리되는지 확인한다.

### P2 — 문서 계약 결함

#### 14. 제거된 callback 복구 설명을 superseded 처리한다

- 근거: `docs/adr/0005-prepare-wiki-database-boundary.md:16`, `docs/adr/0006-async-ai-tasks-and-parallel-ingest.md:11`
- 문제: ADR 0005는 제거된 callback/`notify_pending` 복구 경로를 현행처럼 설명한다.
- 합의: ADR 0005의 해당 결정을 ADR 0006으로 대체됐다고 표시하고 Kafka result event + run polling 계약으로 통일한다.
- 검증: 현행 architecture/API/demo 문서와 ADR에서 존재하지 않는 callback 복구 절차가 검색되지 않는지 확인한다.

## 4. 판단 보류·추가 합의 항목

#### 5. 모든 AI task의 주기적 polling은 보류한다

- 근거: AI worker는 result event를 `send_and_wait`한 뒤 command offset을 commit하고, Spring Kafka listener는 결과 반영이 성공해야 record 처리를 끝낸다.
- 정상 장애 처리: result 발행 실패 시 command offset이 전진하지 않아 command가 재전달된다. result 발행 성공 후 command offset commit이 실패하면 event가 중복될 수 있으나 #3·#4의 receipt 멱등성으로 처리한다. Spring 결과 반영이 실패해도 listener가 예외를 반환하므로 result record가 재전달된다.
- polling이 필요한 경우: document-svc 중단이 result topic retention보다 길었거나, 운영자가 consumer offset을 건너뛰었거나, Kafka 데이터 유실·잘못된 ack 같은 비정상 운영 사고가 발생한 경우다. 이때 AI의 terminal run은 core projection을 재구성할 최종 원본이 된다.
- 현재 판단: 모든 run을 계속 polling하는 이중 전달 경로는 만들지 않고 보류한다. 필요성이 확인되면 일정 시간 이상 남은 outstanding operation만 bounded batch로 조회하는 reconciler 또는 운영자 수동 복구 명령을 우선 검토한다.
- 재논의 조건: 실제 event 유실 사례, topic retention보다 긴 복구 목표, 감사 상태 자동 복구 SLO가 확정될 때.

#### 7. Concept evidence lost update 방어는 설명 후 판단한다

- 근거: `workspace_concept_lock.py:14`, `postgres_wiki_ingestion_repository.py:599`, `postgres_wiki_output_persistence.py:264-307`
- 막으려는 문제: Redis lock TTL 120초가 끝난 뒤 worker A와 B가 같은 Concept Markdown을 읽고 각자 새 evidence를 append하면, 같은 MinIO object key에 마지막으로 쓴 본문이 앞선 worker의 evidence를 덮을 수 있다. DB unique는 Concept 행 중복만 막고 본문 lost update는 막지 않는다.
- 제안한 최소안: atomic upsert로 canonical page ID를 정하고, 현재 Markdown을 읽기 전에 해당 `wiki_pages` 행을 `FOR UPDATE`로 잠가 read→merge→MinIO write→DB update 구간만 직렬화한다. workspace Redis lock과 DB unique는 그대로 둔다.
- 제외: Redlock, 전체 ingest 분산 락, lock TTL 자동 연장은 만들지 않는다.
- 현재 판단: 수정 필요성은 인정 후보지만 사용자 이해·합의 전까지 merge blocker로 확정하지 않는다.

#### 15. 동기 Query HTTP 경로의 유지 여부는 추가 합의한다

- 근거: `QueryController.java:66`, `QueryService.java:56,76`, `PipelineQueryRequester.java`
- 현재 상태: 비동기 `/query/runs`와 별개로 POST `.../query`가 Spring에서 AI HTTP 완료를 동기로 기다린다.
- 쟁점: 최초 원안은 Spring executor와 동기 AI HTTP 제거였지만 PR #159는 명시적 동기 호환 경로를 남겼다.
- 현재 판단: 일단 유지한다. 제거 또는 공식 지원 여부를 별도 합의한 뒤 관련 controller, requester, 설정, 테스트와 문서를 한 번에 정리한다.

## 5. 최종 배포 전 완료 조건

#### 16. Agent run/job/plan을 ai_db로 이전한다

- 근거: AI worker의 `connect_core()` 사용, cutover 이후 Agent table에 남겨 둔 `ai_runtime` DML 권한, 현행 문서의 “전환기 예외”
- `ai_runtime`의 정체: 새 서비스가 아니라 ai-svc 애플리케이션이 DML에 사용하는 PostgreSQL runtime 계정이다. DDL은 별도 migration 계정이 담당한다. 원칙상 `ai_runtime`은 `ai_db`에만 접근해야 한다.
- 생긴 이유: 서비스별 DB 분리와 runtime/migration 권한 분리를 도입할 때 AI 프로세스가 superuser나 core 계정을 쓰지 않도록 만들었다. 당시 pipeline/embedding과 Agent·Skill·checkpoint 테이블이 `core_db`에 남아 있어 전환기 동안 같은 계정에 core 접근 권한도 부여했다.
- 현재 예외: bootstrap 시 Agent 계열 Flyway 테이블이 아직 없어서 `infra/postgres/init-db-isolation.sh`가 먼저 core의 넓은 DML을 허용하고, Wiki cutover 후 `wiki_db_cutover.py`가 Agent·Skill·checkpoint 테이블과 필요한 sequence만 남기도록 축소한다.
- 문제: 목표 소유권은 기존 Agent run/job/plan이 ai_db에 있고 `ai_runtime`의 core DML 권한을 완전히 회수하는 것이다. 현재 구현은 이 목표를 완료하지 않았다.
- 합의: 이 항목은 현재 stacked PR의 merge blocker는 아니지만 최종 배포와 권한 회수의 차단 조건이다. 사용자가 판단할 것은 이전 여부가 아니라 이번 merge에 포함할지 후속 PR로 바로 수행할지의 순서다.
- 최소안: Agent 테이블과 checkpoint를 ID 보존 상태로 ai_db에 이전하고 worker 연결을 바꾼 뒤 core DML grant를 제거한다. 공통 run 테이블은 만들지 않는다.
- 검증: Agent run/job/approval 흐름이 ai_db에서 동작하고 `ai_runtime`으로 core DML이 실패하는지 확인한다.

## 6. 합의된 수정 순서

1. 실행 계약 복구: #1 → #11 → #2
2. terminal 원자성·멱등성: #3 → #4 → #10
3. 상태 계약: #9 → #12
4. ingest 경합·stale 방어: #6 → #8 → #17
5. 운영 안전성: #13
6. 문서 정합성: #14
7. 추가 합의: #5 → #7 → #15
8. 별도 배포 완료 조건: #16

각 단계는 해당 항목의 회귀 검증을 통과한 뒤 다음 단계로 진행한다.

## 7. 기각한 대안

- `pipeline_runs.id`를 prefix 허용 `text`로 변경: UUID 계약 하나를 맞추는 것보다 영향이 크다.
- 거대한 공통 `ai_task_runs`: 기존 pipeline/agent/query 저장 구조 재사용 원칙과 충돌한다.
- dual-write Wiki migration: maintenance cutover 합의와 충돌하고 장애 모드를 늘린다.
- Redlock 또는 ingest 전체 분산 락: DB unique·atomic upsert·row lock이면 정합성을 닫을 수 있다.
- 모든 AI task 상시 polling: Kafka 재전달로 닫히는 정상 장애 경로와 중복된다. 실제 복구 SLO가 필요할 때 outstanding 작업만 제한적으로 조회한다.
- Query 취소 protocol: 현재 문제는 임의 timeout이므로 timeout 제거가 가장 작다.
- Mongo/PostgreSQL 분산 트랜잭션: 기존 write receipt 재시도로 감사 projection을 복구한다.
- 과거 Restore 부분 커밋 호환 상태 머신: 아직 배포되지 않은 open PR에 불필요하다.
- workspace canonical Concept 전환: 현재 user+workspace DB 계약을 바꾸는 별도 제품 결정이다.

## 8. 사용자 판단 체크리스트

- merge 전 필수 #1~#4, #6, #8~#14, #17은 수정·검증과 최종 재검토를 완료했다.
- #5는 polling 복구 SLO가 필요해질 때 재논의한다.
- #7은 lost update 시나리오와 최소 row lock 방식을 이해·합의한 뒤 포함 여부를 결정한다.
- #15는 동기 Query 호환 경로의 공식 지원 여부를 별도로 합의한다.
- #16은 merge 전에 함께 처리하거나, merge 직후 배포 전 후속 PR로 처리한다.
- 현재 merge 전 blocker는 없으며, merge 여부와 #16의 실행 순서만 사용자가 결정한다.

## 9. 구현·검증 상태

| 항목 | 상태 |
|---|---|
| #1, #2, #3, #4, #6, #8~#14, #17 | 구현 및 회귀 테스트 완료 |
| #5, #7, #15 | 합의대로 이번 수정에서 제외 |
| #16 | 합의대로 최종 배포 전 후속 완료 조건 유지 |
| Spring 전체 | `./gradlew test` 성공 |
| Python 전체 | `814 passed`, `61 subtests passed` |
| Frontend | `npx tsc --noEmit` 성공 |
| Compose/Kustomize | 전체 Compose 병합 config와 base/AWS overlay build 성공 |
| PR #159 CI | Backend·Frontend·llmPipeline·Docker Compose 4종 성공 (`750357e3`) |

## 10. 최종 독립 재검토

초기 13건 수정 뒤 독립 리뷰에서 추가로 확인된 세 결함도 다음 커밋에서 닫았다.

- Query terminal projection: `13e3a74b`에서 `QueryRunStore`가 최초 Redis terminal 전이 여부를 반환하게 하고, 그 전이가 성공한 경우에만 SSE complete/fail을 발행한다. 동일 success 재수신과 success 뒤 failed 재수신 회귀 테스트를 추가했다.
- AI result event 유실: `750357e3`에서 `AiTaskResultConsumer` 전용 listener factory에 unlimited `FixedBackOff`를 적용해 Spring Kafka 기본 유한 재시도 뒤 recover/ack되는 경로를 제거했다. 기본 횟수를 넘긴 12회에도 recover하지 않는 테스트로 확인했다.
- Restore stale poison event: `750357e3`에서 `RestorePreviewStaleException`만 operation `conflict`와 receipt를 바깥 `applyRestore` transaction에서 함께 확정하고 정상 반환한다. 내부 `RestoreApplier`에는 해당 business conflict의 `noRollbackFor`를 지정해 transaction이 rollback-only가 되지 않게 했으며, 그 밖의 일시 장애는 그대로 throw해 Kafka 재전달에 맡기는 회귀 테스트를 추가했다.

최종 결론은 merge 전 필수 blocker 없음, #5·#7·#15 보류, #16 최종 배포·core 권한 회수 전 완료 조건이다.
