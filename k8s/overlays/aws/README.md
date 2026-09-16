# AWS(EKS) overlay


`k8s/base`(앱 + Strimzi Kafka)를 그대로 쓰고 상태 계층만 관리형으로 바꾼다:
postgres → RDS, redis → ElastiCache, minio → S3, secret.yaml → Secrets Manager(ExternalSecret).

전제: 승인된 IaC 적용과 scripts/aws-platform-up.sh의 고정 버전 addon·k8s/platform/aws 설치. [현행 플랫폼/앱 운영 절차](../../../docs/script.md#aws-iac플랫폼-운영-절차)를 따른다.

## 렌더 입력 출처

입력 예시는 [deploy-config.example.json](./deploy-config.example.json)이다. 배포 시 저장소 밖으로 복사해 채우며, placeholder가 남아 있으면 렌더가 실패한다. 준비 단계에서는 [로컬 검증과 입력 준비](../../../docs/script.md#배포-준비까지만-수행하는-경우)까지만 수행한다.

| 위치 | 값 | 출처 |
|---|---|---|
| `kustomization.yaml` images | `REPLACE_ME_ACCOUNT_ID` | AWS 계정 ID (`terraform output ecr_repository_urls`) |
| `kustomization.yaml` patches | `REPLACE_ME_CORE_RDS_ENDPOINT` | `terraform output core_rds_endpoint` |
| `kustomization.yaml` patches | `REPLACE_ME_ACCESS_RDS_ENDPOINT` | `terraform output access_rds_endpoint` |
| `configmap-aws.yaml` | `REPLACE_ME_REDIS_ENDPOINT` | `terraform output redis_endpoint` |
| `configmap-aws.yaml` | `REPLACE_ME_S3_BUCKET` | `terraform output s3_bucket` |
| `configmap-aws.yaml` | `REPLACE_ME_APP_DOMAIN` | Vercel production 도메인 |
| `ingress.yaml` | `REPLACE_ME_ACM_CERT_ARN` | ACM 인증서 ARN |
| `ingress.yaml` | `REPLACE_ME_DOMAIN` | API 도메인 (api.·access. 붙는 zone) |

## 배포

수동 검증:

```bash
kubectl kustomize k8s/overlays/aws   # 렌더 확인
# 전체 리소스 일괄 apply는 migration 선행을 보장하지 않는다.
# docs/script.md의 AWS 서비스 자격증명과 migration 실행 계약대로 단계별 적용한다.
```

실제 입력 치환과 순차 배포는 scripts/aws_deploy.py를 사용한다. 원본 파일을 수동 치환하지 않는다. [현행 배포 절차](../../../docs/script.md#aws-순차-배포와-동일-스키마-sha-복구)의 JSON 입력과 계정·context·플랫폼 읽기 확인 → 앱 Secret → DB 사전검증 → migration → 전체 rollout → smoke gate를 따른다. 실제 AWS 검증은 별도다.

## 로컬(kind)과 차이

| 항목 | kind (base + -f 개별 적용) | AWS overlay |
|---|---|---|
| postgres·redis·minio | pod (`base/*.yaml`) | RDS·ElastiCache·S3 |
| secret | 자기 서비스 키만 선택; MFA는 별도 Secret | 서비스별 ExternalSecret ← Secrets Manager `fruition/app` |
| migration | 자기 서비스 startup migration | 별도 migration Job 3개, runtime에는 runtime 자격증명만 |
| 노출 | NodePort 30080/30081 | ALB Ingress (host 기반: api.→document, access.→access) |
| 이미지 | 로컬 빌드 + `imagePullPolicy: Never` | ECR + 커밋 SHA 태그 |
| Kafka | Strimzi broker 1 | 동일 (§8.3 — MSK 아님) |

## 알려진 제약

- 실행 로그는 S3 `pipeline-runs/{run_id}/pipeline.log`, 상태와 manifest는 ai_db에 저장한다. API·ingest는 독립 `emptyDir` scratch를 사용하며 공유 PVC·same-node affinity가 없다.
- AI worker와 converter는 AI Worker Spot node group의 label/taint에 맞춰 배치한다. node group은 0대에서 Cluster Autoscaler로 확장하며 실제 scale-from-zero·Spot 중단 복구는 AWS에서 검증해야 한다.
- Strimzi broker 1대 — AZ 장애 시 중단 허용, 복구는 operation 재발행 절차(§8.3).


AWS overlay는 서비스별 Redis ACL 비밀번호·TLS, Document/AI IRSA, 앱/Job NetworkPolicy를 포함한다. `storage_role_arns`와 `network_deploy_inputs` Terraform output을 배포 JSON에 반영한다. SMTP port는 JSON에서 ConfigMap과 정책으로 동일하게 렌더된다. DB 사전검증 전에 네트워크 정책을 적용한다. 구체적인 prefix·metadata 공유 예외와 실제 AWS 검증은 [아키텍처](../../../docs/architecture.md#aws-저장소통신-권한), [실행 절차](../../../docs/script.md#aws-저장소-iamredis-acl네트워크-검증)를 따른다.

앱 deployer는 namespace·StorageClass·ClusterSecretStore·RBAC를 적용하지 않는다. EKS fruition:deployers 그룹으로 fruition namespace의 허용된 리소스만 변경한다. ExternalSecret API는 v1, AWS Kafka는 4.3.0과 암호화 gp3 StorageClass를 사용한다. CRD/controller의 실제 동작과 server-side dry-run은 별도 AWS gate다.
