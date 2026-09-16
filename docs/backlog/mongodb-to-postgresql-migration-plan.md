# MongoDB 제거 및 PostgreSQL 통합 이관 계획

상태: 구현·검증 완료 (공유 Mongo 실데이터 삭제 미실행)

작성 기준: `feat/multi-provider-chat-model-routing` / `0b798873`

근거 자료:

- `<local-downloads>/mongodb-removal-rationale.md`
- `<local-downloads>/0016-consolidate-document-body-into-postgres.md`
- 위 기준 commit의 실제 코드·테스트·설정

이 문서는 현행 문서가 아니라 구현 작업용 backlog다. 구현 후 실제 구조는
`docs/architecture.md`, `docs/data-model.md`, `docs/script.md`와 정식 ADR에 반영한다.

## 1. 목표와 완료 조건

문서 본문, 편집 revision, `revision_write_id` 처리 결과, 콘텐츠 버전·자산 참조·AI 적용 기록,
Kafka outbox를 `core_db`의 단일 PostgreSQL transaction으로 커밋한다. 전환이 끝나면 MongoDB
런타임·의존성·설정·배포 리소스를 삭제한다.

완료 조건은 다음과 같다.

- 문서 본문 저장의 모든 관계형 변경과 `document_edit_outbox` insert가 한 PostgreSQL
  transaction에서 함께 commit 또는 rollback된다.
- 변경 저장, 무변경 저장, 같은 write ID 재전송, 다른 payload 재사용, revision 충돌,
  동시 저장의 외부 동작이 테스트로 고정된다.
- 기존 HTTP 응답과 `document.edit.event` topic·key·JSON schema는 바뀌지 않는다.
- Kafka 발행은 현재와 같은 at-least-once이며 AI consumer의 revision 비교로 중복을 흡수한다.
- 운영 경로의 MongoDB 코드·의존성·환경 변수·CI·Compose·Kubernetes·Terraform 참조가 0건이다.
- 전환 후 MongoDB fallback, dual write, 호환 계층을 남기지 않는다.

## 2. 확인된 현행 상태

### 2.1 저장소와 원자성

| 책임 | 현행 저장 위치 | 확인된 문제 |
|---|---|---|
| 최신 Markdown·revision | MongoDB `document_edit_states` | PostgreSQL metadata와 commit 경계가 다르다. |
| write ID 처리 결과 | MongoDB `document_edit_writes` | 본문과는 원자적이지만 PostgreSQL version/audit와는 원자적이지 않다. |
| 편집 event outbox | MongoDB `document_edit_outbox` | 본문과는 원자적이지만 PostgreSQL metadata와는 원자적이지 않다. |
| legacy 본문 projection | PostgreSQL `document_edit_states` | 테이블은 이미 존재하지만 revision이 없고 Mongo 최신 본문보다 뒤처질 수 있다. |
| 버전·문서 hash·자산 참조·AI 작업 기록 | PostgreSQL | 현재 저장 경로에서는 여러 transaction으로 나뉠 수 있다. |

`DocumentService.saveContent()` 자체에는 transaction 경계가 없다. 일부 호출자가 이미 연
PostgreSQL transaction에 참여할 수는 있지만, 어떤 호출 경로도 MongoDB commit과 PostgreSQL
commit을 하나로 묶을 수 없다. 따라서 “모든 PostgreSQL 쓰기가 언제나 각각 commit된다”가 아니라
“MongoDB와 PostgreSQL 사이의 원자 commit이 불가능하다”가 정확한 문제 정의다.

### 2.2 직접 사용하는 코드

Mongo 저장소의 직접 기능 호출은 다음 네 서비스에 있다.

- `DocumentService`: 변환 결과 저장, 상세 조회, 일반 본문 저장, 버전 목록 revision 조회,
  재처리 본문 조회
- `DocumentExportService`: 내보낼 최신 본문 조회
- `AgentToolService`: Agent 도구용 최신 본문 조회
- `SkillReferenceService`: skill reference용 최신 본문 조회

삭제 대상 Mongo package:

