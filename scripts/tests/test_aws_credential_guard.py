import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

path = Path(__file__).resolve().parents[2] / "infra/lambda/credential_guard/handler.py"
spec = importlib.util.spec_from_file_location("credential_guard", path)
guard = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"boto3": types.SimpleNamespace()}):
    spec.loader.exec_module(guard)


class CredentialGuardTests(unittest.TestCase):
    def test_credentialless_root_is_not_reported_as_unprotected(self):
        now = datetime.now(timezone.utc)
        values = guard.measurements({}, [], [], {"CreatedDate": now}, now)
        self.assertEqual(values["RootCredentialsUnprotected"], 0)
        self.assertEqual(values["HumanMfaMissing"], 1)

    def test_root_password_requires_mfa_and_root_keys_always_raise(self):
        now = datetime.now(timezone.utc)
        for summary, expected in [({"AccountPasswordPresent": 1}, 1),
                                  ({"AccountPasswordPresent": 1, "AccountMFAEnabled": 1}, 0),
                                  ({"AccountAccessKeysPresent": 1, "AccountMFAEnabled": 1}, 1)]:
            self.assertEqual(guard.measurements(summary, [1], [], {"CreatedDate": now}, now)["RootCredentialsUnprotected"], expected)

    def test_unrelated_secret_updates_do_not_reset_password_age(self):
        now = datetime.now(timezone.utc)
        secret = {"CreatedDate": now - timedelta(days=100), "LastChangedDate": now}
        self.assertEqual(guard.measurements({}, [1], [], secret, now)["DbCredentialAgeDays"], 100)
        secret["Tags"] = [{"Key": "fruition:jwt-signing-key-rotated-at", "Value": now.isoformat()}]
        values = guard.measurements({}, [1], [{"PolicyName": "AdministratorAccess"}], secret, now)
        self.assertEqual(values["JwtSigningKeyAgeDays"], 0)
        self.assertEqual(values["DbCredentialAgeDays"], 100)
        self.assertEqual(values["HumanDirectAdministratorAccess"], 1)

    def test_invalid_or_future_rotation_evidence_fails_closed(self):
        now = datetime.now(timezone.utc)
        for value in ["invalid", "2099-01-01T00:00:00Z", "2026-01-01T00:00:00"]:
            self.assertEqual(guard.age_days({"tag": value}, "tag", now, now), 10000)

    def test_missing_creation_date_fails_closed(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(guard.age_days({}, "tag", None, now), 10000)

    def test_signing_certificate_is_a_root_credential_even_with_mfa(self):
        now = datetime.now(timezone.utc)
        values = guard.measurements({"AccountSigningCertificatesPresent": 1, "AccountMFAEnabled": 1},
                                    [1], [], {"CreatedDate": now}, now)
        self.assertEqual(values["RootCredentialsUnprotected"], 1)

    def test_handler_reads_all_pages_and_only_secret_metadata(self):
        now = datetime.now(timezone.utc)
        iam, secret_client, cloudwatch = Mock(), Mock(), Mock()
        iam.get_account_summary.return_value = {"SummaryMap": {}}
        mfa_pages, policy_pages = Mock(), Mock()
        mfa_pages.paginate.return_value = [{"MFADevices": []}, {"MFADevices": [{"SerialNumber": "device"}]}]
        policy_pages.paginate.return_value = [{"AttachedPolicies": [{"PolicyName": "Other"}]},
                                              {"AttachedPolicies": [{"PolicyName": "AdministratorAccess"}]}]
        iam.get_paginator.side_effect = lambda name: {"list_mfa_devices": mfa_pages,
                                                       "list_attached_user_policies": policy_pages}[name]
        secret_client.describe_secret.return_value = {"CreatedDate": now}
        clients = {"iam": iam, "secretsmanager": secret_client, "cloudwatch": cloudwatch}
        with patch.object(guard, "boto3", types.SimpleNamespace(client=lambda name: clients[name])):
            with patch.dict(guard.os.environ, {"OPERATOR_USER": "operator", "APP_SECRET_ARN": "app-secret", "PROJECT": "test"}):
                self.assertEqual(guard.handler({}, None), {"metrics_published": 6})
        mfa_pages.paginate.assert_called_once_with(UserName="operator")
        policy_pages.paginate.assert_called_once_with(UserName="operator")
        secret_client.describe_secret.assert_called_once_with(SecretId="app-secret")
        secret_client.get_secret_value.assert_not_called()
        metrics = {item["MetricName"]: item["Value"] for item in cloudwatch.put_metric_data.call_args.kwargs["MetricData"]}
        self.assertEqual(metrics["HumanMfaMissing"], 0)
        self.assertEqual(metrics["HumanDirectAdministratorAccess"], 1)
        self.assertEqual(metrics["CredentialAuditHeartbeat"], 1)

    def test_failed_audit_does_not_publish_a_healthy_heartbeat(self):
        iam, cloudwatch = Mock(), Mock()
        iam.get_account_summary.side_effect = RuntimeError("AWS unavailable")
        clients = {"iam": iam, "cloudwatch": cloudwatch}
        with patch.object(guard, "boto3", types.SimpleNamespace(client=lambda name: clients[name])):
            with patch.dict(guard.os.environ, {"OPERATOR_USER": "operator"}):
                with self.assertRaisesRegex(RuntimeError, "AWS unavailable"):
                    guard.handler({}, None)
        cloudwatch.put_metric_data.assert_not_called()

    def test_guard_policy_cannot_read_secret_values(self):
        terraform = (path.parents[2] / "terraform/credential-guard.tf").read_text()
        self.assertIn("secretsmanager:DescribeSecret", terraform)
        self.assertNotIn("GetSecretValue", terraform)
        self.assertNotIn("kms:Decrypt", terraform)

    def test_missing_samples_only_page_on_heartbeat_with_jitter_tolerance(self):
        terraform = (path.parents[2] / "terraform/credential-guard.tf").read_text()
        self.assertIn('each.key == "CredentialAuditHeartbeat" ? 2 : 1', terraform)
        self.assertIn('each.key == "CredentialAuditHeartbeat" ? "breaching" : "ignore"', terraform)


if __name__ == "__main__":
    unittest.main()
