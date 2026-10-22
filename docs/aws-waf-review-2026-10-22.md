# WAF 스캔 조사와 운영 보완안 (2026-10-22)

2026-10-22의 `fruition-ops-waf_blocked` 경보 두 건을 AWS 조회와 요청 재현으로 조사했다. 첫 번째 스캔 126건은 모두 WAF에서 차단됐다. 두 번째 스캔의 WAF 통과 50건은 리스너 규칙·분 단위 지표·재현 결과가 ALB 기본 404에서 종료됐다는 판단을 뒷받침한다. 확인한 범위에서 파일 반환이나 유출을 시사하는 근거는 없다. 다만 두 번째 스캔은 당시 개별 응답 로그가 없어 **요청별 직접 증명이 아닌 정황 근거에 따른 판단**이다.

이 문서의 계정·서비스 도메인·ALB 주소는 공개용 예시로 치환했다. 최초 조사·계획 작성 단계에서는 운영 설정을 변경하지 않았다. 이후 요청에 따른 실제 적용은 7절에 기록했다. 예시 계정은 `123456789012`, 리전은 `ap-northeast-2`이며, 시간은 별도 표기가 없으면 한국시간(KST)이다.

## 1. 조사 결과와 판단 범위

| 구분 | 첫 번째 스캔 | 두 번째 스캔 |
|---|---|---|
| 경보 발생 | 12:58:03 | 13:48:03 |
| 요청 출발 IP | `91.92.242.37` | `54.252.245.37` |
| WAF 국가 분류 | NL | AU |
| 실제 차단 요청 시각 | 12:56:10–12:56:50 | 13:46:28–13:47:16 |
| WAF 차단 | 126건, IP 평판 규칙 | 120건: KnownBadInputs 117, Common 2, not-public-paths 1 |
| WAF 통과 | 조회 범위 내 0건 | 50건: GET 49, POST 1 |
| 요청 Host | `198.51.100.11` | `198.51.100.10` |
| 프로토콜 | HTTPS | HTTPS |

조회 범위는 UTC 03:40부터 조사 시점까지다. 쿼리 종료는 UTC 05:15로 지정했지만 미래 구간의 관측을 뜻하지 않는다. WAF 로그는 `aws-waf-logs-fruition`을 사용했다. 국가 분류는 요청 IP에 대한 분류이며 공격자의 국적이나 소재지를 확정하지 않는다.

주요 요청은 `/.env.test`, `/app/.env.prod`, `/config/.env` 등 설정 파일 탐색이었다. 두 번째 스캔은 `/.git/config`, 일부 `.env` 변형, PHP 진단 경로도 탐색했다. WAF의 ALLOW는 WAF 평가 통과를 뜻하며 앱의 성공 응답이나 파일 반환을 뜻하지 않는다.

### WAF 통과 50건이 ALB에서 종료됐다고 판단한 근거

1. **사실:** Host 집계 쿼리 `118c86f2-1e2b-4266-ab93-37398ce10681`에서 50건 모두 Host가 `198.51.100.10`였다. 서비스 도메인을 사용하지 않았다. 요청 목록 쿼리의 `@timestamp`는 UTC다.
2. **사실:** 조사 시점(약 13:52–13:53)에 조회한 HTTPS:443 리스너의 비기본 규칙 31개 모두 Host 조건이 있었다. 허용 호스트는 `web.example.com`, `api.example.com`, `access.example.com`뿐이었다. **추론:** 공격 시점에도 같은 규칙이었다면 IP Host 요청은 기본 규칙의 고정 404로 종료된다. 근거 5가 이 전제를 보강한다. HTTP:80은 조회 결과 기본 HTTPS 301 리다이렉트였으며 이번 공격 요청은 모두 HTTPS였다.
3. UTC 04:46의 WAF 통과 19건과 UTC 04:47의 31건이 같은 분의 `HTTP_Fixed_Response_Count` 19·31건과 일치했다. 이 지표는 집계값이며 개별 요청과의 일대일 연결 기록은 아니다.
4. UTC 04:53:08에 조회한 ALB DNS 이름으로 접속하면서 `Host: 198.51.100.10`, 경로 `/.git/config`를 재현했다. 결과는 `404`, `server: awselb/2.0`, 본문 0바이트였다. 본문 없는 기본 규칙 응답과 일치한다(별도 not-public 규칙은 `Not Found` 본문을 설정한다). Claude 검토 후 WAF 쿼리 `bac42175-b287-4d82-838c-70f641da295b`로 같은 시각·Host·URI의 ALLOW 기록과 `httpSourceId=123456789012-app/<ALB_ARN_SUFFIX>`를 확인해 재현 대상의 ALB 동일성을 보강했다. 재현은 그 시점의 동작을 검증한다.
5. 당일 UTC 00:00부터 조사 시점까지 조회한 CloudTrail에서 `ModifyRule`, `CreateRule`, `DeleteRule`, `ModifyListener`, `CreateListener`, `SetRulePriorities` 기록은 없었다. CloudTrail 수집 지연과 조회 범위의 한계는 남는다.

