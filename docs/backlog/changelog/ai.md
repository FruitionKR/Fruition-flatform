# Changelog — AI / Pipeline

llmPipeline(AI/LLM/pipeline) 변경 이력입니다. 날짜 역순으로 기록합니다.

---

## 2026-08-07

### feat: ai 계층 데이터 분리 1단계와 document.edit.event consumer

- access 테이블(workspaces·workspace_members) 직접 참조 5곳 제거 — workspace 검증은
  document-svc 인가 계층 담당. skill 모듈은 비활성(AGENT_SKILLS_ENABLED=false) 유지,
  재설계 필요 주석만 추가.
- pipeline 접속을 core_db의 ai_runtime 계정으로 전환(`DATABASE_URL`), **ai_db 신설**:
  python 소유 `db/ai_schema.sql`(멱등) + 기동 시 부트스트랩(`AI_DB_MIGRATION_URL` 있을
  때 적용, `AI_DATABASE_URL`로 verify). `wiki_schemas`를 ai_db로 이전(5개 ai 테이블 중
  유일하게 교차 결합 0 — 나머지 4개 차단 사유는 `docs/issue/ai/2026-08-07.md`).
- `app/workers/edit_event_consumer.py` 신설 — `document.edit.event` 소비 →
  `document_derived_state`(ai_db) upsert(revision 역행 방지 멱등). 편집 hash vs
  ingest hash 불일치로 파생물 stale 판정(조회 시 계산). ingest 완료 시
  best-effort로 ingested hash 갱신.
- E2E 실검증: 편집→outbox→Kafka→consumer→ai_db 행 생성, stale=true 판정,
  재발행·revision 역행 멱등 확인.

## 2026-08-06

### feat: ingest Kafka worker 신설

- `app/workers/ingest_worker.py` — `ai.ingest.command`를 소비해 기존 실행 경로
  (`_run_pipeline_request`, run_id 주입 파라미터 추가)를 재사용하는 aiokafka worker.
- 수동 커밋(처리 후), succeeded run 멱등 스킵, `max_poll_records=1` +
  `max.poll.interval` 30분으로 분 단위 LLM 작업 중 리밸런싱 방지. heartbeat·결과는
  기존 HTTP 콜백(X-Internal-Token) 유지.
- 처리량 = worker 수 × partition(12). BackgroundTasks 배포 시 유실 문제 해소.

### feat: pipeline 신뢰 경계 — 전 엔드포인트 내부 토큰 인증

- 모든 라우터(pipeline/query/wiki-schema/documents 조회 포함)에 `X-Internal-Token`
  검증 dependency를 적용했다(`INTERNAL_CALLBACK_TOKEN`, secrets.compare_digest,
  미설정 시 fail-closed 503). `/health`만 제외.
- backend로 보내는 콜백(query events, pipeline-events heartbeat)에도 같은 헤더를
  부착했다. query events callback은 backend가 검증을 요구하는데 pipeline이 헤더를
  보내지 않던 기존 결함이 함께 해소됐다.
- wiki_page_links·document_wiki_links INSERT에 `workspace_id`를 포함한다
  (V20 migration 대응, manifest의 workspace_id 사용).

---

## 2026-08-06

### feat: 자연어 기반 Skill authoring API 추가

- `POST /skills/author`가 짧은 자연어와 선택적 참조 문서 ID를 받아 저장하지 않은 Skill Markdown 제안을 반환하도록 추가
- `/agent/turn`의 일반 “Skill 만들어줘” 요청도 `skill_authoring`으로 분류해 같은 작성 UseCase를 사용하고, “방금 방식대로” 요청은 기존 완료 AgentRun proposal 흐름으로 유지
- Skill 관리 화면의 단발 자연어 작성은 정보가 부족해도 일반 placeholder를 사용한 편집 가능한 제안을 반환하고, 멀티턴 채팅만 필요한 경우 보충 질문을 허용
- 채팅 보충 질문 뒤의 짧은 답변은 `recent_conversation_summary`에 유지된 Skill 생성 요청을 확인해 authoring 흐름으로 복귀
- `POST /skills/author`에 선택적 커맨드와 `preserve`/`enhance` 모드를 추가해 사용자 원문 보존과 LLM 구체화를 분리하고, 보안 차단 issue는 위치·이유와 함께 반환하며 저장을 막음
- Skill 제목을 `/` 뒤에 사용하는 lowercase-hyphen 커맨드 이름으로 통일하고, `name`과 `slug`에 같은 값을 저장하도록 변경
- personal Skill은 `workspace_id`에 저장하지 않고 소유자 계정 전체에서 조회·사용하도록 Skill repository 범위를 분리
- personal은 계정, team은 Workspace 범위로 같은 커맨드 이름의 중복 생성을 차단
- 모든 Skill이 최소 1개의 Agent capability에 연결되도록 검증하고, 지원하지 않는 작업을 기존 capability에 억지로 매핑하지 않고 거절
- 서로 다른 system prompt의 Skill intent 분류기·검증기가 `skill_kind`·참조 용도·Tool에 합의해야 capability를 확정하고, 불일치·모호함은 fail-closed 처리
- 채팅의 `pending_skill_proposal`로 커맨드·개인/팀 범위·Markdown을 DB 없이 유지하고, AI 재생성·보안 재검토·자연어 게시 승인을 같은 `AuthorSkillUseCase`로 처리
- 참조 문서는 임의 AgentRun ID 없이 Skill authoring 전용 Backend read endpoint로 조회하고, 실제 문서명·본문은 제외한 heading·목록 marker·표 header 구조만 비신뢰 데이터로 전달하며 prompt injection, credential, 고정 참조값과 capability 밖 Tool을 저장 전에 차단
- LLM이 참조 문서의 용도를 고정 템플릿과 일반 구조 참고로 구분하고, 고정 템플릿에서만 서버가 추출한 Markdown 구조를 조립하며 AI 재생성에서도 해당 블록을 유지
- 내부 `capabilities`·`allowed_tools`는 응답에서 숨기고 사용자에게 Markdown·범위·보안 issue만 반환
- `POST /skills/author/publish`가 최종 Markdown을 LLM과 규칙으로 다시 검증한 뒤 version 1을 `published`, 자연어 자동 라우팅을 기본 ON으로 transaction 저장
- 차단 화면의 AI 재생성은 위험 구간을 서버에서 제거한 뒤 `regenerate` 모드로 다시 작성하고, 규칙 marker에 없는 의미 기반 prompt injection도 LLM의 `blocked` 판정과 서버 검증 위치로 표시
- instruction뿐 아니라 description·참조 구조의 의미 기반 injection도 출처별로 검증하고, 참조 issue에는 문서 ID와 해당 문서 기준 위치를 반환
- 완료 AgentRun 기반 proposal도 공통 `AuthorSkillUseCase`에서 재검토하고 검토 단계에서 성공 작업의 내부 권한 상한을 유지하며 사용자 응답에서는 capability·Tool을 숨김
- 생성 결과가 차단되면 위험 구간을 마스킹한 미저장 Skill Markdown과 issue를 함께 반환해 검토 화면에서 수정 가능하도록 변경
- pending proposal의 재생성·보안 재검토·커맨드·범위 변경은 LLM 호출 없이 `skill_authoring` 후속 흐름으로 고정
- pending proposal 게시를 명시적인 긍정 승인 문장 전체 일치로 제한해 `do not publish` 같은 부정문이 저장을 실행하지 않도록 보강
- 보안 검토를 우회하던 직접 `POST /skills`를 제거하고 `PATCH /skills/{skill_id}`도 사용자 Markdown만 받아 같은 `AuthorSkillUseCase`에서 재검증
- DB migration 없이 개인 계정·팀 Workspace별 커맨드 advisory lock을 추가해 동시 중복 생성 경쟁을 직렬화
- 같은 Skill의 동시 수정은 parent row lock 안에서 다음 version 번호를 다시 계산해 version 충돌을 방지
- DB draft와 별도 `/skills/{skill_id}/publish` 없이 미저장 proposal을 최종 게시
- Skill 수정은 새 draft 대신 검증된 published version으로 바로 교체하고, 자동 라우팅 OFF 상태를 유지
- 자연어 자동 라우팅을 끈 published Skill도 명시적 `/command`로 계속 실행하도록 선택 조건을 분리
- OpenAI `skill-creator`의 간결한 작성·trigger description·progressive disclosure 원칙을 기존 `ChatCompletionsJsonClient` prompt에 적용하고 별도 런타임 의존성은 추가하지 않음
- Skill module 단위 테스트 `74 passed`, llmPipeline 전체 `546 passed`; Python compile과 `git diff --check` 통과

### refactor: Agent 실행 흐름을 LangGraph로 전환

- 수동 planning·승인 대기·최대 40단계 실행·verification 분기를 LangGraph state graph와 PostgreSQL checkpoint 재개 흐름으로 전환
- run별 job 순서를 직렬화하고 DB/checkpoint 사이 재시작 경계를 terminal·clarification·plan 상태로 멱등 복구
- Tool 조회 원문은 checkpoint에서 제외하고 Agent graph LangSmith tracing을 비활성화하며, 90일 만료 시 checkpoint를 AgentRun보다 먼저 삭제
- Spring Flyway가 관리할 checkpoint schema 요구사항을 `docs/issue/backend/2026-08-06.md`에 기록
- llmPipeline 전체 테스트 `719 passed`, `57 subtests passed`; Python compile과 `git diff --check` 통과

### fix: Agent prompt injection 실행 경계 보강

- `/agent/turn` 입력과 planning hierarchy·Skill instruction·Tool observation에 크기·중첩·제어 문자 검증을 적용
- mutation action은 대화·문서·Skill context를 제거한 사용자 `message`만으로 같은 의도가 다시 확인될 때 AgentRun을 시작하도록 제한
- Spring 연동용 API 계약에 Skill·Wiki Schema 관리 책임 결정, AgentRun proxy, 전체 요청·응답 예시와 callback 방향·인증 조건을 정리
- llmPipeline 전체 테스트 `704 passed`, `53 subtests passed`; Python compile, 문서 JSON 예시와 `git diff --check` 통과

## 2026-08-05

### fix: AI 작업 결과 콜백에 내부 인증 토큰 추가

- 결과 콜백에 `INTERNAL_CALLBACK_TOKEN` 값을 `X-Internal-Token` 헤더로 보내 Backend의 내부 콜백 인증을 통과하도록 수정
- 재시도되는 모든 요청이 같은 인증 토큰을 유지하는 회귀 테스트 추가
- Lint 복구 실패 정보의 `operation_id`를 Backend 계약인 `action`·`resource_id`로 맞춰 실패 대상이 유실되지 않도록 수정
- Ingestion·Lint 복구의 `deleted_pages`에 연결된 양방향 Wiki link, Document link, embedding unit·미참조 vector·legacy Page embedding을 제거하고 Page를 `deleted`로 전환
- 삭제 정리를 callback 전에 실행하고 Workspace 범위 제한·재실행 멱등성·비대상 Page 보존을 단위 테스트와 격리 PostgreSQL에서 검증
- Backend와 llmPipeline을 함께 실행해 ingest `202`, 인증된 결과 callback `200`, 작업 로그 `partially_succeeded` 확정을 확인
- Backend가 호출하는 Query·Ingest·Restore·Schema·Lint·Agent route에 `X-Internal-Token` 검증을 적용하고 `/health`만 인증에서 제외
- 진행 로그·Query event callback에도 작업 결과 callback과 같은 `INTERNAL_CALLBACK_TOKEN`을 전송하도록 통일
- 보호 route의 토큰을 request body 파싱 전 middleware에서 검증해 잘못된 JSON도 인증 실패를 먼저 반환하도록 수정
- 복구 정리와 비동기 Page embedding 저장이 같은 `wiki_pages` 행 잠금을 사용해 삭제된 Page의 legacy embedding이 다시 생성되지 않도록 수정
- 복구 요청에서 Source Page·재조립 Page·삭제 Page의 역할이 서로 충돌하면 `422`로 거절하도록 계약 검증 추가
- llmPipeline 전체 테스트 `697 passed`, `49 subtests passed`; `git diff --check` 통과
- AI 작업 로그 API의 현재 상태와 이관된 이슈 문서 링크를 현행 경로로 정리

## 2026-08-04

### fix: 공통 LLM prompt injection과 숫자형 개인정보 방어 추가

- 공통 Chat Completions system prompt에 역할·승인·Tool 결과 사칭, 과거 승인 재사용과 보호 데이터 외부 전송을 금지하고 거부 시에도 기존 출력 schema를 유지하도록 보안 경계를 추가
- LLM 요청·응답·오류 로그에서 전화번호, 주민등록번호, 카드번호와 명시된 계좌번호를 정규식으로 마스킹하되 날짜와 version 번호는 유지
- llmPipeline 전체 테스트 `684 passed`, `49 subtests passed`; Python compile과 `git diff --check` 통과

### feat: Workspace 문서 Tool과 완료 작업 기반 Skill proposal 추가

