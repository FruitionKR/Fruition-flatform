# k6 부하 시험 (AWS EKS 시험 단계 배포)

Fruition 시험 단계 배포(ALB + WAF + EKS)의 처리량·지연·자동 확장을 k6로 확인하는 시나리오다.
이 폴더의 스크립트는 **우리 계정의 시험 환경만** 대상으로 한다. 운영 사용자 데이터·타사 엔드포인트에는 보내지 않는다.

- 대상: 화면과 같은 출처 API를 쓰는 앱 호스트(`app_domain`, 예: `web.<도메인>`). ALB가 `/api/*`를 access-svc·document-svc로 나눈다([ingress.yaml](../k8s/overlays/aws/ingress.yaml)).
- 이 저장소에서는 스크립트와 절차만 관리한다. 실제 AWS 실행은 아래 "실행 전 준비"를 마친 뒤 담당자가 직접 한다.

## 1. AWS 정책 확인 결과 (2026-10-17 확인)

| 구분 | 내용 | 출처 |
|---|---|---|
| 일반 부하·스트레스 시험 | AWS는 "정상 트래픽 또는 시험 트래픽을 특정 대상 애플리케이션에 대량으로 보내는 성능 시험"을 Network Stress Test로 보고, 대상이 그 트래픽을 처리할 것으로 예상되면 허용한다. 25Gbps(경로·리전에 따라 100Gbps)를 넘는 급증에는 AWS가 트래픽을 제한할 수 있다. | [Amazon EC2 Testing Policy](https://aws.amazon.com/ec2/testing/) |
| 사전 승인 없이 보안 시험 가능한 서비스 | EC2, ELB, WAF, NAT Gateway, RDS/Aurora, CloudFront, API Gateway, Lambda, ECS/Fargate 등 | [Penetration Testing](https://aws.amazon.com/security/penetration-testing/) |
| 금지 | DoS/DDoS 공격, 포트·프로토콜·**요청 flooding(로그인 요청 flooding, API 요청 flooding)**, Route 53 zone walking 등 | 같은 문서 |
| 사전 승인(Simulated Events 양식) 필요 | 시뮬레이션 DoS/DDoS(아래 정책), red/blue/purple team, 볼륨 시험, iPerf, 피싱·악성코드 시험 등. 시작 **2주 전**에 계정 ID·자산·일정·연락처를 적어 AWS Support 콘솔의 Simulated Events 양식으로 제출, 회신은 약 2영업일 | 같은 문서 |
| DDoS 시뮬레이션 | AWS DDoS Test Partner(NCC Group, RedWolf, Red Button, Safedash)만, Shield Advanced 보호 리소스에만, **AWS 리소스에서 출발하지 않는** 트래픽으로 할 수 있다. 상한 20Gbps, 50,000 rps, 50,000 pps(CloudFront는 5M pps). 넘으면 14일 전 예외 요청 | [DDoS Simulation Testing](https://aws.amazon.com/security/ddos-simulation-testing/) |
| 이용 정책 | 사용자·네트워크·시스템의 보안·무결성·**가용성**을 해치는 사용 금지 | [Acceptable Use Policy](https://aws.amazon.com/aup/) |
| ALB 확장 | ALB는 트래픽에 맞춰 자동 확장한다. 5분 안에 평소의 2배를 넘는 급증이 예상되면 LCU 예약(최소 100 LCU, 리전 단위·AZ 균등 분배)을 검토하라고 안내한다. 예약량은 부하 시험이나 `PeakLCUs`(분당 Sum)로 정한다. | [ALB capacity reservation](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/capacity-unit-reservation.html), [발표](https://aws.amazon.com/about-aws/whats-new/2024/11/load-balancer-capacity-unit-reservation-application-balancers) |
| WAF rate-based 규칙 | 평가 창 60/120/300/600초, 최소 한도 10, 한도는 "근사치"로 적용된다. | [Rate-based rule 설정](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-high-level-settings.html) |
| Distributed Load Testing on AWS | AWS 솔루션이 k6 스크립트(압축 파일 업로드)를 지원한다. 다만 스크립트의 stages·동시성·thresholds 대신 콘솔의 Traffic Shape(task 수, task당 VU, ramp-up, hold) 값을 쓴다. k6는 AGPL-3.0이라 생성 시 라이선스 확인 문구가 뜬다. | [Design considerations](https://docs.aws.amazon.com/solutions/latest/distributed-load-testing-on-aws/design-considerations.html) |

### 우리 시험에 적용한 결론

- `smoke`·`load`·`soak`과, 아래 상한 안에서의 `stress`·`spike`는 **자기 애플리케이션에 대한 정상 형태의 성능 시험**이라 사전 승인 대상이 아니다. 최대 수백 req/s, 수 Mbps 수준으로 25Gbps·50,000rps와 차이가 크다.
- 실제 사용자 행동(로그인 1회 후 토큰 재사용, 행동 사이 1~3초 대기)을 흉내 낸다. **로그인만 반복하거나 한 API만 무한 반복하는 시나리오는 만들지 않는다**(정책의 "request flooding" 금지와 구분).
- 부하 발생기는 **우리 AWS 계정의 EC2**에서 같은 리전으로 보낸다. 다른 회사 계정·개인 PC 여러 대에서 분산해 보내지 않는다.
- **타사 엔드포인트는 대상이 아니다.** LLM 질의는 OpenAI 등 외부 제공자를 부르므로 기본 `LLM_SHARE=0`이다. 켜더라도 VU당 상한(`LLM_MAX_PER_VU`)을 둔다. 제공자의 rate limit·이용 약관은 별도로 지킨다.
- S3에는 큰 파일을 올리지 않는다. 업로드 시나리오는 multipart 티켓 발급 직후 중단(abort)만 한다.
- 이 배포는 CloudFront를 쓰지 않는다(ALB 직접). CloudFront를 붙이면 캐시·요금·DDoS 정책 상한이 달라지므로 이 문서를 다시 확인한다.
- 시험 규모를 크게 늘리거나(예: 수천 req/s 이상, 장시간 고정 최대 부하) 정책 해석이 애매하면 **2주 전에 Simulated Events 양식으로 미리 알린다.**

### 공식 자료로 확인하지 못한 점

- "부하 시험"이 "볼륨 시험(사전 승인 필요)"으로 바뀌는 **수치 기준은 공식 문서에 없다.** 위 결론의 "수백 req/s는 승인 불필요"는 EC2 Testing Policy 문구에 근거한 판단이다.
- Penetration Testing 페이지는 Network Stress Test에 대해 "Stress Test policy를 보라"고만 하며, 그 정책(EC2 Testing Policy)은 승인 절차를 적지 않는다. 별도 통보 의무가 없다는 명시 문구는 찾지 못했다.
- ALB 사전 워밍(과거 Support 요청 방식)이 지금도 받는지는 확인하지 못했다. 현재 공식 수단은 LCU 예약이다.
- 아래 비용 항목의 단가는 리전 요금표로 실행 직전에 다시 확인한다(이 문서는 단가를 적지 않는다).

## 2. 시스템 사실 (이 저장소 기준)

| 항목 | 값 | 위치 |
|---|---|---|
| API Pod | access-svc·document-svc·pipeline-api 각 HPA 2~4, CPU 70%, scaleUp 안정화 30초(분당 최대 2배), scaleDown 5분 | [api-autoscaling.yaml](../k8s/overlays/aws/api-autoscaling.yaml) |
| 요청값 | access 250m/512Mi, document 500m(overlay), frontend 2 replica 250m/768Mi | k8s base·overlay |
| 노드 | 일반 t3.large 최소 2·최대 5, AI Spot 노드 0~4 | [eks.tf](../infra/terraform/eks.tf) |
| AI worker | KEDA(Kafka lag) — query 1~4, agent 1~4, ingest 1~4. HTTP 부하로는 늘지 않는다 | [keda-scaledobject.yaml](../k8s/base/keda-scaledobject.yaml) |
| DB·캐시 | RDS PostgreSQL 16 `db.t4g.small` 2개, ElastiCache `cache.t4g.micro` — 모두 burstable(CPU 크레딧) | rds.tf, elasticache.tf |
| WAF `per-source-ip` | IP당 5분 3,000건(≈10 req/s), `/_next/static/` 제외, 초과 시 429 | [cost-guards.tf](../infra/terraform/cost-guards.tf) |
| WAF `all-api-requests` | **전체** `/api/` 5분 6,000건(≈20 req/s), 초과 시 모든 사용자 429 | 같은 파일 |
| WAF `frontend-access-code` | app_domain의 `/api/*`(로그인·초대·워크스페이스 목록 제외)는 `fruition_access` 쿠키 = 접근 코드 SHA-256 hex가 없으면 403 | 같은 파일 |
| ALB | idle timeout 120초, TLS1.2+, WAF 연결 | ingress.yaml |
| 절전 | request-wake가 켜져 있으면 노드가 내려간 상태일 수 있다. 첫 요청은 5xx | [aws-request-wake.md](../docs/aws-request-wake.md) |
| 관측 | Container Insights 수집 주기 300초 — 짧은 급증은 놓친다 | [aws-observability.md](../docs/aws-observability.md) |

### 호출하는 API와 비용 성격

| 행동(비율) | API | 비용 |
|---|---|---|
| 탐색 트리 70% | `GET /api/workspaces/{ws}/document-tree`(ETag/304), 가끔 `GET /api/workspaces`, `GET .../folders/{id}/children` | API·DB만 |
| 문서 열기·저장 20% | `GET .../documents/{id}` → `POST .../edit-lock` → `PUT .../content`(multipart, `base_revision`) → `DELETE .../edit-lock` | API·DB, Kafka `document.edit.event` 1건(edit-event-consumer가 파생 상태만 갱신, LLM 없음) |
| 업로드 티켓 5% | `POST .../documents/uploads` → `POST .../uploads/abort` | S3 multipart 생성·중단 요청만(데이터 없음) |
| 채팅 5% | `GET .../chat/sessions`, `.../messages`; `LLM_SHARE` 확률일 때만 `POST .../query/runs` + `GET /api/query/runs/{id}` 폴링 | 질의는 Kafka → query worker → **외부 LLM 호출(유료, 크레딧 차감)** |
| 회의 WS(별도) | `POST .../meetings` → `POST .../live-tickets` → `WS /api/meetings/{id}/live` → `finish` | 접속만 해도 AI 실시간 전사 연결·크레딧 예약. 기본 꺼짐 |

인증: `POST /api/auth/login`(access token 15분 + HttpOnly `fruition_refresh_token`, Path `/api/auth`) → 만료 1분 전 `POST /api/auth/refresh`. refresh 토큰은 회전하고 같은 토큰을 동시에 쓰면 하나만 성공하므로 **VU마다 자기 로그인 세션**을 쓴다.

## 3. 시나리오

| 파일 | executor | 기본 형태 | 목적 |
|---|---|---|---|
| `smoke.js` | constant-vus | 1 VU, 1분 | 계정·접근 코드·시드·정리·모든 행동 1회씩 |
| `load.js` | ramping-arrival-rate | 2분 상승 → 초당 3 행동 10분 → 1분 하강 | 평소 부하에서 p95·오류율 |
| `stress.js` | ramping-arrival-rate | 초당 5 → 10 → 20 → 40 → 80 행동, 단계마다 3분 유지 | HPA 상한·노드·RDS 한계 찾기 |
| `spike.js` | ramping-arrival-rate | 초당 2 → 10초 만에 20 → 2분 유지 → 복귀 후 3분 회복 | 급증 대응(ALB 확장·HPA 반응) |
| `soak.js` | constant-arrival-rate | 초당 2 행동, 90분 | 누수·DB 연결·CPU 크레딧·토큰 회전 |
| `meeting-ws.js` | per-vu-iterations | 1 VU 1회, `MEETING_WS_ENABLED=1` 필요 | 회의 WS 접속 경로(ticket·Origin·ready·finish) |
| `cleanup.js` | 1회 | — | 중단된 실행이 남긴 `k6-loadtest-*` 워크스페이스 삭제 |

행동 1회는 요청 1~4건이다. **`load`의 기본값(초당 3 행동 ≈ 6~8 req/s)만 WAF 기본 한도 안쪽이다.** `stress`·`spike`는 WAF 한도를 임시로 올려야 한다(아래 4-3).

### 합격 기준과 자동 중단

| 지표 | 합격 | 자동 중단(abortOnFail) |
|---|---|---|
| `http_req_failed` | < 1% | ≥ 5%(30초 유예) |
| `checks` | > 99% | — |
| `waf_blocks`(WAF 403·429) | 0 | 1건이라도 생기면 즉시 |
| `http_req_duration` 전체 p95 | < 1초 | ≥ 3초(30초 유예) |
| p95 by `ep` | tree·doc_read·doc_lock·workspaces·chat_read·query_poll 500ms, upload_ticket 800ms, doc_save·query_start 1초 | — |
| soak `auth_refresh` p95 | < 800ms | — |

공동 편집 충돌(409)·편집 잠금 경합(423)·트리 304는 정상 응답으로 보고 `edit_contention` 지표로 따로 센다.

## 4. 실행 전 준비

### 4-1. 시험 계정·데이터

1. 시험 전용 계정을 **동시에 쓸 VU 수의 1/5 이상** 만든다(예: VU 50 → 계정 10개). 가입은 이메일 인증을 거치므로 운영자가 미리 만든다. 실제 사용자 계정은 쓰지 않는다.
2. `accounts.example.json`을 `accounts.json`으로 복사해 채운다(git 무시 대상).
3. `LLM_SHARE`를 0보다 크게 쓰거나 `meeting-ws.js`를 돌릴 계정에는 크레딧을 충전한다(`BILLING_ENFORCE`가 켜져 있으면 402).
4. 시드: 각 스크립트의 `setup()`이 계정마다 `k6-loadtest-<RUN_ID>` 워크스페이스, 폴더 1개, Markdown 문서 `SEED_DOCS`개, 채팅 세션 1개를 만든다. 다른 워크스페이스는 읽거나 쓰지 않는다.
5. 정리: `teardown()`이 그 워크스페이스를 지운다(소프트 삭제 → 휴지통, 보존 기간 뒤 파기). 중간에 끊겼으면 `k6 run cleanup.js`로 `k6-loadtest-*`만 지운다. 각 VU의 로그인 세션(refresh token)은 만료(14일)까지 남는다.

### 4-2. 접근 코드

WAF `frontend-access-code` 규칙 때문에 app_domain의 `/api/*`에는 `fruition_access` 쿠키가 필요하다. `ACCESS_CODE`에 평문 코드를 주면 k6가 프론트엔드와 같은 방식(trim 후 SHA-256 hex)으로 쿠키를 만든다. 값은 Secrets Manager의 앱 secret `ACCESS_CODE`에서 실행 직전에 읽는다.

```bash
export ACCESS_CODE="$(aws secretsmanager get-secret-value --region ap-northeast-2 \
  --secret-id <앱 secret 이름> --query SecretString --output text | jq -r .ACCESS_CODE)"
```

### 4-3. WAF 한도 (stress·spike·큰 load)

부하 발생기 IP 하나에서 보내므로 `per-source-ip`(5분 3,000건)에 먼저 걸리고, 전체 `all-api-requests`(5분 6,000건)는 **다른 사용자까지 429**를 받게 한다. 한도를 넘는 시험은 시험 시간대에만 Terraform 변수로 올렸다가 끝나면 되돌린다.

```bash
# 예: IP당·전체 5분 120,000건(≈400 req/s). 시험 후 같은 명령에서 -var 를 빼고 다시 apply 해 기본값으로 되돌린다.
terraform -chdir=infra/terraform plan \
  -var 'waf_requests_per_ip_5m=120000' -var 'waf_requests_total_5m=120000'
```

- 올리지 않고 돌리면 `waf_blocks` 임계값이 시험을 바로 멈춘다(의도된 안전장치).
- 한도 상향은 비용 가드를 잠시 약하게 만든다. 시험 동안 Budget·WAF 지표를 지켜보고, 이상하면 `waf_emergency_block=true`로 API를 막는다.
- WAF 규칙에 부하 발생기 IP 예외(IP set)를 두는 방식은 현재 Terraform에 없다. 필요하면 별도 인프라 변경으로 다룬다.

### 4-4. 환경 상태

- 절전 상태가 아닌지 확인한다(`aws lambda invoke ... '{"action":"status"}'`, [aws-request-wake.md](../docs/aws-request-wake.md)). 절전 일정과 시험 시간이 겹치지 않게 한다.
- `kubectl get hpa -n fruition`에서 CPU 값이 `<unknown>`이 아닌지(metrics-server) 확인한다.
- 팀에 시험 시간·대상·중단 담당자를 미리 알린다. 시험 단계라도 같은 ALB·WAF·RDS를 쓰는 사람이 있으면 영향을 받는다.

### 4-5. 관찰할 지표

| 영역 | 지표 |
|---|---|
| ALB | `RequestCount`, `TargetResponseTime`, `HTTPCode_ELB_5XX_Count`(특히 503), `HTTPCode_Target_5XX_Count`, `ActiveConnectionCount`, `PeakLCUs`, `RejectedConnectionCount` |
| WAF | `fruition-per-source-ip`, `fruition-all-api-requests`, `fruition-frontend-access-code` 의 Blocked |
| EKS | `kubectl get hpa -n fruition -w`, `kubectl top pods -n fruition`, Pending Pod, Cluster Autoscaler 로그, Pod 재시작(OOMKilled) |
| RDS | `CPUUtilization`, **`CPUCreditBalance`**(t4g), `DatabaseConnections`, `ReadLatency`/`WriteLatency`, `FreeableMemory` |
| ElastiCache | `EngineCPUUtilization`, `CurrConnections`, `Evictions`, `CPUCreditBalance` |
| Kafka/KEDA | `document.edit.event` 소비 지연(edit-event-consumer 1 replica), LLM을 켰다면 `ai.query.command` lag와 query-task-worker 수 |
| NAT | `BytesOutToDestination`(LLM 호출·이미지 pull) — 관측 경보 1GiB 기준이 있다 |

Container Insights는 300초 주기라 spike 분석에는 ALB 1분 지표와 `kubectl` 관찰을 같이 쓴다.

## 5. 실행 방법

### 5-1. 부하 발생기(EC2)

- 같은 리전(ap-northeast-2), **우리 계정**, EKS VPC 밖의 퍼블릭 서브넷(또는 기본 VPC)에 둔다. EKS 프라이빗 서브넷에 두면 ALB 공인 주소로 나가는 트래픽이 NAT Gateway 처리 요금을 내고 NAT 경보를 울린다.
- 크기: `smoke`·`load`·`soak`은 `c7i.large`(2 vCPU) 하나면 충분하다. `stress` 최대 단계(VU 수백)는 `c7i.xlarge`. k6 프로세스 CPU가 80%를 넘으면 결과가 발생기 한계를 재는 것이므로 더 큰 인스턴스로 바꾼다.
- 시험이 끝나면 인스턴스를 종료한다. SSM Session Manager로 접속하면 SSH 포트를 열지 않아도 된다.

```bash
# Amazon Linux 2023
sudo dnf install -y https://dl.k6.io/rpm/repo.rpm
sudo dnf install -y k6 git jq
ulimit -n 65536
git clone https://github.com/FruitionKR/Fruition-flatform.git && cd Fruition-flatform/loadtest
cp .env.example .env && cp accounts.example.json accounts.json   # 값 채우기
```

### 5-2. 순서

```bash
set -a; . ./.env; set +a
export RUN_ID="$(date +%Y%m%d-%H%M)"

k6 run smoke.js                                   # 1) 반드시 먼저. 실패하면 멈춘다
k6 run --summary-export results/load.json load.js # 2) 평소 부하
# 3) WAF 한도를 올린 뒤에만
k6 run --summary-export results/stress.json stress.js
k6 run --summary-export results/spike.json spike.js
k6 run --summary-export results/soak.json soak.js # 4) 1~2시간
MEETING_WS_ENABLED=1 k6 run meeting-ws.js         # 선택, 비용 확인 후
k6 run cleanup.js                                 # 중단된 실행이 있었다면
```

`mkdir -p results` 후 실행한다. 중단은 `Ctrl+C`(teardown 정리는 수행됨). 한 번 더 누르면 정리 없이 끝나므로 그때는 `cleanup.js`를 돌린다.

### 5-3. 멈출 때

- 자동: 위 abortOnFail 조건.
- 수동: ALB 5xx가 계속 늘거나, Pod가 OOMKilled/Pending으로 쌓이거나, RDS `CPUCreditBalance`가 바닥에 가까워지거나, 예산 경보가 오면 바로 `Ctrl+C`.
- 비상: `waf_emergency_block=true` apply(모든 공개 API 차단, 큐에 있는 작업은 멈추지 않음).

### 5-4. 로컬에서 먼저 확인

```bash
BASE_URL=http://localhost:3000 ACCOUNTS_FILE=/절대/경로/accounts.json SMOKE_DURATION=30s k6 run smoke.js
```

로컬(`localhost`)은 `CONFIRM_TARGET` 없이 실행된다. 로컬 dev 스택에는 WAF가 없으므로 `waf_blocks`는 항상 0이다.

## 6. 비용 메모

| 항목 | 생기는 이유 | 줄이는 법 |
|---|---|---|
| LLM | 질의·회의 WS가 외부 제공자를 부르고 크레딧을 쓴다 | `LLM_SHARE=0`(기본), `LLM_MAX_PER_VU`, 작은 모델 지정 |
| NAT Gateway | 앱 Pod의 외부 호출(LLM 등)과, 발생기를 EKS 프라이빗 서브넷에 둔 경우 | 발생기를 VPC 밖 퍼블릭 서브넷에 둔다 |
| ALB | 시간당 LCU(요청·연결·처리 바이트). LCU 예약을 쓰면 예약량만큼 과금 | spike는 예약 없이 먼저 측정 |
| WAF | 요청 수 과금, **WAF 로그가 CloudWatch Logs로 요청마다 기록**된다 | 시험 시간을 짧게, 불필요한 반복 실행 금지 |
| CloudWatch | 로그 수집량(앱 로그·WAF 로그), Container Insights | soak은 한 번만, 로그 검색 범위를 좁게 |
| S3 | multipart 생성·중단 요청 수(데이터 없음) | 업로드 비율 5% 유지 |
| EC2(발생기)·노드 증설 | 시험 동안 HPA·Cluster Autoscaler가 노드를 늘린다 | 끝나면 발생기 종료, 노드 축소 확인 |
