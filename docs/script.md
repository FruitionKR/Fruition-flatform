# 실행 스크립트·로컬 데모 절차

프로젝트 스크립트의 역할, 로컬 스택 구동 순서와 데모 시나리오를 정리한다. 상세 문제 해결은 원문을 참조한다.

> 원문: docs/backlog/local-runbook.md

모든 통합 명령은 `platform/`을 현재 디렉터리로 실행한다. `../frontend/`, `../Access/`, `../Document/`, `../AI/` checkout은 platform과 같은 상위 디렉터리에 둔다. 서비스 단독 실행법은 각 서비스의 `docs/script.md`가 소유한다.

## 1. 사전 조건

필요 도구.

| 도구 | 버전 | 확인 |
|---|---|---|
| Docker + Compose | 최신 | `docker compose version` |
| Java JDK | 21 | `java -version` |
| Node.js / npm | 20+ / 10+ | `node -v`, `npm -v` |
| Python | 3.10+ | `python3 --version` |
| curl | 기본 | `curl --version` |

로컬 인프라와 backend 테스트는 Quay의 공식 MinIO 서버 `RELEASE.2025-09-07T16-13-09Z`를 사용한다.
로컬 버킷 초기화용 `mc`도 `RELEASE.2025-08-13T08-35-41Z`로 고정한다.

환경변수는 `infra/.env`에서 관리. 없으면 예시에서 복사.

구동·재검증 명령에서 `infra/.env`를 shell source하지 않는다. `scripts/*.sh`의
`--env-file` 경로와 Gradle `bootRun`의 dotenv 경로를 사용한다.

```sh
cp infra/.env.example infra/.env
```

필수 키 이름(값은 각자 채움, 시크릿 커밋 금지).

- 공통: `JWT_SECRET`
- AI 기능 사용 시: ai-svc secret env `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` 중 사용할 provider의 키
- 소셜 로그인 사용 시(선택): `GOOGLE_CLIENT_ID/SECRET`, `NAVER_CLIENT_ID/SECRET`, `KAKAO_CLIENT_ID/SECRET`
- 이메일 로그인 데모용 고정 인증 코드: `AUTH_EMAIL_DEV_FIXED_CODE`

Java 21이 기본이 아니면 경로 지정.

```sh
export JAVA_HOME=/path/to/jdk-21
export JAVA_HOME_21="$JAVA_HOME"
```

`JAVA_HOME_21`은 프로젝트 구동 스크립트가 사용하고, `JAVA_HOME`은 직접 실행한 Gradle wrapper가 사용한다.

pipeline 테스트를 로컬에서 처음 실행할 때만 가상환경을 만들고 requirements를 설치합니다.

```sh
python3 -m venv ../AI/pipeline/.venv
../AI/pipeline/.venv/bin/python -m pip install -r ../AI/pipeline/requirements-dev.txt
cd ../AI/pipeline
.venv/bin/python -m pytest -q --ignore=tests/modules/document_restoration
```

이미 `../AI/pipeline/.venv`가 있고 requirements가 바뀌지 않았다면 기존 interpreter를
그대로 사용한다. 재검증마다 가상환경을 다시 만들거나 의존성을 다시 설치하지 않는다.

Agent turn router의 의미 분류는 승인된 seed 사례로 실제 provider를 평가한다. 결과는
`route_correct`, `agent_turn_failed`, 비편집 요청을 편집으로 분류한
`mutation_false_positives`를 분리해 출력한다.
`evals/agent_turn_router.jsonl`의 `expected`는 기본 route이고, 동일한
`document_operation`·`persist` 경계 안에서만 `acceptable` 배열로 복수 route를 허용할 수 있다.

```sh
cd ../AI/pipeline
OPENAI_API_KEY=... .venv/bin/python evaluate_agent_turn_router.py \
  --provider openai \
  --model gpt-5-nano
```

실제 Agent turn은 `ai_db.agent_runs` 행에 live로 적재된다. 성공 route는 `result->'route'`,
실패 코드는 `error_code`, route 계약 실패의 안전한 교정 사유는
`result->'contract_failures'`로 조회한다. core DB의 `agent_route_outcomes` view는 같은 run의
적용 projection과 기존 채팅을 연결해 편집 적용을 `accepted`, 실행 실패를
`technical_failure`, 그 밖의 결과를 `unlabeled`로 즉시 노출한다. 취소·재시도를 route 실패로
추정하거나 새 원문 대화와 provider 예외 메시지를 별도로 복제하지 않는다.

```sql
SELECT outcome_label, route ->> 'action' AS action, count(*)
FROM agent_route_outcomes
WHERE observed_at >= date_trunc('month', now()) - interval '1 month'
GROUP BY outcome_label, route ->> 'action'
ORDER BY outcome_label, action;
```

`document_restoration` 테스트까지 실행하려면 추가로 `requirements-document-restoration.txt`를 설치합니다.

## 2. 실행 스크립트

일반적인 로컬 개발은 루트 디렉터리에서 `dev-up.sh`와 `dev-down.sh`를 사용한다.

| 스크립트 | 역할 | 유지되는 항목 |
|---|---|---|
| `scripts/bootstrap.sh` | 필수 도구와 프론트엔드 의존성을 준비한다. `dev-up.sh`가 자동 호출한다. | 해당 없음 |
| `scripts/dev-up.sh` | 공용 인프라, PDF 변환기, 호스트 백엔드, AI API·워커, 프론트엔드를 순서대로 시작한다. | 실행 중인 supervisor가 전체 호스트 프로세스를 관리한다. |
| `scripts/dev-down.sh` | 이 프로젝트가 등록한 supervisor와 Compose 컨테이너를 종료한다. | 기본값은 로컬 볼륨을 유지한다. |
| `scripts/front-up.sh` / `front-down.sh` | 프론트엔드만 시작하거나 종료한다. | 백엔드와 Compose 서비스는 유지한다. |
| `scripts/back-up.sh` / `back-down.sh` | 공용 인프라와 호스트 백엔드를 시작하거나 백엔드만 종료한다. | 종료 후 공용 인프라와 볼륨은 유지한다. |
| `scripts/back-test.sh` | Java 21을 찾아 백엔드 Gradle 테스트를 실행한다. 인자가 없으면 CI와 같은 세 모듈 테스트를 실행한다. | 서비스를 시작하거나 종료하지 않는다. |
| `../Document/scripts/sql/preview-duplicate-document-names.sql` | `psql -Xq -f`로 실행해 V48 적용 전 중복 문서 이름 변경안을 CSV로 출력한다. 먼저 업로드된 문서를 유지하고 기존 이름과 충돌하지 않는 번호를 붙인다. | 실제 문서 행은 변경하지 않으며 임시 테이블도 롤백한다. |
| `scripts/ai-up.sh` / `ai-down.sh` | 백엔드 기동 후 AI image 하나로 Pipeline API와 워커 전체를 시작하거나 종료한다. | 종료 후 공용 인프라와 볼륨은 유지한다. |
| `scripts/ai-e2e.sh` | 배포용 Compose 조합을 빌드하고 converter·ingest·query·agent·lint를 Gemini로 실제 실행한다. | 전체 컨테이너와 DB 볼륨을 유지해 결과를 재확인할 수 있다. |

전체 로컬 환경을 시작한다.

```sh
./scripts/dev-up.sh
```

`dev-up.sh`는 현재 터미널에서 계속 실행된다. 다른 터미널에서 다음 명령으로 종료한다.

```sh
./scripts/dev-down.sh
```

PDF 변환기 `markitdown`(:8010)은 `dev-up.sh`가 함께 시작하고 `dev-down.sh`가 함께 종료한다. 단독으로 다룰 때는 다음 명령을 쓴다. `--env-file`을 생략하면 LLM API key 없이 기동되어 `dev-up.sh`와 동작이 달라진다.

```sh
docker compose --env-file infra/.env -f infra/compose.converter.yml up -d
```

지표 확인용 Prometheus·Grafana도 선택 스택이다. 자세한 절차는 3-6을 본다.

```sh
docker compose -f infra/compose.monitoring.yml up -d
```

up 스크립트는 `.runtime/`에 supervisor PID를 등록한다. down 스크립트는 등록된 supervisor만 종료하며, 같은 포트를 사용하는 다른 프로젝트 프로세스는 종료하지 않는다. 이미 다른 프로세스가 필요한 포트를 사용 중이면 up 스크립트는 즉시 실패한다.

## 3. 상세 구동 순서

### 3-1. 인프라 (PostgreSQL·Kafka·Redis·MinIO)

```sh
docker compose --env-file infra/.env -f infra/compose.infra.yml up -d
docker compose -f infra/compose.infra.yml ps
```

`fruition-postgresql-dev`가 `healthy`가 되면 다음 단계 진행.

배포 이미지 단위 검증은 공용 인프라·AI·변환기·컨테이너 통합 override를 함께 구성한다.

```sh
docker compose --env-file infra/.env \
  -f infra/compose.infra.yml -f infra/compose.ai.yml \
  -f infra/compose.converter.yml -f infra/compose.containerized.yml \
  up -d --build
```

### 3-2. 백엔드 (document-svc :8080 → access-svc :8081)

백엔드 테스트는 Java 설치 경로를 직접 추측하지 말고 루트에서 스크립트로 실행한다.

```sh
./scripts/back-test.sh
./scripts/back-test.sh Document test --tests 'fruition.core.aihistory.*'
```

스크립트 사용(인프라 기동 포함, Flyway 소유자인 document-svc를 먼저 시작).

```sh
./scripts/back-up.sh
```

수동 실행 시(터미널 2개).

```sh
SERVICE_ENV_FILE="$PWD/infra/.env" ../Document/gradlew -p ../Document bootRun  # :8080
# 별도 터미널에서 실행
SERVICE_ENV_FILE="$PWD/infra/.env" ../Access/gradlew -p ../Access bootRun      # :8081
```

확인.

actuator는 업무 포트와 분리된 관리 포트에 있다(document 8082, access 8083).
ALB Ingress가 업무 포트만 라우팅하므로 `/actuator/prometheus`가 외부에 노출되지 않는다.

```sh
curl http://localhost:8082/actuator/health   # document-svc {"status":"UP"}
curl http://localhost:8083/actuator/health   # access-svc  {"status":"UP"}
curl http://localhost:8082/actuator/prometheus   # Prometheus 스크레이프용 지표
```

### 3-3. ai-svc (converter → pipeline-api·워커)

PDF→Markdown 변환기(markitdown, :8010).

```sh
docker compose -f infra/compose.converter.yml up -d
curl http://localhost:8010/health
```

실제 PDF를 Gemini로 변환하는 Docker E2E는 공용 스크립트로 실행한다. 스크립트는
`infra/.env`의 `GEMINI_API_KEY`를 사용해 이미지를 다시 빌드하고, health 확인 후
Markdown과 복원 summary를 저장소의 `.tmp/converter-e2e/`에 저장한다. 출력 경로를
명시하면 그 위치를 사용한다. 별도 worktree의 env 파일을
사용하려면 `CONVERTER_ENV_FILE`을 지정한다.

```sh
./scripts/converter-e2e.sh /path/to/input.pdf [/path/to/output.md]
```

