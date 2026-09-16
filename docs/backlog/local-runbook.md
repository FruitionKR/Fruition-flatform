# 로컬 실행 가이드

이 문서는 Fruition MVP를 새 환경에서 재현 가능하게 실행하기 위한 요구사항과 실행 순서를 정리합니다. 로컬 실행 대상은 PostgreSQL, MinIO, Spring Boot 백엔드, Next.js 프론트엔드입니다.

## 요구사항

| 항목 | 권장 버전 | 확인 명령 | 비고 |
|---|---:|---|---|
| Docker | 최신 안정 버전 | `docker --version` | PostgreSQL, MinIO 실행에 필요 |
| Docker Compose | Docker CLI plugin | `docker compose version` | `docker-compose` 단독 명령이 아니라 `docker compose` 사용 |
| Java JDK | 21 | `java -version` 또는 `$JAVA_HOME_21/bin/java -version` | 백엔드 Gradle toolchain 요구사항 |
| Node.js | 20 LTS 이상 | `node -v` | 프론트엔드 Next.js 실행 |
| npm | 10 이상 | `npm -v` | `frontend/package-lock.json` 기준 설치 |
| curl | 기본 제공 또는 설치 | `curl --version` | 기동 확인에 사용 |
| lsof 또는 fuser | OS 기본 도구 | `lsof -v` 또는 `fuser -V` | 전체 종료 스크립트의 포트 기반 프로세스 정리에 사용 |

macOS에서 Docker Desktop 대신 Colima를 쓸 수 있습니다. 이 경우 `colima start` 후 Docker context가 Colima를 보도록 설정되어 있어야 합니다. 제공 스크립트는 Docker daemon에 연결하지 못하고 `colima` 명령이 있으면 Colima 시작을 시도합니다.

## 포트

아래 포트가 비어 있어야 합니다.

| 포트 | 서비스 |
|---:|---|
| `3000` | Next.js 프론트엔드 |
| `8080` | Spring Boot 백엔드 |
| `5432` | PostgreSQL |
| `9000` | MinIO API |
| `9001` | MinIO Console |

기본 실행 스크립트가 pipeline API까지 함께 실행하므로 `8000`도 필요합니다. 기본 프론트엔드 설정은 백엔드를 `http://localhost:8080`으로 호출합니다.

## 환경변수

로컬 환경변수는 `infra/.env`에서 관리합니다. 파일이 없으면 아래 명령으로 생성합니다.

```sh
cp infra/.env.example infra/.env
```

기본 인프라와 프론트/백엔드 기동에는 예시 값만으로 충분합니다. 문서 처리 pipeline 또는 LLM 기능을 실제로 사용하려면 provider에 맞는 `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`을 채워야 합니다.

Java 21이 기본 Java가 아닌 환경에서는 아래 중 하나를 지정합니다.

```sh
export JAVA_HOME_21=/path/to/jdk-21
```

macOS Homebrew 설치 예시는 다음 경로입니다.

```sh
export JAVA_HOME_21=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
```

## 한 번에 실행

처음 실행하는 컴퓨터에서는 bootstrap 스크립트로 로컬 환경 파일과 프로젝트 의존성을 먼저 준비할 수 있습니다.

```sh
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

스크립트가 수행하는 작업은 아래와 같습니다.

1. 필수 명령(`curl`, `docker`, `docker compose`, `node`, `npm`)과 Node.js 20 이상, npm 10 이상, Java 21 확인
2. `infra/.env`가 없으면 `infra/.env.example`에서 복사
3. `frontend/node_modules`가 없거나 `package.json` / `package-lock.json`이 더 최신이면 `npm install` 실행

pipeline API는 Docker 컨테이너 안에서 `llmPipeline/requirements.txt`를 설치하므로 일반 실행에는 로컬 Python 가상환경이 필요하지 않습니다. pipeline 코드를 로컬에서 직접 실행하거나 테스트해야 하면 아래 옵션을 사용합니다.

```sh
./scripts/bootstrap.sh --with-python
```

이 옵션은 `llmPipeline/.venv`를 만들고 `llmPipeline/requirements.txt`를 설치합니다.

실행 스크립트를 사용하면 인프라, pipeline API, 백엔드, 프론트엔드를 순서대로 시작하고 HTTP 응답까지 확인합니다.

```sh
chmod +x scripts/dev-up.sh
./scripts/dev-up.sh
```

스크립트가 수행하는 작업은 아래와 같습니다.

1. `scripts/bootstrap.sh`로 로컬 환경 파일과 프론트엔드 의존성 준비
2. Docker daemon 확인, 가능한 경우 Colima 시작
3. `infra/compose.infra.yml`로 PostgreSQL과 MinIO 시작
4. Java 21 경로 탐색 후 `backend/./gradlew bootRun` 실행 및 `http://localhost:8080/actuator/health` 응답 확인
5. backend Flyway 완료 후 `infra/compose.ai.yml`의 pipeline API 시작 및 `http://localhost:8000/health` 응답 확인
6. `frontend/npm run dev` 실행 및 `http://localhost:3000` 응답 확인

