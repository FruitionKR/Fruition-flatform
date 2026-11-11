# 2026-11-11 최신 main 배포 검증

네 서비스는 dev가 main의 조상이며 dev...main 파일 차이가 없습니다. main 전용 커밋은 병합 기록입니다.

- frontend: 871af6eede26705957b41f9eee399716d632d40a
- document: 2e7a20c6013035f7855a7d16bf1c80adf7b00233
- ai: 208b6f42a2698350f62f179fdf4ddea4bdfeb30e
- access: 44d22c6f68b2417ef0d11129cad6f253550b7eca
- platform: c9f2ae41f73c607d379e258a49e25eb2d4e9bef0

직전 배포는 7d707f8dbd1df4a09b20c717212d9eb30844f609입니다. access는 동일하며 나머지 세 저장소는 새 main을 배포합니다.

## DB 검증

Document/Access migration 변경은 없습니다. AI는 nullable source_display_name 컬럼 추가와 기존 MCP 소스 slug 정규화 UPDATE가 있습니다. 행 삭제와 컬럼 제거는 없습니다.

네트워크 없는 일회용 PostgreSQL 16-alpine 컨테이너, tmpfs, 합성 데이터로 다음 시험을 수행했고 모두 통과했습니다.

1. 이전 배포의 ai_schema.sql 적용.
2. legacy slug, 정상 웹 slug, 기존 slug 충돌, 정규화 결과가 같은 두 slug, 개념 페이지를 포함한 6행 생성.
3. pg_dump -Fc → 별도 DB pg_restore --exit-on-error, 행 수 비교.
4. 새 스키마 두 번 적용. legacy slug만 doc-ab-1로 바뀌고 충돌·중복·개념 페이지는 유지됨.
5. source_display_name 컬럼 존재 확인.
6. 기존 형태의 wiki_pages INSERT 성공.
7. 적용 후 pg_dump/pg_restore → 새 스키마 재적용, 7행 유지, INVALID 인덱스 0.

SQL SHA256:
- 이전: c72bdb9664e5a17fb44ce963784b418d7a21563f52b375f1c66525e1860fbd03
- 신규: fa5d6b308f1ff2195daeaeec1bef2e36aff1173fb3266ebf80c6420e55eefcb2

한계: 게시 이미지가 아닌 정확한 소스 SQL을 사용했습니다. 운영 데이터, 운영 규모 잠금 시간, 구/신 앱 동시 실행, RDS PITR 복원은 시험하지 않았습니다. slug 보정은 데이터 변경이므로 구버전으로 돌아가도 자동으로 원상복구되지 않습니다.

## 운영 적용

Terraform plan에서 변경은 aws_iam_policy.storage의 document/pipeline 두 개 update뿐입니다. tmp/mcp-convert 결과 읽기와 final.json PUT/multipart 권한을 적용한 뒤 앱을 배포합니다. 리소스 생성·삭제는 없습니다.

배포기는 converter → access → document → pipeline API → 기타 worker/frontend 순서로 롤아웃하며 migration·DB 게이트와 인증 smoke·대용량 PDF smoke를 수행합니다.

진행 중 MCP ingest/승인 대기 초안/PDF 계획은 새 버전에서 다시 시작해야 할 수 있습니다. document와 ai 사이 롤링 중 일부 MCP 요청이 잠시 실패할 수 있으며 함께 롤백해야 합니다.
