# Agent Skill과 승인형 Workspace 작업

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-08-03
- 관련 이슈:
  - docs/issue/backend/2026-08-04.md
  - docs/issue/frontend/2026-08-04.md
- 관련 PR:
- 관련 작업 계획: docs/spec/sdd/tasks/agent-skills-and-folder-organization-tasks.md
- 관련 문서:
  - docs/spec/wiki-schema-contract.md
  - docs/spec/sdd/markdown-document-hierarchy.md
  - docs/spec/sdd/markdown-document-ai-editing.md

상태 흐름: Draft → Approved → In Progress → Verified

## 2. 배경

현재 llmPipeline의 /agent/turn은 요청을 분류한 뒤 query, Markdown 생성, Markdown 편집 UseCase 중 하나를 직접 실행한다. 여러 tool의 결과를 바탕으로 다음 행동을 결정하는 agent workflow는 제공하지 않는다.

현재 wiki_schema는 workspace/user별 활성 prompt 설정이다. 프론트엔드는 이를 “스킬”로 표시하지만 요청별 Skill 선택, 여러 enabled Skill, 명시적 Skill 커맨드, tool 실행, 변경 계획 승인과 실행 후 검증은 지원하지 않는다.

Backend에는 Workspace 단위 폴더 트리와 조회, 검색, 생성, 이름 변경, 이동 기능이 있다. 폴더·문서 변경에는 권한, current_version, Idempotency-Key, hierarchy cycle 검사가 적용된다.

사용자는 자연어나 명시적 Skill 커맨드로 문서 생성·편집과 폴더 정리를 요청하고, 채팅에서 함께 완료한 작업 방식을 재사용 가능한 Skill로 만들고자 한다. LLM의 초안 생성과 계획은 상태를 변경하지 않지만, Workspace 상태 조회와 폴더·문서 저장·변경은 모두 권한이 제한된 업무 Tool을 통해야 한다. 모든 mutation은 계획, 승인, 실행, 검증을 포함한 AgentRun으로 처리해야 한다.

## 3. 목표

- 자연어 또는 /<skill-name> <요청>으로 Skill을 선택한다.
- 요청별 Skill 미적용 모드를 제공한다.
- 개인 Skill과 Workspace 팀 Skill을 지원한다.
- Skill은 Markdown 생성·편집, Template 적용, 폴더 정리에 적용한다.
- query와 상태를 변경하지 않는 Markdown 초안·편집안 생성은 기존 실행 경로를 유지한다.
- Workspace 상태 조회는 read Tool, 폴더·문서의 영속 변경은 mutation Tool로만 수행한다.
- 문서 저장·본문 반영을 포함한 상태 변경 작업은 승인형 비동기 AgentRun으로 실행한다.
- 승인 전에는 상태를 변경하지 않고 승인된 operation만 실행한다.
- 계획이나 대상 version이 바뀌면 기존 승인을 무효화한다.
- 실행 후 operation별 결과와 최종 폴더·문서 상태를 보여준다.
- Agent는 실행 사용자의 현재 권한을 넘지 않는다.
- 현재 채팅에서 선택한 완료 작업을 일반화해 저장하지 않은 Skill proposal을 제안한다.

## 4. 범위

### 포함

- Skill 생성·수정·preview·publish·enable/disable
- 여러 enabled Skill, 개인 Skill, Workspace 팀 Skill
- 자연어 자동 선택, 명시적 선택, Skill 미적용 모드
- Markdown 생성·편집과 Template Skill
- 폴더 구조·문서 metadata·본문 조회와 검색
- 폴더 생성·이름 변경·이동
- 문서 생성·이름 변경·이동·본문 편집
- 계획 생성·preview·수정·승인·거절·취소
- 승인된 operation 실행과 결과 검증
- AgentRun, plan, 승인, job, tool 실행 이력
- PostgreSQL 기반 비동기 llmPipeline worker
- 채팅 안의 계획·승인·진행 상태 UI
- 현재 채팅의 완료 AgentRun 선택과 미저장 Skill proposal 제안
- 일회성 ID를 제거한 작업 규칙 추출, proposal 검토와 최종 publish 확인

### 제외

- query에 Skill 적용
- 폴더·문서 삭제와 복구
- 외부 Drive, 로컬 filesystem, S3 폴더 조작
- Workspace 사이의 항목 이동
- shell, SQL, 범용 HTTP tool
- Agent의 tool·권한 자체 확장
- 승인 bypass와 승인 후 계획의 임의 확장
- 예약 실행과 장시간 background automation
- 여러 Agent의 병렬 계획 실행
- SKILL.md import/export
- 별도 AgentRun 상세 화면과 SSE·WebSocket
- 실패·취소된 operation의 성공 사례 학습
- 사용자 확인 없는 Skill proposal publish·enable
- 승인된 operation을 그대로 재생하는 고정 ID 기반 매크로

### 사용자와 권한

- 기존 Backend 권한이 허용하는 모든 Workspace 멤버가 Agent Skill을 사용할 수 있다.
- 개인 Skill은 본인만 관리·사용한다.
- 팀 Skill은 owner/editor가 관리하고 모든 Workspace 멤버가 사용한다.
- 실제 폴더·문서 작업은 기존 Backend 권한 검사를 다시 통과해야 한다.

## 5. 요구사항

### REQ-001 Skill 호출 모드

시스템은 auto, explicit, off 호출 모드를 지원해야 한다.

- auto: enabled Skill 중 요청에 맞는 Skill을 자동 선택한다.
- explicit: /<skill-name> <요청>으로 Skill을 명시한다.
- off: 채팅 UI와 API의 skill_mode=off로 해당 요청에 Skill을 적용하지 않는다.
- 명시적 호출 API는 표시 이름이 아니라 skill_id를 전달한다.

#### 인수 조건

- Given: 별도 Skill 선택이 없는 자연어 요청이다.
- When: 요청을 처리한다.
- Then: auto 모드로 처리한다.
- Given: 접근 가능한 enabled Skill을 명시했다.
- When: 요청을 처리한다.
- Then: 명시한 Skill을 자동 선택보다 우선한다.
- Given: 명시한 Skill이 없거나 disabled 상태다.
- When: 요청을 처리한다.
- Then: 실행하지 않고 SKILL_NOT_FOUND 또는 SKILL_DISABLED를 반환한다.
- Given: off 모드다.
- When: 요청을 처리한다.
- Then: Skill 없이 기존 기능을 실행한다.

### REQ-002 Skill 자동 선택

AgentTurnRouter는 action과 Skill을 한 번에 선택해야 한다. 후보는 enabled 상태이고 현재 사용자가 접근할 수 있으며 action과 capability가 호환되는 개인 Skill 또는 현재 Workspace 팀 Skill이어야 한다. 한 요청에는 작업 Skill을 최대 하나만 적용한다.

#### 인수 조건

- Given: 하나의 Skill이 명확히 일치한다.
- When: Router가 요청을 분류한다.
- Then: action과 selected_skill_id를 반환한다.
- Given: 호환되는 Skill이 없다.
- When: 요청을 처리한다.
- Then: Skill 없이 기존 기능을 실행한다.
- Given: 여러 Skill이 비슷하게 일치한다.
- When: 하나를 명확히 선택할 수 없다.
- Then: 실행하지 않고 clarify와 후보 설명을 반환한다.
- And: 사용자는 Skill 하나 또는 Skill 없이 계속을 선택한 뒤 요청을 재개한다.
- Given: action이 chat_answer다.
- When: 요청을 처리한다.
- Then: query에는 Skill을 적용하지 않는다.

### REQ-003 Skill 적용과 우선순위

우선순위는 다음과 같다.

    system·developer 정책
    → Backend 권한·승인·안전 정책
    → 현재 사용자 요청
    → 명시적으로 선택한 Skill
    → 자동 선택한 Skill
    → Wiki Schema 기본 설정

Skill은 상위 정책, Backend 권한, 승인 정책, allowed tool을 변경하거나 약화할 수 없다. AgentRun은 시작 당시 선택한 Skill version을 끝까지 사용한다.

#### 인수 조건

