# 인프라 변경 기록

## 2026-10-22

- 기존 설치의 비가산 pending migration을 위한 `maintenance-cutover`를 추가했다. 이전 성공 release 전체 해시·현재 이미지 digest·DB 전후 fingerprint와 실제 리허설/복원/중단 근거를 묶고, 기존 expand-only/none/initial-install 및 rollback 검사를 유지한다.
- 503 Ingress, 기존 ALB binding 제거, 전체 앱 중지, scaler·CronJob·writer Pod/세션 부재를 확인한 뒤 실제 migration을 실행한다. 실패/중단 시 시작 기록을 보존해 후속 배포를 차단하며 정상 종료 후 scaler 복구는 운영자가 수행한다. 앱 deployer 권한은 CronJob 조회만 추가했다.
- AWS 계약 240개(실제 로컬 PostgreSQL 세션 차단 포함), Terraform 두 root fmt/init(backend=false)/validate, Kustomize 3경로, shell 30개 문법과 변경 preflight 3종 ShellCheck를 통과했다. 전체 ShellCheck의 기존 경고와 release 문서 SHA 오탐 8개는 별도 확인했으며 새 비밀정보는 발견하지 않았다.
- [실행 절차와 증거 계약](../aws-maintenance-cutover.md)을 작성했다. runner Docker 부재와 로컬 Docker 대안, 실제 리허설 미수행 상태를 명시했으며 worker는 운영 변경·analytics 송신을 하지 않았다.

- PostHog dev에 PR98이 병합된 main(`03c47f0`)의 운영 보안 계약을 통합했다. RSA 개인키 Access 전용·HMAC 제거·DB verify-full·WAF Secret 분리를 보존하고, preflight 충돌은 optional analytics와 TLS 검사를 함께 유지하도록 해결했다. MFA 강제 기본 false는 유지한다.
- AWS 계약 230개, Terraform 두 root fmt/init(backend=false)/validate, Kustomize 3경로, shell 29개 문법·변경 shell ShellCheck를 통과했다. 비밀정보 검사에서 기존 release 문서의 Access 소스 SHA 오탐 8개만 확인했으며 실제 비밀정보는 발견하지 않았다.
- [배포 호환성 감사](../posthog-deployment-compatibility.md)에 서비스별 SHA·migration 파괴적 변경·cutover/restore 증적 요구를 기록했다. Document V74–76 등은 expand-only 배포를 차단하며 live DB 이력은 미검증이다. AWS 변경·analytics 송신·배포는 수행하지 않았다.

- 통합 `dev-up.sh`에서도 Document·Access·frontend 실행 직전에 `local_analytics_env`를 적용한다. 개별 실행 스크립트와 동일하게 기본 수집 off·운영 설정 격리·명시적 LOCAL_* 설정·서비스별 Git SHA를 보장하며 기존 `SERVICE_ENV_FILE` 전달 순서는 유지한다.
- 실제 launch 함수를 임시 Git 저장소와 가짜 실행 파일로 검증하는 회귀 테스트 5개를 추가했다. 기존 184개를 포함한 AWS 계약 테스트 189개, Bash 문법, Kustomize 3개 경로 렌더링을 통과했다. 신규 테스트는 수정 전 코드에서 모두 실패하며 실제 서비스·AWS·analytics 호출은 수행하지 않는다.
- ShellCheck는 기존 `docker rm $container_ids`의 SC2086 외 추가 경고가 없음을 확인했다.

- PostHog 알파의 frontend·Access·Document·AI 런타임 환경을 추가했다. 기본 수집 off, 빈 토큰, production 환경과 서비스별 source SHA를 사용하며 토큰은 전용 ExternalSecret의 단일 키로만 주입한다.
- 수집 활성화 시 토큰 누락·잘못된 형식을 배포 preflight에서 차단하고, local native/Compose 실행은 별도 LOCAL_* 설정으로 운영 토큰 상속을 막는다. 기존 expand-only migration·fingerprint gate와 다른 Secret 키는 유지한다.
- AWS 계약 테스트, Terraform/Kustomize 및 shell 검증을 수행했다. [운영 절차](../posthog-operations.md)에 안전한 Secret 병합·승인 배포·중지·mock 검증을 정리했다. 실제 토큰 저장·analytics 송신·운영 배포는 실행하지 않았다.

