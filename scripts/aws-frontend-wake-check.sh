#!/usr/bin/env bash
# 화면 Pod와 같은 조건(Fargate·fruition-frontend 계정·dnsPolicy Default)으로 일회성 점검 Pod를 띄워
# VPC DNS 조회, IRSA role, 기동 상태 조회와 이벤트 권한 경계를 확인한다.
# runner 호스트(세션 관리자 또는 SSM send-command)에서 fruition:operators 권한으로 실행한다.
# 절전 중에는 ALB controller webhook 때문에 Pod를 만들 수 없으므로 깨어 있을 때 실행한다.
# resolv.conf가 VPC DNS를 가리키면 CoreDNS가 없는 절전 중에도 같은 조회가 된다.
#
# 사용: bash scripts/aws-frontend-wake-check.sh [--send]
#   --send  기동 요청 이벤트를 실제로 보낸다. 깨어 있으면 Lambda는 상태를 바꾸지 않는다.
set -Eeuo pipefail

SEND=false
case "${1:-}" in
  "") ;;
  --send) SEND=true ;;
  *) echo "usage: $0 [--send]" >&2; exit 2 ;;
esac

REGION=${AWS_REGION:-ap-northeast-2}
CLUSTER=${CLUSTER_NAME:-fruition-eks}
NS=fruition
POD="frontend-wake-check-$(date +%s)"

aws eks update-kubeconfig --region "$REGION" --name "$CLUSTER" >/dev/null
trap 'kubectl -n "$NS" delete pod "$POD" --ignore-not-found --wait=false >/dev/null 2>&1 || true' EXIT

kubectl -n "$NS" apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  labels:
    # Fargate profile selector와 같아야 화면과 같은 Fargate에서 실행된다.
    app: frontend
spec:
  restartPolicy: Never
  serviceAccountName: fruition-frontend
  automountServiceAccountToken: false
  dnsPolicy: Default
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    # IRSA token 파일을 비root 사용자가 읽게 한다. 화면 Pod도 pod-seccomp.yaml로 같은 값을 받는다.
    fsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
  - name: check
    image: public.ecr.aws/aws-cli/aws-cli:2.27.0
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop: ["ALL"]
    # 화면 Service(app=frontend)의 endpoint로 잡혀 사용자 요청을 받지 않도록 Ready가 되지 않게 한다.
    readinessProbe:
      exec:
        command: ["false"]
      periodSeconds: 5
    env:
    - name: HOME
      value: /tmp
    - name: AWS_REGION
      value: "$REGION"
    - name: SEND
      value: "$SEND"
    command: ["/bin/sh", "-c"]
    args:
    - |
      set -u
      echo "== resolv.conf (클러스터 DNS가 아닌 VPC DNS여야 한다)"
      cat /etc/resolv.conf
      echo "== IRSA role"
      aws sts get-caller-identity --query Arn --output text || exit 11
      echo "== 기동 상태"
      aws dynamodb get-item --table-name fruition-request-wake \
        --key '{"id":{"S":"controller"}}' --query 'Item.phase.S' --output text || exit 12
      echo "== 허용되지 않은 이벤트는 거부되어야 한다"
      # 권한 거부(AccessDenied)만 통과로 본다. 네트워크·제한 오류를 거부로 오인하지 않는다.
      if OUT=\$(aws events put-events --entries '[{"Source":"fruition.check","DetailType":"wake-requested","Detail":"{}"}]' 2>&1); then
        echo "다른 source 발행이 허용됨" >&2; exit 13
      fi
      case "\$OUT" in
        *AccessDenied*) echo "거부됨" ;;
        *) echo "예상과 다른 오류: \$OUT" >&2; exit 15 ;;
      esac
      if [ "\$SEND" = true ]; then
        echo "== 기동 요청 이벤트 발행"
        aws events put-events --entries '[{"Source":"fruition.frontend","DetailType":"wake-requested","Detail":"{}"}]' \
          --query FailedEntryCount --output text || exit 14
      fi
    volumeMounts:
    - name: tmp
      mountPath: /tmp
  volumes:
  - name: tmp
    emptyDir:
      sizeLimit: 16Mi
EOF

# Fargate는 Pod마다 실행 환경을 새로 준비하므로 1~2분 걸린다.
for _ in $(seq 1 60); do
  PHASE=$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.status.phase}')
  case "$PHASE" in Succeeded|Failed) break ;; esac
  sleep 5
done
kubectl -n "$NS" logs "$POD" || true
echo "dnsPolicy=$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.spec.dnsPolicy}') node=$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.spec.nodeName}')"
if [ "$PHASE" != "Succeeded" ]; then
  echo "pod phase: $PHASE" >&2
  # 운영자 Role에는 events 조회 권한이 없어 describe 대신 Pod 상태만 출력한다.
  kubectl -n "$NS" get pod "$POD" -o jsonpath='{.status.conditions}{"\n"}{.status.containerStatuses}{"\n"}' >&2
  exit 1
fi