- Given: Skill이 승인 생략이나 허용되지 않은 tool 사용을 지시한다.
- When: Agent가 Skill을 적용한다.
- Then: 해당 지시를 따르지 않고 기존 승인·권한·tool 정책을 유지한다.
- Given: 실행 중인 AgentRun의 Skill이 새 version으로 바뀌었다.
- When: 기존 AgentRun을 계속 처리한다.
- Then: 시작 당시 기록한 Skill version을 사용한다.

### REQ-004 Workspace 작업 계획

시스템은 읽기 전용 Tool로 현재 폴더·문서 상태를 조사하고 상태를 변경하지 않은 채 `create_folder`, `rename_folder`, `move_folder`, `create_document`, `move_document`, `rename_document`, `apply_document_edit` 계획을 생성해야 한다.

사용자에게 대상 이름, 현재·변경 위치 또는 편집 범위, 이유, 예상 최종 폴더·문서 상태를 표시한다. 내부 계획에는 대상 ID, `base_version`, 편집 target, operation 의존 관계를 저장한다.

- 실행 ReAct decision 최대 step: 40
- 계획 최대 operation: 20
- AgentRun 최대 tool 호출: 40
- 계획 생성 timeout: 3분

20개를 초과하는 작업은 현재 계획 완료 후 새 계획으로 처리한다. 대상을 명확히 식별할 수 없으면 clarification_required로 전환한다.

#### 인수 조건

- Given: 폴더 또는 문서 상태를 변경하는 요청이 들어왔다.
- When: 계획 생성이 완료됐다.
- Then: 상태 변경 없이 최대 20개의 operation을 반환한다.
- Given: 대상이 모호하거나 제한을 초과했다.
- When: 계획을 생성한다.
- Then: 추측하거나 제한을 넘기지 않고 확인 또는 제한 초과 사유를 반환한다.

### REQ-005 변경 승인과 취소

읽기, 검색, 계획 생성에는 승인이 필요하지 않다. 모든 Workspace mutation operation은 실행 전에 plan 승인을 받아야 하며 MVP에서는 bypass를 지원하지 않는다. Skill은 게시 전 검토와 최종 게시 확인을 REQ-011에 따라 별도로 처리한다.

승인은 run_id, plan_id, plan_version, operations_hash, 승인자와 승인 시각에 결합한다. 버튼 또는 같은 채팅의 자연어로 승인·거절할 수 있다. 자연어 승인은 해당 채팅에 승인 대기 계획이 정확히 하나일 때만 인증된 승인 API로 처리한다.

- 미승인 plan은 실행 job을 만들 수 없다.
- plan version이나 hash가 달라지면 재승인을 요구한다.
- 일부 operation 제외 요청은 새 plan version을 만들고 전체 재승인을 요구한다.
- 실행 중 취소하면 현재 operation 이후 새 operation을 시작하지 않는다.

#### 인수 조건

- Given: plan이 승인되지 않았다.
- When: 변경 tool 호출을 시도한다.
- Then: 호출을 거부한다.
- Given: 승인 후 plan version이나 hash가 바뀌었다.
- When: 실행을 시도한다.
- Then: 기존 승인을 무효화하고 재승인을 요구한다.

### REQ-006 승인된 계획 실행

- 계획에 없는 operation을 추가하지 않는다.
- 매 decision마다 최근 관찰과 operation 상태를 LLM에 제공하며, 필요한 현재 상태는 허용된 read tool로 조회한다.
- LLM은 허용된 read tool 호출, 실행 가능한 승인 operation 하나 선택, 새 계획 요청 중 하나만 선택한다. 남은 operation이 없으면 시스템이 자동으로 검증 단계로 전환한다.
- 상태 변경 tool과 인자는 LLM 출력이 아니라 승인된 plan operation에서 읽는다.
- 의존 operation은 선행 결과가 확인된 뒤 선택할 수 있으며 operation은 한 번에 하나씩 실행한다.
- LLM이 승인되지 않았거나 아직 실행 가능하지 않은 operation을 선택하면 실행하지 않는다.
- 승인된 계획으로 목표를 안전하게 달성할 수 없으면 clarification_required로 중단하고 새 plan version과 hash 승인을 요구한다.
- 실행 decision은 최대 40회이며 AgentRun 전체 tool 호출은 최대 40회다.
- 남은 Tool 호출 수가 pending mutation 수와 같으면 추가 read를 허용하지 않으며, 더 적으면 react_tool_budget_insufficient 사유로 clarification_required 전환한다.
- operation마다 고유한 Idempotency-Key를 사용한다.
- timeout 또는 retryable 오류는 같은 key로 최대 2회 재시도한다.
- 실패한 operation과 독립적인 operation은 계속 실행한다.
- 자동 rollback은 수행하지 않는다.
- 대상 version이 다르면 conflicted로 기록하고 실행하지 않는다.
- LLM의 chain-of-thought는 저장하지 않고 선택한 action, 제한된 관찰 결과와 실행 결과만 사용한다.
- 새 계획 요청 사유는 state_changed, insufficient_information, plan_no_longer_safe, goal_not_achievable 중 하나만 허용하고 AgentRun error_code로 반환한다.

#### 인수 조건

- Given: 폴더 생성에 의존하는 문서 이동이 있다.
- When: 계획을 실행한다.
- Then: 폴더 생성 성공 후 문서 이동을 실행한다.
- Given: 여러 독립 operation이 실행 가능하다.
- When: 다음 행동을 선택한다.
- Then: LLM이 그중 하나를 선택하고 시스템은 승인 당시 저장한 tool과 인자로 실행한다.
- Given: LLM이 계획에 없는 operation이나 변경된 인자를 반환한다.
- When: 상태 변경을 실행하려 한다.
- Then: 해당 출력을 실행하지 않고 승인된 operation 경계를 유지한다.
- Given: 관찰 결과 승인된 계획을 그대로 진행할 수 없다.
- When: LLM이 새 계획을 요청한다.
- Then: 제한된 사유 코드를 반환하고 clarification_required로 중단한 뒤 사용자 수정 지시와 새 승인을 기다린다.
- Given: 남은 Tool 호출 수가 pending mutation 수 이하이다.
- When: 다음 행동을 선택한다.
- Then: mutation 실행 예산을 보존하고 부족하면 계획 축소를 요청한다.
- Given: operation 하나가 최종 실패했다.
- When: 독립 operation이 남아 있다.
- Then: 남은 작업을 계속하고 최종 상태를 partial_failed로 기록한다.

### REQ-007 실행 결과 검증

Tool 호출 후 실제 위치, 이름, 본문 version을 다시 조회해야 한다. API 호출이 성공했더라도 실제 상태가 계획과 다르면 verification_failed로 기록하고 추가 변경을 수행하지 않는다.

Operation 상태는 succeeded, failed, skipped, forbidden, conflicted, verification_failed, cancelled 중 하나다. 검증 후 operation별 상태와 최종 폴더·문서 상태를 보여준다.

#### 인수 조건

- Given: 변경 tool 호출이 성공했다.
- When: 검증 단계를 실행한다.
- Then: 실제 위치, 이름, version을 재조회해 계획과 비교한다.
- Given: 재조회 결과가 계획과 다르다.
- When: 결과를 기록한다.
- Then: verification_failed로 표시하고 추가 변경을 수행하지 않는다.

### REQ-008 비동기 AgentRun

Workspace mutation AgentRun은 PostgreSQL job과 별도 llmPipeline worker가 비동기로 실행해야 한다.

    queued → planning → awaiting_approval
    → queued_for_execution → executing → verifying
    → completed | partial_failed | failed | conflicted | cancelled

API는 완료를 기다리지 않고 run_id를 반환한다. 화면이나 HTTP 연결이 종료돼도 Worker는 저장된 상태를 기준으로 계속 처리하며 사용자는 run_id로 상태를 다시 조회할 수 있다.

#### 인수 조건

- Given: 폴더 또는 문서 mutation AgentRun을 시작했다.
- When: API가 요청을 접수했다.
- Then: 완료를 기다리지 않고 run_id와 현재 상태를 반환한다.
- Given: 화면이나 API 연결이 종료됐다.
- When: Worker가 job을 처리한다.
- Then: 저장된 상태를 기준으로 계속 실행하고 run_id 조회를 지원한다.

