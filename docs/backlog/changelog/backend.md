# Changelog — Backend

Spring Boot 백엔드 변경 이력입니다. 날짜 역순으로 기록합니다.

> AI/LLM/pipeline(llmPipeline) 변경 이력은 `docs/changelog/ai.md`를 참고하세요.

---

## 2026-08-10

- 워크스페이스 OWNER가 ingest/lint AI provider와 model을 설정하고 MEMBER가 조회할 수 있는 API를 추가했다.
- Query별 AI provider/model 선택값과 사용자 전역 웹 검색 허용 여부를 실행 이력에 snapshot으로 저장한다.
- 사용자 웹 검색 설정 조회·변경 API와 access/document 서비스 간 내부 조회를 추가했다. 기본값과 조회 실패 시 동작은 모두 비허용이다.
- AI Query HTTP/Kafka payload에는 설정을 `allow_web_search` boolean으로 전달하며 AI pipeline 구현은 변경하지 않는다.
- `java-shared`, `access-svc`, `document-svc` 전체 테스트를 통과했다.

## 2026-08-07

### feat: PDF 원본 Markdown 변환 제품 흐름 연결

- `POST /api/workspaces/{wid}/documents/{id}/convert-markdown`(202) — PDF 원본 검증
  + Idempotency-Key, placeholder markdown 문서 즉시 생성(`source_document_id` 연결)
  후 `document_convert_queue`(V21) 등록.
- `DocumentConvertWorker`(2초 폴링·stuck 복구, 기존 처리 큐 패턴)와 `ConverterClient`
  (S3 원본 → converter `/convert`, read timeout 900s) — 완료 시 Mongo edit store로
  본문 반영(write_id `convert:{queueId}` 멱등) 후 completed, 실패 시 failed+원인.
- **버그 수정: afterCommit 콜백에서 기본(REQUIRED) 트랜잭션 INSERT가 조용히 유실**
  — 이미 커밋된 트랜잭션에 참여해 커밋되지 않는 문제. REQUIRES_NEW로 교체.
  같은 패턴이 `requestProcessingAfterCommit`에도 존재(`docs/issue/backend/2026-08-07.md`).
- E2E 실검증: PDF 업로드→변환 요청→OCR→markdown 문서 completed·본문 확인.

### feat: 문서 편집 원본 MongoDB 전환과 edit outbox 발행 (§3.1)

- 문서 본문·편집 revision·write-id를 MongoDB(`document_edit_states`·`document_edit_writes`·
  `document_edit_outbox`)로 이전 — 본문 갱신+revision 증가+write receipt+outbox 저장을
  **단일 Mongo 트랜잭션**으로 처리(참조 브랜치 feat/msa-mongodb-outbox 포팅).
- PUT content 계약 변경: `base_version` → `base_revision` + `revision_write_id`(멱등 재시도).
  상세 응답에 `edit_revision` 추가. PostgreSQL에는 metadata·버전 스냅샷 projection 유지.
- `MongoDocumentEditOutboxPublisher`(신규): 미발행 outbox를 Kafka `document.edit.event`
  (key=document_id)로 발행 — at-least-once, 문서별 순서 보존.
- `JpaConfig`에 `@Primary` JpaTransactionManager 명시 — mongoTransactionManager 등장으로
  JPA @Transactional 자동 구성이 꺼지는 문제 예방.
- E2E 실검증: 저장(rev 2)→같은 write_id 재생(멱등, 동일 응답)→낡은 revision 409→
  outbox 발행·Kafka 소비 확인. 테스트 444+108 통과.

### feat: PostgreSQL access/core 분리와 계정 격리

- 단일 `fruition_mvp` DB를 `access_db`/`core_db`/`ai_db` + runtime(DML)·migration(DDL)
  계정 6개로 분리. 타 서비스 DB write 불가 (`infra/postgres/init-db-isolation.sh`,
  validation 스크립트로 실검증: runtime CREATE 거부·타 DB write 거부).
- access-svc가 **자체 Flyway 소유** 시작: V1 baseline(users·oauth·refresh·email verification·
  workspaces·members·idempotency 7테이블, 실DB pg_dump 기반) + V2 세션 스키마
  (`initialize-schema=never` 전환 — runtime 계정은 DDL 불가).
- document-svc 마이그레이션에서 access 테이블·교차 FK 13건 제거(V1·V3·V9·V15·V20,
  V7/V10/V14는 no-op화). `DocumentRepository.findByIdInActiveWorkspace`의 workspaces
  EXISTS 서브쿼리 제거 — workspace 유효성은 WorkspaceAccessGuard가 전담.
- Idempotency 테이블은 각 DB에 서비스별 사본(코드는 java-shared 공유 유지).
- ai 테이블(pipeline_runs·임베딩)은 core_db 전환기 동거 — ai_runtime 별도 계정으로
  접속(차단 사유 실측: `docs/issue/ai/2026-08-07.md`).
- 테스트: access-svc 108 + document-svc 435 통과. 로컬 스택 실검증(가입→문서 흐름,
  access_db 10테이블/core_db 26테이블 분리 확인).

### feat: backend를 access-svc·document-svc로 물리 분리 (MSA Phase 3)

- 단일 Spring 앱을 Gradle 멀티프로젝트 3개로 분할: `access-svc`(:8081, 인증·OAuth·
  세션·워크스페이스·멤버·권한 projection), `document-svc`(:8080, 문서·채팅·Wiki·query,
  Flyway 스키마 소유, stateless), `java-shared`(JWT·공통 예외·Idempotency 라이브러리).
- 코드 경계를 컴파일러가 강제: document→access, access→document import 0건. 두 앱은
  서로의 DB repository를 직접 쓰지 않는다.
- 인가를 Redis 권한 projection(`authz:role:{wid}:{uid}`, TTL 300s)으로 전환. document
  guard는 캐시 hit 즉시 판정, miss 시 access 내부 API(`/internal/authz`) 폴백, 실패 시
  fail-closed. access는 멤버십 변경 시 write-through/무효화. → **access 다운 중에도 캐시
  warm 문서 기능 생존**(실검증: 로그인 000 / 문서 조회 200 / 업로드 201).
- access→document 초기 노트는 내부 API로 전환, 트랜잭션 커밋 후 호출(FK 위반 해소, best-effort).
- 실런타임 버그 수정: `DocumentRepository.findByIdInActiveWorkspace` JPQL이 access로 이관된
  Workspace 엔티티를 참조해 부팅이 깨지던 것을 native query로 교체.
- 테스트: access-svc 108 + document-svc 435, 실패 0.
- 문서: `docs/msa/`(현행 구조·배포·검증).

## 2026-08-06

### feat: ingest command를 Kafka 발행으로 전환

- 문서/채팅 Wiki ingest 요청을 pipeline 동기 HTTP 호출 대신 `ai.ingest.command`
  topic 발행(`IngestCommandPublisher`)으로 전환했다. key=workspace_id로 워크스페이스별
  순차·워크스페이스 간 병렬을 보장한다.
- run_id는 backend가 생성해 command에 싣는다 — 동기 응답 없이 문서 run 기록과
  pipeline-events 콜백 run_id 대조를 유지한다. 발행 실패는 기존 실패 마킹 경로 재사용.
- `DocumentProcessingRequester` 제거(발행으로 대체). E2E 검증: worker 다운 중 발행
  → Kafka lag 대기 → 기동 후 소비(유실 0).

### feat: AWS 배포 대비 — 인증·인가 경계 확립과 상태 외부화 (MSA Phase 0~2 일부)

- SecurityConfig를 deny-by-default로 전환. 공개 경로(인증·OAuth·swagger·내부 콜백)만
  화이트리스트로 남기고 나머지는 전부 authenticated. `/api/query/runs/**` 조회·SSE에
  인증과 workspace 멤버십 검사를 적용했다(QueryRun에 workspace_id 추가).
- JWT에 iss(`fruition-access`)·aud(`fruition-api`) 클레임을 발급·검증한다(HS256 유지,
  RS256/JWKS는 access-svc 분리 시점 항목).
- 11개 서비스에 복제돼 있던 워크스페이스 멤버십 검사를 단일 인가 지점
  `WorkspaceAccessGuard.requireMember`로 통합했다. 예외(404 fail-closed)는 동일.
- 상태 외부화(Redis): OAuth 교환 코드(TTL 60s, GETDEL 1회 사용), query run 상태
  (JSON+TTL), SSE 이벤트(list replay + pub/sub 인스턴스 간 중계, sequence 중복 제거).
  인스턴스 2대 이상에서 로그인·질의 SSE가 동작하는 구조가 됐다.
- V20 migration: `wiki_page_links`·`document_wiki_links`·`chat_partial_wiki`에
  `workspace_id` 추가·backfill·NOT NULL·FK·인덱스. WikiService의 메모리 workspace
  보정을 `findAllByWorkspaceId` 쿼리로 대체.
- pipeline 호출 client 7개를 공용 `PipelineClientFactory`(connect 5s + 호출별 read
  timeout, `X-Internal-Token` 기본 헤더)로 통합. timeout이 없어 무한 대기하던
  DocumentProcessingRequester에 `app.processing.timeout-seconds`(기본 200s)를 부여.
- 무인증이던 내부 콜백(DocumentPipelineController, query events callback)에
  `X-Internal-Token` 상수시간 검증을 추가했다.

## 2026-08-06

### refactor: 이미지 asset placeholder 대응 정리와 UUID version 제약 완화

**배경**

- 이미지 asset 계약 리뷰의 남은 지적 사항을 정리했다. 동작을 바꾸지 않는 구조 개선과, 프론트가
  발급하는 placeholder UUID의 불필요한 제약 제거가 대상이다.

**변경된 것**

- `DocumentAssetValidator.validateAll`이 `List` 대신 `Map<UUID, MultipartFile>`을 받고
  `Map<UUID, ValidatedAsset>`을 돌려준다. 기존에는 호출부가 `keySet()`과 `values()`의 반복 순서가
  일치한다는 가정으로 인덱스를 세어 placeholder와 검증 결과를 다시 짝지었다. `Map.copyOf`는 반복
  순서를 보장하지 않아 가정에 기대는 구조였다.
- placeholder UUID 정규식에서 version(`1-5`)과 variant 제약을 제거하고 UUID 형태만 강제한다.
  프론트가 UUIDv7 등을 발급하면 저장이 `400`으로 거절되던 문제를 없앤다. `UUID.fromString` 검증과
  placeholder–file part 1:1 대응 검사는 그대로 유지된다.
- 외부 호출자가 없던 `DocumentService.validateContentSave` 4-arg 오버로드를 제거했다.
- `DocumentController`와 `DocumentExportService`의 인라인 FQN(`fruition.document.exception....`,
  `java.io.IOException`)을 import로 정리하고, 컨트롤러 지역 변수명을 실제 의미에 맞춰
  `attachments`에서 `fileParts`로 바꿨다.

**검증**

- `cd backend && ./gradlew test` 통과
- placeholder–검증 결과 대응과 v4가 아닌 UUID 수용을 단위 테스트로 추가 검증했다.

### fix: 문서 내보내기 스트리밍 전환과 저장 응답 최종 Markdown 정합

**배경**

- 이미지 asset 계약 리뷰에서 내보내기 응답이 ZIP 전체를 힙에 올리는 문제와, 저장 응답의
  `markdown` 필드가 요청 형식에 따라 달라지는 문제를 확인했다.

**수정된 것**

- `DocumentExportResult`가 `byte[]` 대신 `contentLength`와 `InputStream`을 전달한다. 기존에는
  임시 파일에 ZIP을 스트리밍으로 완성한 뒤 `Files.readAllBytes`로 최대 100MB를 다시 힙에 올려,
  임시 파일을 쓴 이점이 사라지고 동시 내보내기에서 메모리 사용량이 선형으로 늘었다. 임시 파일은
  `StandardOpenOption.DELETE_ON_CLOSE`로 응답 stream이 닫힐 때 함께 정리한다.
- 내보내기의 DB 조회와 ZIP 생성을 분리했다. 기존에는 `@Transactional(readOnly = true)` 안에서
  최대 100MB를 MinIO에서 내려받아 그동안 DB 커넥션을 붙잡았다. 이제 조회만 짧은 트랜잭션에서
  수행하고 다운로드와 압축은 트랜잭션 밖에서 한다.
- 이미지 없이 저장하는 경로도 응답에 최종 Markdown을 담는다. 기존에는 `metadata` multipart 저장만
  `markdown`을 채우고 `markdown` part 저장은 `null`을 반환해, `docs/spec/api/document.md`의 응답
  계약과 어긋났고 프론트가 저장 형식별로 분기해야 했다. no-op 저장도 서버가 가진 현재 본문을
  반환한다.

**주의사항**

- 내보내기 트랜잭션이 쪼개지면서 조회들이 하나의 스냅샷이 아니게 된다. asset 누락 시 `422`로
  전체 실패하므로 불완전한 ZIP은 나가지 않는다.
- HTTP 응답 형식은 바뀌지 않는다. 저장 응답의 `markdown`은 스키마에 이미 있던 필드이며 값이
  `null`에서 실제 본문으로 채워질 뿐이다.
- Markdown 본문에 raw HTML `<img>`로 관리 이미지 경로를 적으면 참조로 인식되지 않는다. 관리
  이미지는 인증이 필요해 `<img src>`로 표시되지 않고 SDD가 raw HTML 미실행과 CommonMark 사용을
  명시하므로 현행 유지로 결정했다. 프론트 이미지 렌더러 작업 시 입력 단계에서 막는다.

**검증**

- `cd backend && ./gradlew test` 통과
- 내보내기 stream 길이와 ZIP 내용, 일반 저장·no-op 응답의 `markdown`을 단위 테스트로 검증했다.

### refactor: 이미지 asset 조회와 정리 worker의 object storage 호출 범위 축소

**배경**

- 이미지 asset 계약 리뷰에서 object storage 호출이 필요 이상으로 일찍 실행되거나 DB 트랜잭션
  안에서 수행되는 지점 두 곳을 확인했다.

**변경된 것**

- `DocumentAssetReadService.read`를 `readMetadata`와 `openStream`으로 나눴다. ETag는 DB의 content
  hash에서 나오므로 조건부 요청 판정에 object storage가 필요 없는데, 기존에는 `304`로 응답할
  경우에도 MinIO에서 object를 먼저 받아온 뒤 닫았다.
- 이미지 정리 worker의 트랜잭션을 쪼갰다. 기존에는 하나의 `@Transactional` 안에서 asset 100건과
  orphan 100건, 최대 200회의 MinIO 삭제를 수행해 그동안 DB 커넥션과 row lock을 붙잡았다. 이제
  후보 조회와 row 삭제만 짧은 트랜잭션에서 처리하고 MinIO 삭제는 트랜잭션 밖에서 수행한다.
  기존 `DocumentProcessingWorker`의 `TransactionTemplate` 패턴을 따랐다.
- `FOR UPDATE SKIP LOCKED` native 잠금 쿼리 두 개와 사용처가 없던 조회 메서드 두 개를 제거하고
  derived query로 통일했다.

**주의사항**

- 잠금 쿼리 제거로 여러 인스턴스가 같은 정리 후보를 동시에 집을 수 있다. MinIO `removeObject`와
  `deleteById` 모두 멱등이라 결과는 같다.
- HTTP 응답 형식(상태 코드·헤더·본문)은 바뀌지 않아 프론트 영향이 없다.

**검증**

- `cd backend && ./gradlew test` 통과
- `304` 응답에서 object stream을 열지 않는지, 정리 worker가 storage 삭제 성공·실패별로 row를
  어떻게 처리하는지 단위 테스트로 검증했다.

### fix: 일반 Markdown 저장의 asset 참조 동기화와 이미지 용량 한도 정합 수정

**배경**

- 이미지 asset 계약 리뷰에서 저장 경로가 `metadata` multipart와 `markdown` part 둘로 갈리면서 생긴
  정합성 문제 두 건을 확인했다.

**수정된 것**

- 이미지를 첨부하지 않는 일반 저장(`DocumentService.saveContent`)에서도 본문을 기준으로 asset
  reference를 동기화한다. 기존에는 `saveContentWithAssets`에서만 동기화해서, 본문에서 이미지를
  지우고 저장해도 reference row가 남아 `unreferenced_since`가 찍히지 않았고 정리 worker가 해당
  object를 영구히 삭제하지 못했다. 반대로 본문에 관리 이미지 경로를 새로 붙여도 reference가
  생기지 않았다.
- `spring.servlet.multipart.max-request-size`를 50MB에서 110MB로 올렸다. 이미지 합계 한도 100MB를
  코드에서 검사하기 전에 Spring이 요청을 먼저 차단해, 계약상 `413 DOCUMENT_ASSET_TOO_LARGE`가
  나가야 할 50~100MB 구간이 `400 INVALID_REQUEST "파일이 없거나 비어 있습니다."`로 응답됐다.
- `MaxUploadSizeExceededException` 전용 handler를 추가해 multipart 한도 초과를
  `413 PAYLOAD_TOO_LARGE`로 구분한다. 기존 `MultipartException` handler는 파일 누락 400 응답을
  그대로 유지한다.

**주의사항**

- 일반 저장에도 참조 동기화가 걸리면서, 본문에 잘못된 관리 이미지 경로나 다른 workspace의 asset
  경로가 있으면 이제 400으로 거절된다. 이미지 포함 저장 경로에는 이미 적용되던 규칙이며 두 경로의
  동작을 일치시킨 것이다.
- `max-request-size` 확대는 다른 multipart endpoint에도 적용된다. 파일 1개 한도는
  `max-file-size=50MB`로 유지된다.

**검증**

- `cd backend && ./gradlew test` 통과
- 일반 저장의 참조 동기화 호출과 413/400 구분을 각각 단위 테스트로 추가했다.

---

## 2026-08-05

### feat: Markdown 이미지 asset 저장 모델 추가

**배경**

- Markdown 본문과 신규 이미지를 원자 저장하기 위한 선행 단계로 asset metadata와 문서 참조 관계를
  DB에서 추적할 기반이 필요했다.

**추가된 것**

- `document_assets`, `document_asset_references` 테이블과 workspace·사용자·문서 FK를 추가했다.
- 참조 중 asset 삭제를 차단하고, 미참조 정리와 asset 기준 reference 조회 index를 추가했다.
- asset과 복합키 reference JPA entity 및 repository를 추가했다.
- 이미지 저장 `metadata` JSON과 `attachment_<uuid>` file part를 해석하고 placeholder 누락, 중복 file,
  미사용 file과 잘못된 part를 거절하는 요청 parser를 추가했다.
- PNG·JPEG·WebP·GIF signature와 decoder/구조, dimension, 개별 10MB, 요청당 20개·100MB 제한을
  검증하고 검증된 MIME·SHA-256·원본 bytes를 만드는 이미지 검증기를 추가했다.
- asset 전용 MinIO adapter와 저장 coordinator를 추가해 여러 이미지 저장 중 실패하면 이미 저장된
  object를 보상 삭제하고, 삭제 하나가 실패해도 나머지 삭제를 계속 시도하도록 했다.
- 보상 삭제 실패 object를 `document_asset_orphans`에 별도 transaction으로 기록해 이후 worker가
  재시도할 수 있게 했다.
- CommonMark 이미지 destination에서 관리 asset 참조를 추출하고 workspace batch 검증, 문서별
  reference diff, 마지막 참조 제거·재참조 상태를 동기화하도록 했다.
- Markdown 문서 복제 시 asset row와 MinIO object를 복사하지 않고 기존 asset reference만 복사한다.
- `PUT /documents/{document_id}/content`에 `metadata` JSON과 `attachment_<uuid>` file part 저장 흐름을
  연결했다. 저장 전후 version을 각각 확인하고 성공 시 치환된 Markdown과 attachment–asset 매핑을
  반환한다.
- 문서 본문·asset row·reference를 한 DB transaction에서 갱신하고 DB 실패나 version 충돌에는 이번
  요청에서 선저장한 MinIO object를 보상 삭제한다.
- 이미지 포함 저장도 `apply_operation_id`를 전달받아 AI 편집 성공 또는 version 충돌 작업 로그를
  일반 Markdown 저장과 같은 기준으로 기록한다.
- workspace 멤버 전용 이미지 조회 endpoint를 추가했다. 비멤버·다른 workspace asset은 `404`로
  처리하고 검증 MIME·길이·private cache·ETag·`nosniff`와 조건부 `304` 응답을 제공한다.
- 7일 이상 미참조 이미지와 7일 경과 보상 삭제 orphan을 `FOR UPDATE SKIP LOCKED` batch로 정리하는 worker를
  추가했다. MinIO 삭제에 성공한 경우만 DB row를 제거하고 실패 항목은 다음 실행에서 재시도한다.
- 관리 이미지가 있는 Markdown 내보내기를 ZIP으로 확장했다. 관리 URL을 로컬 상대 경로로 치환하고
  파일명 충돌, 100개·100MB 제한, asset 누락과 MinIO 실패를 완성 전 검증하며 외부 URL은 fetch하지 않는다.
- multipart Controller가 알 수 없는 업로드 file part를 버리지 않고 parser 검증으로 전달하도록 수정해
  잘못된 part 이름이 조용히 무시되지 않게 했다. API·OpenAPI와 SDD 요구사항 추적 결과도 갱신했다.

**검증**

- `DocumentEditingSchemaIntegrationTest`로 migration 적용과 참조 중 asset 삭제 차단을 검증했다.
- `DocumentAssetSaveRequestParserTest`로 정상 매핑, 이미지 없는 요청과 잘못된 multipart 조합을 검증했다.
- `DocumentAssetValidatorTest`로 MIME 위장, SVG·손상 파일 거절, PNG/JPEG/GIF/WebP dimension,
  GIF bytes 보존과 개수·크기 제한을 검증했다.
- `DocumentAssetStorageCoordinatorTest`로 정상 object key 생성, 중간 저장 실패 보상과 일부 삭제 실패
  시 전체 삭제 시도를 검증했다.
- schema 통합 테스트로 orphan 테이블 migration을 검증했다.
- parser·synchronizer·문서 복제 테스트로 코드 블록/일반 링크 제외, 중복 참조, workspace 격리,
  reference 추가·제거와 복제 동작을 검증했다.
- asset 저장 orchestration과 Controller 테스트로 placeholder 치환, 최종 응답, 충돌 보상과 기존
  이미지 없는 저장의 하위 호환을 검증했다.
- asset 조회 service·Controller 테스트로 멤버 stream, 비멤버·workspace 격리, 보안·cache header와
  ETag 조건부 응답을 검증했다.
- 정리 worker 테스트로 7일 기준 조회, object 선삭제 순서, MinIO 실패 시 asset row 유지와 orphan
  retry metadata 갱신을 검증했다.
- 내보내기 service·Controller 테스트로 기존 `.md` 호환, ZIP MIME·entry·경로 치환·파일명 충돌,
  외부 URL 유지, 누락 asset과 개수·합계 용량 제한을 검증했다.
- Markdown 5MB와 이미지 제한의 `413` 오류 코드 분리, 잘못된 multipart file part 전달을 검증하고
  Backend 전체 테스트, `flywayValidate`, `git diff --check`를 통과했다.

---

## 2026-08-04

### fix: 복구 callback 삭제 대상을 지시서와 대조

- 복구 callback의 `deleted_pages`가 `restore_manifest`의 `delete` 대상에 포함되는지 변경 저장 전에 검증한다.
- 계획에 없는 페이지가 오면 422 `INVALID_CALLBACK_PAYLOAD`로 거절해 다른 페이지의 삭제 감사 로그가 잘못 남지 않게 했다.
- 계획에 포함된 삭제 대상 일부만 보고하는 부분 성공 callback은 계속 허용한다.
- 회귀 테스트와 Backend 전체 `./gradlew test`, `git diff --check`가 통과했다.

---

## 2026-08-04

### feat: lint 작업 로그 저장과 되돌리기 지원

**배경**

Wiki lint는 llmPipeline이 페이지를 직접 변경하지만 Backend에는 작업별 버전과 변경 이력이 남지 않아 조회하거나 되돌릴 수 없었다. 또한 lint 되돌리기는 ingest와 달리 기여를 제거하는 대신 lint 작업이 만든 페이지 변경만 역산해야 한다.

**변경된 것**

- 실제 lint 실행 전에 Backend가 `operation_id`를 발급하고, llmPipeline의 `changed_pages`를 받아 페이지 버전과 `ai_operation_changes`를 저장한다. lint는 새 기여를 만들거나 기존 기여 수를 늘리지 않는다.
- lint 로그의 목록·상세·diff 조회를 지원하고, 생성 페이지는 삭제, 수정 페이지는 활성 기여로 재조립하는 되돌리기 계획을 추가했다. 대상 이후 같은 페이지가 변경됐으면 안전하게 거절한다.
- llmPipeline의 `/wiki/lint-restore-runs` 계약에 맞춰 재조립 페이지와 삭제 페이지를 전달한다.
- 복구 callback의 `deleted_pages`, `link_changes`, `failed_actions`를 수신한다. 삭제 페이지와 제거·복원 relation link를 감사 로그로 남기고 부분 성공 상태와 건수 요약을 보존한다.

**검증**

- lint 시작·결과 반영·조회·미리보기·실행·callback 계약 테스트를 추가했다.
- 실제 PostgreSQL 동시 실행 테스트로 같은 페이지의 revision이 충돌하지 않고 순차 증가하는지 확인했다.
- Backend 전체 `./gradlew test`와 `git diff --check`가 통과했다.

**남은 주의사항**

- llmPipeline callback에 `X-Internal-Token`이 없어 현재 Backend가 결과를 401로 거절한다.
- llmPipeline에서 `deleted_pages`의 링크·임베딩을 실제 정리하는 작업은 별도 AI 이슈로 남아 있다.

---

## 2026-08-04

### fix: 미리보기와 실행의 검증을 일치시킴

**배경**

실행은 `document_edit`·`ingest`·`lint`만 받고 나머지는 400으로 거절하는데, **미리보기에는 유형 검사가 없었다.** 되돌리기 기록(`restore` 유형)을 지목하면 미리보기가 그럴듯한 계획을 돌려준다. `restore` 로그도 `target_document_id`를 갖고 있어 범위 결정과 페이지 판정이 끝까지 수행되기 때문이다. 로그 목록에 `restore` 항목이 그대로 나오므로 실제로 눌릴 수 있고, 사용자는 확인 화면을 다 본 뒤에 400을 받는다.

원문 페이지 확인과 빈 계획 거절도 실행에만 있었다.

**변경된 것**

- `RestoreTargetValidator`를 추가해 세 검증을 한곳에 모았다. 되돌릴 수 있는 유형인지, 계획이 비지 않았는지, ingest면 원문 페이지가 있는지다.
- `RestorePreviewService`와 `RestoreExecuteService`가 이것을 공유한다. **미리보기가 통과시킨 것은 실행도 통과한다**(그사이 대상이 바뀌는 경우는 `preview_token`이 잡는다).
- `RestoreExecuteService`에 있던 `requireSourcePage`와 유형 검사를 옮기면서 `WikiPageRepository` 의존이 빠졌다.

**검증**

- `RestoreTargetValidatorTest` 6개 — 허용 유형 3종, `restore` 거절, 빈 계획 거절, `page_type`으로 원문 페이지 찾기, 원문 없으면 거절, lint는 조회 자체를 안 함.
- `RestorePreviewServiceTest` 6개 — 유형 거절, 실행이 거절할 계획은 미리보기도 거절, 정상 응답, 문서 편집 분기, 비멤버 404, 없는 작업 404. 이 서비스에 전용 테스트가 없었다.
- `RestoreExecuteServiceTest`는 검증기를 mock으로 두고 배선만 확인하도록 정리했다. 판별 규칙은 검증기 테스트가 다룬다.
- Backend 전체 `./gradlew test` 473개가 통과했다.

---

## 2026-08-04

### fix: 재작성 대상이 없어도 llmPipeline 결과를 기다리도록 수정

**배경**

지시서를 보낸 뒤 `plan.hasRebuild()`가 false면 그 자리에서 `succeeded`로 확정했다. 그런데 **llmPipeline은 `rebuild_pages`가 비어 있어도 항상 콜백을 보낸다**(`restore_wiki_pages.py`의 `execute_ingest`·`execute_lint`가 무조건 `_notify` 호출). 결과적으로:

- 콜백이 종료된 작업에 도착해 `payload_hash` 불일치로 **409**가 난다. 계약상 llmPipeline은 409를 받으면 중단하므로 그 복구는 매번 오류로 끝난다.
- llmPipeline이 링크·임베딩 정리를 끝내기도 전에 사용자에게 **완료로 보인다.**

문서를 두 번 ingest하고 마지막을 취소하면 판정이 `restore`와 `delete`로만 나와 실제로 도달하는 경로다.

**변경된 것**

- `RestoreOperationLifecycle.finish` — 통지에 성공하면 재작성 대상 유무와 무관하게 `rebuilding`이다. 확정은 재조립 결과를 받을 때 한다.
- `RestoreExecuteResponse.from` — `status`와 `rebuilding`을 같은 기준으로 맞췄다. `rebuilding`은 이제 "llmPipeline 결과를 기다리는 중"을 뜻한다.
- 문서 편집 되돌리기는 그대로다. llmPipeline을 부르지 않으므로 즉시 `succeeded`다.

**요약이 사라지지 않게 함께 고침**

중간 상태로 옮길 때도 요약을 남기도록 `OperationLog.moveTo(status, summary)`를 추가했다. 결과를 기다리는 동안 목록에 무엇을 했는지 보여야 한다.

그리고 llmPipeline 복구 결과 payload에는 `summary`가 없어서, `RestoreRebuildApplier`가 확정할 때 기존 요약을 null로 덮어쓰고 있었다. 콜백에 값이 없으면 유지하도록 바꿨다.

**검증**

- `RestoreExecuteServiceTest`의 "재작성 대상이 없고 통지에 성공하면 그 자리에서 끝난다"를 "재작성 대상이 없어도 llmPipeline 결과를 기다린다"로 뒤집었다.
- `OperationQueryControllerTest`의 되돌리기 응답 단정도 함께 맞췄다.
- Backend 전체 `./gradlew test` 462개가 통과했다.

---

## 2026-08-04

### fix: 원문 페이지를 못 찾으면 반영 전에 거절

**배경**

llmPipeline의 `source_page.page_id`는 필수 필드다. Backend가 원문 페이지를 못 찾아 `null`을 보내면 Pydantic이 400으로 거절하는데, 그 시점에는 이미 DB 반영이 끝나 있어 **복구가 `notify_pending`에 영구히 갇힌다.** 재시도해도 같은 요청이라 계속 실패한다.

**변경된 것**

- 원문 페이지를 `document_wiki_links`의 `source_of`가 아니라 **`wiki_pages.page_type`** 으로 찾는다. 링크 테이블은 llmPipeline이 관리하고 문서 재처리 과정에서 지워질 수 있어, 페이지 자신이 들고 있는 값을 보는 편이 안전하다. `WikiPageRepository.findIdsByPageType`을 추가했다.
- 못 찾으면 **`applier.apply()` 전에** `InvalidRestoreRequestException`(400)으로 거절한다. 아무것도 바꾸지 않으므로 갇히는 상태가 생기지 않는다.
- 그 결과 쓰이지 않게 된 `DocumentWikiLinkRepository` 의존을 `RestoreExecuteService`에서 걷어냈다.

거절해도 안전한 이유는, 원문 페이지가 계획에 없다는 것은 취소 대상이 건드린 활성 기여가 하나도 없다는 뜻이고, 그러면 다른 페이지도 마찬가지라 계획이 통째로 비어 이미 400이 나기 때문이다. 실질적으로는 안전망이다.

### test: AI 작업 로그 컨트롤러 테스트 추가

`aihistory` 도메인만 `@WebMvcTest`가 없어 인증·권한·응답 직렬화가 서비스 테스트로만 덮여 있었다.

- `OperationQueryControllerTest` 11개 — snake_case 직렬화, 커서·필터 전달, 상세의 `hunks` 포함과 `diff_too_large` 생략, 미리보기가 Wiki면 `pages`·문서면 `document`만 차는지, `preview_token` 전달, 404·409·400, 미인증 401.
- `OperationCallbackControllerTest` 9개 — **토큰 검증이 서비스에 닿기 전에 끊는지**(없음·틀림·사용자 JWT 모두), 확정 상태를 고정값이 아니라 실제 값으로 돌려주는지, 404·409·422 매핑, `changed_pages` 누락 400, 재조립 결과의 `failed_pages` 수용.

콜백 테스트에서 `verify(ingestService, never())`로 **인증 실패 시 서비스 호출이 없는 것**까지 확인한다. 저장소 객체를 읽는 것이 그 뒤라 순서가 중요하다.

**정리**

`RestoreApplier`의 `WikiPage`, `WikiService`의 `WikiPageStatus` import가 각각 `wiki_pages` 쓰기 제거와 삭제 판정 변경으로 고아가 돼 지웠다.

**검증**

Backend 전체 `./gradlew test` 462개가 통과했다.

---

## 2026-08-04

### fix: 복구 조립 지시서를 llmPipeline 계약에 맞춤

**배경**

`origin/dev` 병합으로 llmPipeline의 복구 구현이 이미 들어와 있는 것을 확인했다. 양쪽이 **서로 다른 계약을 가정하고 병렬로 만들어** 엔드포인트와 필드가 어긋나 있었다. llmPipeline이 테스트까지 갖춰 병합돼 있어 Backend를 그쪽에 맞춘다.

지금 상태로는 되돌리기를 실행하면 404가 나고 `notify_pending`에서 멈춘다.

**변경된 것**

- 엔드포인트를 둘로 나눈다. llmPipeline이 `POST /wiki/ingest-restore-runs`와 `POST /wiki/lint-restore-runs`를 따로 열어 두었고 요청 스키마도 다르다. 설정 키도 `app.wiki-restore.ingest-endpoint`·`lint-endpoint`로 나눴다.
- `PipelineRestoreRequester`를 지시서 2종으로 다시 썼다.

| 항목 | 처리 |
|---|---|
| `excluded_operations` | `cancel_operation_ids`로 이름 맞춤 |
| `keep_contributions[].object_key` | **제거.** llmPipeline이 `wiki/{ws}/pages/{page}/ops/{op}.json`을 같은 규칙으로 조립하고 조각 안 식별자까지 대조한다 |
| `contribution_count` | **제거.** Backend만 쓰는 값이라 `restore_manifest`에 보관한다 |
| `restored_pages`·`restored_from`·`user_id` | **제거.** 받지 않는 필드다 |
| `restore_to_operation_id` | **추가.** source page를 어느 작업 시점으로 되돌릴지. `PageRestorePlan`에 `targetOperationId`를 넣어 계획 단계에서 계산한다 |
| `source_page` | **추가.** 필수 필드다. `document_wiki_links`의 `source_of`로 찾는다 |

- `RestoreApplier`가 되돌린 페이지 목록을 반환하지 않는다. llmPipeline이 `restored_pages`를 받지 않아 쓸 곳이 없어졌다.

**source page는 양쪽이 각자 되돌린다**

`source_page`가 필수라 안 보낼 수 없고, llmPipeline은 그것을 받으면 자기 사본 객체를 만들어 `changed_pages`로 보고한다. Backend도 로컬에서 되돌린다.

두 결과의 **본문이 같아** 콜백 수신 시 `content_hash` 비교로 걸러지므로 revision이 중복 생기지 않는다. 이를 위해 `RestoreRebuildApplier`가 지시서의 `restore` 판정 페이지도 인정하도록 넓혔다. 이전에는 `rebuild` 목록에만 있으면 인정해서, source page가 실려 오면 재조립 수신 전체가 422로 실패했다.

Backend가 로컬에서 처리하므로 되돌리기 속도는 그대로다. llmPipeline 왕복을 기다리지 않는다.

**lint는 엔드포인트만 맞췄다**

`WikiMaintenanceService`에 작업 로그 연동이 아직 없어 lint 작업 자체가 기록되지 않는다. 되돌릴 대상이 없으므로 실제 호출은 lint 연동이 생길 때 확인한다.

**검증**

- `RestoreExecuteServiceTest`에 3개를 더해 12개가 됐다. ingest 지시서에 source page와 되돌릴 시점을 싣는지, 남는 기여가 없으면 `restore_to_operation_id`가 null인지, lint가 다른 엔드포인트로 가는지다.
- `RestoreRebuildApplierTest`의 "되돌리기로 끝낸 페이지는 재조립 대상이 아니다"를 뒤집었다. 이제 받아들이되 내용이 같아 건너뛴다. 지시서에 아예 없는 페이지를 거절하는 테스트를 따로 뒀다.
- Backend 전체 `./gradlew test` 440개가 통과했다.

**남은 것**

llmPipeline 복구 경로에 DB 접근이 없어, 삭제된 페이지의 링크(`wiki_page_links`·`document_wiki_links`)와 임베딩이 정리되지 않는다. `docs/issue/ai/2026-08-03.md`에 요청 항목으로 남겼다.

---

## 2026-08-03

### fix: Backend가 wiki_pages에 쓰지 않도록 정리

**배경**

`wiki_pages`는 llmPipeline 소유다. `5f230a4`("refactor: Wiki 페이지 이름 변경을 llmPipeline에 위임")에서 rename까지 걷어냈는데, 이번 작업이 그보다 깊은 쓰기를 다시 넣었다. 설계 문서에 "`markdown_uri` 갱신은 항상 Backend"라고 적은 것 자체가 코드베이스 규약과 어긋난 판단이었다.

llmPipeline의 ingest 경로가 `markdown_uri`를 갱신하고 Backend가 콜백을 받아 다른 키로 덮어써, 두 주체가 같은 컬럼을 두고 다투는 상태이기도 했다.

**걷어낸 것**

- `WikiPage.moveMarkdownUri()`·`softDelete()` 제거. 호출부 4곳(`OperationApplier`, `RestoreApplier` 2곳, `RestoreRebuildApplier`)도 함께.
- `RestoreApplier`의 링크 삭제 2곳 제거. `wiki_page_links`·`document_wiki_links`도 llmPipeline 소유다.
- 그 결과 쓰이지 않게 된 `WikiPageLinkRepository`·`DocumentWikiLinkRepository` 의존과, 고아가 된 `findByIdAndWorkspaceId`·`findAllByWorkspaceId`를 지웠다.

**현재 본문을 어디서 읽나**

`wiki_page_versions`의 **최신 revision**이 답한다. Backend가 revision을 쌓는 것 자체가 "현재 내용이 이것"이라는 뜻이라, 포인터를 따로 옮길 이유가 없었다. 중복 상태 하나가 사라진다.

상세 조회가 MinIO 왕복에서 RDS 읽기로 바뀌어 저장소 장애와도 무관해진다. revision 기록이 없는 페이지(이 기능 이전 생성)만 `markdown_uri`로 폴백한다. 본문이 객체 저장소에 있어 SQL 마이그레이션으로 채울 수 없으므로 폴백을 남겼다.

**삭제를 어떻게 판단하나**

`status='deleted'` 대신 `wiki_page_contributions`에 활성 기여가 남았는지로 본다. 이것이 원래 삭제 판정의 근거였고, 상태 컬럼은 그 결론을 복사한 것뿐이었다.

| 기여 상태 | 판정 |
|---|---|
| 하나라도 활성 | 살아 있음 |
| 기여가 있고 전부 비활성 | 삭제됨 |
| 기여가 아예 없음 | 살아 있음 — 이 기능 이전 페이지 |

`findAliveByWorkspaceId`·`findAliveByIdAndWorkspaceId`·`findAliveIds`로 교체했다.

`V17`은 이미 적용된 마이그레이션이라 되돌리지 않는다. `WikiPageStatus.deleted`도 CHECK 제약이 허용하는 값을 읽을 수 있도록 남기고, 쓰지 않는 이유를 주석으로 적었다.

**바뀌지 않는 것**

되돌리기의 `restore` 판정은 지금처럼 Backend가 DB만으로 즉시 끝낸다. llmPipeline 왕복이 늘지 않는다.

**검증**

- `WikiServiceTest`에 2개를 더해 7개가 됐다. 최신 revision에서 본문을 읽는지(저장소 미접근 확인), revision이 없으면 폴백하는지다.
- `WikiPageLockIntegrationTest`의 `markdown_uri` 단정을 "Backend가 갱신하지 않는다"로 뒤집었다.
- Backend 전체 `./gradlew test` 436개가 통과했다.

**llmPipeline 이슈 문서 정정**

`docs/issue/ai/2026-08-03.md`의 L2-3(`ON CONFLICT`에서 `markdown_uri`·`status` 제거 요청)을 **철회**했다. 전제가 틀렸다. 대신 복구로 삭제된 페이지의 **링크·임베딩 정리**를 요청 항목으로 넣었다. 현재 llmPipeline 복구 경로에 DB 접근이 없어 이 정리가 누락된다.

---

## 2026-08-03

### fix: 되돌리기 범위에 지목한 작업 자신을 포함

**배경**

ingest 되돌리기가 "이 시점으로 되돌리기"였다. `A1 → A2 → A3`에서 A2를 지목하면 A3만 취소되고 A2는 살아남았다. 그런데 lint 되돌리기는 지목한 작업 하나만 취소한다. **같은 버튼인데 작업 유형에 따라 결과가 달랐다.**

로그 목록에서 항목을 보고 되돌리기를 누르는 흐름에서는 "이 항목이 한 일을 없앤다"가 자연스럽다. ingest를 lint 쪽에 맞춘다.

**변경된 것**

- `RestoreScopeResolver` — 취소 집합에 지목한 작업 자신을 넣는다. A2를 지목하면 `{A2, A3}`가 된다. `LinkedHashSet`이라 같은 시각 작업이 조회에 섞여 들어와도 중복되지 않는다.
- Swagger 설명과 스펙·설계 문서, 프론트 이슈 문서의 문구를 바꾼다.

**사용자에게 달라지는 것**

```
"A2가 만든 걸 없애고 싶다"   →  A2 지목      (기존에는 A1을 지목해야 했다)
"A2까지는 살리고 싶다"       →  A3 지목
```

**바뀌지 않는 것**

- `RestorePlanner`는 취소 집합을 받아 판정할 뿐이라 그대로다. 집합이 커질 뿐이다.
- llmPipeline 계약도 그대로다. `restore_to_operation_id`와 `cancel_operation_ids`를 따로 받으므로 어느 의미로 채우든 수용한다.

**검증**

- `RestoreScopeResolverTest` 3개를 새 의미로 고쳤다. 지목 작업 포함, 같은 시각 중복 방지, 마지막 작업 지목이다.
- Backend 전체 `./gradlew test` 434개가 통과했다.

---

## 2026-08-03

### fix: 코드리뷰 지적 사항 반영 (동시성·원자성·N+1)

**동시성·원자성**

- `OperationApplier` — ingest 적재가 행 잠금 없이 `findMaxRevision() + 1`로 채번했다. 같은 페이지 콜백 2건이 동시에 오면 revision이 겹쳐 한쪽이 PK 위반으로 500이 났다. `findByIdForUpdate`로 바꾸고 `page_id` 오름차순으로 처리한다. 복구 경로(`RestoreApplier`)와 같은 순서다.
- `DocumentRestoreApplier` — `@Transactional`이 없어 `saveContent` 커밋과 변경내역 insert가 별개 트랜잭션이었다. 뒤가 실패하면 문서만 바뀌고 감사 기록이 없다. `@Transactional`을 붙여 `saveContent`가 같은 트랜잭션에 참여하게 한다.

**재전송 판정 기준 변경**

`OperationApplier`가 직전 버전의 `content_hash`로 재전송을 가렸는데, 이 기준이 **무변경 판정과 재전송 방어를 겸하고 있어** 문제였다. 다른 문서의 ingest가 우연히 같은 내용을 만들면 재전송으로 오인해 그 문서의 기여가 원장에 남지 않았다. 그러면 나중에 앞 문서를 되돌릴 때 받치는 문서가 남았는데도 페이지가 삭제된다.

재전송 판정을 `(page_id, ingest_operation_id)` 존재 여부로 바꿨다. 이 PK가 곧 "이 작업이 이 페이지에 이미 반영됐다"는 뜻이라 판정이 정확해진다.

**오류 응답 구분**

- `WikiObjectReader` — `catch (Exception)`이 MinIO 장애까지 `InvalidCallbackPayloadException`(422)으로 바꿨다. 422는 계약상 "다시 쓰고 재전송"이라 저장소가 죽었을 때 llmPipeline이 무의미하게 재작업한다. 원인 예외도 로그 없이 삼켜 진단이 불가능했다. 경로 불일치만 422로 두고, 읽기 실패는 `WikiObjectReadException`(500 `WIKI_OBJECT_READ_FAILED`)으로 올리며 원인을 로깅한다.
- `ChangeDiffLoader` — 모든 `RuntimeException`을 `diff_too_large: true`로 표시해 NPE 같은 오류도 "너무 큽니다"로 나갔다. `MarkdownDiffTooLargeException`만 그렇게 표시하고 나머지는 `hunks`만 비운다.

**성능**

- `ChangeDiffLoader` — 변경내역마다 버전을 2번씩 조회해 리소스 30개면 60쿼리였다. 필요한 본문을 리소스 종류별로 `findAllById` 일괄 조회한 뒤 Map 조인하도록 바꿔 **2쿼리**가 된다.

**정리**

- 호출부가 없는 `WikiPageContributionRepository.findActiveByPageId`와 `WikiPageVersionRepository.findSummaries`를 제거했다.
- `WikiLineCounter`가 `WikiPageVersion`에 묶여 있어 문서 경로가 재사용하지 못하고 `OperationRecorder`에 같은 로직이 따로 있었다. 본문 문자열을 받는 `LineCounter`로 일반화해 세 경로가 공유한다.

**검증**

- `WikiPageLockIntegrationTest`에 3개를 더해 7개가 됐다. 동시 ingest 콜백의 revision 비충돌, 같은 작업 재전송 무시, 다른 작업의 동일 내용에도 기여 기록이다.
- 동시 콜백 테스트는 **잠금을 되돌리면 실제로 실패하는 것을 확인**했다.
- `ChangeDiffLoaderTest`에 일괄 조회 검증을 더해 7개가 됐다.
- Backend 전체 `./gradlew test` 434개가 통과했다.

---

## 2026-08-03

### test: Wiki 페이지 행 잠금 통합 테스트 추가

**배경**

`RestoreApplier`가 `page_id` 오름차순으로 `findByIdForUpdate` 잠금을 잡는데, 그게 실제로 동작하는지 단위 테스트로는 확인할 수 없었다. Mockito가 리포지토리를 대신하면 쿼리가 실행조차 되지 않는다. Testcontainers로 실제 Postgres에 붙여 검증한다.

**추가된 것**

- `WikiPageLockIntegrationTest` 4개
  - `findByIdForUpdate`가 행을 잠가 다른 트랜잭션이 막힌다. 짧은 `lock_timeout`으로 시도해 실제로 대기하는지 확인하고, 앞 트랜잭션이 끝나면 다시 잠기는 것까지 본다
  - 서로 다른 페이지는 동시에 잠긴다 (테이블 잠금이 아님을 확인)
  - `page_id` 오름차순으로 잠그면 동시 복구에도 교착이 나지 않는다
  - **반대 순서로 잠그면 교착이 난다** — 정렬이 필요한 이유를 대조군으로 고정

**교착 테스트의 단정**

Postgres가 교착을 감지하면 한쪽만 중단시키고 다른 쪽은 커밋된다. 그래서 `forwardOk ^ backwardOk`로 **정확히 한쪽만 실패**하는지 본다. "둘 다 성공하지 않음"으로 두면 다른 이유로 둘 다 실패해도 통과해버린다.

두 스레드가 각자 첫 행을 잡은 뒤에 두 번째를 시도해야 교착이 재현되므로, 그 지점에서 `CountDownLatch`로 서로를 기다린다.

**검증**

- 3회 연속 실행해 흔들림이 없음을 확인했다. 교착 테스트가 매번 1.0초 걸리는데 Postgres `deadlock_timeout` 기본값과 일치해, 실제로 교착이 재현되고 감지된 것이다.
- Backend 전체 `./gradlew test` 430개가 통과했다.

**남은 주의사항**

- 이 테스트는 복구 경로만 다룬다. **ingest 적재(`OperationApplier`)는 여전히 행 잠금이 없다.** 같은 페이지에 대한 콜백 2개가 동시에 오면 `max(revision)+1`이 겹쳐 한쪽이 PK 위반으로 실패한다.

---

## 2026-08-03

### feat: 작업 로그 상세에 변경분 포함

**배경**

목록에서 한 건을 고르면 상세와 변경분을 한 번에 받도록 한다. 기존에는 상세를 부르고 항목마다 diff 엔드포인트를 다시 불러야 했다.

**변경된 것**

- `ChangeDiffLoader` — 변경내역 한 건의 두 revision 본문을 읽어 그 자리에서 비교한다. `resource_type`에 따라 `wiki_page_versions` 또는 `document_content_versions`에서 읽는다.
- `OperationLogDetailResponse.Change`에 `hunks`와 `diff_too_large`를 추가한다. 값이 없으면 응답에서 생략된다.
- `additions`·`deletions`는 그대로 저장 시점 값이다. 다시 세지 않는다.

**한 항목의 실패가 상세 전체를 실패시키지 않는다**

큰 페이지 하나 때문에 나머지 멀쩡한 항목까지 못 보는 것은 잘못된 트레이드오프다. 개별 diff 엔드포인트였다면 422였을 경우도 상세에서는 200이고 그 항목만 `diff_too_large: true`가 된다. 버전 행이 없는 경우도 조용히 건너뛴다.

`before_revision`이나 `after_revision`이 없는 항목(`created`·`deleted`·`delegated`·`rebuild_failed`)은 비교할 짝이 없어 본문을 읽지 않는다.

**상한을 두지 않았다**

ingest 한 건이 위키 페이지를 몇 개나 건드리는지 실측 데이터가 없다. `document_wiki_links`가 0행이고 `wiki_pages`에 테스트 데이터 4건뿐이라 판단할 근거가 없었다. 없을지도 모르는 문제에 대비해 `diff_omitted` 같은 분기를 클라이언트에 강요하지 않기로 했다. 실제 운영 수치를 본 뒤 필요하면 추가한다. 응답에 필드가 느는 것이라 기존 클라이언트를 깨지 않는다.

**검증**

- `ChangeDiffLoaderTest` 6개를 추가했다. Wiki diff, 문서 diff, 생성 건너뛰기, `after_revision` 없는 3종 건너뛰기, 버전 부재, 계산 거부 시 예외 대신 표시다.
- Backend 전체 `./gradlew test`가 통과했다.

---

## 2026-08-03

### feat: AI 문서 편집 되돌리기를 복구 API로 통일

**배경**

되돌리기는 사용자에게 한 가지 동작인데, AI 문서 편집만 복구 API가 받지 않고 400으로 거절했다. 프론트가 작업 종류를 보고 `POST /documents/{id}/versions/{version}/restore`를 따로 불러야 했고, 그러려면 되돌릴 버전 번호까지 알아야 했다. 이제 `POST .../ai-operation-logs/{operation_id}/restore` 하나로 처리한다.

**변경된 것**

- `DocumentRestorePlanner` — `ai_operation_changes.before_revision`에서 되돌릴 버전을 읽는다. Wiki와 달리 계산할 것이 없다. `from_version`은 대상 작업이 만든 버전이 아니라 **지금 문서 버전**이다. 그 작업 이후 사용자가 더 저장했을 수 있다.
- `DocumentRestoreApplier` — 되돌릴 버전 본문으로 `DocumentService.saveContent`를 호출한다. 편집 잠금·낙관적 잠금·편집 상태 갱신이 이미 그 안에 있어 되돌리기라고 다르게 처리하지 않는다. 적용 표를 넘기지 않으므로 `document_edit` 로그는 생기지 않고, 대신 `restore` 작업에 `restored` 변경내역을 남긴다.
- `PreviewTokenSigner`에 문서용 서명을 추가한다. `from_version`이 서명에 들어가 미리보기 이후 문서가 저장되면 실행이 409로 막힌다.
- `RestorePreviewResponse`에 `document` 필드를 추가한다. Wiki면 `pages`가 차고 문서 편집이면 `document`가 찬다. 둘이 동시에 차지 않으며 빈 쪽은 응답에서 생략된다.
- `RestoreExecuteService`가 `document_edit`을 문서 분기로 보낸다. 재작성이 없어 llmPipeline을 부르지 않고 그 자리에서 `succeeded`로 끝난다.

**과거 버전을 되살리지 않고 새 버전을 쌓는다**

버전 5 → 6(AI 편집) 상태에서 되돌리면 5로 돌아가는 것이 아니라 5의 내용으로 **버전 7**이 생긴다. Wiki revision과 같은 원칙이다. 되돌린 것도 다시 되돌릴 수 있고, 같은 번호가 다른 내용을 가리키는 일이 없다.

**거절하는 경우**

새로 만든 문서라 `before_revision`이 NULL, 이미 그 버전, 문서 변경내역이 없는 작업, 되돌릴 내용이 현재와 같아 저장이 일어나지 않는 경우다.

**검증**

- `DocumentRestoreTest` 9개를 추가했다. 계획 5개(목적지 결정, `from_version`이 현재 버전인지, 이전 버전 없음, 이미 그 버전, 문서 변경내역 없음), 반영 3개(새 버전 append, `restored` 기록, 무변경 거절), 토큰 1개(문서가 바뀌면 서명 불일치)다.
- `RestoreExecuteServiceTest`에 문서 분기 라우팅과 토큰 불일치 2개를 더해 9개가 됐다.
- Backend 전체 `./gradlew test`가 통과했다.

**남은 주의사항**

- 기존 `POST /documents/{id}/versions/{version}/restore`는 그대로 둔다. 버전 목록 화면에서 쓰는 별개 경로이며 AI 작업 로그를 만들지 않는다.
- 채팅 메시지에서 되돌리기를 누르려면 `chat_messages`와 작업 로그를 잇는 작업이 따로 필요하다. 이번 범위에 없다.

---

## 2026-07-31

### fix: 소프트 삭제된 Wiki 페이지를 조회에서 제외

**배경**

복구가 페이지를 소프트 삭제하면 `wiki_pages.status`만 `deleted`로 바뀐다. 그런데 그래프·상세 조회 쿼리에 `status` 조건이 없어 삭제된 페이지가 그대로 응답에 나왔다. 복구가 링크는 정리하므로 그래프에서는 **고립 노드**로 남는 상태였다.

**변경된 것**

- `WikiPageRepository`에 `findAllByWorkspaceIdAndStatusNot`, `findByIdAndWorkspaceIdAndStatusNot`을 추가하고 `WikiService.findGraph`·`findById`가 이 쿼리를 쓰게 한다. 삭제된 페이지의 상세는 404다.
- 상세의 `related_pages`에서 삭제된 대상 링크를 뺀다. 복구가 링크를 정리하지만 그 전에 조회가 들어올 수 있다. **대상 자체가 존재하지 않는 링크는 기존대로 남겨 필드만 null로 내려간다** — 삭제와 부재는 다르게 다룬다.
- 그래프 간선은 page id 집합 기준으로 걸러지므로 별도 처리 없이 함께 빠진다.
- `GET .../wiki/pages/{id}/diff`는 그대로 둔다. 그래프·상세가 현재 상태를 보여주는 것과 달리 diff는 이력 조회이므로, 삭제된 페이지의 과거 revision 사이 변경분은 계속 볼 수 있어야 한다.
- `docs/spec/api/wiki.md`의 정합성 항목을 실제 동작에 맞춰 갱신한다.

**검증**

- `WikiServiceTest`에 3개를 추가해 5개가 됐다. 그래프에서 삭제 페이지·간선 제외, 삭제 페이지 상세 404, 연관 페이지에서 삭제 대상만 제외하고 부재 대상은 유지다.
- Backend 전체 `./gradlew test`가 통과했다.

**남은 주의사항**

- `docs/spec/api/wiki.md`의 rename 절이 실제와 다르다. 문서는 Backend가 slug를 생성하고 충돌을 검사하는 흐름으로 적혀 있으나, 현재 `WikiService.rename`은 `PipelineWikiPageRequester`에 그대로 위임한다(`5f230a4`). 이번 변경 범위 밖이라 손대지 않았다.
- `WikiPageRepository.findAllByStatus`, `findAllByPageType`은 호출부가 없다. 이번 변경으로 생긴 것이 아니라 이전부터 있던 미사용 메서드다.

