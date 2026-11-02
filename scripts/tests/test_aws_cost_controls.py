import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aws_deploy as deploy

ROOT = Path(__file__).resolve().parents[2]


class HeadroomTests(unittest.TestCase):
    documents = [{"kind": "Deployment", "metadata": {"name": "pipeline-api"},
                  "spec": {"template": {"spec": {"containers": [{"image": "fixture@sha256:abc"}]}}}}]

    def test_ready_capacity_is_released_before_return_and_has_bounded_lifetime(self):
        ready = json.dumps({"items": [{"status": {"phase": "Running", "conditions": [
            {"type": "Ready", "status": "True"}]}}]})
        with patch.object(deploy, "kubectl", side_effect=["", ready, ""]) as kube:
            deploy.reserve_deployment_headroom(self.documents)
        job = yaml.safe_load(kube.call_args_list[0].kwargs["input"])
        self.assertEqual(1200, job["spec"]["activeDeadlineSeconds"])
        self.assertEqual(60, job["spec"]["ttlSecondsAfterFinished"])
        pod = job["spec"]["template"]["spec"]
        self.assertEqual({"eks.amazonaws.com/capacityType": "ON_DEMAND"}, pod["nodeSelector"])
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertNotIn("env", pod["containers"][0])
        resources = pod["containers"][0]["resources"]
        self.assertEqual({"cpu": "1200m", "memory": "3Gi"}, resources["requests"])
        self.assertEqual(resources["requests"], resources["limits"])
        # 빈 t3.large(1930m) - DaemonSet 추정 255m에 10% 이상 여유를 남기고, 가장 큰 API surge 1개는 덮는다.
        self.assertLessEqual(1200, (1930 - 255) * 0.9)
        output = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "k8s/overlays/aws")], text=True)
        apis = [r for r in yaml.safe_load_all(output) if r and r["kind"] == "Deployment"
                and r["metadata"]["name"] in {"access-svc", "document-svc", "pipeline-api"}]
        def millicores(value):
            return int(value[:-1]) if value.endswith("m") else int(float(value) * 1000)
        def mebibytes(value):
            return int(value[:-2]) * (1024 if value.endswith("Gi") else 1)
        for api in apis:
            request = api["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]
            self.assertLessEqual(millicores(request["cpu"]), 1200, api["metadata"]["name"])
            self.assertLessEqual(mebibytes(request["memory"]), 3 * 1024, api["metadata"]["name"])
        self.assertEqual("delete", kube.call_args_list[-1].args[0])
        self.assertIn("--wait=true", kube.call_args_list[-1].args)

    def test_failed_reservation_cleans_up_and_stops_rollout(self):
        failed = json.dumps({"items": [{"status": {"phase": "Failed"}}]})
        with patch.object(deploy, "kubectl", side_effect=["", failed, ""]) as kube:
            with self.assertRaises(RuntimeError):
                deploy.reserve_deployment_headroom(self.documents)
        self.assertEqual("delete", kube.call_args_list[-1].args[0])

    def test_timeout_cleans_up_without_accepting_pending_capacity(self):
        with patch.object(deploy, "kubectl", return_value="") as kube, \
                patch.object(deploy.time, "monotonic", side_effect=[0, 901]):
            with self.assertRaises(TimeoutError):
                deploy.reserve_deployment_headroom(self.documents)
        self.assertEqual(["create", "delete"], [c.args[0] for c in kube.call_args_list])

    def test_conflicting_job_is_not_deleted(self):
        with patch.object(deploy, "kubectl", side_effect=subprocess.CalledProcessError(1, "create")) as kube:
            with self.assertRaises(subprocess.CalledProcessError):
                deploy.reserve_deployment_headroom(self.documents)
        self.assertEqual(1, kube.call_count)


class ServiceLimitTests(unittest.TestCase):
    def test_ai_limits_stay_off_and_reach_document_svc(self):
        output = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "k8s/overlays/aws")], text=True)
        resources = [r for r in yaml.safe_load_all(output) if r]
        config = next(r for r in resources if r["kind"] == "ConfigMap" and r["metadata"]["name"] == "fruition-config")
        self.assertEqual("false", config["data"]["AI_LIMIT_ENABLED"])
        # 업로드 한도는 코드 기본값(켜짐)을 쓴다. 여기서 끄지 않는다.
        self.assertNotIn("UPLOAD_LIMITS_ENABLED", config["data"])
        document = next(r for r in resources if r["kind"] == "Deployment" and r["metadata"]["name"] == "document-svc")
        container = document["spec"]["template"]["spec"]["containers"][0]
        self.assertIn({"configMapRef": {"name": "fruition-config"}}, container["envFrom"])
        self.assertNotIn("AI_LIMIT_ENABLED", {e["name"] for e in container.get("env", [])})


class TelemetryTests(unittest.TestCase):
    def test_alarm_metrics_survive_allowlist_with_compatible_dimensions(self):
        config = json.loads((ROOT / "infra/observability/addon-config.json").read_text())
        otel = config["agent"]["otelConfig"]
        names = otel["processors"]["filter/cost"]["metrics"]["include"]["metric_names"]
        self.assertEqual({"node_cpu_utilization", "node_memory_utilization", "cluster_failed_node_count",
                          "pod_cpu_utilization", "pod_memory_utilization"}, set(names))
        self.assertNotIn("logs", config["agent"]["config"])
        self.assertFalse(otel["receivers"]["awscontainerinsightreceiver/cost"]["enable_control_plane_metrics"])
        exporter = otel["exporters"]["awsemf/cost"]
        self.assertEqual("ContainerInsights", exporter["namespace"])
        self.assertEqual("NoDimensionRollup", exporter["dimension_rollup_option"])
        self.assertEqual([["ClusterName"]], exporter["metric_declarations"][0]["dimensions"])
        self.assertEqual([["ClusterName", "Namespace"]], exporter["metric_declarations"][1]["dimensions"])


if __name__ == "__main__":
    unittest.main()