- `DocumentEditMongoMigrationService`
- `MongoDocumentEditOutboxEvent`
- `MongoDocumentEditOutboxPublisher`
- `MongoDocumentEditSaveResult`
- `MongoDocumentEditState`
- `MongoDocumentEditStore`
- `MongoDocumentEditWrite`
- `MongoTransactionConfig`

`AgentTurnService`, `DocumentRestoreApplier`, `DocumentRepository`, `JpaConfig`의 Mongo 언급은
직접 저장 호출이 아니라 설명·간접 설정이다. 전환 시 문구와 설정만 실제 구조에 맞춘다.

본문 생성 경로인 업로드, 문서 복제, 직접 Markdown 생성, 변환 placeholder 생성은 이미
PostgreSQL `DocumentEditStateRepository`에 insert한다. 새 revision 필드가 빠지지 않도록 이
경로들도 함께 수정해야 한다.

### 2.3 확인 과정에서 바로잡은 전제

- 외부 벤치마크의 약 1.4배 수치는 PostgreSQL 18 JSONB 상품 문서와 MongoDB를 비교한 결과다.
  이 프로젝트의 PostgreSQL 16 `text` Markdown 예상치로 단정하지 않는다.
- 이관 비용이 0이라는 주장은 사실이 아니라 “현재 데이터를 폐기해도 된다”는 제품 결정일 때만
  성립한다.
- `documents.current_version`은 이동·삭제·복원 등에도 증가하므로 편집 revision의 backfill
  원천으로 사용할 수 없다.
- Mongo outbox publisher는 Kafka 전송 후 published 표시 전에 죽으면 같은 event를 다시 보낼
  수 있다. 중복 0건을 완료 조건으로 두지 않는다.
- 현재 Kubernetes의 document service와 edit-event consumer는 각각 1 replica다. 이번 동등성
  이관에 다중 publisher claim/lease를 미리 만들지 않는다.
- repo에는 정식 `docs/adr/0016-...`과 이 초안이 참조하는 ADR 0018이 없다. 다운로드 파일을
  이미 채택된 repo ADR로 취급하지 않는다.

조사 당시 로컬 MongoDB 표본은 state 23건, write receipt 27건, outbox 26건(미발행 0건,
발행 26건)이었다. Markdown은 30~697 byte, 평균 약 206 byte였다. 이 숫자는 이관 직전에 다시
측정해야 하며 폐기 승인을 대신하지 않는다. 당시 로컬 PostgreSQL container에는 예상한
`core_db`가 없어 Compose volume도 현행 구성과 일치한다고 볼 수 없었다.

## 3. 확정 설계

### 3.1 최소 PostgreSQL schema

기존 `document_edit_states`에 `revision bigint NOT NULL`만 추가한다. Markdown, content hash,
created/updated timestamp는 기존 열을 그대로 쓴다.

새 `document_edit_writes`는 replay에 필요한 값만 저장한다.

- `(document_id, revision_write_id)` primary key
- `request_hash`: 같은 write ID에 다른 `base_revision + content_hash`가 들어왔는지 판정
- `result_revision`, `result_content_hash`, `result_updated_at`
- `actor_user_id`, `changed`, `created_at`

기존 Mongo receipt의 `base_markdown`은 PostgreSQL에 다시 저장하지 않는다. 최초 저장 transaction은
잠근 state에서 base Markdown을 바로 version/audit에 사용하고, replay는 `replayed=true` 결과로
metadata 작업을 건너뛴다. 최초 transaction이 원자적이므로 replay가 누락된 projection을 복구할
필요가 없어진다.

새 `document_edit_outbox`는 현재 event 계약과 발행 상태만 저장한다.

- `event_id` primary key
- `document_id`, `workspace_id`, `revision`, `content_hash`
- `event_type`, `schema_version`, `created_at`
- `published`, `published_at`

기존 `ai_operation_logs` 감사 행은 보존한다. 다만 fresh cutover로 편집 revision 세대가 바뀌므로
V39는 `document_restore_blocked boolean NOT NULL DEFAULT false`를 추가하고 migration 당시의
`document_edit` 행만 `true`로 표시한다. preview와 execute는 공통 `RestoreTargetValidator`에서
이 값을 확인해 해당 문서 편집 복구를 차단하며, 새 작업과 `ingest`·`lint` 복구는 유지한다.

