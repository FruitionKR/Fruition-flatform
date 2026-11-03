# 운영 설정값 참조

운영 중인 Fruition 서비스의 설정값을 한곳에 모은 문서입니다. 사양, 옵션의 유무, 환경 변수, 비밀값의 이름, 경보 기준, 배포 규칙을 담습니다. 절차는 각 문서에 있으니 여기서는 값과 근거만 적고 링크를 겁니다.

| 항목 | 값 |
|---|---|
| 기준 시각 | 2026-11-03 15:40 KST 전후 (AWS 조회 시각) |
| 플랫폼 기준 커밋 | `Fruition-flatform` origin/main `0607f11` |
| 서비스 기준 커밋 | access `914319d`, document `d40eadf`, ai `ad0f2c7`, frontend `678c5b6` (모두 origin/main) |
| 운영 중 이미지 묶음 | `b7f01174428025f2f33e0eabb3f177532e5b7701` (2026-11-03 06:03 UTC 배포 성공). 위 서비스 커밋 4개와 같습니다 |
| dev 브랜치 | document·ai 모두 origin/dev에 main보다 앞선 커밋이 없습니다. 아직 반영 안 된 작업은 열린 PR이나 로컬 브랜치에만 있습니다(각 절에 표시) |

> **비밀값 규칙.** 이 저장소는 공개 저장소입니다. 비밀번호, API 키, 토큰, 개인 키, 웹훅 주소, 계정 정보가 들어간 DB 접속 문자열은 이 문서에 절대 적지 않습니다. 비밀값은 **이름, JSON 키, 쓰는 곳, 교체 방법**만 적습니다. 도메인, 저장 버킷 이름의 무작위 접미사, 운영자 IAM 사용자 이름도 적지 않습니다. 각각 `app_domain`, `fruition-storage-<hex>`, `human_operator_user_name`(tfvars)으로 표시합니다.

**표기 방법**

