# Fruition 역할별 날짜형 마일스톤

`마일스톤.md`의 DevOps 날짜형 표 구조에 맞춰 AI / Backend / Front / DevOps/System / Test를 `기간 / 단계 / 핵심 목표 / 주요 산출물` 형식으로 재구성했다.

---

## 전체 목표 일정

| 기간 | 단계 | 핵심 목표 | 주요 산출물 |
| --- | --- | --- | --- |
| 2026-06-08 ~ 2026-06-14 | 선행 분석 및 설계 | 요구사항, 아키텍처, 역할별 일정의 선후관계 고정 | 요구사항 정리, API/데이터 흐름 분석, 역할별 마일스톤 기준, Jira 일정 기준 |
| 2026-06-15 ~ 2026-06-28 | 1단계 | MVP API 계약 고정 및 프론트-백엔드 연결 완성 | 문서 업로드/목록, Wiki graph/page, 질의, 채팅 조회 API 연결, 상태 polling, 그래프 하이라이트, 로컬 동시 실행 스크립트, `.env.example`, 기본 CI |
| 2026-06-29 ~ 2026-07-05 | 2단계 | 채팅 저장과 Wiki 근거 저장 | `chat_messages`, `chat_message_references`, 이전 대화 조회, 답변 근거 node/path 하이라이트, DB migration 규칙, seed/test data |
| 2026-07-06 ~ 2026-07-19 | 3단계 | MD 편집기와 Wiki 페이지 버전 관리 | Markdown 로드/저장 API, `wiki_page_versions`, split preview/edit, diff 미리보기, object storage 구조, 백업/복구 초안 |
| 2026-07-20 ~ 2026-07-26 | 선행 안정화 | 롤백/감사 기반 구축 | `activity_logs`, `audit_diffs`, rollback API, 변경 이력 조회, structured logging, request id, audit log 보존 정책 |
| 2026-07-27 ~ 2026-08-02 | 4단계 | 사용자 개별 스키마와 문서 초안 템플릿 | `wiki_guidelines`, `document_templates`, 섹션 기반 템플릿, 설정 화면 |
| 2026-08-03 ~ 2026-08-09 | 5단계 | Markdown lint와 Wiki 품질 관리 | lint 규칙, 저장 전 검사, CI 연동, Evidence/source reference 누락 검사, 품질 게이트 |
| 2026-08-10 ~ 2026-08-23 | 6단계 | AWS 소규모 SaaS 테스트 배포 | 테스트 서버 크기 AWS 배포, SaaS 접속 URL, CloudWatch 로그, 사용자 피드백 수집, 운영 runbook 초안 |
| 2026-08-24 ~ 2026-08-30 | 7A단계 | Obsidian vault 자료 이식 | vault/zip 업로드, `.md` 파싱, wikilink/front matter/tag 추출, 첨부 저장, import job 로그/모니터링 |
| 2026-08-31 ~ 2026-09-06 | 7B단계 | Notion export 자료 이식 | Notion export zip 파싱, hierarchy 변환, 첨부/Markdown/CSV 처리, 실패 재시도/운영 리포트 |
| 2026-09-07 ~ 2026-09-13 | 8단계 | TTS/STT 추가 | 음성 업로드/녹음, STT 저장, 답변/Wiki 페이지 TTS, 음성 캐시, job timeout/retry, 비용/latency 로그 |
| 2026-09-14 ~ 2026-09-27 | 9단계 | 팀 공유, 권한, AWS 운영 분리 | users/workspaces/members, role 권한, workspace_id 적용, 초대/권한 UI, production 분리 기준, secret/CORS/IAM 정책 |
| 2026-09-28 ~ 2026-10-11 | 10단계 | 데스크톱 앱 패키징 | Electron shell, 로컬 파일 접근, API base URL 환경변수화, 로컬 백엔드/LLM 옵션, SaaS API 연동, 패키징/배포 문서 |

---

## AI 날짜형 마일스톤

