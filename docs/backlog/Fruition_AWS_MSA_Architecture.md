# Fruition AWS MSA 목표 구조

> 작성일: 2026-07-27
> 상태: 목표 구조 확정안
> 대상 리전: AWS Asia Pacific (Seoul), `ap-northeast-2`

> **반영 현황 (2026-08-07)**: 이 목표 구조의 핵심(Access·Document·AI Service 물리 분리, Kafka command/worker, EKS/Strimzi/KEDA, 권한 projection 기반 장애 격리)이 코드에 반영되어 로컬 compose·kind에서 실검증됐다. 현행 구조·배포·검증 상세는 [`msa/`](msa/README.md)를 따른다. 남은 목표: 물리 DB 분할, RS256/JWKS, result topic, converter 연결, Terraform·Secrets Manager(실배포).

## 1. 결정

Fruition은 학습과 포트폴리오를 목적으로 다음 구조를 사용한다.

- Frontend는 **Vercel**에 배포한다.
- Backend와 AI workload는 **Amazon EKS**에서 실행한다.
- 서비스는 **Access Service**, **Document Service**, **AI Service**로 분리한다.
- Production Kafka는 **Amazon MSK**, 로컬·학습 Kafka는 **Strimzi**를 사용한다.
- 긴 AI 작업은 Kafka command/result topic과 Kubernetes worker로 처리한다.
- 문서 metadata는 PostgreSQL, 현재 본문과 편집 revision은 MongoDB, 파일과 고정 snapshot은 S3에 저장한다.
- SQS, ECS on Fargate, Amplify Hosting은 사용하지 않는다.

이 구조는 최소 비용 구성이 아니다. Kubernetes, Kafka, MSA, Polyglot Persistence를 실제 경계로 학습하는 것이 목적이다.

## 2. 전체 구조

```text
사용자
  │
  ├─ app.fruition.com
  │    └─ Vercel
  │         └─ Next.js Frontend
  │
  └─ api.fruition.com
       └─ Route 53
            └─ AWS WAF
                 └─ Application Load Balancer
                      └─ Amazon EKS
                           ├─ ALB 라우팅 대상
                           │    ├─ Access Service
                           │    └─ Document Service
                           └─ cluster 내부 전용 (ClusterIP)
                                ├─ AI API
                                ├─ Query Worker
                                ├─ Ingest Worker
                                ├─ Converter Worker
                                ├─ Embedding Worker
                                ├─ Retry Consumer
                                └─ KEDA

Amazon MSK
  ├─ AI command topics
  ├─ AI result topic
  ├─ retry topics
  └─ DLQ topic

Data
  ├─ Amazon RDS for PostgreSQL
  ├─ MongoDB Atlas
  ├─ Amazon ElastiCache for Valkey/Redis
  ├─ Amazon S3
  └─ PostgreSQL FTS + pgvector
```

Frontend와 API는 별도 도메인을 사용한다. Backend CORS는 Vercel Production domain만 허용하고, OAuth callback·cookie의 `SameSite`, `Secure`, `Domain` 정책을 함께 설정한다.

ALB는 Access Service와 Document Service에만 라우팅한다. AI API와 worker는 §7처럼 ClusterIP로만 노출하고, 외부 요청은 Document Service를 거쳐 §4.3의 비동기 흐름으로만 AI Service에 도달한다.

## 3. 서비스와 데이터 소유권

| 서비스 | 책임 | 원본 저장소 |
|---|---|---|
| Access Service | 사용자, OAuth, JWT, Workspace, membership, role | Access PostgreSQL |
| Document Service | 문서, 폴더, Wiki, 채팅, revision, operation | Core PostgreSQL, MongoDB, S3 |
| AI Service | Query, LLM, 변환, Wiki 생성, embedding, 검색 projection | AI PostgreSQL, S3 |

