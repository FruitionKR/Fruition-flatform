# Changelog — Infra

로컬 개발 인프라 변경 이력입니다. 날짜 역순으로 기록합니다.

---

## 2026-08-10

- backend에서 노출할 AI provider를 제한하는 `AI_ENABLED_PROVIDERS` 설정을 로컬 배포 예시와 Kubernetes ConfigMap에 추가했다.
- 기본 활성 provider는 `openai`다.

## 2026-08-07

### feat: AWS 배포 IaC와 EKS overlay·deploy workflow

- `infra/terraform/` 신설 — 목표 문서 §8 소규모 profile: VPC(2AZ·NAT 1),
  EKS(General t3.large 2/2/3 On-Demand + AI Worker Spot 0/0/2 taint) + IRSA 4종,
  **RDS 2대 분할**(access/core, t4g.small Single-AZ), ElastiCache(t4g.micro),
  S3(versioning·lifecycle)+앱 IAM 키, ECR 4 repo, GitHub OIDC deploy role,
  Secrets Manager `fruition/app`(DB URL·계정 비밀번호 자동, 나머지 CHANGE_ME,
  이후 콘솔 관리 — ignore_changes), Budget 500/700. `terraform validate` 통과.
- `k8s/overlays/aws/` — base 참조 + ECR 이미지 치환, NodePort→ClusterIP,
  ALB Ingress(host 기반: api.→document, access.→access — Vercel rewrite가 path
  분기 담당), ExternalSecret←Secrets Manager, deployment별 RDS host 주입,
  §8.2 resource 상향. pipeline-runs PVC(RWO) 제약으로 ingest-worker는
  pipeline-api와 podAffinity 동일 노드 배치(S3 이전 시 해제).
- `.github/workflows/deploy.yml` — workflow_dispatch 수동 트리거, OIDC →
  이미지 4종 빌드·ECR push(SHA 태그) → kustomize set image → rollout 대기.
- Kafka는 MSK가 아니라 EKS 내 Strimzi 유지(§8.3). 잔여 수동 절차는
  `infra/terraform/README.md`·`docs/issue/infra/2026-08-07.md`.

### feat: edit-event-consumer 배포 단위와 k8s base kustomization

- `k8s/base/edit-event-consumer.yaml` 신규(ingest-worker 이미지 재사용, replicas 1),
  `k8s/base/kustomization.yaml` 신설 — 앱 계층만 포함(상태 계층은 kind 전용으로 제외,
  AWS overlay가 이 base를 참조).
- compose에 `edit-event-consumer` 서비스 추가(필요 env만 축소 주입).

### feat: MongoDB(replica set)·document.edit.event topic 인프라

- k8s에 mongodb 매니페스트 추가(mongo:7.0 단일 replica set rs0 — 트랜잭션 필요),
  Strimzi `document.edit.event` KafkaTopic(partitions 12) 추가.
- dev compose kafka-init에 `document.edit.event` topic 생성 추가(auto-create off 환경).

### feat: PostgreSQL 3-DB·계정 격리 로컬 인프라

- postgres 컨테이너가 최초 기동 시 `access_db`/`core_db`/`ai_db` + runtime/migration
  계정 6개를 자동 생성(`infra/postgres/init-db-isolation.sh`, 참조 브랜치
  feat/msa-db-isolation 포팅). ai_runtime에는 core_db 전환기 grant 포함.
- 격리 검증 컨테이너 추가: `docker compose --profile validation up db-isolation-validate`
  — 비superuser·own DML·runtime CREATE 거부·타 DB write 거부 검사.
- compose(dev/pipeline/deploy)와 k8s(base configmap·secret·postgres init ConfigMap),
  `.env.example`을 새 계약(ACCESS_DB_*/CORE_DB_*/AI_* env)으로 전환.
- MongoDB(replica set rs0) dev compose 서비스는 문서 편집 원본 전환 커밋에서 사용
  (같은 파일에 포함되어 이 커밋에 동반됨). 주의: colima bind mount 캐시로 수정
  스크립트가 컨테이너에 부분 반영될 수 있음 — 재기동 또는 docker cp로 해소.

### feat: Kubernetes 매니페스트 도입 (kind 로컬 검증 완료)

- `k8s/` 신설: kind 클러스터 구성 + Strimzi Kafka(KRaft, `ai.ingest.command` 12
  partitions) + KEDA(ingest-worker lag 기반 min1/max4) + 전 서비스
  Deployment/Service/ConfigMap/Secret/NetworkPolicy + 상태 계층(postgres·redis·minio).
