# 인프라 변경 기록

## 2026-10-29

### 운영 경보 Discord 메시지 한국어 판정 근거

- CloudWatch SNS 이벤트의 경보 조건·평가 구간·측정값을 한국어로 설명하고 영어 원문 사유를 보존한다. 데이터 누락으로 OK가 된 경우 실제 복구 확인이 필요함을 안내하며 근본 원인을 추정하지 않는다.
- 운영 지표별 알람 설명과 점검 안내를 한국어로 보강했다. 임계값과 예산 알림 경로는 유지하며 운영 반영에는 Lambda 코드와 알람 설명의 Terraform 배포가 필요하다.
- AWS 회귀 테스트 266개, 로컬 종료 테스트 2개, Terraform fmt/validate와 비밀정보 검사를 통과했다. 운영 배포·Discord 발송은 수행하지 않았다.

### PR #131 리뷰: 누락 데이터 처리 설정과 비정상 진단 정보

- `notBreaching` 경보가 데이터 누락으로 OK가 되면 매번 "실제 복구 여부 추가 확인"으로 안내됐다. 이제 SNS `Trigger.TreatMissingData`를 표시하고, 그 설정에 따라 정상 판정됐다고만 설명한다. 실제 0건이나 복구 완료는 단정하지 않는다. 설정이 없거나 알 수 없으면 기존처럼 추가 확인을 안내하고, 누락이 포함된 ALARM은 누락을 유일한 원인으로 단정하지 않는다.
- 비표준 입력에서 `ComparisonOperator`·`OldStateValue`가 list/dict이면 `TypeError`로 알림 전체가 실패했다. 진단용 부가 정보는 타입을 확인한 뒤 비정상 값의 줄만 생략하고, 필수 필드(`AlarmName`, `NewStateValue`) 검증은 유지한다. `DatapointsToAlarm`이 없는 비표준 입력은 N-of-N을 가정하지 않고 평가 구간만 표시한다.

### PR #130 리뷰: converter 종료 순서 보장

- `dev-down.sh --graceful`에서도 의존성 없는 converter와 DB가 동시에 종료돼 drain 중 연결이 끊겼다. converter의 `stop`을 먼저 완료한 뒤 전체 `down`을 실행하고, `stop` 실패 시 인프라·볼륨을 보존한다.
- 기본·graceful·볼륨 삭제·조합 옵션과 stop 실패를 회귀 테스트 2개로 검증했다. 기존 코드에서 실패하고 수정 후 통과하며 AWS IaC CI에도 이 테스트를 연결했다.
- 격리된 실제 Docker 프로젝트에서 수정 전 `conv-term → db-term → conv-db-GONE`, 수정 후 `conv-term → conv-db-alive → db-term`을 확인했다. 시험 컨테이너·네트워크는 정리했고 운영 환경은 변경하지 않았다.

### #90 인프라 후속 작업과 운영 확인

- Kafka scaler에 lag가 있는 파티션 수 제한, 120초 확장 안정화, 분당 1 Pod 확장 제한을 추가했다. 장기 실행을 누락시키는 persistent lag 제외는 사용하지 않는다. 정확한 대기 작업 지표 분리는 여전히 별도 개선이다.
- maintenance worker의 임시 저장소 2Gi 예약, 임베딩 10초·AI 파기 120초 환경변수, 기존 RDS 로그 그룹의 선택적 선언형 import를 추가했다. 신규 환경에서는 import 목록을 비운다.
- 로컬 종료에 converter를 명시적으로 포함하고 기본 대기를 30초로 제한했다. `--graceful`은 7800초를 기다린다. 시간 초과로 끊긴 작업은 재전달될 수 있다.
- 삭제된 Wiki cutover 스크립트의 실행 안내와 전용 환경변수를 정리했다. 운영 core_db에서 V74 성공을 읽기 전용 조회로 확인했다.
- 운영 읽기 전용 확인(2026-10-29): access의 현재 ID 전체(삭제 유예 포함)와 AI reconciliation 대상 10개 workspace/5개 user 소스를 비교하고 export 이전 1시간 안전 여유를 적용했다. workspace 후보 0, user 후보 3, 시각 근거 부족·최근 생성 제외 0건이다. 이는 현재 파기 후보 수이며 과거 `--apply` 실행 여부를 증명하지 않는다. 데이터 파기는 수행하지 않았다.
- 운영 음성 원장: `speech_synthesis` / `gpt-realtime-2.1-mini` 성공 1건(마지막 2026-10-23 08:31:46 UTC), 취소 2건. 실제 공급사 TTS 성공 근거이며 사용자 기기의 청취 성공까지 증명하지 않는다. 현재 회의·회의 전사 segment는 모두 0건이라 실시간 회의와 iOS 무음 스위치는 별도 실측이 필요하다.
- 검증: AWS 회귀 테스트 266개, 로컬 종료 옵션 테스트 1개(3개 모드), Terraform fmt/validate, Bash 문법 및 diff 공백 검사를 통과했다.
- 운영 확인은 SSM runner의 일회성 읽기 전용 DB Pod로 수행하고 Pod를 삭제했다. Secret·개인 ID·본문은 결과에 기록하지 않았다. 이 변경의 Kubernetes/Terraform 운영 적용은 수행하지 않았다.