| 기간 | 단계 | 핵심 목표 | 주요 산출물 |
| --- | --- | --- | --- |
| 2026-06-08 ~ 2026-06-14 | 선행 분석 및 설계 | Query/Wiki 생성 흐름과 AI 산출물 계약 분석 | Query 응답 구조 초안, evidence/page/path 연결 기준, AI 산출물 검수 기준 |
| 2026-06-15 ~ 2026-06-28 | 1단계 | MVP API 연결과 기본 질의 플로우 | Query 응답에 필요한 기본 `answer` / `evidence` / `page` / `path` 구조 초안 정의. 후속 연결 기능: Backend Query 응답 DTO, Front 근거 표시. |
| 2026-06-29 ~ 2026-07-05 | 2단계 | 채팅 저장 기능 | 목표: 전체 채팅 또는 Compact / Part 단위 요약을 저장하고 페이지로 생성. Day 1~2 Compact 요약 기능: 긴 채팅을 짧게 요약하는 LLM 프롬프트. Day 3 Part 단위 요약 기능: 사용자가 선택한 구간만 요약. Day 3~4 요약 페이지 생성: md/wiki 페이지 자동 생성. Day 4~5 수정/재생성/QA: 요약 재생성, 제목 자동 생성, 오류 처리. |
| 2026-07-06 ~ 2026-07-19 | 3단계 | Wiki 상세, Markdown 편집기, 버전 관리 | 저장된 채팅 요약을 md/wiki 페이지로 생성하는 출력 포맷 확정. 후속 연결 기능: 채팅 저장 결과를 Wiki 페이지로 연결. |
| 2026-07 중 우선 검증 | SLLM | SLLM Query Process 치환 | 목표: 기존 Query Process 일부를 SLLM으로 대체해 비용/속도 최적화. Day 1~2 SLLM 호출 래퍼 구현: SLLM API wrapper. Day 3 Intent 분류 적용: 질문 유형 분류 기능. Day 4 Query rewrite 적용: 검색/검색어 개선 기능. Day 5 Routing 적용: LLM / SLLM / 검색 분기. Day 6 기존 방식과 비교: 속도, 비용, 품질 비교표. Day 7 fallback 처리: SLLM 실패 시 기존 LLM 사용. |
| 2026-07-20 ~ 2026-07-26 | 선행 안정화 | Rollback, Audit, 변경 이력 | 자동 생성/자동 수정 작업의 변경 사유 메시지 포맷 정의. 후속 연결 기능: AI 수정 이력 표시. |
| 2026-07-27 ~ 2026-08-02 | 4단계 | Schema / 템플릿 기능 | 목표: 사용자가 직접 Schema/Template을 작성하거나 LLM으로 초안 생성. Day 1 `Claude.md` 유사 포맷 정의: `schema.md` 기본 구조. Day 1~2 직접 작성 기능: 템플릿 작성/수정 UI. Day 2 템플릿 저장 기능: 템플릿 저장 API / DB. Day 3 LLM 초안 생성: 목적 입력 -> md 초안 생성. Day 4 템플릿 미리보기: 생성된 md preview. Day 4~5 템플릿 적용: 채팅 저장, Wiki, 회의록 등에 적용. |
| 2026-08-03 ~ 2026-08-09 | 5단계 | Lint / Wiki 최신화 | 목표: Schema 기준으로 Wiki 문서를 정리하고 최신 상태 유지. Day 1~2 Lint 규칙 설계: 누락, 중복, 오래된 내용 검사 기준. Day 2 문서 검사 기능: Wiki 문서 스캔 기능. Day 3 자동 정리 기능: 스키마에 맞게 문서 재정렬. Day 4 최신화 제안 기능: 수정 필요 항목 리스트. Day 5 적용/검수: 자동 수정 또는 수동 승인 플로우. 규칙 예시: 필수 섹션 누락, 중복 내용, 오래된 내용, 형식 오류, 링크 오류. |
| 2026-08-24 ~ 2026-08-30 | 7A단계 | Obsidian Import | import된 문서의 schema 정렬/요약/중복 탐지 기준. 후속 연결 기능: Lint/Wiki 최신화와 연결. |
| 2026-08-31 ~ 2026-09-06 | 7B단계 | Notion Import | Notion 구조를 Fruition schema로 정렬하는 변환 규칙. 후속 연결 기능: Lint/Wiki 최신화와 연결. |
| 2026-09-07 ~ 2026-09-13 | 8단계 | TTS / STT 회의록 | 목표: 회의 음성을 텍스트로 변환하고 LLM으로 회의록 작성. Day 1 입력 방식 정의: 음성 파일 업로드 또는 실시간 녹음. Day 1~2 STT 연동: 음성 -> 텍스트 변환. Day 2~3 텍스트 정리: 화자, 문단, 타임라인 정리. Day 3 LLM 회의록 생성: 요약, 결정사항, 액션아이템 추출. Day 4 회의록 템플릿 적용: md/doc 형태 회의록 생성. Day 5 저장/공유: Wiki 저장, 다운로드, 링크 공유. |
| 2026-09-14 ~ 2026-09-27 | 9단계 | 팀 공유와 권한 | workspace별 가이드라인/템플릿 조회 기준 반영. 후속 연결 기능: 팀별 AI 출력 차별화. |
| 2026-09-28 ~ 2026-10-11 | 10단계 | Electron 데스크톱 앱 | local LLM 옵션과 fallback 정책 정의. 후속 연결 기능: 오프라인 또는 로컬 우선 실행. |

