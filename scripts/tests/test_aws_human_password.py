"""Evaluate the checked-in policy's self-service boundaries, including legacy Allow.

This small evaluator covers only the Action/NotAction/Resource/NotResource forms
used by this policy. It is not a substitute for AWS IAM simulation before rollout.
"""
import fnmatch
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
OWN = "arn:aws:iam::123456789012:user/operator"
OTHER = "arn:aws:iam::123456789012:user/other"
ROLE = "arn:aws:iam::123456789012:role/fruition-human-admin"


def statements():
    source = (ROOT / "infra/terraform/human-access.tf").read_text()
    source = source.split('resource "aws_iam_user_policy" "human_mfa_only"')[1]
    result = []
    for sid, body in re.findall(r'\{\s*Sid\s*=\s*"([^"]+)"(.*?)\n\s*\}', source, re.S):
        entry = {"Sid": sid}
        for key, raw in re.findall(r'(Effect|NotAction|Action|NotResource|Resource)\s*=\s*(\[[^\]]*\]|"[^"]*"|[^\s\n]+)', body, re.S):
            references = {"local.human_operator_arn": OWN, "aws_iam_role.human_admin[0].arn": ROLE}
            entry[key] = references[raw] if raw in references else json.loads(raw)
        result.append(entry)
    return result


def matches(patterns, value):
    patterns = [patterns] if isinstance(patterns, str) else patterns
    return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)


def evaluate(policy, action, resource):
    decision = "implicitDeny"
    for statement in policy:
        action_applies = matches(statement["Action"], action) if "Action" in statement else not matches(statement["NotAction"], action)
        resource_applies = matches(statement["Resource"], resource) if "Resource" in statement else not matches(statement["NotResource"], resource)
        if action_applies and resource_applies:
            if statement["Effect"] == "Deny":
                return "explicitDeny"
            decision = "allowed"
    return decision


class HumanPasswordPolicyTests(unittest.TestCase):
    def test_self_password_change_and_requirements_are_allowed(self):
        policy = statements()
        self.assertGreater(len(policy), 5)
        self.assertEqual(evaluate(policy, "iam:ChangePassword", OWN), "allowed")
        self.assertEqual(evaluate(policy, "iam:GetAccountPasswordPolicy", "*"), "allowed")

    def test_other_user_password_changes_remain_denied_with_legacy_admin(self):
        policy = statements() + [{"Effect": "Allow", "Action": "*", "Resource": "*"}]
        self.assertEqual(evaluate(policy, "iam:ChangePassword", OTHER), "explicitDeny")
        self.assertEqual(evaluate(policy, "iam:ChangePassword", OWN), "allowed")

    def test_password_reset_and_account_policy_changes_remain_denied(self):
        policy = statements() + [{"Effect": "Allow", "Action": "*", "Resource": "*"}]
        for action in ["iam:UpdateLoginProfile", "iam:CreateLoginProfile", "iam:DeleteLoginProfile",
                       "iam:UpdateAccountPasswordPolicy", "iam:DeleteAccountPasswordPolicy",
                       "iam:CreateAccessKey", "iam:DeactivateMFADevice", "iam:AttachUserPolicy",
                       "secretsmanager:GetSecretValue", "s3:GetObject"]:
            for resource in (OWN, OTHER, "*"):
                with self.subTest(action=action, resource=resource):
                    self.assertEqual(evaluate(policy, action, resource), "explicitDeny")

    def test_role_routing_still_denies_other_roles(self):
        policy = statements() + [{"Effect": "Allow", "Action": "*", "Resource": "*"}]
        self.assertEqual(evaluate(policy, "sts:AssumeRole", ROLE), "allowed")
        self.assertEqual(evaluate(policy, "sts:AssumeRole", ROLE + "-other"), "explicitDeny")


if __name__ == "__main__":
    unittest.main()
