# CI/CD 속도·안정성 검토 (2026-09-20)

현재 workflow, 서비스 main의 Dockerfile/CI, 실제 GitHub Actions 실행 시간을 확인했다. 아래 개선안은 제안이며 아직 workflow에 적용하지 않았다. 이미지 게시와 운영 배포는 별개다.

## 최초 조사 시점의 실행 결과

최신 main의 네 이미지 게시가 성공했다. [실행 35508307316](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35508307316)은 11:36:26–11:48:48 UTC, 총 **12분 22초**가 걸렸다. [새 릴리스](https://github.com/FruitionKR/Fruition-flatform/releases/tag/images-4e07e7688ae2592c2038ebef8fc0ee8c42038e5f)의 ID는 `4e07e7688ae2592c2038ebef8fc0ee8c42038e5f`다. 게시 후 manifest 식별자 검증 및 네 이미지의 ECR digest 일치를 별도로 확인했다.

| 소스 | 커밋 |
|---|---|
| Access | `b73cf750a312383057dad366ee5827868a0c9354` |
| Document | `59ce6fa64529e0c4ab890881372f8b899465d680` |
| AI | `224f2c20f992e52b2b06b774651aa9eb7864c6ec` |

이번 작업 전체 시간은 Access 1분 24초, Document 1분 32초, Pipeline 7분 9초, Converter 10분 18초였다. 아래 과거 표는 build/push 단계만 측정했으므로 직접 동일 지표로 비교하지 않는다. workflow를 수정한 실행이 아니므로 과거 대비 차이를 개선 효과로 해석하지 않는다.

최초 조사 시점에는 EKS 배포를 실행하지 않았고 feedback 검증 계정 입력과 실제 업무 호환성 검토가 남아 있었다. 이후 진행 상황은 문서 마지막의 후속 배포 기록에 정리한다. Terraform은 변경하지 않았다.

## 측정 기준

[9월 17일 이미지 게시](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35200876795)는 요청부터 완료까지 **12분 58초**였다. 각 서비스의 `Build pinned source and push immutable image` 단계는 다음과 같다. 단일 실행의 측정치이며 평균이나 p95가 아니다.

| 이미지 | 빌드·게시 단계 |
|---|---:|
| access-svc | 1분 28초 |
| document-svc | 1분 35초 |
| pipeline | 6분 25초 |
| converter | 9분 47초 |

동시 빌드는 두 개로 제한되어 있다. Converter 작업이 시작될 때까지 약 2분 49초가 걸렸다. 네 개를 동시에 시작하면 이 대기를 줄일 수 있지만 runner 할당·다운로드 속도에 따라 효과가 달라진다. 4배 빨라지는 변경은 아니다.

[최신 Document CI](https://github.com/FruitionKR/Fruition-document/actions/runs/35499218111)는 2분 51초이며, Gradle test/bootJar가 2분 27초였다. [최신 AI CI](https://github.com/FruitionKR/Fruition-ai/actions/runs/35499211176)는 3분 34초이며, 의존성 설치 1분 47초, 테스트 30초, Python 설정·캐시 복원 40초, 종료 시 캐시 처리 31초였다. AI에서는 테스트 병렬화보다 의존성 설치·캐시 전송을 먼저 측정할 가치가 크다.

## 적용 우선순위

### 1. 이미지 빌드에 외부 캐시 추가

`scripts/aws_image_release.py`는 매번 새 hosted runner에서 `docker build --pull` 후 push한다. 외부 `cache-from/cache-to`가 없으므로 릴리스 사이에 빌드 결과를 재사용하지 못한다. Pipeline·Converter의 Rust 컴파일, npm 설치, OS 패키지·모델 다운로드가 반복된다.

- Buildx와 서비스별 `scope`를 둔 GitHub Actions 캐시를 도입한다. 다단계 Rust 빌드 결과를 보존하려면 `mode=max`를 검토한다.
- 공식 `docker/build-push-action`은 캐시 인증 환경을 처리한다. 기존 Python에서 직접 Buildx를 호출한다면 런타임 캐시 URL·토큰 제공을 별도로 구현해야 한다. 플래그만 추가해서는 충분하지 않다.
- 캐시 내보내기에 짧은 timeout과 `ignore-error=true`를 설정하여 캐시 장애가 정상 이미지 게시를 실패시키지 않게 한다. 이미지 build/push/digest 검증 실패는 계속 차단한다.
- AI 캐시의 용량·전송시간·퇴출 빈도를 측정한다. GitHub 캐시가 부적합하면 별도 ECR 캐시 저장소를 검토한다. 현재 배포 이미지 저장소는 immutable이므로 같은 `buildcache` 태그를 계속 덮어쓰는 방식은 그대로 적용할 수 없다.
- `RUN --mount=type=cache`의 내용은 GitHub 캐시로 자동 보존되지 않는다. 먼저 레이어 캐시를 적용하고, Gradle/Cargo 캐시 마운트는 별도 보존 경로까지 검증한다.

근거: [Docker GitHub Actions cache](https://docs.docker.com/build/cache/backends/gha/), [캐시 관리](https://docs.docker.com/build/ci/github-actions/cache/), [캐시 최적화](https://docs.docker.com/build/cache/optimize/).

### 2. 동시 빌드 2 → 4 및 변경 없는 이미지 재사용

우선 `max-parallel: 4`를 별도 변경으로 검증한다. 각 작업은 별도 hosted runner이므로 배포 EC2 크기를 바꿀 필요는 없다. 동일 작업 수의 동시 실행을 늘리는 것이지만 계정의 동시 실행 한도와 외부 저장소 부하를 확인한다.

그다음 서비스별 소스·빌드 설정 식별자를 도입한다. 이번 Access 소스는 이전 릴리스와 같지만 전체 릴리스 ID가 달라 재빌드한다. 이전 이미지의 소스 및 빌드 설정이 정확히 같고 ECR digest가 유효할 때만 기존 manifest를 새 릴리스 태그에 연결할 수 있다. 이는 manifest 검증과 테스트를 포함하는 별도 설계 변경이다.

AI 저장소는 Pipeline과 Converter가 `pipeline/app`, Rust 도구 등의 입력을 공유한다. Converter 디렉터리만 비교하면 변경을 놓친다. 변경 감지는 각 Dockerfile의 전체 COPY 입력과 공통 의존성을 반영해야 한다. 보안 업데이트용 의도적 재빌드도 별도로 지원해야 한다.

### 3. CI 성공 직후 이미지 게시 요청

현재 15분 cron이지만 실제 실행은 지연될 수 있다. 9월 20일 서비스 CI가 08:22 UTC까지 끝난 후 11:36 UTC 수동 실행 전까지 새 이미지가 게시되지 않았다. cron의 다음 실행을 배포 SLA로 간주하면 안 된다.

서비스 main CI 성공 후 GitHub App의 최소 권한으로 플랫폼 `repository_dispatch` 또는 `workflow_dispatch`를 요청하고, cron은 누락 복구용으로 유지하는 방안을 검토한다. 다른 저장소의 `workflow_run`만 선언해서 연결할 수는 없다. 플랫폼은 이벤트 payload를 신뢰해 소스를 선택하지 않고 지금처럼 허용된 저장소의 main SHA와 해당 push CI 성공을 다시 검증한다. 여러 서비스의 연속 완료는 기존 concurrency와 동일 릴리스 중복 검출로 합친다.

근거: [GitHub workflow 이벤트 및 schedule 지연](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

### 4. 배포 입력을 mutation 전에 한 번에 검증

현재 workflow의 render 단계는 배포 설정·SHA를 검사하지만, 릴리스 검토 기록과 smoke 입력은 AWS 인증·이미지 확인 이후 deploy 스크립트에서 검사한다. 검토 JSON 존재·형식, `migration_mode`, 검증 계정 설정을 초기 preflight에서 함께 확인하면 runner 시간을 낭비하는 실패를 줄일 수 있다. 비밀번호는 값이나 길이를 로그에 남기지 않고 존재 여부만 검사한다.

동일 SHA의 bootstrap 업무 검증 승격과 새 릴리스 배포를 UI·summary에서 구분한다. 최초 설치 기록을 지우거나 새 SHA를 bootstrap으로 실행하는 방식으로 우회하지 않는다. DB migration, 이미지 digest, ALB readiness, 업무 smoke, feedback 승인은 유지한다.

### 5. 배포 이미지 자체의 회귀 검증 강화

AI CI는 일반 pytest만 실행하며 document_restoration 테스트를 명시적으로 제외한다. 현재 CI 성공만으로 Converter 이미지·Rust 바이너리·OCR 도구 실행 성공을 입증하지 못한다.

- 이미지 게시 전에 네 이미지의 기본 프로세스/import/바이너리 실행 검사를 추가한다. 네트워크·실제 AWS 자격 증명에 의존하지 않는 검사부터 시작한다.
- 공유 Rust·Converter·복원 모듈 변경 시 별도 통합 검사를 실행한다. 제외된 기능을 전체 검증 완료로 표시하지 않는다.
- AI pip 캐시 키에 `requirements-dev.txt` 및 참조된 모든 requirements 입력을 포함한다. 실제 사용되는 테스트 의존성과 캐시 식별 입력을 맞춘다.
- mutable base image와 넓은 Python 버전 범위 때문에 같은 소스를 재빌드해도 결과가 달라질 수 있다. base digest와 dependency lock을 도입하고 정기 업데이트 PR로 갱신한다. 외부 모델 파일도 checksum을 확인한다.
- API 조회와 패키지 다운로드의 일시적 429/5xx/timeout에 제한된 재시도를 적용한다. 권한 오류·manifest 불일치·테스트 실패·DB migration을 일괄 재시도하지 않는다.

### 6. 운영 runner 복구 및 관측

현재 배포 전용 self-hosted runner 한 대가 online이다. 먼저 설치 도구 버전, 디스크 여유, runner 서비스 및 private EKS 연결을 주기적으로 확인하고 복구 절차를 문서화한다. 이후 사용량에 따라 ephemeral runner를 검토한다. 단일 배포 runner에 문제가 생길 수 있다는 이유만으로 즉시 ARC 전체를 도입할 필요는 없다.

근거: [GitHub self-hosted runner reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners).

## 개선 효과 확인 방법

현재 값과 변경 후 값을 같은 기준으로 기록한다: CI 완료→게시 시작 지연, job queue 시간, 이미지별 build/push/cache 시간, cold/warm cache, 배포 사전검사·migration·rollout·smoke 시간, 실패 단계, 재실행 성공 여부. 최초 1회 캐시 채우기와 이후 실행을 구분한다. 같은 소스와 Dockerfile로 비교하고, 캐시 없는 경우에도 정상 빌드되는지 확인한다. 최소 여러 실행의 중앙값·p95를 확보한 후 절감률을 제시한다.

## 이번 배포의 선행 조건

- 이미지 게시 실행: [35508307316](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35508307316).
- 최초 설치 준비 완료 버전(성공 release 기록은 아직 없음): `a2b46a13a49f5850a6a9febb367546d97e47da73`.
- 조사 초기 없었던 feedback 검증 값은 등록 완료했다. 이메일·비밀번호는 Secret, workspace ID는 Variable이다.
- Document V49는 `ALTER TABLE chat_messages ADD COLUMN progress jsonb NOT NULL DEFAULT '[]'::jsonb;`다. 운영 RDS PostgreSQL은 16.13이다. 상수 기본값을 추가하는 경우 전체 행 재작성은 보통 필요 없지만 DDL 잠금과 구·신 앱의 읽기/쓰기 호환성을 시험해야 한다. [PostgreSQL 16 문서](https://www.postgresql.org/docs/16/ddl-alter.html).
- RDS 두 인스턴스는 available, 백업 보존 7일이며 최근 복원 가능 시각이 확인됐다. 이는 실제 복원 시험 성공을 뜻하지 않는다.
- 새 release 검토 JSON의 호환성·복원 시험 URL은 실제 결과로 채워야 한다. 이전 최초 설치 기록을 새 버전의 호환성 시험으로 대신 사용할 수 없다.

### 수행한 V49 제한 검증

네트워크를 차단한 임시 PostgreSQL 컨테이너에서 실제 V49 SQL을 실행했다. 로컬 이미지 버전은 **16.14**로 운영의 16.13과 다르다. 최소 `chat_messages` 테이블의 합성 행 1,000개에 대해 기존 행 기본값, progress를 생략한 INSERT, 새 JSON 값을 쓰는 INSERT, 논리 백업·복원 후 데이터 checksum 일치를 확인했다. `relfilenode`가 유지되어 이 시험에서 테이블 재작성은 없었다. 컨테이너는 시험 후 삭제됐다.

이 검증은 전체 업무 스키마·실제 구/신 앱·운영 데이터량·잠금 경합·Flyway 실행·RDS 복원 시험을 포함하지 않는다. 따라서 새 배포 검토의 업무 호환성 증거를 대체하지 않는다. 상세 결과는 Git 제외 로컬 파일 `.local/aws/v49-rehearsal-20260920.json`에 있다.

이 문서는 성능 조사와 배포 준비 기록이며, 새 릴리스의 호환성·복원 시험 증거가 아니다.

## 후속 배포에서 확인한 안정성 문제

- [게시 35512369894](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35512369894)는 12분 23초였다. 실제 새 이미지의 AWS IRSA/S3 PUT·GET·DELETE, 구·신 API와 V49, 세 DB 93개 테이블의 논리 복원 비교는 [검증 PR #16](https://github.com/FruitionKR/Fruition-flatform/pull/16)에 기록했다.
- [배포 35513545554](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35513545554)는 새 이미지 교체·문서 저장을 통과했지만 AI 결과 저장의 중첩 PostgreSQL advisory lock에서 실패했다. mock뿐인 잠금 시험으로 놓친 경합을 실제 PostgreSQL 서비스가 있는 AI CI에서 검증하도록 [AI PR #10](https://github.com/FruitionKR/Fruition-ai/pull/10)을 main에 병합했고 main CI가 통과했다. 전체 외부 LLM ingest 성공은 아직 확인되지 않았다.
- 같은 배포 시간대에 노드 한 대의 DiskPressure와 ephemeral-storage 회수 이벤트가 발생했다. 이후 6대 모두 Ready/압박 없음으로 회복했고 failed_nodes 경보도 OK로 전환됐다. 이미지 다운로드·압축 해제·기존 이미지 보관을 고려한 노드 디스크 여유 확인을 배포 사전 진단에 포함할 필요가 있다. 디스크 사용 원인과 용량은 추가 측정 후 조정한다. [AWS 디스크 압박 대응](https://repost.aws/knowledge-center/eks-resolve-disk-pressure).

- 배포 전 kubelet 통계에서 노드 디스크는 각각 약 19.9GiB이며, 경보가 있었던 노드의 가용 공간은 약 3.6GiB였다. 해당 노드에는 실행 중인 Pod가 사용하지 않는 이전 converter 이미지도 남아 있었다. 수동 삭제나 Terraform 디스크 변경은 실행하지 않았다. 새 릴리스 이미지는 [게시 실행 35516021765](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35516021765)에서 게시 완료됐다.

- AI 수정 PR #10과 플랫폼 검증 PR #17을 main에 병합했다. 새 pipeline 이미지의 운영 RDS 중첩 잠금·예외 해제 검증이 통과했다. [배포 35516709166](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35516709166)은 새 릴리스 `5a7940f19c4bec95b7006b8ea7ee158d0bce6245`, migration_mode=none으로 feedback 승인 대기 중이다. 전체 업무 smoke 성공은 아직 미확인이다.

## 최종 배포 확인

[배포 35516709166](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35516709166)은 2026-09-20 23:38:39 KST에 성공했다. 로그인·문서 생성/조회·AI ingest 완료·시험 문서 정리를 포함한 업무 smoke gate가 통과했고 새 SHA의 첫 성공 릴리스 ConfigMap을 확인했다. 모든 Deployment가 목표 replica에 도달했고 노드 6대는 Ready/DiskPressure=false다.

배포 중 이전 노드에서 ephemeral-storage 회수 이벤트가 발생했으나 점검 시 해당 노드는 교체되어 있었고, 현재 디스크 여유는 6.3–15.9GiB였다. 이 점검에서 노드를 교체하거나 Terraform을 수정하지 않았다. failed_nodes 경보는 23:44:57 KST에 OK로 복귀했다. Discord 알림 실패 경보는 별도로 남아 있으며 실패 큐에 13건이 확인됐다. 메시지를 삭제하거나 재전송하지 않았고 실패 원인은 아직 조사하지 않았다.

## Discord 실패 큐 후속 조사

실패 메시지 표본은 9월 17일의 DeliveryError(delivery_failed), RetriesExhausted였다. 같은 날 18:29–18:30 KST에는 invalid_webhook_secret 로그가 있고, Secret의 현행 버전 생성 시각은 18:31:09 KST다. 이후 18:31:58부터 전송 성공이 확인된다. 최초 delivery_failed의 세부 예외는 로그에서 숨겨져 있어 Secret 미설정이 원인인지는 확정할 수 없다.

현행 Secret 버전 생성 이후 조회 범위에서 budget_notification_failed 로그는 없고, 9월 20일 전송 성공 로그 9건을 확인했다. 9월 20일 UTC 00시 이후 조회한 SQS NumberOfMessagesSent는 모든 시간 구간에서 0이었다. 큐 가시 메시지 수는 근사값이며 조사 중 13에서 16으로 조회됐다. 실패 큐가 비어 있지 않아 알림 실패 경보는 계속 ALARM이다. 노드 경보는 OK다.

표본 조회는 visibility timeout 0으로 수행했으며 메시지를 삭제·재전송하지 않았다. 보존기간은 14일이다. 증거 보관과 처리 여부 검토 후 오래된 실패 메시지만 선별 정리할 수 있으며, 전체 큐 purge나 경보 임계값 완화는 하지 않았다.

## 9월 21일 GC·캐시 적용 완료

[PR #18](https://github.com/FruitionKR/Fruition-flatform/pull/18)을 main에 병합했다. Terraform으로 launch template·노드 그룹 네 리소스를 변경했고, 디스크 증설 없이 두 노드 그룹 업데이트를 완료했다. 일반 그룹은 버전 교체 전에 최대 비가용 수 1을 명시적으로 선적용해 provider의 업데이트 순서에 의존하지 않도록 했다. 최종 두 그룹 모두 ACTIVE/template v2/maxUnavailable=1이다. 최종 조회한 4개 노드 전체가 GC 70/60%, 24h를 사용하고 Ready/DiskPressure=false였으며 모든 Deployment·Kafka 정상, 노드 경보 OK를 확인했다.

[캐시 빌드 35518197122](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35518197122)가 성공했고 네 서비스의 GHA 캐시와 게시 manifest/ECR digest 일치를 확인했다. 첫 캐시 생성 실행은 12분 23초이며 warm cache 시간 절감은 아직 측정하지 않았다. 새 빌드 릴리스는 게시만 했고 운영 애플리케이션은 기존 성공 버전을 유지했다. 24시간 정리의 실제 시간 경과 효과와 장기 DiskPressure 재발 여부는 추후 관측 대상이다.