## 2026-10-23

### 이메일 인증 요청 Redis 권한 복구

- 인증 요청 제한에 새로 분리된 `auth:email-verification-request:*` 키가 Access ACL에서 누락돼 500 응답이 발생했다. 기존 제한용 selector에 해당 패턴만 추가했다.
- 이메일·IP별 카운터와 TTL, 기존 이메일 중복 확인 버킷의 독립성, GET/SET/DEL 및 인접 키 거절을 실제 Redis로 검증했다. 전체 AWS 검증 261개와 Terraform 두 root 검증 통과.
- 운영 Access Redis 사용자에 동일 ACL을 적용하고 active 상태 확인 후 실제 웹 이메일 인증 요청의 202 응답을 확인했다. 비밀번호·DB·서비스 이미지는 변경하지 않았다.

### PDF 표시 정책과 명시적 AI 편입 배포 검증

- 운영 화면의 `frame-src`가 PDF 저장소 출처를 명시적으로 허용하는지도 검사해, 파일 다운로드만 통과하고 실제 미리보기가 차단되는 배포를 검출한다.
- PDF 변환 뒤 AI run만 기다려 타임아웃되던 검증을 보완했다. 이번 probe가 생성한 변환 완료 문서만 편입 API로 한 번 요청하고 실제 AI 완료까지 확인한다. 사용자 문서·워크스페이스 설정은 바꾸지 않는다.
- 자동 편입 완료 문서는 중복 요청하지 않으며, 변환 상태만 완료된 문서를 AI 성공으로 처리하지 않는다. PDF smoke 테스트 11개와 AWS 전체 테스트 260개 통과.

## 2026-10-23

- curl 재시도 출력은 `/dev/null` 대신 접근 제한된 임시 일반 파일로 받으며 요청 뒤 제거한다. 공개 라우팅 복구 중 일시적 503→200 전환에서도 정상 재시도한다.
- 세 DB migration이 이미 완료된 뒤 공개 검증에서 실패한 릴리스에 한해 명시적 `recover` 동작을 추가했다. 별도 계획의 원본 시작/실패 감사 해시, 정확한 target manifest·이미지, 성공 migration Job, 쓰기 중단과 after 스키마를 모두 대조하며 SQL을 재실행하지 않는다. 복구 시작/실패 기록은 새 immutable 기록으로 남기고 기존 감사 기록은 보존한다.
- 실제 HTTP 재시도 및 미완료/변경된 상태 차단, 업무 smoke 실패 시 앱 중지, 자동 재시도 거부를 회귀 검증한다. 복구도 GitHub main·Environment 승인·이미지 검증과 로그인/문서/AI·PDF gate를 따른다.

- 점검 전환의 예상 HTTP 503 검사에서만 curl 재시도를 끈다. 503 재시도 중 `/dev/null` 출력 재설정 오류(exit 23)로 DB 변경 전에 배포가 중단되던 문제를 해결하며, 세 공개 경로의 정확한 503 검사와 기존 DB·감사 gate는 유지한다.
- 재시도가 활성화되면 exit 23으로 실패하는 회귀 조건으로 점검 배포 성공을 검증한다.

## 2026-10-22

- Strimzi Helm 1.1.0의 실제 실행 형태인 `command` 생략 + 단일 launcher `args`를 maintenance inventory에서 인식한다. 기존 기본/명시적 command 실행 형태를 유지하고 임의 command·추가 args·두 launcher 혼합은 거부한다.
- 실제 Deployment·Pod 실행 형태를 반영한 fixture로 14개 Deployment에서 정확히 12개 앱을 검사하며, 위조 실행 8종을 Deployment/Pod 각각에서 차단하는 회귀를 추가했다. maintenance 15개·전체 AWS 246개 테스트를 통과했고 source secret scan의 기존 SHA/fingerprint 오탐 10건을 확인했다. 이미지·계정·owner·labels 및 DB session·scaler·503·fingerprint gate는 유지한다.

