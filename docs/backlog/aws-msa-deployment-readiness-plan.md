# AWS MSA 배포 준비 보완 계획

## 실행 절차와 단계별 검증

현재 코드 기준으로 아래 순서를 따른다. 사용자 피드백 환경을 기본 대상으로 하며, 실제 AWS 생성·배포 및 비용이 발생하는 장애·부하 실험은 저장소 코드 검증과 구분한다. 기존 사용자 변경은 보존한다. 구현 과정에서 새 사실이 확인되면 다음 단계에 착수하기 전에 이 계획의 범위와 완료 조건을 갱신한다.

### 에이전트 운영 규칙

- Assign one implementation agent per stage.
- Finish and test the current stage before assigning its independent verification agent.
- Verify only the stage changes and their integration with previously accepted stages.
- Report PASS, FAIL, or BLOCKED with commands, results, affected files, and remaining external checks.
- Return every finding to the implementation agent. Reverify fixes before advancing.
- Never mark an unexecuted AWS, recovery, or load test as passed.
- Preserve pre-existing user changes. Do not commit, push, deploy, or rotate live credentials as part of local implementation.

| 단계 | 구현 범위 | 다음 단계 진입 조건 |
|---|---|---|
| 1. DB 소유권 bootstrap | `infra/postgres/`에 대상 `all/access/core` 경계, 원격 접속, 해당 DB·role만 생성, 반복 실행과 권한 검증. 로컬 통합 실행은 all 사용 | 격리된 임시 PostgreSQL에서 all/access/core 생성 범위·반복 실행·runtime DML 허용·DDL 및 교차 접근 거부 검증, 기존 개발 DB 미변경, 검증 에이전트 PASS |
| 2. 서비스 자격증명·migration 경계 | AWS 서비스별 Secret/ServiceAccount, runtime에 타 DB·migration 비밀번호 미주입, 별도 migration 실행 경로. base/kind도 타 서비스 Secret 주입 제거. MFA 키·SMTP·초대 URL 필수 배포 설정 포함 | AWS workload별 허용 키 검사, migration 선행 후 runtime 기동 계약 검증, base/kind 타 서비스 키 비노출, 기존 로컬 실행 경로 회귀 확인, 검증 에이전트 PASS |
| 3. AWS 배포 재현성 | 임시 디렉터리 렌더·입력 검증, DB bootstrap/migration 선행 gate, 전체 Deployment 및 controller readiness, 공개 smoke test, 동일 image SHA rollback 경로 | placeholder·빈 입력·실패한 migration/worker를 성공으로 처리하지 않는 테스트, source manifest 불변, 검증 에이전트 PASS |
| 4. AI artifact·확장 | 실제 run 파일 의존성 조사 후 영속 artifact의 object storage 저장, 임시 파일 분리, 공유 PVC·같은 노드 제약 제거, AI node scheduling 연결 | 서로 다른 작업 디렉터리의 API/worker 조회 및 재처리 테스트, 기존 pipeline 회귀 테스트, 검증 에이전트 PASS. 실제 다중 노드·Spot 중단은 AWS gate |
| 5. 저장소·네트워크 권한 | S3 workload credential chain과 서비스별 권한, 정적 AWS IAM 사용자 제거. Redis 공유 projection 계약·ACL 및 내부 통신 허용 범위를 코드 근거로 확정 | 로컬 MinIO 경로와 AWS 임시 자격증명 경로 테스트, workload별 권한·허용 연결 검사, 검증 에이전트 PASS. 실제 IAM 거부·네트워크 차단은 AWS gate |
| 6. IaC·배포 운영 통제 | 지원 중인 EKS/add-on 버전, 원격 state/locking 경로, 배포 권한·필수 budget 입력, CI 검증과 배포·복구 절차 | Terraform fmt/validate와 manifest 검증, 최소 권한 정책 검토, 검증 에이전트 PASS. AWS plan/apply·복구·비용/부하 실측은 별도 미완료 gate |

운영 고가용성, converter 용량 및 provider 공정성의 구체적 수치는 아래 원래 계획의 측정 항목이다. 실측 없이 상한·처리량·가용성을 충족했다고 선언하지 않는다. 운영 환경 목표가 선택되면 다중 AZ 구성을 별도 구현 단계로 추가한다.

이 6단계는 이번 서비스 경계·권한·배포 재현성 보완 범위다. 원래 계획 전체의 완료를 의미하지 않는다. 전체 runtime non-root 전환, 관측 수집기·dashboard·alert 구축, provider별 공정성/비용 제어, 운영 replica/PDB와 종료 정책은 별도 구현·검증이 남는다. AWS IAM/CNI/TLS·다중 노드·복구·부하 실측처럼 코드가 있어도 아직 실행하지 않은 검증과, 이 추가 구현 항목을 구분한다.

### 단계 간 실행 계약

- 단계 2의 migration Job 이름은 `access-migration`, `document-migration`, `ai-migration`이며 `app.kubernetes.io/component=migration`으로 식별한다. 배포는 Secret 동기화·설정·ServiceAccount 준비 → bootstrap 검증 → migration 성공 → runtime rollout 순서를 지킨다.
- Java migration은 업무 서버·scheduler를 시작하지 않는 `--migrate-only` 실행이며, AI migration은 SQL 적용 전용 프로세스다. runtime이 migration 계정 없이 자기 스키마를 사용할 수 있어야 한다.
- 로컬 Compose/base/kind는 개발 편의를 위한 자기 서비스 startup migration을 유지한다. 이 개발 실행 경로의 자기 migration credential은 AWS runtime 무DDL 계약의 예외이며, 타 서비스 credential 주입은 base/kind에서도 허용하지 않는다.
- GitHub Environment를 배포 workflow에 연결할 때 OIDC subject도 `repo:…:environment:…` 계약에 함께 맞춘다. branch subject만 허용한 role을 그대로 두지 않는다.
- 새로운 라이브러리 도입 전 설치된 MinIO Java/Python credential provider를 확인한다. 현재 두 SDK 모두 AWS 환경변수·IAM/web identity 공급자를 포함한다.
- NetworkPolicy와 EKS VPC CNI의 `enableNetworkPolicy` 설정을 함께 검증한다. Kubernetes 표준 정책의 L4/IP 허용 범위와 FQDN 제한의 한계를 명시하고, 실제 차단 검증 없이 집행 완료로 기록하지 않는다.
- 단계 3 DB 사전검증 Job은 `app.kubernetes.io/component=db-preflight`, Pod `app=<access|document|ai>-db-preflight`로 식별한다. 단계 5의 네트워크 허용 목록에는 이 Job과 migration Job의 DB 연결도 포함한다. rollback은 성공 release의 실제 schema fingerprint와 현재 값을 대조하고, 이미지 태그는 immutable로 관리한다.
- 단계 5에서는 runtime·migration의 PostgreSQL TLS 설정과 Redis 사용자/TLS 설정도 함께 대조한다. DB 사전검증 Job의 `PGSSLMODE=require`만으로 runtime의 TLS 설정을 검증했다고 보지 않는다. Redis ACL은 Access의 `auth:*`·`oauth:exchange:*`, Document의 `query:*`, AI의 `wiki:concept-index:*`와 Access·Document 공유 `authz:role:*` 계약을 실제 호출 코드에 맞춰 확인한다.