- `workspace_workflow`가 폴더 정리와 같은 AgentRun 계획·승인·bounded ReAct 경로를 사용하고 `get_document_content`, `create_document`, `apply_document_edit` 계약을 처리하도록 확장
- 문서 mutation plan에는 본문 대신 Backend의 `list_agent_run_artifacts`로 조회한 run·사용자·Workspace 결합 artifact ID, content hash와 편집 target만 포함하고 승인된 operation과 일치할 때만 실행
- 완료 AgentRun의 성공 Tool과 사용자 지시를 일반화하는 `skill_draft_proposal` action·preview를 추가하고, 고정 resource 값·승인 우회 지시·관찰하지 않은 mutation Tool을 차단하며 자동 저장·publish는 수행하지 않음
- mutation Skill에는 계획에 필요한 hierarchy read Tool을 필수로 포함하고 완료 작업에서 만든 proposal에도 동일 정책을 적용
- llmPipeline 전체 테스트 `680 passed`, `49 subtests passed`; Python compile과 `git diff --check` 통과

## 2026-08-03

### feat: 요청별 Agent Skill과 폴더 정리 AgentRun 추가

- Wiki Schema와 분리된 개인·팀 Skill의 draft/version, preview, publish, enable/disable, capability·허용 Tool 정책을 추가
- 자연어 `auto`, `/<skill>`·`skill_id` 명시 선택, `off`, 모호한 후보 확인을 Agent turn에 통합하고 Markdown 생성·편집에는 선택된 Skill 지침을 후순위로 주입
- 폴더 정리 요청을 계획·plan hash 승인·수정·취소·비동기 실행·결과 검증 상태를 가진 AgentRun으로 분리하고 PostgreSQL job lease, heartbeat와 Tool 호출 제한을 구현
- 승인 후 실행은 최근 관찰 결과를 바탕으로 LLM이 허용된 read, 실행 가능한 승인 operation 하나, 새 계획 요청 중 다음 action을 선택하는 bounded ReAct loop로 전환하고 mutation tool·arguments는 승인된 plan 값만 사용
- 완료된 operation만 남으면 추가 LLM 호출 없이 검증하고, pending mutation의 Tool 호출 예산을 우선 보존하며 재계획 사유는 제한된 error_code로만 저장·응답
- 실제 변경은 `X-Agent-Service-Token`으로 인증하는 Spring Backend Tool Gateway만 사용하며 Skill의 빈 `allowed_tools`를 제한 없음으로 해석하지 않고 planner에도 허용 mutation Tool만 전달
- 종료된 AgentRun의 90일 정리와 worker 실행·health check 기반을 추가하고, 마지막 job 실패 시 남은 `running` operation을 `failed`로 마감하며 기능은 `AGENT_SKILLS_ENABLED=false`가 기본값인 kill switch 뒤에 배치
- llmPipeline 전체 테스트 `665 passed`, `49 subtests passed`; Python compile, Compose config, `git diff --check` 통과

## 2026-07-31

### feat: Wiki 작업 로그와 복구 흐름 추가

- ingest 실행별 Source·Concept Markdown과 Concept 기여 JSON을 object storage에 저장하고, 현재 Wiki Markdown과 복구용 작업 산출물을 분리
- 부분·무변경 reingest에서는 이번 실행의 기여 JSON이 있는 Concept만 작업 산출물로 저장해 유지된 기존 Concept의 JSON 누락으로 실행이 실패하지 않도록 제한
- 취소할 operation을 제외한 활성 로그를 재생하는 `POST /wiki/ingest-restore-runs`, `POST /wiki/lint-restore-runs`를 추가하고, ingest 취소는 restore point 이후 여러 reingest를 함께 취소해 Source와 Concept을 복구하며 lint 취소는 Concept 재조립 결과로 제거·복원할 간선을 계산
- lint 변경도 operation Markdown·JSON으로 기록해 이후 복구에서 본문 변경과 간선 추가·삭제를 재생할 수 있도록 구성
- ingest·lint의 operation artifact를 현재 Wiki object 변경보다 먼저 저장하고, non-dry-run lint의 DB 변경과 로그 저장을 하나의 transaction 경계로 묶어 로그 저장 실패 시 간선 제거 등이 commit되지 않도록 처리
- 활성 ingest·lint 로그를 순서대로 재생해 더 이상 지지되지 않는 관리 간선만 고아 간선으로 판정하고, 로그에 없던 기존 간선은 보존
- 결과 callback의 일시적 실패를 재시도하고, 422 응답에는 작업 산출물 key·hash를 다시 구성하며, 최종 전송 실패 시 URL·payload를 `notify_pending` manifest에 저장해 재전송할 수 있도록 구성
- llmPipeline 전체 테스트 `606 passed`, `43 subtests passed`; Python compile과 `git diff --check` 통과

## 2026-07-28

### fix: LLM provider 환경변수 계약 단일화

- ingestion·query·evaluator·agent router·Markdown 편집·Wiki schema organizer가 provider와 관계없이 `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`만 공통 설정으로 사용하도록 통일
- `UPSTAGE_*` legacy fallback과 Compose 전달을 제거해 OpenAI 등 다른 provider 설정에 Upstage endpoint·key·model이 섞이는 문제 차단
- env 예시와 실행 문서를 `LLM_*` 계약으로 갱신하고 모든 실시간 LLM 경로의 legacy fallback 부재를 회귀 테스트로 검증

## 2026-07-27

### feat: Markdown 문서 재편입 흐름 추가

- `POST /pipeline/reingest-runs`가 같은 `document_id`의 최신 Markdown과 기존 Source Page·source block을 받아 추가·수정 블록만 의미 추출
- 유지·이동·추가·수정·삭제 블록을 구분하고 기존 블록 ID를 유지하며, 삭제된 블록 ID는 이후 실행에서도 재사용하지 않도록 마지막 발급 번호를 보존
- 삭제·수정 블록에만 연결된 기존 추출 항목을 제외하고 요약·카테고리처럼 블록 귀속을 확인할 수 없는 기존 정보는 lint 전까지 유지
- 공백뿐인 Markdown 재편입은 기존 source block을 제거하며, Source Page가 없는 문서는 `409`로 거부
- llmPipeline 전체 테스트 `522 passed`, `43 subtests passed`; `git diff --check` 통과

### feat: 재편입 기여분 기반 lint 구조 정리 추가

- 편입 실행별 concept·relation·block 변경 기여분을 기존
  `pipeline_runs.manifest.source_contribution`에 필요한 식별값만 저장하고 문서별
  최신 성공 실행을 사용
- 변경 전 실행에 별도 기여분이 없더라도 기존 manifest의 concept·relation을 읽어
  최초 재편입부터 사라진 구조를 찾고, 최신 claim 식별값이 없는 과거 재편입은
  active cluster 자동 삭제에서 제외
- 파일 경로로 전달된 relation 목록도 기여 이력에 포함하고, relation의 일부
  근거만 무효화된 경우 유효한 근거를 남긴 변경 결과를 보존
- lint dry-run에서 수정·삭제 block, 사라진 문서-concept 연결, 사라진 relation을
  `reconciliation_candidates`로 반환
- `dry_run=false`에서 오래된 문서-concept 연결·해당 문서의 embedding unit과
  다른 활성 문서가 지지하지 않는 relation만 삭제하고 적용 여부를 기록
- 최신 재편입 기여분과 비교해 active cluster의 이전 claim을 제거하고 relation에
  유효한 근거가 함께 있으면 이전 claim 근거만 제거하며, 근거가 모두 사라지면
  relation 후보도 제거
- 무효화된 source ref가 포함된 cluster를 자동 승격에서 제외하고
  `needs_review` 대상으로 분류
- Concept 본문 의미 재작성은 안전한 기여 병합 단계가 더 필요해
  `docs/issue/ai/2026-07-27.md`에서 후속 관리
- 집중 테스트 `31 passed`, llmPipeline 전체 `533 passed`,
  `43 subtests passed`; Python compile과 `git diff --check` 통과

## 2026-07-26

### fix: Query hybrid 후보와 탐색 기준 복원

- lexical 후보를 먼저 제한해 의미만 유사한 page가 embedding 비교에서 누락되던 회귀를 수정하고, Workspace 전체 저장 page embedding의 semantic Top-K를 keyword Top-K와 합친 뒤 bounded Markdown만 로드
- Source·Concept hybrid 비율을 `embedding 60% + keyword 40%`로 조정하고 정확한 이름 일치 보정은 유지
- semantic-only Concept의 기존 통과 기준을 유지하도록 focus threshold를 `0.60`에서 `0.45`로 함께 보정
- graph traversal의 상대 유사도 하한을 변하는 path score가 아니라 최초 최고 seed score의 95%로 고정해 여러 hop에서 relevance가 점진적으로 낮아지는 문제 차단
- keyword 우선 순위, semantic 후보 전달, PostgreSQL exact cosine 후보, 최초 seed 하한 회귀 테스트 추가
- exact 전역 비교 비용은 현재 검색 정확성을 위한 의도된 동작으로 기록하고, 실제 사용자 지연이나 운영 지표가 확인되기 전에는 index 작업을 활성 이슈로 만들지 않음
- Query 모듈 `78 passed`, `4 subtests passed`, llmPipeline 전체 `509 passed`, `43 subtests passed`; PostgreSQL 16 array cosine·ranking CTE 문법 확인

### perf: PDF 복원 기본 경로를 Docling-only로 전환

- 문서 복원 CLI 기본 mode를 `docling-only`로 변경해 Docling Markdown 생성 후 느린 crop OCR·Formula OCR·SLLM 단계를 실행하지 않도록 조정
- `selective-repair` mode에서 기존 코드가 찾은 표·수식·손상 본문만 페이지별로 `gpt-5.6-terra low` Responses API에 병렬 요청하고 block ID·Markdown 형식을 검증한 뒤 병합
- display math replacement의 `$$...$$`와 `\[...\]` 표기를 동일하게 허용하고 최종 조립 전 `$$...$$`로 정규화
- 그림은 선택 복원 대상에서 제외해 Docling image asset과 caption을 그대로 보존
- 기존 복원 pipeline은 `--mode full-repair`로 명시한 경우에만 실행하도록 유지
- 캐시된 Docling JSON·Markdown 동시 입력과 최종 `restored.md` 게시 단계를 추가하고 timing JSON에 실행 mode 기록
- 재실행 전에 이전 mode의 평가·복원 산출물을 전체 정리해 local OCR·Vision을 포함한 stale 결과가 최종 조립에 섞이는 문제 방지
- `detected.md` 조립에서는 이전 recovery와 layout decision을 모두 무시해 stale 결과를 모델 입력으로 다시 사용하는 재실행 오류 차단
- 캐시된 Docling JSON·Markdown은 항상 한 쌍으로 받도록 검증해 서로 다른 실행의 stale baseline 조합 방지
- OpenAI가 교정한 heading의 Markdown 계층을 최종 조립에서 보존하고 여러 줄 heading 결과는 거부
- Responses API 오류는 HTTP status만 전달해 provider 오류 본문과 문서 내용 노출 방지
- 30페이지 benchmark에서 미선택 349 block 중 107개 false-negative를 확인해 코드 detector 기반 선택 복원은 최종 품질 경로로 부적합하다고 판정
- 모든 heading·paragraph를 `gpt-5.6-terra low` crop-only로 처리하는 detector-free lane을 검증하고, 표·수식 lane과 합친 model-assisted 전수 평가에서 418/445(93.93%) 확인
- 본문 lane 30회와 표·수식 lane 25회의 복원 wall을 87.76~133.14초, Docling 포함 E2E를 207.33~252.71초로 추정
- 문서 복원 모듈 `59 passed`, llmPipeline 전체 `503 passed`, `43 subtests passed`

## 2026-07-25

### fix: AI/Pipeline 미해결 이슈 보강

- Agent 편집·생성·질의에 workspace/user 범위의 활성 Wiki schema fragment를 주입하고 scope나 활성 schema가 없으면 기존 빈 prompt 동작 유지
- Wiki ingest의 `source_related_to` 전체 Source 조합 생성·저장을 제거하고 legacy edge를 Query와 traversal에서 제외
- ingestion·markdown 편집·query·agent router의 provider 설정을 `LLM_*`로 통합하고 Claude Messages API 요청·응답 변환 추가
- 삭제 document/workspace의 실행 중 pipeline을 heartbeat에서 취소하고 Wiki 산출물 저장 전 DB lock과 활성 상태 검사로 완료 경합 차단
- llmPipeline 전체 테스트 `486 passed`, `43 subtests passed`, Python compile과 diff 검사 통과

### perf: Query 후보와 graph 조회량 제한

