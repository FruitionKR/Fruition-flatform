# Platform 문서

전체 구조와 서비스 간 계약·인프라·통합 운영을 관리합니다. 서비스 자체 문서는 각 서비스 저장소가 소유합니다.

| 문서 | 책임 |
|---|---|
| [architecture.md](architecture.md) | 전체 아키텍처·통신·공통 권한·AWS 배치·저장소 소유권 |
| [AWS 배포 아키텍처 그림](aws-deployment-architecture.md) | 배포 후 서비스 배치·요청 흐름·배포와 알림 연결을 쉬운 그림으로 설명 |
| [api/](api/README.md) | 서비스별 API 진입 안내와 서비스 간 호출 경로 |
| [data-model.md](data-model.md) | 저장소·DB 계정 격리·서비스 간 관계 |
| [script.md](script.md) | 통합 실행·검증·AWS 준비와 운영 절차 |
| [안전한 배포·유지보수](aws-maintenance.md) | 보안 적용, API 순차 교체, DB 변경 검토·복원, 자동 확장 범위 |
| [AWS 구성·비용 위험 요약](aws-deployment-costs.md) | 현재 사양·확장 한도·트래픽 급증 비용·공개 전 보완 순서 |
| [Terraform 전체 관리 항목](aws-resource-inventory.md) | 최신 plan의 185개 항목별 주소·역할·분야별 개수 |
| [CloudWatch·Discord 운영](aws-observability.md) | 로그·사용량 수집, 대시보드, 경보 임계값, 웹훅 입력과 실제 수신 시험 |
| [ADR-0020](adr/0020-platform-and-document-ownership.md) | 플랫폼과 서비스 문서 관리 결정 |
| [AWS 운영 보완 계획](architecture.md#aws-운영-보완-계획) | 확인된 부족 항목·담당·우선순위·완료 기준 |
| [운영 보완 실행 계획](script.md#aws-운영-보완-실행-계획) | 알림 초안·Runbook·복원 시험·배포 전 검증 |
| [ADR-0021](adr/0021-aws-observability-and-operations.md) | CloudWatch 중심 관측과 운영 준비 결정 |
| [backlog/](backlog/README.md) | 과거 통합 설계·이슈·다이어그램 보관 |

서비스별 문서: [frontend](https://github.com/FruitionKR/Fruition-frontend/blob/main/docs/README.md) · [Access](https://github.com/FruitionKR/Fruition-access/blob/main/docs/README.md) · [Document](https://github.com/FruitionKR/Fruition-document/blob/main/docs/README.md) · [AI](https://github.com/FruitionKR/Fruition-ai/blob/main/docs/README.md)

문서 링크는 형제 checkout 기준입니다. 서비스 원격 GitHub 주소가 정해지면 저장소 간 링크를 해당 주소로 연결합니다.