기존 `ai_command_outbox`를 범용 테이블로 바꾸지 않는다. topic이 다른 두 queue를 합치면 장애 시
서로를 막을 수 있고, Mongo 제거에 필요하지 않은 변경 범위가 늘어난다.

이번 작업에는 receipt TTL, content version 보존 기간, TOAST/fillfactor/autovacuum 조정,
Wiki Markdown 열 제거를 포함하지 않는다. 측정된 문제가 생길 때 별도 결정으로 다룬다.

### 3.2 저장 알고리즘

기존 `TransactionTemplate`과 PostgreSQL transaction manager를 재사용한다. 같은 클래스 내부 호출에
`@Transactional`을 붙여 해결하려 하지 않는다. Spring proxy self-invocation에는 새 transaction
경계가 적용되지 않기 때문이다.

한 저장 transaction은 다음 순서를 따른다.

1. `(document_id, revision_write_id)` receipt를 조회한다.
2. receipt가 있으면 `request_hash`를 비교한다. 같으면 저장 결과를 `replayed=true`로 반환하고,
   다르면 기존 idempotency conflict를 반환한다.
3. state를 준비하고 `base_revision`과 일치하는 행만 PostgreSQL conditional update한다.
4. 변경 저장은 Markdown·hash·updated timestamp를 바꾸고 revision을 1 증가시킨다.
5. 무변경 저장도 `WHERE document_id=? AND revision=? AND content_hash=?` 조건의 no-op
   `UPDATE ... RETURNING`을 실행한다. 동시에 다른 변경이 먼저 commit되면 0행이 되어 409를
   반환해야 한다.
6. receipt를 insert한다. unique 충돌은 transaction을 재시도한 뒤 receipt replay/충돌 판정으로
   귀결한다.
7. 실제 변경일 때만 base/current `document_content_versions`, `documents.current_content_hash`,
   asset row·reference, 유효한 Agent apply token·operation log·version link,
   `document_edit_outbox`를 같은 transaction에 기록한다.
8. 변환 저장이면 placeholder 변환 완료 metadata도 같은 transaction에 기록한다.
9. 하나라도 실패하면 위 DB 변경을 모두 rollback한다.

PostgreSQL 16 기본 `READ COMMITTED`에서 concurrent `UPDATE`는 선행 writer를 기다린 뒤 `WHERE`
조건을 다시 평가한다. conditional update 결과 행 수/`RETURNING`을 revision CAS의 기준으로 삼는다.

`apply_operation_id`가 null이면 일반 사용자 저장으로 처리한다. null이 아닌 값은 같은 transaction에서
사용자·문서가 일치하는 유효한 token인지 확인하고 소비한다. 위조되거나 이미 소비된 값이면 본문,
version, outbox를 commit하지 않는다. revision conflict는 본문 변경이 없으므로 기존처럼 별도
PostgreSQL transaction에서 token 소비와 conflict audit를 함께 남긴 뒤 409를 반환할 수 있다.

S3/MinIO object 업로드는 DB transaction에 포함할 수 없다. 기존처럼 먼저 업로드하되, 새 asset
row는 본문 변경 transaction 안에서 insert하고 실패·무변경이면 호출자가 업로드 object를 정리한다.

### 3.3 outbox publisher

- 미발행 행을 `created_at, event_id` 순으로 최대 100건 조회한다.
- Kafka key는 계속 `document_id`를 쓴다.
- topic, event type `document.edit.saved.v1`, schema version 1, JSON 필드명을 유지한다.
- 전송 성공 후 `published=true`, `published_at=now()`로 갱신한다.
- 한 event가 실패하면 문서별 순서를 보수적으로 지키기 위해 현재 주기를 중단한다.
- 발행은 at-least-once다. 전송 후 marking 전 장애 중복을 허용하고 AI consumer가 더 큰 revision만
  반영하는 현재 동작을 회귀 테스트한다.