- Workspace 전체 Wiki page/link를 먼저 읽던 Query repository 계약을 Source/Concept별 bounded 후보와 후보 page 사이 bounded link 조회로 변경
- PostgreSQL lexical rank로 후보 pool을 제한한 뒤 기존 hybrid scoring과 evidence·related page·traversal path 계약 유지
- Query 모듈 `68 passed`, `4 subtests passed`, llmPipeline 전체 `487 passed`, `43 subtests passed`
- 리뷰 후 metadata 후보를 먼저 제한하고 해당 page의 embedding unit만 집계하도록 변경
- 초기 후보에 닿는 bounded link와 반대쪽 page를 추가 조회해 lexical Top-K 밖의 직접 연결 node도 graph traversal에 포함
- embedding unit 본문 match 후보를 metadata 후보와 합쳐 본문에만 관련 내용이 있는 page의 누락 방지
- 전역 link budget 안에서 frontier를 최대 3단계 반복 조회해 `max_depth=3` traversal 계약 유지
- 다중 검색어를 OR 본문 후보로 변환해 일부 검색어만 포함하거나 서로 다른 unit에 검색어가 나뉜 page도 후보화
- 집중 테스트 `39 passed`, llmPipeline 전체 `497 passed`, Python compile과 diff 검사 통과

### chore: Legacy source 관계 정리 절차 추가

- Workspace/user별 legacy `source_related_to` row를 기본 dry-run으로 확인하고 `--apply`에서만 삭제하는 운영 명령 추가
- Query Engine과 backend 출력 계약에서 `source_related_to` 원본 저장·traversal 설명을 제거하고 소비 계약 없는 관련 Source materialization을 보류
- 정리 명령·기존 삭제 범위 테스트 `11 passed`, llmPipeline 전체 `489 passed`, `43 subtests passed`

### test: Provider 실환경 E2E runner 추가

- 실제 provider API로 ingestion JSON, agent router, `markdown_create`를 독립 실행하고 오류 본문 없이 pass/fail·latency·HTTP status를 기록하는 smoke runner 추가
- Upstage 실제 실행에서 ingestion과 router 통과 후 account credit 부족으로 `markdown_create` HTTP 403 확인
- OpenAI·Gemini·Claude credential 부재로 해당 실환경 검증은 미완료 상태를 유지하고 llmPipeline 전체 `491 passed`, `43 subtests passed`

### fix: Claude Wiki maintenance provider 전달 보완

- Wiki maintenance가 Claude에서도 `provider_api_endpoint()`로 `/messages`를 선택하고 공통 client에 `provider=claude`를 전달하도록 수정

## 2026-07-24

### feat: Markdown AI 편집 응답 계약 확장

- 편집 응답을 `requested_target`, `actual_target`, `scope_expanded`, `changed`로 구분하고 requested target을 포함하는 bounded context 범위 확장을 허용
- 범위 확장 시 Markdown 구조·보호 조각·HTML·MDX를 검증하고 JSON 파싱 실패를 모델 원문이 노출되지 않는 1회 계약 보정으로 처리
- Agent router의 JSON·필수 action 계약도 1회 보정하고 대화 context prompt injection과 오류 로그 원문 노출을 차단
- 편집·source-range·생성의 필수 문자열 타입을 검증하고 객체·배열 모델 출력을 1회 계약 보정
- actual target과 table 보호 조각의 CRLF를 보존하고 동일 결과·생성형 GFM target 경계를 검증해 llmPipeline 전체 테스트 `463 passed`, `43 subtests passed`

## 2026-07-22

### fix: Agent 전체 편집과 오류 응답 보강

- target 없는 전체 편집의 line 계산을 `markdown_line_count()`로 통일해 후행 `\n`·`\r\n` 범위를 보존
- 예상하지 못한 Agent 예외의 내부 문자열은 server log에만 남기고 HTTP 500은 안정된 `internal_server_error` 응답으로 변환

### refactor: Wiki maintenance HTTP 경계 분리

- `POST /wiki/maintenance/lint`를 `wiki_ingestion/interfaces/http`로 이동하고 DB·LLM 실행을 `WikiMaintenancePort` 뒤로 분리
- 기존 lint top-level 응답 계약을 `WikiLintOut` response model로 명시

### fix: PDF evaluator 원본 보존 검증 강화

- 모든 `equation_candidate`를 원본 crop 필수 검토 대상으로 지정하고 수식 행·항·계수·연산자·분모·지수·첨자·부호를 대조
- 표 `corrected`·`match`·text-layout 결과가 PDF word 좌표의 행·열별 cell token과 OCR에서 확인한 이미지 부호를 누락하면 채택하지 않도록 공통 검증하고, OCR 실행 실패 시 text-layout 결과를 Vision 검증으로 이관
- 전체 `llmPipeline` 테스트 `424 passed`, `32 subtests passed`

## 2026-07-21

### fix: sLLM Markdown 출력 구조 검증

- 생성형 Markdown edit와 새 문서 create 결과를 `markdown-it-py`의 CommonMark+table parser로 검증
- 닫히지 않은 backtick/tilde code fence, frontmatter와 display math를 구조 오류로 판정
- 구조 오류를 기존 1회 재시도에 전달하고 재실패 결과는 기존 output contract error로 미적용
- Markdown 편집 모듈 `60 passed`, `26 subtests passed`; 문서 복원 제외 전체 `357 passed`, `30 subtests passed`

### fix: pipeline run 동시 실행 방지와 heartbeat 추가

- module-level process-wide lock으로 문서·Chat Wiki pipeline과 서로 다른 use case 인스턴스의 동시 실행을 방지
- Flyway V6로 `pipeline_runs.updated_at`을 추가하고 각 pipeline log event에서 실행 시각 갱신
- heartbeat DB 갱신 실패는 pipeline 실행을 중단하지 않고 `pipeline.log`에 기록
- 동시 실행 요청이 앞선 run의 완료·실패 처리를 마칠 때까지 대기하는 회귀 테스트 추가

### fix: Query 검색 범위를 Workspace로 격리

- `POST /query`가 필수 `workspace_id`를 받아 Query application과 repository까지 전달하도록 변경
- active Wiki page와 link 조회를 요청 Workspace로 제한해 다른 Workspace 데이터를 검색 후보에서 제외
- Workspace 요청 계약과 PostgreSQL 조회 조건을 추가하고 Query 테스트 61개 통과

### fix: pipeline startup의 DB 생성 책임 제거

- FastAPI lifespan에서 `CREATE TABLE`을 실행하지 않고 Flyway 필수 테이블 존재 여부만 확인하도록 변경
- Python의 공용·파이프라인·Wiki schema DDL과 `POST /admin/init-db` 제거
- Flyway가 적용되지 않은 환경은 누락 테이블을 표시하며 startup 단계에서 fail-fast
- API 계약·schema readiness 테스트와 문서 복원 제외 전체 테스트 `349 passed`, `28 subtests passed`

## 2026-07-20

### fix: 앱 시작 시 DB 스키마 자동 초기화

- `init_db()`가 수동 `POST /admin/init-db` 엔드포인트로만 노출되어, 호출 전에는 `pipeline_runs`·임베딩 테이블이 생성되지 않던 문제 수정
- 테이블 부재로 `POST /pipeline/runs`가 `relation "pipeline_runs" does not exist` 500을 반환 → 백엔드가 문서를 `failed`로 마킹하던 원인 제거
- FastAPI `lifespan` 핸들러를 추가해 앱 시작 시 `database.init_db()`·`wiki_schema_database.init_db()`를 자동 실행 (`CREATE TABLE IF NOT EXISTS` 기반이라 멱등)
- pipeline-api 재빌드 후 `pipeline_runs`·`wiki_page_embeddings`·`wiki_embedding_vectors`·`wiki_embedding_units` 생성 확인

### test: lifespan DB 초기화와 API 계약 테스트 격리

- API 계약 테스트의 `TestClient` startup에서 실제 PostgreSQL 초기화를 호출해 `DATABASE_URL` 없이 실패하던 문제 수정
- 공통 test client에서 schema 초기화를 mock하고, 별도 lifespan 테스트로 두 `init_db()` 호출을 검증
- 문서 복원 전용 의존성 테스트를 제외한 llmPipeline 테스트 `348 passed`, `28 subtests passed`

---

## 2026-07-19

### refactor: Pipeline typed 실행과 persistence 내부 흐름 정리

- HTTP·CLI 입력을 `PipelineRunCommand`로 통일하고 `argparse.Namespace` 역변환 제거
- Wiki output의 Source·Concept·link 저장 단계를 명시하고 source-related 점수 계산을 순수 함수로 분리
- 기존 API·CLI·저장 순서를 유지하고 전체 테스트 388개와 28개 subtest 통과

---

### refactor: Pipeline HTTP와 application 입력 경계 분리

- Pipeline·Chat Wiki 실행 schema와 route, dependency 조립을 `wiki_ingestion/interfaces/http`로 이동
- `PipelineRunCommand`로 application 입력을 명시하고 infrastructure에서만 `argparse.Namespace`로 변환
- 기존 HTTP 계약을 유지하고 전체 테스트 378개와 28개 subtest 통과

---

### refactor: Wiki output persistence orchestration 분리

- manifest 해석과 source/concept/link/cluster 저장 순서를 `postgres_wiki_output_persistence`로 이동
- 기존 `finish_pipeline_run` transaction과 저장 순서를 고정하고 관련 테스트 39개 통과

---

### refactor: Wiki PostgreSQL writer 경계 분리

- page/link upsert, embedding unit 저장, source-related 갱신, object storage I/O를 공통 writer로 분리
- 기존 repository private import 경로를 유지하고 Wiki ingestion 테스트 22개 통과

---

### refactor: Wiki PostgreSQL schema 초기화 분리

- ingestion repository의 테이블·인덱스 생성 SQL을 `postgres_wiki_schema` 책임으로 분리
- 기존 `init_db()` connection·transaction 경로를 유지하고 Wiki ingestion 테스트 22개 통과

---

### refactor: Pipeline run application 경계 분리

- run 등록·실행·성공/실패 저장·embedding 시작 순서를 `RunPipelineUseCase`와 port adapter로 이동
- FastAPI 요청·응답 계약을 유지하고 API contract 16개와 application 상태 순서 테스트 2개 통과

---

### refactor: Query graph 탐색과 context I/O 분리

- seed·traversal·path 보정 결과를 `_InternalRetrievalGraph`로 명시하고 Markdown·embedding 로드와 분리
- 기존 Query event 순서와 응답 계약을 유지하고 Query 테스트 57개 통과

---

### refactor: Wiki page 조립 내부 책임 분리

- Source page 준비, concept 입력 구성, source 조립, concept mode별 조립 책임 분리
- 기존 Concept 입력 → Source Page → Concept Page 로그 순서를 고정하고 관련 테스트 12개 통과

---

### fix: Meaning Cluster active 상태 읽기 순서 복원

- concept update 판단 직후 active cluster Markdown을 읽도록 기존 ingest 순서 복원
- 동시 ingest의 최신 상태 반영 시점을 유지하고 전체 테스트 373개와 28개 subtest 통과

---

### refactor: Wiki evaluator 내부 타입 명시

- 정규화 이후 evaluator 결과를 `GenerationEvaluation`으로 명시해 graph·repair·artifact port 계약 통합
- 숫자가 아닌 score를 안전한 평가 실패로 변환하고 전체 테스트 373개와 28개 subtest 통과

---

### refactor: Query 내부 context 조립 단계 분리

- seed 선택, graph traversal, Markdown·embedding 로드, answer context 생성을 `_InternalQueryContext`로 분리
- original/retrieval/evidence question 계약을 유지하고 전체 테스트 373개와 28개 subtest 통과

---

### refactor: Query Wiki scoring 단계 분리

- Wiki page/link 로드, Markdown 보강, source/concept scoring 결과를 `_ScoredWikiCandidates`로 분리
- 이벤트 순서와 web fallback 판단 계약을 유지하고 전체 테스트 373개와 28개 subtest 통과

---

### refactor: Meaning Cluster 조립 단계 분리

- candidate 판단, 기존 cluster 비교, artifact·maintenance summary 생성을 독립 단계로 분리
- 빈 candidate와 기존 출력 경로 계약을 유지하고 전체 테스트 373개와 28개 subtest 통과

---

### refactor: Wiki page 조립 단계 분리

- source page 누적·polish, concept page 생성, link 조립을 명시적 `WikiPageOutputs` 경계로 분리
- skeleton/API mode와 source artifact 계약을 유지하고 전체 테스트 372개와 28개 subtest 통과

---

### refactor: pipeline concept resolution 단계 분리

- concept resolution의 LLM 호출, 응답 정규화, same-source context 병합을 독립 함수로 분리
- normalized 결과와 debug artifact 계약을 유지하고 전체 테스트 371개와 28개 subtest 통과

---

### refactor: pipeline 입력 준비 단계 분리

- `run_pipeline`의 prompt 로드, API client 준비, source block 추출을 책임별 함수로 분리
- 호출 순서와 로그·debug artifact 계약을 유지하고 전체 테스트 370개와 28개 subtest 통과

---

### fix: Wiki evaluator 응답 형식 검증

- 잘못된 `scores`, `issues`, `warnings`, 상태 필드를 안전한 평가 실패로 변환해 재시도 경로 유지
- 누락 필드의 기존 기본값 계약을 보존하고 전체 테스트 368개와 28개 subtest 통과