이 판단은 **이번 두 IP의 해당 시간대 요청**에 한정한다. 다른 시간대·공격 경로·계정 전체 침해 여부까지 검증한 결과는 아니다. ALB 접근 로그는 비활성 상태였고, 애플리케이션 로그 검색에도 대응 기록이 없었다. 앱 로그에 기록이 없다는 사실 자체는 미도달의 증명이 아니다. EKS API는 조사 환경에서 사설 주소 연결 시간 초과로 접근하지 못했으므로 실행 중인 컨테이너의 파일·설정은 검사하지 않았다.

재조회에 사용할 WAF Logs Insights query ID:

- IP별 차단 수·최초/최종 시각: `cafcca0a-134f-4b9e-b8e2-8a1baa586ac9`
- 두 IP의 ALLOW/BLOCK 집계: `72ae2925-3269-4dee-874e-b5d17c9b446f`
- Host·프로토콜·action 집계: `118c86f2-1e2b-4266-ab93-37398ce10681`
- 통과 요청 목록: `f0bcefdb-7dc3-4398-a117-2e34e79108ed`

query ID는 영구 증거 보관을 대신하지 않는다. 아래 만료 전에 이번 증거를 보존할 필요가 있으며, **권고 완료일은 2026-10-28**이다. 이는 문서의 제안 일정이며 증거 보관소 생성·업로드를 완료했다는 뜻이 아니다.

| 증거 | 재조회·해상도 유지 기간 | 이번 사건의 대략적 기한 |
|---|---|---|
| Logs Insights 쿼리 결과 | 7일 | 10월 29일 전후 |
| WAF 원본 로그 | 현재 retention 14일 | 11월 5일 전후(실제 삭제 지연에 의존하지 않음) |
| CloudWatch 1분 지표 | 15일 이후 5분 단위로 집계 | 11월 6일 전후 |

보존 대상은 쿼리 문자열·UTC 범위·결과, 관련 WAF 기록, 1분 단위 ALB 고정 응답/대상 응답 지표, 리스너·ALB attributes·WAF 설정, CloudTrail 결과, 재현 명령·응답 헤더다. 각 파일에 수집 시각(UTC)·수집자·실행 명령·SHA-256을 함께 남긴다. 접근 제한된 증거 보관소를 사용하고 원본 헤더·토큰·응답 비밀값을 Git에 저장하지 않는다.

## 2. 최초 조사 당시 확인한 설정

| 항목 | 현재 상태 | 근거 |
|---|---|---|
| 미등록 Host | ALB 기본 고정 404 | 운영 리스너·규칙 조회 |
| ALB 접근 로그 | S3 저장 꺼짐 | 운영 ALB attributes 조회 |
| 잘못된 헤더 제거 | `routing.http.drop_invalid_header_fields.enabled=true` | 운영 조회, [Ingress](../k8s/overlays/aws/ingress.yaml) |
| HTTP desync 완화 | `defensive` | 운영 ALB attributes 조회 |
| WAF 평가 불가 시 우회 허용 | `waf.fail_open.enabled=false` | 운영 ALB attributes 조회 |
| WAF 자체 경로 차단 | `/internal`, `/swagger-ui`, `/v3/api-docs` 계열 | [cost-guards.tf](../infra/terraform/cost-guards.tf)의 `not-public-paths` |
| WAF 요청 제한 | IP당 3,000/5분, 전체 API 6,000/5분 | 운영 WAF 조회, cost-guards.tf |
| WAF 로그 | CloudWatch 14일, Authorization·Cookie·X-API-Key·query 마스킹 설정 | 운영 로그 그룹 조회, cost-guards.tf |
| WAF 경보 | 전체 규칙 차단 합계 >100/300초, 1/1 평가, missing=`notBreaching` | 운영 경보 조회, [observability.tf](../infra/terraform/observability.tf) |

