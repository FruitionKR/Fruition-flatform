# 2026-11-02 alpha 사용량·업로드 한도 배포 검토

릴리스: `bd2bd019e9a4837d8a72281f0cc9bd501c152c2a` (마지막 성공 배포 `2c288f31e68d899a481a1e23a21c553a7be168de`)

## 소스

- Access [PR56](https://github.com/FruitionKR/Fruition-access/pull/56) → `914319df8932b4882eb690d3755a7b13e6d4e23f`
  - V31 refresh token 조회 인덱스(CONCURRENTLY, UNIQUE token_hash 포함)
  - 운영 Hikari 풀 5
- Document [PR177](https://github.com/FruitionKR/Fruition-document/pull/177) → `8ec769f7ceb5f02566b6f233287fb8593ae2d0bb`
  - AI 사용량 한도와 업로드 한도
  - 저장 공간 API, `error_code`
  - 채팅·작업 로그 인덱스
  - V85–V89, Hikari 5
- Frontend [PR222](https://github.com/FruitionKR/Fruition-frontend/pull/222) → `72e483478ab0d68cc173e9cb445822dff41cc711`
  - 한도 안내와 저장 공간 표시
  - 업로드 동시 2개 제한
  - 그래프 갱신 개선
- AI `6aae9d200fdd776eb0ce8669efe93d439731b702`
  - 운영 대비 90커밋 앞선 main을 그대로 배포한다(수용된 범위).
  - `ai_schema.sql`은 새 테이블 3개, 새 컬럼, 새 테이블의 unique index만 더한다.
  - `DROP COLUMN IF EXISTS wiki_pages.merged_into_page_id`도 포함한다. 이 컬럼은 운영 소스(`30f5c74`) 스키마와 코드 어디에도 없어서 운영에서는 아무 일도 하지 않는다.
- Platform [PR134](https://github.com/FruitionKR/Fruition-flatform/pull/134) → `e80c38c710332d4cefc642454e76f518148137c5`
  - KEDA 0대 축소, 배포 여유 용량 확보, Kafka offset 보존
  - 운영 `AI_LIMIT_ENABLED: "false"`

## 시험

- PR CI와 병합된 main CI가 모두 통과했다.
  - Access: https://github.com/FruitionKR/Fruition-access/actions/runs/41415836611
  - Document: https://github.com/FruitionKR/Fruition-document/actions/runs/41415844703
  - Frontend: https://github.com/FruitionKR/Fruition-frontend/actions/runs/41415855365
  - Platform: https://github.com/FruitionKR/Fruition-flatform/actions/runs/41415863533
- 로컬 테스트: Access 594, Document 1561, Frontend 1595, Platform 295.
- DB 격리 시험: https://github.com/FruitionKR/Fruition-flatform/issues/135 (요약은 `alpha-limits-2026-11-02-migration-evidence.json`)
  - PostgreSQL 16, 네트워크 없음, 합성 데이터
  - 이전 스키마 적용 → 논리 백업·복원 → 정방향 적용 → 다시 논리 백업·복원 순서로 진행했다.
  - INVALID 인덱스 0, 이전 버전 형태 INSERT 성공, exit 0, `MIGRATION_AND_LOGICAL_RESTORE_OK`.

## 시험하지 않은 것과 위험

- 운영 데이터 규모에서 `CREATE INDEX CONCURRENTLY`가 걸리는 시간은 재지 않았다.
  - lock_timeout은 120s다. 오래 열린 트랜잭션이 있으면 migration이 실패하고 INVALID 인덱스가 남는다.
  - 복구 절차는 각 SQL 주석에 있다.
- V31은 `token_hash` UNIQUE 인덱스다. 운영에 중복이 있으면 실패한다. 애플리케이션은 단건 조회를 전제로 하지만, 운영 DB를 직접 확인하지는 않았다.
- RDS PITR와 스냅샷 복원은 시험하지 않았다. 배포 직전에 두 DB의 수동 스냅샷을 만든다.
- schema가 바뀌므로 이전 이미지 rollback은 fingerprint gate에 막힌다. 문제가 생기면 앞으로 고치는 방식으로 대응한다.
- Kafka 설정 변경으로 broker가 한 번 재시작해 1~2분간 이벤트가 지연될 수 있다.
- AI worker가 0대로 줄어든 뒤 첫 AI 작업은 3~5분 cold start가 생길 수 있다.
- AI 사용량 한도는 운영 configmap으로 꺼져 있다. 업로드 한도는 켜져 있다.

이 파일은 배포 성공 증명이 아니다. 배포 run의 preflight, migration, rollout, smoke 결과로 판단한다.
