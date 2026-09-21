# 요청으로 EKS 노드 깨우기

`request_wake_enabled = true`이면 EKS 밖의 Lambda가 1분마다 절전 상태를 확인합니다. 노드가 모두 종료된 `asleep` 상태에서 기존 ALB에 HTTPS 요청이 들어와 `HTTPCode_ELB_5XX_Count`가 발생하면 일반 노드의 최소·희망 수를 2대로 복구합니다. AI 노드의 Launch 중단도 해제하므로 KEDA와 Cluster Autoscaler가 작업에 맞춰 다시 확장할 수 있습니다. ALB의 라우팅·도메인·WAF는 그대로 사용합니다.

**첫 요청은 보관하거나 재실행하지 않습니다.** ALB가 502·503·504 등을 반환할 수 있으며 지표 전달과 노드·Kafka·API 기동에 수분이 걸립니다. 기동 후 요청을 다시 보내야 합니다. 업로드·결제·문서 수정 등의 요청을 무조건 자동 재시도하면 안 됩니다. 프런트엔드는 별도 저장소에 있으므로 이 변경에는 로딩 화면이나 프런트엔드 재시도가 포함되지 않습니다.

## 절전 기준

자동 종료는 하지 않습니다. HTTP 요청이 없어도 Kafka consumer나 AI 작업이 진행 중일 수 있으므로, 운영자가 진행 중인 작업과 배포가 없음을 확인한 뒤 절전을 요청합니다. 이 절차는 노드를 종료하며 API·Kafka·백그라운드 작업을 중단합니다. EKS 노드 수 축소는 PDB만으로 작업 완료를 보장하지 않습니다. 영속 볼륨과 외부 DB는 삭제하지 않지만 메모리·임시 디스크 작업은 유실될 수 있습니다.

노드가 0대이면 Cluster Autoscaler 자체도 멈추므로 외부 Lambda가 기동을 담당합니다. 절전 도중 기존 Autoscaler가 노드를 다시 만들지 못하도록 두 노드 그룹의 ASG `Launch` 프로세스만 잠시 중단합니다. 다른 ASG 프로세스는 변경하지 않습니다. 기동 시 중단을 해제합니다. 기존에 운영자가 Launch를 중단해 둔 그룹은 절전을 거부합니다.

DynamoDB에 `sleeping → asleep → waking → awake` 상태를 기록하고 Lambda 동시 실행을 1개로 제한합니다. 요청 감지는 `asleep`이 된 시각부터 시작합니다. `sleeping` 동안 Pod 축출로 생기는 502·504는 감지 대상이 아니므로 모니터링·봇 요청이 있어도 절전이 완료됩니다. 노드 그룹 축소는 PDB와 무관하게 노드당 최대 15분 뒤 강제 종료됩니다. EKS의 노드 그룹 `desiredSize`는 ASG 값을 주기적으로만 동기화하므로, 완료 판정과 기동 용량은 ASG의 실제 `DesiredCapacity`를 함께 봅니다. AWS API 호출 중 일부가 실패해도 다음 1분 실행에서 재개합니다. `awake`는 일반 노드 2대 이상이 EC2 `InService`이고 EKS 노드 그룹이 ACTIVE라는 뜻이며, 앱의 정상 응답까지 보장하지 않습니다.

## 설치

관측 설정과 같은 `observability_alb_arn_suffix`를 사용합니다. 기존 앱 ALB의 ARN에서 `loadbalancer/` 뒤 `app/이름/ID`를 확인하고 배포용 tfvars에 입력합니다.

```hcl
request_wake_enabled = true
observability_alb_arn_suffix = "app/실제-ALB-이름/실제ID"
```

기존 backend와 비밀 변수 주입 절차로 Terraform plan을 생성하고 변경 내용을 확인한 뒤 적용합니다. 설치 자체는 실행 중인 노드를 끄지 않습니다. CloudWatch 5분 수집 설정과 별개로 **ALB의 AWS 기본 지표**를 조회합니다. EKS 일반 노드 설정의 기본 최소 2대는 유지합니다.

```bash
terraform -chdir=infra/terraform output request_wake
```

Lambda 공개 URL이나 외부 HTTP 제어 API는 만들지 않습니다. 아래 명령은 대상 계정에서 해당 Lambda의 `lambda:InvokeFunction` 권한이 있는 운영자만 실행할 수 있습니다. 절전 명령은 비동기 재시도를 피하기 위해 반드시 `RequestResponse`로 보냅니다. 응답의 `FunctionError` 여부와 결과 파일을 함께 확인합니다. 예약 실행과 겹쳐 `TooManyRequestsException`이 나면 수초 뒤 다시 시도합니다.

