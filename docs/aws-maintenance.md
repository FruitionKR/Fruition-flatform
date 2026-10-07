# 안전하게 배포하고 점검하기

이 문서는 보안·재배포·복구 설정의 적용 순서입니다. RDS Multi-AZ, Redis 복제, Kafka 3노드, AZ별 NAT 증설은 이번 변경에 포함하지 않았습니다. 따라서 DB·Kafka·Redis의 점검이나 장애까지 무중단으로 만드는 구성은 아닙니다.

## 무엇이 자동으로 늘어나나요?

| 대상 | 현재 동작 | 상한 |
|---|---|---|
| ALB | 요청을 준비된 Pod에 나누어 전달 | 앱 서버 수를 직접 늘리지 않음 |
| 인증·문서·Pipeline API | 평소 각각 2개 Pod, 롤링 배포 중 임시 1개 추가. HPA가 CPU 평균 70% 기준으로 조절 | 각각 2~4개 Pod |
| 수집·질의·에이전트 작업자 | KEDA가 Kafka의 미처리 메시지 수를 보고 조절 | 각각 1~4개 Pod |
| 유지보수 작업자 | KEDA가 Kafka 대기 작업을 보고 조절 | 1~2개 Pod |
| EC2 일반 노드 | Cluster Autoscaler가 자원 부족으로 배치되지 못한 Pod를 보고 조절 | 최소 2대, 최대 5대 |
| EC2 AI 노드 | 같은 방식, CPU Spot 사용 | 최소 0대, 최대 4대 |

API HPA(`k8s/overlays/aws/api-autoscaling.yaml`)는 metrics-server의 CPU 사용률만 보며, 요청 수나 응답 시간으로는 늘어나지 않습니다. 실제 확장 동작은 부하 시험으로 확인해야 합니다. AI 작업 Pod가 늘어나도 EC2 최대치에 도달하면 대기할 수 있습니다. CloudWatch는 관측·알림용이며 HPA와 연결되지 않습니다. 일반 노드는 평소 2~4대이고, 롤아웃 중 Pending Pod가 생기면 상한인 5대까지 늘어나 비용이 증가할 수 있습니다. 유휴 노드는 Cluster Autoscaler가 다시 줄입니다. 단, emptyDir를 쓰는 Pod가 있는 노드는 기본 설정상 줄이지 않습니다. metrics-server에는 `cluster-autoscaler.kubernetes.io/safe-to-evict: "true"`를 붙여 이 제약을 풀었습니다(`infra/terraform/eks.tf`). converter는 변환 도중 중단 위험이 커서 붙이지 않았으므로, converter가 있는 AI 노드는 줄어들지 않습니다.

## 배포할 때 어떤 Pod가 교체되나요?

schema 3 이미지 릴리스는 서비스별 digest로 Deployment·Job 이미지를 고정합니다([이미지 릴리스](aws-image-releases.md)). 이전 배포와 같은 digest이고 설정도 같은 서비스는 Pod template이 바뀌지 않아 재시작되지 않습니다. 이미지가 바뀐 서비스만 롤링 교체됩니다. pipeline 이미지를 쓰는 AI Pod들(pipeline-api, pipeline-agent-worker, 수집·질의·에이전트·유지보수 작업자, edit-event-consumer, embedding-server)은 함께 교체됩니다.

- 배포 로그의 `image changed: <이름>`/`image unchanged: <이름>`은 현재 cluster의 Deployment 이미지와 비교한 안내입니다. 비교가 실패해도 배포를 막지 않으며, 설정(ConfigMap 등) 변경으로 인한 교체는 이 목록에 나오지 않습니다.
- migration Job과 DB·smoke 검사는 교체 여부와 관계없이 기존 순서대로 실행됩니다.
- schema 3으로 처음 배포할 때는 이미지 참조 형식이 태그에서 digest로 바뀌므로 모든 Deployment가 한 번 교체됩니다.
- schema 1·2 릴리스로 rollback하면 이전처럼 릴리스 ID 태그를 쓰므로 모든 Deployment가 다시 교체됩니다.
- ECR은 서비스별로 최근 이미지 60개만 보존합니다(`b-` 빌드 태그·이전 릴리스 태그 포함). 실행 중인 digest와 rollback 대상 digest가 이 범위 안에 있어야 재배포·rollback 검증이 통과합니다. 자주 바뀌는 서비스일수록 오래된 rollback 후보가 먼저 만료됩니다.

