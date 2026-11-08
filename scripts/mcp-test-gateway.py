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
from urllib.parse import urlsplit


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
        path = urlsplit(self.path).path
        if path == "/client-metadata":
            self._metadata()
            return
        if self.server.server_port == 9443:
            if path.startswith("/internal/mcp/wiki/"):
                self._proxy("pipeline-api", 8000)
            else:
                self.send_error(404)
            return
        if path.startswith(("/internal", "/swagger-ui", "/v3/api-docs")):
            self.send_error(404)
        elif any(pattern.match(path) for pattern in ACCESS_PATTERNS):
            self._proxy("access-svc", 8081)
        elif any(pattern.match(path) for pattern in DOCUMENT_PATTERNS):
            self._proxy("document-svc", 8080)
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
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY:
                self.send_error(413)
                return
            body = self.rfile.read(length) if length else None
            headers = {name: value for name, value in self.headers.items()
                       if name.lower() not in HOP_HEADERS and name.lower() != "host"}
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

    def log_message(self, message, *args):
        print("[mcp-test-gateway] " + message % args, flush=True)


def serve(port: int, tls: bool):
    server = ThreadingHTTPServer(("0.0.0.0", port), Router)
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain("/run/mcp-test/tls.crt", "/run/mcp-test/tls.key")
        server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


for listen_port, use_tls in ((8080, False), (8443, True), (9443, True)):
    threading.Thread(target=serve, args=(listen_port, use_tls), daemon=True).start()
threading.Event().wait()
