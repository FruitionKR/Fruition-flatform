# 이미지 자동 게시와 승인 배포

서비스 저장소의 main CI가 성공하면 플랫폼의 `Publish image release`가 바뀐 서비스의 이미지만 새로 빌드하고, 나머지는 이미 ECR에 있는 이미지를 재사용해 5개 이미지 묶음을 게시합니다. 모두 성공한 묶음만 플랫폼 GitHub Releases에 표시합니다. 게시 자체는 EKS를 변경하지 않습니다.

## 처음 한 번 준비

1. 이 변경을 플랫폼 main에 병합합니다. 서비스 저장소 Access·Document·AI·frontend의 배포용 수정도 각각 main에 병합되어 있어야 합니다.
2. `gh api repos/FruitionKR/Fruition-flatform/actions/oidc/customization/sub --jq .sub_claim_prefix`로 실제 OIDC prefix를 확인해 로컬 `feedback.tfvars`의 `github_oidc_subject_prefix`에 넣습니다. 새 저장소는 owner/repository 고유 ID를 포함할 수 있으므로 이름만 보고 추정하지 않습니다. Terraform을 새로 plan하고 검토·apply합니다. 이미지 게시용 IAM role/policy 2개와 배포 role의 `ecr:DescribeImages` 권한이 추가됩니다. 이전 저장 plan에는 이 변경이 없습니다.
3. 플랫폼 저장소 **Settings → Secrets and variables → Actions → Variables**에 아래 값을 등록합니다. 게시 workflow는 feedback Environment 밖에서 실행되므로 **Repository variables**에 설정해야 합니다.

| Repository variable | 값 |
|---|---|
| `AWS_ACCOUNT_ID` | 배포할 AWS 계정의 12자리 ID |
| `AWS_IMAGE_PUBLISH_ROLE_ARN` | `terraform -chdir=infra/terraform output -raw github_image_publish_role_arn` 결과 |
| `AWS_IMAGE_PUBLISH_ENABLED` | 위 준비를 마친 후 `true`로 설정 |

장기 AWS access key나 저장소 간 PAT는 사용하지 않습니다. 현재 공개 서비스 저장소 네 개를 조회하고 정확한 커밋을 가져옵니다. 비공개 저장소로 전환하면 GitHub App 등의 별도 읽기 인증을 먼저 구성해야 합니다.

4. 기존 `feedback` Environment의 main 전용 배포 정책과 required reviewer를 확인합니다. `AWS_DEPLOY_ROLE_ARN`, `AWS_DEPLOY_CONFIG_JSON`, 검증 계정 설정은 기존대로 필요합니다. EKS·Runner·플랫폼 설치·DB 초기화도 먼저 완료합니다.
5. 최초에는 **Actions → Publish image release → Run workflow → main**으로 게시를 실행합니다. 게시 실패 시 같은 workflow를 다시 실행할 수 있습니다.

## 자동으로 하는 일

- 15분 간격으로 Access·Document·AI·frontend의 현재 main 커밋과 각 `ci.yml`의 해당 커밋에 대한 push CI 성공을 확인합니다. 서비스 push 직후 즉시 실행되는 것은 아니며 GitHub 일정 실행은 지연될 수 있습니다. 공개 저장소의 장기 비활동 시 일정이 비활성화될 수도 있습니다.
- 하나라도 CI가 실패하거나 진행 중이면 게시를 건너뛰고 다음 실행에서 다시 확인합니다. PR·다른 브랜치의 성공 결과로 우회하지 않습니다.
- 네 소스 커밋과 빌드 스크립트·workflow 해시로 40자리 릴리스 ID를 계산합니다. 이는 특정 저장소의 Git 커밋 SHA가 아닙니다. 문서·배포 검토 기록만 바꾸면 새 이미지를 만들지 않습니다.
- 서비스마다 빌드 context(Access·Document·frontend·converter는 저장소 루트, pipeline은 `pipeline/` 디렉터리)의 Git tree SHA, Dockerfile 경로, `BUILDER_VERSION`으로 빌드 ID를 계산해 `b-<40자리>` ECR 태그로 씁니다. 같은 태그가 이미 ECR에 있으면 clone·로그인·빌드 없이 그 이미지를 재사용합니다. converter는 AI 저장소 루트가 context라 AI 저장소의 어떤 커밋에도 다시 빌드되고, pipeline은 `pipeline/` 아래가 바뀔 때만 다시 빌드됩니다.
- GitHub hosted Linux runner에서 x86_64 이미지 `access-svc`, `document-svc`, `pipeline`, `converter`, `frontend`를 빌드합니다. `frontend`는 Fruition-frontend 루트 Dockerfile을 `SAME_ORIGIN_API=true`로 빌드해 Next rewrite 없이 ALB 경로 라우팅을 따릅니다. 동시에 최대 4개를 빌드합니다(`max-parallel: 4`).
- `b-` 태그도 immutable입니다. 부분 실패 후 재실행하면 이미 게시된 같은 태그를 재사용합니다.
- 다섯 이미지가 모두 준비되면 `images-<40자리 ID>` GitHub Release를 게시합니다. 릴리스 설명에는 서비스별 태그와 이번 게시에서 새로 빌드했는지·재사용했는지를 표로 남깁니다. `release.json`(`schema_version: 3`)에는 소스 커밋, `builder_version`, 서비스별 `builds`(context tree·Dockerfile·태그), `images`(태그·digest)를 기록합니다. 검증 시 태그를 기록된 빌드 입력으로 다시 계산하므로 임의 태그를 섞을 수 없습니다. AWS 계정이나 비밀번호는 manifest에 넣지 않습니다.
- `publish-images.yml`의 build job을 바꾸면 같은 소스여도 다른 이미지가 나올 수 있습니다. 이때 `scripts/aws_image_release.py`의 `BUILDER_VERSION`을 올리고 옆의 `BUILDER_JOB_SHA256`을 새 값으로 갱신해야 테스트가 통과합니다. 버전을 올리면 다음 게시에서 다섯 이미지를 모두 다시 빌드합니다.

