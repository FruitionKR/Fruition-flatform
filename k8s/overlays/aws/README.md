# AWS(EKS) overlay


`k8s/base`(앱 + Strimzi Kafka)를 그대로 쓰고 상태 계층만 관리형으로 바꾼다:
postgres → RDS, redis → ElastiCache, minio → S3, secret.yaml → Secrets Manager(ExternalSecret).

전제: 승인된 IaC 적용과 scripts/aws-platform-up.sh의 고정 버전 addon·k8s/platform/aws 설치. [현행 플랫폼/앱 운영 절차](../../../docs/script.md#aws-iac플랫폼-운영-절차)를 따른다.

## 렌더 입력 출처

입력 예시는 [deploy-config.example.json](./deploy-config.example.json)이다. 배포 시 저장소 밖으로 복사해 채우며, placeholder가 남아 있으면 렌더가 실패한다. 준비 단계에서는 [로컬 검증과 입력 준비](../../../docs/script.md#배포-준비까지만-수행하는-경우)까지만 수행한다.

실제 환경값은 Git에 커밋하지 않는다. 로컬 준비 파일 `k8s/overlays/aws/deploy-config.feedback.json`은 `.gitignore`로 제외하며, 저장소에는 `deploy-config.example.json`만 추적한다. 새 checkout에서는 예시를 로컬 준비 파일 또는 저장소 밖 파일로 복사한다. 로컬 파일은 Git으로 백업되지 않으므로 필요한 경우 접근 제한된 별도 위치에 보관한다. ARN 기록만으로 인증서 `Issued` 상태나 ALB 연결이 확인된 것은 아니다.

준비 파일에 계정·도메인·ACM ARN, Terraform output의 RDS·Redis·S3·서비스별 storage role·네트워크 값과 실제 Vercel production 호스트를 채운다. `smtp_port=587`은 기존 STARTTLS 기본값이며 실제 SMTP 설정과 맞춰 확인한다. placeholder가 남아 있으면 기존 검증기가 배포 전에 중단한다. 비밀번호와 webhook URL은 이 JSON에 넣지 않는다.

ALB 생성 후 DNS의 `api`와 `access` CNAME을 ALB DNS 이름으로 연결한다. 같은 이름의 A/AAAA가 있다면 CNAME과 충돌하지 않도록 정리한다. ACM 검증용 밑줄 CNAME 두 개는 갱신을 위해 유지한다. 프론트엔드에는 `NEXT_PUBLIC_BACKEND_URL=https://api.<domain>`, `NEXT_PUBLIC_ACCESS_URL=https://access.<domain>`을 설정하고 로그인·업로드·AI 스트리밍을 검증한다.

## 설정 완료 후 GitHub Environment로 이전

1. 로컬 JSON의 모든 placeholder를 채우고 기존 `scripts/aws_deploy.py render --config <로컬-파일> --sha <실제-release-SHA>`로 검증한다. 렌더는 AWS를 변경하지 않으며 출력에도 환경 정보가 있으므로 공개 artifact로 올리지 않는다.
2. platform 저장소의 Settings → Environments에서 `feedback`을 생성하거나 선택한다. 환경명은 workflow와 OIDC trust policy의 `feedback`과 같아야 한다.
3. 해당 환경의 **Environment variables**에 `AWS_DEPLOY_CONFIG_JSON`을 만들고 완성된 JSON 전체를 값으로 저장한다. `AWS_DEPLOY_ROLE_ARN`에는 Terraform의 `github_deploy_role_arn` output을 저장한다. 일반 repository variable 대신 이 환경에 설정한다.
4. 사용할 GitHub 플랜에서 제공하는 배포 승인·브랜치 제한을 설정하고, `feedback` 환경의 OIDC 권한 및 전용 runner 준비를 확인한다. 앱 비밀번호·API 키·Discord webhook은 AWS Secrets Manager에서 관리한다. Environment Variables는 비밀값 저장소가 아니다.
5. 기존 `.github/workflows/deploy.yml`은 `environment: feedback`과 `vars.AWS_DEPLOY_CONFIG_JSON`/`vars.AWS_DEPLOY_ROLE_ARN`을 이미 사용한다. 배포 시 환경값으로 runner 임시 파일을 만들기 때문에 로컬 준비 파일을 커밋하거나 workflow에 실제 값을 하드코딩할 필요가 없다.

현재는 로컬 준비만 수행하며, GitHub Environment 생성·변수 등록·배포 실행은 실제 설정이 완료된 뒤 진행한다.

| 위치 | 값 | 출처 |
|---|---|---|
| `kustomization.yaml` images | `REPLACE_ME_ACCOUNT_ID` | AWS 계정 ID (`terraform output ecr_repository_urls`) |
| `kustomization.yaml` patches | `REPLACE_ME_CORE_RDS_ENDPOINT` | `terraform output core_rds_endpoint` |
| `kustomization.yaml` patches | `REPLACE_ME_ACCESS_RDS_ENDPOINT` | `terraform output access_rds_endpoint` |
| `configmap-aws.yaml` | `REPLACE_ME_REDIS_ENDPOINT` | `terraform output redis_endpoint` |
| `configmap-aws.yaml` | `REPLACE_ME_S3_BUCKET` | `terraform output s3_bucket` |
| `configmap-aws.yaml` | `REPLACE_ME_APP_DOMAIN` | Vercel production 도메인 |
| `ingress.yaml` | `REPLACE_ME_WAF_ACL_ARN` | `terraform output -raw waf_acl_arn` (필수, 서울 regional ACL) |
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

비용 보호 WAF는 Ingress 배포 후 실제 ALB 연결까지 확인해야 한다. 임계값·긴급 차단·영향은 [비용 보호 운영](../../../docs/aws-deployment-costs.md#추가한-비용-보호-설정과-적용-방법)을 따른다.

## 보안·순차 배포 보완

API 3종은 각 2개 Pod, PDB·분산·ALB readiness gate를 사용합니다. Kafka는 mTLS 9093과 역할별 KafkaUser ACL을 사용하므로 수정된 AI 이미지를 먼저 게시해야 합니다. 최초 bootstrap, 검증 계정, 릴리스 검토 파일, rollback 제한과 인증서 갱신 순서는 [유지보수 문서](../../../docs/aws-maintenance.md)를 따릅니다.
