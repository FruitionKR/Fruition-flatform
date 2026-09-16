# MSA 서비스 ↔ 코드 매핑

> 작성일: 2026-08-06
> 기준: [Fruition MSA 전환 및 AWS 배포 제안서](../../../../docs/backlog/backlog/Fruition_MSA_Proposal_revised.md)의 3-서비스 목표 구조
> 이 문서는 저장소 물리 재배치(services/ 도입)와 함께 작성되었다.

## 폴더 구조

```text
루트
├─ services/
│  ├─ backend/                Spring Boot 앱 1개 (access-svc + backend-api 예정분 동거)
│  │  └─ src/main/java/fruition/
│  │     ├─ access/           access-svc 이관 예정분
│  │     ├─ core/             backend-api 이관 예정분
│  │     └─ shared/           공용 유틸 (분리 시 양쪽에 복제 또는 라이브러리화)
│  └─ ai-svc/
│     ├─ pipeline/            구 llmPipeline (FastAPI, :8000)
│     └─ converter/           구 infra/converter (FastAPI, :8010, 아직 미연결)
├─ frontend/                  Next.js (문서 §2.4 — 서비스 분리와 무관)
└─ infra/                     compose·환경변수 (배포 단위 아님)
```

## 서비스 ↔ 패키지 매핑

| 제안서 서비스 | 코드 위치 | 구성 패키지/모듈 |
|---|---|---|
| `access-svc` | `services/backend/.../fruition/access/` | `user`, `security`(+oauth), `workspace` |
| `backend-api` | `services/backend/.../fruition/core/` | `document`, `wiki`, `wikischema`, `wikimaintenance`, `chat`, `query`, `agent`, `aihistory`(제안서 이후 신설) |
| `ai-svc` | `services/ai-svc/` | `pipeline/`(llmPipeline 모듈 11개), `converter/` |
| (공용) | `services/backend/.../fruition/shared/` | `util` — GlobalExceptionHandler, OpenApiConfig 등 |

## 아직 물리 분리하지 않은 이유

`fruition.core`의 8개 서비스가 `fruition.access.workspace.WorkspaceMemberRepository`를
컴파일 타임에 직접 참조한다(멤버십 검사). 제안서 §9 Phase 0~3의 선행 작업
(단일 인가 지점, 권한 projection, JWKS)이 구현되기 전에는 두 앱으로 나눌 수 없다.
현재 구조는 그 경계를 패키지 수준에서 먼저 고정한 것이다.

## 경로 이동 내역 (2026-08-06)

| 이전 | 이후 |
|---|---|
| `backend/` | `services/backend/` |
| `llmPipeline/` | `services/ai-svc/pipeline/` |
| `infra/converter/` | `services/ai-svc/converter/` |
| `fruition.{user,security,workspace}` | `fruition.access.{…}` |
| `fruition.{document,wiki,wikischema,wikimaintenance,chat,query,agent,aihistory}` | `fruition.core.{…}` |
| `fruition.util` | `fruition.shared.util` |

갱신된 참조: `scripts/*.sh`, `infra/compose.{ai,converter}.yml`,
`.github/workflows/tests.yml`, `services/backend/build.gradle`(infra/.env 상대경로), `.gitignore`.

**미갱신**: `docs/` 아래 79개 문서가 구 경로(`llmPipeline/`, `backend/`)를 언급한다.
역사적 문서(백로그·changelog)는 당시 경로가 맞으므로 그대로 두고,
현행 운영 문서를 수정할 때 마주치는 대로 갱신한다.

## 파일명 ↔ 기능 불일치 (관찰, 미수정)

| 위치 | 불일치 | 비고 |
|---|---|---|
| `services/ai-svc/pipeline/` | 폴더명은 pipeline이지만 동기 query·agent turn API도 포함 | 제안서 §4가 동기/비동기 분리를 요구 — 실행 형태 분리 시 정리 |
| `fruition.core.query` + `QueryRunStore` | in-memory 상태라 이름과 달리 확장 불가 | 제안서 Phase 1 외부화 대상 |
| `fruition.access.security.OAuthExchangeCodeStore` | "Store"지만 프로세스 메모리 Map | 제안서 Phase 1 외부화 대상 |
| `services/ai-svc/converter/app.py` | 단일 파일 앱, 모듈 구조 없음 | 제품 경로 미연결 상태라 유지 |
| `fruition.core.wikimaintenance` | 실제 기능은 lint 요청 중계 | 분리 시 이름 재검토 |
