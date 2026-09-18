# 안전하게 배포하고 점검하기

이 문서는 보안·재배포·복구 설정의 적용 순서입니다. RDS Multi-AZ, Redis 복제, Kafka 3노드, AZ별 NAT 증설은 이번 변경에 포함하지 않았습니다. 따라서 DB·Kafka·Redis의 점검이나 장애까지 무중단으로 만드는 구성은 아닙니다.

## 무엇이 자동으로 늘어나나요?

| 대상 | 현재 동작 | 상한 |
|---|---|---|
| ALB | 요청을 준비된 Pod에 나누어 전달 | 앱 서버 수를 직접 늘리지 않음 |
| 인증·문서·Pipeline API | 각각 2개 Pod, 롤링 배포 중 임시 1개 추가 | HPA 미설정 |
| 수집·질의·에이전트 작업자 | KEDA가 Kafka의 미처리 메시지 수를 보고 조절 | 각각 1~4개 Pod |
| 유지보수 작업자 | KEDA가 Kafka 대기 작업을 보고 조절 | 1~2개 Pod |
| EC2 일반 노드 | Cluster Autoscaler가 자원 부족으로 배치되지 못한 Pod를 보고 조절 | 최소 2대, 최대 4대 |
| EC2 AI 노드 | 같은 방식, CPU Spot 사용 | 최소 0대, 최대 2대 |

트래픽 증가만으로 일반 API의 Pod 수가 늘어나지는 않습니다. AI 작업 Pod가 늘어나도 EC2 최대치에 도달하면 대기할 수 있습니다. CloudWatch는 관측·알림용이며 현재 API HPA와 연결되지 않습니다. Pod 2개를 실행할 여유가 없으면 일반 노드가 상한인 4대까지 늘어나 비용이 증가할 수 있습니다.

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

## 노드·EKS 버전 점검

API는 각 2개 Pod이며 `maxUnavailable: 0`, `maxSurge: 1`로 교체합니다. 노드 점검은 PDB가 최소 1개 Pod를 보호합니다. ALB Service/Ingress와 TargetGroupBinding을 먼저 만들고 Pod를 생성해 readiness gate가 주입되게 합니다. ALB Pod webhook 실패 시 새 Pod 생성을 막아 gate 없이 배포가 진행되지 않도록 합니다. 이미 있는 Pod에는 자동 주입되지 않으므로 최초 전환의 재배포 후 실제 Pod의 gate와 ALB target 상태를 확인하세요.

종료유예 60초에는 신규 요청 차단을 기다리는 10초와 Spring 종료 대기 40초가 포함됩니다. 긴 SSE/AI 작업의 완주를 보장하지 않습니다. 클라이언트 재연결, 작업 재시도·중복 방지와 Spot 회수 처리를 실제 서비스에서 시험하세요.

EKS 업그레이드는 Terraform `cluster_version`, 애드온 버전, `scripts/aws-platform-up.sh`의 Kubernetes·Autoscaler 검사, `scripts/aws_deploy.py`의 버전 검사, runner kubectl 버전을 함께 검토합니다. 검증을 통과시키기 위해 버전 검사를 지우면 안 됩니다. 지원 업그레이드 경로·CRD/API 호환성 확인 후 시험 환경 → 제어 영역 → 호환 애드온/노드 순으로 진행하고 단계마다 확인합니다. Kafka 단일 Pod를 가진 노드의 점검은 AI 작업 지연을 동반합니다.

## 남는 보안 경계

Namespace는 baseline 정책을 강제하고 restricted 위반은 경고·감사합니다. 앱/Job에는 권한 상승 차단, capability 제거, 기본 seccomp와 UID/GID 10001 비관리자 실행을 강제합니다. 네 이미지의 Dockerfile도 같은 사용자로 변경하고, 임시 볼륨은 fsGroup 10001로 쓰기를 허용합니다. 플랫폼 operator가 함께 있는 namespace는 호환성을 위해 baseline을 유지합니다. 전체 업무 이미지 빌드·서비스 연동을 검증한 뒤 플랫폼 operator까지 포함한 restricted 강제를 별도로 검토하세요.

배포 권한은 Pod/Job을 통해 앱 Secret을 읽을 수 있는 신뢰된 운영자 권한입니다. Secret 직접 조회 금지가 이 권한까지 차단하는 것은 아닙니다. 영구 self-hosted Runner는 신뢰된 workflow만 실행해야 하며, 공개 PR 코드를 운영 Runner에서 실행하지 마세요. Actions 고정 SHA, 모든 외부 PR 실행 승인과 Environment 승인은 이 경계를 보완하지만 일회성 Runner 격리를 대체하지 않습니다. main의 PR 병합 보호 규칙은 현재 미설정이므로 main 쓰기 권한자를 신뢰된 운영자로 한정해야 합니다.

GitHub 보호 설정은 `scripts/github-deployment-protection.py --reviewer <사용자> --apply`로 재현할 수 있습니다. 현재 단독 운영을 위해 본인이 실행한 배포의 승인도 허용합니다. 독립적인 2인 승인이 필요하면 다른 운영자를 지정하고 self-review를 차단하세요. Kafka 인증서 갱신 후에는 연결 중인 클라이언트가 새 인증서를 로드하도록 해당 앱을 순차 재시작하고 연결을 확인하세요.
