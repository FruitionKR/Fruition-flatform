"""MCP OAuth loopback redirect_uri의 WAF 예외 경계. 실제 WAF 판정은 운영 탐침으로 확인한다."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "infra/waf/oauth-loopback-redirect.json").read_text())
TERRAFORM = (ROOT / "infra/terraform/cost-guards.tf").read_text()


def exempt(method, path):
    # WAF는 메서드·URI 경로를 변환 없이 EXACTLY로 비교한다.
    return any(r["method"] == method and r["path"] == path for r in POLICY["routes"].values())


def rule_block(name):
    start = TERRAFORM.index(f'name     = "{name}"')
    return TERRAFORM[start:TERRAFORM.index("visibility_config", start)]


class WafOAuthLoopbackRedirectTests(unittest.TestCase):
    def test_only_generic_rfi_query_and_body_are_counted(self):
        self.assertEqual(
            {"AWSManagedRulesCommonRuleSet": {
                "GenericRFI_QUERYARGUMENTS": "awswaf:managed:aws:core-rule-set:GenericRFI_QueryArguments",
                "GenericRFI_BODY": "awswaf:managed:aws:core-rule-set:GenericRFI_Body"}},
            POLICY["managed_rule_overrides"])
        self.assertIn("lookup(local.waf_oauth_loopback_redirect.managed_rule_overrides, rule.value, {})", TERRAFORM)

    def test_only_three_exact_method_path_pairs_are_exempt(self):
        self.assertEqual({("GET", "/oauth2/authorize"), ("GET", "/mcp/authorize"), ("POST", "/oauth2/token")},
                         {(r["method"], r["path"]) for r in POLICY["routes"].values()})
        for method, path in [("POST", "/oauth2/authorize"), ("GET", "/oauth2/token"), ("POST", "/mcp/authorize"),
                             ("GET", "/oauth2/authorize/"), ("GET", "/mcp/authorize/x"), ("POST", "/oauth2/token/"),
                             ("POST", "/oauth2/authorize/9f1c2d3e-4b5a-4c6d-8e7f-0a1b2c3d4e5f"),
                             ("GET", "/oauth2/authorization/google"), ("GET", "/login/oauth2/code/kakao"),
                             ("POST", "/mcp"), ("GET", "/api/mcp-endpoint"), ("GET", "/OAUTH2/authorize"),
                             ("GET", "/oauth2/../oauth2/authorize")]:
            self.assertFalse(exempt(method, path), (method, path))

    def test_contract_matches_method_path_and_app_host_exactly(self):
        rule = rule_block("oauth-loopback-redirect-contract")
        self.assertIn("count {}", rule)
        self.assertNotIn("allow", rule)
        self.assertIn('rule_label { name = "fruition:oauth-loopback-redirect" }', rule)
        self.assertIn("for_each = local.waf_oauth_loopback_redirect.routes", rule)
        self.assertIn('for_each = var.app_domain != "" ? [var.app_domain] : []', rule)
        self.assertIn('single_header { name = "host" }', rule)
        self.assertEqual(3, rule.count('positional_constraint = "EXACTLY"'))
        self.assertIn("search_string         = statement.value.method", rule)
        self.assertIn("search_string         = statement.value.path", rule)
        self.assertNotIn("regex", rule)

    def test_guard_blocks_rfi_labels_outside_contract_after_managed_groups(self):
        rule = rule_block("oauth-loopback-redirect-guard")
        self.assertIn("block {}", rule)
        self.assertIn("values(rules)]))", rule)
        self.assertIn("local.waf_oauth_loopback_redirect.managed_rule_overrides", rule)
        self.assertIn('key   = "fruition:oauth-loopback-redirect"', rule)
        self.assertIn("not_statement", rule)
        priority = int(re.search(r"priority = (\d+)", rule).group(1))
        contract = int(re.search(r"priority = (\d+)", rule_block("oauth-loopback-redirect-contract")).group(1))
        self.assertLess(contract, 10)  # 관리형 규칙(10-13)보다 먼저 라벨을 붙인다.
        self.assertGreater(priority, 13)

    def test_document_body_guard_does_not_absorb_rfi_labels(self):
        body_overrides = TERRAFORM[TERRAFORM.index("waf_content_body_overrides = {"):]
        body_overrides = body_overrides[:body_overrides.index("\n  }\n")]
        self.assertNotIn("GenericRFI", body_overrides)


if __name__ == "__main__":
    unittest.main()
