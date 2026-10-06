# AWS 배포 전 준비 상태 기록

2026-10-06 backlog 이관. 첫 AWS 배포(2026-09-20) 전 준비 단계의 상태 서술을 모았다. 이후 배포 기록은 `docs/releases/`를 따른다.

## script.md "배포 준비까지만 수행하는 경우" 원문 일부

준비 범위는 서비스별 이미지·Deployment·Secret·migration·통신 경계의 로컬 검증과 입력 예시 작성이다. 아래 예시는 배포 시 저장소 밖 보안 디렉터리로 복사해 채운다. 실제 계정 입력이 없는 지금은 placeholder를 유지하며, Terraform plan/apply·플랫폼 install·앱 deploy/rollback·AWS 장애 주입은 실행하지 않는다.

로컬 준비 완료 기준은 아래 IaC 검증과 outbox 테스트 통과다. 이미지 빌드·push에는 변경사항이 포함된 실제 commit SHA를 사용한다. 실제 배포 시에는 Helm을 포함한 운영 도구, 고정 egress/VPC runner, DNS·ACM, DB bootstrap, 플랫폼 설치를 준비한 뒤 순차 배포 절차를 실행한다. 현재 로컬에 Helm이 없는 경우도 이 시점에 설치한다.

실환경 검증은 별도 배포 시 수행한다. 먼저 정상 사용자 요청과 AI 작업 완료를 확인하고, AI Pod 재시작 후 작업·로그 복구, pipeline-api 장애 시 일반 문서 요청 영향, rolling update와 재전달 시 업무 중복 여부를 확인한다. 노드 drain은 replica·PDB·배치 조건을 갖춘 뒤, RDS failover는 Multi-AZ 적용 후에만 수행한다. 각 실험 전 정상 상태와 중단 조건을 기록하고 복구 후 동일 요청을 재검증한다. 이는 실행 예정 절차이며 로컬 테스트 통과를 AWS 장애 검증 성공으로 기록하지 않는다.

#### AWS 사전조회 상태

이 절차는 저장소 코드의 실행 계약이다. 준비 작업 당시 인증 계정의 서울 리전을 실제 조회했으며 EKS·RDS·VPC·ACM 인증서·ECR repository가 없고, S3 bucket·Route 53 hosted zone 목록도 비어 있었다. EKS 1.35 managed addon build와 EC2 On-Demand vCPU quota는 조회했다. Terraform plan/apply·addon 설치·서비스 배포·AWS 장애 복구 검증은 아직 수행하지 않았다. 새 환경의 도메인·Discord webhook 보안 입력·고정 접근 CIDR·SMTP 보안 입력을 준비해야 한다. 로컬 검증 스크립트는 AWS API를 호출하지 않는다.

## aws-deployment-costs.md "지금 어디까지 했나요?" 원문

- Terraform 상태 기록용 S3와 연결은 완료를 확인했습니다.
- 비용 보호만 담았던 계획은 157개였습니다. 이후 CloudWatch를 넣은 계획은 **185개**였습니다. 2026-10-06 state에는 226개가 있습니다. 어느 개수도 곧 요금은 아닙니다.
- RDS 암호화와 보호 설정은 최신 계획에 들어 있는지 확인한 뒤 적용해야 합니다.
- 실제 서비스 설치·많은 요청 시험·Discord 수신 확인은 별도 단계입니다. 자동 긴급 차단은 아직 연결하지 않았습니다.
