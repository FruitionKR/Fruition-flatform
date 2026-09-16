"""플랫폼 설치 CLI는 모두 가짜 실행파일로 대체한다. AWS 계정에 접속하지 않는다."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = "123456789012"
ARN = f"arn:aws:eks:ap-northeast-2:{ACCOUNT}:cluster/fruition-eks"
ENDPOINT = "https://fixture.eks.amazonaws.com"
OUTPUTS = {
    "cluster_name": {"value": "fruition-eks"},
    "cluster_arn": {"value": ARN},
    "cluster_endpoint": {"value": ENDPOINT},
    "irsa_role_arns": {"value": {name: f"arn:aws:iam::{ACCOUNT}:role/{name}"
                               for name in ("alb_controller", "external_secrets", "cluster_autoscaler")}},
}
CLUSTER = {"cluster": {"arn": ARN, "endpoint": ENDPOINT, "version": "1.35", "status": "ACTIVE",
                        "resourcesVpcConfig": {"vpcId": "vpc-fixture"}}}
CLI = r"""
import json, os, sys
from pathlib import Path
tool = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["CLI_EVENTS"], "a") as stream:
    stream.write(json.dumps([tool, *args]) + "\n")
if tool == "aws" and args[0] == "sts":
    print(os.environ["FAKE_ACCOUNT"])
elif tool == "aws" and args[0] == "eks":
    print(os.environ["FAKE_CLUSTER"])
elif tool == "kubectl" and args[:2] == ["config", "view"]:
    print(os.environ["FAKE_ENDPOINT"], end="")
elif tool == "kubectl" and args[:2] == ["get", "--raw"]:
    print('{"major":"1","minor":"35+"}')
"""

class PlatformTests(unittest.TestCase):
    def invoke(self, *, account=ACCOUNT, endpoint=ENDPOINT, cluster=None, outputs=None):
        with tempfile.TemporaryDirectory(prefix="fruition-platform-test-") as directory:
            folder = Path(directory)
            for tool in ("aws", "kubectl", "helm"):
                path = folder / tool
                path.write_text(f"#!{sys.executable}\n" + CLI)
                path.chmod(0o700)
            config = folder / "outputs.json"
            config.write_text(json.dumps(outputs or OUTPUTS))
            events = folder / "events"
            env = {**os.environ, "PATH": str(folder) + os.pathsep + os.environ["PATH"],
                   "FAKE_ACCOUNT": account, "FAKE_ENDPOINT": endpoint,
                   "FAKE_CLUSTER": json.dumps(cluster or CLUSTER), "CLI_EVENTS": str(events)}
            result = subprocess.run(["bash", str(ROOT / "scripts/aws-platform-up.sh"), "install", str(config)],
                                    env=env, text=True, capture_output=True)
            calls = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
            return result, calls

    def test_wrong_account_or_context_cannot_mutate(self):
        for kwargs in ({"account": "999999999999"}, {"endpoint": "https://another.eks.amazonaws.com"}):
            with self.subTest(kwargs=kwargs):
                result, calls = self.invoke(**kwargs)
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(any(c[0] == "helm" or c[1] in {"apply", "patch", "delete"} for c in calls))

    def test_wrong_actual_cluster_or_role_cannot_mutate(self):
        for field, value in (("arn", ARN.replace(ACCOUNT, "999999999999")),
                             ("endpoint", "https://another.eks.amazonaws.com"),
                             ("version", "1.34"), ("status", "UPDATING")):
            cluster = copy.deepcopy(CLUSTER)
            cluster["cluster"][field] = value
            result, calls = self.invoke(cluster=cluster)
            self.assertNotEqual(0, result.returncode, field)
            self.assertFalse(any(c[0] == "helm" or c[1] == "apply" for c in calls))
        outputs = copy.deepcopy(OUTPUTS)
        outputs["irsa_role_arns"]["value"]["alb_controller"] = "arn:aws:iam::999999999999:role/wrong"
        result, calls = self.invoke(outputs=outputs)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(calls)

    def test_matching_target_runs_pinned_installs_after_checks(self):
        result, calls = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)
        first_write = next(i for i, call in enumerate(calls) if call[0] == "helm" or call[1] == "apply")
        self.assertTrue(any(call[:3] == ["aws", "eks", "describe-cluster"] for call in calls[:first_write]))
        self.assertTrue(any(call[:3] == ["kubectl", "config", "view"] for call in calls[:first_write]))
        versions = [call[call.index("--version") + 1] for call in calls if "--version" in call]
        self.assertEqual(["3.5.0", "2.9.0", "9.59.0", "1.1.0", "2.20.2"], versions)

if __name__ == "__main__":
    unittest.main()