- PostHog 실제 수집·실패/재시도·PDF·초대·내보내기·복원 검증과 운영 DB 격리 복원/실제 이미지 migration 리허설 결과를 기록했다. 세 DB의 정확한 전후 schema hash, 기존 immutable audit 전체 hash와 12개 live image digest를 묶은 release 검토를 추가했으며 reset/repair 없이 기존 main 점검 배포 경로를 사용한다.

- maintenance inventory가 실제 Strimzi cluster operator를 앱 writer로 오인하던 문제를 수정했다. 검증된 Helm labels·Pod labels·service account·단일 operator 이미지와 실행 설정, 대응 ReplicaSet 소유 Pod만 제외해 전체 14 Deployment 중 기존 entity operator와 함께 정확히 12개 앱을 검사한다.
- 이름 변경·위장 labels·다른 이미지/계정·추가 컨테이너·잘못된 Pod owner·활성 앱을 거부하는 회귀를 추가했다. 기존 성공 audit·fingerprint·DB session·scaler·503 검사를 유지하며 AWS 계약 244개, Kustomize 3경로와 Terraform 두 root 검증을 통과했다. 운영 변경과 이미지 release recipe 변경은 수행하지 않았다.

- 기존 설치의 비가산 pending migration을 위한 `maintenance-cutover`를 추가했다. 이전 성공 release 전체 해시·현재 이미지 digest·DB 전후 fingerprint와 실제 리허설/복원/중단 근거를 묶고, 기존 expand-only/none/initial-install 및 rollback 검사를 유지한다.
- 503 Ingress, 기존 ALB binding 제거, 전체 앱 중지, scaler·CronJob·writer Pod/세션 부재를 확인한 뒤 실제 migration을 실행한다. 실패/중단 시 시작 기록을 보존해 후속 배포를 차단하며 정상 종료 후 scaler 복구는 운영자가 수행한다. 앱 deployer 권한은 CronJob 조회만 추가했다.
- AWS 계약 240개(실제 로컬 PostgreSQL 세션 차단 포함), Terraform 두 root fmt/init(backend=false)/validate, Kustomize 3경로, shell 30개 문법과 변경 preflight 3종 ShellCheck를 통과했다. 전체 ShellCheck의 기존 경고와 release 문서 SHA 오탐 8개는 별도 확인했으며 새 비밀정보는 발견하지 않았다.
- [실행 절차와 증거 계약](../aws-maintenance-cutover.md)을 작성했다. runner Docker 부재와 로컬 Docker 대안, 실제 리허설 미수행 상태를 명시했으며 worker는 운영 변경·analytics 송신을 하지 않았다.

- PostHog dev에 PR98이 병합된 main(`03c47f0`)의 운영 보안 계약을 통합했다. RSA 개인키 Access 전용·HMAC 제거·DB verify-full·WAF Secret 분리를 보존하고, preflight 충돌은 optional analytics와 TLS 검사를 함께 유지하도록 해결했다. MFA 강제 기본 false는 유지한다.
- AWS 계약 230개, Terraform 두 root fmt/init(backend=false)/validate, Kustomize 3경로, shell 29개 문법·변경 shell ShellCheck를 통과했다. 비밀정보 검사에서 기존 release 문서의 Access 소스 SHA 오탐 8개만 확인했으며 실제 비밀정보는 발견하지 않았다.
- [배포 호환성 감사](../posthog-deployment-compatibility.md)에 서비스별 SHA·migration 파괴적 변경·cutover/restore 증적 요구를 기록했다. Document V74–76 등은 expand-only 배포를 차단하며 live DB 이력은 미검증이다. AWS 변경·analytics 송신·배포는 수행하지 않았다.

- 통합 `dev-up.sh`에서도 Document·Access·frontend 실행 직전에 `local_analytics_env`를 적용한다. 개별 실행 스크립트와 동일하게 기본 수집 off·운영 설정 격리·명시적 LOCAL_* 설정·서비스별 Git SHA를 보장하며 기존 `SERVICE_ENV_FILE` 전달 순서는 유지한다.
- 실제 launch 함수를 임시 Git 저장소와 가짜 실행 파일로 검증하는 회귀 테스트 5개를 추가했다. 기존 184개를 포함한 AWS 계약 테스트 189개, Bash 문법, Kustomize 3개 경로 렌더링을 통과했다. 신규 테스트는 수정 전 코드에서 모두 실패하며 실제 서비스·AWS·analytics 호출은 수행하지 않는다.
- ShellCheck는 기존 `docker rm $container_ids`의 SC2086 외 추가 경고가 없음을 확인했다.

