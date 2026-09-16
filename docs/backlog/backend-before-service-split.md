# Fruition Backend

Spring Boot 기반 문서 업로드 및 처리 백엔드 서버입니다.

## 기술 스택

| 항목 | 버전 |
|---|---|
| Java | 21 |
| Spring Boot | 3.5.x |
| PostgreSQL | 16 |
| MinIO | 최신 |
| Gradle | Wrapper 포함 |
| springdoc-openapi | 2.8.16 |

---

## 로컬 개발 환경 세팅

### 1. 사전 요구사항

- Java 21 이상 (`java -version` 으로 확인)
- Docker Desktop 실행 중

### 2. 인프라 실행 (PostgreSQL + MinIO)

`infra/` 디렉토리에서 실행합니다. `.env` 파일이 해당 위치에 있어야 합니다.

```bash
cd infra
docker compose -f compose.infra.yml up -d
```

컨테이너가 정상 기동되면 다음 서비스가 활성화됩니다.

| 서비스 | 주소 |
|---|---|
| PostgreSQL | `localhost:5432` |
| MinIO API | `localhost:9000` |
| MinIO 콘솔 | `http://localhost:9001` |

MinIO 콘솔 로그인: `fruition` / `fruition_dev_secret`

### 3. 서버 실행

```bash
cd backend
./gradlew bootRun
```

서버가 기동되면 `http://localhost:8080` 에서 응답합니다.

### 4. 인프라 종료

```bash
# infra/ 디렉토리에서 실행
docker compose -f compose.infra.yml down
```

볼륨까지 초기화하려면:

```bash
docker compose -f compose.infra.yml down -v
```

---

## 데이터베이스 스키마 (Flyway)

DB 스키마는 **Flyway가 단일 소스로 관리**합니다. 앱은 기동 시 스키마를 검증만 하고(`spring.jpa.hibernate.ddl-auto=validate`), 실제 테이블 생성/변경은 `backend/src/main/resources/db/migration/` 아래 `Vn__*.sql` 마이그레이션으로만 이뤄집니다.

- 마이그레이션은 `./gradlew bootRun` 기동 시 자동 적용됩니다. 별도 명령이 필요 없습니다.
- Spring Session 테이블(`spring_session*`)은 Flyway 관리 대상이 아니며 Spring Session JDBC가 별도로 생성합니다.

### 처음 받았을 때 / 브랜치를 pull 한 뒤 (팀원 공통)

기존 로컬 DB가 예전 스키마(`ddl-auto=update` 시절의 잔재 포함)면 새 baseline과 맞지 않아 기동이 실패할 수 있습니다. **로컬 DB를 한 번 비우고 새로 만들면** 됩니다. 로컬 데이터는 소모성입니다.

```bash
# infra/ 디렉토리에서
docker compose -f compose.infra.yml down -v   # postgres 볼륨 삭제
docker compose -f compose.infra.yml up -d

# backend/ 디렉토리에서
./gradlew bootRun   # 빈 DB에 Flyway가 V1부터 자동 적용
```

이후 평상시에는 `git pull` 뒤 `./gradlew bootRun`만 하면 새 마이그레이션이 자동 적용됩니다.

### 스키마를 바꿀 때 (엔티티 수정 시)

엔티티를 수정하면 **같은 PR에 마이그레이션 파일을 함께** 추가해야 합니다. `ddl-auto=validate`라 마이그레이션을 빠뜨리면 기동이 실패하므로 누락이 바로 드러납니다.

1. `db/migration/`에 다음 번호로 파일을 추가합니다. 예: `V3__add_xxx_column.sql`
   - 파일명 형식: `V<번호>__<설명>.sql` (버전과 설명 사이 밑줄 2개)
2. 변경 DDL을 작성합니다. 예: `ALTER TABLE documents ADD COLUMN xxx varchar(255);`
3. `./gradlew bootRun` 또는 `./gradlew test`로 적용/검증합니다.

