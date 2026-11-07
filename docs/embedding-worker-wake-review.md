# 임베딩 작업자 기동 조건 검토

2026-11-07 운영 읽기 전용 확인과 A안 범위다. 코드 이미지·DB 스키마·비밀값 변경은 없다.

## 문제와 변경

embedding-server의 KEDA trigger가 query·agent만 감시해 ingest·maintenance만 실행될 때 서버가 0대에 머물렀다. 두 작업자를 기존 kubernetes-workload selector에 추가한다. 로컬 Compose에서는 두 호출자가 embedding-server healthy 상태를 기다리도록 의존성을 맞춘다.

## 실제 관찰과 비용 추정

- 두 작업자는 모두 minReplicaCount=0, cooldownPeriod=600초다. 마지막 활성 시각은 ingest 03:25:04 UTC, maintenance 03:28:34 UTC이며 이후 둘 다 실제 replicas=0을 확인했다. 항상 켜진 작업자가 아니다.
- 임베딩은 min=0/max=1, cooldown=300초, 요청 CPU 500m/메모리 3Gi다. 작업자가 계속 실행되면 서버도 계속 켜진다. 모든 감시 대상이 사라진 뒤 5분과 스케일러 지연까지 유지되므로 비대화형 작업의 마지막 lag 이후 약 15분 이상 유지될 수 있다.
- 최근 24시간 Container Insights는 600초 간격의 희소 표본이다. ingest가 관측된 분 8개, maintenance 7개, embedding 17개이며 앞 두 작업자가 있고 embedding이 없던 표본 시각은 5개다. 이는 정확한 가동 시간이 아니다. 표본 하나를 10분으로 보는 거친 추정은 추가 약 50분/일이며 기동·종료 꼬리 시간과 표본 사이 작업을 누락할 수 있다.
- 같은 시각 AWS Spot API의 서울 m6i.xlarge/m7i.xlarge Linux 요금은 가용영역별 시간당 0.0625~0.0836 USD다. 기존 노드 여유 안에 들어가고 노드 종료를 늦추지 않으면 EC2 한계 비용은 0일 수 있다. 추가 노드 1대가 필요한 경우 위 50분 추정은 약 0.052~0.070 USD/일이며 24시간 계속 유지되는 경우 약 1.50~2.01 USD/일(30일 45.00~60.19 USD)이다. Spot 변동, 노드 잔류 시간, EBS·네트워크·모델 호출 비용은 별도다.
- 실제 작업 빈도에 따라 항상 켜질 수 있다. 큐 기반 trigger는 작업자 idle 유지 시간을 줄일 대안이지만 consumer offset·실행 중 작업·대화형 작업의 기존 trigger를 함께 설계해야 하므로 이번 A안에는 포함하지 않는다.

## 배포 및 검증 범위

기존 성공 이미지 묶음 a377209ef0d7ef2ac918aee26bc117704c9880ee를 그대로 쓴다. 배포 실행기는 성공 manifest의 고정 리소스를 재사용하고 SCALING_KINDS만 현재 저장소에서 반영하므로 새 이미지를 만들거나 migration을 실행할 필요가 없다. 기존 릴리스 검토 기록과 DB 스냅샷 available 상태를 다시 확인하고 feedback 게이트가 있는 deploy.yml로 적용한다. 운영 검증 결과는 실제 실행 후 별도 보고하며 이 문서는 아직 배포 성공을 주장하지 않는다.

## 남은 한계

Kubernetes에서 query·agent는 init container로 임베딩 준비를 기다리지만 ingest·maintenance에는 그 대기가 없다. 이번 변경은 서버를 깨우지 못하는 문제를 해결하며 모델 적재가 끝나기 전 요청의 ConnectError/503 경쟁까지 보장하지 않는다. 준비 대기 추가는 Deployment 변경을 수반해 별도 묶음·검토가 필요한 범위다. 운영 시험에서 기동과 요청 시각을 대조한다.
