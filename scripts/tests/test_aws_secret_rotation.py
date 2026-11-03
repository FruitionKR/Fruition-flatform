"""Credential lifecycle failures must neither expose values nor repeat a promotion."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import aws_secret_tools as secrets
import aws_jwt_keys as keys


class SecretTransportTests(unittest.TestCase):
    def test_payload_uses_private_file_and_is_removed(self):
        observed = []

        def run(command, **kwargs):
            path = Path(command[-1].removeprefix("file://"))
            observed.append(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(json.loads(path.read_text()), {"SecretString": "sensitive"})
            self.assertNotIn("sensitive", " ".join(command))
            return subprocess.CompletedProcess(command, 0, "{}", "")

        with patch.object(secrets.subprocess, "run", side_effect=run):
            secrets.aws("region", "secretsmanager", "put-secret-value", payload={"SecretString": "sensitive"})
        self.assertFalse(observed[0].exists())

    def test_provider_error_never_echoes_sensitive_stderr(self):
        result = subprocess.CompletedProcess([], 1, "", "sensitive-connection-string")
        with patch.object(secrets.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as caught:
                secrets.aws("region", "secretsmanager", "get-secret-value")
        self.assertNotIn("sensitive", str(caught.exception))

    def test_compare_and_swap_preserves_expected_version(self):
        with patch.object(secrets, "aws", return_value={}) as aws:
            token = secrets.promote_secret("region", "secret", "original", {"key": "value"})
        stage = aws.call_args_list[0].kwargs["payload"]["VersionStages"][0]
        self.assertNotEqual(stage, "AWSCURRENT")
        promotion = aws.call_args_list[1].kwargs["payload"]
        self.assertEqual(promotion["RemoveFromVersionId"], "original")
        self.assertEqual(promotion["MoveToVersionId"], token)

    def test_conflict_does_not_retry_or_overwrite_newer_version(self):
        with patch.object(secrets, "aws", side_effect=[{}, RuntimeError("conflict"), {}]) as aws:
            with patch.object(secrets, "read_secret", return_value=("concurrent", {})):
                with self.assertRaisesRegex(RuntimeError, "reconcile"):
                    secrets.promote_secret("region", "secret", "original", {})
        self.assertEqual(aws.call_count, 3)
        self.assertNotEqual(aws.call_args.kwargs["payload"]["VersionStage"], "AWSCURRENT")

    def test_lost_success_response_is_reconciled(self):
        with patch.object(secrets.uuid, "uuid4", return_value="new-version"):
            with patch.object(secrets, "aws", side_effect=[{}, RuntimeError("timeout"), {}]):
                with patch.object(secrets, "read_secret", return_value=("new-version", {})):
                    self.assertEqual(secrets.promote_secret("r", "s", "old", {}), "new-version")

    def test_cleanup_failure_is_not_reported_as_failed_promotion(self):
        with patch.object(secrets, "aws", side_effect=[{}, {}, RuntimeError("cleanup")]):
            with self.assertWarnsRegex(RuntimeWarning, "label cleanup"):
                self.assertTrue(secrets.promote_secret("region", "secret", "original", {}))


class JwtLifecycleTests(unittest.TestCase):
    def test_initial_stage_preserves_hmac_and_unrelated_credentials(self):
        data = {"JWT_SECRET": "legacy", "OTHER": "keep"}
        with patch.object(keys, "rsa_pair", return_value=("private", "public")):
            self.assertTrue(keys.stage(data))
        self.assertEqual(data["JWT_SECRET"], "legacy")
        self.assertEqual(data["OTHER"], "keep")
        self.assertEqual(data["JWT_PREVIOUS_PUBLIC_KEY"], "")

    def test_stage_is_idempotent(self):
        data = {"JWT_PRIVATE_KEY": "private", "JWT_PUBLIC_KEY": "public", "JWT_KEY_ID": "id"}
        with patch.object(keys, "rsa_pair") as generate:
            self.assertFalse(keys.stage(data))
            generate.assert_not_called()

    def test_incomplete_key_set_fails_without_replacement(self):
        with patch.object(keys, "rsa_pair") as generate:
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                keys.stage({"JWT_PRIVATE_KEY": "private"})
            generate.assert_not_called()

    def test_rotation_preserves_previous_public_key_but_not_private_key(self):
        data = {"JWT_PRIVATE_KEY": "old-private", "JWT_PUBLIC_KEY": "old-public", "JWT_KEY_ID": "old-id"}
        with patch.object(keys, "rsa_pair", return_value=("new-private", "new-public")):
            keys.stage(data, rotate=True)
        self.assertEqual(data["JWT_PREVIOUS_PUBLIC_KEY"], "old-public")
        self.assertEqual(data["JWT_PREVIOUS_KEY_ID"], "old-id")
        self.assertNotIn("old-private", data.values())

    def test_rotation_refuses_to_discard_unretired_verification_key(self):
        data = {"JWT_PRIVATE_KEY": "private", "JWT_PUBLIC_KEY": "public", "JWT_KEY_ID": "id",
                "JWT_PREVIOUS_PUBLIC_KEY": "previous"}
        with self.assertRaisesRegex(ValueError, "explicitly retired"):
            keys.stage(data, rotate=True)

    def test_retirement_requires_explicit_consumer_confirmation(self):
        with patch.object(sys, "argv", ["aws_jwt_keys.py", "retire-hmac"]):
            with patch.object(keys, "read_secret", return_value=("v", {})):
                with patch.object(keys, "promote_secret") as promote:
                    with self.assertRaisesRegex(ValueError, "verified RSA consumers"):
                        keys.main()
                    promote.assert_not_called()


if __name__ == "__main__":
    unittest.main()