## 사용

진행 중인 작업·배포가 없음을 확인한 뒤 절전:

```bash
aws lambda invoke --region ap-northeast-2 --function-name fruition-request-wake \
  --invocation-type RequestResponse --cli-binary-format raw-in-base64-out \
  --payload '{"action":"sleep","confirm_no_active_jobs":true}' /tmp/fruition-sleep.json
cat /tmp/fruition-sleep.json
```

상태 확인:

```bash
aws lambda invoke --region ap-northeast-2 --function-name fruition-request-wake \
  --invocation-type RequestResponse --cli-binary-format raw-in-base64-out \
  --payload '{"action":"status"}' /tmp/fruition-wake-status.json
cat /tmp/fruition-wake-status.json
```

`asleep`이 된 뒤 API의 읽기 전용 경로에 요청을 한 번 보내고, 수분 뒤 상태가 `waking`, `awake`로 바뀌는지 확인합니다. 그 뒤 API health와 실제 읽기 요청을 확인합니다. 지표 지연 때문에 첫 요청 직후 상태가 바뀌지는 않을 수 있습니다. ALB 자체의 health check는 이 요청 실패 지표에 포함되지 않습니다. HTTP(80) 요청은 ALB가 301로 리다이렉트하므로 깨우지 않으며 HTTPS 요청만 감지합니다. WAF에 차단된 요청이나 ALB의 404 응답은 깨우지 않습니다. WAF를 통과해 실제 경로에 도달한 봇·모니터링 요청은 깨울 수 있습니다.

요청이 없어도 즉시 기동을 시작하거나, 수집 지표 장애 시 복구:

```bash
aws lambda invoke --region ap-northeast-2 --function-name fruition-request-wake \
  --invocation-type RequestResponse --cli-binary-format raw-in-base64-out \
  --payload '{"action":"wake"}' /tmp/fruition-wake.json
cat /tmp/fruition-wake.json
```

## 운영·복구

- `asleep`이 된 1분 구간의 ALB 오류는 지표가 늦게 도착해도 감지합니다. 첫 요청을 놓치지 않도록 선택한 동작입니다. 절전 명령 직후가 아니라 `asleep` 전환 직후 요청이 있었다면 바로 깨어날 수 있습니다.
- 절전 중에는 노드 지표가 없어 기존 `telemetry_missing` 경보가 발생할 수 있습니다. Lambda 오류 경보와 controller 상태를 함께 확인합니다.
- **Terraform 적용·노드 그룹 교체·기능 비활성화 전에 반드시 wake 후 정상 응답을 확인합니다.** EKS 모듈은 `desired_size`만 무시하고 `min_size`는 추적하므로, 절전 중 apply하면 최소 2대 복원이 시도되지만 Launch가 중단돼 인스턴스가 뜨지 않고 EKS 업데이트가 실패할 수 있습니다. controller 상태는 이를 알지 못합니다. 절전 중 apply하지 않습니다. 잠든 동안 그룹이 교체되면 다른 ASG를 건드리지 않고 오류를 냅니다.
- 복구 실패 시 `/aws/lambda/fruition-request-wake`와 EKS node group 상태를 확인합니다. 최후 수단으로 운영자가 기존 두 ASG의 `Launch`를 `aws autoscaling resume-processes`로 복구하고 일반 그룹을 `aws eks update-nodegroup-config --scaling-config minSize=2,desiredSize=2`로 올릴 수 있습니다. 기동 성공 후 controller의 `wake`를 다시 실행해 상태도 복구합니다.
- 원격에서 실제 절전·기동 시험은 진행 중인 작업이 없는 시간에 합니다. 단위 테스트와 Terraform validate만으로 Kafka 복구 시간이나 실제 첫 요청 이후 정상화 시간을 확정할 수 없습니다.

## 비용

절전 중 워커 EC2 실행 요금과 해당 컨테이너 관측량이 줄어듭니다. EKS 관리비, ALB, NAT, EBS, RDS, Redis, 배포 runner 비용 등은 계속 발생합니다. 추가 리소스는 Lambda의 분당 짧은 실행, DynamoDB의 작은 상태 항목, EventBridge 예약 실행, CloudWatch API 조회·로그·경보입니다. 클러스터나 DB를 없애는 기능이 아닙니다.

근거: [ALB 지표](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html), [EKS scaling config](https://docs.aws.amazon.com/eks/latest/APIReference/API_NodegroupScalingConfig.html), [ASG 프로세스 중단](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-suspend-resume-processes.html).
