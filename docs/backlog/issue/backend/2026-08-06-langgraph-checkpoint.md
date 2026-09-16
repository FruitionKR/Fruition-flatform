# 2026-08-06 Backend 이슈

## LangGraph PostgreSQL checkpoint schema 적용

### 배경

- LLM Pipeline Agent Worker가 `run_id`를 LangGraph `thread_id`로 사용해 planning, 사용자 승인 대기,
  bounded execution, verification 상태를 중단·재개하도록 변경되었다.
- 운영 worker는 `langgraph-checkpoint-postgres`의 `PostgresSaver`를 사용한다.
- DB migration의 단일 소유자는 기존 합의대로 Spring Flyway다. LLM Pipeline은 운영 중
  `PostgresSaver.setup()`을 호출하거나 DDL을 실행하지 않는다.
- 기존 Agent·Skill table 작업은 `docs/issue/backend/2026-08-04.md`의
  **작업 1. DB Migration과 저장 모델**을 함께 참조한다.

### 필요한 migration

사용 중인 `langgraph-checkpoint-postgres>=3.0,<4.0`이 요구하는 다음 table과 후속 migration을
Spring Flyway에 반영한다.

```text
checkpoint_migrations
checkpoints
checkpoint_blobs
checkpoint_writes
```

- `checkpoint_writes.task_path` 컬럼과 thread 조회 index를 포함한다.
- 패키지의 공식 `BasePostgresSaver.MIGRATIONS`와 동일한 컬럼·PK·index 계약을 사용한다.
- 임의로 Java entity를 만들거나 Spring 업무 모델에 checkpoint table을 포함하지 않는다.
- migration은 Agent Worker 배포 전에 완료한다.
- checkpoint payload에는 인증 token, system prompt, Tool 조회 원문을 넣지 않는다.

### 확인 위치

- `llmPipeline/agent_worker.py` — `PostgresSaver` 생성과 worker 주입
- `llmPipeline/app/modules/agent_run/infrastructure/agent_worker.py` —
  planning → interrupt → execution → verification graph, `thread_id=run_id`
- `llmPipeline/requirements.txt` — `langgraph-checkpoint-postgres` 버전 범위
- 주요 API: `POST /agent/runs/{run_id}/approve`, `POST /agent/runs/{run_id}/revise`

### 테스트와 완료 조건

- [ ] 빈 PostgreSQL에 Spring Flyway를 적용하면 네 checkpoint table과 필요한 index가 생성된다.
- [ ] planning job 완료 후 checkpoint에 승인 interrupt가 저장된다.
- [ ] worker를 재시작한 뒤 approve job이 같은 `run_id` checkpoint에서 재개된다.
- [ ] revise job이 기존 interrupt를 재개해 새 plan version을 만들고 다시 승인 대기한다.
- [ ] worker retry에도 동일 operation의 Tool idempotency key가 유지된다.
- [x] AgentRun 90일 보관 정리 시 LLM Pipeline이 `delete_thread(run_id)`로 checkpoint를 먼저 삭제한다.