---

## Backend 날짜형 마일스톤

| 기간 | 단계 | 핵심 목표 | 주요 산출물 |
| --- | --- | --- | --- |
| 2026-06-08 ~ 2026-06-14 | 선행 분석 및 설계 | API, DB, 저장소 경계와 개발 순서 확정 | API 계약 초안, ERD/저장소 구조 검토, migration 방향, 개발 의존성 정리 |
| 2026-06-15 ~ 2026-06-28 | 1단계 | MVP API 연결 완성 | 공통 API 응답/에러 형식 정의, Swagger/OpenAPI 정리, CORS 설정, 로컬 실행 환경 구성, 문서 업로드 API, 문서 목록/상세/상태 API, Wiki graph/page API, Query API 1차, Chat 조회 API 1차, Mock Builder 연동. 문서 업로드/목록/상세/상태 API 구현, Wiki graph/page API와 Query API 1차 구현. |
| 2026-06-29 ~ 2026-07-05 | 2단계 | 채팅 저장과 근거 하이라이트 | Query 결과를 단순 문자열로 반환하지 않고, 답변과 근거를 분리 저장. Query 응답에 `answer`, `evidence_snippets`, `related_pages`, `graph_context`, `traversal_paths` 분리 반환, 이전 대화 조회 API 구현. `chat_messages`, `chat_message_references` 스키마 설계. |
| 2026-07-06 ~ 2026-07-19 | 3단계 | Wiki 상세/MD 편집기 | Spring Boot는 Object Storage 또는 로컬 스토리지에 저장된 Markdown을 읽어 반환하고, 사용자가 수정한 Markdown을 다시 저장하는 API를 제공. Wiki 페이지 Markdown 로드 API, Markdown 저장 API, Wiki 페이지 수정 API, 저장 시 새 버전 생성, `wiki_page_versions` 설계, active/draft 상태 관리, optimistic lock 또는 updated_at 기반 충돌 방지, diff preview API 1차. |
| 2026-07-20 ~ 2026-07-26 | 선행 안정화 | 버전, diff, rollback | Wiki 페이지 rollback API, 이전 버전 복구, 변경 이력 조회, `activity_logs` 저장, `audit_diffs` 저장, 누가/언제/무엇을 바꿨는지 기록, 변경 전후 `markdown_uri` 추적. `wiki_page_versions` 저장 완료가 rollback API, 변경 이력 조회의 선행 조건. |
| 2026-07-27 ~ 2026-08-02 | 4단계 | 사용자 가이드라인/템플릿 | `wiki_guidelines` CRUD, 가이드라인 활성화/비활성화, 문서 처리 시 활성 가이드라인 조회, Builder 요청에 가이드라인 주입, `document_templates` CRUD, 템플릿 기반 Wiki 페이지 skeleton 생성. |
| 2026-08-03 ~ 2026-08-09 | 5단계 | Markdown lint와 품질 검사 | Markdown 저장 전 lint API, source reference 누락 검사, evidence 누락 검사, wikilink 깨짐 검사, front matter 검사, 품질 경고 저장, CI 또는 테스트에서 lint 실행 가능하도록 분리. 품질 경고 저장 구조와 테스트 실행 가능한 lint 모듈 분리. |
| 2026-08-10 ~ 2026-08-23 | 6단계 | AWS 소규모 SaaS 테스트 배포 지원 | health check, dependency check, migration 상태 확인 endpoint. 후속 연결 기능: 배포 후 smoke test. request id, user id, workspace id, job id structured logging 유지. 후속 연결 기능: CloudWatch 로그 조회. |
| 2026-08-24 ~ 2026-08-30 | 7A단계 | Obsidian import | vault zip 업로드 API, `.md` 파일 일괄 파싱, front matter 추출, wikilink 추출, tag 추출, 첨부 파일 저장, Obsidian 페이지를 Fruition `wiki_pages`로 변환, import job 상태 관리. import job 상태 관리와 실패/성공 로그. |
| 2026-08-31 ~ 2026-09-06 | 7B단계 | Notion import | Notion export zip 업로드 API, Markdown/CSV/첨부 파싱, page hierarchy 변환, Notion 페이지를 document/wiki page로 매핑, 첨부 파일 저장, import 실패/성공 로그 관리. page hierarchy 변환 규칙과 실패/성공 로그. |
| 2026-09-07 ~ 2026-09-13 | 8단계 | TTS/STT 추가 | 음성 파일 업로드 API, STT 요청 job 생성, STT 결과를 transcript 문서로 저장, 답변/Wiki 페이지 TTS 요청 API, TTS 결과 audio cache 저장, 음성 처리 상태 관리, FastAPI 또는 외부 음성 모듈 호출. |
| 2026-09-14 ~ 2026-09-27 | 9단계 | 팀 공유/권한 | 사용자 계정 API, 로그인/인증, workspace 생성/조회, workspace member 관리, owner/editor/viewer 권한, 기존 주요 테이블에 workspace_id 적용, API별 권한 체크, 초대/권한 변경 API. users, workspaces, members, role 모델 설계, 기존 주요 테이블에 `workspace_id` 적용, API별 owner/editor/viewer 권한 체크. |
| 2026-09-28 ~ 2026-10-11 | 10단계 | Electron 데스크톱 앱 | Electron용 API base URL 환경변수화, local backend mode 지원, local storage path 설정, health check API, local file import API, 외부 LLM/local LLM 설정 분리, 로컬 실행 문서 정리, 데스크톱 앱과 API 연동 테스트. SaaS API 연동 포함. |

