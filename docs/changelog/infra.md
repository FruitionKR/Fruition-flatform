## 2026-09-21 — 요청 기반 EKS 기동과 관측 비용 절감

- Container Insights 수집 주기를 60초에서 300초로 늘려 관측 건수를 줄인다. 기존 5분 경보 간격은 유지하며 짧은 부하 급증은 놓칠 수 있다.
- 운영자가 작업 종료 후 노드를 절전하면, 외부 Lambda가 ALB 요청 실패 지표를 감지해 일반 노드 2대를 복구한다. DynamoDB 상태와 단일 동시 실행으로 중간 실패를 재개하고 절전 중 ASG Launch 충돌을 방지한다.
- 요청 감지는 노드가 모두 종료된 `asleep` 이후에만 하며, drain 중 오류로 다시 깨어나지 않는다. 완료 판정과 기동 용량은 ASG 실제 desired를 함께 본다. ALB 식별자는 `observability_alb_arn_suffix`를 공용한다.
- 첫 요청은 저장·재전송하지 않으며 기동에 수분이 걸릴 수 있다. 자동 유휴 종료는 하지 않고 절전·수동 기동·복구 절차를 문서화했다.
- AWS 검증 101개(기동 제어 15개 포함)와 Terraform validate를 통과했다. 실제 AWS에 기동 장치와 300초 수집 설정을 적용했으며, 실제 노드 절전 후 요청으로 복구하는 시험은 아직 수행하지 않았다.

## 2026-09-21 — PDF 배포 검증 실패 단계와 HTTP 상태 기록

- multipart 시작·파트 URL 발급·S3 PUT·완료·완료 재호출 단계를 구분해 실패 위치를 보고한다.
- API와 S3 오류의 HTTP 상태 코드만 기록하며 서명 URL·응답 본문·인증 정보는 출력하지 않는다.
- API 500 및 S3 403 오류 보고 회귀 테스트를 추가했다.

## 2026-09-21 — 대용량 PDF 직접 업로드 인프라와 converter 설정

- 브라우저 S3 multipart 업로드를 위해 storage 버킷 CORS를 `document_upload_allowed_origins` 변수로 생성한다. 구체적인 HTTPS origin만 허용하며 PUT/GET/HEAD와 Range·ETag 관련 헤더만 노출한다. 공개 읽기 권한은 추가하지 않는다.
- 문서 IRSA 정책에 `tmp/document-uploads/*` 읽기·쓰기와 `s3:GetObjectVersion`을 추가한다. 임시 prefix 삭제 권한은 부여하지 않으며 `tmp/` 이전 버전은 7일 lifecycle로 만료한다.
- converter Deployment에 `CONVERTER_SOURCE_HOSTS`, `PDF_PAGES_PER_BATCH` 환경 변수를 ConfigMap에서 주입한다. AWS overlay 값은 리전 S3 endpoint와 버킷 hostname placeholder로 두며 배포 시 실제 버킷으로 치환한다.
- 처리 경로·배포 순서·검증 범위는 `docs/aws-document-transfer.md`에 정리했다. S3 CORS·lifecycle·IAM 대상 plan(1 add, 2 change, 0 destroy)을 운영에 적용하고 라이브 상태를 확인했다. 앱 이미지(converter·document-svc)와 프런트엔드 flag 배포는 별도 진행한다.
- 배포 순서를 converter 우선으로 바꾼다. foundation·migration·routing 이후 converter Deployment를 먼저 적용하고 rollout 완료를 확인한 뒤에만 document·pipeline 등 나머지 workload를 적용한다. 새 document-svc가 converter `/convert-source-batch`를 요구하므로 converter 실패 시 document rollout을 시작하지 않는다.
- deploy workflow에 `deploy` 액션 전용 gate `scripts/aws_pdf_smoke.py`를 추가한다. 배포 성공 후 검증 계정으로 65MiB 합성 PDF의 multipart 업로드·완료 재호출·Range 읽기·11페이지 분할 변환·AI 완료를 확인하고 테스트 문서만 정리한다. bootstrap/rollback에서는 실행하지 않는다.
- 프런트엔드는 `BACKEND_URL`이 있으면 직접 업로드를 기본 활성화하며 `DOCUMENT_DIRECT_UPLOAD_ENABLED=false`로만 비활성화한다.
- 검증: Terraform validate, actionlint, boundaries 테스트에 임시 prefix·GetObjectVersion 계약 추가, PDF smoke 테스트 3개와 workflow 배선 테스트 추가.