converter뿐 아니라 컨테이너형 백엔드와 모든 AI worker를 함께 검증하려면 통합 E2E를 실행한다.
이 명령은 로컬 고정 이메일 인증번호로 격리된 계정·워크스페이스를 생성하고 실제
스마트팜 문서 10개를 누적 ingest한 뒤 query·agent·lint 완료까지 기다리고 `과습 관리`
promotion 결과도 Markdown으로 기록한다. 결과는 `.tmp/ai-e2e/<실행 ID>/`에 남으며
기존 개발 DB를 마이그레이션하거나 지우지 않도록 `fruition-ai-e2e` Compose project의
별도 볼륨을 쓴다. 고정 컨테이너 이름 충돌을 막기 위해 기존 개발 컨테이너는 내리지만
그 볼륨은 보존하며, E2E 컨테이너와 볼륨도 후속 점검을 위해 유지한다. 성공 기준은
lint 결과에 materialized 또는 merged promotion이 있고, 해당 산출물 `promotion.md`에
`# 과습 관리` 제목이 포함되는 것이다.

```sh
./scripts/ai-e2e.sh /path/to/input.pdf
```

저장소에 포함된 합성 PDF와 스마트팜 Markdown 10개로 실행하려면 다음 명령을 사용한다.
스크립트는 PDF 경로는 인자로 받고, Markdown 입력은
`../AI/pipeline/examples/ai-e2e/*.md`에서 읽는다. 각 문서의 운영 기록에 언급된
`과습 관리`가 의미 cluster에 누적되고 실제 concept로 승격되어야 성공한다.

```sh
./scripts/ai-e2e.sh ../AI/pipeline/examples/ai-e2e/synthetic-smart-farm.pdf
```

다른 env 또는 결과 디렉터리를 쓰려면 `AI_E2E_ENV_FILE`, `AI_E2E_OUTPUT_DIR`을 지정한다.

검증 후 converter를 종료한다.

```sh
docker compose --env-file infra/.env -f infra/compose.converter.yml down
```

pipeline-api(:8000)와 워커(ingest/query/agent/maintenance task worker, edit-event-consumer). 백엔드 기동 후 실행(스키마 순서 보장).

```sh
docker compose --env-file infra/.env \
  -f infra/compose.infra.yml -f infra/compose.ai.yml \
  up -d pipeline-api ingest-worker query-task-worker agent-task-worker \
  maintenance-task-worker edit-event-consumer pipeline-agent-worker
curl http://localhost:8000/health
```

`./scripts/ai-up.sh`는 pipeline image를 한 번 빌드한 뒤 pipeline-api와 전체 워커를 같은 image로 시작한다.
기존 image를 재사용할 때는 위 compose 명령을 `--build` 없이 실행한다.

### 안정적 통합 재검증 규칙

- 백엔드는 `./scripts/back-up.sh` 또는 위의 Gradle 명령으로 전용 장기 runner 터미널에서 실행한다. 일회성 테스트 agent가 runner를 소유하거나 종료하지 않는다.
- 결과 topic은 표준 이름을 사용하고 publisher와 consumer의 topic 설정이 일치하는지 먼저 확인한다.
- 격리된 통합 재검증 wave마다 아직 존재하지 않는 consumer group을 하나만 만들고 `latest`를 한 번 적용한다. wave 안에서는 같은 group을 모든 lane이 재사용하며 lane마다 group을 새로 만들거나 offset을 초기화하지 않는다.
- 재검증 전후에 HEAD, health, 프로세스 cwd, Tool flags, 재시작 횟수, partition별 log-end와 lag를 기록하고 고정한다. 각 lane 전후에는 동일한 고정 preflight를 실행하고, 기준선과 달라진 값은 테스트 결과와 별도의 drift로 분류한다.
- 변경되지 않은 서비스·의존성은 재시작·재빌드·재설치하지 않는다. backend-only 변경이면 기존 AI image를 유지한다. worker를 내릴 때도 runtime 자체를 중지하지 않는다.
- AI image를 빌드하기 전 `docker system df`, `uname -m`, `docker info --format '{{.Architecture}}'`로 저장공간과 host/Docker 아키텍처를 확인한다. 공간 부족이나 host/image 아키텍처 불일치는 코드 결함과 분리하고, 대상이 확인된 미사용 build cache·image만 정리한다. 실행 중인 container와 공용 volume은 정리하지 않는다.
- 로컬 CPU 재검증에 불필요한 GPU/CUDA 산출물이 설치되기 시작하면 반복 설치하지 말고 requirements, base image, host/image 아키텍처가 맞는지 먼저 확인한다.
- 재검증 중 Kafka, DB, volume을 reset하지 않는다.
- 재검증 요청 중 상태를 바꾸는 public API에는 첫 요청부터 255자 이하의 짧은 `Idempotency-Key`를 넣는다.
- 여러 단계의 재검증 harness는 `#!/usr/bin/env bash`를 선언하고 Bash로 실행한다. zsh 일회성 명령에서는 읽기 전용 변수 `status`를 쓰지 않고 `http_status` 또는 `state`를 사용한다.
- curl 증거를 `{status, body}`로 감쌌다면 HTTP 코드는 `.status`, 비동기 업무 상태는 `.body.status`로 판정한다. operation log 목록은 응답의 `.logs` 배열을 읽는다.
- Bash에서 JSON 기본값을 `${arg:-{}}`처럼 중괄호가 겹치는 매개변수 확장으로 만들지 않는다. 빈 값은 별도 문장으로 `'{}'`를 대입하고, 요청 전 `jq -e .`로 payload를 검증한다.
- 이전 단계가 성공한 fixture, 응답, 비동기 checkpoint는 그대로 이어서 사용하고 lane의 모든 검증이 끝난 뒤 한 번만 정리한다. harness 오류만 고친 경우 ingest·서비스 기동·의존성 설치부터 다시 시작하지 않는다.
- fixture 정리는 public API로 수행한다. 문서 삭제 요청에는 직전 조회에서 확인한 현재 `base_version`을 넣고, 이미 정리된 fixture 때문에 앞 단계 전체를 다시 실행하지 않는다.

통합 재검증용 backend를 처음 띄우는 runner 터미널에서 group을 한 번만 지정한다. 이미
backend가 실행 중이면 `back-up.sh`가 그대로 반환하므로, 실행 중간에 group을 바꾸지 않는다.

```sh
export AI_TASK_RESULT_CONSUMER_GROUP="document-svc-ai-task-result-$(git rev-parse --short HEAD)-$(date +%Y%m%d%H%M%S)"
./scripts/back-up.sh
```

AI image를 처음 만들거나 AI 코드·의존성이 바뀐 경우에만 위 compose 명령의 `up -d`에
`--build`를 추가한다.
기존 image로 재검증할 때는 `--build` 없이 `up -d`를 사용한다.

### 3-3-1. 기존 AI 데이터 maintenance cutover

신규 빈 환경에는 필요 없다. 기존 `core_db`의 Wiki·Agent·Skill·checkpoint를 옮길 때는 먼저 외부 요청을 차단하고 `pipeline-api`를 내려 lint/restore/reingest/Agent mutation을 막는다. Wiki와 Agent 실행이 모두 terminal 상태가 된 뒤 관련 worker를 내린다.

```sh
docker compose --env-file infra/.env \
  -f infra/compose.infra.yml -f infra/compose.ai.yml \
  stop pipeline-api agent-task-worker pipeline-agent-worker
docker compose --env-file infra/.env -f infra/compose.infra.yml \
  exec -T postgresql sh -c \
  'PGPASSWORD="$CORE_DB_MIGRATION_PASSWORD" exec psql -U "$CORE_DB_MIGRATION_USER" -d "$CORE_DB_NAME" -At' <<'SQL'
select count(*) from pipeline_runs where status not in ('succeeded','failed','notify_pending');
select count(*) from agent_runs where status not in ('completed','partial_failed','failed','conflicted','rejected','cancelled');
SQL
docker compose --env-file infra/.env \
  -f infra/compose.infra.yml -f infra/compose.ai.yml \
  stop ingest-worker
```

두 결과가 0인지 확인하고 core/ai DB snapshot 식별자를 기록한다. 먼저 두 runtime role의 core Wiki·Agent·Skill·checkpoint DML을 차단한다. `copy`는 active run 0건과 이 권한 차단 상태를 다시 검증한 뒤, 하나의 `REPEATABLE READ READ ONLY` source transaction에서 ID 보존 stream copy와 row count·PK·canonical content hash·고아 참조 검증을 수행한다.

```sh
../AI/pipeline/.venv/bin/python ../AI/pipeline/wiki_db_cutover.py lock-core-writes
../AI/pipeline/.venv/bin/python ../AI/pipeline/wiki_db_cutover.py copy \
  --writes-stopped \
  --core-snapshot-id '<core snapshot ID>' \
  --ai-snapshot-id '<ai snapshot ID>'
```

`copy` 또는 row count·PK·hash·고아 참조 검증이 실패하면 연결을 전환하지 말고 즉시 write fence를 복구한다. 실패한 target transaction은 rollback되므로 ai_db의 부분 복사본을 덮어쓰지 않는다. rollback 명령은 `core_runtime`과 `ai_runtime`의 source table·sequence 권한을 복구하고 두 role의 실제 write를 검증한다.

```sh
../AI/pipeline/.venv/bin/python ../AI/pipeline/wiki_db_cutover.py rollback-core-permissions
```

외부 요청 차단은 유지한 채 새 이미지의 `pipeline-api`만 올린다.

```sh
docker compose --env-file infra/.env \
  -f infra/compose.infra.yml -f infra/compose.ai.yml \
  up -d --build pipeline-api
```

내부 pipeline API로 ingest/query/lint/restore/agent smoke test를 모두 실행하고, 다섯 기능이 성공한 경우에만 `ai_runtime`의 core 권한을 완전히 회수하고 core source table을 read-only로 유지한 뒤 worker를 재개한다.

```sh
../AI/pipeline/.venv/bin/python ../AI/pipeline/wiki_db_cutover.py \
  finalize-core-permissions --smoke-tested ingest query lint restore agent
docker compose --env-file infra/.env \
  -f infra/compose.infra.yml -f infra/compose.ai.yml \
  start ingest-worker
```

smoke test가 실패하면 worker를 재개하지 않는다. 구버전 이미지와 core DB 연결로 되돌린 뒤 다음 명령으로 core source write 권한을 복구한다.

```sh
../AI/pipeline/.venv/bin/python ../AI/pipeline/wiki_db_cutover.py rollback-core-permissions
```