> **이미 머지된 마이그레이션 파일은 절대 수정하지 않습니다.** 항상 새 번호로 추가하세요. Flyway가 적용 이력(`flyway_schema_history`)과 체크섬을 추적하므로, 적용된 파일을 바꾸면 검증에 실패합니다.

### 운영/공유 DB

`spring.flyway.baseline-on-migrate=true`가 설정되어, 이미 데이터가 있는 기존 DB는 V1을 재실행하지 않고 v1로 마킹만 한 뒤 V2부터 적용합니다. 기존 DB도 데이터 유지한 채 Flyway로 편입됩니다.

### 상태 모니터링

**적용 상태 한눈에 보기 (Flyway Gradle 플러그인):**

```bash
cd backend
./gradlew flywayInfo        # 각 마이그레이션의 Version/State(Success/Pending 등) 표로 출력
./gradlew flywayValidate    # 로컬 파일과 DB 적용 이력의 정합성(체크섬 등) 검증
```

`flywayInfo`/`flywayValidate`는 접속 정보를 `infra/.env`에서 읽습니다(없으면 로컬 기본값). `bootRun`이 아니므로 DB(Docker)만 떠 있으면 됩니다.

**적용 이력 직접 조회 (psql):**

```bash
docker compose -f infra/compose.infra.yml exec -T postgresql \
  psql -U fruition -d fruition_mvp \
  -c "SELECT installed_rank, version, description, success, installed_on FROM flyway_schema_history ORDER BY installed_rank;"
```

`success`가 모두 `t`면 정상입니다. `flyway_schema_history`가 Flyway의 진실 소스입니다.

**기동 로그:** 적용 시 `Migrating schema "public" to version "N - ..."` / `Successfully applied N migration(s)`, 변경 없을 때 `No migration necessary`가 찍힙니다.

### 트러블슈팅

| 증상 | 원인 | 대처 |
|---|---|---|
| 기동 실패 `Schema-validation: missing table/column ...` | 엔티티는 바꿨는데 마이그레이션을 안 만듦 | 해당 변경의 `Vn__*.sql`을 추가 |
| `Migration checksum mismatch` | 이미 적용된 마이그레이션 파일을 수정함 | 파일을 원상복구하고 변경은 **새 번호**로 추가. `./gradlew flywayValidate`로 확인 |
| `Detected applied migration not resolved locally` | 로컬에 없는 버전이 DB에만 적용됨(브랜치 꼬임) | 브랜치/파일 정합성 확인, 로컬 DB 리셋(`down -v`) |
| 마이그레이션 SQL 오류로 기동 실패 | SQL 문법/제약 위반 | Postgres는 트랜잭션 DDL이라 실패분은 롤백됨 → SQL 고쳐 다시 `bootRun`(대개 수동 복구 불필요) |
| FK/제약 추가가 실패 | 기존 DB에 무결성 안 맞는(고아) 데이터 | 로컬은 리셋, 운영은 데이터 정리 후 적용 |

### 마이그레이션 작성 관행

- 한 마이그레이션 = 하나의 논리적 변경. 무관한 변경을 섞지 않습니다.
- 파괴적 변경은 단계적으로(expand-contract): 컬럼 rename은 ① 새 컬럼 추가 → ② 백필/양쪽 사용 → ③ 다음 릴리스에서 옛 컬럼 DROP.
- 두 사람이 동시에 같은 번호를 만들면 나중 머지하는 쪽이 다음 번호로 조정합니다.
- 운영 DB는 리셋 금지, 파괴적 변경 전 백업.

---

## 환경 변수

환경 변수는 `infra/.env` 파일에서 관리합니다.
처음 세팅할 때 `infra/.env.example`을 복사해서 사용하세요.

```bash
cp infra/.env.example infra/.env
```