검색 projection(PostgreSQL FTS + pgvector)은 원본이 아니라 문서 원본에서 재생성 가능한 파생 데이터다. AI Service가 소유하고 갱신하지만 §10처럼 백업 대상이 아니라 재생성 대상으로 관리한다.

초기에는 Access, Core, AI database를 같은 RDS instance 안의 별도 database와 별도 계정으로 운영할 수 있다. 다른 서비스 database에 대한 write 권한은 주지 않는다.

### 3.1 MongoDB

MongoDB는 현재 문서 편집 상태의 원본이다.

| Collection | 데이터 |
|---|---|
| `document_edit_states` | Markdown, revision, content hash, schema version |
| `document_edit_writes` | revision write ID, 요청 hash, 반영 revision |
| `document_edit_outbox` | Kafka에 발행할 문서 변경 event |

본문 갱신, revision 증가, `revision_write_id` 기록, outbox 저장은 하나의 MongoDB transaction에서 처리한다. MongoDB와 Kafka에 직접 dual write하지 않는다.

```text
Document Service
  → MongoDB transaction
       본문 갱신
       revision 증가
       write ID 기록
       outbox event 저장
  → Outbox Publisher 또는 Change Stream
  → Kafka
```

문서 metadata와 목록 조회용 revision projection은 Core PostgreSQL에 둔다. 업로드 원본, 고정 revision snapshot, export, 대용량 AI 입출력은 S3에 둔다.

S3는 두 서비스가 함께 쓰므로 prefix와 IAM 권한으로 경계를 나눈다.

| Prefix | 쓰기 | 읽기 |
|---|---|---|
| `documents/` — 업로드 원본, revision snapshot, export | Document Service | Document Service, AI Service |
| `ai-input/` — AI command의 `input_uri` 대상 | Document Service | AI Service |
| `ai-output/` — AI 실행 결과 산출물 | AI Service | Document Service, AI Service |

각 서비스 IRSA role에는 자기 쓰기 prefix에 대한 `PutObject`만 부여하고 나머지는 읽기 권한만 준다.

## 4. 주요 요청 흐름

### 4.1 로그인과 권한

```text
Vercel Frontend
  → WAF → ALB
  → Access Service
  → 사용자 확인
  → access JWT + refresh token 발급
```

JWT는 사용자 신원만 증명한다. Workspace 역할은 Access PostgreSQL이 원본이며 Redis는 선택적 projection/cache다. Cache miss에서는 원본을 조회하고 원본도 확인할 수 없으면 `fail closed`로 거절한다.

### 4.2 문서 저장

```text
Frontend
  → Document Service
  → Workspace 권한 확인
  → MongoDB 현재 revision 확인
  → base_revision이 같으면 저장
  → revision 증가
```

다른 저장이 먼저 완료됐다면 `409 Conflict`를 반환한다. 같은 `revision_write_id`의 재시도는 기존 성공 결과를 반환한다.

### 4.3 긴 AI 작업

```text
Document Service
  → Core PostgreSQL transaction
       operation 저장
       AI command outbox 저장
  → Kafka command topic
  → EKS AI Worker
  → AI 실행
  → AI PostgreSQL과 S3에 결과 저장
  → Kafka result topic
  → Document Service result consumer
  → 현재 권한·revision·멱등성 재검사
  → MongoDB에 결과 반영
```

요청 당시 revision과 현재 revision이 다르면 결과를 자동 반영하지 않고 `CONFLICT`로 보관한다.

outbox는 두 종류이며 저장소가 다르다. AI command outbox는 `operation`과 같은 Core PostgreSQL transaction에 저장하고, 문서 본문 변경 event outbox는 §3.1처럼 MongoDB transaction에 저장한다. 하나의 흐름이 PostgreSQL과 MongoDB에 걸쳐 dual write하지 않는다. 결과 반영 단계(`MongoDB에 결과 반영`)에서 operation 상태 갱신이 필요하면 MongoDB 반영을 먼저 확정하고 PostgreSQL operation은 result consumer가 멱등하게 뒤따라 갱신한다.

