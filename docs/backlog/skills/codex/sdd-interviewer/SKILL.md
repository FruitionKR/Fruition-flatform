---
name: sdd-interviewer
description: Interview the user to turn an incomplete or abstract feature idea into a concrete, reviewable single-document SDD under docs/spec/sdd. Use when the user asks to create, draft, complete, refine, or review an SDD, specification, feature design, acceptance criteria, implementation plan, or verification plan through guided questions and explicit section-by-section confirmation.
---

# SDD Interviewer

Build an SDD through a staged Korean interview. Convert vague answers into observable behavior, explicit boundaries, decisions, tasks, and verification criteria. Never invent unresolved facts.

## Ground Rules

- Write every user-facing question, draft, and explanation in Korean.
- Read `AGENTS.md` and `docs/spec/sdd/TEMPLATE.md` before starting.
- Treat the template as the required document structure unless the user approves a deviation.
- Ask 3–5 related questions at a time. Do not present the entire interview at once.
- Prefer questions the user can answer from product intent. Inspect the repository for discoverable technical facts instead of asking the user to find them.
- State assumptions and distinguish confirmed facts, proposals, and open questions.
- Do not modify or create a file until the repository approval rules are satisfied.

## Workflow

### 1. Establish the Subject

Ask for:

- the feature or problem in one sentence;
- the primary actor;
- the current behavior or failure sequence;
- the observable outcome that means the work succeeded;
- any known exclusions.

If the user has already supplied an answer, reuse it and ask only for missing information.

### 2. Clarify Background, Goal, and Scope

Turn abstract answers into concrete statements by asking:

- Who encounters the problem, and during which action?
- What happens now, and what should happen instead?
- How often or under which conditions does it happen?
- What user-visible or system-visible result proves success?
- Which adjacent behaviors must remain unchanged?

Draft sections 1–4 of the template. Label assumptions and open questions. Ask the user to approve or correct the exact draft before continuing.

### 3. Define Requirements

Create one independently testable requirement per behavior. Assign stable IDs such as `REQ-001`.

For each requirement, establish:

- actor and precondition;
- triggering input or action;
- observable output or state change;
- invalid, empty, duplicate, unauthorized, timeout, and partial-failure behavior when relevant;
- measurable limits such as duration, size, count, ordering, or compatibility;
- Given/When/Then acceptance criteria.

Do not accept words such as “빠르게”, “적절히”, “안정적으로”, or “사용하기 쉽게” without asking how they will be measured or observed. Draft section 5 and obtain explicit confirmation.

### 4. Develop the Design

Inspect relevant repository code and documents when the design depends on the current implementation. Summarize evidence before proposing changes.

Clarify:

- components and responsibilities that change;
- request, response, event, and data contracts;
- validation and failure handling;
- state transitions and persistence;
- compatibility, migration, deployment, security, and observability impacts;
- alternatives considered and why one option is preferred.

Use `DEC-001` identifiers for material decisions. Present tradeoffs rather than silently selecting among materially different interpretations. Draft section 6 and obtain explicit confirmation.

### 5. Produce the Work Plan

Create small tasks with `TASK-001` identifiers. Link every task to one or more requirement IDs. For each task, specify the likely change target and an observable completion check.

Order tasks so that a failing test or reproducible check precedes implementation when practical. Do not add speculative refactoring or unrelated cleanup. Draft section 7 and obtain explicit confirmation.

Store the confirmed work plan separately under `docs/spec/sdd/tasks/<feature>-tasks.md`. Keep requirements and design in the feature SDD under `docs/spec/sdd/<feature>.md`.

### 6. Define Verification

Map every requirement to at least one automated or manual verification method. Include exact commands only after confirming they exist in the repository. Cover normal behavior, relevant failure cases, and regression risk.

Keep outcomes `Pending` until checks have actually run. Draft sections 8–10 and obtain explicit confirmation.

### 7. Assemble and Write

Assemble only confirmed text into the template. Preserve unresolved items in `미결정 사항`; do not guess.

Before writing:

1. Propose lowercase hyphenated paths such as `docs/spec/sdd/user-login.md` and `docs/spec/sdd/tasks/user-login-tasks.md`.
2. Summarize every feature SDD and task file to create or modify, the reason, and the impact scope.
3. Request explicit user approval.

After approval, create or update only the approved feature SDD and task files. Re-read them, run `git diff --check`, and report the file paths plus any remaining open questions. Do not implement the described product changes unless separately requested and approved.

## Confirmation Format

Use this compact format after each stage:

```md
## 문서 반영 초안

[exact proposed section text]

확인해 주세요.
- 이 내용 그대로 확정할까요?
- 수정할 문장이 있다면 원하는 표현이나 사실을 알려주세요.
```

Treat short approvals such as “응”, “확정”, or “그대로 진행” as confirmation of the presented draft only. If the user corrects part of it, revise the draft and request confirmation again.
