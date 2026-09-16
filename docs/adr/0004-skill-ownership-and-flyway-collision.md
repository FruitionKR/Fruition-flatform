# ADR-0004: Skill 저장소 소유권 이전과 dev↔dev-msa Flyway 번호 충돌

- 상태: 채택 (Skill 소유권 이전) / 미해결 과제 기록 (Flyway 번호 충돌)
- 관련: [ADR-0001](0001-choose-primary-database.md), [data-model.md](../data-model.md), `Document/src/main/resources/db/migration/V25__add_agent_skill_and_langgraph_schema.sql`

## 맥락

`dev`(모놀리스)와 `dev-msa`(MSA 전환)가 병렬로 진행되면서 두 갈래로 갈라진 것이 두 가지 있다.

1. **Skill 소유권**: 두 브랜치의 분기점(`f9c4ee63`)에는 Skill 기능이 아직 없었고, 이후 양쪽이 같은 기능을 각각 구현했다. `dev`는 Java `fruition.skill` 패키지(26개 클래스)가 `skills`·`skill_versions`를 소유하도록 만들고 `V20__add_skills.sql`·`V21__make_personal_skills_global.sql`로 스키마를 세웠다. MSA 전환 라인은 같은 기능을 Python pipeline에 구현했고 테이블 DDL만 document-svc Flyway(`V25`)에 두었다. 즉 한쪽이 다른 쪽을 지운 것이 아니라 두 구현이 병렬로 존재하며, 통합 시 어느 쪽을 남길지 정해야 한다.
2. **Flyway 번호 충돌**: dev의 `V18`~`V21`과 document-svc의 `V18`~`V21`이 번호는 같은데 내용이 완전히 다르다. 추가로 `V1`·`V3`·`V4`·`V7`·`V9`·`V10`·`V11`·`V14`·`V15`는 파일명이 같은데 내용이 다르다(access 테이블·크로스 DB FK 제거분).

| V | dev | document-svc |
|---|---|---|
| V18 | `add_document_assets` | `readd_wiki_page_status_check_not_valid` |
| V19 | `add_document_asset_orphans` | `validate_wiki_page_status_check` |
| V20 | `add_skills` | `add_workspace_id_to_link_tables` |
| V21 | `make_personal_skills_global` | `add_document_convert_queue` |

## 결정

1. **Skill 테이블 소유권은 Python pipeline 구현을 채택한다.** DDL 생성만 document-svc Flyway가 담당하고(운영 중 pipeline은 DDL을 실행하지 않는다), 읽기·쓰기는 `AI/pipeline/app/modules/skill/`이 전담한다. 통합 시 `dev`의 Java `fruition.skill` 구현은 가져오지 않는다.
2. **컬럼명은 dev 이름을 따른다.** 재설계 과정에서 바뀌었던 `skills.slug` → `skills.command`, `skill_versions.lint_result` → `skill_versions.safety_result`로 되돌렸다(인덱스 `uq_skills_personal_command`·`uq_skills_team_command` 포함). 컬럼 구성 차이(`status`·`enabled_version_id`·`published_at` 추가, `auto_routing_enabled`·`deleted_at`·`created_by`·`reference_documents`·`definition_hash` 제거, jsonb → text[])는 소유권 이전에 따른 재설계 결과이므로 유지한다.
3. **Flyway 번호 충돌은 이번 전환 범위에서 해결하지 않는다.** `dev`를 `dev-msa`에 병합하는 시점에 document-svc 마이그레이션 재번호매김 또는 MSA 전용 baseline 압축으로 단독 처리한다.

## 대안과 기각 사유

- **`dev`의 Java 구현을 채택**: Agent 실행 루프·LangGraph checkpoint가 전부 Python에 있어 Skill만 Java에 두면 매 실행마다 서비스 왕복이 생긴다. 기각.
- **Python 도메인 필드와 HTTP 스키마까지 `command`/`safety_result`로 개명**: pipeline `/skills/*`의 외부 계약이 바뀐다. DB 컬럼명만 맞추고, 저장소가 dict key를 읽는 지점만 컬럼명에 맞췄다.
- **지금 Flyway 재번호매김**: MSA 전환 PR 범위를 넘고, 두 브랜치가 아직 각자 진행 중이라 병합 시점에 또 어긋난다. 병합 시점 단독 작업으로 미룬다.

## 결과

- `skills`/`skill_versions` 컬럼명이 dev와 일치한다 — 병합 시 컬럼 레벨 충돌 없음.
- **주의**: `V25`는 `CREATE TABLE IF NOT EXISTS`다. dev의 `V20`을 이미 적용한 DB에서는 dev 모양 테이블이 남아 skip되고, Python이 `status`·`enabled_version_id` 컬럼을 참조하다 런타임에 실패한다. dev 스키마가 적용된 DB에 MSA를 올릴 때는 `skills`·`skill_versions`를 먼저 드롭해야 한다.
- Flyway 체크섬 불일치는 병합 시점까지 남아 있는 알려진 부채다.
