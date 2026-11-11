# RESTORE 결과 충돌 수정 릴리스

- 후보: `e12d216011b1abe3ec5b3f7fab8c51a923216bf3`
- 현재 적용 릴리스: `8f88b19678a31ee76e04f3209afac91d36f0dbe8`
- 이전 배포의 롤아웃·기본 AI smoke는 성공했지만 PDF smoke는 conversion-and-ai에서 1800초 후 실패했다: https://github.com/FruitionKR/Fruition-flatform/actions/runs/42994222627

## 원인과 수정

운영에서 완료된 복구 작업의 저장 payload_hash가 publication의 operation_type을 ingest_restore로 바꾼 결과의 해시와 정확히 같음을 읽기 전용 조회로 확인했다. PDF는 converter가 두 batch를 처리했지만 Document의 마지막 결과 반영은 관측되지 않았다. 같은 소비기는 OperationPayloadConflictException을 무한 재시도했다. Kafka 파티션별 선후 관계는 직접 확인하지 않았으며 수정 후 PDF smoke로 복구를 검증한다.

- Document #265/#266: 복구 대상의 서버 등록 유형이 ingest/lint이고 전체 payload hash가 알려진 구형/정규 형식과 일치할 때만 중복으로 인정한다. 양쪽 도착 순서를 처리하며 기존 hash·본문·원장 변경은 없다. 다른 내용은 계속 거절한다.
- AI #272/#273: Kafka 복구 성공 결과를 publication 형식으로 정규화한다. journal의 구형 캐시 재생에도 적용한다. HTTP 응답 계약은 유지한다.
- Kafka offset 변경, 이벤트 유실 처리, 운영 이력 덮어쓰기는 하지 않았다.

## 검증

- Document 로컬: OperationIngestServiceTest 18개, AiTaskResultApplierTest 64개, 실제 PostgreSQL/MinIO WikiPublicationEventIntegrationTest 20개 통과. 구형 결과 선반영 후 publication receipt가 저장되고, 재전송에도 버전·변경 기록이 증가하지 않음을 확인했다.
- AI 로컬: worker·restore 응답 계약 153개 통과, 격리 DB가 필요한 2개 제외. 실제 HTTP 응답을 worker 경계에 통과시켜 publication result와 동일한지 확인했다.
- Document dev 전체 CI 성공: https://github.com/FruitionKR/Fruition-document/actions/runs/43007671342
- AI dev 전체 CI 성공: https://github.com/FruitionKR/Fruition-ai/actions/runs/43007691787
- 게시 workflow는 정확한 main SHA의 CI 성공 이후에만 이미지를 게시한다.

## DB·인프라

AI schema와 Document/Access migration은 현재 적용 릴리스와 동일하다. migration_mode=none으로 배포한다. DB 복원 증거는 동일 SQL의 이전 격리 pg_dump/pg_restore 시험(#202)을 재사용하며 이번에 새 복원 시험을 수행했다고 주장하지 않는다. IAM·Secret·ConfigMap 변경 없음.

## 배포 후 확인

- 새 이미지 digest와 deployment readiness 일치.
- 반복되던 RESTORE 오류가 멈추고 해당 publication receipt가 ACCEPTED로 확정되는지 조회. 기존 operation payload_hash가 유지되는지 확인.
- 기본 문서·AI smoke와 대용량 PDF multipart·Range·변환·AI smoke 통과.
