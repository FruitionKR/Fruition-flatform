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
| POST | `skills/test-run` | application/json |
| POST | `meetings/mtg_[0-9a-f]{32}/notes/{숫자 버전}/apply` | application/json |
| POST | `speech/transcriptions` | `audio/wav`·`audio/mpeg`·`audio/mp4`·`audio/webm` + 선택 파라미터(`;codecs=opus` 등) |
| PUT | `icon/image` | multipart/form-data + boundary |

업로드 경로 중 워크스페이스 접두사가 없는 것도 같은 방식이다.

| 메서드 | 경로 | Content-Type | 서비스 |
|---|---|---|---|
| PUT | `/api/auth/me/avatar` | multipart/form-data + boundary | access |

2026-11-11 추가 근거:

- 채팅 음성 입력(`useDictation`)은 녹음 Blob을 그대로 본문으로 보낸다. Chrome·Firefox는 `audio/webm;codecs=opus`, Safari는 `audio/mp4`다. 2026-11-05 운영 WAF 로그에 `fruition.wiki`의 이 요청 3건이 `SizeRestrictions_Body`로 `document-content-body-guard`에 차단됐다. 서버(`SpeechController`)는 type/subtype만 비교해 위 네 형식만 받고 24MiB에서 413이다.
- 워크스페이스 아이콘·프로필 사진은 access가 `@RequestPart("file")` multipart로 받고 1MiB에서 413이다. 8KB를 넘는 이미지는 모두 본문 크기 규칙에 걸린다.
- 회의록 문서 저장(`notes/{version}/apply`)과 Skill 테스트 실행(`skills/test-run`)은 회의록·문서 Markdown 전체를 JSON에 담는다. 로그상 차단 기록은 아직 없지만 같은 종류라 함께 넣었다.
- 회의 녹음 파일과 PDF 직접 업로드는 바이트를 presigned S3 URL로 보내므로 WAF를 지나지 않는다. 그 제어 요청은 작은 JSON이다.

MCP 서버 요청도 같은 방식으로 예외에 넣는다. 워크스페이스 접두사가 없는 정확한 경로다.

| 메서드 | 경로 | Content-Type |
|---|---|---|
| POST | `/mcp` | application/json |