## 처음 적용할 순서

이미지 자동 게시 설정과 버전 선택·승인 절차는 [이미지 릴리스 안내](aws-image-releases.md)를 따릅니다. 서비스 main CI 성공 후 정기 게시하며, 운영자가 게시된 릴리스 ID를 선택해 기존 배포 workflow를 실행합니다.

1. Terraform 변경을 새로 plan하고 내용을 확인해 apply합니다. 이전 저장 plan에는 이번 변경이 없습니다.
2. Access·Document·AI pipeline·converter의 비관리자 실행 변경과 AI Kafka TLS 지원 변경을 포함한 네 이미지를 새 release SHA로 게시합니다. 변경 위치는 각 서비스 Dockerfile과 별도 `Fruition-ai` 저장소의 `pipeline/app/core/kafka_security.py`, worker 연결 코드입니다. 이전 AI 이미지를 그대로 사용하면 TLS Kafka에 접속하지 못합니다.
3. 플랫폼 관리자로 `scripts/aws-platform-up.sh install <terraform-outputs.json>`을 실행합니다. Namespace 보안·ALB readiness 라벨, Kafka/KEDA CRD 및 배포 RBAC를 앱보다 먼저 적용합니다.
4. `feedback` GitHub Environment의 배포 입력을 준비합니다. 기존 `AWS_DEPLOY_CONFIG_JSON`, `AWS_DEPLOY_ROLE_ARN` 외에 아래 검증 계정 값을 추가합니다.
5. 검토 기록 JSON을 `docs/releases/<release_sha>.json`으로 추가하고 main에서 검토합니다.
6. 배포 workflow를 실행하고 Environment 승인 단계에서 검토 후 승인합니다.

기존 평문 Kafka를 사용 중이라면 TLS로 바꾸는 첫 전환에는 점검 시간을 확보하세요. Kafka는 여전히 1개이며 listener 변경·클라이언트 교체를 완전 무중단으로 보장하지 않습니다. 새 인프라에는 처음부터 TLS를 사용합니다.

| GitHub feedback 값 | 종류 | 용도 |
|---|---|---|
| `AWS_SMOKE_EMAIL` | Secret | 검증 전용 계정 이메일 |
| `AWS_SMOKE_PASSWORD` | Secret | 검증 전용 계정 비밀번호 |
| `AWS_SMOKE_WORKSPACE_ID` | Variable | 검증 전용 workspace ID (`ws_`로 시작) |

사용자가 직접 검증 계정의 이메일 인증과 workspace 준비를 마쳐야 합니다. 검증용 계정에는 실제 업무 데이터 접근권한을 주지 마세요. 최초 설치는 workflow의 `bootstrap`을 선택합니다. 이 모드는 기존 앱 Deployment가 없을 때만 허용하며, API 준비까지만 확인하고 성공 release를 기록하지 않습니다. 초기 화면에서 계정/workspace를 만든 뒤 위 값을 등록하고 같은 SHA로 `deploy`를 실행해 업무 검증을 완료합니다. 첫 설치가 DNS 연결·노드 준비 등의 이유로 부분 실패하면 같은 SHA와 같은 설정으로 `bootstrap`을 재시도할 수 있습니다. 최초 설치 표식과 모든 앱 이미지 SHA를 대조하며, 성공 release가 한 번이라도 있으면 거부합니다. 다른 SHA로 일반 운영 검증을 우회할 수 없습니다.

검증은 로그인 → 작은 Markdown 문서 생성 → 조회 → AI ingest 완료 확인 → 생성 문서 휴지통 이동 순서입니다. AI API 사용료가 소량 발생할 수 있습니다. 실패·시간초과에도 자신이 생성한 문서만 정리하며, AI가 만든 Wiki 자료는 검증 workspace에 남을 수 있으므로 주기적으로 확인하세요. 업무 검증은 readiness gate나 전체 부하·장애 시험을 대체하지 않습니다.

## DB 변경 검토와 실패 처리

검토 파일은 [예제](releases/review.example.json)를 복사합니다. 예제의 자리표시는 그대로 배포할 수 없습니다.

