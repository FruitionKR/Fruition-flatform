# AWS 자격증명 보완과 적용 상태

2026-10-22 보안 점검 후 DB 서버 인증서 검증, JWT 서명권한 분리, 사람의 AWS 관리 접근, 자격증명 교체·감시를 보완한다.
아래 표는 문서 작성 시점의 운영 확인 결과이며 코드 존재와 운영 적용 완료를 구분한다.
공개 문서에는 실제 계정 번호·접속 주소·자격증명·내부 검증 원문을 포함하지 않는다.

| 항목 | 확인·적용 상태 | 완료를 위한 검증 |
| --- | --- | --- |
| DB TLS 서버 검증 | DB 사용 Deployment 9개에 `verify-full` 적용. 정상 연결과 잘못된 호스트명 거부 확인 | 후속 migration Job과 새 이미지 배포에서도 CA 마운트·설정 유지 |
| JWT 서명권한 분리 | RSA 키 생성·Secret 저장 완료. 앱 RSA 전환은 후속 배포 대상 | Access 개인키 발급, Document 공개키 검증, 잘못된 서명 거부, 구 HMAC 폐기 |
| IAM 사용자 MFA | MFA 필수 관리 역할 생성. 강제 정책은 `enforce_human_mfa_only=false`, 기존 사용자 관리자 권한 유지 | 소유자 MFA 등록, 별도 역할 세션 검증 후 강제 정책 적용·직접 관리자 권한 제거 |
| 루트 자격증명 | 비밀번호·액세스 키·서명 인증서 모두 없음. MFA 없음만으로 취약 상태라고 판단하지 않음 | 자격증명 생성 없이 조직의 루트 접근 관리 상태 유지·감시 |
| 교체 절차 | 종류별 교체·검증·폐기 절차와 JWT 도구 작성 | 실제 교체별 소비자 검증과 이전 값 폐기 증적 |
| 일일 감시 | 관련 13개 리소스 적용, 수동 최초 실행 성공 및 CloudWatch 지표 6개 확인 | 후속 정기 실행과 경보 대응 유지 |

DB 앱 비밀번호 자동 교체기는 구현하지 않았고 이번 변경을 DB 비밀번호 교체 완료로 기록하지 않았다.
교체 증적 날짜 태그도 설정하지 않았다. RDS 관리자 비밀번호의 기존 7일 자동 교체와 앱 계정 교체는 별개이다.

## DB TLS와 권한

RDS CA를 ConfigMap으로 제공하고 Java JDBC·Python/libpq 소비자가 이를 사용해 서버 인증서 체인과 호스트명을 검증한다.
`PGSSLMODE=verify-full`과 CA 경로를 적용하며, JDBC에는 드라이버에 전달되는 CA 속성도 구성한다.
Secret URL에 포함된 `sslmode`가 환경변수보다 우선할 수 있으므로 URL과 환경변수 양쪽을 일치시킨다.
이 변경 전에도 TLS 암호화는 사용했지만 서버 신원 확인을 강화할 필요가 있었다.

앱은 DB 관리자 계정 대신 서비스별 runtime 역할을 사용하며, 이번 변경은 DB 관리자 권한을 앱에 추가하지 않는다.
IAM DB 인증 사용 여부는 SQL 권한과 별개이다. IAM 인증을 단순히 켜는 것으로 SQL 최소 권한이나 탈취 대응이 해결되지 않는다.

관련 구현:

- `k8s/overlays/aws/configmap-aws.yaml`
- `k8s/overlays/aws/rds-ca-mount.yaml`
- `k8s/overlays/aws/certs/rds-ca-bundle.pem`
- `scripts/aws_deploy.py`, `scripts/aws-ops-db-query.sh`

인증서 오류가 나면 배포·CA 버전·정확한 RDS 호스트명을 점검한다. 인증서 검증을 끄는 것을 정상 복구 절차로 사용하지 않는다.

## JWT 서명권한 분리

대칭 JWT 키를 여러 서비스에 배포하면 검증 서비스도 토큰을 서명할 수 있다.
RSA 전환에서는 Access에 개인키를 투영하고 Document에는 공개키만 투영한다.
키는 운영 도구로 생성해 Secrets Manager에 저장하며 Git·Terraform state·터미널에 개인키를 출력하지 않는다.

키 생성만으로 앱의 서명 알고리즘이 바뀌지는 않는다. ExternalSecret, 앱 이미지, 환경변수와 모든 replica 전환을 함께 검증해야 한다.
검증에는 정상 발급·인증, 변조된 서명 거부, 의도하지 않은 알고리즘 거부, 만료·발급자·대상 검증이 포함된다.
Document 런타임에 개인키와 기존 HMAC 값이 없는지도 값 출력 없이 확인한다.

구 replica와 신규 토큰이 섞이면 인증 실패가 발생할 수 있으므로 현재 도구는 무중단 교체를 보장하지 않는다.
전환 순서, 유예기간, HMAC 및 이전 공개키 폐기는 [교체 절차](aws-credential-rotation.md)를 따른다.

## 사람의 AWS 관리 접근

