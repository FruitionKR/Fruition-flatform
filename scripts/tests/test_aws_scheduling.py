"""공유 파일 제거와 Terraform/Kubernetes worker 배치 계약을 검증한다."""
from pathlib import Path
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKERS = {"ingest-worker", "pipeline-agent-worker", "query-task-worker", "agent-task-worker", "maintenance-task-worker", "edit-event-consumer", "converter"}


class SchedulingTest(unittest.TestCase):
    def test_independent_scratch_and_spot_workers(self):
        terraform = (ROOT / "infra/terraform/eks.tf").read_text()
        self.assertIn('"fruition.io/node-role" = "ai-worker"', terraform)
        self.assertIn('key    = "fruition.io/ai-worker"', terraform)
        self.assertIn('effect = "NO_SCHEDULE"', terraform)
        for overlay in ("base", "overlays/aws"):
            output = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "k8s" / overlay)], text=True)
            resources = list(yaml.safe_load_all(output))
            self.assertFalse(any(r["kind"] == "PersistentVolumeClaim" and r["metadata"]["name"] == "pipeline-runs" for r in resources))
            seen = set()
            for resource in resources:
                if resource["kind"] != "Deployment":
                    continue
                name = resource["metadata"]["name"]
                pod = resource["spec"]["template"]["spec"]
                self.assertNotIn("podAffinity", pod.get("affinity", {}))
                if name in ("pipeline-api", "ingest-worker"):
                    self.assertEqual(next(v for v in pod["volumes"] if v["name"] == "runs"), {"name": "runs", "emptyDir": {}})
                if overlay == "overlays/aws" and name in WORKERS:
                    seen.add(name)
                    self.assertEqual(pod["nodeSelector"], {"fruition.io/node-role": "ai-worker"})
                    self.assertIn({"key": "fruition.io/ai-worker", "operator": "Equal", "value": "true", "effect": "NoSchedule"}, pod["tolerations"])
                elif overlay == "overlays/aws":
                    self.assertFalse(pod.get("tolerations"))
            if overlay == "overlays/aws":
                self.assertEqual(seen, WORKERS)
        self.assertNotIn("pipeline-runs:", (ROOT / "infra/compose.ai.yml").read_text())

    def test_api_rollout_can_surge_on_two_nodes_and_preserves_one_ready_pod(self):
        output = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "k8s/overlays/aws")], text=True)
        resources = list(yaml.safe_load_all(output))
        apis = {"access-svc", "document-svc", "pipeline-api"}
        budgets = {r["metadata"]["name"]: r["spec"] for r in resources if r["kind"] == "PodDisruptionBudget"}
        self.assertEqual(set(budgets), apis)
        for r in resources:
            if r["kind"] != "Deployment" or r["metadata"]["name"] not in apis:
                continue
            name, spec = r["metadata"]["name"], r["spec"]
            pod = spec["template"]["spec"]
            self.assertEqual(spec["replicas"], 2)
            self.assertEqual(spec["strategy"]["rollingUpdate"], {"maxUnavailable": 0, "maxSurge": 1})
            self.assertEqual(budgets[name]["minAvailable"], 1)
            self.assertEqual(budgets[name]["selector"], spec["selector"])
            self.assertNotIn("requiredDuringSchedulingIgnoredDuringExecution", pod.get("affinity", {}).get("podAntiAffinity", {}))
            host = next(c for c in pod["topologySpreadConstraints"] if c["topologyKey"] == "kubernetes.io/hostname")
            self.assertEqual(host["labelSelector"], spec["selector"])
            self.assertEqual(host["whenUnsatisfiable"], "DoNotSchedule")
            self.assertEqual(host["nodeTaintsPolicy"], "Honor")
            # One replacement can coexist with two existing replicas on the same two nodes.
            self.assertLessEqual(max(2, 1) - min(2, 1), host["maxSkew"])
            self.assertGreater(max(2, 0) - min(2, 0), host["maxSkew"])
            zone = next(c for c in pod["topologySpreadConstraints"] if c["topologyKey"] == "topology.kubernetes.io/zone")
            self.assertEqual(zone["whenUnsatisfiable"], "ScheduleAnyway")
            container = pod["containers"][0]
            drain = container["lifecycle"]["preStop"]["sleep"]["seconds"]
            self.assertGreater(pod["terminationGracePeriodSeconds"], drain + 40)
            if name != "pipeline-api":
                env = {e["name"]: e.get("value") for e in container["env"]}
                self.assertEqual(env["SERVER_SHUTDOWN"], "graceful")
                self.assertEqual(env["SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE"], "40s")

    def test_security_preserves_converter_and_enforces_namespace_before_addons(self):
        output = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "k8s/overlays/aws")], text=True)
        resources = list(yaml.safe_load_all(output))
        for r in resources:
            if r["kind"] not in {"Deployment", "Job"}:
                continue
            pod = r["spec"]["template"]["spec"]
            self.assertEqual(pod["securityContext"]["seccompProfile"]["type"], "RuntimeDefault")
            context = pod["containers"][0]["securityContext"]
            self.assertFalse(context["allowPrivilegeEscalation"])
            self.assertIn("ALL", context["capabilities"]["drop"])
            if r["metadata"]["name"] == "converter":
                self.assertTrue(context["readOnlyRootFilesystem"])
            self.assertTrue(pod["securityContext"]["runAsNonRoot"])
            self.assertEqual(pod["securityContext"]["runAsUser"], 10001)
            self.assertEqual(pod["securityContext"]["fsGroup"], 10001)
        labels = yaml.safe_load((ROOT / "k8s/platform/aws/namespace.yaml").read_text())["metadata"]["labels"]
        self.assertEqual(labels["pod-security.kubernetes.io/enforce"], "baseline")
        self.assertEqual(labels["pod-security.kubernetes.io/warn"], "restricted")
        self.assertEqual(labels["elbv2.k8s.aws/pod-readiness-gate-inject"], "enabled")
        script = (ROOT / "scripts/aws-platform-up.sh").read_text()
        self.assertLess(script.index('kubectl apply -f "$repo_root/k8s/platform/aws/namespace.yaml"'), script.index("helm upgrade --install"))


if __name__ == "__main__":
    unittest.main()