## 5. Kafka와 AI Worker 계약

### 5.1 Topic

```text
ai.query.command.v1
ai.ingest.command.v1
ai.convert.command.v1
ai.embedding.command.v1
ai.result.v1
ai.retry.1m.v1
ai.retry.10m.v1
ai.dlq.v1
```

대용량 본문은 message에 넣지 않고 S3 URI를 전달한다. 같은 문서의 순서가 중요하면 `document_id`를 Kafka message key로 사용한다.

### 5.2 Message

```json
{
  "event_id": "uuid",
  "operation_id": "uuid",
  "schema_version": 1,
  "workspace_id": "uuid",
  "requester_id": "uuid",
  "document_id": "uuid",
  "document_revision": 42,
  "input_uri": "s3://...",
  "idempotency_key": "uuid",
  "trace_id": "uuid"
}
```

### 5.3 Poll과 Offset

장시간 작업 중에도 Kafka consumer가 정상으로 인식되도록 poll과 작업 실행을 분리한다.

```text
Consumer thread
  → poll 계속 수행
  → bounded executor에 작업 전달
  → 처리량 초과 시 partition pause

Worker thread
  → AI 작업 수행
  → durable storage에 결과 저장
  → result event 발행
  → 완료 offset 전달

Consumer thread
  → offset commit
  → partition resume
```

`enable.auto.commit=false`를 사용한다. 결과가 DB와 S3에 안전하게 저장되고 result event가 발행된 뒤 offset을 commit한다. 구현을 단순화해 별도 worker thread 없이 consumer thread에서 직접 처리한다면 `max.poll.records=1`과 `max.poll.interval.ms > 최대 작업 시간`을 함께 적용한다.

AI 작업을 수행하는 worker Pod 하나는 동시에 한 건만 처리한다. bounded executor 병렬도를 1로 두고, 작업이 끝날 때까지 배정된 partition을 모두 pause한다. §8.2의 Pod resource가 한 건 기준이고, §5.5의 실질 병렬성도 Pod 수를 기준으로 계산한다. 여러 건을 동시에 처리하면 나중에 시작한 offset이 먼저 끝나 commit될 수 있고, 그 시점에 Pod가 죽으면 아직 처리 중이던 낮은 offset이 재전달되지 않아 유실된다. §5.4의 멱등성 key는 중복 실행만 막고 이 누락은 막지 못한다. 처리량은 Pod 안의 동시 실행이 아니라 partition 수와 replica 수로 늘린다.

### 5.4 멱등성과 재시도

- `event_id` 또는 `idempotency_key`를 AI PostgreSQL의 unique key로 저장한다.
- 같은 event를 다시 받으면 실행하지 않고 기존 결과를 반환한다.
- 결과 반영 전 현재 Workspace 권한, document revision, operation 취소 여부를 다시 확인한다.
- 일시 오류는 retry topic으로 보내고 영구 오류나 최대 재시도 초과는 DLQ topic으로 보낸다.
- 재시도 단계는 `ai.retry.1m.v1` 3회 → `ai.retry.10m.v1` 3회, 총 6회를 상한으로 한다. 6회를 넘기면 `ai.dlq.v1`로 보낸다. 현재 시도 횟수는 event header에 실어 단계 간에 이어 센다.
- 시도 횟수를 늘리고 보낼 topic을 고르는 쪽은 command topic consumer다. 처리에 실패하면 header의 시도 횟수를 1 늘리고, 그 값이 1~3이면 `ai.retry.1m.v1`, 4~6이면 `ai.retry.10m.v1`, 6을 넘으면 `ai.dlq.v1`로 발행한다. retry consumer는 횟수를 바꾸지 않고 원래 command topic으로 되돌리기만 한다.
- offset은 처리 성공 또는 retry/DLQ 발행이 확인된 뒤 commit한다.