### docs: AI 작업 로그 API 스펙 작성

**변경된 것**

- `docs/spec/api/ai-operation-log.md`를 추가한다. 다른 스펙 문서와 같은 재구성 스펙 형식이며 데이터 모델, 사용자 엔드포인트 4개, 내부 콜백 1개, 복구 계산 규칙, llmPipeline 연동 계약, 작업 등록 지점, 예외·설정 키를 담는다.
- `docs/spec/api/00-common.md`를 갱신한다. 전역 예외 표에 신규 예외 7개(`AI_OPERATION_NOT_FOUND`, `INVALID_RESTORE_REQUEST`, `RESTORE_PREVIEW_STALE`, `AI_OPERATION_PAYLOAD_CONFLICT`, `INVALID_CALLBACK_TOKEN`, `INVALID_CALLBACK_PAYLOAD`, `WIKI_PAGE_VERSION_NOT_FOUND`)를 추가하고, `/api/ai-operations/**`가 Spring Security 대신 `X-Internal-Token`으로 검증된다는 점과 설정 키 3개를 더한다.
- `OperationLogRepository`에서 `findByTargetDocumentIdAndOperationTypeOrderByCreatedAtAsc`를 제거한다. 복구 범위 선택(`mode`)을 없애면서 호출부가 사라진 메서드다.
- 같은 이유로 남아 있던 `mode=since`·`mode=document` 언급을 리포지토리 주석과 작업 계획 문서에서 정리한다.

**검증**

- 문서에 적은 경로·요청·응답 필드·예외 코드를 실제 컨트롤러와 `GlobalExceptionHandler`에서 대조했다.
- Backend 전체 `./gradlew test`가 통과했다.

**남은 주의사항**

- TASK-009의 나머지 완료 조건인 실제 ingest·복구 E2E 검증은 llmPipeline이 `operation_id` 수용, 기여 조각 저장, `POST /wiki/restore-runs`를 구현한 뒤에야 가능하다.

### feat: 복구 재조립 결과 수신 추가

**변경된 것**

- `POST /api/ai-operations/{operation_id}/result`가 작업 유형에 따라 갈린다. `restore`면 재조립 분기로 가서 복구의 `rebuilding` 단계를 끝낸다. 엔드포인트는 그대로 하나다.
- `OperationResultRequest`에 `failed_pages`를 추가한다. 재조립에만 실리며 없으면 전량 성공이다.
- `RestoreRebuildApplier` — 재조립 결과를 한 트랜잭션으로 반영한다. 성공분은 `revision = max+1`로 적재하고 `rebuilt`를, 실패분은 본문을 건드리지 않고 `rebuild_failed`와 사유를 기록한다. `delegated` 행은 그대로 둔다.
- `contribution_count`는 다시 세지 않고 복구가 보관해 둔 `restore_manifest`에서 꺼낸다. 그사이 새 ingest가 들어와도 목표값이 흔들리지 않는다.
- 지시서에 `rebuild`로 없는 페이지가 결과에 오면 422로 거절한다. 요청하지 않은 페이지다.
- 콜백 응답이 실제 상태를 돌려준다. 기존에는 `succeeded`로 고정이라 부분 실패를 알 수 없었다. `OperationResultResponse`를 추가하고 `accept()`가 이 값을 반환한다.
- `WikiLineCounter`를 분리한다. ingest 적재와 재조립이 같은 방식으로 증감 줄 수를 센다. `OperationApplier`에 있던 `countLines`를 옮긴 것이며 계산 방식은 그대로다.

**멱등**

- 작업이 이미 확정 상태면 `payload_hash`를 비교해 같으면 기존 결과를, 다르면 409를 돌려준다. 기존 ingest와 같다.
- `rebuilding` 중 같은 페이지가 다시 오면 `content_hash` 일치로 걸러 새 버전을 만들지 않는다. 재조립 본문은 복구 시점의 본문과 다르므로 해시가 같다는 것은 이미 반영했다는 뜻이다.
- 실패 기록은 `(operation_id, page_id, rebuild_failed)` 존재 여부로 거른다. 실패에는 대조할 해시가 없다.
- 재조립을 기다리는 상태(`rebuilding`·`notify_pending`)가 아니면 422로 거절한다.

**검증**

- `RestoreRebuildApplierTest` 8개를 추가했다. 지시서 기여 수 사용, `rebuilt` 기록, 실패 기록, 전량 성공 확정, 동일 내용 재전송, 중복 실패 기록, 미요청 페이지 거절, 되돌리기로 끝낸 페이지 거절이다. 지시서는 실제와 같이 JSON 직렬화·역직렬화를 거쳐 검증했다.
- `OperationIngestServiceTest`에 재조립 분기 라우팅·상태 검증·해시 불일치 3개를 더해 10개가 됐다.
- Backend 전체 `./gradlew test`가 통과했다.

**남은 주의사항**

- llmPipeline이 아직 이 payload를 보내지 않는다. mock payload로만 검증했다.
- 재조립 실패 페이지는 복구 직전 내용 그대로 남는다. 남은 기여와 본문이 어긋난 상태이며 다음 lint가 정리해야 한다.

### feat: 이 시점으로 되돌리기 실행 추가

**변경된 것**

- `POST /api/workspaces/{ws}/ai-operation-logs/{operation_id}/restore`를 추가한다. body는 미리보기 응답의 `preview_token` 하나다. 미리보기와 같은 계산을 다시 하고 결과를 Wiki에 반영한다.
- `RestoreExecuteService` — 되돌릴 수 있는 작업인지 확인(`ingest`·`lint`만), `preview_token` 재검증, 계획 계산, 반영, llmPipeline 통지까지의 순서를 맡는다.
- `RestoreApplier` — 반영을 한 트랜잭션으로 처리한다. 교착을 피하려고 `page_id` 오름차순으로 `FOR UPDATE` 잠금을 잡고, 제외 대상 기여를 `active=false`로 끈 뒤 페이지마다 복원·삭제·위임으로 갈린다.
- `RestoreOperationLifecycle` — 복구 작업의 시작(`applying`)과 종료를 각각 별도 트랜잭션으로 커밋한다. 반영 중 실패해도 `applying`으로 남아 같은 `restore_manifest`로 재시도할 수 있다.
- `PipelineRestoreRequester` — `POST {app.wiki-restore.endpoint}`로 조립 지시서를 보낸다. 재작성 대상, 되돌린 페이지, 삭제된 페이지를 함께 싣는다.
- `WikiPageStatus.deleted`와 `V17__add_wiki_page_deleted_status.sql`을 추가한다. `wiki_pages.status` CHECK 제약에 `deleted`를 넣는다.
- `WikiPageRepository.findByIdForUpdate`(비관적 쓰기 잠금)와 `DocumentWikiLinkRepository.deleteByIdWikiPageId`를 추가한다.
- `RestorePreviewStaleException`을 409 `RESTORE_PREVIEW_STALE`로 매핑한다.
- `app.wiki-restore.endpoint`·`app.wiki-restore.timeout-seconds` 설정을 추가한다.

**설계 확정**

- **ingest 되돌리기는 Wiki만 되돌린다.** ingest는 원문 문서를 읽기만 하고 바꾸지 않으므로 되돌릴 문서 본문이 없다. 문서 본문 복원은 `document_edit`의 몫이라 여기서 뺐다.
- **Backend는 저장소에 쓰지 않는다.** 되돌릴 revision의 object가 불변 key로 이미 있으므로 같은 본문을 다시 쓰지 않고 `markdown_uri`를 그 key로 옮긴다.
- 삭제는 소프트 삭제다. 하드 삭제하면 `wiki_page_versions`·`wiki_page_contributions`가 CASCADE로 사라져 되살릴 수 없다.
- 기여 행은 지우지 않고 끈다. 지우면 연속 복구에서 이전에 제외한 기여가 되살아난다.
- 통지 실패는 예외를 올리지 않는다. 복구는 이미 반영됐고 재작성만 보류되므로 `notify_pending`으로 남긴다.

**검증**

- `RestoreExecuteServiceTest` 7개를 추가했다. 토큰 불일치 409, 되돌릴 수 없는 작업 유형, 빈 계획, 재작성 없음→`succeeded`, 재작성 있음→`rebuilding`, 통지 실패→`notify_pending`, 콜백 주소 전달이다.
- Backend 전체 `./gradlew test`가 통과했다.

**남은 주의사항**

- llmPipeline `POST /wiki/restore-runs`가 아직 없다. 재작성 대상이 있는 복구는 지금은 `notify_pending`에서 멈춘다.
- `notify_pending` 자동 재전송이 없다. 재시도는 수동이다.
- `applying` 상태 동안 같은 문서의 새 ingest를 막는 처리가 아직 없다.
- 행 잠금 동작은 단위 테스트로 검증할 수 없다. Testcontainers 통합 테스트가 필요하다.

### feat: AI 작업 로그 조회 API 추가

**변경된 것**

- `GET /api/workspaces/{ws}/ai-operation-logs`를 추가한다. 최신순 커서 페이지네이션이며 `type`·`status`로 거를 수 있다. 로그 테이블만 읽고 diff를 계산하지 않는다. 기본 20건, 최대 100건이다.
- `GET .../ai-operation-logs/{operation_id}`를 추가한다. 그 작업이 바꾼 리소스를 함께 반환한다. 줄 수는 저장된 값이라 계산이 없다.
- `GET .../ai-operation-logs/{operation_id}/restore-preview`를 추가한다. 이미 만들어 둔 미리보기 서비스에 엔드포인트를 얹었다.
- `GET .../wiki/pages/{page_id}/diff?from=&to=`를 추가한다. 두 revision 본문을 읽어 요청 시점에 계산한다.
- `MarkdownDiffService`에 리소스 중립 `diff()`를 추가하고 기존 `compare()`는 어댑터로 남긴다. 문서와 Wiki가 같은 계산기를 쓰되 응답 타입만 다르다. **기존 `/documents/{id}/diff` 응답 스키마는 바뀌지 않는다.**
- `WikiPageVersionNotFoundException`을 404 `WIKI_PAGE_VERSION_NOT_FOUND`로 매핑한다.

**복구 범위 선택 제거**

- 복구를 "이 시점으로 되돌리기" 하나로 고정하고 `mode` 파라미터를 없앤다. 기준 작업 이후 같은 문서의 작업이 전부 취소되며, 그사이에 만들어진 source page·concept page는 받치는 기여가 사라져 삭제된다.
- lint는 `target_document_id`가 없어 문서 범위를 만들 수 없다. 그 작업 하나만 취소하도록 내부에서 처리하며 사용자에게 선택지를 노출하지 않는다.
- `RestoreMode`를 삭제하고 `preview_token` 서명 대상에서도 뺐다.

**검증**

- 실제 데이터를 넣고 Swagger로 목록·필터·상세·미리보기·diff를 호출해 확인했다. 다중 버전 시나리오(`A1 A2 A3 B A4`)에서 A3 지목 시 A4가 만든 페이지가 삭제되고, A2 지목 시 A3·A4가 만든 페이지가 대상이 되며 문서 B가 보탠 페이지는 재작성되는 것을 확인했다.
- `RestoreScopeResolverTest` 4개를 추가했다. 이후 작업 수집, 기준 작업 보존, 빈 범위, lint 단독 취소다.
- Backend 전체 `./gradlew test`가 통과했다.

**남은 주의사항**

- 목록 조회가 `(:cursor IS NULL OR ...)` 형태에서 500으로 실패했다. Postgres가 timestamp 파라미터의 타입을 추론하지 못한다. 첫 페이지에 `null` 대신 먼 미래 값을 넘기도록 고쳤다. 단위 테스트로는 잡히지 않는 종류라 통합 테스트가 필요하다.
- 로그가 쌓이려면 프론트엔드가 `apply_operation_id`를 전달하거나 `ingest-logging-enabled`를 켜고 llmPipeline이 콜백을 보내야 한다.

### feat: ingest 결과 콜백 수신 추가

**변경된 것**

- `POST /api/ai-operations/{operation_id}/result`를 추가한다. llmPipeline이 ingest를 마치고 호출하는 내부 콜백이며 사용자 인증 대상이 아니다. `X-Internal-Token` 헤더를 상수 시간 비교로 검증하고, **통과하기 전에는 저장소 객체를 읽지 않는다.**
- `IngestOperationStarter`가 llmPipeline 호출 **전에** `processing` 로그를 별도 트랜잭션으로 커밋한다. 콜백이 도착했을 때 대조할 등록값이 없으면 결과를 받아들일 수 없다. 호출 자체가 실패하면 `failed`로 확정한다.
- `OperationIngestService`가 멱등·정합성·읽기를 맡는다. 같은 `payload_hash` 재전송은 기존 결과를 200으로 돌려주고, 같은 작업에 다른 payload가 오면 409다. 콜백이 보낸 workspace·user·document는 권한 근거가 아니라 등록값과의 대조용이다.
- `OperationApplier`가 적재를 한 트랜잭션으로 처리한다. 페이지마다 revision을 채번하고 기여를 먼저 넣어 그 시점 기여 수를 버전 행에 담는다. 검증을 마친 뒤에만 `wiki_pages.markdown_uri`를 옮긴다.
- `WikiObjectReader`가 key 검증과 읽기를 맡는다. bucket은 환경 설정으로 고정하고 `wiki/{ws}/pages/{page}/ops/{op}.md`와 정확히 일치할 때만 읽는다.
- `app.aihistory.ingest-logging-enabled` 플래그를 추가하고 기본값을 끈다.

**검증**

- `OperationIngestServiceTest` 7개를 mock payload로 검증했다. 정상 수신, 해시 불일치 422, 미등록 404, 경로·본문 id 불일치, 타 워크스페이스 위조, 재전송 200, 다른 payload 409다.
- Backend 전체 `./gradlew test`가 통과했다.

**남은 주의사항**

- **플래그가 꺼져 있어야 한다.** llmPipeline의 `PipelineRunIn`이 `extra="forbid"`라 스키마가 준비되기 전에 `operation_id`를 보내면 ingest가 422로 깨진다. 플래그가 꺼져 있으면 해당 필드가 `null`이라 직렬화에서 빠져 기존 동작이 그대로다.
- `@Transactional`을 같은 클래스의 `protected` 메서드에 두면 자기 호출이라 프록시를 타지 않는다. 그래서 적재를 `OperationApplier`로 분리했다.
- 아직 `SELECT ... FOR UPDATE` 행 잠금이 없어 같은 페이지에 동시 콜백이 오면 revision이 겹칠 수 있다. 통합 테스트와 함께 이어서 붙인다.
- lint 확장은 이번 범위에서 분리했다.

### feat: 문서 AI 편집 로그 기록 추가

**변경된 것**

- `AgentApplyOperationStore`를 추가한다. `POST /agent/turns`가 편집안마다 일회용 적용 표를 발급하고, 저장 요청이 그 표를 돌려주면 AI 작업으로 기록한다. TTL 30분이며 메모리에만 둔다.
- `AgentTurnResponse`에 `applyOperationId`를 추가한다. 프론트엔드는 이 값을 `PUT /documents/{id}/content`의 `apply_operation_id` part로 전달해야 AI 편집 로그가 남는다.
- `DocumentService.saveContent`에 `applyOperationId`를 받는 오버로드를 추가한다. 표 검증에 성공한 경우에만 `ai_operation_logs`·`ai_operation_changes`를 문서 저장과 같은 트랜잭션에서 기록하고 `document_content_versions.operation_id`를 연결한다.
- `base_version` 불일치는 본 트랜잭션이 롤백되므로 `OperationRecorder.recordConflict`를 `REQUIRES_NEW`로 분리해 `conflict` 로그를 남긴다.
- 줄 수 계산이 실패해도 저장을 막지 않는다. 큰 문서는 diff 계산이 거부될 수 있는데 로그 때문에 사용자 저장이 실패해서는 안 된다.

**검증**

- `AgentApplyOperationStoreTest` 5개로 재사용·위조·타 사용자·타 문서 표가 통과하지 못하는 것을 확인했다.
- Backend 전체 `./gradlew test`가 통과했다.

**남은 주의사항**

- `source=agent` 문자열만으로는 AI 작업 여부를 판단하지 않는다. 그 값은 클라이언트가 임의로 넣을 수 있어 수동 편집을 AI 작업으로 위장할 수 있다. 기존 `source` 파라미터는 그대로 두되 기록 판단에는 쓰지 않는다.
- 표를 소비하는 시점은 저장 성공 직후다. 검증 단계에서 소비하면 `base_version` 충돌 시 표가 사라져 재시도할 수 없다.
- 프론트엔드가 `apply_operation_id`를 전달하기 전까지 AI 편집 로그는 쌓이지 않는다. 필드 추가는 하위 호환이라 기존 동작에는 영향이 없다.
- `saveContent`의 기록 분기는 DB가 필요해 아직 통합 테스트로 덮지 못했다.

### feat: AI 작업 복구 판정 추가

**변경된 것**

- `RestorePlanner`를 추가한다. 기여 명단만 보고 페이지마다 삭제·복원·재조립을 가른다. 본문을 읽지 않는 순수 계산이라 미리보기에 저장소 접근이 없다.
- 판정 기준은 세 가지다. 받치는 기여가 하나도 남지 않으면 삭제, 남길 기여의 마지막 revision이 담고 있던 기여가 남길 집합과 정확히 같으면 그 스냅샷으로 복원, 그 외에는 llmPipeline 재조립이다.
- `RestoreMode`를 추가한다. `since`(기본)는 기준 작업 이후 같은 문서의 작업을 전부 제외하고, `single`은 하나만, `document`는 그 문서 전부를 제외한다. 로그 목록에서 한 시점을 골라 되돌리는 조작이 가장 흔해 `since`를 기본값으로 둔다.
- 판정기는 활성 기여만이 아니라 **비활성 기여까지 입력받는다.** 복원 목적지가 유효한지 판단하려면 그 revision이 담고 있던 기여를 알아야 하는데, 이전 복구로 꺼진 기여가 그 안에 들어 있을 수 있다.

**검증**

- 설계 문서 §5.4의 시나리오를 `RestorePlannerTest` 14개로 고정했다. 기본 취소 5개, 연속 복구 3개, `mode=since` 2개, 경계 4개다.
- DB 없이 도는 순수 단위 테스트라 Testcontainers가 필요 없다.

**남은 주의사항**

- 복원 목적지를 처음에 `제외 대상 중 가장 이른 sequence_revision - 1`로 계산했는데, 연속 복구 시나리오에서 이미 비활성화한 기여가 담긴 revision을 고르는 버그가 있었다. 남길 기여의 마지막 revision을 쓰되 그 시점 기여 집합이 남길 집합과 같은지 확인하는 방식으로 고쳤다. lint가 기여 없이 revision만 올린 구간도 이 방식으로 함께 처리된다.

### feat: 복구 미리보기 서비스 추가

**변경된 것**

- `RestoreScopeResolver`를 추가한다. 기준 작업과 `mode`로 제외할 작업 집합을 정한다. `since`는 기준 작업 이후만, `document`는 기준 작업을 포함한 그 문서 작업 전부를 제외한다. lint와 restore는 기여를 만들지 않아 ingest만 모은다.
- `PreviewTokenSigner`를 추가한다. 미리보기 시점의 상태를 HMAC-SHA256으로 서명하고, 실행 시 상태를 다시 계산해 서명을 대조한다. 토큰에 상태를 담지 않아 별도 저장이 필요 없다. 서명 대상에 기여의 활성 여부까지 넣어 그사이 다른 복구가 끼어든 것도 잡는다.
- `RestorePreviewService`를 추가한다. 워크스페이스 멤버십을 확인하고 제외 집합·기여 명단·판정·토큰을 엮어 미리보기를 만든다. 본문을 읽지 않아 저장소 접근이 없다.
- `WikiPageContributionRepository`의 페이지별 조회를 전체 기여(활성·비활성)로 바꾼다. 복원 목적지 유효성을 보려면 그 revision이 담고 있던 기여를 알아야 한다.
- 예외 2건을 전역 핸들러에 등록한다. `OperationNotFoundException`은 404 `AI_OPERATION_NOT_FOUND`, `InvalidRestoreRequestException`은 400 `INVALID_RESTORE_REQUEST`다. 후자는 `target_document_id`가 없는 lint 작업에 `since`·`document`를 쓰려 할 때 난다.

**검증**

- `RestorePlannerTest` 14개가 계속 통과한다.
- 서명 키는 기동 시 `SecureRandom`으로 만든다. 미리보기 토큰은 수명이 짧고 재시작 시 무효여도 무방하다. 다중 인스턴스로 확장할 때 공유 시크릿으로 바꾼다.

**남은 주의사항**

- 미리보기 엔드포인트는 아직 없다. 조회 API 작업에서 다른 엔드포인트와 함께 붙인다.
- `RestoreScopeResolver`와 `RestorePreviewService`의 통합 테스트는 실제 데이터가 쌓이는 콜백 수신 작업 이후에 붙인다.

### feat: AI 작업 로그 스키마 추가

**변경된 것**

- `ai_operation_logs`를 추가한다. 문서 AI 편집·Wiki ingest·lint·복구를 한 테이블에 기록한다. `operation_id`가 PK이며 작업 등록 중복을 막는다. `target_document_id`는 복구 대상 선정의 근거이고, `restore_manifest`와 `payload_hash`는 각각 재조립 결과 수신과 콜백 재전송 판별에 쓴다.
- `ai_operation_changes`를 추가한다. 작업 1회가 바꾼 리소스를 1행씩 남기는 감사 기록이다. `(operation_id, resource_type, resource_id, change_type)` UNIQUE가 콜백 재전송 시 중복을 막는 최종 방어선이다. diff 본문은 저장하지 않고 줄 수만 남긴다.
- `wiki_page_versions`를 추가한다. Wiki 페이지 본문 이력이며 `revision`은 단조 증가한다. 복구도 새 revision을 append한다. `markdown_key`에 불변 object key를 함께 남겨 복구가 저장소에 쓰지 않고 옛 object를 재사용한다.
- `wiki_page_contributions`를 추가한다. "지금 어느 문서가 이 페이지를 받치고 있나"의 현재 상태이며 복구 판정의 근거다. 복구는 행을 지우지 않고 `active`를 끄고 `deactivated_by`를 남긴다. 지우면 연속 복구에서 제외한 기여가 다시 살아난다.
- `document_content_versions.operation_id`를 추가한다. 그 버전을 만든 AI 작업을 가리키며 수동 편집이면 NULL이다.
- `wiki_pages`는 변경하지 않는다. revision 채번은 `max(revision)`으로 얻고, 재조립 실패는 `ai_operation_changes.rebuild_failed`로 남긴다.

**검증**

- Flyway V15·V16 적용과 `Successfully validated 16 migrations`를 확인했다.
- `spring.jpa.hibernate.ddl-auto=validate` 상태에서 애플리케이션이 정상 기동해 엔티티와 스키마 일치를 확인했다.

**남은 주의사항**

- 아직 어떤 서비스도 이 테이블을 쓰지 않는다. 기록·조회·복구는 후속 작업에서 붙인다.
- 설계와 작업 계획은 `docs/design/ai-operation-log.md`와 `ai-operation-log-tasks.md`를 따른다.
---

## 2026-07-30

### fix: Markdown 버전 diff 계산에 크기 가드 추가

**변경된 것**

- 두 버전의 본문이 동일하면 diff 계산 전에 빈 결과를 반환한다. 빈 본문끼리 비교할 때 Myers 배열이 범위를 벗어나 500이 나던 문제를 막는다.
- Myers trace의 예상 메모리가 16MB를 넘으면 `MarkdownDiffTooLargeException`으로 계산을 중단하고 422 `MARKDOWN_DIFF_TOO_LARGE`를 반환한다. 큰 문서 비교로 서버 메모리가 무제한 늘어나는 것을 막는다.

**검증**

- 빈 본문 비교와 대용량 거부를 `MarkdownDiffServiceTest`로, 422 응답 계약을 `DocumentControllerTest`로 검증했다.
- Backend 전체 `./gradlew test`가 통과했다.

---

## 2026-07-29

### docs: Swagger 요청 기본값 추가

**변경된 것**

- 로그인 요청 body의 기본값을 `user@example.com`, `stringst`로 제공한다.
- 모든 `workspace_id` parameter의 예시와 기본값을 `ws_9d47a0e9a6324341b47562553b75f92a`로 통일한다.

**검증**

- OpenAPI schema와 parameter customizer 테스트로 example과 default 반영을 검증했다.

### feat: GitHub 스타일 Markdown 버전 diff 추가

**변경된 것**

- 수동 저장, AI 편집 적용, 복원으로 본문이 변경될 때 변경 전·후 전체 Markdown 스냅샷을 저장하도록 버전 이력을 보강했다.
- `GET /api/workspaces/{workspace_id}/documents/{document_id}/diff`를 추가해 두 버전의 추가·삭제 줄과 GitHub 스타일 hunk를 반환한다.
- diff 응답은 각 줄의 `CONTEXT`, `DELETE`, `ADD` 유형과 이전·이후 줄 번호를 제공한다.

**검증**

- diff 알고리즘, 저장·복원 스냅샷, HTTP 응답 계약을 단위·컨트롤러 테스트로 검증했다.
- Backend 전체 `./gradlew test`가 통과했다.
- 변경 전 스냅샷이 없는 기존 버전은 소급 비교할 수 없다.

---

## 2026-07-28

### fix: Markdown 업로드를 저장 전용으로 변경

**변경된 것**

- Markdown 업로드가 처리 큐를 자동 등록하지 않고 원본과 편집 상태만 `uploaded` 상태로 저장하도록 변경했다.
- 업로드한 Markdown은 사용자가 `POST /documents/{document_id}/ingest`를 호출할 때만 Wiki pipeline 처리를 시작한다.
- PDF 등 읽기 전용 원본의 기존 저장 전용 동작은 유지한다.

**검증**

- Markdown·PDF 업로드 상태와 처리 큐 미등록, 명시적 재ingest를 문서 서비스·컨트롤러 테스트로 검증했다.

### fix: 채팅 세션을 워크스페이스 멤버별로 격리

**변경된 것**

- 채팅 세션 목록과 단건 소유권 검증에 `user_id` 조건을 추가해 같은 워크스페이스의 다른 멤버 세션이 노출·조회·삭제되지 않도록 수정했다.
- 세션 최대 10개 제한을 워크스페이스 전체가 아닌 워크스페이스 멤버별로 적용했다.
- Query와 Wiki export가 공통으로 사용하는 `verifyOwnedSession`에도 동일한 세션 소유자 검증을 적용했다.

**검증**

- 전체 chat 테스트가 통과했다.
- 다중 세션 목록·전환 Frontend UI는 `docs/issue/frontend/2026-07-23.md`의 미해결 작업으로 유지한다.

### fix: 채팅 편입 문서를 워크스페이스 문서 목록에 노출

**변경된 것**

- `origin='chat_export'` 문서를 평면 문서 목록, 폴더 트리, 이름 검색 결과에 포함하도록 조회
  조건을 통일했다.
- 채팅 편입 API가 MinIO와 `documents` 테이블에 저장한 Markdown을 프론트가 목록 갱신 후
  실제 워크스페이스 문서로 열 수 있다.

**검증**

- AI 편집의 `source=agent` 저장 스냅샷 서비스 테스트가 통과했다.
- 목록 조회 회귀 테스트는 `chat_export` 포함 기대값으로 갱신했다. 로컬 Colima 환경에서는
  Testcontainers PostgreSQL 공개 포트 연결 거부로 해당 통합 테스트 실행이 환경 단계에서
  중단됐고, production 코드와 테스트 코드는 Java 21로 컴파일됐다.
- 로컬 전체 스택에서 `source=agent` 저장의 `document_content_versions` 생성과 채팅 편입
  문서의 MinIO `source_uri`, `documents(origin='chat_export')`, 목록 노출을 확인했다.

### refactor: Wiki 페이지 이름 변경을 llmPipeline에 위임

**변경된 것**

