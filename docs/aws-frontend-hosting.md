# 화면(frontend)을 EKS Fargate로 옮기기

화면을 Vercel에서 기존 EKS의 Fargate로 옮기고, 같은 ALB가 한 주소(`app_domain`)에서 화면과 API를 경로로 나눕니다.

## 왜 옮기나

- Access는 로그인 시도 제한의 IP를 `X-Forwarded-For`의 오른쪽 1개, 즉 ALB가 실제로 본 주소로 정합니다.
- Vercel rewrite를 거치면 이 주소가 Vercel 서버 주소가 됩니다. 사용자들이 IP 제한을 나눠 쓰게 되고, 남이 화면을 통해 다른 사람 계정의 실패 횟수를 채울 수 있습니다.
- 브라우저가 ALB를 직접 부르면 오른쪽 1개가 실제 사용자 주소입니다. Access 설정을 바꿀 필요가 없습니다.
- Fargate Pod는 노드 그룹 밖에서 돌기 때문에 절전(노드 0대) 중에도 화면이 열립니다.
- Vercel Hobby는 상업 이용이 허용되지 않습니다.

## 바뀌는 것

| 위치 | 내용 |
|---|---|
| `k8s/overlays/aws/ingress.yaml` | `app_domain` 호스트에 순서가 있는 경로 규칙을 둡니다. `/internal*`·`/swagger-ui*`·`/v3/api-docs*`는 모든 호스트에서 404입니다. |
| `k8s/overlays/aws/frontend.yaml` | 화면 Deployment(2개)·Service·전용 ServiceAccount·`ACCESS_CODE` ExternalSecret·PDB |
| `infra/terraform/eks.tf` | `frontend` Fargate profile, Fargate 로그 권한 |
| `infra/terraform/cost-guards.tf` | 접근 코드 WAF 규칙(`frontend-access-code`), 속도 제한에서 `/_next/static/` 제외 |
| `infra/terraform/ecr.tf` | `fruition-frontend` 저장소 |
| `k8s/platform/aws/fargate-logging.yaml` | Fargate 로그를 기존 application log group으로 보냅니다. |
| 이미지 게시·배포 | 이미지 5개(schema 2), 화면 TargetGroupBinding 대기, 공개 경로 차단과 화면 응답 확인 |

접근 코드 검사는 화면의 Next middleware가 하던 일입니다. ALB가 `/api/*`를 서비스로 바로 보내면 middleware가 돌지 않으므로, 같은 규칙을 WAF가 `app_domain` 호스트에서 수행합니다. 코드 없이 열리는 경로도 middleware와 같습니다(`/api/auth/`, `/api/invitations/`, `/api/workspaces`, `/api/workspaces/{id}`). `api.`·`access.` 호스트에는 지금처럼 적용하지 않습니다.

## 운영자가 직접 할 일 (순서대로)

1. **인증서.** ACM 인증서가 `app_domain`(예: `web.fruitiontest.accesscam.org`)도 포함하도록 새로 발급하고 검증합니다. 배포 JSON의 `acm_cert_arn`을 새 ARN으로 바꿉니다.
2. **비밀값.** Secrets Manager `fruition/app`에 `ACCESS_CODE` 속성을 추가합니다. 게이트를 쓰지 않으려면 빈 문자열로 둡니다. 속성이 없으면 ExternalSecret 동기화가 실패해 배포가 멈춥니다.
3. **Terraform 입력.** 로컬 `feedback.tfvars`에 아래를 넣습니다.

   ```hcl
   app_domain                      = "web.fruitiontest.accesscam.org"
   document_upload_allowed_origins = ["https://web.fruitiontest.accesscam.org"]
   ```

   WAF가 비교할 쿠키 값은 Terraform이 `fruition/app`의 `ACCESS_CODE`를 읽어 화면과 같은 방식(앞뒤 공백 제거 후 SHA-256 소문자 16진수)으로 계산합니다. 그래서 Terraform 실행 계정에 이 Secret 읽기 권한이 필요합니다.
