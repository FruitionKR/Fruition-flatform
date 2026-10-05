"""화면·API를 한 호스트에서 나누는 ALB 규칙과 접근 코드 WAF 규칙이 기존 rewrite·middleware와 같은지 검사한다."""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def alb_pattern(path):
    # ALB 경로 패턴: *는 /를 포함한 0자 이상, ?는 정확히 1자. 나머지는 그대로 비교한다.
    return re.compile("".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in path) + r"\Z")


def route(rules, host, path):
    rule = next(r for r in rules if r["host"] == host)
    for item in rule["http"]["paths"]:
        if alb_pattern(item["path"]).match(path):
            return item["backend"]["service"]["name"]
    return None


class FrontendRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ingress = yaml.safe_load((ROOT / "k8s/overlays/aws/ingress.yaml").read_text())
        cls.rules = cls.ingress["spec"]["rules"]

    def test_app_host_reproduces_frontend_rewrites_in_order(self):
        app = "REPLACE_ME_APP_DOMAIN"
        expected = {
            "/api/auth/login": "access-svc",
            "/api/auth/refresh": "access-svc",
            "/api/workspaces": "access-svc",
            "/api/workspaces/trash": "access-svc",
            "/api/workspaces/ws_1": "access-svc",
            "/api/workspaces/ws_1/restore": "access-svc",
            "/api/workspaces/ws_1/icon": "access-svc",
            "/api/workspaces/ws_1/icon/image": "access-svc",
            "/api/workspaces/ws_1/members": "access-svc",
            "/api/workspaces/ws_1/members/usr_1": "access-svc",
            "/api/workspaces/ws_1/invitations": "access-svc",
            "/api/workspaces/ws_1/invitations/inv_1": "access-svc",
            "/api/invitations/token/accept": "access-svc",
            "/oauth2/authorization/google": "access-svc",
            "/login/oauth2/code/kakao": "access-svc",
            # access의 /{id}/restore 패턴보다 먼저 document 복구로 가야 한다.
            "/api/workspaces/ws_1/documents/doc_1/restore": "document-svc",
            "/api/workspaces/ws_1/documents/doc_1/versions/3/restore": "document-svc",
            "/api/workspaces/ws_1/folders/fld_1/restore": "document-svc",
            "/api/workspaces/ws_1/ai-operation-logs/op_1/restore": "document-svc",
            "/api/workspaces/ws_1/documents": "document-svc",
            "/api/workspaces/ws_1/document-tree": "document-svc",
            "/api/workspaces/ws_1/wiki-schema/drafts": "document-svc",
            "/api/workspaces/ws_1/agent/turn/run_1/events": "document-svc",
            "/api/workspaces/ws_1/ai/tasks/t_1": "document-svc",
            "/api/query/runs/req_1/events": "document-svc",
            "/api/meetings/m_1/live": "document-svc",
            "/api/ai-models": "document-svc",
            "/api/document-transport": "frontend",
            "/": "frontend",
            "/oauth/callback": "frontend",
            "/access/verify": "frontend",
            "/healthz": "frontend",
            "/_next/static/chunks/app.js": "frontend",
        }
        for path, service in expected.items():
            with self.subTest(path=path):
                self.assertEqual(service, route(self.rules, app, path))

    def test_internal_and_openapi_are_not_public_on_any_host(self):
        annotation = self.ingress["metadata"]["annotations"]["alb.ingress.kubernetes.io/actions.not-public"]
        self.assertIn('"statusCode":"404"', annotation)
        for host in ("REPLACE_ME_APP_DOMAIN", "api.REPLACE_ME_DOMAIN", "access.REPLACE_ME_DOMAIN"):
            for path in ("/internal/workspaces/ws_1", "/internal/authz/check", "/v3/api-docs", "/swagger-ui/index.html", "/swagger-ui.html"):
                with self.subTest(host=host, path=path):
                    self.assertEqual("not-public", route(self.rules, host, path))
        self.assertEqual("document-svc", route(self.rules, "api.REPLACE_ME_DOMAIN", "/api/workspaces/ws_1/documents"))
        self.assertEqual("access-svc", route(self.rules, "access.REPLACE_ME_DOMAIN", "/api/auth/login"))

    def test_frontend_target_group_checks_its_own_port(self):
        # Ingress 전역 헬스체크(:8082)를 그대로 쓰면 화면 target이 모두 unhealthy가 된다.
        service = next(d for d in yaml.safe_load_all((ROOT / "k8s/overlays/aws/frontend.yaml").read_text())
                       if d["kind"] == "Service")
        annotations = service["metadata"]["annotations"]
        self.assertEqual("/healthz", annotations["alb.ingress.kubernetes.io/healthcheck-path"])
        self.assertEqual("traffic-port", annotations["alb.ingress.kubernetes.io/healthcheck-port"])
        self.assertEqual("8082", self.ingress["metadata"]["annotations"]["alb.ingress.kubernetes.io/healthcheck-port"])

    def test_waf_access_code_rule_mirrors_frontend_middleware_open_paths(self):
        terraform = (ROOT / "infra/terraform/cost-guards.tf").read_text()
        regex = re.search(r'waf_access_code_open_path_regex = "(.+)"', terraform).group(1)
        opened = re.compile(regex)
        # frontend middleware.ts OPEN_API_PATTERNS와 같은 경로만 코드 없이 열린다.
        for path in ("/api/auth/login", "/api/invitations/token", "/api/workspaces", "/api/workspaces/ws_1"):
            self.assertTrue(opened.search(path), path)
        for path in ("/api/workspaces/ws_1/documents", "/api/workspaces/ws_1/members", "/api/query/runs/r",
                     "/api/document-transport", "/api/ai-models"):
            self.assertFalse(opened.search(path), path)
        self.assertIn('included_cookies = ["fruition_access"]', terraform)
        self.assertIn("search_string         = var.app_domain", terraform)
        # 쿠키 값은 화면 hashAccessCode와 같은 trim + SHA-256이어야 한다.
        self.assertIn("trimspace(", terraform)
        self.assertIn("search_string         = sha256(local.waf_access_code)", terraform)
        self.assertIn('regex_string = "^/+(internal|swagger-ui|v3/api-docs)"', terraform)


if __name__ == "__main__":
    unittest.main()