## 2026-09-21 — 문서 본문 API 전체에 WAF 본문 규칙 예외 확장

- 파일 업로드 외 Markdown 생성·문서 저장·AI 편집·질의·위키 스키마·Skill API도 임의 본문을 받아 CommonRuleSet 본문 규칙과 SQLi 본문 규칙에 차단되던 문제를 수정한다.
- 허용 요청 조건(메서드·경로·Content-Type)을 `infra/waf/document-content-contracts.json` 한 곳에서 정의하고 Terraform과 테스트가 함께 읽는다. 조건 일치 시 Count 라벨만 부여하고, 본문 규칙 라벨이 있으나 문서 요청 라벨이 없는 요청은 `document-content-body-guard`가 차단한다.
- 종료 Allow는 추가하지 않는다. URI·쿼리·헤더·쿠키 검사, IP 평판, KnownBadInputs, rate limit과 서버 인증·파일 검증은 유지한다. 상세는 `docs/aws-waf-document-content.md`.
- 검증: `aws_wafv2_web_acl.cost_guard` 단일 리소스 대상 plan을 운영에 적용했다. 합성 프로브 57건(예외 44건 401, 차단 유지 13건 403)과 WAF 로그 대조를 통과했다. 새 계약 테스트 6개 추가.

## 2026-09-21 — 문서 업로드 WAF 본문 규칙 조정

- 정상 파일 업로드가 CommonRuleSet의 8KB 크기 제한 및 GenericLFI 본문 검사로 차단되는 문제를 수정한다.
- POST `/api/workspaces/ws_[0-9a-f]{32}/documents`의 multipart/form-data boundary 요청만 두 본문 규칙의 예외로 처리한다. Count label과 후속 Block으로 다른 경로·메서드·Content-Type에는 기존 차단을 유지한다.
- 나머지 관리형 규칙·rate limit·서버 인증 및 파일 검증은 유지한다. WAF 전체 Allow나 인증 실패 무시는 추가하지 않는다.

## 2026-09-20 — 노드 이미지 자동 정리와 빌드 캐시

- 20GiB 노드의 DiskPressure 재발 대응으로 kubelet 이미지 정리를 85/80%에서 70/60%로 앞당기고 24시간 미사용 이미지 정리를 활성화한다. 디스크 크기는 유지하며 노드 그룹당 최대 1대씩 순차 업데이트한다.
- 이미지 게시를 Buildx/공식 build-push-action과 서비스별 GHA v2 캐시로 전환한다. 중간 레이어도 저장하며 캐시 내보내기는 2분 제한·실패 허용, 이미지 빌드·게시·digest 검증 실패는 계속 차단한다.
- 네 이미지 빌드를 최대 4개 병렬 실행한다. 같은 릴리스 재시도는 기존 immutable 이미지를 사용하며, 새 이미지의 action digest와 ECR digest를 비교한 뒤에만 릴리스에 포함한다.
- 변경된 checkout SHA·digest 불일치·기존 태그 재사용 회귀 시험을 추가했다. 운영 GC 정책은 Terraform 적용 및 노드 교체 후 검증이 필요하며 캐시 시간 절감은 실제 cold/warm 실행으로 측정한다.

# 인프라 변경 기록

## 2026-09-20

- bootstrap 준비 완료 후 OAuth Secret 연결 추가로 최초 deploy가 차단되는 문제에 전용 복구 옵션을 추가했습니다. Access의 6개 연결 추가만 허용하며 기존 설치·health·준비 완료 기록과 DB schema를 대조하고 별도 immutable 복구 기록을 남깁니다. migration 재실행 없이 업무 smoke를 통과해야 성공 처리합니다. AWS 계약 테스트 83개, Terraform validate, actionlint를 통과했고 실제 DB 3개의 schema가 설치 완료 기록과 일치함을 확인했습니다. 운영 복구 배포는 병합 후 승인 실행이 필요합니다.