- `release_sha`: 실제 네 이미지에 붙인 같은 SHA입니다.
- `migration_mode`: 운영 변경은 `expand-only` 또는 `none`을 사용합니다. `none`이면 migration Job을 생략하고, `expand-only`이면 기존 앱과 호환되는 추가 변경만 실행합니다. 컬럼 삭제·이름 변경·즉시 NOT NULL 강제 등 파괴적 변경은 별도 점검 릴리스로 분리합니다.
- `compatibility_test_url`: 변경 후 DB에서 이전 버전과 새 버전의 로그인·문서·AI 흐름이 동작한 실제 시험 기록입니다. 새 빈 DB에서 migration 성공만 확인해서는 부족합니다. 데이터가 많은 복제 DB에서 잠금·실행시간도 확인하세요.
- `restore_test_url`: 최근 별도 DB 복원 시험 기록입니다. 최초 배포는 시험용 DB 백업·복원으로 절차를 먼저 검증할 수 있습니다.

최초 설치는 `docs/releases/review.initial.example.json`의 `initial-install` 형식을 사용합니다. `compatibility_test_url` 대신 `installation_test_url`에 실제 게시 이미지의 빈 DB 마이그레이션·재실행 시험 기록을 적고, `restore_test_url`에는 별도 DB 복원 시험 기록을 적습니다. 과거 SQL 이력을 실행하는 첫 설치를 운영 DB의 expand-only 변경으로 표시하지 않습니다.

- `bootstrap`은 성공 release와 기존 앱이 없는 환경에서 DB 3개의 소유권·권한과 빈 상태를 검사합니다. 빈 상태는 public 테이블뿐 아니라 함수·타입, 별도 사용자 schema, plpgsql 외 extension 부재까지 확인합니다. 초기화된 DB·계정·권한은 먼저 준비해야 합니다.
- 세 DB가 모두 통과한 뒤 immutable `fruition-bootstrap` 기록에 SHA·설정·렌더된 manifest를 고정합니다. 중간 실패는 이 값들이 모두 같을 때만 재시도할 수 있습니다. 빈 DB 검사 실패 시 migration이나 최초 설치 기록을 만들지 않습니다. 사전검사를 위한 Secret·ServiceAccount·NetworkPolicy는 적용될 수 있습니다.
- API 준비까지 통과하면 immutable `fruition-bootstrap-ready`에 schema fingerprint를 남깁니다. 아직 성공 release는 아닙니다. 이 시점부터 `bootstrap` 대신 같은 SHA로 `deploy`합니다.
- 검증 계정·workspace 설정 후 실행하는 `deploy`는 완료 기록과 현재 DB schema를 대조하며 migration을 다시 실행하지 않습니다. 실제 로그인·문서·AI smoke를 통과해야 성공 release를 기록합니다. smoke 실패는 같은 SHA로 재시도할 수 있습니다.
- 다른 성공 release, 다른 이미지·설정·manifest 또는 DB schema 변경이 있으면 이 최초 설치 경로로 넘어갈 수 없습니다. 기존 방식으로 생성한 bootstrap 기록은 빈 DB 검증 증거로 인정하지 않습니다. 기록을 삭제해 우회하지 말고 별도 점검해야 합니다.

Access 상태 확인이 정상 HTTP 200이어도 SMTP 등의 응답을 포함해 기본 1초를 초과할 수 있어 AWS probe timeout을 5초로 지정합니다. 이미 이전 manifest로 시작한 미완료 최초 설치는 검토 후 workflow의 `bootstrap_probe_recovery`를 명시적으로 선택해야 합니다. 이 복구는 Access의 startup/readiness/liveness `timeoutSeconds`가 1(또는 생략)에서 5로 바뀌는 것만 허용합니다. 이미지·경로·자원·설정·다른 workload 변경은 거부합니다. 원본 `fruition-bootstrap`을 수정·삭제하지 않고 immutable `fruition-bootstrap-probe-recovery`에 원본과 복구 manifest를 기록합니다. 이후 같은 복구 manifest 재시도와 `deploy` 승격은 이 기록을 대조합니다. 준비 완료·성공 release가 있는 환경에서는 복구 옵션을 사용할 수 없습니다.

