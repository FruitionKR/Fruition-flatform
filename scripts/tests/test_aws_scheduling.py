"""공유 파일 제거와 Terraform/Kubernetes worker 배치 계약을 검증한다."""
from pathlib import Path
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKERS = {"ingest-worker", "query-task-worker", "agent-task-worker", "maintenance-task-worker", "converter", "embedding-server"}
# 상시 1개가 필요한 작은 worker. AI 노드에 두면 AI node group이 0대로 내려가지 못한다.
GENERAL_WORKERS = {"edit-event-consumer", "pipeline-agent-worker"}


def render(overlay="overlays/aws"):
    return [r for r in yaml.safe_load_all(subprocess.check_output(
        ["kubectl", "kustomize", str(ROOT / "k8s" / overlay)], text=True)) if r]


def millicores(value):
    return int(value[:-1]) if value.endswith("m") else int(float(value) * 1000)


class SchedulingTest(unittest.TestCase):
    def test_cost_scale_down_only_allows_api_scratch(self):
        resources = list(yaml.safe_load_all(subprocess.check_output(
            ["kubectl", "kustomize", str(ROOT / "k8s/overlays/aws")], text=True)))
        deployments = {r["metadata"]["name"]: r for r in resources if r["kind"] == "Deployment"}
        api = deployments["pipeline-api"]
        annotations = api["spec"]["template"]["metadata"]["annotations"]
        key = "cluster-autoscaler.kubernetes.io/safe-to-evict-local-volumes"
        self.assertEqual("runs", annotations[key])
        volumes = {v["name"]: v for v in api["spec"]["template"]["spec"]["volumes"]}
        self.assertIn("emptyDir", volumes[annotations[key]])
        self.assertEqual(0, api["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"])
        for name in WORKERS | GENERAL_WORKERS:
            self.assertNotIn(key, deployments[name]["spec"]["template"]["metadata"].get("annotations", {}))
        pdb = next(r for r in resources if r["kind"] == "PodDisruptionBudget" and r["metadata"]["name"] == "pipeline-api")
        self.assertEqual(1, pdb["spec"]["minAvailable"])

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
                if name == "maintenance-task-worker":
                    # 회의 녹음 전사: 500MiB 녹음 + chunk WAV를 담는 /tmp.
                    tmp = next(v for v in pod["volumes"] if v["name"] == "tmp")
                    self.assertEqual(tmp["emptyDir"]["sizeLimit"], "1536Mi")
                    self.assertIn({"name": "tmp", "mountPath": "/tmp"}, pod["containers"][0]["volumeMounts"])
                    self.assertEqual(pod["containers"][0]["resources"]["requests"]["ephemeral-storage"], "2Gi")
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
        # frontend는 Fargate라 노드 분산 제약 없이 PDB만 둔다.
        self.assertEqual(set(budgets), apis | {"frontend"})
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

    def test_kafka_backlog_guards_survive_aws_trigger_replacement(self):
        for overlay in ("base", "overlays/aws"):
            output = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "k8s" / overlay)], text=True)
            resources = list(yaml.safe_load_all(output))
            scalers = [r for r in resources if r["kind"] == "ScaledObject" and r["spec"]["triggers"][0]["type"] == "kafka"]
            self.assertEqual(len(scalers), 5)
            for scaler in scalers:
                spec = scaler["spec"]
                meta = spec["triggers"][0]["metadata"]
                self.assertEqual(meta["limitToPartitionsWithLag"], "true")
                self.assertNotEqual(meta.get("excludePersistentLag"), "true")
                behavior = spec["advanced"]["horizontalPodAutoscalerConfig"]["behavior"]
                self.assertEqual(behavior["scaleUp"]["stabilizationWindowSeconds"], 120)
                self.assertEqual(behavior["scaleUp"]["policies"], [{"type": "Pods", "value": 1, "periodSeconds": 60}])
                self.assertGreaterEqual(behavior["scaleDown"]["stabilizationWindowSeconds"], 300)
            config = next(r for r in resources if r["kind"] == "ConfigMap" and r["metadata"]["name"] == "fruition-config")
            self.assertEqual(config["data"]["AI_PURGE_READ_TIMEOUT"], "120s")
            self.assertEqual(config["data"]["EMBEDDING_TIMEOUT_SECONDS"], "10")

    def test_converter_waits_for_a_whole_command_on_sigterm(self):
        # worker는 SIGTERM 뒤에도 진행 중인 command를 끝낸다(마감 7200초). 짧으면 SIGKILL로 끊겨 재전달·모델 비용이 반복된다.
        for overlay in ("base", "overlays/aws"):
            output = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "k8s" / overlay)], text=True)
            resources = list(yaml.safe_load_all(output))
            converter = next(r for r in resources if r["kind"] == "Deployment" and r["metadata"]["name"] == "converter")
            self.assertGreaterEqual(converter["spec"]["template"]["spec"]["terminationGracePeriodSeconds"], 7200 + 600)
            self.assertFalse(any(r["kind"] == "Service" and r["metadata"]["name"] == "converter" for r in resources))
            scaler = next(r for r in resources if r["kind"] == "ScaledObject" and r["metadata"]["name"] == "converter")
            trigger, = scaler["spec"]["triggers"]
            self.assertEqual("ai.convert.command", trigger["metadata"]["topic"])
            self.assertEqual("ai.convert.command-worker", trigger["metadata"]["consumerGroup"])
            self.assertEqual("1", trigger["metadata"]["lagThreshold"])

    def test_maintenance_worker_waits_for_a_whole_meeting_transcription_on_sigterm(self):
        # 회의 녹음 전사(ai ADR 0035)의 마감은 1500초다. 900초면 rollout·scale-down 때 SIGKILL로 끊겨 재전달된다.
        for overlay in ("base", "overlays/aws"):
            output = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "k8s" / overlay)], text=True)
            worker = next(r for r in yaml.safe_load_all(output)
                          if r and r["kind"] == "Deployment" and r["metadata"]["name"] == "maintenance-task-worker")
            self.assertGreaterEqual(worker["spec"]["template"]["spec"]["terminationGracePeriodSeconds"], 1500 + 300)

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

    def test_ai_workers_scale_to_zero_without_losing_kafka_offsets(self):
        for overlay in ("base", "overlays/aws"):
            resources = render(overlay)
            scalers = {r["metadata"]["name"]: r["spec"] for r in resources if r["kind"] == "ScaledObject"}
            self.assertEqual(set(scalers), WORKERS)
            for name, spec in scalers.items():
                self.assertEqual(0, spec["minReplicaCount"], name)
                trigger, = spec["triggers"]
                if trigger["type"] == "kafka":
                    # 0에서 깨우는 기준은 lag 1건이다. 대화형 질의·에이전트는 대화 중 다시 cold start하지 않게 오래 둔다.
                    self.assertNotIn("activationLagThreshold", trigger["metadata"])
                    self.assertNotEqual("true", trigger["metadata"].get("scaleToZeroOnInvalidOffset"))
                    self.assertGreaterEqual(spec["cooldownPeriod"], 1800 if name in {"query-task-worker", "agent-task-worker"} else 600)
            # embedding-server는 질의 임베딩을 부르는 worker Pod가 있을 때만 1개 뜬다.
            embedding = scalers["embedding-server"]
            self.assertEqual(1, embedding["maxReplicaCount"])
            self.assertEqual({"type": "kubernetes-workload", "metadata": {
                "podSelector": "app in (query-task-worker,agent-task-worker)", "value": "1"}}, embedding["triggers"][0])
            # 빈 consumer group의 offset이 지워지면 KEDA는 lag을 topic 끝 offset 전체로 보고 worker를 계속 깨운다.
            kafka = next(r for r in resources if r["kind"] == "Kafka")
            retention_minutes = kafka["spec"]["kafka"]["config"]["offsets.retention.minutes"]
            self.assertGreaterEqual(retention_minutes, 365 * 24 * 60)
            for topic in (r for r in resources if r["kind"] == "KafkaTopic"):
                self.assertGreater(retention_minutes * 60_000, int(topic["spec"]["config"]["retention.ms"]))

    def test_embedding_callers_wait_for_embedding_server_before_consuming(self):
        deployments = {r["metadata"]["name"]: r for r in render() if r["kind"] == "Deployment"}
        for name in ("query-task-worker", "agent-task-worker"):
            pod = deployments[name]["spec"]["template"]["spec"]
            env = {e["name"]: e.get("value") for e in pod["containers"][0]["env"]}
            self.assertEqual("http://embedding-server:8000", env["EMBEDDING_SERVICE_URL"])
            init, = pod["initContainers"]
            self.assertIn("http://embedding-server:8000/health", init["command"][-1])
            self.assertEqual(pod["containers"][0]["image"], init["image"])
            self.assertFalse(init["securityContext"]["allowPrivilegeEscalation"])
            self.assertEqual(["ALL"], init["securityContext"]["capabilities"]["drop"])
        # 다른 worker는 embedding-server를 부르지 않으므로 기다리지 않는다.
        for name in (WORKERS | GENERAL_WORKERS) - {"query-task-worker", "agent-task-worker"}:
            self.assertNotIn("initContainers", deployments[name]["spec"]["template"]["spec"])

    def test_general_node_steady_state_requests_fit_two_t3_large(self):
        resources = render()
        deployments = {r["metadata"]["name"]: r for r in resources if r["kind"] == "Deployment"}
        general = {name: d for name, d in deployments.items()
                   # frontend는 Fargate profile로 뜬다(test_api_rollout_can_surge_on_two_nodes...).
                   if not d["spec"]["template"]["spec"].get("nodeSelector") and name != "frontend"}
        self.assertEqual({"access-svc", "document-svc", "pipeline-api"} | GENERAL_WORKERS, set(general))
        app = sum(d["spec"].get("replicas", 1) * millicores(d["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"])
                  for d in general.values())
        pool = next(r for r in resources if r["kind"] == "KafkaNodePool")
        kafka = millicores(pool["spec"]["resources"]["requests"]["cpu"])
        # 2026-11-02 실측: 일반 노드 3대 할당 가능 합 5790m, 요청 합 4710m 중 앱(fruition) 2950m.
        # 나머지 1760m = 시스템 controller + 노드별 DaemonSet x 3. DaemonSet을 노드당 300m 이하로 보면
        # 2대일 때 시스템 요청은 1760 - 300 = 1460m 이상 1560m 이하다. Strimzi operator(Helm 설치)는 200m.
        allocatable, system, operator = 2 * 1930, 1560, 200
        total = app + kafka + operator + system
        # 배포 때 늘어난 3번째 노드를 Cluster Autoscaler가 지우려면 그 위의 Pod가 2대에 다시 들어가야 한다.
        # API마다 1개(100+150+150m)와 일반 worker(100m), 다음 rollout surge 1개(150m)를 받을 여유에
        # 시스템 요청 추정 오차 250m를 더해 남긴다.
        self.assertGreaterEqual(allocatable - total, 400 + 100 + 150 + 250, total)
        # Kafka는 일반 노드 상주이며 요청값을 줄이지 않는다.
        self.assertEqual(250, kafka)

    def test_api_autoscaling_keeps_absolute_cpu_trigger_after_request_cut(self):
        resources = render()
        requests = {r["metadata"]["name"]: millicores(r["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"])
                    for r in resources if r["kind"] == "Deployment"}
        expected = {"access-svc": 175, "document-svc": 300, "pipeline-api": 300}
        for hpa in (r for r in resources if r["kind"] == "HorizontalPodAutoscaler"):
            name = hpa["metadata"]["name"]
            target = hpa["spec"]["metrics"][0]["resource"]["target"]["averageUtilization"]
            self.assertEqual(expected[name], requests[name] * target // 100, name)
            self.assertEqual((2, 4), (hpa["spec"]["minReplicas"], hpa["spec"]["maxReplicas"]))


if __name__ == "__main__":
    unittest.main()