---

### refactor: 문서 복원 dead contract 제거

- 항상 `False`를 반환하던 numeric header predicate와 무의미한 부정 조건 제거
- equation number evidence 검사에서 사용하지 않던 `markdown` 인자 제거

---

### refactor: SemanticNormalizer 미사용 인덱스 제거

- 생성 후 사용되지 않던 `source_reference_id` 기반 `by_ref_id` 인덱스 제거
- 실제 anchor 검증에 사용하는 `by_block_id` 계약은 유지

---

### refactor: Wiki graph 폐기 설정 제거

- 사용되지 않던 `min_node_score` 생성자 인자와 테스트 전달값 제거
- seed 유효성 검사 뒤 다시 읽히지 않던 최고 점수 갱신 제거

---

### fix: Wiki graph 깊이 제한 종료 사유 구분

- 최대 깊이 node에 확장 가능한 후보가 있을 때만 `max_depth` 종료로 기록
- graph가 제한 깊이에서 자연 종료하면 `no_frontier`를 유지하고 query spec을 현재 계약과 동기화

---

### fix: Wiki graph 최대 탐색 깊이 적용

- `TraverseWikiGraphUseCase.max_depth`에 도달한 node에서 frontier 확장을 중단
- retrieval summary가 실제 방문 깊이를 표시하도록 수정하고 Query 테스트 62개와 4개 subtest 통과

---

## 2026-07-18

### refactor: Markdown table header 조립 분리

- 표 복원 함수에서 계층형 header 해석과 Markdown row escaping을 순수 함수로 분리
- body 판정과 출력 계약을 유지하고 Document evaluation 테스트 36개 통과

---

### refactor: Wiki graph traversal 경로 조립 통합

- 신규 방문과 재방문 분기에 중복된 `TraversalEdge`·`TraversalPath` 생성을 공통 함수로 통합
- 탐색·점수·stop reason 계약을 유지하고 Query 테스트 62개와 4개 subtest 통과

---

### refactor: semantic note anchor 검증 통합

- `_normalize_single_note`의 내부 anchor 변환 함수를 기존 `_anchor_refs`와 통합
- unknown block 경고, limit, 중복 제거 순서를 유지하고 Wiki generation 테스트 69개 통과

---

### refactor: meaning-cluster ingest 로그 렌더링 분리

- artifact assembler에 섞여 있던 ingest 로그 Markdown 생성을 `meaning_cluster_log.py`의 순수 함수로 분리
- 로그 경로와 제목의 날짜를 일치시키고 Wiki generation 테스트 69개 통과

---

### refactor: Markdown output validator 규칙 분리

- 단일 함수에 모여 있던 edit goal 형상, 요청 문법, 보호 콘텐츠, 축약 검증을 명시적 규칙 함수로 분리
- 오류 수집 순서와 외부 계약을 유지하고 Markdown edit 테스트 28개 통과

---

### refactor: concept evidence Markdown 갱신 분리

- concept 문서의 Evidence 섹션 추가·placeholder 제거·중복 방지 로직을 `concept_evidence.py`로 분리
- repository의 DB orchestration과 Markdown 변환 책임을 분리하고 Wiki ingestion 테스트 19개 통과

---

### refactor: Wiki lint report 렌더링 분리

- PostgreSQL repository에 섞여 있던 lint Markdown 렌더링을 `wiki_lint_report.py`로 분리
- 로그 경로와 제목에 같은 날짜를 사용하도록 고정하고 Wiki ingestion 테스트 19개 통과

---

### refactor: concept resolution ledger 병합 분리

- incoming concept의 canonical slug 병합·alias·근거 합산을 `merge_concept_ledger`로 분리
- hint resolution과 evidence 연결 계약을 유지하고 Wiki generation 테스트 68개 통과

---

### refactor: local document 평가 계획 분리

- block 분류, table evidence, fallback chunk와 batch 제한을 명시적 `EvaluationPlan`으로 분리
- 모델 호출과 resume 순서를 유지하고 문서 평가 테스트 36개 통과

---

### refactor: 문서 복원 recovery 단계 분리

- `recover_block`에서 deterministic 후보 선택, SLLM system message 결정, 결과 파일 저장 단계를 분리
- retry와 fallback 순서를 보존하고 문서 복원 테스트 41개 통과

---

### refactor: Query evaluator 후속 route 처리 분리

- `AnswerQueryUseCase.execute`에서 evaluator 결과에 따른 답변 대체·evidence 재번호·종료 사유 변경을 별도 메서드로 분리
- web fallback 조기 반환 계약을 유지하고 Query 테스트 25개와 4개 subtest 통과

---

### refactor: 문서 복원 deterministic validator 분리

- 복원 결과의 공통 orchestration에서 table·equation 전용 오류 수집 규칙을 분리
- 오류 문구와 판정 순서를 보존하고 관련 테스트 13개 통과

---

### refactor: repository 오류 메시지 길이 제한 통합

- Wiki ingestion과 embedding repository의 240자 오류 저장 규칙을 `app.core.error_text`로 통합
- 관련 core·Wiki embedding·ingestion 테스트 23개 통과

---

### refactor: Vision 복원 evidence clipping 규칙 통합

- figure 복원과 block review가 공유하는 evidence 길이 제한과 clipping marker를 domain 함수로 통합
- 관련 문서 복원 테스트 10개 통과

---

### refactor: 문서 복원 좌표 판정과 Docling I/O 공통화

**배경**

문서 복원 단계마다 Markdown brace, bbox 겹침, Docling provenance와 PDF 경로를 같은 규칙으로 판정하면서 구현을 중복하고 있었습니다.

**변경된 것**

- Markdown brace 균형 검사를 문서 복원 domain 함수로 통합
- bbox 중심·방향성 겹침·대칭 match score 계산을 순수 domain 함수로 분리
- Docling JSON 로딩, PDF 탐색, provenance bbox 변환을 전용 infrastructure 모듈로 분리

**검증**

- 문서 복원과 Wiki ingestion 관련 테스트 52개 통과

---

### refactor: Wiki ingestion unit text 정규화 통합

**배경**

active cluster claim과 embedding unit이 source reference와 Markdown marker를 같은 규칙으로 제거하면서도 구현을 각각 유지하고 있었습니다.

**변경된 것**

- unit text 정규화 규칙을 `wiki_ingestion.domain.unit_text`로 이동
- active cluster와 embedding unit 생성이 동일한 정규화 함수를 사용하도록 변경

**검증**

- Wiki ingestion unit text와 concept index 관련 테스트 통과

---

### refactor: 반복 검증과 Markdown 정규화 공통화

**배경**

여러 LLM adapter와 문서 복원 단계에서 동일한 guard clause와 정규화 함수가 중복되어, 같은 규칙을 호출부마다 따로 유지하고 있었습니다.

**변경된 것**

- candidate decision의 구조와 `candidate_id`를 검증하는 공통 함수 추가
- schema prompt 결합 규칙을 `app.core`의 공통 함수로 통합
- 문서 복원의 Markdown code fence 제거와 table 형태 검증을 domain 함수로 통합

**검증**

- `cd llmPipeline && .venv/bin/python -m pytest -q tests` — 346개 테스트와 28개 subtest 통과

---

### feat: Wiki ingest evaluator를 LangGraph로 전환

**배경**

Wiki ingest evaluator가 일반 Python loop로 실행되어 LangSmith에서 의미 추출·평가·보정·재시도 흐름을 graph node 단위로 확인하기 어려웠고, API 기본값이 비활성화되어 evaluator가 요청마다 명시적으로 켜져야 했습니다.

**변경된 것**

- Wiki ingest evaluator loop를 `semantic_generation`, `normalize`, `evaluate`, `repair`, `reevaluate`, `prepare_retry` LangGraph node로 전환
- production과 같은 topology builder를 사용하는 `wiki_ingest_evaluator` Studio graph entry 추가
- `POST /pipeline/runs`, `POST /chat-wiki/runs`, CLI의 evaluator loop를 기본 활성화하고 명시적 비활성화 옵션 유지
- Wiki evaluator의 `issues`는 반드시 재시도하고 선택적 제안은 `warnings`로 분리하도록 평가 계약 보강
- Wiki evaluator의 concept/evidence/source block target에 대해 target block 주변 문맥과 기존 target 항목만 전달하는 `replace/remove/add` patch 경로 추가
- deterministic observation repair를 raw semantic note에 반영하고 다시 normalize해 최상위 registry와 `semantic_notes`가 일치하도록 보강
- patch의 수정 path와 source anchor를 검증하고 실패 시 관련 packet 재생성, target 해석 실패 시 전체 재생성으로 fallback
- 평가 기록에 `retry_mode`와 성공한 `applied_patch_operations`를 남겨 evaluator feedback의 실제 반영 내역을 추적
- 실제 문서에 없는 source block target은 전체 재생성으로 처리하고, debug retry artifact에도 확정된 재시도 방식과 patch operation을 기록
- patch에서 evaluator target과 무관한 semantic note와 의미 항목은 그대로 유지하고, 최대 시도 후 남은 issue는 manifest의 `generation_evaluation_status=unresolved`로 기록
- Wiki evaluator 시도별 상세 결과를 pipeline manifest와 DB run manifest에 보관
- Query evaluator에 `revise_answer` route를 추가하고, actionable feedback이 있는 답변은 재생성·재평가하도록 변경
- Query 답변 재생성은 `revise_answer`에만 적용하고 web/unsupported route는 즉시 해당 후속 처리로 전달
- Query 수정이 최대 시도 후에도 해결되지 않으면 검증되지 않은 답변 대신 unsupported 답변 반환
- `LANGSMITH_TRACING=true`이더라도 `LANGSMITH_API_KEY`가 없으면 graph 실행은 유지하고 tracing만 생략
- Query production·Studio graph에도 key 없는 tracing 차단을 적용해 LangSmith 경고와 네트워크 재시도를 방지
- LangGraph 로컬 실행 산출물인 `llmPipeline/.langgraph_api/`를 Git 추적 대상에서 제외

**검증**

- Wiki generation graph, target 기반 patch·fallback, API 계약, CLI 인자, LangSmith tracing guard 관련 테스트 통과

---

## 2026-07-16

### fix: pipeline 입력 문서 생성 책임을 Backend로 일원화

- 일반 `POST /pipeline/runs`는 Backend가 먼저 생성한 `document_id`를 입력으로 사용하고 llmPipeline의 직접 `documents` 생성 경로를 제거했다.
- `/chat-wiki/runs`의 `input_markdown`은 기존 source page에 새 대화만 누적하는 delta 입력으로 유지했다.
- Wiki 저장 범위의 `user_id`, `workspace_id`는 `document_id`로 기존 `documents` row에서 조회하도록 정리했다.
- llmPipeline 운영 접근 제한 후속은 `docs/issue/infra/2026-07-21.md`로 이관했다.

### feat: PDF 복원 흐름과 평가 기록 개선

**배경**

표와 수식에 같은 Text SLLM 경로를 적용하면 표의 행·열 관계가 손상되고 처리시간이 늘어났다. 또한 Docling group 내부 참고문헌 누락, Vision 거절 표현 판정, PDF 입력부터 최종 평가 Markdown까지의 시간 기록을 보완할 필요가 있었다.

**변경된 것**

- Docling 중첩 group을 문서 순서대로 탐색하고 참고문헌 `list_item` 원문을 보존하도록 변경
- Text SLLM은 코드만으로 복원하지 못한 수식에만 사용하고 표는 Vision SLLM 중심으로 처리하도록 분리
- Vision 거절 결과의 대괄호·대소문자 차이를 동일하게 판정
- 복원 시간과 evaluator 실행·누적·합산 처리시간을 평가 산출물에 기록
- 사용하지 않는 표·그림 Text SLLM prompt 제거
- 현재 흐름, prompt, PDF 4개 정확도·처리시간을 멘토 설명 문서로 추가

**검증**

- `cd llmPipeline && .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` — 249개 통과
- 변경 Python 파일 `py_compile` 통과

---

## 2026-07-15

### feat: Markdown 편집 라우팅과 생성 결과 계약 보강

**배경**

일반적인 문서 전체 편집과 원문 구조 보존 요청이 template 재구성으로 차단되고, 아직 지원하지 않는 섹션 뒤 추가 요청이 `replace`로 처리될 수 있었습니다. 신규 Markdown 생성은 필수 필드가 누락돼도 LLM 재시도를 하지 않았습니다.

**추가/변경된 것**

- 외부 template 재구성만 보류하고 문서 전체·구조 보존형 일반 편집은 router가 처리하도록 범위를 좁혔습니다.
- `insert_after`를 `current_section` 전용 operation으로 추가하고, local guard와 application 계층 모두 현재 섹션 target이 없으면 `clarify`로 반환합니다.
- 삽입 결과가 기존 섹션 heading을 반복하면 계약 실패로 처리해 기존 내용의 중복 삽입을 막습니다.
- 신규 Markdown의 `title`, `summary`, `markdown`을 검증하고 한 번 재시도한 뒤 재실패 시 전용 422를 반환합니다.
- 편집 목적에서 operation을 결정하는 규칙과 Markdown 생성 결과의 정규화·검증 흐름을 공통화했습니다.
- Agent 연동 계약과 backend 출력 계약의 `insert_after`, Markdown 생성 및 422 오류 설명을 현재 구현과 일치시켰습니다.

