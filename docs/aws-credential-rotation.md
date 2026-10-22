# 운영 자격증명 교체와 폐기

공통 Secret의 자동 교체 설정 부재만으로 자격증명 유출이나 취약점이 확정되지는 않는다.
이 문서는 종류별 교체, 소비자 검증, 이전 값 폐기, 교체 시점 기록을 정한다.
RDS 관리자 비밀번호는 RDS가 7일 주기로 관리한다. 아래 절차는 별도의 앱 자격증명에 적용한다.
이 문서와 도구 추가는 실제 DB 비밀번호 교체 완료를 뜻하지 않는다.

## 공통 운영 규칙

- 담당자는 교체 전 Secret의 `VersionId`, 변경 대상 키 이름, 소비자 목록, 복구 방법을 기록한다. 값은 기록하지 않는다.
- 쉘 인자, 환경 덤프, 터미널 출력, Git, Terraform 변수·state, CI artifact에 비밀값을 넣지 않는다.
- `scripts/aws_secret_tools.py`는 읽은 버전의 `AWSCURRENT`에 대해서만 교체한다. 다른 운영자 변경과 충돌하면 재조회·재검토한다.
- 도구는 AWS CLI에 비밀값을 전달할 때 0700 임시 디렉터리의 0600 파일을 사용하고 호출 후 삭제한다. 강제 종료 시 남은 임시 파일도 비밀정보로 취급한다.
- AWS 응답 유실 시 현재 버전을 확인한다. 실패 메시지를 보고 새 자격증명을 무조건 다시 생성하지 않는다.
- Secret 갱신은 Kubernetes 환경변수를 자동 갱신하지 않는다. ExternalSecret 동기화와 모든 관련 Deployment/worker의 rollout 및 새 연결을 검증한다.
- 소비자 오류·인증 실패율과 정상 업무 요청을 확인한 뒤 이전 값을 폐기한다. Secret 버전만 되돌리는 것으로 DB·외부 제공자 변경까지 복구되지는 않는다.
- 교체 증적에는 UTC 시각, 이전/신규 버전 ID, 대상, 검증 결과, 폐기 여부만 남긴다. 증적 저장소의 읽기 권한도 제한한다.

## DB 앱 계정

대상은 `access_runtime`, `core_runtime`, `ai_runtime`, 실제 배포된 converter 계정 및 별도 migration 계정이다.
관리자 비밀번호 교체가 이 계정들을 교체하지는 않는다. 공통 Secret에서 비밀번호뿐 아니라 같은 값을 포함한 URL도 일관되게 갱신한다.

1. 실제 소비자와 연결 풀을 조사한다. Secret의 runtime 비밀번호, `AI_DATABASE_URL`, `AI_CONVERTER_DATABASE_URL`, migration URL과 향후 실행될 Job도 포함한다.
2. 모든 새 연결에 RDS CA와 `sslmode=verify-full`을 사용한다. 자신의 비밀번호 교체 외에 관리자 권한을 앱에 추가하지 않는다.
3. PostgreSQL 단일 역할은 이전·신규 비밀번호를 동시에 받아주지 않는다. DB 변경과 Secrets Manager 변경도 원자적이지 않다. 현재 구조에서는 새 요청과 worker를 멈춘 계획된 점검시간을 사용하거나, 사전에 검증된 역할 교대 설계를 별도로 배포한다. 역할 교대 시에도 기존 최소 권한과 DB 간 접근 차단을 유지한다.
4. 점검시간에는 복구용 기존 연결을 유지하고 변경 전 Secret 버전을 다시 확인한다. 새 난수 비밀번호를 메모리에서 생성하고 드라이버의 안전한 인용 기능으로 자신의 역할 비밀번호를 변경한다. SQL·드라이버 오류에 비밀번호를 기록하지 않는다.
5. **새 연결**로 새 비밀번호와 TLS 검증 성공을 확인하고, 관련 비밀번호·URL 필드를 한 Secret 버전에 반영한다. CAS 충돌이나 응답 유실이면 DB·Secret 양쪽 상태를 조사하고 변경을 중단한다. DB만 변경된 경우 유지한 기존 연결로 복원하거나 새 값으로 Secret을 일치시킨 뒤 진행한다.
6. ExternalSecret을 동기화하고 각 Secret의 Ready 상태와 원본 버전 대응을 확인한다. 관련 앱과 worker를 재시작하고 rollout 완료, 새 DB 연결, 정상 업무 요청, 역할 권한 및 다른 DB 접근 거부를 검증한다. 기존 풀 연결만 성공하는 것은 검증이 아니다.
7. 이전 비밀번호로 **새 연결이 실패**하는지 확인한다. 다른 앱 자격증명을 변경하지 않는다. 오류 시 요청 재개 전에 DB·Secret·Pod 값을 같은 검증된 버전으로 복구한다.

