# ADR-0024: converter 전용 최소 권한 DB 계정

상태: 승인됨. 결정 출처는 Fruition-flatform#69(PR #75)와 Fruition-ai#81이다.

## 맥락

converter는 사용자가 올린 신뢰할 수 없는 PDF를 파싱한다. selective repair의 공급사 호출을 사용량 원장(ai_db)에 기록하려면 DB 접근이 필요하다. 기존 `ai_runtime` 계정을 쓰면 converter가 침해될 때 AI 전체 테이블을 읽고 쓸 수 있다.

## 결정

전용 `ai_converter` role을 둔다.

- 인프라 init 스크립트는 role 생성과 `CONNECT`·`USAGE`까지만 맡는다.
- 테이블 권한은 AI 스키마 bootstrap이 `AI_DB_CONVERTER_ROLE` 값으로 부여한다: 호출 시작 `INSERT`, 완료 기록은 `finish_call` 컬럼에 한정한 `UPDATE`, `SELECT(id, status, finished_at)`.
- 배포 preflight가 converter 계정으로 접속과 권한을 확인한다.

## 대안과 기각 사유

- `ai_runtime` 재사용: converter가 신뢰할 수 없는 PDF를 처리하므로 침해 시 영향 범위가 AI 전체가 된다.
- 권한을 인프라 init에서만 부여: 새 환경에서는 테이블이 AI 스키마 bootstrap 뒤에 생겨 순서 문제가 생긴다.
- 양쪽에 고정 role 이름: 인프라와 AI 코드가 이름으로 결합한다. env로 받는다.

## 결과

- converter 침해 시 영향은 원장 행 추가·완료 기록으로 제한된다.
- 남는 위험: `SELECT(id, status, finished_at)`와 UPDATE 때문에 행 접근은 가능하며 다른 행의 토큰 값 변경을 막으려면 행 수준 보안(RLS)이 필요하다.
