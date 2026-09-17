# Discord 예산 알림

AWS Budgets → SNS → Python 3.12 Lambda → Discord 일반 텍스트 채널의 webhook.
코드·로컬 검증 준비 단계이며 실제 AWS 생성·Discord 전송은 별도다.

## 동작과 비용 범위

- 계정 전체의 월 실제 USD 비용이 $400, $550, $650을 **초과**하면 알린다. 프로젝트 태그 필터가 없으므로 같은 계정의 다른 자원도 포함된다. AWS Budgets 기본 cost type 설정을 사용한다. Vercel·외부 LLM 제공자 청구는 포함되지 않는다.
- AWS 비용 집계는 지연될 수 있다. 이 알림은 지출 상한이나 자동 종료 기능이 아니다. 동일 월의 actual 임계치 알림은 지속적인 반복 알림이 아니다.
- Secret은 `fruition/budget-discord-webhook`이며 **일반 문자열 SecretString에 URL 한 개**를 저장한다. JSON key/value 형식이 아니다. `https://discord.com/api/webhooks/<id>/<token>` 형태의 일반 채널 webhook을 사용한다. forum/thread URL은 지원하지 않는다.
- Terraform은 빈 Secret 컨테이너만 만든다. URL용 변수/SecretVersion/data 조회가 없어서 웹훅 URL이 Terraform state에 들어가지 않는다. 기존 앱 Secret과 분리되어 앱 Pod에 전달되지 않는다.
- VPC 연결·NAT·Provisioned Concurrency를 추가하지 않는다. 128MB, 20초 제한, 로그 14일 보관. boto3는 Lambda 런타임 제공 버전을 사용한다. archive provider가 handler.py만 zip으로 패키징한다.
- Secret은 매 호출 읽으므로 변경 후 Lambda 재배포는 필요하지 않다. Secret이 비어 있으면 알림 전송은 실패한다. apply 성공만으로 알림 준비가 완료된 것은 아니다.

## 실제 적용 시 준비

1. 검토된 Terraform plan을 적용한다. 기존에 이메일 예산 리소스가 있다면 이전 $500/$700 예산 삭제와 새 예산 생성이 plan에 나타나는지 확인한다. 기존 개인 tfvars의 `budget_email`은 제거한다.
2. `terraform -chdir=infra/terraform output -json budget_notifications`의 Secret ARN을 확인한다.
3. Secrets Manager 콘솔에서 해당 Secret의 일반 텍스트 값에 webhook URL을 입력한다. URL은 채팅·Git·tfvars·CLI 명령 인수·로그에 기록하지 않는다.
4. 명시적으로 전송이 승인된 테스트 메시지를 SNS 콘솔의 해당 topic에 게시한다. 이 테스트는 실제 Discord 메시지를 보낸다. 게시 역할에는 그 topic의 `sns:Publish`가 필요하며 앱 배포 역할에는 이 권한이 없다.
5. Discord 수신, CloudWatch의 `budget_notification_delivered`, Lambda Errors/DestinationDeliveryFailures, SNS NumberOfNotificationsFailed, SQS 대기 메시지 수를 확인한다. SNS 테스트는 Budgets 자체의 발행 성공을 증명하지 않으므로 SNS 정책과 각 Budget의 구독 상태도 확인한다.

## 실패와 복구

- HTTP 429/5xx, 네트워크 오류, 잘못된 webhook/Secret, 응답 확인 실패는 안전한 오류 코드로 실패한다. HTTP 리다이렉트를 따르지 않고 원문 메시지·URL·응답 body·SDK 예외는 로그에 남기지 않는다. Discord 멘션은 비활성화한다.
- Lambda 비동기 함수 오류는 최대 2회 추가 재시도한다. 이벤트 최대 나이는 1시간이다. 장시간 rate limit은 재시도 동안 해소되지 않을 수 있다. 실패 이벤트는 SQS `fruition-budget-alert-failures`에 14일 보관된다. SNS가 Lambda에 전달하지 못한 이벤트도 같은 큐에 보관한다.
- 재시도·중복 이벤트·전송 성공 후 네트워크 단절 때문에 같은 알림이 중복 전달될 수 있다. exactly-once 전달을 보장하지 않는다.
- 실패 큐를 확인하고 Secret·권한·Discord 응답 원인을 수정한다. Lambda destination 레코드는 `requestPayload.Records[0].Sns`, SNS DLQ 레코드는 원래 SNS 메시지 형식일 수 있으므로 내용을 먼저 확인한다. 원래 Subject/Message를 SNS topic에 다시 게시하고 수신 확인 후 실패 큐 항목을 삭제한다. destination 전체를 예산 메시지로 재게시하지 않는다.
- 재시도와 큐 보관은 구현되어 있지만, 이 전송기 자체가 고장났을 때 별도 채널로 알리는 기능은 없다. 배포 후 실패 지표와 큐를 운영 점검 대상에 포함한다.

## 로컬 검증 (외부 전송 없음)

```sh
python3 -m unittest discover -s scripts/tests -p 'test_aws_budget_discord.py' -v
terraform -chdir=infra/terraform init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform validate
```

전체 IaC 검증은 `scripts/aws-iac-validate.sh`를 사용한다. 변경된 archive provider lockfile도 함께 유지한다. AWS IAM/SNS/Budgets/Discord 실제 연결과 재시도·SQS 수신 검증은 로컬 mock 테스트로 대체되지 않는다.
