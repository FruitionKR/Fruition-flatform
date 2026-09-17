#!/usr/bin/env bash
# Run interactively through SSM, never through cloud-init or an Actions job.
set +x
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ -f /var/lib/fruition-runner-ready ]] || { echo 'Bootstrap has not completed.' >&2; exit 1; }
cd /opt/actions-runner
[[ ! -e .runner ]] || { echo 'Already registered; inspect sudo ./svc.sh status.' >&2; exit 1; }
repo=$(jq -er '.github_repo' /etc/fruition-runner.json)
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || exit 1
read -r -s -p 'GitHub repository runner registration token (hidden): ' runner_token
printf '\n'
[[ -n "$runner_token" ]] || { echo 'Empty token.' >&2; exit 1; }
trap 'unset runner_token' EXIT
runuser -u gh-runner -- ./config.sh --unattended \
  --url "https://github.com/$repo" --token "$runner_token" \
  --name "fruition-feedback-$(hostname)" --labels fruition-feedback --work _work
unset runner_token
# The runner has no sudo rights. The root operator installs the system service.
./svc.sh install gh-runner
./svc.sh start
./svc.sh status
