# PostHog 알파 배포·검증

목표 프로젝트 658129는 production 전용으로 사용한다. 실제 프로젝트 ID와 공개 키의 소속은 coordinator가 로그인 후 확인해야 한다. 이 저장소는 이벤트를 발행하지 않으며 각 서비스가 소유하는 outbox/relay와 프론트 런타임 설정에 환경을 공급한다. 실제 키, 개인정보, 이벤트 payload를 Git·CI artifact·운영 로그에 남기지 않는다.

## 서비스 계약

- `ANALYTICS_ENABLED=false`가 기본이다. false는 기록과 relay를 중지한다. `POSTHOG_PROJECT_TOKEN`이 없거나 공백이면 relay/브라우저 전송은 중지한다.
- `ANALYTICS_ENVIRONMENT`: local / staging / production, 서비스 기본값 local. AWS overlay는 production이다.
- `APP_VERSION`: 배포 release.json의 해당 서비스 저장소 소스 SHA. 릴리스 묶음 ID와 구분한다.
- `POSTHOG_HOST`: 서버 capture origin. 운영은 `https://us.i.posthog.com`, 로컬 서버는 mock origin. 프론트는 US endpoint를 사용하므로 브라우저 검증은 네트워크 interception 또는 별도 테스트 프로젝트가 필요하다.
- `distinct_id`는 원 요청 사용자, `timestamp`는 실제 발생 UTC로 재시도에도 고정한다. properties에는 `event_id`, `schema_version=1`, `event_source`, `environment`, `app_version`, `$groups.workspace`(원 대상 workspace)를 둔다.
- UUIDv5 namespace `6ba7b811-9dad-11d1-80b4-00c04fd430c8`, name `fruition.analytics.v1:{event}:{logicalKey}`. 서비스별 허용 속성만 전송한다. 이름·제목·본문·질문·답·오류 원문·URL은 금지한다.
- Access/Document/AI의 트랜잭션 outbox 및 relay 구현·이벤트 완전성은 각 서비스 PR 검증 대상이다. 플랫폼 단위 테스트는 이를 대신하지 않는다.

## 로컬 검증 (실행 중인 서비스는 자동 재시작하지 않음)

`front-up.sh`와 `back-up.sh`는 `scripts/lib/analytics.sh`를 통해 운영 환경변수를 덮어쓰고 로컬 설정만 전달한다. 로컬 프론트·Spring의 APP_VERSION은 각 서비스 체크아웃의 HEAD다. Compose AI·Spring은 아래 설정을 명시적으로 전달한다. 기존 `infra/.env` 내용을 출력하거나 운영 토큰을 복사하지 않는다.

| 설정 | 기본값 | 용도 |
|---|---|---|
| LOCAL_ANALYTICS_ENABLED | false | 명시적으로 true일 때만 기록 활성화 |
| LOCAL_POSTHOG_PROJECT_TOKEN | 빈 값 | mock 전용 더미 또는 별도 테스트 프로젝트 키 |
| LOCAL_POSTHOG_HOST | native: http://127.0.0.1:18080, compose: http://host.docker.internal:18080 | 서버 mock sink |
| LOCAL_APP_VERSION | local | Compose 서비스 테스트 버전; 가능하면 시험 서비스 소스 SHA 지정 |

1. 기본 설정에서 앱 시작·제품 API가 정상이며 analytics 송신이 0건인지 확인한다. 토큰이 비어 있는 true 설정에서도 송신이 없어야 한다.
2. 서버 테스트에는 localhost HTTP mock을 사용한다. `LOCAL_ANALYTICS_ENABLED=true`, mock 더미 토큰, host endpoint를 **명령 환경**에 지정한다. 실제 PostHog로 보내지 않는다. 프론트 요청은 브라우저 테스트에서 US 수집 endpoint를 intercept한다.
3. 제품 성공 시 outbox 1행, 트랜잭션 rollback 시 0행을 확인한다. mock 500 → 200 재시도에서도 event_id/uuid·timestamp·distinct_id·workspace가 같아야 한다. 500이 제품 응답을 실패시키면 안 된다.
4. 동일 AI 결과 재전달은 1개 논리 이벤트, 사용자가 새로 실행한 run은 새 이벤트인지 확인한다. workspace 전환 후 지연 완료에도 원 workspace/사용자를 유지해야 한다.
5. 수집 payload의 속성 allowlist, UUIDv5, UTC, app_version을 각 서비스 테스트와 대조한다. 금지 원문을 fixture로 넣었을 때 payload에 없어야 한다. payload를 실제 운영 데이터로 시험하지 않는다.
6. 별도 staging 프로젝트를 선택했다면 `environment=staging`과 전용 키를 해당 환경에만 설정한다. 이 AWS production overlay나 658129 토큰을 staging에 재사용하지 않는다.

