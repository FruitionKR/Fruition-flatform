# AWS 로컬 설정 보관

실제 환경 설정은 저장소 루트의 `.local/aws/`에 모아 보관합니다. 폴더 전체는 Git에서 제외하며 파일은 소유자만 읽고 쓸 수 있게 설정합니다.

| 파일 | 용도 |
|---|---|
| `feedback.tfvars` | 메인 인프라 입력과 Gmail 앱 비밀번호 |
| `feedback.tfbackend` | 기존 S3 backend 연결 설정 |
| `state.tfvars` | 상태 저장용 인프라 입력 |
| `deploy-config.feedback.json` | 실제 앱 배포 설정 |

현재 작업 폴더의 이전 위치에는 이 파일을 가리키는 상대 심볼릭 링크를 두었습니다. 기존 Terraform 명령도 계속 사용할 수 있으며, 어느 경로에서 편집해도 같은 파일을 수정합니다. 링크 역시 Git 제외 대상입니다. 이 로컬 이동과 링크는 다른 clone/worktree에 자동으로 전달되지 않습니다.

## 폴더를 직접 지정하는 실행 방법

저장소 루트에서 실행합니다. `-chdir` 때문에 입력 경로는 `infra/terraform` 기준입니다.

```bash
terraform -chdir=infra/terraform init -reconfigure \
  -backend-config=../../.local/aws/feedback.tfbackend \
  -input=false -lockfile=readonly

umask 077
terraform -chdir=infra/terraform plan -input=false \
  -var-file=../../.local/aws/feedback.tfvars \
  -out=feedback.tfplan
```

계획을 검토한 뒤 적용합니다. 적용하면 AWS 리소스 생성과 과금이 시작될 수 있습니다.

```bash
terraform -chdir=infra/terraform apply feedback.tfplan
```

## 보관 및 복원

- `.local/aws/`는 암호화된 별도 저장소에 백업합니다. Git 제외나 파일 권한은 디스크 암호화를 대신하지 않습니다.
- 새 clone/worktree에는 이 폴더를 안전하게 복원하고 위 직접 경로 명령을 사용합니다. 기존 경로의 심볼릭 링크가 없어도 됩니다.
- `infra/terraform-state-bootstrap/terraform.tfstate`는 실행 위치와 연결된 관리 기록이라 이동하지 않습니다. 이 state도 별도로 안전하게 백업해야 합니다. 설정 폴더만으로 전체 복구가 되는 것은 아닙니다.
- 메인 인프라 state는 기존 S3 backend에서 관리합니다. `.terraform/`는 로컬 초기화 정보와 캐시이며 새 환경에서는 init으로 준비합니다.
- 기존 `*.tfplan`은 원래 위치에 보존했습니다. plan에는 비밀값이 포함될 수 있고 입력 변경이 자동 반영되지 않으므로 적용 전 새로 생성합니다.
- 예제 파일과 `.terraform.lock.hcl`은 Git에서 계속 관리합니다.