- kind 실검증: 전 pod Ready, Flyway migration, 가입·로그인 스모크, pipeline 내부 토큰
  401/통과, worker consumer group join(12 partition), pod 강제 삭제 자가 복구,
  NetworkPolicy 시행(외부 namespace에서 pipeline 차단), KEDA ScaledObject Ready.
- 접속: `http://localhost:30080` (NodePort). 절차는 `k8s/README.md`.
- 한계: LLM_API_KEY secret 주입 필요, pipeline-runs PVC는 단일 노드 전제(멀티 노드 시
  S3 이전), 상태 계층 single replica(EKS에선 RDS·ElastiCache·MSK·S3로 대체).

---

## 2026-08-06

### feat: Kafka 도입·backend 컨테이너화·배포 compose

- `compose.infra.yml`에 Kafka(KRaft 단일 브로커, apache/kafka:3.9) + topic 초기화
  (`ai.ingest.command` partitions 12) 추가. 컨테이너는 `kafka:19092`, 호스트는
  `localhost:9092`로 접속(이중 리스너).
- `compose.ai.yml`에 `ingest-worker` 서비스 추가(pipeline 이미지 공용,
  command만 교체).
- `services/backend/Dockerfile` 신설(gradle 멀티스테이지→JRE) +
  `compose.containerized.yml`로 backend까지 컨테이너 실행하는 배포 단위 검증 구성.
- `.env.example`에 `KAFKA_BOOTSTRAP_SERVERS`·`INGEST_COMMAND_TOPIC` 추가.

### feat: Redis 도입·내부 포트 루프백 제한

- `compose.infra.yml`에 `redis:7-alpine` 서비스 추가(healthcheck 포함). backend의
  공유 store(OAuth 교환 코드, query run 상태·SSE 중계)가 사용한다. AWS에서는
  ElastiCache로 대체한다.
- pipeline(:8000)·converter(:8010) 포트 바인딩을 `127.0.0.1`로 제한해 호스트 외부에서
  도달할 수 없게 했다.
- `.env.example`에 `REDIS_HOST`/`REDIS_PORT` 추가.

---

## 2026-08-05

### fix: Backend와 llmPipeline의 결과 콜백 토큰 공유

- `infra/.env.example`과 pipeline 전용 예시에 `INTERNAL_CALLBACK_TOKEN`을 추가
- pipeline API 컨테이너에 같은 환경변수를 전달해 Backend의 `app.internal.callback-token`과 공유

## 2026-08-03

### feat: Agent worker 실행과 내부 인증 설정 추가

- `agent-skills` Compose profile에 PostgreSQL job 기반 `pipeline-agent-worker`와 process health check를 추가
- pipeline API와 worker에 공통 `AGENT_INTERNAL_TOKEN`을 전달해 Backend↔llmPipeline 내부 Agent 통신의 `X-Agent-Service-Token` 검증에 사용
- `AGENT_SKILLS_ENABLED=false`를 기본값으로 유지하고 Docker image에 `agent_worker.py`를 포함
- Compose config와 llmPipeline 전체 테스트 `651 passed`, `49 subtests passed` 통과

## 2026-07-28

### fix: Pipeline LLM 환경변수 전달 단일화

- `compose.ai.yml`에서 legacy `UPSTAGE_*` 전달을 제거하고 모든 provider가 `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`만 사용하도록 통일
- `infra/.env.example`과 `infra/.env.pipeline.example`을 같은 계약으로 갱신하고 Compose 설정 렌더링 검증 통과

## 2026-07-24

### fix: pipeline 컨테이너에 범용 LLM env(LLM_*) 전달 추가

**변경된 내용**

- `compose.ai.yml`의 pipeline-api 환경변수에 `LLM_API_KEY/LLM_BASE_URL/LLM_MODEL`을 추가 전달하고, `LLM_PROVIDER`를 `${LLM_PROVIDER:-upstage}`로 일반화했다. `UPSTAGE_MODEL/UPSTAGE_BASE_URL`의 강제 기본값(solar-pro2 / upstage v1)을 제거해 빈 값 pass-through로 바꿨다.

**배경**

- Upstage → Gemini(OpenAI 호환 엔드포인트) 전환 시, compose가 `LLM_*`를 컨테이너에 전달하지 않고 `UPSTAGE_BASE_URL` 기본값을 강제해 우선순위상 Upstage가 이겨 `agent/turn`이 503(RuntimeError: Missing API key)으로 실패했다. 이를 해결.