이번에는 현재 1 replica 전제를 유지한다. publisher를 2개 이상 실행해야 할 때만
`FOR UPDATE SKIP LOCKED` 기반 claim/lease를 별도 작업으로 추가한다.

## 4. 구현 순서와 검증

### 테스트 실행 병렬화 원칙

다음 검증은 서로 상태를 공유하지 않으므로 작업과 실행을 병렬화할 수 있다.

- 문서 상세·내보내기·Agent 도구·Skill reference의 조회 consumer 단위 테스트
- Kafka event 직렬화·publisher 단위 테스트와 AI consumer의 중복·역순 revision 처리 테스트
- Mongo 참조 `rg`, Compose config, Kustomize 같은 읽기 전용 정적 검사

PostgreSQL integration test는 각 테스트가 고유한 `document_id`, `revision_write_id`,
`apply_operation_id`를 사용하고 독립 transaction/cleanup으로 격리됐음이 확인된 경우에만 병렬로
실행한다. revision CAS 경합은 여러 테스트를 우연히 동시에 실행해서 검증하지 않고, 테스트 하나
안에서 두 transaction을 latch/barrier로 제어해 의도적으로 동시에 실행한다.

다음 검증 게이트는 순서를 고정한다.

```text
Flyway → store CAS·replay → 전체 metadata rollback → 데이터 이관 대조
       → Mongo 코드·구성 제거 → fresh PostgreSQL E2E
```

schema migration, 실제 데이터 import/삭제, source/target 대조는 다른 DB 변경 작업과 병렬로
실행하지 않는다. 빠른 피드백 단계에서 격리된 테스트만 병렬화하되, 최종 승인 전에는 Gradle
`--parallel` 없이 전체 suite와 E2E를 순차 실행해 공유 DB·Testcontainers lifecycle로 인한
간헐적 성공을 배제한다.

### 0단계. 기준 재확인과 데이터 처리 방식 승인

작업 시작 시 다음을 먼저 수행한다.

- `git status --short`, 현재 branch/HEAD를 기록하고 이 문서 기준 이후의 관련 변경을 diff한다.
- `rg`로 Mongo 직접 호출, 설정, 테스트, 배포 참조를 다시 수집한다.
- Mongo 세 collection의 총건수와 미발행 outbox 수를 다시 센다.
- PostgreSQL `document_edit_states` 건수와 Mongo state의 document별 revision/hash를 비교한다.

그 뒤 아래 둘 중 하나를 사용자가 명시적으로 선택해야 한다.

**A. 데이터 폐기**

- 적용 환경의 MongoDB 편집 collection(`document_edit_states`, `document_edit_writes`,
  `document_edit_outbox`)과 기존 PostgreSQL `document_edit_states`,
  `document_content_versions`를 폐기해도 되는지 정확한 DB·table/collection·volume 단위로 승인을 받는다.
- broad `docker compose down -v`, workspace 전체 삭제, 불명확한 volume 삭제는 하지 않는다.
- 승인된 대상만 초기화하고 fresh database에서 migration을 적용한다.

**B. 데이터 보존**

- 서비스 쓰기를 중지한다.
- Mongo state를 `document_edit_states`의 Markdown/hash/revision으로 offline import한다.
- 기존 write receipts를 새 최소 schema로 변환해 replay 의미를 보존한다.
- 미발행 outbox를 새 PostgreSQL outbox로 옮긴다. 발행 완료 행 보존 여부는 운영 감사 요구로
  결정하되 미발행 행은 누락하면 안 된다.
- document 존재, state 수, revision/hash, receipt 수, pending event 수를 source/target 간 검증한다.
- 검증 실패 시 cutover하지 않는다.

`documents.current_version`으로 revision을 채우는 제3의 경로는 허용하지 않는다. 보존 경로는
runtime dual read 없이 서비스가 중지된 offline schema 준비/import/검증/cutover로 수행한다.

완료 확인: 선택한 데이터 방식을 기록했고, 삭제가 있다면 별도 명시 승인을 받았으며, source/target
검증 쿼리 결과가 남아 있다.

### 0단계 실행 기록

