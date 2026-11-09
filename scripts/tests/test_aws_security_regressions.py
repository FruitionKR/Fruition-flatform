"""Security policy checks; no AWS or Kubernetes calls."""
import re
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SecurityRegressionTests(unittest.TestCase):
    def test_denied_operator_stops_before_pod_or_database_access(self):
        for script, args in [("aws-ops-db-query.sh", ["SELECT 1"]),
                             ("aws-frontend-wake-check.sh", [])]:
            with self.subTest(script=script), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                log = root / "calls"
                for name, body in {
                    "aws": '#!/bin/sh\nexit 0\n',
                    "kubectl": '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\nexit 1\n',
                }.items():
                    executable = root / name
                    executable.write_text(body)
                    executable.chmod(0o755)
                env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
                       "CALL_LOG": str(log), "TMPDIR": directory}
                result = subprocess.run(["bash", str(ROOT / "scripts" / script), *args],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 1)
                self.assertIn("fruition:operators", result.stderr)
                self.assertEqual(log.read_text().splitlines(),
                                 ["-n fruition auth can-i create pods --quiet"])

    def test_db_query_pod_is_outside_service_and_hpa_but_allowed_to_database(self):
        script = (ROOT / "scripts/aws-ops-db-query.sh").read_text()
        label = re.search(r"^    app: (\S+)$", script, re.M).group(1)
        self.assertIn("requests:", script)
        manifests = list((ROOT / "k8s").rglob("*.yaml"))
        selected = [path.name for path in manifests
                    if re.search(rf"selector:\s*\n(\s+matchLabels:\s*\n)?\s+app: {label}\s*$", path.read_text(), re.M)]
        self.assertEqual(selected, [])
        policies = (ROOT / "k8s/overlays/aws/networkpolicy.yaml").read_text().split("---")
        for name in ("aws-app-dns", "aws-app-database"):
            policy = next(doc for doc in policies if re.search(rf"^  name: {name}$", doc, re.M))
            self.assertRegex(policy, rf"- {label}\b")

    def test_operator_role_has_no_workload_mutation_or_secret_read(self):
        documents = (ROOT / "k8s/platform/aws/deploy-rbac.yaml").read_text().split("---")
        roles = [doc for doc in documents
                 if re.search(r"^kind: Role$", doc, re.M)
                 and re.search(r"^  name: operations-query$", doc, re.M)]
        self.assertEqual(len(roles), 1)
        rules = roles[0].split("rules:", 1)[1]
        for verbs in re.findall(r"verbs: \[([^\]]+)\]", rules):
            self.assertLessEqual({v.strip() for v in verbs.split(",")}, {"get", "list", "watch"})
        for resources in re.findall(r"resources: \[([^\]]+)\]", rules):
            self.assertLessEqual({r.strip() for r in resources.split(",")},
                                 {"pods", "pods/log", "deployments"})

    def test_global_api_rate_limit_normalizes_before_prefix_comparison(self):
        text = (ROOT / "infra/terraform/cost-guards.tf").read_text()
        start = text.index('name     = "all-api-requests"')
        rule = text[start:text.index("visibility_config", start)]
        self.assertIn('search_string         = "/api/"', rule)
        self.assertIn('positional_constraint = "STARTS_WITH"', rule)
        transforms = re.findall(
            r'text_transformation\s*\{\s*priority\s*=\s*(\d+)\s*type\s*=\s*"([A-Z_]+)"', rule)
        self.assertEqual(sorted(transforms), [("0", "URL_DECODE"), ("1", "NORMALIZE_PATH")])


if __name__ == "__main__":
    unittest.main()