- Google·Naver·Kakao OAuth 6개 항목의 Terraform 빈 초기값과 Access 전용 ExternalSecret 매핑을 추가했습니다. 서비스별 자격증명 경계 및 원본 키 매핑 검증을 보강했습니다. 기존 Secret의 운영 값은 보존하며 실제 값은 코드에 포함하지 않습니다. 환경변수 대조와 기존 bootstrap manifest 고정으로 인한 배포 전환 조건을 문서화했습니다.

## 2026-09-18

- Access Pod·ALB health가 SMTP 인증을 반복해 메일 서버 로그인 제한과 HTTP 503을 일으키던 문제를 AWS health의 mail 항목만 제외해 수정했습니다. 실제 메일 발송·DB·Redis health는 유지합니다. 미완료 최초 설치에 명시적 SMTP health 복구 옵션과 원본 보존 기록 연결을 추가했습니다. 테스트 78개 및 같은 이미지의 임시 EKS Pod에서 SMTP egress 차단 상태로 health 10/10 HTTP 200(최대 0.09초)을 확인했습니다. 실제 메일 발송은 제한 해제 후 별도 검증이 필요합니다.

- Redis ACL 수정 후에도 Access health의 정상 응답이 기본 probe 제한 1초를 초과해 재시작되는 문제를 AWS timeout 5초로 보완했습니다. 이미 시작된 최초 설치에는 workflow의 명시적 probe 복구 옵션을 추가했으며, 원본 기록을 보존하고 Access 세 probe의 1→5초 변경만 허용합니다. 이미지·자원·경로 변경 거부와 기록 검증을 포함해 테스트 76개를 통과했습니다.
- private EKS에 비활성 public CIDR 빈 목록 변경을 보내 AWS가 `already at the desired configuration`으로 거부하던 요청을 null로 생략합니다. 실제 복구 후 private 전용 상태와 해당 Terraform 계획의 변경 없음 결과를 확인했습니다. CIDR 목록을 채우는 것은 public endpoint 활성화를 의미하므로 private 모드 유지 목적으로 값을 채우지 않습니다.

- 첫 AWS 배포에서 Spring Redis health의 INFO 명령이 ACL에 없어 Access·Document가 준비되지 않던 문제를 해당 두 계정에 `+info`만 추가해 수정했습니다. 일반 노드 3대 상한에서도 Pipeline API가 CPU 부족으로 대기해 상한을 4대로 올렸습니다. 추가 노드가 실행되면 비용이 증가합니다. 실제 Redis INFO 허용·관리 명령 거부를 포함한 AWS 테스트 74개와 Terraform validate를 통과했습니다. 운영 반영·배포 재시도는 병합 후 수행합니다.

- 빈 DB의 최초 설치에 운영 버전 호환성 증명을 요구하던 순환 조건을 `initial-install` 검토로 분리했습니다. DB 3개 빈 상태 검사 후 SHA·설정·manifest를 고정하고, 설치 완료 schema가 일치하며 로그인·문서·AI smoke까지 통과한 경우에만 성공 release를 기록합니다. 게시 이미지 3종의 DB 마이그레이션·재실행·논리 복원 시험과 AWS 테스트 73개를 통과했습니다. 실제 시험 기록 PR #10을 참조하는 대상 이미지 릴리스 검토 JSON도 추가했습니다. 실제 EKS 최초 앱 배포와 업무 smoke는 아직 수행하지 않았습니다.

- RDS 관리자에게 migration role의 INHERIT·SET 소속이 자동 부여되지 않아 기본 권한 설정이 실패하던 문제를 명시적 GRANT로 수정했습니다. 서비스 계정에는 관리자 권한을 부여하지 않습니다. 실제 RDS의 서비스 DB 3개·계정 6개 초기화 및 권한 검증, 로컬 회귀 테스트 68개를 통과했습니다.

- Ubuntu Runner 초기화에서 `awscli` 패키지를 찾지 못해 중단되던 문제를 AWS 공식 CLI v2 설치 파일 사용으로 수정했습니다. 재시도 시 기존 설치를 갱신하며 Runner 스크립트 문법 검사와 교체 후 재등록 안내를 추가했습니다. 전체 테스트 68개와 Terraform validate를 통과했으며, Terraform 적용 시 Runner 교체가 필요합니다.

