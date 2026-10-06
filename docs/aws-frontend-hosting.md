# 화면(frontend) EKS Fargate 운영

화면은 기존 EKS의 Fargate에서 돌고, 같은 ALB가 한 주소(`app_domain`)에서 화면과 API를 경로로 나눕니다. Vercel에서 옮긴 이유와 전환 절차는 [backlog/aws-frontend-fargate-migration.md](backlog/aws-frontend-fargate-migration.md)에 보관합니다(Vercel 프로젝트는 정리 완료).

## 구성 위치

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
- 화면 서버는 로그인 전에 기동 요청 이벤트를 보내 503보다 먼저 깨울 수 있습니다. 서비스계정 `fruition-frontend`가 이벤트 발행·상태 조회만 하는 role을 쓰고, Pod는 `dnsPolicy: Default`로 VPC DNS를 씁니다. 계약은 [요청 기반 기동](aws-request-wake.md#화면의-기동-요청)을 따릅니다.

## 되돌리기

- 화면 이전 후 release끼리는 기존과 같이 `rollback`을 씁니다.
- 화면이 없는 이전 형식 release(schema 1)는 `deploy`에 쓸 수 없습니다. 새 manifest의 화면 Deployment가 없는 이미지 태그를 받게 되기 때문입니다. `rollback`에서만 허용합니다.
