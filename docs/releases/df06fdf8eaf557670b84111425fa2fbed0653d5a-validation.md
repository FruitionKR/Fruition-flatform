# 대용량 PDF 분할 처리 릴리스 검토

대상 릴리스: `df06fdf8eaf557670b84111425fa2fbed0653d5a`

## 소스

- FruitionKR/Fruition-access: `b73cf750a312383057dad366ee5827868a0c9354`
- FruitionKR/Fruition-ai: `f8ef19f33282807ed950ca27cb1820593f7ac9f1`
- FruitionKR/Fruition-document: `c4152ec27b96c42b0d5f9ad3739fae57c1a62b18`

## 변경과 검증 근거

- [Document PR #8](https://github.com/FruitionKR/Fruition-document/pull/8): S3 직접 multipart 업로드, 원본 Range 조회, 페이지 묶음 변환, 변환 진행 상태 재개 및 AI 입력 분할. Gradle 시험 886개와 실제 MinIO 65MiB multipart 복사·완료 재호출 시험을 통과했다.
- [AI PR #11](https://github.com/FruitionKR/Fruition-ai/pull/11): S3 Range 기반 PDF 배치 변환, 제한된 동시 AI 작업 및 중단된 agent 실행의 재전달 처리. 실제 PostgreSQL을 포함한 pipeline 시험 1,279개 통과, 12개 조건부 생략, converter 시험 8개 통과. 실패 상태를 커밋한 뒤 예외를 전달하는 회귀 시험은 이전 구현에서 실패하고 수정본에서 통과했다.
- [Platform PR #22](https://github.com/FruitionKR/Fruition-flatform/pull/22): S3 권한·CORS·임시 객체 수명 관리, converter 선행 rollout, 배포 후 실제 PDF 검증. AWS 관련 단위 시험 98개 및 GitHub CI 통과.

## DB 호환성과 복원 범위

Document V50은 기존 변환 큐에 기본값이 있는 진행·재시도 컬럼 다섯 개와 claim 인덱스를 추가한다. 기존 컬럼을 제거하거나 타입을 변경하지 않으므로 `expand-only`로 검토한다. 실제 PostgreSQL 16.14의 합성 큐 1,000행에서 기존 행 기본값, 구버전 형태 INSERT, 새 claim 및 stale 복구 쿼리, 인덱스 생성과 테이블 재작성 부재를 확인했다. pg_dump 논리 복원 후 내용 checksum이 일치했다. 공개 근거는 Document PR #8의 `docs/db/v50-rehearsal-2026-09-21.md`이다.

이 리허설은 격리된 합성 변환 큐 대상이며 운영 부하·전체 DB 복원·RDS PITR 검증을 의미하지 않는다. 전체 Flyway V1–V50 실행은 Document의 실제 PostgreSQL Testcontainers 시험에서 별도로 검증했다. V50 적용 후 schema fingerprint가 바뀌므로 이전 성공 릴리스의 자동 rollback 조건은 충족하지 않는다. 실패 시 컬럼을 삭제하지 않고 호환되는 수정으로 복구한다.

## 운영 성공 조건

이미지 게시 manifest의 소스와 네 이미지 digest를 확인한 후 `action=deploy`로 배포한다. converter가 준비된 뒤 나머지 서비스를 교체하고, 기존 로그인·문서 저장·AI ingest 검증을 통과해야 한다. 이어 65MiB / 11페이지 PDF로 multipart 완료 및 같은 요청 재호출, S3 Range 읽기, 두 묶음 변환과 AI 완료, 시험 문서 정리를 검증한다. 이 추가 검증 성공 전 프런트엔드의 직접 전송 기능을 운영에 배포하지 않는다.

실제 2GiB 초과 PDF 전체 OCR·AI 완료는 이 시험의 검증 범위 밖이다. 대용량 원본의 Range 읽기 및 제한된 메모리 사용은 별도 회귀 시험으로 검증했으며 처리 비용과 시간은 페이지 수와 내용에 따라 증가한다.

## 실제 배포 결과: 중단 및 변환 서비스 복구

[운영 배포 실행](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35582927074)은 2026-09-21 converter 선행 rollout 중 중단했다. 새 이미지의 CUDA/cuDNN 의존성을 압축 해제하면서 CPU 작업 노드의 20GiB 디스크가 부족해졌다. 다른 애플리케이션 교체는 시작되지 않았으며 기존 converter는 계속 Ready 상태였다. 배포를 취소한 뒤 배포 전 converter template을 복원했고 rollout 성공과 디스크 여유 공간 회복을 확인했다.

Document V50은 중단 전에 정상 적용됐다(Flyway 실행 0.030초). DB 확장 컬럼을 되돌리지 않았으며 이후 배포는 V50이 적용된 상태에서 진행한다. 이 릴리스는 PDF 운영 검증을 통과하지 않았으므로 재배포 대상으로 사용하지 않는다. CPU 전용 의존성을 강제한 후 새 이미지 릴리스로 검증을 다시 진행한다. 프런트엔드는 이 실행에서 활성화하지 않았다.
