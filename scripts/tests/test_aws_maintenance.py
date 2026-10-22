"""Maintenance regression: existing guards, offline transition, and partial failure."""
import copy
import json
import subprocess
import unittest
from unittest.mock import patch

from test_aws_deploy import CONFIG, SHA, MANIFEST, REVIEW, FakeCluster, deploy
import aws_maintenance as maintenance


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
