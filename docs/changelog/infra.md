# 인프라 변경 기록

## 2026-10-22

- 통합 `dev-up.sh`에서도 Document·Access·frontend 실행 직전에 `local_analytics_env`를 적용한다. 개별 실행 스크립트와 동일하게 기본 수집 off·운영 설정 격리·명시적 LOCAL_* 설정·서비스별 Git SHA를 보장하며 기존 `SERVICE_ENV_FILE` 전달 순서는 유지한다.
- 실제 launch 함수를 임시 Git 저장소와 가짜 실행 파일로 검증하는 회귀 테스트 5개를 추가했다. 기존 184개를 포함한 AWS 계약 테스트 189개, Bash 문법, Kustomize 3개 경로 렌더링을 통과했다. 신규 테스트는 수정 전 코드에서 모두 실패하며 실제 서비스·AWS·analytics 호출은 수행하지 않는다.
- ShellCheck는 기존 `docker rm $container_ids`의 SC2086 외 추가 경고가 없음을 확인했다.

- PostHog 알파의 frontend·Access·Document·AI 런타임 환경을 추가했다. 기본 수집 off, 빈 토큰, production 환경과 서비스별 source SHA를 사용하며 토큰은 전용 ExternalSecret의 단일 키로만 주입한다.
- 수집 활성화 시 토큰 누락·잘못된 형식을 배포 preflight에서 차단하고, local native/Compose 실행은 별도 LOCAL_* 설정으로 운영 토큰 상속을 막는다. 기존 expand-only migration·fingerprint gate와 다른 Secret 키는 유지한다.
- AWS 계약 테스트, Terraform/Kustomize 및 shell 검증을 수행했다. [운영 절차](../posthog-operations.md)에 안전한 Secret 병합·승인 배포·중지·mock 검증을 정리했다. 실제 토큰 저장·analytics 송신·운영 배포는 실행하지 않았다.

- WAF 자동 스캔 대응으로 민감 파일 경로 차단, 지속/대량 차단 경보 분리, WAF 로그 미수신·ALB 자체 5xx 경보를 추가했다.
- ALB 접근 로그를 비공개 SSE-S3 버킷에 30일 보관하고 Controller annotation으로 활성화했다. 배포 전 버킷 소유 계정·리전·비공개 정책 검사와 메타데이터 전용 권한을 추가했다.
- 빈 도메인/접근 코드로 운영 접근 코드 규칙이 제거되지 않도록 사전 검증을 추가했다. SQLi 확장 본문 규칙도 기존 문서 요청 조건 안에서만 처리하고 나머지 요청은 재차단한다.
- AWS 계약 테스트 176개와 Terraform·Kustomize 검증을 통과하고, 운영 민감 경로 49건·문서 본문 57건 및 실제 로그를 대조했다. 접근 코드 규칙 일시 제거·복구와 범위 밖 검증 사항은 [운영 적용 기록](../aws-waf-review-2026-10-22.md#7-2026-10-22-운영-적용-기록)에 남겼다.
- Public ECR 다운로드 한도로 `minio-init` 이미지 pull이 실패하던 CI를 보완했다. 같은 AWS CLI 2.37.4 버전의 공식 Docker Hub 이미지를 다중 아키텍처 digest로 고정했다. 별도 Compose 프로젝트에서 4개 서비스의 정상 기동, MinIO·Kafka 초기화 종료 코드 0, 생성 버킷 조회 성공을 확인했다.