4. **Terraform plan·apply.** 기존 절차로 plan을 만들어 검토합니다. ECR 저장소 1개, Fargate profile·실행 role, 로그 정책, WAF 규칙 변경(`frontend-access-code`, `not-public-paths`, 속도 제한 범위), S3 CORS 변경이 보여야 합니다.
5. **플랫폼 설치 재실행.** `bash scripts/aws-platform-up.sh install /secure/terraform-outputs.json`으로 `aws-observability` namespace와 로그 설정을 적용합니다.
6. **GitHub 배포 입력.** `AWS_DEPLOY_CONFIG_JSON`의 `app_domain`을 새 주소로 바꿉니다. `CORS_ALLOWED_ORIGINS`·OAuth 복귀 주소·초대 주소가 이 값에서 만들어집니다.
7. **OAuth 제공자.** Google·Naver·Kakao 콘솔에 `https://<app_domain>/login/oauth2/code/{google|naver|kakao}`를 redirect URI로 추가합니다. 기존 `access.` 주소는 전환이 끝날 때까지 지우지 않습니다.
8. **이미지 게시와 배포.** frontend 저장소 main CI가 성공하면 다음 게시 실행이 이미지 5개짜리 release를 만듭니다. `docs/releases/<ID>.json` 검토 기록을 main에 반영한 뒤 `deploy`를 실행하고 승인합니다. 배포 스크립트는 DNS 전환 전에도 ALB 주소로 `/healthz`와 `/`를 확인합니다.
9. **DNS 전환.** `app_domain`을 `api.`·`access.`와 같은 ALB 주소로 CNAME 연결합니다. ALB IP는 바뀌므로 A 레코드는 쓰지 않습니다. 현재 DNS(Dynu)는 호스트명 자체(`fruitiontest.accesscam.org`)에 CNAME을 걸기 어려워 `web.` 같은 하위 이름을 씁니다.
10. **확인 후 정리.** 아래 확인을 마친 뒤 Vercel 프로젝트와 이전 Vercel 주소를 정리합니다.

## 배포 후 확인

- `https://<app_domain>/`이 열리고 로그인, OAuth 로그인, PDF 업로드, 회의 실시간 받아쓰기가 동작합니다.
- `/internal/...`, `/v3/api-docs`, `/swagger-ui.html`은 모든 호스트에서 404입니다.
- 접근 코드를 켰다면 쿠키 없이 `/api/workspaces/<id>/documents`를 호출하면 403이고, 화면에서 코드를 입력한 뒤에는 통과합니다.
- access-svc 로그의 로그인 IP가 실제 사용자 주소입니다. 한 IP에서 로그인 실패를 반복하면 그 IP만 429를 받습니다.
- 절전 시험: 절전 후에도 화면이 열리고, 화면의 API 호출이 노드를 깨웁니다.

## 접근 코드 바꾸기

`fruition/app`의 `ACCESS_CODE`를 바꾼 뒤 Terraform을 다시 적용합니다. 적용 전까지 WAF는 이전 해시를 비교하므로 새 코드로 받은 쿠키는 403입니다(닫힌 채로 실패). 화면 Pod는 ExternalSecret 갱신(최대 1시간) 후 재시작해야 새 코드를 씁니다.

쿠키 값은 코드의 해시라서, Web ACL 설정이나 Terraform state를 읽을 수 있는 사람은 쿠키를 만들 수 있습니다. 접근 코드는 공개 전 화면 잠금 용도이며 인증을 대신하지 않습니다.

## 절전 중 제약

- 이미 떠 있는 화면 Pod는 계속 응답합니다.
- ALB controller의 Pod 생성 webhook(`failurePolicy=Fail`)과 CoreDNS가 general 노드에 있습니다. 절전 중에는 화면 Pod를 새로 만들 수 없어 재배포·교체가 실패합니다. 노드를 깨운 뒤 배포합니다.
- 화면은 서버에서 다른 서비스를 부르지 않으므로 CoreDNS가 없어도 응답에는 영향이 없습니다.
- 절전 중 화면의 API 호출은 ALB 503이 되고, 이 오류가 노드를 깨웁니다.

## 되돌리기

- 화면 이전 후 release끼리는 기존과 같이 `rollback`을 씁니다.
- 화면이 없는 이전 형식 release(schema 1)는 `deploy`에 쓸 수 없습니다. 새 manifest의 화면 Deployment가 없는 이미지 태그를 받게 되기 때문입니다. `rollback`에서만 허용합니다.
- 이전 release의 성공 기록에는 이전 배포 JSON(`app_domain`이 Vercel 주소)이 저장되어 있습니다. 배포 JSON이 다르면 rollback이 거부되므로, 이전 release로 되돌리려면 DNS를 Vercel로 되돌리고 배포 JSON의 `app_domain`·`acm_cert_arn`도 이전 값으로 맞춘 뒤 실행합니다. 이때 EKS의 화면 Pod는 남아 있지만 사용되지 않습니다.