`schema_version: 2` 릴리스는 다섯 이미지에 같은 릴리스 ID 태그를 붙인 이전 형식입니다. 검증·배포·rollback에 계속 쓸 수 있으며 이 경우 배포도 이전처럼 릴리스 ID 태그를 사용합니다. frontend가 EKS로 오기 전 릴리스는 `schema_version: 1`(저장소 3개·이미지 4개)입니다. 이 릴리스도 검증은 하지만 frontend 이미지가 없으므로 `rollback`에만 쓸 수 있습니다. deploy workflow는 action이 `rollback`일 때만 `aws_image_release.py verify --allow-legacy`를 붙이고, `deploy`·`bootstrap`에 schema 1 ID를 넣으면 검증 단계에서 멈춥니다.

빌드 권한은 플랫폼 main의 OIDC만 허용하고 다섯 ECR 저장소에 한정합니다. EKS·DB·Secrets Manager·Terraform state 권한은 없습니다. main에 코드를 쓸 수 있는 사람은 신뢰된 운영자여야 합니다.

## 운영자가 버전을 선택하고 승인

1. 플랫폼 저장소 **Releases**에서 배포할 `Images …`를 선택하고 설명의 40자리 ID를 복사합니다. 아직 draft이거나 실패한 빌드는 배포 대상이 아닙니다.
2. `docs/releases/<ID>.json`에 DB 변경 호환성과 복원 시험의 실제 검토 기록을 작성해 main에 반영합니다. 운영 변경은 `review.example.json`, 최초 설치는 `review.initial.example.json` 형식을 사용합니다. 최초 설치에는 게시 이미지의 마이그레이션·재실행 및 복원 시험 기록이 필요하며, 업무 호환성을 통과한 것으로 대신 표시하지 않습니다.
3. **Actions → Deploy (EKS) → Run workflow**에서 branch는 `main`, action은 `deploy`, `release_sha`는 선택한 ID로 지정합니다. 최초 설치는 `bootstrap`, 이전 성공 버전 복구는 `rollback`과 `rollback_sha`를 사용합니다.
4. `feedback`의 **Review deployments**에서 버전과 검토 내용을 확인하고 승인합니다. GitHub 입력의 선택 목록은 릴리스 목록과 자동 동기화되지 않으므로 현재 UI는 Releases에서 선택한 ID를 입력하는 방식입니다.
5. Deploy workflow는 AWS 인증 전에 게시된 릴리스의 manifest를 한 번 받아(`aws_image_release.py fetch`) render·검증·배포에 같은 파일을 씁니다. 배포 role은 그 파일에 기록된 모든 이미지(schema 2·3은 5개)의 실제 ECR digest가 기록과 같은지 확인합니다(`verify --manifest`). schema 3은 각 Deployment·Job 이미지를 `fruition-<서비스>@<digest>`로 고정하므로 이전 배포와 digest가 같은 서비스는 Pod가 재시작되지 않습니다. 통과한 경우 기존 DB 검사·migration·순차 교체·업무 smoke를 수행합니다. 운영자 승인 없이 push가 배포를 시작하지 않습니다.

최초 설치 후 검증 계정과 workspace를 만들고 같은 ID로 `deploy`를 실행해 업무 검증까지 완료해야 합니다. CI/이미지 빌드 성공은 실제 AWS 서비스 연동 성공을 의미하지 않습니다.

## 실패·보존·비용

- 게시 실패는 GitHub Actions에서 확인합니다. 이 hosted 게시 workflow는 AWS 운영 SNS 접근권한이 없어 Discord 전송을 하지 않습니다. 배포 실패의 기존 Discord 알림은 유지됩니다.
- 같은 ID가 이미 완전히 게시되어 있으면 정기 실행은 빌드를 생략합니다. 새 소스는 바뀐 서비스만 빌드합니다. 게시 스크립트나 workflow만 바뀌면 새 릴리스 ID가 생기지만 이미지는 모두 재사용합니다.
- ECR은 저장소마다 `b-` 빌드 태그 최근 30개와 그 밖의 이전 릴리스 ID 태그 최근 30개를 따로 보존합니다(`infra/terraform/ecr.tf`). 오래된 GitHub Release가 있어도 이미지가 만료되면 배포/rollback 검증에서 실패합니다. 현재 실행 중인 digest와 rollback 후보 digest가 서비스별 최근 30개 빌드 안에 있는지 확인해야 합니다. 만료된 빌드 태그는 같은 입력이 다시 오면 새로 빌드되지만 digest가 달라 이전 Release로는 검증되지 않습니다.

## schema 3 전환 시 한 번 일어나는 일

- 이 변경 후 첫 게시는 ECR에 `b-` 태그가 하나도 없어 다섯 이미지를 모두 새로 빌드합니다.
- 그 릴리스를 처음 배포하면 이미지 참조가 `:<릴리스 ID>`에서 `@<digest>`로 바뀌므로 모든 Deployment가 한 번 교체됩니다. 이후 배포부터 digest가 같은 서비스는 교체되지 않습니다.
- 공개된 Release 기록은 배포 검증의 신뢰 자료이므로 운영자가 임의로 편집하거나 digest를 교체하지 않습니다. 재현되지 않는 base image·외부 패키지 최신 변경을 적용하려면 소스 또는 빌드 방식 변경으로 새 릴리스 ID를 만드세요.
