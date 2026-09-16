# 0012. Restore AI Changes Using Operation and Contribution History

## Status
Implemented

## Context
Concept Page는 여러 Source의 기여를 합친 결과다. 특정 Ingest를 과거 Page snapshot으로 덮어쓰면 이후 추가된 다른 Source의 정상 기여까지 제거될 수 있다.

## Decision
AI 변경은 append-only operation·Page revision·Source contribution 이력을 남기고, 복구 시 대상 contribution만 제외한 상태로 Page를 복원하거나 재조립한다.

## Alternatives Considered
- 완성된 Markdown에서 해당 작업 부분만 제거: 어떤 문장이 어느 Source에서 왔는지 안정적으로 구분할 수 없어 기각했다.
- 과거 Page snapshot으로 전체 복원: 이후 반영된 다른 Source contribution까지 제거할 수 있어 기각했다.
- Page와 이력 hard delete: 복구 감사 이력이 사라지므로 soft delete와 append revision을 선택했다.

## Consequences/Tradeoffs
### Positive
- 취소 대상이 아닌 Source contribution을 유지할 수 있다.
- 복구 자체도 새 operation과 revision으로 기록할 수 있다.

### Negative
- Ingest 시점부터 Source별 contribution을 보존해야 한다.
- 남은 contribution 조합의 snapshot이 없으면 Concept Page를 다시 조립해야 한다.
- 비동기 복구 중 상태가 바뀌지 않았는지 revision과 contribution hash를 검증해야 한다.

## Follow-up
오래된 operation, revision, contribution과 object의 보존 정책을 정한다.