오프라인 플랫폼 검증: `rtk proxy /path/to/python -m unittest discover -s scripts/tests -p 'test_aws_*.py' -v` (PyYAML, redis 필요). 전체 인프라 검증은 `AWS_VALIDATION_PYTHON`을 지정해 `rtk proxy bash scripts/aws-iac-validate.sh`를 실행한다. 테스트는 실제 analytics/AWS 전송을 하지 않는다.

## DB 추가 마이그레이션과 release gate

기존 `expand-only` 경로가 Access Flyway, Document Flyway, AI migration Job을 workload 교체 전에 실행하고 변경 후 fingerprint를 기록한다. outbox는 각 DB migration role 소유로 추가한다. 기존 default privileges가 runtime에 table SELECT/INSERT/UPDATE/DELETE와 sequence 권한을 부여한다. converter에 outbox 권한을 추가하지 않는다.

기존 성공 release의 fingerprint를 덮어쓰거나 bootstrap/initial-install로 우회하지 않는다. 스키마가 달라진 후 이전 release의 직접 rollback은 기존 fingerprint gate에 막힌다. 긴급 복구는 수집 off 또는 이전 코드와 새 additive schema가 호환됨을 시험한 **새 release와 review**를 사용한다. DB 초기화·TRUNCATE·DROP은 이 변경에 필요하지 않다.

## AWS Secret 연결과 활성화

