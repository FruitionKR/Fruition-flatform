import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("waf_probe", ROOT / "scripts/aws_waf_content_probe.py")
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)
CONTRACTS = json.loads((ROOT / "infra/waf/document-content-contracts.json").read_text())


def matches(method, path, content_type):
    return any(c["method"] == method and re.search(c["path_regex"], path)
               and re.search(c["content_type_regex"], content_type.lower()) for c in CONTRACTS.values())


class WafContentTests(unittest.TestCase):
    def test_all_live_probe_routes_match_only_their_intended_contract(self):
        for name, method, path, kind, text, expected in PROBE.cases():
            with self.subTest(name=name):
                ct, _ = PROBE.body(kind, text)
                # The query-XSS negative control intentionally has the correct
                # body contract; the independent managed query rule must block.
                if name == "control-query-xss":
                    self.assertTrue(matches(method, path.split("?")[0], ct))
                else:
                    self.assertEqual(expected == "auth", bool(matches(method, path, ct)))

    def test_content_type_is_not_a_prefix_allowlist(self):
        path = PROBE.WORKSPACE + "/documents/markdown"
        for ct in ["application/json", "Application/JSON; charset=UTF-8"]:
            self.assertTrue(matches("POST", path, ct))
        for ct in ["application/jsonp", "text/plain", "application/json-malicious", ""]:
            self.assertFalse(matches("POST", path, ct))
        self.assertFalse(matches("POST", PROBE.WORKSPACE + "/documents", "multipart/form-data"))
        self.assertFalse(matches("POST", PROBE.WORKSPACE + "/documents", "multipart/form-data; boundary="))

    def test_route_boundaries_reject_alternate_paths_and_identifiers(self):
        path = PROBE.DOCUMENT + "/content"
        for wrong in [path + "/", path + "/extra", path.replace("/content", "/rename"),
                      path.replace("doc_", "bad_"), path.replace("ws_", "bad_"),
                      path.replace("/documents/", "/documents/../documents/")]:
            self.assertFalse(matches("PUT", wrong, "multipart/form-data; boundary=x"), wrong)
        self.assertFalse(matches("PATCH", PROBE.WORKSPACE + "/skills/not-a-uuid", "application/json"))

    def test_mcp_json_rpc_body_is_a_contract_only_on_exact_post_path(self):
        # MCP 도구 호출(위키 window 제출, 문서 수정 제안)은 문서 원문을 본문에 담아 8KB를 넘는다.
        for ct in ["application/json", "application/json; charset=utf-8", "Application/JSON;charset=UTF-8"]:
            self.assertTrue(matches("POST", "/mcp", ct))
        for method, path, ct in [("GET", "/mcp", "application/json"), ("DELETE", "/mcp", "application/json"),
                                 ("POST", "/mcp/", "application/json"), ("POST", "/mcp/authorize", "application/json"),
                                 ("POST", "/mcp/workspaces/ws_1/runs/run_1", "application/json"),
                                 ("POST", "/api/mcp", "application/json"), ("POST", "/mcpx", "application/json"),
                                 ("POST", "/mcp", "text/plain"), ("POST", "/mcp", "application/jsonp"), ("POST", "/mcp", ""),
                                 ("POST", "/mcp", "application/x-www-form-urlencoded")]:
            self.assertFalse(matches(method, path, ct), (method, path, ct))
        # MCP OAuth(access)는 예외가 아니다. 토큰·인가 요청은 작은 form/JSON이라 기본 8KB 검사 안에 든다.
        for method, path, ct in [("POST", "/oauth2/token", "application/x-www-form-urlencoded"),
                                 ("POST", "/oauth2/authorize/9f1c2d3e-4b5a-4c6d-8e7f-0a1b2c3d4e5f", "application/json"),
                                 ("GET", "/.well-known/oauth-authorization-server", "")]:
            self.assertFalse(matches(method, path, ct), (method, path, ct))

    def test_regexes_fit_waf_limit_and_have_explicit_boundaries(self):
        for contract in CONTRACTS.values():
            for key in ("path_regex", "content_type_regex"):
                expression = contract[key]
                self.assertLessEqual(len(expression), 512)
                self.assertTrue(expression.startswith("^"))
                self.assertTrue(expression.endswith("$"))
                re.compile(expression)

    def test_large_probe_really_exceeds_byte_limit_in_both_encodings(self):
        for _, _, _, kind, text, expected in PROBE.cases():
            if len(text) > 8000:
                self.assertGreater(len(PROBE.body(kind, text)[1]), 8192)

    def test_probe_never_follows_redirects(self):
        self.assertIsNone(PROBE.NoRedirect().redirect_request(None, None, 302, None, None, "https://other.example"))


if __name__ == "__main__":
    unittest.main()