- 외부 Wiki 페이지 이름 변경 API는 워크스페이스 멤버십만 검증하고 llmPipeline의 `PATCH /wiki/pages/{wiki_page_id}/rename`을 호출하도록 변경했다.
- 이름 변경 경로에서 Backend의 `wiki_pages` 조회·수정을 제거하고, llmPipeline의 `400`·`404`·`409`·`422` 응답을 보존한다.
- pipeline endpoint·timeout 설정과 연결 실패 시 `503 WIKI_PAGE_PIPELINE_UNAVAILABLE` 응답을 추가했다.
- llmPipeline 구현 계약과 완료 조건은 `docs/issue/ai/2026-07-28.md`에 기록했다.

**검증**

- requester JSON 계약·오류 매핑과 멤버십 선검증·`WikiPageRepository` 미접근 테스트가 통과했다.
- llmPipeline 내부 API 구현 전까지 실제 이름 변경 요청은 `503`으로 실패한다.

### feat: 전체 문서 트리 조회 API 추가

**변경된 것**

- `GET /api/workspaces/{workspace_id}/document-tree`를 추가해 활성 폴더와 문서를 전체 중첩 구조로 한 번에 조회할 수 있게 했다.
- 전체 트리는 폴더·문서를 같은 부모의 `sort_order`, ID 순으로 정렬하고 소프트 삭제된 항목을 제외한다.
- `/navigation`, `/folders/{folder_id}/children`, `/document-tree` 응답에 `current_version`을 포함해 프론트가 이름 변경·이동·삭제 요청의 `base_version`으로 사용할 수 있게 했다.

**검증**

- document-tree·navigation·folder controller 테스트와 `FolderServiceIntegrationTest`가 통과했다.
- 실제 API 응답의 중첩 구조와 `current_version`, Swagger endpoint 등록을 확인했다.

### fix: 워크스페이스 조회·소유자 권한 판정 오류 수정

**변경된 것**

- 워크스페이스 목록 조회의 불필요한 `PESSIMISTIC_WRITE`를 제거해 트랜잭션 없는 조회가 `500`으로 실패하던 문제를 수정했다.
- `workspace_members.role`을 `WorkspaceRole` enum(`OWNER`, `MEMBER`)으로 전환하고, 기존 lowercase 데이터를 변환하는 Flyway `V14`와 허용값 `CHECK` 제약을 추가했다.
- 이름 변경·삭제·복구·휴지통과 폴더 owner 판정이 동일한 enum 값을 사용하도록 통일했다.
- 워크스페이스 삭제·복구의 `Idempotency-Key`에 Swagger UUID 예시를 추가했다.

**검증**

- workspace·folder 관련 테스트와 `compileJava`가 통과했다.
- 실제 API에서 워크스페이스 목록 조회와 이름 변경이 `200`으로 응답하고, 기존 role이 `OWNER`로 변환되며 DB 제약이 생성되는 것을 확인했다.

---

## 2026-07-27

> `feat/agent-turn-base-version` 브랜치에서 dev와 중복되지 않는 고유 기능만 최신 `dev` 위에 재적용한 묶음입니다. 폴더 트리·wiki-schema·wiki-maintenance는 dev 구현을 사용합니다.

### feat: 문서 편집 잠금(활성 편집 추적) 추가

**변경된 것**

- 한 문서를 동시에 두 사람이 편집하지 못하게 lease(TTL + heartbeat) 기반 편집 잠금을 추가했다. 테이블 `document_edit_locks`(마이그레이션 `V13`).
- `POST/DELETE /documents/{id}/edit-lock`(획득/해제), `POST /documents/{id}/edit-lock/heartbeat`(연장). 획득은 원자적 조건부 upsert(비었거나 만료됐거나 본인 보유일 때만 성립).
- 쓰기 계열(`saveContent`·`agent/turn`·버전 복원·재ingest)은 **다른 사용자가 유효한 잠금 보유 중이면 `423 DOCUMENT_EDIT_LOCKED`** 로 차단한다. 잠금이 없거나 만료됐거나 본인 보유면 통과(잠금 강제 아님, 비파괴적).
- `GET /documents/{id}` 응답에 `edit_lock` 필드(보유자·표시 이름·만료 시각) 추가. 열람은 누구나 가능(읽기 전용), 보이는 내용은 마지막 저장본.
- heartbeat 상실 시 `409 EDIT_LOCK_LOST`. TTL 기본 45초(`app.document.edit-lock.ttl-seconds`).
- 설계: `docs/design/document-edit-lock.md`, 프론트 계약: `docs/issue/frontend/2026-07-27.md`.

**검증**: `DocumentEditLockServiceTest`(획득 self/other·heartbeat 상실·requireWritable·getStatus) 통과.

### feat: 운영 이메일 인증 SMTP 발송 추가 (트랜잭션 분리·timeout 포함)

**변경된 것**

- `spring.mail.host`가 설정되면 실제 SMTP 발송(`SmtpEmailVerificationSender`), 없으면 dev 로그 stub로 동작하도록 `EmailSenderConfig`로 분기한다.
- 인증번호 발송은 DB 커밋 후 트랜잭션 밖에서 수행하고(외부 메일 왕복 동안 커넥션 점유 방지), SMTP connection/read/write timeout을 적용한다.

**검증**: `SmtpEmailVerificationSenderTest`, `EmailVerificationServiceTest` 통과.

### feat: Agent turn 오래된 baseVersion을 pipeline 호출 전 409로 거절

**변경된 것**

- `POST /agent/turn`에서 요청 `base_version`이 문서 현재 version과 다르면 pipeline 호출 전에 `DOCUMENT_VERSION_CONFLICT`(409)로 거절해, 오래된 스냅샷으로 LLM을 낭비하지 않는다.

### feat: 편집본 재ingest API 추가 (POST /documents/{id}/ingest)

**변경된 것**

- 편집 가능 Markdown 문서를 최신 편집본으로 다시 Wiki 파이프라인에 넣는다. DB 편집본을 MinIO 원본으로 승격한 뒤 `processing`으로 되돌리고 처리 큐에 재등록한다.
- 이미 처리 중이면 `DOCUMENT_ALREADY_PROCESSING`(409). 편집 가능(EDITABLE) 문서만 대상.

### feat: 문서 콘텐츠 버전 이력·롤백 추가 (AI 편집 스냅샷)

**변경된 것**

- `document_content_versions` 테이블(마이그레이션 `V12`)에 편집 가능 Markdown의 콘텐츠 스냅샷을 저장한다.
- `GET /documents/{id}/versions`(목록), `GET /documents/{id}/versions/{version}`(단건 본문), `POST /documents/{id}/versions/{version}/restore`(비파괴 복원) 추가.
- 스냅샷은 **AI 편집(`source=agent`)일 때만** 기록한다. `PUT /documents/{id}/content`에 선택적 `source` multipart part를 추가했고, `source=agent`이면 저장 성공 시 스냅샷을 남긴다. 수동 저장은 `source` 생략(스냅샷 없음).
- 복원은 대상 버전 본문을 새 version으로 저장하며(base_version 낙관적 잠금), 복원 동작 자체는 새 스냅샷을 남기지 않는다.
- 프론트 연동 계약은 `docs/issue/frontend/2026-07-27.md` 참고(코드는 이 PR에서 건드리지 않음).

---

## 2026-07-25

### feat: 폴더 하위 항목 개별 복구 (TASK-H006)

**변경된 것**

- 폴더 복구(`POST /folders/{folder_id}/restore`)를 삭제 작업(op) 전체 복구에서 **복구 대상 폴더의 하위 트리** 복구로 바꿨다. 대상 폴더와 그 하위에서 같은 삭제 작업으로 삭제된 폴더·문서만 되살린다.
- 복구 대상의 원래 부모 폴더가 아직 삭제 상태이면 최상위의 마지막에 배치하고, 살아 있으면 원래 위치로 복구한다. 삭제 작업의 최상위 폴더를 복구하면 종전처럼 하위 트리 전체가 원위치로 복구된다.
- 문서 개별 복구는 기존 `POST /documents/{document_id}/restore`가 `folder_id`를 최상위(null)로 되돌려 이미 지원한다.

**검증**

- 통합 테스트로 하위 폴더 개별 복구 시 최상위 배치(원래 부모는 삭제 유지)와 최상위 폴더 복구 시 전체 트리 원위치 복구를 검증했다.
- `./gradlew test` 전체 통과.

### feat: 폴더 트리 breadcrumb·이름 검색 추가 (TASK-H005)

**변경된 것**

- `GET /api/workspaces/{workspace_id}/navigation/breadcrumb`로 폴더 또는 문서의 최상위→현재 경로를 반환한다. `folder_id` 또는 `document_id` 중 하나만 지정하며, 문서는 상위 폴더 경로 뒤에 문서 노드를 붙인다. recursive CTE로 조상 폴더 경로를 계산한다.
- `GET /api/workspaces/{workspace_id}/navigation/search?query=`로 폴더 이름과 문서 표시 이름·파일명을 평면 검색한다. 각 결과에 항목 종류·상위 폴더 breadcrumb를 포함하고, 소프트 삭제 항목과 `chat_export` 문서는 제외한다. 본문은 검색하지 않는다.
- `folder_id`/`document_id`를 동시 지정하거나 빈 검색어는 `400 INVALID_HIERARCHY_REQUEST`, 없는 항목은 `404 HIERARCHY_ITEM_NOT_FOUND`다.

**검증**

- 통합 테스트로 중첩 폴더·문서의 root→현재 경로와 폴더·문서 혼합 검색·breadcrumb를 검증했고, 컨트롤러 테스트로 endpoint·인증을 검증했다.
- `./gradlew test` 전체 통과.

**남은 주의사항**

- 검색 결과별 breadcrumb를 항목마다 CTE로 계산하므로, 대량 결과의 성능 최적화(cursor 페이지네이션 포함)는 후속 과제다.

### feat: 문서 생성·업로드에 folder_id 위치 지정 (TASK-H004)

**변경된 것**

- Markdown 생성(`POST /documents/markdown`)과 업로드(`POST /documents`)가 선택적 `folder_id`를 받아 문서를 해당 폴더 안에 생성한다. Markdown 생성은 요청 body의 `folder_id`, 업로드는 multipart `folder_id` part로 지정한다.
- `folder_id`를 지정하면 폴더·문서 혼합 순서의 마지막에 배치하고, 생략하면 기존처럼 최상위에 배치한다.
- 존재하지 않거나 다른 workspace의 `folder_id`는 `404 HIERARCHY_ITEM_NOT_FOUND`로 거절한다.
- `Document.place(folderId, sortOrder)`를 추가하고 `DocumentService`가 폴더 존재 검증·혼합 배치를 수행하도록 `FolderRepository`를 주입했다. 복제는 원본과 같은 폴더 유지, 초기 노트는 최상위 생성을 유지한다.

**검증**

- 통합 테스트로 선택한 폴더에 문서 생성·배치와 없는 폴더 `404`를 검증했고, 컨트롤러 테스트로 업로드 `folder_id` part 전달을 검증했다.
- `./gradlew test` 전체 통과.

**남은 주의사항**

- 복제 대상 폴더 재지정과 원본 변환 편집본의 폴더 배치(변환 pipeline 연동 이후)는 후속 구현한다.

### feat: 폴더 트리 최상위 조회·삭제·복구 API 추가 (TASK-H005/H006)

**변경된 것**

- `GET /api/workspaces/{workspace_id}/navigation`으로 폴더 트리 최상위 폴더·문서를 혼합 순서로 조회한다(`FolderService.children(..., null)` 재사용). 프론트가 전체 트리를 최상위부터 지연 조회할 수 있다.
- `DELETE /api/workspaces/{workspace_id}/folders/{folder_id}`로 폴더 트리를 소프트 삭제한다. 루트 폴더와 하위 폴더·포함 문서를 recursive CTE로 같은 `delete_operation_id`로 소프트 삭제하고, 루트는 `current_version` 낙관적 잠금으로 충돌을 검사한다.
- 빈 폴더는 모든 워크스페이스 멤버가 삭제할 수 있고, 내용이 있는 폴더는 워크스페이스 소유자만 삭제할 수 있다(`403 HIERARCHY_WRITE_FORBIDDEN`).
- `POST /api/workspaces/{workspace_id}/folders/{folder_id}/restore`로 같은 `delete_operation_id`의 폴더 트리를 원래 부모·순서로 복구한다. 소프트 삭제가 `parent_folder_id`·`sort_order`를 보존하므로 복구 시 원위치가 유지된다.
- 삭제·복구는 `Idempotency-Key`로 재요청을 no-op 처리한다.

**검증**

- 통합 테스트(Testcontainers)로 하위 트리 전체 소프트 삭제(폴더·문서 동일 작업 ID), 원래 부모 아래 복구, 내용 있는 폴더의 비소유자 삭제 `403`, 빈 폴더의 멤버 삭제 허용을 검증했다. 컨트롤러 테스트로 navigation·삭제·복구 endpoint와 인증을 검증했다.
- `./gradlew test` 전체 통과.

**남은 주의사항**

- breadcrumb와 이름 검색(TASK-H005 잔여), 하위 항목 개별 복구, 삭제된 부모 아래로의 복구 회피는 후속 구현한다.
- frontend가 `localStorage` 대신 navigation·폴더 API로 트리를 복원하는 재배선은 TASK-H007(별도 frontend 작업)이다.

### feat: 폴더·문서 이동 시 형제 위치(position) 지정 지원

**변경된 것**

- 폴더·문서 이동 API(`PATCH …/folders/{id}/position`, `PATCH …/documents/{id}/position`)에 `position`을 추가했다. 대상 부모의 폴더·문서 혼합 목록에서 0-based 목표 인덱스이며, 생략하면 기존처럼 맨 뒤에 배치한다.
- 이동 시 대상 부모의 형제(폴더·문서)를 비관적 잠금으로 잠그고 `sort_order`를 재배열하는 `SiblingReorderer`를 추가해 폴더 이동과 문서 이동이 공유한다.
- 이동 대상 항목만 `current_version`을 검사·증가시키고, 나머지 형제는 순서만 조정한다. 범위를 벗어난 `position`은 목록 끝으로 clamp한다.
- TASK-H002·H003에서 "이동 시 대상 부모의 마지막에만 배치"하던 제약을 해소하고 SDD `REQ-H005`의 "대상 형제 위치"를 구현했다.

**검증**

- 단위·통합 테스트로 폴더를 지정 인덱스로 이동, 문서를 폴더 사이 위치로 이동, 혼합 `sort_order` 재배열을 검증했다.
- `./gradlew test` 전체 통과.

### feat: 문서 이동·정렬 API 추가 (TASK-H003)

**변경된 것**

- `PATCH /api/workspaces/{workspace_id}/documents/{document_id}/position`로 문서를 다른 폴더 또는 최상위로 이동한다. 워크스페이스 멤버는 소유자가 아니어도 읽기 가능한 문서를 이동할 수 있다.
- 이동한 문서는 대상 폴더의 폴더·문서 혼합 순서 마지막에 배치한다.
- `documents.current_version` 낙관적 잠금으로 오래된 이동을 `409 HIERARCHY_VERSION_CONFLICT`로 거절하고, `Idempotency-Key`로 재요청을 no-op 처리한다.
- 대상 `folder_id`가 없는 폴더면 `404 HIERARCHY_ITEM_NOT_FOUND`다. `folder_id`는 UUID이므로 문서 id처럼 UUID가 아닌 값을 부모로 지정하면 역직렬화 단계에서 `400`이 된다(문서는 부모가 될 수 없음).
- `DocumentController`/`DocumentService`를 건드리지 않도록 `DocumentPositionController`·`DocumentPlacementService`로 분리하고 H002의 `IdempotencyService`와 혼합 정렬을 재사용했다.

**검증**

- 단위(`DocumentPlacementServiceTest`)·컨트롤러(`DocumentPositionControllerTest`)·통합(`FolderServiceIntegrationTest`) 테스트로 최상위↔폴더 이동, 문서를 부모로 지정 시 400, 버전 충돌 409, 멱등 재요청을 검증했다.
- `./gradlew test` 전체 통과.

**남은 주의사항**

- 형제 사이 임의 위치(index) 재정렬은 아직 지원하지 않고 대상 폴더의 마지막에 배치한다.
- 최상위 navigation·breadcrumb·검색(TASK-H005), 계층 삭제·복구(TASK-H006)는 후속 구현한다.

### feat: 폴더 생성·이름변경·이동 API 추가 (TASK-H002)

**변경된 것**

- 파일탐색기식 폴더 트리의 폴더 조작 API를 추가했다.
  - `POST /api/workspaces/{workspace_id}/folders` — 폴더 생성(최상위 또는 상위 폴더 아래, 형제 마지막에 배치)
  - `PATCH …/folders/{folder_id}` — 폴더 이름 변경(`base_version` 낙관적 잠금)
  - `PATCH …/folders/{folder_id}/position` — 폴더 이동(대상 부모로, 형제 마지막에 배치)
  - `GET …/folders/{folder_id}/children` — 직계 하위 폴더·문서를 공용 정렬로 혼합 조회, 폴더는 `has_children` 포함
- 폴더 이동은 recursive CTE로 대상 부모의 조상 경로를 조회해 자기 자신·하위 폴더로의 순환 이동을 `409 HIERARCHY_CYCLE`로 거절한다.
- 오래된 버전의 이름변경·이동은 `409 HIERARCHY_VERSION_CONFLICT`, 없는 폴더는 `404 HIERARCHY_ITEM_NOT_FOUND`, 잘못된 요청은 `400 INVALID_HIERARCHY_REQUEST`로 응답한다.
- 폴더·문서의 `sort_order`는 같은 부모 범위에서 하나의 혼합 순서를 공유한다(생성·이동 시 폴더와 문서 중 최대 순서 다음에 배치).
- 동일 이름 폴더 생성을 허용하고, 생성·이름변경·이동은 `Idempotency-Key`로 재요청을 no-op 처리한다.
- 여러 endpoint가 공유하는 `IdempotencyService`를 추가했다.

**검증**

- 단위(`FolderServiceTest`)·컨트롤러(`FolderControllerTest`)·통합(`FolderServiceIntegrationTest`, Testcontainers) 테스트로 동일 이름 허용, 혼합 정렬, 순환·버전 충돌, 멱등 재요청을 검증했다.
- `./gradlew test` 전체 통과.

**남은 주의사항**

- 형제 사이 임의 위치(index) 재정렬은 아직 지원하지 않고 이동 시 대상 부모의 마지막에 배치한다. 세밀한 드래그 순서는 후속 보완한다.
- 문서 이동·정렬(TASK-H003), 최상위 navigation·breadcrumb·검색(TASK-H005), 계층 삭제·복구(TASK-H006)는 후속 구현한다.

### feat: 문서 폴더 배치를 단일 folder_id로 통일 (V11)

**변경된 것**

- 문서 계층을 파일탐색기식 단일 폴더 트리로 통일하는 데이터 계층을 구현했다. 폴더가 유일한 컨테이너이고 문서는 leaf다.
- migration `V11__unify_folder_tree.sql`: `source_folders`→`folders` 일반화, `documents.source_folder_id`→`folder_id`, `parent_document_id` 컬럼·FK 제거, 역할별 배치 check 제약과 역할별 인덱스 제거, 단일 배치 인덱스 `idx_documents_folder_order` 생성.
- `SourceFolder`/`SourceFolderRepository`를 `Folder`/`FolderRepository`(table `folders`)로 일반화했다.
- `Document`의 `parentDocumentId`+`sourceFolderId`를 단일 `folderId`(UUID)로 합쳤다. EDITABLE·ORIGINAL 모두 역할과 무관하게 폴더에 배치할 수 있다.
- `DocumentDuplicateResponse`의 `parent_document_id`를 `folder_id`로 교체했다.

**검증**

- `DocumentEditingSchemaIntegrationTest`(Testcontainers)가 V1~V11 실제 적용 후 컬럼·폴더 테이블·backfill·복구·폴더 배치를 검증한다.
- `./gradlew test` 전체 통과, `flywayValidate` 통과.

**남은 주의사항**

- 폴더 CRUD·이동·정렬 API(TASK-H002·H003)와 navigation·breadcrumb·검색(TASK-H005)은 후속 구현한다.
- 역할별 root 정렬 범위는 이번 단계에서 보존했고, 폴더·문서 혼합 정렬은 이동 서비스(H002/H003)에서 구현한다.

### feat: wiki maintenance lint Java 프록시 추가

**변경된 것**

- llmPipeline `POST /wiki/maintenance/lint`를 workspace 범위 public API로 중계하는 Spring 프록시(`fruition.wikimaintenance`)를 추가했다.
- `POST /api/workspaces/{workspace_id}/wiki/maintenance/lint`에서 `workspace_id`를 path, `user_id`를 `@AuthenticationPrincipal`에서 주입한다.
- public body는 `{ materializePromotions, dryRun }`만 받고, LLM provider·model 등 pipeline 튜닝 knob은 노출하지 않는다. body를 생략하거나 옵션이 null이면 pipeline 기본값(`dry_run=true`, `materialize_promotions=false`)이 적용된다.
- workspace 멤버십을 검증해 비멤버 요청을 `WorkspaceNotFoundException`(404)으로 차단한다.
- pipeline의 400/422는 원본 detail을 보존하고, 그 외(500 포함)는 `503`(`WIKI_MAINTENANCE_PIPELINE_UNAVAILABLE`)으로 매핑한다.
- lint가 LLM을 호출하므로 프록시 read timeout 기본값을 200초로 두고 `app.wiki-maintenance.endpoint`(`WIKI_MAINTENANCE_ENDPOINT`)를 추가했다.

**검증**

- requester(user_id·workspace_id 주입, null 옵션·null 요청 시 payload 생략, 400 body 보존, 500→503), service(멤버십·위임·비멤버 차단), controller(body 있음·없음·미인증 401) 테스트를 추가했다.
- `./gradlew test` 전체가 통과했다.

**남은 주의사항**

- 프론트 maintenance UI 연동은 `docs/issue/frontend/2026-07-23.md`의 `4. wiki maintenance UI`에서 관리한다.

### feat: wiki-schema Java 프록시 추가

**변경된 것**

- llmPipeline `wiki_schema` 모듈을 workspace 범위 public API로 중계하는 Spring 프록시(`fruition.wikischema`)를 추가했다.
- `POST /api/workspaces/{workspace_id}/wiki-schema/preview`, `POST …/drafts`, `POST …/{schema_id}/activate`, `GET …/active` 4개 endpoint를 `AgentTurnController`/`PipelineAgentRequester` 패턴 그대로 구현했다.
- `drafts`는 `workspace_id`를 path에서, `user_id`를 `@AuthenticationPrincipal`에서 주입하고, `active`는 활성 스키마가 없으면 pipeline의 `null`을 그대로 반환한다.
- workspace 멤버십을 검증해 비멤버 요청을 `WorkspaceNotFoundException`(404)으로 차단한다.
- pipeline의 400/422/404는 원본 detail을 보존하고, 그 외 오류는 `503`(`WIKI_SCHEMA_PIPELINE_UNAVAILABLE`)으로 매핑한다.
- pipeline base URL 설정 `app.wiki-schema.endpoint`(`WIKI_SCHEMA_ENDPOINT`)와 timeout을 추가했다.

**검증**

- requester(snake_case 변환·null name 생략·활성 없음 시 `null` 통과·422/404 body 보존·500→503), service(멤버십·위임·비멤버 차단), controller(4개 endpoint·미인증 401·blank 입력 400) 테스트를 추가했다.
- `./gradlew test` 전체가 통과했다.

**남은 주의사항**

- 프론트 목업(`frontend/app/_lib/api/schema.ts`, `frontend/app/_components/schema/`) 교체는 별도 Frontend 작업으로 남는다.

### docs: Document API 계약과 core 추적표 정합화

**변경된 것**

- `docs/spec/api/document.md`를 현재 backend의 Markdown 생성·업로드·조회·저장·복제·소프트 삭제·내보내기 계약으로 갱신했다.
- Swagger에 직접 생성, 휴지통, 권한·version 오류와 필수 `Idempotency-Key` 설명을 보강했다.
- 비소유 workspace 멤버는 다른 소유자의 문서를 읽을 수 있지만 rename·삭제·복구할 수 없음을 서비스 테스트로 검증했다.
- Core 요구사항을 구현 테스트 또는 PDF 변환·계층 이동·이미지 ZIP 후속 task와 연결했다.

**검증**

- `./gradlew clean test flywayValidate`가 통과했다.
- 전체 backend 테스트 247개와 `git diff --check`가 통과했다.

**남은 주의사항**

- 직접 생성 Markdown의 레거시 `/original`은 현재 `404`이며 `docs/issue/backend/2026-07-25.md`에서 후속 관리한다.
- 비소유 멤버의 문서 이동 허용은 hierarchy `TASK-H008`에서 검증한다.

### feat: Markdown 원문 내보내기 추가

**변경된 것**

- `GET /api/workspaces/{workspace_id}/documents/{document_id}/export`에서 활성 workspace 멤버가 최신 Markdown 편집본을 UTF-8 `.md` 파일로 내려받을 수 있게 했다.
- 현재 표시 이름과 UTF-8 `Content-Disposition`을 사용하며 원본 자료, 삭제 문서, 편집 상태가 없는 문서는 `404`로 처리한다.
- 내보내기는 문서 version·수정 시각·본문을 변경하지 않고 이미지 URL을 Markdown 문자열 그대로 유지한다.

**검증**

- service·controller 테스트에서 멤버 권한, UTF-8 본문, 한글 파일명과 오류 조건을 검증했다.
- PostgreSQL 통합 테스트에서 최신 편집본 반환과 문서 상태 불변을 검증했다.
- `./gradlew clean test` 전체 246개 테스트가 통과했다.

**남은 주의사항**

- 이미지 파일을 포함하는 ZIP 내보내기는 assets SDD TASK-008에서 후속 구현한다.
- PDF 등 Markdown 외 내보내기 형식은 `docs/issue/backend/2026-07-25.md`에서 관리한다.
- frontend 다운로드 연동은 `docs/issue/frontend/2026-07-25.md`에서 관리한다.

### feat: 문서와 workspace 소프트 삭제 추가

**변경된 것**

- 문서 삭제를 물리 삭제에서 `base_version` 기반 소프트 삭제로 전환하고 휴지통·복구 API를 추가했다.
- 문서 복구는 원본, Markdown 편집 상태, Wiki와 block을 유지하며 역할별 최상위 마지막 위치에 배치한다.
- workspace에 `deleted_at`, `deleted_by`를 추가하고 하위 문서·채팅·Wiki·멤버십을 변경하지 않는 소프트 삭제·복구를 구현했다.
- 삭제 workspace는 공통 멤버십 조회에서 제외해 문서·채팅·Wiki API 접근을 `404`로 처리한다.
- 삭제 workspace 또는 삭제 문서는 새 backend pipeline 요청과 status·heartbeat callback 대상에서 제외한다.
- 문서·workspace 삭제와 복구에 `Idempotency-Key`를 적용하고 문서 수명주기는 행 잠금과 `current_version`으로 동시 요청을 제어한다.

**검증**

- service·controller 테스트에서 삭제·휴지통·복구, 소유권, version과 멱등 계약을 검증했다.
- PostgreSQL 통합 테스트에서 원본·본문·하위 workspace 데이터 보존, 접근 차단·복구와 동시 문서 삭제를 검증했다.
- `./gradlew clean test` 전체 242개 테스트가 통과했다.

**남은 주의사항**

- 페이지·원본 폴더 트리 삭제와 원래 위치 복구는 `docs/issue/backend/2026-07-25.md`에서 관리한다.
- frontend 휴지통 UI는 `docs/issue/frontend/2026-07-25.md`, 실행 중 pipeline 중단은 `docs/issue/ai/2026-07-25.md`에서 관리한다.

## 2026-07-24

### feat: Markdown 최신 편집본 복제 추가

**변경된 것**

- `POST /api/workspaces/{workspace_id}/documents/{document_id}/duplicate`에서 문서 소유자가 최신 Markdown 편집본을 새 문서로 복제할 수 있게 했다.
- 복제본은 새 ID, `text/markdown`, `completed`, version 1로 생성하고 원본과 같은 부모의 마지막 `sort_order`에 배치한다.
- 서버가 `복사본`, `복사본 (N)` 이름을 선택하며 255자를 넘으면 `.md`와 접미사를 보존한 채 이름 본체를 줄인다.
- 같은 부모의 활성 페이지를 잠가 이름과 순서를 원자적으로 결정하고, `Idempotency-Key` 재요청은 최초 결과를 반환한다.
- 원본 파일, `source_uri`, 공유 설정과 이력은 복제하지 않으며 `source_document_id`로 복제 원본만 추적한다.

