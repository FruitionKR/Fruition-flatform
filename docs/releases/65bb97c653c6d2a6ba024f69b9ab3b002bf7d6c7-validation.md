# 릴리스 65bb97c6 검증 기록

## 소스
access bba83127, ai 760fcbf3, document 4cdf3cb0, frontend 1a569b86. 게시 직전 네 저장소 main과 일치. 새로 빌드: access-svc·document-svc·pipeline·converter. 재사용: frontend.

## 변경
- access #72(#73): 이전 동의의 SESSION 쿠키가 남은 브라우저 이동도 `/mcp/authorize` 동의 화면으로 넘긴다. 두 번째 MCP 인증에서 JSON이 보이던 문제.
- document #279(#280): MCP 블록 ID를 pipeline `source_blocks` 레지스트리로 통일(`POST /internal/mcp/source-blocks/resolve`), `get_document` 블록 줄 범위, `get_wiki_page` lint 준비 정보(`lint_target`·statements·links·`lint_target_page_ids`), pipeline 호출을 DB 트랜잭션 밖으로. `mcp-tools.v14`.
- ai #281(#282): resolve endpoint, MCP 편입 발행의 레지스트리 재대조·수정/삭제 블록만 무효화, `mcp_read=true` lint 준비 정보, ADD/REMOVE_LINK 키 비교.
- flatform #212: `MCP_WIKI_DRAFT_MAX_REQUEST_BYTES` 1 MiB → 4 MiB.

## DB 변경 (expand-only)
AI DB `mcp_wiki_source_blocks`에 nullable 컬럼 `line_start`·`line_end`·`block_type`을 `ADD COLUMN IF NOT EXISTS`로 추가. 기존 행·이전 이미지와 호환(이전 pipeline은 컬럼을 읽지 않음). document·access DB 변경 없음.

## 시험
- document: MCP 전체·wiki·lint 소켓 통합·아키텍처·OpenAPI 스냅샷 216개, CI 통과.
- ai: mcp_wiki_draft·mcp_read·wiki_ingestion 844개(Postgres 16), CI 통과. resolve `raw_text`와 줄 범위 원문을 무작위 문서 5000개(블록 19,270개)로 대조해 불일치 0.
- access: MCP 162개, CI 통과.
- 사전 배포 독립 리뷰: CRITICAL/HIGH 없음. MEDIUM 3건(트랜잭션 안 HTTP, 요청 한도, 여러 줄 라벨) 수정.

## 배포 중 알려진 영향
API rollout 순서가 access → document → pipeline이라, document 교체 후 pipeline 교체 전 수 분 동안 MCP `get_document`·편입·lint 원문 읽기가 `DEPENDENCY_UNAVAILABLE`일 수 있다. 웹 화면·웹 편입은 영향 없음. 배포 전 순번 ID로 시작된 MCP 편입은 웹 편입된 문서에서 `SOURCE_CHANGED`(재시작 필요).

## 배포 후 확인
- 운영 MCP: `get_document`가 레지스트리 ID·줄 범위를 주는지, `get_wiki_page.lint_target`·`statements`로 lint 제출(UPSERT·REMOVE_STATEMENT)과 웹 승인이 되는지.
- 같은 브라우저에서 MCP 인증을 두 번 연속 시도해 두 번째도 동의 화면이 뜨는지.
- MCP 클라이언트 도구 목록 갱신(`mcp-tools.v14`).