Kafka에는 message 단위 지연 발행이 없으므로 `1m`, `10m` 지연은 retry topic 전용 consumer가 직접 구현한다. command topic consumer는 재시도로 보낼 때 header에 `not_before`(재처리 가능 시각)를 싣는다. 값은 발행 시각에 고른 topic의 지연을 더한 값이고, `ai.retry.1m.v1`이면 1분, `ai.retry.10m.v1`이면 10분이다. retry consumer는 partition head message의 `not_before`가 아직 오지 않았으면 그 partition을 pause한 뒤 남은 시간만큼 대기했다가 resume한다. partition마다 따로 판단하므로 §5.3의 한 건 제한은 적용하지 않는다. 대기와 재발행만 하고 AI 작업은 수행하지 않는다. 시각이 지난 message는 원래 command topic으로 재발행하고 offset을 commit한다. 재발행할 때 시도 횟수 header는 그대로 옮기고 `not_before`만 제거한다. header를 새로 만들면 시도 횟수가 초기화되어 6회 상한이 무너진다.

retry topic은 4개 command topic의 재시도를 함께 받고 producer도 worker Pod마다 다르다. 한 topic 안의 지연 폭은 같지만 partition append 순서는 각 Pod가 broker에 도달한 시각 순이므로 `not_before` 순서와 정확히 일치하지는 않는다. 어긋나는 폭은 Pod 사이의 발행 시각 편차이고 지연 폭인 1분, 10분보다 훨씬 작으므로, head만 확인하는 방식에서는 뒤쪽 message가 그 편차만큼 더 기다린다. 이 지연은 허용하고 head만 본다. 편차가 문제가 될 만큼 커지면 partition 앞쪽 여러 건의 `not_before`를 함께 확인하는 방식으로 바꾼다.

대기 중에도 poll은 계속 수행하므로 `max.poll.interval.ms`를 넘기지 않는다.

### 5.5 병렬 처리와 KEDA

KEDA는 Kafka consumer lag을 기준으로 worker Deployment를 확장한다. Consumer group의 실질적인 최대 병렬성은 topic partition 수와 `maxReplicaCount` 중 작은 값이다. Partition 수를 넘겨 replica를 늘려도 남는 Pod는 partition을 배정받지 못한다.

```text
ai.convert.command.v1: 3 partitions (§8.3)
converter worker:      maxReplicaCount=2 (§8.4)
실질 최대 병렬성:       2
```

Query, ingest, convert, embedding은 자원 특성이 다르므로 topic과 Deployment를 분리한다. 일반 worker는 Kubernetes `Deployment`로 실행한다. 작업별 자원 격리나 GPU node가 필요할 때만 dispatcher가 Kubernetes `Job`을 생성한다.

## 6. Kafka 운영 모델

### 6.1 Production: Amazon MSK

Production에서는 EKS application과 Kafka broker의 장애 범위를 분리한다.

```text
Amazon EKS
  └─ API, Worker, KEDA

Amazon MSK
  └─ Kafka broker
```

AWS가 broker, storage, 복구와 upgrade의 상당 부분을 관리한다. 기본 후보는 MSK Serverless이며, 안정적인 저처리량에서는 MSK Provisioned 견적과 비교한 뒤 더 저렴한 방식을 선택한다.

### 6.2 로컬·학습: Strimzi

Strimzi Operator로 Kubernetes 안에서 Kafka를 운영한다.

```text
Kubernetes
  ├─ Strimzi Operator
  ├─ Kafka broker/controller
  ├─ API
  └─ Worker
```

로컬은 `kind` 또는 `k3d`를 사용한다. AWS 검증이 필요할 때만 Terraform으로 EKS 환경을 만들고 테스트 후 제거한다. Strimzi 단일 broker 구성은 학습용이며 Production HA로 간주하지 않는다.

## 7. Network와 보안