Access의 AWS health에서는 `MANAGEMENT_HEALTH_MAIL_ENABLED=false`로 SMTP 인증을 제외합니다. Pod와 ALB가 상태 확인마다 SMTP 로그인을 반복해 계정 제한과 서비스 재시작을 일으키지 않도록 하기 위함입니다. DB·Redis health와 실제 SMTP 발송 설정은 유지합니다. API 준비/업무 smoke 통과가 메일 발송 성공을 보장하지 않으므로, SMTP 제한 해제 후 사용자 주도로 실제 인증 메일 발송을 별도 확인해야 합니다.

이 변경 전 manifest로 시작한 미완료 최초 설치는 `bootstrap_mail_health_recovery`만 선택합니다(`bootstrap_probe_recovery`는 선택하지 않음). 이미지·SMTP 자격 증명·다른 health 설정은 바꿀 수 없으며 Access env에 위 한 항목을 추가하는 변경만 허용합니다. 기존 probe 복구 기록이 있으면 그 결과를 원본으로 이어서 immutable `fruition-bootstrap-mail-health-recovery`에 저장합니다. 최초 기록과 이전 복구 기록을 삭제하거나 수정하지 않습니다. 원본 연결·SHA·설정·허용 변경을 모두 대조한 후 동일 manifest 재시도와 업무 검증 승격을 허용합니다.

URL은 `FruitionKR`의 GitHub Actions 실행·이슈·PR 기록을 사용합니다. 스크립트는 형식과 SHA를 검사하지만, 링크 안의 주장이 사실인지나 SQL 호환성을 자동 증명하지는 않습니다. Environment 승인자가 실제 결과를 확인해야 합니다.

### 준비 완료 후 OAuth 연결 변경으로 최초 deploy가 차단된 경우

bootstrap 준비 완료 이후 Google·Naver·Kakao OAuth Secret 연결 6개가 추가되면 같은 이미지 SHA라도 manifest가 달라 최초 업무 검증이 차단됩니다. 이 경우 `Deploy (EKS)`에서 `action=deploy`, **기존 bootstrap의 release SHA**와 `bootstrap_oauth_recovery=true`를 선택합니다. probe/mail 복구 옵션은 선택하지 않습니다. 새 이미지 릴리스로 실행하거나 `bootstrap`을 다시 실행하는 복구가 아닙니다.

이 옵션은 `fruition-access` ExternalSecret에 `GOOGLE_CLIENT_ID/SECRET`, `NAVER_CLIENT_ID/SECRET`, `KAKAO_CLIENT_ID/SECRET`를 `fruition/app`의 같은 이름 property로 연결하는 6개 항목의 추가만 허용합니다. 연결 대상·기존 Secret 항목·이미지·워크로드·배포 설정이 함께 바뀌면 거부합니다. 실제 자격 증명 값은 복구 기록에 넣지 않습니다.

기존 bootstrap, probe/mail 복구 이력, 준비 완료 기록은 수정·삭제하지 않습니다. 원본 연결과 SHA·설정·현재 DB schema를 확인한 뒤 immutable `fruition-bootstrap-oauth-recovery`를 추가하고, migration을 재실행하지 않고 rollout·로그인·문서·AI smoke를 수행합니다. 실제 smoke가 성공해야 성공 release가 기록됩니다. 실패한 경우 같은 입력으로 재실행할 수 있으며, 기록이 있으면 옵션을 생략해도 기록을 검증합니다. 성공 release가 있는 환경에서는 복구 옵션을 다시 사용하지 않습니다.

`최초 설치 manifest가 다릅니다`는 health 문제에만 해당하는 메시지가 아닙니다. 실제 리소스 차이를 먼저 확인하고 해당 복구 경로를 선택해야 합니다. 설치 기록을 지우거나 검사를 생략해 해결하지 않습니다.

온라인 DB 변경은 **새 컬럼 추가 → 호환 코드 배포 → 데이터 이전 → 이후 릴리스에서 옛 컬럼 제거**로 나눕니다. 실행 중 앱이 계속 DB를 사용하므로 호환 변경도 긴 테이블 잠금을 만들면 안 됩니다.

실패하면 이후 단계를 멈추고 성공 release를 기록하지 않습니다. AWS OIDC 인증 이후 실패는 기존 운영 SNS → Lambda → Discord로 알립니다. AWS 인증 전 실패나 알림 전송 자체의 실패는 GitHub Actions에서 확인해야 합니다. Discord 웹훅 Secret 등록과 실제 수신 시험은 별도로 필요합니다.