### REQ-009 기존 기능과 Endpoint 경계

기존 `/agent/turn`은 query, 새 Markdown 초안과 사용자가 직접 제공한 비영속 텍스트의 편집안을 직접 처리한다. 기존 Workspace 문서를 읽거나 Markdown 결과를 새 문서에 저장·기존 본문에 반영하는 요청은 `workspace_workflow`로 처리한다. Router가 `folder_organize` 또는 `workspace_workflow`로 판정하면 내부적으로 AgentRun을 생성하고 `run_id`를 반환한다. Frontend는 요청을 미리 분류해 별도 생성 endpoint를 다시 호출하지 않는다. Kill switch 상태에서도 기존 query와 Workspace 상태에 접근하지 않는 draft 생성은 유지한다.

#### 인수 조건

- Given: 기존 query, 새 Markdown 초안 또는 사용자가 직접 제공한 비영속 텍스트 편집 요청이다.
- When: /agent/turn으로 요청한다.
- Then: 기존 요청·응답 계약을 유지한다.
- Given: `folder_organize` 또는 문서 저장·본문 반영 요청이다.
- When: Router가 여러 단계와 승인이 필요하다고 판정한다.
- Then: AgentRun을 생성하고 run_id를 반환한다.
- Given: Agent Skill kill switch가 꺼져 있다.
- When: 기존 query와 저장하지 않는 Markdown 초안·편집안 생성을 실행한다.
- Then: 기존 UseCase가 정상 작동한다.

### REQ-010 Tool-only Workspace 상태 접근

Agent는 Workspace의 폴더·문서 상태를 Frontend snapshot, DB나 내부 repository에서 직접 읽거나 변경하지 않고 Spring Backend의 업무 단위 Tool만 사용해야 한다. LLM의 판단, 계획과 Workspace 상태에 의존하지 않는 Markdown 초안 생성은 Tool 대상이 아니며, 영속 저장과 본문 반영은 mutation Tool로 분리한다.

#### 인수 조건

- Given: Agent가 문서 내용을 확인해야 한다.
- When: 계획 또는 실행에 필요한 현재 상태를 조사한다.
- Then: 실행 사용자의 권한을 검사하는 `get_document_content` read Tool을 사용한다.
- Given: LLM이 새 문서 Markdown을 생성했다.
- When: Workspace에 저장하려 한다.
- Then: 승인된 `create_document` operation을 Backend Tool Gateway로 실행한다.
- Given: LLM이 문서 편집안을 생성했다.
- When: 기존 본문에 반영하려 한다.
- Then: 승인된 `apply_document_edit` operation과 `base_version`으로 실행한다.
- Given: Tool Gateway를 통하지 않는 DB, shell, SQL 또는 repository 접근을 요청했다.
- When: Agent가 실행을 결정한다.
- Then: 실행하지 않고 허용되지 않은 경계로 기록한다.

### REQ-011 완료 작업 기반 Skill proposal

사용자가 같은 채팅에서 완료한 작업을 Skill로 만들어 달라고 요청하면 시스템은 선택된 성공 AgentRun과 사용자 수정 지시에서 반복 가능한 규칙을 추출해 저장하지 않은 Skill proposal을 제안해야 한다.

- 사용자가 완료 작업과 반영할 사용자 지시 turn을 명시적으로 선택하며, 선택이 없으면 같은 채팅의 가장 최근 completed AgentRun 하나와 그 run에 연결된 요청·수정 지시만 사용한다.
- failed, conflicted, cancelled operation은 성공한 실행 예시로 사용하지 않는다.
- 고정 resource ID, 일회성 이름·위치, 문서 본문, 인증정보를 Skill instructions에 복사하지 않는다.
- 성공한 Tool 종류는 capability와 `allowed_tools` 후보를 좁히는 근거로만 사용한다.
- 사용자 추가·제외 지시는 반복 가능한 제약 규칙으로 제안한다.
- LLM은 구조화된 Skill proposal만 반환하며 자동으로 저장·publish·enable하지 않는다.
- 사용자가 proposal을 확인하고 게시를 승인하면 최종 보안 검증 후 published version으로 바로 저장한다.

#### 인수 조건

- Given: 같은 채팅에 완료된 프로젝트 정리 AgentRun이 있다.
- When: 사용자가 “방금 방식대로 Skill로 만들어줘”라고 요청한다.
- Then: 사용한 Tool과 사용자 수정 지시를 일반화한 이름, 설명, capability, instructions, `allowed_tools` proposal을 반환한다.
- Given: 선택한 작업 기록에 문서·폴더 ID와 일회성 프로젝트 이름이 있다.
- When: Skill proposal을 만든다.
- Then: 해당 값을 고정 인자로 저장하지 않고 새 요청에서 다시 식별할 규칙으로 바꾼다.
- Given: 사용자가 proposal 저장을 확인하지 않았다.
- When: 응답을 반환한다.
- Then: Skill row, published version과 enabled 상태를 만들지 않는다.
- Given: 사용자가 proposal 게시를 승인했다.
- When: Skill을 최종 저장한다.
- Then: 선택한 source run 참조와 lint 결과를 기록하고 published version을 활성화한다.

## 6. 설계

### 6.1 설계 요약

    Frontend
    → Spring backend
    → llmPipeline Router
       ├─ query·비영속 Markdown draft → 기존 UseCase
       ├─ folder_organize      → AgentRun
       ├─ workspace_workflow   → AgentRun
       │                         → read Tool로 관찰
       │                         → 계획
       │                         → 승인 대기
       │                         → 승인된 mutation Tool 실행
       │                         → 검증
       ├─ skill_authoring      → 현재 자연어 요구 구체화
       │                         → 입력·참조·출력 필터링
       │                         → 미저장 제안 검토
       │                         → 최종 검증 후 published 저장
       └─ skill_draft_proposal → 완료 AgentRun 일반화
                                 → 사용자 확인 후 최종 게시

Wiki Schema는 모든 요청에 적용되는 기본 설정으로 유지하고 Skill은 요청별 작업 지침으로 별도 관리한다. Agent는 Workspace 상태에 접근할 때 Spring Backend의 업무 단위 Tool만 사용한다. LLM의 초안·편집안 생성과 reasoning은 Tool이 아니지만 결과를 영속화하는 작업은 반드시 승인된 mutation Tool로 분리한다.

### 6.2 Skill과 version

    skills
    - id, workspace_id(nullable for personal), scope_type, owner_user_id, slug
    - enabled_version_id, status, created_at, updated_at

    skill_versions
    - id, skill_id, version, name, description
    - instructions_markdown, capabilities, allowed_tools
    - lint_result, status, created_by, created_at, published_at

    skill_version_sources
    - skill_version_id, source_agent_run_id, source_turn_id, source_type, created_at

Enabled Skill 수정은 기존 version을 덮어쓰지 않고, 안전성 검사를 통과한 새 published version을 만든 뒤 enabled_version_id를 교체한다. 기존 AgentRun은 시작 당시 version을 유지한다.

완료 작업에서 만든 Skill proposal은 게시 전에는 저장하지 않는다. 최종 게시 시 사용자가 선택한 source AgentRun과 사용자 지시 turn 참조만 별도 저장한다. 현재 채팅 전체를 암묵적으로 입력하지 않으며 문서 본문, 전체 prompt, 인증정보와 LLM chain-of-thought는 Skill source에 복사하지 않는다.

### 6.3 Capability와 Tool

MVP capability는 document-create, document-edit, folder-organize, template이다. 시스템은 capability별 허용 tool 목록을 제한하고 allowed_tools는 후보를 더 좁힌다.

읽기 tool:

    list_root_items
    list_folder_children
    search_hierarchy
    get_breadcrumb
    get_document_metadata
    get_document_content
    list_agent_run_artifacts

변경 tool:

    create_folder
    rename_folder
    move_folder
    move_document
    rename_document
    create_document
    apply_document_edit

#### 6.3.1 공통 Skill 선택 흐름