IP 요청을 막은 Host 라우팅은 유지한다. Host는 공격자가 바꿀 수 있으므로 도메인 비공개나 Host 검사만으로 민감 파일을 보호한다고 보지 않는다. 이번 알림은 IP별/전체 요청 제한 규칙에서 발생한 것이 아니다.

## 3. 보완 우선순위와 완료 기준

### 우선순위 1 — ALB 접근 로그와 증거 보존

전용 S3 버킷에 접근 로그를 저장하고, 우선 30일 보관 후 자동 삭제하는 안을 적용 대상으로 삼는다. 30일은 제안값이며 개인정보·보안 요구와 비용을 확인해 확정한다. 사고 관련 자료는 만료 전에 별도로 보존한다.

- 버킷은 ALB와 같은 서울 리전, 전체 퍼블릭 접근 차단, 최소 읽기 권한으로 만든다. 전통적인 ALB S3 접근 로그 방식은 SSE-S3를 사용한다. 기존 SSE-KMS 버킷을 그대로 재사용할 수 있다고 가정하지 않는다.
- 현재 AWS 문서의 서비스 principal `logdelivery.elasticloadbalancing.amazonaws.com`에 `s3:PutObject`를 허용하고 리소스는 `<prefix>/AWSLogs/123456789012/*`로 제한한다. 지원되는 `aws:SourceArn` 조건으로 허용 리전·계정도 제한한다. HTTPS 강제 정책과 서비스 전달 정책의 호환성도 확인한다. 스토리지·요청·검색 비용을 추적한다.
- 실제 ALB는 AWS Load Balancer Controller가 관리하므로 [Ingress annotation](../k8s/overlays/aws/ingress.yaml)의 `load-balancer-attributes`와 배포 설정 생성 경로에서 로깅을 관리한다. 버킷·정책을 먼저 준비한 뒤 `access_logs.s3.enabled/bucket/prefix`를 기존 헤더 제거·idle timeout과 같은 annotation 문자열에 추가한다. 같은 IngressGroup의 다른 Ingress와 설정 충돌도 확인한다. 콘솔/CLI 변경만으로 끝내거나 별도 `aws_lb`를 중복 생성하지 않는다.
- 로그 비활성화 전 버킷을 삭제하거나 전달 정책을 제거하지 않는다. Controller 재조정 실패·추후 Ingress 변경 차단과 로그 중단 위험을 검증하고 순서대로 되돌린다. 증거 prefix는 일반 로그의 만료 규칙에서 제외한다. 버전 관리를 켠다면 이전 버전 만료도 명시한다.
- ALB 로그의 `request`와 리다이렉트 URL에는 query가 남을 수 있다. IP·User-Agent도 개인정보로 취급한다. WAF 마스킹 설정은 ALB 로그에 전파되지 않는다. URL에 장기 비밀값을 싣지 않고, OAuth 콜백의 code/state·초대 링크 토큰 등을 고려해 원본 로그의 권한·보관 기간을 제한한다. Athena를 사용하면 검색 결과 저장 위치에도 같은 제한·만료를 적용한다. 공유본은 query를 제거한다. ALB 로그에 WAF와 같은 임의 필드 마스킹이 있다고 가정하지 않는다.
- `elb_status_code`, `target_status_code`, `matched_rule_priority`, `actions_executed`, 대상 정보와 시간으로 WAF 통과 이후를 확인한다. 로그만으로 응답 본문의 내용이나 유출 여부를 확정하지 않는다.
- ALB 로그는 지연·누락 가능성이 있는 best-effort 기록이다. 앱의 인증·권한 실패 및 민감 데이터 접근 감사 기록과 함께 판단한다.