**검증**

- pipeline 컨테이너 재생성 후 `printenv`로 `LLM_*` 주입 확인. `agent/turn` 200 복구, Gemini가 실제 문서 편집 반영.

**남은 주의사항**

- 당시 채팅→원본문서 편입의 wiki 생성(ingestion) 경로는 `run_lab.py`가 `UPSTAGE_API_KEY`를 별도로 강제해 실패했다. 해결 기록은 `docs/backlog/issue-2026-07-25.md`의 `AI/Pipeline — Multi-provider 설정과 Claude Messages API 지원`을 참고한다.

**gitignore**

- Playwright MCP 테스트 산출물(`.playwright-mcp/`, 루트 `*.png` 스크린샷)을 `.gitignore`에 추가.

---

## 2026-07-23

### fix: 로컬 이메일 인증 profile 기본값 정리

- `./gradlew bootRun`이 별도 지정이 없을 때 `local` profile로 실행되도록 하고, 외부 `SPRING_PROFILES_ACTIVE`는 유지한다.
- `infra/.env.example`에 로컬 전용 `AUTH_EMAIL_DEV_FIXED_CODE=9700` 예시를 추가했다.
- production 공통 설정은 고정 코드가 없는 기존 기본값을 유지한다.

## 2026-07-22

### fix: 프론트엔드 의존성 취약점 자동 수정

- `scripts/bootstrap.sh`가 `npm install` 후 `npm audit fix`를 실행하도록 변경했다.
- breaking change를 피하기 위해 `--force`는 사용하지 않으며, 자동 수정되지 않은 취약점이 있어도 개발 서버 기동을 계속한다.
- `bash -n scripts/bootstrap.sh`, `git diff --check` 통과.

## 2026-07-21

### chore: 로컬 노트 저장 mock profile 활성화

- `scripts/dev-up.sh`가 별도 profile 지정이 없을 때 backend를 `local` profile로 실행하도록 변경했다.
- 외부에서 `SPRING_PROFILES_ACTIVE`를 지정하면 해당 값을 유지한다.
- `bash -n scripts/dev-up.sh` 통과.

## 2026-07-20

### fix: dev-up backend readiness 확인 복구

**배경**

사용자용 Document API가 `/api/workspaces/{workspace_id}/documents`로 이동한 뒤에도 `scripts/dev-up.sh`가 제거된 `GET /api/documents`를 확인하고 있었습니다. 백엔드가 정상 기동해도 이 요청이 `405 Method Not Allowed`를 반환해 스크립트가 60초 후 실패하고 프론트엔드를 시작하지 못했습니다.

빈 PostgreSQL에서도 pipeline API가 backend보다 먼저 공용 테이블을 생성하면서 Flyway가 schema를 기존 DB로 판단해 V1을 건너뛰었고, V3가 존재하지 않는 `workspaces` 테이블을 참조해 backend 기동이 실패했습니다.

**변경된 것**

- `scripts/dev-up.sh` — backend readiness 확인 URL을 업무 API와 분리된 `GET /actuator/health`로 변경
- `scripts/dev-up.sh` — PostgreSQL/MinIO → backend Flyway → pipeline API → frontend 순서로 변경해 backend와 pipeline의 schema 초기화 race 제거
- `docs/local-runbook.md` — 자동·수동 실행의 backend 확인 URL과 정상 응답 문서화
- `backend/README.md` — health endpoint와 현재 workspace 기반 Document API 경로 반영

**검증**

- `bash -n scripts/dev-up.sh`
- `./gradlew test`
- `./scripts/dev-up.sh`로 PostgreSQL/MinIO, pipeline API, 백엔드, 프론트엔드 기동 확인

## 2026-07-04

### ci: web-services workflow 검증 강화

**배경**

기존 CI의 `docker compose ps` 단계는 컨테이너가 죽어 있어도 exit 0이라 실패를 잡지 못했고, timeout·concurrency·paths 필터가 없어 잡 멈춤이나 불필요한 실행에 취약했습니다.

**변경된 것**

