# AI 작업 취소·복구 공통 계약

취소는 후속 실행을 중단하고, 해당 작업이 이미 저장한 변경을 역순으로 복구합니다.
`cancelled`는 Python과 backend의 복구 확인이 모두 끝난 상태입니다. 취소 요청의 HTTP 성공만으로
복구 완료를 판단하지 않습니다. 다른 작업의 후속 변경과 충돌하면 그 값을 보존하고 `rollback_failed`로 남깁니다.

[Document 공개·업무 복구 API](https://github.com/FruitionKR/Fruition-document/blob/main/docs/api/tasks.md) · [AI 내부 취소 API](https://github.com/FruitionKR/Fruition-ai/blob/main/docs/api/tasks.md)

## 권한·일관성 규칙

- backend는 취소 상태를 먼저 커밋해 늦은 결과와 추가 저장을 막습니다.
- Python은 실행 중인 handler·하위 작업이 끝난 뒤 AI DB와 객체 저장소의 변경 기록을 역순 복구합니다.
- Agent 도구는 변경 전 snapshot으로 역작업을 만들고, 원래 승인과 연결된 정확한 인자·별도 멱등키로 실행합니다.
- Python이 업무 DB의 미복구 변경 ID를 역순 지정하고, backend는 각 행의 현재 값·참조를 검사해 한 변경씩 원자적으로 복구합니다.
- 본문을 복구하면 새 revision과 outbox 이벤트를 생성하고 AI 파생 상태에도 동기 반영합니다. 삭제된 생성 문서는 운영 tombstone으로 늦은 편집 이벤트를 흡수합니다.
- 모든 단계가 끝난 뒤에만 `cancelled`와 Query `query.cancelled` SSE를 전달합니다. 늦은 완료 이벤트는 재생되지 않습니다.
- PDF 변환 취소는 HTTP 작업 중단을 전달하고 converter 하위 프로세스 종료를 기다린 뒤 placeholder·생성 파일을 복구합니다.
- 문서·폴더 역작업은 이름·내용·부모·순서를 복원합니다. 버전 번호와 운영 감사·멱등 기록은 되감지 않습니다.
- 새 폴더에 다른 항목이 생겼거나 게시한 Skill 버전을 다른 Agent가 사용한 경우 등은 강제 삭제하지 않습니다.
- 전송한 도구 요청의 성공 여부가 불명확하면 복구 완료를 선언하지 않습니다.

## 검증 범위

- “현재까지 업로드 한 문서, 알맞은 폴더 이름 생성해서 주제별로 정리해 줘”를 기준으로
  메모리 Workspace에 기존 폴더 2개·문서 6개를 준비하고, 폴더 생성·문서 이동 9단계의 각 중단 지점에서 원래 구조 복원을 검증합니다.
- 별도 PostgreSQL schema에서 실제 DB trigger·역순 복구·동시 취소·부모/자식·Skill 게시/수정을 검증합니다.
- Backend 통합 테스트는 실제 PostgreSQL·Redis와 Python 경계를 대체한 client를 사용합니다.
- Converter 테스트는 실제 하위 프로세스 종료와 연결 중단 시 정리를 검증합니다.
- 로컬 서비스 E2E는 실제 Gemini 모델·공개 API·Kafka worker·PostgreSQL·Redis를 연결합니다.
  같은 입력으로 승인 전 변경 0회, 마지막 이동 중 취소, 생성한 폴더 2개와 이동한 문서 6개의
  역작업 8회, 원래 이름·부모·순서 복원과 `cancelled`를 확인했습니다. Query 취소 후 말풍선 제거도 확인했습니다.
  모델이 생성한 계획은 실행마다 달라질 수 있습니다. 입력·계획·복구 결과 JSON을 별도 파일로 남깁니다.
- 이 서비스 E2E가 PDF 변환·Skill·Wiki 수집의 모든 중단 지점이나 MinIO 객체 복구까지 검증한 것은 아닙니다.
  해당 경계는 별도 통합·단위 테스트로 검증합니다. 추가 수동 통합 검증에서는 실제 backend·MinIO로
  본문 편집/복구(revision 1→2→3)와 PostgreSQL 변경 기록에 따른 MinIO 원본 객체 복원을 확인했습니다.
  실행법은 [스크립트 문서](../script.md#ai-작업-취소-e2e)를 따릅니다.

이 보장은 작업 기록을 생성하는 공개 제품 경로에 적용됩니다. 운영자가 직접 호출하는 내부 단발
`/query`, `/pipeline/**`, Wiki 유지보수 HTTP와 기존 기록 없는 작업은 공통 취소 대상으로 자동 등록되지 않습니다.
배포 전 실행 중인 구버전 작업을 종료하고 큐를 비워야 합니다. 기존 실행의 역작업을 추측해 만들지 않습니다.
