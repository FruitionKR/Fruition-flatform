# AWS feedback IaC

현행 절차는 [docs/script.md의 IaC·플랫폼 운영](../../docs/script.md#aws-iac플랫폼-운영-절차)을 따른다. 이 root는 project=fruition, 서울 region, EKS 1.35/AL2023, feedback Environment를 검증한다. 실제 AWS 조회·plan/apply·설치·복구는 이번 로컬 작업에서 수행하지 않았다.

| 구성 | 책임 |
|---|---|
| VPC / EKS | 2 AZ, General 2대, AI Worker 0–2대 Spot, 명시적 API CIDR·addon build |
| RDS | Access/Core PostgreSQL 16 인스턴스 2대, core/ai는 Core RDS 내 별도 DB·role |
| Redis | 7.1 single primary replication group, TLS·서비스별 ACL |
| S3 | versioning, Document/AI IRSA prefix 권한, 정적 앱 key 없음 |
| ECR / GitHub | 네 repository immutable SHA, 제한된 ECR/DescribeCluster role, namespace RBAC 그룹 |
| Secrets Manager | DB·Redis·내부 token·MFA/SMTP 원본, 서비스별 ExternalSecret 투영 |
| Budget | 필수 수신 이메일로 $500/$700 알림 |
| State | 별도 bootstrap bucket의 S3 encrypted backend/native lockfile |

로컬 검증:

    bash scripts/aws-iac-validate.sh

Terraform >=1.10,<2.0과 두 root의 lockfile을 유지한다. module pin은 EKS 20.37.2, IAM 5.60.0, VPC 5.21.0이다. init -backend=false와 validate는 실제 AWS 가용성 검증이 아니다.

승인된 운영 작업의 순서는 state bucket bootstrap/보관 → private backend 설정 → 계정별 addon build·CIDR·SMTP·예산 입력 → 저장된 plan 검토/승인/apply → 플랫폼 설치 → DB bootstrap → 앱 순차 배포다. state/plan에 비밀번호가 있으므로 공개 artifact로 게시하지 않는다. 구체 명령·locking·복구 경계는 현행 문서에만 유지한다.

플랫폼 addon 설치는 버전이 고정된 scripts/aws-platform-up.sh를 사용한다. 출력의 계정·cluster ARN·endpoint와 실제 AWS/kubeconfig가 일치해야 시작한다. Namespace·gp3·SecretStore·RBAC는 k8s/platform/aws가 소유하며 앱 workflow가 생성하지 않는다. GitHub 배포는 별도 self-hosted/linux/x64/fruition-feedback runner, feedback required reviewers·branch 제한이 필요하다. 동적 hosted runner를 위해 EKS API 전체 인터넷을 열지 않는다.

DB bootstrap은 Access endpoint에 DB_ISOLATION_TARGET=access, Core endpoint에 core를 사용한다. 관리자 credential은 runtime과 migration Job에 주입하지 않는다. 각 대상의 PostgreSQL init/validate 절차와 RDS CA verify-full은 docs/script.md를 따른다.

Secrets Manager는 ignore_changes로 운영 값을 보존한다. 기존 환경에 MFA/SMTP/Redis 키를 추가할 때 Terraform 재실행만으로 채워졌다고 가정하지 않는다. MFA 키를 재생성하면 기존 TOTP secret을 복호화하지 못한다. Redis 사용자 password와 서비스 Secret 값을 같은 보안 입력 경로로 맞춘다. 정적 S3 IAM key 제거·Redis 리소스 교체는 실제 plan에서 별도 검토한다.

S3의 Document/AI object 권한은 prefix로 제한하지만 신규 객체 404 판별에 필요한 bucket ListBucket metadata는 공유한다. RDS Single-AZ, Redis primary 1개, Kafka broker 1개는 사용자 피드백 profile의 단일 장애점이다. HA·관측성·provider 공정성·실측 부하와 복구는 별도 남은 범위다. ESO 2.9.0의 공식 테스트 표는 Kubernetes 1.36이며 EKS 1.35 실호환 검증을 아직 하지 않았다.
