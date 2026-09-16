# Backlog 문서

이 디렉터리는 현재 구현 기준과 다르거나, 구현 전 설계 단계에서 작성된 이전 자료, 그리고 운영이 끝난 날짜별 이슈·changelog를 보관한다.

현행 기준 문서는 `docs/README.md`, 최상위 본문 4개와 ADR이다:
`README.md` · `architecture.md` · `api.md` · `data-model.md` · `script.md` · `adr/`

아래 목록의 `docs/spec/…`, `docs/issue/…`, `docs/changelog/…`, `docs/msa/…` 경로는 2026-08-07 이관으로 전부 이 디렉터리 내부(`spec/`, `issue/`, `changelog/`, `msa/`) 경로로 읽는다.

## 평가 보고서

- `evaluation/pr-215-ai-quality-benchmark-rerun.md` — PR #215 AI 품질 벤치마크 재평가: Ingest·Agent·Skill·Query·Log·Lint의 현재·역사 결과와 한계.

## 진행 예정 계획

- `aws-msa-deployment-readiness-plan.md` — AWS MSA 보완 계획. DB 격리 → Secret·migration → 배포 자동화 → AI artifact → 저장소·네트워크 → IaC 순서로 구현하고, 단계마다 독립 검증 에이전트의 통과를 확인하는 실행 절차와 진행 기록.
- `mongodb-to-postgresql-migration-plan.md` — 문서 본문·revision·write receipt·edit outbox를 PostgreSQL 단일 transaction으로 통합하고 MongoDB를 제거하는 검증·이관 계획.

## 2026-08-10 검토 기록

- `ai-async-pr1-pr4-review-consensus.md` — PR #156~#159 누적 통합 리뷰. merge 전 필수 13건, 판단 보류·추가 합의 3건, 최종 배포 전 Agent DB 이전 조건 1건.
- `changelog/backend.md`·`changelog/infra.md` — PR #163에서 작성된 2026-08-10 변경 기록을 종료된 역할별 changelog 역사 자료에 통합 이관.

## 2026-08-07 일괄 이관 (문서 구조 개편)

현행 4문서 + ADR 체계로 압축하면서 이관한 자료:

- `msa/` — 전환기 현행 아키텍처·배포·실검증·서비스 맵 (→ `docs/architecture.md`로 압축. `service-map.md`는 분리 전 구조 설명이라 현행과 불일치)
- `spec/` — API 상세 명세(`spec/api/`)·SDD·계약 문서 33개 (→ `docs/api.md`로 요약)
- `issue/` — 역할별 날짜 이슈 문서. **2026-08-07자 미해결 항목 포함** (`issue/ai/2026-08-07.md`: ai 테이블 이전 차단 지점, `issue/infra/2026-08-07.md`: Terraform apply 대기, `issue/backend/2026-08-07.md`)
- `changelog/` — 역할별 변경 기록 (ai/backend/frontend/infra). 운영 종료, 이후 기록은 git 이력·현행 문서 갱신으로 대체
- `design/`, `evaluation/`, `llm-wiki/` — 설계 초안·LLM 평가 리포트·파이프라인 흐름 문서
- `Fruition_AWS_MSA_Architecture.md` — MSA 전환 목표 문서 (달성분은 `docs/architecture.md`에 반영)
- `Fruition_MVP_Architecture.md`, `Fruition_MVP_Erd.md` (→ `docs/data-model.md`로 압축), `Fruition_MVP_API_Contract.md`(최신판, 동명 구판 덮어씀), `Fruition_User_Story.md`, `fruition_역할별_날짜형_마일스톤.md 19-24-05-163.md`
- `local-runbook.md` (→ `docs/script.md`로 압축), `pdf-to-markdown-guide.md`, [AI Python 규칙](../../../AI/docs/backlog/python_convention.md), `backend-llmpipeline-integration.md`(최신판 덮어씀), `development.md`(최신판 덮어씀)
- `skills/claude/sdd-interviewer/`, `skills/codex/sdd-interviewer/` — `docs/spec/sdd` 아래에 SDD를 작성하던 스킬. spec 이관과 함께 운영 종료 (`.claude/skills/`·`.codex/skills/`에서 이동)

## 보관 문서 (2026-08-07 이전 이관분)

