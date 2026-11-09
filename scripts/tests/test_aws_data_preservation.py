"""Lossless gates must reject missing backups, changed rows and unreviewed inventories."""
import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aws_data_preservation as preservation
import aws_maintenance as maintenance
from test_aws_deploy import CONFIG, SHA, MANIFEST, deploy
from test_aws_maintenance import MaintenanceCluster


def evidence():
    return {
        "databases": {s: {"tables": [{"name": "records", "columns": ["id", "value"]}], "sha256": "a" * 64}
                      for s in preservation.SERVICES},
        "restored_sha256": {s: "a" * 64 for s in preservation.SERVICES},
        "snapshots": {s: {"id": "lossless-" + s, "created_after": "2026-11-09T00:00:00Z"} for s in ("access", "core")},
        "credit_exemption_cutoff": "2026-11-09T00:00:00Z",
    }


class PreservationTests(unittest.TestCase):
    def test_explicit_false_requires_complete_evidence(self):
        cluster = MaintenanceCluster(deploy.render(CONFIG, SHA, MANIFEST))
        review = cluster.review()
        review["data_loss_accepted"] = False
        with self.assertRaises(ValueError):
            maintenance.validate_maintenance_review(review, SHA)
        review["preservation"] = evidence()
        maintenance.validate_maintenance_review(review, SHA)
        review["data_loss_accepted"] = 0
        with self.assertRaises(ValueError):
            maintenance.validate_maintenance_review(review, SHA)

    def test_incomplete_restore_wrong_inventory_and_injection_rejected(self):
        for mutate in (
            lambda e: e["restored_sha256"].pop("ai"),
            lambda e: e["restored_sha256"].update(ai="b" * 64),
            lambda e: e["databases"]["ai"].update(tables=[]),
            lambda e: e["databases"]["ai"]["tables"][0].update(name='records; DROP TABLE users'),
            lambda e: e["databases"]["ai"]["tables"][0].update(columns=["id", "id"]),
            lambda e: e["snapshots"]["core"].update(created_after="2026-11-09T00:00:00"),
            lambda e: e.update(credit_exemption_cutoff="2026-11-09T00:00:00Z'; --"),
        ):
            e = evidence(); mutate(e)
            with self.assertRaises(ValueError): preservation.validate_preservation(e)

    def test_changed_data_prevents_resume(self):
        with patch.object(preservation, "data_digest", return_value="b" * 64):
            with self.assertRaisesRegex(ValueError, "original data changed"):
                preservation.verify_after(Mock(), CONFIG, evidence())

    def test_before_requires_inventory_but_after_preserves_original_columns(self):
        with patch.object(preservation, "data_digest", return_value="a" * 64) as digest:
            preservation.verify_data(Mock(), CONFIG, evidence(), before=True)
            self.assertTrue(all(c.kwargs["require_inventory"] for c in digest.call_args_list))
            digest.reset_mock()
            preservation.verify_data(Mock(), CONFIG, evidence(), before=False)
            self.assertTrue(all(not c.kwargs["require_inventory"] for c in digest.call_args_list))

    def test_snapshot_target_encryption_completion_and_time_checked(self):
        instance = {"Endpoint": {"Address": "db.example.com"}, "DBInstanceIdentifier": "db", "DbiResourceId": "resource-1"}
        snapshot = {"Status": "available", "SnapshotType": "manual", "Encrypted": True,
                    "DBInstanceIdentifier": "db", "DbiResourceId": "resource-1", "SnapshotCreateTime": "2026-11-09T01:00:00Z"}
        config = {"access_rds_endpoint": "db.example.com", "core_rds_endpoint": "db.example.com"}
        def api_for(s):
            return SimpleNamespace(run=Mock(side_effect=[json.dumps({"DBInstances": [instance]}),
                json.dumps({"DBSnapshots": [s]}), json.dumps({"DBSnapshots": [s]})]))
        preservation.verify_snapshots(api_for(snapshot), config, evidence()["snapshots"])
        for key, value in [("Status", "creating"), ("Encrypted", False), ("DbiResourceId", "other"),
                           ("SnapshotType", "automated"), ("SnapshotCreateTime", "2026-11-08T00:00:00Z")]:
            bad = {**snapshot, key: value}
            with self.assertRaises(ValueError):
                preservation.verify_snapshots(api_for(bad), config, evidence()["snapshots"])

    def test_snapshot_failure_prevents_data_jobs(self):
        with patch.object(preservation, "verify_snapshots", side_effect=ValueError("missing backup")), \
             patch.object(preservation, "verify_data") as data:
            with self.assertRaises(ValueError): preservation.verify_before(Mock(), CONFIG, evidence())
            data.assert_not_called()

    def test_generated_job_keeps_tls_ownership_and_quiescence(self):
        api = SimpleNamespace(preflight_job=deploy.preflight_job, job=Mock(), kubectl=Mock(return_value="a" * 64))
        preservation.data_digest(api, CONFIG, "ai", evidence()["databases"]["ai"], require_inventory=True)
        job = api.job.call_args.args[0]
        c = job["spec"]["template"]["spec"]["containers"][0]
        self.assertIn({"name": "PGSSLMODE", "value": "verify-full"}, c["env"])
        self.assertIn("DB ownership gate failed", c["command"][2])
        self.assertIn("Maintenance requires no other DB clients", c["command"][2])
        self.assertIn("preserved inventory differs", c["command"][2])
        self.assertNotIn("pg_dump", c["command"][2])

    def test_credit_job_keeps_csv_and_credentials_in_pod_and_checks_balances(self):
        api = SimpleNamespace(preflight_job=deploy.preflight_job, job=Mock(), kubectl=Mock(return_value="credit exemptions verified"))
        preservation.prepare_credit_exemptions(api, CONFIG, evidence())
        job = api.job.call_args.args[0]
        c = job["spec"]["template"]["spec"]["containers"][0]
        self.assertIn("ACCESS_MIGRATION_CREDENTIAL", [e["name"] for e in c["env"]])
        script = c["command"][2]
        self.assertIn("a.balance IS DISTINCT FROM b.balance", script)
        self.assertIn("a.reserved IS DISTINCT FROM b.reserved", script)
        self.assertIn("credit cutoff does not include every existing member", script)
        self.assertIn("trap 'rm -f /tmp/existing-credit-users.csv' EXIT", script)
        self.assertNotIn("cat /tmp/existing-credit-users.csv", script)