- Vercel Frontend와 AWS API를 별도 도메인으로 분리한다.
- 공개 API는 Route 53, WAF, HTTPS ALB를 통과한다.
- ACM certificate를 ALB에 연결하고 HTTP는 HTTPS로 redirect한다.
- EKS node와 Pod, RDS, Redis는 private subnet에 둔다.
- AI Service와 worker는 공개 ALB에서 직접 접근할 수 없다.
- Kubernetes ServiceAccount에 EKS Pod Identity 또는 IRSA를 연결해 최소 IAM 권한을 부여한다.
- Secret은 Kubernetes manifest에 평문으로 두지 않고 Secrets Manager와 연동한다.
- Access token, refresh token, 문서 본문, 외부 AI credential을 log에 기록하지 않는다.
- 모든 HTTP 요청과 Kafka message에 `trace_id`, `operation_id`, `workspace_id`를 전달한다.

## 8. 소규모 사용자 피드백 실행 Profile

이 Profile은 개발·테스트와 초대 사용자 피드백을 위한 24시간 환경이다. 정식 Production SLA보다 비용과 복구 가능성을 우선한다.

```text
초대 사용자       20~100명
동시 접속         5~10명
동시 AI 작업      최대 2~3개
목표 비용         월 USD 350~900
RPO               1시간
RTO               4시간
```

### 8.1 EKS Node

| Node Group | min/desired/max | 용도 | 구매 방식 |
|---|---|---|---|
| General | `2/2/3` | API, Kafka, Query Worker, Retry Consumer, 기본 system workload | On-Demand |
| AI Worker | `0/0/2` | ingest, converter, embedding 등 고자원 배치 작업 | Spot 허용 |

General node는 `2 vCPU / 8 GiB`급 2대로 시작하고 2개 AZ에 분산한다. AI Worker node는 `4 vCPU / 16 GiB`급으로 시작하되 작업이 없으면 0대로 축소한다. Kafka, DB, API에는 Spot을 사용하지 않는다.

Query Worker는 §8.4처럼 항상 1대 이상 유지해야 하는 대화형 경로이므로 Spot을 허용하는 AI Worker node가 아니라 General node에 둔다. Spot eviction이 대화 응답 중단으로 이어지고, embedding 모델을 다시 로드하는 데 수 분이 걸린다.

두 node group 모두 §8.4의 `maxReplicaCount` 합계를 담을 만큼 크지 않다. General은 API 3종과 Kafka broker, Retry Consumer가 `2.35 CPU`를 쓰므로 node 2대에서는 Query Worker 1대분 여유만 있고 2대를 담으려면 node가 3대로 늘어야 하며, AI Worker는 세 worker가 동시에 상한에 도달하면 `8 CPU`가 필요해 node 2대(`8 vCPU`)의 allocatable을 넘는다. 이는 의도한 동작이다. `maxReplicaCount`는 worker type별 상한일 뿐이고 실제 동시 실행은 node 용량이 먼저 묶는다. 초과분은 Pod pending으로 대기하며, 배치 작업은 Kafka에 그대로 남아 있으므로 유실되지 않는다. 이 profile에서 실질 동시 실행을 결정하는 값은 §8.6의 Workspace별 동시 작업 제한이다.

KEDA는 worker Pod 수를 조정하고 Karpenter 또는 Cluster Autoscaler는 pending Pod를 기준으로 AI Worker node 수를 조정한다. 두 autoscaler의 책임을 구분한다.

### 8.2 Pod Resource

| Workload | Replica | CPU request | Memory request |
|---|---:|---:|---:|
| Access Service | 1 | 250m | 512Mi |
| Document Service | 1 | 500m | 1Gi |
| AI API | 1 | 500m | 1~2Gi |
| Query Worker | 1~3 | 1 CPU | 2Gi |
| Ingest Worker | 0~2 | 1 CPU | 2~4Gi |
| Converter Worker | 0~2 | 1 CPU | 2Gi |
| Embedding Worker | 0~2 | 2 CPU | 8Gi |
| Retry Consumer | 1 | 100m | 256Mi |
| Kafka Broker | 1 | 1 CPU | 2Gi |