- `.github/workflows/web-services.yml` — `up -d --wait --wait-timeout 120`으로 healthcheck 통과까지 대기하도록 변경하고, 가짜 검증이던 `ps` 단계를 `minio-init` 컨테이너 exit code 확인으로 교체
- `.github/workflows/web-services.yml` — `paths` 필터(`infra/**`, workflow 자체), `concurrency`(cancel-in-progress), `timeout-minutes: 10` 추가
- `.github/workflows/web-services.yml` — `down` 단계에도 `--env-file infra/.env.example`을 지정해 변수 미정의 경고 제거

**검증**

- YAML 문법 검사 통과 (ruby YAML.load_file)
- 로컬 `up`/`down -v` 실행 검증은 로컬 dev 볼륨(`fruition-mvp-dev`) 삭제 위험으로 생략 — PR의 Actions run으로 실제 동작 확인 필요
- minio 서비스에 healthcheck가 없어 `--wait`는 running 상태만 확인함 — 추후 compose에 minio healthcheck 추가 여지 있음

## 2026-07-01

### chore: LangSmith tracing과 evaluator graph 환경변수 추가

**배경**

로컬 pipeline API에서 LangSmith tracing과 query evaluator graph 재시도 횟수를 같은 compose 설정으로 관리해야 했습니다.

**변경된 것**

- `infra/.env.example`에 `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT`, `QUERY_EVALUATOR_MODE`, `QUERY_EVALUATOR_MAX_ATTEMPTS` 예시를 추가했습니다.
- `infra/compose.ai.yml`에서 LangSmith와 query evaluator 환경변수를 pipeline container로 전달하도록 추가했습니다.

**검증**

- `docker compose --env-file infra/.env -f infra/compose.infra.yml -f infra/compose.ai.yml up -d --build pipeline-api`로 pipeline container 재빌드 확인.
- 컨테이너 내부에서 `LANGSMITH_TRACING=true`, `QUERY_EVALUATOR_MODE=llm`, `QUERY_EVALUATOR_MAX_ATTEMPTS=2` 반영 확인.

## 2026-06-28

### chore: pipeline query 보강 설정 추가

**배경**

Query evaluator, web search 보강, 내부 근거 관련도 기준을 로컬 pipeline API에서 환경변수로 제어할 수 있어야 했습니다.

**변경된 것**

- `infra/compose.ai.yml` — `QUERY_EVALUATOR_MODE`, `QUERY_WEB_SEARCH_MODE`, `QUERY_WEB_SEARCH_MAX_RESULTS`, `QUERY_WEB_SEARCH_TIMEOUT_SECONDS`, `QUERY_MIN_INTERNAL_RELEVANCE_SCORE` 환경변수 추가
- `infra/compose.ai.yml` — `TAVILY_API_KEY`를 외부 환경변수로 주입할 수 있게 추가

**검증**

- `PYTHONPATH=llmPipeline llmPipeline/.venv/bin/python -m pytest llmPipeline/tests -q`

---

## 2026-06-26

### chore: 로컬 bootstrap 스크립트 추가

**배경**

처음 저장소를 실행하는 컴퓨터에서 필요한 프로젝트 의존성을 매번 수동으로 확인하고 설치해야 했습니다.

**변경된 것**

- `scripts/bootstrap.sh` — 필수 명령과 Node.js/npm/Java 버전을 확인하고, `infra/.env` 생성과 프론트엔드 의존성 설치를 자동화
- `scripts/bootstrap.sh` — `--with-python` 옵션으로 `llmPipeline/.venv` 생성과 `llmPipeline/requirements.txt` 설치 지원
- `scripts/dev-up.sh` — 실행 시작 시 bootstrap을 먼저 호출하도록 변경
- `docs/local-runbook.md` — bootstrap 사용법과 Python 가상환경 옵션 문서화

**검증**

- `bash -n scripts/bootstrap.sh`
- `bash -n scripts/dev-up.sh`

---

## 2026-06-18

### chore: dev-up pipeline API 포함

**배경**

채팅 질의와 문서 업로드 후 처리는 Spring 백엔드가 `localhost:8000`의 pipeline API를 호출해야 합니다. 기존 `scripts/dev-up.sh`는 PostgreSQL, MinIO, 백엔드, 프론트엔드만 실행해 `POST /api/query`가 503으로 실패하고 업로드 문서가 `processing`에 머물 수 있었습니다.

또한 `infra/compose.ai.yml`로 실행했던 `pipeline-api` 컨테이너가 중지 상태로 남으면, 기본 `scripts/dev-up.sh` 실행 시 Docker Compose가 orphan container 경고를 출력했습니다.