MCP 도구 호출(위키 원문 window 제출, 문서 수정 제안 등)은 문서 원문을 JSON-RPC 본문에 담아 8KB를 넘는다. 기존 계약에 호스트 조건이 없으므로 이 계약도 호스트를 묻지 않는다. `/mcp`는 화면 호스트와 `api.` 호스트 모두 document로 가고, document는 화면 호스트가 아닌 요청을 400(`CANONICAL_ENDPOINT_REQUIRED`)으로 거절한다. `/mcp/*` 승인 화면, `/api/mcp-endpoint`, MCP OAuth(access의 `/oauth2/token`·`/oauth2/authorize`·`/.well-known/oauth-authorization-server`)는 본문 예외가 아니다. 토큰·인가 요청은 작은 form/JSON이라 기본 8KB 검사 안에 든다. loopback `redirect_uri`만 [별도 예외](#mcp-oauth-loopback-redirect_uri-예외)로 다룬다. access에는 동적 클라이언트 등록(registration) 경로가 없다. 클라이언트 metadata(CIMD)는 access가 밖으로 받아오므로 들어오는 본문이 아니다.

JSON은 선택적인 charset 파라미터를 허용한다. 잘못된 ID·다른 메서드·다른 Content-Type·추가 경로는 예외가 아니다. 이름 변경·삭제·복원·ingest·AI 승인 API는 문서 본문을 받지 않으므로 예외에 포함하지 않는다.

## 평가 순서

1. 긴급 차단이 활성화됐으면 먼저 차단한다.
2. 정확한 요청 조건에 일치하면 Count로 `fruition:document-content` 라벨만 붙인다. 이어서 `not-public-paths`가 디코딩한 `/internal`·`/swagger-ui`·`/v3/api-docs` 경로를, `sensitive-file-paths`가 `.git`·`.env` 등 민감 파일 경로를 404로 차단한다. 본문 예외는 URI 차단을 면제하지 않는다.
3. 기존 관리형 규칙 4개를 평가한다. CommonRuleSet의 `SizeRestrictions_BODY`, `GenericLFI_BODY`, `CrossSiteScripting_BODY`와 SQLiRuleSet의 `SQLi_BODY`, `SQLiExtendedPatterns_BODY`만 Count로 전환한다. OAuth 예외용으로 CommonRuleSet의 `GenericRFI_*`·`EC2MetaDataSSRF_*` 쿼리 인자·본문 규칙 4개도 Count다.
4. 위 다섯 규칙의 라벨이 있지만 문서 요청 라벨이 없으면 `document-content-body-guard`가 차단한다. 같은 WebACL의 라벨은 `fruition:document-content`라는 로컬 이름으로 참조한다.
   `GenericRFI_QUERYARGUMENTS`·`EC2MetaDataSSRF_QUERYARGUMENTS` 라벨이 있지만 `fruition:oauth-loopback-redirect` 라벨(우선순위 4에서 부착)이 없으면 `oauth-loopback-redirect-guard`(우선순위 21)가 차단한다. `GenericRFI_BODY`·`EC2MetaDataSSRF_BODY` 라벨은 OAuth 라벨도 문서 요청 라벨도 없을 때 `rfi-ssrf-body-guard`(우선순위 22)가 차단한다. 아래 MCP OAuth 절과 [문서 본문의 loopback·IP URL](#문서-본문의-loopbackip-url) 절을 참고한다.
5. `app_domain`이 설정되고 접근 코드가 있으면 `frontend-access-code`가 해당 호스트의 `/api/` 요청 중 코드 없이 열리는 경로가 아니고 `fruition_access` 쿠키 해시가 맞지 않는 요청을 403으로 차단한다.
6. IP별 제한 `per-source-ip`(5분 3,000건, `/_next/static/` 제외)와 전체 제한 `all-api-requests`(5분 6,000건, `/api/`만 계산)를 평가한다. 초과 시 429다. 값은 `cost-guards.tf`의 `waf_requests_per_ip_5m`·`waf_requests_total_5m` 기본값이다.

종료 동작인 Allow를 추가하지 않는다. URI·쿼리·쿠키·헤더 검사, IP 평판, KnownBadInputs와 기타 본문 규칙, 서버 인증·인가 및 파일 검증은 계속 적용된다. 예외는 요청 전체의 모든 공격 검사를 끄는 기능이 아니다. 검색 API의 쿼리 검사도 유지한다.

## MCP OAuth loopback redirect_uri 예외

Claude Code·Codex·VS Code·Copilot CLI·Zed 같은 MCP OAuth 클라이언트는 `http://127.0.0.1:<port>/callback`, `http://localhost:<port>/callback` 형태의 loopback `redirect_uri`를 쓴다. 2026-11-11 운영(`https://fruition.wiki`) 탐침에서 쿼리 인자나 form 본문 값에 호스트가 IP 리터럴이거나 localhost인 URL(`http://127.0.0.1/cb`, `http://[::1]/cb`, `http://10.1.2.3/cb`, `http://localhost.example.com/cb` 등)이 있으면 403이었다. `http://example.com/cb`, `https://claude.ai/...`는 통과했다. 이 때문에 인가·동의 화면·토큰 교환이 모두 막혔다.

2026-11-11 WAF 로그로 확인한 차단 규칙은 CommonRuleSet의 두 계열이다. 루프백 호스트(`localhost`, `127.0.0.1`, `[::1]`)는 `EC2MetaDataSSRF_QUERYARGUMENTS`·`EC2MetaDataSSRF_BODY`(라벨 `awswaf:managed:aws:core-rule-set:EC2MetaDataSSRF_QueryArguments`·`...:EC2MetaDataSSRF_Body`)가, 그 밖의 IPv4 URL은 `GenericRFI_QUERYARGUMENTS`·`GenericRFI_BODY`(라벨 `...:GenericRFI_QueryArguments`·`...:GenericRFI_Body`)가 막았다. CRS는 첫 매치에서 끝나므로 SSRF만 풀면 다음 순서의 GenericRFI가 `127.0.0.1`을 잡는다. 그래서 네 규칙을 함께 예외로 둔다.

[요청 조건 목록](../infra/waf/oauth-loopback-redirect.json)이 Terraform과 테스트의 입력이다.

| 메서드 | 경로(정확히 일치) | 위치 | 서비스 |
|---|---|---|---|
| GET | `/oauth2/authorize` | 쿼리 `redirect_uri` | access |
| GET | `/mcp/authorize` | 같은 쿼리를 전달받는 동의 화면 | frontend |
| POST | `/oauth2/token` | form 본문 `redirect_uri` | access |

- 두 규칙만 Count로 바꾸고, `oauth-loopback-redirect-contract`(우선순위 4, Count)가 위 세 메서드+경로에 `fruition:oauth-loopback-redirect` 라벨을 붙인다. `app_domain`이 설정되면 Host 헤더가 그 값과 정확히 같아야 한다(소문자 변환). 경로는 변환 없이 정확히 비교하므로 끝 `/`·하위 경로·대소문자 변형은 예외가 아니다.
- `oauth-loopback-redirect-guard`(우선순위 21)가 두 쿼리 인자 라벨 중 하나가 있고 예외 라벨이 없는 요청을 차단한다. 두 본문 라벨은 `rfi-ssrf-body-guard`(우선순위 22)가 예외 라벨과 문서 요청 라벨이 모두 없는 요청을 차단한다. 그 밖의 경로의 차단은 이전과 같다. 문서 본문 계약 경로의 본문 예외는 2026-11-11에 추가했다(다음 절).
- 보안 영향: 세 경로에서는 `http://169.254.169.254/...` 같은 메타데이터 URL도 쿼리·본문으로 통과한다. access는 `redirect_uri`를 서버에서 가져오지 않고, 서버가 가져오는 `client_id`(CIMD)는 허용 목록 검사 뒤 공인 IP만 허용하는 resolver로 받으므로 SSRF로 이어지지 않는다.
- `GenericRFI_URIPATH`, `EC2MetaDataSSRF_COOKIE`·`EC2MetaDataSSRF_URIPATH`, LFI·XSS·SQLi 쿼리 검사, KnownBadInputs(`Host_localhost_HEADER` 포함)는 그대로다. Allow를 추가하지 않으며 redirect_uri 일치·PKCE 검증은 access가 책임진다.

운영 확인: 적용 후 위 세 경로에 loopback URL을 담은 인증 없는 요청이 403이 아닌 앱 응답(400/302/401 등)을 받는지, 다른 경로(예: `GET /mcp/authorize/x?x=http://127.0.0.1/cb`)는 403인지 본다. WAF 로그에서 해당 요청의 `labels`에 GenericRFI 라벨이 있는지 확인한다. 예외 경로가 여전히 403이면 `terminatingRuleId`와 `ruleGroupList`로 다른 관리형 규칙이 차단하는지 확인한다.

## 문서 본문의 loopback·IP URL

개발 메모처럼 문서 본문 첫 8KB에 `http://127.0.0.1:8080`, `http://localhost:3000`, `http://10.0.0.5/` 같은 URL이 있으면 `EC2MetaDataSSRF_BODY`·`GenericRFI_BODY`가 저장·업로드를 403으로 막았다. 2026-11-11부터 이 두 본문 규칙은 `fruition:document-content` 라벨이 있는 요청(위 표의 모든 계약)에서도 통과한다.

- [OAuth 정책 파일](../infra/waf/oauth-loopback-redirect.json)의 `document_content_body_rules`가 대상 규칙 목록이다. 쿼리 인자 규칙(`GenericRFI_QUERYARGUMENTS`·`EC2MetaDataSSRF_QUERYARGUMENTS`)은 넣지 않는다. 문서 경로라도 쿼리의 loopback URL은 `oauth-loopback-redirect-guard`(21)가 차단한다.
- `rfi-ssrf-body-guard`(22)가 두 본문 라벨이 있고 OAuth 라벨과 문서 요청 라벨이 모두 없는 요청을 차단한다. 그 밖의 경로(로그인, 이름 변경 등)의 본문은 이전처럼 막힌다. 21번 규칙에 중첩 조건을 더하지 않고 쿼리 인자(21)와 본문(22)으로 규칙을 나눠 각 규칙을 "라벨 있음 + 예외 라벨 없음" 형태로 유지했다.
- `GenericRFI_URIPATH`, `EC2MetaDataSSRF_URIPATH`·`_COOKIE`는 그대로다.

SSRF 점검(2026-11-11, Fruition-document·Fruition-ai 코드): 문서 본문·Markdown·편집기 JSON·채팅·에이전트 질의·가져오기 본문에 들어 있는 URL을 서버가 가져오는 코드는 없다.

- document: HTTP 클라이언트는 `RestClient`·JDK `HttpClient`·MinIO뿐이며 모든 대상이 설정값(내부 서비스·결제·환율·PostHog) 고정 호스트다. 문서 이미지 참조는 `/api/workspaces/{ws}/assets/{uuid}/content` 관리 자산만 인정하고 외부 이미지 URL은 문자열로 둔다(`DocumentAssetReferenceParser`). 내보내기는 DB·MinIO의 관리 자산만 묶는다. Notion 가져오기는 브라우저가 해석하고 서버는 세션만 관리한다. 링크 미리보기·원격 이미지 가져오기·HTML→PDF 렌더러는 없다.
- ai: 에이전트 웹 검색은 질문 문자열을 Tavily API(설정 고정 주소)에 보낼 뿐 결과 URL을 가져오지 않는다. PDF 복원은 S3 원본을 로컬에서 렌더링하고 scheme·host가 있는 이미지 링크는 건너뛴다. 그 밖의 호출도 설정 고정 주소다.
- 따라서 사설·loopback 주소 차단 코드도 없다. 링크 미리보기나 원격 이미지 가져오기를 추가하면 이 WAF 예외와 별개로 서버에서 사설 주소·리다이렉트·DNS rebinding 차단을 먼저 넣어야 한다.

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

프로브는 0으로 채운 합성 ID, 인증 없는 요청, 합성 Markdown만 사용한다. 문서를 변경하거나 AI 작업을 시작하지 않는다. 16개 API 경로에 크기·LFI·XSS·SQLi·loopback URL 예문을 보내는 80개 요청과, 예외에 포함되면 안 되는 16개 요청(쿼리 인자의 loopback URL, JSON으로 보낸 음성 경로 포함)을 보낸다. 음성 경로에는 `audio/webm;codecs=opus`로 합성 바이트를 보낸다.

- 예외 요청의 기대 결과는 **401**: WAF를 통과해 서버 인증에서 거부됨.
- 차단 유지 요청의 기대 결과는 **403**: WAF 로그의 `BLOCK`과 차단 규칙을 추가로 대조한다.
- 로그의 `x-fruition-waf-probe` 헤더와 결과 파일 `run_id`로 해당 실행만 찾는다. SQLi 등의 예문이 실제 관리형 라벨을 발생시켰는지도 확인한다. 403 상태만으로 WAF 차단을 확정하지 않는다.
- 프런트엔드 주소로 호출하면 별도의 접근 코드 게이트가 먼저 403을 반환할 수 있다. 이것은 WAF 검증 성공이나 WAF 회귀의 증거가 아니다. 프로브는 API 직접 주소로 수행하며, 로그인 후 실제 저장은 별도 업무 검증이다.
- `api.` 호스트는 모든 경로를 document로 보낸다. 아이콘·프로필 사진 경로도 document에 닿아 인증 거절(401)을 기대하지만, 이 결과는 WAF 판정 확인용이며 access 업로드 검증이 아니다. 기대와 다른 상태 코드면 WAF 로그의 `action`·라벨로 판단한다.
- 새 계약도 기존 계약처럼 호스트를 묻지 않는다. 라벨만 붙이는 Count라 화면 호스트의 접근 코드 게이트(우선순위 25)는 그대로 적용된다. `/api/auth/me/avatar`는 원래 접근 코드 없이 열린 경로(`^/api/(auth/|...)`)이고, 음성·아이콘·회의록·Skill 경로는 계속 접근 코드가 필요하다.
- 프로브는 `api.` 주소로 보내므로 `/mcp`는 넣지 않았다. document가 화면 호스트가 아닌 `/mcp`를 400으로 거절하기 때문이다. MCP 계약은 단위 테스트로 검사하고, 운영에서는 화면 호스트의 인증 없는 `POST /mcp`(본문 8KB 초과)가 401인지 확인한다.

운영 적용 시 Terraform 계획에서 `aws_wafv2_web_acl.cost_guard` 한 리소스의 변경만 확인한다. 다른 기능의 미병합 Terraform 코드가 있는 경우 전체 apply로 관련 리소스를 제거하지 않도록 검토한 WAF 대상 계획을 사용한다.

## 2026-09-21 검증 결과

- Terraform 검증과 AWS 테스트 92개(요청 조건 테스트 6개 포함)를 통과했다.
- 운영 WAF 한 리소스만 수정했다. 적용 후 조회한 용량은 1,210 WCU다.
- 운영 API 합성 요청 57개가 통과했다: 예외 요청 44개는 401, 차단 유지 요청 13개는 403이었다.
- 동일 실행의 WAF 로그 57개를 대조해 ALLOW 44개·BLOCK 13개를 확인했다. ALLOW 요청마다 해당 관리형 본문 검사 라벨과 문서 요청 라벨이 모두 존재했다. SQLi를 포함해 검사를 실제로 유발한 요청에만 예외가 적용됐음을 확인했다.
- 프런트 경유 비인증 요청은 별도의 접근 코드 게이트에서 403을 반환했다. 해당 결과를 WAF 회귀로 처리하거나 게이트를 해제하지 않았다.
- 로그인한 사용자의 문서 생성·저장·재조회와 AI 실행까지 포함한 업무 검증은 수행하지 않았다. 테스트는 사용자 문서를 변경하지 않았다.

근거: [AWS 기본 규칙](https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-baseline.html), [SQLi 규칙](https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-use-case.html), [ALB 본문 검사 제한](https://docs.aws.amazon.com/waf/latest/APIReference/API_Body.html), [로컬 라벨 참조](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-label-match-examples.html).

## 2026-10-22 호환성 보완

운영 회귀 검사에서 SQL 예문 11건이 `SQLiExtendedPatterns_BODY`에 차단되는 기존 예외 누락을 발견했다. 이 본문 규칙도 Count로 평가하고, 같은 라벨 `awswaf:managed:aws:sql-database:SQLiExtendedPatterns_Body`를 기존 재차단 guard에 추가했다. 요청 조건 목록은 넓히지 않았으며 쿼리·URI·헤더·쿠키 SQLi 검사는 유지한다.

적용 후 인증 없는 합성 요청 57건과 해당 WAF 로그를 대조했다. 예외 44건은 ALLOW/401, 대조군 13건은 BLOCK/403이었다. ALLOW 중 SQLi 확장 라벨이 발생한 11건도 확인했다. 이는 WAF 호환성 검사이며 로그인한 사용자의 저장·AI 실행까지 검증한 결과는 아니다.