**검증**

- service·controller 테스트에서 최신 본문, 이름 증가, 부모·정렬 위치, 소유권과 원본 자료 거절을 검증했다.
- PostgreSQL 통합 테스트에서 동일 멱등 키의 동시 복제가 문서와 멱등 기록을 각각 한 건만 생성하는지 검증했다.
- `./gradlew clean test` 전체 229개 테스트가 통과했다.

**남은 주의사항**

- PDF 원본의 `.md` 복제는 변환 편집본 등록 이후 연결하며 `docs/issue/backend/2026-07-24.md`에서 관리한다.
- frontend 복제 UI와 응답 반영은 `docs/issue/frontend/2026-07-24.md`에서 후속 관리한다.

### feat: Markdown 수동 저장과 Notion식 페이지 제목 변경 추가

**변경된 것**

- `PUT /api/workspaces/{workspace_id}/documents/{document_id}/content`에서 전체 Markdown과 `base_version`을 multipart part로 받아 현재 편집 상태를 수동 저장한다.
- 본문 저장과 `PATCH /rename`은 `documents.current_version` 조건부 update로 동시 변경을 차단하고, 실제 변경 시 version을 1 증가시킨다.
- 동일 본문·동일 제목은 `changed=false`로 반환하며 version과 수정 시각을 유지한다.
- rename은 `display_name`을 Notion식 page title로 사용하고 기존 확장자를 유지하며 Markdown heading, Wiki Source Page 제목과 업로드 원본은 변경하지 않는다.
- 문서 소유자만 본문 저장과 rename을 수행할 수 있고, 비소유 workspace 멤버는 `403 DOCUMENT_WRITE_FORBIDDEN`을 받는다.
- production 저장 API와 충돌하던 local 메모리 content mock을 제거했다.
- Swagger가 실제 multipart body를 생성하도록 `markdown`, `base_version`을 `@RequestPart`로 명시하고 요청·오류 응답 설명을 갱신했다.

**검증**

- service·controller 테스트에서 정상 저장, no-op, version 충돌, 소유권, 확장자 유지와 Swagger multipart 요청을 검증했다.
- PostgreSQL 통합 테스트에서 조건부 rename·본문 갱신과 오래된 version의 update 차단을 검증했다.
- `./gradlew clean test` 전체 222개 테스트가 통과했다.

**남은 주의사항**

- frontend의 저장·rename 계약 변경과 미저장 이탈 경고는 `docs/issue/frontend/2026-07-24.md`에서 후속 관리한다.
- 이미지 attachment 저장은 assets SDD의 후속 task에서 구현한다.

### fix: 비 Markdown 업로드의 불필요한 pipeline 요청 차단

**변경된 것**

- 업로드 형식은 제한하지 않되 비 Markdown 파일은 `uploaded`, `ORIGINAL`, `editable=false`인 원본 자료로 저장한다.
- 비 Markdown 원본은 편집 상태와 처리 큐를 생성하지 않아 Markdown 입력만 받는 Wiki pipeline에 잘못 전달되지 않게 했다.
- Markdown 업로드의 즉시 편집 상태 생성과 기존 Wiki pipeline 실행 흐름은 유지한다.

**검증**

- PDF 원본의 MinIO·DB 저장, `uploaded` 상태, 편집 상태 미생성과 처리 큐 미등록을 서비스 테스트로 검증했다.
- `./gradlew clean test` 전체 217개 테스트가 통과했다.

**남은 주의사항**

- PDF 복원 CLI 연동과 Markdown을 포함한 내보내기는 `docs/issue/backend/2026-07-24.md`에서 후속 관리한다.

### feat: Markdown 직접 생성과 즉시 편집 업로드 추가

**변경된 것**

- `POST /api/workspaces/{workspace_id}/documents/markdown`으로 빈 본문을 포함한 Markdown 문서를 직접 생성할 수 있게 했다.
- 직접 생성 문서는 MinIO 원본 없이 `source_uri=null`, `completed`, version 1인 편집 문서와 현재 편집 상태를 같은 transaction에서 생성한다.
- Markdown 업로드는 원문으로 편집 상태를 즉시 생성하고 pipeline 완료 전에도 `editable=true`를 반환한다.
- 생성·업로드에 `Idempotency-Key`를 적용하고 24시간 동안 같은 요청에는 저장된 최초 응답을 반환하며, 같은 key의 다른 요청은 `409`로 거절한다.
- 동일한 파일명과 내용의 새로운 요청은 별도 문서로 허용하고, 새 문서는 역할별 최상위 마지막 순서에 배치한다.
- MinIO 저장 후 DB transaction이 실패하면 업로드 객체를 보상 삭제하고, 초기 노트는 MinIO 없이 직접 생성 경로를 사용한다.

**검증**

- 빈 본문, UTF-8 5MB 초과, Markdown 즉시 편집, 최초 응답 replay와 key 충돌을 테스트했다.
- MinIO 실패 시 DB 미저장과 DB 실패 시 MinIO 보상 삭제를 검증했다.
- 초기 노트의 `source_uri=null`, 편집 상태 생성과 MinIO 미사용을 검증했다.
- `./gradlew clean test` 전체 216개 테스트가 통과했다.

**남은 주의사항**

- 선택적 `parent_document_id`, `source_folder_id` 위치 연동은 hierarchy `TASK-H004`에서 구현한다.
- production 본문 저장과 `base_version` 충돌 처리는 후속 Core TASK로 유지한다.

### feat: Markdown 문서 조회·파일명 검색 확장

**변경된 것**

- 기존 `GET /api/workspaces/{workspace_id}/documents` 호환 목록에 페이지·원본 영역, 항목 종류, 표시 이름, 파일 형식, 편집 가능 여부, 현재 version, 원본 참조와 수정 시각을 추가했다.
- 목록에 선택적 `query`를 받아 `display_name`과 `filename`만 대소문자 구분 없이 검색하며, 본문은 검색하지 않는다.
- 목록은 공용 `sort_order`를 적용하고 삭제 문서, 다른 workspace 문서, `origin=chat_export` 문서를 제외한다.
- 문서 상세에 현재 Markdown과 `current_version`을 반환하고, 삭제 문서는 상세·원본·block API에서 조회되지 않게 했다.

**검증**

- 페이지·원본 구분, 검색어 전달, 현재 Markdown 상세 응답을 service·controller 테스트로 검증했다.
- PostgreSQL 통합 테스트에서 삭제 문서, 다른 workspace, `chat_export` 제외와 본문 검색 제외를 검증했다.
- `./gradlew clean test` 전체 208개 테스트가 통과했다.

**남은 주의사항**

- `/navigation`, breadcrumb와 직계 자식 지연 조회는 hierarchy `TASK-H005`에서 구현한다.
- production 본문 저장과 `base_version` 충돌 처리는 후속 Core TASK로 유지한다.

### feat: Markdown 문서 편집 입력 규칙 추가

**변경된 것**

- 표시 이름의 앞뒤 공백과 금지 문자·제어문자·255자 제한을 검증하고, 이름 변경 시 기존 PDF·Markdown 확장자를 유지하는 규칙을 추가했다.
- Markdown 본문은 빈 문자열을 허용하되 `null`, 잘못된 UTF-8, UTF-8 기준 5MB 초과를 구분해 거절한다.
- 저장 전에 SHA-256 hash를 계산하고 현재 hash와 비교해 동일 본문 no-op을 판정할 수 있게 했다.
- 기존 Markdown 편집 상태 lazy 생성도 같은 UTF-8·크기·hash 규칙을 사용한다.

**검증**

- PDF·Markdown 확장자 유지, 한글 UTF-8 5MB 경계, 빈 본문·`null`, 잘못된 UTF-8, SHA-256·no-op 테스트를 추가했다.
- 같은 workspace에서 파일명과 내용이 모두 같은 문서를 생성할 수 있음을 PostgreSQL 통합 테스트로 검증했다.
- `./gradlew clean test` 전체 204개 테스트가 통과했다.

**남은 주의사항**

- 이 규칙을 사용하는 production 본문 생성·저장 API와 `base_version` 충돌 처리는 후속 Core TASK에서 구현한다.

### feat: Markdown 문서 편집 Core 데이터 기반 추가

**변경된 것**

- Flyway `V9`에서 `documents`에 표시 이름, 문서 역할(`EDITABLE`/`ORIGINAL`), 현재 version·hash, 페이지·원본 폴더 관계, 정렬과 소프트 삭제 필드를 추가했다.
- 동일 workspace의 같은 내용 문서를 허용하도록 기존 content hash UNIQUE 제약을 제거했다.
- 현재 Markdown, 원본 폴더, 24시간 요청 멱등 결과를 위한 `document_edit_states`, `source_folders`, `idempotency_records`를 추가했다.
- 기존 V8 문서를 역할별 최상위 위치와 순서로 backfill하고, 기존 Markdown은 최초 상세 조회 시 MinIO 원문으로 편집 상태를 lazy 생성한다.
- 동시 최초 조회는 `INSERT ... ON CONFLICT DO NOTHING`으로 하나의 편집 상태만 생성한다.

**검증**

- V8 데이터를 별도 PostgreSQL database에서 V9로 올려 표시 이름, 역할, 순서, version·hash backfill을 검증했다.
- 문서 역할별 부모 제약, 동일 hash 허용, 편집 상태 1:1, 폴더 self-reference와 멱등 키 UNIQUE 통합 테스트를 추가했다.
- `./gradlew clean test` 전체 198개 테스트가 통과했다.

**남은 주의사항**

- 직접 생성·업로드·저장 API의 멱등 응답 처리와 파일명·본문 검증은 후속 Core TASK에서 구현한다.
- 원본 폴더 CRUD·이동·정렬과 다른 workspace 부모 차단은 hierarchy TASK에서 구현한다.

## 2026-07-22

### fix: 로컬 이메일 인증 고정 코드 복구

**변경된 것**

- `local` profile의 이메일 인증번호 기본값을 임시 코드 `9700`으로 설정하고 `AUTH_EMAIL_DEV_FIXED_CODE`로 덮어쓸 수 있게 했다.
- `./gradlew bootRun`도 별도 profile 지정이 없으면 `local`로 실행되게 해 개발 실행 방식에 따라 고정 코드가 누락되지 않도록 했다.
- 공통 설정의 고정 코드 기본값은 빈 값으로 유지해 production에는 `9700`이 적용되지 않게 했다.

**남은 주의사항**

- 운영 메일 서버 연동과 dev 발송 stub 제거 작업은 `docs/issue/backend/2026-07-23.md`의 `3. 운영 이메일 인증 메일 서버 연동`에서 관리한다.

**검증**

- `EmailVerificationServiceTest`에서 개발 고정 코드 `9700`이 발송 코드로 사용되는 회귀 테스트를 포함해 통과했다.

### feat: Markdown Agent turn Spring 프록시 추가

**변경된 것**

- `POST /api/workspaces/{workspace_id}/agent/turn`을 추가해 인증된 workspace 문서의 Agent 요청을 `llmPipeline`의 `POST /agent/turn`으로 전달한다.
- 문서 접근 권한과 Markdown 형식, line target 범위를 pipeline 호출 전에 확인한다.
- frontend의 camelCase editor snapshot을 pipeline의 `active_markdown_context` snake_case 계약으로 변환하고, 결과에 `documentId`, `baseVersion`, `requestId`를 붙여 반환한다.
- pipeline의 HTTP 400/422 응답 본문을 보존하며 timeout·연결 실패는 503으로 변환한다.
- `AGENT_ENDPOINT`, `AGENT_TIMEOUT_SECONDS` 설정을 추가했다.

**검증**

- Agent controller·service·requester 테스트 7건 통과.
- Backend 전체 190건 중 183건 통과. Testcontainers Docker 연결 환경 6건과 이번 변경과 무관한 초기 노트 hash 기대값 1건이 실패했다.

**남은 주의사항**

- production 문서 content 영속화가 준비되기 전까지 Backend는 요청의 `baseVersion`을 보존하지만 현재 저장 version과 직접 비교하지 않는다.
- 실제 chat session 요약·reference context 구성은 `docs/issue/backend/2026-07-22.md`의 후속 작업으로 유지한다.

## 2026-07-21

### feat: 이메일 인증 기반 회원가입·비밀번호 재설정 API 추가

**배경**

- 회원가입·비밀번호 재설정 화면에 필요한 이메일 인증 API가 없어, 프론트가 임시 인증번호(9700)와 인증 전 signup 선호출로 우회하고 있었다.

**변경된 것**

- 인증번호 발급 `POST /api/auth/email-verifications`(purpose=signup|password_reset), 검증 `POST /api/auth/email-verifications/{id}/confirm`, 비밀번호 재설정 `POST /api/auth/password-reset` 추가.
- `POST /api/auth/signup`에 `verification_token`을 필수로 추가하고, 중복 검사 후 토큰을 검증·소비하도록 변경.
- `email_verifications` 테이블(Flyway `V7`) 추가. 인증번호와 `verification_token`은 SHA-256 해시만 저장하고, 새 코드 발급 시 같은 (email, purpose)의 미소비 코드를 폐기.
- 재요청 cooldown·일일 상한(429), 코드 만료·오입력·시도 초과, 토큰 1회성·재사용 차단 정책을 적용. 관련 설정 키는 `app.auth.email-verification.*`. 존재 노출(signup 409)도 rate limit 게이트 뒤에 두어 동일하게 throttle 대상에 포함한다.
- 회원가입은 중복 이메일에 409(존재 노출)를, 비밀번호 재설정은 계정 존재 여부와 무관하게 동일 응답(존재 무노출)을 반환. 재설정 성공 시 해당 사용자 refresh token 전체 폐기.
- 인증번호 발송은 dev 로그 stub(`LoggingEmailVerificationSender`)로 처리하며, 운영 배포 전 실제 SMTP 발송 구현으로 교체 필요. stub이 활성화된 채 부팅되면 인증번호 로그 노출 위험을 알리는 경고를 남긴다.
- 일일 상한 초과 429의 `retry_after`는 윈도 내 최고령 요청이 24h를 벗어나는 시점 기준으로 계산한다.
- 잔여 프론트 작업은 `docs/issue/backend/2026-07-21.md` 참조.

**검증**

- user 패키지 테스트 54개 통과(`EmailVerificationServiceTest` 13, `AuthControllerTest` 20 포함).
- 전체 컨텍스트 로딩 테스트 통과 — Testcontainers Postgres에 `V7` 적용 및 `ddl-auto=validate` 매핑 정합성 확인.

**남은 주의사항**

- 운영 전 `dev-fixed-code`는 빈값 유지, 발송 sender를 실제 메일 발송으로 교체.
- 프론트엔드의 임시 인증번호·인증 전 signup 선호출 제거 및 발급→검증→가입 재배선 필요(프론트 팀).

### feat: 새 노트 편집용 local 저장 mock 추가

**변경된 것**

- `local` profile에서만 등록되는 노트 본문 메모리 mock controller를 추가했다.
- `GET/PUT /api/workspaces/{workspace_id}/documents/{document_id}/content`로 draft 조회와 version 기반 저장을 제공한다.
- 이전 version으로 저장하면 `409 Conflict`를 반환하며 DB, MinIO, pipeline, Wiki 데이터는 변경하지 않는다.
- frontend의 `PUT` 요청을 허용하도록 CORS method에 `PUT`을 추가했다.

**검증 및 주의사항**

- controller test에서 미저장 `404`, 저장/version 증가, 충돌 시 기존 draft 유지, 비인증 `401`을 검증했다.
- Colima 환경에서 Docker 소켓과 Testcontainers override를 지정해 전체 151개 테스트가 통과했다.
- 이 API는 frontend 프로토타입용이며 production 저장 계약을 대체하지 않는다.

### fix: query pipeline 요청에 workspace_id 전달

**배경**

- Backend는 workspace URL에서 세션 소유권을 검증했지만 LLM Pipeline `POST /query` 본문에 workspace 식별자를 보내지 않아, Pipeline이 질의의 데이터 범위를 구분할 수 없었다.

**변경된 것**

- 동기·비동기 query 호출 경로에 `workspaceId`를 전달하고, Pipeline 요청 JSON에 `workspace_id`를 포함한다.
- Pipeline 요청 로그에 `workspaceId`를 추가한다.
- `llmPipeline` 코드와 내부 workspace 조회 로직은 변경하지 않았다.

**검증**

- query 관련 controller·service·requester 테스트 통과
- Backend 전체 154개 중 비관련 기존 `DocumentServiceBlocksTest` 1개 실패(초기 노트 hash 기대값 불일치)

### fix: query 비동기 run 타임아웃 정리와 SSE heartbeat 스케줄 연결

**배경**

- 응답 없이 파이프라인이 멈추면 run이 `RUNNING`에 영구히 남아, 화면은 "처리 중"으로 끝나지 않고 in-memory에도 누적됐다. 기존 정리(`evictExpired`)는 종료된(`COMPLETED`/`FAILED`) run만 대상이라 고착 run을 치우지 못했다.
- `QueryEventBroker.sendHeartbeat()`는 구현돼 있으나 이를 주기 호출하는 스케줄러가 없어, 진행 이벤트가 뜸한 긴 질의에서 idle SSE 연결이 중간 네트워크 장비에 끊길 수 있었다.

**변경된 것**

- `QueryRunStore.failStuck(timeout, msg)` 추가: 미종료(`RUNNING`/`PENDING`)이고 생성 후 timeout을 넘긴 run을 `FAILED`로 전이(스캔 이후 정상 종료된 run은 덮어쓰지 않는 레이스 가드)하고 requestId 목록 반환.
- `QueryRunService.failStuckRuns()`(`@Scheduled` 60초, `RUNNING_TIMEOUT=5분`): 고착 run을 실패 종결하고 `query.failed` SSE를 발행. 이후 기존 TTL 정리가 dispose.
- `QueryEventBroker.sendHeartbeat()`에 `@Scheduled`(15초)를 부착해 idle SSE 연결에 주기적으로 `:ping`을 전송.

**검증**

- `QueryRunStoreTest`에 `failStuck` 케이스 2개 추가(오래된 미종료만 실패 처리 / 완료 run 무시).
- `QueryRunStoreTest`, `QueryRunServiceTest`, `QueryEventBrokerTest` 통과.

**남은 주의사항**

- 여전히 in-memory 단일 인스턴스 전제다. 당시 검토한 다중 인스턴스 run 공유안은 `docs/backlog/query-sse-redis.md`에 보관했다.

### fix: 초기 노트의 임시 주석 제거 및 status를 completed로 저장

**배경**

워크스페이스 생성 시 만드는 초기 노트(`새 노트.md`)는 본문이 모두 `# 새 노트`로 같아, 과거 전역 `content_hash` UNIQUE와 충돌하는 것을 피하려 `<!-- fruition-workspace: ws_... -->` 식별 주석을 넣어 해시를 워크스페이스마다 다르게 만들었다. 이 주석은 문서 내용이 아닌데 원본 Markdown에 섞여 미리보기에 내부 워크스페이스 ID가 노출됐다. 또한 초기 노트는 파이프라인 처리 큐에 올리지 않는데도 `status`가 `processing`으로 남았다.

**변경된 것**

- V5로 중복 판별이 `(workspace_id, content_hash)` 범위가 되면서 우회 주석이 불필요해져, `DocumentService.createInitialNote`의 본문을 `# 새 노트`로 정리(주석 제거).
- 초기 노트를 저장 직전 `updateStatus(DocumentStatus.completed, null, now, null)`로 완료 처리 → 목록/상세의 `processing_state`도 `completed`로 일관.

**남은 주의사항**

- 이미 생성된 기존 초기 노트의 원본 오브젝트에는 주석이 남아 있다. 미리보기 노출 숨김(프론트) 처리는 별도 후속 작업으로 둔다.

### fix: query 메시지 선저장과 실패 상태 전이 보장

**배경**

비동기 query가 끝난 뒤 user/assistant 메시지를 함께 저장해, 처리 중에는 사용자의 질문이 채팅 DB에 보이지 않았다. pipeline 실패 기록도 원래 query transaction과 함께 rollback될 수 있었고, 예상 밖 예외에서는 run이 `RUNNING`에 남을 수 있었다.

**변경된 것**

- `QueryRunService.start()`가 `202`를 반환하기 전에 같은 `pair_id`의 `user=completed`, `assistant=pending` 메시지를 `REQUIRES_NEW` transaction으로 commit한다.
- 성공 시 기존 assistant를 `completed`와 최종 답변으로 갱신하고, pipeline 또는 예상 밖 오류 시 같은 assistant를 `failed`와 오류 메시지로 갱신한다.
- 예상 밖 `Exception`도 run을 `FAILED`로 바꾸고 일반화된 `query.failed` SSE를 발행한다. 상세 stack trace는 서버 로그에만 남긴다.
- 당시 인메모리 SSE 흐름과 Redis Pub/Sub·Streams 적용 기준을 `docs/backlog/query-sse-redis.md`에 시각화했다.

**검증**

- `202` 직후 SSE 연결 전 채팅 조회에서 `user=completed`, `assistant=pending` 확인
- pipeline 403 종료 후 동일 assistant가 `failed`로 갱신된 것을 PostgreSQL에서 확인
- `./gradlew test` 통과

### feat: query run·문서 파이프라인 이벤트 관측 로깅 보강

**배경**

query 비동기 run과 문서 처리 파이프라인 흐름에서 요청/응답·상태 전이·SSE 발행 시점을 추적할 로그가 부족해, 장애 원인 파악이 어려웠다.

**변경된 것**

- query 계열(`QueryController`, `QueryRunController`, `QueryService`, `QueryRunService`, `QueryRunStore`, `QueryEventBroker`, `PipelineQueryRequester`)에 요청 수신·run 상태 전이·파이프라인 호출/응답·SSE 구독/발행/완료·만료 제거 로그를 추가. 로그에는 원문 question 대신 `questionLength`만 남긴다.
- 문서 처리 계열(`DocumentProcessingRequester`, `DocumentProcessingWorker`)에 파이프라인 요청 데이터·큐 선택/삭제 로그 추가.
- `DocumentPipelineController`가 pipeline-events 콜백의 `message`/`data`를 `DocumentService.applyPipelineEvent`로 전달하도록 연결(관측용 수신, DTO 저장은 하지 않음).
- `QueryService`는 근거/관련 페이지 저장 건수 로깅을 위해 지역 변수로 추출(동작 동일).

**검증**

- merge된 트리 `./gradlew compileJava` 통과.

### feat: document 중복 판별을 workspace 범위로 전환 (V5)

**배경**

지금까지 `content_hash`에 전역 UNIQUE가 걸려 있어, 다른 workspace가 같은 내용의 문서를 올려도 중복으로 막혔다. 중복 판별을 "같은 workspace 안에서만" 하도록 바꾼다.

**변경된 것**

- `V5__scope_document_content_hash_per_workspace.sql`로 전역 `content_hash UNIQUE`(Hibernate 생성명 `ukeafca5s6k4behm6am8avmcik3`)를 제거하고 `(workspace_id, content_hash)` 복합 UNIQUE(`uq_documents_workspace_content_hash`)로 교체.
- `Document` 엔티티: `content_hash` 컬럼의 `unique=true` 제거, `@Table`에 복합 UNIQUE 명시.
- `DocumentRepository.findByContentHash` → `findByWorkspaceIdAndContentHash`로 교체.
- `DocumentService.upload()` / `createChatExportDocument()`의 중복 조회를 workspace 범위로 교체.
- 판별 기준은 `content_hash`(내용 해시)만이며, 중복 시 업로드 거부. 파일명은 판별에 쓰지 않는다.

**검증**

- 로컬 DB에 중복 (workspace_id, content_hash)이 없어 복합 UNIQUE 전환은 무충돌.

### fix: 파이프라인 스키마를 Flyway 관리 대상으로 통합

**배경**

FastAPI lifespan이 공용·파이프라인 테이블을 직접 생성해, Backend Flyway보다 먼저 실행되면 baseline 판정과 migration 순서가 깨질 수 있었습니다.

**변경된 것**

- `V4__add_pipeline_schema.sql`에서 `pipeline_runs`, 임베딩 테이블, `wiki_schemas`를 생성하고 버전을 관리합니다.
- Flyway V1~V3 적용 후 Python 초기화로 pipeline 테이블이 생성된 DB도 수용하도록 비파괴 migration으로 작성했습니다.
- Flyway 이력 없이 Python이 공용 테이블 일부만 만든 로컬 DB는 V3를 적용할 수 없으므로 기존 Flyway 안내대로 volume을 한 번 리셋해야 합니다.
- Backend 통합 테스트에서 Flyway 적용 후 파이프라인 테이블 5개의 존재를 확인합니다.

**검증**

- 격리된 PostgreSQL에서 V1 → V4 순차 적용 및 V4 재실행
- `BackendApplicationTests` 실행 시도: 로컬 Java runtime 부재로 미실행

## 2026-07-20

### feat: 워크스페이스 초기 노트 자동 생성

**배경**

새 워크스페이스가 비어 있어 첫 진입 시 바로 확인할 문서가 없었다.

**변경된 것**

- 기본 워크스페이스와 사용자가 추가한 워크스페이스 생성 시 실제 Markdown 문서 `새 노트.md`를 함께 저장한다.
- 초기 노트는 일반 문서와 같은 저장소와 처리 큐를 사용하며, 워크스페이스별 콘텐츠 해시 충돌을 피하도록 식별 주석을 포함한다.
- 워크스페이스 생성 연결과 워크스페이스별 고유 문서 저장을 단위 테스트로 검증한다.

**검증**

- `./gradlew test`

### fix: 로컬 기동용 health endpoint 추가

**배경**

`scripts/dev-up.sh`가 제거된 사용자용 `GET /api/documents`를 backend readiness 확인에 사용해, 서버가 정상 기동해도 `405 Method Not Allowed`를 실패로 판단했습니다. readiness 확인을 인증·workspace·업무 API 계약과 분리할 endpoint가 필요했습니다.

**변경된 것**

- `backend/build.gradle` — `spring-boot-starter-actuator` 의존성 추가
- `scripts/dev-up.sh` — backend Flyway가 공용 스키마를 먼저 생성하도록 pipeline API보다 backend를 먼저 시작
- `SecurityConfig` — `GET /actuator/health`를 인증 없이 호출할 수 있도록 명시
- `BackendApplicationTests` — 비인증 health 요청이 `200 OK`, `{"status":"UP"}`를 반환하는 통합 테스트 추가
- `backend/README.md`, `docs/spec/document-upload.md`, `docs/spec/backend-mvp-erd.md` — health endpoint와 현재 workspace 기반 Document API 경로 반영

**검증**

- `./gradlew test`
- 빈 PostgreSQL volume에서 backend가 Flyway V1~V3를 적용한 뒤 pipeline API 기동
- `curl http://localhost:8080/actuator/health`

## 2026-07-16

### refactor: displayName 결정 규칙을 공용 유틸로 추출 + OAuth 닉네임 길이 상한

**배경**

회원가입(`UserService`)과 OAuth 신규 가입(`OAuthUserService`)에 "닉네임 있으면 trim, 없으면 이메일 앞 3글자" 로직이 중복돼 있었고, OAuth 경로는 provider 닉네임을 길이 제한 없이 저장해 회원가입(`@Size(max=50)`)과 규칙이 어긋났다.

**변경된 것**

- `fruition.util.DisplayNames`로 결정 규칙을 추출(`resolve`, `isPresent`). 결과를 최대 50자로 잘라 두 경로의 상한을 통일했다.
- `UserService`/`OAuthUserService`가 이 유틸을 재사용하도록 정리(동작 동일, OAuth 닉네임만 50자 상한 추가).
- `DisplayNamesTest`로 trim/fallback/상한/blank 판정을 검증.

### feat: workspace 삭제 연쇄를 위한 DB 레벨 FK CASCADE 도입 (V3)

**배경**

