# Fruition Platform

[한국어](#한국어) · [English](#english)

## 한국어

`platform/` 전체를 인프라용 GitHub 저장소 루트로 관리합니다.

| 폴더 | 소유·관리 범위 |
|---|---|
| `infra/` | Terraform, DB 인스턴스·계정, Redis·Kafka·S3, 로컬 Compose, 관측 |
| `k8s/` | Deployment·Ingress·NetworkPolicy·스케일링·플랫폼 operator 설정 |
| `scripts/` | 전체 서비스 실행·종료, DB 격리·migration 통합 검증, E2E, AWS 준비·배포 |
| `docs/` | 전체 아키텍처·공통 API 안내·DB 소유권·운영 절차·공통 ADR |
| `docs/backlog/` | 과거 통합 문서·다이어그램 원문 |

서비스 코드·테이블 migration·OpenAPI·단독 테스트와 서비스 문서는 각 서비스 저장소가 소유합니다. Document 전용 SQL은 `Document/scripts/sql/`에 있습니다.

GitHub 저장소 이름은 `Fruition-flatform`이며, 통합 실행 스크립트에서 사용하는 로컬 폴더 이름은 `platform`입니다.

새 통합 개발 환경은 빈 작업 폴더에서 아래 이름으로 clone합니다.

```bash
git clone git@github.com:FruitionKR/Fruition-frontend.git frontend
git clone git@github.com:FruitionKR/Fruition-access.git Access
git clone git@github.com:FruitionKR/Fruition-document.git Document
git clone git@github.com:FruitionKR/Fruition-ai.git AI
git clone git@github.com:FruitionKR/Fruition-flatform.git platform
```

서비스별 Orca 워크트리는 독립 빌드·테스트에 사용합니다. 전체 로컬 스택 실행은 위 형제 checkout 구조에서 수행합니다.

통합 개발 checkout 구조는 다음과 같습니다.

```text
workspace/
├─ frontend/
├─ Access/
├─ Document/
├─ AI/
└─ platform/
```

```bash
# platform 디렉터리에서 실행
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
./scripts/aws-iac-validate.sh
# 전체 로컬 서비스를 실행할 때만 형제 checkout이 필요
./scripts/dev-up.sh
```

이 저장소의 `.github/workflows/`는 서비스 소스 없이 IaC와 격리 계약을 검증합니다. 서비스 연동 검증과 전체 로컬 스택 실행에는 위 형제 checkout이 필요합니다.

배포 workflow는 ECR의 기존 이미지 묶음 `release_sha`를 입력받습니다. 서비스별 이미지 게시 CI와 OIDC는 실제 원격 저장소에 맞춰 연결해야 합니다. 현재 배포기는 같은 태그의 네 이미지를 요구하며 서비스별 SHA 입력은 후속 작업입니다. 실제 AWS 배포는 실행하지 않았습니다.

[문서 안내](docs/README.md) · [아키텍처](docs/architecture.md) · [운영 절차](docs/script.md)

## English

This repository owns the shared infrastructure and operations configuration.

| Directory | Ownership |
|---|---|
| `infra/` | Terraform, database instances and accounts, Redis, Kafka, S3, local Compose, and observability |
| `k8s/` | Deployments, Ingress, NetworkPolicy, scaling, and platform operator configuration |
| `scripts/` | Stack startup/shutdown, database isolation and migration integration checks, E2E, AWS preparation and deployment |
| `docs/` | Shared architecture, API overview, database ownership, operations procedures, and shared ADRs |
| `docs/backlog/` | Historical integrated documentation and original diagrams |

Each service repository owns its source code, table migrations, OpenAPI specification, standalone tests, and service documentation. Document-specific SQL belongs in `Document/scripts/sql/`.

The GitHub repository name is `Fruition-flatform`. The local directory name expected by integration scripts is `platform`.

Clone into an empty workspace using the following local directory names:

```bash
git clone git@github.com:FruitionKR/Fruition-frontend.git frontend
git clone git@github.com:FruitionKR/Fruition-access.git Access
git clone git@github.com:FruitionKR/Fruition-document.git Document
git clone git@github.com:FruitionKR/Fruition-ai.git AI
git clone git@github.com:FruitionKR/Fruition-flatform.git platform
```

Use individual Orca worktrees for standalone builds and tests. Run the full local stack from the sibling checkout layout below:

```text
workspace/
├─ frontend/
├─ Access/
├─ Document/
├─ AI/
└─ platform/
```

```bash
# Run from the platform directory.
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
./scripts/aws-iac-validate.sh
# Sibling service checkouts are required for the full local stack.
./scripts/dev-up.sh
```

Workflows in `.github/workflows/` validate IaC and isolation contracts without service source code. Service integration checks and full local stack execution require sibling checkouts.

The deployment workflow takes `release_sha`, identifying an existing set of ECR images. Service image publishing CI and OIDC must still be configured for the actual repositories. The current deployment script requires four images with the same tag; separate service SHA inputs remain future work. AWS deployment has not been performed.

[Documentation index](docs/README.md) · [Architecture](docs/architecture.md) · [Operations](docs/script.md)

## 저작권 및 라이선스 / Copyright and License

**한국어**

저작권 (c) 2026 Fruition 팀. 모든 권리 보유.

Fruition 팀이 저작권을 보유하는 코드·문서·자산의 무단 사용을 금지합니다. 상업적·비상업적 목적의 사용·복제·수정·배포·재라이선스·판매에는 Fruition 팀의 사전 서면 허가가 필요합니다. 제3자 구성요소에는 각 라이선스가 적용됩니다. 적용 범위와 예외는 [LICENSE](LICENSE)를 참고하세요.

**English**

Copyright (c) 2026 Team Fruition. All rights reserved.

Unauthorized use of code, documentation, and assets copyrighted by Team Fruition is prohibited. Use, copying, modification, distribution, sublicensing, or sale for commercial or non-commercial purposes requires prior written permission from Team Fruition. Third-party components remain subject to their own licenses. See [LICENSE](LICENSE) for the scope and exceptions.