`infra/terraform/human-access.tf`는 지정 IAM 사용자가 MFA 인증 후 한 시간 이내 임시 관리 역할을 사용하도록 구성한다.
이 역할은 운영 관리 작업을 위한 관리자 권한을 유지한다. 역할 사용 전환 자체가 세부 업무별 최소 권한 분할 완료를 뜻하지 않는다.
GitHub OIDC와 앱 IRSA는 사람의 장기 액세스 키와 별도로 유지한다.

현재 강제 정책을 적용하지 않은 이유는 소유자 MFA 등록과 독립적인 정상 관리 세션 검증이 아직 필요하기 때문이다.
기존 경로를 먼저 차단하면 후속 배포·복구에 필요한 관리 접근까지 잃을 수 있다.
다음 순서로 전환한다.

1. 계정 소유자가 자신의 인증 장치로 IAM 사용자 MFA를 등록한다. OTP·MFA seed를 문서·채팅·자동화 로그에 남기지 않는다.
2. MFA가 포함된 임시 역할 세션을 별도로 만들고 호출자 역할, 필요한 AWS 조회, EKS 접근과 복구 작업을 검증한다.
3. 검증된 역할 세션에서 `enforce_human_mfa_only=true` 계획을 검토·적용한다. 직접 서비스 접근과 다른 역할 우회가 거부되는지 확인한다.
4. 기존 IAM 사용자에 직접 연결된 `AdministratorAccess`를 제거하고 역할 경유 경로를 재검증한다. MFA 미등록 상태에서는 이 단계를 완료로 보고하지 않는다.
5. 사람의 장기 키에 의존하는 자동화가 없는지 확인한다. 별도 SSO 또는 검증된 로그인 경로로 역할 사용이 가능해진 뒤 불필요한 장기 키를 비활성화·폐기한다.

MFA를 등록해도 기존 장기 API 키가 자동으로 폐기되지는 않는다. 장기 키를 폐기하기 전까지 직접 서비스 접근 제한의 실제 효과를 검증해야 한다.
자격증명이 없는 루트에는 MFA를 등록하려고 새로운 비밀번호나 액세스 키를 만들지 않는다.

## 교체 증적과 일일 감시

[자격증명 교체 절차](aws-credential-rotation.md)는 DB 계정·JWT·내부 토큰·외부 제공자 키를 각각 다룬다.
MFA 데이터 암호화키는 데이터 재암호화 설계 없이 변경하지 않는다.

`infra/lambda/credential_guard/handler.py`는 Secrets Manager의 메타데이터와 IAM 계정·사용자 상태만 조회한다.
Lambda 역할에는 `GetSecretValue`나 `kms:Decrypt` 권한을 부여하지 않는다.
MFA 장치와 직접 연결 정책은 전체 페이지를 조회한다. 그룹·인라인·조직 정책을 합친 전체 유효 권한 분석을 대신하지 않는다.

감시는 다음을 CloudWatch `Fruition/Security`에 발행한다.

- 비밀번호가 있는데 MFA가 없거나, 액세스 키·서명 인증서가 있는 루트 상태
- 지정 IAM 사용자의 MFA 부재와 직접 연결된 `AdministratorAccess`
- DB 앱 자격증명·JWT 서명키의 마지막 검증된 교체 증적부터 지난 일수
- 전체 조회 및 지표 발행이 성공했음을 나타내는 heartbeat

DB와 JWT는 90일 관리 기준을 사용한다. 증적 태그가 없으면 Secret 생성일을 보수적 기준으로 삼고, 잘못된 날짜·미래 날짜는 경보 대상이 된다.
단순 Secret 수정일로 교체 기한을 초기화하지 않는다. 태그는 실제 교체·소비자 검증·이전 값 폐기를 모두 마친 뒤에만 기록한다.

감시가 실패하면 정상 heartbeat를 발행하지 않는다. 일일 실행이 UTC 경계를 넘는 지연을 허용하도록 heartbeat는 두 일간 평가 구간의 누락을 경보한다.
CloudWatch의 누락 데이터 평가 방식 때문에 정확히 48시간 만에 경보한다고 보장하지는 않는다.
다른 보안 지표는 누락 시 기존 상태를 유지하므로 **정상 지표와 heartbeat를 함께** 확인한다. 감시 중단을 보안 조치 완료로 해석하지 않는다.

## 검증과 적용 증적

```sh
rtk proxy python3 -m unittest discover -s scripts/tests -p test_aws_secret_rotation.py -v
rtk proxy python3 -m unittest discover -s scripts/tests -p test_aws_credential_guard.py -v
rtk proxy terraform -chdir=infra/terraform validate -no-color
```

교체 도구 테스트는 CAS 충돌, 응답 유실, 비밀값 전달·오류 억제, 키 보존·폐기 조건을 확인한다.
감시 테스트는 pagination, 루트 자격증명 조건, 날짜 처리, 실패 시 heartbeat 미발행과 최소 IAM 권한을 확인한다.
단위 검증은 운영 적용 증적을 대신하지 않는다. 배포 담당자는 계획·적용·실제 소비자 동작을 확인한 뒤 상태 표를 갱신한다.
이 변경의 플랫폼 AWS 테스트 198개와 Terraform 검증이 통과했다. 실제 DB TLS 동작 검증과 감시 리소스 적용은 위 상태 표에 별도로 기록했다.
