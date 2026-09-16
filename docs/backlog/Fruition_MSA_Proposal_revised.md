# Fruition MSA 전환 및 AWS 배포 제안서

> **이전 자료 안내 (2026-07-27)**: 이 문서는 ECS on Fargate와 SQS를 전제로 한 이전 제안서다. 현재 Vercel·EKS·Kafka 구조는 [Fruition AWS MSA 목표 구조](../../../../docs/Fruition_AWS_MSA_Architecture.md)를 따른다.

> **반영 현황 갱신 (2026-08-06)**: §1.2의 "현재 상태" 진단 다수가 코드에 반영되어 해소됐다. 무엇이 해소되고 무엇이 남았는지는 바로 아래 [현재 반영 현황](#현재-반영-현황-2026-08-06)이 이 문서의 진단·Phase 계획을 갱신한다. §1.2 표와 본문의 file:line 근거는 작성 시점 기록으로 남긴다.

> 작성일: 2026-07-20
> 재구성: 2026-07-24
> 개정: 2026-07-27 — 목표 구조를 3개 서비스로 축소하고, 로그인부터 AI 호출까지의 흐름을 문서의 중심으로 재구성
> 상태: Draft (반영 현황은 2026-08-06 기준)
> 기준: 현재 저장소의 `services/backend/`, `services/ai-svc/{pipeline,converter}/`, `frontend/` (구 `backend/`, `llmPipeline/`, `infra/converter/`)

---

## 현재 반영 현황 (2026-08-06)

### 한눈에 보는 현재 구조

```text
Frontend (Next.js)
    │  /api/:path* → 단일 backend URL rewrite (변경 없음)
    │  access token 만료 시 silent refresh 후 재시도        [신규]
    ▼
services/backend (Spring Boot 모놀리스 — 패키지만 access/core로 논리 분리)
    ├─ 인증: deny-by-default, JWT iss·aud 검증(HS256)      [신규]
    ├─ 인가: WorkspaceAccessGuard 단일 지점 (11곳 통합)     [신규]
    ├─ PostgreSQL (V20: 링크 테이블 3개 workspace_id 격리)  [신규]
    ├─ Redis   OAuth 교환 코드 · query run 상태 ·
    │          SSE 이벤트 replay+pub/sub 중계               [신규 — 다중 인스턴스 검증 완료]
    ├─ MinIO / S3 호환 storage
    └─ services/ai-svc/pipeline (FastAPI, 127.0.0.1:8000)
         ├─ 전 엔드포인트 X-Internal-Token 필수(fail-closed) [신규]
         ├─ 양방향 콜백에도 동일 토큰                        [신규]
         └─ 여전히 같은 PostgreSQL에 직접 write (§2.3 목표 미달)

services/ai-svc/converter (FastAPI, 127.0.0.1:8010) ── 여전히 미연결
```

### §1.2 진단 대비 해소 현황

| §1.2 진단 | 현재 |
|---|---|
| 인증 경계 없음 (`anyRequest().permitAll()`) | **해소** — deny-by-default, 공개 경로 화이트리스트 + 내부 콜백은 컨트롤러 토큰 검증 |
| JWT에 iss·aud 없음 | **해소** — 발급·검증 모두 적용 (RS256/JWKS는 access-svc 분리 시점으로 유보) |
| 멤버십 검사 8곳 복제 | **해소** — `WorkspaceAccessGuard.requireMember` 단일 지점 (실제로는 11곳이었음) |
| 역할 표기 불일치(OWNER 리터럴) | **해소** — V14에서 enum 통일 |
| 링크 테이블 workspace 격리 없음 | **해소** — V20 migration + 메모리 보정 제거, pipeline INSERT도 workspace_id 포함 |
| `/api/query/runs/**` 무인증·무스코프 | **해소** — 인증 + run의 workspace 멤버십 검사 |
| in-memory 상태(OAuth 코드·query run) → 2대에서 깨짐 | **해소** — Redis 외부화. 2-인스턴스 동시 기동으로 로그인·상태 조회·SSE 교차 중계 실검증 |
| pipeline 전 엔드포인트 무인증, 포트 공개 | **해소** — 내부 토큰 필수 + 127.0.0.1 바인딩 |
| 콜백 무인증(DocumentPipelineController 등) | **해소** — 상수시간 토큰 검증 |
| timeout 없는 AI client | **해소** — 공용 팩토리(connect 5s + 호출별 read timeout). retry·circuit breaker는 미도입 |
| FE refresh 흐름 미구현 | **해소** — 401 시 재발급 1회 후 재시도 |
| 한 schema에 writer 둘 (pipeline 직접 write) | **미해소** — 콜백 경유 단일 writer 전환은 Phase 2 잔여 |
| ingest가 BackgroundTasks (배포 시 유실) | **미해소** — Queue 도입 필요 |
| 임베딩 모델 프로세스 상주, converter 미연결 | **미해소** |

문서와 다르게 구현된 것: 자동저장은 5초가 아니라 **800ms** debounce이고, 문서 본문·버전은 MongoDB가 아니라 **PostgreSQL**(`document_edit_states` + `document_content_versions` append-only 이력)이다. 멱등성은 `revision_write_id` 대신 base_version 낙관적 잠금 + `Idempotency-Key` 헤더. 버전 목록·diff·비파괴 복원 API와 FE 연동은 완료됐다(`docs/spec/document-version-history.md`).

### Phase 진행 위치

| Phase | 상태 |
|---|---|
| 0 격리·인가 정합성 | **완료** (JWKS만 Phase 3으로 유보) |
| 1 상태 외부화 | **완료** (MongoDB 이관은 재평가 항목 — PostgreSQL 구현이 이미 동작) |
| 2 ai-svc 신뢰 경계 | **부분 완료** — 인증·포트·timeout 완료 / 직접 write 회수·Queue·converter 연결 잔여 |
| 3 access-svc 분리 | 미착수 (패키지 `fruition.access.*` 논리 분리까지만) |
| 4 AWS 실행 형태 | 미착수 (Terraform·Queue·Secrets Manager — `docs/issue/{backend,infra}/2026-08-06.md`) |

**요약**: 이 문서가 "인스턴스 하나 늘리는 것도 안전하지 않다"고 진단한 상태는 벗어났다. 현재 코드는 **다중 인스턴스에서 동작하는 보안 경계 갖춘 모놀리스 + 내부 인증된 ai-svc** 구성이며, 서비스 물리 분리(access-svc)와 비동기 큐가 다음 단계다. 변경 상세는 `docs/changelog/{backend,ai,infra,frontend}.md`의 2026-08-06 항목 참조.

이 문서는 Fruition을 어떤 서비스 경계로 나누고 AWS에서 어떻게 운영할지 제안한다. 중심 질문은 다음 네 가지다.

1. 왜 이 서비스 경계가 필요한가
2. 로그인부터 AI 호출까지 각 구간에서 무엇이 어디서 검증되는가
3. 한 서비스의 장애가 다른 기능으로 전파되지 않게 하려면 어떻게 해야 하는가
4. 특정 Workspace나 기능에 트래픽이 몰릴 때 어떻게 확장하고 과부하를 제한할 것인가

DB 필드, Operation 상태 전이, Outbox claim, message version과 재처리 알고리즘은 [MSA 구현·운영 계약](msa-operational-contracts.md)에서 다룬다.

---

## 1. 현재 구조와 전환이 필요한 이유

### 1.1 현재 실행 구조

```text
Frontend (Next.js)
    │  /api/:path* → 단일 backend URL로 rewrite
    ▼
Backend (Spring Boot, 242 files)
    ├─ PostgreSQL          단일 datasource, public schema 하나
    │    └─ Spring Session도 같은 DB에 저장
    ├─ MinIO / S3 호환 storage
    └─ llmPipeline (FastAPI, :8000)
           └─ 같은 PostgreSQL에 직접 write

Converter (FastAPI, :8010)  ── 호출하는 코드 없음 (미연결)
```

Converter는 컨테이너와 API가 존재하지만 `backend/`와 `frontend/` 어디에서도 호출하지 않는다. 현재는 독립 도구이며 제품 경로에 연결되어 있지 않다.

### 1.2 지금 구조가 만드는 구체적 위험

전환의 근거는 일반론이 아니라 코드에서 확인되는 사실이다.

| 위험 | 현재 상태 | 근거 |
|---|---|---|
| 인증 경계가 서비스 분리를 감당하지 못함 | `/api/auth/me`와 `/api/workspaces/**`만 인증 대상이고 나머지는 `permitAll` | `SecurityConfig.java:73-77`, TODO `:63` |
| token에 검증 근거가 부족함 | principal이 `userId` 문자열이고 authority가 없다. `iss`·`aud` 검증도 없다 | `JwtAuthenticationFilter.java:28-36`, `JwtTokenProvider.java:55-57` |
| 멤버십 검사가 8곳에 복제됨 | 같은 `verifyWorkspaceOwnership` private 메서드가 서비스마다 따로 있다 | `DocumentService:144`, `FolderService:312`, `DocumentExportService:40`, `DocumentPlacementService:81`, `WikiService:60`, `ChatSessionService:30`, `WikiSchemaService:44`, `WikiMaintenanceService:23` |
| 역할 기반 인가가 사실상 동작하지 않음 | 상수는 `owner`·`member` 소문자인데 쿼리는 `'OWNER'` 대문자 리터럴을 비교한다 | `WorkspaceMemberRepository.java:41-51, 53-61` |
| Workspace 격리가 비어 있는 경로가 있음 | `wiki_page_links`·`document_wiki_links`에 workspace 컬럼이 없어 메모리에서 보정한다. `chat_partial_wiki`도 무스코프이며 `/api/query/runs/**`는 `permitAll`에 Workspace 파라미터도 없다 | `WikiService.java:70-72`, `QueryRunController`, `DocumentPipelineController` |
| 이미 단일 인스턴스에 고정됨 | OAuth 교환 코드와 query run 상태가 프로세스 메모리 Map이다. 인스턴스를 2대로 늘리면 로그인과 SSE가 깨진다 | `OAuthExchangeCodeStore.java:15,19`, `QueryRunStore.java:25` |
| AI 경계에 인증이 전혀 없음 | llmPipeline 전 엔드포인트가 무인증이고 host `:8000`에 공개된다. `GET /documents/{id}`는 스코프 검사 없이 원본 row를 반환한다 | `llmPipeline/api.py:50` 및 전체 |
| 한 schema에 writer가 둘 | Spring과 llmPipeline이 `documents`·`wiki_pages`·링크·임베딩 테이블을 함께 write한다. 공유 transaction은 없다. V4 마이그레이션이 `IF NOT EXISTS`를 쓰는 이유다 | `docs/spec/pipeline-db-ownership.md` |
| AI 호출에 안전장치가 없음 | client 5개가 각자 생성되고 pool·retry·circuit breaker가 없다. 그중 하나는 **timeout 자체가 없어 무한 대기한다** | `DocumentProcessingRequester.java:23-31`, 나머지는 30s·60s·200s로 제각각 |
| AI가 수평 확장되지 않음 | ingest가 uvicorn 프로세스 안의 BackgroundTasks로 돌고, 실행 로그는 로컬 볼륨에 남으며, `@lru_cache(maxsize=1)`와 in-process bge-m3 모델이 인스턴스를 고정한다 | `llmPipeline/` |

정리하면 현재 구조는 기능 개발에는 적합하지만, **인스턴스를 하나 더 늘리는 것조차 이미 안전하지 않다**. 아래 문제가 함께 존재한다.

- Backend 또는 공유 DB 장애가 로그인·문서·채팅·Wiki 전체로 전파된다.
- 파일 변환과 LLM 작업이 API 자원을 함께 사용해 실시간 요청을 느리게 만든다.
- 재시작·배포 때 memory 기반 작업 상태와 진행 event가 사라진다.
- 특정 기능만 트래픽이 늘어도 전체 application과 DB를 함께 확장해야 한다.

### 1.3 MSA 전환 목표

MSA 전환의 목적은 서비스를 많이 만드는 것이 아니다. 데이터 소유권, 장애 범위와 확장 단위를 제품 기능에 맞게 분리하는 것이다.

- 로그인 장애가 기존 사용자의 문서·채팅 조회까지 즉시 중단시키지 않게 한다.
- 파일 변환·LLM·임베딩 작업의 부하가 API 응답 자원을 고갈시키지 않게 한다.
- 각 서비스가 자기 원본 데이터와 저장 규칙을 소유하게 한다.
- 오래 걸리는 작업은 Queue에 전달해 API 배포와 worker 재시작에서 복구할 수 있게 한다.
- Workspace별 요청량과 LLM 비용을 제한해 한 고객이 전체 시스템을 독점하지 못하게 한다.

### 1.4 이 문서의 목표와 비목표

이 문서는 목표 운영 구조와 선택 이유를 정한다. 다음 항목은 구체적인 제품과 운영 수치를 확정할 때 별도 검증한다.

- HPA/오토스케일 replica 수, timeout, retry 횟수와 Queue별 visibility timeout
- message field와 DB index
- migration, backfill, cutover와 rollback 명령
- 내부 서비스 인증의 구체 구현과 Quota 저장 기술

문서 편집용 MongoDB는 현재 목표 구조에 포함한다. 현재 Markdown·revision·content hash·저장 멱등성은 MongoDB가 함께 소유하고, Core RDS에는 문서 metadata와 조회용 revision projection만 둔다. Wiki 원본 MongoDB와 Search/Vector의 물리 분리는 도메인 분할 단계(§9 Phase 5)의 결정 항목으로 유지한다.

---

## 2. 목표 구조: 3개 서비스

### 2.1 서비스 경계

```text
Fruition
├─ access-svc              로그인 · Workspace · 권한
│  ├─ 이관 대상            backend의 user, security(+oauth), workspace
│  ├─ Access RDS           users, user_oauth_accounts, user_refresh_tokens,
│  │                       workspaces, workspace_members
│  └─ 권한 store           OAuth 교환 코드, 멤버십·역할 projection
│
├─ backend-api             문서 · 채팅 · Wiki 비즈니스 로직
│  ├─ 이관 대상            document, wiki, wikischema, wikimaintenance,
│  │                       chat, query, agent
│  ├─ Core RDS             document metadata·revision projection, folders,
│  │                       chat_*, wiki_pages, wiki_*_links, operation 상태
│  ├─ Document MongoDB     현재 Markdown·revision·content hash·저장 멱등성
│  ├─ S3                   문서 원본 · 고정 revision snapshot · export 산출물
│  └─ 실시간 store         query run 상태 · SSE event
│
└─ ai-svc                  LLM · 변환 · 임베딩 계산
   ├─ 이관 대상            llmPipeline/ + infra/converter/
   ├─ 실행 형태            동기 API + 비동기 worker (§4에서 선택)
   ├─ AI store             pipeline_runs, 실행 로그, 임베딩·벡터 색인
   └─ 업무 테이블 write 권한 없음 (목표 상태)
```

### 2.2 왜 세 개인가

서비스 개수는 도메인 모델이 아니라 **지금 사실로 확인되는 경계**를 기준으로 정한다. 세 축만이 오늘 이미 서로 다른 신뢰 경계·자원 형태·장애 범위를 가진다.

**access-svc를 나누는 이유는 신뢰 경계다.** 현재 인가 판단은 8개 서비스에 복제된 private 메서드 하나이고, 역할 상수는 소문자인데 쿼리는 대문자를 비교한다(`WorkspaceMemberRepository.java:41-51`). 즉 역할 기반 인가가 사실상 동작하지 않는다. 이 상태로 도메인을 넷으로 나누면 깨진 인가 규칙이 네 벌로 복제된다. 인가는 분산하기 전에 먼저 한곳으로 모아야 한다. 또한 OAuth 교환 코드가 프로세스 메모리에 있어(`OAuthExchangeCodeStore.java:15,19`) 로그인은 지금 인스턴스 2대에서 이미 깨진다. 로그인만 분리하면 이 수정의 범위가 한 서비스로 한정된다.

**ai-svc를 나누는 이유는 자원 형태와 신뢰 경계다.** llmPipeline은 전 엔드포인트가 무인증이고 `GET /documents/{id}`가 스코프 검사 없이 원본 row를 반환한다. 동시에 bge-m3 임베딩 모델을 API 프로세스 메모리에 적재하고 ingest를 BackgroundTasks로 같은 프로세스에서 돌리므로, API를 늘리면 모델도 함께 늘어난다. Converter는 최대 600초 걸리는 블로킹 subprocess를 event loop 안에서 실행한다. 이 셋은 실시간 API와 자원 단위가 다르다. 도메인이 아니라 실행 형태가 분리를 강제한다.

**문서·채팅·Wiki를 지금 나누지 않는 이유는 독립 신호가 아직 없기 때문이다.** 세 기능은 현재 한 Spring transaction과 공용 조회 경로(`DocumentRepository.findByIdInActiveWorkspace`)를 공유하고, chat→wiki export와 document→wiki ingest, query→wiki 검색으로 서로를 직접 호출한다. 지금 나누면 오늘 한 transaction인 경로가 분산 transaction이 되는데, 그 대가를 정당화할 기능별 부하 격차 측정치가 없다. 게다가 `wiki_page_links`·`document_wiki_links`에는 workspace 컬럼조차 없다(`WikiService.java:70-72`가 메모리에서 보정). `workspace_id` 격리가 완성되기 전의 도메인 분할은 격리 결함을 서비스 경계 너머로 확산시킨다.

따라서 도메인 4분할은 폐기가 아니라 **후속 단계**다(§9 Phase 5). 이 문서의 목표 구조는 세 개다.

`worker`와 `engine`은 별도 제품 영역이 아니라 `ai-svc` 안의 계산 프로그램이다. 사용자 요청을 받는 API와 CPU·LLM 중심 작업을 분리해 필요한 부분만 확장한다.

장시간 command와 실패 재처리는 SQS를 사용한다. 실시간 답변 token과 짧은 진행 event는 `backend-api`의 실시간 store에 둔다. 하나의 event를 여러 독립 consumer가 장기간 replay하거나 순서를 지속해서 보장해야 하는 요구가 실제로 확인될 때만 Kafka를 검토한다.

### 2.3 데이터 소유권

| 영역 | 원본 저장소 | 쓰기 책임 | 현재 대비 변화 |
|---|---|---|---|
| 사용자·로그인·refresh token | Access RDS | `access-svc` | 같은 DB에서 schema·계정 분리 → 이후 별도 RDS |
| Workspace·멤버·역할 | Access RDS | `access-svc` | 역할 표기 통일이 선행 조건 |
| 권한 조회 projection | 권한 store | `access-svc`가 갱신, 나머지가 조회 | 신규 |
| OAuth 교환 코드 | 권한 store | `access-svc` | in-memory Map 제거 |
| 문서 metadata·폴더 | Core RDS | `backend-api` | 현재 본문·편집 revision의 원본 책임 제거, ai-svc write 권한 회수 |
| 현재 Document 본문·편집 revision | Document MongoDB | `backend-api` | `document_edit_states` 이동, content hash·저장 멱등성까지 함께 소유 |
| Document 고정 revision·source block | S3, Core RDS checkpoint metadata | `backend-api` | AI 편집·rollback·Wiki ingest·export 입력만 불변 snapshot으로 보존 |
| 채팅·세션·partial wiki | Core RDS | `backend-api` | `chat_partial_wiki`에 `workspace_id` 추가 |
| Wiki page·link | Core RDS | `backend-api` | 현재 llmPipeline이 직접 write. 목표는 콜백 경유 단일 writer |
| pipeline run·실행 로그 | AI store | `ai-svc` | V4의 이중 소유 해소 |
| 임베딩·벡터 색인 | AI store | `ai-svc` | 검색 projection은 원본에서 재생성 가능 |
| query run 상태·SSE event | 실시간 store | `backend-api` | `QueryRunStore` in-memory 대체 |

각 프로그램은 다른 서비스의 저장소를 직접 수정하지 않는다. 서비스 간 관계는 FK 대신 ID와 version이 있는 API·message로 연결한다. 모든 업무 데이터와 message는 검증된 `workspace_id`로 격리한다.

`docs/spec/pipeline-db-ownership.md`는 llmPipeline이 backend 테이블을 직접 write하는 것을 ADR로 수용하고 있다. 3-서비스 목표 구조는 이 ADR을 폐기가 아니라 **만료 대상**으로 본다. 전환 중에는 `ai-svc`에 별도 schema와 최소 권한 DB 계정을 부여해 업무 테이블 write를 단계적으로 회수하고, 회수가 끝나면 해당 ADR을 superseded로 표시한다.

초기에는 Access RDS와 Core RDS를 물리적으로 나누지 않고 **같은 PostgreSQL의 schema와 접속 계정만 분리**할 수 있다. 물리 분할은 접속 수·용량·복구 시간이 실제 한계를 넘을 때 수행한다. Spring Session이 업무 DB에 저장되는 현재 구성(`spring.session.store-type=jdbc`)은 `access-svc` 분리 시점에 함께 정리한다.

### 2.4 프런트엔드 영향

프런트엔드는 모든 요청을 상대 경로 `/api/...`로 보내고 `next.config.mjs`가 단일 backend URL로 rewrite한다. 3-서비스 분할은 **경로 기반 라우팅만으로 프런트엔드 변경 없이 수용된다.**

- `/api/auth/*`, `/api/workspaces`(목록·생성) → `access-svc`
- 그 외 `/api/workspaces/{wid}/**` 및 기능 경로 → `backend-api`

이미 Workspace 범위 경로가 모두 URL에 `{workspace_id}`를 포함하고 있어 라우팅 규칙이 단순하다. 예외는 `/api/query/runs/{requestId}`와 `/events` 두 경로이며, 여기에 Workspace 스코프를 추가하는 것이 분할의 선행 조건이다.

---

## 3. 핵심 흐름: 로그인 → Workspace 정보 제공 → backend 로직 + AI 요청

이 절은 제품의 기본 요청을 세 구간으로 나눠 각 구간에서 **무엇이 어디서 검증되고, 검증할 수 없을 때 어떻게 실패하는지**를 정한다. 세 서비스 경계는 이 세 구간과 일치한다.

### 3.0 전체 그림

```text
        ┌──────────────┐
        │  Frontend    │  /api/:path*
        └──────┬───────┘
               │ HTTPS
        ┌──────▼───────┐
        │  WAF + ALB   │  경로 기반 라우팅
        └──┬────────┬──┘
           │        │
  /api/auth/*       │  그 외 전부
  /api/workspaces   │
           │        │
    ┌──────▼─────┐  │
    │ access-svc │  │      ① 로그인   ② Workspace 정보 제공
    │  JWT 발급  │  │
    │  JWKS 공개 │  │
    └──┬─────┬───┘  │
       │     │      │
 Access RDS  │  ┌───▼─────────────┐
             │  │   backend-api   │  ③ 비즈니스 로직
  권한 store └─▶│  JWT 로컬 검증  │
       ▲        │  멤버십·역할    │
       │ 조회   └───┬─────────┬───┘
       └────────────┘         │  ④ AI 요청 (내부 전용)
                     Core RDS │
                        S3    │
                              ▼
                       ┌─────────────┐
                       │   ai-svc    │  LLM · 변환 · 임베딩
                       │ 호출자 검증 │  (VPC 내부에서만 도달)
                       └──┬──────┬───┘
                          │      │
                     AI store   외부 LLM / Bedrock
```

`backend-api`와 `ai-svc`는 사용자 요청 경로에서 **`access-svc`를 중계로 거치지 않는다.** 각 서비스가 cache한 JWKS 공개키로 JWT를 스스로 검증하고 권한 store에서 Workspace 상태와 역할을 확인한다. 따라서 `access-svc`가 멈춰도 이미 로그인한 사용자는 token 만료 전까지 기능을 계속 사용한다. 서명 key를 교체할 때는 새 key를 서명에 사용하기 전에 먼저 배포하고, 기존 token과 각 서비스의 JWKS cache가 만료될 때까지 이전 key를 겹쳐 제공한다.

### 3.1 구간 ① 로그인

```text
Frontend                access-svc              OAuth Provider
   │                        │                        │
   │ POST /api/auth/login   │                        │
   │  또는 OAuth 시작       │                        │
   ├───────────────────────▶│                        │
   │                        │  authorize / token     │
   │                        ├───────────────────────▶│
   │                        │◀───────────────────────┤
   │                        │
   │                        │ 교환 코드를 공유 store에 저장 (TTL 60s)
   │                        │   ※ 현재는 프로세스 메모리 → 2대에서 깨짐
   │                        │
   │  access JWT            │
   │  + opaque refresh      │
   │◀───────────────────────┤
   │                        │
   │  refresh 회전          │
   ├───────────────────────▶│ 기존 hash 무효화 후 새 쌍 발급
```

| 항목 | 목표 상태 | 현재와의 차이 |
|---|---|---|
| access token | RS256 서명, `iss`·`aud`·`kid`·`sub`(user_id)·`exp` 포함, TTL 900초 | 현재 `iss`·`aud` 검증 없음 (`JwtTokenProvider.java:55-57`) |
| token 안의 권한 | Workspace 역할을 넣지 않는다 | 유지. 역할은 변경 즉시 반영돼야 하므로 token에 굳히지 않는다 |
| refresh token | 32바이트 난수 opaque, SHA-256 hash 저장, 사용 시 회전 | 유지 (`AuthService.java:89-103, 155-160`) |
| 회전 재사용 탐지 | 이미 사용된 refresh 재제출 시 해당 계정 refresh 계열 전체 무효화 | 신규 |
| OAuth 교환 코드 | 공유 store, 1회 사용, TTL 60초 | in-memory Map 제거 필수 |
| 키 배포 | `access-svc`가 JWKS 공개, 소비 서비스는 cache + `kid` 미스 시 1회 재조회 | 신규 |
| 실패 동작 | 서명·`iss`·`aud`·`exp` 중 하나라도 검증 불가면 401. fallback 없음 | — |
| 프런트엔드 | access token 만료 시 silent refresh, 실패할 때만 재로그인 | **refresh 흐름 미구현** (`shared/lib/auth.ts` 주석이 명시) |

token 보관 위치(localStorage vs. HttpOnly cookie)는 이번 분할의 선행 조건이 아니므로 이 문서에서 확정하지 않되, `access-svc`가 분리되는 시점에 별도 결정 항목으로 다룬다.

### 3.2 구간 ② Workspace 정보 제공

```text
Frontend                     access-svc                권한 store
   │                             │                          │
   │ GET /api/workspaces         │                          │
   │  Authorization: Bearer JWT  │                          │
   ├────────────────────────────▶│ JWT 검증 → user_id       │
   │                             │ Access RDS 조회          │
   │                             │  workspaces + 내 역할    │
   │◀────────────────────────────┤                          │
   │  [{id, name, role, status}] │                          │
   │                             │                          │
   │ 사용자가 Workspace 선택     │                          │
   │  (0개면 생성 화면)          │                          │
   │                             │                          │
   │ POST /api/workspaces        │ 생성·멤버 변경 시        │
   ├────────────────────────────▶├─────────────────────────▶│
   │                             │ projection 반영 확인 후  │
   │◀────────────────────────────┤ 성공 응답                │
```

| 항목 | 목표 상태 | 근거·차이 |
|---|---|---|
| 응답 필드 | `workspace_id`, 이름, 내 역할, 상태(`active`·`deleting`·`deleted`) | 역할을 응답에 포함시켜 UI가 권한별 화면을 그릴 수 있게 한다 |
| 역할 값 | 저장·조회·비교에서 표기를 하나로 통일 | 현재 상수는 소문자, 쿼리는 `'OWNER'` 대문자 리터럴(`WorkspaceMemberRepository.java:41-51, 53-61`). **분할 전 수정 필수** |
| 선택 방식 | 목록이 여러 개면 사용자가 고른다 | 현재는 `workspaces[0]` 자동 선택 + 없으면 기본 Workspace 자동 생성 |
| 선택 결과 | 이후 모든 기능 요청 URL에 `{workspace_id}`로 실린다 | 이미 그렇게 되어 있음. 예외는 `/api/query/runs/{requestId}`와 `/events` |
| 권한 변경 반영 | 역할 변경·멤버 제거·Workspace 삭제는 권한 store 반영을 확인한 뒤에만 성공 응답 | 성공 응답 이후의 요청이 이전 권한으로 통과하지 않게 하는 유일한 규칙 |
| projection 유실 | Access RDS에서 재구축. 재구축 전 요청은 fail-closed 거부 | 재구축 시간이 전체 서비스의 허용 중단 시간 안에 들어와야 한다 |

### 3.3 구간 ③ backend 로직 + AI 요청

```text
Frontend            backend-api                    ai-svc
   │                    │                             │
   │ POST /api/workspaces/{wid}/...                   │
   ├───────────────────▶│                             │
   │                    │ (1) JWKS로 JWT 로컬 검증    │
   │                    │ (2) 권한 store에서          │
   │                    │     (wid, user_id) 역할 조회 │
   │                    │     · 조회 불가 → 거부       │
   │                    │     · status != active → 거부│
   │                    │ (3) 작업별 최소 역할 확인    │
   │                    │ (4) 업무 로직 · DB 기록      │
   │                    │                             │
   │                    │ (5) AI 필요 시              │
   │                    │  service identity 부착       │
   │                    │  + workspace_id              │
   │                    │  + operation_id              │
   │                    │  + 남은 시간 예산            │
   │                    ├────────────────────────────▶│
   │                    │                             │ (6) 호출자 신원 검증
   │                    │                             │     실패 → 401 즉시 종료
   │                    │                             │ (7) 계산만 수행
   │                    │                             │     업무 테이블 write 없음
   │                    │◀────────────────────────────┤
   │                    │ (8) 저장 직전 권한·상태 재확인 │
   │                    │ (9) Core RDS 기록            │
   │◀───────────────────┤                             │
```

| 항목 | 규칙 |
|---|---|
| 사용자 인증 | 각 서비스가 JWKS로 로컬 검증한다. `access-svc` 호출 없음 |
| 인가 판단 위치 | `backend-api`의 단일 인가 지점. 8곳에 복제된 `verifyWorkspaceOwnership`을 대체한다 |
| 역할 구분 | 작업별 최소 역할을 명시한다. 최소한 Workspace 삭제·멤버 관리·Wiki 전체 재생성은 `owner`로 제한한다 |
| 실패 동작 | 권한을 확인할 수 없으면 허용하지 않는다(fail-closed). cache 미스면 원본 조회, 원본도 불가면 거부 |
| 장시간 작업 | 결과 저장 직전에 현재 역할과 Workspace 상태를 다시 확인한다 |
| `ai-svc` 호출자 인증 | §4.4의 선택지 중 하나. 어느 방식이든 만료·대상(audience)·재사용 방지를 가져야 한다 |
| `ai-svc`의 `workspace_id` | 요청 본문 값을 그대로 신뢰하지 않는다. 호출자 신원 문맥에 묶인 값과 일치할 때만 처리한다 |
| `ai-svc`의 데이터 접근 | 목표 상태에서 업무 테이블 직접 접근 없음. 필요한 입력은 요청에 담기거나 `backend-api`가 발급한 범위 제한 참조로 전달한다 |
| timeout 예산 | 상위 요청의 남은 시간보다 짧은 timeout을 하위에 준다. **timeout 없는 client는 허용하지 않는다**(`DocumentProcessingRequester.java:23-31`가 현재 무한) |
| 재시도 | 한 계층에서만, backoff·jitter 적용. 비멱등 요청은 재시도하지 않는다 |
| 회로 차단 | provider·경로별 circuit breaker. 열린 동안은 즉시 실패하고 대체 응답을 만들지 않는다 |

비동기 경로와 콜백은 별도 규칙을 가진다. 현재 `DocumentPipelineController`의 콜백이 무인증이므로 이 부분이 특히 중요하다.

```text
backend-api                 Queue              ai-svc worker
    │                         │                     │
    │ operation 레코드 생성   │                     │
    │  (accepted)             │                     │
    │ 작업 전달               │                     │
    ├────────────────────────▶├────────────────────▶│
    │                         │                     │ 계산 · 진행 로그
    │◀── 진행/완료 콜백 ────────────────────────────┤
    │   · 호출자 신원 검증 필수                      │
    │   · operation_id 기준 idempotent               │
    │   · 이미 종료된 operation의 콜백은 무시         │
    │ 권한 재확인 → Core RDS 반영                    │
    │                                                │
    │ SSE 또는 폴링으로 사용자에게 진행 전달          │
    │   ※ 진행 상태는 실시간 store에 둔다             │
```

성공 여부를 Queue 내부를 뒤져 판단하지 않는다. 최종 성공·실패의 기준은 `backend-api`의 operation 레코드다. 중복 전달은 `operation_id` 기준 멱등 처리로 흡수하고, 반복 실패는 DLQ로 격리한다. 이 상태 전이의 구체 값은 [MSA 구현·운영 계약](msa-operational-contracts.md)의 operation 상태 기계를 따른다.

SSE가 끊겨도 답변 생성과 최종 저장은 계속한다. 재접속한 사용자는 실시간 store의 남은 event 또는 Core RDS의 최종 결과를 조회한다.

### 3.4 Document import·edit·export

```text
backend-api가 요청과 원본을 접수
  → Queue로 변환·AI 편집 작업 전달
  → ai-svc worker가 결과 artifact 생성
  → backend-api가 현재 권한·revision을 확인
  → MongoDB에 새 Document edit revision 저장 또는 export 결과 기록
```

Frontend는 마지막 입력 후 5초가 지나면 현재 `base_revision`과 새 `revision_write_id`로 자동저장을 요청한다. Backend는 MongoDB transaction에서 현재 revision이 `base_revision`과 같을 때만 본문·content hash를 갱신하고 revision을 증가시킨다. 다른 저장이 먼저 끝났으면 `409 Conflict`를 반환한다. 같은 저장 요청의 네트워크 재시도는 동일한 `revision_write_id`를 사용하며, 서버가 이미 저장한 요청이면 충돌 대신 기존 성공 결과를 반환한다.

자동저장 revision은 충돌 제어용 단조 증가 token이다. 모든 자동저장을 S3에 영구 보존하지 않고, AI 편집·rollback·Wiki ingest·export 또는 사용자가 버전을 고정할 때만 해당 revision의 불변 snapshot을 만든다. Core RDS의 revision 값은 목록 조회용 projection이며 저장 가능 여부는 MongoDB revision으로만 판단한다.

### 3.5 Wiki ingest와 검색 반영

```text
backend-api가 고정된 Document revision 또는 Chat snapshot 접수
  → Queue로 Wiki 생성·Lint 작업 전달
  → ai-svc worker가 결과를 콜백으로 반환
  → backend-api가 Core RDS의 Wiki 원본 갱신
  → ai-svc 색인 경로가 임베딩·벡터 projection 갱신
```

Wiki 원본 저장 성공과 검색 반영은 같은 시점이 아니다. 원본 page 조회는 먼저 가능할 수 있으며 Query 검색은 projection이 반영된 뒤 최신 결과를 사용한다. UI는 이 짧은 지연을 실패로 표시하지 않고 검색 반영 대기 상태로 안내한다.

---

## 4. AI 컨테이너 호출·실행 방식 선택지 (AWS)

`ai-svc`는 하나의 실행 형태로 통일할 수 없다. 현재 코드에는 성격이 다른 네 종류의 작업이 섞여 있다.

| workload | 현재 구현 | 특성 |
|---|---|---|
| 동기 질의 | `POST /query`, `POST /agent/turn`, wiki schema preview, lint | 사용자가 기다린다. 수 초~수십 초. 실패 시 재시도 가능 |
| 비동기 ingest | `POST /pipeline/runs`, `POST /chat-wiki/runs` (BackgroundTasks) | 분 단위. 사용자가 화면을 떠나도 완료돼야 한다 |
| 파일 변환 | `infra/converter`의 `POST /convert` | 최대 600초 블로킹 subprocess. CPU·메모리 집약 |
| 임베딩 | 프로세스 내 SentenceTransformer BAAI/bge-m3 | 모델이 상주한다. API를 늘리면 모델도 함께 늘어난다 |

아래는 각 실행 형태의 선택지와 근거다. 하나를 강제하지 않고 workload별로 조합해 선택한다.

### 4.1 선택지 비교

| 선택지 | 잘 맞는 workload | 지연·기동 | 실행 시간 한계 | 비용 형태 | 운영 부담 | 장애 시 동작 |
|---|---|---|---|---|---|---|
| **A. ECS Fargate + 내부 ALB (동기 HTTP)** | 동기 질의, lint, schema preview | 기동 후 cold start 없음. 신규 task 기동은 이미지 크기에 비례(ML 이미지는 수십 초~분) | ALB idle timeout 기본 60초, 조정 가능 | 실행 중 task의 vCPU·GB 시간, 상시 과금 | 낮음. task 정의와 서비스 오토스케일 | task 비정상 시 헬스체크 후 교체. ALB가 남은 task로 분배 |
| **B. EKS Deployment (동기 HTTP)** | A와 동일 | A와 동일 | A와 동일 | A + cluster 제어 평면 상시 비용 | 높음. cluster upgrade·네트워킹·노드 관리 | A와 유사하나 cluster 전역 설정 실수의 영향 범위가 크다 |
| **C. SQS + Fargate worker (비동기)** | ingest, Wiki 생성, 파일 변환, 재색인 | 대기 시간이 곧 지연. 사용자 대기 경로에 부적합 | visibility timeout 최대 12시간, 메시지 보존 최대 14일 | worker task 시간 + SQS 요청 비용. backlog 없으면 0까지 축소 | 중간. Queue·DLQ·멱등성·상태 API 필요 | 실패 메시지는 재시도 후 DLQ로 격리. worker 재시작으로 재개 |
| **D. Lambda (컨테이너 이미지)** | 짧은 단발 계산 — lint, schema preview, 소형 변환 | 콜드 스타트 존재. 이미지가 클수록 커진다 | **최대 15분 (하드 한계)** | 요청·실행 시간 과금. 유휴 시 0 | 낮음. 단 이미지·메모리 상한 관리 | 자동 재시도 정책. 15분 초과 작업은 구조적으로 불가 |
| **E. Bedrock 직접 호출 (컨테이너 없음)** | 순수 LLM 호출 — 답변 생성, Wiki 초안 | 컨테이너 기동 개념 없음. 지연은 모델·토큰 수에 비례 | provider 호출 timeout | **토큰당 과금. 유휴 비용 0** | 가장 낮음 | provider 오류·throttling. 회로 차단과 provider fallback 필요 |
| **F. SageMaker 엔드포인트 (bge-m3)** | 임베딩 전용 | 상시 엔드포인트는 콜드 스타트 없음 | 실시간 추론 요청 timeout 내 | **인스턴스 상시 과금이 가장 큰 단점.** serverless·async 변형은 축소 가능하나 메모리·GPU 제약 있음 | 중간. 모델 아티팩트·엔드포인트 버전 관리 | 엔드포인트 장애 시 임베딩·재색인 중단, 기존 색인 조회는 유지 |

이 표를 읽을 때 반드시 함께 고려해야 하는 제약이 있다.

- **Lambda의 15분은 우회 불가능한 한계다.** 현재 converter가 최대 600초를 쓰므로 최악 경로는 15분 안에 들어오지만 여유가 작고, 입력이 커지면 구조적으로 실패한다. 변환을 Lambda에 올리려면 먼저 입력 크기 상한을 정해야 한다.
- **Lambda에는 GPU가 없고 메모리 상한이 있다.** bge-m3를 Lambda에 올리면 콜드 스타트마다 모델을 적재하므로 권장하지 않는다.
- **Fargate에도 GPU가 없다.** GPU 추론이 필요해지면 EC2 기반 실행이나 SageMaker가 필요하며, 이것이 §7의 EKS 승격 조건 (a)와 연결된다.
- **ALB의 기본 idle timeout은 60초다.** 동기 LLM 호출은 이 값을 넘기기 쉬우므로, 동기 경로를 A로 갈 때는 timeout 상향과 §3.3의 시간 예산 규칙을 함께 적용하거나 해당 경로를 비동기(C)로 돌린다.
- **Bedrock의 모델 가용성은 Region마다 다르다.** 사용하려는 모델이 대상 Region에서 제공되는지 먼저 확인하고, 없으면 cross-Region 추론 사용 여부를 데이터 처리 위치 정책과 함께 승인한다.
- **Bedrock은 현재 코드에 provider로 존재하지 않는다.** 지원 provider는 `openai`·`gemini`·`claude`·`upstage`·`generic`이며 기본값은 `upstage`/`solar-pro2`다. Bedrock 채택은 배포 선택이 아니라 **inference adapter에 provider를 추가하는 구현 작업**이다.
- **SageMaker 실시간 엔드포인트는 요청이 없어도 과금된다.** 임베딩 호출량이 낮은 초기 단계에서는 이 비용이 정당화되지 않을 수 있다.

### 4.2 workload별 권장 조합

| workload | 기본 선택 | 이유 | 대안 |
|---|---|---|---|
| 동기 질의 (query, agent turn) | **A. Fargate 동기 HTTP + 내부 ALB** | 상시 대기 상태가 필요하고 콜드 스타트를 허용할 수 없다. 지연 예측이 쉽다 | 응답 지연이 ALB 한계를 넘기 시작하면 C로 이동하고 SSE로 진행을 전달 |
| 짧은 계산 (lint, schema preview) | **A에 합류** | 별도 실행 단위를 늘릴 만큼의 부하가 아니다 | 호출 빈도가 낮고 간헐적이면 D가 비용상 유리 |
| ingest 파이프라인 | **C. SQS + Fargate worker** | 현재 BackgroundTasks가 프로세스에 묶여 배포 시 유실된다. 이 문제를 해결하는 유일한 선택지 | 없음. D는 15분 한계로 부적합 |
| 파일 변환 | **C. 전용 Queue + 전용 worker** | 600초 CPU 집약 작업이 API 자원을 점유하지 못하게 한다. Queue를 ingest와 분리해 서로를 굶기지 않게 한다 | 입력 크기 상한을 낮게 정할 수 있으면 D도 가능 |
| 순수 LLM 호출 | **E. Bedrock을 우선 provider로** | 컨테이너 자원 없이 토큰 과금만 발생하고 VPC 내부 연결로 외부 egress를 줄인다 | 승인된 외부 LLM API를 대체 provider로 유지. 이는 배포 선택이 아니라 adapter 안의 provider 선택 |
| 임베딩 (bge-m3) | **1단계: C의 worker 안에 유지하되 동기 API와 분리** | 모델을 API 프로세스에서 떼는 것만으로 확장 결합이 끊어진다. 비용 추가 없음 | **2단계: F 또는 관리형 임베딩 모델.** 모델을 바꾸면 벡터가 달라지므로 전체 재색인 비용을 먼저 산정한다 |

기본 조합은 **A(동기) + C(비동기) + E(LLM provider)** 이며, F는 임베딩 호출량이 전용 엔드포인트 비용을 정당화할 때 도입한다. B(EKS)는 §7의 승격 조건을 만족할 때만 선택한다. D는 특정 짧은 작업에 한정된 최적화이지 `ai-svc` 전체의 실행 형태가 될 수 없다.

이 조합의 공통 성질은 **동기 경로와 비동기 경로가 자원을 공유하지 않는다**는 것이다. 현재 구조에서 ingest·임베딩·변환이 API와 같은 프로세스·같은 인스턴스에 묶여 있는 것이 가장 큰 확장 제약이므로, 어떤 선택지를 고르더라도 이 분리는 유지해야 한다.

로컬 Ollama는 지원 provider로 등록되어 있지 않고 문서 복원 평가 경로에만 하드코딩된 형태로 존재한다. Desktop·On-premise 옵션으로 논하려면 먼저 정식 provider로 승격해야 하며, 웹 운영 구조의 필수 구성으로 보지 않는다. provider를 변경할 때마다 같은 평가 문서로 품질·지연·비용을 다시 측정한다.

### 4.3 선택을 확정하기 위해 측정할 것

- 동기 질의의 p95·p99 응답 시간 — ALB timeout 설정과 A/C 선택의 기준
- 파일 변환 입력 크기 분포와 실행 시간 분포 — D 가능성과 worker 크기 결정
- 임베딩 호출량과 배치 크기 — F 도입 손익 분기
- 대상 Region의 Bedrock 모델 가용성과 품질·비용 재측정 결과
- 재색인 1회 총비용과 소요 시간

### 4.4 `backend-api` → `ai-svc` 인증 방식 선택지

현재 `ai-svc` 계열에는 인증이 전혀 없으므로 이 선택도 함께 확정해야 한다.

| 방식 | 내용 | 장점 | 비용·제약 |
|---|---|---|---|
| 네트워크 격리만 | 보안 그룹·private subnet으로 도달 경로 제한 | 즉시 적용 가능 | 호출자를 구분하지 못한다. **단독으로는 불충분** |
| **서명된 내부 token** | `backend-api`가 짧은 TTL의 서명 token 발급. `aud=ai-svc`, `workspace_id`·`operation_id` 바인딩 | 애플리케이션 레벨에서 요청 문맥까지 묶을 수 있다 | 키 관리와 만료·재사용 방지 구현 필요 |
| AWS 서명 기반 호출 | `ai-svc` 앞단에 IAM 인증을 붙이고 task role로 서명 | 자격증명 배포 부담이 없다 | 앞단 구성 요소가 추가된다 |
| mTLS / service mesh | 상호 인증서로 워크로드 신원 확인 | 전송 계층에서 신원 보장 | 서비스 3개 규모에는 운영 부담이 크다 |

권장은 **네트워크 격리 + 서명된 내부 token**이다. 비동기 worker의 콜백에는 반드시 별도 신원을 적용한다. 사용자 권한 확인과 워크로드 자체 인증은 다른 문제이며 서로를 대신하지 않는다. mTLS·service mesh는 서비스 수가 늘어난 뒤 재검토한다.

---

## 5. 장애 전파 방지

### 5.1 기본 원칙

| 위험 | 대응 |
|---|---|
| 하위 서비스가 느려짐 | 상위 요청의 남은 시간보다 짧은 timeout 적용 |
| 여러 계층이 같은 오류를 재시도 | 한 계층만 제한적으로 retry하고 backoff·jitter 적용 |
| 외부 LLM이나 검색 장애가 지속됨 | circuit breaker로 신규 호출을 차단하고 제한된 확인 요청으로 복구 판단 |
| 느린 호출이 connection을 점유 | 서비스별 connection pool과 동시 실행 수 제한. `DocumentProcessingRequester.java:23-31`에 timeout이 없어 이 위험은 가설이 아니라 현재 상태다 |
| worker 부하가 API를 압박 | API와 worker의 실행 단위·오토스케일 분리 |
| 권한 또는 쓰기 결과가 불확실 | fallback하지 않고 fail-closed |
| Queue 작업이 반복 실패 | 전용 DLQ로 격리하고 원래 작업 ID로 복구 |
| 호환되지 않는 message가 도착 | 재시도하지 않고 schema quarantine에 격리 |

재시도와 circuit breaker는 업무 성공 상태를 대신하지 않는다. 최종 성공·실패는 각 서비스의 원본 DB가 판단한다.

### 5.2 장애 범위

| 장애 | 허용되는 영향 | 계속 가능한 기능 |
|---|---|---|
| `access-svc` 장애 | 신규 로그인·token 갱신·Workspace 생성·멤버 변경 중단 | 유효한 JWT와 권한 projection을 사용하는 문서·채팅·Wiki 요청 |
| 권한 store 장애 | Workspace 범위 요청을 fail-closed 거부 | 권한이 필요 없는 상태 확인 |
| `backend-api` 장애 | 제품 기능 전반 중단 | 원본 데이터 보존. 진행 중 AI 작업은 재개 가능 |
| Document MongoDB 장애 | 문서 본문 조회·자동저장·AI 편집 반영 중단 | 로그인, Workspace 관리, 기존 S3 snapshot 기반 export·복구 |
| `ai-svc` 동기 경로 장애 | Query 답변·agent turn 실패 | 기존 대화·문서·Wiki 조회, 저장과 편집 |
| `ai-svc` 비동기 worker 장애 | ingest·변환·Wiki 생성 지연 | 기존 Wiki page 조회, 문서 편집 |
| 외부 LLM provider 장애 | 신규 생성 실패 | 저장된 결과 조회, provider fallback 정책에 따른 축소 동작 |
| 실시간 store 장애 | SSE 진행 event 지연·유실 | 최종 결과의 DB 조회와 폴링 |
| Core RDS 장애 | 제품 기능 중단 | 로그인·Workspace 조회 (Access RDS 분리 시) |
| 실행 플랫폼 공통 장애 | API·worker 요청 처리 중단 또는 지연 | RDS·MongoDB·S3의 원본과 Queue의 미완료 작업 보존 |

서비스별 실행 단위·resource limit·저장소 분리는 부하와 저장 장애의 전파를 줄이지만 단일 실행 플랫폼과 Region 자체의 장애까지 격리하지는 않는다. 플랫폼 전역 설정과 upgrade는 단계적으로 검증하고, 원본 DB와 Queue를 이용해 API·worker를 다시 올렸을 때 미완료 작업을 재개할 수 있어야 한다. 별도 cluster나 교차 Region 구성은 복구 목표와 규제 요구가 현재 구조로 충족되지 않을 때 도입한다.

### 5.3 Workspace 삭제

Workspace 삭제는 접근 차단과 물리 삭제를 분리한다.

```text
active → deleting → deleted → purged
```

- `deleting`: 신규 접근 차단과 진행 작업 취소 시작
- `deleted`: 모든 서비스의 사용자 조회 차단 확인
- `purged`: 서비스 접근 경로와 일반 저장소의 삭제 완료

삭제 ack의 주체는 `backend-api`와 `ai-svc` 두 곳이다. 도메인 분할(§9 Phase 5) 이후 ack 주체가 늘어나면 계약 문서의 도메인별 ack event를 그대로 적용한다.

S3 Versioning의 noncurrent version과 backup처럼 보존 정책이 적용되는 데이터는 `purged` 이후에도 정해진 기간 남을 수 있다. 서비스 조회에서는 계속 차단하고 별도 만료 정책으로 제거한다.

---

## 6. 트래픽 급증 대응

### 6.1 확장 단위

| 부하 | 우선 확장 대상 | 확장 신호 |
|---|---|---|
| 로그인·권한 요청 | `access-svc` | 응답 시간, 오류율, CPU |
| 제품 API 요청 | `backend-api` | 응답 시간, DB connection, CPU |
| 동기 LLM 답변·agent | `ai-svc` 동기 pool | pending 요청, 첫 token 지연, provider quota |
| ingest·Wiki 생성·Lint | `ai-svc` 비동기 worker | Queue depth, oldest message age, 실행 시간 |
| 파일 변환 | 변환 worker | Queue depth, 실행 시간, CPU·memory |
| 임베딩·색인 | 임베딩 실행 단위 | 색인 backlog, 반영 지연 |
| SSE 연결 | `backend-api` | 동시 연결 수, event 전달 지연 |

API는 CPU와 응답 시간을 중심으로 확장하고 worker는 Queue depth와 가장 오래 기다린 message 시간을 함께 사용한다. 실제 부하 시험 전에는 오토스케일 수치를 임의로 고정하지 않는다.

### 6.2 과부하 제어

확장만으로 무제한 트래픽을 처리하려 하지 않는다.

- API 진입점에서 Workspace별 요청률과 대기 작업 수를 제한한다.
- worker는 Workspace별 동시 실행 lease를 얻어 한 Workspace가 전체 worker를 점유하지 못하게 한다.
- LLM 호출 전 token·비용 budget을 확인한다.
- Queue 대기 시간이 한계를 넘으면 비필수 신규 작업을 거부하거나 재시도 가능 응답을 반환한다.
- 실시간 Query와 장시간 ingest·변환 작업은 다른 Queue와 worker pool을 사용한다.
- 외부 provider quota가 부족하면 낮은 우선순위 작업부터 load shedding한다.

Quota 상태는 권한 store와 실시간 store에 섞지 않는다. 구체적인 저장 기술은 원자성·비용·장애 시 동작을 검증한 뒤 선택한다.

### 6.3 공정성과 비용 보호

전체 시스템 한도와 Workspace 한도를 별도로 관리한다.

- Workspace별 요청률, pending 수와 동시 실행 수
- provider별 동시 호출과 token 사용량
- 문서 크기, Wiki 생성 page 수와 결과 크기
- Queue별 최대 대기 시간과 DLQ 증가율

한 Workspace의 제한 초과는 다른 Workspace의 정상 요청을 차단하는 전체 장애로 전파되지 않아야 한다.

---

## 7. AWS 운영 배치

### 7.1 Network와 실행 환경

- Route 53이 public DNS 진입점을 제공한다.
- 인터넷의 application API 요청은 WAF와 ALB를 통과한다.
- API와 worker는 private subnet에서 서로 다른 실행 단위로 배포한다.
- DB·store는 private network에 둔다.
- **`ai-svc`는 인터넷과 공개 ALB에서 도달할 수 없다.** 현재 host `:8000`, `:8010` 공개 상태는 전환 시 제거한다.
- S3 signed URL은 권한 확인 뒤 browser가 직접 사용하는 별도 data path다.
- 외부 LLM과 OAuth backend 호출은 공통 egress 경로를 사용한다.
- S3·SQS·Bedrock 등 AWS API는 가능한 경우 VPC Endpoint와 private 연결을 사용한다.

보안 그룹과 TLS만으로 내부 호출자를 신뢰하지 않는다. 비동기 worker callback과 내부 API는 검증 가능한 service identity를 사용한다(§4.4).

### 7.2 실행 플랫폼

기본 실행 플랫폼은 **ECS on Fargate**로 한다. 서비스가 3개이고 worker 종류가 소수인 단계에서 Kubernetes는 cluster 운영·upgrade·네트워킹 부담을 추가하면서 얻는 것이 적다. HPA·PodDisruptionBudget·NetworkPolicy에 해당하는 기능은 ECS Service Auto Scaling, deployment circuit breaker, 보안 그룹, Service Connect로 대체할 수 있다.

EKS로 승격하는 조건은 다음 중 둘 이상이 충족될 때다.

- (a) GPU node가 필요한 자체 추론을 운영한다
- (b) worker 종류가 늘어 Pod 단위 스케줄링·bin packing 이득이 측정된다
- (c) 조직에 이미 Kubernetes 운영 표준과 담당 인력이 있다

승격은 ADR로 승인하고 이 문서와 구조도를 함께 개정한다.

플랫폼과 무관하게 적용하는 운영 규칙은 다음과 같다.

- API와 worker에 health check와 resource request·limit을 설정한다.
- 실행 단위를 여러 가용 영역에 분산한다.
- 운영 인스턴스가 동시에 내려가지 않도록 배포 중 최소 가용 수를 보장한다.
- API와 worker에 서로 다른 오토스케일 정책을 적용한다.
- rolling update 오류율이 기준을 넘으면 이전 image로 되돌린다.
- DB migration은 인스턴스 시작 시 실행하지 않고 배포 단계의 별도 Job으로 수행한다.
- CPU·memory 경합이 실제로 확인될 때만 전용 실행 자원을 분리한다.

CI에서 application image를 build·test해 ECR에 저장하고 단계적으로 배포한다. Network·실행 플랫폼·RDS·IAM 같은 인프라는 Terraform의 plan·review·apply 절차로 관리하며 application 배포와 인프라 변경의 rollback 경계를 분리한다. 조직에 이미 동등한 IaC 표준이 있다면 도구는 대체할 수 있지만 수동 console 변경을 목표 운영 절차로 사용하지 않는다.

### 7.3 관리형 LLM

웹 AWS 배포에서는 GPU 기반 SLLM 서버를 직접 운영하지 않는다. 공통 inference adapter를 통해 Amazon Bedrock 또는 승인된 외부 LLM API를 호출한다. 실행 형태와 provider 선택지는 §4에서 다룬다.

---

## 8. 관측성·백업·보안

### 8.1 관측성

모든 HTTP 요청과 비동기 message는 `request_id`, `event_id`, Workspace 식별자와 trace 문맥을 전달한다.

Application trace는 OpenTelemetry로 계측해 AWS Distro for OpenTelemetry(ADOT) Collector를 거쳐 AWS X-Ray에 저장한다. 구조화 application·container log는 CloudWatch Logs, 인프라 metric과 application custom metric은 CloudWatch Metrics에 수집한다. CloudWatch Alarms가 임계값 위반을 감지하면 SNS를 통해 운영 알림 channel로 전달한다.

- API: 응답 시간, 오류율, 권한 조회 지연
- `backend-api` → `ai-svc`: 호출 지연, timeout 발생률, circuit breaker 상태, 콜백 실패율
- Queue: depth, oldest message age, retry, DLQ·quarantine
- Worker: 실행 시간, retry, lease 만료, 결과
- LLM: 첫 token 지연, 전체 시간, token·비용, provider 오류
- Document 편집: 자동저장 지연·실패율, revision 충돌률, 중복 write 재사용, RDS projection 지연
- Wiki: revision 충돌과 검색 projection 반영 지연
- 실행 플랫폼: task 재시작, health check 실패, 배포 롤백, 오토스케일 한계 도달

장시간 비동기 재발행은 새 trace로 기록하고 최초 요청 trace와 연결한다. 질문·문서 본문, access token과 API key는 일반 로그에 기록하지 않는다.

### 8.2 백업과 복구

Multi-AZ와 replica는 백업이 아니다.

| 저장소 | 보호 방식 |
|---|---|
| Access RDS | 자동 백업과 시점 복구 |
| Core RDS | 자동 백업과 시점 복구 |
| Document MongoDB | 관리형 snapshot·시점 복구, 정기 restore rehearsal |
| AI store | 원본에서 재생성 가능한 색인은 재구축, 실행 이력은 보존 기간 정책 적용 |
| S3 | Versioning과 Lifecycle |
| 권한 store·실시간 store | 원본 DB에서 재구축 |

권한 store는 Multi-AZ 복제와 자동 failover를 사용하고 Access RDS에서 재구축하는 절차와 시간을 검증한다. 권한 store가 복구될 때까지 Workspace 요청은 fail-closed되므로 재구축 시간은 전체 서비스의 허용 중단 시간 안에 들어와야 한다.

저장소별 RPO·RTO를 정하고 격리된 환경에서 정기적으로 복원한다. 장기 보존·교차 Region·immutable backup 요구가 생기면 AWS Backup 등 중앙 정책 도입을 검토한다.

### 8.3 보안

- 외부·내부 통신에 TLS 적용
- 저장소·log·backup 저장 암호화
- Pod Identity 또는 task role로 AWS 권한 분리
- DB 계정과 IAM을 서비스별 최소 권한으로 제한
- S3 Block Public Access 적용
- DB credential, OAuth secret과 외부 provider API key는 AWS Secrets Manager에 보관하고 지원되는 secret은 rotation 적용
- 파일 업로드는 크기·형식 제한, quarantine, 악성 파일 검사와 sandbox 적용
- 외부 LLM은 데이터 등급·provider·Region·보존 정책을 승인한 경우에만 사용

`ai-svc`에는 다음 세 가지를 추가로 적용한다.

1. VPC 내부에서만 도달 가능하며 어떤 공개 진입점도 갖지 않는다.
2. 모든 엔드포인트는 호출자 신원 검증 후에만 동작하며, 요청 본문의 `workspace_id`를 무검증 신뢰하지 않는다.
3. 요청별 provider 자격증명을 본문으로 받는 경로를 제거한다. 현재 `PipelineRunIn`은 무인증 엔드포인트에서 raw `api_key`를 받는다. 자격증명은 Secrets Manager에서만 로드한다.

---

## 9. 단계적 전환

### 9.1 전환 순서

```text
Phase 0  격리·인가 정합성 (서비스 분할 전 필수)
  - 역할 표기 통일과 쿼리 수정
  - 8곳의 verifyWorkspaceOwnership을 단일 인가 지점으로 통합
  - wiki_page_links · document_wiki_links · chat_partial_wiki에 workspace_id 추가
  - /api/query/runs/** 에 Workspace 스코프와 인증 적용
  - JWT에 iss·aud·kid 도입, JWKS 노출

Phase 1  상태의 외부화
  - OAuthExchangeCodeStore, QueryRunStore를 공유 store로 이동
  - DocumentEditStore 경계를 만들고 현재 편집 본문·revision·content hash를 MongoDB로 backfill·cutover
  - 5초 자동저장, optimistic locking과 revision_write_id 멱등성 검증
  - 프런트엔드 refresh 흐름 구현
  - 인스턴스 2대 이상 동시 실행 확인

Phase 2  ai-svc 신뢰 경계 확립
  - 전 엔드포인트에 호출자 인증 적용, 공개 포트 제거
  - GET /documents/{id} 등 스코프 없는 조회 제거·대체
  - backend-api의 AI client를 공용 구성으로 통합 (timeout·retry·circuit breaker)
  - 업무 테이블 write를 콜백 경유로 회수, AI store 분리
  - Converter를 ai-svc의 변환 경로로 연결 (현재 미연결)

Phase 3  access-svc 분리
  - user·security·workspace 이관, Access schema와 계정 분리
  - ALB 경로 라우팅 적용 (프런트엔드 변경 없음)
  - 권한 projection 도입, fail-closed 검증

Phase 4  AWS 실행 형태 확정
  - §4의 선택지 중 workload별 조합 확정, 부하·장애·복구 시험

Phase 5+ 도메인 분할 (후속)
  - 측정된 부하 격차가 확인되면 backend-api를 document·chat·wiki로 분할
  - 이 단계의 필드·상태 전이·Outbox 계약은 계약 문서를 참조
```

한 번에 전체 시스템을 교체하지 않는다. 각 단계는 기존 기능과 결과를 비교할 수 있어야 하며 데이터 backfill, cutover와 rollback 절차를 먼저 검증한다.

### 9.2 계약 문서와의 관계

[MSA 구현·운영 계약](msa-operational-contracts.md)은 도메인 4분할을 전제로 작성된 구현·운영 계약이다. 이 문서의 목표 구조는 3개 서비스이므로 두 문서의 서비스 이름이 일치하지 않는다. 계약 문서의 **필드·상태 전이·재처리 알고리즘은 서비스 개수와 무관하게 그대로 적용되고, 서비스 이름과 저장소 분할만 후속 단계의 목표로 읽는다.**

| 계약 문서의 프로그램 | 이 문서의 위치 | 적용 시점 |
|---|---|---|
| `access-svc` | `access-svc` (동일) | Phase 3 |
| `document-api`, `chat-api`, `wiki-api` | `backend-api` 안의 모듈 | Phase 5에 서비스로 분리 |
| `markdown-edit-engine`, `query-engine`, `wiki-generation-worker`, `lint-worker` | `ai-svc`의 동기·비동기 실행 경로 | Phase 2 |
| `converter-worker` | `ai-svc`의 변환 worker | Phase 2 (현재 미연결 상태 해소) |
| `indexer` | `ai-svc`의 색인 경로 | Phase 2 |
| `speech-worker` | 미구현 기능 | 범위 밖 |
| Access·Document·Chat RDS 분리 | Access schema · Core schema → 이후 RDS 분리 | Phase 3(schema) / Phase 5(물리) |
| Document 편집 MongoDB | 현재 본문·revision·content hash·저장 멱등성의 원본 | Phase 1 |
| Wiki MongoDB, Search/Vector | Core RDS + AI store | Phase 5 |
| 권한 Redis / 답변 Redis 분리 | 권한 store / 실시간 store | Phase 1(도입), Phase 3(분리) |

### 9.3 운영 전 필수 결정

| 항목 | 완료 조건 | 단계 |
|---|---|---|
| Document 편집 데이터 이전 | PostgreSQL `document_edit_states`의 MongoDB backfill, dual-read 검증, cutover와 rollback rehearsal | Phase 1 |
| 영역별 RDS 데이터 이전 | backfill 검증, cutover와 rollback rehearsal | Phase 3 |
| 내부 서비스 인증 | §4.4 방식 확정, 만료·audience·replay 방지 | Phase 2 |
| AI 동기·비동기 경로 분리 기준 | 어떤 요청이 동기이고 어떤 요청이 Queue인지의 판단 규칙 | Phase 2 |
| 임베딩 모델 실행 위치 | API 프로세스 분리 방식, 모델 교체 시 재색인 비용과 시간 | Phase 2 |
| message 호환성 | version 정책, DLQ·quarantine replay 절차 | Phase 2 |
| 인증 연속성 | JWKS cache·key 교체 중첩, 권한 store Multi-AZ failover와 재구축 시간 검증 | Phase 3 |
| 실시간 연결 | ALB timeout, heartbeat, SSE 재연결과 event 보존 정책 | Phase 1 |
| Quota | 원자적 lease, 장애 시 동작과 비용 정산 검증 | Phase 4 |
| 복구 목표 | 저장소별 RPO·RTO와 실제 복원 시험 | Phase 4 |
| 관측성 | SLI·SLO, 경보 임계값, 담당자와 runbook 연결 | Phase 4 |
| 실행 플랫폼 적합성 | ECS Fargate 기준 비용·운영 검증, EKS 승격 조건 재평가 | Phase 4 |
| Document MongoDB | conditional update, transaction, unique index, snapshot·복원 검증 | Phase 1 |
| Wiki MongoDB | transaction, change feed, snapshot·복원 검증 | Phase 5 |
| Search/Vector | Workspace 격리, 검색 목표와 전체 rebuild 시간 검증 | Phase 5 |

구체적인 구현 필드와 복구 알고리즘은 [MSA 구현·운영 계약](msa-operational-contracts.md)에 기록하고, 제품 선택과 운영 수치는 ADR 또는 runbook에서 확정한다.
