# PostHog dev와 운영 보안 계약 통합 검토

## 범위와 근거 (2026-10-22)

- 시작 dev: `872227d5fc67d63d554159976cc8ac6ef5026f1b`.
- 통합 main: `03c47f0ce5117d9fe05ae90ec315bb9ea2469887` (PR98 병합).
- 보안 원본: PR98 `cdf15bb67541e7ee71a97311c9b4c99e3d82e409`. main과 이 SHA의 파일 tree는 같다.
- 기존 소유자 브랜치/작업 공간은 변경하지 않았다. 새 dev 기반 child에서 main을 병합했다.
- [보안 적용 기록](aws-credential-hardening.md), [교체 절차](aws-credential-rotation.md)의 운영 확인은 원본 작성자의 과거 증적이다. 이번 작업은 AWS/Secret/Kubernetes 조회·변경 또는 배포를 수행하지 않았으며 현재 live 상태를 재검증하지 않았다.

## 통합 결과

Access만 RSA 개인키를 받고 Document는 공개키/키 ID만 받는다. AWS ExternalSecret에서 제거된 HMAC을 다시 요청하지 않는다. 이전 공개키 필드는 원본 계약대로 유지한다. 빈 값도 포함해 실제 Secret에 해당 property가 존재하는지 배포 담당자가 값 출력 없이 확인해야 한다.

DB runtime, migration Job, preflight와 운영 조회의 `verify-full` 및 공개 RDS CA 마운트를 유지한다. JDBC CA 속성, Python/libpq CA 경로와 URL의 TLS 옵션도 함께 유지한다. WAF는 전용 Secret만 조회하며 앱 개인키 전체를 Terraform data source로 읽지 않는다.

main의 기존 관리 역할·메타데이터 감시 선언을 함께 보존했다. `enforce_human_mfa_only=false` 기본값을 바꾸지 않았고 IAM/MFA 정책을 적용하지 않았다. 전체 main tree 통합으로 향후 dev→main 역병합에서 이미 배포된 보안 리소스를 제거하는 일을 피한다.

PostHog 전용 optional Secret/env, 기본 수집 off, 서비스별 APP_VERSION, local launcher 격리와 활성화 시 토큰 preflight를 보존했다. 충돌한 `preflight_job`은 TLS 검증과 analytics 검사를 모두 실행한다. 실제 analytics 송신은 하지 않았다.

## Migration 소스 감사

원격 main/dev를 fetch한 뒤 아래 SHA를 읽기 전용으로 확인했다. 다른 서비스 소스는 수정하지 않았다.

| 서비스 | 검토 dev SHA | main SHA / 마지막 SQL 버전 | dev 마지막 SQL 버전 |
| --- | --- | --- | --- |
| Access | `4dc09a99ec7d1913380f558fa763b70cf11efecd` | `bf2af788e843f3b49da8c6c0547b979a531c26f5` / V27 | V29 |
| Document | `a56e97f2133daa1d3f1d7b9ccb4b29ac573cce45` | `12aa94f78195b094112c7b12fba8e64cd6f82a33` / V79 | V82 |
| AI | `b1d2d2b11c0278180583281c6d803f4e0cf2b404` | `844d021c12f353821ad8ee836fd91bacc7818740` / 단일 멱등 DDL | 단일 멱등 DDL |

PR98의 “Access 6개·Document 19개 미배포”는 **버전 목록이나 live schema fingerprint가 아니다**. 위 main 상한에서 단순 계산하면 V21/V60이지만, 당시 소스와 연속 이력이 같다는 가정에 의존한다. 이를 운영 사실로 사용하지 않는다. 보수적으로 Access V22–29, Document V61–82를 검토했으며 실제 pending 목록은 운영 Flyway 성공 이력·checksum·이미지 소스와 대조해야 한다.

| 범위 | 소스에서 확인한 변화 | 배포 전 조건 |
| --- | --- | --- |
| Access V22–23, V26, V28–29 | 파기 요청·동의·avatar·메일 알림·analytics outbox 추가 | 기존 행/FK/check, 신규 background job의 파기·메일 부수효과, 구/신 앱 호환성 확인 |
| Access V24, V27 | 기존 workspace 모델/provider 값을 UPDATE | 원래 값 보존·정책 승인과 구 앱 모델 해석 검증; DDL 추가만으로 분류하지 않음 |
| Access V25 | 권한 테이블과 auto-ingest 기본 false 추가; 기존 멤버 권한 미이관 명시 | 기존 멤버 권한 축소와 OWNER 부여 절차, 혼합 버전 인가 검증 |
| Document V61–67, V69–73 | hash/권한/충돌/알림/청구/크레딧/결제/음성 구조·가격 시드 | 기존 데이터 제약 및 원장 잔액 대사, 시드 effective_from, 비용·권한·background job 동작 확인 |
| Document V68, V79 | AI command outbox JSON 모델/provider UPDATE | 발행 중인 command와 replay의 원래 snapshot·중복 처리·혼합 worker 호환성 검증 |
| Document V74 | legacy AI 테이블 23개 DROP TABLE; CASCADE 없음 | core→ai 소유권 이전 완료, 보관본 row count/무결성 및 실제 복원 시험, 모든 구 reader/writer 중단 증거 |
| Document V75 | PDF queue attempts/next_attempt_at과 claim index 제거, Kafka batch 구조 추가 | 구 polling worker 중단, 진행 PDF drain/취소/재개·batch 중복/결과 병합 검증; 구 이미지 단순 rollback 불가 |
| Document V76 | transcription claimed_at/index 제거, 진행 전사 failed UPDATE | 진행 녹음 처리/재시도 계획, 새 run ID/Kafka 결과 경로와 구 worker 중단 검증 |
| Document V77–78, V81 | workspace 버전·AI 출처·folder 컬럼 추가, 기존 version 출처 backfill | 원본 hash/이력 유지와 NULL·backfill 호환성 검증 |
| Document V80 | 열린 충돌을 version 이력으로 보관, revision 증가·outbox 발행·충돌 종료 | concurrent 편집 중지, R보다 큰 기존 version 충돌 검사, 본문 hash/모든 충돌 보존, replay·restore 시험 |
| Document V82 | analytics outbox/context/query terminal, chat export lineage, 재귀 origin/first-ingest view | 기존 문서 lineage/cycle/workspace 경계, VIEW 비용, 이전 ingest 최소 시각·off 상태 provenance 검증 |
| AI ai_schema.sql + migrate_ai_schema.py | 전체 DDL 재실행, 제약 교체·title 타입 변경·trigger 재생성, agent_runs UPDATE, converter UPDATE 권한 회수 후 컬럼 제한 재부여, analytics outbox 추가 | live schema와 전체 diff, 기존 행 제약 충족, 취소 journal/checkpoint/사용량 기록, runtime·converter 최소 권한 및 새 연결 검증 |