class LosslessOrderingTests(unittest.TestCase):
    def setUp(self):
        self.documents = deploy.render(CONFIG, SHA, MANIFEST)
        self.fake = MaintenanceCluster(self.documents)
        for target, kwargs in (("run", {"side_effect": self.fake.run}), ("smoke_settings", {"return_value": {}}),
                               ("authenticated_smoke", {}), ("http_status", {"return_value": "503"}), ("check_public_routes", {})):
            m = patch.object(deploy, target, **kwargs); m.start(); self.addCleanup(m.stop)
        self.review = self.fake.review()
        self.review.update(data_loss_accepted=False, preservation=evidence())

    def test_failed_preservation_never_starts_workloads(self):
        with patch.object(preservation, "verify_before"), \
             patch.object(preservation, "verify_after", side_effect=ValueError("data changed")), \
             patch.object(preservation, "prepare_credit_exemptions") as credit, \
             patch.object(deploy, "complete_rollout") as rollout:
            with self.assertRaisesRegex(ValueError, "data changed"):
                deploy.deploy(CONFIG, SHA, self.documents, review=self.review)
            credit.assert_not_called(); rollout.assert_not_called()

    def test_order_is_preservation_then_credit_then_resume(self):
        events = []
        with patch.object(preservation, "verify_before", side_effect=lambda *a: events.append("before")), \
             patch.object(preservation, "verify_after", side_effect=lambda *a: events.append("after")), \
             patch.object(preservation, "prepare_credit_exemptions", side_effect=lambda *a: events.append("credit")), \
             patch.object(deploy, "complete_rollout", side_effect=lambda *a, **k: events.append("resume")):
            deploy.deploy(CONFIG, SHA, self.documents, review=self.review)
        self.assertEqual(events, ["before", "after", "credit", "resume"])

    def test_credit_failure_never_resumes(self):
        with patch.object(preservation, "verify_before"), patch.object(preservation, "verify_after"), \
             patch.object(preservation, "prepare_credit_exemptions", side_effect=ValueError("credit failed")), \
             patch.object(deploy, "complete_rollout") as rollout:
            with self.assertRaisesRegex(ValueError, "credit failed"):
                deploy.deploy(CONFIG, SHA, self.documents, review=self.review)
            rollout.assert_not_called()


if __name__ == "__main__":
    unittest.main()