---

## Front 날짜형 마일스톤

| 기간 | 단계 | 핵심 목표 | 주요 산출물 |
| --- | --- | --- | --- |
| 2026-06-08 ~ 2026-06-14 | 선행 분석 및 설계 | 핵심 화면 흐름과 API 의존성 확정 | 화면 정보구조, API client 경계, loading/error/empty 상태 기준, 그래프/채팅 UX 흐름 |
| 2026-06-15 ~ 2026-06-28 | 1단계 | MVP API 연결과 기본 질의 플로우 | API client, route 구조, loading/error/empty 상태 공통 처리. 후속 연결 기능: 이후 모든 기능 화면의 기반. 문서 업로드 화면, 문서 처리 상태 UI, 그래프 렌더링, Wiki 페이지 조회, 질의 화면, 상태 polling, 그래프 하이라이트. |
| 2026-06-29 ~ 2026-07-05 | 2단계 | 채팅 저장과 Wiki 근거 저장 | 채팅 메시지 목록, 근거 snippet, related page, graph path 표시 컴포넌트. 후속 연결 기능: Wiki 상세, 요약 페이지 생성 플로우. 사용자가 저장할 전체 채팅/부분 구간을 선택하는 UI. 후속 연결 기능: AI Part 요약, 페이지 자동 생성. |
| 2026-07-06 ~ 2026-07-19 | 3단계 | MD 편집기와 Wiki 페이지 버전 관리 | Markdown editor, preview, 저장/취소/dirty 상태 처리. 후속 연결 기능: 버전 관리, lint, template 적용. split preview/edit, diff 미리보기. |
| 2026-07-20 ~ 2026-07-26 | 선행 안정화 | Rollback, Audit, 변경 이력 | 변경 이력 목록, diff viewer, rollback 확인 modal. 후속 연결 기능: 사용자 검수, 복구 플로우. |
| 2026-07-27 ~ 2026-08-02 | 4단계 | Schema, Guideline, Template 기능 | 템플릿 작성/수정 UI, 미리보기, 활성화/비활성화 UI. 후속 연결 기능: AI 초안 생성, 채팅 저장 템플릿 적용. 템플릿 적용 대상 선택 UI. 후속 연결 기능: Wiki, 회의록, 채팅 저장 결과 생성. |
| 2026-08-03 ~ 2026-08-09 | 5단계 | Markdown Lint와 Wiki 최신화 | 저장 전 lint 결과 표시, 수정 필요 항목 리스트, 승인/무시 UI. 후속 연결 기능: 수동 승인 기반 자동 정리. |
| 2026-08-10 ~ 2026-08-23 | 6단계 | AWS 소규모 SaaS 테스트 배포 | 사용자 피드백 수집 경로, issue tracker, 운영 리포트 양식. 후속 연결 기능: 테스트 사용자 피드백 관리. |
| 2026-08-24 ~ 2026-08-30 | 7A단계 | Obsidian Import | zip 업로드 UI, import 진행률, 결과 리포트. 후속 연결 기능: 사용자의 기존 자료 이식. |
| 2026-08-31 ~ 2026-09-06 | 7B단계 | Notion Import | Notion export 업로드 UI, hierarchy preview, import 결과 리포트. 후속 연결 기능: 사용자의 기존 자료 이식. |
| 2026-09-07 ~ 2026-09-13 | 8단계 | TTS/STT 회의록 | 음성 업로드/녹음 UI, STT 처리 상태, 회의록 preview. 후속 연결 기능: 저장/공유 플로우. TTS 재생 컨트롤과 음성 캐시 상태 처리. 후속 연결 기능: Wiki/Chat 음성 재생. |
| 2026-09-14 ~ 2026-09-27 | 9단계 | 팀 공유와 권한 | workspace switcher, member 관리, 권한별 disabled/readonly 상태. 후속 연결 기능: 협업 UI. |
| 2026-09-28 ~ 2026-10-11 | 10단계 | Electron 데스크톱 앱 | 브라우저 환경과 Electron 환경의 API base URL 분기. 후속 연결 기능: 데스크톱 패키징. 로컬 파일 접근/권한 UX, 설정 화면. 후속 연결 기능: 사용자 로컬 환경 설정. |