backend를 pipeline API보다 먼저 시작하는 이유는 공용 DB 스키마를 Flyway가 먼저 생성해야 하기 때문입니다. pipeline API의 startup schema 초기화가 먼저 실행되면 빈 DB에서도 Flyway V1과 테이블 생성이 충돌할 수 있습니다.

스크립트를 종료하려면 터미널에서 `Ctrl-C`를 누릅니다. 이때 백엔드와 프론트엔드 프로세스는 종료되지만 PostgreSQL, MinIO, pipeline API 컨테이너는 유지됩니다.

## 수동 실행 순서

자동 스크립트 대신 단계별로 실행하려면 아래 순서를 사용합니다.

### 1. 인프라 시작

```sh
docker compose --env-file infra/.env -f infra/compose.infra.yml up -d
```

상태 확인:

```sh
docker compose -f infra/compose.infra.yml ps
```

`fruition-postgresql-dev`가 `healthy` 상태가 되면 백엔드를 실행할 수 있습니다.

### 2. 백엔드 시작

Java 21이 기본 Java인 경우:

```sh
cd backend
./gradlew bootRun
```

기본 Java가 21이 아닌 경우:

```sh
cd backend
./gradlew bootRun -Porg.gradle.java.installations.paths=/path/to/jdk-21
```

기동 확인:

```sh
curl http://localhost:8080/actuator/health
```

정상 응답은 `{"status":"UP"}`입니다. readiness 확인은 인증과 workspace ID가 필요한 업무 API가 아니라 Actuator health endpoint를 사용합니다.

Swagger UI:

```text
http://localhost:8080/swagger-ui.html
```

### 3. 프론트엔드 시작

```sh
cd frontend
npm install
npm run dev
```

기동 확인:

```sh
curl -I http://localhost:3000
```

브라우저에서 아래 주소를 엽니다.

```text
http://localhost:3000
```

## 종료

프론트엔드와 백엔드는 실행 중인 터미널에서 `Ctrl-C`로 종료합니다.

인프라 컨테이너를 중지하려면 저장소 루트에서 아래 명령을 실행합니다.

```sh
docker compose -f infra/compose.infra.yml down
```

로컬 데이터베이스와 객체 스토리지 볼륨까지 삭제하려면 `-v`를 추가합니다.

```sh
docker compose -f infra/compose.infra.yml down -v
```

## 전체 종료 스크립트

앱 프로세스와 로컬 인프라, pipeline API를 한 번에 종료하려면 아래 스크립트를 사용합니다.

```sh
./scripts/dev-down.sh
```

스크립트가 수행하는 작업은 아래와 같습니다.

1. `3000` 포트의 Next.js 프로세스 종료
2. `8080` 포트의 Spring Boot 프로세스 종료
3. `8000` 포트 사용 프로세스와 `infra/compose.infra.yml`, `infra/compose.ai.yml`의 PostgreSQL, MinIO, pipeline API 컨테이너 종료

로컬 데이터베이스와 객체 스토리지 볼륨까지 삭제하려면 `--volumes` 옵션을 사용합니다.

```sh
./scripts/dev-down.sh --volumes
```

`--volumes`는 업로드 문서, Wiki page, DB 레코드, pipeline 실행 산출물 등 로컬 개발 데이터를 삭제하므로 재현 환경 초기화가 필요한 경우에만 사용합니다.

## 문제 해결

### Docker daemon에 연결할 수 없음

오류 예:

```text
failed to connect to the docker API at unix:///var/run/docker.sock
```

Docker Desktop을 사용하면 앱이 실행 중인지 확인합니다. Colima를 사용하면 아래 명령으로 시작합니다.

```sh
colima start
docker context use colima
```

필요하면 Docker socket을 직접 지정합니다.

```sh
export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
```

### Java 21 toolchain을 찾지 못함

오류 예:

```text
Cannot find a Java installation matching: {languageVersion=21}
```

JDK 21을 설치하고 `JAVA_HOME_21`을 지정하거나, Gradle 실행 시 경로를 직접 넘깁니다.

```sh
./gradlew bootRun -Porg.gradle.java.installations.paths=/path/to/jdk-21
```

### 포트가 이미 사용 중임

아래 포트를 점유한 프로세스를 종료하거나, 해당 서비스를 먼저 내립니다.

```sh
lsof -nP -iTCP:3000 -sTCP:LISTEN
lsof -nP -iTCP:8080 -sTCP:LISTEN
lsof -nP -iTCP:5432 -sTCP:LISTEN
```

### 프론트엔드에서 백엔드 호출이 실패함

`frontend/next.config.mjs`는 기본 백엔드 주소를 `http://localhost:8080`으로 사용합니다. 다른 주소를 사용해야 하면 프론트엔드 실행 전에 아래 값을 지정합니다.

```sh
export NEXT_PUBLIC_BACKEND_URL=http://localhost:8080
```

### 업로드 후 문서 처리가 계속 processing 상태임

기본 실행은 pipeline API까지 포함합니다. 문서 처리가 계속 `processing` 상태라면 `http://localhost:8000/health` 응답과 `infra/.env`의 `PROCESSING_ENDPOINT`, `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` 값을 확인해야 합니다.