- **근거**: `파일:줄`은 플랫폼 저장소 기준입니다. 서비스 저장소는 `access:`, `document:`, `ai:`, `frontend:`를 붙입니다. `AWS`는 기준 시각에 AWS API로 직접 조회한 값입니다.
- **기본값과 운영값**: 코드나 Terraform의 기본값과 실제 운영값이 다를 때만 둘 다 적습니다.
- **⚠ 표시**: 코드와 실제 운영이 다르거나 확인이 필요한 항목입니다. [9. 불일치·확인 필요 목록](#9-불일치확인-필요-목록)에 한 번에 모았습니다.

**다시 갱신하는 방법**

1. 기준 커밋을 정합니다. `git fetch`한 뒤 각 저장소의 origin/main SHA를 위 표에 적습니다.
2. 매니페스트를 다시 그립니다. `kubectl kustomize k8s/overlays/aws`로 최종 Deployment, ConfigMap, ExternalSecret, HPA, ScaledObject를 확인합니다. `REPLACE_ME_*` 자리는 배포 때 `AWS_DEPLOY_CONFIG_JSON`(GitHub Environment 변수) 값으로 바뀝니다.
3. AWS 값은 조회 명령만 씁니다. `aws eks describe-cluster/describe-nodegroup`, `aws rds describe-db-instances`, `aws elasticache describe-replication-groups`, `aws wafv2 get-web-acl`, `aws cloudwatch describe-alarms`, `aws logs describe-log-groups`, `aws secretsmanager list-secrets/describe-secret`, `aws budgets describe-budgets`를 씁니다. **`get-secret-value`는 쓰지 않습니다.**
4. 바뀐 값만 고치고 기준 시각과 커밋을 바꿉니다. 비밀값 검사(문서 끝 [갱신 점검](#갱신-점검))를 돌린 뒤 PR을 올립니다.

---

## 1. 환경 한눈에

### 1.1 계정·네트워크

| 항목 | 값 | 근거 |
|---|---|---|
| AWS 계정 / 리전 | `273366117740` / `ap-northeast-2` (서울) | `infra/terraform/variables.tf:11`, AWS |
| 환경 이름 | `feedback` (GitHub Environment, 경보 차원 `Environment=feedback`) | `variables.tf:43` |
| VPC | `fruition-vpc`, `10.0.0.0/16` | `vpc.tf:10-24`, `variables.tf:21` |
| 가용 영역 | 2a, 2b 두 곳 | `vpc.tf:7` |
| 공개 서브넷 (ALB) | 2a `10.0.0.0/20`, 2b `10.0.16.0/20` | `vpc.tf:18`, AWS |
| 사설 서브넷 (EKS·RDS·Redis·runner) | 2a `10.0.128.0/20`, 2b `10.0.144.0/20` | `vpc.tf:19`, AWS |
| NAT Gateway | 1개 (2a, `single_nat_gateway=true`) | `vpc.tf:21-22`, AWS |
| 공인 IPv4 | 3개: NAT 1개 + ALB 네트워크 인터페이스 2개 | AWS `describe-addresses` |
| S3 Gateway endpoint | 있음. 사설 라우팅 테이블에 연결해 S3 트래픽이 NAT를 거치지 않습니다 | `vpc.tf:39-45` |
| VPC Flow Logs | S3 직접 전송, `ALL`, 집계 60초, 시간별 파티션, 14일 뒤 삭제. 예전 CloudWatch 그룹 `/aws/vpc-flow-log/<vpc-id>`는 14일 보관으로 남아 있습니다 | `vpc-flow-logs.tf:72-104,121-127`, AWS |

### 1.2 EKS

| 항목 | 값 | 근거 |
|---|---|---|
| 클러스터 | `fruition-eks`, Kubernetes **1.35**, 플랫폼 `eks.27` | `eks.tf:7-8`, `variables.tf:27`, AWS |
| 지원 정책 | **EXTENDED**. 1.35 표준 지원은 **2027-03-27**에 끝납니다. 그 전에 올리지 않으면 control plane 요금이 월 약 $73에서 약 $438로 오릅니다 | AWS, [aws-deployment-costs.md](aws-deployment-costs.md) |
| API 엔드포인트 | 사설만 (`endpointPublicAccess=false`). 배포 runner 보안 그룹만 443으로 접근합니다 | `eks.tf:14-30`, AWS |
| 인증 모드 | `API_AND_CONFIG_MAP`. access entry: `github_deploy` → `fruition:deployers`, `runner_operations` → `fruition:operators`, `human_admin` → 클러스터 관리자 | `eks.tf:138-161`, `human-access.tf:44-58` |
| control plane 로그 | `api`, `audit`, `authenticator` 켜짐. `controllerManager`, `scheduler` 꺼짐. 그룹 `/aws/eks/fruition-eks/cluster` 14일 | `eks.tf:9`, AWS |
| 애드온 (운영 버전) | coredns `v1.13.2-eksbuild.24`, kube-proxy `v1.35.3-eksbuild.29`, vpc-cni `v1.22.4-eksbuild.3` (NetworkPolicy 켬), aws-ebs-csi-driver `v1.66.0-eksbuild.1`, metrics-server `v0.9.0-eksbuild.11`, amazon-cloudwatch-observability `v6.6.0-eksbuild.1` | `eks.tf:171-201`, `observability.tf:2-5`, AWS |
| EBS CSI 설정 | provisioner·attacher·resizer lease 60/40/10초, snapshotter 끔. **운영에 반영됨** | `eks.tf:181-189`, AWS `describe-addon` |
| kubelet 이미지 정리 | 디스크 70%에서 시작, 60%까지 정리, 최대 24시간 | `eks.tf:71-86` |
| 노드 루트 디스크 | 30GiB gp3, 암호화 (두 노드 그룹 모두) | `eks.tf:58-68`, AWS 시작 템플릿 |
| IMDS | v2 필수, hop limit 2 | AWS 시작 템플릿 |

**노드 그룹**

| 그룹 | 인스턴스 | 용량 | 최소/희망/최대 (코드) | 운영 희망 수 | 기타 | 근거 |
|---|---|---|---|---|---|---|
| `general` | `t3.large` (2 vCPU, 8GiB) | ON_DEMAND | 2 / 2 / 5 | **3** (실행 중 2대 확인) | 코드는 CPU credit `standard`, 실제 인스턴스는 **`unlimited`** ⚠ | `eks.tf:91-100`, AWS |
| `ai_worker` | `m5.xlarge`, `m5d.xlarge`, `m6i.xlarge`, `m7i.xlarge` (4 vCPU, 16GiB) | SPOT | 0 / 0 / 4 | **1** (m6i.xlarge 1대) | label `fruition.io/node-role=ai-worker`, taint `fruition.io/ai-worker=true:NoSchedule` | `eks.tf:101-122`, AWS |
| Fargate `frontend` | Pod당 Fargate | - | - | frontend Pod 2개 | namespace `fruition`, label `app=frontend` | `eks.tf:127-135` |

- 희망 수는 Cluster Autoscaler와 절전 Lambda가 바꿉니다. Terraform 값은 처음 만들 때만 씁니다.
- 노드 AMI 릴리스가 그룹마다 다릅니다(general `1.35.7-20260911`, ai_worker `1.35.8-20260930`).

**클러스터 안 플랫폼 구성요소** (helm, `scripts/aws-platform-up.sh:48-82`)

| 구성요소 | 차트 버전 | 주요 설정 |
|---|---|---|
| AWS Load Balancer Controller | 3.5.0 | `podMutatorWebhookConfig.failurePolicy=Fail`, IRSA `fruition-alb-controller` |
| External Secrets | 2.9.0 | IRSA `fruition-external-secrets` |
| Cluster Autoscaler | 9.59.0 (이미지 v1.35.0) | `scale-down-utilization-threshold=0.7`, lease 60/40/10초 |
| Strimzi | 1.1.0 | `fullReconciliationIntervalMs=600000`, lease 60000/40000/10000ms |
| KEDA | 2.20.2 | operator lease 60/40/10초, metrics adapter 권한 캐시 60초 |

> ⚠ Strimzi·Cluster Autoscaler·KEDA의 lease와 캐시 설정은 2026-11-02 감사 로그 절감용으로 추가됐습니다. `aws-platform-up.sh`를 다시 실행해야 반영됩니다. EKS API가 사설이라 이 문서 작성 때 실제 helm 값은 확인하지 못했습니다. [aws-deployment-costs.md](aws-deployment-costs.md)의 "EKS 감사 로그 발생량 줄이기" 절을 봅니다.

### 1.3 RDS (PostgreSQL)

| 항목 | access (`fruition-access-postgres`) | core (`fruition-core-postgres`) | 근거 |
|---|---|---|---|
| 담는 DB | `access_db` | `core_db` + `ai_db` | `rds.tf:1-6` |
| 클래스 | `db.t4g.micro` (1GiB) | `db.t4g.small` (2GiB) | `rds.tf:84,120`, AWS |
| 엔진 | PostgreSQL 16 (운영 `16.13`, 자동 minor 업그레이드 켬) | 같음 | `rds.tf:81-82`, AWS |
| Multi-AZ | 아니오 (2b) | 아니오 (2b) | `rds.tf:103,135`, AWS |
| 저장소 | 30GiB gp3, 3000 IOPS, 125MB/s, 암호화, 자동 확장 없음 | 같음 | `rds.tf:88-90`, AWS |
| 백업 보관 | 7일 | 7일 | `rds.tf:106,138` |
| 백업 시간 (UTC) | 16:07-16:37 (KST 01:07-01:37) | 16:22-16:52 (KST 01:22-01:52) | AWS |
| 유지 관리 시간 (UTC) | 수 15:32-16:02 (KST 목 00:32-01:02) | 월 13:07-13:37 (KST 월 22:07-22:37) | AWS |
| 삭제 보호 | 켬 | 켬 | `rds.tf:107,139` |
| 최종 스냅샷 | `fruition-access-postgres-final` | `fruition-core-postgres-final` | `rds.tf:108-109,140-141` |
| 파라미터 그룹 | `fruition-postgres16`. 직접 넣은 값은 `rds.force_ssl=1`. `max_connections`는 엔진 기본식 `LEAST({DBInstanceClassMemory/9531392},5000)` (micro 약 80) | 같음 | `rds.tf:38-47`, AWS |
| CA | `rds-ca-rsa2048-g1`. 앱은 `verify-full` + `/etc/rds-ca/root.crt` | 같음 | `rds.tf:98`, `configmap-aws.yaml:27-30` |
| 관리자 비밀번호 | RDS가 관리하는 Secrets Manager 비밀값 (`rds!db-…`, 7일 자동 교체) | 같음 | `rds.tf:95`, AWS |
| 로그 | `postgresql`을 CloudWatch로 보냄, 14일 | 같음 | `rds.tf:67-71` |
| Performance Insights | 꺼짐 | 꺼짐 | `rds.tf:113,145` |
| 대기 중인 유지 관리 | `system-update` (OS 업데이트) | `system-update` | AWS |
| access 즉시 적용 변수 | `access_db_apply_immediately` 기본 `false` | - | `rds.tf:73-77` |

DB 계정: `access_runtime`/`access_migration`, `core_runtime`/`core_migration`, `ai_runtime`/`ai_migration`/`ai_converter` (`rds.tf:8-12`, `infra/postgres/init-db-isolation.sh`). runtime 계정은 DML만 하고 DDL은 migration 계정이 합니다.

### 1.4 ElastiCache (Redis)

| 항목 | 값 | 근거 |
|---|---|---|
| 복제 그룹 | `fruition-redis`, 노드 `fruition-redis-001` (2b) | `elasticache.tf:63-82`, AWS |
| 엔진 / 노드 | Redis 7.1 / `cache.t4g.micro` 1개 | 같음 |
| 자동 장애 조치 / Multi-AZ | 꺼짐 / 꺼짐 | `elasticache.tf:72-74` |
| 전송·저장 암호화 | TLS `required`, 저장 암호화 켬 | `elasticache.tf:76-78` |
| 인증 | AUTH 토큰 없음. 사용자 그룹 `fruition-services`의 ACL 사용자 `access`, `document`, `pipeline` (비밀번호 방식). `default` 사용자는 `off -@all` | `elasticache.tf:25-61`, AWS |
| 유지 관리 시간 (UTC) | 월 05:00-06:00 (KST 월 14:00-15:00) | AWS |
| 스냅샷 | 보관 0 (백업 없음). 시간대 01:00-02:00 | AWS |

ACL 허용 키 범위 (`elasticache.tf:26-29`):
- `access`: `auth:mfa:attempts:*`, `auth:email-availability:*`, `auth:email-verification-request:*` 등. 권한 projection은 삭제만 할 수 있습니다.
- `document`: `authz:role:*` (get/set), `query:*`와 `query-events` 채널 등.
- `pipeline`: `wiki:concept-index:*`의 get, setex, del만 할 수 있습니다.

### 1.5 Kafka (Strimzi, 클러스터 안)

| 항목 | 값 | 근거 |
|---|---|---|
| Kafka 버전 | 4.3.0 | `k8s/overlays/aws/kustomization.yaml` (Kafka patch) |
| 노드 풀 | `dual-role` 1개 (controller+broker), replicas 1 | `k8s/base/kafka.yaml` |
| 저장소 | JBOD, PVC 5Gi gp3, `deleteClaim: true` | `kafka.yaml:21`, overlay patch |
| JVM / 자원 | `-Xms512m -Xmx512m`, 요청 250m/768Mi, 메모리 한도 1536Mi | `kafka.yaml:26-29` |
| 리스너 | `tls` 9093, mTLS 인증, 내부 전용. 허용 Pod: document-svc, 각 worker, converter, edit-event-consumer, KEDA operator | `overlays/aws/kafka-security.yaml` |
| 권한 | `simple` ACL, KafkaUser 8개 (아래) | `overlays/aws/kafka-users.yaml` |
| 주요 설정 | `auto.create.topics.enable=false`, `default.replication.factor=1`, `min.insync.replicas=1`, **`offsets.retention.minutes=525600` (365일)**, offsets·transaction 복제 1 | `kafka.yaml:60` 부근 |
| 토픽 | `ai.ingest.command`, `ai.query.command`, `ai.agent.command`, `ai.maintenance.command`, `ai.convert.command`, `ai.task.event`, `document.edit.event`. 모두 파티션 12, 복제 1, `retention.ms=259200000` (3일) | `kafka.yaml:88-174` |

KafkaUser와 권한 (`kafka-users.yaml`):

| 사용자 | 읽기 | 쓰기 | 그룹 |
|---|---|---|---|
| `kafka-document` | `ai.task.event` | ingest·query·agent·maintenance·convert command, `document.edit.event` | `document-svc-ai-task-result` |
| `kafka-ingest-worker` | `ai.ingest.command` | `ai.task.event`, `ai.maintenance.command` | `ingest-worker` |
| `kafka-query-task-worker` | `ai.query.command` | `ai.task.event` | `query-task-worker` |
| `kafka-agent-task-worker` | `ai.agent.command` | `ai.task.event` | `agent-task-worker` |
| `kafka-maintenance-task-worker` | `ai.maintenance.command` | `ai.task.event` | `maintenance-task-worker` |
| `kafka-converter` | `ai.convert.command` | `ai.task.event` | `ai.convert.command-worker` |
| `kafka-edit-event-consumer` | `document.edit.event` | - | `derived-state-tracker` |
| `kafka-keda` | 명령 토픽 5개 Describe만 | - | worker 그룹 5개 Describe만 |

### 1.6 S3

| 버킷 | 용도 | 암호화 | 버전 관리 | 수명 주기 규칙 | 근거 |
|---|---|---|---|---|---|
| `fruition-storage-<hex>` | 문서 원본, 첨부, 위키, AI 파일, 회의 녹음 | SSE-KMS (`alias/fruition-storage`, 키 자동 교체, bucket key 켬) | 켬 | 미완료 multipart 7일 삭제. `tmp/` 7일. `tmp/convert/` 1일. `pipeline-runs/meeting-transcription/` 1일. `pipeline-runs/` 30일 (이전 버전 1일). 버킷 전체 이전 버전 30일, 만료된 delete marker 삭제 | `s3.tf:7-163`, AWS |
| `fruition-alb-access-logs-273366117740-ap-northeast-2` | ALB 접근 로그 (`alb/` 접두사) | SSE-S3 | 없음 | `alb/AWSLogs/` 30일, 미완료 업로드 7일. `evidence/`는 만료 대상이 아닙니다 | `alb-access-logs.tf:7-85`, AWS |
| `fruition-vpc-flow-logs-273366117740-ap-northeast-2` | VPC Flow Logs (`flow/`) | SSE-S3 | 없음 | `flow/AWSLogs/` 14일, 미완료 업로드 7일 | `vpc-flow-logs.tf:2-87`, AWS |
| `fruition-tfstate-273366117740-ap-northeast-2` | Terraform state | SSE-S3 | 켬 | 없음 | `infra/terraform-state-bootstrap/main.tf`, AWS |

- 모든 버킷은 공개 접근 차단 4개 항목을 켜고, TLS가 아닌 요청을 거부합니다.
- 저장 버킷 CORS는 `document_upload_allowed_origins`가 있을 때만 만듭니다. 허용 메서드는 PUT/GET/HEAD, 헤더는 `content-type`, `range`, 캐시 300초입니다 (`s3.tf:63-73`).
- 서비스별 S3 권한(IRSA)은 [4.3](#43-irsa와-iam-role)에 있습니다.

### 1.7 ECR

| 저장소 | 태그 | 푸시 때 스캔 | 수명 주기 | 이미지 수 (기준 시각) |
|---|---|---|---|---|
| `fruition-access-svc` | IMMUTABLE | 켬 | 최근 60개 보존 (`tagStatus=any`) | 62 |
| `fruition-document-svc` | IMMUTABLE | 켬 | 같음 | 79 |
| `fruition-pipeline` | IMMUTABLE | 켬 | 같음 | 60 |
| `fruition-converter` | IMMUTABLE | 켬 | 같음 | 54 |
| `fruition-frontend` | IMMUTABLE | 켬 | 같음 | 65 |

근거는 `ecr.tf:3-41`, AWS입니다. 60개를 넘는 수는 ECR 수명 주기가 비동기로 정리하기 때문일 수 있습니다(매일 1회 수준). 실행 중인 digest와 rollback 대상 digest가 이 60개 안에 있어야 재배포와 rollback 검증이 통과합니다.

### 1.8 ALB·Ingress

| 항목 | 값 | 근거 |
|---|---|---|
| ALB | `k8s-fruition-dfa6d0737e`, internet-facing, AWS Load Balancer Controller가 소유 (group `fruition`) | `k8s/overlays/aws/ingress.yaml:13-31`, AWS |
| 리스너 | 80 → 443 리다이렉트, 443 HTTPS | `ingress.yaml:17-18`, AWS |
| TLS 정책 | `ELBSecurityPolicy-TLS13-1-2-2021-06` (TLS 1.2 이상) | `ingress.yaml:20`, AWS |
| 속성 | 잘못된 헤더 버림, idle timeout **120초** (실시간 받아쓰기 WebSocket), 접근 로그 S3 `alb/` | `ingress.yaml:24` |
| 대상 | `target-type: ip`. 헬스 체크 `/actuator/health`, 포트 8082 (관리 포트) | `ingress.yaml:16,26-28` |
| 인증서 | ACM (`acm_cert_arn`, 배포 설정) | `ingress.yaml:25` |
| WAF 연결 | `fruition-cost-guard` | `ingress.yaml:14` |

경로 분기 (위에서부터 먼저 맞는 규칙). 호스트는 `app_domain` 하나에 화면과 API를 함께 둡니다.

| 경로 | 대상 |
|---|---|
| `/internal*`, `/swagger-ui*`, `/v3/api-docs*` | 고정 404 (`not-public`) |
| `/api/document-transport` | frontend:3000 |
| `/api/workspaces/*/documents/*`, `/folders/*`, `/ai-operation-logs/*` | document-svc:8080 |
| `/api/workspaces/*/restore`, `/icon`, `/icon/*`, `/members`, `/members/*`, `/invitations`, `/invitations/*` | access-svc:8081 |
| `/api/workspaces/*/*` | document-svc:8080 |
| `/api/workspaces`, `/api/workspaces/*`, `/api/auth/*`, `/api/invitations/*`, `/oauth2/*`, `/login/oauth2/*`, `/api/users/*/avatar` | access-svc:8081 |
| `/api/*` | document-svc:8080 |
| `/*` | frontend:3000 |

예전 호스트 `api.<domain>`(document-svc 전체)과 `access.<domain>`(access-svc 전체)도 같은 비공개 경로 404를 두고 남아 있습니다.

### 1.9 WAF (`fruition-cost-guard`, REGIONAL)

| 우선순위 | 규칙 | 동작 | 내용 |
|---|---|---|---|
| 0 | `emergency-block` | 차단 | **`waf_emergency_block=true`일 때만 생깁니다.** 운영에는 없습니다 (기본 `false`) |
| 1 | `document-content-contract` | Count | 문서 본문 API 계약 경로 표시 ([aws-waf-document-content.md](aws-waf-document-content.md)) |
| 2 | `not-public-paths` | 차단 | `/internal`, swagger, api-docs |
| 3 | `sensitive-file-paths` | 차단 | `.git`, `.env` 경로 조각 (`waf_sensitive_paths_block` 기본 `true`, `infra/waf/sensitive-paths.json`) |
| 10 | AWS IP Reputation | 관리형 | 그대로 |
| 11 | AWS Common Rule Set | 관리형 | `SizeRestrictions_BODY`, `GenericLFI_BODY`, `CrossSiteScripting_BODY`는 Count |
| 12 | AWS Known Bad Inputs | 관리형 | 그대로 |
| 13 | AWS SQLi | 관리형 | `SQLi_BODY`, `SQLiExtendedPatterns_BODY`는 Count |
| 20 | `document-content-body-guard` | 차단 | 본문 계약 경로에서 본문 규칙 적용 |
| 25 | `frontend-access-code` | 차단 | 접근 코드 쿠키 없는 `/api/*` 차단. 예외 경로 `^/api/(auth/\|invitations/\|workspaces$\|workspaces/[^/]+$)` |
| 30 | `per-source-ip` | 차단 | **IP당 5분 3,000건** (`/_next/static/` 제외, TCP 연결 IP 기준) |
| 40 | `all-api-requests` | 차단 | **전체 `/api/` 5분 6,000건** (모든 호스트 합계) |

근거: `infra/terraform/cost-guards.tf:4-38,57-80`, AWS `get-web-acl`. 기본 동작은 허용입니다. 로그는 `aws-waf-logs-fruition` (14일)에 남습니다. 한도를 바꿀 때는 `waf_requests_per_ip_5m`, `waf_requests_total_5m` 값을 바꾸고 Terraform plan/apply를 합니다. 긴급 차단은 `-var waf_emergency_block=true`로 적용합니다. 이 규칙은 공개 API HTTP 요청만 막습니다. 이미 쌓인 작업이나 고정 요금은 멈추지 않습니다.

### 1.10 배포 runner와 기타

| 항목 | 값 | 근거 |
|---|---|---|
| runner | `fruition-feedback-runner`, `t3.small` (CPU credit `standard`, 실제도 standard), Ubuntu 24.04, 사설 서브넷 2a, 공인 IP 없음, 30GiB gp3 암호화, IMDSv2 hop 1 | `runner.tf:92-143`, AWS |
| runner 접근 | SSM Session Manager만 씁니다(SSH 없음). GitHub self-hosted label `self-hosted, linux, x64, fruition-feedback` | `runner.tf:67-72`, `.github/workflows/deploy.yml:47` |
| 절전·기동 Lambda | `fruition-request-wake` (python3.12, 128MB, 55초, 동시 실행 1). 1분마다 실행되고, 화면의 `wake-requested` 이벤트로도 실행됩니다. 상태 테이블은 DynamoDB `fruition-request-wake` (온디맨드) | `request-wake.tf`, AWS, [aws-request-wake.md](aws-request-wake.md) |
| 알림 Lambda | `fruition-budget-discord` (python3.12, 128MB, 20초, 재시도 2회, 이벤트 최대 1시간). 실패하면 SQS `fruition-budget-alert-failures`로 갑니다 | `budgets.tf:124-169` |
| 자격 증명 점검 Lambda | `fruition-credential-guard` (python3.12, 128MB, 30초). EventBridge `fruition-credential-audit-daily`가 `rate(1 day)`로 실행합니다 | `credential-guard.tf:37-63`, AWS |

---

## 2. 서비스별 설정

### 2.1 워크로드 요약 (운영 매니페스트 기준)

모든 워크로드의 namespace는 `fruition`입니다. 숫자는 `kubectl kustomize k8s/overlays/aws`로 그린 최종 값입니다.

| 워크로드 | 이미지 (ECR) / 소스 저장소 | 복제 수·확장 | 요청 CPU/메모리 | 메모리 한도 | 배치 | 종료 유예 | ServiceAccount |
|---|---|---|---|---|---|---|---|
| access-svc | `fruition-access-svc` / Fruition-access | HPA 2~4, CPU 175% | 100m / 512Mi | 1024Mi | general | 60s | `fruition-access` |
| document-svc | `fruition-document-svc` / Fruition-document | HPA 2~4, CPU 200% | 150m / 1Gi | 2Gi | general | 60s | `fruition-document` |
| pipeline-api | `fruition-pipeline` / Fruition-ai | HPA 2~4, CPU 200% | 150m / 1Gi | 2Gi | general | 60s | `fruition-pipeline` |
| frontend | `fruition-frontend` / Fruition-frontend (`web/`) | 고정 2 | 250m / 768Mi | 768Mi | Fargate | 30s | `fruition-frontend` |
| pipeline-agent-worker | `fruition-pipeline` | 고정 1 | 50m / 256Mi | 1Gi | general | 900s | `fruition-pipeline` |
| edit-event-consumer | `fruition-pipeline` | 고정 1 | 50m / 128Mi | 512Mi | general | 기본 30s | `fruition-pipeline` |
| ingest-worker | `fruition-pipeline` | KEDA 0~4 | 1 / 2Gi | 4Gi | ai-worker | 900s | `fruition-pipeline` |
| query-task-worker | `fruition-pipeline` | KEDA 0~4 | 500m / 2560Mi | 3584Mi | ai-worker | 900s | `fruition-pipeline` |
| agent-task-worker | `fruition-pipeline` | KEDA 0~4 | 500m / 2560Mi | 3584Mi | ai-worker | 900s | `fruition-pipeline` |
| maintenance-task-worker | `fruition-pipeline` | KEDA 0~2 | 500m / 2560Mi (+ephemeral 2Gi) | 3584Mi | ai-worker | 1800s | `fruition-pipeline` |
| converter | `fruition-converter` / Fruition-ai (`converter/`) | KEDA 0~3 | 100m / 256Mi | 1Gi | ai-worker | 7800s | `fruition-converter` |
| embedding-server | `fruition-pipeline` | KEDA 0~1 | 500m / 3Gi | 4Gi | ai-worker | 기본 30s | `fruition-pipeline` |

- 근거: `k8s/overlays/aws/kustomization.yaml:105-400`, `api-autoscaling.yaml:33-109`, `api-availability.yaml`, `frontend.yaml:31-64`, `k8s/base/*.yaml`.
- base 값은 kind 개발용입니다. 운영에서는 overlay가 덮습니다. 예: access-svc 요청 CPU는 base 250m, 운영 100m입니다. document-svc는 base 250m/768Mi, 운영 150m/1Gi입니다.
- CPU 한도는 어느 워크로드에도 없습니다. 노드의 남는 CPU를 씁니다.
- API 3개와 frontend는 rolling update `maxSurge 1`, `maxUnavailable 0`, PDB `minAvailable 1` (`unhealthyPodEvictionPolicy: AlwaysAllow`)입니다 (`api-disruption-budgets.yaml`).
- query·agent worker에는 init container `wait-embedding-server`가 있습니다. embedding-server `/health`를 5초 간격으로 최대 180회 확인합니다 (`kustomization.yaml:270-291`).
- ai-worker 배치는 nodeSelector `fruition.io/node-role=ai-worker`와 toleration으로 합니다. pipeline-agent-worker와 edit-event-consumer는 상시 1개라 AI 노드가 0대로 내려갈 수 있도록 일반 노드에 둡니다.

**HPA 동작** (API 3개 같음, `api-autoscaling.yaml`): 확장은 30초 안정화 뒤 60초마다 최대 100%입니다. 축소는 300초 안정화 뒤 120초마다 1개씩입니다. 목표가 175~200%로 높은 이유는 요청 CPU를 실측에 맞춰 낮췄기 때문입니다. Pod당 약 300m에서 확장합니다.

**KEDA ScaledObject** (`k8s/base/keda-scaledobject.yaml`, TLS는 `overlays/aws/kafka-scalers-tls.yaml`)

| 대상 | 트리거 | lag 기준 | 최소/최대 | cooldown | 확장 동작 |
|---|---|---|---|---|---|
| ingest-worker | Kafka `ai.ingest.command` / `ingest-worker` | 5 | 0/4 | 600s | 120초 안정화, 60초마다 1개 / 축소 300초 |
| query-task-worker | `ai.query.command` / `query-task-worker` | 10 | 0/4 | 1800s | 같음 |
| agent-task-worker | `ai.agent.command` / `agent-task-worker` | 6 | 0/4 | 1800s | 같음 |
| maintenance-task-worker | `ai.maintenance.command` / `maintenance-task-worker` | 2 | 0/2 | 600s | 같음 |
| converter | `ai.convert.command` / `ai.convert.command-worker` | 1 | 0/3 | 600s | 같음 |
| embedding-server | `kubernetes-workload`: `app in (query-task-worker,agent-task-worker)` Pod 수, 값 1 | - | 0/1 | 300s | - |

Kafka 트리거는 모두 `limitToPartitionsWithLag=true`, `offsetResetPolicy=earliest`, TLS(`TriggerAuthentication kafka-tls`)를 씁니다.

**Probe**

| 워크로드 | startup | readiness | liveness |
|---|---|---|---|
| access-svc | `/actuator/health:8082`, 5s × 60, timeout 5s | 10s, timeout 5s | 15s, timeout 5s |
| document-svc | `/actuator/health:8082`, 5s × 60 | 10s | 15s |
| pipeline-api | - | `/health:8000`, 초기 5s, 10s | 초기 20s, 15s |
| embedding-server | `/health:8000`, 5s × 60 | 10s, timeout 5s | 15s, timeout 5s, 실패 6회 |
| frontend | - | `/healthz:3000`, 5s, timeout 3s | 15s, timeout 3s, 실패 4회 |
| pipeline-agent-worker | - | - | exec: PID 1이 `agent_worker.py`인지 확인, 30s, 초기 10s |

access-svc의 timeout 5초는 SMTP를 포함한 health가 1초를 넘을 수 있어서 둡니다. 운영에서는 `MANAGEMENT_HEALTH_MAIL_ENABLED=false`로 메일 health를 뺍니다 (`kustomization.yaml` 마지막 두 patch).

### 2.2 공통 ConfigMap `fruition-config` (운영 최종값)

base(`k8s/base/configmap.yaml`)에 AWS patch(`k8s/overlays/aws/configmap-aws.yaml`)를 합친 값입니다. `envFrom`으로 access-svc, document-svc, pipeline-api, 모든 worker, converter, edit-event-consumer, pipeline-agent-worker가 받습니다. embedding-server와 frontend는 받지 않습니다. Deployment에 직접 넣은 `env`가 같은 이름이면 그쪽이 이깁니다(2.3 참조).

| 이름 | 운영값 | base 값과 다르면 | 의미 / 쓰는 곳 | 근거 |
|---|---|---|---|---|
| `SPRING_PROFILES_ACTIVE` | `production` | base `local` | access·document 프로필. production은 Flyway 끔, Hikari 5/2, 필수 비밀값 검사 | `configmap-aws.yaml:9` |
| `AUTH_REFRESH_COOKIE_SECURE` | `true` | base `false` | access refresh 쿠키 Secure | `configmap-aws.yaml:10` |
| `REDIS_HOST` | Redis primary endpoint (배포 설정) | base `redis` | 전 서비스 | `configmap-aws.yaml:13` |
| `REDIS_PORT` | `6379` | - | | `configmap.yaml:33` |
| `REDIS_SSL` | `true` | - | | `configmap-aws.yaml:26` |
| `S3_ENDPOINT` | `https://s3.ap-northeast-2.amazonaws.com` | base MinIO | document, ai | `configmap-aws.yaml:14` |
| `S3_BUCKET` | `fruition-storage-<hex>` (배포 설정) | | | `configmap-aws.yaml:15` |
| `S3_CREDENTIALS_MODE` | `aws` (IRSA) | base `local` | | `configmap-aws.yaml:24` |
| `AWS_REGION` | `ap-northeast-2` | | | `configmap-aws.yaml:25` |
| `CORS_ALLOWED_ORIGINS` | `https://<app_domain>` | base localhost | access·document `/api/**` CORS | `configmap-aws.yaml:17` |
| `OAUTH_FRONTEND_REDIRECT_URI` | `https://<app_domain>/oauth/callback` | | access | `configmap-aws.yaml:18` |
| `WORKSPACE_INVITATION_ACCEPT_URL` | `https://<app_domain>/invitations` | | access (production은 https 필수) | `configmap-aws.yaml:19` |
| `SPRING_FLYWAY_ENABLED` | `false` | | 마이그레이션은 Job으로만 실행 | `configmap-aws.yaml:20` |
| `SPRING_MAIL_PORT` | `587` (배포 설정 `smtp_port`) | | access SMTP | `configmap-aws.yaml:31`, `variables.tf:131` |
| `SPRING_MAIL_PROPERTIES_MAIL_SMTP_AUTH` / `_STARTTLS_ENABLE` / `_STARTTLS_REQUIRED` | `true` / `true` / `true` | | access SMTP TLS | `configmap-aws.yaml:21-23` |
| `PGSSLMODE` / `PGSSLROOTCERT` | `verify-full` / `/etc/rds-ca/root.crt` | | 모든 DB 연결 | `configmap-aws.yaml:27-28` |
| `SPRING_DATASOURCE_HIKARI_DATA_SOURCE_PROPERTIES_SSLROOTCERT` | `/etc/rds-ca/root.crt` | | JDBC용 CA | `configmap-aws.yaml:30` |
| `AI_LIMIT_ENABLED` | **`false`** | base 없음 (코드 기본 `true`) | document AI 하루 토큰 한도 끔 | `configmap-aws.yaml:34` |
| `POSTGRES_HOST` | `postgresql` (Deployment별 env가 덮음) | | | `configmap.yaml:17` |
| `POSTGRES_PORT` | `5432` | | | `configmap.yaml:18` |
| `ACCESS_DB_NAME` / `ACCESS_DB_RUNTIME_USER` / `ACCESS_DB_MIGRATION_USER` | `access_db` / `access_runtime` / `access_migration` | | access | `configmap.yaml:20-22` |
| `CORE_DB_NAME` / `CORE_DB_RUNTIME_USER` / `CORE_DB_MIGRATION_USER` | `core_db` / `core_runtime` / `core_migration` | | document | `configmap.yaml:23-25` |
| `AI_DB_NAME` / `AI_DB_RUNTIME_USER` / `AI_DB_MIGRATION_USER` | `ai_db` / `ai_runtime` / `ai_migration` | | ai | `configmap.yaml:27-29` |
| `AI_DB_CONVERTER_ROLE` | `ai_converter` | | ai 마이그레이션이 converter 권한 부여 | `configmap.yaml:31` |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka-kafka-bootstrap:9092` | | Kafka를 쓰는 Deployment는 env로 `:9093` TLS로 덮습니다 | `configmap.yaml:34` |
| `INGEST_COMMAND_TOPIC` … `DOCUMENT_EDIT_EVENT_TOPIC` | `ai.ingest.command`, `ai.query.command`, `ai.agent.command`, `ai.maintenance.command`, `ai.convert.command`, `ai.task.event`, `document.edit.event` | | 토픽 이름 7개 | `configmap.yaml:35-41` |
| `PROCESSING_ENDPOINT` | `http://pipeline-api:8000/pipeline/runs` | | document → ai | `configmap.yaml:45` |
| `CHAT_PROCESSING_ENDPOINT` | `http://pipeline-api:8000/chat-wiki/runs` | | | `configmap.yaml:46` |
| `QUERY_ENDPOINT` | `http://pipeline-api:8000/query` | | | `configmap.yaml:47` |
| `AGENT_STATUS_ENDPOINT` / `AGENT_RUN_ENDPOINT` | `…/internal/agent/runs` / `…/agent/runs` | | | `configmap.yaml:48-49` |
| `SKILL_ENDPOINT` | `http://pipeline-api:8000/skills` | | | `configmap.yaml:50` |
| `WIKI_SCHEMA_ENDPOINT` / `WIKI_PAGE_ENDPOINT` / `WIKI_STATE_ENDPOINT` | `…/wiki-schema` / `…/wiki/pages` / `…/wiki` | | | `configmap.yaml:51-53` |
| `SPEECH_LIVE_ENDPOINT` | `ws://pipeline-api:8000/speech/transcriptions/live` | | | `configmap.yaml:55` |
| `SPEECH_TRANSCRIPTION_ENDPOINT` / `SPEECH_SYNTHESIS_ENDPOINT` | `…/speech/transcriptions` / `…/speech/synthesis` | | | `configmap.yaml:56-57` |
| `MEETING_NOTES_ENDPOINT` | `…/meeting-notes/preview` | | | `configmap.yaml:58` |
| `BILLING_ENFORCE` | **`false`** | | document 크레딧 강제 끔 | `configmap.yaml:61` |
| `MODEL_USAGE_ENDPOINT` / `MODEL_USAGE_CALLS_ENDPOINT` | `…/usage/models` / `…/internal/model-usage/calls` | | document 과금 수집 | `configmap.yaml:63-64` |
| `ACCESS_INTERNAL_BASE_URL` | `http://access-svc:8081` | | | `configmap.yaml:67` |
| `DOCUMENT_INTERNAL_BASE_URL` | `http://document-svc:8080` | | | `configmap.yaml:68` |
| `AI_INTERNAL_BASE_URL` | `http://pipeline-api:8000` | | access 개인정보 파기 호출 | `configmap.yaml:70` |
| `AI_PURGE_READ_TIMEOUT` | `120s` | | access → ai 파기 읽기 timeout | `configmap.yaml:71` |
| `LEGAL_CONSENT_REQUIRED` | **`false`** | 코드 기본 `true` | access 가입 약관 동의 필수 여부. 화면 `NEXT_PUBLIC_LEGAL_PAGES_ENABLED`와 맞춰야 합니다 | `configmap.yaml:77` |
| `LANGSMITH_TRACING` | `false` | | ai 추적 끔 | `configmap.yaml:79` |
| `LANGSMITH_PROJECT` | `local-pilot-dev` ⚠ | | 추적이 꺼져 있어 영향 없음 | `configmap.yaml:80` |
| `LANGSMITH_ENDPOINT` | `https://api.smith.langchain.com` | | | `configmap.yaml:81` |
| `QUERY_EMBEDDING_MODE` | `text-only` | 코드 기본 `bge-m3` | pipeline-api는 BM25만. 세 task worker는 env `bge-m3`로 덮습니다 | `configmap.yaml:82` |
| `EMBEDDING_TIMEOUT_SECONDS` | `10` | | 원격 임베딩 timeout | `configmap.yaml:83` |
| `QUERY_EVALUATOR_MODE` | `web` | | 답변 평가에 웹 검색 사용 | `configmap.yaml:84` |
| `QUERY_EVALUATOR_MAX_ATTEMPTS` | `2` | | | `configmap.yaml:85` |
| `QUERY_WEB_SEARCH_MAX_RESULTS` | `5` | | | `configmap.yaml:86` |
| `QUERY_WEB_SEARCH_TIMEOUT_SECONDS` | `10` | 코드 기본 `20` | | `configmap.yaml:87` |
| `QUERY_MIN_INTERNAL_RELEVANCE_SCORE` | `0.5` | | | `configmap.yaml:88` |
| `AGENT_SKILLS_ENABLED` | `true` | 코드 기본 `false` | Agent Skills 켬 | `configmap.yaml:89` |
| `JEV_ROUTING_ENABLED` / `JEV_EVIDENCE_ENABLED` / `JEV_CONCEPT_MERGE_ENABLED` | `false` / `false` / `false` | | Jev(TypeSafe) 기능 꺼짐 | `configmap.yaml:91-93` |
| `SKILL_API_ENABLED` | `true` | | Skill API 라우터 | `configmap.yaml:94` |
| `ANALYTICS_ENABLED` / `ANALYTICS_ENVIRONMENT` / `APP_VERSION` / `POSTHOG_HOST` / `POSTHOG_PROJECT_TOKEN` | ConfigMap에는 `false`/`local`/`local`/로컬 주소/빈 값. **각 Deployment env가 덮습니다** (2.3) | | | `configmap.yaml:10-14` |

### 2.3 Deployment별 환경 변수

공통 ConfigMap 외에 각 Deployment에 직접 넣는 값입니다. 출처는 `k8s/overlays/aws/workload-credentials.yaml`, `kafka-client-tls.yaml`, `analytics-runtime.yaml`, `kustomization.yaml`, `frontend.yaml`, `k8s/base/*.yaml`입니다. "비밀"은 Kubernetes Secret에서 오며 값은 [4장](#4-비밀값과-권한)의 Secrets Manager 키입니다.

**모든 앱 공통 분석 설정** (`analytics-runtime.yaml`, access·document·frontend·pipeline-api·pipeline-agent-worker·ingest/query/agent/maintenance worker·edit-event-consumer에 적용)

| 이름 | 값 |
|---|---|
| `ANALYTICS_ENABLED` | `false` (배포 설정 `analytics_enabled`) |
| `ANALYTICS_ENVIRONMENT` | `production` |
| `APP_VERSION` | 서비스 소스 SHA (배포 때 치환) |
| `POSTHOG_HOST` | `https://us.i.posthog.com` |
| `POSTHOG_PROJECT_TOKEN` | 비밀 `fruition-analytics` / `POSTHOG_PROJECT_TOKEN` (optional) |

**Kafka TLS 클라이언트** (`kafka-client-tls.yaml`, ingest/query/agent/maintenance worker·converter·edit-event-consumer)

| 이름 | 값 |
|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka-kafka-bootstrap.fruition.svc:9093` |
| `KAFKA_SECURITY_PROTOCOL` | `SSL` |
| `KAFKA_SSL_CAFILE` / `KAFKA_SSL_CERTFILE` / `KAFKA_SSL_KEYFILE` | `/etc/kafka/ca/ca.crt` / `/etc/kafka/client/user.crt` / `/etc/kafka/client/user.key` (Strimzi가 만든 Secret 마운트) |

**워크로드별**

| 워크로드 | 이름 | 값 / 출처 | 의미 |
|---|---|---|---|
| access-svc | `POSTGRES_HOST` | access RDS endpoint (배포 설정) | |
| | `MANAGEMENT_PORT` | `8082` | actuator 포트 (코드 기본 8083) |
| | `REDIS_USERNAME` | `access` | |
| | `SERVER_SHUTDOWN` / `SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE` | `graceful` / `40s` | |
| | `MANAGEMENT_HEALTH_MAIL_ENABLED` | `false` | 상태 검사가 SMTP 인증을 반복하지 않게 함 |
| | envFrom 비밀 `fruition-access` | `ACCESS_DB_RUNTIME_PASSWORD`, `INTERNAL_CALLBACK_TOKEN`, `MFA_ENCRYPTION_KEY`, `SPRING_MAIL_HOST`, `SPRING_MAIL_USERNAME`, `SPRING_MAIL_PASSWORD`, `MAIL_FROM`, `GOOGLE_CLIENT_ID/SECRET`, `NAVER_CLIENT_ID/SECRET`, `KAKAO_CLIENT_ID/SECRET`, `REDIS_PASSWORD`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, `JWT_KEY_ID`, `JWT_PREVIOUS_PUBLIC_KEY`, `JWT_PREVIOUS_KEY_ID` | |
| document-svc | `POSTGRES_HOST` | core RDS endpoint | |
| | `KAFKA_BOOTSTRAP_SERVERS` | `kafka-kafka-bootstrap.fruition.svc:9093` | |
| | `SPRING_KAFKA_SECURITY_PROTOCOL` | `SSL` | |
| | `SPRING_KAFKA_SSL_KEYSTORETYPE` / `…TRUSTSTORETYPE` | `PKCS12` / `PKCS12` | |
| | `SPRING_KAFKA_SSL_KEYSTORELOCATION` / `…TRUSTSTORELOCATION` | `file:/etc/kafka/client/user.p12` / `file:/etc/kafka/ca/ca.p12` | |
| | `SPRING_KAFKA_SSL_KEYSTOREPASSWORD` | 비밀 `kafka-document` / `user.password` (Strimzi 생성) | |
| | `SPRING_KAFKA_SSL_TRUSTSTOREPASSWORD` | 비밀 `kafka-cluster-ca-cert` / `ca.password` (Strimzi 생성) | |
| | `SERVER_SHUTDOWN` / `SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE` | `graceful` / `40s` | |
| | `MANAGEMENT_PORT` | `8082` | |
| | `REDIS_USERNAME` | `document` | |
| | envFrom 비밀 `fruition-document` | `CORE_DB_RUNTIME_PASSWORD`, `INTERNAL_CALLBACK_TOKEN`, `AGENT_INTERNAL_TOKEN`, `REDIS_PASSWORD`, `KOREAEXIM_AUTH_KEY`, `JWT_PUBLIC_KEY`, `JWT_KEY_ID`, `JWT_PREVIOUS_PUBLIC_KEY`, `JWT_PREVIOUS_KEY_ID` | |
| pipeline-api | `REDIS_USERNAME` | `pipeline` | |
| | envFrom 비밀 `fruition-pipeline` | `AI_DATABASE_URL`, `INTERNAL_CALLBACK_TOKEN`, `AGENT_INTERNAL_TOKEN`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `TYPESAFE_API_KEY`, `LANGSMITH_API_KEY`, `TAVILY_API_KEY`, `REDIS_PASSWORD` | |
| pipeline-agent-worker | `AGENT_BACKEND_URL` | `http://document-svc:8080` | |
| | `REDIS_USERNAME` | `pipeline` | |
| | envFrom 비밀 `fruition-pipeline` | 위와 같음 | |
| ingest-worker | `REDIS_USERNAME` + Kafka TLS + 비밀 `fruition-pipeline` | | consumer group 코드 기본 `ingest-worker` |
| query-task-worker | `AI_COMMAND_TOPIC` / `AI_COMMAND_CONSUMER_GROUP` / `AI_TASK_CONCURRENCY` | `ai.query.command` / `query-task-worker` / `8` | |
| | `QUERY_EMBEDDING_MODE` / `EMBEDDING_SERVICE_URL` | `bge-m3` / `http://embedding-server:8000` | 질의 임베딩을 embedding-server에 요청 |
| | `REDIS_USERNAME` + Kafka TLS + 비밀 `fruition-pipeline` | | |
| agent-task-worker | `AI_COMMAND_TOPIC` / `…_CONSUMER_GROUP` / `AI_TASK_CONCURRENCY` | `ai.agent.command` / `agent-task-worker` / `4` | |
| | `QUERY_EMBEDDING_MODE` / `EMBEDDING_SERVICE_URL` | `bge-m3` / `http://embedding-server:8000` | |
| maintenance-task-worker | `AI_COMMAND_TOPIC` / `…_CONSUMER_GROUP` / `AI_TASK_CONCURRENCY` | `ai.maintenance.command` / `maintenance-task-worker` / `1` | 회의 전사 마감 1500초라 종료 유예 1800초 |
| | `QUERY_EMBEDDING_MODE` | `bge-m3` (임베딩을 직접 만듦, 서버 미사용) | |
| edit-event-consumer | `REDIS_USERNAME` + Kafka TLS + 비밀 `fruition-pipeline` | | 그룹 코드 기본 `derived-state-tracker` |
| converter | Kafka TLS | | |
| | `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` | 비밀 `fruition-converter` | |
| | `AI_DATABASE_URL` | 비밀 `fruition-converter` (Secrets Manager 키 `AI_CONVERTER_DATABASE_URL`, 최소 권한 계정) | |
| | `PDF_DIAGNOSTIC_TIMEOUT_SECONDS` | `60` | |
| | (이미지) `RESTORATION_COMMAND` | `python -m app.modules.document_restoration.interfaces.cli` | `ai:converter/Dockerfile:32` |
| embedding-server | `INTERNAL_CALLBACK_TOKEN` | 비밀 `fruition-pipeline` | ConfigMap을 받지 않습니다 |
| frontend | `ACCESS_CODE` | 비밀 `fruition-frontend` | 접근 코드 문 |
| | `AWS_REGION` | `ap-northeast-2` | |
| | `REQUEST_WAKE_EVENT_SOURCE` / `REQUEST_WAKE_DETAIL_TYPE` / `REQUEST_WAKE_STATE_TABLE` | `fruition.frontend` / `wake-requested` / `fruition-request-wake` | 절전 기동 요청 |
| | `CSP_S3_ORIGIN` | `https://fruition-storage-<hex>.s3.ap-northeast-2.amazonaws.com` | CSP connect/media/frame |
| | (이미지) `NODE_ENV=production`, `SAME_ORIGIN_API=true`, `PORT=3000`, `HOSTNAME=0.0.0.0`, `NEXT_TELEMETRY_DISABLED=1` | `frontend:web/Dockerfile:10,17` | |

**마이그레이션 Job** (`k8s/overlays/aws/migration-jobs.yaml`, `backoffLimit 0`, `activeDeadlineSeconds 600`, 요청 100m/256Mi, 한도 1Gi)

| Job | 명령 | env | 비밀 |
|---|---|---|---|
| `access-migration` | `--migrate-only` | `PGSSLMODE=verify-full`, `PGSSLROOTCERT`, `POSTGRES_HOST`(access), `POSTGRES_PORT=5432`, `ACCESS_DB_NAME=access_db`, `ACCESS_DB_MIGRATION_USER=access_migration` | `fruition-access-migration` / `ACCESS_DB_MIGRATION_PASSWORD` |
| `document-migration` | `--migrate-only` | 같은 형태, `CORE_DB_NAME=core_db`, `CORE_DB_MIGRATION_USER=core_migration` | `fruition-document-migration` / `CORE_DB_MIGRATION_PASSWORD` |
| `ai-migration` | `python -m app.modules.wiki_ingestion.infrastructure.migrate_ai_schema` | `PGSSLMODE`, `PGSSLROOTCERT`, `AI_DB_CONVERTER_ROLE=ai_converter` | `fruition-ai-migration` / `AI_DB_MIGRATION_URL` |

### 2.4 access-svc 애플리케이션 설정 (Spring)

근거 접두사 `access:`는 `src/main/resources/application.properties`(AP), `application-production.properties`(PROD)입니다. 운영 프로필은 `production`입니다.

| 설정 | 환경 변수 | 기본값 | 운영값 | 근거 |
|---|---|---|---|---|
| 서버 포트 / 관리 포트 | `SERVER_PORT` / `MANAGEMENT_PORT` | 8081 / 8083 | 8081 / 8082 | AP:8,25 |
| actuator 노출 | - | `health,prometheus` | 같음 | AP:26 |
| Hikari 최대 / 최소 유휴 | - | 10 / 10 | **5 / 2** | PROD:5-6 |
| Flyway | `SPRING_FLYWAY_ENABLED` | 켬 | 끔 (Job으로만) | AP:54, PROD:2 |
| Flyway 잠금 | - | `postgresql.transactional-lock=false` | 같음 | AP:59 |
| JPA | - | `ddl-auto=validate` | 같음 | AP:49 |
| 세션 | - | JDBC (`spring_session`) | 같음 | AP:43-45 |
| access 토큰 TTL | `JWT_ACCESS_EXPIRATION_SECONDS` | 900 (15분) | 같음 | AP:78 |
| refresh 토큰 TTL | `JWT_REFRESH_EXPIRATION_SECONDS` | 1209600 (14일) | 같음 | AP:79 |
| JWT issuer / audience | `JWT_ISSUER` / `JWT_AUDIENCE` | `fruition-access` / `fruition-api` | 같음 | AP:80-81 |
| 서명 방식 | `JWT_SIGNING_MODE` | `rsa` | 같음 (production은 RSA 키 필수) | AP:219 |
| refresh 쿠키 | `AUTH_REFRESH_COOKIE_SECURE` | false | true. 이름 `fruition_refresh_token`, HttpOnly, SameSite=Strict, Path `/api/auth` | AP:83, `AuthController.java:737-745` |
| 신뢰 프록시 수 | `CLIENT_ADDRESS_TRUSTED_PROXY_COUNT` | 1 (ALB) | 같음 | AP:18 |
| multipart 파일 / 요청 | `MULTIPART_MAX_FILE_SIZE` / `MULTIPART_MAX_REQUEST_SIZE` | 2MB / 4MB (아이콘 실제 한도 1MB) | 같음 | AP:128-132 |
| 스케줄 스레드 | `TASK_SCHEDULING_POOL_SIZE` | 3 | 같음 | AP:63 |
| Redis timeout | `REDIS_CONNECT_TIMEOUT` / `REDIS_COMMAND_TIMEOUT` | 2s / 2s | 같음 | AP:89-90 |
| SMTP timeout | `MAIL_SMTP_CONNECTION_TIMEOUT_MS` 외 2개 | 5000ms | 같음 | AP:146-148 |
| 초대 유효 기간 | `WORKSPACE_INVITATION_TTL_SECONDS` | 604800 (7일) | 같음 | AP:143 |
| 약관 버전 | `LEGAL_TERMS_VERSION` / `LEGAL_PRIVACY_VERSION` | `2026-10-01` / `2026-10-01` | 같음 | AP:188-189 |
| AI 공급자 | - | `openai,gemini,claude` | 같음 | AP:69 |
| MFA issuer / 확인 대기 | `MFA_ISSUER` / `MFA_CHALLENGE_TTL_SECONDS` | `Fruition` / 300 | 같음 | AP:137-139 |

**로그인·메일·MFA 시도 한도** (Redis 고정 시간 창. 창이 끝나면 풀리며 별도 잠금은 없습니다)

| 한도 | 환경 변수 | 기본값 (운영 같음) | 근거 |
|---|---|---|---|
| 로그인 창 | `AUTH_LOGIN_WINDOW_SECONDS` | 300초 | AP:101 |
| 로그인 IP당 | `AUTH_LOGIN_IP_LIMIT` | 50회 | AP:102 |
| 로그인 계정+IP 실패 | `AUTH_LOGIN_ACCOUNT_FAILURE_LIMIT` | 10회 (성공 시 초기화) | AP:103 |
| 비밀번호 변경 실패 | `AUTH_PASSWORD_CHANGE_FAILURE_LIMIT` / `…_WINDOW_SECONDS` | 5회 / 300초 | AP:107-108 |
| 이메일 사용 가능 확인 | `AUTH_EMAIL_AVAILABILITY_IP_LIMIT` / `…_EMAIL_LIMIT` / `…_WINDOW_SECONDS` | IP 30회, 이메일 5회 / 60초 | AP:93-95 |
| MFA 코드 시도 | (고정) | 사용자당 300초에 5회 | `MfaAttemptLimiter.java:14-16` |
| 인증 코드 유효 | `AUTH_EMAIL_CODE_TTL_SECONDS` | 300초 | AP:111 |
| 인증 완료 토큰 | `AUTH_EMAIL_TOKEN_TTL_SECONDS` | 600초 | AP:112 |
| 재발송 대기 | `AUTH_EMAIL_RESEND_COOLDOWN_SECONDS` | 60초 | AP:113 |
| 하루 발송 | `AUTH_EMAIL_DAILY_LIMIT` | 5회 | AP:114 |
| 코드당 오답 | `AUTH_EMAIL_MAX_ATTEMPTS` | 5회 | AP:115 |
| OAuth 교환·연결 코드 | (고정) | 60초, 1회용. 가입 토큰 10분 | `OAuthExchangeCodeStore.java:26-32` |
| 비밀번호 규칙 | (고정) | 8~72자, BCrypt | `SignupRequest.java:17` |

**production 시작 검사** (`ProductionSettings.java:29-76`): 메일 host·username·password·from, MFA 키(32바이트), 초대 URL(https), JWT 개인·공개 키와 key id, refresh 쿠키 Secure, `INTERNAL_CALLBACK_TOKEN`이 비어 있거나 `REPLACE_ME`면 시작하지 않습니다.

**예약 작업** (모든 replica에서 돕니다. 분산 잠금 없음)

| 작업 | 주기 | 내용 |
|---|---|---|
| `DataPurgeRequestJob` | 60초 | 개인정보 파기 요청 재시도 |
| `ExpiredRecordCleanupJob` | 1일 | 인증 기록 7일, refresh 토큰 7일, 초대 30일, **워크스페이스 휴지통 30일**, 실패한 이메일 변경 알림 30일 지난 것 삭제 |
| `EmailChangeNotificationJob` | 10초 | 이메일 변경 알림 outbox. 최대 5회, 1분부터 두 배씩 대기 |

권한 역할은 워크스페이스 `OWNER`, `MEMBER`뿐이고 별도 운영자 역할은 없습니다.

### 2.5 document-svc 애플리케이션 설정 (Spring)

근거 접두사 `document:`는 `src/main/resources/application.properties`(AP), `application-production.properties`(PROD)입니다.

| 설정 | 환경 변수 | 기본값 | 운영값 | 근거 |
|---|---|---|---|---|
| Hikari 최대 / 최소 유휴 | - | 10 / 10 | **5 / 2** | PROD:5-6 |
| Flyway | - | 켬, `transactional-lock=false` | 끔 (Job으로만) | AP:64-69, PROD:2 |
| JPA | - | `validate`, 트랜잭션 뒤 연결 반환 | 같음 | AP:56-61 |
| multipart 파일 / 요청 | - | 50MB / 110MB | 같음 | AP:39-42 |
| 편집 잠금 TTL | `DOCUMENT_EDIT_LOCK_TTL_SECONDS` | 45초 | 같음 | AP:52 |
| 변환 배치 페이지 | `CONVERT_PAGES_PER_BATCH` | 10 | 같음 | AP:134 |
| 문서당 동시 변환 배치 | `CONVERT_MAX_IN_FLIGHT` | 3 | 같음 | AP:135 |
| AI 명령 outbox 주기 | `AI_COMMAND_OUTBOX_POLL_INTERVAL_MS` | 1000 | 같음 | AP:85 |
| 결과 consumer group | `AI_TASK_RESULT_CONSUMER_GROUP` | `document-svc-ai-task-result` | 같음 | AP:84 |
| pipeline 요청 timeout / 확인 주기 | `PIPELINE_RUN_TIMEOUT_SECONDS` / `PIPELINE_RUN_POLL_INTERVAL_MS` | 5초 / 3000ms | 같음 | AP:87-88 |
| 질의 timeout | `QUERY_TIMEOUT_SECONDS` | 30초 | 같음 | AP:92 |
| 에이전트 상태 timeout | `AGENT_STATUS_TIMEOUT_SECONDS` | 5초 | 같음 | AP:99 |
| Skill timeout | `SKILL_TIMEOUT_SECONDS` | 60초 | 같음 | AP:104 |
| 음성 전사 / 회의록 생성 / 합성 | `SPEECH_TRANSCRIPTION_TIMEOUT_SECONDS` / `MEETING_NOTES_GENERATION_TIMEOUT_MINUTES` / `SPEECH_SYNTHESIS_READ_TIMEOUT_SECONDS` | 150초 / 30분 / 30초 | 같음 | AP:110-115 |
| 위키 상태 timeout | `WIKI_STATE_TIMEOUT_SECONDS` | 30초 | 같음 | AP:129 |
| 사용량 수집 / 대조 / 재계산 | `USAGE_CHARGE_COLLECT_INTERVAL_MS` / `…RECONCILE…` / `…RECOMPUTE…` | 5초 / 1일 / 1시간 | 같음 | AP:172-174 |
| access JWT 검증 | `JWT_PUBLIC_KEY` 외 | production은 RSA 공개 키 필수 | 비밀 | AP:223-227 |
| Redis timeout | `REDIS_CONNECT_TIMEOUT` / `REDIS_COMMAND_TIMEOUT` | 2s / 2s | 같음 | AP:147-148 |
| AI 공급자 | - | `openai,gemini,claude` | 같음 | AP:93 |
| 복원 미리보기 서명 키 | `RESTORE_PREVIEW_TOKEN_SECRET` | 빈 값이면 Pod마다 무작위 키 | **설정 안 됨** ⚠ | AP:122 |
| 환율 API | `KOREAEXIM_ENDPOINT` / `KOREAEXIM_AUTH_KEY` | 수출입은행 URL / 비밀 (비면 갱신 건너뜀) | 비밀 있음 | AP:176-177 |

**업로드 한도**

| 한도 | 환경 변수 | 기본값 | 운영 | 근거 |
|---|---|---|---|---|
| 저장 공간 한도 스위치 | `UPLOAD_LIMITS_ENABLED` | `true` | 설정 없음 → **켜짐** | AP:45, `configmap-aws.yaml:33` 주석 |
| 사용자당 저장 공간 | `UPLOAD_USER_QUOTA_BYTES` | 5368709120 (**5GB**, 휴지통 포함, 문서·이미지·녹음 합계) | 기본값 | AP:49 |
| PDF 한 개 | `UPLOAD_MAX_PDF_BYTES` | 104857600 (**100MB**). 스위치를 꺼도 항상 적용 | 기본값 | AP:47 |
| 첨부 이미지 | (고정) | 파일당 10MB, 요청당 100MB, 20개, 16384px | | `DocumentAssetValidator.java:25-28` |
| 마크다운 본문 | (고정) | 5MB | | `DocumentEditingRules.java:23` |
| 회의 녹음 | (고정) | 500MB, 내려받기 URL 5분 | | `MeetingRecordingService.java:41-42` |
| 음성 파일 | (고정) | 24MB | | `SpeechController.java:33` |
| 직접 업로드 | (고정) | part URL 15분, 업로드 ticket 1일, part 크기 max(64MiB, 크기/10000), 요청당 URL 1~32개 | | `DirectMultipartUpload.java:59-100` |
| 원본 내려받기 URL | (고정) | 3600초 | | `DocumentService.java:1405` |

**AI 사용 한도와 과금** (금액 단위는 milli-KRW, 1000 = 1원)

| 설정 | 환경 변수 | 기본값 | 운영 | 근거 |
|---|---|---|---|---|
| AI 하루 토큰 한도 | `AI_LIMIT_ENABLED` | `true` | **`false`** | AP:205, `configmap-aws.yaml:34` |
| 하루 토큰 수 | `AI_LIMIT_DAILY_TOKENS` | 10,000,000 (사용자당, KST 자정 초기화, 넘으면 429 `AI_USAGE_LIMIT_EXCEEDED`) | 기본값. **이 코드는 운영 이미지 `b7f0117`에 들어가 있지만 스위치가 꺼져 있습니다** | AP:206, document PR #197 |
| 크레딧 강제 | `BILLING_ENFORCE` | `false` | `false` | AP:183, `configmap.yaml:61` |
| 결제 | `BILLING_PAYMENTS_ENABLED` | `false` (주문·웹훅 API 404) | 기본값 | AP:209 |
| 기본 예상치 | `BILLING_DEFAULT_ESTIMATE_KRW_MILLI` | 500000 | 기본값 | AP:184 |
| 종류별 예상치 | `BILLING_ESTIMATE_QUERY` 300000, `_AGENT` 500000, `_AGENT_RUN` 500000, `_DOCUMENT` 1000000, `_MEETING_NOTES` 500000, `_MEETING_TRANSCRIPTION` 1000000, `_MEETING_LIVE` 1000000, `_SPEECH_TRANSCRIPTION` 100000, `_SPEECH_SYNTHESIS` 500000 | | 기본값 | AP:185-194 |
| 최소 잔액 | `app.billing.minimum.<kind>` | 예상치의 10% | 기본값 | `CreditService.java:133` |
| 묵은 예약 해제 | `BILLING_STALE_RESERVATION_HOURS` / `BILLING_RELEASE_INTERVAL_MS` | 48시간 / 1시간 | 기본값 | AP:195-196 |
| ingest 뒤 보류 | `BILLING_POST_INGEST_HOLD_SECONDS` | 900 | 기본값 | AP:198 |
| 실시간 갱신 | `BILLING_LIVE_RENEW_SECONDS` | 60 | 기본값 | AP:200 |

**예약 작업** (모든 replica에서 돕니다)

| 작업 | 주기 | 비고 |
|---|---|---|
| `DocumentTrashPurgeWorker` | 1일 (시작 때 1회), **보관 30일**, 배치 100 | `app.document-trash.retention=30d` |
| `DocumentAssetCleanupWorker` | 1일 | |
| `DocumentOriginalHashWorker` | 30초 | |
| `DocumentPipelineRunReconciler` / `ChatWikiExportReconciler` | 3초 | |
| `AiCommandOutboxPublisher` / 편집 이벤트 outbox | 1초 | |
| `AiTaskCancellationService.resume` | 1초 | |
| `MeetingNotesService.sweepExpired` | 60초 | |
| `QueryEventBroker` SSE heartbeat | 15초 | |
| `SpeechAudioStore.cleanupExpired` | 1시간 | |
| `CreditService.releaseStale` | 1시간 | |
| `FxRateService.refresh` | cron `0 30 11 * * MON-FRI` (KST) | 유일한 cron |
| `UsageChargeService` | 수집 5초, 대조 1일, 재계산 1시간 | |
| `IdempotencyService.deleteExpired` | 1시간 | |
| `AnalyticsRelay` | 10초 | |

열린 PR document #198은 외부 호출 작업 4개(파이프라인·채팅 대조, 원본 해시, 환율)를 회차마다 한 Pod만 돌게 하고, 휴지통 인덱스(V94)를 추가합니다. **아직 병합 전**입니다.

### 2.6 pipeline (Fruition-ai) 설정

근거 접두사는 `ai:`이고 경로는 `pipeline/` 아래입니다. 프로세스별 운영 env는 2.3에 있습니다.

| 설정 | 환경 변수 | 기본값 | 운영 | 근거 |
|---|---|---|---|---|
| 허용 모델 | `AI_ALLOWED_LLM_MODELS` | 비면 공급자별 기본 모델 3개만. `*`는 검사 끔(시험용) | 설정 없음 → 기본 3개 | `app/core/llm_env.py:21,76-84` |
| 기본 모델 | (코드) | openai `gpt-6-luna`, gemini `gemini-3.5-flash-lite`, claude `claude-haiku-4-5-20251001` | 같음 | `llm_env.py:14-16` |
| 워크스페이스 공유 단계 모델 | (코드) | ingest·lint·Skill·회의록·변환 보정은 openai·gemini만. 범위 밖이면 `gemini-3.5-flash-lite` | 같음 | `llm_env.py:24-25,87-104` |
| 추론 강도 | (코드) | OpenAI gpt-5 이상·o 계열 `medium`, Gemini 3 이상 `low` | 같음 | `llm_env.py:130-141` |
| 임베딩 모델 | `EMBEDDING_MODEL_NAME` | `BAAI/bge-m3` (이미지 고정 revision, 오프라인) | 같음 | `remote_embedding_model.py:11`, `pipeline/Dockerfile:70-78` |
| 원격 임베딩 묶음 | (코드) | 요청당 64개, 글자당 4000자. 서버는 한 번에 한 요청씩 처리 | 같음 | `remote_embedding_model.py:15-16`, `embedding_server.py:32-46` |
| task worker poll 간격 | `AI_TASK_MAX_POLL_INTERVAL_MS` | 1800000 (30분) | 같음 | `task_worker.py:108` |
| ingest poll 간격 | `INGEST_MAX_POLL_INTERVAL_MS` | 1800000, 한 번에 1건 | 같음 | `ingest_worker.py:63,301` |
| 중단된 작업 재실행 | `AI_TASK_MAX_INTERRUPTED_ATTEMPTS` | 3 | 같음 | `postgres_task_journal.py:49` |
| 변환 전체 마감 | `CONVERT_BATCH_DEADLINE_SECONDS` | 7200초 (poll 간격 = 마감+600초) | 같음 | `converter/worker.py:31-34` |
| 변환 시도 timeout | `CONVERT_ATTEMPT_TIMEOUT_SECONDS` | 1500초 (넘으면 범위를 반으로 나눠 재시도) | 같음 | `converter/app.py:34` |
| 명령당 최대 페이지 | (코드) | 50 | 같음 | `converter/worker.py:37` |
| 회의 전사 동시 / 마감 | `MEETING_TRANSCRIPTION_CONCURRENCY` / `…_DEADLINE_SECONDS` | 4 / 1500초 | 같음 | `speech/interfaces/command/dependencies.py:20-21` |
| LLM timeout | `QUERY_LLM_TIMEOUT_SECONDS`, `QUERY_EVALUATOR_TIMEOUT_SECONDS`, `AGENT_ROUTER_LLM_TIMEOUT_SECONDS`, `CONVERSATION_REPLY_LLM_TIMEOUT_SECONDS`, `AGENT_PLAN_LLM_TIMEOUT_SECONDS`, `MARKDOWN_EDIT_LLM_TIMEOUT_SECONDS`, `SKILL_AUTHORING_LLM_TIMEOUT_SECONDS`, `SKILL_DRAFT_LLM_TIMEOUT_SECONDS` | 모두 180초 | 같음 | 각 `chat_completions_*.py` |
| 짧은 LLM timeout | `AGENT_FOLDER_LOOKUP_LLM_TIMEOUT_SECONDS`, `TASK_CLARIFICATION_LLM_TIMEOUT_SECONDS` | 60초 | 같음 | |
| 근거 개수 | `QUERY_EVIDENCE_LIMIT` | 8 | 같음 | `query/.../dependencies.py:56` |
| 에이전트 도구 timeout | `AGENT_TOOL_TIMEOUT_SECONDS` | 30초 | 같음 | `agent_worker.py:49` |
| 에이전트 worker poll | `AGENT_WORKER_POLL_SECONDS` | 1초. lease 90초, heartbeat 30초, 3회 실패 시 종료 | 같음 | `agent_worker.py:67` |
| 권한 확인 timeout | `ACCESS_AUTHZ_TIMEOUT_SECONDS` | 3초 | 같음 | `workspace_authorization.py:38` |
| 의미 패치 병렬 | `WIKI_SEMANTIC_MAX_WORKERS` | 4 | 같음 | `generation_loop_adapters.py:50` |
| Jev | `JEV_SKILL_INTENT_ENABLED`, `JEV_FOLDER_LOOKUP_ENABLED` | `false` | 설정 없음 → 꺼짐 | `jev_client.py:33-34` |
| Jev timeout / 차단 | `JEV_TIMEOUT_SECONDS` / `JEV_BLOCK_SECONDS` | 30초 / 600초 | 같음 | `jev_client.py:63,214` |
| 프롬프트 기록 | `LLM_PROMPT_LOG_DIR` | 빈 값 (끔) | 같음 | `chat_completions_llm.py:66` |

DB 스키마는 Flyway가 아니라 `pipeline/db/ai_schema.sql` 한 파일로 관리합니다. `AI_DB_MIGRATION_URL`로 멱등 실행(`ADD COLUMN IF NOT EXISTS`)하고, converter 역할 권한을 매번 다시 줍니다(`migrate_ai_schema.py:17-55`). 끝난 AgentRun은 90일 뒤 지웁니다(`agent_worker.py:21-37`, 24시간마다).

### 2.7 frontend 설정

| 설정 | 종류 | 기본값 | 운영 | 근거 |
|---|---|---|---|---|
| `NEXT_PUBLIC_LEGAL_PAGES_ENABLED` | 빌드 시점 | 없으면 false | **false**. 이미지 빌드에 build-arg가 없어 켤 수 없습니다 | `frontend:web/src/shared/config/legal.ts:13`, `web/Dockerfile` |
| `SAME_ORIGIN_API` | 빌드·실행 | 없음 | `true` (Dockerfile). Next rewrite 끔, ALB가 `/api` 분기 | `frontend:web/next.config.mjs:7-13` |
| `NEXT_PUBLIC_DOCUMENT_DIRECT_API` | 빌드 시점 (자동 계산) | `SAME_ORIGIN_API=true`면 `true` | `true` | `next.config.mjs:11` |
| `DOCUMENT_DIRECT_UPLOAD_ENABLED` | 실행 | 없으면 켜짐. `"false"`면 S3 직접 multipart 업로드 끔 | 설정 없음 → 켜짐 | `frontend:web/app/api/document-transport/route.ts:12` |
| `ACCESS_CODE` | 실행, 비밀 | 없으면 접근 코드 문 끔 | 설정됨 | `accessCode.ts:6` |
| 접근 코드 쿠키 | (고정) | `fruition_access`, SHA-256, HttpOnly, SameSite=Lax, 30일 | | `access/verify/route.ts:45-55` |
| 접근 코드 오답 한도 | (고정) | 클라이언트당 10분에 10회 (Pod 메모리) | | `attemptLimiter.ts:4-7` |
| `CSP_S3_ORIGIN` | 실행 | `https://*.amazonaws.com` | 저장 버킷 주소 | `contentSecurityHeaders.ts:22` |
| `BACKEND_URL` / `ACCESS_URL` | 실행 | localhost | 운영에 없음 (같은 주소) | `next.config.mjs:3-4` |

CSP는 middleware에서 요청마다 nonce를 붙여 만듭니다. `default-src 'self'`, `script-src 'self' 'nonce-…' 'strict-dynamic'`, `object-src 'none'`, `frame-ancestors 'none'`, `report-uri /csp-report`입니다 (`frontend:web/middleware.ts`, `contentSecurityPolicy.ts:46-77`).

---

## 3. 기능 스위치(옵션) 표

| 스위치 | 운영값 | 기본값 | 어디서 바꾸나 | 상태 |
|---|---|---|---|---|
| `AI_LIMIT_ENABLED` | `false` | `true` | `k8s/overlays/aws/configmap-aws.yaml:34` → 배포 | 코드 운영 반영, 스위치 꺼짐 |
| `AI_LIMIT_DAILY_TOKENS` | 10,000,000 (기본값) | 10,000,000 | ConfigMap에 키 추가 → 배포 | 위와 같음 |
| `UPLOAD_LIMITS_ENABLED` | 켜짐 (키 없음) | `true` | ConfigMap에 `"false"` 추가 → 배포 | 운영 |
| `UPLOAD_USER_QUOTA_BYTES` | 5GB | 5GB | ConfigMap | 운영 |
| `UPLOAD_MAX_PDF_BYTES` | 100MB | 100MB | ConfigMap. WAF 본문 규칙, multipart 한도와 함께 확인 | 운영 |
| `BILLING_ENFORCE` | `false` | `false` | `k8s/base/configmap.yaml:61` | 운영 |
| `BILLING_PAYMENTS_ENABLED` | `false` | `false` | ConfigMap + PG 비밀값 필요 | 미사용 |
| `BILLING_ESTIMATE_*` | 기본값 (2.5 표) | | ConfigMap | 운영 |
| `DOCUMENT_DIRECT_UPLOAD_ENABLED` (frontend) | 켜짐 | 켜짐 | `k8s/overlays/aws/frontend.yaml` env | 운영. 백엔드에는 스위치가 없습니다 |
| `SAME_ORIGIN_API` (frontend) | `true` | Dockerfile 고정 | 이미지 재빌드 | 운영 |
| `NEXT_PUBLIC_LEGAL_PAGES_ENABLED` (frontend) | false | false | 이미지 빌드 인자 추가가 필요 (현재 방법 없음) | 꺼짐 |
| `LEGAL_CONSENT_REQUIRED` (access) | `false` | `true` | `k8s/base/configmap.yaml:77`. 위 화면 스위치와 같이 바꿔야 가입이 깨지지 않습니다 | 꺼짐 |
| 업로드 시 자동 ingest | 워크스페이스별 `auto_ingest_on_upload`, 기본 꺼짐 | 꺼짐 | 화면의 워크스페이스 설정(OWNER). 조회 실패 시 꺼짐, 60초 캐시 | 운영 |
| 에이전트 계획 자동 승인 | 사용자별 `agent_auto_approval_settings`(`content_edit`, `organize`), 기본 꺼짐 | 꺼짐 | 사용자 설정 API | **운영 반영** (document #195 / V93, ai #191) |
| Skill `requires_source` | 코드 동작 | | - | **운영 반영** (ai #192, document #181~#193) |
| PDF 그림 설명 | 없음 | | - | **미병합.** 로컬 브랜치 `feat/pdf-restore-figure-captions`에만 있고 원격 브랜치·PR이 없습니다 |
| `AGENT_SKILLS_ENABLED` | `true` | `false` | ConfigMap | 운영 |
| `SKILL_API_ENABLED` | `true` | `true` | ConfigMap | 운영 |
| `JEV_*_ENABLED` 5개 | 모두 꺼짐 | `false` | ConfigMap + `TYPESAFE_API_KEY` | 꺼짐 |
| `QUERY_EMBEDDING_MODE` | api `text-only`, worker `bge-m3` | `bge-m3` | ConfigMap / overlay patch | 운영 |
| `QUERY_EVALUATOR_MODE` | `web` | `web` | ConfigMap | 운영 |
| `AI_ALLOWED_LLM_MODELS` | 미설정 (기본 3개) | | ConfigMap에 CSV 추가 | 운영 |
| `ANALYTICS_ENABLED` | `false` | `false` | 배포 설정 `analytics_enabled` | 꺼짐 |
| `LANGSMITH_TRACING` | `false` | | ConfigMap + `LANGSMITH_API_KEY` | 꺼짐 |
| `MANAGEMENT_HEALTH_MAIL_ENABLED` (access) | `false` | `true` | overlay patch | 운영 |
| CORS | `https://<app_domain>` 하나 | localhost | `configmap-aws.yaml:17` | 운영 |
| WAF IP당 / 전체 한도 | 3,000 / 6,000 (5분) | 같음 | Terraform `waf_requests_per_ip_5m`, `waf_requests_total_5m` | 운영 |
| WAF 긴급 차단 | 꺼짐 | `false` | Terraform `waf_emergency_block` | 꺼짐 |
| WAF 민감 경로 차단 | 켜짐 | `true` | Terraform `waf_sensitive_paths_block` | 운영 |
| WAF 접근 코드 필수 | 켜짐 | `true` | Terraform `waf_access_code_required` + `app_domain` | 운영 |
| 절전·기동 | 켜짐 | `false` | Terraform `request_wake_enabled` | 운영 |
| 사람 MFA 전용 정책 | 미확인 | `false` | Terraform `enforce_human_mfa_only` | ⚠ MFA 경보 상태를 보면 아직 끝나지 않았습니다 |
| access DB 즉시 적용 | `false` | `false` | `-var access_db_apply_immediately=true` | 필요할 때만 |

ConfigMap을 바꾸면 이미지는 그대로라도 새 release 기록이 필요합니다. 배포는 [aws-image-releases.md](aws-image-releases.md)의 순서를 따릅니다.

---

## 4. 비밀값과 권한

### 4.1 Secrets Manager

**값은 적지 않습니다.** 모든 앱 비밀값은 KMS CMK `alias/fruition-secrets`(키 자동 교체)로 암호화합니다. External Secrets가 1시간마다(`refreshInterval: 1h`) 필요한 키만 Kubernetes Secret으로 옮깁니다 (`k8s/overlays/aws/external-secrets.yaml`, ClusterSecretStore `aws-secrets-manager`).

| 비밀값 | 형식 | 관리 주체 | 마지막 변경 (메타데이터) | 근거 |
|---|---|---|---|---|
| `fruition/app` | JSON | 처음 값만 Terraform이 넣고(`ignore_changes`), 이후는 콘솔/CLI와 교체 스크립트 | 2026-10-22. 태그 `fruition:jwt-signing-key-rotated-at=2026-10-22T08:24Z`. `fruition:db-credentials-rotated-at` 태그는 **없습니다** ⚠ | `secrets.tf:16-101`, AWS |
| `fruition/waf-access-code` | JSON `{ACCESS_CODE}` | `scripts/aws_waf_access_code.py`가 `fruition/app`에서 복사 | 2026-10-22 | `waf-access-code.tf:2-15` |
| `fruition/budget-discord-webhook` | 문자열 1개 (Discord 웹훅) | 콘솔/CLI에서 직접 입력. Terraform은 빈 그릇만 만듭니다 | 2026-09-17. AWS 관리 키로 암호화 | `budgets.tf:47-50` |
| `rds!db-…` 2개 | RDS 관리 | RDS가 7일마다 자동 교체 | 2026-10-29 교체 | `rds.tf:95,129`, AWS |

**`fruition/app` JSON 키**

| 키 | 용도 | 쓰는 곳 (Kubernetes Secret → env) | 교체 |
|---|---|---|---|
| `ACCESS_DB_RUNTIME_PASSWORD` | access runtime DB 계정 | `fruition-access` → 같은 이름 | DB 계정 교체 절차 |
| `ACCESS_DB_MIGRATION_PASSWORD` | access migration 계정 | `fruition-access-migration` | 같음 |
| `CORE_DB_RUNTIME_PASSWORD` | core runtime | `fruition-document` | 같음 |
| `CORE_DB_MIGRATION_PASSWORD` | core migration | `fruition-document-migration` | 같음 |
| `AI_DB_RUNTIME_PASSWORD`, `AI_DB_MIGRATION_PASSWORD`, `AI_DB_CONVERTER_PASSWORD` | ai 계정 원본 (아래 URL과 함께 바꿈) | 직접 쓰는 Pod 없음 | 같음 |
| `AI_DATABASE_URL` | ai runtime 접속 문자열 | `fruition-pipeline` → `AI_DATABASE_URL` | 같음 |
| `AI_DB_MIGRATION_URL` | ai migration 접속 문자열 | `fruition-ai-migration` | 같음 |
| `AI_CONVERTER_DATABASE_URL` | converter 최소 권한 접속 문자열 | `fruition-converter` → `AI_DATABASE_URL` | 같음 |
| `ACCESS_REDIS_PASSWORD` / `DOCUMENT_REDIS_PASSWORD` / `PIPELINE_REDIS_PASSWORD` | Redis ACL 사용자 | 각 Secret → `REDIS_PASSWORD` | Terraform `random_password.redis` + ElastiCache 사용자 갱신 |
| `JWT_PRIVATE_KEY` | access 토큰 서명 (RSA) | `fruition-access` | `scripts/aws_jwt_keys.py` (stage → rotate) |
| `JWT_PUBLIC_KEY`, `JWT_KEY_ID`, `JWT_PREVIOUS_PUBLIC_KEY`, `JWT_PREVIOUS_KEY_ID` | 토큰 검증, 키 교체 중 이전 키 | `fruition-access`, `fruition-document` | 같음 |
| `MFA_ENCRYPTION_KEY` | TOTP 비밀 암호화 (32바이트) | `fruition-access` | 바꾸면 기존 MFA 등록을 못 읽습니다. 영향 확인 없이 바꾸지 않습니다 |
| `SPRING_MAIL_HOST`, `SPRING_MAIL_USERNAME`, `SPRING_MAIL_PASSWORD`, `MAIL_FROM` | SMTP | `fruition-access` | 메일 제공자에서 발급 후 갱신 |
| `INTERNAL_CALLBACK_TOKEN` | 서비스 간 `X-Internal-Token` | access, document, pipeline, embedding-server | 모든 서비스 동시 재시작 필요 |
| `AGENT_INTERNAL_TOKEN` | document ↔ ai 에이전트 토큰 | document, pipeline | 같음 |
| `GOOGLE_CLIENT_ID/SECRET`, `NAVER_CLIENT_ID/SECRET`, `KAKAO_CLIENT_ID/SECRET` | OAuth | `fruition-access` | 각 제공자 콘솔 |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` | LLM | `fruition-pipeline`, `fruition-converter` | 제공자 콘솔 |
| `TYPESAFE_API_KEY` | Jev | `fruition-pipeline` | |
| `LANGSMITH_API_KEY` | LangSmith | `fruition-pipeline` | |
| `TAVILY_API_KEY` | 웹 검색 | `fruition-pipeline` | |
| `KOREAEXIM_AUTH_KEY` | 환율 API | `fruition-document` | |
| `ACCESS_CODE` | 화면 접근 코드 | `fruition-frontend` + WAF 전용 비밀값 | 바꾼 뒤 `aws_waf_access_code.py`로 복사하고 WAF plan/apply |
| `POSTHOG_PROJECT_TOKEN` | 분석 (선택) | `fruition-analytics` (`dataFrom` 템플릿) | |

Strimzi가 만드는 Kubernetes Secret(`kafka-*` 사용자 인증서, `kafka-cluster-ca-cert`)은 Secrets Manager 밖에 있습니다. Strimzi가 갱신합니다.

**GitHub 쪽 값** (`Fruition-flatform`)

| 이름 | 종류 | 용도 |
|---|---|---|
| `AWS_SMOKE_EMAIL`, `AWS_SMOKE_PASSWORD` | Environment `feedback` secret | 배포 smoke 전용 계정 |
| `AWS_SMOKE_WORKSPACE_ID` | 변수 | smoke workspace (`ws_` + 32자리) |
| `AWS_DEPLOY_ROLE_ARN`, `AWS_DEPLOY_CONFIG_JSON` | 변수 | 배포 role, 배포 설정 (endpoint, 도메인, ARN 등. 비밀값 없음) |
| `AWS_IMAGE_PUBLISH_ROLE_ARN`, `AWS_ACCOUNT_ID`, `AWS_IMAGE_PUBLISH_ENABLED` | 저장소 변수 | 이미지 게시 |

**교체 주기와 담당** ([aws-credential-rotation.md](aws-credential-rotation.md))

- DB 앱 계정과 JWT 서명 키는 **최대 90일**마다 교체합니다. 담당은 플랫폼 운영자입니다.
- 교체를 끝내면 `fruition/app`에 태그 `fruition:db-credentials-rotated-at`, `fruition:jwt-signing-key-rotated-at`을 기록합니다.
- 태그가 없으면 credential-guard가 비밀값 생성일을 기준으로 나이를 셉니다. 2026-11-02 기준 DB 계정은 **46일째**로, 2026-12 중순에 90일 경보가 울립니다. JWT는 11일째입니다.
- RDS 관리자 비밀번호는 RDS가 7일마다 교체합니다.

### 4.2 사람·CI 접근

| 주체 | 내용 | 근거 |
|---|---|---|
| 운영자 IAM 사용자 (`human_operator_user_name`) | `fruition-human-admin` role을 MFA로 assume (세션 1시간, EKS 클러스터 관리자). MFA 전용 정책은 `enforce_human_mfa_only` 기본 `false` | `human-access.tf:3-117` |
| 현재 경보 상태 | `HumanMfaMissing` **ALARM**, `HumanDirectAdministratorAccess` **ALARM** ⚠. 운영자 사용자에 MFA 장치가 없고 AdministratorAccess가 직접 붙어 있습니다 | AWS |
| 루트 | `RootCredentialsUnprotected` OK | AWS |
| GitHub OIDC 공급자 | `token.actions.githubusercontent.com`, audience `sts.amazonaws.com` | `github-oidc.tf:14-19` |
| `fruition-github-deploy` | subject `<prefix>:environment:feedback`만 허용. ECR `ListImages`/`DescribeImages`, `eks:DescribeCluster`, 운영 SNS `Publish`, ALB 로그 버킷 메타데이터 확인. 클러스터 안에서는 `fruition:deployers` RBAC (`k8s/platform/aws/deploy-rbac.yaml`) | `github-oidc.tf:21-87`, `alb-access-logs.tf:98-109` |
| `fruition-github-image-publish` | subject `<prefix>:ref:refs/heads/main`만 허용, 세션 2시간. ECR 5개 저장소에 푸시만 허용. EKS·DB·Secrets·state 권한 없음 | `github-image-publish.tf:2-48` |
| `fruition-feedback-runner-host` | runner EC2. SSM, EKS describe, 클러스터 안 `fruition:operators` (일회성 조회 Pod만) | `runner.tf:51-90`, `eks.tf:145-148` |
| GitHub Environment `feedback` | required reviewers + 브랜치 정책(사용자 지정, main) | GitHub API |

### 4.3 IRSA와 IAM role

| Role | ServiceAccount | 권한 요약 |
|---|---|---|
| `fruition-document-storage` | `fruition:fruition-document` | S3 읽기 `sources/documents/*`, `assets/*`, `wiki/*`, `tmp/document-uploads/*`, `tmp/convert/*`, `meetings/*` (버전 읽기 포함). 쓰기·multipart는 `sources/documents/*`, `assets/*`, `tmp/document-uploads/*`, `meetings/*`. 삭제는 `sources/documents/*`, `assets/*`, `meetings/*`. 저장 KMS 키 Decrypt/GenerateDataKey, ListBucket |
| `fruition-pipeline-storage` | `fruition:fruition-pipeline` | 읽기 `sources/documents/*`, `wiki/*`, `agent-runs/*`, `pipeline-runs/*`, `meetings/*`. 쓰기 `wiki/*`, `agent-runs/*`, `pipeline-runs/*`. 삭제 `wiki/*`, `agent-runs/*`, `pipeline-runs/meeting-transcription/*` |
| `fruition-converter-storage` | `fruition:fruition-converter` | 읽기 `sources/documents/*`, 쓰기 `tmp/convert/*`. 삭제 없음 |
| `fruition-frontend-wake` | `fruition:fruition-frontend` | 고정 source/detail-type의 EventBridge PutEvents, 상태 테이블 GetItem |
| `fruition-ebs-csi` | `kube-system:ebs-csi-controller-sa` | AWS 관리 EBS CSI 정책 |
| `fruition-alb-controller` | `kube-system:aws-load-balancer-controller` | 컨트롤러 v3.5.0 공식 정책 (`policies/aws-load-balancer-controller-v3.5.0.json`) |
| `fruition-external-secrets` | `external-secrets:external-secrets` | `fruition/app` 읽기, secrets CMK 복호화만 |
| `fruition-cluster-autoscaler` | `kube-system:cluster-autoscaler` | ASG 조회. 크기 변경은 discovery 태그 2개가 있는 ASG만 |
| `fruition-cloudwatch-agent` | `amazon-cloudwatch:cloudwatch-agent`, `amazon-cloudwatch:fluent-bit` | AWS 관리 `CloudWatchAgentServerPolicy` |
| access (`fruition-access`) | IRSA 없음 | S3 권한 없음 |

S3 정책 근거는 `s3.tf:165-223`, 나머지는 `eks.tf:244-369`, `request-wake.tf:173-212`, `observability.tf:23-35`입니다. Lambda role: `fruition-request-wake`, `fruition-budget-discord`, `fruition-credential-guard`.

---

## 5. 관측

### 5.1 CloudWatch 경보 (37개, 기준 시각 상태 포함)

모든 경보는 SNS `fruition-operations-alerts` → Lambda `fruition-budget-discord` → Discord로 갑니다. 실패하면 SQS `fruition-budget-alert-failures`로 갑니다. 대부분 OK 알림도 보냅니다. 근거는 `infra/terraform/observability.tf:105-284`, `credential-guard.tf:84-109`, `request-wake.tf:221-242`, AWS `describe-alarms`입니다.

| 경보 (`fruition-ops-` 뒤) | 지표 | 통계 | 기준 | 주기 × 구간 (경보 구간) | 결측 처리 | 상태 |
|---|---|---|---|---|---|---|
| `notification_test` | Fruition/Operations NotificationTest | Sum | > 0 | 300s × 1 | 정상 | OK |
| `pod_cpu` | ContainerInsights pod_cpu_utilization (ns fruition) | Max | > 80% | 600s × 3 | missing | OK |
| `pod_memory` | pod_memory_utilization | Max | > 85% | 600s × 3 | missing | OK |
| `node_cpu` | node_cpu_utilization | Avg | > 80% | 600s × 3 | missing | OK |
| `node_memory` | node_memory_utilization | Max | > 85% | 600s × 3 | missing | OK |
| `failed_nodes` | cluster_failed_node_count | Max | > 0 | 600s × 2 | missing | OK |
| `telemetry_missing` | node_cpu_utilization | SampleCount | < 1 | 600s × 3 | 경보 | OK |
| `application_log_volume` | AWS/Logs IncomingBytes (application) | Sum | > 100MiB | 300s × 1 | 정상 | OK |
| `nat_egress` | NAT BytesOutToDestination | Sum | > 1GiB | 300s × 1 | 정상 | OK |
| `redis_memory` | DatabaseMemoryUsagePercentage | Max | > 80% | 300s × 2 | missing | OK |
| `rds_access_space` / `rds_core_space` | FreeStorageSpace | Min | < 5GiB | 300s × 2 | missing | OK |
| `rds_access_cpu` / `rds_core_cpu` | CPUUtilization | Avg | > 80% | 300s × 3 | missing | OK |
| `rds_access_memory` | FreeableMemory | Avg | < 100MiB | 300s × 3 | missing | OK |
| `rds_access_swap` | SwapUsage | Max | > 64MiB | 300s × 1 | missing | OK |
| `rds_access_connections` | DatabaseConnections | Max | > 60 | 300s × 2 | missing | OK |
| `alb_5xx` | HTTPCode_Target_5XX_Count | Sum | > 10 | 300s × 1 | 정상 | OK |
| `alb_elb_5xx` | HTTPCode_ELB_5XX_Count | Sum | > 10 | 300s × 3 (2) | 정상 | OK |
| `alb_latency` | TargetResponseTime | Avg | > 2초 | 300s × 3 | 정상 | OK |
| `alb_requests` | RequestCount | Sum | > 2000 | 300s × 1 | 정상 | OK |
| `waf_blocked` | WAFV2 BlockedRequests (ALL) | Sum | > 100 | 300s × 3 (2) | 정상 | OK |
| `waf_blocked_burst` | BlockedRequests | Sum | > 1000 | 300s × 1 | 정상 | OK |
| `waf-log-delivery` | 식: 허용+차단 > 0인데 WAF 로그 IncomingLogEvents < 1 | - | > 0 | 300s × 3 | 정상 | OK |
| `ai_fx_policy_missing` | Fruition/AIUsage (로그 지표 필터) | Sum | ≥ 1 | 86400s × 1 | 정상 | OK |
| `ai_fx_refresh_failed` | 같음 | Sum | ≥ 1 | 86400s × 1 | 정상 | **ALARM** ⚠ |
| `ai_model_switched` | 같음 | Sum | ≥ 1 | 86400s × 1 | 정상 | OK |
| `ai_price_missing` | 같음 | Sum | ≥ 1 | 86400s × 1 | 정상 | OK |
| `ai_usage_check_needed` | 같음 | Sum | ≥ 1 | 86400s × 1 | 정상 | **ALARM** ⚠ |
| `discord-delivery-failures` | SQS ApproximateNumberOfMessagesVisible | Max | > 0 | 300s × 1 | 정상 | OK. **알림 대상이 없습니다** (Discord 실패를 Discord로 보낼 수 없어서). 콘솔에서 봐야 합니다 |
| `request-wake-errors` | Lambda Errors (`fruition-request-wake`) | Sum | > 0 | 300s × 1 | 정상 | OK |
| `security-CredentialAuditHeartbeat` | Fruition/Security | Max | < 1 | 86400s × 2 | 경보 | OK |
| `security-DbCredentialAgeDays` | 같음 | Max | > 90일 | 86400s × 1 | 무시 | OK (46일) |
| `security-JwtSigningKeyAgeDays` | 같음 | Max | > 90일 | 86400s × 1 | 무시 | OK (11일) |
| `security-HumanMfaMissing` | 같음 | Max | > 0 | 86400s × 1 | 무시 | **ALARM** ⚠ |
| `security-HumanDirectAdministratorAccess` | 같음 | Max | > 0 | 86400s × 1 | 무시 | **ALARM** ⚠ |
| `security-RootCredentialsUnprotected` | 같음 | Max | > 0 | 86400s × 1 | 무시 | OK |

AI 사용량 지표 5개는 application 로그 그룹의 document-svc WARN 줄을 세는 지표 필터입니다 (`observability.tf:241-270`).

### 5.2 대시보드·로그 그룹

- 대시보드: `fruition-operations` 1개 (`observability.tf:285-317`).
- 로그 그룹은 모두 **STANDARD** 클래스, **14일** 보관입니다.

| 로그 그룹 | 내용 |
|---|---|
| `/aws/containerinsights/fruition-eks/application` | 앱 로그 (EC2 노드 Fluent Bit + Fargate 라우터 `fargate-` 접두사) |
| `/aws/containerinsights/fruition-eks/dataplane`, `/host` | 노드·런타임 로그 |
| `/aws/containerinsights/fruition-eks/performance` | Container Insights 성능 로그 (EMF) |
| `/aws/eks/fruition-eks/cluster` | control plane (api, audit, authenticator). 가장 큽니다 |
| `/aws/rds/instance/fruition-{access,core}-postgres/postgresql` | RDS |
| `/aws/lambda/fruition-{budget-discord,credential-guard,request-wake}` | Lambda |
| `/aws/vpc-flow-log/<vpc-id>` | 예전 Flow Logs (S3 전환 후 남은 것) |
| `aws-waf-logs-fruition` | WAF |

**Container Insights 수집** (`infra/observability/addon-config.json`)

- 수집 주기는 **600초**입니다.
- 지표 5개만 남깁니다: `node_cpu_utilization`, `node_memory_utilization`, `cluster_failed_node_count`, `pod_cpu_utilization`, `pod_memory_utilization`.
- Application Signals, OTel Container Insights, control plane 지표는 모두 꺼져 있습니다.
- 에이전트 자원은 요청 50m/128Mi, 한도 500m/512Mi입니다.

**Fluent Bit**

- cloudwatch-agent, fluent-bit, aws-node, kube-proxy 로그는 본 입력에서 뺍니다. fluent-bit과 cloudwatch-agent는 별도 입력(버퍼 5MB)으로 받습니다.
- kubernetes 필터는 라벨과 annotation을 붙이지 않습니다.
- grep 필터로 `GET|HEAD /health(z)` 200 접근 로그를 버립니다.
- Fargate는 `aws-observability/aws-logging` ConfigMap으로 같은 application 그룹에 보냅니다 (`k8s/platform/aws/fargate-logging.yaml`).

### 5.3 예산과 Discord

- 예산: `fruition-monthly-50` … `fruition-monthly-1000`, **$50 단위로 20개**입니다. 계정 전체 실제 사용액(ACTUAL)이 100%를 넘으면 SNS `fruition-budget-alerts` → 같은 Discord Lambda로 갑니다. 비용을 자동으로 멈추지는 않습니다 (`budgets.tf:6-23`).
- 기준 시각 이번 달 실제 사용액은 **$52.88**입니다(11/1~11/3). `fruition-monthly-50`을 넘었습니다. AWS 예측값 $845.99는 월초 외삽이라 크게 부풀려졌을 수 있습니다.
- Discord 메시지는 한국어 설명을 먼저 쓰고 AWS 원문을 뒤에 붙입니다 ([aws-observability.md](aws-observability.md)).

---

## 6. 배포·릴리스

| 단계 | 내용 | 근거 |
|---|---|---|
| 이미지 게시 | `Publish image release`가 **매시 7·22·37·52분**(15분 간격)에 돕니다. 수동 실행도 됩니다(입력 없음). `AWS_IMAGE_PUBLISH_ENABLED=true`, main에서만 돕니다. 네 서비스의 main 커밋과 그 커밋의 `ci.yml` 성공을 확인합니다. 바뀐 서비스만 `b-<context tree>` 태그로 빌드하고 나머지는 재사용합니다. linux/amd64, build-arg 없음. GitHub Release `images-<ID>`와 `release.json`을 만듭니다 | `.github/workflows/publish-images.yml:4-7,19`, [aws-image-releases.md](aws-image-releases.md) |
| 검토 기록 | `docs/releases/<ID>.json`을 main에 올립니다. 키는 정확히 `release_sha`, `migration_mode`, `compatibility_test_url`(최초 설치는 `installation_test_url`), `restore_test_url` 네 개입니다. `migration_mode`는 `expand-only`, `none`, `initial-install` 중 하나입니다(`maintenance-cutover`는 별도 검증). URL은 `https://github.com/FruitionKR/<repo>/(actions/runs\|issues\|pull)/<n>`이어야 합니다. 보통 `<ID>-validation.md`도 함께 둡니다 | `scripts/aws_release_safety.py:12-29`, `docs/releases/review.example.json` |
| 배포 실행 | **Actions → Deploy (EKS)**, branch `main`만, Environment `feedback` 승인이 필요합니다. 입력은 `action`(deploy/rollback/bootstrap/recover), `release_sha`, `rollback_sha`, 최초 설치 복구용 boolean 3개입니다. self-hosted runner, 90분 timeout, 동시 실행 1개(`deploy-eks-feedback`, 취소 안 함) | `.github/workflows/deploy.yml:1-48` |
| 항상 최신 main | 배포 workflow와 검토 기록은 main 기준입니다. 서비스 변경도 각 저장소 main에 병합돼야 게시됩니다. 오래된 브랜치에서 배포하지 않습니다 | `deploy.yml:45`, [aws-image-releases.md](aws-image-releases.md) |
| document·ai 흐름 | 기능 PR → `dev` → release PR(dev→main) → main CI 성공 → 이미지 게시. access·frontend는 main으로 바로 갑니다 | release 기록 `docs/releases/b7f0117…-validation.md` |
| 배포 전 스냅샷 | 배포 전에 RDS 수동 스냅샷을 만듭니다. 이름은 `fruition-{access,core}-pre-release-<SHA 앞 8자리>`입니다(예: 2026-11-03 `…-b7f01174`) | AWS `describe-db-snapshots` |

**`aws_deploy.py` 순서** (`scripts/aws_deploy.py:625-865`)

1. 입력을 검증합니다(설정, 매니페스트, 검토 기록, smoke 계정). 대상 계정과 ALB 로그 버킷을 확인합니다. 렌더한 뒤에만 AWS를 바꿉니다.
2. namespace 라벨(ALB readiness gate, PSS `baseline`), `gp3` StorageClass, ClusterSecretStore 준비 상태를 확인합니다.
3. 같은 SHA의 성공 기록(`fruition-release-<sha>` ConfigMap)이 있으면 비교합니다. DB **fingerprint가 다르면 재배포를 막습니다**.
4. 기반 리소스를 적용합니다: ServiceAccount, ConfigMap, ExternalSecret, NetworkPolicy. 예전 `internal-only-ingress` 정책을 지우고 ExternalSecret Ready를 기다립니다.
5. 새 release면 `migration_mode`에 따라 마이그레이션 Job을 실행합니다(`expand-only`일 때). 그 뒤 fingerprint를 다시 잽니다.
6. Kafka, KafkaNodePool, KafkaTopic을 적용합니다. Kafka는 **operator가 새 generation을 반영하고 broker Pod가 모두 Ready가 될 때까지 최대 10분** 기다립니다. 그다음 KafkaUser를 적용합니다.
7. Service와 Ingress를 적용하고 ALB 바인딩을 기다립니다.
8. **converter를 먼저** 교체합니다(rollout 600초).
9. **배포 여유 Job** `fruition-deploy-headroom`을 띄웁니다. 요청·한도 **1200m / 3Gi**, ON_DEMAND 노드, 최대 1200초. Ready를 15분 안에 못 받으면 중단합니다. 받으면 지웁니다.
10. API 3개(access, document, pipeline-api)를 하나씩 교체합니다(각 600초). 그다음 나머지 Deployment를 교체합니다. KEDA 대상은 `replicas`를 빼고 적용합니다.
11. TriggerAuthentication, ScaledObject, HPA·PDB를 적용합니다.
12. 공개 경로 상태를 확인하고, 전용 계정으로 smoke를 돌립니다(로그인 → 문서 생성 → AI ingest → 삭제). 성공하면 `fruition-release-<sha>` 기록을 남깁니다.
13. workflow는 이어서 `scripts/aws_pdf_smoke.py`로 대용량 PDF multipart 업로드, Range 읽기, 일괄 변환, AI를 검증합니다. 실패하면 운영 Discord로 알립니다.

**마이그레이션 규칙**

| 대상 | 규칙 | 근거 |
|---|---|---|
| access·document | Flyway를 k8s Job(`--migrate-only`, migration 계정)으로만 실행합니다. 앱은 `validate`만 합니다. `transactional-lock=false`(session advisory lock) | `document:AP:64-69`, `access:AP:54-59` |
| 인덱스 | `CREATE INDEX CONCURRENTLY IF NOT EXISTS`만 담은 별도 파일 + 같은 이름의 `.sql.conf`에 `executeInTransaction=false`. `SET lock_timeout = '120s'` … `RESET`. INVALID 인덱스 수동 복구 안내를 주석으로 둡니다 | document V85, V87, V89, V91, V92 |
| 일반 DDL | `SET LOCAL lock_timeout = '5s'` | document V86, V88, V90 |
| ai | `ai_schema.sql` 멱등 실행 (`IF NOT EXISTS`) | 2.6 |
| 허용 범위 | 운영 배포는 `expand-only` 또는 `none`입니다. 파괴적 변경은 [aws-maintenance-cutover.md](aws-maintenance-cutover.md)의 점검 절차로만 합니다 | `aws_release_safety.py:23` |

**되돌리기**

- 이전 성공 release(`rollback_sha`)로만 되돌립니다. 그 release의 DB fingerprint와 현재 DB가 같아야 합니다.
- DB가 이미 바뀌었으면 rollback이 막힙니다. 이때는 **호환되는 수정 release로 앞으로 나갑니다(roll-forward)**. 자동 DB rollback은 없습니다.
- 보안 계약 버전 2 이전 release는 재사용하지 않습니다.
- 자세한 내용은 [aws-maintenance.md](aws-maintenance.md)에 있습니다.

---

## 7. 정기 작업과 일정

| 작업 | 시각·주기 | 근거 |
|---|---|---|
| RDS 백업 | access KST 01:07-01:37, core KST 01:22-01:52, 매일, 7일 보관 | AWS |
| RDS 유지 관리 | access KST 목 00:32-01:02, core KST 월 22:07-22:37. 대기 중: OS `system-update` | AWS |
| Redis 유지 관리 | KST 월 14:00-15:00 (업무 시간 ⚠). 스냅샷 없음 | AWS |
| RDS 관리자 비밀번호 | RDS가 7일마다 자동 교체 | AWS |
| 문서 휴지통 영구 삭제 | 매일, 30일 지난 것 (document) | 2.5 |
| 워크스페이스 휴지통 | 매일, 30일 (access) | 2.4 |
| 끝난 AgentRun 삭제 | 매일, 90일 (ai) | 2.6 |
| 환율 갱신 | 평일 KST 11:30 (document) | 2.5 |
| S3 수명 주기 | 1.6 표 (tmp 7일, tmp/convert 1일, pipeline-runs 30일, 이전 버전 30일) | `s3.tf` |
| 로그 보관 | CloudWatch 14일, ALB 로그 30일, Flow Logs 14일 | 5.2, 1.6 |
| Kafka 메시지 / offset | 3일 / 365일 | 1.5 |
| 자격 증명 점검 | 매일 (credential-guard) | 4.1 |
| DB 계정·JWT 키 교체 | 90일 이내. DB는 태그가 없어 생성일 기준으로 2026-12 중순에 경보 | 4.1 |
| ECR 정리 | 저장소마다 최근 60개 | 1.7 |
| 이미지 게시 확인 | 15분마다 | 6 |
| 절전 상태 확인 | 1분마다 (request-wake) | 1.10 |
| EKS 업그레이드 | **2027-03-27 전에** 1.36 이상으로. 넘기면 연장 지원 요금 | 1.2 |

**문서 작성 시점 미완료 항목**

| 항목 | 상태 |
|---|---|
| 감사 로그 절감 helm 값 (Strimzi·Cluster Autoscaler·KEDA) | 코드에는 있습니다. `aws-platform-up.sh` 재실행이 필요합니다(운영 반영 미확인). EBS CSI 쪽은 반영됐습니다 |
| 일반 노드 CPU credit | 코드 `standard`, 실제 `unlimited`. 원인 확인이 필요합니다 |
| 에이전트 자동 승인 / `requires_source` | 운영 반영 (이미지 `b7f0117`) |
| AI 하루 토큰 한도 | 코드 운영 반영, 스위치 꺼짐 |
| PDF 그림 설명 | 미병합 (로컬 브랜치만) |
| document #198 (스케줄 lease, 휴지통 인덱스 V94) | 열린 PR |
| ai #193 (post-ingest 품질 상태), #195 (대기 ledger 기여) | 열린 PR |
| 운영자 MFA·AdministratorAccess | 경보 ALARM 상태 |

---

## 8. 비용 요약

| 항목 | 값 |
|---|---|
| 현재 월 추정 | 2026-11-02 기준 **월 약 $680**입니다. 같은 문서의 비용 통제 변경을 모두 적용하면 **약 $185 줄어** 월 약 $495 수준으로 어림합니다. 이 추정은 access DB·Redis·일반 노드 최대 수를 바꾸기 전에 계산한 값이라 **다시 계산해야** 합니다 ([aws-deployment-costs.md](aws-deployment-costs.md)) |
| 이번 달 실제 (11/1~11/3) | $52.88 (AWS Budgets) |
| 빠진 것 | 외부 AI API 요금(OpenAI·Gemini·Anthropic 등), 세금, 환율 |
| 크게 바뀌는 요인 | Spot 가격과 AI 노드 가동 시간, 일반 노드 수(배포 중 5번째 노드), CloudWatch 수집량(특히 EKS 감사 로그), NAT 전송량, EKS 연장 지원 전환(월 +약 $365) |
| 한계 | Cost Explorer 조회 권한이 없어 서비스별 실제 청구는 이 문서에서 확인하지 못했습니다. 위 값은 공시 단가 기반 추정입니다 |

---

## 9. 불일치·확인 필요 목록

| # | 내용 | 코드·문서 | 실제 | 조치 제안 |
|---|---|---|---|---|
| 1 | 일반 노드 t3 CPU credit | `eks.tf:92` `standard` | 인스턴스 `unlimited`, 시작 템플릿에 credit 설정 없음 | 모듈이 credit_specification을 시작 템플릿에 넣는지 확인 |
| 2 | 일반 노드 희망 수 | Terraform 2 | EKS 희망 3, 실행 중 2대 확인 (교체 중일 수 있음) | Cluster Autoscaler 축소 확인 |
| 3 | `fruition:db-credentials-rotated-at` 태그 | 교체 절차가 기록해야 함 | 태그 없음, 생성일 기준 46일 | 다음 DB 계정 교체 때 태그 기록 |
| 4 | 운영자 MFA·직접 관리자 권한 | `human-access.tf`는 MFA role 전환을 전제로 함 | `HumanMfaMissing`, `HumanDirectAdministratorAccess` ALARM | MFA 등록 후 `enforce_human_mfa_only=true` |
| 5 | AI 사용량 경보 | - | `ai_fx_refresh_failed`, `ai_usage_check_needed` ALARM | 환율 갱신 실패 로그와 사용량 확인 필요 항목 점검 |
| 6 | 감사 로그 helm 값 | `aws-platform-up.sh`에 있음 | EKS API가 사설이라 확인 못 함 | runner에서 `helm get values`로 확인 |
| 7 | `RESTORE_PREVIEW_TOKEN_SECRET` | 비면 Pod마다 무작위 키 | 운영 미설정, document-svc 2개 | 다중 replica에서 복원 미리보기 토큰이 다른 Pod에서 실패할 수 있습니다. 비밀값 추가를 검토합니다 |
| 8 | `LANGSMITH_PROJECT` | base `local-pilot-dev` | 운영도 같음 (추적 꺼짐) | 추적을 켤 때 이름 정리 |
| 9 | `NEXT_PUBLIC_LEGAL_PAGES_ENABLED` | 화면 기능 있음 | 이미지 빌드에 인자가 없어 켤 수 없음 | 약관 공개 전에 build-arg 경로 추가 |
| 10 | `discord-delivery-failures` 경보 | - | 알림 대상 없음 | 콘솔 확인 또는 이메일 구독 검토 |
| 11 | Redis 유지 관리 시간 | 명시 안 함 | KST 월 14:00-15:00 | 단일 노드라 재로그인이 생길 수 있습니다. 새벽으로 옮기는 것을 검토합니다 |
| 12 | `eks.tf:1` 주석 | "General node 2/2/3" | 실제 최대 5 | 주석만 낡았습니다 |
| 13 | ECR 이미지 수 | 60개 보존 | document 79, frontend 65 등 | 수명 주기 정리가 늦는 것인지 다음 날 다시 확인 |

**이 문서에서 확인하지 못한 것**

- 클러스터 안 실제 상태: helm 값, 실행 중 Pod의 env, Kubernetes Secret에 실제 들어간 키. EKS API가 사설이라 runner를 거쳐야 합니다.
- Cost Explorer 서비스별 청구 (권한 없음).
- `fruition-operations` 대시보드 위젯 구성 (Terraform만 확인).
- GitHub Environment required reviewer 명단.

---

## 관련 문서

[aws-resource-inventory.md](aws-resource-inventory.md) · [aws-deployment-costs.md](aws-deployment-costs.md) · [aws-observability.md](aws-observability.md) · [aws-maintenance.md](aws-maintenance.md) · [aws-maintenance-cutover.md](aws-maintenance-cutover.md) · [aws-credential-rotation.md](aws-credential-rotation.md) · [aws-image-releases.md](aws-image-releases.md) · [aws-request-wake.md](aws-request-wake.md) · [aws-waf-document-content.md](aws-waf-document-content.md) · [releases/](releases/) · [ADR-0021](adr/0021-aws-observability-and-operations.md)

## 갱신 점검

문서를 고친 뒤 아래 명령의 출력이 비어 있어야 합니다(비밀값 형태 검사).

```bash
grep -nE 'AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|xox[abps]-|discord(app)?\.com/api/webhooks|phc_[A-Za-z0-9]{10,}|postgres(ql)?://[^ ]*:[^ ]*@|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}' docs/operations-reference.md
```