---

## DevOps/System 날짜형 마일스톤

| 기간 | 단계 | 핵심 목표 | 주요 산출물 |
| --- | --- | --- | --- |
| 2026-06-08 ~ 2026-06-14 | 선행 분석 및 설계 | 환경, 배포, 운영 경계와 일정 충돌 제거 | local/dev/test/staging/prod 역할 정의, 운영/배포 분리 기준, 품질 게이트 선후관계 |
| 2026-06-15 ~ 2026-06-28 | 1단계 | 개발 환경 표준화 | 목표: 팀원이 동일한 방식으로 로컬 환경을 실행하고 API 계약을 검증할 수 있는 기반 구축. Backend/Frontend 동시 실행 방식 정리: `docker-compose` 또는 dev script. 환경변수 표준화: `.env.example`, local/staging/prod 변수 목록. 환경 전략 초안: local/dev/test/staging/prod 목적, 배포 트리거, 접근 권한 기준. API 상태 확인: health check API, dependency check. 협업 실행 문서: 로컬 실행 README, 트러블슈팅. 기본 CI 구성: Backend test, Frontend lint/build, type check. |
| 2026-06-29 ~ 2026-07-19 | 2~3단계 | DB Migration과 파일 저장소 운영 | 목표: 채팅, Markdown, 버전 데이터가 늘어나도 안전하게 스키마와 파일을 관리. DB migration 규칙 정의: migration naming/versioning rule. Migration 안전장치 정의: backward-compatible migration 원칙, destructive migration 금지, 실패 시 배포 중단 기준. seed/test data 구성: 개발/테스트용 fixture. Object Storage 구조 정의: document, markdown, attachment, audio path 규칙. 백업/복구 초안: DB backup/restore, storage restore 절차. 복구 리허설 계획: 샘플 DB/object storage restore drill, 복구 시간 기록. 데이터 보존 기준: markdown version, import file, audio cache 보존 정책. |
| 2026-07-20 ~ 2026-08-23 | M5-a 운영 | 로그, 감사, 관측성 | 목표: 사용자 변경 이력과 비동기 작업 실패를 추적하고 운영 중 문제 원인을 확인할 수 있게 구성. Structured logging 도입: request id, user id, workspace id, job id 포함 로그. Audit log 운영 정책: 보존 기간, 조회 기준, 민감 정보 제외 기준. API 지표 수집: latency, error rate, endpoint별 실패율. Import job 모니터링: 성공/실패/부분 실패 로그, 재시도 기준. LLM/SLLM 지표 수집: model, latency, token/cost, fallback 여부. 운영 대시보드 초안: API p95 latency, 5xx rate, job failure, upload failure, LLM cost/token. 기본 알림 기준: health check 실패, 5xx 급증, job queue 적체, migration 실패, 비용 임계치 초과. |
| 2026-08-03 ~ 2026-09-06 | M5-b 배포 | CI 품질 게이트와 배포 준비 | 목표: 배포 전에 기본 품질 게이트를 구성하고, import와 권한 기능까지 포함해 품질과 보안 검증 범위를 확장. Markdown lint CI 연동: schema/evidence/source reference 검사. OpenAPI 변경 검증: spec diff, breaking change 확인. 권한 테스트 자동화: workspace owner/editor/viewer API 테스트. GitHub Actions CD 파이프라인 설계: branch/tag 배포 트리거, test/staging/prod 승격 규칙, workflow 파일 구조. 배포 artifact 관리: Docker image registry, image tag/version 규칙, release note 생성 기준. 배포 후 검증 자동화: health check, smoke test, migration 상태 확인, 실패 시 배포 중단 기준. Rollback 절차 정의: image rollback, DB migration rollback, 수동 승인 기준, 장애 알림 경로. AWS CDK IaC 구조 설계: CDK app/stack 구조, 환경별 context/parameter, synth/deploy workflow. 보안 설정 분리: secret 관리 방식, 환경별 CORS 정책. Secret/Config 주입 방식: AWS Secrets Manager 또는 SSM Parameter Store, GitHub Actions secret, 로컬 `.env` 분리. 보안 스캔 자동화: dependency audit, Docker image vulnerability scan, secret scanning. 파일 업로드 방어: size/type 제한, 악성 파일 차단 기준. |
| 2026-08-10 ~ 2026-08-23 | M5-b 배포 | AWS 소규모 SaaS 테스트 배포 | 목표: Markdown lint와 기본 품질 게이트까지 완료된 뒤, 작은 사용자 규모를 전제로 AWS 테스트 서버에 SaaS 형태로 먼저 배포하고 사용자 피드백과 운영 로그를 수집. AWS 테스트 배포 대상 정의: 테스트 서버 크기 EC2 기반 ECS 구성안. CDK 기반 테스트 환경 생성: VPC, EC2 capacity, ECS cluster/service, DB, storage, log group 생성/삭제 절차. SaaS 테스트 환경 구성: Backend/Frontend 배포 URL, API base URL, CORS, env 설정. Docker image build/push: Backend/Frontend image, registry push, tag/version 규칙. 테스트 배포 CD 적용: GitHub Actions workflow, main 또는 release tag 기준 자동 배포, 수동 승인 옵션. DB migration 배포 절차: 테스트 DB migration 적용/rollback 절차. CloudWatch 로그 구성: request id, user id, workspace id, job id 기반 로그 검색. 테스트 환경 알림 구성: health check, 5xx, job failure, 비용 초과 알림. 사용자 피드백 수집 경로: feedback form, issue tracker, 운영 리포트 양식. 운영 runbook 초안: 장애 확인, 로그 조회, 복구, rollback 절차. |
| 2026-09-14 ~ 2026-09-27 | M5-a 운영 | AWS 운영 환경 확장과 production 분리 | 목표: SaaS 테스트 배포에서 수집한 로그와 피드백을 기준으로 production 분리 여부와 운영 기준을 정리. AWS 환경 분리 기준 정의: test/staging/prod 계정 또는 VPC 분리 기준. production 전환 기준 정의: 사용자 수, 에러율, 응답 속도, 피드백 기준. 테스트/운영 서버 분리: 테스트 서버와 production 서버, 배포 URL, 도메인 분리. 환경별 CDK stack 분리: test/staging/prod stack, context/parameter 분리, drift 확인 절차. CloudWatch 로그 확장: 환경별 log group, metric, alarm 기준. 운영 대시보드 구성: latency p95, error rate, DB connection, job queue, LLM 비용, storage 사용량. 로그 조회와 장애 조사 절차: test/prod 로그 확인 방법, 주요 CloudWatch query 예시. Secret 관리: AWS Secrets Manager 또는 SSM Parameter Store 적용 기준. IAM 권한 정책: 배포 권한, 로그 조회 권한, 운영자 권한 분리. 배포 감사 추적: deploy actor, commit SHA, release tag, rollback 수행자 기록. 알림 구성: CloudWatch Alarm, error rate/latency/job failure 알림. 비용 모니터링: AWS Budget, 서비스별 비용 태그, LLM/SLLM 비용 지표 연동. Backup/Restore 리허설: 정기 restore drill, RPO/RTO 기록, 복구 실패 항목 backlog화. |
| 2026-09-28 ~ 2026-10-11 | M5-b 배포 | Electron 데스크톱 앱 패키징 | 패키징, 자동 업데이트 여부, 로컬 실행 문서. 후속 연결 기능: 사용자 설치와 SaaS 이후 데스크톱 지원. Electron은 SaaS 테스트 배포와 피드백 수집 이후 지원. API base URL, local mode, storage path 같은 결정은 Backend 초기부터 고려. |