지금까지 workspace 삭제 시 하위 리소스 정리를 애플리케이션 코드에 의존했고, `WorkspaceService.delete()`의 낡은 주석(`wiki_pages`에 workspace_id가 없다고 오기재) 때문에 **workspace 삭제 시 `wiki_pages`(특히 concept page)가 고아로 남는 버그**가 있었다(`docs/issue/backend/2026-07-15.md` #3). Flyway 도입 이후 이제 DB 레벨 참조 무결성을 세울 수 있게 됐다.

**변경된 것**

- `V3__add_workspace_fk_cascade.sql`로 FK 20개 추가 — 소유 관계는 `ON DELETE CASCADE`(15개), 단순 참조(nullable)는 `ON DELETE SET NULL`(5개).
- 파이프라인이 같은 트랜잭션에서 wiki_pages보다 링크를 먼저 insert해도 안 깨지도록, wiki_pages를 참조하는 링크 FK 3개(`document_wiki_links.wiki_page_id`, `wiki_page_links.from_page_id/to_page_id`)는 `DEFERRABLE INITIALLY DEFERRED`.
- 삭제 의미론: **workspace 삭제 → 그 안의 모든 것(concept page 포함) 연쇄 삭제**. **단일 document 삭제 → concept·source page 본체는 보존**(documents는 wiki_pages의 부모가 아님)하고, source page 선택 삭제 규칙은 앱 로직(`DocumentService.deleteInternal`)이 유지.
- `WorkspaceService.delete()`의 낡은 주석을 정정(로직 변경 없음). 앱 레벨 삭제 코드는 MinIO 오브젝트 삭제·source/concept 규칙 때문에 이번엔 유지.

**검증**

- 빈/기존 DB에 V3 적용, `ddl-auto=validate` 통과. FK 20개의 ON DELETE 동작(CASCADE/SET NULL)과 DEFERRABLE 3개를 `pg_constraint`로 확인.
- SQL 실증: workspace 삭제 전체 연쇄(고아 0), 단일 문서 삭제 시 wiki_pages 2개 보존 + 참조 SET NULL, concept page 삭제 시 링크 CASCADE + 참조 SET NULL, DEFERRABLE 링크 순서 insert commit 성공.
- `./gradlew test --rerun-tasks` 통과. `ChatSessionCascadeDeleteIntegrationTest`는 새 FK에 맞게 부모 행 생성/참조 null로 테스트 데이터를 보정했다.

### chore: Flyway 도입 및 스키마 관리 방식 전환 (ddl-auto=validate)

**배경**

`ddl-auto=update`는 컬럼/제약을 추가만 하고 삭제·변경을 반영하지 못해, 엔티티 변경 시 옛 제약이 "잔재"로 남는다. 실제로 `wiki_pages`의 잔재 unique constraint `uq_wiki_pages_type_slug`가 llmPipeline의 wiki page upsert를 막는 문제가 있었다(`docs/backlog/issue-2026-07-16.md` 이슈 1). 스키마를 버전 관리되는 마이그레이션으로 전환한다.

**변경된 것**

- `build.gradle`에 `flyway-core`, `flyway-database-postgresql` 의존성을 추가했다.
- `ddl-auto`를 `update` → `validate`로 바꿔 스키마의 단일 소스를 Flyway로 일원화했다. 앱은 기동 시 검증만 수행한다.
- `application.properties`에 `spring.flyway.enabled/baseline-on-migrate/baseline-version`을 추가했다. 기존 데이터가 있는 DB는 v1로 마킹만 하고 V2부터 적용된다.
- baseline 마이그레이션 `V1__baseline_schema.sql`(엔티티 16개 기준 깨끗한 스키마)과 잔재 제거 마이그레이션 `V2__drop_leftover_wiki_pages_unique.sql`을 추가했다.
- `backend/README.md`에 팀원용 Flyway 사용법(최초 1회 리셋 / 평상시 pull+bootRun / 스키마 변경 시 Vn 규칙 / 운영 DB baseline)을 문서화했다.
- Spring Session 테이블은 Flyway 관리 대상이 아니며 기존대로 Spring Session JDBC가 생성한다.

**검증**

- 빈 DB 기동 시 Flyway가 V1 → V2를 적용하고 `ddl-auto=validate`가 통과했다. `flyway_schema_history`에 2건 success 확인.
- 적용 후 `wiki_pages`에 잔재 constraint가 제거되고 `uq_wiki_pages_workspace_type_slug`만 남는 것을 확인했다.
- `./gradlew test --rerun-tasks` (Testcontainers) 통과. Test worker 로그에 `Successfully applied 2 migrations` 확인.

### feat: 회원가입 닉네임 입력 및 인증 로그 추가

**배경**

일반 회원가입에서도 이메일/비밀번호 외에 닉네임을 받을 수 있게 하고, 카카오 OAuth에서 받은 닉네임도 사용자 표시명으로 저장해야 했다. 동시에 회원가입·로그인·OAuth 흐름을 로컬에서 확인하기 쉽도록 민감값을 제외한 진단 로그가 필요했다.

**변경된 것**

- `SignupRequest`에 선택 필드 `display_name`을 추가했다. 값이 있으면 trim 후 `displayName`으로 저장하고, 없거나 공백이면 기존처럼 이메일 앞 3글자를 저장한다.
- OAuth 신규 사용자 생성 시 provider가 제공한 이름/닉네임을 `displayName`으로 우선 저장하고, 없으면 이메일 prefix fallback을 사용한다.
- 회원가입, 로그인, OAuth 사용자 매핑, OAuth 인증 redirect, OAuth code 교환 흐름에 로그를 추가했다. 비밀번호, token, OAuth code, client secret은 로그에 남기지 않는다.
- 닉네임 저장 규칙 테스트를 보강했다.

**검증**

- 실제 로컬 API 호출로 회원가입 `201`, 로그인 `200`을 확인했다.
- Google/Naver/Kakao OAuth authorization endpoint가 각각 `302` redirect를 생성하는 것을 확인했다.
- `./gradlew test --tests fruition.user.service.UserServiceTest --tests fruition.user.service.AuthServiceTest --tests fruition.user.service.OAuthUserServiceTest --tests fruition.security.oauth.domain.OAuth2UserInfoTest` 통과.

## 2026-07-10

### perf: reconciler 폴링 최적화 — reconciled_at 마커 + 인덱스 + @DynamicUpdate

**배경**

`ChatWikiExportReconciler`가 매 3초마다 완료된 chat_export를 훑는데, `documents`에 인덱스가 없어 순차 스캔이었고 이미 후처리된 문서까지 매번 다시 조회했다. 또 파이프라인이 같은 `documents` 행에 raw SQL로 직접 쓰므로(공유 쓰기), backend의 JPA full-column UPDATE가 파이프라인 컬럼을 덮어쓸 위험이 있었다. (설계 배경·대안: `docs/spec/pipeline-db-ownership.md`)

**변경된 것**

- `document/domain/Document`: `reconciled_at` 컬럼(null=미처리) + `markReconciled` + 재생성(`reopenForChatExportRegeneration`) 시 `reconciled_at` 리셋. `@Index(idx_documents_reconcile: origin, status, reconciled_at)`로 순차 스캔 제거. `@DynamicUpdate`로 **변경한 컬럼만 UPDATE**해 파이프라인이 쓴 `status` 등을 덮어쓰지 않게 함(공유 테이블 컬럼 단위 소유 분리).
- `document/repository/DocumentRepository`: `findAllByOriginAndStatus` → `findAllByOriginAndStatusAndReconciledAtIsNull`(미처리분만 조회).
- `chat/service/ChatWikiExportReconciler`: 새 쿼리 사용 + 후처리 성공 문서에 `markReconciled` + save. 미완(source_blocks/page 미생성)이면 마킹 안 하고 다음 tick 재시도(self-healing 유지).

**검증**

- 컴파일·`fruition.document.*`/`fruition.chat.*` 테스트 통과.

**주의사항**

- 인덱스·컬럼은 `ddl-auto=update`로 **재시작 시 생성**. 기존 `origin=chat_export AND status=completed` 문서는 `reconciled_at=NULL`이라 재시작 후 1회 재-reconcile되나 멱등이라 무해.
- 이번 변경은 파이프라인의 `documents` 직접쓰기라는 근본 문제의 우회(단기안)다. 소유권 회수(중기 C-poll)는 `docs/spec/pipeline-db-ownership.md` 후속작업 참고.

### feat: 채팅 export를 llmPipeline `/chat-wiki/runs` 엔드포인트로 라우팅

**배경**

llmPipeline이 채팅 전용 엔드포인트 `POST /chat-wiki/runs`(모델 `ChatWikiRunIn`)를 추가했다. 이 엔드포인트는 `document_id`(신원) + `selection_mode` + `input_markdown`(delta)을 동시 수용하고, full=기존 chat source page 누적(append)/partial=독립 페이지로 처리한다. 기존 `/pipeline/runs`는 `exactly_one_input` 제약이 있어 full 재생성 inline이 불가능했던 하드 블로커가 이 엔드포인트로 해소됐다. 일반 문서 ingest는 그대로 `/pipeline/runs`를 쓴다.

**변경된 것**

- `resources/application.properties`: `app.processing.chat-endpoint`(`${CHAT_PROCESSING_ENDPOINT:http://localhost:8000/chat-wiki/runs}`) 추가.
- `document/repository/DocumentProcessingRequester`: `chatEndpoint` 주입, `request(..., boolean chatWiki)`로 endpoint 분기(로그에 endpoint 표기). 페이로드(`PipelineRunRequest`)는 불변 — 보내는 필드가 모두 `ChatWikiRunIn`에 존재.
- `document/service/DocumentService.doRequestProcessing`: `origin=chat_export`이면 `chatWiki=true`로 전달.

**검증**

- 컴파일·`fruition.document.*`/`fruition.chat.*` 테스트 통과. 페이로드는 chat 계약(`docs/spec/chat-to-wiki-contract.md` §3)과 정합.

**주의사항**

- 실제 동작하려면 **backend 재시작 + `/chat-wiki/runs`를 포함한 파이프라인(현재 dev 반영분) 재빌드**가 필요하다. 재빌드 전엔 chat export가 `/chat-wiki/runs` 404로 실패한다.

## 2026-07-09

### fix: partial export가 세션 정식 export 문서를 덮어써 full 재생성이 오작동하던 문제

**배경**

`assignWikiExportDocument`가 full·partial 공통 경로라, partial export가 세션의 `wikiExportDocumentId`를 partial 문서 id로 덮어썼다. 그러면 이후 full 재생성이 그 값을 재사용해 **partial 문서를 대상으로 재생성**(MinIO 원본 덮어쓰기·status 리셋·재큐)하는 정합성 문제가 있었다.

**변경된 것**

- `chat/service/ChatWikiExportService.export`: `wikiExportDocumentId` 기록(+세션 save)을 **full일 때만** 수행. partial은 세션 정식 상태를 건드리지 않는다(독립 발췌).
- 회귀 테스트 추가: partial export 후 `wikiExportDocumentId` 불변·`save` 미호출 검증.

### feat: 채팅 full 재생성 시 기존 문서 재사용 + delta inline markdown 전송

**배경**

이미 위키가 연결된 세션을 다시 full로 export(재생성)할 때, 매번 새 문서를 만들지 않고 **기존 export 문서를 갱신**한다. 원본은 세션 전체로 덮어써 누적 기록을 유지하고, 파이프라인엔 미편입 문답(delta)만 inline으로 보내 append 처리에 쓰게 한다.

**추가/변경된 것**

- `document/domain/Document`: `pipeline_input_markdown`(TEXT) 컬럼 추가 + `reopenForChatExportRegeneration(contentHash, byteSize, inputMarkdown)`(status=processing 리셋, 원본 해시/크기 갱신, inline delta 저장).
- `document/service/DocumentService`: `regenerateChatExportDocument(documentId, fullMarkdown, fullContentHash, deltaMarkdown)` 추가 — 기존 문서의 MinIO 원본을 세션 전체로 **덮어쓰고** 처리 큐에 재등록. `doRequestProcessing`가 `Document.pipelineInputMarkdown`을 파이프라인 요청에 전달.
- `document/repository/DocumentProcessingRequester`: `PipelineRunRequest`에 `input_markdown`(`@JsonInclude(NON_NULL)`) 추가. 일반 업로드·첫 export는 null이라 키가 빠져 요청 불변.
- `chat/service/ChatWikiExportService`: `isRegeneration`(`full` + `session.wikiPageId != null` + `wikiExportDocumentId != null`) 분기. 재생성이면 기존 문서 재사용(원본=세션 전체, inline=delta), 그 외는 기존 신규 생성 경로.

**검증**

- 단위테스트 추가(재생성: 기존 문서 재사용, 원본=전체·inline=delta 분리, 신규 생성 경로 미호출). 전체 테스트 통과.

**주의사항 (하드 블로커)**

- **full 재생성은 llmPipeline 변경 전까지 실패한다.** 현재 `PipelineRunIn`은 `document_id`/`input_markdown` 중 하나만 허용(`exactly_one_input`)하고, inline 경로는 합성 `api-inline-{run_id}` id를 만들어 완료·reconciler가 깨진다. 파이프라인이 `document_id`(신원) + `input_markdown`(내용) 동시 수용 + `selection_mode` append 처리를 구현해야 한다. 상세: `docs/backlog/issue-2026-07-09.md` "llmPipeline 후속 작업".
- 첫 full·partial·일반 업로드는 기존 `document_id`+storage 경로 그대로.

### feat: partial 발췌 위키 멤버십(chat_partial_wiki) 기록 + 문답별 위키 노출

**배경**

한 문답을 서로 다른 발췌(partial) 위키에 여러 번 담을 수 있으므로(1:N), full 전용 `chat_messages.wiki_page_id`(1:1)로는 partial 멤버십을 표현할 수 없다. partial "문답 ↔ 위키 페이지" 관계를 별도 junction으로 정규화하고, 채팅 화면이 문답별로 "이미 위키인지"를 알 수 있게 노출한다.

**추가/변경된 것**

- `chat/domain/ChatPartialWiki`(신규) + `chat/repository/ChatPartialWikiRepository`(신규): 테이블 `chat_partial_wiki(session_id, pair_id, wiki_page_id, document_id, created_at)`, `UNIQUE(pair_id, wiki_page_id)`. partial 발췌 멤버십만 기록(full은 기존대로 `chat_messages.wiki_page_id`).
- `chat/service/ChatWikiExportReconciler`: 완료 문서를 **full/partial 분기**로 후처리. partial이면 `chat_partial_wiki`에 문답 멤버십 기록(`existsByDocumentId` 멱등 가드). `linkSession`을 "미연결 세션만 연결"로 바꿔, 잘못된 데이터(같은 세션 full 문서 다수)에도 무한 재기록/flip을 방지.
- `chat/dto/ChatMessageResponse`에 `wiki_page_id`(full, nullable) + `partial_wiki_page_ids`(partial 페이지 목록) 노출. `chat/controller/ChatSessionController`가 `findAllBySessionId`로 pair별 partial 페이지를 매핑해 채운다.

**검증**

- `compileJava`/`compileTestJava` 통과, `fruition.chat.*` 테스트 통과(`ChatSessionControllerTest`에 `ChatPartialWikiRepository` `@MockBean` 추가).

**주의사항**

- `chat_partial_wiki` 테이블은 `ddl-auto=update`로 자동 생성.
- 방향2(위키 페이지 → 원본 문답) 조회는 레포 메서드(`findAllByWikiPageId`)만 두고 엔드포인트는 후속.

## 2026-07-08

### refactor: 채팅 Wiki page화를 문답(pair) 단위 직렬화 + full/partial 선택으로 전환

**배경**

채팅 → 위키 계약이 개정되어(v2), 직렬화 단위를 메시지 → 문답(pair)로, 원문 링크 식별을 `session_id + pair_id`로 바꾼다. 이 커밋은 backend의 직렬화·선택 부분을 새 계약(§4)에 맞춘다. 입력 방식은 "storage/document_id 유지" 결정에 따라 그대로 둔다.

**추가/변경된 것**

- `chat/service/ChatWikiMarkdownSerializer`: 메시지 단위 헤딩 → **문답 pair 단위 `[session_id:pair_id]Q : … / A : …`** 포맷(§4). 불완전 문답(user·assistant 미완) 제외, 문답 내 빈 줄 접기.
- `chat/service/ChatWikiExportService.export`: `ChatWikiExportRequest(selection_mode, pair_ids)`를 받아 **full(전체) / partial(선택 문답)** 직렬화. partial은 선택된 pair만 포함.
- `chat/dto/ChatWikiExportRequest`(신규), `chat/exception/InvalidChatWikiExportRequestException`(신규 → 400 `INVALID_CHAT_WIKI_EXPORT_REQUEST`): selection_mode 검증.
- `chat/dto/ChatMessageResponse`에 `pair_id` 노출 — 프론트가 문답 단위로 선택할 수 있게.
- `document/domain/Document`에 `selection_mode` 컬럼 추가. export 시 저장하고, 워커가 `/pipeline/runs` 요청에 `selection_mode`로 전달한다(`@JsonInclude(NON_NULL)`이라 일반 업로드 요청은 불변). `createChatExportDocument`는 chat_export 문서에 selection_mode가 비면 생성을 거부한다. 파이프라인이 아직 이 값을 읽지 않아 현재는 no-op이며, append/create_new 분기 구현 시 사용된다.

**검증**

- serializer 단위테스트 재작성(포맷·순서·불완전 제외·빈 줄 접기).
- 라이브 e2e: full/partial 각각 export → `source_blocks`에 `[session:pair]Q/A` 포맷 저장, partial은 선택 pair만 담김, `wiki_pages` 생성 확인.

**주의사항 (breaking)**

- `POST .../{session_id}/wiki`가 **요청 body 필수**로 바뀜: `{"selection_mode":"full"}` 또는 `{"selection_mode":"partial","pair_ids":[...]}`. 무 body 호출은 400.
- chat_pair provenance·append/create·pair dedup·query 링크는 pipeline(A·B) 이후. 현재는 pipeline이 새 포맷을 일반 문서로 처리하며, source page 제목이 모두 "Chat Export"로 동일해지는 한계가 있다.

## 2026-07-07

### feat: 채팅 세션 Wiki page화 (chat → wiki export)

**배경**

저장된 채팅을 검색 가능한 wiki graph에 편입하려면 채팅을 Markdown 원문 문서로 만들어 기존 문서 ingestion 파이프라인에 넣어야 한다. `llmPipeline`엔 위키 생성 전용 API가 없고 위키는 문서 ingestion(source/concept page)으로만 생성되므로, 채팅을 "문서처럼" 태우는 경로를 재사용한다. 설계는 `docs/spec/chat-to-wiki-contract.md`를 따른다.

**추가/변경된 것**

- `chat/service/ChatWikiMarkdownSerializer`(신규): 세션 + completed 메시지를 계약 §6 Markdown으로 직렬화.
- `util/SecretMasker`(신규): export 전 best-effort 비밀값 마스킹(private key 블록, `sk-`/`AKIA`/`ghp_` 등, Bearer, `key=value`).
- `chat/service/ChatWikiExportService`(신규): 권한검증 → 직렬화 → 마스킹 → 안정 content_hash(sessionId + 대화내용, `exported_at` 등 휘발성 제외) → 문서 저장/큐 등록 위임. export 시 `ChatSession.wikiExportDocumentId` 기록. 임시 `previewMarkdown`과 정식 `export` 제공.
- `document/service/DocumentService`: `createChatExportDocument` 추가(dedup → MinIO 저장 → `documents` 행(origin=chat_export) → 처리 큐 등록). `findAll`을 `findVisibleByWorkspaceId`로 바꿔 문서 목록에서 chat_export 제외.
- `document/domain/Document`: `origin` 컬럼 추가(upload/chat_export). `document/repository/DocumentRepository`: `findVisibleByWorkspaceId`(null 안전).
- `chat/service/ChatWikiExportReconciler`(신규): 파이프라인이 완료를 DB에 직접 쓰므로(백엔드 콜백 미경유), `@Scheduled`로 completed된 chat_export를 감지해 `source_of` 링크 → `ChatSession.wikiPageId` 연결.
- `chat/domain/ChatSession`: `wikiExportDocumentId` 컬럼 + 링크 도메인 메서드. `chat/controller/ChatWikiExportController`(신규): `POST .../{session_id}/wiki`(202) 및 임시 `.../wiki/preview`.
- completed 메시지가 없는 세션 export는 `EmptyChatWikiExportException`으로 400(`EMPTY_CHAT_WIKI_EXPORT`) 반환해 빈 위키 생성·불필요한 파이프라인 실행을 막는다.

**검증**

- `./gradlew test` 문서/serializer/masker 단위테스트 및 컨텍스트 배선 통과(upload 회귀 없음).
- 라이브 e2e: `POST .../wiki` → 202, `documents(origin=chat_export, status=completed)`, 파이프라인이 `wiki_pages(source, active)` + concept + `document_wiki_links(source_of)` 생성, reconciler가 `ChatSession.wikiPageId`를 자동 연결함을 확인.

**주의사항 / 남은 작업**

- **재-export(재위키화)는 미지원** — 추후 과제. 내용이 바뀐 재-export는 옛 위키가 graph에 남고 reconciler가 새 export를 연결하지 못하는 gap이 있어, 구현 시 함께 해결해야 한다.
- 마스킹은 정규식 best-effort라 오탐/누락 가능. 위키 공유·공개 단계에서 재설계 필요.
- 초기 설계의 message↔block 매핑 테이블/heading 앵커는 계약 미규정·미사용이라 제외했다(source_blocks로 충분).

## 2026-07-04

### feat: wiki 조회를 workspace 경로 기반으로 격리 (Scope B)

**배경**

파이프라인이 실제 workspace_id를 wiki_pages에 기록하게 됐지만(직전 커밋), `WikiController`(`/api/wiki`)의 graph/detail 조회가 `wikiPageRepository.findAll()`로 **전 workspace 페이지를 반환**해 다른 workspace의 wiki가 그대로 새어 나오던 상태였다. 실측으로 두 workspace(`ws_7baa...` 4개, `local-workspace` 3개)의 페이지가 `GET /api/wiki/graph` 한 번에 7개 모두 반환되는 것을 확인했다.

**추가/변경된 것**

- `wiki/controller/WikiController.java`: base path를 `/api/wiki` → **`/api/workspaces/{workspace_id}/wiki`** 로 변경(문서·채팅 API와 동일한 경로 규약). 각 엔드포인트가 `@PathVariable workspace_id`와 `@AuthenticationPrincipal userId`를 받는다. 이로써 `/api/workspaces/**` 규칙에 걸려 인증이 필수가 된다.
- `wiki/service/WikiService.java`: `WorkspaceMemberRepository`를 주입해 `verifyWorkspaceOwnership`(멤버십 검증) 추가. `findGraph`/`findById`/`rename`이 `(workspaceId, userId)`를 받아 소유권 검증 후 workspace scope로 조회. graph는 `findAllByWorkspaceId`로 페이지를 가져오고, `wiki_page_links`는 workspace 컬럼이 없으므로 해당 page id 집합 안에서 양 끝점이 모두 존재하는 링크만 포함. detail/rename은 `findByIdAndWorkspaceId`로 다른 workspace 페이지 접근을 404 처리.
- repository: `WikiPageRepository.findAllByWorkspaceId`/`findByIdAndWorkspaceId`, `WikiPageLinkRepository.findAllByIdFromPageIdIn` 추가.

**검증**

- `./gradlew test` 전체 통과.
- 라이브 e2e(두 workspace 데이터 공존 상태): `GET /api/workspaces/{ws_7baa}/wiki/graph`가 `ws_7baa` 페이지 4개만 반환(이전엔 7개), 옛 경로 `/api/wiki/graph`는 404, 인증 없으면 401, 다른 workspace 페이지 상세 요청은 404, 내 페이지는 200을 확인.

**주의사항**

- **API 경로가 바뀌는 breaking change다.** 프론트엔드가 호출하는 `/api/wiki/graph` 등을 `/api/workspaces/{workspace_id}/wiki/...`로 바꾸고 인증 헤더를 붙여야 한다(`docs/backlog/issue-2026-07-02.md` "프론트엔드 workspace-scoped API 마이그레이션"과 연결).
- 페이지 필터링은 문서 API와 동일하게 멤버십 검증 후 **workspace_id 기준**이다(공유 workspace 대비). 현재 MVP는 owner 1인 구조라 user 단위와 동일하게 동작한다.

### feat: 파이프라인 실행 요청에 실제 user_id/workspace_id 전달

**배경**

`DocumentProcessingRequester`가 `/pipeline/runs`에 `{document_id, log_callback_url}`만 보내, llmPipeline이 `wiki_pages`를 DDL 기본값 `local-user`/`local-workspace`로 기록했다. wiki_pages 스키마·삭제는 workspace scope로 맞췄지만(2026-07-04 이전 커밋), 실제 workspace 값이 전달되지 않아 **데이터 레벨 격리가 안 되고 모든 문서의 wiki가 `local-workspace`로 섞이던** 상태를 e2e로 확인했다(`docs/backlog/issue-2026-07-02.md` B3).

**추가/변경된 것**

- `document/repository/DocumentProcessingRequester.java`: JSON 문자열 수동 조립을 `PipelineRunRequest` record로 교체(escaping 취약점 제거). `request(documentId, userId, workspaceId, callbackUrl)`로 시그니처를 바꿔 `user_id`/`workspace_id`를 body에 포함.
- `document/service/DocumentService.java`: `doRequestProcessing`이 문서를 로드해 그 문서의 `userId`/`workspaceId`를 요청에 전달. 문서가 이미 삭제됐으면 조용히 반환.

**검증**

- `./gradlew test` 전체 통과.
- 라이브 e2e: `ws_7baa...` 워크스페이스에 문서 업로드→인제스트 후, 생성된 source/concept wiki_pages가 모두 실제 `user_id=user_6fdd...`, `workspace_id=ws_7baa...`로 기록됨을 확인(이전엔 `local-user`/`local-workspace`).

**주의사항**

- `source_page_mode`/`concept_page_mode`/`provider`는 파이프라인 기본값(auto/auto/upstage)이 합리적이고, 명시하면 백엔드에 하드코딩이 되므로 이번엔 전달하지 않았다. 필요 시 별도 config로 추가한다.
- 이제 데이터 레벨 workspace 격리가 되므로, graph/detail 조회를 요청 workspace로 필터링하는 후속 작업(Scope B)이 의미를 갖는다.

### fix: documents.error_message를 TEXT로 변경해 긴 에러 저장 시 크래시 제거

**배경**

`DocumentProcessingWorker`가 파이프라인 실패를 문서에 기록할 때 `documents.error_message`(varchar(255))에 255자를 넘는 에러 문자열을 넣어 `value too long for type character varying(255)`(DataIntegrityViolationException)로 워커가 크래시하고, 문서가 `failed`로도 전이되지 못한 채 `processing`에 갇히는 버그를 e2e 검증 중 확인했다. llmPipeline DDL도 `documents.error_message`를 `TEXT`로 정의(및 write 시 truncate)하고 있어, Spring 엔티티가 varchar(255)로 잡던 것이 실제 의도와 어긋난 상태였다.

**추가/변경된 것**

- `document/domain/Document.java`: `error_message` 컬럼을 `@Column(columnDefinition = "TEXT")`로 변경. 새로 생성되는 DB에서는 TEXT로 만들어진다.

**검증**

- `./gradlew test` 전체 통과.
- 기존 dev DB는 `ddl-auto=update`가 컬럼 타입을 바꾸지 못하므로 `ALTER TABLE documents ALTER COLUMN error_message TYPE TEXT`로 직접 넓혔고(무손실), 400자 문자열 UPDATE가 성공하는 것을 확인(이전엔 여기서 `value too long` 발생).

**주의사항**

- 다른 기존 DB에도 동일한 수동 ALTER가 필요하다(`ddl-auto=update`는 varchar→text 타입 변경을 반영하지 않음). 새로 생성하는 DB는 엔티티 기준으로 TEXT가 된다.

### fix: 문서 삭제가 opaque wiki page id에 대응하고 하위 데이터를 명시 삭제

**배경**

llmPipeline이 wiki page id를 옛 의미형(`source:{documentId}`, `concept:{slug}`)에서 opaque UUID(`wiki_page_{uuid}`)로 바꾸면서(2026-07-02 커밋), `DocumentService.deleteInternal()`이 source page를 `wikiPageRepository.findById("source:" + documentId)`로 찾던 코드가 조용히 깨졌다 — 실제 id는 UUID라 항상 못 찾아 문서 삭제 시 source wiki page가 고아로 남았다. 추가로 이 로직은 `source_blocks`/`document_wiki_links`/`wiki_page_links` 정리를 DB `ON DELETE CASCADE`에 의존했는데, 로컬 dev DB를 새로 만들면 이 테이블들을 Spring이 먼저 varchar로 생성해 CASCADE FK가 걸리지 않아(그 FK는 llmPipeline DDL에만 정의됨) 삭제 후 고아가 남는 것을 실측으로 확인했다.

**추가/변경된 것**

- `document/service/DocumentService.java`:
  - source page를 id 문자열이 아니라 `document_wiki_links`의 `source_of` 링크로 찾아 삭제(opaque UUID 대응). concept page는 공유 자원이라 삭제하지 않는다.
  - `source_blocks`(document_id), `document_wiki_links`(document_id)를 명시적으로 삭제. `wiki_page_links`는 link_type이 아니라 삭제되는 source page id(from/to)로 좁혀 삭제.
  - `WikiPageLinkRepository`를 새로 주입.
- repository에 delete 메서드 추가: `SourceBlockRepository.deleteByIdDocumentId`, `DocumentWikiLinkRepository.deleteByIdDocumentId`, `WikiPageLinkRepository.deleteByIdFromPageIdOrIdToPageId`.
- `DocumentServiceBlocksTest`: 생성자 변경에 맞춰 `WikiPageLinkRepository` mock 추가.

**검증**

- `./gradlew test` 전체 통과.
- 라이브 e2e: 문서 업로드→인제스트(source 1 + concept 3 + source_blocks 7 + document_wiki_links 4 + wiki_page_links 3)→삭제 후 `documents`/source page/`source_blocks`/`document_wiki_links`/`wiki_page_links` 모두 0, concept page 3개는 유지됨을 확인.

**주의사항**

- DB CASCADE 대신 앱 레벨 명시 삭제를 택한 이유: 현재 스키마 소유권이 Spring/llmPipeline 사이에 엉켜 있어(varchar vs TEXT, 생성 순서에 따라 CASCADE FK 유무가 갈림) CASCADE 정석화는 소유권 정리(2026-07-03 "documents/wiki_pages CASCADE 보류")와 함께 다뤄야 한다. 문서 삭제는 현재 Spring 경로로만 일어나므로 앱 레벨 정리로 충분하다.
- `wiki_embedding_units`/`wiki_page_embeddings`는 llmPipeline 전용(Spring 레포 없음)이고 현재 비어 있어 이번 정리 범위에서 제외했다. 임베딩 저장 흐름이 붙으면 별도 정리가 필요하다.

### fix: wiki_pages 엔티티를 llmPipeline의 workspace scope에 정렬

**배경**

llmPipeline(`postgres_wiki_ingestion_repository.py`)은 `wiki_pages`를 `user_id`/`workspace_id` 컬럼과 `(user_id, workspace_id, page_type, slug)` scope unique index(`uq_wiki_pages_workspace_type_slug`)로 관리하도록 바뀌었는데, Spring `WikiPage` 엔티티는 옛 전역 unique `(page_type, slug)`를 선언하고 `workspace_id`를 매핑조차 하지 않아 실제 DB와 어긋나 있었다. 이 불일치로 (1) `ddl-auto=update`가 전역 제약을 심으려다 충돌/부팅 실패, (2) Spring이 workspace 단위 격리를 할 수 없었다(`docs/backlog/issue-2026-07-02.md` B1 / "Wiki 격리 미구현").

**추가/변경된 것**

- `wiki/domain/WikiPage.java`: `user_id`/`workspace_id` 컬럼 매핑과 getter 추가. `@UniqueConstraint`를 DB와 동일하게 `uq_wiki_pages_workspace_type_slug (user_id, workspace_id, page_type, slug)`로 교체.
- `wiki/repository/WikiPageRepository.java`: `findByPageTypeAndSlug` → `findByUserIdAndWorkspaceIdAndPageTypeAndSlug`.
- `wiki/service/WikiService.java`: rename slug 충돌 검사를 페이지 자신의 `userId`/`workspaceId` scope 안에서 수행.

**검증**

- `./gradlew test` 전체 통과.
- 로컬 dev DB를 새로 생성(볼륨 초기화 + pipeline 재빌드)하고 실제 기동해 `\d wiki_pages`로 확인: `user_id`/`workspace_id` 컬럼과 scoped unique만 존재하고 옛 전역 제약은 사라짐. 문서 업로드→인제스트 e2e로 `wiki_pages`에 정상 기록되는 것까지 확인.

**주의사항**

- Spring은 `wiki_pages`에 INSERT하지 않고 읽기/rename만 하며(실제 INSERT는 llmPipeline), `new WikiPage(...)` 생성 코드가 없어 생성자 시그니처는 건드리지 않았다.
- graph/detail 조회(`findAll()`)를 요청 workspace 단위로 필터링하는 작업은 `WikiController`에 workspace_id 소스가 필요하고 파이프라인이 실제 `workspace_id`를 전달해야(B3) 의미가 생겨 이번엔 제외했다. e2e에서 인제스트된 페이지의 `workspace_id`가 아직 기본값 `local-workspace`로 찍히는 것을 확인했다(B3 미구현).

### fix: PK ID를 전체 UUID로 전환해 충돌 위험 제거

**배경**

`User`/`Workspace`/`ChatSession`/`Document` 등의 PK를 `prefix_` + `UUID.randomUUID()` 앞 8자리(hex)로 생성하고 있었다. 앞 8자리만 쓰면 무작위성이 32비트로 줄어, 생일 역설 기준 같은 종류 ID가 수만 건 쌓이면 PK 충돌로 `save()`가 500 에러를 내는 잠재 버그가 있었다(`docs/backlog/issue-2026-07-03.md` "PK ID 생성 시 UUID 8자리 truncate로 인한 충돌 위험").

**추가/변경된 것**

- 아래 5개 서비스의 ID 생성에서 `.substring(0, 8)`을 제거해 전체 32자 hex(122비트 무작위성)를 사용하도록 통일했다. prefix(`user_`/`ws_`/`session_`/`doc_`)는 그대로 유지.
  - `user/service/UserService.java`, `user/service/OAuthUserService.java` (`user_`)
  - `workspace/service/WorkspaceService.java` (`ws_`)
  - `chat/service/ChatSessionService.java` (`session_`)
  - `document/service/DocumentService.java` (`doc_`)
- ID 컬럼은 length 미지정(기본 VARCHAR(255))이라 32자로 길어져도 스키마 변경이 필요 없다.

**검증**

- `./gradlew test` 전체 통과. ID prefix를 검사하는 기존 `startsWith(...)` assertion은 prefix가 그대로라 영향 없음.

---

## 2026-07-03

### refactor: 워크스페이스 소유 구조를 workspace_members 테이블로 전환

**배경**

향후 워크스페이스를 여러 유저가 공유할 수 있게 하려면 `workspaces.user_id` 1:1 구조부터 바뀌어야 한다는 논의가 있었다. 이번엔 그 설계의 첫 단계만 구현한다 — 초대/제거 같은 실제 공유 기능은 아직 없고, 워크스페이스마다 owner 1명만 있는 지금과 동일한 동작을 새 테이블 구조로 재구현했다.

**추가/변경된 것**

- `WorkspaceMember` 엔티티 신규 — `(workspace_id, user_id)` 복합 PK, `role`(owner/member), `joined_at`. `@ManyToOne` + `@OnDelete(CASCADE)`로 `Workspace`/`User` 삭제 시 자동 정리되도록 구성. 합성 PK 대신 복합 PK를 선택해 8자리 UUID truncate 충돌 이슈(`docs/backlog/issue-2026-07-03.md`)를 이 테이블에서는 원천적으로 피했다.
- `Workspace.userId` 컬럼 제거. `WorkspaceRepository`의 `findByIdAndUserId`/`findAllByUserIdOrderByCreatedAtDesc` 제거.
- `WorkspaceService`: 워크스페이스 생성 시 `WorkspaceMember(role=owner)`를 함께 생성. `list`/`rename`/`delete`의 소유권 판단을 `WorkspaceMemberRepository` 기준으로 전환.
- `ChatSessionService`/`DocumentService`의 `verifyWorkspaceOwnership()`도 동일하게 `WorkspaceMemberRepository.existsByWorkspace_IdAndUser_Id`로 전환 — 소유권 검증 로직이 3곳에 중복 구현되어 있던 문제를 이번 기회에 함께 정리했다.
- 마이그레이션: `ddl-auto=update`는 "컬럼 삭제 전 데이터 백필" 같은 순서 있는 작업을 안전하게 못 해서, 로컬 개발 DB 볼륨을 초기화하는 방식으로 처리했다(운영 데이터 없음).

**검증**

- `./gradlew test` 전체 통과 (116개).
- `@EmbeddedId` + `@ManyToOne` 조합에서 Spring Data가 `workspaceId`/`userId`를 단일 프로퍼티로 못 찾는 문제 발생 — 이전 `ChatMessage.sessionId` 때와 동일한 패턴이라 언더스코어 문법(`existsByWorkspace_IdAndUser_Id`)으로 해결했다.
- 볼륨 초기화 후 백엔드 재기동 → `\d workspaces`/`\d workspace_members`로 스키마 확인(user_id 컬럼 제거, 복합 PK + 양쪽 FK CASCADE 확인) → 이메일 회원가입 → 자동 생성된 워크스페이스가 `workspace_members`에 `role=owner`로 저장되는지 확인 → 로그인 → 워크스페이스 목록 조회 → 문서 업로드 → 채팅 세션 생성까지 curl로 전 구간 재검증.

**주의사항**

- 이번 변경은 owner 1명만 존재하는 상태까지만 구현했다. 실제 멤버 초대/제거, role 기반 권한 분기(예: rename/delete는 owner 전용), 채팅 세션의 유저별 프라이빗 처리는 별도 이슈로 남겨뒀다.

---

### fix: bootRun이 infra/.env를 못 읽던 경로 버그 수정

**배경**

Google OAuth 로그인을 브라우저로 실제 검증하던 중, `infra/.env`에 채운 실제 Google client-id가 반영되지 않고 `dev-placeholder-client-id`만 보이는 걸 발견했다. 원인은 `backend/build.gradle`의 `bootRun.doFirst`가 `rootProject.file('infra/.env')`를 쓰고 있었는데, `backend/settings.gradle`이 `rootProject.name = 'backend'`만 선언한 단일 프로젝트 빌드라 `rootProject`가 `backend/` 디렉터리 자신을 가리켜서 실제로는 존재하지 않는 `backend/infra/.env`를 찾고 있었다. 이 세션에서 새로 생긴 버그가 아니라, `bootRun`으로 `infra/.env`를 자동 로드하는 기능이 도입된 시점부터 있었던 기존 버그다.

**추가/변경된 것**

- `backend/build.gradle`의 `bootRun.doFirst` 블록에서 `rootProject.file('infra/.env')` → `file("$projectDir/../infra/.env")`로 변경. `build.gradle`이 있는 `backend/`를 기준으로 상위(repo root)의 `infra/.env`를 가리키도록 고쳤다. `docs/local-runbook.md`, `backend/README.md`, `scripts/dev-up.sh`가 공통으로 전제하는 "`infra/.env`는 repo root 기준 단일 관리 파일"이라는 기존 정책과 동일하게 맞춘 것이다.

**검증**

- 백엔드 재기동 후 `curl -sI http://localhost:8080/oauth2/authorization/google`의 `Location` 헤더 `client_id` 파라미터가 `dev-placeholder-client-id`에서 실제 Google client-id로 바뀐 것을 확인.

**주의사항**

- 이 버그로 인해 그동안 `./gradlew bootRun`으로 실행할 때 `infra/.env`의 값이 사실상 한 번도 실제로 반영된 적이 없었다. 지금까지 "동작한 것처럼 보였던" 이유는 `application.properties`의 기본값이 로컬 Docker 인프라 설정과 우연히 일치했기 때문이다.

---

### fix: /api/** 요청에 CORS 설정 추가

**배경**

Google OAuth 로그인 흐름을 브라우저로 실제 검증하던 중, 백엔드에 CORS 설정이 전혀 없다는 걸 발견했다. 지금은 프론트엔드가 없어서 안 드러났지만, 프론트엔드(`localhost:3000`)가 fetch/XHR로 백엔드(`localhost:8080`)의 `/api/auth/oauth/exchange` 등을 호출하는 순간 브라우저가 차단하는 구조였다.

**추가/변경된 것**

- `SecurityConfig`에 `CorsConfigurationSource` 빈 추가, 필터체인에 `.cors(...)` 연결. `/api/**` 경로에 적용.
- 허용 origin은 하드코딩하지 않고 `app.cors.allowed-origins` 설정값(콤마 구분, `List<String>`)으로 뺐다. 기존 `app.oauth.frontend-redirect-uri` 패턴과 동일하게 구성.
- `application.properties`에 `app.cors.allowed-origins=${CORS_ALLOWED_ORIGINS:http://localhost:3000}` 추가.
- `infra/.env.example`에 `CORS_ALLOWED_ORIGINS=http://localhost:3000` 추가.
- 허용 HTTP 메서드는 실제 컨트롤러에서 쓰는 것만 포함: `GET, POST, PATCH, DELETE, OPTIONS`.

**검증**

- `./gradlew compileJava` 통과.
- 관련 슬라이스 테스트(`SecurityConfig`를 `@Import`하는 `AuthControllerTest`, `WorkspaceControllerTest`, `DocumentControllerTest`, `QueryRunControllerTest`, `QueryControllerTest`, `ChatSessionControllerTest`) 전부 통과.
- 백엔드 재기동 후 `curl -X OPTIONS`로 preflight 요청 시 `Access-Control-Allow-Origin: http://localhost:3000` 헤더 확인.
- `Origin: http://localhost:3000`을 붙인 실제 요청(`GET /api/workspaces`)에서도 CORS 헤더가 정상적으로 붙는 것 확인(응답 자체는 인증 필요라 401, CORS 차단은 아님).
- 기존 Google OAuth 리다이렉트(`/oauth2/authorization/google`)가 CORS 설정 추가 후에도 동일하게 동작하는 것 재확인.

**주의사항**

- `app.cors.allowed-origins`는 콤마로 여러 origin을 넣을 수 있게 `List<String>`으로 바인딩했다. 배포 환경이 늘어나면 `CORS_ALLOWED_ORIGINS` 값에 콤마로 추가하면 된다.

---

### refactor: chat_sessions 하위 리소스 삭제를 DB FK ON DELETE CASCADE로 전환

**배경**

직전 커밋에서 `ChatSessionService`가 세션 삭제 시 `chat_messages`/`chat_message_references`/`chat_message_related_pages`를 애플리케이션 코드로 직접 정리하도록 구현했다. `documents`, `wiki_pages`는 llmPipeline(Python)이 DDL을 직접 소유해서 FK를 걸려면 스키마 소유권 조율이 필요하지만, `chat_sessions`/`chat_messages`/`chat_message_references`/`chat_message_related_pages`는 전부 Spring 전용 테이블이라 이 관계만 먼저 DB 레벨 CASCADE로 전환했다. `documents`/`wiki_pages` 쪽 FK 전환은 별도로 남겨둔다 (`docs/backlog/issue-2026-07-03.md` 참고).

**추가/변경된 것**

- `ChatMessage.sessionId`(String) → `@ManyToOne ChatSession session` + `@OnDelete(action = OnDeleteAction.CASCADE)`로 전환.
- `ChatMessageReference.chatMessageId`, `ChatMessageRelatedPage.chatMessageId`도 동일하게 `@ManyToOne ChatMessage chatMessage` + `@OnDelete(CASCADE)`로 전환. `getChatMessageId()` 등 기존 getter는 유지(내부적으로 연관 엔티티의 id를 반환).
- Hibernate `ddl-auto=update`가 위 매핑을 보고 실제 FK 제약(`ON DELETE CASCADE`)을 생성한다. Flyway 등 별도 마이그레이션 도구 도입 없이 처리했다.
- `ChatSessionService.delete()`/`deleteAllByWorkspaceId()`에서 메시지/참조/관련페이지를 직접 지우던 코드를 제거 — 이제 `chatSessionRepository.delete(session)` 한 줄이면 DB가 나머지를 cascade한다.
- `QueryService`가 메시지 생성 전에 `ChatSession` 엔티티를 먼저 조회하도록 변경(연관관계 설정에 필요). 세션이 존재하지 않으면 `ChatSessionNotFoundException`을 던진다.
- 리포지토리 파생 쿼리 메서드명을 중첩 프로퍼티 경로로 변경: `findAllBySessionIdOrderByCreatedAtAsc` → `findAllBySession_IdOrderByCreatedAtAsc`, `findAllByChatMessageIdIn` → `findAllByChatMessage_IdIn` (Spring Data가 변경 전 이름을 단일 프로퍼티로 오인해 매핑 실패했다).
- 테스트 편의를 위해 `TestcontainersConfiguration`을 package-private → public으로 변경.

**검증**

- `./gradlew test` 통과 (116개).
- `ChatSessionCascadeDeleteIntegrationTest` 신규 추가 — Mockito 단위 테스트로는 실제 FK 동작을 확인할 수 없어, Testcontainers Postgres에 실제로 세션을 저장하고 삭제한 뒤 메시지/참조/관련페이지가 DB에서 사라졌는지 직접 검증한다.
- `BackendApplicationTests`(전체 context 로드, 실제 Postgres 대상)가 통과해 Hibernate가 FK DDL을 문제없이 생성함을 확인했다.

---

### fix: 워크스페이스 삭제 시 소속 문서/채팅 세션 CASCADE 삭제

**배경**

커밋 리뷰 중 `WorkspaceService.delete()`가 Workspace row만 지우고 소속 documents/chat_sessions는 그대로 남기는 걸 확인했다. DB에 `workspace_id` FK CASCADE 제약이 없어서(Spring이 plain VARCHAR 컬럼으로만 관리, JPA 연관관계 미사용), 워크스페이스를 지우면 고아 데이터가 남는 상태였다.

**추가/변경된 것**

- `DocumentService`: 기존 `delete()`의 실제 삭제 로직을 `deleteInternal(Document)`로 추출하고, 워크스페이스 소속 문서를 전부 정리하는 `deleteAllByWorkspaceId(workspaceId)` 추가 (MinIO 오브젝트, source wiki page 정리 로직 재사용).
- `ChatSessionService`: 세션 삭제 시 딸린 `chat_messages`/`chat_message_references`/`chat_message_related_pages`까지 함께 삭제하도록 `deleteInternal(ChatSession)` 추가, 워크스페이스 소속 세션 전체를 정리하는 `deleteAllByWorkspaceId(workspaceId)` 추가.
- `ChatMessageReferenceRepository`, `ChatMessageRelatedPageRepository`에 `deleteAllByChatMessageIdIn` 추가.
- `WorkspaceService.delete()`가 workspace 삭제 전에 `documentService.deleteAllByWorkspaceId()`, `chatSessionService.deleteAllByWorkspaceId()`를 호출하도록 변경 (같은 트랜잭션).

**검증**

- `./gradlew test` 통과 (세션 삭제 시 메시지/참조 함께 삭제, 워크스페이스 삭제 시 문서·세션 전체 cascade, 소유권 실패 시 cascade 미실행 케이스 포함).

**주의사항**

- `wiki_pages`는 여전히 workspace_id가 없어 이번 CASCADE 대상에서 제외됨 (`docs/backlog/issue-2026-07-02.md` 참고). source wiki page는 문서별 삭제 로직(`deleteInternal`)에서 기존과 동일하게 document_id 기준으로 정리된다.

---

## 2026-07-02

### feat: ChatSession 도입 및 채팅 API workspace 격리

**배경**

`GET /api/chat/messages`가 session/workspace 개념 없이 시스템 전체의 모든 채팅 메시지를 하나의 글로벌 로그로 반환하고 있었다 (다른 사용자의 대화가 그대로 노출되는 상태). ERD에 정의된 `chat_sessions` 테이블이 아예 없었고, `chat_messages`에도 `session_id`/`pair_id`/`wiki_page_id` 컬럼이 없었다.

**추가/변경된 것**

- `ChatSession` 엔티티(`session_{UUID}`, workspace_id/user_id/title/context_summary/last_message_at/wiki_page_id) + repository + `ChatSessionService` 추가.
- 워크스페이스당 세션 최대 10개 제한. 초과 시 `POST` 요청을 409로 거부(자동 삭제하지 않음 — 프론트가 사용자에게 기존 세션 삭제를 요청해야 함).
- `ChatMessage`에 `session_id`(필수), `pair_id`(user/assistant 쌍 식별, 필수), `wiki_page_id`(nullable) 컬럼 추가.
- `ChatController`(글로벌 조회) 제거, `ChatSessionController`(`/api/workspaces/{workspace_id}/chat/sessions`)로 대체: 세션 생성/목록/삭제, 세션별 메시지 조회(`GET /{session_id}/messages`).
- `QueryService.query()`가 `sessionId`를 받아 메시지에 스탬프하고, 질의 성공/실패와 무관하게 세션의 `last_message_at`을 갱신하도록 변경.
- 질의 API를 세션 하위로 이동: `POST /api/workspaces/{workspace_id}/chat/sessions/{session_id}/query`(동기), `.../query/runs`(비동기 run 시작)로 통합. `QueryRunController`는 `request_id` 기준 polling/SSE/callback(`GET /api/query/runs/{id}`, `/events`, `/events/callback`)만 남기고 flat 경로 유지 — 이 endpoint들은 이미 발급된 request_id로 접근하는 후속 조회라 워크스페이스 인증을 다시 요구하지 않음.

**검증**

- `./gradlew test` 통과. 세션 생성/제한 초과/소유권 검증, 메시지 조회 소유권 검증, 동기/비동기 질의 endpoint 인증 여부 테스트 포함.

**주의사항**

- `chat_messages`에 `session_id`/`pair_id`가 NOT NULL로 추가됐다. `ddl-auto=update`는 기존 row가 있는 테이블에 NOT NULL 컬럼을 추가하지 못하므로, 기존 로컬 DB에 채팅 데이터가 남아있다면 볼륨을 초기화해야 한다(`docs/local-runbook.md` 참고). Document의 `workspace_id`/`user_id` 추가도 동일한 제약이 있다.
- Wiki는 여전히 workspace 미연동 상태다 (`docs/backlog/issue-2026-07-02.md` 참고).

---

### feat: Document API에 workspace 소유권 연동

**배경**

User/Workspace/Auth 기반을 구현한 뒤, 기존 documents API가 로그인·워크스페이스와 전혀 연결되어 있지 않던 부분을 연동했다. `wiki_pages`는 실제 row 생성 주체가 Spring Boot가 아니라 llmPipeline(Python)이라 훨씬 큰 범위의 작업으로 확인되어 이번 단계에서는 제외했다. 상세 내용은 `docs/backlog/issue-2026-07-02.md` 참고.

**추가/변경된 것**

- `Document` 엔티티에 `workspace_id`, `user_id` 컬럼 추가.
- `DocumentRepository`에 `findAllByWorkspaceId`, `findByIdAndWorkspaceId` 추가.
- `DocumentService`의 모든 사용자용 메서드가 workspace 소유권을 먼저 검증(`WorkspaceRepository.findByIdAndUserId`)하도록 변경. 소유하지 않은 workspace_id를 넘기면 `WorkspaceNotFoundException`(404).
- 사용자용 `DocumentController`를 `/api/documents/*` → `/api/workspaces/{workspace_id}/documents/*`로 이동.
- llmPipeline이 호출하는 콜백 endpoint(`PATCH /api/documents/{id}/status`, `POST /api/documents/{id}/pipeline-events`)는 workspace_id를 알지 못하므로 `DocumentPipelineController`로 분리해 기존 경로(`/api/documents/{id}/...`) 그대로 유지.

**검증**

- `./gradlew test` 통과 (workspace 소유권 검증, 미소유 workspace 404, 미인증 401 케이스 포함).

---

### feat: 이메일 회원가입 API 추가

**배경**

MVP는 로그인 없이 시작했지만, 문서·워크스페이스·채팅을 사용자별로 격리 관리하려면 인증 체계가 필요합니다. `docs/spec/Fruition_MVP_Erd.md` ERD를 기준으로 user, workspace, 인증 기능을 순차 구현하기로 하고 그 첫 단계로 이메일 회원가입을 추가했습니다.

**추가/변경된 것**

- Spring Security 의존성 추가, `BCryptPasswordEncoder` 기반 `SecurityConfig` 골격 추가(현재는 모든 요청 permitAll, 이후 인증 필터 도입 시 전환 예정).
- `User` 엔티티/repository, 회원가입 API(`POST /api/auth/signup`) 추가. displayName은 이메일 앞 3글자로 자동 설정, 비밀번호는 BCrypt 해시로 저장.

**검증**

- `./gradlew test` 통과.
- Spring Security 의존성 도입으로 기존 `@WebMvcTest` 슬라이스 테스트(`DocumentControllerTest`, `QueryRunControllerTest`)가 403으로 깨지는 회귀를 발견해 `SecurityConfig` import로 수정.

---

### feat: JWT 로그인/토큰 재발급/로그아웃 API 추가

**배경**

회원가입만으로는 인증된 API 호출이 불가능해, 이메일/비밀번호 로그인과 JWT 기반 인증을 이어서 구현했습니다.

**추가/변경된 것**

- JJWT(0.12.6) 의존성 추가.
- `UserRefreshToken` 엔티티(원문 대신 SHA-256 해시로 저장) + repository.
- `JwtTokenProvider`(access token 발급/검증, HS256), `JwtAuthenticationFilter`(Authorization 헤더 검증 후 SecurityContext에 인증 주입).
- `POST /api/auth/login`, `POST /api/auth/refresh`(기존 refresh token 폐기 + 새 토큰쌍 발급, 회전 방식), `POST /api/auth/logout`, `GET /api/auth/me` 추가.
- `SecurityConfig`: JWT 필터 연결, `/api/auth/me`만 인증 필요로 전환, 미인증 요청에 403 대신 401을 반환하도록 `AuthenticationEntryPoint` 설정.

**검증**

- `./gradlew test` 통과 (로그인 성공/실패, refresh 회전/만료/미존재, 로그아웃, me 인증 여부 케이스 포함).

---

### feat: Workspace CRUD 및 회원가입 시 첫 워크스페이스 자동 생성

**배경**

문서·wiki·채팅을 사용자별로 격리 관리하려면 워크스페이스 단위가 필요합니다. 로그인 기반이 갖춰졌으니 이어서 워크스페이스 CRUD와, 가입 직후 바로 쓸 수 있는 기본 워크스페이스 자동 생성을 구현했습니다.

**추가/변경된 것**

- `Workspace` 엔티티(`ws_{UUID}`)/repository, CRUD API(`POST/GET/PATCH/DELETE /api/workspaces`) 추가. user_id는 요청 바디가 아니라 JWT 인증 정보로만 결정하고, 소유하지 않은 워크스페이스는 404로 응답.
- `UserService.signup()`이 유저 생성 직후 같은 트랜잭션에서 `WorkspaceService.createDefault(userId, displayName)`을 호출해 `"{displayName}의 워크스페이스"` 이름으로 첫 워크스페이스를 자동 생성.
- `SecurityConfig`에 `/api/workspaces/**` 인증 필요 규칙 추가.

**검증**

- `./gradlew test` 통과 (워크스페이스 생성/목록/이름변경/삭제, 소유권 검증, 회원가입 시 기본 워크스페이스 생성 케이스 포함).

---

### feat: OAuth 소셜 로그인(Google/Naver/Kakao) 추가

**배경**

이메일/비밀번호 가입 외에 소셜 로그인 진입점을 제공하기 위해 Google/Naver/Kakao OAuth 로그인을 추가했습니다.

**추가/변경된 것**

- OAuth2 Client 의존성 추가.
- `UserOAuthAccount` 엔티티(provider + provider_user_id 복합 유니크)/repository.
- provider별 사용자 정보 파서: `GoogleOAuth2UserInfo`(평면 구조), `NaverOAuth2UserInfo`(`response` 중첩), `KakaoOAuth2UserInfo`(`kakao_account.email`, `kakao_account.profile.nickname` 중첩) + `OAuth2UserInfoFactory`. Naver/Kakao는 Spring Security 기본 provider가 아니라 `application.properties`에 authorization-uri/token-uri/user-info-uri를 직접 등록.
- `OAuthUserService`: provider+provider_user_id로 기존 연결 조회 → 없으면 이메일로 기존 유저를 찾아 연결만 추가 → 그것도 없으면 신규 유저 + 첫 워크스페이스를 함께 생성(`password_hash`는 null).
- `CustomOAuth2UserService`가 Spring Security OAuth2 로그인 훅에 `OAuthUserService`를 연결하고 내부 `userId`를 인증 principal로 노출.
- 1회용 code 교환 방식으로 토큰 발급: `OAuthExchangeCodeStore`(메모리, 60초 TTL) + `OAuth2AuthenticationSuccessHandler`(로그인 성공 시 프론트로 `?code=xxx` redirect)/`OAuth2AuthenticationFailureHandler`(`?error=oauth_failed` redirect) + `POST /api/auth/oauth/exchange`.
- `SecurityConfig`: `oauth2Login()` 연결. OAuth2 로그인 redirect 흐름에 세션이 필요해 세션 정책을 STATELESS에서 IF_REQUIRED로 변경(기존 미사용이던 `spring-session-jdbc`가 이제 실제로 쓰임).

**검증**

- `./gradlew test` 통과. Testcontainers 기반 전체 context 로드 테스트(`BackendApplicationTests`)도 OAuth2 client placeholder 설정으로 정상 기동 확인.

**주의사항**

- Google/Naver/Kakao client-id/secret은 dev placeholder 기본값입니다. 실제 OAuth 로그인은 `infra/.env`에 실제 값을 채운 뒤 동작합니다.
- documents/wiki_pages/chat_sessions에는 아직 `workspace_id`/`user_id` 연동이 되어 있지 않아 다음 단계에서 진행할 예정입니다.

---

## 2026-06-29 (3)

### feat: 여러 문서 동시 업로드 시 pipeline 처리 순서 보장 — DB 기반 처리 큐 도입

**배경**

프론트에서 파일을 여러 개 동시에 업로드하면 각 업로드 요청이 병렬로 처리되어 pipeline run이 동시에 여러 개 실행됐습니다.
llmPipeline 내부에 전역 큐나 단일 worker 제한이 없어 처리 순서와 완료 순서가 보장되지 않았습니다.

**추가/변경된 것**

- `document_processing_queue` 테이블 추가. 컬럼: `id`, `document_id`(UNIQUE), `created_at`, `status`(`pending`|`processing`).
- `DocumentProcessingQueue` 엔티티 + `DocumentProcessingQueueRepository` 추가.
- `DocumentProcessingWorker` 추가. `@Scheduled(fixedDelay=2000)`로 `pending` 항목을 `created_at` 오름차순으로 하나씩 꺼내 pipeline 요청을 순차 실행합니다.
- `@PostConstruct`에서 서버 재시작 시 `processing` 상태로 stuck된 항목을 `pending`으로 리셋합니다.
- `DocumentService.requestProcessingAfterCommit()`이 pipeline을 즉시 호출하는 대신 queue에 INSERT하도록 변경했습니다.
- `DocumentService.delete()`가 문서 삭제 시 queue 항목도 함께 제거합니다.

**주의사항**

- 서버 인스턴스가 여러 개인 환경에서는 `pending → processing` 전환의 원자성을 보장하지 않습니다. 현재 로컬 단일 인스턴스 기준 구현입니다.

---

## 2026-06-29 (2)

### feat: 문서 삭제 API 추가 — DELETE /api/documents/{id}

**배경**

프론트의 삭제 메뉴가 로컬 tree 상태만 제거하고 backend API를 호출하지 않아 새로고침하면 문서가 다시 나타났습니다.

**추가/변경된 것**

- `DELETE /api/documents/{document_id}` endpoint 추가. 성공 시 `204 No Content`.
- 삭제 범위: source wiki page, MinIO 원본/추출 텍스트 오브젝트.
- DB CASCADE로 자동 처리: `source_blocks`, `document_wiki_links`, `wiki_page_links`, `wiki_page_embeddings`, `wiki_embedding_units`.
- concept wiki page는 여러 문서 공유 가능하므로 삭제 제외.
- MinIO 오브젝트 삭제는 DB commit 이후 실행. 실패 시 경고 로그만 남기고 204 반환.
- `processing` 상태 문서도 삭제 허용. 이후 pipeline callback은 404 무시.

---

## 2026-06-29

### feat: 문서 처리 상태 신뢰성 개선 — pipeline_run_id 추적 및 processing_state 추가

**배경**

`documents.status=processing`만으로는 pipeline worker가 실제로 살아서 처리 중인지 알 수 없었습니다.
pipeline 요청 실패, 장시간 무응답 상태를 구분할 방법이 없어 프론트엔드에서 신뢰도 있는 상태 표시가 불가능했습니다.

**추가/변경된 것**

- `Document` 엔티티에 `pipeline_run_id`, `processing_started_at`, `processing_updated_at` 필드를 추가했습니다.
- `markPipelineStarted()`, `markProcessingHeartbeat()`, `markProcessingFailed()` 메서드를 추가해 상태 변경을 엔티티에서 관리합니다.
- `DocumentProcessingRequester.request()`가 pipeline 요청 성공 시 `PipelineRunResponse`를 반환하고, 실패 시 예외를 throw하도록 변경했습니다. callback URL도 요청 body에 포함합니다.
- `DocumentService.doRequestProcessing()`을 분리해 pipeline 요청 성공 시 `pipeline_run_id`를 저장하고, 실패 시 `status=failed`로 즉시 기록합니다.
- `POST /api/documents/{document_id}/pipeline-events` endpoint를 추가했습니다. llmPipeline의 `PipelineLog.emit()`이 단계마다 이 URL로 POST하면 `processing_updated_at`이 갱신됩니다.
- `DocumentListResponse`, `DocumentDetailResponse`에 `pipeline_run_id`, `processing_state` 필드를 추가했습니다.
- `processing_state` 계산 규칙: `pipeline_run_id` 없으면 `starting`, heartbeat가 60초 이상 없으면 `stalled`, 그 외 `running`.
- `DocumentProcessingState` enum(`starting/running/stalled/completed/failed`)을 추가했습니다.

**주의사항**

- `spring.jpa.hibernate.ddl-auto=update`로 개발 환경에서는 컬럼이 자동 추가됩니다. 공유 DB 환경은 별도 migration 필요.
- llmPipeline의 `log_callback_url` 기능은 이미 구현되어 있어 callback URL을 전달하면 자동으로 heartbeat가 발송됩니다.

---

## 2026-06-20

### feat: Query run 비동기 처리 및 SSE 진행상황 중계 (POST /api/query/runs)

**배경**

기존 `POST /api/query`는 pipeline 처리가 끝날 때까지 응답을 기다리는 동기 방식이라, 사용자가 질의 처리 중 실제 진행 상황(`query_started`, `retrieval_scored` 등)을 확인할 수 없었습니다. `dev`에 먼저 병합된 pipeline 커밋이 `request_id`/`log_callback_url`을 받아 요청별로 동적 callback publisher를 생성하도록 지원하면서, 백엔드도 이 callback을 수신해 SSE로 중계할 구조가 필요했습니다.

**추가/변경된 것**

- `POST /api/query/runs` — query run 생성, 비동기로 pipeline 호출을 시작하고 즉시 `{request_id, status}` 반환 (202)
- `GET /api/query/runs/{requestId}/events` — SSE 구독. callback으로 들어온 event를 `sequence`/`received_at`과 함께 중계, heartbeat 전송
- `POST /api/query/runs/{requestId}/events/callback` — pipeline → backend event 수신
- `GET /api/query/runs/{requestId}` — 상태/최종 결과 조회 (SSE 연결 실패 시 polling fallback)
- `query/domain/QueryRun`, `QueryRunStatus` — 진행 상태 추적용 immutable 도메인 모델 (상태 전이마다 새 인스턴스 반환)
- `query/service/QueryRunStore` — in-memory `ConcurrentHashMap` 기반 run 저장, 완료 후 10분 TTL 자동 정리
- `query/service/QueryEventBroker` — requestId별 `SseEmitter` 구독/버퍼/heartbeat/complete 관리
- `query/service/QueryRunService` — run 생성, 전용 executor로 비동기 실행 orchestration, 만료 run 정리 스케줄러
- `query/controller/QueryRunController`, `query/dto/QueryRunCreateResponse`, `QueryRunStatusResponse`, `PipelineEventCallbackRequest` 추가
- `query/exception/QueryRunNotFoundException` + `GlobalExceptionHandler` 404 핸들러 추가
- `QueryService.query()`, `PipelineQueryRequester.query()` — `requestId`/`logCallbackUrl` overload 추가. 기존 메서드는 새 overload에 위임만 하므로 **기존 `POST /api/query` 동기 경로는 요청/응답/저장 로직 100% 동일하게 유지**
- `application.properties`/`infra/.env.example` — `app.callback.base-url`/`CALLBACK_BASE_URL` 추가. backend가 docker-compose 서비스가 아니라 호스트에서 직접 실행되는 구조라 기본값을 `http://host.docker.internal:8080`으로 설정
- `infra/compose.ai.yml` — `pipeline-api`에 `extra_hosts: host.docker.internal:host-gateway` 추가 (Docker Desktop 외 환경 호환)
- `query/config/QueryAsyncConfig` — `Clock`, 전용 `queryRunExecutor`(`ThreadPoolTaskExecutor`) bean 추가, `BackendApplication`에 `@EnableScheduling` 추가
- `docs/spec/backend-query-events-api.md`, `docs/backlog/issue-2026-06-20.md` 추가

**검증**

- `./gradlew test` 32개 전체 통과
- 로컬 전체 스택(Postgres/MinIO/pipeline-api/backend/frontend)을 직접 기동해 `POST /api/query/runs` → SSE 구독 → `query_started`~`answer_generated` 전체 단계 event를 순서대로(`sequence` 1~10) 실시간 수신 → `query.completed` 종료까지 end-to-end 확인
- 기존 `POST /api/query` 동기 경로, `GET /api/chat/messages` 저장 결과 회귀 없음 확인

---

## 2026-06-19

### feat: related_pages 별도 테이블 저장 및 채팅 조회 API 반영

**배경**

`chat_message_references`에 `related_pages`를 `reference_type`으로 섞어 저장하면 "근거 스니펫(quote)"과 "탐색된 Wiki 페이지 목록"이 하나의 테이블에 혼재됩니다. 두 개념은 쓰임새가 다르므로(`evidence_snippets` = 인용 근거, `related_pages` = "찾은 자료" 카드) 별도 테이블로 분리했습니다.

**추가/변경된 것**

- `ChatMessageRelatedPage` 엔티티 추가 (`chat_message_related_pages` 테이블)
- `ChatMessageRelatedPageRepository` 추가 (`findAllByChatMessageIdIn()` 배치 조회)
- `ChatMessageRelatedPageResponse` DTO 추가 (`wiki_page_id`, `page_type`, `title`, `slug`, `relevance_score`, `role`, `depth`, `rank`)
- `QueryService` — `relatedPageRepository` 주입, `buildRelatedPages()` 추가, `query()` 내 `relatedPageRepository.saveAll()` 호출
- `ChatMessageResponse` — `related_pages` 필드 추가 (`references` 앞)
- `ChatController` — `relatedPageRepository` 주입, `GET /api/chat/messages` 응답에 `related_pages` 포함 (배치 조회로 N+1 방지)
- `backend-mvp-erd.md` — `chat_message_related_pages` 테이블 및 관계 추가
- `QueryServiceTest` — `relatedPageRepository` mock 추가, `buildRelatedPages()` 저장 검증 추가

**검증**

- `./gradlew test --tests "fruition.query.service.QueryServiceTest"` 통과

---

### fix: buildReferences() 저장 전 reference 유효성 검증 추가

**배경**

`QueryService.buildReferences()`가 `pageId != null`인 evidence snippet을 조건 없이 저장했습니다.
이 때문에 DB에 없는 wiki_page를 참조하거나 원문 viewer에서 열 수 없는 항목이 "근거 자료"로 표시됐습니다.

**추가/변경된 것**

- `buildReferences()`에 3단계 필터 추가
  - `quote` 비공백: `snippet.text()`가 null이거나 blank면 제외
  - `wiki_pages` 존재: `WikiPageRepository.findAllById()` batch 조회 후 DB에 없는 pageId 제외
  - 원문 viewer 접근 가능: `markdownUri != null` 또는 `document_wiki_links` 연결이 있는 page만 저장
- `WikiPageRepository`, `DocumentWikiLinkRepository` 의존성 추가
- `QueryServiceTest` — 신규 의존성 Mock 추가 및 wiki page 스텁 설정

**검증**

- `./gradlew test --tests "fruition.query.service.QueryServiceTest"` 통과

---

### feat: 원본 문서 조회 API 구현 (GET /api/documents/{document_id}/original)

**배경**

프론트엔드에서 원본 문서를 클릭하면 MinIO에 저장된 raw 원본 파일이 아니라 source Wiki page를 열고 있었습니다. DB의 `documents.source_uri`를 기준으로 MinIO 객체를 스트리밍하는 엔드포인트가 없어 원본 파일을 직접 조회할 수 없었습니다.

**추가/변경된 것**

- `document/exception/DocumentOriginalNotFoundException` — document는 DB에 있지만 MinIO 객체가 없는 경우 전용 예외 추가. `DOCUMENT_NOT_FOUND`와 구분되는 `DOCUMENT_ORIGINAL_NOT_FOUND` 에러코드 반환
- `document/dto/DocumentOriginalResult` — service → controller 사이 전달용 record (`mimeType`, `filename`, `inputStream`)
- `DocumentService.getOriginal()` — `documents.source_uri`로 MinIO `getObject()` 호출 후 스트림 반환. `s3://` 형식과 plain object key 형식 모두 처리하는 `normalizeObjectKey()` 추가
- `DocumentController` — `GET /{document_id}/original` 엔드포인트 추가. `Content-Type`은 `document.mimeType` 기준, PDF/text는 `inline`, 그 외 `attachment`로 `Content-Disposition` 설정
- `GlobalExceptionHandler` — `DocumentOriginalNotFoundException` 핸들러 추가 (404, `DOCUMENT_ORIGINAL_NOT_FOUND`)

**검증**

- `./gradlew compileJava` 통과
- `QueryServiceTest` 통과

---

## 2026-06-16

### feat: Wiki page 상세 응답에 markdown 본문 포함

**배경**

프론트 원문 viewer에서 source/concept Wiki page의 실제 markdown 본문을 바로 렌더링해야 했습니다. 기존 상세 API는 `markdown_uri`만 제공해 프론트가 원문 내용을 표시할 수 없었습니다.

**추가/변경된 것**

- `WikiService.findById()` — `markdown_uri`가 가리키는 MinIO object를 읽어 `markdown` 필드로 함께 반환
- `s3://{bucket}/...` 형식과 object key 형식을 모두 처리하도록 object path 정규화 추가
- markdown 읽기 실패 시 상세 조회 자체는 유지하고 `markdown`만 비워두도록 처리

**검증**

- `./gradlew test` 통과.
- 로컬 API에서 `GET /api/wiki/pages/{wiki_page_id}` 응답에 source/concept markdown이 포함되는 것을 확인.

---

### feat: chat_messages 테이블에 error_message 컬럼 추가

**배경**
채팅 메시지 생성 시 발생하는 오류를 DB에서 직접 확인할 수 없었습니다.

**추가/변경된 것**
- `ChatMessage` 엔티티 — `error_message VARCHAR(255)` 필드 추가, 생성자에 `errorMessage` 파라미터 추가
- `ChatMessageResponse` DTO — `error_message` 응답 필드 추가 (null 시 응답에서 생략)
- `ChatController` — `ChatMessageResponse` 생성 시 `errorMessage` 매핑 추가
- `QueryService` — `ChatMessage` 생성 시 정상 흐름에서 `errorMessage=null` 전달
- `docs/spec/backend-mvp-erd.md` — `chat_messages` 테이블에 `error_message` 컬럼 반영

**검증 결과**
- 정상 흐름에서 `error_message`는 `null`로 저장되며 응답에서 생략됨

### feat: Spring 백엔드 Query API 구현 (POST /api/query)

**배경**
FastAPI 파이프라인이 제공하는 그래프 기반 자연어 질의응답을 Spring 백엔드에서 중계해야 했습니다. 기존 `QueryController`는 스텁이었으며, `QueryResponse` DTO가 pipeline 출력 형식과 불일치했습니다.

**추가/변경된 것**
- `query/service/QueryService` — FastAPI pipeline에 질의를 전달하고 응답을 변환하는 서비스 추가
- `query/repository/PipelineQueryRequester` — FastAPI `/query` 엔드포인트 HTTP 클라이언트
- `query/repository/PipelineQueryResponse` — pipeline 응답 역직렬화 DTO
- `query/exception/PipelineQueryException` — pipeline 오류 전파용 도메인 예외
- `QueryController` — `QueryService` 주입 및 스텁 제거
- `QueryResponse` — pipeline 출력 형식으로 재구성 (`HighlightedPath`, `QueryRelatedPage`, `SourceReference` DTO 제거)
- `application.properties` — `app.query.endpoint`, `app.query.timeout-seconds` 환경변수 추가
- `docs/backlog/backend-query-api.md` — Query API 구현 전 스펙 문서 추가

**주의사항**
FastAPI pipeline 주소는 `QUERY_ENDPOINT` 환경변수로 주입하며 기본값은 `http://localhost:8000/query`입니다.

---

### feat: Chat 기록 조회 API 구현 (GET /api/chat/messages)

**배경**
채팅 메시지 목록 API가 스텁으로 빈 배열을 반환하고 있었습니다. ChatMessage와 ChatMessageReference 도메인 모델을 구현해 실제 대화 이력을 반환하도록 교체했습니다.

**추가/변경된 것**
- `chat/domain/ChatMessage` — 채팅 메시지 JPA 엔티티
- `chat/domain/ChatMessageReference` — 메시지별 근거 참조 JPA 엔티티
- `chat/repository/ChatMessageRepository` — Spring Data JPA, 세션별 메시지 조회
- `chat/repository/ChatMessageReferenceRepository` — 메시지 ID 목록 기준 일괄 조회 (N+1 방지)
- `ChatController` — `ChatMessageRepository` / `ChatMessageReferenceRepository` 주입, 실제 데이터 반환
- `ChatMessageReference` DTO — `pageRole`, `rank`, `sentenceIndex` 필드 추가

---

### feat: 문서 이름 변경 API 구현 (PATCH /api/documents/{document_id}/rename)

**배경**
`docs/Fruition_MVP_API_Contract.md` 명세에 정의된 문서 이름 변경 API가 구현되지 않았습니다. `sync_source_title=true`이면 연결된 source WikiPage 제목도 함께 동기화합니다.

**추가/변경된 것**
- `document/dto/DocumentRenameRequest` — `filename`, `sync_source_title` 요청 DTO
- `document/dto/DocumentRenameResponse` — 이전 파일명, source page ref(`id`, `title`, `renamed`) 포함 응답 DTO
- `document/exception/InvalidDocumentFilenameException` — 파일명 검증 실패 예외 (400)
- `Document.rename()` — 파일명 변경 도메인 메서드 추가
- `DocumentService.rename()` — 파일명 검증(1~255자, 경로 구분자 금지), source_of 링크 탐색 후 WikiPage 제목 동기화, 응답 생성
- `DocumentController` — `PATCH /{document_id}/rename` 엔드포인트 추가

---

### feat: Wiki graph source doc 참조 및 Wiki page 이름 변경 API 구현

**배경**
Wiki graph 조회 시 source 타입 노드에 원본 문서 참조가 표시되지 않는 이슈가 있었습니다. 또한 `docs/Fruition_MVP_API_Contract.md` 명세의 Wiki page 이름 변경 API가 구현되지 않았습니다.

**추가/변경된 것**
- `DocumentWikiLinkRepository.findAllByIdWikiPageIdIn()` — graph 조회 시 source 페이지 일괄 조회 (N+1 방지)
- `WikiService.buildSourceDocRefs()` — source 타입 WikiPage에 연결된 원본 문서 참조를 WikiGraphNode에 포함
- `wiki/dto/WikiPageRenameRequest` — `title`, `update_slug` 요청 DTO
- `wiki/dto/WikiPageRenameResponse` — 이전 제목/slug, slug 업데이트 여부 포함 응답 DTO
- `wiki/exception/InvalidWikiPageTitleException` — 제목 검증 실패 예외 (400)
- `wiki/exception/WikiPageSlugConflictException` — slug 중복 예외 (409)
- `WikiPage.renameTitle()`, `WikiPage.updateSlug()` — 제목/slug 변경 도메인 메서드 추가
- `WikiService.rename()` — 제목 검증, slug 재생성(`update_slug=true` 시), `page_type+slug` 중복 검사
- `WikiController` — `PATCH /pages/{wiki_page_id}/rename` 엔드포인트 추가
- `GlobalExceptionHandler` — `PipelineQueryException`, `InvalidDocumentFilenameException`, `InvalidWikiPageTitleException`, `WikiPageSlugConflictException` 핸들러 추가

**주의사항**
slug 재생성 시 소문자 변환, 공백→하이픈, 한글 유지, 연속 하이픈 정리를 적용합니다. 같은 `page_type+slug` 조합이 이미 존재하면 409로 응답합니다.

---

## 2026-06-11

### feat: Wiki 도메인 서비스 구현

**배경**

Wiki 그래프 조회 및 페이지 상세 조회 엔드포인트가 스텁으로 노출되어 있었습니다. Wiki 도메인 모델·Repository·Service를 구현해 실제 데이터를 반환하도록 교체했습니다.

**추가된 것**

- `wiki/domain/WikiPage` — Wiki 페이지 JPA 엔티티 (`id`, `title`, `slug`, `summary`, `markdownUri`, `pageType`, `status`, `createdAt`, `updatedAt`)
- `wiki/domain/WikiPageType` — enum: `CONCEPT`, `PROCESS`, `ENTITY`, `OVERVIEW`
- `wiki/domain/WikiPageStatus` — enum: `active`, `draft`, `archived`
- `wiki/domain/WikiPageNotFoundException` — 도메인 예외 (404)
- `wiki/domain/WikiPageLink` — Wiki 페이지 간 링크 JPA 엔티티 (복합키: `fromPageId` + `toPageId`)
- `wiki/domain/WikiPageLinkId` — 복합키 클래스
- `wiki/domain/DocumentWikiLink` — 문서 ↔ Wiki 페이지 연결 JPA 엔티티 (복합키: `documentId` + `wikiPageId`)
- `wiki/domain/DocumentWikiLinkId` — 복합키 클래스
- `wiki/domain/DocumentWikiRelationType` — enum: `primary_source`, `supporting`, `referenced`
- `wiki/infra/WikiPageRepository` — Spring Data JPA Repository
- `wiki/infra/WikiPageLinkRepository` — `findAllByIdFromPageId` 포함
- `wiki/infra/DocumentWikiLinkRepository` — `findAllByIdWikiPageId` 포함
- `wiki/application/WikiService` — `findGraph()` / `findById()` 구현
  - `findGraph()`: 전체 WikiPage + WikiPageLink를 nodes/edges로 변환
  - `findById()`: 페이지 조회 → 연결 문서(`source_documents`) + 연결 페이지(`related_pages`) 조합

**변경된 것**

- `WikiController` — 스텁 제거, `WikiService` 주입 및 실제 서비스 호출로 교체
- `GlobalExceptionHandler` — `WikiPageNotFoundException` 핸들러 추가 (404 `WIKI_PAGE_NOT_FOUND`)

---

## 2026-06-10

### feat: FastAPI 콜백 패턴 기반 문서 처리 상태 업데이트 (`0595937`)

**배경**

문서 업로드 후 FastAPI 파이프라인이 비동기로 파일을 처리하며, 단계마다 Spring 서버에 진행 상태를 알려야 합니다. 업로드 응답은 즉시 반환하되, 처리 진행 상황은 콜백으로 수신하는 패턴을 적용했습니다.

**추가된 것**

- `PATCH /api/documents/{document_id}/status` — FastAPI 파이프라인 콜백 수신 엔드포인트
- `DocumentStatusUpdateRequest` — 콜백 요청 DTO (`status` 필수, `extracted_text_uri` / `processed_at` / `error_message` 선택)
- `Document.updateStatus()` — JPA dirty checking으로 상태 필드 갱신 (별도 save 호출 불필요)
- `DocumentService.updateStatus()` — `@Transactional` 트랜잭션 내 상태 업데이트
- `DocumentProcessingRequester` — 업로드 직후 FastAPI에 `document_id` + `source_uri` POST, 성공/실패 응답 로깅
- `application.properties` — `app.processing.endpoint` 환경변수 추가 (기본값: `http://localhost:8001/process`)

**FastAPI 측 연동 스펙**

```
POST {PROCESSING_ENDPOINT}
Content-Type: application/json

{ "document_id": "doc_abc12345", "source_uri": "sources/documents/doc_abc12345/original" }
```

응답은 `{ "document_id": "...", "status": "..." }` 형태를 기대하며, 실패 시 서버 로그에 경고만 기록하고 업로드 응답에는 영향을 주지 않습니다.

---

### feat: MVP API 컨트롤러 및 Swagger 구성 추가 (`5fceb59`)

**배경**

`docs/Fruition_MVP_API_Contract.md` 명세 기준으로 7개 엔드포인트의 컨트롤러와 Swagger 어노테이션을 구성했습니다. Wiki / Query / Chat 도메인은 프론트엔드 연동 준비를 위해 스텁으로 먼저 노출합니다.

**추가된 것**

- `GET /api/documents` — 문서 목록 조회 (상태 polling용)
- `GET /api/documents/{document_id}` — 문서 상세 조회 (연결된 Wiki 페이지 목록 포함, 현재 빈 목록)
- `GET /api/wiki/graph` — Wiki 그래프 전체 조회 스텁 (빈 nodes/edges 반환)
- `GET /api/wiki/pages/{wiki_page_id}` — Wiki 페이지 상세 스텁 (501)
- `POST /api/query` — 자연어 질의응답 스텁 (501)
- `GET /api/chat/messages` — 채팅 메시지 목록 스텁 (빈 목록 반환)
- 전체 엔드포인트에 `@Tag`, `@Operation`, `@ApiResponse` Swagger 어노테이션 적용
- `GlobalExceptionHandler` — `@Valid` 입력 검증 오류(필드별 오류 목록) 및 `DocumentNotFoundException` 처리 추가
- `ErrorResponse` — `details` 필드(필드 오류 목록) 추가, `@JsonInclude(NON_NULL)` 적용
- `DocumentNotFoundException` — 도메인 예외 신규 추가

---

## 2026-06-09

### feat: 문서 업로드 Service / Repository 구현 (`16ce32b` ~ `c19a081`)

**추가된 것**

- `DocumentService.upload()` — SHA-256 중복 확인 → MinIO 저장 → DB 레코드 생성 → 처리 요청 순서로 구현
- `DocumentRepository` — Spring Data JPA, `findByContentHash` 포함
- `Document` JPA 엔티티 — `id`, `filename`, `mime_type`, `byte_size`, `status`, `source_uri`, `extracted_text_uri`, `content_hash`, `uploaded_at`, `processed_at`, `error_message` 필드
- `DocumentStatus` enum — `processing`, `completed`, `failed`
- `GlobalExceptionHandler` — `DuplicateDocumentException` (409), `DocumentUploadException` (500) 처리

---

## 2026-06-07

### feat: Spring Boot 백엔드 초기 세팅 (`7156846`)

**추가된 것**

- Spring Boot 3.5.x 프로젝트 초기화 (Java 21, Gradle)
- 의존성: `spring-boot-starter-web`, `spring-boot-starter-data-jpa`, `postgresql`, `minio`, `springdoc-openapi-starter-webmvc-ui`
- `DocumentController` 업로드 스텁 (`POST /api/documents`)
- `MinioConfig`, `OpenApiConfig`, `StorageProperties` 기본 설정

---

*커밋 단위 이력은 `git log` 로 확인하세요.*
