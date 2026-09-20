# AWS 환경변수 대조 (2026-09-20)

비교 대상은 `infra/.env.example`, `infra/.env.pipeline.example`, Terraform Secret 초기값 및 `kubectl kustomize k8s/overlays/aws` 결과다. 운영 OAuth 6개 항목은 비어 있지 않음만 확인했으며 실제 값은 문서에 포함하지 않는다. 다른 서비스 저장소의 실행 코드와 기본값까지 검증한 결과는 아니다. Terraform은 인프라·Secret 초기 생성을, Kubernetes ConfigMap/ExternalSecret은 앱 환경변수 주입을 담당하므로 예제의 모든 변수를 Terraform에 추가할 필요는 없다.

## OAuth 등록 절차

1. 서울 리전 Secrets Manager에서 기존 `fruition/app`을 연다.
2. Secret value → Retrieve secret value → Edit → Key/value에서 아래 여섯 항목을 추가하거나 수정한다. 기존 DB·Redis·JWT·MFA·메일·AI 항목은 보존한다.
3. `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `KAKAO_CLIENT_ID`, `KAKAO_CLIENT_SECRET`에 재발급한 운영 값을 입력한다. 값에 `.env` 문법의 따옴표나 `KEY=`를 포함하지 않는다.
4. 저장 후 Access용 ExternalSecret 매핑 배포와 동기화 확인이 필요하다. OAuth 매핑은 코드에 포함되어 있으며 운영 반영은 별도다. Secret만 저장하거나 Access만 재시작해서는 연결되지 않는다.
5. 검토된 배포 절차로 Access Pod를 교체하고 세 제공자의 로그인 시작 리다이렉트 및 실제 로그인 완료를 검증한다. 최초 설치 manifest 고정 검증을 우회하기 위해 bootstrap 기록을 삭제하지 않는다.

Terraform의 여섯 빈 초기값은 신규 Secret의 항목 준비용이며 실제 값 관리 수단이 아니다. 기존 Secret은 `ignore_changes = [secret_string]`으로 보호되어 apply만으로 키를 추가하지 않는다. ignore_changes 제거·Secret 재생성·기존 JSON 전체 교체는 필요 없다.

각 제공자의 콘솔에는 Access 공개 주소의 `/login/oauth2/code/google`, `/login/oauth2/code/naver`, `/login/oauth2/code/kakao`를 각각 등록한다. 프론트 복귀 URI와 CORS는 배포 설정의 프론트 도메인으로 렌더링하며 localhost 값을 복사하지 않는다.

## 누락 또는 추가 검토 항목

| 변수 | AWS 구성에서 확인한 상태 | 판단 |
|---|---|---|
| OAuth ID/Secret 6개 | Terraform 빈 초기값 및 Access ExternalSecret 매핑 포함 | 6개 값 입력 확인; 매핑 배포 필요 |
| `RESTORE_PREVIEW_TOKEN_SECRET` | Terraform/ExternalSecret/ConfigMap 없음 | 예제가 다중 백엔드에서 공통 키 사용을 안내함. Document 2 replicas이므로 서명 키 기본값·공유 동작을 서비스 코드에서 우선 확인 |
| `WIKI_SEMANTIC_MAX_WORKERS` | 명시적 주입 없음 | 앱 기본값 확인 후 동시 처리·비용 정책 결정 |
| `QUERY_TIMEOUT_SECONDS`, `POST_INGEST_EVIDENCE_LIMIT`, `QUERY_EVIDENCE_LIMIT` | 명시적 주입 없음 | 앱 기본값 확인 후 필요 시 ConfigMap에 고정 |
| `JWT_ACCESS_EXPIRATION_SECONDS`, `JWT_REFRESH_EXPIRATION_SECONDS` | 명시적 주입 없음 | 앱 기본값 확인 후 인증 만료 정책 고정 |
| `MAIL_SMTP_CONNECTION_TIMEOUT_MS`, `MAIL_SMTP_TIMEOUT_MS`, `MAIL_SMTP_WRITE_TIMEOUT_MS` | 명시적 주입 없음 | 예제는 기본 5000ms를 안내하나 서비스 코드 확인 필요 |
| `MFA_ISSUER`, `WORKSPACE_INVITATION_TTL_SECONDS` | 명시적 주입 없음 | 표시명·초대 만료의 앱 기본값 확인 필요 |

## AWS에서 다른 방식으로 처리하거나 로컬 전용인 항목

| 변수 | 처리 방식 / 확인 범위 |
|---|---|
| `POSTGRES_ADMIN_USER`, `POSTGRES_ADMIN_PASSWORD` | RDS 관리자 계정/관리형 Secret 및 별도 DB 초기화. 앱 runtime에 주입하지 않음 |
| `ACCESS_DATABASE_URL`, `CORE_DATABASE_URL`, `CORE_DB_MIGRATION_URL` | AWS Java 서비스/마이그레이션은 서비스별 DB host·name·user·password 설정 사용. 예제 URL을 그대로 복사하지 않음 |
| `AI_DB_RUNTIME_PASSWORD`, `AI_DB_MIGRATION_PASSWORD` | Terraform에서 생성하고 연결 URL을 구성. 앱/Job에는 `AI_DATABASE_URL`, `AI_DB_MIGRATION_URL`로 전달 |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | AWS는 IRSA와 `S3_CREDENTIALS_MODE=aws` 사용. 로컬 MinIO 정적 키를 추가하지 않음 |
| `S3_REGION` | AWS는 `AWS_REGION`을 명시. 서비스별 변수 해석은 코드 확인 필요 |
| `S3_PUBLIC_ENDPOINT`, `S3_FORCE_PATH_STYLE` | AWS 매니페스트에는 미지정. 예제는 로컬 MinIO용 값이며 실제 S3 URL·접근 방식은 서비스 코드에서 확인 필요 |
| `AUTH_EMAIL_DEV_FIXED_CODE` | 운영에 추가하지 않는 개발용 고정 인증번호 |
| `APP_ENV`, `WEB_ORIGIN` | 예제에는 있으나 AWS 매니페스트에는 없음. Spring production profile 및 CORS는 별도 명시. 모든 서비스에서 동등한 대체인지는 코드 확인 필요 |
| `ACCESS_PORT`, `PIPELINE_API_PORT` | 로컬 포트 설정. AWS Service/container 포트는 매니페스트에서 지정 |

## 이미 연결됐거나 예제와 다른 항목

- DB·Redis·JWT·MFA·SMTP·내부 토큰은 Terraform 초기 설정과 서비스별 ExternalSecret 경로가 있다.
- `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `LANGSMITH_API_KEY`, `TAVILY_API_KEY`는 빈 초기값과 ExternalSecret 매핑이 있다. 실제 운영 값 입력 여부는 이번 조사에서 확인하지 않았다.
- CORS, OAuth 프론트 복귀 주소, 초대 URL, 내부 API URL, Kafka, HTTPS 쿠키 설정은 ConfigMap/Deployment에서 관리한다.
- `QUERY_EMBEDDING_MODE`: 예제 `bge-m3`, AWS 렌더 결과 `text-only`.
- `QUERY_WEB_SEARCH_TIMEOUT_SECONDS`: 예제 `20`, AWS 렌더 결과 `10`.
- LangSmith는 tracing `false`, 프로젝트명 `local-pilot-dev`를 상속한다. 추적을 켤 때 운영 프로젝트명도 결정한다.
- `AGENT_SKILLS_ENABLED`, `SKILL_API_ENABLED` 및 query evaluator 설정은 ConfigMap에 있다.
- 이전 환경변수 목록의 `LLM_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`, `AI_ENABLED_PROVIDERS`, `QUERY_WEB_SEARCH_MODE`는 현재 두 예제 파일에 없다. 현재 예제는 provider별 키와 API/DB 모델 설정을 안내하므로 이전 목록을 일괄 주입하지 않는다.

이 대조 작업은 AWS 설정을 변경하거나 배포하지 않았다.

## 배포 전제

현재 최초 설치 릴리스는 bootstrap 준비 완료 상태이고 업무 검증 deploy가 남아 있다. 기존 초기 설치 기록은 manifest를 고정하므로 이 변경을 병합한 main에서 같은 initial-install SHA를 실행하면 manifest 불일치로 차단된다. 검증 계정(`AWS_SMOKE_EMAIL`, `AWS_SMOKE_PASSWORD`)과 workspace 변수(`AWS_SMOKE_WORKSPACE_ID`) 준비뿐 아니라 기존 검토 manifest로 최초 업무 검증을 완료할 배포 경로가 필요하다. 이후 변경 manifest를 반영한 새 릴리스와 호환성·복원 검토를 준비한다. 이 PR은 해당 전환 기능을 추가하지 않으며, 기록 삭제나 직접 apply로 검증을 우회하지 않는다.
