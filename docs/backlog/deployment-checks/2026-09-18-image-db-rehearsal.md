# 최초 배포 이미지의 DB 마이그레이션·논리 복원 시험

시험일: 2026-09-18. 대상 릴리스: `a2b46a13a49f5850a6a9febb367546d97e47da73`.

## 결과

게시된 실제 이미지로 서비스 DB 3개의 첫 마이그레이션, 동일 이미지 재실행, 별도 PostgreSQL 컨테이너로의 논리 백업 복원을 통과했습니다. 운영 RDS의 앱 스키마는 변경하지 않았습니다.

| DB | 첫 마이그레이션 | 재실행 | 복원·비교 | public 테이블 수 |
| --- | ---: | ---: | ---: | ---: |
| access_db | 7.81초, Flyway V19 | 6.95초 | 0.41초 | 16 |
| core_db | 9.01초, Flyway V48 | 7.20초 | 0.55초 | 51 |
| ai_db | 3.65초, Python SQL 실행 | 3.58초 | 0.46초 | 26 |

테이블 수는 시험용 probe를 제외하고 Flyway 이력 테이블은 포함합니다. 시간은 로컬 프로세스 실행·컨테이너 시작 등을 포함하며, 운영 RDS의 실행시간이나 복구 목표시간을 나타내지 않습니다.

## 이미지 고정

| 이미지 | 게시 digest |
| --- | --- |
| access-svc | `sha256:96bc01490cff6f55c5b4f0f1884f685967cf10f9d8ca29d0b8704709016a512e` |
| document-svc | `sha256:212a0a666f8da893a68e1c4acb223e5c1efe5b2b73ebd49051190a7f35cd4bee` |
| pipeline | `sha256:e6d6e25a3a05f30db4b201bcbf6ceea187000b751033aad0f98c0cce66fb5ca8` |

## 수행 절차

1. 외부 통신을 차단한 Docker internal network에 PostgreSQL 16 시험 서버를 생성했습니다. 운영 비밀번호 대신 합성 시험 비밀번호를 사용했으며 호스트 포트를 노출하지 않았습니다.
2. 임시 자체 서명 인증서와 `sslmode=require`로 TLS를 사용했습니다. 이 시험은 운영 CA 검증 시험이 아닙니다.
3. 비관리자 서비스 계정 6개와 DB 3개를 저장소의 `init-db-isolation.sh`로 구성했습니다. 초기화 관리자는 SUPERUSER 없이 CREATEDB·CREATEROLE을 사용했습니다.
4. digest로 고정한 linux/amd64 이미지에서 Access·Document의 `--migrate-only`, Pipeline의 `python -m app.modules.wiki_ingestion.infrastructure.migrate_ai_schema`를 실행했습니다. 앱 컨테이너는 읽기 전용 루트 파일시스템, 임시 /tmp, capability 제거와 권한 상승 금지를 적용했습니다.
5. 각 migration 계정으로 시험 테이블을 생성하고 runtime 계정으로 표식 한 행을 넣었습니다. 동일 이미지의 마이그레이션을 반복 실행해 스키마와 표식이 유지됨을 확인했습니다.
6. `pg_dumpall --roles-only`와 DB별 `pg_dump -Fc`로 역할·DB를 백업했습니다. 다른 새 PostgreSQL 서버에서 역할을 복원하고 `pg_restore --create --exit-on-error`로 DB를 복원했습니다.
7. 원본·복원본의 schema dump를 비교하고 runtime 계정으로 시험 표식을 읽었습니다. 복원 전후 모두 `validate-db-isolation.sh`를 통과했습니다: runtime DML·sequence 허용, runtime DDL 거부, 서비스 계정 관리자 속성·상속 소속 부재, 다른 DB CONNECT/read/write 거부.
8. 시험 컨테이너·볼륨·네트워크를 제거하고 임시 Docker ECR 인증에서 로그아웃했습니다.

초기 문자열 비교는 CHECK 제약식의 `varchar[] → text[]` 변환이 복원 후 각 원소의 `varchar → text` 변환으로 출력되어 실패했습니다. 의미가 같은 이 한정된 캐스트 표현과 dump 주석·임의 restrict 토큰만 정규화한 뒤 세 DB의 전체 schema dump가 일치했습니다. 제약식이나 권한 항목을 비교 대상에서 제외하지 않았습니다.

## 검증하지 않은 범위와 배포 조건

- 실제 로그인, 문서 생성·조회, AI 처리 등 업무 흐름은 실행하지 않았습니다. 이전 운영 앱이 없는 최초 설치 환경이며, 이전·새 버전 동시 호환성 시험을 수행한 것으로 기록하지 않습니다.
- 복원한 데이터는 migration이 만든 데이터와 합성 시험 표식입니다. 실제 업무 데이터 전체 정합성이나 대용량 DB 잠금·성능을 검증하지 않았습니다.
- 이 시험은 PostgreSQL 논리 백업 복원입니다. RDS 스냅샷·PITR·장애 복구 훈련은 아닙니다.
- 과거 migration에는 컬럼 삭제와 이름 변경이 포함됩니다. 빈 DB에서 전체 이력을 실행한 결과가 기존 운영 DB에 대한 expand-only 보장을 의미하지 않습니다.
- 이 기록은 `initial-install`의 `installation_test_url`·`restore_test_url` 근거로만 사용합니다. 운영 변경의 `compatibility_test_url` 근거가 아닙니다.
- 최초 설치 전용 경로는 빈 DB 확인, 동일 SHA·설정·manifest 재시도 제한, 설치 후 업무 smoke 통과 전 성공 release 기록 금지를 적용합니다. 기존 환경의 배포 호환성 조건은 유지합니다.