실측 전 초기값이다. `request`는 scheduler가 보장할 자원이며 `limit`은 request의 약 2배로 시작해 부하 테스트로 조정한다.

### 8.3 Strimzi Kafka

```text
Broker와 KRaft controller: 1
Replication factor:        1
EBS gp3:                   50GB
일반 topic 보존:           3일
DLQ topic 보존:            14일
```

| Topic | Partition |
|---|---:|
| `ai.query.command.v1` | 3 |
| `ai.ingest.command.v1` | 3 |
| `ai.convert.command.v1` | 3 |
| `ai.embedding.command.v1` | 3 |
| `ai.result.v1` | 3 |
| `ai.retry.1m.v1` | 3 |
| `ai.retry.10m.v1` | 3 |
| `ai.dlq.v1` | 1 |

단일 broker는 HA 구성이 아니다. Kafka를 원본 저장소로 사용하지 않고 operation 상태를 PostgreSQL에 보존한다. Broker 복구 뒤 미완료 operation을 다시 발행할 수 있어야 한다.

broker의 gp3 volume은 AZ에 묶이므로 §8.1처럼 General node를 2개 AZ에 분산해도 broker Pod는 volume이 있는 AZ 밖으로 재스케줄되지 않는다. broker StatefulSet은 한쪽 AZ의 node에 고정하고, 그 AZ 장애는 broker 중단으로 간주해 복구 절차(operation 재발행)로 대응한다.

### 8.4 KEDA

- Query Worker는 `minReplicaCount=1`, `maxReplicaCount=3`을 사용한다. 대화형 응답 경로이고 유사도 검색용 embedding 모델 로드에 수 분이 걸리므로 0대로 축소하지 않는다.
- Ingest, Converter, Embedding Worker는 `minReplicaCount=0`, `maxReplicaCount=2`를 사용한다.
- 이 상한들은 worker type별 값이며 동시에 모두 도달할 수 있는 값이 아니다. §8.1처럼 node 용량이 먼저 묶는다.
- Retry Consumer는 KEDA 대상이 아니다. replica 1로 고정하고 두 retry topic을 함께 소비한다. 지연 대기 중인 message도 lag으로 잡히므로 lag 기준으로 확장하면 대기만 하는 Pod가 늘어난다. 대기와 재발행만 하므로 partition 6개를 한 Pod가 맡아도 부하가 되지 않는다.
- Topic을 명시해 scale-to-zero 상태에서도 lag을 확인한다.
- API Pod는 사용자 요청을 받아야 하므로 0대로 축소하지 않는다.
- 최대 병렬 처리는 partition 수와 Workspace별 동시 작업 제한을 함께 적용한다.

### 8.5 Data

| 저장소 | 시작 구성 | 보호 정책 |
|---|---|---|
| RDS PostgreSQL | Single-AZ, `db.t4g.small`급, gp3 30~50GB | 자동 backup 7일, PITR |
| MongoDB Atlas | M10급, 10GB 이상 | transaction, backup |
| Redis | Single node, `cache.t4g.micro`급 | 실시간 상태 전용, TTL |
| S3 | 원본·snapshot·AI 파일 | Versioning, 임시 파일 lifecycle |

Access, Core, AI database는 같은 RDS instance에서 시작할 수 있지만 database·계정·write 권한을 분리한다. 권한 원본은 Access PostgreSQL이며 Redis 장애 시에도 권한을 확인할 수 있어야 한다.

### 8.6 Network와 운영 제한