`fruition-analytics` ExternalSecret은 기존 `fruition/app`을 읽되 `engineVersion=v2`, `mergePolicy=Replace`로 `POSTHOG_PROJECT_TOKEN` 한 키만 target Secret에 쓴다. missing-key는 `index`와 `default`로 빈 문자열이 된다. 다른 서비스 Secret의 property 목록은 바꾸지 않는다. [ESO 템플릿·Replace 계약](https://external-secrets.io/main/guides/templating/)을 따른다. Deployment는 이 단일 키를 optional secretKeyRef로 받는다. 값은 manifest·ConfigMap·Next build arg에 들어가지 않는다.

토큰이 없는 기본 배포는 정상 진행한다. `AWS_DEPLOY_CONFIG_JSON`의 선택 입력 `"analytics_enabled": "true"`를 명시하면 Access DB preflight Job에서 phc_ 공개 키 형식·공백 여부를 검사하고 실패 시 migration/workload 교체를 막는다. Secret 자체를 읽는 deployer 권한은 추가하지 않는다. 서비스도 토큰 누락/공백일 때 전송을 중지해야 한다.

다음은 **운영자/coordinator가 기존 사용자 승인 범위에서 실행할 절차**이며 이 worker는 실행하지 않았다. 사용자는 통합·배포·공개 토큰 연결을 이미 승인했다. 이 문서는 추가 허가를 요구하지 않으며 기존 GitHub branch/Environment와 immutable release 보호만 유지한다. 먼저 동시 Secret 편집을 중지하고 프로젝트 ID와 phc_ 공개 키 소속을 확인한다. personal API key(phx_)를 사용하지 않는다. 아래 코드는 키를 터미널 비표시 입력으로 받고, 기존 JSON 전체를 메모리에서 보존하여 한 property만 병합한다. Secret 값을 인수·파일·로그에 쓰지 않는다. AWS는 JSON property 단위 compare-and-swap을 제공하지 않으므로 동시 편집을 허용하면 안 된다.

```sh
rtk proxy python3 - <<'PYCODE'
import getpass, json, re, subprocess

def aws(*args, payload=None):
    result = subprocess.run(["aws", "secretsmanager", *args,
                             "--region", "ap-northeast-2", "--output", "json"],
                            input=payload, text=True, capture_output=True)
    if result.returncode:
        raise SystemExit("Secrets Manager operation failed; values suppressed")
    return json.loads(result.stdout)

token = getpass.getpass("Verified public project token (hidden): ").strip()
if not re.fullmatch(r"phc_[A-Za-z0-9_-]+", token):
    raise SystemExit("Expected public phc_ project token")
before = aws("get-secret-value", "--secret-id", "fruition/app")
data = json.loads(before["SecretString"])
if not isinstance(data, dict):
    raise SystemExit("Expected existing JSON object; no write performed")
updated = {**data, "POSTHOG_PROJECT_TOKEN": token}
current = aws("get-secret-value", "--secret-id", "fruition/app")
if current["VersionId"] != before["VersionId"]:
    raise SystemExit("Concurrent secret edit detected; no write performed")
aws("put-secret-value", "--secret-id", "fruition/app",
    "--secret-string", "file:///dev/stdin", payload=json.dumps(updated))
after = aws("get-secret-value", "--secret-id", "fruition/app")
if json.loads(after["SecretString"]) != updated:
    raise SystemExit("Verification mismatch; inspect without printing secret values")
print("Project token merged and all other properties preserved")
PYCODE
```

ExternalSecret의 최대 1시간 refresh를 기다리거나 승인된 관리자가 해당 리소스만 refresh annotation을 갱신한다. `kubectl get secret -o yaml`처럼 값을 출력하지 않는다. Secret env는 Pod 시작 시 고정되므로 새 배포/승인된 rollout이 필요하다. 로컬/mock에서 flag=false와 활성화 경로를 모두 검증한다. 프로젝트 확인과 기존 배포 gate를 통과하면 첫 운영 배포부터 flag=true를 사용할 수 있다.

## dev → main → 게시 → review → 배포

1. 플랫폼과 Access·Document·AI·frontend의 feature PR을 각각 `dev` 대상으로 리뷰한다. CI, outbox rollback/retry/idempotency, 브라우저 allowlist와 수집 off를 확인한다. 플랫폼 PR만 통과했다고 이벤트 수집 완성을 선언하지 않는다.
2. 각 저장소 `dev` 검증 후 기존 branch 보호와 사용자 승인 범위에 따라 `dev → main` PR을 병합한다. 플랫폼 main에는 이 env 배선과 아래 release review가 필요하다. 이 작업자는 PR merge·deploy dispatch를 실행하지 않는다.
3. 서비스 main의 정확한 소스 SHA에 대한 push CI 성공을 확인한다. 기존 `Publish image release`는 15분 일정 또는 운영자의 수동 실행으로 5개 immutable 이미지 묶음을 게시한다. 이 단계는 배포가 아니다. release.json의 sources가 승인된 네 저장소 커밋이며 digest가 게시되었는지 확인한다.
4. `docs/releases/<release ID>.json`을 `review.example.json` 형식으로 추가한다. outbox 추가 릴리스는 `migration_mode=expand-only`, 실제 호환성 시험 URL과 복원 시험 URL을 포함한다. 초기화 모드를 사용하지 않는다. Document/Access Flyway 및 AI schema migration에 runtime grant가 실제 적용됐는지 검증한다.
5. `AWS_DEPLOY_CONFIG_JSON`에 `analytics_enabled`를 생략하거나 문자열 `"false"`로 두면 수집 off다. 프로젝트·토큰 확인과 mock 검증이 끝났으면 기존 사용자 승인 범위에서 문자열 `"true"`로 첫 배포할 수 있다. 운영자가 Deploy (EKS), main, action=deploy, 게시된 release_sha를 지정하고 feedback Environment review를 승인한다. AWS 인증 전 render, immutable digest, Secret readiness, DB preflight, migration, 변경 후 fingerprint, rollout, 업무 smoke, PDF smoke gate를 모두 통과해야 한다.
6. 이미 off로 성공 배포한 뒤 수집을 켜는 경우에는 프로젝트 확인, mock/staging 대조, Secret 병합 후 `"analytics_enabled": "true"`로 **새 release ID**를 배포한다. 기존 성공 release는 config와 manifest를 고정하므로 같은 ID에 flag만 바꿔 재배포할 수 없다. 서비스 소스 또는 게시 recipe 변경으로 새 release가 필요하며 gate를 우회하지 않는다. APP_VERSION은 이 release manifest의 각 서비스 source SHA이며 Next 재빌드용 `NEXT_PUBLIC_*` 토큰은 없다.
7. 활성화 뒤 이벤트 이름·건수·환경·app_version, outbox dead 수와 지연만 관찰한다. 본문/개인정보를 로그에 출력하지 않는다. 실제 운영 수집/라이브 E2E는 기존 사용자 승인 범위와 Environment gate에 따라 수행하며 본 PR의 오프라인 검증 결과와 구분한다.

긴급 중지는 승인된 운영자가 대상 Deployment의 `ANALYTICS_ENABLED=false`를 설정하고 rollout 완료를 확인한다(프론트 포함). 이것은 release 외 운영 변경이므로 기록하고 다음 정상 release에도 false를 반영해야 한다. 장기 비활성화는 새 release config=false로 고정한다. outbox 테이블과 기존 행은 삭제하지 않는다. 토큰을 비우는 경우에도 env refresh를 위한 Pod 재시작이 필요하다. 다시 true로 켜면 대기 이벤트가 재전송될 수 있으므로 이벤트 보존·재개 범위를 서비스 담당자와 확인한다.