`./gradlew bootRun` 실행 시 `infra/.env`를 자동으로 읽어 환경변수를 주입합니다.
Docker Compose 인프라 기동 시에도 동일한 파일을 사용하므로 값을 한 곳에서만 관리하면 됩니다.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | PostgreSQL 호스트 |
| `POSTGRES_PORT` | `5432` | PostgreSQL 포트 |
| `POSTGRES_DB` | `fruition_mvp` | 데이터베이스명 |
| `POSTGRES_USER` | `fruition` | DB 사용자명 |
| `POSTGRES_PASSWORD` | `fruition_dev_password` | DB 비밀번호 |
| `S3_ENDPOINT` | `http://localhost:9000` | MinIO 엔드포인트 |
| `S3_ACCESS_KEY` | `fruition` | MinIO 액세스 키 |
| `S3_SECRET_KEY` | `fruition_dev_secret` | MinIO 시크릿 키 |
| `S3_BUCKET` | `fruition-storage` | 오브젝트 스토리지 버킷명 |
| `PROCESSING_ENDPOINT` | `http://localhost:8000/pipeline/runs` | FastAPI 문서 처리 파이프라인 실행 엔드포인트 |
| `OPENAI_API_KEY` | (없음) | ai-svc가 OpenAI live 호출에 사용하는 secret |
| `GEMINI_API_KEY` | (없음) | ai-svc가 Gemini live 호출에 사용하는 secret |
| `ANTHROPIC_API_KEY` | (없음) | ai-svc가 Claude live 호출에 사용하는 secret |

provider/model은 사용자 설정·API·DB·Kafka payload snapshot에서 정하며 backend env override와 API key 전달은 없다. 지원 조합은 `openai/gpt-5-nano`(기본), `gemini/gemini-3.1-flash-lite`, `claude/claude-sonnet-5`다.

---

## API

### Swagger UI

서버 실행 후 브라우저에서 전체 API 명세를 확인할 수 있습니다.

```
http://localhost:8080/swagger-ui.html
```

### Health check

actuator는 업무 포트(8080)가 아니라 관리 포트(8082)에 있다. access-svc는 8083이다.

```bash
curl http://localhost:8082/actuator/health
```

정상 응답은 `{"status":"UP"}`입니다.

### 엔드포인트 목록

#### Documents

| 메서드 | 경로 | 설명 | 상태 |
|---|---|---|---|
| `POST` | `/api/workspaces/{workspace_id}/documents` | 문서 업로드 (PDF/Markdown) | 구현 완료 |
| `GET` | `/api/workspaces/{workspace_id}/documents` | 문서 목록 조회 | 구현 완료 |
| `GET` | `/api/workspaces/{workspace_id}/documents/{document_id}` | 문서 상세 조회 | 구현 완료 |
| `PATCH` | `/api/documents/{document_id}/status` | FastAPI 콜백 — 처리 상태 업데이트 | 구현 완료 |

#### Wiki

| 메서드 | 경로 | 설명 | 상태 |
|---|---|---|---|
| `GET` | `/api/wiki/graph` | Wiki 그래프 전체 조회 | 구현 완료 |
| `GET` | `/api/wiki/pages/{wiki_page_id}` | Wiki 페이지 상세 조회 | 구현 완료 |

#### Query

| 메서드 | 경로 | 설명 | 상태 |
|---|---|---|---|
| `POST` | `/api/query` | 자연어 질의응답 | 스텁 (501) |

#### Chat

| 메서드 | 경로 | 설명 | 상태 |
|---|---|---|---|
| `GET` | `/api/chat/messages` | 채팅 메시지 목록 조회 | 스텁 (빈 목록 반환) |

---

### 공통 에러 응답 형식

```json
{
  "error": {
    "code": "에러_코드",
    "message": "에러 메시지",
    "details": [
      { "field": "필드명", "reason": "오류 사유" }
    ]
  }
}
```

`details`는 입력 유효성 검사 오류(`400 INVALID_REQUEST`)일 때만 포함됩니다.

---

### POST /api/workspaces/{workspace_id}/documents — 문서 업로드

**요청**

```
POST /api/workspaces/{workspace_id}/documents
Authorization: Bearer {access_token}
Content-Type: multipart/form-data
```

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `file` | MultipartFile | O | 업로드할 파일 (PDF 또는 Markdown) |