네 capability는 같은 Skill 선택 절차를 사용하지만 선택 이후의 실행 방식은 서로 다르다.

    사용자 요청
    → skill_mode 해석
      - auto: 접근 가능한 enabled Skill 전체를 후보로 사용
      - explicit: skill_id 또는 /<skill-slug>로 지정한 Skill만 사용
      - off: Skill 후보를 비우고 기존 기능 실행
    → 현재 사용자와 Workspace 기준 접근 권한 확인
    → AgentTurnRouter가 action과 호환 Skill을 함께 선택
    → capability와 action 호환성 재검증
    → 선택된 Skill version의 instructions 적용

action과 capability의 호환 관계는 다음과 같다.

| capability | 호환 action | 실행 방식 | 상태 변경 승인 | allowed_tools |
|---|---|---|---|---|
| document-create | markdown_create 또는 workspace_workflow | 초안은 기존 UseCase, 저장은 AgentRun | create_document 전 plan 승인 | hierarchy planning read, get_document 계열, create_document |
| document-edit | markdown_edit 또는 workspace_workflow | 비영속 입력 편집은 기존 UseCase, Workspace 문서 편집은 AgentRun | apply_document_edit 전 plan 승인 | hierarchy planning read, get_document 계열, apply_document_edit |
| template | markdown_create, markdown_edit 또는 workspace_workflow | 초안·편집안은 기존 UseCase, 저장·반영은 AgentRun | mutation 전 plan 승인 | document capability Tool의 부분집합 |
| folder-organize | folder_organize 또는 workspace_workflow | AgentRun과 bounded ReAct | mutation 전 plan 승인 | folder/document 배치 Tool의 부분집합 |

명시한 Skill이 없거나 published version이 없거나 접근할 수 없으면 오류를 반환한다. `disabled`는 자연어 auto 후보에서만 제외하며 명시적 커맨드는 계속 실행할 수 있다. auto 후보 중 하나가 명확히 일치하면 해당 Skill을 적용한다. 여러 후보가 비슷하면 실행하지 않고 Skill 하나 또는 Skill 없이 계속할지를 사용자에게 묻는다. 호환되는 Skill이 없으면 Skill 없이 기존 action을 실행한다. chat_answer에는 Skill을 적용하지 않는다.

Skill instructions는 system·developer 정책, Backend 권한·승인·안전 정책과 사용자 요청보다 낮은 우선순위로 조립한다. 선택 이후에는 정확한 published Skill version을 사용하며 실행 중 enabled version이 바뀌어도 현재 요청에는 영향을 주지 않는다.

#### 6.3.2 document-create 예시: meeting-notes Skill

`meeting-notes` Skill은 회의록의 구조와 사실성 규칙을 제공한다. 사용자는 자연어로 요청하거나 Skill을 명시할 수 있다.

    사용자:
    오늘 논의한 내용으로 회의록을 만들어줘.

    Agent:
    `meeting-notes` Skill을 적용해 대화에서 확인된 내용으로 회의록을 작성하겠습니다.
    확인되지 않은 참석자, 결정 사항, 담당자와 기한은 임의로 만들지 않습니다.

    Agent:
    # 2026-08-04 제품 회의록

    ## 참석자
    - 김OO

    ## 논의 내용
    - Agent가 사용할 수 있는 Tool과 권한 경계를 검토했습니다.

    ## 결정 사항
    - Agent는 사용자가 직접 수행할 수 있는 범위의 작업만 실행합니다.

    ## 후속 작업
    - Backend Tool Gateway 구현 — 담당: 김OO, 기한: 2026-08-08

명시적 호출은 같은 방식으로 실행한다.

    사용자:
    /meeting-notes 오늘 논의한 내용으로 회의록을 만들어줘.

    Agent:
    요청한 `meeting-notes` Skill을 적용해 회의록을 작성했습니다.

Markdown 초안을 만드는 단계까지는 상태를 변경하지 않으므로 별도 계획과 승인을 만들지 않는다. Router는 `markdown_create`와 Skill을 선택하고 기존 문서 생성 UseCase에 Skill instructions를 전달한다.

사용자가 결과를 Workspace 문서로 저장하면 mutation 경로로 전환한다.

    사용자:
    이대로 `제품 회의록` 문서로 저장해줘.

    Agent:
    다음 변경을 실행하려고 합니다.
    1. 현재 Workspace에 `제품 회의록` 문서를 생성합니다.
    2. 방금 확인한 Markdown을 본문으로 저장합니다.
    저장 권한과 대상 위치를 확인했고, 승인 전에는 문서를 만들지 않습니다.
    [승인] [수정 요청] [취소]

승인 후 `create_document` Tool이 기존 Backend 문서 생성 권한과 Idempotency-Key를 검사해 저장한다.

여러 생성 Skill이 비슷하게 일치하면 결과를 만들기 전에 다음과 같이 묻는다.

    Agent:
    이 요청에는 `meeting-notes`와 `quick-meeting-summary` Skill이 모두 비슷하게 맞습니다.
    어느 Skill을 사용할까요? Skill 없이 작성할 수도 있습니다.

#### 6.3.3 document-edit 예시: formal-style-editor Skill

`formal-style-editor` Skill은 의미와 Markdown 구조를 유지하면서 선택 영역의 문체만 변경한다.

    사용자:
    이 문단을 공식적인 문체로 정리해줘.

    Agent:
    `공식 문체 교정` Skill을 적용하겠습니다.
    선택한 문단의 의미, 수치, 링크, 코드와 고유명사는 유지합니다.

    변경 전:
    이번에 우리가 만든 기능은 여러 상황에서 꽤 잘 쓸 수 있을 것 같아요.

    변경 후:
    이번에 구현한 기능은 다양한 상황에서 활용할 수 있습니다.

명시적 호출은 `/formal-writing 선택한 문단을 공식적인 문체로 정리해줘`처럼 입력한다. 활성 문서 ID와 selection은 target 힌트로만 사용하며 본문 source of truth로 신뢰하지 않는다. Agent는 `get_document_content` Tool로 현재 권한과 version을 확인한다. 활성 문서가 없고 사용자가 편집할 텍스트도 직접 제공하지 않았다면 추측하지 않고 문서를 열거나 텍스트를 제공해 달라고 요청한다.

사용자가 직접 제공한 비영속 텍스트의 편집안은 `markdown_edit` UseCase로 만들 수 있다. 기존 Workspace 문서 편집은 `workspace_workflow`에서 read Tool로 현재 본문을 가져와 편집안과 mutation plan을 함께 만들고, Agent는 target, 변경 요약과 예상 version을 설명한다. 승인 후 `apply_document_edit` Tool을 호출하며 Backend는 문서 편집 권한, `base_version`과 target 범위를 다시 검사한다.

#### 6.3.4 template 예시: 주간보고서 Template Skill

`주간보고서 Template` Skill은 제공된 업무 내용을 정해진 섹션 순서로 작성한다.

    사용자:
    이번 주 대화 내용을 바탕으로 주간보고서를 새로 만들어줘.

    Agent:
    `주간보고서 Template` Skill을 적용하겠습니다.
    대화에서 확인된 내용만 사용하고, 정보가 없는 항목은 비워 두겠습니다.

    Agent:
    # 주간보고서

    ## 이번 주 목표
    - Agent Skill 실행 구조 확정

    ## 완료한 작업
    - bounded ReAct 실행 경계 구현

    ## 진행 중인 작업
    - 사용자 승인 흐름 문서화

    ## 문제와 위험
    - Backend와 Frontend 통합 검증이 남아 있음

    ## 다음 주 계획
    - 통합 테스트 수행

명시적 호출은 `/weekly-report 이번 주 업무 내용으로 새 주간보고서를 만들어줘`처럼 입력한다. 결과를 초안으로만 반환하면 `markdown_create` 경로를 사용하고, Workspace에 저장하거나 기존 문서에 반영하면 `workspace_workflow` 계획과 승인을 거친다.

