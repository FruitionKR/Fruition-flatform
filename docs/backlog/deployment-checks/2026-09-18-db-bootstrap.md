# 최초 RDS DB 초기화 검증

## 수행 결과

- Access RDS에 `access_db`, Core RDS에 `core_db`·`ai_db`를 생성했습니다.
- 초기 조회에서 대상 서비스 DB와 계정이 없음을 확인했습니다.
- 각 DB의 runtime·migration 계정 2개씩, 총 6개를 구성했습니다. 비밀번호는 기존 Secrets Manager 값과 동일하게 주입했습니다.
- EKS의 임시 작업 Pod에서 RDS CA와 `sslmode=verify-full`로 접속했으며, 양쪽 서버에서 TLS 연결을 확인했습니다.
- runtime DML, migration DDL, runtime DDL 거부 및 서비스 계정 관리자 권한·role membership 부재를 검사했습니다.
- Core·AI DB 사이의 CONNECT/read/write 거부를 검사했습니다. Access와 Core RDS 사이의 별도 네트워크 격리 시험은 이 검사에 포함하지 않았습니다.
- 작업 후 임시 Pod·ConfigMap·NetworkPolicy·Namespace를 삭제했습니다. DB 비밀번호는 이 문서나 저장소에 기록하지 않았습니다.

## 발견한 문제와 수정

RDS PostgreSQL 관리자에게 `createrole_self_grant`의 INHERIT·SET 소속이 자동 부여되지 않아 `ALTER DEFAULT PRIVILEGES`가 실패했습니다. 초기화 관리자에게 migration role 소속을 명시적으로 부여한 뒤 중단된 작업을 재실행해 완료했습니다. 서비스 계정의 권한은 높이지 않았습니다.

로컬 PostgreSQL 16 통합 테스트에는 migration role에 대한 ADMIN 소속만 가진 관리자를 구성해 재현 조건을 추가했습니다. 초기화 반복 실행과 권한 검증을 포함한 전체 AWS 테스트 68개를 통과했습니다.

## 검증 범위의 한계

이 기록은 서비스 DB·계정·권한 초기화 결과입니다. 앱 이미지의 스키마 migration, 기존/신규 앱 호환성, 로그인·문서·AI 업무 흐름, 백업 복원 시험은 아직 수행하지 않았습니다. 따라서 이 기록을 릴리스의 `compatibility_test_url` 또는 `restore_test_url` 증거로 사용하지 않습니다.