**검증**

- `llmPipeline/.venv/bin/python -m pytest -q` 결과 292개 테스트와 28개 subtest를 통과했습니다.

## 2026-07-14

### refactor: 문서 복원·평가 pipeline DDD 이관

**배경**

PDF 문서 복원과 최종 Markdown 평가 코드가 `tmp/`의 실행 산출물과 함께 있어 제품 경계, 재사용 가능한 진입점, 테스트 위치가 불명확했습니다.

**추가/변경된 것**

- canonical 문서 복원 단계를 `app/modules/document_restoration`의 domain/application/infrastructure/interfaces 구조로 이관했습니다.
- `RestoreDocumentUseCase`가 단계 순서를 담당하고 파일·subprocess·Docling 실행은 application port 뒤의 infrastructure adapter로 분리했습니다.
- 외부 evaluator job과 local-first evaluator CLI를 `app/modules/document_evaluation/interfaces`로 이동했습니다.
- 복원 prompt, 전용 requirements, CLI 실행 문서와 회귀 테스트를 정식 경로에 추가했습니다.
- PDF, crop, model cache와 실행 산출물이 포함된 `tmp/`, `paddle_cache/`는 Git 추적 대상에서 제외했습니다.
- 얕은 output 경로에서도 Paddle cache를 안전하게 찾도록 보정하고 `pix2tex` 의존성과 `unittest` 수집 범위를 명확히 했습니다.

**검증**

- `llmPipeline/.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'` 결과 170개 테스트를 통과했습니다.
- document restoration/evaluation CLI 3개와 개별 infrastructure stage CLI 8개의 `--help` 실행을 확인했습니다.
- 정식 모듈과 테스트의 `compileall`, `git diff --check`를 통과했습니다.

**주의사항**

- 문서 복원 CLI는 `requirements-document-restoration.txt`와 시스템 `tesseract`가 필요합니다.
- Paddle FormulaRecognition은 `paddleocr`이 설치된 환경에서 선택적으로 사용됩니다.
- 수식 image-to-LaTeX 근거 생성에는 전용 requirements에 포함된 `pix2tex`가 필요합니다.

### perf: canonical PDF 복원 플로우 최적화 (v5~v8)

`docs/backlog/issue-2026-07-14.md`에 기록되었던 작업 완료 내용을 changelog로 이관한 항목입니다.

- 복원 플로우 실행 시간을 39.7% 단축했습니다 (v5 최적화).
- 최종 Markdown 평가를 외부 evaluator job 대신 local-first evaluator로 전환했습니다 (153.34초, 테스트 31개 통과).
- 불완전 종결 heuristic을 제거했습니다 (v7).
- 구조 이상 표는 직접 Vision 검토로 처리하도록 변경했습니다 (v8, 최종 결론).
- 해당 코드는 PR 74/75로 `llmPipeline/app/modules/document_restoration`, `document_evaluation`에 DDD 구조로 이관되었습니다. 당시 실측 리포트 경로(`tmp/canonical_flow_run_*`)는 git 추적 제외 산출물이라 현재는 stale입니다.

---

## 2026-07-10

### docs: Prompt 지시문 영문화

**배경**

LLM system prompt의 지시문은 영어로 유지하되, 모델이 생성해야 하는 한국어 결과와 한국어 사용자 표현 예시는 보존해야 했습니다.

**추가/변경된 것**

- `agent_turn_router`, `concept_page_generation`, `markdown_edit`, `wiki_schema_organizer` prompt에서 영어 지시문과 한국어 출력 예시의 역할을 구분했습니다.
- meeting notes 섹션명, schema organizer 출력 예시, 한국어 follow-up trigger처럼 실제 결과 구조나 사용자 입력 매칭에 필요한 한국어는 유지했습니다.

**검증**

- `rg -n "Discussion Items|Decisions|Pending Items|Next Actions|do it that way|contrasting concept|please do it|Prioritize it as a concept candidate" llmPipeline/prompts` 결과 잘못 영문화된 출력 예시가 없음을 확인했습니다.

---

### feat: Chat Wiki 누적 API 계약 분리

**배경**

채팅 Wiki page화는 일반 문서 ingest와 달리 `session_id:pair_id`를 source reference로 유지하고, 기존 chat source page가 있을 때만 신규 pair를 누적해야 했습니다. 기존 `/pipeline/runs` 계약에 섞으면 `selection_mode`와 inline Markdown 입력을 잘못 사용할 수 있어 chat 전용 API boundary가 필요했습니다.

**추가/변경된 것**

- `/chat-wiki/runs`를 추가하고 `document_id`, `selection_mode`를 필수로 검증합니다.
- `input_markdown`은 기존 source page가 있는 `full` 누적에서만 허용하고, `partial` 또는 최초 `full`에서는 거부합니다.
- chat Markdown의 `[session_id:pair_id]` prefix를 source reference로 보존합니다.
- 기존 source page markdown과 artifact를 context로 사용해 `full` 누적 source page를 평가/병합합니다.
- source accumulation evaluator 결과가 source page artifact, concept page 입력, DB summary에 반영되도록 조정했습니다.
- 후속 정리로 chat API 입력 해석 로직을 별도 함수로 분리해 `input_markdown` 허용 조건과 저장 문서 fallback 경로를 한 곳에서 읽히게 했습니다.
- chat source accumulation payload 생성과 evaluator 결과 적용 로직을 `chat_source_accumulation.py`로 분리해 pipeline orchestration과 구조화 결과 매핑 책임을 나눴습니다.
- 기존 source page row가 없으면 `full` 누적 context가 없는 것으로 판단해 `input_markdown`을 거부하도록 보정했습니다.

**검증**

- `PYTHONPATH=llmPipeline llmPipeline/.venv/bin/python -m pytest llmPipeline/tests/test_pipeline_run_api_contract.py llmPipeline/tests/modules/wiki_generation llmPipeline/tests/modules/wiki_ingestion` 통과.
- 최종 결과: `68 passed, 1 warning`
- 실제 API 실행으로 `full` 누적 시 기존 ref와 신규 ref가 source/concept page에 함께 반영되고 DB source summary가 evaluator 결과로 저장되는 것을 확인했습니다.

---

## 2026-07-04

### refactor: Chat completions JSON parser 분리

**배경**

`chat_completions_llm.py`가 HTTP client, LLM adapter, JSON parsing/repair 정책을 함께 들고 있어 외부 호출 경계와 순수 parsing 규칙이 섞여 있었습니다.

**추가/변경된 것**

- JSON fence 제거, JSON object repair, section polish output 정규화를 `json_output_parser.py`로 분리했습니다.
- 기존 `chat_completions_llm.py`의 parser import 경로는 유지해 호출부 계약을 바꾸지 않았습니다.
- JSON parsing/repair와 section polish schema normalization 동작을 테스트로 고정했습니다.

**검증**

- `services/ai/pipeline/.venv/bin/python -m pytest tests/modules/wiki_generation/test_json_output_parser.py tests/modules/wiki_generation/test_wiki_generation_graph.py` 통과.
- `services/ai/pipeline/.venv/bin/python -m py_compile app/modules/wiki_generation/infrastructure/chat_completions_llm.py app/modules/wiki_generation/infrastructure/json_output_parser.py tests/modules/wiki_generation/test_json_output_parser.py run_lab.py` 통과.

### refactor: Query graph path helper 분리

**배경**

`AnswerQueryUseCase`가 query orchestration과 direct concept match 시 graph node/path 보정 규칙을 함께 들고 있어 use case 본문이 길어졌습니다.

**추가/변경된 것**

- focus concept related page 병합, direct concept path backfill, focus concept 연결 source 확장, answer path 선택을 `query_graph_paths.py`로 분리했습니다.
- query scoring, traversal, answer generation, 응답 계약은 유지했습니다.
- 분리된 graph path helper의 정렬, 중복 제거, direct concept path 보정 동작을 단위 테스트로 고정했습니다.

**검증**

- `services/ai/pipeline/.venv/bin/python -m pytest tests/modules/query/test_query_graph_paths.py tests/modules/query/test_answer_query.py` 통과.
- `services/ai/pipeline/.venv/bin/python -m py_compile app/modules/query/application/answer_query.py app/modules/query/application/query_graph_paths.py tests/modules/query/test_query_graph_paths.py` 통과.

### refactor: Generated concept page assembler 분리

**배경**

`assemble.py`가 backend source/concept page 조립과 LLM generated concept page 출력 정규화/Markdown 조립을 함께 들고 있어 assembly 책임이 넓었습니다.

**추가/변경된 것**

- `GeneratedConceptPageAssembler`를 `generated_concept_page_assembler.py`로 분리했습니다.
- 기존 `assemble.py` import 경로는 유지해 호출부 계약을 바꾸지 않았습니다.
- generated concept page assembler의 block id mapping과 Markdown 조립 동작을 테스트로 고정했습니다.

**검증**

- `services/ai/pipeline/.venv/bin/python -m pytest tests/modules/wiki_generation/test_source_extraction_artifact.py tests/modules/wiki_generation/test_ref_format.py` 통과.
- `services/ai/pipeline/.venv/bin/python -m py_compile app/modules/wiki_generation/infrastructure/assemble.py app/modules/wiki_generation/infrastructure/generated_concept_page_assembler.py tests/modules/wiki_generation/test_source_extraction_artifact.py` 통과.

### refactor: Concept section polish stage 분리

**배경**

`run_pipeline()`가 source page polish와 별도로 concept page section polish payload 구성, LLM 호출, fallback 처리, page assembly를 직접 들고 있어 concept 생성 분기가 길어졌습니다.

**추가/변경된 것**

- concept definition/key points/related hint section polish 준비와 결과 mapping을 `_prepare_concept_section_polish()`로 분리했습니다.
- `section-polish`, `api/full-llm`, backend skeleton mode 분기와 manifest 계약은 유지했습니다.
- concept polish helper가 resolution link hint와 polished Markdown을 연결하는 동작을 테스트로 고정했습니다.

**검증**

- `services/ai/pipeline/.venv/bin/python -m pytest tests/modules/wiki_generation/test_wiki_generation_graph.py tests/modules/wiki_generation/test_section_polish_mapping.py` 통과.
- `services/ai/pipeline/.venv/bin/python -m py_compile run_lab.py tests/modules/wiki_generation/test_wiki_generation_graph.py` 통과.

### refactor: Source page polish stage 분리

**배경**

`run_pipeline()`가 pipeline stage orchestration과 source page section polish payload 구성/실패 처리/결과 mapping을 함께 들고 있어 stage 흐름이 길어졌습니다.

**추가/변경된 것**

- source page summary/key points section polish 준비와 결과 mapping을 `_prepare_source_page_polish()`로 분리했습니다.
- source page 생성, concept page 생성, manifest 계약은 유지했습니다.
- source polish helper의 skeleton mode와 polish mapping 동작을 테스트로 고정했습니다.

**검증**

- `services/ai/pipeline/.venv/bin/python -m pytest tests/modules/wiki_generation/test_wiki_generation_graph.py tests/modules/wiki_generation/test_section_polish_mapping.py` 통과.
- `services/ai/pipeline/.venv/bin/python -m py_compile run_lab.py tests/modules/wiki_generation/test_wiki_generation_graph.py` 통과.

### refactor: Wiki persistence payload helper 분리

**배경**

`postgres_wiki_ingestion_repository.py`가 DB write 흐름과 pipeline manifest/page payload 정규화 규칙을 함께 들고 있었습니다.

**추가/변경된 것**

- source summary, Markdown title, page payload, stored manifest, page id resolution helper를 `wiki_persistence_payload.py`로 분리했습니다.
- repository의 SQL/DB persistence 흐름과 저장 계약은 유지했습니다.
- persistence payload helper 단위 테스트를 추가했습니다.

**검증**

- `services/ai/pipeline/.venv/bin/python -m pytest tests/modules/wiki_ingestion/test_wiki_persistence_payload.py tests/modules/wiki_ingestion/test_concept_index.py tests/modules/wiki_ingestion/test_markdown_sections.py tests/modules/wiki_ingestion/test_promotion_concept_page.py` 통과.
- `services/ai/pipeline/.venv/bin/python -m py_compile app/modules/wiki_ingestion/infrastructure/postgres_wiki_ingestion_repository.py app/modules/wiki_ingestion/infrastructure/wiki_persistence_payload.py` 통과.

### refactor: Query evidence text helper 분리

**배경**

`EvidenceSelector`가 evidence 후보 선택과 Markdown 문단/sentence 분리, 토큰 정규화, specificity bonus 계산을 함께 담당하고 있었습니다.

**추가/변경된 것**