**변경된 것**

- `scripts/dev-up.sh` — `infra/compose.infra.yml`와 `infra/compose.ai.yml`을 함께 실행하고 `http://localhost:8000/health`까지 확인하도록 변경
- `scripts/dev-up.sh` — `fruition-mvp-dev` project의 중지된 `pipeline-api` 컨테이너만 `docker compose up` 전에 정리하도록 추가
- `scripts/dev-down.sh` — pipeline API compose 파일과 `8000` 포트 종료를 포함하도록 변경
- `docs/local-runbook.md` — 자동 실행/종료 스크립트가 pipeline API를 포함한다는 내용으로 갱신

**검증**

- `bash -n scripts/dev-up.sh`
- `bash -n scripts/dev-down.sh`
- `./scripts/dev-up.sh` 실행 시 orphan container 경고 없이 PostgreSQL/MinIO, pipeline API, 백엔드, 프론트엔드 기동 확인
- `./scripts/dev-down.sh`로 앱 프로세스와 PostgreSQL/MinIO/pipeline API 컨테이너 종료 확인

---

## 2026-06-16

### chore: Discord PR 알림 설정 문서화

**배경**

팀이 새 PR을 Discord에서 바로 확인할 수 있도록 GitHub Webhook 기반 알림 설정
절차를 문서화했습니다.

**추가된 것**

- `docs/development.md` — GitHub repository webhook과 Discord Webhook `/github` endpoint 설정 절차 문서화
- `docs/development.md` — GitHub Webhook 방식의 이벤트 및 대상 브랜치 필터 제한과 Webhook URL 보안 주의사항 문서화

**검증**

- GitHub와 Discord 공식 문서의 repository webhook 설정 절차 확인
- 애플리케이션 기능 코드 변경 없음

---

## 2026-06-13

### docs: 로컬 실행 가이드와 실행 스크립트 추가

**배경**

새 환경에서도 프론트엔드, 백엔드, 로컬 인프라를 같은 순서로 실행하고 확인할 수 있도록 요구사항과 절차를 한곳에 정리했습니다.

**추가된 것**

- `docs/local-runbook.md` — Docker, Java 21, Node.js 요구사항과 수동/자동 실행 순서 문서화
- `scripts/dev-up.sh` — `infra/.env` 준비, PostgreSQL/MinIO 기동, 백엔드/프론트엔드 실행, HTTP 응답 확인 자동화
- `scripts/dev-down.sh` — 프론트엔드/백엔드 프로세스와 로컬 인프라 컨테이너 전체 종료 자동화

**검증**

- `bash -n scripts/dev-up.sh`
- `bash -n scripts/dev-down.sh`
- `./scripts/dev-up.sh`로 PostgreSQL/MinIO, 백엔드, 프론트엔드 기동 및 HTTP 응답 확인
- `./scripts/dev-down.sh`로 앱 프로세스와 PostgreSQL/MinIO 컨테이너 종료 확인

---

## 2026-06-11

### docs: changelog 및 이슈 추적 규칙 추가

**배경**

커밋 시점마다 변경사항이 changelog에 누락되지 않도록 작업 지침을 보강하고, backend와 llmPipeline 통합 과정에서 남은 이슈를 별도 문서로 분리했습니다.

**추가된 것**

- `AGENTS.md` — 커밋 전 관련 changelog 갱신 규칙 추가
- `CLAUDE.md` — 커밋 전 관련 changelog 갱신 규칙 추가
- `docs/backlog/issue-2026-06-11.md` — backend / AI Pipeline 담당 영역별 미해결 이슈 정리

**검증**

- 문서 내용 확인
- `git status --short`로 변경 파일 확인

---

## 2026-06-09

### chore: 로컬 Docker 개발 환경 추가 (`8453cf1`)

**추가된 것**

- `infra/compose.infra.yml` — PostgreSQL 16 + MinIO 컨테이너 구성
- `infra/minio-init` — 버킷 자동 생성 컨테이너 (`fruition-storage`)
- `infra/.env` / `infra/.env.example` — 환경변수 단일 관리
- `backend/build.gradle` — `bootRun` 태스크에서 `infra/.env` 자동 로드

**로컬 서비스 구성**

| 서비스 | 포트 |
|---|---|
| PostgreSQL | `5432` |
| MinIO API | `9000` |
| MinIO 콘솔 | `9001` |

---

*커밋 단위 이력은 `git log` 로 확인하세요.*
