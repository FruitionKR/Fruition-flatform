# ADR-0001: 주 데이터베이스 선택 — PostgreSQL 물리 분리 + MongoDB 본문 저장

- 상태: 부분 대체 — 결정 4는 [ADR-0005](0005-prepare-wiki-database-boundary.md)로 대체됨
- 관련: [architecture.md](../architecture.md) §4, [data-model.md](../data-model.md)

## 맥락

단일 PostgreSQL에 인증·워크스페이스·문서·AI 테이블이 동거했다. MSA 전환에서 서비스별 데이터 소유권을 강제해야 했고, 문서 편집 본문은 revision·write-id·outbox를 한 트랜잭션으로 묶는 저장 모델이 필요했다.

## 결정

1. **PostgreSQL을 서비스별 물리 DB로 분리**: access_db(access-svc) / core_db(document-svc) / ai_db(ai-svc). AWS에서는 Access RDS + Core RDS 2 instance.
2. **DB 계정 격리**: 서비스마다 runtime(DML)/migration(DDL) 계정 분리, 타 서비스 DB write 불가 (`infra/postgres/init-db-isolation.sh`, validation 스크립트로 실검증).
3. **문서 본문·편집 revision은 MongoDB**: `document_edit_states`·`document_edit_writes`·`document_edit_outbox`를 단일 Mongo 트랜잭션으로 기록. AWS에서는 MongoDB Atlas.
4. **전환기 예외(대체됨)**: AI 테이블을 core_db에 유지한다는 결정은 ADR-0005의 maintenance cutover로 대체됐다. Wiki·pipeline run·embedding·Agent·Skill·checkpoint는 ai_db가 소유하고 `ai_runtime`은 core DB에 접근하지 않는다.

## 대안과 기각 사유

- **단일 DB + 스키마 분리만**: 계정 실수·JOIN 유혹으로 경계 침식. 물리 분리로 컴파일·네트워크 수준 강제 선택.
- **본문도 PostgreSQL(JSONB)**: revision + write-id + outbox 원자 기록과 문서 단위 동시 편집 병합 모델에 Mongo 트랜잭션 + 문서 지향 모델이 단순.

## 결과

- 서비스 간 DB 직접 참조 불가 — 내부 API·Redis projection·Kafka로만 연결.
- Flyway는 core_db(document-svc 소유), access_db(access-svc 소유) 각자 관리. ai_db는 python `ai_schema.sql` 멱등 부트스트랩.
- 비용: RDS 2대 + Atlas. 트레이드오프로 수용.