- 운영 RSA 전환 후 로그인·문서 접근·refresh와 변조/필수 claim 누락 거부를 확인했다. 기존 토큰 TTL+여유시간 뒤 모든 Pod와 공통 Secret 현재 버전에서 HMAC을 제거하고, 이전 키로 새로 서명한 토큰의 401 거부도 확인했다. 플랫폼 215개와 운영 hotfix 382/1,036개 테스트가 통과했다.
- MFA 전환 뒤 본인 암호 변경이 차단되지 않도록 자기 계정 변경만 허용했다. 다른 사용자 변경과 직접 관리자 동작은 회귀 테스트 4개 및 실제 IAM 정책 시뮬레이션으로 거부됨을 확인했다.
- WAF 접근 코드 조회를 전용 Secret으로 분리해 이후 Terraform refresh가 앱 JWT 개인키 전체를 state로 읽지 않게 했다. 값 출력 없는 복사 도구와 관련 회귀 테스트 6개를 추가했다.
- MFA 필수 임시 관리자 역할과 직접 접근·다른 역할 우회 차단 정책을 추가했다. 사용자 MFA 등록·별도 접속 검증 전에는 강제 정책을 켜지 않는다.
- 비밀값 접근 없이 루트 자격증명·사용자 MFA·직접 관리자 정책·교체 경과일을 매일 감시한다. guard 테스트 10개, Terraform 검증과 운영 최초 지표 6개 발행을 확인했다.
- JWT 개인키를 Access에만 투영하고 Document에는 공개키만 전달하도록 분리했다. Secret 버전 충돌 방지·키 생성·기존 키 폐기 도구와 단계별 전환 절차를 추가하고 관련 테스트 12개를 통과했다.
- DB 연결과 migration·운영 조회를 `verify-full`로 강화하고 공식 RDS CA를 마운트했다. 운영 DB 소비자 9개와 잘못된 호스트명 거부를 확인했으며 AWS 테스트 198개가 통과했다.
- WAF 자동 스캔 대응으로 민감 파일 경로 차단, 지속/대량 차단 경보 분리, WAF 로그 미수신·ALB 자체 5xx 경보를 추가했다.
- ALB 접근 로그를 비공개 SSE-S3 버킷에 30일 보관하고 Controller annotation으로 활성화했다. 배포 전 버킷 소유 계정·리전·비공개 정책 검사와 메타데이터 전용 권한을 추가했다.
- 빈 도메인/접근 코드로 운영 접근 코드 규칙이 제거되지 않도록 사전 검증을 추가했다. SQLi 확장 본문 규칙도 기존 문서 요청 조건 안에서만 처리하고 나머지 요청은 재차단한다.
- AWS 계약 테스트 176개와 Terraform·Kustomize 검증을 통과하고, 운영 민감 경로 49건·문서 본문 57건 및 실제 로그를 대조했다. 접근 코드 규칙 일시 제거·복구와 범위 밖 검증 사항은 [운영 적용 기록](../aws-waf-review-2026-10-22.md#7-2026-10-22-운영-적용-기록)에 남겼다.
- Public ECR 다운로드 한도로 `minio-init` 이미지 pull이 실패하던 CI를 보완했다. 같은 AWS CLI 2.37.4 버전의 공식 Docker Hub 이미지를 다중 아키텍처 digest로 고정했다. 별도 Compose 프로젝트에서 4개 서비스의 정상 기동, MinIO·Kafka 초기화 종료 코드 0, 생성 버킷 조회 성공을 확인했다.

- 운영 JWT 전환 검증용 수동 Security authentication smoke workflow를 추가했다. feedback 환경의 검증 계정으로 공개 HTTPS 로그인·Access/Document 조회·refresh 교체·변조 서명 거부를 확인하고 테스트 세션을 로그아웃한다. 문서 생성·변경과 AWS 설정 변경은 수행하지 않으며 자격증명·응답 본문은 로그나 artifact에 남기지 않는다. 독립 회귀 테스트 7개를 통과했다.
- self-hosted runner 공통 계약에 맞춰 AWS_EC2_METADATA_DISABLED를 명시하고 관련 테스트 10개를 통과했다.
