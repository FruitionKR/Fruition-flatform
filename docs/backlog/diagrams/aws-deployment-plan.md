# AWS 배포 실행 계획

기준일 2026-09-14. 이 문서는 "AWS에 올리기 위해 **무엇을 고쳐야 하고, 어떤 순서로 배포하는가**"를 다룬다. 아키텍처 작도(무엇을 어디에 배치하는가)는 [aws-deployment.md](./aws-deployment.md), 서비스 계약은 [architecture.md](../../architecture.md)를 따른다.

현재 작업 범위는 **배포 준비까지**다. 실제 AWS 리소스 생성·서비스 배포·장애 주입은 수행하지 않는다. 입력 예시와 로컬 준비 절차는 [배포 준비 안내](../../script.md#배포-준비까지만-수행하는-경우)를 따른다.

검토 범위는 `frontend/`, `Access/`, `Document/`, `AI/`, `infra/terraform/`, `k8s/`, 배포 스크립트·현행 운영 문서의 대조와 로컬 Kustomize 렌더다. 아래 실환경·장애 검증 항목은 수행 결과가 아니라 배포 시 확인할 조건이다.

---

## 0. 한 줄 결론

**AWS(EKS) 배포 코드와 절차는 구현돼 있지만, 실제 AWS 배포·복구 검증은 미완료다.** 코드 대조와 로컬 렌더만으로 실제 프로비저닝이나 배포 성공을 보장할 수 없다. 실제 계정 조회 결과와 Phase 0의 미충족 입력은 [현행 실행 문서](../../script.md#aws-iac플랫폼-운영-절차)를 따른다. circuit breaker·PDB 등은 각 선행조건에 맞춰 보강해야 한다. AI command outbox 행 잠금은 구현하고 로컬 PostgreSQL에서 검증했으며, 소비자 멱등성과 AWS rolling update 검증은 별도다.

---

## 1. 배포 코드 구현 상태 — 실제 AWS 검증과 구분

아래는 코드 대조와 로컬 렌더로 확인한 구현 상태다. 실제 AWS 리소스 생성·권한·네트워크·rollout 성공 여부는 별도 검증 대상이다. 앞서 수행한 읽기 전용 계정 조회와 미실행 배포 단계는 [AWS 사전조회 상태](../../script.md#aws-사전조회-상태)에 구분해 기록했다.

| 영역 | 상태 | 근거 파일 |
|---|---|---|
| AI 단일 이미지 + command 분기 | ✅ 구현됨 | `AI/pipeline/Dockerfile`, `k8s/base/task-workers.yaml` (동일 `python -m app.workers.task_worker`, topic만 env 분기) |
| KEDA 스케일 정책 | ✅ 구현됨 | `k8s/base/keda-scaledobject.yaml` (ingest/query/agent 1~4·lag5, maintenance 1~2·lag2) |
| ECR repo ↔ 이미지 매핑 | ✅ 일치 | `infra/terraform/ecr.tf` (`fruition-{document-svc,access-svc,pipeline,converter}`) ↔ `k8s/overlays/aws/kustomization.yaml` |
| ALB host 라우팅 | ✅ 구현됨 | `k8s/overlays/aws/ingress.yaml` (`api.*`→document, `access.*`→access, healthcheck 8082) |
| **도메인별 Secret 배선** | ✅ **구현됨** | `k8s/overlays/aws/external-secrets.yaml`(생성) + `k8s/overlays/aws/workload-credentials.yaml`(소비: `env:[$patch:replace]` 후 `envFrom: secretRef: fruition-<domain>`) |
| 도메인별 ServiceAccount·IRSA | ✅ 구현됨 | `k8s/overlays/aws/service-accounts.yaml`, `workload-credentials.yaml`, `infra/terraform/eks.tf` |
| migration Job 분리 (runtime과 격리) | ✅ 구현됨 | `k8s/overlays/aws/migration-jobs.yaml` (access/document/ai 3개, migration 자격증명만) |
| 앱·Job NetworkPolicy (default-deny + 허용) | ✅ 구현됨 | `k8s/overlays/aws/networkpolicy.yaml` (`app` 라벨 기반 podSelector) |
| RDS 2대 / VPC / node group | ✅ Terraform 정의 구현됨 (실제 프로비저닝 미검증) | `infra/terraform/rds.tf`, `vpc.tf`, `eks.tf` |

> 참고: Secret은 문서 §9.2가 말한 "도메인별 분리"가 **이미 끝나 있다.** ExternalSecret이 `fruition-access/document/pipeline/converter`를 만들고, `workload-credentials.yaml` patch가 base의 단일 `fruition-secret` 참조를 도메인 secret으로 통째로 치환한다. base 매니페스트의 `fruition-secret`은 kind(로컬) 전용이며 AWS overlay에서는 사용되지 않는다.

---

## 2. 코드 수정이 필요한 것 — 현행 vs 목표(문서 §9)

아래는 문서 [aws-deployment.md](./aws-deployment.md) §9의 목표와 현행 구현의 차이다. 이미 구현된 timeout·메모리 limits와 추가 작업을 구분하고, 배포 전제와 장애·확장 시 검증 조건을 함께 기록한다.

| # | 항목 | 문서 서술 | 실제 코드 | 배포 차단? | 무엇을 언제 필요로 하나 |
|---|---|---|---|---|---|
| A | **outbox 동시 publisher 경쟁 방지** | replica 2 전 `FOR UPDATE SKIP LOCKED` 필요 | AI command의 조회·Kafka 발행·DB 삭제를 행 잠금과 동일 트랜잭션으로 보호. 로컬 PostgreSQL 경쟁·재시도·롤백 테스트 통과 | 실제 rolling update·소비자 재전달 검증 필요 | 락은 동시 폴링 경쟁을 막고 장애 후 재전달은 소비자 멱등성으로 처리. 별도 document edit publisher와 다른 다중 replica 경로도 확장 전 검증 |
| B | **동기 호출 circuit breaker** | document→pipeline-api에 timeout+Resilience4j | `PipelineClientFactory`에 연결 timeout 5초·호출별 read timeout 구현. Resilience4j/CircuitBreaker 없음 | ❌ | 기존 timeout 위에 circuit breaker 추가 검토. AI 장애 시 일반 문서 요청의 지연·오류율로 격리 효과 검증 |
| C | **PodDisruptionBudget** | access·document minAvailable 1 | `k8s/` 전체에 PDB 0건 | ❌ | replica 2 이상·노드 분산과 함께 적용. replica 1 + minAvailable 1은 drain 차단. Spot 강제 종료·노드 장애의 최소 Pod 보장은 아님 |
| D | **ResourceQuota / 자원 정책** | ns별 ResourceQuota | AWS 렌더의 Deployment 10개 모두 CPU·메모리 requests와 메모리 limits 있음. CPU limits·ResourceQuota 없음 | ❌ | CPU 상한 정책과 namespace 자원 예산 검토. KEDA 최대 확장·rollout 시 노드 용량과 일반 요청 영향 검증 |
| E | **RDS Multi-AZ** | SLA 단계 `multi_az=true` | `rds.tf` 둘 다 `multi_az=false` | ❌ (현재는 백업7일) | 다른 AZ의 standby로 자동 전환하는 기능 없음. 백업은 failover를 대체하지 않음 |
| F | **namespace 5분할** | access/document/ai/messaging/platform | 단일 `fruition` ns와 이를 강제하는 배포 스크립트·RBAC | ❌ | 격리 고도화. 매니페스트·NetworkPolicy·배포 코드·권한·DNS·테스트 변경 필요 |

### 단일 구성의 장애 영향과 복구 (E 상세)

| 구성 | 장애 영향 | 현재 복구 범위와 한계 |
|---|---|---|
| Single-AZ RDS 2대 (`rds.tf`) | 장애가 난 DB를 사용하는 기능 중단 | 일부 인스턴스 장애는 AWS가 자동 복구하지만, 다른 AZ의 standby로 자동 전환하지 못함. 데이터 복원은 백업 복구 절차와 별도 검증 필요 |
| Redis 1노드 (`elasticache.tf`: `num_cache_clusters=1`) | Redis 의존 기능 중단 | 가용 replica로 전환할 수 없어 단일 노드 복구를 기다려야 함 |
| Kafka 1 broker (`k8s/base/kafka.yaml`) | 이벤트 발행·소비 중단 | Pod 재기동·재스케줄과 스토리지 복구에 의존. 다른 broker로 전환할 수 없음 |
| NAT Gateway 1개 (`vpc.tf`: `single_nat_gateway=true`) | 해당 NAT 경로를 사용하는 private subnet의 외부 통신 중단 | 해당 AZ 장애 시 다른 AZ의 NAT로 전환하는 구성이 없음 |

Single-AZ의 자동 복구와 Multi-AZ failover는 별개다. 위 구성들의 장애·복구 시간을 각각 측정해야 하며, RDS Multi-AZ만으로 전체 서비스의 고가용성을 보장하지 않는다. [AWS Single-AZ 복구 설명](https://aws.amazon.com/blogs/database/amazon-rds-under-the-hood-single-az-instance-recovery/)

### namespace 현황 (F 상세)

- namespace를 **정의**하는 코드는 `k8s/base/namespace.yaml`, `k8s/platform/aws/namespace.yaml` **딱 2개**이며 둘 다 단일 `fruition`만 만든다.
- 앱·플랫폼 매니페스트의 `namespace: fruition` 참조와 Kustomize namespace 설정을 함께 재배치해야 한다.
- 도메인 격리는 namespace가 아니라 pod의 `app` 라벨 + podSelector NetworkPolicy로 구현돼 있다.
- `scripts/aws_deploy.py`는 `NAMESPACE = "fruition"`을 기준으로 다른 namespace의 앱 리소스를 거부한다. `k8s/platform/aws/deploy-rbac.yaml`의 앱 배포 Role·RoleBinding도 `fruition`에 묶여 있다.
- 5분할은 매니페스트뿐 아니라 배포 스크립트·RBAC·IRSA 신뢰 조건·서비스 DNS·배포 검증 테스트를 함께 변경해야 한다. NetworkPolicy의 교차 namespace 통신은 같은 peer 안에 `namespaceSelector`와 `podSelector`를 함께 지정해 namespace와 대상 Pod 조건을 모두 유지한다. 두 selector를 별도 peer로 나누면 OR 조건이 되어 허용 범위가 넓어진다. [Kubernetes NetworkPolicy 선택 규칙](https://kubernetes.io/docs/concepts/services-networking/network-policies/)

---

## 3. 전체 배포 계획 (4 Phase)

Phase 0에서 실제 환경의 배포 가능 여부를 검증한 뒤 안정성·가용성·격리를 보강한다. 번호는 기본 진행 순서이며, outbox 경쟁 제어는 rolling update 전에도 검토한다. Multi-AZ 전환은 circuit breaker나 outbox 구현 완료에 종속되지 않는다.

```text
Phase 0 : 배포 준비·실환경 검증 (필수 입력·플랫폼·DB·rollout·smoke)
Phase 1 : 안정성 보강 (기존 timeout + circuit breaker 검토·자원 정책)
Phase 2 : 가용성 확장 (outbox 경쟁 제어 → replica 2·PDB·배치 분산, Multi-AZ)
Phase 3 : 격리 고도화 (namespace·배포 도구·RBAC·DNS·정책 전환)
```

### Phase 0 — 환경 준비와 최초 배포 검증

현행 코드를 기준으로 준비한 실제 환경에서 배포를 검증한다. document·access는 replica 1, RDS는 single-AZ, namespace는 단일 구성이다. AI worker는 KEDA 정책에 따라 확장하며 실제 배포 성공은 아직 확인하지 않았다.

- 선행조건: [docs/script.md](../../script.md)의 IaC·플랫폼 절차에 따라 승인된 Terraform plan/apply, 필수 addon과 `k8s/platform/aws` 설치, 대상 계정·kubeconfig 확인을 완료한다. DB·role bootstrap과 권한 검증, Secrets Manager 필수 값, DNS·발급 완료 ACM 인증서, 배포 JSON 입력 및 지정 커밋 SHA의 ECR 이미지를 준비한다. `scripts/aws_deploy.py`는 DB·role이나 플랫폼을 대신 생성하지 않는다.
- 절차: `k8s/overlays/aws/README.md` + `docs/script.md`의 순차 배포(`scripts/aws_deploy.py`) — 입력·계정·context·플랫폼 읽기 확인 → 앱 Secret → DB 사전검증 → migration → 전체 rollout → smoke gate.
- 로컬 검증: `kubectl kustomize k8s/overlays/aws`로 구조와 Secret 참조를 확인하고, `scripts/aws_deploy.py render`로 실제 입력 치환·SHA 정합을 확인한다. 로컬 렌더 성공은 AWS 배포 성공을 의미하지 않는다.
- 실제 환경 검증: ExternalSecret·Kafka·KafkaTopic·ScaledObject Ready, DB 사전검증·migration Job Complete, 전체 Deployment rollout 및 공개 API HTTPS smoke gate 통과를 확인한다. 복구 절차는 별도로 검증한다.
- 한계: pod/노드 장애 "동안"의 무중단은 없음(replica 1). AI 장애가 문서 동기 경로로 전파될 수 있음(B 미구현). 현재 기본 RollingUpdate는 replica 1에서도 구·신 Pod를 겹쳐 실행할 수 있으므로, 최초 배포 후 갱신 전에 A의 동시 publisher 제어와 재전달 멱등성 검증을 선행한다.

### Phase 1 — 안정성 보강 (배포 후 우선 작업)

기존 timeout·자원 설정을 바탕으로 장애 영향과 용량을 검증하고 필요한 설정을 보강한다. **아래는 후속 코드/매니페스트 작업이며, PDB 적용은 Phase 2의 replica 확장과 연계한다.**

| 작업 | 수정 대상 | 검증 |
|---|---|---|
| B. 기존 timeout 위에 circuit breaker 추가 검토 | `Document`의 `PipelineClientFactory`·호출 클라이언트와 의존성 설정 | pipeline-api 중단·지연 주입 시 AI 의존 요청의 실패 응답·대기시간과 일반 문서 요청의 지연·오류율 확인, 복구 후 호출 재개 확인 |
| C. PDB 적용·노드 정비 절차 수립 | Phase 2에서 access·document를 replica 2 이상으로 분산한 뒤 AWS overlay에 `minAvailable: 1` 적용 | 두 Pod가 서로 다른 노드에서 Ready인 상태로 실제 drain을 수행해 정비 완료·서비스 가용성 확인 |
| D. CPU 상한·자원 예산 검토 | `k8s/base/`·AWS overlay의 기존 requests/메모리 limits, KEDA 최대 replica, namespace ResourceQuota 정책 | 최대 확장·rollout 여유를 포함한 용량 계산과 부하검증: Pending·OOM·CPU 경합 및 일반 요청 지연 확인. CPU limits 채택 시 throttling도 측정 |

단일 replica 운영 중에는 `minAvailable: 1` PDB를 무조건 추가하지 않는다. 노드 정비 시 계획 중단을 수용하거나, document-svc의 outbox 동시 발행 대책(A)을 먼저 마련한 뒤 임시 증설하고 다른 노드의 Ready Pod를 확인한다. PDB는 자발적 eviction을 제한하며 Spot 강제 종료·노드 장애 자체를 막지 않는다. [Kubernetes PDB 설정](https://kubernetes.io/docs/tasks/run-application/configure-pdb/), [중단 유형과 제약](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)

> B는 기존 timeout으로 제한되는 대기시간과 반복 실패의 영향을 먼저 측정한다. circuit breaker 하나만으로 문서 기능 전체의 장애 격리가 보장되지는 않으므로 기능별 검증 결과로 우선순위를 정한다.

### Phase 2 — 가용성 확장 (SLA 트리거 시)

```text
A(outbox 락 + 재전달 멱등성 검증) ──필수 선행──▶ replica 2 + anti-affinity
E(RDS Multi-AZ)  ← 독립적으로 함께 적용 가능
```

| 순서 | 작업 | 수정 대상 | 검증 |
|---|---|---|---|
| 1 | A. outbox 동시 폴링 제어 + 재전달 검증 | `AiCommandOutboxRepository`(`FOR UPDATE SKIP LOCKED`) + `AiCommandOutboxPublisher`의 조회·발행·삭제를 보호하는 트랜잭션 경계, 소비자 멱등 처리 확인 | 정상 동작: 2 publisher 동시 폴링 시 동일 행 경쟁 발행 없음. 장애 주입: Kafka 발행 성공 후 DB 삭제 커밋 전 종료·재시작 시 재전달돼도 업무 중복 처리 없음 |
| 2 | replica 2 + pod anti-affinity + PDB(C) | AWS overlay에서 document·access replica/배치 patch와 `minAvailable: 1` PDB 적용 | 서로 다른 노드의 2 Pod Ready 확인 후 drain 완료·서비스 가용성 검증 |
| — | E. RDS Multi-AZ | `infra/terraform/rds.tf` (`multi_az=true`), 앱의 DNS 갱신·DB 재연결 설정 점검 | failover 후 DB 전환 시간과 앱 요청 복구 시간을 각각 측정. 60~120초는 일반적인 DB failover 시간이며 보장값이 아님. [AWS failover 문서](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.Failover.html) |

> **AI command의 동시 publisher 제어는 구현됐으며 AWS rolling update·소비자 멱등성 검증이 남았다.** Kafka 발행 성공과 DB 행 삭제 커밋 사이에 종료되면 재발행되므로, at-least-once 전달을 전제로 소비자 멱등성을 검증해야 한다. 락을 exactly-once 발행 보장이나 전체 document-svc 다중 replica 검증 완료로 해석하지 않는다. [Kubernetes 기본 RollingUpdate 동작](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)

### Phase 3 — namespace 분리 (격리 고도화, 마지막)

문서 §9.2의 5-ns 분리. 파급이 커서 별도 작업으로 분리한다.

- 매니페스트·통신: namespace 생성 및 리소스 재배치, Kustomize 설정, ns별 ResourceQuota, ESO/KEDA/ALB 대상 ns, Secret·ServiceAccount 참조, 교차 namespace 서비스 DNS를 함께 변경한다. NetworkPolicy는 default-deny를 각 ns에 적용하고, peer의 `namespaceSelector`와 `podSelector`를 결합해 기존 app 라벨 제한을 유지한다.
- 배포·권한: `scripts/aws_deploy.py`의 단일 namespace 검증·조회·Job·배포 기록 처리를 도메인별로 변경하고, `k8s/platform/aws/deploy-rbac.yaml`의 Role·RoleBinding과 Terraform IRSA의 `namespace:serviceaccount` 신뢰 조건을 함께 맞춘다.
- 검증: `scripts/tests/test_aws_deploy.py`의 단일 ns 전제를 갱신하고 허용하지 않은 ns의 배포 거부를 유지한다. 렌더된 리소스·Secret·ServiceAccount 배치, 배포 계정의 ns별 권한, migration·rollout·smoke gate, 서비스 DNS 연결 및 NetworkPolicy 허용·차단 경로를 확인한다.
- 선행조건: Phase 0~2 안정화.
- 참고: 현재 단일 ns + app 라벨 NetworkPolicy로도 §9.3 보안 목표(내부 전용 차단, DB SG 분리, ALB 단일 진입점)는 상당 부분 이미 달성돼 있어, 이 Phase는 "추가 격리"이지 "필수 보안"이 아니다.

---

## 4. 요약 — 무엇을 언제 고치나

| Phase | 코드 수정 | 배포 전 필수 |
|---|---|---|
| 0 (배포 검증) | 실환경 검증 결과에 따라 판단 | 인프라·플랫폼·DB bootstrap·입력·이미지 준비, rollout·smoke 통과. rolling update의 outbox 경쟁·재전달 검증 |
| 1 (안정성) | 기존 timeout 유지 + circuit breaker 검토(B), 자원 정책(D), 단일 replica 유지보수 절차(C) | AI 장애 시 기능별 영향과 최대 부하 검증 |
| 2 (가용성) | outbox 경쟁 제어(A), replica·anti-affinity·PDB(C), Multi-AZ(E) | **A → document rolling update·replica 확장**, PDB는 replica·퇴거 정책과 함께 검증. E는 독립 적용 가능 |
| 3 (격리) | namespace·NetworkPolicy·배포 스크립트·RBAC·DNS·테스트·Quota | 전환 대상 환경 안정화 및 새 경계의 배포·통신·권한 검증 |

핵심 원칙:
- **실제 의존관계에 따라 순서를 정한다.** outbox 경쟁 제어는 document publisher 동시 실행에, PDB는 replica 수와 유지보수 절차에 맞춘다. 자원 정책과 Multi-AZ 전환을 circuit breaker 구현 때문에 미루지는 않는다.
- AGENTS.md §10에 따라 secret·outbox 등 교체 시 하위호환 폴백을 남기지 않고 완전 전환한다.
