# 기존 설치의 PostHog 유지보수 전환

## 범위와 승인 경계

`maintenance-cutover`는 기존 설치에 실제 pending migration을 실행하는 **중단 배포**다.
DB reset, Flyway repair/baseline/clean, 성공 release 삭제, `initial-install` 재사용은 하지 않는다.
사용자의 기존 데이터 손실 허용을 `data_loss_accepted: true`로 검토에 기록하되,
가능한 데이터는 정상 migration으로 보존한다. 이 허용은 시험 결과나 백업이 존재한다는 뜻이 아니다.
기존 `expand-only`, `none`, 최초 설치와 동일 schema rollback의 계약은 유지한다.

2026-10-22 coordinator의 읽기 전용 운영 조사: Access V21, Document V60.
검토 dev는 Access V29, Document V82이며 Document V74/V75/V76/V80은 비가산 변경이다.
자세한 SQL 위험은 [소스 감사](posthog-deployment-compatibility.md)를 따른다.
이 문서는 수행 결과가 아니며 아직 실제 release SHA·복원 시험 URL을 제공하지 않는다.

이 worker는 production/Secret/main을 변경하지 않았다. primary가 운영 전환과 실제 리허설을 소유한다.
Access 개인키 / Document 공개키, RDS `verify-full` + CA, WAF 별도 Secret,
`enforce_human_mfa_only=false`를 변경하지 않는다. PostHog project/token은 primary가 선택·연결하며
analytics가 켜진 배포는 기존 토큰 preflight를 그대로 통과해야 한다.

## 검토 파일 계약

기존 `docs/releases/<release_sha>.json`을 사용한다. release SHA는 이미지 manifest의 ID이며 platform git SHA가 아니다.
`aws_release_safety.validate_review`가 아래 **정확한** 키 집합을 검사한다.

| 키 | 실제 입력 |
| --- | --- |
| `release_sha` | 게시·검증된 대상 이미지 release ID |
| `migration_mode` | `maintenance-cutover` |
| `expected_predecessor_release` | 보존할 현재 성공 release ID, 대상과 달라야 함 |
| `predecessor_record_sha256` | 이전 immutable ConfigMap의 **data 객체 전체**를 아래 canonical 함수로 해시 |
| `before_fingerprints` | access/document/ai 각각 중지 후 실제 preflight SHA256 |
| `after_fingerprints` | 동일 client 버전으로 실제 리허설에서 얻은 세 DB의 예상 schema SHA256 |
| `expected_live_images` | 모든 앱의 `Deployment/container` → 현재 `repository@sha256:digest` 매핑 |
| `maintenance_test_url` | 정확한 전후 소스·digest, pending SQL/checksum, 전환·검증 결과의 실제 GitHub 기록 |
| `restore_test_url` | 별도 로컬 PostgreSQL로 실제 논리 복원한 결과의 실제 GitHub 기록 |
| `quiescence_test_url` | downtime/drain·취소·replay 정책, 외부 writer 중지, 허용 손실 범위의 검토 기록 |
| `data_loss_accepted` | JSON boolean `true` |

URL은 FruitionKR의 실제 actions run / issue / PR만 허용한다. URL은 검토자의 증명이며
도구가 원격 내용을 읽어 진실성을 검증하지 않는다. 단위 테스트·빈 DB 설치 결과를 기존 DB 전환 증거로 제출하지 않는다.
이전 release fingerprint와 현재 fingerprint가 hotfix 때문에 다를 수 있다. 이전 기록은 수정하지 않고
전체 record digest, 실제 live image digest, 현재 before fingerprint를 별도로 묶는다.
태그만 있는 현재 Deployment는 **Pod imageID/ECR digest를 확인한 뒤**, 0 replicas 상태에서 같은 이미지를
`@sha256`로 고정한다. 소스 SHA나 태그가 실제 hotfix 이미지와 같다고 추정하지 않는다.

## 유료 리소스 없는 실제 리허설

기존 SSM runner에 Docker가 있다는 최초 가정은 폐기한다. coordinator의 2026-10-22 읽기 전용 확인은
`docker: not found`였고, 이 worker의 로컬 Docker는 사용 가능했다. primary는 다음 중 실제 가능한 경로를 선택한다.

