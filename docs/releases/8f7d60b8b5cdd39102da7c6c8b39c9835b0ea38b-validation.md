# 삭제 문서 위키 정리·BGE-M3 운영 준비 릴리스 검토

대상 릴리스: `8f7d60b8b5cdd39102da7c6c8b39c9835b0ea38b` ([게시 실행](https://github.com/FruitionKR/Fruition-flatform/actions/runs/36430806118))

- Access: `b73cf750a312383057dad366ee5827868a0c9354` (이전 릴리스와 같음)
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

- Document V52(데이터 변경):
  - 이미 휴지통에 있는 문서마다 `document_deleted` command를 `ai_command_outbox`에 한 번 넣는다. topic은 기본값 `ai.ingest.command`이다.
  - 휴지통의 편집 문서 `status`를 `uploaded`로 바꾼다.
  - 그 문서들의 `wiki_page_contributions.active`를 끈다.
  - 스키마 변경은 없다. 이전 코드도 비활성 기여를 원래 복구 대상에서 제외하고, 휴지통 문서의 상태를 읽지 않으므로 롤링 중 구버전과 함께 동작한다.
- Document V53: `wiki_page_contributions(source_document_id) WHERE active` 부분 인덱스를 추가한다. 추가 전용이다.
- AI `ai_schema.sql`: `wiki_source_tombstones` 테이블을 추가한다(`IF NOT EXISTS`). 이전 코드는 이 테이블을 읽지 않는다.
- **되돌림 주의:** V52의 데이터 변경(편입 상태 초기화·기여 비활성화·정리 command 발행)은 이미지 롤백으로 되돌아가지 않는다. 휴지통 문서는 복구 후 다시 편입해야 한다.

## 검증

- Document: [PR #18](https://github.com/FruitionKR/Fruition-document/pull/18) Testcontainers 통합 테스트에서 V52·V53 적용과 삭제·폴더 삭제·편입 중 삭제 시나리오를 확인했다. `dev` 로컬 901개, [main push CI](https://github.com/FruitionKR/Fruition-document/actions/runs/36429905970) 통과.
- AI: `dev` 로컬 1272개 통과. 같은 코드로 빌드한 이미지 안에서도 pytest를 실행했다(lab·eval 스크립트와 데이터를 마운트한 파일 포함, 실패 0).
- pipeline 이미지: 게시 실행에서 BGE-M3 단계(#31)가 완료됐다. 로컬 arm64 이미지에서 `--network none`·앱 사용자(10001)로 모델 로드·임베딩과 최고 메모리 1.97GB를 확인했다.
- 호환·복원 리허설: [Document PR #24](https://github.com/FruitionKR/Fruition-document/pull/24)(`docs/db/v52-v53-rehearsal-2026-09-28.md`). 격리 postgres:16에서 V51 스키마·synthetic 데이터로 V52(11ms)·V53(2ms) 적용, 테이블 재작성 없음, 구·신 버전 SQL 호환, V51 시점 `pg_dump`→`pg_restore` checksum 일치(0.26s), 복원본 재적용 동일 결과, AI `ai_schema.sql` 재적용·복원을 확인했다. 운영 규모·RDS PITR·실제 worker 처리는 범위 밖이다.

## 배포 후 확인

- V52가 발행한 정리 command를 ingest worker가 처리하는지, `document_deleted` 처리에서 잠금 대기 재시도 로그만 있고 실패가 없는지 확인한다.
- 휴지통에 있는 문서의 노드가 그래프에서 사라졌는지 확인한다.
- AI 노드 디스크 사용률을 확인한다. pipeline 이미지가 약 2.1GB 커졌다.
- 운영 임베딩은 이 배포 뒤 Platform #30과 백필로 켠다.
