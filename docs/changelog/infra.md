# 인프라 변경 기록

## 2026-09-17

- Ubuntu Actions에서 archive provider 검증이 실패하던 문제를 Linux amd64 공식 체크섬 추가로 수정했습니다. Mac arm64 체크섬과 provider 버전은 유지하며 Terraform validate를 통과했습니다.

- AWS 초기 배포용 private Runner, OIDC, WAF 비용 보호, CloudWatch 수집·대시보드와 Discord 알림을 구성했습니다.
- API별 2개 Pod와 순차 교체·PDB·ALB readiness gate, 비관리자 실행, Kafka mTLS·역할별 ACL을 적용했습니다.
- DB 변경 검토·업무 smoke·동일 schema rollback·최초 설치 재시도 절차를 추가하고, DB 사전검사에서 명시적 TLS URI를 허용하도록 맞췄습니다.
- 로컬 SMTP·웹훅·계정 입력, Terraform state/plan은 Git에서 제외합니다. 실 AWS 배포·복원 검증은 별도이며 서비스 이미지 4종 재빌드가 필요합니다.
- 검증: Terraform validate, 플랫폼 61개 테스트, AI TLS 5개 테스트와 런타임 권한 smoke 4개 통과. 이중화 증설은 포함하지 않았습니다.
