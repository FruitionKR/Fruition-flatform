# AI DB 경계를 분리하고 maintenance cutover로 이전

## 맥락

AI와 document-svc가 `core_db`의 Wiki 현재 상태를 함께 읽고 쓰고, AI가 `documents.status`까지 갱신해 트랜잭션 소유권이 겹쳤다. 현재 테이블을 즉시 삭제하면 기존 page ID와 문서 원문 연결을 잃을 수 있다.

## 결정

- 먼저 document-svc의 Wiki 현재 상태 조회를 AI 내부 API로 전환하고, AI의 `documents` 접근과 core 기여 이력 JOIN을 내부 API로 바꾼다.
- Wiki 현재 상태·embedding·`pipeline_runs`와 Agent·Skill·checkpoint는 maintenance cutover로 `ai_db`에 ID를 보존해 이전한다. Python `ai_schema.sql`을 이 스키마의 단일 소유자로 둔다.
- DB 경계를 넘게 될 `page_id`·`document_id` FK만 미리 제거하고 opaque logical ID로 취급한다. 테이블은 삭제하지 않는다.
- 데이터가 있는 환경은 Wiki와 Agent mutation을 모두 중지하고 실행 중 `pipeline_runs`와 `agent_runs`가 0건인지 확인한다. 양쪽 DB snapshot 식별자를 기록한 뒤 하나의 `REPEATABLE READ READ ONLY` source transaction에서 stream copy하고 row count·PK·canonical content hash·고아 참조를 검증한다.
- active run이 0건이면 두 runtime role의 core source write를 먼저 차단·검증한다. ingest/query/lint/restore/agent smoke test가 모두 성공한 뒤에만 worker를 재개하고 `ai_runtime` core 권한과 연결 설정을 제거한다.
- 기존 core source 테이블은 안정화 기간에 read-only로 보존한다. copy·검증 실패나 smoke 실패 시 연결 전환 없이 `rollback-core-permissions`로 source write 권한을 복구하며, 안정화 후 별도 migration에서 제거한다.
- 폐기 가능한 로컬 개발 데이터는 DB를 재생성할 수 있지만, 공유·운영 데이터에는 이 예외를 적용하지 않는다.
- 이 ADR의 callback·`notify_pending` 복구 결정은 [ADR 0006](0006-async-ai-tasks-and-parallel-ingest.md)으로 대체됐다. 현재 완료 전달 계약은 Kafka result event이고 ingest만 run polling으로 유실을 복구한다.

## 대안과 기각 사유

- core 테이블 즉시 삭제: ID·원문 연결 보존을 검증할 수 없어 기각했다.
- dual-write: 현재 zero-downtime 요구가 없고 동기화·보정 경로가 늘어나므로 만들지 않는다.
- callback만 사용: callback 의존은 ADR 0006에서 제거했고 Kafka result event와 ingest run polling으로 대체했다.

## 결과

`wiki_db_cutover.py`가 Wiki·Agent·Skill·checkpoint 복사·검증, core source write 차단, smoke 확인 후 권한 회수를 제공한다. AI runtime 상태는 물리적으로 ai_db가 소유하며 core 사본은 rollback용 read-only 데이터다.