현재 이 저장소는 위 단계를 원자적으로 보장하는 DB 자동 교체기를 제공하지 않는다.
한 줄의 `ALTER ROLE`이나 Secret 값 변경만을 자동화해 교체 완료로 보고하지 않는다.

## JWT 서명키

`scripts/aws_jwt_keys.py`는 RSA 3072-bit 키를 생성하고 Secret에만 저장한다. 개인키는 Access에만 투영하고 Document는 공개키만 받는다.
`stage`는 기존 RSA 키가 있으면 변경하지 않는다. 이전 HMAC 값은 명시적으로 폐기할 때까지 보존한다.

```sh
rtk proxy python3 scripts/aws_jwt_keys.py stage
```

초기 HMAC→RSA 전환은 다음 순서로 진행한다. 배포한 코드가 `JWT_SIGNING_MODE`를 지원하는지 먼저 확인한다.

1. Access에 RSA 개인키·공개키, Document에 공개키를 추가하고 기존 `JWT_SECRET`은 잠시 유지한다.
2. 24시간 이내의 명시적 UTC `JWT_LEGACY_UNTIL`을 양쪽에 설정하고 Document부터 RSA·HMAC 겸용 검증 버전으로 배포한다.
3. Access를 `JWT_SIGNING_MODE=legacy`로 배포한다. 모든 replica가 RSA를 검증하되 발급은 HMAC을 유지하는 상태인지 확인한다.
4. Access 전체를 `JWT_SIGNING_MODE=rsa`로 전환한다. 정상 로그인·refresh, 양쪽 인증과 잘못된 서명 거부를 확인한다.
5. 마지막 HMAC 발급 replica가 종료된 뒤 실제 최대 access-token TTL과 clock skew가 지나야 HMAC을 제거한다. 이 대기는 `JWT_LEGACY_UNTIL` 전에 끝내도록 충분한 여유를 둔다.
6. ExternalSecret의 HMAC 투영을 제거하고 양쪽의 모든 replica를 재배포한다. Document에 개인키·HMAC이 없고 이전 HMAC으로 새로 서명한 토큰도 거부됨을 확인한다.

기한이 지나면 legacy 발급은 자동 RSA 전환되고 HMAC 검증은 종료되므로, 기한 직전 발급된 HMAC 토큰의 정상 TTL을 보장하지 않는다.
단계별 전환을 지원하지 않는 버전에는 인증 트래픽을 중지한 점검시간이 필요하다.
동작 검증 후에만 아래 명령으로 HMAC 값을 공통 Secret에서 제거한다. 이전 Secret 버전에는 보존될 수 있으므로 접근 제어·버전 보존 정책도 관리한다.

```sh
rtk proxy python3 scripts/aws_jwt_keys.py retire-hmac --consumers-verified
```

정기 RSA 교체는 현재 공개키를 `JWT_PREVIOUS_PUBLIC_KEY`로 보존한다.

```sh
rtk proxy python3 scripts/aws_jwt_keys.py rotate
```