- Public subnet 2개에 ALB, private subnet 2개에 EKS·RDS·Redis를 둔다.
- NAT Gateway는 비용을 줄이기 위해 1개만 사용한다.
- CloudWatch log 보존 기간은 14일로 시작한다.
- AWS Budget alarm은 월 USD 500과 700에 설정한다.
- Workspace별 동시 AI 작업은 2개로 제한한다.
- Ingest, Converter, Embedding Worker는 KEDA로 0대까지 축소하고 General node는 2대를 유지한다. Query Worker는 §8.4에 따라 1대를 유지한다.

이 Profile은 Kafka broker 1개, RDS Single-AZ, Redis Single node, NAT Gateway 1개를 사용하므로 정식 Production HA가 아니다. 장애 시 일시 중단을 허용하고 backup, PITR, operation 재처리로 복구한다.

## 9. 배포와 전환

### 9.1 CI/CD

```text
Application
  test
  → container build
  → image scan
  → ECR push
  → Helm manifest 갱신
  → EKS rolling deploy
  → smoke test

Infrastructure
  terraform fmt/validate
  → terraform plan
  → review
  → terraform apply
```

GitHub Actions는 장기 AWS access key 대신 OIDC로 AWS deploy role을 assume한다. DB migration은 Pod 시작 시 실행하지 않고 배포 전 별도 Kubernetes Job으로 수행한다.

### 9.2 전체 전환

기능 Phase는 두지 않는다. 신규 Green 환경을 완성한 뒤 한 번에 전환한다.

```text
기존 Blue 환경 유지
  → Green 환경 전체 구축
  → 데이터 backfill
  → 데이터·권한·검색 결과 검증
  → 쓰기 일시 중지
  → 마지막 증분 반영
  → Green smoke test
  → ALB/DNS 전환
  → Blue read-only 보존
```

Green이 사용자 write를 받기 전에는 Blue로 rollback할 수 있다. Green이 새 write를 받은 뒤에는 단순 DNS rollback하지 않고 fix-forward를 기본으로 한다.

## 10. 관측성과 복구

- CloudWatch와 OpenTelemetry로 log, metric, trace를 수집한다.
- Prometheus/Grafana로 Pod, node, Kafka lag과 consumer 상태를 관찰할 수 있다.
- Kafka lag, rebalance, retry, DLQ 증가량에 alarm을 설정한다. retry topic은 §8.4처럼 대기 중인 message도 lag으로 잡히므로 lag 자체가 아니라 지연 폭을 넘겨 밀린 양을 기준으로 본다.
- RDS PITR, MongoDB backup, S3 Versioning을 적용한다.
- Search/Vector는 원본에서 재생성 가능한 projection으로 관리한다.
- 배포 전에 RPO, RTO, backup 보존 기간, restore rehearsal 주기를 확정한다.

## 11. 예상 비용

### 11.1 공통 전제

- 월 730시간, Seoul Region, On-Demand 기준의 계획 범위다.
- 세금, AWS Support, Internet egress, cross-AZ 대용량 전송, 외부 LLM/Bedrock token 비용은 제외한다.
- 실제 금액은 instance class, 저장량, 요청 수, log 양과 환율에 따라 달라진다.
- 계약 전 AWS Pricing Calculator와 MongoDB Atlas Calculator로 다시 산정한다.

### 11.2 로컬 중심 학습 환경

| 항목 | 예상 월 비용(USD) |
|---|---:|
| Vercel Hobby | 0 |
| 로컬 kind/k3d + Strimzi | 0 |
| MongoDB Atlas M0/Flex | 0~30 |
| 소량 S3/ECR/외부 서비스 | 0~20 |
| **합계** | **약 0~50** |

EKS 검증은 상시 운영하지 않고 필요할 때 생성한 뒤 제거한다. 24시간 데모 환경은 사용한 시간만큼 EC2, EBS, ALB, NAT 비용이 추가된다.

### 11.3 소규모 사용자 피드백: EKS + Strimzi