AI에는 Flyway식 순차 버전 이력이 없다. `IF NOT EXISTS`가 있어도 constraint/trigger 교체와 데이터 UPDATE가 추가 변경만이라는 증거는 아니다. 현재 live AI DDL·역할 권한 snapshot 없이 pending 변화나 무중단 호환성을 확정할 수 없다.

## 실제 배포 차단 조건과 필요한 증적

1. 이 PR은 구성 호환성을 해결하지만 **현재 all-dev를 배포 가능하다고 승인하지 않는다**. V74–76이 pending이면 파괴적 migration을 `expand-only`라고 표시할 수 없다. 기존 `none`은 migration을 실행하지 않아 새 앱 스키마 요구를 만족시키지 못한다. 데이터가 있는 운영에 `initial-install`을 쓰거나 fingerprint/설치 기록을 삭제·초기화하지 않는다.
2. 배포 담당자가 현재 Access/Document Flyway 버전·checksum, AI schema/권한 fingerprint, 각 hotfix digest·source/JAR 연결 증적, 성공 release 기록을 확보해야 한다. PR98에 기록된 hotfix는 일반 main 이미지와 같다고 가정하지 않는다.
3. 익명화된 복원 복제 환경에서 정확한 pending 순서로 시험한다. V74 보관 테이블·문서/위키/객체 연결, V75 PDF batch, V76 전사, V80 충돌 본문·revision, 청구 원장 합계 및 role ACL을 전후 대조한다. DB snapshot/PITR와 객체 버전 복원까지 실제 복원 시간·허용 데이터 손실 범위·실패 중간 지점 복구 결과를 기록한다.
4. 구/신 이미지 혼합 시간 동안 로그인·refresh·RSA claim 거부, Document/AI 읽기·쓰기·권한, queue drain/replay/취소 및 중복 방지를 검증한다. schema가 변경되면 구 성공 release fingerprint와 달라 자동 코드 rollback이 거부되는 것이 정상이다. HMAC 전용 이미지 rollback이나 TLS 검증 해제는 복구 수단이 아니다.
5. 파괴적 구간은 별도의 검토된 단계적 expand/contract 설계 또는 명시적 점검시간 전환 절차가 필요하다. 현재 배포 도구는 그 경로를 제공하지 않는다. 이번 PR은 migration SQL이나 gate를 변경하지 않았다. 실제 수행한 compatibility/restore 증적 URL과 정확한 release SHA가 일치해야 하며, 단위 테스트 URL을 DB 복원 증거로 대체하지 않는다.
6. 원본 Secret의 RSA/이전 공개키 property 및 DB URL의 verify-full, CA mount와 새 연결을 담당자가 확인한다. production PostHog project/token 선택·AWS 연결·최종 병합과 배포는 primary 소유다. 토큰이 없어도 기본 off 구현과 로컬 시험은 가능하다.

## 검증

- 기존 통합 AWS 계약 228개 통과 후, RSA/TLS와 optional analytics 동시 유지 회귀 2개를 추가했다.
- 최종 AWS 계약 230개 통과. Terraform 두 root fmt/init(backend=false)/validate, Kustomize base/aws/platform 3경로, tracked shell 29개 bash 문법 및 변경 shell ShellCheck 통과.
- tracked tree Gitleaks 발견 8개는 모두 dev에서 변경되지 않은 release 문서의 Access 소스 SHA 오탐으로 확인했다. 실제 비밀정보는 발견하지 않았다. 테스트는 fake CLI 및 격리된 로컬 PostgreSQL/Redis를 사용하며 실제 AWS/analytics를 호출하지 않는다.

## 후속 유지보수 경로

명시적 중단 전환 구현과 검토 입력은 [유지보수 전환 절차](aws-maintenance-cutover.md)에 정의한다.
이 경로는 위 감사 당시 없던 `maintenance-cutover` 모드이며 실제 pending migration을 실행한다.
과거의 현재 도구 미지원 설명은 감사 시점의 상태이고, 새로운 모드 자체가 실제 리허설/운영 승인 증거는 아니다.
