#!/usr/bin/env bash
set -Eeuo pipefail
# infra/terraform을 실행하며 SMTP 비밀번호를 Secrets Manager에서 읽어 주입한다.
# tfvars에 비밀번호를 평문으로 두지 않기 위한 래퍼다.
#
# 사용:
#   bash scripts/aws-terraform.sh plan
#   bash scripts/aws-terraform.sh apply
#   bash scripts/aws-terraform.sh plan -out=/tmp/x.tfplan
#
# -var-file은 자동으로 붙는다. 다른 tfvars를 쓰려면 TFVARS로 지정한다.
#
# secrets.tf의 aws_secretsmanager_secret_version.app은 ignore_changes=[secret_string]이라
# Terraform이 이 값을 덮어쓰지 않는다. 같은 값을 되먹이므로 plan에 차이가 생기지 않으며,
# 혹시 ignore_changes가 풀리더라도 placeholder가 아닌 실제 값이 들어간다.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tf_dir="$repo_root/infra/terraform"
region="${AWS_REGION:-ap-northeast-2}"
secret_id="${APP_SECRET_ID:-fruition/app}"
tfvars="${TFVARS:-feedback.tfvars}"

[[ $# -ge 1 ]] || { echo "usage: $0 <plan|apply|...> [terraform args]" >&2; exit 2; }
[[ -f "$tf_dir/$tfvars" ]] || { echo "$tf_dir/$tfvars 가 없습니다. TFVARS로 지정하세요." >&2; exit 1; }

if [[ -z "${TF_VAR_smtp_password:-}" ]]; then
  # 최초 설치처럼 시크릿이 아직 없으면 운영자가 직접 TF_VAR_smtp_password를 넣어야 한다.
  if ! secret_json=$(aws secretsmanager get-secret-value \
    --secret-id "$secret_id" --region "$region" \
    --query SecretString --output text 2>/dev/null); then
    echo "Secrets Manager에서 $secret_id 를 읽지 못했습니다." >&2
    echo "최초 설치라면 TF_VAR_smtp_password를 직접 export한 뒤 다시 실행하세요." >&2
    exit 1
  fi

  TF_VAR_smtp_password=$(SECRET_JSON="$secret_json" python3 -c '
import json, os, sys
raw = os.environ["SECRET_JSON"]
data = json.loads(raw)
if isinstance(data, str):
    data = json.loads(data)
value = data.get("SPRING_MAIL_PASSWORD", "")
if not str(value).strip():
    sys.exit("SPRING_MAIL_PASSWORD가 비어 있습니다")
print(value)
')
  export TF_VAR_smtp_password
  echo "SMTP 비밀번호를 $secret_id 에서 읽었습니다 (값은 출력하지 않습니다)."
fi

cd "$tf_dir"
exec terraform "$@" -var-file="$tfvars"
