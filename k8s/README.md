# Kubernetes

서비스의 Kubernetes 배포 설정을 보관한다.

- `base/`: 공통 Kubernetes 리소스
- `kind/`: 로컬 kind 클러스터 설정
- `overlays/`: 환경별 Kustomize 설정
- `platform/aws/`: EKS 플랫폼 공용 설정(배포 RBAC·SecretStore·StorageClass·Fargate 로깅)

## kind 로컬 절차

`base/kustomization.yaml`은 앱 계층만 포함한다. 상태 계층(`postgres.yaml`·`redis.yaml`·`minio.yaml`)과 `secret.yaml`은 kind 전용이라 아래처럼 개별 적용한다. 자동화 스크립트는 없으며 실제 검증 기준은 Compose(`scripts/dev-up.sh`)다.

1. `kind create cluster --config k8s/kind/cluster.yaml` (document-svc 30080, access-svc 30081을 호스트로 노출)
2. base가 참조하는 로컬 이미지(`fruition-access-svc:dev`, `fruition-document-svc:dev`, `fruition-converter:latest`, `fruition-mvp-dev-*:latest`)를 빌드해 `kind load docker-image --name fruition <image>`로 주입
3. `kubectl apply -f k8s/base/namespace.yaml` 후 Strimzi operator(fruition namespace 대상)와 KEDA를 설치
4. `kubectl apply -f k8s/base/secret.yaml`, MFA 키 Secret `fruition-mfa` 생성([운영 절차](../docs/script.md) 참조)
5. `kubectl apply -f k8s/base/postgres.yaml -f k8s/base/redis.yaml -f k8s/base/minio.yaml`
6. `kubectl apply -k k8s/base`

AWS는 `overlays/aws`를 사용하며 상태 계층은 RDS·ElastiCache·S3로 대체된다([overlays/aws/README.md](overlays/aws/README.md)).

## Kafka worker 확장과 임시 저장소

Kafka lag에는 처리 중인 미커밋 메시지도 포함된다. 5개 worker ScaledObject는 lag가 있는 파티션 수로 replica 상한을 제한하고,
HPA가 120초 동안 관측한 확장 권고를 안정화한 뒤 60초당 최대 1 Pod씩 늘린다. 축소 안정화는 300초다.
AWS의 TLS trigger 교체에도 같은 파티션 제한을 적용한다.
장시간 작업 때문에 offset이 그대로인 정상 파티션을 누락시키지 않도록 `excludePersistentLag`는 켜지 않는다.
이는 과도한 증설을 완화하는 설정이며 실행 중 작업과 대기 작업을 정확히 분리하는 지표는 아니다.
지속적인 여러 파티션의 backlog에는 기존 최대 replica까지 확장되며, 첫 확장에는 최대 약 2분의 지연이 추가된다.
근거: [KEDA Kafka scaler](https://keda.sh/docs/2.18/scalers/apache-kafka/).

maintenance worker는 `/tmp`의 1536Mi 제한과 별도로 `ephemeral-storage: 2Gi`를 예약한다.
노드에 공간이 없으면 작업 시작 후 디스크가 부족해지는 대신 스케줄링 단계에서 Pending이 될 수 있다.
공통 ConfigMap의 `EMBEDDING_TIMEOUT_SECONDS=10`, `AI_PURGE_READ_TIMEOUT=120s`는 기존 서비스 기본값을 명시한 것이다.