---

## Test 날짜형 마일스톤

| 기간 | 단계 | 핵심 목표 | 주요 산출물 |
| --- | --- | --- | --- |
| 2026-06-08 ~ 2026-06-14 | 선행 분석 및 설계 | 테스트 기준과 일정 의존성 확정 | 단계별 완료 조건, 개발 종료 후 테스트 착수 기준, Jira 일정 충돌 점검 기준 |
| 2026-06-29 ~ 2026-07-05 | 1단계 | 기본 CI와 API 계약 검증 | 기본 CI 구성: Backend test, Frontend lint/build, type check. API 상태 확인: health check API, dependency check. 공통 API 응답/에러 형식, CORS, Swagger/OpenAPI, 로컬 실행 환경 고정은 Front API client, 상태 polling, 에러 처리의 기반. |
| 2026-07-20 ~ 2026-07-26 | 2~3단계 | Migration, seed/test data, storage 복구 검증 | DB migration 규칙 정의, backward-compatible migration 원칙, destructive migration 금지, 실패 시 배포 중단 기준. seed/test data 구성: 개발/테스트용 fixture. Object Storage 구조, DB backup/restore, storage restore 절차, 샘플 DB/object storage restore drill, 복구 시간 기록. |
| 2026-08-03 ~ 2026-08-09 | 선행~4단계 | Rollback/Audit/Template 검증 | `activity_logs`, `audit_diffs`, rollback API, 변경 이력 조회, structured logging, request id, audit log 보존 정책. Template 기능은 AI 출력 포맷, DB 저장 형식, Front 편집 UI의 필드 구조를 먼저 맞춰야 함. |
| 2026-08-10 ~ 2026-08-16 | 5단계 | Markdown lint와 품질 게이트 | Markdown lint CI 연동: schema/evidence/source reference 검사. 저장 전 lint API, source reference/evidence/wikilink/front matter 검사, 품질 경고 저장. CI에서 lint 실행 가능한 명령과 fixture 구성. 품질 검사 자동화. |
| 2026-08-24 ~ 2026-08-30 | 6단계 | AWS 배포 후 Smoke Test | 배포 후 검증 자동화: health check, smoke test, migration 상태 확인, 실패 시 배포 중단 기준. 테스트 DB migration 적용/rollback 절차. CloudWatch 로그 구성과 request id/user id/workspace id/job id 기반 로그 검색. 테스트 환경 알림: health check, 5xx, job failure, 비용 초과 알림. |
| 2026-09-07 ~ 2026-09-13 | 5~7B단계 | CI 품질 게이트와 배포 준비 검증 | OpenAPI 변경 검증: spec diff, breaking change 확인. 권한 테스트 자동화: workspace owner/editor/viewer API 테스트. GitHub Actions CD 파이프라인 설계 검증, 배포 artifact 관리, Docker image vulnerability scan, secret scanning, 파일 업로드 방어 기준. |
| 2026-09-07 ~ 2026-09-13 | 7A~7B단계 | Import job/log/progress 검증 | Obsidian import는 Markdown 저장, Wiki 페이지 버전, lint가 먼저 있어야 안정적. Notion은 hierarchy와 첨부 처리 복잡도가 높으므로 Obsidian import에서 job/log/progress 구조를 먼저 검증한 뒤 확장. 실패/성공 로그, 실패 재시도/운영 리포트 확인. |
| 2026-09-14 ~ 2026-09-20 | 8단계 | TTS/STT job 검증 | 음성 업로드/녹음, STT 저장, 답변/Wiki 페이지 TTS, 음성 캐시, job timeout/retry, 비용/latency 로그. 회의록 저장은 Template 기능과 Wiki 저장 기능이 먼저 있어야 완성. |
| 2026-09-28 ~ 2026-10-04 | 9단계 | 권한, 보안, AWS 운영 분리 검증 | workspace owner/editor/viewer API 테스트, workspace_id와 권한 모델 검증. production 분리 기준, secret/CORS/IAM 정책, AWS 환경 분리와 CloudWatch 로그, Secret/Config 관리 기준, Migration 안전장치와 복구 리허설 확인. |
| 2026-10-12 ~ 2026-10-18 | 10단계 | Electron/E2E QA | SaaS API 연동, API base URL 환경변수화, local backend mode, local storage path, local file import API, 외부 LLM/local LLM 설정 분리, 패키징/배포 문서, 로컬 실행 문서, 데스크톱 앱과 API 연동 테스트. |

