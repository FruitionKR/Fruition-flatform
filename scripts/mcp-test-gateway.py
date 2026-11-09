#!/usr/bin/env python3
"""Small local-only TLS/same-origin router for the isolated MCP stack."""

from __future__ import annotations

import http.client
import json
import os
import re
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


MAX_BODY = 4 * 1024 * 1024
HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}
ACCESS_PATTERNS = (
    re.compile(r"^/api/auth(?:/|$)"),
    re.compile(r"^/api/invitations(?:/|$)"),
    re.compile(r"^/api/mcp/connections(?:/|$)"),
    re.compile(r"^/api/users/[^/]+/avatar(?:/|$)"),
    re.compile(r"^/oauth2(?:/|$)"),
    re.compile(r"^/login/oauth2(?:/|$)"),
    re.compile(r"^/\.well-known/oauth-authorization-server$"),
    re.compile(r"^/api/workspaces/?$"),
    re.compile(r"^/api/workspaces/[^/]+/(?:restore|icon|members|invitations|mcp-policy|mcp-connections)(?:/|$)"),
)
DOCUMENT_PATTERNS = (
    re.compile(r"^/mcp$"),
    re.compile(r"^/\.well-known/oauth-protected-resource/mcp$"),
    re.compile(r"^/api(?:/|$)"),
)
# compose 서비스 주소. 테스트는 로컬 fixture 주소로 교체한다.
UPSTREAMS = {
    "ai": ("pipeline-api", 8000),
    "access": ("access-svc", 8081),
    "document": ("document-svc", 8080),
}
# Document McpWikiPageClient: wikiSearchUri origin + /wiki/pages/{id}?workspace_id=...&mcp_read=true
INTERNAL_PAGE_READ = re.compile(r"^/wiki/pages/[^/]+$")


class BodyError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


class Router(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "FruitionMcpTestGateway/1"

    def do_GET(self): self._route()
    def do_HEAD(self): self._route()
    def do_POST(self): self._route()
    def do_PUT(self): self._route()
    def do_PATCH(self): self._route()
    def do_DELETE(self): self._route()
    def do_OPTIONS(self): self._route()

    def _route(self):
        target = urlsplit(self.path)
        path = target.path
        if path == "/client-metadata":
            self._metadata()
            return
        if self.server.internal:
            page_read = (self.command == "GET" and INTERNAL_PAGE_READ.match(path)
                         and parse_qs(target.query).get("mcp_read") == ["true"])
            if path.startswith("/internal/mcp/wiki/") or page_read:
                self._proxy(*UPSTREAMS["ai"])
            else:
                self.send_error(404)
            return
        if path.startswith(("/internal", "/swagger-ui", "/v3/api-docs")):
            self.send_error(404)
        elif any(pattern.match(path) for pattern in ACCESS_PATTERNS):
            self._proxy(*UPSTREAMS["access"])
        elif any(pattern.match(path) for pattern in DOCUMENT_PATTERNS):
            self._proxy(*UPSTREAMS["document"])
        else:
            upstream = urlsplit(os.environ["MCP_TEST_FRONTEND_UPSTREAM"])
            self._proxy(upstream.hostname, upstream.port or 80)

    def _metadata(self):
        body = json.dumps({
            "client_id": os.environ["MCP_TEST_CLIENT_ID"],
            "client_name": "Fruition isolated MCP test client",
            "redirect_uris": [os.environ["MCP_TEST_CLIENT_REDIRECT_URI"]],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        }, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _proxy(self, host, port):
        try:
            try:
                body = self._read_body()
            except BodyError as error:
                self.send_error(error.status)
                return
            # body는 bytes로 다시 보내므로 http.client가 Content-Length를 새로 계산한다.
            headers = {name: value for name, value in self.headers.items()
                       if name.lower() not in HOP_HEADERS | {"host", "content-length"}}
            external_host = self.headers.get("Host", "localhost")
            host_name, _, host_port = external_host.partition(":")
            headers.update({
                "Host": external_host,
                "X-Forwarded-Host": external_host,
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Port": host_port or "443",
                "X-Forwarded-For": self.client_address[0],
                "Connection": "close",
            })
            connection = http.client.HTTPConnection(host, port, timeout=120)
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status, response.reason)
            for name, value in response.getheaders():
                if name.lower() not in HOP_HEADERS and name.lower() != "content-length":
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
            connection.close()
        except (OSError, http.client.HTTPException, ValueError):
            self.send_error(502)

    def _read_body(self):
        lengths = self.headers.get_all("Content-Length", [])
        encodings = self.headers.get_all("Transfer-Encoding", [])
        if encodings:
            if lengths:
                raise BodyError(400)  # CL+TE 동시 지정은 smuggling 모호성이라 거부한다.
            if [e.strip().lower() for e in ",".join(encodings).split(",")] != ["chunked"]:
                raise BodyError(501)
            return self._read_chunked()
        if not lengths:
            return None
        if len(lengths) > 1 or not re.fullmatch(r"[0-9]+", lengths[0].strip()):
            raise BodyError(400)
        length = int(lengths[0])
        if length > MAX_BODY:
            raise BodyError(413)
        body = self.rfile.read(length)
        if len(body) != length:
            raise BodyError(400)
        return body

    def _read_chunked(self):
        body = bytearray()
        while True:
            line = self.rfile.readline(1026)
            size = line.split(b";", 1)[0].strip()
            if not line.endswith(b"\r\n") or not re.fullmatch(rb"[0-9a-fA-F]+", size):
                raise BodyError(400)
            size = int(size, 16)
            if len(body) + size > MAX_BODY:
                raise BodyError(413)
            if size == 0:
                break
            body += self.rfile.read(size)
            if self.rfile.read(2) != b"\r\n":
                raise BodyError(400)
        for _ in range(64):  # trailer는 전달하지 않고 소비만 한다.
            line = self.rfile.readline(8194)
            if line == b"\r\n":
                return bytes(body)
            if not line.endswith(b"\r\n"):
                raise BodyError(400)
        raise BodyError(400)

    def log_message(self, message, *args):
        print("[mcp-test-gateway] " + message % args, flush=True)


def serve(port: int, tls: bool):
    server = ThreadingHTTPServer(("0.0.0.0", port), Router)
    server.internal = port == 9443
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain("/run/mcp-test/tls.crt", "/run/mcp-test/tls.key")
        server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    for listen_port, use_tls in ((8080, False), (8443, True), (9443, True)):
        threading.Thread(target=serve, args=(listen_port, use_tls), daemon=True).start()
    threading.Event().wait()
