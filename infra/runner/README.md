# 배포 runner 준비와 운영

현재 코드 준비와 실제 서버 등록은 별도다. 아래 단계가 끝나고 `Check deployment runner`가 성공해야 runner 구성이 완료된다. 명령은 별도 안내가 없으면 저장소 루트의 로컬 터미널에서 실행한다.

## 1. 로컬 입력 확인

`infra/terraform/feedback.tfvars`에는 SMTP 주소, 검증한 서울 Ubuntu 24.04 AMI, EKS addon build를 넣는다. SMTP 비밀번호는 파일에 쓰지 않고 **같은 터미널**의 `TF_VAR_smtp_password`로 전달한다. 기존 터미널에 없다면 zsh에서 다음처럼 다시 입력한다.

```zsh
read -rs 'TF_VAR_smtp_password?Gmail 앱 비밀번호: '
echo
export TF_VAR_smtp_password="${TF_VAR_smtp_password// /}"
aws sts get-caller-identity
```

AWS 계정이 배포 대상인지 확인한다. 초기 플랫폼 설치는 EKS 생성에 사용한 동일 관리자 identity로 진행한다. 로컬에는 Terraform, AWS CLI, kubectl 1.35, Helm, jq가 필요하다.

초기 로컬 설치를 위해 `curl -4 https://checkip.amazonaws.com`으로 현재 공인 IPv4를 확인하고, `feedback.tfvars`의 `eks_public_access_cidrs`를 `["현재_IP/32"]`로 잠시 바꾼다. `0.0.0.0/0`은 사용하지 않는다. IP가 바뀌면 다시 확인한다. 5단계에서 `[]`로 돌린다.

## 2. Terraform state 저장소 생성

`infra/terraform-state-bootstrap/state.tfvars`의 bucket 이름과 `infra/terraform/feedback.tfbackend`의 bucket 이름이 같아야 한다. 두 파일은 Git에서 제외한다. 기존 배포 state가 있다면 새로 만들지 말고 먼저 기존 state를 복구한다.

```bash
umask 077
terraform -chdir=infra/terraform-state-bootstrap init -input=false -lockfile=readonly
terraform -chdir=infra/terraform-state-bootstrap plan -var-file=state.tfvars -out=bootstrap.tfplan
```

예상한 S3 state bucket과 관련 보안 설정만 생성하는지 검토한 다음 실행한다.

```bash
terraform -chdir=infra/terraform-state-bootstrap apply bootstrap.tfplan
```

bootstrap 디렉터리의 `terraform.tfstate`와 백업은 접근이 제한된 별도 저장소에 보관한다. S3 이름 충돌 시 두 설정 파일을 함께 변경한다.

## 3. AWS 인프라와 runner 생성

이 단계는 runner만이 아니라 VPC/EKS/RDS 등 전체 Terraform 인프라를 생성하며 비용이 발생한다. 비밀번호가 포함될 수 있는 plan/state를 Git이나 공개 artifact에 올리지 않는다.

```bash
terraform -chdir=infra/terraform init -reconfigure -backend-config=feedback.tfbackend -lockfile=readonly
terraform -chdir=infra/terraform plan -var-file=feedback.tfvars -out=feedback.tfplan
```

계정·리전, 생성/교체/삭제 목록, EC2 수와 DB 사양을 검토한 다음 적용한다.

```bash
terraform -chdir=infra/terraform apply feedback.tfplan
mkdir -p .runtime
terraform -chdir=infra/terraform output -json > .runtime/terraform-outputs.json
chmod 600 .runtime/terraform-outputs.json
terraform -chdir=infra/terraform output deployment_runner
```

## 4. 플랫폼 권한 설치와 GitHub 등록

먼저 로컬 관리자 터미널에서 플랫폼을 설치한다. 앱 배포 role은 이 작업을 할 수 없다.

```bash
aws eks update-kubeconfig --region ap-northeast-2 --name fruition-eks
bash scripts/aws-platform-up.sh install .runtime/terraform-outputs.json
```

GitHub 저장소 **Settings → Environments → feedback**에서 deployment branch를 `main`으로 제한하고 required reviewers를 지정한다. 공개 저장소이므로 self-hosted runner에 PR 코드를 실행하는 workflow를 추가하지 않는다. 현재 배포·점검 workflow는 `workflow_dispatch`와 `main` 조건을 사용한다. 다른 workflow가 이 runner를 사용하도록 변경되면 별도 검토한다. GitHub는 공개 저장소의 self-hosted runner 사용에 주의를 요구한다([공식 문서](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners)).

이제 AWS 콘솔 **EC2 → Instances → fruition-feedback-runner → Connect → Session Manager**로 접속한다. SSH 키나 22번 포트는 필요 없다. SSM이 아직 표시되지 않으면 잠시 기다린 뒤 instance IAM role 및 NAT 경로를 확인한다. 접속한 서버에서:

```bash
sudo cloud-init status --wait
sudo test -f /var/lib/fruition-runner-ready && echo READY
```

READY가 없으면 `/var/log/cloud-init-output.log`에서 설치 실패를 확인하고 해결한다. GitHub **Settings → Actions → Runners → New self-hosted runner → Linux / x64**에서 표시되는 `--token` 뒤의 등록 토큰만 복사한다. 다운로드 명령은 서버 초기화가 이미 수행했다. 서버에서:

```bash
sudo /usr/local/sbin/fruition-runner-register
```

입력 요청에 등록 토큰을 붙여 넣는다. 화면에는 표시되지 않는다. 토큰을 파일·채팅에 저장하지 않는다. 등록 토큰은 발급 후 1시간 유효하다([GitHub 문서](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners)). GitHub runner 목록에서 `Idle`과 `fruition-feedback` label을 확인한다.

## 5. EKS 외부 접속 종료

로컬 `feedback.tfvars`에서 `eks_public_access_cidrs = []`로 변경한다. 같은 SMTP 환경변수를 유지한 터미널에서:

```bash
terraform -chdir=infra/terraform plan -var-file=feedback.tfvars -out=private-only.tfplan
```

EKS public endpoint를 닫는 예상 변경인지 확인하고 적용한다.

```bash
terraform -chdir=infra/terraform apply private-only.tfplan
```

이후 로컬 kubectl 직접 접속은 안 되며, VPC 내부 runner가 private endpoint를 사용한다. 추후 관리자 작업은 일시적으로 현재 `/32`를 허용하고 작업 후 닫는 동일 절차를 사용한다.

## 6. Environment 연결과 완료 점검

코드 변경은 검토 후 GitHub `main`에 반영해야 workflow가 표시된다. 커밋·push·merge는 이 준비 작업에서 자동 실행하지 않는다.

로컬에서 아래 출력값을 GitHub **Settings → Environments → feedback → Environment variables**의 `AWS_DEPLOY_ROLE_ARN`에 등록한다.

```bash
terraform -chdir=infra/terraform output -raw github_deploy_role_arn
```

GitHub **Actions → Check deployment runner → Run workflow → main**을 실행하고 필요한 Environment 승인을 진행한다. 이 점검은 앱을 배포하지 않으며 다음을 확인한다.

- GitHub OIDC로 올바른 AWS 계정/role에 인증된다.
- EKS는 private-only이고 runner에서 API 연결이 된다.
- fruition namespace의 Deployment 조회와 Job 생성 권한이 있다.
- Secret 조회, RoleBinding 생성, 다른 namespace 배포 권한이 없다.

`Idle`만으로는 EKS 배포 준비 완료가 아니다. 위 점검까지 성공해야 runner 완료다. 실제 앱 배포 전에는 [환경값 이전 절차](../../k8s/overlays/aws/README.md#설정-완료-후-github-environment로-이전)에 따라 `AWS_DEPLOY_CONFIG_JSON`도 등록하고, DB bootstrap 및 네 서비스 이미지 게시를 마쳐야 한다.

## 구성과 역할

| 구성 | 역할 |
|---|---|
| private subnet의 t3.small 1대, 암호화 gp3 30GB | GitHub 배포 명령을 실행하는 상시 서버 |
| 기존 NAT Gateway | GitHub·패키지 저장소·AWS API로 나가는 연결 |
| SSM + 서버 IAM role | 관리 접속. 서버 role에 앱 배포 권한은 없음 |
| GitHub OIDC + deploy role | 작업 시 임시 AWS 인증, ECR 태그 확인과 대상 EKS 조회 |
| EKS access entry + RBAC | 허용된 namespace의 앱 배포 권한 |
| Python 3.12, AWS CLI, kubectl | 설정 렌더링, AWS 인증, Kubernetes 배포 실행 |
| systemd 서비스, gh-runner 사용자 | 로그아웃·재부팅 후에도 작업 수신. sudo 권한 없음 |

이미지 빌드와 PR 테스트는 GitHub-hosted runner에서 수행한다. 이 서버는 Vercel 프론트나 AI 추론을 실행하지 않는다. 별도 EC2/EBS 상시 요금과 NAT 데이터 처리 비용이 발생하며 전체 예산에 포함해 계산해야 한다. 기존 NAT를 공유하며 runner용 NAT는 추가하지 않는다.

SSM에서 `cd /opt/actions-runner && sudo ./svc.sh status`로 상태를 확인한다. 서버 재생성 시 기존 GitHub runner를 제거하고 새 토큰으로 재등록한다. 부팅 스크립트나 AMI 변경은 Terraform에서 EC2 교체를 유발할 수 있으므로 plan을 확인한다. runner 자체 자동 업데이트는 활성화되며 OS/도구 업데이트는 유지보수 시간에 수행하고 점검 workflow를 다시 실행한다.