허용 형식: `application/pdf`, `text/markdown` / `text/x-markdown` (`.md`)

```bash
curl -X POST http://localhost:8080/api/workspaces/{workspace_id}/documents \
  -H "Authorization: Bearer {access_token}" \
  -F "file=@/path/to/document.pdf"
```

**응답 (201 Created)**

```json
{
  "id": "doc_a1b2c3d4",
  "filename": "document.pdf",
  "mime_type": "application/pdf",
  "byte_size": 204800,
  "status": "processing",
  "source_uri": "sources/documents/doc_a1b2c3d4/original",
  "uploaded_at": "2026-06-10T07:00:00Z"
}
```

| HTTP 상태 | 코드 | 설명 |
|---|---|---|
| 400 | `INVALID_REQUEST` | 파일이 없거나 비어 있음 |
| 409 | `DOCUMENT_ALREADY_EXISTS` | 동일 파일이 이미 업로드됨 (SHA-256 기준) |
| 415 | `UNSUPPORTED_FILE_TYPE` | PDF, Markdown 외 파일 형식 |
| 500 | `INTERNAL_SERVER_ERROR` | 서버 처리 오류 |

---

### PATCH /api/documents/{document_id}/status — FastAPI 콜백

FastAPI 파이프라인이 문서 처리 단계마다 Spring 서버로 호출하는 콜백 엔드포인트입니다.

**요청**

```
PATCH /api/documents/{document_id}/status
Content-Type: application/json
```

```json
{
  "status": "completed",
  "extracted_text_uri": "sources/documents/doc_a1b2c3d4/extracted.txt",
  "processed_at": "2026-06-10T07:05:00Z",
  "error_message": null
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `status` | `processing` \| `completed` \| `failed` | O | 처리 상태 |
| `extracted_text_uri` | string | X | 추출된 텍스트 Object Storage 경로 |
| `processed_at` | ISO 8601 | X | 처리 완료 시각 |
| `error_message` | string | X | 실패 사유 (`status=failed` 시 사용) |

**응답 (204 No Content)**

| HTTP 상태 | 코드 | 설명 |
|---|---|---|
| 204 | — | 상태 업데이트 성공 |
| 400 | `INVALID_REQUEST` | 요청 형식 오류 |
| 404 | `DOCUMENT_NOT_FOUND` | 문서 ID 없음 |

---

### FastAPI 연동 흐름

```text
[Spring] POST /api/workspaces/{workspace_id}/documents
  → MinIO에 원본 파일 저장 (sources/documents/{id}/original)
  → documents 레코드 생성 (status=processing)
  → 사용자에게 201 응답
  → [비동기] FastAPI에 POST {PROCESSING_ENDPOINT}
        body: { "document_id": "..." }

[FastAPI] documents row 조회 → MinIO에서 Markdown/text 입력 fetch
  → Wiki Markdown / graph 결과 생성
  → wiki_pages / document_wiki_links / wiki_page_links 저장
  → documents.status, pipeline_runs 상태 업데이트
