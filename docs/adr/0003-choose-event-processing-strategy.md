# ADR-0003: 이벤트 처리 전략 — Kafka + Mongo outbox, 동기 경로는 HTTP 유지

- 상태: 부분 대체 — ingest key와 Query·Agent·Lint 비동기 계약은 [ADR-0006](0006-async-ai-tasks-and-parallel-ingest.md)으로 대체됨
- 관련: [architecture.md](../architecture.md) §5

## 맥락

문서 ingest(임베딩·Wiki 생성)는 수 분 단위 장기 작업 — 요청-응답으로 묶으면 안 된다. 문서 편집 이벤트는 파생물(임베딩·Wiki) stale 추적에 필요하며, 본문 저장과 이벤트 발행 사이 원자성이 깨지면 유실·불일치가 생긴다. 반면 query·agent·lint는 사용자가 대기하는 동기 흐름이다.

## 결정

1. **비동기는 Kafka**:
   - `ai.ingest.command` (key=workspace_id, 12 partitions): document-svc 발행 → ingest-worker 소비. KEDA lag 기반 스케일(min1/max4).
   - `document.edit.event` (key=document_id): 문서별 순서 보존, edit-event-consumer가 파생물 stale 추적(ai_db).
2. **Outbox 패턴**: 본문 저장은 Mongo 단일 트랜잭션(본문+revision+write-id+outbox 테이블) → `MongoDocumentEditOutboxPublisher`가 Kafka 발행. at-least-once, 발행 유실 없음.
3. **동기 경로(query·agent·lint)는 HTTP 유지**: document-svc → pipeline 내부 HTTP + X-Internal-Token, 결과는 HTTP 콜백 + heartbeat.

위 결정 중 `ai.ingest.command`의 `workspace_id` key와 query·agent·lint 동기 HTTP/callback 계약은 ADR-0006이 각각 `document_id` key와 workload별 Kafka command/result event로 대체했다. Mongo outbox와 `document.edit.event` 결정은 그대로 유효하다.

## 대안과 기각 사유

- **저장 후 직접 Kafka 발행(outbox 없이)**: 저장 성공 + 발행 실패 시 이벤트 유실. 기각.
- **query 결과도 Kafka result topic**: pipeline 재시작 중 결과 유실을 막을 수 있으나, HTTP 콜백이 검증된 현 시점엔 과잉. 유실이 실제 문제 될 때 전환 — 참조 구현 `feat/msa-kafka-publisher-consumers` 브랜치(318b991) 포팅 가능.
- **경량 큐(Redis Stream 등)**: partition 키 기반 순서 보존·consumer group·lag 기반 오토스케일(KEDA)·AWS 매핑을 Kafka가 일괄 제공. 기각.

## 결과

- 유실 실측: worker 정지 중 발행 → lag 대기 → 기동 후 전량 소비 → lag 0.
- at-least-once이므로 consumer는 멱등해야 함 (Idempotency 테이블 서비스별 사본).
- 트레이드오프: Kafka 운영 비용 — 로컬 Strimzi(kind)·AWS Strimzi on EKS로 흡수.