현재 구현은 기존 문서 전체를 외부 Template 구조로 재구성하는 `template_transform`을 지원하지 않는다. 이 요청은 일반 편집으로 추측하지 않고 다음과 같이 안내한다.

    사용자:
    기존 문서를 회사 주간보고서 Template 구조로 전부 다시 배치해줘.

    Agent:
    기존 문서 전체를 외부 Template 구조로 재배치하는 기능은 현재 지원하지 않습니다.
    선택 영역이나 현재 섹션의 일반 편집은 가능하지만, 전체 재구성은 실행하지 않았습니다.

#### 6.3.5 folder-organize 예시: 프로젝트 자료 정리 Skill

`프로젝트 자료 정리` Skill은 관련성이 명확한 문서만 프로젝트 폴더로 옮긴다. 폴더와 문서 배치를 변경하므로 계획, 사용자 승인, bounded ReAct 실행과 결과 검증을 거친다.

##### 요청과 계획 생성

    사용자:
    Alpha 프로젝트 관련 문서를 한 폴더로 정리해줘.

    Agent:
    `프로젝트 자료 정리` Skill을 적용하겠습니다.
    현재 폴더와 문서를 확인한 뒤 변경 계획을 제안할게요.
    계획을 승인하기 전에는 폴더나 문서를 변경하지 않습니다.

Agent는 읽기 Tool로 현재 hierarchy와 대상 문서를 조사한다. Planner LLM은 조사 결과와 Skill instructions를 바탕으로 operation을 만들고, 시스템은 각 대상 ID, `base_version`, 의존 관계와 `allowed_tools`를 검증한다.

    Agent:
    다음과 같이 정리하려고 합니다.

    1. 루트에 `Alpha` 폴더를 생성합니다.
       이유: 같은 이름의 프로젝트 폴더가 현재 없습니다.
    2. `Alpha 기획서`를 새 `Alpha` 폴더로 이동합니다.
       이유: 문서 제목과 내용에서 Alpha 프로젝트 관련 문서임을 확인했습니다.

    예상 결과:
    /
    └─ Alpha/
       └─ Alpha 기획서

    다른 문서와 폴더는 변경하지 않습니다.
    이 계획을 승인하면 실행을 시작합니다.
    [승인] [수정 요청] [취소]

화면에는 자연어 설명과 함께 승인 대상 `plan_version`과 `operations_hash`가 결합된 계획 카드를 표시한다. 내부 operation은 다음과 같다.

    operation 1: Alpha 폴더 생성
      tool: create_folder
      depends_on: []

    operation 2: Alpha 기획서 이동
      tool: move_document
      depends_on: [operation 1]
      destination: operation 1의 생성 결과 id

##### 계획 수정과 승인

사용자는 버튼이나 같은 채팅의 자연어로 승인할 수 있다. 자연어 승인은 승인 대기 중인 계획이 정확히 하나일 때만 허용한다.

    사용자:
    Alpha 회의록도 같이 옮기는 계획으로 바꿔줘.

    Agent:
    기존 계획은 실행하지 않고 수정하겠습니다.
    `Alpha 회의록`이 관련 문서인지 확인한 뒤 새 계획을 보여드릴게요.

수정 요청은 기존 plan을 덮어쓰지 않고 새 `plan_version`과 `operations_hash`를 만든다. 이전 승인은 무효이며 사용자는 변경된 전체 계획을 다시 승인해야 한다.

    사용자:
    승인해줘.

    Agent:
    승인된 계획으로 실행을 시작합니다.
    계획에 없는 작업이나 승인된 인자와 다른 변경은 수행하지 않습니다.

##### 승인 후 ReAct 실행

승인 후 LLM은 최근 Tool 결과를 관찰하고 다음 행동을 하나씩 고른다. LLM이 새 mutation을 자유롭게 만드는 것이 아니라, 승인된 operation 중 현재 실행 가능한 하나를 선택한다.

    Agent:
    `Alpha` 폴더를 생성하고 있습니다.

    Agent:
    ✓ `Alpha` 폴더를 생성했습니다.
    `Alpha 기획서`를 새 폴더로 이동하고 있습니다.

    Agent:
    ✓ `Alpha 기획서`를 이동했습니다.
    최종 폴더 구조를 확인하고 있습니다.

    Agent:
    ✓ 최종 폴더 구조와 문서 위치를 확인했습니다.
    요청한 정리가 완료됐습니다.

각 mutation의 Tool과 arguments는 LLM 응답이 아니라 승인된 operation에서 읽는다. Backend는 호출할 때마다 실행 사용자의 현재 Workspace·리소스 권한, plan version·hash, `base_version`과 `Idempotency-Key`를 다시 검사한다. 남은 operation이 없으면 추가 LLM 호출 없이 실제 hierarchy 검증으로 전환한다.

##### 실행 중 계획을 계속 사용할 수 없는 경우

계획 후 대상 version이나 hierarchy가 바뀌어 승인된 계획을 안전하게 계속할 수 없으면 Agent는 임의로 우회하지 않는다.

    Agent:
    `Alpha 기획서`의 위치가 계획 승인 후 변경되어 현재 계획을 그대로 실행할 수 없습니다.
    실행을 중단했습니다. 현재 상태를 다시 확인해 새 계획을 만들까요?

사용자가 동의하면 `state_changed` 사유로 새 계획을 만들고 다시 설명한 뒤 승인을 요청한다. Tool 호출 예산이 pending mutation 수보다 적으면 `react_tool_budget_insufficient`로 중단하고 작업 범위를 줄인 새 계획을 요청한다.

Skill은 `allowed_tools`를 넓히지 못한다. 예를 들어 Skill이 `create_folder`와 `move_document`만 허용한다면 rename Tool은 사용할 수 없다. 삭제, SQL, shell, 범용 HTTP Tool은 capability에 존재하지 않으므로 instructions에 적혀 있어도 실행할 수 없다.

### 6.4 Skill 생성·수정·활성화 흐름

Skill 관리 화면은 사용자가 직접 작성한 원문을 보존하는 authoring과 짧은 자연어를 LLM으로 구체화하는 authoring을 함께 지원한다. 두 방식 모두 게시 전 검토 화면으로 이동하며, 사용자에게 capability·Tool은 보여주지 않는다.

#### 6.4.1 자연어 Skill authoring

사용자는 범위, 짧은 자연어와 필요할 때만 참조 문서 ID를 보낸다. capability와 `allowed_tools`를 직접 입력하지 않는다.

    사용자:
    선택한 회의록 문서 구조로 이후 회의록을 작성하는 Skill을 만들어줘.

    시스템:
    1. AgentRun Tool과 분리된 Skill authoring 전용 read endpoint에서 Workspace·User 권한으로 참조 문서 metadata와 Markdown을 조회한다.
    2. 입력과 참조의 크기·prompt injection을 먼저 검사한다.
    3. 참조 Markdown에서 heading·목록 marker·표 header 구조만 추출하고, 실제 문서명과 본문을 제외한 비신뢰 데이터로 LLM에 전달한다.
    4. 서로 다른 prompt의 intent 분류기와 검증기가 `skill_kind`, 참조 용도, Tool을 각각 판정한다.
    5. 두 판정이 전부 일치할 때만 서버가 `skill_kind`를 capability로 변환하고 Markdown을 생성한다.
    6. 사용자에게 capability와 Tool을 제외한 Skill Markdown과 보안 결과를 반환하고 DB에는 저장하지 않는다.

Skill 관리 화면의 `POST /skills/author`는 단발 입력이므로 세부 정보가 부족해도 보충 질문 대신 편집 가능한 일반 구조를 반환한다. 다만 intent 판단이 모호하거나 두 판정이 불일치하면 지원 작업을 명확히 적도록 `400`으로 거절한다. 커맨드 식별자는 lowercase-hyphen이며 입력하지 않으면 LLM이 후보를 제안한다. personal Skill은 계정 전체, team Skill은 현재 Workspace에 귀속한다. `preserve`는 현재 Markdown을 변경하지 않고 보안 재검토하며, `enhance`는 자연어를 구체화한다. 차단 화면의 `regenerate`는 규칙 검사에서 찾은 위험 구간을 필수 제거한 뒤 안전한 흐름으로 재작성한다. 분류기와 검증기는 참조 문서의 용도를 고정 템플릿과 일반 구조 참고로 각각 구분하고, 고정 템플릿으로 일치하게 판단한 참조 문서가 하나일 때만 서버가 추출한 heading·목록 marker·표 header를 고정 출력 템플릿으로 그대로 조립한다. 세 모드 모두 제안만 반환하며, 지원 Agent action에 매핑할 수 없는 요청은 제안·게시하지 않는다. 채팅의 모호함·불일치는 보충 질문으로 반환한다.

