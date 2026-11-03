import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import aws_waf_access_code as copy_code


class WafAccessCodeTests(unittest.TestCase):
    def test_only_access_code_is_copied_and_bytes_are_preserved(self):
        source = {"ACCESS_CODE": " gate ", "JWT_PRIVATE_KEY": "must-not-copy", "DB_PASSWORD": "also-not"}
        with patch.object(copy_code, "read_secret", side_effect=[("s1", source), ("d1", {"ACCESS_CODE": ""}), ("s1", source)]):
            with patch.object(copy_code, "promote_secret") as promote:
                self.assertTrue(copy_code.sync("r", "source", "dest"))
        promote.assert_called_once_with("r", "dest", "d1", {"ACCESS_CODE": " gate "})

    def test_destination_with_other_credentials_is_rejected(self):
        with patch.object(copy_code, "read_secret", side_effect=[("s", {"ACCESS_CODE": "a"}), ("d", {"ACCESS_CODE": "b", "JWT_PRIVATE_KEY": "key"})]):
            with patch.object(copy_code, "promote_secret") as promote:
                with self.assertRaises(ValueError):
                    copy_code.sync("r", "source", "dest")
                promote.assert_not_called()

    def test_empty_or_nonstring_code_does_not_disable_gate(self):
        for value in (None, "", "  ", 123):
            with self.subTest(value=value):
                with patch.object(copy_code, "read_secret", side_effect=[("s", {"ACCESS_CODE": value}), ("d", {"ACCESS_CODE": "existing"})]):
                    with patch.object(copy_code, "promote_secret") as promote:
                        with self.assertRaises(ValueError):
                            copy_code.sync("r", "source", "dest")
                        promote.assert_not_called()

    def test_same_code_is_idempotent(self):
        with patch.object(copy_code, "read_secret", side_effect=[("s", {"ACCESS_CODE": "a"}), ("d", {"ACCESS_CODE": "a"}), ("s", {})]):
            with patch.object(copy_code, "promote_secret") as promote:
                self.assertFalse(copy_code.sync("r", "source", "dest"))
                promote.assert_not_called()

    def test_concurrent_source_change_requires_reconciliation(self):
        with patch.object(copy_code, "read_secret", side_effect=[("s1", {"ACCESS_CODE": "a"}), ("d", {"ACCESS_CODE": "b"}), ("s2", {})]):
            with patch.object(copy_code, "promote_secret"):
                with self.assertRaisesRegex(RuntimeError, "reconcile"):
                    copy_code.sync("r", "source", "dest")

    def test_terraform_does_not_read_current_app_payload(self):
        terraform = (ROOT / "infra/terraform/cost-guards.tf").read_text()
        self.assertNotIn('"app_current"', terraform)
        self.assertNotIn('secret_id  = aws_secretsmanager_secret.app.id', terraform)
        self.assertIn('secret_id  = aws_secretsmanager_secret.waf_access_code.id', terraform)
        self.assertIn('sha256(local.waf_access_code)', terraform)


if __name__ == "__main__":
    unittest.main()