설계 기준은 [AWS database-per-service](https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-data-persistence/database-per-service.html), [EKS workload identity](https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html), [Terraform S3 backend locking](https://developer.hashicorp.com/terraform/language/backend/s3), [EKS 버전 지원 일정](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html)을 참조한다. 실제 배포 시점의 지원 버전과 계정별 설정은 별도 확인한다.

### 최신 대조 결과 반영

- 로컬 runtime/migration role의 소유 DB 접속과 runtime DML/DDL 경계는 실제 카탈로그로 확인했다. AWS 적용 여부는 미검증이다.
- converter는 이미 provider key만 개별 주입한다. 공통 Secret 전체 주입 문제는 Access·Document·AI workload에 해당한다.
- Access 부팅 필수 `MFA_ENCRYPTION_KEY`, SMTP와 `MAIL_FROM`, 공개 초대 URL을 단계 2~3의 배포 계약에 포함한다.
- 원본 AWS overlay는 렌더되지만 placeholder가 남는다. 렌더 성공을 배포 성공으로 취급하지 않는다.
- 단계 4 사전 조사(`artifact_inventory`): API의 `LocalPipelineLogReader`만 정상 제품 경로에서 worker의 로컬 파일을 교차 조회한다. 상태·manifest는 ai_db, Wiki/operation/Agent 본문은 이미 object storage에 있다. run 로그는 `pipeline-runs/{run_id}/pipeline.log`에 저장하고 running/failed/cancelled 상태에서도 조회되게 한다. 병렬 emit의 유실과 취소 rollback에 의한 로그 삭제를 막는다. CLI의 명시적 디버그 파일은 Pod 간 공유 계약에 포함하지 않는다.
- 단계 5 사전 조사(`stage6_inventory`): Access·converter는 S3 권한이 필요 없다. Document는 `sources/documents/*`·`assets/*` 읽기/쓰기/삭제 및 `wiki/*` 읽기, AI는 원본 읽기와 `wiki/*`·`agent-runs/*` 읽기/쓰기/삭제 및 `pipeline-runs/*` 읽기/쓰기가 필요하다. AI 객체 취소 복구는 AI 내부 API에 위임하며 Document에 AI 객체 쓰기 권한을 추가하지 않는다.
- Redis의 Access `SCAN`은 key ACL로 결과 이름이 필터링되지 않는다. 기존 workspace projection 일괄 무효화를 유지하는 범위에서 key 이름 열람 예외를 명시하고, 서비스별 값 접근·변경 및 Document `query-events` pub/sub 경계를 격리 Redis에서 검증한다. 이 상태를 Redis 완전 격리로 표현하지 않는다.
- S3는 없는 객체의 GET을 404로 구분하려면 `s3:ListBucket`이 필요하다([AWS GetObject 계약](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html)). AI 취소 journal의 신규 객체 판정과 최초 로그 조회를 보존하기 위해 앱 버킷의 목록 권한을 허용하고 객체 이름 공유를 명시한다. 객체 본문 읽기/쓰기/삭제 prefix 경계는 유지하며 403을 없는 객체로 처리하지 않는다.
- 단계 6 사전 조사(`stage6_inventory`): EKS 1.35와 AL2023 노드를 후보로 삼되 managed add-on build는 실제 리전의 `describe-addon-versions` 결과를 필수 입력으로 고정한다. 플랫폼 Namespace·SecretStore·StorageClass·RBAC 준비와 namespace 앱 배포를 분리한다. EKS 모듈 v20에 없는 node-group `autoscaling_group_tags` 입력을 사용하지 않고 실제 ASG tag 리소스로 scale-from-zero label/taint 정보를 관리한다. 선택한 addon 전체의 API server 검증은 AWS gate다.

### 완료 범위와 실제 AWS 미검증 항목

이전 사용자 요청으로 중단했던 단계 6의 남은 로컬 작업을 완료했다. 단계 1~6 모두 각 구현과 독립 검증을 통과했으며, 현재 코드의 서비스·DB·내부 API 경계도 다시 대조했다. 사용자 지시에 따라 실제 AWS 계정 조회·검증·리소스 생성·배포는 실행하지 않았다. 커밋·push 없이 기존 사용자 변경을 유지했다.

단계 6에 작성된 범위:

- `infra/terraform/`: S3 backend/lock, 모듈·provider lock, EKS 1.35/AL2023, managed add-on build 필수 입력, feedback profile/CIDR/budget 검증, ECR·배포 group·CA/ALB IAM 및 Spot ASG tag.
- `infra/terraform-state-bootstrap/`: state bucket 보호 설정과 별도 provider lock. 실제 bucket 생성과 backend 연결은 미실행.
- `k8s/platform/aws/`: Namespace·gp3 StorageClass·SecretStore·배포 RBAC. AWS overlay의 ESO v1 및 Kafka 4.3.0/gp3.
- `scripts/aws_deploy.py`의 플랫폼 읽기/앱 변경 분리와 `scripts/aws-platform-up.sh`의 버전 고정 설치 경로. 스크립트 작성만 완료했으며 실제 설치는 미실행.
- 실제 provider가 거부한 Redis authentication enum을 `no-password-required`로 보정. 기본 사용자 비활성화는 유지.

초기 checkpoint에서 발견한 플랫폼 설치 대상 검증 누락은 수정했고, 수동 앱 배포에도 동일한 대상 검증을 적용했다. 최종 독립 검증에서는 `scripts/aws-iac-validate.sh` 전체(양 root의 readonly lock 초기화·fmt·validate, 플랫폼 렌더·shell, 배포/권한 회귀 30개)가 통과했다. 현재 manifest의 공식 CRD 20개·Kubernetes 1.35 기본 리소스 50개도 다시 검증했다. 실제 AWS 성공을 보증하는 판정이 아니라 저장소 코드와 로컬 배포 준비 검증 완료 판정이다.

재개 작업의 완료 내역:

1. 플랫폼 설치와 수동 앱 배포가 최초 변경 전에 AWS 계정·EKS ARN·API endpoint·현재 kubeconfig 대상을 대조한다. 실제 AWS 호출 대신 fake CLI/runner로 잘못된 대상의 변경 0건을 검증했다.
2. 현행 실행·아키텍처 문서와 Terraform/AWS README를 플랫폼/앱 분리 및 고정 버전에 맞췄다. backend 입력·최초 bootstrap state 보관·잠금·plan/apply·복구 경계를 기록하고 기존 unversioned 설치 절차를 정리했다.
3. `.github/workflows/aws-iac.yml`과 `scripts/aws-iac-validate.sh`를 추가했다. CI workflow 정의를 검토하고 같은 검증 스크립트를 로컬에서 독립 실행했다. 실제 GitHub CI 실행이나 AWS 배포는 하지 않았다.
4. 이전 미해결 문제 수정과 단계 6 전체 로컬 변경에 대해 독립 검증 PASS를 받았다. MSA 경계 감사와 공식 배포 스키마 대조에서도 추가 차단 문제를 발견하지 못했다.

실제 AWS 미검증 항목은 정확한 managed add-on build 가용성, ESO/EKS 조합의 controller/admission 동작, backend 잠금·복구, RBAC 허용/거부, IRSA/IAM·RDS/Redis TLS·CNI·ALB, migration/배포/smoke/rollback, Spot 0→N·중단·복구다. 향후 별도 요청이 있을 때 검증하며, 현재 PASS로 표시하지 않는다. 실제 배포에는 계정별 입력·Secret, 고정 egress 또는 VPC 전용 feedback runner와 GitHub Environment 설정이 필요하다.

관측·provider 공정성·전체 non-root·운영 고가용성 등 이번 6단계 밖의 추가 구현은 위 범위 설명과 아래 원래 계획을 따른다.

### 진행 기록

재개 후 로컬 MSA 경계 감사(`stage6_inventory`)에서는 Access↔Document 교차 패키지 import, Converter DB 접근, AI의 타 서비스 DB 연결 및 dblink/FDW를 발견하지 못했다. DB 대상별 2회 bootstrap·DML/DDL/교차접근, 격리 Java/AI migration과 runtime, credential 2개·scheduling 1개, AI worker/인가/API 139개를 독립 재실행해 통과했다. Root의 내부 API·인가 Java 20개도 통과했다. 실제 개발 DB/Kafka에 연결하지 않았으며 실제 AWS 검증은 수행하지 않았다.

별도 로컬 스키마 감사(`stage4_artifacts`)는 공식 index의 SHA256을 확인한 ALB 3.5.0·ESO 2.9.0·Strimzi 1.1.0·KEDA 2.20.2 chart를 Kubernetes 1.35 대상으로 렌더했다. 앱/platform CR 20개의 고정 CRD 스키마·알 수 없는 필드 검사, 기본 리소스 50개 및 chart 기본 리소스 117개의 Kubernetes 1.35 OpenAPI 대조가 통과했다. Strimzi의 Kafka 4.3.0 이미지 매핑도 확인했다. CEL·admission webhook·controller reconciliation은 실행하지 않았으며 실제 클러스터와 AWS에 접속하지 않았다.

| 단계 | 구현 | 독립 검증 | 증거·남은 조건 |
|---|---|---|---|
| 1 | 완료 (`stage1_db`) | PASS (`verify_stage1`) | 독립 재실행: `bash infra/postgres/test-db-isolation.sh`, 실제 Docker entrypoint Unix socket 초기화, 위험 role 사전 거부, shell/Compose/Kustomize/원본 사본 일치 통과. 실제 RDS/TLS는 미검증 |
| 2 | 완료 (`stage2_credentials`) | PASS (`verify_stage2`) | 독립 재실행: 운영 설정 `--rerun`, credential manifest 2개, 실제 migration 각 2회·runtime 기동·AI 전체 schema·권한 검사 통과. 최초 runtime 테스트의 개발 Kafka group join/leave는 격리 증거에서 제외(소비/offset commit 여부 확인 불가). 임시 PostgreSQL·Redis, 비활성 Kafka listener와 격리 endpoint로 보완한 재실행만 통과 근거로 사용 |
| 3 | 완료 (`stage3_deploy`) | PASS (`verify_stage3`, 2건 수정 후 재검증) | 동일 SHA 설정·manifest·실제 schema 불일치와 AI URI 대상/TLS query 우회를 수정. 임시 PostgreSQL 포함 AWS 테스트 12개 독립 재실행 통과. 실제 AWS/RDS TLS는 미검증 |
| 4 | 완료 (`stage4_artifacts`) | PASS (`stage3_deploy`, 단계 4 구현 미참여) | Python 회귀 80개, AWS 통합 계약 13개 독립 재실행 통과. API→object storage 조회·취소/병렬 로그·PVC 제거·Spot 배치 확인. 실제 다중 노드/Spot 중단 미검증 |
| 5 | 완료 (`stage6_inventory`) | PASS (`stage4_artifacts`, 1건 수정 후 재검증) | 기존 넓은 정책 명시적 삭제·삭제 실패 시 배포 중단 확인. AWS 21개·Python 83개·실제 Java SDK/Lettuce·임시 migration/runtime/DB권한 독립 재실행 통과. 실제 IAM·CNI·IRSA·TLS·ALB는 미검증 |
| 6 | 로컬 구현 완료 (`stage3_deploy`) | PASS (`stage4_artifacts`, 이전 checkpoint 지적 수정 후 재검증) | 양 root readonly init/fmt/validate·배포/권한 30개·공식 CRD 20개/native 50개 독립 통과. IAM/RBAC/ASG·CI/runner/OIDC·state/복구 문서 대조 완료. 실제 AWS 검증 미실행 |

아래는 최초 조사 시점의 상세 계획이다. 최신 실행 범위와 통과 여부는 위 표가 우선하며, 구현 완료 사실은 관련 현행 문서에도 반영한다.

검토 기준: 2026-08-23

이 문서는 현재 로컬·kind 기준 MSA를 AWS에 실제 배포하고, 여러 사용자의 장시간 AI 작업을 안정적으로 처리하기 위해 남은 보완 사항을 정리한다. 아직 적용되지 않은 작업 계획이므로 현행 아키텍처 문서가 아니라 backlog에서 관리한다. 구현이 끝난 항목은 이 문서의 완료 조건을 검증한 뒤 `docs/architecture.md`, `docs/data-model.md`, `docs/script.md`와 관련 ADR에 현재 상태를 반영한다.

## 1. 현재 상태와 목표

현재 배포 구조는 서비스마다 Kubernetes cluster를 만드는 방식이 아니다. 하나의 EKS cluster 안에서 애플리케이션을 Deployment로 분리하고, AI 작업은 Kafka topic·consumer group과 node group으로 격리하는 구조다.

```text
Vercel
└─ frontend
   ├─ api.<domain>    → ALB → document-svc
   └─ access.<domain> → ALB → access-svc

Amazon EKS
├─ API: access-svc · document-svc · pipeline-api
├─ AI: ingest · query · agent · maintenance worker
├─ 변환: converter
└─ event: Strimzi Kafka + KEDA

AWS managed state
├─ RDS PostgreSQL: access instance · core/ai instance
├─ ElastiCache Redis
└─ S3
```

현재 구현에서 확인된 기반:

- Access·Document·AI가 독립 배포 단위이고 데이터 소유권이 분리돼 있다.
- Document와 AI 사이의 장시간 작업은 Kafka command/result topic으로 비동기 처리한다.
- 작업 종류별 consumer group과 KEDA `ScaledObject`가 존재한다.
- Outbox, 수동 offset commit, run 상태와 결과 receipt로 at-least-once 전달의 중복을 흡수한다.
- Terraform에 VPC, EKS, RDS, ElastiCache, S3, ECR, Secrets Manager, GitHub OIDC, Budget이 정의돼 있다.
- `k8s/overlays/aws`는 `kubectl kustomize`로 렌더된다.

목표는 다음 두 단계를 구분한다.

1. **사용자 피드백 배포**: 단일 장애점과 제한된 처리량을 명시적으로 허용하되, 배포·복구·비용·보안을 검증한다.
2. **운영 배포**: AZ 또는 node 장애를 견디고, 부하와 외부 LLM 제한에 맞춰 자동 확장하며, 관측·복구·권한 최소화를 충족한다.

## 2. P0 — 첫 AWS 배포 전 차단 항목

### 2.1 EKS Kubernetes version 갱신

현재 `infra/terraform/variables.tf` 기본값은 `1.31`이다. 2026-08-23 기준 EKS 1.31은 extended support 상태이며 2026-11-26에 extended support가 끝난다. extended support cluster는 control plane 요금이 $0.10/h에서 $0.60/h로 6배(월 약 +$365)가 되므로 비용 관점에서도 차단 항목이다. 신규 cluster에는 적용 시점에 standard support인 version을 사용한다. 2026-08-23 기준 standard support version은 1.34(standard 종료 2026-12-02)·1.35·1.36이며, 1.34는 약 3개월 뒤 extended로 전환되므로 신규 cluster는 1.35 이상을 우선 검토한다.

수정 대상:

- `infra/terraform/variables.tf`
- 필요 시 `infra/terraform/versions.tf`
- `infra/terraform/README.md`
- `k8s/kind/cluster.yaml`

작업:

- 배포 시점의 EKS standard support version을 조회한다.
- Strimzi, KEDA, AWS Load Balancer Controller, External Secrets Operator, EBS CSI Driver, Cluster Autoscaler 호환표를 확인하고 version을 고정한다.
- cluster와 add-on version을 한 번에 무검증 갱신하지 않고 kind 또는 별도 검증 cluster에서 manifest를 먼저 확인한다.

완료 조건:

- 선택한 Kubernetes version이 AWS standard support 범위다.
- 모든 CRD와 manifest가 server-side dry-run 또는 검증 cluster에서 성공한다.
- add-on version과 갱신 절차가 `docs/script.md`에 기록된다.

### 2.2 AWS overlay의 placeholder 자동 주입

현재 AWS overlay에는 다음 값이 `REPLACE_ME_*`로 남아 있고, GitHub Actions는 image URI와 tag만 바꾼다.

- ECR account/repository
- Access/Core RDS endpoint
- Redis endpoint
- S3 bucket
- ACM certificate ARN
- API domain
- Vercel application domain

수정 대상:

- `k8s/overlays/aws/kustomization.yaml`
- `k8s/overlays/aws/configmap-aws.yaml`
- `k8s/overlays/aws/ingress.yaml`
- `.github/workflows/deploy.yml`
- 필요 시 배포 전용 script

작업:

- 민감하지 않은 endpoint와 domain의 단일 원본을 Terraform output 또는 GitHub Environment variable로 정한다.
- CI가 원본 파일을 영구 수정하지 않고 임시 render directory에서 Kustomize 값을 주입하도록 한다.
- `kubectl apply` 전에 렌더 결과에서 `REPLACE_ME`를 검색해 하나라도 남으면 실패시킨다.
- production GitHub Environment에 승인 gate를 둔다.

완료 조건:

- 저장소의 placeholder를 수동 편집하지 않아도 동일 workflow로 재배포할 수 있다.
- 배포 전 단계가 미정 값, 빈 domain, 빈 certificate ARN을 차단한다.
- 최종 manifest와 secret 값은 workflow log에 노출되지 않는다.

### 2.3 Terraform state와 plan 통제

현재 Terraform remote backend가 없고 local state를 전제로 한다. 여러 환경이나 CI에서 실행하면 state 유실·동시 적용·비밀값 노출 위험이 있다.

수정 대상:

- `infra/terraform/versions.tf`
- bootstrap용 별도 Terraform 또는 수동 생성 절차
- `.gitignore`
- `infra/terraform/README.md`

작업:

- S3 remote state와 locking 방식을 정한다.
- state bucket에 versioning, encryption, public access block을 적용한다.
- dev 또는 feedback 환경과 production state를 분리한다.
- provider와 module lock file을 검토·커밋한다.
- `rds.tf`의 `engine_version = "16"`은 major만 고정돼 minor가 자동 갱신될 수 있다. 재현성을 위해 minor까지 고정할지, auto minor upgrade를 허용할지 결정해 기록한다.
- `fmt -check → init → validate → plan`을 PR 검증 단계로 추가하고, `apply`는 승인된 환경에서만 수행한다.
- Terraform state에는 DB password와 S3 access key가 포함될 수 있으므로 접근자를 제한한다.

완료 조건:

- 두 실행 주체가 동시에 apply할 수 없다.
- 새 작업 환경에서도 같은 state를 조회해 동일 plan을 만든다.
- plan artifact와 workflow log에 secret 평문이 남지 않는다.

### 2.4 RDS database·role bootstrap 자동화 또는 명확한 gate

Terraform은 RDS instance만 만들고 `access_db`, `core_db`, `ai_db`와 runtime/migration role은 `infra/postgres/init-db-isolation.sh`로 별도 생성한다. 이 단계를 생략하면 application rollout이 실패한다.

수정 대상:

- `infra/postgres/init-db-isolation.sh`
- `infra/postgres/validate-db-isolation.sh`
- `infra/terraform/README.md`
- `.github/workflows/deploy.yml` 또는 별도 bootstrap workflow

작업:

- EKS 내부 Job, 제한된 bastion 또는 일회성 operator command 중 실행 경계를 결정한다.
- Access RDS에는 `access_db`만, Core RDS에는 `core_db`와 `ai_db`만 생성한다.
- Secrets Manager 비밀번호와 role 비밀번호가 같은지 검증한다.
- runtime role의 DDL 및 타 database 쓰기를 차단하고 migration role만 schema 변경 권한을 갖게 한다.
- bootstrap 완료 전 application deploy를 시작하지 않는다.

완료 조건:

- 빈 AWS 계정에서 문서화된 한 경로로 database와 role이 재현된다.
- `validate-db-isolation.sh`가 own DML 허용, cross-database write 거부, public schema create 거부를 확인한다.
- bootstrap 재실행이 안전하다.

### 2.5 배포 workflow 완결

현재 rollout 확인 대상에는 `query-task-worker`, `agent-task-worker`, `maintenance-task-worker`, `pipeline-agent-worker`가 빠져 있고 smoke test는 비활성화돼 있다. 실패한 worker를 놓친 채 workflow가 성공할 수 있다.

수정 대상:

- `.github/workflows/deploy.yml`

작업:

- 모든 Deployment와 필요한 Stateful workload의 rollout을 확인한다.
- `ExternalSecret Ready`, Strimzi Kafka Ready, KafkaTopic Ready, KEDA ScaledObject Ready를 확인한다.
- DB migration 완료 이후 application readiness를 확인한다.
- `api.<domain>`과 `access.<domain>`의 비파괴 smoke test를 활성화한다.
- 이전 정상 image SHA로 rollback하는 workflow 또는 runbook을 둔다.
- image scan의 critical finding 처리 정책을 정한다.

완료 조건:

- worker 하나라도 crash loop이면 workflow가 실패한다.
- 공개 API smoke test가 실패하면 배포 성공으로 표시되지 않는다.
- 이전 image로 복구하는 절차를 한 번 실검증한다.

## 3. P1 — 다중 사용자 AI 처리 전 필수 보완

### 3.1 `pipeline-runs` 공유 PVC 제거와 AI worker stateless 전환

현재 `pipeline-api`와 `ingest-worker`는 `pipeline-runs` ReadWriteOnce EBS PVC를 공유한다. AWS overlay는 ingest worker를 pipeline API와 같은 node에 강제 배치한다. 이 상태에서는 KEDA가 Pod를 늘려도 여러 node와 AZ로 자유롭게 분산할 수 없고, Terraform의 AI Spot node group도 사용할 수 없다.

수정 대상:

- AI pipeline의 run artifact 저장 adapter
- `k8s/base/pipeline-api.yaml`
- `k8s/base/ingest-worker.yaml`
- `k8s/overlays/aws/kustomization.yaml`
- `infra/terraform/s3.tf`
- 관련 AI test와 current docs

작업:

- `/app/runs`에 남는 파일의 종류, 수명, 조회 주체를 먼저 분류한다.
- 영속 artifact는 S3 key 규약으로 이전하고 임시 파일만 Pod `emptyDir`를 사용한다.
- database 상태와 object artifact의 완료 순서 및 재처리 규칙을 정의한다.
- PVC, required podAffinity와 node-local 가정을 제거한다.
- 동일 run 재처리 시 artifact 중복·부분 파일을 흡수하도록 idempotent key를 사용한다.
- S3 gateway VPC endpoint를 추가한다. 무료이며, artifact를 S3로 옮기면 private subnet의 S3 트래픽이 NAT를 경유해 처리비($0.059/GB)가 발생하는 것을 제거한다.

완료 조건:

- pipeline API와 ingest worker를 서로 다른 node에서 실행해도 같은 run을 처리·조회할 수 있다.
- worker Pod를 작업 도중 종료해도 재전달 후 결과가 한 번만 최종 반영된다.
- ingest worker 2개 이상을 서로 다른 node에 배치한 통합 검증이 통과한다.

### 3.2 AI node scheduling 실제 연결

Terraform에는 `fruition.io/node-role=ai-worker` label과 `fruition.io/ai-worker=true:NoSchedule` taint를 가진 Spot node group이 있지만, AI workload에는 이를 선택하는 scheduling 설정이 없다.

수정 대상:

- `k8s/overlays/aws/kustomization.yaml`
- 필요 시 AI workload별 patch
- `infra/terraform/eks.tf`

작업:

- stateless 전환 후 ingest, query, agent, maintenance, converter 중 Spot 허용 workload를 분류한다.
- 해당 Pod에 `nodeSelector` 또는 node affinity와 `tolerations`를 추가한다.
- 중단 민감 API·Kafka·controller는 On-Demand general node에 남긴다.
- Spot interruption 시 Kafka 재전달과 durable run 상태로 복구되는지 확인한다.
- worker별 CPU·memory request를 실측하고 node가 실제로 scale-out 가능한 조합으로 맞춘다.

완료 조건:

- Kafka lag 증가 → KEDA Pod 증가 → pending Pod 발생 → AI node group 증가가 순서대로 관측된다.
- Spot worker 종료 후 작업이 유실되지 않는다.
- 부하 종료 후 worker Pod와 AI node가 설정된 cooldown 뒤 축소된다.

### 3.3 converter 동시 처리 정책

converter는 현재 1 replica의 내부 HTTP service이고 Kafka/KEDA 확장 대상이 아니다. OCR·PDF 복원은 CPU·memory와 실행시간이 커서 여러 사용자의 동시 업로드에서 별도 병목이 될 수 있다.

수정 대상 후보:

- `services/ai/converter`
- document 변환 queue 경계
- `k8s/base/converter.yaml`
- 필요 시 Kafka topic과 KEDA 설정

작업:

- 먼저 동시 PDF 1·3·5건의 처리시간, memory peak, timeout을 측정한다.
- 단일 Pod에서 허용할 동시 작업 수를 제한한다.
- 단순 replica/HPA로 충분한지, `convert.command` Kafka worker가 필요한지 측정 결과로 결정한다.
- HTTP 900초 연결을 유지하는 현재 경계를 계속 사용할 경우 caller 재시도와 중복 변환 방지 규칙을 검증한다.

완료 조건:

- 정해진 최대 크기 PDF 동시 처리에서 OOM과 무제한 대기가 발생하지 않는다.
- timeout 또는 Pod 종료 후 같은 변환이 중복 반영되지 않는다.
- queue 대기시간과 변환 처리시간을 분리해 관측할 수 있다.

### 3.4 외부 LLM rate limit·비용·공정성 제어

KEDA가 worker를 늘려도 provider의 RPM, TPM, 동시 요청, 429 제한과 비용 상한은 늘어나지 않는다. Pod 수만 늘리면 429와 재시도 비용이 더 커질 수 있다.

수정 대상 후보:

- AI provider client 공통 경계
- Kafka command admission 경계
- workspace/user 설정과 사용량 저장소
- 운영 metric과 alert

작업:

- provider/model별 timeout, retry 횟수, exponential backoff와 jitter를 통일한다.
- workspace/user별 동시 실행 수와 queue 진입률을 제한한다.
- 작업별 최대 토큰·시간·재시도 budget을 둔다.
- provider 429·5xx와 영구 실패를 구분한다.
- poison command를 무한 재처리하지 않도록 DLQ 또는 durable failed-command 저장소와 운영 재처리 절차를 둔다.
- run별 provider/model, token, latency, retry, 예상 비용을 기록한다.

완료 조건:

- 한 사용자의 대량 요청이 다른 workspace 작업을 무기한 막지 않는다.
- 429 상황에서 요청 폭증 없이 제한된 backoff로 회복한다.
- 동일 작업의 총 재시도와 최대 비용이 상한을 넘지 않는다.
- 운영자가 실패 작업을 조회하고 선택적으로 재처리할 수 있다.

### 3.5 KEDA와 Kafka 용량 기준 검증

현재 command topic은 각각 12 partition이고 KEDA max replica는 ingest/query/agent 4, maintenance 2다. `lagThreshold`는 초기값일 뿐 실제 작업시간과 목표 대기시간으로 검증되지 않았다.

작업:

- workload별 평균·p95 처리시간과 목표 queue 대기시간을 정한다.
- `필요 처리율 = 유입률`, `필요 worker ≈ 유입률 × 평균 처리시간`으로 초기 replica 상한을 산정한다.
- partition key가 같은 document/run의 순서를 보장하면서 workspace 간 병렬성을 막지 않는지 검증한다.
- 긴 작업의 `max.poll.interval`, graceful termination, consumer rebalance 시간을 부하에서 확인한다.
- Kafka broker, DB connection pool, provider limit 중 실제 병목을 구분한다.

완료 조건:

- 동시 사용자 단계별 테스트에서 queue lag가 목표 시간 안에 감소한다.
- worker 증가가 provider 429, DB connection exhaustion, Kafka rebalance 폭증을 만들지 않는다.
- 측정값을 근거로 partition, lag threshold, min/max replica를 기록한다.

## 4. P1 — 보안과 권한 보완

### 4.1 S3 정적 access key를 workload role로 교체

현재 Terraform은 application IAM user와 장기 access key를 만들어 Secrets Manager에 저장한다. 유출·회전 부담을 줄이기 위해 AWS SDK default credential chain과 IRSA 또는 EKS Pod Identity를 사용한다.

작업:

- Java와 Python object storage adapter가 endpoint 명시 없이 AWS credential provider chain을 사용할 수 있게 한다.
- S3를 사용하는 ServiceAccount에만 bucket 최소 권한 role을 연결한다.
- MinIO local profile과 AWS profile의 credential 경계를 분리한다.
- 기존 IAM user와 access key를 제거하고 유출 여부를 점검한다.

완료 조건:

- Kubernetes Secret에 `S3_ACCESS_KEY`, `S3_SECRET_KEY`가 없다.
- 각 Pod는 허용된 bucket/prefix 외 접근이 거부된다.
- credential rotation 없이 임시 자격증명이 자동 갱신된다.

### 4.2 Secret 최소 노출

현재 하나의 `fruition-secret`을 대부분의 Pod가 `envFrom`으로 읽는다. 그 결과 S3 key, DB password, JWT secret, internal token, 모든 provider key가 필요하지 않은 workload에도 전달된다.

작업:

- access, document, pipeline, converter별 ExternalSecret과 ServiceAccount를 분리한다.
- workload가 실제 사용하는 key만 주입한다.
- provider key가 Kafka payload, application log, error response에 포함되지 않는지 검증한다.
- secret rotation 시 재배포 또는 reload 절차를 정한다.

완료 조건:

- converter가 access/core DB password를 읽지 못하고 access-svc가 LLM provider key를 읽지 못한다.
- secret 변경과 token 회전 runbook이 검증된다.

### 4.3 EKS API와 GitHub deploy 권한 축소

현재 EKS public endpoint CIDR 기본값은 `0.0.0.0/0`이고 GitHub deploy role은 cluster-wide admin이다.

작업:

- GitHub-hosted runner 유지, self-hosted runner, VPN/private endpoint 중 운영 방식을 결정한다.
- public endpoint를 유지하면 접근 CIDR과 audit log를 제한·관측한다.
- deploy role을 `fruition` namespace와 필요한 CRD 작업으로 축소한다.
- Terraform 변경 권한과 application deploy 권한을 분리한다.
- production environment 승인자를 설정한다.

완료 조건:

- application deploy role이 IAM, VPC, RDS를 변경할 수 없다.
- 다른 namespace의 Secret과 workload를 조회·변경할 수 없다.
- 허가되지 않은 network에서 EKS API 접근이 차단된다.

### 4.4 Pod와 network 기본 보안

현재 converter만 non-root, read-only root filesystem, capability drop을 명시한다. Java image와 pipeline image는 root로 실행되며, NetworkPolicy는 일부 내부 service ingress만 제한하고 default deny와 egress 제한은 없다. Kafka 내부 listener도 plain text다.

작업:

- 모든 runtime image에 non-root user를 둔다.
- `runAsNonRoot`, `allowPrivilegeEscalation: false`, capability drop, seccomp profile을 공통 적용한다.
- 쓰기가 필요한 경로만 `emptyDir` 또는 volume으로 제공하고 가능한 workload는 read-only root filesystem을 사용한다.
- default-deny ingress/egress 뒤 필요한 service, DNS, RDS, Redis, S3, provider endpoint만 허용한다.
- Kafka TLS·인증 도입 시점은 사용자 피드백 환경과 운영 환경을 구분해 결정한다.
- Pod가 Kubernetes API를 쓰지 않으면 service account token 자동 mount를 끈다.

완료 조건:

- container가 root와 추가 Linux capability 없이 실행된다.
- pipeline/converter가 ALB에서 직접 접근되지 않는다.
- 의도하지 않은 service 간 연결과 metadata endpoint 접근이 차단된다.

## 5. P1 — 관측, 복구, 배포 운영

### 5.1 관측성 구축

현재 application에는 request/run identifier가 있으나 AWS overlay에는 metric 수집기, dashboard, alert가 정의돼 있지 않다.

필수 metric:

- API request rate, error rate, p50/p95/p99 latency
- Kafka topic별 lag, consumer rebalance, 처리 성공·실패·재시도
- AI run queue time과 execution time
- provider별 429·5xx·timeout, token과 비용
- Pod CPU·memory·restart·OOMKill·pending 시간
- node scale-out/in 시간과 Spot interruption
- RDS connection, CPU, storage, slow query, deadlock
- Redis memory, eviction, connection
- S3 error와 artifact 크기

작업:

- CloudWatch Container Insights, Amazon Managed Prometheus/Grafana 또는 자체 stack 중 하나를 선택한다.
- `requestId`, `flowId`, `run_id`, `workspace_id`의 log correlation 규칙을 통일한다. 사용자 입력과 secret은 log에 남기지 않는다.
- 사용자 영향 기준 alert와 운영 dashboard를 만든다.

완료 조건:

- 단일 run ID로 document 발행부터 AI worker와 최종 결과 반영까지 추적할 수 있다.
- queue 지연, provider 장애, OOM, DB 포화가 사용자 신고 전에 alert로 드러난다.
- alert별 1차 대응 runbook이 존재한다.

### 5.2 무중단 배포와 종료 처리

현재 대부분의 API와 Kafka가 1 replica이고 PodDisruptionBudget, topology spread, 명시적 termination grace 검증이 없다.

작업:

- 가용성이 필요한 API를 2 replica 이상으로 전환한다.
- topology spread 또는 anti-affinity로 AZ/node를 분산한다.
- PodDisruptionBudget을 추가한다.
- Kafka worker가 SIGTERM 시 새 message 수신을 멈추고 현재 작업·offset을 안전하게 종료하는지 검증한다.
- `preStop`, `terminationGracePeriodSeconds`, max task time의 관계를 정한다.
- schema migration과 application rollout 순서를 분리한다.

완료 조건:

- node drain과 rolling deploy 중 공개 API가 목표 SLO를 유지한다.
- 작업 중 worker 종료로 최종 결과가 유실되거나 중복 적용되지 않는다.
- migration 실패 시 application rollout이 중단되고 복구 절차가 작동한다.

### 5.3 Backup·restore와 재해 복구

현재 RDS backup 7일과 S3 versioning은 정의돼 있으나 실제 restore 검증과 RPO/RTO는 없다. Kafka·Redis는 사용자 피드백 profile에서 단일 node다.

작업:

- access/core/ai 데이터별 RPO와 RTO를 정한다.
- RDS snapshot/PITR 복구와 S3 version 복원을 별도 환경에서 실검증한다.
- Redis 유실 시 재구성 가능한 상태와 유실되는 실시간 상태를 명시한다.
- Kafka broker/PVC 유실 시 outbox와 durable run을 기준으로 어떤 command를 재발행할지 runbook을 만든다.
- Terraform destroy와 종료 전에 final snapshot·artifact 보존 정책을 확인한다.

완료 조건:

- 문서화된 절차로 빈 환경에 DB와 object를 복원한다.
- restore 결과의 데이터 정합성을 검증한다.
- 측정된 복구 시간이 선언한 RTO 안에 든다.

### 5.4 부하·장애·비용 검증

동시 사용자 지원은 manifest 존재가 아니라 측정 결과로 증명한다.

검증 시나리오:

1. 동시 사용자 1·5·10·20명으로 query, agent, ingest를 각각 실행한다.
2. 혼합 workload에서 사용자별 대기시간과 공정성을 확인한다.
3. 작업 중 worker를 종료하고 재처리·멱등 반영을 확인한다.
4. Kafka broker, Redis, Access API를 차례로 중단해 허용된 장애 동작을 확인한다.
5. provider 429·timeout을 주입해 backoff와 비용 상한을 확인한다.
6. KEDA Pod scale과 node autoscale의 상승·하강 시간을 확인한다.
7. 이전 image SHA rollback을 실행한다.

기록할 결과:

- 성공률
- queue wait p50/p95/p99
- execution time p50/p95/p99
- 최대 Kafka lag와 회복시간
- provider 오류와 retry 횟수
- CPU·memory·DB connection peak
- run당 token·비용과 전체 시간당 비용
- scale-out/in 및 장애 복구 시간

예상 고정비 baseline (2026-08 ap-northeast-2 on-demand 요금 근사, 730h/월):

| 항목 | 구성 | 월 비용 근사 |
|---|---|---|
| EKS control plane | $0.10/h | ~$73 |
| General node | t3.large × 2 (On-Demand 상시) | ~$150 |
| AI worker node | m5.xlarge Spot, desired 0 | 유휴 시 $0, 확장 시 종량 |
| NAT Gateway | 단일, $0.059/h + $0.059/GB | ~$43 + 트래픽 |
| RDS | db.t4g.small × 2, gp3 30GB, Single-AZ | ~$60 |
| ElastiCache | cache.t4g.micro × 1 | ~$15 |
| ALB | $0.0225/h + LCU | ~$17 + LCU |
| EBS·S3·ECR·Secrets·CloudWatch | 소량 | ~$10–20 |
| **합계** | | **약 $370–420 + 변동비** |

비용 주의 사항:

- `budgets.tf`는 `budget_email`이 비어 있으면 budget alarm을 아예 생성하지 않는다. 첫 배포 전 필수 입력값으로 다룬다.
- baseline은 $500 warn budget 안에 들지만 여유가 약 $80–130뿐이다. NAT 트래픽, CloudWatch log 수집(§5.1 관측성 설치 시), LLM API 사용량이 변동비로 얹힌다.
- EKS 1.31을 유지한 채 배포하면 extended support 요금 +$365/월이 더해져 $700 high budget을 초과할 수 있다. §2.1이 선행돼야 하는 비용 근거다.
- 상시 고정비의 최대 항목은 General node 2대다. 사용자 피드백 기간 요금을 낮추려면 Compute Savings Plans 또는 (검증 후) general node 1대 축소를 검토하되, §5.2 무중단 배포 요건과 상충하므로 단계적으로 결정한다.

완료 조건:

- 사용자 피드백 환경의 동시 사용자 상한을 수치로 선언한다.
- 상한 초과 시 무제한 실패가 아니라 queue, rate limit 또는 명시적 거부로 보호된다.
- 월 예상 고정비와 workload별 변동비가 Budget 기준 안에 든다.

## 6. P2 — 운영 가용성과 비용 최적화

사용자 피드백 배포에서는 아래 단일 장애점을 명시적으로 허용할 수 있다. 운영 배포로 전환할 때는 별도 결정과 검증이 필요하다.

| 현재 | 운영 전환 후보 | 전환 기준 |
|---|---|---|
| Kafka broker 1, replication 1 | 3 broker·다중 AZ Strimzi 또는 MSK | broker 장애 중에도 command 접수·처리가 필요할 때 |
| RDS Single-AZ | Multi-AZ, 성능·연결 수 재산정 | 선언한 RPO/RTO가 Single-AZ 복구시간보다 짧을 때 |
| Redis single node | replication group·Multi-AZ failover | 캐시·SSE 상태 유실이 허용 범위를 넘을 때 |
| NAT Gateway 1 | AZ별 NAT 또는 VPC endpoint | AZ 장애 내성과 egress 비용 측정 후 |
| API 1 replica | 2개 이상·AZ 분산·PDB | 실제 사용자가 지속 접속하는 시점 |
| General `t3.large` | 비버스터블 또는 workload 맞춤 instance | CPU credit와 지연 변동이 SLO에 영향을 줄 때 |
| Cluster Autoscaler | 유지 또는 Karpenter 검토 | workload 종류와 Spot instance 선택 폭이 커질 때 |

EKS를 서비스별 cluster로 분리하지 않는다. 보안·규제·조직 소유권 때문에 control plane 격리가 반드시 필요한 시점 전까지는 하나의 cluster에서 namespace, ServiceAccount, NetworkPolicy, node scheduling과 quota로 격리한다. 서비스별 node group 남발도 피하고 workload 자원 특성이 실제로 다를 때만 분리한다.

## 7. 문서 정합성 수정

구현과 함께 다음 문서 불일치를 해소한다.

- `infra/terraform/README.md` 상단은 Access/Core RDS 2대를 설명하지만 `한계`에는 단일 RDS와 물리 분할 미적용이라고 적혀 있다. 실제 `rds.tf` 기준으로 고친다.
- `infra/terraform/eks.tf` 주석은 ingest·converter가 AI Worker node를 사용한다고 설명하지만 현재 manifest에는 해당 toleration/node selector가 없다. 현재 상태 또는 선행 조건을 명시한다.
- `docs/architecture.md`의 “코드 변경 0, env만 교체” 표현은 공유 PVC의 S3 전환, IAM role 전환, placeholder 자동화가 끝나기 전까지 제한사항을 함께 표시한다.
- AWS 배포를 실제 검증하기 전에는 `배포 가능`, `다중 사용자 보장`, `운영 환경` 같은 완료 표현을 사용하지 않는다.
- 구현 완료 시 이 backlog 문서만 고치지 않고 현행 문서와 ADR을 같은 변경에서 갱신한다.

## 8. 권장 실행 순서와 gate

| 단계 | 작업 | 다음 단계 진입 조건 |
|---|---|---|
| 1 | EKS/add-on version 갱신, overlay placeholder 자동화, remote state | 정적 검증과 plan 성공 |
| 2 | DB bootstrap gate, secret 주입, deploy/rollback workflow 완결 | 빈 환경 배포 절차 재현 |
| 3 | 제한된 AWS 사용자 피드백 환경 최초 배포 | 모든 workload Ready, smoke test 성공 |
| 4 | 관측성 설치와 기준 부하 측정 | 병목·비용 baseline 확보 |
| 5 | pipeline artifact S3 이전, AI node scheduling 연결 | worker 다중 node 확장 성공 |
| 6 | provider rate limit, quota, DLQ, converter 정책 | 혼합 부하와 장애 검증 성공 |
| 7 | 권한 최소화, non-root, NetworkPolicy, restore 검증 | 보안·복구 gate 통과 |
| 8 | 필요할 때만 Multi-AZ Kafka/RDS/Redis와 API HA | 운영 SLO·RPO·RTO 충족 |

## 9. 완료 정의

AWS 배포 준비 완료는 다음 조건을 모두 만족할 때 선언한다.

- 적용 시점에 standard support인 EKS와 호환되는 add-on version을 사용한다.
- repository 수동 편집 없이 Terraform output에서 배포 manifest가 생성된다.
- remote state, locking, plan 승인, rollback 경로가 작동한다.
- DB bootstrap과 권한 격리 검증이 재현된다.
- 모든 API와 worker rollout 및 smoke test가 자동 검증된다.
- AI worker가 공유 PVC 없이 여러 node에서 처리된다.
- Kafka lag에 따라 Pod와 node가 확장·축소된다.
- provider rate limit, 사용자 공정성, 비용 상한과 실패 재처리가 동작한다.
- 장기 AWS access key 없이 workload role을 사용한다.
- workload별 secret·IAM·network·container 권한이 최소화돼 있다.
- request/run 단위 추적과 핵심 alert가 동작한다.
- backup restore, worker 종료, provider 오류, rollback을 실검증했다.
- 지원 가능한 동시 사용자 수와 비지원 조건을 측정값으로 설명할 수 있다.

## 10. 지원서·면접에서 사용할 수 있는 표현 기준

AWS 실제 배포 전:

> Access·Document·AI의 책임과 데이터 소유권을 분리하고, 장시간 LLM 작업을 Kafka command/result topic으로 비동기화했습니다. 작업 종류별 consumer group과 KEDA 확장 정책을 구성했으며, kind에서 배포 단위를 검증하고 EKS·RDS·ElastiCache·S3로 전환하기 위한 Terraform과 Kustomize 구성을 준비했습니다.

AWS 최초 배포 후:

> Terraform과 GitHub OIDC 기반 배포 파이프라인으로 AWS 환경을 재현하고, RDS·ElastiCache·S3와 EKS workload를 연결해 공개 API smoke test까지 검증했습니다.

다중 사용자 부하 검증 후:

> 동시 작업 부하에서 Kafka lag를 기준으로 AI worker와 node가 확장되는 과정을 검증하고, queue 대기시간·실패율·provider 제한·비용을 측정해 replica와 rate limit 기준을 조정했습니다.

검증하지 않은 `무중단`, `고가용성`, `여러 사용자가 문제없이 사용`, `production-ready` 표현은 사용하지 않는다.

## 참고

- 현행 구조: [`../architecture.md`](../architecture.md)
- 현행 데이터 소유권: [`../data-model.md`](../data-model.md)
- 현행 실행 절차: [`../script.md`](../script.md)
- 기존 AWS 목표 구조: [`Fruition_AWS_MSA_Architecture.md`](Fruition_AWS_MSA_Architecture.md)
- AWS overlay: [`../../k8s/overlays/aws/README.md`](../../k8s/overlays/aws/README.md)
- Terraform: [`../../infra/terraform/README.md`](../../infra/terraform/README.md)
- [Amazon EKS version lifecycle](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html)
- [Amazon EKS reliability best practices](https://docs.aws.amazon.com/eks/latest/best-practices/reliability.html)
- [Running highly available applications on EKS](https://docs.aws.amazon.com/eks/latest/best-practices/application.html)
- [Amazon EKS data plane scaling](https://docs.aws.amazon.com/eks/latest/best-practices/scale-data-plane.html)
- [Amazon S3 security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html)
- [Amazon MSK best practices](https://docs.aws.amazon.com/msk/latest/developerguide/bestpractices.html)