완료 기준: 제어된 미등록 Host 요청은 `fixed-response`/404/대상 없음으로, 정상 도메인의 안전한 요청은 기대한 전달 대상으로 기록된다. 버킷 테스트 파일뿐 아니라 실제 요청 로그 도착, 비공개 정책, 자동 만료 설정까지 확인한다. 로그 전달 실패와 실제 트래픽 대비 장기 미수신을 구분해 점검한다.

### 우선순위 2 — 민감 파일 경로의 명시적 차단

도메인 Host를 사용해도 `.env`와 Git 메타데이터 탐색을 막는 별도 WAF 규칙을 추가한다. 기존 AWS 관리 규칙과 Host별 ALB 라우팅은 유지한다.

직접적인 보완 근거는 통과 목록의 `/.git/config` 1건과 루트 `.env.*` 변형 16건이다. 나머지는 PHP·환경 진단 경로 31건과 `/` GET·POST 각 1건이다. 기존 관리형 규칙이 이 경로의 차단을 보장하지 않았으며, 서비스 도메인 Host였다면 현재 ALB의 도메인별 포괄 경로 규칙상 앱 전달 대상이 된다. 이것이 실제 파일 반환을 뜻하지는 않는다.

- URI 경로의 세그먼트 경계를 기준으로 `/.git` 및 하위 경로, `.env` 및 합의한 점·백업 접미사 변형을 차단 대상으로 설계한다. 예: `/.git/config`, `/.env`, `/.env.local`, `/config/.env`.
- `env` 문자열 전체나 모든 dot 경로를 막는 규칙은 피한다. `/.well-known/`, 정상 정적 자산, 사용자 문서 이름과 실제 API 경로가 오탐되지 않아야 한다. 문서 본문 예외 정책과 충돌시키지 않는다.
- `URL_DECODE` → `NORMALIZE_PATH` → `LOWERCASE` 등 변환 순서와 WCU를 검토한다. `%2e`, 중복 슬래시, 대소문자, 이중 인코딩은 실제 서버 디코딩 동작과 함께 검증한다. 한 번 디코딩하는 것만으로 모든 우회를 막는다고 주장하지 않는다.
- 먼저 Count로 오탐과 매치 결과를 확인한 후 Block으로 전환한다. Count는 요청을 보호하지 않으므로 검증 중에도 기존 방어와 앱의 파일 비노출 정책을 유지한다.
- 기존 priority 1·2 및 관리형 규칙과 충돌하지 않는 평가 순서를 정한다. Count 단계의 `CountedRequests`, 전환 후 `BlockedRequests`와 매치 로그를 점검한다. 적용 전 `CheckCapacity`와 실제 WebACL 용량으로 WCU 증가를 확인한다. 과거 문서에 적힌 용량을 현재 값으로 간주하지 않는다.
- PHP 진단 경로·기타 백업 파일의 추가 차단은 서비스가 사용하지 않음을 확인한 다음 범위를 정한다. 이번 IP만 영구 차단하거나 국가 전체를 차단하는 것을 기본 해결책으로 삼지 않는다.

완료 기준: 실제 서비스 도메인의 세 Host에서 차단 대상·인코딩 변형이 의도한 규칙에 매치하고, 정상 API·로그인·문서 저장·정적 자산은 통과한다. 응답 코드만으로 성공을 판정하지 않고 WAF 규칙 ID와 action을 대조한다. 운영에서 실제 비밀 파일을 내려받는 방식 대신 비밀이 없는 검증 환경과 합성 경로로 확인한다.

### 우선순위 3 — 짧은 스캔과 지속·영향 있는 이벤트의 경보 구분

현재 1/1 경보는 한 번의 짧은 스캔으로 ALARM, 다음 평가가 낮으면 OK가 된다. 알림 원문의 UTC 데이터포인트는 03:53의 126, 03:59의 7, 04:43의 120이며 연속된 세 기간을 뜻하지 않는다. 짧은 스캔이 기간 경계에 나뉘어 각 기간이 100 이하라면 알림이 없을 수도 있다. 경보가 많다는 이유만으로 차단을 완화하지 않는다.

