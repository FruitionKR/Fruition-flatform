# ADR-0021: AWS 관측과 운영 준비

상태: 설계 방향 결정, 구현·AWS 검증 대기.

## 맥락

현재 AWS 구성에는 앱 로그 수집·운영 대시보드·장애 알림이 없다. 로컬 Prometheus/Grafana와 EKS 제어 영역 로그는 앱 운영 관측을 대신하지 않는다. DB 백업 설정도 복원 성공이나 서비스 전체의 복구 시간을 증명하지 않는다. 다섯 저장소로 분리한 뒤에도 서비스 간 장애 조사와 복구 책임은 연결되어야 한다.

초기 대상은 소규모 외부 피드백 환경이다. 현재 단일 API Pod·Kafka broker·Redis 노드와 Single-AZ RDS를 상시 고가용성 구성으로 표현하지 않는다.

## 결정

1. platform이 CloudWatch Logs/Logs Insights, Container Insights, Dashboard, Alarm/SNS와 수집기 IAM을 관리한다. CloudWatch Observability EKS add-on의 Fluent Bit으로 컨테이너 stdout을 수집한다. add-on 버전·설정은 실제 EKS/리전 호환성을 확인한 뒤 고정한다. [공식 설치 문서](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/install-CloudWatch-Observability-EKS-addon.html)
2. 서비스 저장소는 JSON 로그·민감정보 제외·HTTP/Kafka 상관 ID·업무 지표를 소유한다. platform은 수집 경로와 알림을 소유한다. Vercel 로그는 별도 조회 경로로 명시하고, EKS 수집기가 자동 수집한다고 가정하지 않는다.
3. Prometheus 형식 지표는 CloudWatch agent 수집을 사용한다. 공식 지원 유형인 counter/gauge/summary를 기준으로 설계한다. histogram으로부터 p95를 얻는다고 가정하지 않고 초기 API 지연은 ALB 지표를 사용한다. [지원 지표와 수집 방식](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ContainerInsights-Prometheus.html)
4. Application Signals 자동 계측은 초기에는 명시적으로 비활성화한다. 분산 추적은 기본 관측 검증 후 별도 비용·성능 검토를 거친다. add-on의 자동 활성화 동작을 확인하고 지원 configuration schema로 제어한다. [Application Signals 설정](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-EKS.html)
5. 외부 배포 전 로그 검색, 실제 실패 알림 수신, 조회/긴급 역할 분리, 장애 Runbook, 격리 환경의 데이터 복원 시험을 완료한다. RTO/RPO는 후보 목표와 실측 결과를 구분한다. 복구 시험은 운영 트래픽을 연결하지 않은 격리 환경에서 시작한다. [복원 시험 원칙](https://docs.aws.amazon.com/wellarchitected/2023-10-03/framework/rel_backing_up_data_periodic_recovery_testing_data.html)
6. Document 변환 큐·편집 outbox의 동시 실행 안전성을 롤링 배포 전에 보완한다. 서비스별 image digest release manifest와 업무 smoke를 준비한 뒤 HPA·복제본 확대를 진행한다.

구체적인 작업 순서·파일·담당 역할은 [아키텍처 보완 계획](../architecture.md#aws-운영-보완-계획), 알림 초안·Runbook·증적 기준은 [실행 계획](../script.md#aws-운영-보완-실행-계획)을 따른다.

## 대안과 기각 사유

- AWS에 Prometheus/Grafana/Loki를 직접 운영: 기존 도구와 유사하지만 저장소·업그레이드·백업·자체 장애 대응 책임이 추가된다. 초기 인력과 범위에서 채택하지 않는다. 로컬 개발용 구성은 유지한다.
- AMP/AMG를 초기부터 추가: Prometheus 활용도가 커지면 재평가할 수 있으나 초기에는 관측 서비스와 권한 체계를 늘릴 필요가 확인되지 않았다.
- `kubectl logs`만 사용: Pod 교체 후 로그 조사와 지속 알림·장기 비교를 충족하지 못한다.
- 처음부터 모든 서비스에 분산 추적 적용: 업무 로그와 장애 알림의 공백을 먼저 해결하고, 비용·데이터 범위를 측정한 뒤 도입한다.

## 결과

platform은 공통 운영 구성을, 각 서비스는 자신의 오류·작업 상태·복구 계약을 책임진다. CloudWatch 사용료와 AWS 종속성이 발생하므로 로그 보존·metric dimension·중복 수집·일일 유입량을 관리한다. 요청 ID나 사용자 ID를 metric dimension에 넣지 않는다.

이 결정은 운영 기능이 이미 설치되었다는 의미가 아니다. 담당자·연락 채널·운영 시간·관측 예산·복구 목표를 확정하고 검증 관문을 통과해야 외부 배포 준비가 완료된다. 실제 AWS 배포는 이번 작업 범위에 포함하지 않는다.