문서 편집 저장소는 V39가 비어 있는 `document_edit_states`와 `document_content_versions`에 편집 revision을 초기화하는 fresh PostgreSQL cutover다. 기존 Mongo 편집 데이터와 두 PostgreSQL table의 폐기는 대상별 승인 후 수행하며, 기존 편집 상태·write receipt·pending edit event를 import하거나 dual-write하지 않는다. 초기화된 편집 상태의 본문·revision·receipt·content version·asset/reference·적용 감사·outbox를 하나의 core DB transaction으로 기록한다. 결정 근거: [adr/0016](https://github.com/FruitionKR/Fruition-document/blob/main/docs/adr/0016-consolidate-document-body-into-postgres.md).

### 3-4. 프론트엔드 (:3000)

```sh
./scripts/front-up.sh
```

또는 수동 실행.

```sh
cd ../frontend
npm install
npm run dev
```

확인: `curl -I http://localhost:3000` 후 브라우저에서 `http://localhost:3000` 접속.

### 3-5. 로그 확인

`dev-up.sh`는 로그를 `logs/`에 남긴다. 컨테이너 로그는 `dev-down.sh`로 컨테이너를 지우면 함께 사라지므로, 재기동 뒤에도 이전 에러를 보려면 이 파일을 본다. `logs/`는 gitignore 대상이다.

```
logs/workers.log        워커 6개 + pipeline-api (서비스명 접두어로 구분)
logs/document-svc.log   backend
logs/access-svc.log     backend
logs/frontend.log       frontend
```

```sh
tail -f logs/*.log                      # 흐름 실시간 확인
grep -iE "error|exception" logs/*.log   # 에러만 확인
```

워커 로그 수집만 따로 제어하려면 `./scripts/logs-up.sh [start|stop|status]`를 쓴다. 수집을 시작할 때 `workers.log`가 100MB를 넘었으면 `workers.log.1`로 밀고 새로 쌓는다(수집 중에는 회전하지 않는다).

### 3-6. 모니터링 (선택)

백엔드 지표를 그래프로 보는 스택이다. 업무 기능과 무관하므로 `dev-up.sh`는 띄우지 않는다.

```sh
docker compose -f infra/compose.monitoring.yml up -d
```

| 대상 | 주소 | 비고 |
|---|---|---|
| Prometheus | http://localhost:9090 | 15초마다 백엔드 관리 포트와 kafka-exporter를 긁는다 |
| Grafana | http://localhost:3001 | 초기 계정 `admin` / `admin` |
| kafka-exporter | (내부 전용 :9308) | 브로커에 직접 물어 consumer group별 lag을 낸다 |
| pipeline-api | http://localhost:8000/metrics | FastAPI 요청 지표. Prometheus는 infra 네트워크에서 컨테이너 이름으로 긁는다 |

kafka-exporter는 `compose.infra.yml`이 만드는 네트워크(`fruition-mvp-dev_default`)에 붙으므로 **인프라가 먼저 떠 있어야 한다**. Kafka의 EXTERNAL 리스너는 `localhost:9092`로 광고돼 컨테이너에서 쓸 수 없어 INTERNAL(`kafka:19092`)로 접속한다.

동작 원리는 세 단계다. 백엔드가 `/actuator/prometheus`에 지표를 텍스트로 내걸고, Prometheus가 주기적으로 긁어 시계열로 쌓고, Grafana가 그것을 조회해 그린다. 세 프로세스는 HTTP로만 연결돼 있어 서로를 모른다.

확인 순서.

1. http://localhost:9090/targets — `document-svc`와 `access-svc`가 모두 UP이어야 한다. DOWN이면 백엔드가 떠 있는지, 관리 포트(8082·8083)가 열렸는지 본다.
2. Grafana 접속 → Dashboards → **Fruition 운영**. 데이터소스와 대시보드 모두 기동 시 자동 등록되므로 import 절차가 없다.

#### 무엇을 보는가

`Fruition 운영`은 장애 조사 1차 화면이다. Google SRE의 Four Golden Signals를 인과 순서대로 배치했으므로
왼쪽 위에서 시작해 시계 방향으로 읽는다.

| 순서 | 패널 | 정상 | 이상 신호 |
|---|---|---|---|
| ① | **Traffic** | 평소 수준 | 다른 세 신호를 해석하는 기준선이다. 이것 없이는 지연·에러가 유입 증가 탓인지 코드 탓인지 구분할 수 없다 |
| ② | **Saturation** | lag 0(또는 올랐다 복귀), DB 사용률 0.5 이하 | lag이 안 내려오면 워커 정지·반복 실패. 점선은 KEDA `lagThreshold`(5). DB 사용률이 1.0에 붙으면 풀(기본 10개)이 마른 것으로, API 지연의 원인이 DB가 아니라 풀인 경우다 |
| ③ | **Latency** | 배포 전과 비슷 | p95·p99가 평소의 3~5배. 트래픽이 없으면 선이 끊기는데 정상이다(rate 분모가 0) |
| ④ | **Errors** | 0 | 건수가 아니라 **비율**이다. 4xx는 뺀다 — 미로그인 401은 정상 동작이라 신호가 되지 않는다 |

네 신호 아래에는 드릴다운 패널이 하나 더 있다. **partition별 lag**은 ②에서 특정 consumer group이
밀릴 때 어느 partition인지 좁힌다. 메시지 key가 `document_id`라 partition은 문서 단위로 묶이므로,
한 partition만 쌓여 있으면 그 partition에 걸린 특정 문서가 반복 실패하는 것이고, 전 partition이
고르게 쌓이면 처리량 부족이다. 상단 `Consumer group` 드롭다운으로 대상을 바꾼다.

그래프의 세로선은 **프로세스 재시작(배포) 시각**이다. 배포 전후로 지표가 어떻게 달라졌는지 눈으로
맞출 수 있다. `process_start_time_seconds`로 감지하며, 재시작 후 5분 이내 구간을 표시하므로
실제 시각과 최대 5분 차이가 날 수 있다.

④에는 한계가 있다. 여기 잡히는 것은 프로토콜 수준의 **명시적 실패**뿐이다. AI 처리는 202로 즉시 응답한 뒤
비동기로 실패할 수 있어, 이 그래프가 평평해도 사용자는 결과를 못 받을 수 있다. 그런 **묵시적 실패**는 현재
ERROR 로그로만 간접 관측된다. 처리 실패율을 직접 세려면 워커에 도메인 지표를 심어야 한다.

여기서 이상이 잡히면 JVM 내부를 본다. Grafana → Dashboards → New → Import → ID `4701`(JVM Micrometer) → 데이터소스 `Prometheus`. 힙·GC·스레드를 `application` 단위로 보여준다. 다만 이 대시보드의 Heap used(%)는 로컬에서 의미가 없다 — `-Xmx`를 주지 않아 max heap이 12GB로 잡히므로 사용률이 항상 1%대다. 비율 대신 `JVM Heap` 패널의 톱니 모양을 본다. `Utilisation` 패널도 비어 있는데, Tomcat 스레드 지표에 `server.tomcat.mbeanregistry.enabled=true`가 필요하기 때문이다. 지금 규모에서는 DB 풀이 훨씬 먼저 막히므로 켜지 않았다.

`prometheus.yml`을 고쳤다면 Prometheus를 재시작해야 반영된다(`docker restart fruition-prometheus`). 대시보드 JSON은 30초마다 자동으로 다시 읽으므로 재시작이 필요 없다.

단, `git rebase`나 브랜치 전환처럼 디렉터리를 지웠다 다시 만드는 작업 뒤에는 bind mount가 옛 inode를
가리켜 컨테이너에서 파일이 보이지 않는다. 대시보드 수정이 반영되지 않으면 이것부터 의심한다.

```sh
docker exec fruition-grafana ls /var/lib/grafana/dashboards/   # 비어 있으면 마운트가 끊긴 것
docker compose -f infra/compose.monitoring.yml up -d --force-recreate grafana
```

데이터소스·대시보드는 기동 시 자동 등록된다(`infra/monitoring/grafana/provisioning/`, `infra/monitoring/grafana/dashboards/`). 대시보드는 파일이 단일 소스라 UI에서 고쳐도 저장되지 않는다 — JSON을 고쳐 커밋한다. 스크레이프 대상은 `infra/monitoring/prometheus.yml`에 있고, 호스트에서 bootRun으로 도는 백엔드를 가리킨다. `compose.containerized.yml`로 백엔드를 컨테이너로 띄웠다면 대상 주소를 바꿔야 한다.

종료는 다음과 같다. 볼륨을 지우지 않으면 수집한 지표와 대시보드가 남는다.

```sh
docker compose -f infra/compose.monitoring.yml down
```

## 4. 데모 시나리오

1. 로그인 — `http://localhost:3000` 접속, 이메일 가입/로그인. 인증 코드는 `infra/.env`의 `AUTH_EMAIL_DEV_FIXED_CODE` 값 입력. (OAuth 키 설정 시 소셜 로그인도 가능)
2. 워크스페이스 — 워크스페이스 생성 후 진입.
3. 문서 업로드 — PDF 업로드 → converter가 Markdown 변환 → pipeline 워커가 처리. 상태가 `processing`에서 완료로 바뀌는지 확인. 멈춰 있으면 `:8000/health`와 선택 provider secret key를 확인.
4. 문서 편집 — 문서를 열어 내용 수정. 편집 이벤트가 Kafka(`document.edit.event`)로 흘러 파생 상태가 갱신됨.
5. AI 질의 — 비동기 Query run/SSE가 완료되고 업로드 문서 기반 응답·원문 링크가 저장되는지 확인.
   Query 질문을 전송한 뒤 입력창을 클릭하고 `Esc`를 누르면 해당 질의의 취소·변경 복구를 요청한다.
   작업 ID를 받기 전에 누른 경우도 접수 직후 취소하며, `cancelled` 확인 후 진행 중 문답을 제거한다.
   입력창 밖의 `Esc`는 질의를 취소하지 않는다. 위키 편입·Lint는 이 단축키 대상이 아니다.
   복구 실패·상태 조회 오류가 표시되면 입력창에서 `Esc`로 같은 작업의 취소를 재시도한다.
6. Agent/Lint/Restore — 요청이 즉시 202를 반환하고 각 run 완료 후에만 결과가 반영되는지 확인.
7. 병렬 ingest — 같은 workspace의 서로 다른 문서를 동시에 올려 병렬 처리되고 동일 slug Concept가 하나만 남는지 확인.

## 5. 종료·초기화

앱 프로세스와 인프라·pipeline 컨테이너 일괄 종료.

```sh
./scripts/dev-down.sh
```

converter 종료.

```sh
docker compose -f infra/compose.converter.yml down
```

모니터링 종료.

```sh
docker compose -f infra/compose.monitoring.yml down
```

데이터까지 초기화(DB·MinIO·pipeline 산출물과 이 project의 orphan 볼륨 삭제, 재현 환경 초기화 시에만).

```sh
./scripts/dev-down.sh --volumes
```

개별 종료 스크립트: `scripts/front-down.sh`, `scripts/back-down.sh`, `scripts/ai-down.sh`.
호스트 앱 종료 스크립트는 `.runtime/`에 등록된 supervisor만 종료한다. 다른 프로젝트가 같은 포트를 사용 중이면 종료하지 않는다.
`scripts/ai-down.sh`는 pipeline-api와 전체 워커를 함께 종료한다.

### MFA 컨테이너 설정

`infra/.env`의 `MFA_ENCRYPTION_KEY`에 Base64로 인코딩한 32바이트 키를 설정한다. `compose.containerized.yml`은 이 값을 access-svc 환경에 전달하며, 누락되면 Compose 단계에서 중단한다. 기존 MFA secret 복호화에 필요한 키이므로 재시작 때 같은 값을 유지한다.


## AI 작업 취소 E2E

현재 코드로 구동한 로컬 access-svc(8081), document-svc(8080), pipeline과 Kafka worker, PostgreSQL(5432), Redis, MinIO가 필요합니다.
`AGENT_SKILLS_ENABLED=true`, `SKILL_API_ENABLED=true`와 유효한 Gemini 모델 설정을 사용합니다.
테스트는 `infra/.env`의 로컬 DB 접속 설정을 읽고 새 테스트 계정·workspace에 폴더 2개와 문서 6개를 만듭니다.
로컬 이메일 인증 코드 `9700`을 사용하는 개발 환경에서만 실행합니다. 실제 모델 비용이 발생합니다.

```bash
LIVE_TASK_ENV_FILE="$PWD/infra/.env" RUN_LIVE_TASK_E2E=1 ../AI/pipeline/.venv/bin/python -m pytest \
  ../AI/pipeline/tests/test_live_task_cancellation_e2e.py -q -s
```

입력·계획·실행·복구 결과는 `/tmp/ai-cancel-e2e-report.json`에 저장합니다.
`AI_CANCEL_E2E_REPORT`로 경로를 바꿀 수 있습니다. 테스트 workspace는 결과 확인을 위해 남깁니다.
기본 테스트 실행에서는 이 검증을 건너뜁니다. 검증 범위는 [AI 작업 취소 API](api/ai-task-cancellation.md#검증-범위)를 참고합니다.

## DB bootstrap 및 권한 검증

`infra/postgres/init-db-isolation.sh`는 `DB_ISOLATION_TARGET=all/access/core`로 생성 범위를
선택한다. `all`은 단일 PostgreSQL을 쓰는 로컬 기본값이다. AWS Access RDS에는 `access`,
Core RDS에는 `core`를 명시한다. `access`는 Access DB·두 role, `core`는 Core/AI DB·네 role만
생성한다. 선택하지 않은 서비스의 환경변수는 필요하지 않다.

- 각 선택 서비스: `{ACCESS,CORE,AI}_DB_NAME`, `*_DB_RUNTIME_USER`, `*_DB_RUNTIME_PASSWORD`,
  `*_DB_MIGRATION_USER`, `*_DB_MIGRATION_PASSWORD`를 제공한다. 이름 중복, 관리 DB 이름,
  관리자와 같은 role, 빈 값은 DB 변경 전에 거부한다.
- 관리자: `POSTGRES_ADMIN_USER`, `POSTGRES_ADMIN_PASSWORD`를 제공한다. PostgreSQL 컨테이너
  최초 초기화에서는 `POSTGRES_USER`, `POSTGRES_PASSWORD`를 사용한다. 비밀번호 대신
  libpq `PGPASSFILE`도 사용할 수 있다.
- 연결: libpq `PGHOST`, `PGPORT`, `PGSSLMODE`, `PGSSLROOTCERT`를 사용한다. RDS에서는
  endpoint와 RDS CA 인증서를 지정하고 `PGSSLMODE=verify-full`로 인증서를 검증한다.
  변수는 실행 환경/Secret에서 주입하며 실제 비밀번호를 명령이나 저장소에 기록하지 않는다.

```bash
# Access endpoint와 ACCESS_DB_* 입력을 주입한 환경
DB_ISOLATION_TARGET=access bash infra/postgres/init-db-isolation.sh
DB_ISOLATION_TARGET=access bash infra/postgres/validate-db-isolation.sh
# Core endpoint와 CORE_DB_*, AI_DB_* 입력을 주입한 환경
DB_ISOLATION_TARGET=core bash infra/postgres/init-db-isolation.sh
DB_ISOLATION_TARGET=core bash infra/postgres/validate-db-isolation.sh
# 기존 개발 DB 대신 임시 컨테이너만 사용하는 회귀 검증
bash infra/postgres/test-db-isolation.sh
```

init과 validate는 같은 디렉터리의 `db-isolation-config.bash`를 함께 배포해야 한다.
Compose mount와 Kubernetes `postgres-init` ConfigMap은 이 두 입력 파일을 포함한다.
PostgreSQL 16 이상에서 실행한다. 비superuser 관리자는 CREATEDB/CREATEROLE이 필요하며,
생성 role의 SET/INHERIT 권한을 받아 DB 소유권 작업을 수행한다. 초기화는 반복 실행할 수 있으며 선택 서비스 간 기존 직접 접근 권한도 회수한다. 기존 role에
membership이 있으면 상속 권한을 임의로 변경하지 않고 초기화 전에 실패한다.

검증기는 고유한 임시 테이블을 migration 계정으로 만들고 종료 시 삭제한다. runtime의
SELECT/INSERT/UPDATE/DELETE·sequence 사용, public CREATE 거부, 관리자 권한·membership
부재와 같은 인스턴스의 선택 DB 간 양방향 CONNECT/read/write 거부를 확인한다.
Access 단독 대상에서는 교차 DB 쌍이 없으므로 이 항목은 수행하지 않는다. 서로 다른 RDS의
네트워크/인증 경계는 이 스크립트가 검증하지 않으며 실제 AWS 배포 검증에서 별도로 확인한다.


## AWS 서비스 자격증명과 migration 실행 계약

`k8s/overlays/aws`의 ExternalSecret은 `fruition/app`을 통째로 복사하지 않고 서비스별 허용 키만 투영한다. runtime Secret은 `fruition-access`, `fruition-document`, `fruition-pipeline`, `fruition-converter`이며 migration 전용 Secret은 `fruition-access-migration`, `fruition-document-migration`, `fruition-ai-migration`이다. bootstrap 관리자 인증은 별도 실행 환경에서만 사용한다.

1. DB bootstrap 및 권한 검증을 마친다.
2. 플랫폼 관리자가 namespace·SecretStore·RBAC를 준비한 후 앱 ServiceAccount·ConfigMap·ExternalSecret을 적용하고 모든 ExternalSecret Ready를 확인한다. Access에는 `MFA_ENCRYPTION_KEY`, `SPRING_MAIL_HOST/PORT/USERNAME/PASSWORD`, `MAIL_FROM`이 필요하다. MFA 키는 Base64 32바이트이며 Terraform이 최초 생성한다. SMTP는 인증과 STARTTLS를 사용한다. `WORKSPACE_INVITATION_ACCEPT_URL`은 공개 앱의 `https://<app-domain>/invitations`이다. production 기동은 누락·placeholder·localhost 초대 주소·고정 이메일 인증 코드를 거부한다.
3. 동일 배포 SHA 이미지의 `access-migration`, `document-migration`, `ai-migration` Job을 실행한다. Job label은 `app.kubernetes.io/component=migration`, `backoffLimit=0`, deadline은 600초다. 이전 Job이 있으면 해당 Job만 삭제하고 새 SHA로 재생성한다. 세 Job 모두 Complete가 되기 전 runtime을 적용하지 않는다.
4. Java runtime은 production profile에서 Flyway를 끄고 Hibernate validate를 사용한다. AI runtime에는 `AI_DB_MIGRATION_URL`을 주입하지 않아 스키마 검증만 수행한다. migration 성공 뒤 전체 workload rollout과 smoke test를 수행한다. 렌더된 전체 YAML의 일괄 apply는 이 순서를 보장하지 않는다.

Job 내부 명령과 입력:

| Job | 명령 | 필수 환경 |
|---|---|---|
| Access | `java -jar app.jar --migrate-only` | `POSTGRES_HOST/PORT`, `ACCESS_DB_NAME`, `ACCESS_DB_MIGRATION_USER/PASSWORD` |
| Document | `java -jar app.jar --migrate-only` | `POSTGRES_HOST/PORT`, `CORE_DB_NAME`, `CORE_DB_MIGRATION_USER/PASSWORD` |
| AI | `python -m app.modules.wiki_ingestion.infrastructure.migrate_ai_schema` | `AI_DB_MIGRATION_URL` |

Java Job은 migration 이력이 없는 비어 있지 않은 DB를 자동 baseline하지 않는다. bootstrap으로 생성한 빈 DB 또는 기존 Flyway 이력이 정상인 소유 DB를 대상으로 한다. AI 명령은 Agent·Skill·checkpoint를 포함한 `db/ai_schema.sql`을 트랜잭션으로 적용한다.

Secrets Manager 값은 초기 생성 이후 Terraform `ignore_changes`로 보존된다. 기존 환경에 새 MFA/SMTP 키가 없으면 운영자가 Secret 원본에 추가해야 하며 Terraform 재실행만으로 채워졌다고 가정하지 않는다. MFA 키를 임의로 교체하면 기존 TOTP secret 복호화가 불가능하므로 기존 키를 유지·보관한다. Secret 값 변경 후 ExternalSecret 동기화를 확인하고 해당 workload만 재시작한다. 실제 회전·복구 검증은 AWS에서 별도로 수행한다.

로컬 Compose/kind는 자기 서비스의 자동 migration을 유지한다. kind는 `base/secret.yaml`과 별도로 MFA 키 Secret을 생성해야 Access를 시작할 수 있다. 새 로컬 환경에서만 키를 생성하고 기존 환경에서는 보관한 키 파일을 사용한다. 저장소 밖 권한 600 파일에 줄바꿈 없는 Base64 32바이트를 보관한 뒤 다음처럼 적용한다(키 값을 화면에 출력하지 않는다).

```bash
kubectl -n fruition create secret generic fruition-mfa --from-file=MFA_ENCRYPTION_KEY=/secure/path/mfa-key-base64
```

로컬 검증은 실제 AWS 배포 검증을 대신하지 않는다:

```bash
../AI/pipeline/.venv/bin/python scripts/tests/test_aws_credentials.py
# 먼저 Java 21로 두 서비스 bootJar를 빌드한다. 필요한 경우 JAVA_HOME_21과 PIPELINE_PYTHON 지정.
bash scripts/tests/test-service-migrations.sh
```

두 번째 검증은 매번 독립 임시 PostgreSQL·Redis 컨테이너를 생성·정리하고, Kafka listener 자동 시작을 끄고 Kafka·S3·내부 API 주소를 연결 불가 주소로 지정한다. 실제 bootJar/Python migration을 두 번 실행하고 migration 비밀번호 없는 Java runtime 기동 및 AI 필수 테이블 검증, DML 허용·DDL/교차 DB 접근 거부를 확인한다. 기존 개발 DB를 사용하지 않는다.


## AWS 순차 배포와 동일 스키마 SHA 복구


실행 진입점은 scripts/aws_deploy.py이며 Python 3.12 이상, PyYAML 6.0.2, kubectl, curl이 필요하다. render는 Kubernetes API에 접속하지 않고 임시 사본에만 값을 치환한다. 원본 overlay는 변경하지 않는다. deploy와 rollback은 실제 cluster를 변경하므로 대상 kubeconfig와 AWS 환경 준비 후에만 실행한다.

비밀 아닌 JSON 입력 파일에는 아래 14개 키만 넣는다. scheme·port·path 없는 호스트명, 12자리 계정, 서울 region/account가 일치하는 ACM ARN, 40자리 소문자 image SHA를 검증한다. 빈 값과 placeholder는 첫 cluster 변경 전에 실패한다.

| JSON 키 | 출처 |
|---|---|
| account_id | 배포 AWS 계정 ID |
| access_rds_endpoint, core_rds_endpoint, redis_endpoint, s3_bucket | 같은 이름의 Terraform output |
| app_domain | Vercel 공개 앱 호스트 |
| domain | api. 및 access.를 붙일 공개 도메인 |
| acm_cert_arn | 두 API 호스트를 포함하는 발급 완료 인증서 ARN |
| document_storage_role_arn, pipeline_storage_role_arn | `storage_role_arns` output의 각 서비스 ARN |
| vpc_cidr, alb_subnet_cidr_1, alb_subnet_cidr_2, smtp_port | `network_deploy_inputs` output의 문자열 값 |

terraform output -json의 각 output은 value 필드로 제공된다. 스토리지 IAM·네트워크 output과 계정·앱/공개 도메인·ACM 값을 JSON에 모아 GitHub **feedback Environment**의 AWS_DEPLOY_CONFIG_JSON variable로 저장한다. AWS_DEPLOY_ROLE_ARN도 같은 Environment에 설정한다. DB/provider 비밀번호는 이 JSON과 GitHub variable에 넣지 않는다.

    python scripts/aws_deploy.py render --config /secure/path/aws-deploy.json --sha <40자리-commit-SHA>
    # AWS 배포 승인을 받고 대상 kubeconfig를 확인한 뒤 실행
    python scripts/aws_deploy.py deploy --config /secure/path/aws-deploy.json --sha <40자리-commit-SHA>
    python scripts/aws_deploy.py rollback --config /secure/path/aws-deploy.json --sha <이전-성공-SHA>

배포 순서는 다음과 같다.

1. 입력과 임시 Kustomize 렌더를 검증한다. 미치환 값과 SHA가 다른 업무 이미지를 거부한다.
2. AWS 인증 계정·EKS ARN/버전/상태와 현재 kubeconfig endpoint를 대조하고, 플랫폼의 fruition namespace·gp3 StorageClass 존재와 aws-secrets-manager ClusterSecretStore Ready를 읽기 전용으로 확인한다. ServiceAccount·ConfigMap·ExternalSecret·앱 NetworkPolicy만 적용하고 모든 ExternalSecret Ready를 확인한다. 제한 정책 적용 후 기존 `internal-only-ingress` 정책을 이름으로 삭제한다. `kubectl apply`만으로는 과거 정책이 제거되지 않으며 삭제 실패 시 DB gate와 rollout을 진행하지 않는다.
3. access-db-preflight, document-db-preflight, ai-db-preflight Job이 실제 runtime/migration 로그인, DB·public 스키마·테이블 소유권, 관리자 권한/membership 부재, runtime DML·DDL/교차 CONNECT 경계를 검사한다. 서비스별 runtime/migration 키 두 개만 참조하며 관리자 키는 받지 않는다. app.kubernetes.io/component=db-preflight, app=<서비스>-db-preflight Pod label을 네트워크 정책의 대상으로 사용한다.
4. 세 migration Job Complete를 확인한다. 실패하면 runtime 적용을 중단한다. 이후 동일 사전검증으로 실제 변경된 public schema의 pg_dump --schema-only SHA256을 수집한다.
5. Kafka와 모든 KafkaTopic Ready를 확인한 뒤 runtime을 적용한다. 렌더된 모든 Deployment의 rollout 완료와 모든 KEDA ScaledObject Ready를 확인한다.
6. https://api.<domain>/v3/api-docs와 https://access.<domain>/v3/api-docs의 HTTPS 성공, JSON OpenAPI 3 버전과 비어 있지 않은 paths를 검증한다.
7. 전체 성공에 한해 fruition-release-<SHA> immutable ConfigMap에 비밀 없는 manifest·입력·DB fingerprint를 기록한다. 동일 SHA의 기존 성공 기록은 덮어쓰지 않는다. 재시도 전에 저장된 JSON 입력·manifest와 현재 실제 DB fingerprint가 모두 같은지 확인한다. 다른 입력·manifest는 새 SHA가 필요하며, schema 불일치는 복구 검토 전까지 차단한다. 일치하는 성공 SHA 재시도는 migration을 건너뛰고 기록된 manifest를 다시 적용한다.

bootstrap은 앞 절의 별도 관리자 절차다. 이 배포 스크립트는 DB나 role을 생성하지 않으며, 생성/권한/비밀번호가 잘못됐으면 실접속 gate에서 중단한다. 사전검증 Job은 PostgreSQL 16 client를 사용하고 운영 연결은 PGSSLMODE=require다. AI Secret URI는 Terraform 생성 계약인 postgresql://기대-user:password@기대-core-host:5432/ai_db 형식이어야 한다. 다른 user·host·port·DB와 모든 query(sslmode/host 재정의 포함)는 실제 연결 전에 거부한다. 비밀번호는 Terraform의 영숫자 생성값 또는 URI encoding 문자 집합을 사용한다. 이는 TLS 암호화이며 서버 인증서 검증까지 의미하지 않는다. bootstrap의 verify-full CA 검증과 구분한다. 실제 RDS TLS 및 다중 RDS 경계 검증은 AWS에서 별도 수행한다.

rollback은 **실제 public schema가 이전 성공 release와 동일한 경우의 image/manifest 재배포**다. 현재 서비스 Secret으로 먼저 fingerprint를 대조하며 불일치 시 업무 ConfigMap·Secret·Deployment를 적용하지 않는다(검사용 Job만 실행). 일치하면 이전 성공 manifest를 재사용하고 migration을 건너뛴다. schema가 달라졌거나 성공 기록이 없으면 자동 복구를 거부한다. DB down-migration·데이터 복구·외부 S3 artifact 복원을 수행하지 않는다. 데이터 의미 변경까지 fingerprint가 증명하지 않으므로, 그 경우에는 별도 복구 검토/PITR 절차가 필요하다. schema 변경 migration 실패 후 구 image로 되돌리는 것도 일반적으로 보장하지 않는다.

GitHub Deploy (EKS)는 platform 저장소에서 수동 실행한다. action=deploy는 명시한 release_sha를 사용하며 platform commit SHA에서 추정하지 않는다. 네 ECR 저장소에 같은 release 태그의 이미지가 모두 있어야 한다. 이미지가 없으면 실패하며 platform에서 빌드하거나 push하지 않는다. ECR tag는 Terraform에서 IMMUTABLE이다. action=rollback은 기존 성공 release의 rollback_sha를 사용한다. ECR lifecycle이 이전 SHA를 삭제했다면 복구 대상이 아니므로 필요한 release의 보존 정책을 운영자가 관리한다.

GitHub 관리자는 feedback Environment의 **required reviewers와 deployment branch 제한**을 설정해야 한다. YAML만으로 승인자를 강제하지 않는다. OIDC subject는 repo:<owner/repo>:environment:feedback이며 Terraform github_deploy_environment와 workflow Environment를 함께 맞춘다. 이 저장소는 GitHub 표준 Environment subject 형식을 사용하므로 조직에서 subject customization을 했다면 실제 token claim과 trust policy를 함께 검증한다. 환경 보호 규칙·AWS credentials·EKS/addon 설치·DNS/ACM·실제 배포와 복구는 로컬 테스트로 검증되지 않는다.

    # cluster 호출은 가짜 runner이며 kustomize만 실제 실행한다.
    ../AI/pipeline/.venv/bin/python scripts/tests/test_aws_deploy.py -v
    # 매번 생성·삭제되는 PostgreSQL에서만 실제 SQL/오암호·권한·schema fingerprint를 검사한다.
    ../AI/pipeline/.venv/bin/python scripts/tests/test_aws_db_preflight.py -v

설계 근거: [kubectl wait](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_wait/), [rollout status](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_status/), [GitHub Environment OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).


### AI 로그·Pod 독립성 검증

`../AI/pipeline/.venv/bin/python -m pytest ../AI/pipeline/tests/modules/wiki_generation/test_pipeline_log.py ../AI/pipeline/tests/modules/wiki_generation/test_wiki_generation_pipeline.py ../AI/pipeline/tests/test_pipeline_run_api_contract.py ../AI/pipeline/tests/modules/wiki_ingestion/test_ingest_worker.py -q`로 object storage를 mock한 로그·재전달·교차 디렉터리 회귀를 실행한다. `../AI/pipeline/.venv/bin/python scripts/tests/test_aws_scheduling.py`는 base/AWS 렌더와 Spot 배치 계약을 확인한다.

AWS에서는 worker Pod의 노드와 API Pod의 노드가 다른 상태에서 running/failed/cancelled/succeeded run 로그를 조회하고, worker 종료·재전달 및 Spot 중단 후 DB 결과·로그를 확인해야 한다. 로컬 테스트는 실제 AWS node 증설·중단·S3 내구성을 검증하지 않는다.


### AWS 저장소 IAM·Redis ACL·네트워크 검증

AWS는 `S3_CREDENTIALS_MODE=aws`, `AWS_REGION=ap-northeast-2`를 사용한다. Document와 AI의 ServiceAccount에 서로 다른 `storage_role_arns`를 연결하며 기존 MinIO SDK가 AWS 환경 자격증명(session token 포함) → web identity/IAM provider 순서로 갱신한다. AWS 모드는 로컬 S3 키를 사용하지 않고 미리 생성한 bucket만 사용한다. 로컬 Compose/kind는 기본 `local` 모드와 기존 MinIO 키를 유지한다. Access와 converter는 S3 role이 없다. 일반 Kubernetes API token 자동 마운트는 꺼져 있고 IRSA webhook의 audience=sts.amazonaws.com projected token은 별도로 주입된다.

Redis는 ElastiCache 7.1(Redis OSS 7.0 호환) single primary, 저장·전송 암호화, 서비스별 ACL 사용자와 비밀번호를 사용한다. `REDIS_USERNAME`은 workload별 access/document/pipeline, `REDIS_PASSWORD`는 자기 Secret에서만 받고 `REDIS_SSL=true`다. SMTP port는 비밀이 아니므로 Secrets Manager에서 투영하지 않고 배포 JSON→ConfigMap과 NetworkPolicy에서 같은 값을 쓴다. `smtp_port`는 0이 아닌 숫자로 시작하는 정수 문자열이고 Terraform output과 동일하게 입력한다. ALB 두 CIDR은 서로 겹치지 않는 VPC의 진부분 subnet이어야 한다.

기존 Secrets Manager `ignore_changes`는 새 Redis 비밀번호를 자동 투영하지 않는다. 실제 적용 시 운영자가 Terraform의 서비스 Redis 사용자 비밀번호와 Secret 원본의 `ACCESS_REDIS_PASSWORD`, `DOCUMENT_REDIS_PASSWORD`, `PIPELINE_REDIS_PASSWORD`를 같은 보안 입력 경로로 맞추고 ExternalSecret Ready를 확인해야 한다. 정적 S3 IAM user/key 제거와 Redis cluster→replication group 교체는 실제 AWS plan에서 영향과 진행 중 작업을 검토한 뒤 별도 승인으로 수행한다. 이 코드 작업에서는 기존 클라우드 자격증명을 회전하거나 리소스를 변경하지 않았다.

AWS DB runtime·migration·preflight 모두 `PGSSLMODE=require`를 사용한다. Java JDBC에는 sslmode query를 명시하고 AI는 libpq 환경값을 사용한다. 암호화가 인증서 hostname 검증을 의미하지는 않으며 RDS CA를 배포한 verify-full 검증은 외부 gate다. 로컬 기본은 prefer여서 격리 PostgreSQL 회귀 계약을 유지한다.

```bash
../AI/pipeline/.venv/bin/python scripts/tests/test_aws_redis_acl.py
../AI/pipeline/.venv/bin/python scripts/tests/test_aws_boundaries.py
../AI/pipeline/.venv/bin/python -m pytest ../AI/pipeline/tests/modules/wiki_ingestion/test_storage_credentials.py -q
# 저장소 루트에서 실행한다. Colima는 DOCKER_HOST와 TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE 설정이 필요하다.
./scripts/back-test.sh Document test --tests fruition.shared.util.MinioConfigTest --tests fruition.core.query.RedisAclContractTest
```

Redis 테스트는 매번 임시 Redis 7.0 컨테이너를 생성·정리하며 실제 redis-py/Lettuce, Lua, pub/sub, 기본 사용자 및 교차 key/channel 거부를 검사한다. SDK S3 테스트는 loopback HTTP/STS fixture로 로컬·임시 session token·web identity 서명을 검사한다. 실제 AWS IAM의 prefix별 거부, IRSA token 주입, Redis/RDS TLS, VPC CNI 정책 시행, ALB healthcheck, STS/S3/provider/SMTP 통신은 승인된 AWS 환경에서 따로 확인해야 한다. 무단 cross-prefix GET/PUT/DELETE와 converter→DB·metadata 접근 거부까지 확인하기 전에는 실제 배포 경계가 검증됐다고 표시하지 않는다.


## AWS IaC·플랫폼 운영 절차

### 배포 준비까지만 수행하는 경우

준비 범위는 서비스별 이미지·Deployment·Secret·migration·통신 경계의 로컬 검증과 입력 예시 작성이다. 아래 예시는 배포 시 저장소 밖 보안 디렉터리로 복사해 채운다. 실제 계정 입력이 없는 지금은 placeholder를 유지하며, Terraform plan/apply·플랫폼 install·앱 deploy/rollback·AWS 장애 주입은 실행하지 않는다.

| 예시 | 배포 시 채울 값 |
|---|---|
| [state.tfvars.example](../infra/terraform-state-bootstrap/state.tfvars.example) | 최초 state bucket의 전역 고유 이름 |
| [feedback.tfbackend.example](../infra/terraform/feedback.tfbackend.example) | 생성된 state bucket 이름 |
| [feedback.tfvars.example](../infra/terraform/feedback.tfvars.example) | 예산 이메일·고정 접근 CIDR·SMTP host/port·발신 주소·검증한 addon build |
| [deploy-config.example.json](../k8s/overlays/aws/deploy-config.example.json) | Terraform output과 계정·도메인·발급된 ACM ARN 등 14개 입력 |

`TF_VAR_smtp_username`·`TF_VAR_smtp_password`는 배포 시 보안 저장소에서 환경변수로 주입한다. LLM provider 등 앱 비밀값은 기존 Secrets Manager 계약을 따른다. 예시에 실제 비밀번호를 기록하지 않는다. 앱 JSON은 placeholder가 남으면 render 단계에서 거부된다.

로컬 준비 완료 기준은 아래 IaC 검증과 outbox 테스트 통과다. 이미지 빌드·push에는 변경사항이 포함된 실제 commit SHA를 사용한다. 실제 배포 시에는 Helm을 포함한 운영 도구, 고정 egress/VPC runner, DNS·ACM, DB bootstrap, 플랫폼 설치를 준비한 뒤 순차 배포 절차를 실행한다. 현재 로컬에 Helm이 없는 경우도 이 시점에 설치한다.

실환경 검증은 별도 배포 시 수행한다. 먼저 정상 사용자 요청과 AI 작업 완료를 확인하고, AI Pod 재시작 후 작업·로그 복구, pipeline-api 장애 시 일반 문서 요청 영향, rolling update와 재전달 시 업무 중복 여부를 확인한다. 노드 drain은 replica·PDB·배치 조건을 갖춘 뒤, RDS failover는 Multi-AZ 적용 후에만 수행한다. 각 실험 전 정상 상태와 중단 조건을 기록하고 복구 후 동일 요청을 재검증한다. 이는 실행 예정 절차이며 로컬 테스트 통과를 AWS 장애 검증 성공으로 기록하지 않는다.

### AWS 사전조회 상태

이 절차는 저장소 코드의 실행 계약이다. 준비 작업 당시 인증 계정의 서울 리전을 실제 조회했으며 EKS·RDS·VPC·ACM 인증서·ECR repository가 없고, S3 bucket·Route 53 hosted zone 목록도 비어 있었다. EKS 1.35 managed addon build와 EC2 On-Demand vCPU quota는 조회했다. Terraform plan/apply·addon 설치·서비스 배포·AWS 장애 복구 검증은 아직 수행하지 않았다. 새 환경의 도메인·예산 알림 이메일·고정 접근 CIDR·SMTP 보안 입력을 준비해야 한다. 로컬 검증 스크립트는 AWS API를 호출하지 않는다.

### 로컬 및 PR 검증

AI command outbox의 동시 발행 제어는 다음 테스트로 검증한다. PostgreSQL은 격리된 Testcontainers를 사용하고 Kafka ACK·실패는 mock하므로 실제 AWS/Kafka 장애 검증을 대신하지 않는다.

    bash scripts/back-test.sh Document test --tests fruition.core.document.service.AiCommandOutboxPublisherTest --tests fruition.core.document.service.AiCommandOutboxConcurrencyTest

    bash scripts/aws-iac-validate.sh
    # 프로젝트 venv 대신 별도 Python을 사용할 때: PyYAML 6.0.2, redis 5.2.1 필요
    AWS_VALIDATION_PYTHON=/absolute/path/python bash scripts/aws-iac-validate.sh

두 Terraform root의 fmt, backend 비활성 init과 validate, 플랫폼/앱 Kustomize 렌더, IAM·NetworkPolicy·배포 순서·가짜 AWS/kubectl/Helm 대상 검사, 임시 PostgreSQL/Redis 계약을 실행한다. Terraform과 Docker 이미지/라이브러리 다운로드를 제외하면 외부 서비스가 필요하지 않는다. 기존 개발 DB와 Redis는 사용하지 않는다. AWS IaC contracts workflow는 infra/k8s/scripts/workflow 변경에 실행되며 AWS credential과 id-token 권한을 받지 않는다.

Terraform은 >=1.10,<2.0, 검증 runner는 1.15.8이다. 직접 module 버전은 EKS 20.37.2, IAM 5.60.0, VPC 5.21.0으로 고정한다. provider는 두 root의 .terraform.lock.hcl에 고정하며 CI init은 -lockfile=readonly다. module은 lockfile로 고정되지 않으므로 소스의 exact version도 함께 유지한다.

### State bootstrap과 보관

infra/terraform-state-bootstrap은 서울 region의 state S3 bucket만 생성한다. versioning, AES256 저장 암호화, public access 차단, TLS 강제, force_destroy=false, prevent_destroy=true를 사용한다. 이 root는 처음에는 local state이므로 관리자는 전용 보안 작업 디렉터리와 umask 077을 사용하고, 생성 직후 terraform.tfstate와 backup을 암호화된 관리자 보관소에 보관한다. 그 파일을 잃은 채 bootstrap root를 재실행하지 않는다. 필요한 경우 기존 bucket 리소스의 import/state 복구부터 검토한다. bootstrap state는 app state와 별도 책임이며 앱 deploy role이 읽거나 변경하지 못한다.

    umask 077
    terraform -chdir=infra/terraform-state-bootstrap init
    terraform -chdir=infra/terraform-state-bootstrap plan -var-file=/secure/state.tfvars -out=/secure/state.tfplan
    # plan 검토·승인 후 정확히 같은 파일 적용
    terraform -chdir=infra/terraform-state-bootstrap apply /secure/state.tfplan

/secure/state.tfvars에는 조직/계정별 고유 state_bucket_name을 지정한다. app root는 S3 backend의 use_lockfile=true와 encrypt=true를 코드에서 활성화한다. 저장소 밖 /secure/feedback.tfbackend에 실제 bucket, key="feedback/terraform.tfstate", region="ap-northeast-2"를 지정한다. lock은 같은 key의 .tflock object다. 관리자 role에는 bucket ListBucket을 해당 prefix로 제한하고 state object GetObject/PutObject, lock object GetObject/PutObject/DeleteObject만 허용한다. 앱 배포 role에는 이 state 권한을 주지 않는다.

    terraform -chdir=infra/terraform init -backend-config=/secure/feedback.tfbackend
    # 기존 local state를 이전할 때만 backup과 소유 계정 확인 후 -migrate-state 사용

state와 plan에는 sensitive 표시 여부와 관계없이 비밀번호가 포함될 수 있다. .terraform/, *.tfstate*, *.tfvars, *.tfbackend, *.tfplan, *.plan은 Git에서 제외한다. backend 인증은 AWS profile/임시 credential chain을 사용하고 backend 파일에 access key를 넣지 않는다. state/plan/terraform show -json 출력은 PR·공개 CI artifact·로그에 올리지 않는다. 잠금 해제는 다른 실행이 없고 잠금 소유자가 종료됐음을 확인한 관리자가 해당 lock ID로만 수행한다. 정상 실행 중 force-unlock과 -lock=false는 사용하지 않는다.

### 필수 환경과 managed addon 입력

현재 구현은 project=fruition, region=ap-northeast-2, cluster=fruition-eks, namespace=fruition, GitHub Environment=feedback, EKS=1.35 profile만 허용한다. EKS node AMI는 AL2023_x86_64_STANDARD다. budget_email, eks_public_access_cidrs, SMTP 입력, eks_addon_versions는 필수다. Budget $500/$700은 항상 생성한다.

eks_public_access_cidrs에는 고정 egress runner/VPN의 명시적 IPv4 CIDR만 넣는다. 0.0.0.0/0은 거부한다. 배포 workflow는 self-hosted/linux/x64/fruition-feedback label의 전용 runner를 사용하며 PR 코드 검증용 hosted runner와 분리한다. VPC runner는 private endpoint 경로를 사용할 수 있고 public CIDR은 관리자 VPN 범위로 제한한다. 동적 GitHub-hosted runner의 전체 IP 목록을 넓게 허용하는 기본값은 제공하지 않는다. runner 운영·접근 통제는 외부 준비 조건이다.

eks_addon_versions에는 vpc-cni/coredns/kube-proxy/aws-ebs-csi-driver 네 key의 정확한 vX.Y.Z-eksbuild.N 값을 제공한다. 값을 추정하거나 기본 최신 버전에 맡기지 않는다. 승인된 계정에서 서울 EKS 1.35 조회 결과를 확인하여 private tfvars에 기록한다.

    aws eks describe-addon-versions --region ap-northeast-2 --kubernetes-version 1.35 --output json > /secure/addon-versions.json

실제 조회 결과, architecture=amd64, EKS 1.35 호환과 선택 build를 검토한 뒤 plan을 만든다. vpc-cni의 enableNetworkPolicy=true를 유지한다. 버전 문자열 형식 검증과 provider validate가 실제 AWS build 가용성·정책 집행을 증명하지는 않는다.

### 승인된 IaC plan/apply와 복구

인프라 관리자 role과 앱 GitHub deploy role은 분리한다. 앱 role은 네 ECR repository push/read와 대상 EKS DescribeCluster만 받고 IAM/VPC/RDS/state 수정 권한을 받지 않는다. GitHub feedback Environment의 required reviewers·branch 제한, 전용 runner의 사용 주체는 관리자가 별도로 설정한다.

    umask 077
    terraform -chdir=infra/terraform plan -lock-timeout=5m -var-file=/secure/feedback.tfvars -out=/secure/feedback.tfplan > /secure/feedback-plan.txt
    shasum -a 256 /secure/feedback.tfplan
    # 같은 plan 파일과 digest에 대한 승인 후 적용. apply에서 새 plan을 만들지 않는다.
    terraform -chdir=infra/terraform apply -lock-timeout=5m /secure/feedback.tfplan > /secure/feedback-apply.txt
    terraform -chdir=infra/terraform output -json > /secure/terraform-outputs.json

실패한 apply는 state와 실제 리소스를 새 plan으로 대조한 뒤 처리한다. 이전 state 파일을 덮어써 실제 인프라가 복구됐다고 간주하지 않는다. S3 versioning에서 state를 복원할 때에는 실행 중인 작업이 없고 실제 리소스와 맞는지 검토한다. RDS 변경·Redis 교체·IAM key 폐기·EKS 업그레이드는 역방향 apply로 자동 복구되지 않는다. snapshot/PITR, Redis 재생성 범위와 provider별 복구 제약을 별도로 확인한다. 앱 image 복구는 앞 절의 실제 schema 동일성 gate만 제공한다.

### 플랫폼 설치와 앱 배포의 경계

    bash scripts/aws-platform-up.sh install /secure/terraform-outputs.json

플랫폼 스크립트는 출력의 cluster ARN에서 계정을 확인하고 세 addon role 계정, 실제 STS 계정, DescribeCluster의 ARN/endpoint/1.35/ACTIVE, 현재 kubeconfig API endpoint와 server minor를 모두 대조한다. 불일치하면 최초 kubectl/Helm 쓰기 전에 종료한다. account/context 오류는 가짜 CLI 회귀로 검증하며 이번 작업에서 실제 STS/EKS API에 접속하지 않았다.

| 구성 | 고정 버전 | 검증 범위 |
|---|---|---|
| EKS | 1.35, AL2023 | standard support 종료 2027-03-27. 실제 계정 가용성은 외부 gate |
| Strimzi / Kafka | chart 1.1.0 / Kafka 4.3.0 | 공식 Kubernetes 1.30–1.36 범위, 실제 CRD·broker readiness 외부 gate |
| KEDA | chart 2.20.2 | 공식 Kubernetes 1.33–1.35 범위 |
| AWS Load Balancer Controller | chart/app 3.5.0 | 동일 release 공식 IAM JSON 사용 |
| External Secrets Operator | chart/app 2.9.0, API v1 | chart 조건 >=1.19지만 공식 테스트 표는 1.36. EKS 1.35 실제 검증 필수 |
| Cluster Autoscaler | chart 9.59.0 / image v1.35.0 | cluster minor와 일치, 실제 scale-from-zero 외부 gate |

Helm install/upgrade는 스크립트의 --version과 --wait를 사용한다. ALB controller에는 실제 EKS VPC ID를 지정해 metadata 추론에 의존하지 않는다. 플랫폼 관리자는 k8s/platform/aws의 Namespace, gp3 StorageClass, ClusterSecretStore, 앱 배포 Role/RoleBinding 및 이름이 제한된 read-only ClusterRole/Binding을 설치한다. gp3는 ebs.csi.aws.com, 암호화, WaitForFirstConsumer, Retain이며 AWS KafkaNodePool은 class=gp3다.

앱 EKS access entry는 fruition:deployers 그룹만 부여한다. 앱 role은 fruition namespace의 ConfigMap/ServiceAccount/Service/Deployment/Job/Ingress/NetworkPolicy/ExternalSecret/Kafka/ScaledObject를 배포하고 Pod 상태·로그를 조회한다. Secrets/Role/Binding이나 다른 namespace를 직접 읽고 쓰지 못한다. 플랫폼 자원은 이름이 지정된 읽기만 허용한다. 앱 코드도 허용 kind·namespace 밖 apply를 거부한다. 플랫폼 RBAC는 앱 workflow에 넣지 않는다.

    # 플랫폼 관리자 또는 별도 권한 검증 담당자가 실제 AWS에서 수행할 검증
    kubectl auth can-i create deployments -n fruition --as-group=fruition:deployers --as=permission-check
    kubectl auth can-i get secrets -n other --as-group=fruition:deployers --as=permission-check
    kubectl auth can-i create clusterroles --as-group=fruition:deployers --as=permission-check
    kubectl apply --dry-run=server -k k8s/platform/aws

첫 명령은 yes, 뒤 두 권한 명령은 no여야 한다. 실제 EKS role token으로도 같은 결과를 확인한다. 앱 렌더의 server-side dry-run, addon/ExternalSecret Ready, CRD upgrade, IAM·network 거부 검증은 실제 AWS gate이며 로컬 통과로 대체하지 않는다.

AI Spot node group의 실제 ASG에 discovery enabled/cluster-owned 태그와 node-template label/taint 태그를 별도 aws_autoscaling_group_tag로 부여한다. for_each key는 plan 시점에 고정되고 실제 ASG 이름만 생성 후 결정된다. CA의 변경 권한은 동일 discovery 태그 두 개가 있는 ASG로 제한한다. Terraform validate는 0대에서 node가 늘어나는 동작이나 Spot 중단 복구를 증명하지 않는다.

설계 근거: [EKS 지원 일정](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html), [Strimzi 다운로드/호환표](https://strimzi.io/downloads/), [KEDA 호환 범위](https://keda.sh/docs/2.20/operate/cluster/), [ESO 지원 범위](https://external-secrets.io/latest/introduction/stability-support/), [ALB controller v3.5.0](https://github.com/kubernetes-sigs/aws-load-balancer-controller/releases/tag/v3.5.0), [Terraform S3 locking](https://developer.hashicorp.com/terraform/language/backend/s3).

## 저장소별 운영 책임

platform은 Terraform state·클러스터·Ingress·NetworkPolicy·관측·통합 실행을 소유한다. 서비스 소스·DB migration·OpenAPI·단독 테스트는 해당 서비스 저장소가 소유한다.

```bash
# platform 디렉터리에서 실행
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
./scripts/aws-iac-validate.sh
# Document·AI를 형제 디렉터리에 checkout한 통합 환경에서 추가 실행
.venv/bin/python -m unittest discover -s scripts/tests -p 'test_service_contracts.py' -v
```

서비스 연동 검증은 형제 소스가 필요하며 platform 단독 CI와 구분한다. 기본 IaC 검증은 서비스 소스 없이 실행할 수 있다. 로컬 `dev-up.sh`·`front-up.sh`·`back-up.sh`·`ai-up.sh`는 platform의 공통 `.env`·runtime 관리와 Compose 네트워크를 사용하는 통합 도구다.

독립 platform의 배포 workflow에는 `release_sha`로 ECR에 존재하는 40자리 이미지 묶음 태그를 명시한다. 플랫폼 커밋 SHA를 서비스 이미지 SHA로 사용하지 않는다. 현재 배포 스크립트는 네 이미지에 동일한 release 태그가 있는 묶음을 요구한다. 서비스마다 다른 SHA를 직접 입력하는 release manifest와 각 서비스의 이미지 게시 workflow는 아직 구현하지 않았다. 이번 정리는 실제 배포를 실행하지 않는다.

## AWS 운영 보완 실행 계획

상태: **계획이며 아래 수집기·알림·역할·훈련은 아직 구현하거나 AWS에서 실행하지 않았다.** 부족 항목의 코드 근거와 작업 의존성은 [아키텍처](architecture.md#aws-운영-보완-계획), 구성 선택은 [ADR-0021](adr/0021-aws-observability-and-operations.md)을 참조한다. RB는 Runbook을 뜻하며 RBAC와 Rollback을 함께 다룬다.

### 구현 시작 전 확정할 운영 입력

| 입력 | 책임 | 확정 내용 |
|---|---|---|
| 운영 시간과 담당자 | 운영 책임자 | 대응 시간대, 주 담당·대체 담당 실명, 부재 시 인계, 업무 시간 밖 장애 처리와 사용자 안내 |
| 알림 경로 | platform + 운영 책임자 | SNS 수신 주소·구독 확인, 실제 사용할 호출 채널, 미확인 알림의 대체 담당자 전달 방식 |
| 데이터·복구 목표 | 서비스 책임자 | 중요 데이터 범위, 허용 중단/손실, 삭제·취소 작업의 복구 정책, DB/S3/Kafka 정합성 판정 |
| 비용과 보존 | platform + 데이터 책임자 | 월 관측 예산, 예상 일일 로그량·metric 수, 로그/감사 보존 승인, Vercel 조회 권한과 보존 기간 |

후보 목표는 장애 탐지 5분, 운영 시간 내 확인 15분, 같은 스키마의 앱 rollback 30분, 데이터 복원 후 업무 재개 4시간, 업무 데이터 RPO 15분이다. **확정 SLA나 실측 보장이 아니다.** RTO는 장애 발생부터 업무 검증 완료까지, RPO는 장애 시점과 최종 복구 가능한 정합 데이터 시점의 차이로 측정한다. RDS의 7일 백업 보존만으로 RPO 15분을 충족했다고 판정하지 않는다. 담당자와 복구 시험 결과에 따라 목표를 확정하거나 구성을 보완한다.

### 대시보드와 알림 초안

Dashboard는 release별 API 상태, 비동기 처리, 저장소, 클러스터 용량, 수집기 상태·비용으로 구성한다. 알림에는 환경·서비스·발생 시각·지표·Dashboard 링크·Runbook ID를 넣는다. 아래 임계치는 초기 부하 시험에서 보정할 후보이며, 실제 metric 이름·dimension·period·결측 처리까지 IaC에서 고정한다.

| 대상 / 원천 | 후보 조건 | 처리·오탐 방지 | Runbook |
|---|---|---|---|
| API 가용성 / ALB HealthyHostCount, Ready Pod | 대상 서비스의 정상 대상 0 또는 Ready 0이 2분 지속 | 긴급 알림. 배포 중에도 전체 대상 소실은 숨기지 않는다 | RB-01 |
| API 오류 / ALB target 5xx, RequestCount | 5분 합계 요청 100건 이상에서 5xx 비율 5% 초과 | 긴급 알림. ALB 자체 5xx는 별도 패널·알림으로 분리. 저트래픽 전체 장애는 가용성/업무 probe로 보완 | RB-01 |
| API 지연 / ALB TargetResponseTime p95 | 5분 요청 100건 이상에서 5초 초과 | 초기에는 주의 알림. SSE·장시간 응답이 섞이는 target group은 기준선을 분리 검토하며 업무 API p95로 오표기하지 않음 | RB-01 |
| 큐 정체 / DB oldest pending age, Kafka group lag | query 60초·ingest/변환 300초 초과가 5분 지속 | 주의 알림. 10분간 완료 진전도 없으면 긴급 알림. 작업 유형별 기준선 보정, lag만으로 실패 판정하지 않음 | RB-02 |
| AI 실패 / 작업 결과 EMF | 10분간 성공+실패 20건 이상에서 실패율 10% 초과 | 정상 사용자 취소는 분모·분자에서 제외. 복구 실패는 건별 긴급 알림. 공급자 429와 앱 오류 구분 | RB-02 |
| Kafka / exporter·broker 상태 | 정상 broker 0이 2분 지속, consumer lag 증가 10분 지속 | broker 소실은 긴급, lag 증가는 주의. partition·consumer group·worker 최대치 함께 표시 | RB-03 |
| DB / RDS 기본 지표 | 여유 공간 20% 미만 주의·10% 미만 긴급, CPU 80% 초과 15분, 연결 수 예산 80% 초과 5분 | 공간은 할당 용량과 함께 계산. 연결 예산은 실제 DB 설정과 서비스 pool 합계로 산정 | RB-04 |
| Redis / 연결 실패·엔진 지표 | 앱 연결 실패 2분 지속, eviction이 기준선 초과 5분 지속 | 연결 실패는 긴급, eviction은 주의. cache miss와 실제 권한 검증 실패를 구분 | RB-05 |
| 관측 / 수집기와 주기 수집 heartbeat | 1분 주기 heartbeat가 5분 이상 누락 | 결측을 정상 0으로 처리하지 않음. 작업이 없는 경우의 완료 지표 결측은 heartbeat와 구분 | RB-07 |
| 용량 / Pending·재시작·노드 상태 | Pending 5분, 같은 container 재시작 10분 내 3회 | 주의 알림, Ready 소실은 RB-01로 승격. 리소스 부족·이미지·권한·volume 실패 분리 | RB-08 |
| 관측 비용 / 로그 유입량·metric 수·청구 지표 | 확정한 일일 유입 예산 초과 또는 월 예상 비용 상한 초과 | 주의 알림. 기존 전체 AWS 예산 알림과 별도로 원인 확인, 예산 알림을 자동 지출 차단으로 간주하지 않음 | RB-07 |

SNS 구독만으로 확인·재호출·당번 배정이 완성되지는 않는다. 초기 담당자는 합의된 채널에 수신 확인을 남기고, 미확인 15분 후 대체 담당자에게 전달하는 절차를 검증한다. 무인 시간까지 자동 호출이 필요하면 호출 시스템 연동을 외부 배포 전 추가 요구사항으로 확정한다.

### 장애별 Runbook 구성

각 절차는 실행 환경·담당·권한, 증상/영향, 읽기 전용 진단, 완화·복구, 업무 검증, 중단/에스컬레이션 조건, 증적 순서로 작성한다. 아래는 구현 시 실행 명령과 실제 리소스 이름을 채울 절차 초안이다.

| ID / 장애 | 진단 | 완화·복구 순서 | 완료·중단 기준 |
|---|---|---|---|
| RB-01 API 오류·중단 | ALB target health, Ready, 최근 release, 요청 ID 로그, DB 연결 비교 | 직전 배포와 연관되면 RB-06. 자원 부족이면 원인 확인 후 용량 조정. 의존 서비스 장애는 해당 RB 실행 | 로그인·권한이 다른 두 사용자·문서 조회/저장 probe 성공, 오류율 정상화. 무관한 서비스 반복 재시작 금지 |
| RB-02 AI/변환 큐 정체 | oldest age, consumer lag, worker 상태, LLM 429/timeout, DB 작업 상태·attempt | 신규 작업 유입을 합의된 방식으로 제한하고 의존성 복구. 멱등성·소유권이 검증된 작업만 재시도 | 기존 작업 완료/실패/취소가 수렴하고 중복 결과 없음. 상태 불일치·부분 적용이면 재시도 중단 후 서비스 담당자 확인 |
| RB-03 Kafka 중단 | broker/volume/노드, topic·consumer group, outbox 미발행 수 | volume과 broker 복구 후 producer/consumer 순차 확인. 손실 시 DB 원본·outbox·처리 이력으로 재발행 범위 결정 | backlog 해소와 중복 억제 확인. 근거 없는 offset reset·topic 삭제 금지 |
| RB-04 DB·데이터 복구 | RDS 상태/공간/연결, 최근 migration, 복원 가능 시각, 영향 데이터 범위 | 연결·용량 문제부터 완화. 데이터 복원은 격리된 새 DB에서 검증하고 승인된 전환 절차로 연결 변경. Access/Core·S3 version·Kafka 재처리를 조율 | 계정/권한·문서·AI 상태의 정합성, 실측 RTO/RPO 기록. 복원 시점이 다른 저장소를 확인 없이 연결하지 않음 |
| RB-05 Redis 소실 | TLS/ACL/네트워크, 앱 fallback, session/권한 cache·stream 사용 범위 | 연결 복구 후 DB 기반 재구성 범위와 재로그인 영향을 확인. SSE 재연결·업무 상태 재조회 검증 | 다른 사용자 권한 누출 없이 재로그인/재연결 성공. Redis를 전부 재생 가능한 단순 cache로 가정하지 않음 |
| RB-06 잘못된 release | release manifest, image digest, migration 전후 schema, 최초 실패 시각 | 같은 schema에서 직전 성공 이미지 묶음 복구. schema 변경이 있으면 자동 rollback 중단 후 전진 수정 또는 RB-04 판단 | 로그인→workspace→업로드/변환→AI 질의/취소 smoke 성공. 자동 down migration 금지 |
| RB-07 로그·알림 소실/비용 급증 | collector Ready, heartbeat, IAM 거부, network, 유입량·dimension 증가 | 수집 경로 복구, 중복 수집·과도한 필드 수정. 중앙 수집 장애 중에는 Pod 로그로 임시 조사하고 누락 구간 기록 | 새 오류 로그 검색·실제 알림 수신/해제 확인. 비용만을 이유로 전체 감사 로그를 무작정 끄지 않음 |
| RB-08 Spot/노드·Pod 장애 | scheduler events, requests/limits, CA/KEDA 상태, ASG/IP/partition 한도 | graceful 종료·재배치 확인 후 부족한 용량/권한 수정. 작업 소유권·재시도 상태 확인 | Pod/필요 시 노드 확장과 축소, 진행 작업 수렴 확인. 증설이 LLM/DB 한도를 초과하면 제한 후 에스컬레이션 |

운영 역할은 조회 전용, 앱 배포, 플랫폼 변경, 긴급 복구로 분리한다. 조회 역할의 CloudWatch 검색·Pod 로그 접근은 민감 로그 노출까지 고려해 범위를 제한한다. Secret 조회·다른 namespace 변경·IAM 권한 상승 거부를 실제 역할 세션으로 검증하고, 긴급 권한 사용 기록과 회수 절차를 남긴다. 배포 role의 기존 권한 검사만으로 운영자 RBAC 검증을 대체하지 않는다.

다음은 향후 운영자가 실행할 읽기 전용 진단 예시이며 이번 작업에서 실행하지 않았다. 먼저 account/context가 대상 환경과 일치하는지 확인한다.

```bash
aws sts get-caller-identity
kubectl config current-context
kubectl get pods -n fruition -o wide
kubectl get events -n fruition --sort-by=.metadata.creationTimestamp
kubectl get deployments,hpa,scaledobjects -n fruition
# 실제 Pod와 container 이름으로 대체
kubectl logs -n fruition <pod> -c <container> --since=15m
kubectl logs -n fruition <pod> -c <container> --previous
```

### 구현 순서와 검증 관문

구현 묶음은 아키텍처 표의 순서 0~9를 따른다. 먼저 운영 입력을 확정하고 수집/IAM과 서비스 로그 계약을 준비한다. 이어 지표·알림, 역할·Runbook·복원 절차, Document 동시 실행 안전성, 서비스별 release/업무 smoke를 완료한다. HPA와 저장소 이중화는 이 기초 위에 적용한다.

| 관문 | 실행 범위 | 통과 증거 |
|---|---|---|
| A: 로컬 준비 | AWS 변경 없이 Terraform fmt/validate, Kustomize 렌더, 기존 IaC 계약 테스트. 추가 구현에는 로그 비밀값 제외·상관 ID, 지표 집계/결측, release manifest/rollback 거부, 두 worker 동시 실행·재시작 테스트 | 검증 명령·결과, 변경한 IAM/resource 범위, 실패 재현과 수정 후 통과. 렌더 성공을 실제 설치 성공으로 표시하지 않음 |
| B: 격리 AWS 관측·권한 | 별도 실행 승인을 받은 검증 환경에 설치. 앱 Pod 교체 후 이전 로그 조회, 알려진 오류/collector 중단으로 실제 알림 발생·수신·해제, 실제 운영 역할 허용/거부 확인 | request/run ID로 HTTP/Kafka/worker 연결, 수집 지연, 가짜 비밀값 미노출, 담당자 확인 시각, 권한 검사 결과. 알림 강제 상태 변경만으로 통과 불가 |
| C: 격리 AWS 복구·배포 | 실패 release와 같은 schema rollback, DB 새 인스턴스 복원, S3 version 확인, Kafka 재전달·Redis 소실·worker 종료 시험 | Access/Core 공통 복원 시점과 데이터 대조, 삭제/취소/권한 정합성, 미복구 범위, 실측 RTO/RPO. frontend를 포함한 실제 업무 smoke 결과 |
| D: 외부 피드백 진입 | P0 완료·담당/채널 확정 후 제한된 트래픽으로 관측 | 후보 24시간 관찰 동안 업무 probe·알림 경로·비용 유입 확인. 알려진 가용성 한계와 지원 시간 안내, 미통과 P0가 있으면 진입 보류 |
| E: 다중 인스턴스 운영 | P1 구현 후 부하·Pod/노드 drain·Spot 중단·저장소 failover 시험 | Pod/노드 확장·축소, 중복 작업 억제, 승인된 지연/오류 목표, 저장소 정합성. 용량과 비용 한도 재확인 |

업무 smoke는 전용 시험 계정·workspace로 로그인, 권한이 다른 사용자 접근 거부, 문서 업로드/변환/조회, AI 질의·취소와 최종 상태 확인을 포함한다. OpenAPI 응답만으로 업무 정상 판정을 하지 않는다. 외부 LLM 사용료와 시험 데이터 정리 범위도 시험 전에 정한다.

각 훈련은 실행 ID, 환경, 서비스 SHA/digest, 시작·탐지·확인·업무 복구 시각, 알림 수신 기록, 정합성 대조 결과, 잔여 실패와 담당자를 남긴다. 증적 저장 위치는 접근을 제한한 운영 저장소로 정하고 보존·삭제 정책을 적용한다. 토큰·원문 문서·사용자 개인정보를 증적에 포함하지 않는다. 삭제한 루트 `output/`를 운영 증적 저장소로 다시 만들지 않는다.

RDS 복원은 새 인스턴스 생성과 연결 전환을 포함하므로 백업 존재 확인과 구분한다. [RDS 시점 복원](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIT.html), [복구 목표 측정 원칙](https://docs.aws.amazon.com/wellarchitected/2023-10-03/framework/rel_planning_for_recovery_dr_tested.html)을 기준으로 훈련 결과를 평가한다. 이번 작업의 완료 범위는 부족 항목 확인과 계획 문서화이며 관문 A~E의 새 운영 기능 검증을 수행했다는 의미가 아니다.