- `development.md` — 백엔드/프론트엔드 도입 전 개발 환경 기록. 현재 실행 기준은 `docs/local-runbook.md`.
- `Fruition_MSA_Proposal.md` — 4서비스와 SQS를 전제로 한 초기 AWS MSA 제안서. 현재 구조는 `docs/Fruition_AWS_MSA_Architecture.md`.
- `Fruition_MSA_Proposal_revised.md` — ECS on Fargate와 SQS를 전제로 한 3서비스 AWS MSA 제안서. 현재 구조는 `docs/Fruition_AWS_MSA_Architecture.md`.
- `msa-operational-contracts.md` — 4도메인 분할과 SQS/Redis Streams를 전제로 한 구현·운영 계약 초안. 필드·상태 전이·재처리 알고리즘만 참고한다.
- `query-sse-redis.md` — Query 실행·재처리를 Redis Streams로 확장하는 이전 설계안. 현재 AI 작업 큐는 Kafka를 사용하고 Redis는 실시간 상태 전달에 한정한다.
- `issue-2026-06-11.md` — 2026-06-16 기준 해결 또는 이관된 2026-06-11 이슈 기록.
- `issue-2026-06-12.md` — 2026-06-16 기준 해결된 rename API 이슈 기록.
- `issue-2026-06-16.md` — 전 항목 해결(PR 34/38/43/44/54/55/58)된 이슈 기록. 2026-07-15 이관.
- `issue-2026-06-17.md` — 백엔드 query event 중계(PR 39/41) 해결 기록. 프론트 SSE 잔여분은 `docs/issue/frontend/2026-07-15.md`.
- `issue-2026-06-20.md` — 인용 원본 하이라이트(PR 43~46) 해결 기록. 프론트 SSE 잔여분은 `docs/issue/frontend/2026-07-15.md`.
- `issue-2026-06-26.md` — 문서 처리 상태·삭제 API·DB 큐(PR 55) 해결 기록. heartbeat·동시 실행 방지·프론트 연동 잔여분은 `docs/issue/ai/2026-07-15.md`·`docs/issue/frontend/2026-07-15.md`.
- `issue-2026-06-27.md` — PR 49 작업 완료 기록(변경 기록). 요약은 `docs/changelog/ai.md` 2026-06-27 항목.
- `issue-2026-06-29.md` — concept 충돌·삭제 문서 handling 해결 기록. 동시 실행 방지·heartbeat 잔여분은 `docs/issue/ai/2026-07-15.md`.
- `issue-2026-07-02.md` — workspace 격리(PR 58/60/62/66/67) 해결 기록. lint/maintenance·source_refs 잔여분은 `docs/issue/backend/2026-07-15.md`·`docs/issue/frontend/2026-07-15.md`.
- `issue-2026-07-03.md` — PK UUID(PR 67)·프론트 workspace 마이그레이션(PR 68) 해결 기록. OAuth·FK CASCADE 잔여분은 `docs/issue/backend/2026-07-15.md`·`docs/issue/frontend/2026-07-15.md`.
- `issue-2026-07-04.md` — wiki workspace 경로 프론트 후속 작업 원문. 미해결 상태로 `docs/issue/frontend/2026-07-15.md`에 통합 이관.
- `issue-2026-07-09.md` — chat inline markdown 계약(PR 72/73) 해소 기록. processing_stage 폴링 잔여분은 `docs/issue/frontend/2026-07-15.md`.
- `issue-2026-07-10.md` — Chat Wiki API 계약 확정·검증 완료 기록. 계약 원본은 `docs/spec/chat-to-wiki-contract.md`.
- `issue-2026-07-14.md` — 복원 플로우 최적화 v5~v8 완료 기록(변경 기록). 요약은 `docs/changelog/ai.md` 2026-07-14 항목.
- `issue-2026-07-15.md` — 2026-07-15 해결 이슈 기록: 백엔드(query evidence source_refs 노출, documents/wiki_pages FK CASCADE + Flyway 도입)와 AI/Pipeline(pipeline run 동시 실행 방지·heartbeat·Markdown 편집 계약). 미해결분(wiki maintenance lint proxy, Kakao OAuth)은 `docs/issue/backend/2026-07-15.md`.
- `issue-2026-07-16.md` — wiki_pages 잔재 constraint 해결·Flyway 도입 완료 기록. 요약은 `docs/changelog/backend.md` 2026-07-16 항목.
- `ai-issue-2026-07-16.md` — llmPipeline 입력 책임·재실행 검증·PDF 복원 개선 완료 기록.
- `issue-2026-07-18.md` — Wiki ingest evaluator의 선택적 patch, fallback, retry 기록, unresolved 상태 구현 완료 기록.
- `issue-2026-07-20.md` — dev-up backend readiness 해결 기록. content_hash 잔여분은 `docs/issue/backend/2026-07-21.md`, pipeline 스키마 해결 기록은 `issue-2026-07-21.md`로 이관.
- `issue-2026-07-21.md` — 새 노트 생성, pipeline schema 소유권 충돌, Markdown 편집 router·생성 계약, 이메일 인증 회원가입·비밀번호 재설정 API와 Frontend 연동 해결 기록. 노트 본문 저장 API 잔여분은 `docs/issue/backend/2026-07-21.md`. pipeline 동시 실행·heartbeat는 dev에서 해결(요약은 `docs/changelog/ai.md` 2026-07-21 항목).
- `issue-ai-2026-07-22.md` — Agent 전체 편집·500 응답, Wiki maintenance HTTP 경계, PDF evaluator 원본 보존 검증 해결 기록.
- `issue-2026-07-25.md` — Backend의 Markdown 원문 내보내기, wiki-schema·maintenance 프록시, 폴더 트리 영속화와 AI/Pipeline의 활성 schema 주입, `source_related_to` 조합 저장·legacy 정리 절차, Query DB 후보 제한, multi-provider·Claude 지원, 삭제 workspace pipeline 차단 완료 기록. Provider 실환경 E2E는 `docs/issue/ai/2026-07-25.md`에서 계속 관리한다.
- `issue-2026-07-28.md` — AI 편집 승인 저장의 `source=agent` 스냅샷 영속화와 채팅 편입 문서의 워크스페이스 목록·검색 노출, 자동 선택 연결 완료 기록.
- `issue-2026-07-29.md` — 문서 콘텐츠 버전 영속화, 변경 전후 스냅샷, 비파괴 복원과 GitHub 스타일 Markdown diff API 완료 기록. Frontend 연동은 `docs/issue/frontend/2026-07-23.md`에서 계속 관리한다.
- `issue-2026-08-03.md` — AI 작업 로그·복구 연동 완료 기록.
- `issue-2026-08-05.md` — AI 결과 콜백 E2E와 복구 삭제 Page의 link·embedding 정리 완료 기록.
- `core-data-flow.md` — dev 브랜치 시절 단일 backend 기준 핵심 데이터 흐름 정리(2026-08-08 dev 병합으로 이관). 현행 구조는 `docs/architecture.md`.
- `issue/backend/2026-08-06-langgraph-checkpoint.md` — dev 브랜치의 LangGraph PostgreSQL checkpoint schema 적용 이슈(2026-08-08 dev 병합으로 이관).
- `spec/llmpipeline-backend-api-contract.md` — dev 브랜치의 llmPipeline↔Backend API 계약 전문(2026-08-08 dev 병합으로 이관). 현행 요약은 `docs/api.md`.
- `Fruition_MVP_API_Contract.md` — 로그인 없이 단일 기본 workspace만 쓰던 시절 API 계약. 현재 API 계약은 `docs/Fruition_MVP_API_Contract.md`.
- `note-editor-prototype.md` — local mock 저장 전제의 노트 편집기 프로토타입 사양. 본문 저장·버전 이력·복원의 현재 계약은 `docs/spec/document-version-history.md`.
- `settings-backend-api-proposal.md` — 설정 화면(설정 모달) 구현에서 확인한 백엔드 신설 필요 API 제안 목록(2026-09-07). 사용자 프로필·이메일·비밀번호·보안·멤버·워크스페이스 아이콘.

- [서비스 분리 전 Backend 안내](backend-before-service-split.md): 독립 Access·Document 구조로 교체한 Gradle 멀티 프로젝트의 기존 설명.
- [서비스 분리 전 폴더 안내](services-before-service-split.md): 기존 services/ 배치 안내.

- [기존 MVP 제품 개요](root-mvp-overview.md): 서비스별 저장소 안내로 교체한 루트 README 원문.
- `diagrams/`: 기존 AWS 계획·drawio·설명. 현행 배치와 운영 계약은 `../architecture.md`와 `../script.md`에서 관리한다.