입력·description·참조·생성 결과에서 규칙 검사 또는 LLM 의미 검사로 차단 보안 문제가 발견되면 `status=blocked`와 출처·위치·이유를 반환하고 `최종 게시`를 막는다. 참조 문제는 문서 ID를 함께 반환한다. 사용자가 해당 문구를 수정하면 기존 통과 상태를 폐기하고 `보안 재검토`를 눌러 `preserve` 검증을 다시 수행한다. `AI로 재생성`은 `regenerate`로 위험 구간을 제거하고 다시 작성한다. 원문 보존 경로에서는 내용을 자동으로 조용히 삭제하지 않는다.

Skill 관리 화면은 `POST /skills/author`를 직접 호출하고, 채팅의 일반 “Skill 만들어줘” 요청은 `/agent/turn`의 `skill_authoring` action으로 분류한 뒤 같은 `AuthorSkillUseCase`를 호출한다. 저장 범위를 말하지 않으면 채팅에서 개인/현재 팀 중 하나를 확인한다. 제안은 다음 요청의 `pending_skill_proposal`에 `scope_type`, `name`, `description`, `instructions_markdown`으로 유지한다. 커맨드·범위 변경, AI 재생성, 보안 재검토는 이 제안만 갱신하고, “이대로 게시해줘”에서 같은 내용을 다시 검증한 뒤 게시한다. “방금 방식대로 Skill로 만들어줘”처럼 완료 작업을 재사용하는 요청은 `skill_draft_proposal`로 근거와 권한 상한을 계산한 뒤 같은 `AuthorSkillUseCase`의 미저장 검토 결과로 반환한다.

Router가 `skill_authoring`을 반환해도 현재 사용자 메시지나 진행 중 대화 요약에 새 Skill을 만들거나 생성·정의해 달라는 직접 표현이 없으면 실행하지 않는다. “회의록 Skill을 사용해서 문서를 작성해”는 기존 Skill을 적용하는 문서 작업이며 Skill 생성으로 해석하지 않는다.

#### 6.4.2 새 Skill 수동 생성

수동 생성과 채팅 생성은 capability와 Tool을 직접 받지 않고 같은 `AuthorSkillUseCase`를 사용한다. 자연어 Skill 관리 화면은 다음 입력만 사용한다.

    제목(선택): meeting-notes
    내용: 대화 내용을 정해진 회의록 구조로 작성한다.
    참고 문서(선택): 회의록 예시
    범위: 개인

화면은 `게시`와 `AI로 구체화`를 제공하지만 두 버튼 모두 게시 전 검토로 이동한다. 전자는 원문을 보존하고 후자는 LLM 생성 결과를 사용한다. 검토 화면은 `AI로 재생성`, `보안 재검토`, `최종 게시`를 제공하며 차단 상태에서는 최종 게시할 수 없다.

개인 Skill은 본인만 생성·관리·사용할 수 있다. 팀 Skill은 Workspace owner/editor만 생성·관리하며 Workspace 멤버가 사용할 수 있다.

    사용자:
    [게시]

    시스템:
    `meeting-notes` Skill 제안을 만들었습니다.
    Markdown과 보안 결과를 확인한 뒤 최종 게시해 주세요.

검토 전에는 `skills`와 `skill_versions` row를 만들지 않는다. `POST /skills/author/publish`가 최종 검증을 통과하면 version 1을 `published`로 저장하고 자연어 자동 라우팅을 기본 ON으로 설정한다.

#### 6.4.3 lint와 안전성 검사

저장 또는 preview 전에 시스템은 다음 항목을 검사한다.

- 필수 필드와 slug 형식
- 최소 1개의 라우팅 가능한 capability
- capability와 `allowed_tools`의 호환성
- 중복 slug와 접근 범위
- 상위 정책, 승인 또는 권한 우회를 요구하는 instructions
- capability에서 제공하지 않는 Tool 요청

    시스템:
    안전성 검사를 통과했습니다.
    이 Skill은 planning read Tool과 `create_document`만 사용할 수 있으며 실제 저장에는 plan 승인이 필요합니다.

검사에 실패하면 publish를 막고 수정할 위치와 이유를 표시한다. 예를 들어 instructions에 “승인 없이 문서를 이동한다”가 포함되면 해당 지시는 상위 승인 정책을 바꿀 수 없다고 안내한다.

#### 6.4.4 preview

사용자는 Skill을 저장하거나 publish하기 전에 현재 입력값의 validation과 safety lint 결과를 확인한다. preview는 LLM으로 예시 문서를 생성하거나 실제 폴더 계획을 실행하는 기능이 아니다.

    사용자:
    [Preview]

    시스템 preview:
    차단 문제 없음
    - capability: document-create
    - allowed_tools: list_root_items, list_folder_children, create_document
    - 승인·권한 우회 지시: 없음

`POST /skills/preview`는 입력 정의를 저장하지 않고 `lint_result`와 `has_blocked_issues`를 반환한다. 실제 문서·폴더 조회와 Tool 실행은 하지 않는다. 사용 예시는 publish 후 일반 요청 흐름에서 확인한다.

#### 6.4.5 publish와 활성화

    사용자:
    [Publish]

    시스템:
    `meeting-notes` version 1을 publish했습니다.
    이제 자연어 요청의 auto 후보와 `/meeting-notes` 명시적 호출에 사용할 수 있습니다.

최종 publish는 검토 중인 미저장 proposal을 다시 보안 검사하고, 통과한 내용을 published version으로 저장하면서 같은 transaction에서 해당 version을 `enabled_version_id`로 지정한다. 별도의 enable 동작은 자연어 자동 라우팅이 꺼진 published Skill을 다시 후보로 넣을 때 사용한다.

여러 Skill을 동시에 enabled할 수 있지만 한 요청에는 최대 하나만 적용한다. 비슷한 후보가 여러 개이면 자동으로 임의 선택하지 않고 사용자에게 사용할 Skill을 묻는다.

#### 6.4.6 published Skill 수정

published version을 직접 수정하지 않는다. 사용자가 편집한 내용을 검토하고 보안 검사를 통과하면 새 published version을 만든 뒤 현재 enabled version을 교체한다.

    시스템:
    `meeting-notes` version 2를 게시했습니다.
    이후 요청부터 version 2가 적용됩니다.

이미 시작한 AgentRun은 version 1을 고정해서 사용하며 실행 도중 바뀌지 않는다. disable하면 자연어 자동 라우팅 후보에서 제외하지만 명시적 커맨드와 이미 진행 중인 AgentRun에는 영향을 주지 않는다. 다시 enable하면 마지막 published version을 자연어 후보로 복원한다.

#### 6.4.7 완료 작업에서 Skill proposal 생성

사용자는 현재 채팅에서 완료한 작업을 선택하거나 가장 최근 completed AgentRun을 기준으로 Skill 생성을 요청할 수 있다.

    사용자:
    방금 프로젝트 문서를 정리한 방식대로 Skill로 만들어줘.

    Agent:
    최근 완료된 작업에서 다음 규칙을 추출했습니다.

    이름: project-document-organizer
    capability:
      - folder-organize
    instructions:
      - 프로젝트 이름과 같은 폴더가 없으면 생성한다.
      - 제목이나 내용에서 관련성이 명확한 문서만 이동한다.
      - 회의록은 이동 대상에서 제외한다.
      - 같은 이름의 폴더가 있으면 중복 생성하지 않는다.
    allowed_tools:
      - list_root_items
      - list_folder_children
      - search_hierarchy
      - get_document_metadata
      - create_folder
      - move_document

    실행 당시의 프로젝트 이름, folder ID와 document ID는 Skill에 저장하지 않습니다.
    이 내용으로 Skill을 게시할까요?

