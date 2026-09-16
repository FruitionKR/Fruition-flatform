# 서비스별 독립 저장소 경계

## 맥락

frontend·Access·Document·AI를 각각 별도 GitHub 저장소로 관리한다. 기존 Access와 Document는 상위 Gradle 설정과 java-shared에 의존하고 API 명세·일부 테스트는 저장소 루트 파일을 직접 읽어, 하위 폴더만 추출하면 빌드가 깨진다.

## 결정

최상위 `frontend/`, `Access/`, `Document/`, `AI/`를 각각 독립 저장소 루트로 구성한다. Access와 Document는 자체 Gradle wrapper·설정·Dockerfile·API 명세·CI를 소유한다. 기존 java-shared 소스와 테스트는 두 서비스에 편입하고 상위 Gradle 프로젝트를 제거한다. Python API 명세도 pipeline 내부로 이동한다. Redis ACL 테스트는 Document 내부 계약을 사용하고 통합 인프라 테스트에서 Terraform ACL과 일치하는지 검증한다.

converter는 pipeline의 복원 코드·Rust 도구에 의존하므로 AI와 같은 저장소에 둔다. 통합 인프라·배포 준비 스크립트는 platform 저장소가 소유한다([관리 경계](0020-platform-and-document-ownership.md)). HTTP/Kafka 계약과 DB 소유권은 변경하지 않는다.

## 대안과 기각 사유

- 폴더 이동만 수행: 빌드가 다른 저장소 소스와 상위 경로에 계속 의존한다.
- 공통 라이브러리를 별도 저장소·패키지 레지스트리에 발행: 네 서비스 외에 패키지 배포·인증·버전 관리가 필요하다. 현재 분리에는 서비스 내부 소유가 더 단순하다.
- converter 독립 저장소: pipeline 코드에 대한 추가 패키징 경계를 요구한다.

## 결과

각 서비스는 다른 서비스 소스 없이 빌드·테스트할 수 있다. 공통 기술 코드의 수정은 각각 반영해야 하며 JWT·오류 응답 같은 통신 계약은 함께 검증한다. 원격 저장소·OIDC·서비스별 이미지 SHA 전달은 실제 GitHub 분리 시 연결할 작업이다. 이번 변경은 폴더와 빌드 준비이며 원격 게시·배포는 수행하지 않는다.