- 전체 차단 수와 규칙별 수는 대시보드에 유지한다. 단발 스캔은 주의 수준, 지속 급증은 별도 높은 우선순위 알림으로 분리한다. 예를 들어 5분 평가 3개 중 2개 초과는 검토용 초안이며 기준선 확인 후 확정한다.
- 현재 Terraform은 `datapoints_to_alarm = evaluation_periods` 구조다. 2/3을 구현하려면 평가 기간과 초과 개수를 각각 설정할 수 있게 바꿔야 한다. 숫자 하나만 3으로 바꾸면 3/3이 된다.
- 2/3은 15분 창에서 두 기간 이상 초과해야 하므로 이번처럼 짧고 떨어진 두 스캔에는 울리지 않을 수 있다. 차단 합계 경보는 민감 경로의 ALLOW를 감지하지 못한다. 민감 경로 규칙의 Count/Block 관측과 앱 감사 기록을 별도로 유지한다.
- 지속 공격 경보는 서비스 오류 유무와 독립적으로 유지한다. 서비스 영향은 Target 5xx와 별도로 ALB 자체 5xx·가용성도 관찰한다. 현재 `alb_5xx`는 `HTTPCode_Target_5XX_Count`만 본다. 실제 요청 기반 기동의 의도된 503과 장애를 구분한다.
- 보안 경보를 모두 `WAF 차단 AND 5xx` 조건으로 묶지 않는다. 정상적인 데이터 탈취 응답은 200일 수도 있다. 민감 경로에 대한 성공 응답은 앱 감사 기록과 경로별 결과를 추가 조사할 신호다.
- ALARM/OK 모두 구분 가능한 심각도와 규칙·시간 범위·조사 링크를 보낸다. 무트래픽 시 missing=`notBreaching`은 유지하되 로그 수집 장애를 정상 무트래픽과 혼동하지 않도록 별도 점검한다. 공격자 IP를 CloudWatch custom metric dimension으로 무제한 생성하지 않는다.
- 로그 수집 중단 감지 초안은 실제 WAF 허용 트래픽과 `AWS/Logs`의 `IncomingLogEvents`를 대조하는 것이다. 현재 로깅 필터가 없는 설정을 전제로 하되, 수집 지연·누락 지표·최소 트래픽·지속 기간을 반영한 뒤 알림을 연결한다. 한 분의 0건만으로 장애를 확정하지 않는다.

완료 기준: 단발 급증, 2/3 등 지속 조건, 서비스 오류만 발생, 무트래픽, 수집 중단의 각 시나리오에서 기대한 경보·복구·전달 동작을 검증한다. 검증 없이 기존 ALARM/OK 알림을 모두 끄지 않는다.

## 4. 추가로 확인할 범위

아래는 이번 조사에서 취약성이 확인된 항목이 아니라 별도 검증 대상이다.

- **로그 만료 전 우선 확인:** 보관 중인 WAF 로그 범위에서 두 IP 외 모든 IP를 대상으로, 세 서비스 도메인 Host에서 `.env`·`.git` 경로가 ALLOW된 요청을 집계한다. 인코딩 변형을 포함할 검색 조건을 검증하고 결과가 0이어도 쿼리·범위를 보존한다. 발견되면 해당 시간의 앱 로그·대상 지표와 대조한다. 이번 두 IP 조사로 이 조회까지 완료한 것은 아니다.
- 서비스별 Dockerfile·`.dockerignore`·이미지 내용에서 `.git`, `.env`, 키 파일이 배포 산출물이나 정적 공개 경로에 포함되지 않는지 검사한다. 이 저장소는 플랫폼 저장소이므로 서비스 저장소와 실제 배포 이미지에서 확인해야 한다. 런타임 비밀 주입과 공개 정적 파일을 구분하고 비밀값을 출력하지 않는다.
- 서비스 도메인의 응답 검증은 우선 비밀 없는 검증 환경에서 한다. 운영 확인이 필요하면 상태·크기·안전한 헤더만 기록하고 본문 비밀값을 저장·출력하지 않는다. 200이나 본문 존재만으로 유출을 확정하지 않는다(로그인 화면·오류 페이지일 수 있음). 응답 유형·라우팅·앱 기록을 대조해 실제 비밀 반환이 확인되면 노출된 자격증명 교체와 접근 이력 조사로 전환한다.
- 앱은 토큰·Cookie·요청/응답 본문을 기록하지 않고, 필요한 요청 ID·인증/권한 판정·대상 리소스·응답 상태를 감사 기록으로 남길 수 있는지 확인한다. 신뢰할 수 없는 `X-Forwarded-For`를 인증이나 IP 허용의 근거로 삼지 않는다.
- ALB `trace_id`와 앱이 관측한 `X-Amzn-Trace-Id`를 상관 분석에 사용할 수 있는지 검증한다. 외부 입력 가능성을 고려해 인증 근거로 쓰지 않고 길이·형식을 제한하며, WAF 요청 ID와 자동으로 일치한다고 가정하지 않는다.
- ALB를 거치지 않고 서비스 포트에 외부 접근할 수 없는지 security group·Ingress·Service 노출을 확인한다. 이번 WAF/ALB 조회만으로 이 경로까지 검증한 것은 아니다.
- CloudTrail에서 ALB 리스너·규칙·attributes 변경, WebACL 수정·연결 해제, WAF 로깅 삭제, 로그 그룹·보관 기간, S3 정책·수명주기 변경을 추적하고 예상 밖 변경을 알리는 운영 방식을 검토한다. 기존 운영 SNS 연결과 호출 주체 표시로 정상 Controller 재조정과 방어 약화 변경을 구분한다.

