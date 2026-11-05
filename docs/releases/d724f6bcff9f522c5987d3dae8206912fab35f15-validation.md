# 2026-11-06 통합 릴리스 배포 검토

릴리스: `d724f6bcff9f522c5987d3dae8206912fab35f15`. 마지막 성공 배포는 `05ecbfd24b15b9adc8027428c154bb0746bead55`이다(운영 이미지 digest가 그 manifest와 일치함을 확인).

## 소스

### Document `e1cb1062bce12916fd898ba7f1ef85518b95899a`
release [PR212](https://github.com/FruitionKR/Fruition-document/pull/212)로 dev를 main에 반영했다.

| PR | 내용 | DB |
|---|---|---|
| #207 | AgentRun 사용량을 크레딧 설정과 관계없이 수집 | 없음 |
| #209 | 폴더를 편집할 수 없는 사람의 폴더 넣기·꺼내기 거절(`403 DOCUMENT_WRITE_FORBIDDEN`) | 없음 |
| #208 | 되묻기 이유 코드와 보기 권한 문서를 채팅 메시지에 저장 | V97 |
| #210 | Agent turn 참고 문서 첨부, 첨부 수정 프록시, 병합 전용 저장 | 없음 |
| #211 | 영구 삭제 때 core_db 복사본을 지우고 AI에 `document_purged` 전송 | V98~V106 인덱스 9개(CONCURRENTLY) |

### AI `dcbf58a72c054f1ee8779f0cd54cee03fbb074f0`
운영 `31a50b89` 이후 변경이 모두 나간다. #224 취소 run 상태, #223 영구 삭제 복사본 정리, #222 참고 문서, #221 거절된 수정안, #220·#214·#211 release, #217 Markdown 수정(다른 개발자 작업 포함).

스키마는 추가만 한다: `agent_run_artifacts` nullable 컬럼 3개, `ai_document_purges`와 부분 인덱스, 트랜잭션 밖 온라인 인덱스 2개. 온라인 인덱스 실패는 배포를 멈추지 않고 Job 로그에 `ai_db 인덱스 미생성`으로 남는다.

### Access `e590bb57b2056c318473306e8de7d3ab85067f10`
운영과 같다. 이미지를 재사용하므로 교체되지 않는다.

### Frontend `1558b19ac0e7eb22ef5b0ce7e29a751bc613a9d8`
#237 계정 단위 AI 설정 메뉴, #238 AI 작업 자동 처리 설정, #239 휴대폰 사용, #244 서버 병합 뒤 메모 커서·입력 유지, #242 작업 탭 문서 첨부, #243 그래프 노드 표시.

### Platform
- [PR153](https://github.com/FruitionKR/Fruition-flatform/pull/153): `k8s/base/configmap.yaml`의 `JEV_*` 6개를 `true`로 바꾼다. 운영 `fruition-pipeline` Secret의 `TYPESAFE_API_KEY`는 2026-11-05 확인 때 값이 비어 있었다. 코드 주석상 키가 없으면 기존 경로로 처리한다. **키를 넣기 전에는 설정이 켜져도 Jev 판정이 실제로 돌지 않는다.**
- [PR154](https://github.com/FruitionKR/Fruition-flatform/pull/154): 로컬 agent worker 설정. 운영 영향 없음.

## 배포 순서와 불일치 구간 (`scripts/aws_deploy.py`)

migration Job(access → document → ai) 뒤 교체 순서는 converter → access-svc → document-svc → pipeline-api → 나머지(frontend, AI worker) 동시다.

- **`document_purged` 유실을 알고 받아들인 구간이 있다.** PR212가 권장한 순서(AI 먼저)와 달리 한 묶음으로 나가, `document-svc`가 `ingest-worker`보다 먼저 바뀐다. 옛 `ingest_worker`는 이 command를 편입 command로 읽고 버린 뒤 offset을 넘긴다. 사용자가 이 위험을 받아들이고 한 묶음 배포를 결정했다.
- `DocumentTrashPurgeWorker`는 새 Pod가 뜨는 즉시 첫 삭제를 돈다. 배포 직전 읽기 조회에서 30일이 지난 휴지통 문서는 0건이고, 가장 오래된 항목은 2026-11-05 20:03 UTC에 대상이 된다. 이 시각 전에 롤아웃이 끝나면 자동 영구 삭제로는 유실이 나지 않는다. 사용자가 직접 지우는 경로는 이 값으로 알 수 없어 배포 뒤 로그로 확인한다.
- 옛 frontend는 document 뒤에 바뀐다. 짧은 구간에 옛 화면이 #209의 새 403을 받을 수 있다.
- 새 frontend는 document 뒤에 뜨므로 새 API가 먼저 준비된다.

## 시험

PR CI와 병합된 main CI가 모두 통과했다. Document main CI: https://github.com/FruitionKR/Fruition-document/actions/runs/42072774888

DB 격리 시험: https://github.com/FruitionKR/Fruition-flatform/issues/155
- PostgreSQL 16.14, 외부 통신 없음, 합성 데이터, 운영과 같은 계정 구성
- Document는 운영·후보 bootJar의 `--migrate-only`(실제 Flyway), AI는 `migrate_ai_schema` 모듈로 적용했다.
- 적용 전후 논리 백업·복원, INVALID 인덱스 0, 옛·새 형태 쓰기 성공, `MIGRATION_AND_LOGICAL_RESTORE_OK`

운영 DB 읽기 점검: PG 16.13, `source_refs`가 JSON이 아닌 행 0건(전체 117행).

## 시험하지 않은 것과 위험

- 이번 배포 담당이 전체 테스트를 로컬에서 다시 돌리지 않았다. 코드 시험은 CI에 기댄다. 코드 리뷰 결과도 이 파일에 적지 않는다.
- 운영 규모에서 V98~V106의 소요 시간은 재지 않았다. 각 파일은 잠금을 최대 120s 기다리고 Job 제한은 600s다. 실패하면 INVALID 인덱스가 남고 복구 절차는 V95 SQL 주석에 있다.
- V106 뒤에는 JSON이 아닌 `source_refs` 쓰기가 실패한다. 앱은 `SourceRefListJsonConverter`로 쓴다.
- #211은 지운 본문을 복구할 수 없다. 첫 실행 시점은 Pod 기동 직후다.
- RDS PITR·스냅샷 복원은 시험하지 않았다. 배포 직전에 두 RDS 인스턴스의 수동 스냅샷을 만든다.
- schema가 바뀌므로 이전 이미지로의 rollback은 fingerprint gate에 막힌다. 문제가 생기면 앞으로 고쳐 나간다.

이 파일은 배포 성공 증명이 아니다.
