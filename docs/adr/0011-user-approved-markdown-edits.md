# 0011. Apply Markdown Agent Edits Only after User Approval

## Status
Implemented

## Context
LLM이 생성한 Markdown은 사용자의 의도와 다르거나 원문 구조를 손상할 수 있다. 생성 직후 원본 문서에 저장하면 사용자가 변경 내용을 확인하거나 거부할 기회가 없다.

## Decision
Markdown Agent는 문서를 직접 저장하지 않고 적용 가능한 edit proposal을 반환하며, 사용자가 preview와 diff를 확인하고 수락한 경우에만 문서에 반영한다.

## Alternatives Considered
- Agent 결과를 원본 문서에 즉시 저장: 잘못된 변경을 사용자가 확인하기 전에 반영하므로 기각했다.
- 수정된 전체 문서만 반환: 변경 범위와 적용 여부를 명시하기 어려워 target을 포함한 edit operation을 선택했다.

## Consequences/Tradeoffs
### Positive
- 사용자가 변경 범위와 결과를 확인하고 적용·취소·재생성을 선택할 수 있다.
- Agent 생성과 실제 문서 저장의 책임을 분리할 수 있다.

### Negative
- preview, diff와 적용 상태를 Frontend가 관리해야 한다.
- 제안 생성 이후 문서가 바뀌면 적용 전에 version 충돌을 확인해야 한다.