- branch: `feat/mongodb-to-postgresql`
- 시작 HEAD: `9c07cbed` (이 계획을 반영한 carry-over commit)
- 데이터 처리 방식: 사용자 선택 **A. 데이터 폐기** — import는 하지 않고 비교 oracle만 사용한다.
- 읽기 전용 측정: Mongo `fruition_document`는 states 59건, writes 83건, outbox 82건,
  pending 0건이다. PostgreSQL `core_db`는 `document_edit_states` 405건, documents 409건이며,
  대응 비교는 overlap 22건, hash mismatch 22건, hash match 0건, Mongo-only 37건이다.
- 현재 실행 중인 공유 Compose stack은 다른 worktree도 사용하므로 Mongo collection/container/volume과
  PostgreSQL data를 삭제하지 않았다. 정확한 삭제 대상이 격리되지 않았기 때문이다. 코드 cutover에는
  삭제가 필요하지 않으며, 정확한 대상이 확인된 경우에만 삭제할 수 있다.
- PostgreSQL 표본은 pre-V39 상태여서 edit revision column이 없다. `documents.current_version`은
  backfill에 사용하지 않았다.

### 1단계. 현행 동작을 PostgreSQL integration test로 고정

`MongoDocumentEditStoreIntegrationTest`의 의미를 PostgreSQL Testcontainers test로 옮긴다.

- 최초 변경: revision 증가, state·receipt·outbox 생성
- 무변경: revision/updated timestamp 유지, receipt 생성, outbox 미생성
- 같은 write ID와 같은 요청: 같은 응답 replay, metadata 중복 없음
- 같은 write ID와 다른 요청: idempotency conflict
- stale base revision: version conflict, state·receipt·outbox 변화 없음
- 두 변경의 동시 CAS: 정확히 하나만 성공
- no-op과 변경의 동시 CAS: 변경이 먼저 commit되면 no-op은 conflict
- transaction 후반 예외: state·receipt·version·hash·asset·audit·outbox 전부 rollback
- 유효하지 않은 non-null apply token: 본문을 포함해 전부 rollback
- publisher payload/topic/key 유지와 실패 재시도

테스트가 기존 분리 commit을 재현하는 데 머물지 않고 목표 transaction 계약을 검증하게 작성한다.

완료 확인: 새 테스트가 구현 전 실패하고, 어떤 원자성 조건이 깨지는지 명확히 보여 준다.

### 2단계. Flyway schema와 PostgreSQL store 구현

- 다음 순번 Flyway migration으로 revision, write receipt, 전용 edit outbox를 추가한다.
- 0단계에서 선택한 데이터 방식과 맞지 않는 상태에서는 migration/deploy가 실패하도록 guard한다.
- `DocumentEditState`에 revision을 반영하고 모든 신규 state 생성 경로가 초기 revision을 명시하게 한다.
- `JdbcTemplate` 기반의 작은 `PostgresDocumentEditStore` 하나로 conditional update,
  receipt replay, outbox insert를 구현한다. 단일 구현을 위한 interface/factory는 만들지 않는다.
- unique/deadlock 등 재시도가 필요한 경우 store 일부가 아니라 전체 저장 transaction을 제한적으로
  다시 실행한다. 최종 CAS 불일치는 재시도하지 않고 기존 409로 변환한다.

완료 확인: 1단계 store/concurrency/rollback 테스트가 통과한다.

### 3단계. 전체 metadata를 한 transaction으로 묶기

- `DocumentService.saveContent`가 기존 `TransactionTemplate` 안에서 store와 모든 PostgreSQL
  metadata 작업을 실행하게 한다.
- replay 결과에는 version/hash/asset/audit/outbox를 다시 쓰지 않는다.
- `saveContentWithAssets`의 asset row를 같은 transaction에 포함하고 object 정리 책임은 유지한다.
- `applyConvertedMarkdown`의 본문과 변환 완료 metadata를 같은 transaction에 포함한다.
- 정상 저장의 apply token은 본문보다 먼저 검증하거나 같은 transaction rollback으로 보호한다.
- conflict audit처럼 본문 변경이 없는 기록만 별도 transaction으로 유지한다.

