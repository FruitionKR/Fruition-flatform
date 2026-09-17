#!/usr/bin/env bash
# Read-only checks; no workload is deployed. Requires platform RBAC installation.
set -Eeuo pipefail
: "${DEPLOY_ROLE:?Set AWS_DEPLOY_ROLE_ARN in the feedback Environment}"
: "${KUBECONFIG:?Use a temporary kubeconfig}"
[[ "$DEPLOY_ROLE" =~ ^arn:aws:iam::([0-9]{12}):role/(.+)$ ]] || exit 1
account="${BASH_REMATCH[1]}"
role_name="${BASH_REMATCH[2]##*/}"
identity=$(aws sts get-caller-identity --output json)
[[ "$(jq -r .Account <<< "$identity")" == "$account" ]] || { echo "Runner readiness check failed." >&2; exit 1; }
[[ "$(jq -r .Arn <<< "$identity")" == "arn:aws:sts::$account:assumed-role/$role_name/"* ]] || { echo "Runner readiness check failed." >&2; exit 1; }
cluster=$(aws eks describe-cluster --name fruition-eks --region ap-northeast-2 --output json)
jq -e '.cluster.status == "ACTIVE" and .cluster.resourcesVpcConfig.endpointPrivateAccess == true and .cluster.resourcesVpcConfig.endpointPublicAccess == false' <<< "$cluster" >/dev/null
aws eks update-kubeconfig --name fruition-eks --region ap-northeast-2
kubectl --request-timeout=30s get --raw /version >/dev/null
[[ "$(kubectl --request-timeout=30s auth can-i get deployments -n fruition)" == yes ]] || { echo "Runner readiness check failed." >&2; exit 1; }
[[ "$(kubectl --request-timeout=30s auth can-i create jobs -n fruition)" == yes ]] || { echo "Runner readiness check failed." >&2; exit 1; }
# can-i returns status 1 for a denial; also check its output so transport errors fail.
for permission in 'get secrets fruition' 'create rolebindings fruition' 'create deployments default'; do
  read -r verb resource namespace <<< "$permission"
  answer=$(kubectl --request-timeout=30s auth can-i "$verb" "$resource" -n "$namespace") || true
  [[ "$answer" == no ]] || { echo "Runner readiness check failed." >&2; exit 1; }
done
echo 'PASS: OIDC identity, private EKS connectivity and deployment permission boundaries.'