LLM은 선택한 run의 승인된 계획, 성공한 Tool 실행과 사용자가 명시적으로 선택한 요청·수정 지시 turn만 입력으로 받는다. 현재 채팅 전체, 실패·취소된 operation, 문서 본문, 전체 prompt, 인증정보와 chain-of-thought는 입력에서 제외한다.

#### 6.4.8 제안 검토와 최종 게시

Skill proposal은 저장되지 않은 구조화된 응답이다. 사용자가 수정하면 보안 상태는 `재검토 필요`가 되고, 보안 재검토를 통과한 뒤에만 최종 게시할 수 있다.

    사용자:
    응, 개인 Skill로 이대로 게시해줘.

    Agent:
    최종 보안 검증을 통과했습니다.
    `project-document-organizer` version 1을 게시했습니다.

proposal 내용이 수정되면 변경된 전체 정의와 보안 결과를 다시 보여준다. 최종 게시에서도 전체 검증, 개인·팀 관리 권한과 범위별 커맨드 중복 검사를 다시 수행한다. 게시 후 자동 라우팅을 꺼도 명시적 `/command` 실행은 유지된다.

Skill은 과거 operation을 그대로 재생하는 매크로가 아니다. `source_agent_run_id`는 생성 근거 감사용으로만 저장하며 새 요청에서는 현재 상태를 read Tool로 다시 조사하고 Skill 규칙에 맞는 새 plan을 만든다.

### 6.5 AgentRun 저장 모델

AgentRun은 다음 테이블로 관리한다.

    agent_runs
    agent_plans
    agent_plan_operations
    agent_approvals
    agent_jobs
    agent_tool_executions
    agent_run_artifacts
    skill_version_sources

AgentRun은 사용자·Workspace, conversation·turn, action, 선택 Skill version, 상태와 현재 plan을 저장한다. Plan은 version, summary, canonical operation hash를 저장한다. Operation은 대상 ID·version·위치·편집 target·artifact 참조·인자·이유·의존 관계를 저장한다. 승인과 Tool 실행은 plan·operation에 연결한다. `skill_version_sources`는 사용자가 선택한 completed AgentRun과 최종 게시된 Skill version을 연결한다.

비동기 `create_document`와 `apply_document_edit`에 필요한 Markdown 또는 edit operation은 `agent_run_artifacts`에 실행용 payload로 분리하고 plan에는 artifact ID와 content hash만 저장한다. artifact는 run actor·Workspace에 결합하고 Tool Gateway 전달 전 hash를 검증한다. terminal run에서 더 이상 필요하지 않으면 감사 데이터와 분리해 정리하며 Skill source로 사용하지 않는다.

문서 본문, 전체 prompt, 인증 token은 AgentRun 감사 데이터에 저장하지 않는다.

### 6.6 비동기 Worker

별도 llmPipeline worker는 PostgreSQL row lock으로 job을 lease한다. Worker가 중단되면 lease 만료 후 다른 worker가 가져가며 동일한 Idempotency-Key로 중복 변경을 방지한다.

- heartbeat: 30초
- lease: 90초
- Worker job 최대 시도: 3회
- retryable operation 재시도: 최대 2회

### 6.7 사용자 권한 경계

    capability 허용 Tool
    ∩ Skill allowed_tools
    ∩ AgentRun 사용자의 현재 권한
    ∩ 승인된 plan operation

llmPipeline은 DB를 직접 변경하지 않는다. Spring backend는 내부 tool 요청마다 service 인증, AgentRun·operation, 승인된 plan version·hash, Workspace, 실행 사용자, 현재 멤버십·리소스 권한, 대상 version과 tool 허용 여부를 검사한다.

Backend→llmPipeline Agent·Skill 요청과 llmPipeline Worker→Backend tool 요청은 모두
`X-Agent-Service-Token`에 `AGENT_INTERNAL_TOKEN`을 전달해 service를 인증한다. 이 token은
사용자 권한을 대신하지 않으며 양쪽 모두 요청의 사용자·Workspace 권한을 별도로 검증한다.

실제 변경은 기존 FolderService, DocumentService, DocumentPlacementService와 문서 본문 편집 경계를 사용한다. Agent 경로는 기존 권한, version, idempotency, hierarchy와 편집 target 검증을 우회할 수 없다. 계획 후 권한이 회수되면 해당 operation은 forbidden이 된다.

### 6.8 계획·승인·실행

사용자는 operation JSON을 직접 편집하지 않고 자연어로 계획 수정을 요청한다. 수정은 같은 AgentRun에 새 plan version을 만들고 기존 승인을 무효화한다. Markdown 생성기와 편집기는 저장 전 초안·편집안을 만들 수 있지만, Worker는 승인된 `create_document` 또는 `apply_document_edit` operation을 통해서만 결과를 영속화한다.

Worker는 최근 실행 결과를 관찰한 뒤 LLM이 다음 read 또는 실행 가능한 승인 operation 하나를 선택하는 bounded ReAct loop를 수행한다. 상태 변경 tool과 인자는 승인된 plan에서만 가져오며 남은 mutation의 Tool 호출 예산을 우선 보존한다. 실패한 operation의 의존 작업은 skipped로 처리하고 독립 작업은 계속한다. 계획 변경이 필요하면 제한된 사유 코드와 함께 clarification_required로 중단하며 새 plan version과 hash를 다시 승인받는다. 남은 operation이 없으면 LLM 호출 없이 검증 단계로 전환한다. 실행 후 관련 상태를 재조회하며 자동 rollback과 자동 복구는 수행하지 않는다.

### 6.9 API

Frontend는 Spring backend만 호출한다.

    POST /api/workspaces/{workspace_id}/agent/turn

    GET  /api/workspaces/{workspace_id}/agent/runs/{run_id}
    POST /api/workspaces/{workspace_id}/agent/runs/{run_id}/approve
    POST /api/workspaces/{workspace_id}/agent/runs/{run_id}/reject
    POST /api/workspaces/{workspace_id}/agent/runs/{run_id}/cancel
    POST /api/workspaces/{workspace_id}/agent/runs/{run_id}/revise

    POST  /api/workspaces/{workspace_id}/skills/preview
    POST  /api/workspaces/{workspace_id}/skills/author
    POST  /api/workspaces/{workspace_id}/skills/author/publish
    GET   /api/workspaces/{workspace_id}/skills
    GET   /api/workspaces/{workspace_id}/skills/{skill_id}
    PATCH /api/workspaces/{workspace_id}/skills/{skill_id}
    POST  /api/workspaces/{workspace_id}/skills/{skill_id}/enable
    POST  /api/workspaces/{workspace_id}/skills/{skill_id}/disable

    POST  /api/workspaces/{workspace_id}/skills/draft-from-runs/preview

### 6.10 UI, 보관, 배포

계획과 승인은 채팅 카드로 제공한다. Frontend는 종료될 때까지 2초 간격으로 AgentRun을 조회하며 화면을 다시 열어도 run_id로 복원한다.

종료된 AgentRun 기록은 90일 보관하고 하루 한 번 정리한다. 종료되지 않은 AgentRun에는 만료를 적용하지 않는다.

기능은 Workspace별 rollout 없이 한 번에 배포한다. AGENT_SKILLS_ENABLED=false는 신규 Skill 선택과 AgentRun 생성을 차단하되 기존 query와 상태를 변경하지 않는 Markdown 초안·편집안 생성은 유지한다.

### 6.11 주요 설계 결정

#### DEC-001 Tool-first Workspace 상태 경계

- 결정: query와 상태를 변경하지 않는 Markdown 초안·편집안 생성은 기존 UseCase를 유지하고, Workspace 상태 조회는 read Tool, 모든 영속 변경은 승인된 mutation Tool을 사용하는 AgentRun으로 실행한다.
- 이유: LLM 생성 자체와 권한·version·감사가 필요한 실제 변경을 분리하면서 모든 재사용 가능한 작업을 동일한 Tool 실행 기록으로 남긴다.
- 대안: 문서 생성·편집은 direct 경로로 영속화하고 폴더 정리만 Tool로 실행하거나, 모든 reasoning과 생성까지 Tool로 감싼다.
- 영향: `workspace_workflow`, 문서 read/mutation Tool과 기존 Markdown 결과를 AgentRun plan에 연결하는 계약이 필요하다.