## 5. 구현 순서와 검증 범위

1. 조사 증거를 접근 제한된 위치에 보존하고 서비스 이미지의 파일 비노출을 확인한다.
2. Terraform으로 로그 버킷·정책·수명주기를 준비하고, Controller 관리 설정으로 접근 로그를 활성화한다. 실제 로그 도착을 확인한다.
3. 민감 경로 WAF 규칙을 Count로 관측하고 호환성 검증 후 Block으로 바꾼다. 오탐 시 새 규칙만 되돌릴 수 있게 한다.
4. 로그·지표 기준선을 바탕으로 경보를 조정한다. 새 알림 검증 후 기존 알림 경로를 정리한다.

코드 변경 시 Terraform plan과 Ingress 렌더링 결과를 확인하고 WAF 외 리소스 삭제·노드/DB 교체가 끼지 않았는지 검토한다. 이 문서 작성은 배포나 전체 Terraform apply 실행을 뜻하지 않는다.

## 6. Claude 교차 검토

2026-10-22 Claude Code 비대화형 호출이 정상 완료됐다(`is_error=false`, 1 turn, CLI 보고 모델 `claude-opus-5-5`). 초안과 Terraform·Ingress·문서 본문 예외 정책, ALB 규칙 스냅샷, 재현 응답 헤더, 민감정보를 제외한 통과 요청 50건 목록을 제공했다. 도구는 비활성화했으며 Claude가 운영 설정을 변경하거나 AWS를 직접 재조회한 검토는 아니다.

| 검토 결과 | 반영 및 판단 |
|---|---|
| ALLOW/성공 응답 구분, 404 추론의 방향, Controller 소유권, SSE-S3, best-effort, 2/3 구현 지적은 타당 | 유지. 사실과 추론의 구분 및 조회 범위를 더 명확히 함 |
| 증거 보존 기한과 무결성 기록이 부족 | 쿼리 결과 7일·WAF 14일·1분 지표 15일, 10월 28일 권고 보존일, SHA-256·수집 시각 추가. 기간은 AWS 공식 문서로 재확인 |
| 서비스 도메인 Host의 과거 민감 경로 ALLOW 조사 필요 | 로그 만료 전 추가 조회 대상으로 명시. 미수행 상태를 유지 |
| 관리형 규칙 통과 범위가 불명확 | 로컬 통과 목록을 다시 집계해 `.git` 1·`.env.*` 16건 명시 |
| 버킷 정책과 Controller 설정 순서·그룹 충돌·만료 예외가 필요 | 버킷/정책 선행, annotation 병합, IngressGroup 충돌, 증거 prefix 예외와 이전 버전 만료 추가 |
| 민감 URL·로그 수집 장애·방어 약화 변경·상관 분석 보완 | OAuth·초대 URL, Athena 결과, 수집 지연 고려, 설정 변경 추적과 trace 취급 주의 추가 |
| 200 응답 또는 본문 존재만으로 유출 사고 전환 제안 | **미채택.** 로그인·오류 페이지도 가능하므로 추가 증거로 비밀 반환 여부를 판단하도록 수정 |
| 서울 리전은 과거 ELB 계정 principal이 필요한지 확인 제안 | AWS 공식 문서에서 현재 서비스 principal 지원을 확인해 해당 principal과 SourceArn 제한을 명시 |
| 고정 정규식·WCU 수치와 Object Lock 등 추가 도입 제안 | 정규식은 호환성·우회 검증, 용량은 CheckCapacity 후 확정. Object Lock·국가 차단·대규모 신규 서비스는 필수 항목으로 채택하지 않음 |