완료 확인: 서비스 integration test에서 각 후반 실패 지점마다 부분 commit이 0건이다.

### 4단계. 모든 읽기와 생성 경로를 PostgreSQL로 전환

- `DocumentService`의 상세/버전/재처리 조회에서 Mongo fallback을 제거한다.
- `DocumentExportService`, `AgentToolService`, `SkillReferenceService`를
  `DocumentEditStateRepository` 또는 새 PostgreSQL store 조회로 전환한다.
- 업로드, 복제, 직접 Markdown 생성, placeholder 생성, initializer가 revision을 올바르게 설정한다.
- HTTP response의 `currentVersion`, Markdown, content hash가 PostgreSQL state에서 일관되게 나온다.

완료 확인: 네 직접 consumer와 모든 테스트에서 `MongoDocumentEdit*` import/call이 0건이다.

### 5단계. MongoDB 코드와 운영 구성을 삭제

코드:

- `fruition/core/document/mongo/` package와 해당 테스트 삭제
- `document-svc/build.gradle`의 Spring Data MongoDB와 Mongo Testcontainers 의존성 삭제
- `application.properties`의 Mongo URI/migration mode 삭제
- `TestcontainersConfiguration`의 Mongo container/service connection 삭제
- `JpaConfig`와 관련 서비스의 legacy/Mongo 설명을 PostgreSQL 기준으로 정정

운영 구성:

- `.github/workflows/tests.yml`, `.github/workflows/web-services.yml`
- `infra/.env.example`, `infra/compose.infra.yml`, `infra/compose.containerized.yml`
- `infra/terraform/README.md`, `infra/terraform/secrets.tf`
- `k8s/README.md`, `k8s/base/configmap.yaml`, `k8s/base/kafka.yaml`, `k8s/base/mongodb.yaml`
- frontend의 Mongo canonical 설명 주석

`k8s/base/mongodb.yaml`은 현재 `k8s/base/kustomization.yaml`에 포함되지 않고 README에서 수동 적용한다.
존재하지 않는 kustomization 참조를 제거했다고 기록하지 말고 파일과 수동 적용 안내만 삭제한다.

과거 의사결정·backlog의 Mongo 언급은 역사 기록이므로 일괄 삭제하지 않는다.

완료 확인:

```bash
rg -n -i 'mongo(db)?|spring-data-mongodb' \
  services .github infra k8s \
  --glob '!**/build/**'
```

운영 경로 결과가 0건이어야 한다. 역사 문서까지 0건으로 만들 필요는 없다.

### 6단계. 문서와 전체 회귀 검증

- 다운로드 초안을 사실 검증 결과로 고쳐 정식 `docs/adr/0016-...md`로 추가한다.
- ADR 0016에서 ADR 0001의 Mongo 저장 결정과 ADR 0003의 Mongo edit outbox 결정을 명시적으로
  대체한다. 존재하지 않는 ADR 0018 참조는 제거하거나 실제 ADR이 생긴 경우에만 연결한다.
- `docs/architecture.md`: document service 저장소·transaction·outbox 구조 수정
- `docs/data-model.md`: `document_edit_states`, `document_edit_writes`,
  `document_edit_outbox` 소유권과 핵심 제약 수정
- `docs/script.md`: Mongo 기동·환경 변수·초기화 절차 제거
- API 계약이 유지되면 `docs/api.md`는 불필요하게 수정하지 않는다.

검증 명령:

```bash
cd services/backend
./gradlew :document-svc:test

cd ../..
docker compose -f infra/compose.infra.yml config
docker compose -f infra/compose.containerized.yml config
kubectl kustomize k8s/base >/dev/null
git diff --check
```

가능하면 fresh PostgreSQL로 document service를 실제 기동해 Markdown 생성 → 변경 저장 → 같은 write ID
재전송 → stale revision 409 → outbox 발행 → AI state 갱신을 한 번 통과시킨다. 데이터 보존 경로를
선택했다면 이관 전후 count/revision/hash 검증도 배포 승인 조건에 포함한다.

완료 확인: 전체 테스트·Compose/Kustomize 구성 렌더링·fresh PostgreSQL integration 검증이 통과하고 현행 문서가 구현과 일치한다.