#### DEC-002 명시적 승인과 plan hash

- 결정: 상태 변경은 plan version과 operation hash 승인을 요구한다.
- 이유: 사용자가 본 계획과 실제 실행의 일치를 보장한다.
- 대안: 대화 내용만으로 승인한다.
- 영향: 승인 저장 모델과 API가 필요하다.

#### DEC-003 업무 단위 Tool

- 결정: folder/document 업무 단위 tool만 제공한다.
- 이유: 기존 Backend 권한과 도메인 검증을 재사용한다.
- 대안: shell, SQL, 범용 HTTP tool을 제공한다.
- 영향: 새 작업마다 tool 계약이 필요하다.

#### DEC-004 여러 enabled Skill

- 결정: 여러 Skill을 enabled하고 요청마다 최대 하나를 선택한다.
- 이유: 작업 절차를 독립적으로 재사용한다.
- 대안: 하나의 전역 Schema에 모든 규칙을 합친다.
- 영향: selector와 version 관리가 필요하다.

#### DEC-005 사용자 권한을 넘지 않는 Agent

- 결정: Agent는 실행 사용자가 현재 수행할 수 있는 작업만 실행한다.
- 이유: Skill과 Agent가 권한 확대 수단이 되어서는 안 된다.
- 대안: Agent service account의 독립 권한으로 실행한다.
- 영향: 계획과 실행 시점에 권한을 각각 확인한다.

#### DEC-006 Schema와 Skill 분리

- 결정: Wiki Schema는 기본 설정, Skill은 요청별 작업 절차로 유지한다.
- 이유: 전역 설정과 선택형 지침의 역할이 다르다.
- 대안: 기존 Schema를 Skill로 migration한다.
- 영향: UI에서 두 개념을 구분해야 한다.

#### DEC-007 PostgreSQL 기반 비동기 Worker

- 결정: DB job과 별도 llmPipeline worker로 AgentRun을 실행한다.
- 이유: HTTP·API 프로세스 수명과 독립적으로 복구한다.
- 대안: 동기 HTTP 또는 FastAPI BackgroundTasks.
- 영향: lease, heartbeat, worker 배포가 필요하다.

#### DEC-008 일괄 배포와 Kill Switch

- 결정: 한 번에 배포하되 kill switch를 제공한다.
- 이유: 장애 시 신규 Agent 실행을 차단한다.
- 대안: Workspace별 단계적 rollout.
- 영향: 배포 전 전체 경로 검증이 필요하다.

#### DEC-009 승인 경계 안의 bounded ReAct 실행

- 결정: 승인 후에는 LLM이 관찰 결과를 바탕으로 다음 read 또는 실행 가능한 승인 operation 하나를 선택한다.
- 이유: 계획의 목표와 승인 경계를 유지하면서 실행 결과에 따라 다음 행동을 조정한다.
- 대안: 승인 후 operation 순서를 코드가 고정 실행하거나 LLM이 새 mutation을 자유롭게 생성한다.
- 영향: 독립 operation 병렬 실행을 포기하며, 계획 변경 시 중단 후 새 version과 hash를 재승인해야 한다.

#### DEC-010 완료 작업에서 Skill 규칙 추출

- 결정: 사용자가 선택한 같은 채팅의 completed AgentRun과 성공 Tool 실행을 일반화해 저장 전 Skill proposal을 만들고, 검토·보안 재검토 뒤 최종 게시를 확인받는다.
- 이유: 실제로 검증된 작업 방식과 사용자 수정 조건을 재사용하면서 일회성 ID를 고정한 매크로 생성을 막는다.
- 대안: 전체 채팅 원문을 자동 학습하거나 Tool 호출을 그대로 재생하는 workflow macro를 저장한다.
- 영향: AgentRun에 conversation·turn 연결, `skill_version_sources`, 구조화된 proposal 계약과 source redaction이 필요하다.

## 7. 작업 계획

구현 작업은 docs/spec/sdd/tasks/agent-skills-and-folder-organization-tasks.md에서 관리한다.

## 8. 검증

| 요구사항 | 자동 검증 | 수동 검증 | 결과 |
|---|---|---|---|
| REQ-001 | 호출 모드·명시적 오류 계약 | slash command와 off UI | Pending |
| REQ-002 | 자동 선택·모호성·재선택 | 후보 선택 흐름 | Pending |
| REQ-003 | capability·우선순위·안전성 | Schema와 Skill 동시 적용 | Pending |
| REQ-004 | 계획 제한·hash·의존 관계 | 계획·예상 트리 | Pending |
| REQ-005 | 미승인 차단·재승인·자연어 승인 | 승인·수정·취소 UI | Pending |
| REQ-006 | ReAct 선택 경계·멱등성·재시도·충돌 | 관찰 기반 다음 행동·부분 실패 | Pending |
| REQ-007 | 재조회·검증 실패 | 실행 전후 트리 | Pending |
| REQ-008 | lease·heartbeat·worker 복구 | Worker 강제 종료 | Pending |
| REQ-009 | 기존 /agent/turn 회귀 | 기존 질문·생성·편집 | Pending |
| REQ-010 | read/mutation Tool 경계·문서 version | 권한별 문서 저장·편집 승인 | Pending |
| REQ-011 | 완료 run 일반화·민감값 제거·저장 확인 | 채팅에서 Skill proposal 확인·publish | Pending |

### 실행 명령

    cd llmPipeline
    .venv/bin/python -m pytest -q tests

    cd backend
    ./gradlew test
    ./gradlew flywayValidate

    cd frontend
    npm run lint
    npm exec tsc -- --noEmit --incremental false
    npm run test:markdown
    npm run test:user-preferences
    npm run build

    git diff --check

### 수동 검증

- [ ] 개인·팀 Skill의 관리·사용 권한을 확인한다.
- [ ] 자연어, 명시적 Skill, off 모드를 확인한다.
- [ ] 모호한 Skill 후보 선택 후 요청이 재개된다.
- [ ] 계획·승인 전에는 상태가 변경되지 않는다.
- [ ] 버튼과 자연어 승인, 계획 수정·재승인을 확인한다.
- [ ] 관찰 기반 다음 행동, 의존 순서, 부분 실패, 취소를 확인한다.
- [ ] 권한 회수와 version 충돌이 안전하게 차단된다.
- [ ] 실행 결과와 최종 폴더 트리를 확인한다.
- [ ] Worker 중단 후 job이 복구되고 중복 변경이 없다.
- [ ] kill switch 상태에서 기존 기능 회귀가 없다.
- [ ] 감사 로그에 본문, 전체 prompt, token이 남지 않는다.
- [ ] 문서 초안·편집안은 승인 전 영속 상태를 변경하지 않는다.
- [ ] 문서 저장·본문 반영은 승인된 Tool과 `base_version`으로만 실행된다.
- [ ] 같은 채팅의 완료 작업에서 고정 ID가 제거된 Skill proposal을 만든다.
- [ ] proposal 확인 전 draft가 저장되지 않고 publish를 별도로 확인한다.

## 9. 미결정 사항

- [ ] Frontend Agent Skill·AgentRun 단위 테스트 package script 이름
- [ ] `agent_run_artifacts` 실행 payload의 암호화 방식과 terminal/orphan 정리 TTL

## 10. 결과

- 검증일: 2026-08-03
- 최종 상태: 폴더 정리 llmPipeline 자동 검증 완료, Tool-first 문서 작업·완료 작업 기반 Skill 생성과 Backend·Frontend 통합 Pending
- 자동 검증: llmPipeline `680 passed, 49 subtests passed`, Python 구문 검사와 `git diff --check` 통과
- 남은 문제: 문서 read/mutation Tool, `workspace_workflow`, Skill proposal 생성, Backend migration·양방향 service 인증·Tool Gateway와 Frontend UI/E2E
- 후속 작업:
  1. 요구사항 테스트부터 작성한다.
  2. 작업 계획 순서대로 구현한다.
  3. 요구사항별 자동·수동 검증을 실행한다.
  4. 검증 결과를 기록하고 상태를 Verified로 변경한다.