- evidence text unit 분리, section weight, sentence cleanup, token normalization을 `evidence_text.py`로 분리했습니다.
- `EvidenceSelector`는 기존 evidence 후보 생성과 선택 흐름을 유지하고 순수 text helper만 새 모듈에 위임합니다.
- evidence text helper 단위 테스트를 추가했습니다.

**검증**

- `services/ai/pipeline/.venv/bin/python -m pytest tests/modules/query/test_evidence_text.py tests/modules/query/test_evidence_selector.py tests/modules/query/test_answer_query.py` 통과.
- `services/ai/pipeline/.venv/bin/python -m py_compile app/modules/query/application/evidence_selector.py app/modules/query/application/evidence_text.py` 통과.

### refactor: Meaning cluster artifact assembler 분리

**배경**

`assemble.py`가 source/concept page 조립 외에 meaning cluster active/log artifact 조립까지 함께 담당해 파일 책임이 계속 커지고 있었습니다.

**추가/변경된 것**

- meaning cluster 후보 수집, active cluster Markdown, ingest log Markdown 조립을 `meaning_cluster_artifact.py`로 분리했습니다.
- 기존 `assemble.py` import 경로는 유지해 호출부 계약을 바꾸지 않았습니다.

**검증**

- `services/ai/pipeline/.venv/bin/python -m pytest tests/modules/wiki_generation/test_source_extraction_artifact.py tests/modules/wiki_generation/test_ref_format.py` 통과.
- `services/ai/pipeline/.venv/bin/python -m py_compile app/modules/wiki_generation/infrastructure/assemble.py app/modules/wiki_generation/infrastructure/meaning_cluster_artifact.py` 통과.

### refactor: Wiki generation section polish mapping 분리

**배경**

`run_lab.py`가 wiki generation graph orchestration과 LLM section polish output 정규화 규칙을 함께 들고 있어 CLI 흐름의 책임이 커졌습니다.

**추가/변경된 것**

- section polish raw output의 text cleanup, anchor ref 검증, item mapping을 `section_polish_mapping.py`로 분리했습니다.
- `run_lab.py`는 기존 section polish 호출 흐름을 유지하고 mapping 함수만 application 모듈에서 가져오도록 정리했습니다.
- section polish mapping 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m py_compile llmPipeline/run_lab.py llmPipeline/app/modules/wiki_generation/application/section_polish_mapping.py llmPipeline/tests/modules/wiki_generation/test_section_polish_mapping.py` 통과.
- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.wiki_generation.test_section_polish_mapping` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/wiki_generation` 통과.
- `git diff --check` 통과.

### refactor: Wiki ingestion promotion concept page builder 분리

**배경**

`api.py`가 FastAPI route와 lint LLM client 구성 외에 promotion cluster LLM draft를 concept Markdown으로 변환하는 순수 조립 규칙까지 함께 들고 있었습니다.

**추가/변경된 것**

- promotion concept page Markdown 조립, representative 선택, lint ref 정규화/표기 함수를 `promotion_concept_page.py`로 분리했습니다.
- API route는 기존 lint materialization 흐름을 유지하고 promotion page builder만 새 모듈에서 가져오도록 정리했습니다.
- promotion concept page builder 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m py_compile llmPipeline/api.py llmPipeline/app/modules/wiki_ingestion/infrastructure/promotion_concept_page.py llmPipeline/tests/modules/wiki_ingestion/test_promotion_concept_page.py` 통과.
- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.wiki_ingestion.test_promotion_concept_page` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/wiki_ingestion` 통과.
- Docker 환경에서 `tests.modules.wiki_ingestion.test_concept_index`의 pytest-style 함수 테스트 직접 호출 통과.

### refactor: Wiki generation concept page section helper 분리

**배경**

`assemble.py`가 concept page Markdown 조립과 source key point, evidence fallback, related concept line 계산 규칙을 함께 들고 있어 page assembly 책임이 커졌습니다.

**추가/변경된 것**

- concept page의 source key point 수집, evidence 선택, key point line 생성, related concept line 계산을 `concept_page_sections.py`로 분리했습니다.
- `assemble.py`는 기존 Markdown 산출물 조립 흐름을 유지하고 concept section helper만 새 모듈에서 가져오도록 정리했습니다.
- concept page section helper 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m py_compile llmPipeline/app/modules/wiki_generation/infrastructure/assemble.py llmPipeline/app/modules/wiki_generation/infrastructure/concept_page_sections.py llmPipeline/tests/modules/wiki_generation/test_concept_page_sections.py` 통과.
- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.wiki_generation.test_concept_page_sections llmPipeline.tests.modules.wiki_generation.test_ref_format` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/wiki_generation` 통과.
- `git diff --check` 통과.

### refactor: Wiki generation evaluation guard 분리

**배경**

`run_lab.py`가 CLI/graph orchestration과 wiki generation evaluation guard, observation repair 규칙을 함께 들고 있어 pipeline 흐름을 읽기 어려웠습니다.

**추가/변경된 것**

- generation evaluation 보정 규칙과 observation repair 로직을 `evaluation_guards.py`로 분리했습니다.
- `run_lab.py`는 기존 graph 흐름을 유지하고 evaluation guard 함수만 application 모듈에서 가져오도록 정리했습니다.
- evaluation guard와 observation repair 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m py_compile llmPipeline/run_lab.py llmPipeline/app/modules/wiki_generation/application/evaluation_guards.py llmPipeline/tests/modules/wiki_generation/test_evaluation_guards.py llmPipeline/tests/modules/wiki_generation/test_wiki_generation_graph.py` 통과.
- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.wiki_generation.test_evaluation_guards` 통과.
- 로컬 `test_wiki_generation_graph`는 `langgraph` 미설치로 Docker 환경에서 검증했습니다.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/wiki_generation` 통과.
- `git diff --check` 통과.

### refactor: Query source reference parser 분리

**배경**

`EvidenceSelector`가 evidence 선택/scoring과 source block ref 문자열 파싱을 함께 담당해, citation ref 처리 규칙을 독립적으로 검증하기 어려웠습니다.

**추가/변경된 것**

- source ref 감지, block id 추출, structured `SourceReference` 변환, legacy field 변환, ref 제거 로직을 `source_references.py`로 분리했습니다.
- `EvidenceSelector`는 기존 evidence selection 흐름을 유지하고 source ref parser 함수만 새 모듈에서 가져오도록 정리했습니다.
- source ref parser 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m py_compile llmPipeline/app/modules/query/application/evidence_selector.py llmPipeline/app/modules/query/application/source_references.py llmPipeline/tests/modules/query/test_source_references.py llmPipeline/tests/modules/query/test_evidence_selector.py` 통과.
- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.query.test_source_references llmPipeline.tests.modules.query.test_evidence_selector` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/query` 통과.
- `git diff --check` 통과.

### refactor: Wiki ingestion active cluster helper 분리

**배경**

`postgres_wiki_ingestion_repository.py`가 DB persistence와 active cluster Markdown parser/merge, embedding unit 추출 규칙을 함께 들고 있어 repository 책임이 과도했습니다.

**추가/변경된 것**

- active cluster lint/merge 규칙을 `active_cluster_markdown.py`로 분리했습니다.
- wiki embedding unit 추출, canonical representation, hash helper를 `embedding_units.py`로 분리했습니다.
- repository는 기존 persistence 흐름을 유지하고 순수 Markdown/embedding helper만 새 모듈에서 가져오도록 정리했습니다.
- active cluster merge 중복 claim/relation 처리 characterization 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m py_compile llmPipeline/app/modules/wiki_ingestion/infrastructure/postgres_wiki_ingestion_repository.py llmPipeline/app/modules/wiki_ingestion/infrastructure/active_cluster_markdown.py llmPipeline/app/modules/wiki_ingestion/infrastructure/embedding_units.py llmPipeline/tests/modules/wiki_ingestion/test_concept_index.py` 통과.
- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.wiki_ingestion.test_markdown_sections` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/wiki_ingestion` 통과.
- Docker 환경에서 `tests.modules.wiki_ingestion.test_concept_index`의 pytest-style 함수 테스트 직접 호출 통과.
- `git diff --check` 통과.

### refactor: Wiki ingestion Markdown section parser 분리

**배경**

`postgres_wiki_ingestion_repository.py`가 DB persistence 외에 concept Markdown section 파싱 보조 함수까지 함께 들고 있어, 순수 문자열 처리 규칙을 독립적으로 검증하기 어려웠습니다.

**추가/변경된 것**

- Markdown `## Heading` section 추출과 list item 추출 로직을 `markdown_sections.py`로 분리했습니다.
- repository는 기존 DB/persistence 흐름을 유지하고 Markdown parser 함수만 새 모듈에서 가져오도록 정리했습니다.
- Markdown section parser 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.wiki_ingestion.test_markdown_sections` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/wiki_ingestion` 통과.
- Docker 환경에서 `tests.modules.wiki_ingestion.test_concept_index`의 pytest-style 함수 테스트 직접 호출 통과.
- 관련 infrastructure 모듈 `py_compile` 통과.
- `git diff --check` 통과.

### refactor: Wiki generation ref formatting 분리

**배경**

`assemble.py`가 page/cluster artifact 조립과 source block ref 표기 규칙을 함께 들고 있어, citation 표기 규칙을 독립적으로 검증하기 어려웠습니다.

**추가/변경된 것**

- ref label, global ref, citation suffix formatting을 `ref_format.py`로 분리했습니다.
- `assemble.py`는 기존 page/cluster 조립 흐름을 유지하고 ref formatting 함수만 새 모듈에서 가져오도록 정리했습니다.
- ref formatting 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.wiki_generation.test_ref_format` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/wiki_generation` 통과.
- 관련 infrastructure 모듈 `py_compile` 통과.
- `git diff --check` 통과.

### refactor: LLM 환경변수 해석 helper 공통화

**배경**

agent, markdown edit, wiki schema, query LLM infrastructure가 endpoint/API key/model/numeric 옵션을 거의 같은 방식으로 해석하는 함수를 반복하고 있었습니다. 각 모듈의 환경변수 우선순위와 기본값은 유지하면서 공통 parsing만 분리했습니다.

**추가/변경된 것**

- `app/core/llm_env.py`를 추가해 chat completions endpoint, API key, model, float/int option 해석을 공통화했습니다.
- agent router, markdown editor, wiki schema organizer, query answer generator/evaluator가 공통 helper를 사용하도록 정리했습니다.
- API key trim 여부처럼 기존 모듈별 차이는 호출부 옵션으로 유지했습니다.
- env helper 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.test_llm_env llmPipeline.tests.modules.agent.test_handle_agent_turn llmPipeline.tests.modules.markdown_edit.test_generate_markdown_edit llmPipeline.tests.modules.markdown_edit.test_generate_markdown_document llmPipeline.tests.modules.wiki_schema.test_chat_completions_schema_organizer llmPipeline.tests.modules.query.test_query_chat_answer_generator` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules` 통과.
- 관련 모듈 `py_compile` 통과.
- `git diff --check` 통과.

### refactor: Wiki embedding 결과 summary 조립 분리

**배경**

wiki page embedding use case가 동일한 결과 dict shape를 여러 return 지점에서 반복해, 응답 key 변경이나 집계 기준 수정 시 누락 위험이 있었습니다.

**추가/변경된 것**

- embedding 실행 결과 dict를 만드는 `embedding_result()` 보조 함수를 추가했습니다.
- `BuildWikiPageEmbeddingsUseCase`의 기존 반환 shape는 유지하면서 모든 return 지점이 같은 helper를 사용하도록 정리했습니다.
- 결과 summary shape를 고정하는 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.wiki_embedding.test_build_wiki_page_embeddings` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/wiki_embedding` 통과.
- 관련 application 모듈 `py_compile` 통과.
- `git diff --check` 통과.

### refactor: Wiki schema section metadata 공통화

**배경**

schema fragment section 목록이 filter와 preview 렌더링 코드에 각각 정의되어 있어, 새 section을 추가할 때 한쪽만 갱신될 위험이 있었습니다.

**추가/변경된 것**

- `schema_sections.py`를 추가해 schema section field 이름과 preview title을 한 곳에서 관리하도록 했습니다.
- `filter_schema_fragments.py`와 `build_schema_preview.py`가 공통 section metadata를 사용하도록 정리했습니다.
- `SchemaFragments` 필드와 section metadata가 어긋나지 않도록 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.wiki_schema.test_schema_filter llmPipeline.tests.modules.wiki_schema.test_schema_preview llmPipeline.tests.modules.wiki_schema.test_schema_sections` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/wiki_schema` 통과.
- 관련 application 모듈 `py_compile` 통과.
- `git diff --check` 통과.

### refactor: Query event publish 보조 함수 분리

**배경**

query application 흐름에서 callback event publish 실패를 삼키고 본 흐름을 계속 진행하는 처리가 `AnswerQueryUseCase`와 `QueryWebAnswerBuilder`에 중복되어 있었습니다. 같은 실패 처리 정책을 한 곳에서 확인할 수 있도록 보조 함수로 분리했습니다.