| 항목 | 예상 월 비용(USD) |
|---|---:|
| Vercel Pro | 약 20 |
| EKS control plane | 약 73 |
| General node 2대와 EBS | 80~200 |
| 간헐적 AI Spot node | 0~100 |
| RDS PostgreSQL Single-AZ | 30~100 |
| MongoDB Atlas | 60~150 |
| Redis | 10~40 |
| Route 53, ALB, WAF | 30~80 |
| NAT/VPC endpoint | 40~100 |
| S3, ECR, CloudWatch, Secrets | 10~50 |
| **합계** | **약 350~900** |

Strimzi software 비용은 없지만 Kafka broker가 사용하는 EC2와 EBS는 과금된다. 외부 LLM 사용료는 포함하지 않는다.

### 11.4 Production 목표: EKS + MSK

| 항목 | 예상 월 비용(USD) |
|---|---:|
| Vercel Pro와 사용량 | 20~100 |
| Route 53, WAF, ALB | 35~135 |
| EKS control plane | 약 73 |
| EKS worker node와 EBS | 200~700 |
| Amazon MSK | 600~1,300+ |
| RDS PostgreSQL | 150~500 |
| MongoDB Atlas | 60~750 |
| Redis | 20~120 |
| S3 | 5~50 |
| NAT Gateway/VPC endpoint | 50~250 |
| CloudWatch, ECR, Secrets, KMS, Backup | 30~250 |
| **합계** | **약 1,250~4,250+** |

MSK Serverless는 유휴 상태에도 cluster-hour와 partition-hour 비용이 발생한다. AWS 공식 Ohio 예시의 cluster-hour만 월 약 USD 558이므로 서울 리전은 Calculator로 확인한다. 외부 AI 사용료는 다음과 같이 별도 산정한다.

```text
월 AI 비용
  = 입력 token × 입력 단가
  + 출력 token × 출력 단가
  + embedding 비용
  + GPU/CPU worker 실행 시간
```

## 12. 배포 전 확인

- [ ] Vercel Production domain과 API CORS·cookie·OAuth callback을 검증했다.
- [ ] 모든 서비스가 JWT와 Workspace 권한을 검사한다.
- [ ] 서비스별 DB 계정과 write 권한이 분리돼 있다.
- [ ] MongoDB 저장과 outbox가 같은 transaction이다.
- [ ] Kafka consumer가 `enable.auto.commit=false`를 사용한다.
- [ ] 결과 저장 전 offset을 commit하지 않는다.
- [ ] 같은 event를 두 번 받아도 결과가 한 번만 반영된다.
- [ ] 장시간 작업이 `max.poll.interval.ms`를 넘어도 잘못 rebalance되지 않는다.
- [ ] partition 수가 목표 worker 병렬성을 지원한다.
- [ ] KEDA가 consumer lag에 따라 worker를 확장한다.
- [ ] retry와 DLQ 처리 절차가 있다.
- [ ] AI 결과 반영 전 현재 권한과 document revision을 다시 확인한다.
- [ ] RDS, MongoDB, S3 restore를 실제로 검증했다.
- [ ] Production은 MSK, 학습 환경은 Strimzi라는 운영 경계가 명확하다.
- [ ] 사용자 피드백 환경이 Production HA가 아님을 운영자와 사용자에게 명시했다.

## 13. 공식 자료

- [Vercel Pricing](https://vercel.com/pricing)
- [Amazon EKS Pricing](https://aws.amazon.com/eks/pricing/)
- [Amazon MSK Pricing](https://aws.amazon.com/msk/pricing/)
- [MongoDB Atlas on AWS Pricing](https://www.mongodb.com/products/platform/atlas-cloud-providers/aws/pricing)
- [Apache Kafka Consumer Configuration](https://kafka.apache.org/41/generated/consumer_config.html)
- [KEDA Kafka Scaler](https://keda.sh/docs/2.18/scalers/apache-kafka/)
- [Strimzi Documentation](https://strimzi.io/docs/operators/latest/deploying.html)