1. 기존 로컬 Docker에서 linux/amd64 대상 digest로 리허설한다. VPC의 운영 조회/내보내기는 기존 SSM 경로를 사용한다.
2. 운영자가 기존 runner에 Docker를 준비하거나 이미 있는 containerd/nerdctl을 확인한 뒤 같은 격리 시험을 한다.
3. 여유가 검증된 기존 EKS node에 별도 namespace의 임시 DB를 배치한다. 운영 DB endpoint/Secret을
   시험 migration에 주입하지 않고 신규 유료 node/RDS/PVC를 만들지 않는다. 권한·용량 검증 전에는 이 경로를 가능하다고 기록하지 않는다.

최소 시험 입력/순서는 다음과 같다. primary가 결과 로그와 시간, 전체 이미지 digest, client `pg_dump --version`을 기록한다.

- 운영의 Flyway 성공 이력 **version/script/checksum/success** 전체, DB schema/ACL, 세 DB 크기와 extension 목록,
  현재 실행 이미지/JAR/소스 연결 증거를 확보한다. V21/V60 숫자만으로 이전 상태를 재현했다고 주장하지 않는다.
- 동일 PostgreSQL major/extension을 갖춘 외부 통신 차단 Docker internal network의 임시 DB와 **별도 복원 DB**를 사용한다.
  호스트 포트는 공개하지 않는다. 서비스별 migration/runtime/converter 계정을 저장소의 `infra/postgres/init-db-isolation.sh`로 생성한다.
  운영 비밀번호/개인키/API 키는 복제하지 않는다. SMTP/LLM/PostHog/S3 실제 호출은 차단한다.
- read-only 내보내기에서 얻은 schema와 데이터의 익명화 복원본을 사용한다. 대신 이전 정확한 migration 이력으로
  만든 합성 데이터를 쓰면 그 한계를 명시한다. 실제 데이터 의존 조건을 입증하지 못하면 운영 전환 승인 근거로 충분하지 않다.
- V74 legacy table, V75 진행 PDF, V76 진행 전사, V80 충돌/revision/outbox, 청구 원장, 문서 lineage의
  전후 행 수·내용 hash·참조·권한을 검증한다. 버릴 데이터도 종류/수량과 승인 범위를 명시한다.
- migration **직전** 각 DB를 `pg_dump -Fc`로 백업하고 ACL/role 정의도 비밀값 없이 보관한다.
  새 임시 PostgreSQL에 `pg_restore --exit-on-error`로 실제 복원한다. row/hash/ACL과 접근 격리를 다시 검사한다.
- 게시된 실제 이미지와 production migration entrypoint를 사용한다. 렌더된 Job 순서대로
  **Access → AI → Document**를 실행한다(현재 Kustomize 정렬). 서비스 내부 Flyway 순서는 실제 pending 이력이다.
  Access/Document: 해당 digest 이미지의 기본 entrypoint에 `--migrate-only`;
  AI: pipeline-api digest에서 `python -m app.modules.wiki_ingestion.infrastructure.migrate_ai_schema`.
  환경 키는 `k8s/overlays/aws/migration-jobs.yaml`을 따른다. AI에는 `AI_DB_CONVERTER_ROLE=ai_converter`를 제공한다.
- 로컬 TLS도 CA/SAN과 DB hostname이 맞는 인증서를 발급하고 `verify-full`을 사용한다.
  운영 RDS CA 연결 시험은 별도의 운영 read-only preflight 근거이며 로컬 인증서를 RDS CA 검증으로 표현하지 않는다.
- 각 migration 뒤 실패를 주입한 별도 복제본에서 이전 백업을 **다른 임시 DB로** 복원하여 실행시간·일관성을 확인한다.
  이미 변경된 DB에 구 앱을 시작하거나 Flyway 이력을 지워 복구하지 않는다. target 이미지를 재실행해 멱등성도 확인한다.
- 전후 fingerprint는 `aws_deploy.preflight_job`과 같은 PostgreSQL 16 client/schema-only/no-owner/no-privileges 및
  restrict token 제거로 계산한다. 이 fingerprint는 **데이터·ACL hash가 아니다**. 데이터/권한 검증을 별도로 첨부한다.
- 새 앱의 로그인/refresh/RSA 거부, DB 최소 권한, 문서·AI/PDF/전사 처리, queue drain/replay/중복 방지 및
  analytics off 또는 로컬 수신기로 검증한다. 중단 방식이므로 구/신 혼합 운영 호환성을 주장하지 않는다.

