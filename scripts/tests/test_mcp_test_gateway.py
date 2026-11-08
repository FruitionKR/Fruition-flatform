"""MCP 테스트 gateway를 실제 로컬 HTTP upstream fixture에 붙여 라우팅·본문 전달을 검사한다."""

import http.client
import importlib.util
import json
import os
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "mcp_test_gateway", Path(__file__).resolve().parents[1] / "mcp-test-gateway.py")
gateway = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gateway)


class Upstream(BaseHTTPRequestHandler):
    """받은 요청을 그대로 기록하고 JSON으로 되돌려주는 fixture."""
    protocol_version = "HTTP/1.1"

    def _record(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        self.server.seen.append({"method": self.command, "path": self.path,
                                 "headers": dict(self.headers.items()), "body": body})
        payload = json.dumps({"upstream": self.server.name}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _record

    def log_message(self, *args):
        pass


def start(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstreams = {}
        for name in ("ai", "access", "document", "frontend"):
            server = start(ThreadingHTTPServer(("127.0.0.1", 0), Upstream))
            server.name, server.seen = name, []
            cls.upstreams[name] = server
            if name != "frontend":
                gateway.UPSTREAMS[name] = ("127.0.0.1", server.server_port)
        os.environ["MCP_TEST_FRONTEND_UPSTREAM"] = (
            f"http://127.0.0.1:{cls.upstreams['frontend'].server_port}")
        cls.public = start(ThreadingHTTPServer(("127.0.0.1", 0), gateway.Router))
        cls.public.internal = False
        cls.internal = start(ThreadingHTTPServer(("127.0.0.1", 0), gateway.Router))
        cls.internal.internal = True

    @classmethod
    def tearDownClass(cls):
        for server in (cls.public, cls.internal, *cls.upstreams.values()):
            server.shutdown()
            server.server_close()

    def setUp(self):
        for server in self.upstreams.values():
            server.seen.clear()

    def request(self, server, method, path, body=None, headers=None, chunked=False):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        if chunked:
            body = iter([body[:5], body[5:]])
        connection.request(method, path, body=body, headers=headers or {}, encode_chunked=chunked)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return response.status, payload

    def raw(self, server, data):
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=10) as sock:
            try:
                sock.sendall(data)
            except OSError:
                pass  # gateway가 거부 응답 후 먼저 닫을 수 있다.
            return sock.recv(65536).split(b" ", 2)[1].decode()

    def only(self, name):
        hits = {key: server.seen for key, server in self.upstreams.items() if server.seen}
        self.assertEqual(list(hits), [name])
        self.assertEqual(len(hits[name]), 1)
        return hits[name][0]

    def nothing_forwarded(self):
        self.assertFalse(any(server.seen for server in self.upstreams.values()))

    # 내부 9443: Document McpWikiPageClient/McpWikiSearchClient만 이 포트를 쓴다.
    def test_internal_page_read_reaches_ai_with_exact_path_query_and_token(self):
        path = ("/wiki/pages/wiki_page_2a99b4db-0807-5f4a-bb10-d54ae96e5335"
                "?workspace_id=ws-1&mcp_read=true")
        status, payload = self.request(self.internal, "GET", path,
                                       headers={"X-Internal-Token": "fixture-token"})
        self.assertEqual((status, json.loads(payload)), (200, {"upstream": "ai"}))
        seen = self.only("ai")
        self.assertEqual((seen["method"], seen["path"]), ("GET", path))
        self.assertEqual(seen["headers"]["X-Internal-Token"], "fixture-token")

    def test_internal_search_forwards_content_length_and_chunked_bodies_intact(self):
        body = json.dumps({"query": "Project Aurora", "page_size": 5}).encode()
        for chunked in (False, True):
            with self.subTest(chunked=chunked):
                self.setUp()
                status, _ = self.request(self.internal, "POST", "/internal/mcp/wiki/search", body,
                                         {"Content-Type": "application/json"}, chunked)
                self.assertEqual(status, 200)
                seen = self.only("ai")
                self.assertEqual(seen["body"], body)
                self.assertEqual(seen["headers"]["Content-Length"], str(len(body)))
                self.assertNotIn("Transfer-Encoding", seen["headers"])

    def test_internal_port_rejects_everything_outside_the_page_read_and_wiki_routes(self):
        for method, path in (("POST", "/wiki/pages/p1?workspace_id=w&mcp_read=true"),
                             ("GET", "/wiki/pages/p1?workspace_id=w"),
                             ("GET", "/wiki/pages/p1/extra?workspace_id=w&mcp_read=true"),
                             ("POST", "/wiki/pages/lookup"), ("POST", "/agent/runs"),
                             ("GET", "/api/workspaces"), ("GET", "/mcp")):
            with self.subTest(method=method, path=path):
                status, _ = self.request(self.internal, method, path, b"{}" if method == "POST" else None)
                self.assertEqual(status, 404)
        self.nothing_forwarded()

    # 공개 8080/8443: private AI 경로는 절대 AI로 가지 않는다.
    def test_public_port_never_exposes_ai_routes(self):
        for path in ("/internal/mcp/wiki/search", "/internal/mcp/wiki/drafts/d1/preview"):
            with self.subTest(path=path):
                self.assertEqual(self.request(self.public, "GET", path)[0], 404)
        self.nothing_forwarded()
        self.request(self.public, "GET", "/wiki/pages/p1?workspace_id=w&mcp_read=true")
        self.only("frontend")

    def test_public_mcp_oauth_review_routes_keep_host_auth_query_and_body(self):
        host = "mcp.example.test"
        cases = (
            ("POST", "/mcp", "document", b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'),
            ("GET", "/.well-known/oauth-protected-resource/mcp", "document", None),
            ("GET", "/.well-known/oauth-authorization-server", "access", None),
            ("GET", "/oauth2/authorize?client_id=c&state=s%2Fx", "access", None),
            ("POST", "/oauth2/token", "access", b"grant_type=authorization_code&code=abc"),
            ("POST", "/api/workspaces/w1/mcp/wiki-drafts/d1/approve?x=1", "document", b'{"v":1}'),
            ("GET", "/api/workspaces/w1/mcp-policy", "access", None),
            ("GET", "/api/mcp/connections", "access", None),
            ("GET", "/mcp/authorize?pending=p1", "frontend", None),
        )
        for method, path, upstream, body in cases:
            for chunked in ((False, True) if body else (False,)):
                with self.subTest(path=path, chunked=chunked):
                    self.setUp()
                    status, _ = self.request(self.public, method, path, body,
                                             {"Host": host, "Authorization": "Bearer fixture"}, chunked)
                    self.assertEqual(status, 200)
                    seen = self.only(upstream)
                    self.assertEqual((seen["method"], seen["path"]), (method, path))
                    self.assertEqual(seen["body"], body or b"")
                    self.assertEqual(seen["headers"]["Authorization"], "Bearer fixture")
                    self.assertEqual(seen["headers"]["Host"], host)
                    self.assertEqual(seen["headers"]["X-Forwarded-Host"], host)
                    self.assertEqual(seen["headers"]["X-Forwarded-Proto"], "https")

    def test_malformed_ambiguous_and_oversized_bodies_are_rejected_before_forwarding(self):
        big = gateway.MAX_BODY + 1
        head = b"POST /internal/mcp/wiki/search HTTP/1.1\r\nHost: g\r\n"
        cases = (
            ("400", head + b"Content-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n"),
            ("400", head + b"Content-Length: abc\r\n\r\n"),
            ("400", head + b"Content-Length: -1\r\n\r\n"),
            ("400", head + b"Content-Length: 2\r\nContent-Length: 3\r\n\r\n{}"),
            ("501", head + b"Transfer-Encoding: gzip, chunked\r\n\r\n0\r\n\r\n"),
            ("400", head + b"Transfer-Encoding: chunked\r\n\r\nzz\r\n{}\r\n0\r\n\r\n"),
            ("400", head + b"Transfer-Encoding: chunked\r\n\r\n2\r\n{}XX0\r\n\r\n"),
            ("413", head + f"Content-Length: {big}\r\n\r\n".encode()),
            ("413", head + b"Transfer-Encoding: chunked\r\n\r\n" + f"{big:x}\r\n".encode()),
        )
        for expected, data in cases:
            with self.subTest(data=data[len(head):60 + len(head)]):
                self.assertEqual(self.raw(self.internal, data), expected)
        self.nothing_forwarded()

    def test_chunked_body_over_limit_across_chunks_is_rejected(self):
        half = gateway.MAX_BODY // 2 + 1
        chunk = f"{half:x}\r\n".encode() + b"a" * half + b"\r\n"
        data = (b"POST /mcp HTTP/1.1\r\nHost: g\r\nTransfer-Encoding: chunked\r\n\r\n"
                + chunk + chunk + b"0\r\n\r\n")
        self.assertEqual(self.raw(self.public, data), "413")
        self.nothing_forwarded()


if __name__ == "__main__":
    unittest.main()
