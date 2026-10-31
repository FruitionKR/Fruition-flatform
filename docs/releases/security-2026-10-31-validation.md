# 2026-10-31 최신 main 보안 통합 배포 검토

## 소스 통합

- AI [PR172](https://github.com/FruitionKR/Fruition-ai/pull/172): 데이터 파기와 작업 저장 fence 및 객체 변경 journal.
- Access [PR55](https://github.com/FruitionKR/Fruition-access/pull/55): 인증번호 확인·초대·refresh 회전/폐기 동시성. 최신 main의 이메일 재인증·이전 주소 알림을 보존한다.
- Document [PR172](https://github.com/FruitionKR/Fruition-document/pull/172): 내부 경로 토큰 검사·늦은 결과·폴더 복원·이미지/음성 저장과 파기·회의 멤버십. 최신 main의 RSA와 자동 병합을 보존한다.
- Frontend는 `d2616c2984926b4b470a79d4826d7d4bf6b46034` 그대로다. 최신 Access에 이전 주소 알림이 구현되어 있으므로 과거 로컬 문구 수정은 적용하지 않는다.
- 과거 로컬 수정은 이름 있는 stash와 별도 패치 백업에 보존했다. 기존 보안 보고서의 기준 HEAD는 최신 main보다 오래되었다. 공개 HMAC 키 기동 거부만 추가하던 초안은 최신 RSA 검증으로 대체하며, 새 family 마이그레이션은 이미 사용 중인 V28 대신 V30이다.

## DB 검토와 실제 격리 시험

마지막 성공 배포 `67867a8317ff59eec05b0fb52dbbafabfb0a4617` 소스 대비 Access V30과 Document V83이 추가된다. AI schema SQL과 migration entrypoint는 동일하다. 운영 DB 현재 상태는 배포 preflight에서 검증해야 한다.

- PostgreSQL 16 격리 컨테이너에서 Access V1–29, Document V1–82의 정확한 SQL 파일을 순서대로 적용했다. 운영 데이터·비밀값은 사용하지 않았다.
- 기존 사용자 1개와 refresh token 2개를 합성 입력했다. 두 DB를 `pg_dump -Fc`로 백업하고 서로 다른 DB에 `pg_restore --exit-on-error`로 실제 복원했다.
- 정확한 V30/V83을 적용한 뒤 다시 백업·별도 복원했다. 기존 토큰 두 개의 서로 다른 family, 구 버전 형태 INSERT의 기본 family, 복원된 데이터 수와 새 인덱스 두 개를 확인했다.
- 실행 결과: exit 0, `MIGRATION_AND_LOGICAL_RESTORE_OK`. 외부 네트워크 없음, 읽기 전용 소스/rootfs, capability 제거, 비특권 사용자와 자원/시간 제한을 적용했다.
- 이 시험은 SQL 스키마·합성 토큰의 논리 복원이다. 운영 데이터 규모·장시간 잠금·RDS PITR·객체 버전 복원 시험을 수행했다고 주장하지 않는다. 전체 앱 동작은 각 PR CI 및 배포 업무/PDF smoke에서 별도 확인한다.
- V30의 휘발성 기본값은 테이블 재작성과 잠금을 수반한다. 기존 토큰은 각각 별도 family로 초기화된다. 구버전 Access가 남아 있으면 회전 계보 보장이 완전하지 않으므로 전 인스턴스 갱신이 필요하다. V83은 비동시 인덱스 생성이다.
- schema가 변경되므로 이전 이미지의 자동 rollback은 fingerprint gate에 막힐 수 있다. 배포 검사를 우회하거나 migration 이력을 수정하지 않는다.

실행 증거 SHA-256: `0e596c41ffec634ed8f67e40c597cf247feb58dd1c2d1a9a03ab40c667101d09`.

## 완료 조건

각 PR과 병합 main의 전체 CI 성공, 정확한 소스 SHA의 이미지 release 게시, 환경 보호 승인, DB preflight/migration, rollout, 인증 업무 smoke 및 PDF/AI smoke 통과를 확인한 뒤 배포 성공으로 기록한다. 현재 이 파일은 배포 성공 증명이 아니다.