**추가/변경된 것**

- `publish_query_event()`를 추가해 event publisher 없음/실패 시 조용히 반환하는 기존 정책을 공통화했습니다.
- `AnswerQueryUseCase`와 `QueryWebAnswerBuilder`의 `_publish()`는 새 보조 함수에 위임하도록 정리했습니다.
- event publish 성공/무시 동작을 검증하는 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.query.test_answer_query llmPipeline.tests.modules.query.test_query_web_answer_builder llmPipeline.tests.modules.query.test_query_event` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/query` 통과.
- 관련 application 모듈 `py_compile` 통과.
- `git diff --check` 통과.

### refactor: Query application 보조 책임 분리

**배경**

`AnswerQueryUseCase`가 질의 처리 orchestration 외에 대화 맥락 해석과 retrieval summary 조립까지 함께 담당해, query 흐름을 읽고 테스트하기 어려웠습니다. 외부 API 응답 계약은 유지하면서 순수 보조 로직만 분리했습니다.

**추가/변경된 것**

- 대화 맥락 기반 검색 질문 보강과 evidence 질문 선택 로직을 `conversation_context_resolver.py`로 분리했습니다.
- `RetrievalSummary` 조립을 `retrieval_summary.py`로 분리해 내부 답변과 web fallback 답변에서 같은 계산을 재사용하도록 했습니다.
- `AnswerQueryUseCase`와 `QueryWebAnswerBuilder`는 기존 흐름을 유지하고 새 보조 함수에 위임하도록 정리했습니다.
- 분리한 순수 로직에 단위 테스트를 추가했습니다.

**검증**

- `PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.query.test_answer_query llmPipeline.tests.modules.query.test_query_web_answer_builder llmPipeline.tests.modules.query.test_conversation_context_resolver llmPipeline.tests.modules.query.test_retrieval_summary` 통과.
- `docker run --rm -v /private/tmp/local-pilot-llmpipeline-refactor/llmPipeline:/app -w /app fruition-mvp-dev-pipeline-api python -m unittest discover -s tests/modules/query` 통과.
- 관련 application 모듈 `py_compile` 통과.
- `git diff --check` 통과.

### fix: 위키 lint dry-run과 workspace link scope 정리

**배경**

`POST /wiki/maintenance/lint`가 이름과 달리 기본값으로 promotion materialize를 실행할 수 있었고, dry-run 성격의 호출도 lint log object를 쓸 수 있었습니다. 또한 workspace/user scope가 추가된 뒤에도 `source_related_to` 재계산은 전역 link를 삭제하고 재생성해 다른 workspace의 link에 영향을 줄 수 있었습니다.

**추가/변경된 것**

- `WikiLintIn` 기본값을 `dry_run=true`, `materialize_promotions=false`로 변경했습니다.
- dry-run lint 호출에서는 lint log object를 쓰지 않도록 `write_log` 옵션을 분리했습니다.
- `source_related_to` 재계산을 현재 `user_id`/`workspace_id`의 source/concept page 범위로 제한했습니다.
- dry-run log 미작성과 workspace scoped link refresh regression test를 추가했습니다.

**검증**

- Docker `pipeline-api` 컨테이너에서 `python -m compileall -q /tmp/pr66-llmpipeline-ae7e5d5/app /tmp/pr66-llmpipeline-ae7e5d5/api.py /tmp/pr66-llmpipeline-ae7e5d5/run_lab.py` 통과.
- Docker `pipeline-api` 컨테이너에서 `python -m pytest /tmp/pr66-llmpipeline-ae7e5d5/tests` 통과 (`154 passed`).

## 2026-07-02

### feat: query evidence에 다중 원문 source_refs 추가

**배경**

같은 answer citation rank가 여러 원문 문서 block을 동시에 참조할 수 있는데, 기존 `source_document_id` + `source_block_ids` 구조는 document id를 하나만 담을 수 있어 `doc_a:B0001`, `doc_b:B0008` 같은 전역 ref를 정확히 표현하기 어려웠습니다.

**추가/변경된 것**

- `llmPipeline` query evidence domain과 FastAPI 응답에 `source_refs` 배열을 추가했습니다.
- `doc_id:B0001` 전역 ref를 `{source_document_id, source_block_id}` 객체로 구조화해 evidence snippet에 포함합니다.
- 기존 `source_document_id`, `source_block_ids`는 첫 번째 문서 기준 호환 필드로 유지했습니다.
- Spring backend와 frontend의 `source_refs` 소비 작업은 `docs/backlog/issue-2026-07-02.md` 후속작업으로 분리했습니다.

**검증**

- `llmPipeline/.venv/bin/python -m pytest tests/modules/query` 통과.

**주의사항**

- 현재 Spring `/api/query`, `/api/chat/messages` 응답은 아직 `source_refs`를 저장/전달하지 않습니다. 이번 변경은 pipeline API 응답까지입니다.

### feat: 위키 클러스터 승격 lint 흐름 추가

**배경**

section/mention/evidence 후보가 ingest 시점에 너무 일찍 core concept으로 승격되거나, 반대로 active cluster에 쌓인 후보를 lint가 실제 page/link로 반영하지 못했습니다. 또한 source/concept page id를 `source:{id}` 같은 문자열 구조로 가정하면 workspace/user scope와 UUID 기반 page id 전환에 맞지 않았습니다.

**추가/변경된 것**

- `POST /pipeline/runs`에 `user_id`, `workspace_id`를 추가하고, 기존 concept index를 먼저 조회해 같은 concept 후보는 cluster 생성 대신 concept evidence 병합 후보로 처리하도록 변경했습니다.
- meaning cluster 정리본에서 `Summary`/`Observations`를 제거하고 `Evidence Claims`, `Core Relation Candidates`, `Promotion` 중심으로 유지하도록 조정했습니다.
- 새 cluster는 promotion candidate가 될 수 없고, 기존 active cluster에 근거가 누적된 경우에만 LLM 판단으로 promotion candidate가 되도록 prompt와 assembler를 보강했습니다.
- `POST /wiki/maintenance/lint`를 추가해 dry-run에서는 proposal만 조회하고, execute에서는 promotion concept page 생성/기존 concept 병합, active cluster archive 이동, materializable relation link 생성을 수행하도록 구현했습니다.
- lint가 새로 승격된 cluster 내부 relation뿐 아니라 `active.md` 전체 Core Relation Candidates를 처리하도록 확장했습니다.
- ref 없는 claim/promotion은 invalid로 분류해 materialization 대상에서 제외하도록 했습니다.
- `wiki_pages.id`를 opaque UUID 계열 id로 생성하고, page 중복 판단은 `(user_id, workspace_id, page_type, slug)` 기준으로 맞췄습니다.
- backend/frontend 후속 반영 항목을 `docs/backlog/issue-2026-07-02.md`에 정리했습니다.

**검증**

- `PYTHONPATH=llmPipeline llmPipeline/.venv/bin/python -m pytest llmPipeline/tests/modules/wiki_generation/test_source_extraction_artifact.py llmPipeline/tests/modules/wiki_ingestion/test_concept_index.py` 통과.
- Docker 재빌드 후 clean markdown 4개를 Upstage `solar-pro2`로 ingest/lint 재실행했습니다.
- dry-run lint에서 promotion 후보 2개, orphan ref 없음, invalid relation/promotion 없음 확인.
- execute lint에서 concept page 2개 생성, active promotion queue 제거, archive 이동, `anova-analysis uses_or_depends_on robust-design` link 1개 생성을 확인했습니다.

**주의사항**

- `related_evidence`는 core graph edge로 materialize하지 않습니다.
- lint execute는 `wiki_pages`, `wiki_page_links`, embedding unit/vector, MinIO `clusters/active.md`, `clusters/archived.md`, `logs/{yyyy-mm-dd}.md`를 변경할 수 있습니다.
- Spring backend와 frontend의 UUID page id, workspace/user scope, lint proxy, graph/detail 재동기화 반영은 후속 PR 대상입니다.

---

## 2026-07-01

### feat: LangGraph evaluator graph 모듈화와 Studio entry 추가

**배경**

Query evaluator loop가 `AnswerQueryUseCase` 내부에서 직접 LangGraph를 조립해 application layer가 LangGraph SDK에 의존하고, LangGraph Studio에서 graph 구조를 보기 어려웠습니다.

**추가/변경된 것**

- query evaluator retry 흐름을 `QueryEvaluatorGraphPort`와 `query_evaluator_flow.py`로 분리했습니다.
- 실제 LangGraph 실행 구현을 infrastructure의 `LangGraphQueryEvaluatorGraph`로 이동했습니다.
- LangGraph Studio/Agent Server용 `query_evaluator` graph entry와 `langgraph.json`을 추가했습니다.
- LangSmith tracing이 켜진 환경에서 query evaluator graph node와 LLM span을 확인할 수 있게 했습니다.

**검증**

- `llmPipeline/.venv/bin/python -m pytest tests/modules/query/test_answer_query.py tests/modules/query/test_query_evaluator_graph.py tests/modules/query/test_query_evaluator_studio_graph.py` 통과.
- `llmPipeline/.venv/bin/langgraph validate --config langgraph.json` 통과.
- 실제 `POST /pipeline/runs`, `POST /query` 실행 결과 LangSmith에서 `LangGraph`, `generate_answer`, `evaluate_answer`, `prepare_retry` trace 확인.

---

## 2026-06-27

### feat: query 근거 평가와 ingest 저장 흐름 개선

`docs/backlog/issue-2026-06-27.md`에 기록되었던 작업 완료 내용을 changelog로 이관한 항목입니다 (PR 49, 원문: `docs/backlog/issue-2026-06-27.md`).

- `POST /pipeline/runs` inline 입력(`input`/`input_path`) 실행에도 `source_document_id`와 `documents` row가 생성되도록 보강했습니다.
- `QueryAnswerEvaluator`를 추가해 답변/근거 정합성을 판단하고, 필요 시 web fallback 또는 internal web augmented route를 요청하도록 했습니다.
- `wiki_embedding_vectors`(canonical representation 공유)·`wiki_embedding_units`(page/unit 연결) 테이블을 추가해 source/concept 원자 단위 근거 저장 구조를 도입했습니다.
- Query context 조립이 저장된 embedding unit을 우선 사용하고, 없을 때만 markdown parsing fallback을 쓰도록 변경했습니다.
- evidence 선택을 고정 top-N에서 page별 최고 점수 대비 score band 방식으로 바꾸고, 구체성 신호(설계 변수·수치·단위·표 등)를 점수에 반영했습니다.
- 문장마다 자동 `[1]`을 붙이던 citation 후처리를 제거하고, LLM이 실제 인용한 evidence만 `evidence_snippets`에 남기도록 했습니다.
- `parse_json_object()` repair 후보 추가 등 semantic extraction JSON parsing과 prompt를 보강했습니다.

**검증**

- 원문 기준 pytest 31 passed. 논문 ingest 실험 결과는 `docs/backlog/issue-2026-06-27.md`의 실험 이력 참조.

---

## 2026-06-26

### feat: 채팅 Wiki observation 생성과 평가 보정 루프 추가

**배경**

긴 채팅 원문을 source page로 변환할 때 멀티턴 지시어, chunk 경계, 중복 QA episode 때문에 검색용 source 구조가 깨질 수 있었습니다.

**추가/변경된 것**

- `semantic_extraction`에 `observations` 구조를 추가해 `qa_episode`, `follow_up`, `definition`, `comparison` 같은 검색 단위를 source page에 저장하도록 변경했습니다.
- query API에 `recent_conversation_summary`와 `reference_context`를 받아 멀티턴 질문의 검색 질의를 보강하도록 추가했습니다.
- source evidence 선택 시 `Core Concepts` 링크 섹션을 제외하고, bullet 단위 evidence와 observation을 우선 활용하도록 보정했습니다.
- wiki generation evaluator loop를 추가하고, `observation_missing_ref`, `broken_observation`, `duplicate_observation`을 감지해 명확한 observation 문제는 deterministic repair 후 재평가하도록 했습니다.
- `LLM_PROMPT_LOG_DIR` 환경변수 기반 LLM 요청/응답 로그 저장 옵션을 추가했습니다.

