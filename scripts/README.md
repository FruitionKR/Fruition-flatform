# 실행 스크립트

로컬 개발 환경을 준비하고 서비스별로 시작·종료하는 명령과 AWS 준비·배포 도구를 보관한다.

## 로컬

- `dev-up.sh` / `dev-down.sh`: 전체 개발 환경
- `front-up.sh` / `front-down.sh`: 프론트엔드
- `back-up.sh` / `back-down.sh`: 백엔드
- `back-test.sh`: Java 21을 찾아 백엔드 Gradle 테스트 실행(`[Access|Document]` 지정 가능)
- `ai-up.sh` / `ai-down.sh`: Pipeline API, embedding-server와 AI 워커
- `swagger-up.sh` / `swagger-down.sh`: Swagger UI(`infra/docker-compose.swagger.yml`, 기본 포트 8090)
- `logs-up.sh`: 워커 컨테이너 로그를 호스트 파일로 수집
- `ai-e2e.sh`: 컨테이너 전체 스택 기반 AI E2E
- `converter-e2e.sh`: converter 단독 E2E
- `bootstrap.sh`: 필수 도구와 의존성 준비
- `lib/`: 스크립트 공용 함수
- `tests/`: IaC·배포 스크립트 단위 테스트와 `test-service-migrations.sh`

## AWS

- `aws-iac-validate.sh`: AWS 인증 없이 IaC와 격리 테스트 검증(`aws-iac.yml`)
- `aws-terraform.sh`: SMTP 비밀번호를 Secrets Manager에서 읽어 주입하는 `infra/terraform` 실행 래퍼
- `aws-platform-up.sh`: 플랫폼 관리자 전용 EKS 플랫폼 구성 설치(`install <terraform-outputs.json>`)
- `aws-runner-check.sh`: runner 읽기 전용 점검(`runner-check.yml`)
- `aws-ops-db-query.sh`: runner 호스트에서 운영 core_db에 읽기 전용 SELECT 실행(일회성 psql Pod, `fruition:operators` 권한)
- `aws-frontend-wake-check.sh`: runner 호스트에서 화면과 같은 Fargate 조건의 일회성 Pod로 VPC DNS·IRSA·기동 이벤트 권한 확인(`--send`면 이벤트 발행). [요청 기반 기동](../docs/aws-request-wake.md#실제-fargate에서-확인)
- `aws_image_release.py`: 서비스 이미지 묶음 게시(`publish-images.yml`)
- `aws_deploy.py`: manifest 렌더와 순차 배포·rollback gate(`deploy.yml`)
- `aws_release_safety.py`: 릴리스 검토·인증 smoke 공용 모듈(`aws_deploy.py`·`aws_pdf_smoke.py`가 사용)
- `aws_pdf_smoke.py`: 합성 PDF로 운영 인증 smoke(업로드·변환 결과가 원본 문서 하나로 저장되고 AI 처리 완료)
- `aws_waf_content_probe.py`: 인증 없이 합성 텍스트로 WAF 라우팅 확인
- `aws-deploy-notify.py`: 배포 실패를 SNS 운영 알림으로 발행(`deploy.yml`)
- `github-deployment-protection.py`: GitHub feedback 환경 승인·main 전용 보호 준비/적용

상세 사용법은 [`docs/script.md`](../docs/script.md)를 참고한다.
