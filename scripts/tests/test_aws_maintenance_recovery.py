import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

import yaml
from test_aws_maintenance import MaintenanceCluster, maintenance, deploy, CONFIG, SHA, MANIFEST


class HttpRetryTests(unittest.TestCase):
    def test_real_curl_retries_503_then_200_and_removes_response_file(self):
        class Handler(BaseHTTPRequestHandler):
            calls = 0

            def do_GET(self):
                Handler.calls += 1
                self.send_response(503 if Handler.calls == 1 else 200)
                self.end_headers()
                self.wfile.write(b"private response")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        original = deploy.run
        paths = []

        def run(args, **kwargs):
            paths.append(Path(args[args.index("--output") + 1]))
            return original(args, **kwargs)

        try:
            with patch.object(deploy, "run", side_effect=run):
                result = deploy.http_status(f"http://127.0.0.1:{server.server_port}/", "--retry", "1", "--retry-delay", "1")
            self.assertEqual("200", result)
            self.assertEqual(2, Handler.calls)
            self.assertTrue(paths and all(not p.exists() and not p.parent.exists() for p in paths))
        finally:
            server.shutdown()
            worker.join()
            server.server_close()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.documents = deploy.render(CONFIG, SHA, MANIFEST)
        self.fake = MaintenanceCluster(self.documents)
        self.review = self.fake.review()
        self.prefix = maintenance.PREFIX + SHA
        self.started = deploy.install_record(self.prefix + "-started", {
            "config": maintenance.canonical(CONFIG), "review": maintenance.canonical(self.review),
            "manifest": yaml.safe_dump_all(self.documents, sort_keys=False),
            "predecessor_record": maintenance.canonical(self.fake.predecessor["data"])})
        self.failed = deploy.install_record(self.prefix + "-failed", {"state": "operator-recovery-required", "containment": "requested"})
        self.fake.resources["configmaps"] += [self.started, self.failed]
        for d in self.fake.resources["deployments"]:
            target = next(t for t in self.documents if t["kind"] == "Deployment" and t["metadata"]["name"] == d["metadata"]["name"])
            d["spec"]["template"] = copy.deepcopy(target["spec"]["template"])
        self.fake.resources["jobs"] = copy.deepcopy([d for d in self.documents if d["kind"] == "Job"])
        for job in self.fake.resources["jobs"]:
            job["status"] = {"succeeded": 1}
        self.plan = {"release_sha": SHA, "mode": "complete-after-migrations",
            "started_data_sha256": maintenance.digest(self.started["data"]),
            "failed_data_sha256": maintenance.digest(self.failed["data"]),
            "incident_url": "https://github.com/FruitionKR/Fruition-flatform/actions/runs/1"}
        for name, kwargs in (("run", {"side_effect": self.fake.run}), ("smoke_settings", {"return_value": {}}),
                             ("http_status", {"return_value": "503"}), ("check_public_routes", {}), ("authenticated_smoke", {})):
            mock = patch.object(deploy, name, **kwargs)
            mock.start()
            self.addCleanup(mock.stop)

    def recover(self):
        maintenance.complete_migrated_release(deploy, CONFIG, SHA, self.documents, review=self.review, plan=self.plan)

    def test_completion_preserves_audit_never_migrates_and_waits_for_smoke(self):
        before = copy.deepcopy(self.fake.resources["configmaps"])
        self.recover()
        self.assertEqual(before, self.fake.resources["configmaps"])
        self.assertFalse(any(d["metadata"]["name"].endswith("-migration") for d in self.fake.applied("Job")))
        self.assertFalse(self.fake.applied("HorizontalPodAutoscaler"))
        self.assertTrue(any(d["metadata"]["name"] == self.prefix + "-recovery-started" for d in self.fake.applied("ConfigMap")))
        self.assertTrue(any(d["metadata"]["name"] == deploy.release_name(SHA) for d in self.fake.applied("ConfigMap")))
        deploy.authenticated_smoke.assert_called_once()

    def test_rejects_changed_or_unreviewed_audit_before_mutation(self):
        self.plan["started_data_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.recover()
        self.assertFalse(self.fake.applied("ConfigMap"))
        self.assertFalse(self.fake.applied("Deployment"))

    def test_rejects_changed_target_manifest(self):
        self.documents[0]["metadata"]["labels"] = {"changed": "true"}
        with self.assertRaises(ValueError):
            self.recover()
        self.assertFalse(self.fake.applied("ConfigMap"))

    def test_rejects_partial_schema_without_migration_or_rollout(self):
        self.fake.fingerprint = "f" * 64
        with self.assertRaises(ValueError):
            self.recover()
        self.assertFalse(self.fake.applied("Deployment"))
        self.assertFalse(self.fake.applied("ConfigMap"))

    def test_rejects_missing_or_failed_migration_job(self):
        self.fake.resources["jobs"][0]["status"] = {"failed": 1}
        with self.assertRaises(ValueError):
            self.recover()
        self.assertFalse(self.fake.applied("ConfigMap"))

    def test_rejects_active_writer(self):
        self.fake.resources["deployments"][0]["spec"]["replicas"] = 1
        with self.assertRaises(ValueError):
            self.recover()

    def test_does_not_repeat_an_interrupted_recovery(self):
        self.fake.resources["configmaps"].append(deploy.install_record(self.prefix + "-recovery-started", {}))
        with self.assertRaises(ValueError):
            self.recover()
        with self.assertRaises(ValueError):
            deploy.deploy(CONFIG, SHA, self.documents, review=self.review)

    def test_failure_contains_apps_and_does_not_record_success(self):
        with patch.object(deploy, "authenticated_smoke", side_effect=ValueError("smoke failed")):
            with self.assertRaises(ValueError):
                self.recover()
        records = self.fake.applied("ConfigMap")
        self.assertTrue(any(d["metadata"]["name"] == self.prefix + "-recovery-failed" for d in records))
        self.assertFalse(any(d["metadata"]["name"] == deploy.release_name(SHA) for d in records))
        self.assertEqual(12, sum("patch" in args for args, _ in self.fake.events))

    def test_successful_recovery_does_not_lock_future_ordinary_deploys(self):
        self.fake.resources["configmaps"] += [
            deploy.install_record(self.prefix + "-recovery-started", {}),
            deploy.install_record(deploy.release_name(SHA), {})]
        ordinary = {"release_sha": SHA, "migration_mode": "none",
            "compatibility_test_url": self.plan["incident_url"], "restore_test_url": self.plan["incident_url"]}
        with patch.object(deploy, "_deploy") as continuation:
            deploy.deploy(CONFIG, SHA, self.documents, review=ordinary)
        continuation.assert_called_once()
