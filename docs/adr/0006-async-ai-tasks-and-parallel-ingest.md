# AI 작업 비동기화와 문서 단위 ingest 병렬화

## 맥락

Query·Agent·Lint·Restore의 Spring 요청 스레드가 AI HTTP 완료를 기다렸고, ingest Kafka key가 `workspace_id`라 한 workspace의 모든 문서가 순차 처리됐다. key만 `document_id`로 바꾸면 동일 Concept를 동시에 생성하거나 오래된 문서·페이지 결과가 최신 상태를 덮을 수 있다.

## 결정

- Spring이 `run_id`와 필요한 `operation_id`를 먼저 만들고 domain 상태와 command outbox를 한 트랜잭션에 저장한다.
- `ai.ingest.command`, `ai.query.command`, `ai.agent.command`, `ai.maintenance.command`를 workload별 worker가 소비하고 `ai.task.event`로 결과를 보낸다.
- 결과 callback은 제거한다. document-svc는 event를 멱등 반영하며 ingest는 AI run 폴링으로 유실을 복구한다.
- 기존 실행 저장소를 재사용한다: ai_db에서 ingest/lint/restore는 `pipeline_runs`, Agent는 `agent_runs`·`agent_jobs`를 사용하고 Query는 Redis run과 core 채팅 메시지를 사용한다. Markdown Agent는 core에 적용 예약 projection만 두며 AI worker가 공급된 `run_id`와 결정적 job ID를 멱등 생성한다.
- ingest key는 `document_id`로 바꾼다. LLM·분석은 병렬로 실행하고, ingest와 lint `materialize=true`의 Concept 최종 read→merge→object write→DB commit만 `(user_id, workspace_id)` PostgreSQL transaction advisory lock으로 직렬화한다. 기존 ingest Redis short lock은 유지하며 DB unique와 atomic upsert가 중복 생성을 차단한다.
- Concept 본문은 기존 본문에 evidence를 append한다. source revision/content hash와 page `updated_at`가 오래된 ingest·embedding 결과를 차단한다.

## 대안과 기각 사유

- workspace 전체 순차 처리: 정합성은 단순하지만 큰 workspace 하나가 처리량을 독점한다.
- 매 기능별 별도 공통 run framework: 기존 저장 구조와 중복되므로 만들지 않는다.
- Redis lock만 사용: TTL 만료와 worker 장애 시 lost update를 막지 못하므로 DB transaction advisory lock과 unique/upsert를 함께 둔다.
- dual-write: 이번 변경은 DB cutover가 아니며 운영 복잡도만 늘리므로 사용하지 않는다.

## 결과

같은 문서의 순서는 유지되고 서로 다른 문서의 LLM·분석은 병렬 처리된다. 사용자 API는 오래 걸리는 AI 작업에 202를 반환하며, 결과 재전달은 멱등하다. Markdown 결과는 core projection을 ready/failed로 전이하고 apply 시 operation/version audit와 함께 한 번만 소비된다. 같은 user+workspace의 Concept persistence만 DB commit까지 짧게 직렬화되고 Redis 장애 시 해당 ingest는 재시도된다.
