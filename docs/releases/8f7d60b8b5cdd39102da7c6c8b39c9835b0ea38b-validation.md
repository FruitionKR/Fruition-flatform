# 삭제 문서 위키 정리·BGE-M3 운영 준비 릴리스 검토

대상 릴리스: `8f7d60b8b5cdd39102da7c6c8b39c9835b0ea38b` ([게시 실행](https://github.com/FruitionKR/Fruition-flatform/actions/runs/36430806118))

- Access: `b73cf750a312383057dad366ee5827868a0c9354` (운영과 같음)
- Document: `0b32a3d9c11e4615191f2bf9dd68234bcf83367c` ([PR #23](https://github.com/FruitionKR/Fruition-document/pull/23))
- AI: `be6cbebbe0ede9f8e76e56035a32694d33489580` ([PR #21](https://github.com/FruitionKR/Fruition-ai/pull/21))

## 포함 변경

- Document #18: 문서·폴더를 휴지통으로 옮기면 `document_deleted`를 발행하고, 삭제한 문서의 `wiki_page_contributions`를 꺼서 로그 되돌리기가 그 문서를 되살리지 않게 한다. 편입 도중 삭제된 문서의 늦은 결과도 기여를 꺼진 채 저장한다.
- Document #22: 사라진 MinIO 테스트 이미지를 Chainguard 이미지(digest 고정)로 교체했다. 테스트 전용이다.
- AI #19: 근거 검색 키워드 비중을 한국어 질문 10%, 영어 질문 40%로 나눴다. 운영이 `text-only`인 동안은 효과가 없다.
- AI #20: `wiki_source_tombstones`로 삭제 원본을 표시해 복구가 그 source 페이지·링크를 되살리거나 결과로 보고하지 않게 했다.
- AI #22·#23·#25: BGE-M3를 배치 1로 계산하고 모델을 이미지에 넣어 오프라인으로 로드한다. 이 릴리스만으로는 운영 임베딩이 켜지지 않는다(Platform #30 별도).
- AI #24: `/skill`만 보낸 요청을 라우터에 넘기지 않고 초안 생성 또는 사용법 안내로 처리한다.

## DB 변경과 호환성 (`expand-only`)

운영 마지막 배포(`ed5c3285…`)는 Document V50, AI `c6a0308`이다. 이번 배포는 아래를 한 번에 적용한다.

- Document V51(팀원 변경): V48의 workspace 전체 이름 고유 인덱스를 부모 폴더별 고유성(`document_tree_names`·트리거)으로 바꾸고 활성 이름을 backfill한다. 기존 제약을 완화하는 방향이라 구버전 코드의 쓰기와 호환된다. backfill 동안 `documents`·`folders` 쓰기 잠금이 걸린다.
- Document V52(데이터 변경):
  - 휴지통 문서마다 `document_deleted` command를 `ai_command_outbox`에 한 번 넣는다. topic은 기본값 `ai.ingest.command`이다.
  - 휴지통 편집 문서의 `status`를 `uploaded`로 바꾸고, 그 문서들의 `wiki_page_contributions.active`를 끈다.
  - 스키마 변경은 없다.
- Document V53: `wiki_page_contributions(source_document_id) WHERE active` 부분 인덱스를 추가한다.
- AI `ai_schema.sql`: `ai_model_usage`(모델 사용량 원장, AI #16)와 `wiki_source_tombstones` 테이블을 추가한다(`IF NOT EXISTS`). 기존 테이블은 바뀌지 않는다.

**배포 전 필수:** 운영 DB에서 [V51 사전 충돌 조회](https://github.com/FruitionKR/Fruition-document/blob/main/docs/db/v51-folder-names-2026-09-22.md)를 실행해 0행인지 확인한다. 같은 부모 폴더에 이름이 겹치는 파일·폴더가 있으면 V51이 실패해 배포가 멈춘다. 데이터는 원상태로 남는다.

**되돌림 주의:**
- V52의 데이터 변경은 이미지 롤백으로 되돌아가지 않는다.
- V51 이후 다른 폴더에 같은 이름이 생기면 V48 제약으로 단순 복원할 수 없다.
- 되돌리려면 배포 전 백업이나 시점 복원이 필요하다.

## 검증

- Document: [PR #18](https://github.com/FruitionKR/Fruition-document/pull/18) Testcontainers 통합 테스트에서 V52·V53 적용과 삭제·폴더 삭제·편입 중 삭제 시나리오를 확인했다. `dev` 로컬 901개, [main push CI](https://github.com/FruitionKR/Fruition-document/actions/runs/36429905970) 통과.
- AI: `dev` 로컬 1272개 통과. 같은 코드로 빌드한 이미지 안에서도 pytest를 실행했다(lab·eval 스크립트와 데이터를 마운트한 파일 포함, 실패 0).
- pipeline 이미지: 게시 실행에서 BGE-M3 단계(#31)가 완료됐다. 로컬 arm64 이미지에서 `--network none`·앱 사용자(10001)로 모델 로드·임베딩과 최고 메모리 1.97GB를 확인했다.
- 호환·복원 리허설: [Document PR #24](https://github.com/FruitionKR/Fruition-document/pull/24)(`docs/db/v51-v53-rehearsal-2026-09-28.md`). 운영과 같은 migration/runtime role 분리 환경에서 **V50부터** V51~V53을 적용했다.
  - 적용 시간 8/9/1ms, 테이블 재작성 없음
  - `core_runtime`의 새 테이블 권한과 쓰기 트리거 동작
  - V50 시점 `pg_dump`→`pg_restore` checksum 일치(0.28s), 복원본 재적용 동일 결과
  - 이름 충돌 시 사전 조회가 잡고, V51이 실패하면 V50 그대로 남는다
  - AI 운영 스키마(`c6a0308`)에서 새 스키마 재적용·`ai_runtime` 권한·복원
  - 운영 규모·운영 데이터 충돌 여부·RDS PITR·실제 worker 처리는 범위 밖이다.

## 배포 후 확인

- 폴더별 이름 규칙(V51): 같은 폴더의 같은 이름은 거절되고 다른 폴더는 허용되는지 확인한다.

- V52가 발행한 정리 command를 ingest worker가 처리하는지, `document_deleted` 처리에서 잠금 대기 재시도 로그만 있고 실패가 없는지 확인한다.
- 휴지통에 있는 문서의 노드가 그래프에서 사라졌는지 확인한다.
- AI 노드 디스크 사용률을 확인한다. pipeline 이미지가 약 2.1GB 커졌다.
- 운영 임베딩은 이 배포 뒤 Platform #30과 백필로 켠다.
