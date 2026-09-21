# 문서 본문을 전송하는 API의 WAF 정책

문서 저장은 `PUT /documents/{document_id}/content`의 multipart 요청이다. JSON 저장으로 가정하면 예외가 적용되지 않는다. 파일 업로드 외에도 Markdown 생성·AI 편집·질의·위키 스키마·Skill API가 임의의 문서 본문을 받는다. 특히 AI 편집은 일부 문단만 선택해도 `editorSnapshot.markdown`에 전체 문서를 담는다.

## 예외 범위

실제 경로는 `/api/workspaces/ws_[0-9a-f]{32}/`로 시작한다. [요청 조건 목록](../infra/waf/document-content-contracts.json)이 Terraform과 테스트의 입력이다.

| 메서드 | 경로(워크스페이스 접두사 생략) | Content-Type |
|---|---|---|
| POST | `documents` | multipart/form-data + boundary |
| PUT | `documents/doc_[0-9a-f]{32}/content` | multipart/form-data + boundary |
| POST | `documents/markdown` | application/json |
| POST | `agent/turn` | application/json |
| POST | `chat/sessions/session_[0-9a-f]{32}/query`, `/query/runs` | application/json |
| POST | `wiki-schema/preview`, `wiki-schema/drafts` | application/json |
| POST | `skills/author`, `skills/author/publish` | application/json |
| PATCH | `skills/{UUID}` | application/json |

JSON은 선택적인 charset 파라미터를 허용한다. 잘못된 ID·다른 메서드·다른 Content-Type·추가 경로는 예외가 아니다. 이름 변경·삭제·복원·ingest·AI 승인 API는 문서 본문을 받지 않으므로 예외에 포함하지 않는다.

## 평가 순서

1. 긴급 차단이 활성화됐으면 먼저 차단한다.
2. 정확한 요청 조건에 일치하면 Count로 `fruition:document-content` 라벨만 붙인다.
3. 기존 관리형 규칙 4개를 평가한다. CommonRuleSet의 `SizeRestrictions_BODY`, `GenericLFI_BODY`, `CrossSiteScripting_BODY`와 SQLiRuleSet의 `SQLi_BODY`만 Count로 전환한다.
4. 위 네 규칙의 라벨이 있지만 문서 요청 라벨이 없으면 `document-content-body-guard`가 차단한다. 같은 WebACL의 라벨은 `fruition:document-content`라는 로컬 이름으로 참조한다.
5. 기존 IP별·전체 요청량 제한을 평가한다.

종료 동작인 Allow를 추가하지 않는다. URI·쿼리·쿠키·헤더 검사, IP 평판, KnownBadInputs와 기타 본문 규칙, 서버 인증·인가 및 파일 검증은 계속 적용된다. 예외는 요청 전체의 모든 공격 검사를 끄는 기능이 아니다. 검색 API의 쿼리 검사도 유지한다.

## 검사 한계와 서버 역할

ALB WAF는 본문의 첫 8KB만 검사한다. 이 정책은 큰 문서를 WAF에서 전부 검사하거나 5MB 상한을 설정하는 정책이 아니다. Markdown의 서버 한도는 5MiB이며, 이미지 저장 검증은 파일당 10MiB·총 파일 100MiB 제한을 둔다. AI·JSON API의 전체 요청 크기 제한은 이 인프라 변경으로 추가하지 않는다.

예외 경로의 SQL·HTML·경로 문자열은 문서 데이터로 취급한다. 실제 SQL 파라미터 처리, Markdown/HTML 렌더링과 첨부파일 검증은 애플리케이션에서 책임진다. 다른 관리형 규칙이 정상 내용을 차단하면 해당 로그를 근거로 개별 검토한다.

## 재검증

```bash
python3 -m unittest scripts.tests.test_aws_waf_content -v
python3 scripts/aws_waf_content_probe.py \
  --base-url https://api.example.com \
  --output /tmp/waf-content-probe.json
```

프로브는 0으로 채운 합성 ID, 인증 없는 요청, 합성 Markdown만 사용한다. 문서를 변경하거나 AI 작업을 시작하지 않는다. 11개 API 경로에 크기·LFI·XSS·SQLi 예문을 보내는 44개 요청과, 예외에 포함되면 안 되는 13개 요청을 보낸다.

- 예외 요청의 기대 결과는 **401**: WAF를 통과해 서버 인증에서 거부됨.
- 차단 유지 요청의 기대 결과는 **403**: WAF 로그의 `BLOCK`과 차단 규칙을 추가로 대조한다.
- 로그의 `x-fruition-waf-probe` 헤더와 결과 파일 `run_id`로 해당 실행만 찾는다. SQLi 등의 예문이 실제 관리형 라벨을 발생시켰는지도 확인한다. 403 상태만으로 WAF 차단을 확정하지 않는다.
- 프런트엔드 주소로 호출하면 별도의 접근 코드 게이트가 먼저 403을 반환할 수 있다. 이것은 WAF 검증 성공이나 WAF 회귀의 증거가 아니다. 프로브는 API 직접 주소로 수행하며, 로그인 후 실제 저장은 별도 업무 검증이다.

운영 적용 시 Terraform 계획에서 `aws_wafv2_web_acl.cost_guard` 한 리소스의 변경만 확인한다. 다른 기능의 미병합 Terraform 코드가 있는 경우 전체 apply로 관련 리소스를 제거하지 않도록 검토한 WAF 대상 계획을 사용한다.

## 2026-09-21 검증 결과

- Terraform 검증과 AWS 테스트 92개(요청 조건 테스트 6개 포함)를 통과했다.
- 운영 WAF 한 리소스만 수정했다. 적용 후 조회한 용량은 1,210 WCU다.
- 운영 API 합성 요청 57개가 통과했다: 예외 요청 44개는 401, 차단 유지 요청 13개는 403이었다.
- 동일 실행의 WAF 로그 57개를 대조해 ALLOW 44개·BLOCK 13개를 확인했다. ALLOW 요청마다 해당 관리형 본문 검사 라벨과 문서 요청 라벨이 모두 존재했다. SQLi를 포함해 검사를 실제로 유발한 요청에만 예외가 적용됐음을 확인했다.
- 프런트 경유 비인증 요청은 별도의 접근 코드 게이트에서 403을 반환했다. 해당 결과를 WAF 회귀로 처리하거나 게이트를 해제하지 않았다.
- 로그인한 사용자의 문서 생성·저장·재조회와 AI 실행까지 포함한 업무 검증은 수행하지 않았다. 테스트는 사용자 문서를 변경하지 않았다.

근거: [AWS 기본 규칙](https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-baseline.html), [SQLi 규칙](https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-use-case.html), [ALB 본문 검사 제한](https://docs.aws.amazon.com/waf/latest/APIReference/API_Body.html), [로컬 라벨 참조](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-label-match-examples.html).
