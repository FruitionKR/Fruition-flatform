"""Maintenance regression: existing guards, offline transition, and partial failure."""
import copy
import json
import subprocess
import unittest
from unittest.mock import patch

from test_aws_deploy import CONFIG, SHA, MANIFEST, REVIEW, FakeCluster, deploy
import aws_maintenance as maintenance


# Sanitized live Helm installation identity; no credentials or cluster endpoints.
OPERATOR_ENV_NAMES = """STRIMZI_NAMESPACE STRIMZI_FULL_RECONCILIATION_INTERVAL_MS
STRIMZI_OPERATION_TIMEOUT_MS STRIMZI_DEFAULT_KAFKA_EXPORTER_IMAGE
STRIMZI_DEFAULT_CRUISE_CONTROL_IMAGE STRIMZI_KAFKA_IMAGES STRIMZI_KAFKA_CONNECT_IMAGES
STRIMZI_KAFKA_MIRROR_MAKER_2_IMAGES STRIMZI_DEFAULT_TOPIC_OPERATOR_IMAGE
STRIMZI_DEFAULT_USER_OPERATOR_IMAGE STRIMZI_DEFAULT_KAFKA_INIT_IMAGE
STRIMZI_DEFAULT_KAFKA_BRIDGE_IMAGE STRIMZI_DEFAULT_KANIKO_EXECUTOR_IMAGE
STRIMZI_DEFAULT_BUILDAH_IMAGE STRIMZI_DEFAULT_MAVEN_BUILDER STRIMZI_OPERATOR_NAMESPACE
STRIMZI_FEATURE_GATES STRIMZI_LEADER_ELECTION_ENABLED STRIMZI_LEADER_ELECTION_LEASE_NAME
STRIMZI_LEADER_ELECTION_LEASE_NAMESPACE STRIMZI_LEADER_ELECTION_IDENTITY""".split()


def strimzi_controllers():
    template = {"metadata": {"labels": {"name": "strimzi-cluster-operator",
                "strimzi.io/kind": "cluster-operator"}},
                "spec": {"serviceAccountName": "strimzi-cluster-operator", "containers": [{
                    "name": "strimzi-cluster-operator", "image": "quay.io/strimzi/operator:1.1.0",
                    "args": ["/opt/strimzi/bin/cluster_operator_run.sh"],
                    "env": [{"name": name, "value": "sanitized"} for name in OPERATOR_ENV_NAMES]}]}}
    controller = {"kind": "Deployment", "metadata": {"name": "strimzi-cluster-operator",
        "labels": {"app": "strimzi", "app.kubernetes.io/managed-by": "Helm",
                   "chart": "strimzi-kafka-operator-1.1.0", "component": "deployment",
                   "heritage": "Helm", "release": "strimzi"}},
        "spec": {"replicas": 1, "template": template}, "status": {"replicas": 1}}
    pod = copy.deepcopy(template)
    pod["metadata"].update({"name": "strimzi-cluster-operator-6d7846b9b9-abcde",
        "ownerReferences": [{"kind": "ReplicaSet", "name": "strimzi-cluster-operator-6d7846b9b9", "controller": True}]})
    pod["status"] = {"phase": "Running"}
    entity = {"kind": "Deployment", "metadata": {"name": "kafka-entity-operator", "labels": {
        "strimzi.io/cluster": "kafka", "strimzi.io/kind": "Kafka"}}, "spec": {"replicas": 1}}
    return controller, pod, entity