코드 rollback은 기존 성공 release와 실제 DB schema fingerprint가 같을 때만 가능합니다. 보안 보호 적용 전 저장된 release는 재사용하지 않습니다. DB가 바뀌었으면 호환되는 수정 릴리스를 우선 고려하고, 무조건 DB를 과거로 되돌리지 마세요. 자동 DB rollback은 하지 않습니다.

## 복원 연습과 실제 복구

1. Terraform으로 만든 RDS의 자동 백업과 가장 최근 복원 가능 시점을 확인합니다. 두 DB의 시각 차이와 Kafka·S3에 이미 반영된 작업도 고려합니다.
2. 선택한 백업/시점으로 **다른 이름의 비공개 RDS**를 복원합니다. 실제 운영 DB에 덮어쓰지 않습니다. 복원에는 추가 비용과 시간이 듭니다.
3. 별도 시험 네트워크·앱에서 DB 사용자/권한·스키마·데이터, 로그인·문서·AI 작업을 확인합니다. 시험 앱이 운영 Kafka/S3에 쓰지 않도록 격리합니다.
4. 복원 소요시간, 복원 시점, 검증 결과, 데이터 손실 범위를 GitHub 기록에 남깁니다. 시험 DB 정리는 보존할 데이터가 없는지 확인한 뒤 수행합니다.
5. 실제 사고에서는 쓰기·작업 소비 중단 여부와 복구 시점을 결정한 후 복원 DB로 endpoint/Secret을 전환합니다. 앱 연결 재수립과 메시지 재처리·중복 처리를 확인합니다. 이 절차는 점검 시간이 필요할 수 있습니다.

이 저장소는 실제 DB를 생성하거나 복원 시험을 실행했다는 증거를 대신 만들지 않습니다.

## 의미 검색(BGE-M3) 켜기와 기존 위키 임베딩

질의·에이전트·유지보수 작업자만 `QUERY_EMBEDDING_MODE=bge-m3`로 실행합니다. 나머지 AI Pod는 `fruition-config`의 `text-only`를 유지합니다. 모델(약 2.1GB)은 `fruition-pipeline` 이미지에 들어 있고(`HF_HOME=/opt/huggingface`, `HF_HUB_OFFLINE=1`) Pod가 뜰 때 Hugging Face에서 받지 않습니다. 같은 이미지를 쓰는 AI Pod들이 이미지 레이어를 공유하므로 노드 디스크에는 한 번만 저장됩니다. 롤아웃 중 구·신 이미지가 함께 있는 순간을 버티도록 노드 루트 디스크는 30GiB(gp3)로 지정합니다(`infra/terraform/eks.tf`의 `block_device_mappings`).