## 5. 작업 중 중단해야 하는 조건

다음 상황에서는 추측으로 진행하지 않는다.

- 폐기 승인 없이 Mongo collection, PostgreSQL database/schema, Docker volume을 지워야 하는 경우
- Mongo state와 PostgreSQL document의 대응이 깨졌거나 pending outbox가 검증되지 않은 경우
- `documents.current_version` 외에 신뢰할 revision 원천이 없는 보존 대상이 발견된 경우
- 기존 HTTP/Kafka 계약 변경이 필요해진 경우
- 다중 replica publisher, TTL, 보존 정책, DB tuning처럼 이번 이관 범위를 넓혀야 하는 경우
- 작업 시작 시 관련 코드가 이 문서 기준 commit과 달라 원자성 경계가 바뀐 경우

## 6. 최종 검증 실행 기록

- JDK 21 순차 실행: `./gradlew :document-svc:test --no-daemon --rerun-tasks` — XML 결과
  110 suites, 687 tests, failures 0, errors 0, skipped 0.
- `PostgresDocumentEditStoreIntegrationTest`: 10 passed. fresh Testcontainers PostgreSQL과
  Flyway V39에서 결정적 concurrency/replay/rollback 검증을 포함한다.
- dev Compose config pass; merged dev+pipeline+converter+deploy Compose config pass.
- `kubectl kustomize` pass.
- 운영 경로 `mongo`/`spring-data-mongodb` `rg` 결과 0건.
- `git diff --check` pass.
- Terraform CLI는 사용할 수 없어 구조적 HCL 검토만 선행했다.
- 결정적 코드·테스트 실패는 0건이다.
- LLM quality matrix는 이번 이관이 document storage와 event publication만 변경했으므로 재실행하지
  않았다. 기준 `origin/dev-msa` merge #175는 결정적 `PRODUCT DEFECT` 0건,
  `LLM_QUALITY DEFERRED`였고, 이번 migration regression은 전체 `document-svc` suite와 변경되지
  않은 topic/key/schema publisher tests로 검증했다. 모든 live LLM 시나리오가 통과했다고 주장하지
  않는다.

## 7. 구현 체크리스트

- [x] 기준 branch/HEAD와 dirty worktree 확인, 사용자 변경 보존
- [x] Mongo/PG 현황 재측정 및 데이터 폐기 또는 보존 방식 승인
- [x] PostgreSQL store 동작·동시성·rollback 테스트 작성
- [x] Flyway schema와 `PostgresDocumentEditStore` 구현
- [x] 본문·receipt·version·hash·asset·audit·outbox 단일 transaction화
- [x] 네 직접 consumer와 모든 state 생성 경로 PostgreSQL 전환
- [x] Mongo package·의존성·설정·CI·배포 리소스 삭제
- [x] 정식 ADR 0016과 현행 architecture/data-model/demo 문서 갱신
- [x] Gradle test, Compose config, Kustomize, fresh PostgreSQL integration, `rg`, `git diff --check` 통과
- [x] fresh PostgreSQL에서 Markdown 생성→변경 저장→동일 write ID replay→stale revision 409
  → PostgreSQL outbox→Kafka→AI state 갱신 live E2E 통과
- [ ] 승인된 정확한 대상에 한해서만 Mongo data/resource 제거 — 미실행; 정확한 공유 대상이
  격리되지 않아 cutover에 필요하지 않으며, 삭제 완료로 간주하지 않는다.

## 8. 참고 근거

- PostgreSQL 16 transaction isolation:
  <https://www.postgresql.org/docs/16/transaction-iso.html>
- PostgreSQL 16 `UPDATE ... RETURNING`:
  <https://www.postgresql.org/docs/16/sql-update.html>
- Spring declarative transaction과 proxy self-invocation:
  <https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html>
- PostgreSQL TOAST:
  <https://www.postgresql.org/docs/current/storage-toast.html>
- 저장 용량 비교의 원문(이 프로젝트 예상치가 아닌 외부 참고):
  <https://binaryigor.com/json-documents-mongodb-vs-postgresql.html>
