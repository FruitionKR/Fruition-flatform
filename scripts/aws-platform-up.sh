#!/usr/bin/env bash
set -Eeuo pipefail
# 플랫폼 관리자 전용. 명시적 install 인수가 없으면 실제 cluster를 변경하지 않는다.
[[ "${1:-}" == install && -n "${2:-}" ]] || {
  echo "사용법: bash scripts/aws-platform-up.sh install /secure/path/terraform-outputs.json" >&2
  exit 2
}
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
outputs="$2"
alb_role="$(jq -er '.irsa_role_arns.value.alb_controller' "$outputs")"
eso_role="$(jq -er '.irsa_role_arns.value.external_secrets' "$outputs")"
ca_role="$(jq -er '.irsa_role_arns.value.cluster_autoscaler' "$outputs")"
[[ "$(jq -er '.cluster_name.value' "$outputs")" == fruition-eks ]]
cluster_arn="$(jq -er '.cluster_arn.value' "$outputs")"
cluster_endpoint="$(jq -er '.cluster_endpoint.value' "$outputs")"
[[ "$cluster_arn" =~ ^arn:aws:eks:ap-northeast-2:([0-9]{12}):cluster/fruition-eks$ ]] || {
  echo "서울 feedback cluster ARN이 필요합니다" >&2; exit 1;
}
account_id="${BASH_REMATCH[1]}"
for role in "$alb_role" "$eso_role" "$ca_role"; do
  [[ "$role" =~ ^arn:aws:iam::${account_id}:role/[A-Za-z0-9+=,.@_/-]+$ ]] || { echo "동일 계정의 addon IAM role 필요" >&2; exit 1; }
done
# 쓰기 전에 AWS 실제 대상과 현재 kubeconfig의 API 서버를 같은 Terraform output에 대조한다.
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$account_id" ]] || {
  echo "AWS 인증 계정이 대상과 다릅니다" >&2; exit 1;
}
cluster="$(aws eks describe-cluster --region ap-northeast-2 --name fruition-eks --output json)"
[[ "$(jq -er '.cluster.arn' <<< "$cluster")" == "$cluster_arn" &&
   "$(jq -er '.cluster.endpoint' <<< "$cluster")" == "$cluster_endpoint" &&
   "$(jq -er '.cluster.version' <<< "$cluster")" == "1.35" &&
   "$(jq -er '.cluster.status' <<< "$cluster")" == "ACTIVE" ]] || {
  echo "실제 EKS cluster가 Terraform 대상/버전/준비 상태와 다릅니다" >&2; exit 1;
}
[[ "$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')" == "$cluster_endpoint" ]] || {
  echo "현재 Kubernetes context의 API 서버가 대상 EKS와 다릅니다" >&2; exit 1;
}
vpc_id="$(jq -er '.cluster.resourcesVpcConfig.vpcId' <<< "$cluster")"
[[ "$(kubectl get --raw /version | jq -r '.minor | sub("\\+.*$"; "")')" == "35" ]] || {
  echo "검토된 EKS 1.35 cluster가 아닙니다" >&2; exit 1;
}
kubectl apply -f "$repo_root/k8s/base/namespace.yaml"
helm repo add eks https://aws.github.io/eks-charts --force-update
helm repo add external-secrets https://charts.external-secrets.io --force-update
helm repo add autoscaler https://kubernetes.github.io/autoscaler --force-update
helm repo add strimzi https://strimzi.io/charts/ --force-update
helm repo add kedacore https://kedacore.github.io/charts --force-update
helm repo update
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller --version 3.5.0 \
  -n kube-system --wait --timeout 10m \
  --set clusterName=fruition-eks --set region=ap-northeast-2 --set-string "vpcId=$vpc_id" \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set-string "serviceAccount.annotations.eks\.amazonaws\.com/role-arn=$alb_role"
helm upgrade --install external-secrets external-secrets/external-secrets --version 2.9.0 \
  -n external-secrets --create-namespace --wait --timeout 10m \
  --set serviceAccount.name=external-secrets \
  --set-string "serviceAccount.annotations.eks\.amazonaws\.com/role-arn=$eso_role"
helm upgrade --install cluster-autoscaler autoscaler/cluster-autoscaler --version 9.59.0 \
  -n kube-system --wait --timeout 10m --set image.tag=v1.35.0 \
  --set autoDiscovery.clusterName=fruition-eks --set awsRegion=ap-northeast-2 \
  --set rbac.serviceAccount.name=cluster-autoscaler \
  --set-string "rbac.serviceAccount.annotations.eks\.amazonaws\.com/role-arn=$ca_role"
helm upgrade --install strimzi strimzi/strimzi-kafka-operator --version 1.1.0 \
  -n fruition --wait --timeout 10m
helm upgrade --install keda kedacore/keda --version 2.20.2 \
  -n keda --create-namespace --wait --timeout 10m
kubectl apply --dry-run=server -k "$repo_root/k8s/platform/aws"
kubectl apply -k "$repo_root/k8s/platform/aws"
kubectl wait clustersecretstore/aws-secrets-manager --for=condition=Ready --timeout=600s
echo "플랫폼 적용 완료. 앱 role의 허용/거부와 CRD server dry-run을 별도로 검증하세요."