세 작업자는 메모리를 2.5Gi 요청하고 3.5Gi까지 씁니다. BGE-M3를 배치 1로 계산하면(Fruition-ai #22) 최고치가 약 2.5GB입니다. 모델을 넣은 이미지(Fruition-ai #23)와 배치 1 코드가 먼저 배포돼야 합니다. 배치 16이던 이전 코드는 긴 문서에서 5GB를 넘습니다.

AI 노드의 상시 Pod(질의·에이전트·유지보수·수집 작업자 각 1개, embedding-server, converter, edit-event-consumer, pipeline-agent-worker)는 요청 합계가 CPU 3.25 vCPU·메모리 약 13.1GiB입니다. xlarge 1대(4 vCPU/16GiB)의 할당 가능량에 가까워 DaemonSet 요청까지 더하면 1대에 다 들어가지 않을 수 있고, 그러면 평소에도 AI 노드 2대가 켜집니다. 실제 배치는 `kubectl describe node`의 Allocated resources로 확인합니다. KEDA가 질의·에이전트 작업자를 늘리면 AI 노드 상한(2대)에 닿아 Pod가 대기할 수 있습니다.

### 임베딩 서버(embedding-server)

질의·에이전트 작업자는 질문 임베딩을 `embedding-server`(복제본 1개, 메모리 요청 3Gi, 한도 4Gi)에 `EMBEDDING_SERVICE_URL=http://embedding-server:8000`으로 요청합니다([ai ADR-0026](https://github.com/FruitionKR/Fruition-ai/blob/main/docs/adr/0026-embedding-server.md)). 서버는 짧은 텍스트만 받고, 긴 페이지 임베딩은 유지보수 작업자가 계속 직접 계산합니다. 서버는 `/health`가 모델 적재 완료 시에만 200이라 `startupProbe`가 최대 5분 기다립니다. NetworkPolicy는 질의·에이전트 작업자에서 8000번 포트로 오는 요청만 허용합니다.

전환 직후에는 질의·에이전트 작업자의 2.5Gi 메모리 패치를 그대로 둡니다. 운영에서 질문 지연과 오류율을 확인한 뒤 패치를 제거해야 메모리가 줄어듭니다. 서버가 재시작되는 동안에는 질문 임베딩이 실패하므로, 문제가 생기면 두 작업자에서 `EMBEDDING_SERVICE_URL`을 빼면 각자 모델을 올리던 이전 동작으로 돌아갑니다.

### 기존 위키 임베딩 채우기

`text-only`로 운영하던 동안 편입한 페이지에는 페이지 임베딩 행이 없어 자동 재처리 대상이 아닙니다. 유지보수 작업자는 시작할 때 `pending`·`failed` 행을 자기 프로세스의 모델로 다시 계산합니다. 그래서 빈 페이지를 `pending`으로 표시한 뒤 작업자를 재시작합니다. 표시 명령은 모델을 올리지 않으므로 작업자 메모리에 영향이 없습니다.

```bash
kubectl -n fruition exec -i deploy/maintenance-task-worker -- python - <<'PY'
from app.modules.wiki_ingestion.infrastructure import postgres_wiki_ingestion_repository as database

with database.connect() as conn:
    marked = conn.execute("""
        INSERT INTO wiki_page_embeddings
            (page_id, embedding_model, representation_hash, embedding_vector, embedding_dimension, status)
        SELECT page.id, 'BAAI/bge-m3', 'backfill', '{}', 0, 'pending'
        FROM wiki_pages page
        WHERE page.status = 'active'
          AND NOT EXISTS (
              SELECT 1 FROM wiki_page_embeddings embedding
              WHERE embedding.page_id = page.id AND embedding.embedding_model = 'BAAI/bge-m3'
          )
    """).rowcount
print("pending으로 표시한 페이지", marked)
PY
kubectl -n fruition rollout restart deploy/maintenance-task-worker
```

재시작한 작업자 로그에서 `wiki page embedding job completed run_id=pending-recovery`를 확인합니다. 페이지의 근거 단위 벡터도 같은 작업에서 채워집니다. 실패가 남으면 `wiki_page_embeddings.status = 'failed'`로 기록되고, 작업자가 다시 시작하거나 다음 임베딩 작업이 돌 때만 재시도합니다. 실패 수가 0이 될 때까지 재시작을 반복합니다.

## Jev 선택 판단 켜기

AI는 Agent 라우팅·질의 근거 선택·ingest 개념 병합을 TypeSafe Jev로 판정할 수 있습니다([Fruition-ai ADR-0027](https://github.com/FruitionKR/Fruition-ai/blob/main/docs/adr/0027-jev-selective-judge.md)). `fruition-config`의 `JEV_ROUTING_ENABLED`·`JEV_EVIDENCE_ENABLED`·`JEV_CONCEPT_MERGE_ENABLED`는 기본 `false`입니다. 켜도 `TYPESAFE_API_KEY`가 비어 있거나 크레딧 소진·호출 실패가 나면 해당 요청은 기존 경로로 처리됩니다.

1. **배포 전(필수).** Secrets Manager `fruition/app`에 `TYPESAFE_API_KEY` 속성을 추가합니다. 아직 키가 없으면 빈 문자열로 둡니다. `fruition-pipeline` ExternalSecret이 이 속성을 읽으므로, 속성이 없으면 AI Secret 동기화 전체가 실패해 배포가 멈춥니다. 기존 Secret은 Terraform `ignore_changes` 때문에 apply로 키가 추가되지 않으니 콘솔/보안 입력 경로로 이 속성만 추가합니다.
2. **키 입력.** 크레딧을 준비한 뒤 `TYPESAFE_API_KEY`에 실제 키를 넣습니다. ExternalSecret 갱신(최대 1시간)을 기다리거나 강제 동기화한 뒤 AI Pod를 재시작해야 새 값을 읽습니다.
3. **경로별 켜기.** `k8s/base/configmap.yaml`에서 켤 경로의 값만 `"true"`로 바꿔 배포합니다. 경로마다 평가 근거의 강도가 달라 하나씩 켜고 사용량(`GET /usage/models`의 provider `typesafe`)과 품질을 확인합니다.

402(크레딧 소진)·401/403(키 오류)를 받으면 각 Pod가 `JEV_BLOCK_SECONDS`(기본 600초) 동안 Jev 호출을 건너뛰고 기존 경로만 씁니다. 끄려면 해당 설정을 `"false"`로 되돌려 배포합니다.

## 노드·EKS 버전 점검

API는 평소 각 2개 Pod(HPA 2~4개)이며 `maxUnavailable: 0`, `maxSurge: 1`로 교체합니다. 노드 점검은 PDB가 최소 1개 Pod를 보호합니다. ALB Service/Ingress와 TargetGroupBinding을 먼저 만들고 Pod를 생성해 readiness gate가 주입되게 합니다. ALB Pod webhook 실패 시 새 Pod 생성을 막아 gate 없이 배포가 진행되지 않도록 합니다. 이미 있는 Pod에는 자동 주입되지 않으므로 최초 전환의 재배포 후 실제 Pod의 gate와 ALB target 상태를 확인하세요.

종료유예 60초에는 신규 요청 차단을 기다리는 10초와 Spring 종료 대기 40초가 포함됩니다. 긴 SSE/AI 작업의 완주를 보장하지 않습니다. 클라이언트 재연결, 작업 재시도·중복 방지와 Spot 회수 처리를 실제 서비스에서 시험하세요.

EKS 업그레이드는 Terraform `cluster_version`, 애드온 버전, `scripts/aws-platform-up.sh`의 Kubernetes·Autoscaler 검사, `scripts/aws_deploy.py`의 버전 검사, runner kubectl 버전을 함께 검토합니다. 검증을 통과시키기 위해 버전 검사를 지우면 안 됩니다. 지원 업그레이드 경로·CRD/API 호환성 확인 후 시험 환경 → 제어 영역 → 호환 애드온/노드 순으로 진행하고 단계마다 확인합니다. Kafka 단일 Pod를 가진 노드의 점검은 AI 작업 지연을 동반합니다.

## 남는 보안 경계

Namespace는 baseline 정책을 강제하고 restricted 위반은 경고·감사합니다. 앱/Job에는 권한 상승 차단, capability 제거, 기본 seccomp와 UID/GID 10001 비관리자 실행을 강제합니다. 네 이미지의 Dockerfile도 같은 사용자로 변경하고, 임시 볼륨은 fsGroup 10001로 쓰기를 허용합니다. 플랫폼 operator가 함께 있는 namespace는 호환성을 위해 baseline을 유지합니다. 전체 업무 이미지 빌드·서비스 연동을 검증한 뒤 플랫폼 operator까지 포함한 restricted 강제를 별도로 검토하세요.

배포 권한은 Pod/Job을 통해 앱 Secret을 읽을 수 있는 신뢰된 운영자 권한입니다. Secret 직접 조회 금지가 이 권한까지 차단하는 것은 아닙니다. 영구 self-hosted Runner는 신뢰된 workflow만 실행해야 하며, 공개 PR 코드를 운영 Runner에서 실행하지 마세요. Actions 고정 SHA, 모든 외부 PR 실행 승인과 Environment 승인은 이 경계를 보완하지만 일회성 Runner 격리를 대체하지 않습니다. main의 PR 병합 보호 규칙은 현재 미설정이므로 main 쓰기 권한자를 신뢰된 운영자로 한정해야 합니다.

GitHub 보호 설정은 `scripts/github-deployment-protection.py --reviewer <사용자> --apply`로 재현할 수 있습니다. 현재 단독 운영을 위해 본인이 실행한 배포의 승인도 허용합니다. 독립적인 2인 승인이 필요하면 다른 운영자를 지정하고 self-review를 차단하세요. Kafka 인증서 갱신 후에는 연결 중인 클라이언트가 새 인증서를 로드하도록 해당 앱을 순차 재시작하고 연결을 확인하세요.
