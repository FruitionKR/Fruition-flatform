# 플랫폼 저장소와 문서 소유권

## 맥락

네 서비스의 소스를 분리했지만 infra·k8s·scripts·docs가 통합 저장소 루트에 남아 있었다. 서비스별 코드와 인프라의 변경 주체, DB 테이블과 DB 인스턴스의 소유권을 명확히 해야 한다.

## 결정

`platform/`을 독립 저장소로 구성한다. Terraform·공용 Compose 의존 서비스·Kubernetes manifest·모니터링·통합 실행과 E2E는 platform이 소유한다. Document 전용 점검 SQL은 Document에 둔다. 서비스 단독 빌드는 각 서비스의 Gradle/npm/Python 명령으로 실행한다.

서비스 API·데이터 모델·실행법·서비스 내부 ADR은 각 서비스의 docs로 이동한다. 공통 통신·인가·이벤트·복구·인프라 결정은 platform/docs에 유지한다. 과거 혼합 문서와 diagrams는 platform/docs/backlog에 원문으로 보관한다. 현행 전체 아키텍처는 platform/docs/architecture.md다.

platform 단독 IaC CI와 형제 서비스 checkout이 필요한 계약 테스트를 분리한다. platform 배포 workflow는 이미 게시된 이미지 묶음 태그를 입력받으며 서비스 소스를 빌드하지 않는다. 태그를 플랫폼 커밋 SHA에서 추정하지 않는다.

## 대안과 기각 사유

- infra·k8s를 서비스마다 복제: 클러스터·공유 네트워크 설정과 Terraform state 소유자가 중복된다.
- 모든 문서를 platform에 유지: API·스키마 변경과 문서 변경의 저장소가 달라진다.
- 모든 스크립트를 이름별 서비스에 이동: 공통 환경변수·runtime 관리·Compose 연동을 중복하게 된다.

## 결과

다섯 저장소를 형제 폴더로 checkout하면 통합 개발할 수 있다. 서비스 단독 빌드와 platform IaC 검증은 각각 독립 실행한다. 원격 저장소 URL·OIDC 연결·서비스 이미지 게시와 서비스별 SHA release manifest는 실제 원격 분리 단계에서 구성한다. 원격 게시·배포는 이번 작업에 포함하지 않는다.
