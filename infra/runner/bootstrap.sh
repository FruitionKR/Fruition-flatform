#!/usr/bin/env bash
set -Eeuo pipefail
umask 022
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y ca-certificates curl git jq unzip awscli python3.12 python3.12-venv libicu74 libssl3t64 zlib1g

# Ubuntu's signed package repositories supply AWS CLI v2 and Python 3.12.
aws --version
python3.12 --version
if ! snap list amazon-ssm-agent >/dev/null 2>&1; then
  snap install amazon-ssm-agent --classic
fi
snap start --enable amazon-ssm-agent

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
kubectl_version=v1.35.0
curl --fail --silent --show-error --location --retry 3 \
  "https://dl.k8s.io/release/$kubectl_version/bin/linux/amd64/kubectl" -o kubectl
curl --fail --silent --show-error --location --retry 3 \
  "https://dl.k8s.io/release/$kubectl_version/bin/linux/amd64/kubectl.sha256" -o kubectl.sha256
printf '%s  kubectl\n' "$(cat kubectl.sha256)" | sha256sum --check -
install -m 0755 kubectl /usr/local/bin/kubectl

# Official actions/runner v2.337.0 linux-x64 release asset SHA256, checked 2026-09-16.
runner_version=2.337.0
runner_sha256=70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613
curl --fail --silent --show-error --location --retry 3 \
  "https://github.com/actions/runner/releases/download/v$runner_version/actions-runner-linux-x64-$runner_version.tar.gz" -o runner.tar.gz
printf '%s  runner.tar.gz\n' "$runner_sha256" | sha256sum --check -

id gh-runner >/dev/null 2>&1 || useradd --create-home --shell /bin/bash gh-runner
install -d -o gh-runner -g gh-runner /opt/actions-runner
if [[ -e /opt/actions-runner/.runner ]]; then
  echo 'Runner already registered; refusing to overwrite its installation.' >&2
  exit 1
fi
tar -xzf runner.tar.gz -C /opt/actions-runner
chown -R gh-runner:gh-runner /opt/actions-runner
kubectl version --client
touch /var/lib/fruition-runner-ready
echo 'Tools ready. Register via SSM with /usr/local/sbin/fruition-runner-register.'