이 명령만으로 무중단 교체가 되지는 않는다. 특히 구 Access replica는 새 서명키 공개키를 모를 수 있다.
발급 트래픽을 중지하고 모든 검증 소비자 및 Access replica를 갱신·검증한 후 발급을 재개한다.
마지막 구 키 토큰 발급 시점부터 **실제 최대 access-token TTL과 clock skew**를 기다리고 구 replica가 남지 않았는지 확인한다.
그 후 이전 공개키를 폐기한다. 아직 사용 중인 이전 공개키가 있으면 다음 회전을 거부한다.

```sh
rtk proxy python3 scripts/aws_jwt_keys.py retire-previous --consumers-verified
```

탈취가 확인된 경우 기존 토큰을 계속 허용하는 유예보다 즉시 무효화가 우선일 수 있다. 영향 범위를 정하고 세션 재인증을 포함한 사고 대응으로 수행한다.

## 내부 토큰과 외부 API 키

`INTERNAL_CALLBACK_TOKEN`, `AGENT_INTERNAL_TOKEN`은 발신·수신 서비스 전체와 queue 재시도를 조사한다.
수신자의 구·신 토큰 동시 검증이 구현되어 있지 않으면 점검시간에 전체 소비자를 전환한다.
새 토큰 정상 요청 성공과 이전 토큰 거부를 검증한 뒤 폐기를 기록한다. 단순 Secret 변경 후 성공으로 간주하지 않는다.

외부 API·OAuth·SMTP 키는 제공자별 새 키 발급, 권한·한도 확인, 소비자 전환, 실제 호출 검증, 구 키 폐기 순서를 따른다.
제공자가 이중 키를 지원하지 않으면 제공자 절차에 맞는 점검시간이 필요하다. 접근 가능한 발급·폐기 권한 없이 임의의 난수로 대체하지 않는다.

`MFA_ENCRYPTION_KEY`는 저장된 MFA 정보를 복호화하는 데이터 암호화키이다. 단순 교체는 기존 사용자의 MFA를 망가뜨릴 수 있다.
키 버전별 복호화와 데이터 재암호화·복구 검증이 포함된 별도 마이그레이션 없이 변경하지 않는다.
KMS 자동 키 회전은 이 앱 비밀값들의 회전을 대신하지 않는다.

## 교체 기한과 증적 태그

DB 앱 자격증명과 JWT 서명키는 운영 정책상 최대 90일 이내 교체·검증한다. 이는 이 프로젝트의 관리 기준이며 모든 제공자의 보편적 필수 기한은 아니다.
공통 Secret에 다음 태그를 **교체·검증·이전 값 폐기 완료 후에만** UTC ISO8601 (`2026-10-22T12:00:00Z` 형식)로 기록한다.

| 태그 | 기록 조건 |
| --- | --- |
| `fruition:db-credentials-rotated-at` | 관리 대상 앱 DB 계정 전부 교체 완료. 일부만 완료하면 최종 태그를 앞당기지 않고 개별 증적만 남김 |
| `fruition:jwt-signing-key-rotated-at` | 새 서명키로 발급·전체 검증 성공 및 이전 키 폐기 완료. 단순 `stage`에는 기록하지 않음 |

태그가 없으면 감시는 Secret `CreatedDate`를 보수적 기준으로 사용한다. 태그·Secret 변경일 자체를 실제 교체 증명으로 취급하지 않는다.
감시가 알림을 보냈다고 자동 교체가 실행된 것은 아니다. 경보 담당자가 위 절차와 증적을 확인하고 완료 시점을 기록한다.
외부 API 키와 MFA 암호화키를 이 정책에 맞추려 일괄 변경하지 않는다.

## 도구 검증

```sh
rtk proxy python3 -m unittest discover -s scripts/tests -p test_aws_secret_rotation.py -v
```

테스트는 CAS 충돌, AWS 성공 응답 유실, 임시 label 정리 실패, 임시 파일 권한·삭제, 오류 메시지 비밀값 억제,
JWT 단계 재실행, 이전 키 보존과 조기 폐기 방지를 검증한다. 운영 서비스 통합 검증을 대신하지 않는다.