## 2026-09-17

- ElastiCache 생성 API가 거부한 한글 설명을 ASCII 설명으로 수정했습니다. Redis 권한·암호화·용량 설정은 유지합니다.

- AWS 첫 적용에서 거부된 DB·Redis 보안 그룹 설명의 > 문자를 제거했습니다. RDS TLS 파라미터는 pending-reboot로 명시하고 CloudWatch JSON 끝 개행·Redis ACL/비활성 사용자 인증 표기를 AWS 응답과 맞춰 반복 변경을 제거했습니다. 실제 Redis 권한 검사 포함 전체 테스트 68개와 Terraform validate를 통과했습니다.

- 실제 AWS 인증에서 확인한 GitHub immutable OIDC subject 형식을 지원합니다. API의 정확한 sub_claim_prefix를 필수 입력으로 받아 publisher/main과 deploy/feedback 신뢰 정책에 적용하고 저장소 이름 일치를 검증합니다. 기존 이름 전용 추정 때문에 발생하던 AssumeRoleWithWebIdentity 실패를 수정했습니다.

- 서비스 main CI 성공 커밋을 확인해 이미지 4종을 immutable ECR 태그와 GitHub Release로 자동 게시하는 workflow를 추가했습니다. 운영자가 릴리스 ID를 선택하고 feedback 승인 후 배포하며 실제 digest를 대조합니다. main 전용 게시 IAM 권한은 배포 권한과 분리했습니다.
- 게시 활성화는 Terraform 재적용과 Repository variables 설정 후 진행합니다. 로컬 신규 테스트 7개·기존 IaC/Runner 검사·actionlint·Terraform validate 및 실제 GitHub 읽기 검증을 통과했으며, 이미지 게시·AWS 배포 실검증은 아직 수행하지 않았습니다.

- AWS 실제 입력을 `.local/aws/`에서 관리하도록 폴더 전체 Git 제외 규칙과 초기화·계획·백업 안내를 추가했습니다. 실제 설정과 기존 경로 링크는 커밋하지 않으며 bootstrap state는 별도 백업합니다. 로컬 설정 4개 제외 및 비밀정보 검사를 통과했습니다.

- EKS 기본 애드온 4개를 직접 관리해 모듈 출력의 resolve_conflicts 폐기 경고를 제거했습니다. 기존 버전·설정·노드 생성 후 설치 순서를 유지하고 개별 moved 블록으로 기존 주소를 이전합니다. 로컬 plan은 경고 없이 198개 생성·변경/삭제 0개이며 validate와 관련 테스트 5개를 통과했습니다.

- 배포·Runner 점검의 job env에서 사용할 수 없는 runner 컨텍스트를 제거하고 실행 단계에서 임시 kubeconfig 경로를 설정합니다. actionlint 검증을 CI에 추가해 실행 전 워크플로 문법 오류를 확인합니다. 검사 설정 파일의 경로도 CI 트리거와 계약 테스트에 포함했습니다.

- Ubuntu Actions에서 archive provider 검증이 실패하던 문제를 Linux amd64 공식 체크섬 추가로 수정했습니다. Mac arm64 체크섬과 provider 버전은 유지하며 Terraform validate를 통과했습니다.

- AWS 초기 배포용 private Runner, OIDC, WAF 비용 보호, CloudWatch 수집·대시보드와 Discord 알림을 구성했습니다.
- API별 2개 Pod와 순차 교체·PDB·ALB readiness gate, 비관리자 실행, Kafka mTLS·역할별 ACL을 적용했습니다.
- DB 변경 검토·업무 smoke·동일 schema rollback·최초 설치 재시도 절차를 추가하고, DB 사전검사에서 명시적 TLS URI를 허용하도록 맞췄습니다.
- 로컬 SMTP·웹훅·계정 입력, Terraform state/plan은 Git에서 제외합니다. 실 AWS 배포·복원 검증은 별도이며 서비스 이미지 4종 재빌드가 필요합니다.
- 검증: Terraform validate, 플랫폼 61개 테스트, AI TLS 5개 테스트와 런타임 권한 smoke 4개 통과. 이중화 증설은 포함하지 않았습니다.
