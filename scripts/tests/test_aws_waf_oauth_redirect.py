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
                "GenericRFI_BODY": "awswaf:managed:aws:core-rule-set:GenericRFI_Body",
                # 루프백 호스트(localhost, 127.0.0.1, [::1])는 SSRF 규칙이 먼저 잡는다(2026-11-11 WAF 로그 확인).
                "EC2MetaDataSSRF_QUERYARGUMENTS": "awswaf:managed:aws:core-rule-set:EC2MetaDataSSRF_QueryArguments",
                "EC2MetaDataSSRF_BODY": "awswaf:managed:aws:core-rule-set:EC2MetaDataSSRF_Body"}},
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
        self.assertIn("for_each = toset(local.waf_rfi_ssrf_oauth_only_labels)", rule)
        self.assertIn('key   = "fruition:oauth-loopback-redirect"', rule)
        self.assertNotIn("fruition:document-content", rule)
        self.assertIn("not_statement", rule)
        priority = int(re.search(r"priority = (\d+)", rule).group(1))
        contract = int(re.search(r"priority = (\d+)", rule_block("oauth-loopback-redirect-contract")).group(1))
        self.assertLess(contract, 10)  # 관리형 규칙(10-13)보다 먼저 라벨을 붙인다.
        self.assertGreater(priority, 13)

    def test_only_rfi_ssrf_body_rules_are_also_tolerated_on_document_contracts(self):
        # 문서 본문의 http://localhost:3000, http://127.0.0.1:8080 같은 예문은 BODY 규칙만 잡는다.
        self.assertEqual(["GenericRFI_BODY", "EC2MetaDataSSRF_BODY"], POLICY["document_content_body_rules"])
        common = POLICY["managed_rule_overrides"]["AWSManagedRulesCommonRuleSet"]
        self.assertTrue(set(POLICY["document_content_body_rules"]) <= set(common))
        self.assertIn("waf_rfi_ssrf_document_body_labels = [for name in local.waf_oauth_loopback_redirect.document_content_body_rules", TERRAFORM)
        self.assertIn("label if !contains(local.waf_oauth_loopback_redirect.document_content_body_rules, name)", TERRAFORM)
        rule = rule_block("rfi-ssrf-body-guard")
        self.assertIn("block {}", rule)
        self.assertIn("for_each = toset(local.waf_rfi_ssrf_document_body_labels)", rule)
        self.assertEqual(2, rule.count("not_statement"))
        self.assertIn('key   = "fruition:oauth-loopback-redirect"', rule)
        self.assertIn('key   = "fruition:document-content"', rule)
        self.assertGreater(int(re.search(r"priority = (\d+)", rule).group(1)), 13)

    def test_rfi_ssrf_decision_table(self):
        common = POLICY["managed_rule_overrides"]["AWSManagedRulesCommonRuleSet"]
        body = {common[n] for n in POLICY["document_content_body_rules"]}
        oauth_only = set(common.values()) - body
        self.assertEqual({common["GenericRFI_QUERYARGUMENTS"], common["EC2MetaDataSSRF_QUERYARGUMENTS"]}, oauth_only)

        def blocked(label, oauth=False, document=False):
            # oauth-loopback-redirect-guard(21) 다음 rfi-ssrf-body-guard(22)를 그대로 옮긴 판정.
            if label in oauth_only and not oauth:
                return True
            return label in body and not oauth and not document

        for label in common.values():
            self.assertFalse(blocked(label, oauth=True), label)
            self.assertTrue(blocked(label), label)
        for label in body:
            self.assertFalse(blocked(label, document=True), label)
        for label in oauth_only:
            self.assertTrue(blocked(label, document=True), label)  # 문서 경로라도 쿼리 인자는 그대로 차단한다.

    def test_document_body_guard_does_not_absorb_rfi_labels(self):
        body_overrides = TERRAFORM[TERRAFORM.index("waf_content_body_overrides = {"):]
        body_overrides = body_overrides[:body_overrides.index("\n  }\n")]
        self.assertNotIn("GenericRFI", body_overrides)


if __name__ == "__main__":
    unittest.main()