---

## 일정 의존성 요약

| 먼저 끝나야 하는 기반 | 영향을 받는 기능 |
| --- | --- |
| Query 응답 DTO 고정 | 채팅 저장, 근거 하이라이트, graph 하이라이트, SLLM routing |
| Markdown 저장 + `wiki_page_versions` | 편집기, diff, rollback, lint, import, AI 자동 수정 |
| Template/Schema 구조 | 채팅 저장 페이지 생성, Wiki 최신화, 회의록, lint |
| Activity/Audit 로그 | rollback, AI 자동 정리, 팀 협업 신뢰성 |
| Import job/log/progress 구조 | Obsidian import, Notion import |
| `workspace_id`와 권한 모델 | 팀 공유, 템플릿/가이드라인 분리, 문서 접근 제어 |
| 환경변수와 local mode | Electron, 로컬 백엔드, local LLM |
| AWS 환경 분리와 CloudWatch 로그 | 테스트/운영 서버 분리, 장애 대응, 운영 비용 관리 |
| IaC와 환경별 설정 분리 | 반복 가능한 AWS 테스트 배포, staging/prod 분리, drift 관리 |
| CD 파이프라인과 artifact 규칙 | 자동 배포, rollback, release 추적, 운영 감사 |
| Secret/Config 관리 기준 | 안전한 배포, API key/JWT/LLM credential 분리, 권한 통제 |
| Migration 안전장치와 복구 리허설 | 배포 실패 대응, 데이터 복구, production 전환 판단 |
| 운영 대시보드와 알림 기준 | 장애 조기 감지, 비용 초과 감시, 사용자 피드백 대응 |
