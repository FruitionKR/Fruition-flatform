# 배포

배포 단위 = 이미지 = 폴더. 로컬 compose·kind로 검증한 그대로 AWS로 매핑된다.

## 이미지

| 서비스 | 빌드 컨텍스트 | Dockerfile |
|---|---|---|
| access-svc | `services/` | `services/access-svc/Dockerfile` |
| document-svc | `services/` | `services/document-svc/Dockerfile` |
| pipeline-api / ingest-worker | `services/ai-svc/pipeline/` | 공용 이미지, command만 교체 |
| converter | `services/ai-svc/converter/` | `Dockerfile` |
| frontend | — | Vercel |

access-svc·document-svc는 Gradle 멀티프로젝트라 빌드 컨텍스트가 `services/`(공유 모듈 `java-shared` 포함)다.

## 로컬 실행

**개발(호스트에서 gradle 직접)**: `scripts/dev-up.sh` — document-svc(:8080)·access-svc(:8081) 순차 기동(document가 Flyway 소유라 먼저), pipeline·frontend 포함.

**배포 단위 재현(전부 컨테이너)**:
```bash
cd infra
docker compose --env-file .env \
  -f compose.infra.yml \        # postgres·redis·kafka·minio
  -f compose.ai.yml \           # pipeline-api·ingest-worker
  -f compose.converter.yml \
  -f compose.containerized.yml \     # access-svc·document-svc
  up -d --build
# document-svc 다중 인스턴스: --scale document-svc=2 (published 포트 제거 + LB)
```

## K8s (kind 로컬 → EKS)

`k8s/` 매니페스트: Strimzi Kafka(`ai.ingest.command` 12 partitions) + KEDA(ingest-worker lag 기반 min1/max4) + 전 서비스 Deployment/Service/ConfigMap/Secret/NetworkPolicy + 상태 계층. 절차는 `k8s/README.md`.

- access-svc: NodePort 30081, document-svc: NodePort 30080
- ingest-worker·pipeline·converter: ClusterIP (외부 미노출, NetworkPolicy)

## AWS 매핑 (코드 변경 0 — env만 교체)

| 로컬 | AWS |
|---|---|
| kind | Amazon EKS |
| Strimzi Kafka | Amazon MSK |
| postgres 컨테이너 | Amazon RDS for PostgreSQL |
| redis 컨테이너 | ElastiCache |
| minio | S3 |
| 이미지 | ECR |
| Secret(YAML) | Secrets Manager |
| frontend | Vercel |

라우팅: ALB 경로 규칙이 next.config rewrite와 동일 — `/api/auth/*`·`/api/workspaces` → access-svc, 그 외 → document-svc.

## 배포 순서 주의

1. document-svc 먼저(Flyway가 스키마 생성) → access-svc(스키마 검증만)
2. 시크릿: `JWT_SECRET`·`INTERNAL_CALLBACK_TOKEN`은 두 앱 값이 반드시 동일(JWT 상호 검증·내부 API 인증)
3. OAuth redirect_uri는 access-svc 오리진 기준 — provider 콘솔 등록 URI를 access 오리진으로 갱신 필요