기존 [최초 설치 리허설](backlog/deployment-checks/2026-09-18-image-db-rehearsal.md)은 절차 참고일 뿐 이번 증거가 아니다.
논리 복원은 RDS snapshot/PITR·객체 버전 복원 시험이 아니다. 사용자 손실 허용 하에서는 이 중단 경로의 최소
복구 근거를 실제 로컬 논리 복원으로 검토할 수 있지만, 복원 불가능한 객체/queue 데이터와 허용 RPO/RTO를 명시해야 한다.

## primary 실행 절차

아래 명령은 worker가 실행하지 않은 운영 명령이다. `SHA`, `RUN_DIR`, `PREDECESSOR`는 운영자가 검증한 값으로 설정한다.
외부 secret/배포 입력은 보호된 runner 파일로 두며 공개 저장소에 실제 endpoint/계정 정보를 커밋하지 않는다.
기존 main workflow의 environment 승인, OIDC, 이미지 검증, 배포 concurrency를 사용한다. 별도 동시 deploy/스케줄러를 중지한다.

```bash
rtk proxy python scripts/aws_image_release.py fetch --release "$SHA" --output "$RUN_DIR/release.json"
rtk proxy python scripts/aws_image_release.py verify --release "$SHA" --manifest "$RUN_DIR/release.json"
rtk proxy python scripts/aws_deploy.py render --config "$RUN_DIR/deploy-config.json" --sha "$SHA" --manifest "$RUN_DIR/release.json" > "$RUN_DIR/target.yaml"
rtk proxy kubectl -n fruition get configmap "fruition-release-$PREDECESSOR" -o json > "$RUN_DIR/predecessor.json"
rtk proxy kubectl -n fruition get deployments,ingresses,scaledobjects,horizontalpodautoscalers -o json > "$RUN_DIR/before-workloads.json"
```

먼저 maintenance Ingress를 기존 Ingress의 name/namespace/annotations/spec을 보존해서 작성한다.
모든 `rules[].http.paths[].backend`와 `defaultBackend`를 아래 service로 바꾼다.
`alb.ingress.kubernetes.io/actions.maintenance` annotation의 JSON은 정확히 아래 fixed response다.
인증서/WAF/접근 로그/SSL redirect annotation은 그대로 유지한다.

```json
{"service":{"name":"maintenance","port":{"name":"use-annotation"}}}
```

```json
{"type":"fixed-response","fixedResponseConfig":{"contentType":"text/plain","statusCode":"503","messageBody":"Maintenance"}}
```

운영자는 검토한 maintenance Ingress를 적용하고 Access/API/app의 HTTPS `/`가 503인지 확인한다.
Ingress 제거/빈 DNS/우연한 backend 장애를 점검 응답으로 대신하지 않는다.
기존 TargetGroupBinding이 모두 제거될 때까지 기다린다(도구도 검사). 이 중단 모드는 ALB binding 없이
새 Pod의 앱 readiness를 먼저 확인하고 정상 Ingress 복구 후 binding·공개 경로·업무 smoke를 확인한다.
일반 무중단 배포의 Pod admission 전 ALB binding 순서는 변경하지 않는다.
queue/background 작업의 완료·취소·폐기 정책을 수행하고 결과/offset/outbox를 기록한다.

```bash
rtk proxy kubectl -n fruition apply -f "$RUN_DIR/maintenance-ingress.yaml"
# 먼저 전체 기존 scaler manifest를 보관한다. 제거 권한은 플랫폼 운영자 소유다.
rtk proxy kubectl -n fruition get scaledobjects,horizontalpodautoscalers -o yaml > "$RUN_DIR/scalers-before.yaml"
rtk proxy kubectl -n fruition delete scaledobjects --all --wait=true
rtk proxy kubectl -n fruition delete horizontalpodautoscalers --all --wait=true
```

앱 Deployment 각각을 `kubectl patch deployment NAME --type=merge -p '{"spec":{"replicas":0}}'`로 중지한다.
`target.yaml`의 Deployment inventory 전부(현재 12개)가 대상이며 Strimzi `kafka-entity-operator`는 제외한다.
스케줄러/wake automation/외부 DB writer도 중지한다. CronJob이 하나라도 있으면 별도 검토 후 제거해야 gate를 통과한다.
기존 Job은 완료/중지하고 terminationGracePeriod가 긴 worker까지 모든 앱 Pod가 사라질 때까지 기다린다.
KEDA paused annotation만으로 대체하지 않는다. paused-replicas=0이 새 worker rollout도 막을 수 있기 때문이다.

