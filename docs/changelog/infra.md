# 인프라 변경 기록

## 2026-09-18

- 빈 DB의 최초 설치에 운영 버전 호환성 증명을 요구하던 순환 조건을 `initial-install` 검토로 분리했습니다. DB 3개 빈 상태 검사 후 SHA·설정·manifest를 고정하고, 설치 완료 schema가 일치하며 로그인·문서·AI smoke까지 통과한 경우에만 성공 release를 기록합니다. 게시 이미지 3종의 DB 마이그레이션·재실행·논리 복원 시험과 AWS 테스트 73개를 통과했습니다. 실제 시험 기록 PR #10을 참조하는 대상 이미지 릴리스 검토 JSON도 추가했습니다. 실제 EKS 최초 앱 배포와 업무 smoke는 아직 수행하지 않았습니다.

- RDS 관리자에게 migration role의 INHERIT·SET 소속이 자동 부여되지 않아 기본 권한 설정이 실패하던 문제를 명시적 GRANT로 수정했습니다. 서비스 계정에는 관리자 권한을 부여하지 않습니다. 실제 RDS의 서비스 DB 3개·계정 6개 초기화 및 권한 검증, 로컬 회귀 테스트 68개를 통과했습니다.

- Ubuntu Runner 초기화에서 `awscli` 패키지를 찾지 못해 중단되던 문제를 AWS 공식 CLI v2 설치 파일 사용으로 수정했습니다. 재시도 시 기존 설치를 갱신하며 Runner 스크립트 문법 검사와 교체 후 재등록 안내를 추가했습니다. 전체 테스트 68개와 Terraform validate를 통과했으며, Terraform 적용 시 Runner 교체가 필요합니다.

## 2026-09-17

- ElastiCache 생성 API가 거부한 한글 설명을 ASCII 설명으로 수정했습니다. Redis 권한·암호화·용량 설정은 유지합니다.

- AWS 첫 적용에서 거부된 DB·Redis 보안 그룹 설명의 > 문자를 제거했습니다. RDS TLS 파라미터는 pending-reboot로 명시하고 CloudWatch JSON 끝 개행·Redis ACL/비활성 사용자 인증 표기를 AWS 응답과 맞춰 반복 변경을 제거했습니다. 실제 Redis 권한 검사 포함 전체 테스트 68개와 Terraform validate를 통과했습니다.

- 실제 AWS 인증에서 확인한 GitHub immutable OIDC subject 형식을 지원합니다. API의 정확한 sub_claim_prefix를 필수 입력으로 받아 publisher/main과 deploy/feedback 신뢰 정책에 적용하고 저장소 이름 일치를 검증합니다. 기존 이름 전용 추정 때문에 발생하던 AssumeRoleWithWebIdentity 실패를 수정했습니다.

- 서비스 main CI 성공 커밋을 확인해 이미지 4종을 immutable ECR 태그와 GitHub Release로 자동 게시하는 workflow를 추가했습니다. 운영자가 릴리스 ID를 선택하고 feedback 승인 후 배포하며 실제 digest를 대조합니다. main 전용 게시 IAM 권한은 배포 권한과 분리했습니다.
- 게시 활성화는 Terraform 재적용과 Repository variables 설정 후 진행합니다. 로컬 신규 테스트 7개·기존 IaC/Runner 검사·actionlint·Terraform validate 및 실제 GitHub 읽기 검증을 통과했으며, 이미지 게시·AWS 배포 실검증은 아직 수행하지 않았습니다.

- AWS 실제 입력을 `.local/aws/`에서 관리하도록 폴더 전체 Git 제외 규칙과 초기화·계획·백업 안내를 추가했습니다. 실제 설정과 기존 경로 링크는 커밋하지 않으며 bootstrap state는 별도 백업합니다. 로컬 설정 4개 제외 및 비밀정보 검사를 통과했습니다.

- EKS 기본 애드온 4개를 직접 관리해 모듈 출력의 resolve_conflicts 폐기 경고를 제거했습니다. 기존 버전·설정·노드 생성 후 설치 순서를 유지하고 개별 moved 블록으로 기존 주소를 이전합니다. 로컬 plan은 경고 없이 198개 생성·변경/삭제 0개이며 validate와 관련 테스트 5개를 통과했습니다.

- 배포·Runner 점검의 job env에서 사용할 수 없는 runner 컨텍스트를 제거하고 실행 단계에서 임시 kubeconfig 경로를 설정합니다. actionlint 검증을 CI에 추가해 실행 전 워크플로 문법 오류를 확인합니다. 검사 설정 파일의 경로도 CI 트리거와 계약 테스트에 포함했습니다.

- Ubuntu Actions에서 archive provider 검증이 실패하던 문제를 Linux amd64 공식 체크섬 추가로 수정했습니다. Mac arm64 체크섬과 provider 버전은 유지하며 Terraform validate를 통과했습니다.

- AWS 초기 배포용 private Runner, OIDC, WAF 비용 보호, CloudWatch 수집·대시보드와 Discord 알림을 구성했습니다.
- API별 2개 Pod와 순차 교체·PDB·ALB readiness gate, 비관리자 실행, Kafka mTLS·역할별 ACL을 적용했습니다.
- DB 변경 검토·업무 smoke·동일 schema rollback·최초 설치 재시도 절차를 추가하고, DB 사전검사에서 명시적 TLS URI를 허용하도록 맞췄습니다.
- 로컬 SMTP·웹훅·계정 입력, Terraform state/plan은 Git에서 제외합니다. 실 AWS 배포·복원 검증은 별도이며 서비스 이미지 4종 재빌드가 필요합니다.
- 검증: Terraform validate, 플랫폼 61개 테스트, AI TLS 5개 테스트와 런타임 권한 smoke 4개 통과. 이중화 증설은 포함하지 않았습니다.
