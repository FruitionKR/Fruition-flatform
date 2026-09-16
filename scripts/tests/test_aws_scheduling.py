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


if __name__ == "__main__":
    unittest.main()
