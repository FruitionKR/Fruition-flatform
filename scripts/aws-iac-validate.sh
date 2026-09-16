#!/usr/bin/env bash
set -Eeuo pipefail
# AWS 인증·backend 연결·plan/apply 없이 저장소 코드와 격리 테스트만 검증한다.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
python_bin="${AWS_VALIDATION_PYTHON:-$repo_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || { echo "AWS_VALIDATION_PYTHON에 PyYAML·redis가 설치된 Python을 지정하세요" >&2; exit 1; }
for root in infra/terraform infra/terraform-state-bootstrap; do
  terraform -chdir="$root" fmt -check -recursive
  terraform -chdir="$root" init -backend=false -input=false -lockfile=readonly -no-color
  terraform -chdir="$root" validate -no-color
done
bash -n scripts/aws-platform-up.sh infra/postgres/init-db-isolation.sh infra/postgres/validate-db-isolation.sh
kubectl kustomize k8s/platform/aws >/dev/null
# 실제 kustomize 렌더·app RBAC·fake CLI·임시 PostgreSQL/Redis만 사용한다.
"$python_bin" -m unittest discover -s scripts/tests -p 'test_aws_*.py' -v
git diff --check