현재 DB fingerprint 수집에는 기존 preflight Job 실행 권한이 필요하다. production SQL을 쓰지는 않지만 Kubernetes Job을 생성한다.
아래 Python을 보호된 환경에서 실행해 실제 JSON을 저장한다(`RUN_DIR` 환경변수 export 필요).

```bash
rtk proxy python - <<'PYCODE'
import json, os, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
import aws_deploy
from aws_maintenance import digest
p = Path(os.environ['RUN_DIR'])
config = json.loads((p / 'deploy-config.json').read_text())
(p / 'before-fingerprints.json').write_text(json.dumps(aws_deploy.fingerprints(config, require_quiescent=True)))
previous = json.loads((p / 'predecessor.json').read_text())
(p / 'predecessor-data.sha256').write_text(digest(previous['data']) + '\n')
PYCODE
```

live Deployment/container digest inventory는 pinning과 중지 후 다시 수집한다.
실제 리허설 after fingerprint와 근거 URL을 채운 release review를 검토·커밋한 후 기존 workflow의 `deploy`로 실행한다.
직접 실행이 필요한 경우도 같은 권한·동시 실행 방지·이미지 확인과 환경 승인 하에 아래 동일 entrypoint를 사용한다.

```bash
rtk proxy python scripts/aws_deploy.py deploy --config "$RUN_DIR/deploy-config.json" --sha "$SHA" --manifest "$RUN_DIR/release.json" --review "docs/releases/$SHA.json"
```

도구는 predecessor 전체 기록/이미지, 503 route, Deployment observedGeneration와 zero replicas,
앱 Pod/Job 부재, scaler/CronJob 부재, DB 사용자 세션 부재를 검사한다.
시작 기록 `fruition-maintenance-<SHA>-started`는 immutable **create**로만 생성한다.
기반 설정 적용 후 before fingerprint를 다시 비교하고 매 migration 전 writer·DB 세션을 다시 검사한다.
실제 pending migration 후 after fingerprint가 다르면 앱을 시작하지 않는다.
모든 새 앱 rollout이 준비된 뒤 정상 Ingress를 복구하고 기존 HTTP·인증 업무 smoke를 통과해야 성공 release를 남긴다.

성공 뒤에도 ScaledObject/HPA를 자동 복구하지 않는다. 기존 workflow의 PDF smoke와 보안/analytics 설정 검증까지
마친 후 **target.yaml에서** TriggerAuthentication/ScaledObject/HPA만 추출해 적용한다(과거 scaler 버전 복원 아님).
normal same-schema `none` 재배포도 기존 fingerprint gate를 통과하면 scaler를 복구할 수 있으나 새 검토 파일을 사용한다.

## 실패와 남은 차단 조건

- migration/rollout/smoke 예외 시 maintenance Ingress를 다시 적용하고 모든 앱 replicas=0을 요청한다.
  `-failed` immutable 기록은 containment가 `requested`인지 `unverified`인지 남긴다. 성공이라고 주장하지 않는다.
- SIGKILL/호스트 종료/네트워크 단절은 cleanup을 실행하지 못할 수 있다. `-started`만 남아도 성공 release가 없으면
  **모든 모드의 후속 deploy/bootstrap/rollback을 차단**한다. 운영자가 503, 실제 Pod 종료, DB session을 직접 확인한다.
- 기존 성공 기록, 시작/실패 기록을 삭제·수정해서 재시도하지 않는다. 부분 Flyway 상태·AI transaction·after schema를
  조사하고 검증된 forward repair 또는 실제 복원 계획을 별도 검토한다. 자동 retry/repair/resume 플래그는 제공하지 않는다.
- 일반 rollback의 이전 fingerprint 불일치 차단은 그대로다. maintenance 손실 허용이 구 HMAC 이미지나 TLS 완화를 허용하지 않는다.
- 아직 필요한 실제 입력: exact release 이미지와 pending checksum, 현재 predecessor record/live digest,
  전후 DB fingerprint, 실제 restore/maintenance/quiescence 근거, 외부 writer/queue 정책, 새 앱 smoke 결과.
- runner Docker 부재는 사실이다. primary가 실제 격리 시험 환경을 확정해야 한다. 이 PR의 단위/로컬 PostgreSQL 시험은
  운영 데이터 migration 리허설을 대신하지 않는다. worker는 production mutation이나 실제 analytics 이벤트를 수행하지 않았다.