문서 수정 반영 뒤 로컬 링크와 공백 오류를 검사했다. Claude의 검토는 독립적인 침해 포렌식이나 구현·배포 검증을 대체하지 않는다.

## 7. 2026-10-22 운영 적용 기록

사용자 요청으로 아래 설정을 실제 운영에 적용했다. 코드 검토용 PR은 운영 적용과 별개이며 병합은 하지 않는다.

| 항목 | 적용 내용·검증 |
|---|---|
| ALB 로그 | 전용 S3 버킷, SSE-S3, 퍼블릭 접근 전체 차단, BucketOwnerEnforced, 일반 로그 30일 만료. 실제 Ingress annotation으로 활성화하고 테스트 파일뿐 아니라 `.log.gz` 요청 로그 도착까지 확인 |
| 전달 결과 대조 | 세 Host의 Count 단계 합성 경로 로그 36건에서 대상 전달·응답을 확인. Block 단계 양성 24건은 ALB 로그에서 404·대상 상태 없음·`actions_executed=waf`를 확인 |
| 민감 경로 | priority 3의 `sensitive-file-paths`. `.git`·`.gitconfig`·`.git-credentials`·`.env`·`.envrc`·점/백업 접미사, URL 인코딩·대소문자·세미콜론 경로 파라미터 변형을 대상으로 함. 새 규칙 CheckCapacity는 33 WCU |
| 단계별 검증 | Count 단계 세 Host 40건의 WAF 기록에서 양성 24·음성 16건 일치 확인 후 Block 전환. 세미콜론 변형을 포함한 최종 Block 검사 49건도 양성 33·음성 16건 일치. 기존 `.gitignore`·`.environment`·`.well-known`·정상 API·화면 health 경로는 새 규칙에 매치하지 않음 |
| 경보 | `waf_blocked`: 5분 100건 초과 2/3, `waf_blocked_burst`: 5분 1,000건 초과 1/1. 차단 지표는 계속 보존. ALB 자체 5xx 2/3과 WAF 트래픽 대비 로그 미수신 3/3 추가 |
| 배포 전 검증 | 로그 버킷의 소유 계정·서울 리전·비공개 정책 확인을 앱 배포 전 읽기 검사로 추가. 배포 역할에는 해당 버킷의 위치·정책 상태 조회만 허용하고 로그 객체 읽기는 허용하지 않음 |
| 접근 코드 보존 | `waf_access_code_required=true` 기본값에서 도메인·접근 코드 모두 필수. 의도적인 미사용 배포만 명시적으로 false를 선택. 실제 Ingress Host와 Terraform 입력은 plan 검토에서도 대조 |
| 문서 본문 | 관리형 SQLi 확장 본문 규칙의 기존 예외 누락을 보완. 합성 57건과 WAF 기록에서 예외 ALLOW/401 44건, 대조군 BLOCK/403 13건 확인. 경로·메서드·Content-Type 범위는 유지 |

### 적용 중 발견 사항과 복구

