# Platform 문서

전체 구조와 서비스 간 계약·인프라·통합 운영을 관리합니다. 서비스 자체 문서는 각 서비스 저장소가 소유합니다.

| 문서 | 책임 |
|---|---|
| [architecture.md](architecture.md) | 전체 아키텍처·통신·공통 권한·AWS 배치·저장소 소유권 |
| [AWS 배포 아키텍처 그림](aws-deployment-architecture.md) | 배포 후 서비스 배치·요청 흐름·배포와 알림 연결을 쉬운 그림으로 설명 |
| [화면 EKS Fargate 운영](aws-frontend-hosting.md) | 화면·API 같은 주소 경로 분기, 접근 코드 WAF, 절전 중 제약과 되돌리기 |
| [api/](api/README.md) | 서비스별 API 진입 안내와 서비스 간 호출 경로 |
| [data-model.md](data-model.md) | 저장소·DB 계정 격리·서비스 간 관계 |
| [script.md](script.md) | 통합 실행·검증·AWS 준비와 운영 절차 |
| [안전한 배포·유지보수](aws-maintenance.md) | 보안 적용, API 순차 교체, DB 변경 검토·복원, 자동 확장 범위 |
| [AWS 구성·비용 위험 요약](aws-deployment-costs.md) | 현재 사양·확장 한도·트래픽 급증 비용·공개 전 보완 순서 |
| [Terraform 전체 관리 항목](aws-resource-inventory.md) | 2026-09-16 plan 185개 기준 항목별 주소·역할과 이후 추가 항목(현재 state 226개) |
| [CloudWatch·Discord 운영](aws-observability.md) | 로그·사용량 수집, 대시보드, 경보 임계값, 웹훅 입력과 실제 수신 시험 |
| [이미지 자동 게시와 승인 배포](aws-image-releases.md) | 이미지 5개 release 게시, 검토 기록(`releases/`), 승인 배포 |
| [요청으로 EKS 노드 깨우기](aws-request-wake.md) | 절전 상태 판단, ALB 5XX 기반 기동 Lambda |
| [대용량 PDF 업로드·변환](aws-document-transfer.md) | S3 직접 업로드·변환·AI 처리 경로와 검증 |
| [문서 본문 API WAF 정책](aws-waf-document-content.md) | 본문 전송 API의 WAF 규칙 예외와 평가 순서 |
| [노드 이미지 정리와 CI 빌드 캐시](node-image-gc-and-build-cache.md) | kubelet 이미지 GC, 노드 디스크, 빌드 캐시 |
| [AWS 로컬 설정 보관](aws-local-config.md) | `.local/aws/` 설정 파일 보관 규칙 |
| [CI/CD 검토 (2026-09-20)](cicd-review-2026-09-20.md) | CI/CD 속도·안정성 개선안. 일부 적용, 미적용 항목 남음 |
| [ADR-0020](adr/0020-platform-and-document-ownership.md) | 플랫폼과 서비스 문서 관리 결정 |
| [ADR-0021](adr/0021-aws-observability-and-operations.md) | CloudWatch 중심 관측과 운영 준비 결정 |
| [ADR-0022](adr/0022-realtime-speech-transcription.md) | 음성 기능 서비스 책임과 실시간 전사 WebSocket 중계 결정 |
| [ADR-0023](adr/0023-retention-after-personal-data-purge.md) | 개인정보 파기 후 S3 이전 버전·AI 로그·Kafka 보관 기간 |
| [ADR-0024](adr/0024-converter-least-privilege-db-account.md) | converter 전용 최소 권한 DB 계정 |
| [backlog/](backlog/README.md) | 과거 통합 설계·이슈·다이어그램, 완료된 계획·일회성 점검 기록 보관 |

서비스별 문서: [frontend](https://github.com/FruitionKR/Fruition-frontend/blob/main/docs/README.md) · [Access](https://github.com/FruitionKR/Fruition-access/blob/main/docs/README.md) · [Document](https://github.com/FruitionKR/Fruition-document/blob/main/docs/README.md) · [AI](https://github.com/FruitionKR/Fruition-ai/blob/main/docs/README.md)

문서 링크는 형제 checkout 기준입니다. 서비스 원격 GitHub 주소가 정해지면 저장소 간 링크를 해당 주소로 연결합니다.