**검증**

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=llmPipeline /opt/homebrew/bin/python3.12 -m unittest llmPipeline.tests.modules.query.test_answer_query` 통과.
- `test_source_extraction_artifact` 직접 호출 검증 통과.
- 관련 `llmPipeline` Python 파일 `py_compile` 통과.
- 실험 run `<chat-wiki-source-lab>/runs/chat-source-multiturn-context-repair-agent`에서 observation repair 후 evaluator `passed=true`, `overall=0.95` 확인.

### fix: query citation 번호를 실제 사용 근거 기준으로 재정렬

**배경**

pipeline이 evidence 후보 전체 순위로 citation rank를 부여하고, 답변 LLM은 그중 일부만 사용하면서 최종 답변에 `[1]`, `[3]`, `[5]`처럼 중간 번호가 비어 보일 수 있었습니다.

**추가/변경된 것**

- 답변 생성 후 실제 답변에 등장한 citation만 사용 순서대로 `[1]..[N]`으로 다시 매핑하도록 변경했습니다.
- 최종 `evidence_snippets`도 답변에 사용된 근거만 반환하고, 답변 본문의 citation 번호와 같은 `rank`를 갖도록 조정했습니다.
- 답변 citation 재매핑 회귀 테스트를 추가했습니다.

**검증**

- `python3 -m unittest tests.modules.query.test_answer_query` 통과.

---

## 2026-06-21

### feat: query evidence를 원본 source block 기준으로 변경

**배경**

기존 `evidence_snippets`는 Wiki page의 문장 위치(`page_id`, `paragraph_index`, `sentence_index`)를 기준으로 반환되어 답변 citation을 원본 문서 block 하이라이트로 연결하기 어려웠습니다.

**추가/변경된 것**

- `llmPipeline` query evidence 응답을 `rank`, `source_document_id`, `source_block_ids`, `text` 중심으로 변경했습니다.
- block citation(`[B0005]` 등)이 없는 Wiki 문장은 evidence 후보에서 제외했습니다.
- `source_blocks(document_id, block_id, text)` 테이블을 추가하고 pipeline 산출 block을 저장하도록 연결했습니다.
- source page의 `Categories`, `Core Concepts`, `Section Candidates`, `Mentions` 섹션을 별도 retrieval representation으로 점수 계산에 반영했습니다.
- Spring/Frontend 후속 반영 항목은 `docs/backlog/issue-2026-06-21.md`에 정리했습니다.

**검증**

- Docker `python:3.12-slim` 컨테이너에서 `pip install -q -r requirements.txt && python -m unittest discover` 실행 결과 22개 테스트가 통과했습니다.
- `git diff --check`를 통과했습니다.

---

## [Unreleased] — feat/backend-api

query engine 관련 pipeline 작업 브랜치입니다.

### feat: Query 검색 정제와 웹 검색 fallback 추가

**배경**

짧은 개념 질의에서 자연어 전체를 그대로 embedding query로 사용하면 concept page가 존재해도 source page 중심 검색에 묻히는 문제가 있었습니다. 또한 내부 Wiki 근거가 충분하지 않은 질문은 외부 출처를 찾아 근거 기반으로 답변할 fallback 경로가 필요했습니다.

**변경된 것**

- `RuleBasedQueryRewriter`를 추가해 한국어 조사 제거와 핵심 검색어 정제를 수행하도록 했습니다.
- concept title/slug/alias 직접 매치가 있으면 embedding 점수가 낮아도 focus concept으로 유지되도록 name match boost를 추가했습니다.
- direct concept match로 context에 추가된 concept에 대해 기존 `source_mentions_concept` edge를 찾아 `graph_context.edges`와 `traversal_paths`에 backfill하도록 했습니다.
- 내부 Wiki 최고 관련도가 `QUERY_MIN_INTERNAL_RELEVANCE_SCORE`보다 낮으면 `WebSearchPort`를 통해 웹 검색 fallback을 수행할 수 있도록 했습니다.
- Tavily 기반 `WebSearchPort` 구현을 추가하고, 결과를 기존 최종 응답 구조 안에서 `page_type=web`, `role=web_search_result`로 표현하도록 했습니다.
- `embedding_vector`가 `"-"`처럼 비정상 값이거나 dimension이 맞지 않을 때 해당 문서만 fallback scoring으로 넘기도록 방어 로직을 추가했습니다.
- Query representation hash 계산이 embedding 생성 경로와 맞도록 `.strip()`을 적용했습니다.
- 기존 최종 API 응답 구조(`answer`, `related_pages`, `evidence_snippets`, `graph_context`, `traversal_paths`)는 변경하지 않았습니다.

**검증**

- `.\.venv-query\Scripts\python.exe -m unittest tests.modules.query.test_answer_query tests.modules.query.test_stored_wiki_page_embedding_search` 통과.
- `.\.venv-query\Scripts\python.exe -m unittest discover -s tests\modules` 통과.
- 실험 환경에서 `소리꾼은 뭐야?` 질의가 `concept:sorikkun`을 `focus_concept`로 선택하고, `source:golden:06_culture_pansori -> concept:sorikkun` 경로를 `traversal_paths`에 반환하는 것을 확인했습니다.
- 실험 환경에서 내부 문서가 없는 최신성 질의가 Tavily web fallback으로 전환되는 것을 확인했습니다.

---

### refactor: Query graph 탐색과 답변 근거 표시 조정

**배경**

Query graph 탐색이 고정 점수 컷과 감쇠 기준을 함께 사용해, top source page에서 이어지는 상대적으로 유효한 후보가 절대 점수 때문에 제외될 수 있었습니다. 또한 답변 본문과 graph highlight 출력의 책임이 섞여 있어, 사용자가 어떤 문장이 어떤 근거에 기대는지 확인하기 어려웠습니다.

**변경된 것**

- 가장 유사도가 높은 source page 1개를 탐색 시작점으로 사용하도록 조정했습니다.
- 탐색 중 관측된 최고 유사도 기준 95% 미만 후보를 제외하고, 기존 고정 `min_node_score`/감쇠 종료 조건은 사용하지 않도록 변경했습니다.
- 답변 본문은 문장별 `[1]`, `[2]` 형태의 evidence rank 표식을 사용할 수 있도록 query prompt와 static fallback을 갱신했습니다.
- 답변 생성 context에서는 page URL/path id 같은 내부 경로 정보를 제거하고, URL은 `evidence_snippets` 메타데이터로만 유지하도록 정리했습니다.
- API 최종 출력의 `traversal_paths`는 전체 탐색 중간 경로가 아니라 답변 context에 사용하는 상위 path만 반환하도록 제한했습니다.
- 최고 유사도 점수가 0 이하이면 graph를 확장하지 않고 `no_relevant_seed`로 멈추도록 조정했습니다.
- 근거가 직접 답하지 못하는 질문에서는 일반 지식으로 답을 설명하지 않도록 query prompt 정책을 강화했습니다.
- `no_relevant_seed`일 때는 LLM이 외부 지식을 덧붙이지 못하도록 서버에서 고정 unsupported 답변으로 교체하도록 했습니다.
- graph traversal의 depth 제한을 제거하고, 상대 유사도 컷과 방문 node 점수 가드로 종료하도록 변경했습니다.
- `evidence_snippets`를 문단 단위가 아니라 문장 단위로 생성하고, `paragraph_index`/`sentence_index`를 응답에 포함하도록 확장했습니다.
- evidence 문장에서 Markdown heading, frontmatter, block ref, bullet prefix를 제거해 답변 citation이 실제 근거 문장 자체를 가리키도록 정리했습니다.
- 답변 문장별 citation marker가 빠지면 서버에서 fallback marker를 보정하되, 별도 `answer_citations` 응답 필드는 두지 않고 `answer`의 marker와 `evidence_snippets.rank`로 매칭하도록 정리했습니다.

**검증**

- `.\.venv-query\Scripts\python.exe -m unittest tests.modules.query.test_answer_query tests.modules.query.test_query_chat_answer_generator` 통과.
- `.\.venv-query\Scripts\python.exe -m unittest discover -s tests` 통과.
- WSL Docker `pipeline-api`에서 `QUERY_EMBEDDING_MODE=text-only` 상태로 `POST /query` 호출 성공.
- 미지원 질문은 `no_relevant_seed`, `traversal_paths=[]`, 고정 unsupported 답변으로 응답하는 것을 확인.
- 지원 질문 `LLM Wiki가 뭐야?`는 evidence marker `[1]`가 포함된 답변과 `evidence_snippets` rank를 반환하는 것을 확인.
- `.\.venv-query\Scripts\python.exe -m compileall app tests` 통과.
- WSL Docker `pipeline-api`에서 `retrieval_summary.max_depth=0`과 문장 단위 `evidence_snippets[].paragraph_index/sentence_index/text` 반환을 확인.
- WSL Docker `pipeline-api`에서 모든 답변 문장에 citation marker가 보정되고, 별도 `answer_citations` 없이 `answer`와 `evidence_snippets.rank`로 근거를 매칭할 수 있음을 확인.

---

### fix: Query embedding 검색의 text-only 실행 모드 추가

**배경**

로컬 Docker `pipeline-api` 플로우 테스트에서 기본 런타임이 `sentence-transformers`와 대형 `torch`/CUDA wheel을 설치해야 해 rebuild가 반복적으로 실패했습니다. Query 응답 플로우 자체를 검증할 때는 BGE-M3 embedding이 필수는 아니므로, 가벼운 lexical 검색 모드가 필요했습니다.

**변경된 것**

- `QUERY_EMBEDDING_MODE=text-only`이면 `StoredWikiPageEmbeddingSearch` 대신 BM25 기반 검색 점수를 embedding search 자리에 사용하도록 분기했습니다.
- 기본 모드는 기존과 같은 `bge-m3`로 유지해, 환경변수가 없으면 저장된 embedding/BGE-M3 경로를 사용합니다.

**검증**

- `.\.venv-query\Scripts\python.exe -m unittest tests.modules.query.test_answer_query tests.modules.query.test_query_chat_answer_generator` 통과.
- `.\.venv-query\Scripts\python.exe -m unittest discover -s tests` 통과.

---

## 2026-06-12

### refactor: llmPipeline 모듈 구조 정리

**배경**

기존 `fruition_lab` 패키지는 추출, 정규화, LLM 호출, DB 저장, Object Storage 접근이 flat package에 섞여 있어 `docs/python_convention.md`의 bounded context 구조와 맞지 않았습니다. Query Engine 확장 전에 Wiki 생성/수집 책임을 기능 단위 모듈로 분리했습니다.

**변경된 것**

- `app/modules/wiki_generation/` — source/concept page 생성, 정규화, LLM adapter, prompt 렌더링 책임으로 분리
- `app/modules/wiki_ingestion/` — PostgreSQL persistence, MinIO/S3 object storage, file IO 책임으로 분리
- `fruition_lab/` flat package 제거, 내부 import를 `app/modules/*` 경로로 일원화
- `run_lab.py`, `api.py`, query repository import를 새 bounded context 경로로 갱신
- `llmPipeline/README.md`의 모듈 설명을 새 구조 기준으로 갱신

**검증**

- `python -m unittest discover -s llmPipeline\tests`
- `python -m compileall llmPipeline\api.py llmPipeline\run_lab.py llmPipeline\app llmPipeline\tests`
- `api`, `run_lab` import 및 `/query`, `/health`, `/pipeline/runs` route 등록 확인

---

### feat: Wiki graph query engine 기반 추가

**배경**

기존 자연어 질의 응답은 단일 `highlighted_paths` 형태만으로는 source page, concept page, source-source 관계를 경로 단위로 표현하기 어렵습니다. Wiki graph를 질의 컨텍스트로 사용하기 위해 Python `llmPipeline`에 query bounded context를 먼저 구성했습니다.

**추가된 것**

- `llmPipeline/app/modules/query/` — domain/application/infrastructure/interfaces/http 레이어 기반 query 모듈 추가
- source-first retrieval, concept focus hint, `source_related_to` traversal 정책을 use case로 구현
- `POST /query` FastAPI route와 PostgreSQL wiki repository adapter 연결
- query engine 설계 문서 `docs/spec/query-engine.md` 추가
- fake port 기반 유닛 테스트로 concept hint backtracking, source-source traversal, depth limit, 빈 질문 검증 확인
- `BgeM3EmbeddingSearch`와 `Bm25Searcher`를 추가해 BGE-M3 vector similarity + BM25 lexical score 기반 hybrid retrieval 경로 구성
- query 단계별 Spring 콜백 로그(`QUERY_LOG_CALLBACK_URL`)와 Wiki Markdown 본문 기반 evidence context 구성 추가
- 답변 본문에서 context 밖 예시/비유를 만들지 않도록 query prompt 정책을 보강하고, `evidence_snippets`에 `page_slug`/`page_url`을 추가해 근거 문장별 Wiki page 링크 표시를 지원
- Wiki page 생성/저장 완료 후 별도 thread에서 BGE-M3 page embedding을 미리 생성해 `wiki_page_embeddings`에 저장하는 비동기 후처리 흐름 추가
- query retrieval이 저장된 `wiki_page_embeddings` vector를 우선 사용하고, 저장된 vector가 없는 page만 실시간 BGE-M3 계산으로 fallback하도록 변경
- query 답변 생성기를 `StaticAnswerGenerator`에서 Solar Pro 2 기본 query chat adapter로 전환하고, 기존 `UPSTAGE_*`/`LLM_*` 환경변수를 재사용하도록 구성

**검증**

- `python -m unittest discover -s llmPipeline\tests`
- `python -m compileall llmPipeline\api.py llmPipeline\app llmPipeline\tests`
- `api` import 후 `/query` route 등록 확인

---

*커밋 단위 이력은 `git log` 로 확인하세요.*