- 로컬 Terraform 입력과 앱 배포 JSON이 실제 운영보다 오래돼 ALB 식별자·metrics-server 버전·화면 Host가 누락되거나 이전 값이었다. 현재 AWS/EKS/Ingress에서 확인한 값을 Git 제외 입력으로 보정했다.
- 최초 Count 적용에서 빈 `app_domain` 때문에 기존 `frontend-access-code` 규칙이 잠시 제거됐다. 사전 스냅샷의 규칙과 사용자 응답 본문을 즉시 복구했고, 새 규칙 외 모든 기존 WAF 규칙을 API JSON으로 비교해 일치함을 확인했다. 이후 필수 입력 precondition과 적용 계획의 기존 규칙 변경 거부 검사를 추가했다. 잘못된 도메인 오타까지 Terraform이 자동 검증하는 것은 아니므로 실제 Host 대조는 계속 필요하다.
- 최초 전체 plan에는 기존 Lambda 소스와 CORS의 별도 차이도 있었다. 검토한 대상 plan만 적용했으며 노드·DB 교체나 자원 삭제는 실행하지 않았다. 이번 범위 밖 차이를 없애기 위한 전체 apply는 하지 않는다.
- 과거 보관 범위의 서비스 Host 대상으로 `.env`·`.git` 및 일부 인코딩 키워드를 포함한 ALLOW 382건(69개 Host/경로 집계)을 발견했다. 검색은 모든 우회 표현을 포괄한 포렌식이 아니다. 당시 개별 응답 기록은 없으며 이번 스캔 두 IP의 404 판단을 이 과거 요청에 확대하지 않는다. 현재 화면·Access·Document 컨테이너의 `/app` 하위 4단계 파일명 검사에서 `.env*`·`.git`은 발견되지 않았다. JAR 내부 전체나 과거 이미지까지 검사한 결과는 아니다.

### 검토 반영과 남은 한계

최종 `scripts/aws-iac-validate.sh`가 통과했다(Terraform 두 모듈 fmt/validate, Kustomize, AWS 계약 테스트 176개). 이번 대상 자원의 재계획 결과는 변경 0건이었다. 필수 접근 코드 입력을 비우는 음성 plan은 precondition으로 거부됐고, 운영 버킷 사전 검사도 통과했다. IAM 시뮬레이션에서 배포 역할의 버킷 위치·정책 상태 조회는 허용, 로그 객체 GetObject는 허용되지 않음을 확인했다. 새 경보 네 개는 조회 시점 모두 OK였다. 이는 실제 경보 발생·Discord 수신을 새로 유발한 전달 시험은 아니다.

원래 사건의 쿼리 결과·1분 지표·규칙 스냅샷, 적용 후 합성 요청/WAF/ALB 대조 결과 등 30개 파일을 전용 비공개 로그 버킷의 `evidence/waf-2026-10-22/`에 보존했다. manifest에 수집 시각과 파일별 SHA-256을 남겼으며 이 prefix는 일반 로그의 30일 만료에서 제외된다. 민감한 WAF 설정과 요청 메타데이터가 포함될 수 있으므로 운영 조사 권한으로만 취급한다. 원본은 Git에 추가하지 않았다.

Claude Code로 구현 diff와 새 정책을 추가 검토했다. 배포 전 버킷 확인, 접근 코드 필수 의도, 세미콜론 경로 변형, 로그 미수신 경보의 한계를 반영했다. 서울 리전 서비스 principal에 대한 재확인 의견은 현재 AWS 공식 문서와 실제 로그 전달 성공으로 검증했다. 알림 코드는 경보 이름별 매핑이 아니라 `AlarmDescription`을 표시하므로 새 경보에 한글 설명을 넣었다.

WAF 로그 미수신 경보는 연속 세 구간에 트래픽이 있으면서 수신이 완전히 없는 경우를 감지한다. 부분 누락·간헐 트래픽·ALB S3 로그 전달 자체의 중단까지 보장하지 않는다. ALB 로그는 지연·누락될 수 있고 소급 생성되지 않는다. 유출 판정은 접근 로그의 상태·바이트 수만으로 확정하지 않는다. 로그인한 사용자의 저장·AI 실행, 전체 과거 침해 여부, 별도 CloudTrail 변경 경보 구축은 이번 적용의 완료 범위가 아니다.

## 참고 자료

- [ALB 접근 로그와 기록 필드](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-access-logs.html)
- [S3 접근 로그 활성화·리전·SSE-S3·버킷 정책](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-access-logging.html)
- [AWS WAF text transformations](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-transformation.html)
- [CloudWatch 경보](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Alarms.html)
- [Logs Insights 결과 보관 7일](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html)
- [CloudWatch 지표 해상도별 보관 기간](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html)
- [현재 운영 경보와 로그](aws-observability.md), [문서 본문 WAF 예외 정책](aws-waf-document-content.md)
