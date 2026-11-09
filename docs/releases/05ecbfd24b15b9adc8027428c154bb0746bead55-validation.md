# 2026-11-04 통합 릴리스 배포 검토

릴리스: `05ecbfd24b15b9adc8027428c154bb0746bead55`. 마지막 성공 배포는 `b7f01174428025f2f33e0eabb3f177532e5b7701`이다.

## 소스

### Document `41dfa54a83a380562b9cb908e3372e258efcfd88`
release [PR204](https://github.com/FruitionKR/Fruition-document/pull/204), [PR205](https://github.com/FruitionKR/Fruition-document/pull/205)로 dev를 main에 반영했다.

| PR | 내용 | DB |
|---|---|---|
| #199 | PDF 변환 복원 요약 저장, 그림 설명 설정을 변환 요청에 전달 | V94 `documents.conversion_report` |
| #200 | 채팅 답변 듣기(TTS) 운영 스위치 `SPEECH_SYNTHESIS_ENABLED` | 없음 |
| #201 | 채팅에서 만든 문서의 이름 변경을 409 `DOCUMENT_TITLE_LOCKED`로 거절 | 없음 |
| #202 | 테스트 컨테이너 공유(테스트 전용) | 없음 |
| #203 | 변환 대기열 행을 먼저 잠그고, 변환 결과 반영의 잠금 대기를 5초로 제한 | 없음 |
| #198 | 스케줄 작업 4개를 회차마다 한 Pod만 실행, 휴지통 조회 인덱스 (다른 개발자 작업) | V95 `idx_documents_trash`(CONCURRENTLY), V96 `scheduler_leases` |
| #176 | 편입 결과의 `deleted_pages`를 기여 행과 삭제 변경으로 기록 (다른 개발자 작업) | 없음 |

### AI `31a50b89531727b9823dcd11c3cd295815eeceeb`
release [PR205](https://github.com/FruitionKR/Fruition-ai/pull/205), [PR207](https://github.com/FruitionKR/Fruition-ai/pull/207). 운영 `ad0f2c7` 이후 변경이 모두 나간다.
- #196 PDF 원문 대체 사유 안내·요약과 그림 설명(opt-in, 기본 꺼짐)
- #197, #199~#204 post_ingest 근거 정밀도 제외·부분 성공·임베딩 주기 복구, 구간 평가, PDF 연결 끊김 처리, Agent Tool 예산, 수동 ingest POST route 3개 제거, 문서 (다른 개발자 작업)
- #193 `document_quality_reviews`, #195 `wiki_pending_contributions` (다른 개발자 작업)
- #198 agent worker SIGTERM drain과 시도 한도 job 정리

스키마는 추가만 한다: 테이블 2개와 기존 데이터 채우기 DO 블록. 새 환경변수·Secret·Kafka topic은 없다.

### Access `e590bb57b2056c318473306e8de7d3ab85067f10`
- #57 워크스페이스 PDF 그림 설명 설정. V32 `workspaces.describe_pdf_figures`(`NOT NULL DEFAULT false`, `lock_timeout 5s`).

### Frontend `95ab99278dabd858072ac9d8237d44c9dacfb4b3`
- #231 트리 ⋯ 버튼·새로 만들기 메뉴·이름 말풍선 제거
- #232 랜딩 문서 보호 섹션
- #233 직접 로그아웃하면 랜딩으로 이동
- #234 PDF 변환 안내·그림 설명 설정·Markdown+그림 업로드
- #235 TTS 스위치 소비
- #236 채팅 문서 제목 잠금 UI

### Platform
- [PR148](https://github.com/FruitionKR/Fruition-flatform/pull/148): `configmap-aws.yaml`에 `SPEECH_SYNTHESIS_ENABLED: "false"`. **이 배포로 운영의 채팅 답변 듣기가 꺼진다.**
- [PR150](https://github.com/FruitionKR/Fruition-flatform/pull/150): ingest·maintenance worker의 `EMBEDDING_SERVICE_URL`과 NetworkPolicy 허용. `JEV_CONCEPT_MERGE_ENABLED=false`라 지금은 동작 변화가 없다.
- [PR147](https://github.com/FruitionKR/Fruition-flatform/pull/147) CA `max-graceful-termination-sec=900` 등 helm 설정은 Deploy workflow로 적용되지 않는다. AI #198과 함께 운영자가 별도로 적용한다.

## 배포 순서 확인 (`scripts/aws_deploy.py complete_rollout`)

교체 순서: converter → access-svc → document-svc → pipeline-api → 나머지(frontend, AI worker) 동시.

- access가 document보다 먼저 바뀐다. document `WorkspaceSettingsClient`는 `describe_pdf_figures`가 없거나 조회에 실패하면 꺼짐으로 본다. 어느 조합에서도 그림이 외부로 나가지 않는다.
- converter의 `describe_figures`는 없으면 false다. 새 document → 옛 converter, 옛 document → 새 converter 모두 호환된다.
- frontend는 document 뒤에 뜬다. 새 frontend는 `speech_synthesis_enabled`가 없으면 버튼을 숨기고, 옛 서버의 이름 변경 성공도 그대로 처리한다.
- document가 바뀐 뒤 frontend가 바뀌기 전 짧은 구간에, 옛 frontend가 채팅 문서 이름 변경에서 새 409를 받을 수 있다.
- AI migration Job 뒤 새 worker로 바뀌기 전까지 옛 worker가 끝낸 수집은 `document_quality_reviews`를 갱신하지 않는다. 그 문서를 다시 수집하면 바로잡힌다.

## 시험

PR CI와 병합된 main CI가 모두 통과했다.

로컬 시험(배포 소스와 같은 트리):
- Document `./gradlew clean test bootJar` 1,671건 통과, 실패 0
- Access `./gradlew test bootJar` 597건 통과, 모델 카탈로그 검사 통과
- AI `pipeline` 전체 pytest(실제 PostgreSQL, Python 3.12) 2,386 통과·8 건너뜀, converter 40 통과
- Frontend lint·tsc·`npm test` 1,723건·build 통과

DB 격리 시험: https://github.com/FruitionKR/Fruition-flatform/issues/151
- PostgreSQL 16, 네트워크 없음, 합성 데이터, 운영과 같은 계정·권한 구성
- Document는 운영·후보 bootJar의 `--migrate-only`(실제 Flyway), AI는 `migrate_ai_schema.py`로 적용했다.
- 적용 전후 논리 백업·복원, INVALID 인덱스 0, 옛·새 형태 쓰기 성공, `MIGRATION_AND_LOGICAL_RESTORE_OK`

코드 리뷰(document·AI·frontend·access·platform)에서 배포 차단·높음 등급 결함은 없었다.

## 시험하지 않은 것과 위험

- 운영 규모에서 V95 CONCURRENTLY의 소요 시간은 재지 않았다. 열린 트랜잭션을 최대 120s 기다리며 Job 제한은 600s다. 실패하면 INVALID 인덱스가 남고 복구 절차는 SQL 주석에 있다.
- 운영 `pipeline_runs` 규모에서 `document_quality_reviews` 채우기 DO 블록 소요 시간은 재지 않았다.
- RDS PITR 복원은 시험하지 않았다. 배포 직전에 두 DB의 수동 스냅샷을 만든다.
- schema가 바뀌므로 이전 이미지로의 rollback은 fingerprint gate에 막힌다. 문제가 생기면 앞으로 고쳐 나간다.
- Agent가 채팅에서 만든 문서의 이름을 바꾸거나 되돌리면 #201의 409로 그 단계가 실패한다.
- maintenance worker가 기동 직후와 10분마다 임베딩이 없는 활성 페이지를 다시 임베딩한다(AI #201). 배포 직후 CPU·메모리·로그를 본다.
- `FxRateService` 점유는 실패해도 10분 유지된다. 평일 11:20~11:30 배포는 피한다.

이 파일은 배포 성공 증명이 아니다.