class MaintenanceCluster(FakeCluster):
    def __init__(self, documents, **kwargs):
        super().__init__(**kwargs)
        self.resources = {name: [] for name in ("pods", "jobs", "cronjobs", "scaledobjects", "horizontalpodautoscalers", "targetgroupbindings")}
        self.resources["deployments"] = copy.deepcopy([d for d in documents if d["kind"] == "Deployment"])
        for d in self.resources["deployments"]:
            d["metadata"]["generation"] = 2
            d["spec"]["replicas"] = 0
            d["status"] = {"replicas": 0, "observedGeneration": 2}
            for c in d["spec"]["template"]["spec"]["containers"]:
                c["image"] = c["image"].split(":")[0] + "@sha256:" + "d" * 64
        self.predecessor = deploy.install_record(deploy.release_name("c" * 40), {
            "safety_contract_version": "2", "fingerprints": json.dumps({s: "a" * 64 for s in maintenance.SERVICES}),
            "config": json.dumps(CONFIG), "manifest": "preserved historical manifest"})
        self.resources["configmaps"] = [self.predecessor]
        self.resources["ingresses"] = [{"apiVersion": "networking.k8s.io/v1", "kind": "Ingress",
            "metadata": {"name": "public", "namespace": "fruition", "annotations": {
                "alb.ingress.kubernetes.io/actions.maintenance": json.dumps({"type": "fixed-response", "fixedResponseConfig": {
                    "contentType": "text/plain", "statusCode": "503", "messageBody": "Maintenance"}})}},
            "spec": {"rules": [{"http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {
                "service": {"name": "maintenance", "port": {"name": "use-annotation"}}}}]}}]}}]

    def run(self, args, *, input=None):
        result = super().run(args, input=input)
        if any(d["kind"] == "Ingress" and "alb.ingress.kubernetes.io/actions.maintenance" not in
               d["metadata"].get("annotations", {}) for d in self.events[-1][1]):
            self.resources.pop("targetgroupbindings", None)
        if args[0] == "kubectl" and args[3] == "get" and args[4] in self.resources:
            return json.dumps({"items": self.resources[args[4]]})
        return result

    def review(self):
        return {"release_sha": SHA, "migration_mode": "maintenance-cutover",
            "expected_predecessor_release": "c" * 40,
            "predecessor_record_sha256": maintenance.digest(self.predecessor["data"]),
            "before_fingerprints": {s: "b" * 64 for s in maintenance.SERVICES},
            "after_fingerprints": {s: "b" * 64 for s in maintenance.SERVICES},
            "expected_live_images": {d["metadata"]["name"] + "/" + c["name"]: c["image"]
                for d in self.resources["deployments"] for c in d["spec"]["template"]["spec"]["containers"]},
            "maintenance_test_url": REVIEW["compatibility_test_url"],
            "restore_test_url": REVIEW["restore_test_url"], "quiescence_test_url": REVIEW["restore_test_url"],
            "data_loss_accepted": True}


class MaintenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = deploy.render(CONFIG, SHA, MANIFEST)

    def setUp(self):
        self.fake = MaintenanceCluster(self.documents)
        for target, kwargs in (("run", {"side_effect": self.fake.run}), ("smoke_settings", {"return_value": {}}),
                               ("authenticated_smoke", {}), ("http_status", {"return_value": "503"}),
                               ("check_public_routes", {})):
            mock = patch.object(deploy, target, **kwargs)
            mock.start()
            self.addCleanup(mock.stop)

    def perform(self, review=None, **kwargs):
        deploy.deploy(CONFIG, SHA, self.documents, review=review or self.fake.review(), **kwargs)

    def test_live_fourteen_deployments_leave_exact_twelve_apps_and_preserve_audit(self):
        review = self.fake.review()
        controller, pod, entity = strimzi_controllers()
        self.fake.resources["deployments"] += [controller, entity]
        self.fake.resources["pods"] = [pod]
        self.assertEqual(14, len(self.fake.resources["deployments"]))
        apps = maintenance.assert_quiescent(deploy, self.documents)
        self.assertEqual(12, len(apps))
        self.assertEqual({d["metadata"]["name"] for d in self.documents if d["kind"] == "Deployment"},
                         {d["metadata"]["name"] for d in apps})
        before = copy.deepcopy(self.fake.predecessor)
        self.perform(review)
        self.assertEqual(before, self.fake.predecessor)
        self.assertTrue(any(d["metadata"]["name"] == deploy.release_name(SHA)
                            for d in self.fake.applied("ConfigMap")))
        self.assertFalse(any("strimzi" in " ".join(args) and any(a in args for a in ("patch", "delete", "scale"))
                             for args, _ in self.fake.events))

    def test_reviewed_operator_invocations_leave_exact_twelve_apps(self):
        launcher = "/opt/strimzi/bin/cluster_operator_run.sh"
        for invocation in ({"args": [launcher]}, {"command": [launcher]}, {}):
            with self.subTest(invocation=invocation):
                controller, pod, entity = strimzi_controllers()
                for spec in (controller["spec"]["template"]["spec"], pod["spec"]):
                    container = spec["containers"][0]
                    container.pop("args")
                    container.update(invocation)
                self.fake.resources["deployments"] += [controller, entity]
                self.fake.resources["pods"] = [pod]
                self.assertEqual(12, len(maintenance.assert_quiescent(deploy, self.documents)))
                del self.fake.resources["deployments"][-2:]

    def test_forged_operator_invocations_fail_deployment_and_pod_quiescence(self):
        launcher = "/opt/strimzi/bin/cluster_operator_run.sh"
        invocations = (
            {"args": ["/tmp/writer.sh"]},
            {"args": [launcher, "--extra"]},
            {"args": [launcher + " --extra"]},
            {"command": ["/bin/sh", "-c"], "args": [launcher]},
            {"command": ["/tmp/writer.sh"], "args": [launcher]},
            {"command": [launcher, "--extra"]},
            {"command": [launcher], "args": ["--extra"]},
            {"command": [launcher], "args": [launcher]},
        )
        for target in ("deployment", "pod"):
            for invocation in invocations:
                with self.subTest(target=target, invocation=invocation):
                    controller, pod, entity = strimzi_controllers()
                    spec = controller["spec"]["template"]["spec"] if target == "deployment" else pod["spec"]
                    container = spec["containers"][0]
                    container.pop("args")
                    container.update(invocation)
                    self.fake.resources["deployments"] += [controller, entity]
                    self.fake.resources["pods"] = [pod]
                    error = "inventory differs" if target == "deployment" else "Pods terminated"
                    with self.assertRaisesRegex(ValueError, error):
                        maintenance.assert_quiescent(deploy, self.documents)
                    del self.fake.resources["deployments"][-2:]

    def test_unknown_renamed_or_spoofed_controller_deployment_is_rejected(self):
        controller, _, _ = strimzi_controllers()
        variants = []
        for path, value in (
                (("metadata", "name"), "unrelated-writer"),
                (("metadata", "labels", "release"), "other"),
                (("spec", "template", "metadata", "labels", "name"), "writer"),
                (("spec", "template", "spec", "serviceAccountName"), "default"),
                (("spec", "template", "spec", "containers", 0, "image"), "example/writer:1"),
                (("spec", "template", "spec", "containers", 0, "envFrom"), [{"secretRef": {"name": "database"}}]),
                (("spec", "template", "spec", "containers", 0, "env"), [{"name": "DATABASE_URL", "value": "placeholder"}]),
                (("spec", "template", "spec", "containers", 0, "command"), ["sh", "-c", "writer"]),
                (("spec", "template", "spec", "containers", 0, "args"), ["writer"]),
                (("spec", "template", "spec", "containers", 0, "env"), [{"name": "STRIMZI_UNREVIEWED", "value": "placeholder"}]),
                (("spec", "template", "spec", "initContainers"), [{"name": "writer", "image": "example/writer:1"}])):
            candidate = copy.deepcopy(controller)
            target = candidate
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            variants.append(candidate)
        sidecar = copy.deepcopy(controller)
        sidecar["spec"]["template"]["spec"]["containers"].append({"name": "writer", "image": "example/writer:1"})
        variants.append(sidecar)
        for candidate in variants:
            with self.subTest(candidate=candidate):
                self.fake.resources["deployments"].append(candidate)
                with self.assertRaisesRegex(ValueError, "inventory differs"):
                    maintenance.assert_quiescent(deploy, self.documents)
                self.fake.resources["deployments"].pop()

    def test_unrelated_spoofed_or_orphan_operator_pods_are_rejected(self):
        controller, pod, _ = strimzi_controllers()
        self.fake.resources["deployments"].append(controller)
        for path, value in (
                (("metadata", "name"), "unrelated-writer"),
                (("metadata", "labels", "strimzi.io/kind"), "writer"),
                (("metadata", "ownerReferences"), []),
                (("metadata", "ownerReferences", 0, "name"), "unrelated-writer-6d7846b9b9"),
                (("metadata", "ownerReferences", 0, "kind"), "Job"),
                (("metadata", "ownerReferences", 0, "controller"), False),
                (("spec", "serviceAccountName"), "default"),
                (("spec", "containers", 0, "image"), "example/writer:1"),
                (("spec", "ephemeralContainers"), [{"name": "writer", "image": "example/writer:1"}])):
            candidate = copy.deepcopy(pod)
            target = candidate
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            self.fake.resources["pods"] = [candidate]
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Pods terminated"):
                maintenance.assert_quiescent(deploy, self.documents)
        self.fake.resources["deployments"].pop()
        self.fake.resources["pods"] = [pod]
        with self.assertRaisesRegex(ValueError, "Pods terminated"):
            maintenance.assert_quiescent(deploy, self.documents)

    def test_cluster_operator_exemption_never_exempts_active_app(self):
        controller, pod, entity = strimzi_controllers()
        self.fake.resources["deployments"] += [controller, entity]
        self.fake.resources["pods"] = [pod]
        for app in self.fake.resources["deployments"][:-2]:
            with self.subTest(app=app["metadata"]["name"]):
                app["spec"]["replicas"] = 1
                with self.assertRaisesRegex(ValueError, "zero replicas"):
                    maintenance.assert_quiescent(deploy, self.documents)
                app["spec"]["replicas"] = 0

    def test_review_is_strict_and_never_uses_compatibility_or_installation_claim(self):
        review = self.fake.review()
        deploy.validate_review(review, SHA)
        for key, value in (("data_loss_accepted", "true"), ("expected_predecessor_release", SHA),
                           ("before_fingerprints", {}), ("after_fingerprints", {}),
                           ("expected_live_images", {"app/main": "repo:latest"}), ("maintenance_test_url", "TODO")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                deploy.validate_review({**review, key: value}, SHA)
        for mode in ("expand-only", "none", "initial-install"):
            with self.assertRaises(ValueError):
                deploy.validate_review({**review, "migration_mode": mode}, SHA)
        with self.assertRaises(ValueError):
            self.perform(bootstrap=True)
        self.assertFalse(self.fake.events)

    def test_success_preserves_predecessor_audit_and_restores_routes_only_after_rollout(self):
        before = copy.deepcopy(self.fake.predecessor)
        self.perform()
        self.assertEqual(before, self.fake.predecessor)
        configs = self.fake.applied("ConfigMap")
        self.assertTrue(any(d["metadata"]["name"] == maintenance.PREFIX + SHA + "-started" for d in configs))
        self.assertTrue(any(d["metadata"]["name"] == deploy.release_name(SHA) for d in configs))
        self.assertFalse(any(d["metadata"]["name"] == deploy.release_name("c" * 40) for d in configs))
        self.assertFalse(self.fake.applied("HorizontalPodAutoscaler"))
        self.assertFalse(self.fake.applied("ScaledObject"))
        events = self.fake.events
        routes = next(i for i, (_, docs) in enumerate(events) if any(d["kind"] == "Ingress" for d in docs))
        ready = [i for i, (args, _) in enumerate(events) if "rollout" in args]
        self.assertTrue(ready and max(ready) < routes)
        for args, docs in events:
            if any(d["metadata"]["name"].endswith("-started") for d in docs):
                self.assertIn("create", args)
        migrations = [d for d in self.fake.applied("Job") if d["metadata"]["name"].endswith("-migration")]
        self.assertEqual(["access-migration", "ai-migration", "document-migration"], [d["metadata"]["name"] for d in migrations])

    def test_wrong_predecessor_live_images_and_before_schema_fail_before_start(self):
        review = self.fake.review()
        for key, value in (("predecessor_record_sha256", "f" * 64),
                           ("before_fingerprints", {s: "f" * 64 for s in maintenance.SERVICES}),
                           ("expected_live_images", {"extra/container": "example/repo@sha256:" + "f" * 64})):
            self.fake.events.clear()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.perform({**review, key: value})
            self.assertFalse(self.fake.applied("Deployment"))
            self.assertFalse(self.fake.applied("ConfigMap"))

    def test_writers_autoscalers_jobs_and_downtime_fail_closed(self):
        cases = [("horizontalpodautoscalers", [{}]), ("cronjobs", [{}]),
                 ("scaledobjects", [{"metadata": {"annotations": {}}}]),
                 ("pods", [{"metadata": {}, "status": {"phase": "Running"}}]),
                 ("jobs", [{"status": {"active": 1}}]), ("targetgroupbindings", [{}])]
        for resource, value in cases:
            with self.subTest(resource=resource):
                old = self.fake.resources[resource]
                self.fake.resources[resource] = value
                with self.assertRaises(ValueError):
                    self.perform()
                self.fake.resources[resource] = old
        self.fake.resources["deployments"][0]["status"]["observedGeneration"] = 1
        with self.assertRaises(ValueError):
            self.perform()
        self.fake.resources["deployments"][0]["status"]["observedGeneration"] = 2
        with patch.object(deploy, "http_status", return_value="200"), self.assertRaises(ValueError):
            self.perform()
        self.fake.resources["ingresses"][0]["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["name"] = "access-svc"
        with self.assertRaises(ValueError):
            self.perform()
        self.assertFalse(self.fake.applied("ConfigMap"))

    def test_failed_migration_and_after_mismatch_record_failure_and_stop_writers(self):
        for failure in ("Job/document-migration", "after", "deployment/converter"):
            with self.subTest(failure=failure):
                self.fake.events.clear()
                self.fake.fail = failure if failure != "after" else None
                review = self.fake.review()
                if failure == "after":
                    review["after_fingerprints"] = {s: "f" * 64 for s in maintenance.SERVICES}
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    self.perform(review)
                records = self.fake.applied("ConfigMap")
                self.assertTrue(any(d["metadata"]["name"].endswith("-failed") for d in records))
                self.assertFalse(any(d["metadata"]["name"] == deploy.release_name(SHA) for d in records))
                patches = [args for args, _ in self.fake.events if "patch" in args]
                self.assertEqual(len(self.fake.resources["deployments"]), len(patches))
                self.assertTrue(self.fake.applied("Ingress"))

    def test_interrupted_attempt_blocks_every_mode_even_if_failed_marker_missing(self):
        self.fake.resources["configmaps"].append(deploy.install_record(maintenance.PREFIX + SHA + "-started", {}))
        for review, kwargs in ((self.fake.review(), {}), (REVIEW, {}), (None, {"rollback": True}),
                              ({**REVIEW, "migration_mode": "none"}, {})):
            with self.subTest(review=review), self.assertRaisesRegex(ValueError, "unfinished maintenance"):
                deploy.deploy(CONFIG, SHA, self.documents, review=review, **kwargs)
        self.assertFalse(self.fake.applied("Deployment"))
        self.assertFalse(self.fake.applied("Job"))

    def test_smoke_failure_and_writer_return_never_record_success(self):
        with patch.object(deploy, "authenticated_smoke", side_effect=ValueError("smoke failed")):
            with self.assertRaisesRegex(ValueError, "smoke failed"):
                self.perform()
        self.assertFalse(any(d["metadata"]["name"] == deploy.release_name(SHA)
                             for d in self.fake.applied("ConfigMap")))
        self.fake.events.clear()
        # The success-path fake removed old target bindings when normal routing was applied.
        self.fake.resources["targetgroupbindings"] = []
        with patch.object(maintenance, "assert_quiescent", side_effect=[
                self.fake.resources["deployments"], self.fake.resources["deployments"], ValueError("writer returned")]):
            with self.assertRaisesRegex(ValueError, "writer returned"):
                self.perform()
        self.assertFalse(any(d["metadata"]["name"].endswith("-migration") for d in self.fake.applied("Job")))
        self.assertTrue(any(d["metadata"]["name"].endswith("-failed") for d in self.fake.applied("ConfigMap")))

    def test_completed_attempt_allows_only_ordinary_deploy_guard_path(self):
        self.fake.resources["configmaps"] += [deploy.install_record(maintenance.PREFIX + SHA + "-started", {}),
                                              deploy.install_record(deploy.release_name(SHA), {})]
        with patch.object(deploy, "_deploy") as ordinary:
            self.perform(REVIEW)
            ordinary.assert_called_once()
        with self.assertRaisesRegex(ValueError, "ordinary same-schema"):
            self.perform()

    def test_db_quiescence_uses_visible_session_identity_and_preserves_tls(self):
        job = deploy.preflight_job("ai", CONFIG, require_quiescent=True)
        container = job["spec"]["template"]["spec"]["containers"][0]
        script = container["command"][2]
        self.assertIn("pid<>pg_backend_pid() AND usename IS NOT NULL", script)
        self.assertNotIn("backend_type=", script)
        self.assertIn({"name": "PGSSLMODE", "value": "verify-full"}, container["env"])
        self.assertIn("Maintenance requires no other DB clients", script)


if __name__ == "__main__":
    unittest.main()
