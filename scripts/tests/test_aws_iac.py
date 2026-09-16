"""플랫폼·앱 권한과 remote state/버전의 배포 계약을 확인한다."""

import re
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

class IaCContractTests(unittest.TestCase):
    def test_state_is_locked_and_private_files_are_ignored(self):
        main = (ROOT / "infra/terraform/versions.tf").read_text()
        self.assertRegex(main, r'backend "s3"\s*\{[^}]*use_lockfile\s*=\s*true')
        bootstrap = (ROOT / "infra/terraform-state-bootstrap/main.tf").read_text()
        for expected in ('prevent_destroy = true', 'force_destroy = false', 'sse_algorithm = "AES256"',
                         'status = "Enabled"', '"aws:SecureTransport" = "false"'):
            self.assertIn(expected, re.sub(r" +", " ", bootstrap))
        ignored = ["infra/terraform/secret.tfvars", "infra/terraform/state.tfstate.backup",
                   "infra/terraform/private.tfbackend", "infra/terraform/approved.tfplan",
                   "infra/terraform-state-bootstrap/.terraform/providers/private"]
        for path in ignored:
            self.assertEqual(0, subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode, path)
        for folder in ("infra/terraform", "infra/terraform-state-bootstrap"):
            lock = ROOT / folder / ".terraform.lock.hcl"
            self.assertTrue(lock.exists())
            self.assertNotEqual(0, subprocess.run(["git", "check-ignore", "-q", str(lock)], cwd=ROOT).returncode)

    def test_app_iam_and_autoscaler_writes_have_resource_boundaries(self):
        deploy = (ROOT / "infra/terraform/github-oidc.tf").read_text()
        self.assertNotIn("AmazonEC2ContainerRegistryPowerUser", deploy)
        self.assertIn("repository.arn", deploy)
        self.assertIn('"ecr:ListImages"', deploy)
        self.assertNotIn("ecr:PutImage", deploy)
        self.assertNotIn("ecr:InitiateLayerUpload", deploy)
        self.assertIn("module.eks.cluster_arn", deploy)
        eks = (ROOT / "infra/terraform/eks.tf").read_text()
        self.assertIn('kubernetes_groups = ["fruition:deployers"]', re.sub(r" +", " ", eks))
        self.assertNotIn("AmazonEKSClusterAdminPolicy", eks)
        self.assertIn('autoscaling:ResourceTag/k8s.io/cluster-autoscaler/enabled', eks)
        self.assertIn('autoscaling:ResourceTag/k8s.io/cluster-autoscaler/fruition-eks', eks)
        self.assertIn('node_group_autoscaling_group_names[0]', eks)
        self.assertIn('true:NoSchedule', eks)

    def test_addons_and_feedback_profile_are_explicit(self):
        eks = (ROOT / "infra/terraform/eks.tf").read_text()
        variables = (ROOT / "infra/terraform/variables.tf").read_text()
        self.assertIn('AL2023_x86_64_STANDARD', eks)
        self.assertIn('enableNetworkPolicy = "true"', eks)
        for addon in ("vpc-cni", "coredns", "kube-proxy", "aws-ebs-csi-driver"):
            self.assertIn(f'var.eks_addon_versions["{addon}"]', eks)
        self.assertNotIn('default     = ["0.0.0.0/0"]', variables)
        self.assertIn('var.project == "fruition"', variables)
        self.assertIn('var.region == "ap-northeast-2"', variables)
        self.assertIn('var.eks_version == "1.35"', variables)
        self.assertIn('var.github_deploy_environment == "feedback"', variables)
        self.assertNotIn('var.budget_email == ""', (ROOT / "infra/terraform/budgets.tf").read_text())
        self.assertIn('"no-password-required"', (ROOT / "infra/terraform/elasticache.tf").read_text())

    def test_ci_has_no_aws_credentials_and_covers_infra_paths(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/aws-iac.yml").read_text())
        self.assertEqual({"contents": "read"}, workflow["permissions"])
        trigger = workflow.get("on", workflow.get(True))
        for kind in ("pull_request", "push"):
            self.assertEqual({"infra/**", "k8s/**", "scripts/**", ".github/workflows/**"}, set(trigger[kind]["paths"]))
        steps = workflow["jobs"]["validate"]["steps"]
        self.assertFalse(any("configure-aws-credentials" in step.get("uses", "") for step in steps))
        script = (ROOT / "scripts/aws-iac-validate.sh").read_text()
        self.assertIn("-backend=false", script)
        self.assertIn("-lockfile=readonly", script)
        self.assertNotRegex(script, r"(?m)^\s*aws\s")

if __name__ == "__main__":
    unittest.main()