```

---

## 패키지 구조

```
backend/src/main/java/fruition/poc/backend/
├── BackendApplication.java
├── common/
│   ├── ErrorResponse.java               # 공통 에러 응답 (field 오류 목록 포함)
│   └── GlobalExceptionHandler.java      # 전역 예외 처리 (validation, 404 등)
├── config/
│   ├── MinioConfig.java                 # MinIO 클라이언트 빈
│   ├── OpenApiConfig.java               # Swagger 설정
│   └── StorageProperties.java           # 스토리지 설정값
├── document/
│   ├── api/
│   │   └── DocumentController.java      # Documents REST 엔드포인트 (4개)
│   ├── application/
│   │   └── DocumentService.java         # 업로드 / 조회 / 상태 업데이트 로직
│   ├── domain/
│   │   ├── Document.java                # JPA 엔티티
│   │   ├── DocumentNotFoundException.java
│   │   ├── DocumentStatus.java          # enum: processing / completed / failed
│   │   ├── DocumentUploadException.java
│   │   └── DuplicateDocumentException.java
│   ├── dto/
│   │   ├── DocumentDetailResponse.java  # 문서 상세 응답 (wiki_pages 포함)
│   │   ├── DocumentListResponse.java    # 문서 목록 응답
│   │   ├── DocumentStatusUpdateRequest.java  # FastAPI 콜백 요청 DTO
│   │   ├── DocumentUploadResponse.java  # 업로드 응답
│   │   └── DocumentWikiPageRef.java     # 연결된 Wiki 페이지 참조
│   └── infra/
│       ├── DocumentProcessingRequester.java  # FastAPI 처리 요청 (RestClient)
│       └── DocumentRepository.java           # JPA Repository
├── wiki/
│   ├── api/
│   │   └── WikiController.java          # Wiki REST 엔드포인트 (2개)
│   ├── application/
│   │   └── WikiService.java             # 그래프 조회 / 페이지 상세 조회 로직
│   ├── domain/
│   │   ├── DocumentWikiLink.java        # 문서 ↔ Wiki 페이지 연결 JPA 엔티티
│   │   ├── DocumentWikiLinkId.java      # 복합키 클래스
│   │   ├── DocumentWikiRelationType.java # enum: primary_source / supporting / referenced
│   │   ├── WikiPage.java                # Wiki 페이지 JPA 엔티티
│   │   ├── WikiPageLink.java            # Wiki 페이지 간 링크 JPA 엔티티
│   │   ├── WikiPageLinkId.java          # 복합키 클래스
│   │   ├── WikiPageNotFoundException.java
│   │   ├── WikiPageStatus.java          # enum: active / draft / archived
│   │   └── WikiPageType.java            # enum: CONCEPT / PROCESS / ENTITY / OVERVIEW
│   ├── dto/
│   │   ├── WikiGraphEdge.java
│   │   ├── WikiGraphNode.java
│   │   ├── WikiGraphResponse.java
│   │   ├── WikiPageDetailResponse.java
│   │   ├── WikiPageSourceDoc.java
│   │   └── WikiRelatedPage.java
│   └── infra/
│       ├── DocumentWikiLinkRepository.java  # findAllByIdWikiPageId 포함
│       ├── WikiPageLinkRepository.java      # findAllByIdFromPageId 포함
│       └── WikiPageRepository.java          # Spring Data JPA Repository
├── query/
│   ├── api/
│   │   └── QueryController.java         # Query 엔드포인트 스텁
│   └── dto/
│       ├── HighlightedPath.java
│       ├── QueryRelatedPage.java
│       ├── QueryRequest.java
│       ├── QueryResponse.java
│       └── SourceReference.java
└── chat/
    ├── api/
    │   └── ChatController.java          # Chat 엔드포인트 스텁
    └── dto/
        ├── ChatMessageReference.java
        ├── ChatMessageResponse.java
        └── ChatMessagesResponse.java
```

---

## 자주 겪는 문제

**PostgreSQL 연결 실패**

Docker 컨테이너가 완전히 기동되기 전에 서버를 실행하면 연결 오류가 발생합니다.
`docker compose ps` 로 `postgresql` 컨테이너 상태가 `healthy`인지 확인 후 서버를 다시 기동하세요.

**MinIO 버킷 없음 오류**

`minio-init` 컨테이너가 버킷을 자동 생성합니다. 컨테이너 로그를 확인하세요.

```bash
docker logs fruition-minio-init-dev
```

**포트 충돌**

로컬에서 PostgreSQL이나 MinIO가 이미 실행 중이라면 포트가 충돌합니다.
기존 프로세스를 종료하거나 `infra/compose.infra.yml`의 포트 매핑을 변경하세요.

**FastAPI 처리 요청 실패**

`PROCESSING_ENDPOINT`에 FastAPI Pipeline 서버가 실행 중이지 않아도 업로드 응답(201)은 정상 반환됩니다.
실패 시 서버 로그에 `[파이프라인 실행 요청 실패]` 경고가 기록됩니다.