- PostHog 알파의 frontend·Access·Document·AI 런타임 환경을 추가했다. 기본 수집 off, 빈 토큰, production 환경과 서비스별 source SHA를 사용하며 토큰은 전용 ExternalSecret의 단일 키로만 주입한다.
- 수집 활성화 시 토큰 누락·잘못된 형식을 배포 preflight에서 차단하고, local native/Compose 실행은 별도 LOCAL_* 설정으로 운영 토큰 상속을 막는다. 기존 expand-only migration·fingerprint gate와 다른 Secret 키는 유지한다.
- AWS 계약 테스트, Terraform/Kustomize 및 shell 검증을 수행했다. [운영 절차](../posthog-operations.md)에 안전한 Secret 병합·승인 배포·중지·mock 검증을 정리했다. 실제 토큰 저장·analytics 송신·운영 배포는 실행하지 않았다.

- 운영 RSA 전환 후 로그인·문서 접근·refresh와 변조/필수 claim 누락 거부를 확인했다. 기존 토큰 TTL+여유시간 뒤 모든 Pod와 공통 Secret 현재 버전에서 HMAC을 제거하고, 이전 키로 새로 서명한 토큰의 401 거부도 확인했다. 플랫폼 215개와 운영 hotfix 382/1,036개 테스트가 통과했다.
- MFA 전환 뒤 본인 암호 변경이 차단되지 않도록 자기 계정 변경만 허용했다. 다른 사용자 변경과 직접 관리자 동작은 회귀 테스트 4개 및 실제 IAM 정책 시뮬레이션으로 거부됨을 확인했다.
- WAF 접근 코드 조회를 전용 Secret으로 분리해 이후 Terraform refresh가 앱 JWT 개인키 전체를 state로 읽지 않게 했다. 값 출력 없는 복사 도구와 관련 회귀 테스트 6개를 추가했다.
- MFA 필수 임시 관리자 역할과 직접 접근·다른 역할 우회 차단 정책을 추가했다. 사용자 MFA 등록·별도 접속 검증 전에는 강제 정책을 켜지 않는다.
- 비밀값 접근 없이 루트 자격증명·사용자 MFA·직접 관리자 정책·교체 경과일을 매일 감시한다. guard 테스트 10개, Terraform 검증과 운영 최초 지표 6개 발행을 확인했다.
- JWT 개인키를 Access에만 투영하고 Document에는 공개키만 전달하도록 분리했다. Secret 버전 충돌 방지·키 생성·기존 키 폐기 도구와 단계별 전환 절차를 추가하고 관련 테스트 12개를 통과했다.
- DB 연결과 migration·운영 조회를 `verify-full`로 강화하고 공식 RDS CA를 마운트했다. 운영 DB 소비자 9개와 잘못된 호스트명 거부를 확인했으며 AWS 테스트 198개가 통과했다.
- WAF 자동 스캔 대응으로 민감 파일 경로 차단, 지속/대량 차단 경보 분리, WAF 로그 미수신·ALB 자체 5xx 경보를 추가했다.
- ALB 접근 로그를 비공개 SSE-S3 버킷에 30일 보관하고 Controller annotation으로 활성화했다. 배포 전 버킷 소유 계정·리전·비공개 정책 검사와 메타데이터 전용 권한을 추가했다.
- 빈 도메인/접근 코드로 운영 접근 코드 규칙이 제거되지 않도록 사전 검증을 추가했다. SQLi 확장 본문 규칙도 기존 문서 요청 조건 안에서만 처리하고 나머지 요청은 재차단한다.
- AWS 계약 테스트 176개와 Terraform·Kustomize 검증을 통과하고, 운영 민감 경로 49건·문서 본문 57건 및 실제 로그를 대조했다. 접근 코드 규칙 일시 제거·복구와 범위 밖 검증 사항은 [운영 적용 기록](../aws-waf-review-2026-10-22.md#7-2026-10-22-운영-적용-기록)에 남겼다.
- Public ECR 다운로드 한도로 `minio-init` 이미지 pull이 실패하던 CI를 보완했다. 같은 AWS CLI 2.37.4 버전의 공식 Docker Hub 이미지를 다중 아키텍처 digest로 고정했다. 별도 Compose 프로젝트에서 4개 서비스의 정상 기동, MinIO·Kafka 초기화 종료 코드 0, 생성 버킷 조회 성공을 확인했다.

- 운영 JWT 전환 검증용 수동 Security authentication smoke workflow를 추가했다. feedback 환경의 검증 계정으로 공개 HTTPS 로그인·Access/Document 조회·refresh 교체·변조 서명 거부를 확인하고 테스트 세션을 로그아웃한다. 문서 생성·변경과 AWS 설정 변경은 수행하지 않으며 자격증명·응답 본문은 로그나 artifact에 남기지 않는다. 독립 회귀 테스트 7개를 통과했다.
- self-hosted runner 공통 계약에 맞춰 AWS_EC2_METADATA_DISABLED를 명시하고 관련 테스트 10개를 통과했다.
