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
