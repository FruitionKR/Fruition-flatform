#!/usr/bin/env python3
"""Seed synthetic local actors/content and prove the isolated MCP read boundary."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlsplit


def request(method, url, payload=None, token=None, headers=None, expected=(200,), context=None):
    body = None if payload is None else json.dumps(payload).encode()
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60, context=context) as response:
            raw = response.read().decode()
            if response.status not in expected:
                raise RuntimeError(f"{method} {url}: HTTP {response.status}")
            return response.status, response.headers, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        if exc.code in expected:
            return exc.code, exc.headers, {}
        detail = exc.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"{method} {url}: HTTP {exc.code}: {detail}") from exc


def email_code(container, email):
    pattern = re.compile(rf"email={re.escape(email)} purpose=signup code=([0-9]{{6}})")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "logs", container], text=True, capture_output=True, check=True
        )
        logs = result.stdout + result.stderr
        match = pattern.search(logs)
        if match:
            return match.group(1)
        time.sleep(0.5)
    raise RuntimeError("synthetic signup verification code was not emitted")


def b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def mcp_token(private_key, issuer, resource, user_id, workspace_id, client_id, grant_id, generation):
    now = int(time.time())
    header = b64url(json.dumps({"alg": "RS256", "kid": "mcp-test-1", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = b64url(json.dumps({
        "iss": issuer,
        "aud": [resource],
        "sub": user_id,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + 8 * 60 * 60,
        "grant_id": grant_id,
        "workspace_id": workspace_id,
        "client_id": client_id,
        "policy_generation": generation,
        "scope": "read",
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}".encode()
    signed = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(private_key)],
        input=signing_input, capture_output=True, check=True,
    ).stdout
    return f"{header}.{claims}.{b64url(signed)}"


def psql(container, variables, sql):
    command = ["docker", "exec", "-i", container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
               "-U", "fruition_admin", "-d", "access_db"]
    for name, value in variables.items():
        command.append(f"--set={name}={value}")
    subprocess.run(command, input=sql, text=True, check=True, stdout=subprocess.DEVNULL)


def rpc(url, host, ca, token, payload):
    context = ssl.create_default_context(cafile=str(ca))
    _, _, body = request(
        "POST", url, payload, token,
        {"Host": host, "Accept": "application/json, text/event-stream"},
        context=context,
    )
    return body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--access-url", required=True)
    parser.add_argument("--document-url", required=True)
    parser.add_argument("--gateway-url", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--resource", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--real-client-id", default="")
    parser.add_argument("--access-container", required=True)
    parser.add_argument("--postgres-container", required=True)
    parser.add_argument("--terms-version", required=True)
    args = parser.parse_args()

    credentials = args.runtime_dir / "credentials.json"
    if credentials.exists():
        print(f"[mcp-test-seed] existing synthetic fixture: {credentials}")
        return

    run_key = uuid.uuid4().hex[:12]
    email = f"mcp-test-{run_key}@example.test"
    password = "mcp-test-" + uuid.uuid4().hex
    _, _, verification = request(
        "POST", f"{args.access_url}/api/auth/email-verifications",
        {"email": email, "purpose": "signup"}, expected=(202,),
    )
    code = email_code(args.access_container, email)
    _, _, confirmed = request(
        "POST", f"{args.access_url}/api/auth/email-verifications/{verification['verification_id']}/confirm",
        {"code": code},
    )
    _, _, signup = request(
        "POST", f"{args.access_url}/api/auth/signup",
        {
            "email": email,
            "password": password,
            "display_name": "MCP isolated test owner",
            "verification_token": confirmed["verification_token"],
            "age_confirmed": True,
            "terms_version": args.terms_version,
            "marketing_opt_in": False,
        }, expected=(201,),
    )
    _, _, login = request(
        "POST", f"{args.access_url}/api/auth/login", {"email": email, "password": password},
    )
    web_token = login["access_token"]
    _, _, workspace = request(
        "POST", f"{args.access_url}/api/workspaces",
        {"name": f"MCP isolated {run_key}"}, web_token, expected=(201,),
    )
    workspace_id = workspace["id"]
    _, _, policy = request(
        "PUT", f"{args.access_url}/api/workspaces/{workspace_id}/mcp-policy",
        {"enabled": True, "allowed_scopes": ["read"]}, web_token,
    )
    _, _, document = request(
        "POST", f"{args.document_url}/api/workspaces/{workspace_id}/documents/markdown",
        {
            "display_name": "Synthetic MCP read proof",
            "markdown": "# Synthetic MCP read proof\n\nIsolated content; no customer data.\n",
            "folder_id": None,
            "origin": None,
            "agent_run_id": None,
        }, web_token, {"Idempotency-Key": f"mcp-test-{run_key}"}, expected=(201,),
    )

    grant_id = str(uuid.uuid4())
    variables = {
        "client_id": args.client_id,
        "grant_id": grant_id,
        "user_id": signup["id"],
        "workspace_id": workspace_id,
        "generation": str(policy["generation"]),
    }
    real_client_sql = ""
    if args.real_client_id:
        variables["real_client_id"] = args.real_client_id
        real_client_sql = """
INSERT INTO mcp_client_policies(client_id,enabled,updated_at)
VALUES (:'real_client_id',true,now())
ON CONFLICT (client_id) DO UPDATE SET enabled=true,updated_at=now();
"""
    psql(args.postgres_container, variables, f"""
INSERT INTO mcp_client_policies(client_id,enabled,updated_at)
VALUES (:'client_id',true,now())
ON CONFLICT (client_id) DO UPDATE SET enabled=true,updated_at=now();
{real_client_sql}
INSERT INTO mcp_grants(grant_id,user_id,workspace_id,client_id,status,revocation_reason,
                       policy_generation,created_at,revoked_at)
VALUES (:'grant_id'::uuid,:'user_id',:'workspace_id',:'client_id','ACTIVE',NULL,
        :'generation'::bigint,now(),NULL);
INSERT INTO mcp_grant_scopes(grant_id,scope) VALUES (:'grant_id'::uuid,'READ');
""")

    token = mcp_token(
        args.runtime_dir / "jwt-private.pem", args.origin, args.resource,
        signup["id"], workspace_id, args.client_id, grant_id, policy["generation"],
    )
    origin = urlsplit(args.origin)
    host = origin.netloc
    context = ssl.create_default_context(cafile=str(args.runtime_dir / "tls-ca.crt"))
    status, headers, _ = request(
        "POST", args.gateway_url + "/mcp",
        {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}},
        headers={"Host": host}, expected=(401,), context=context,
    )
    challenge = headers.get("WWW-Authenticate", "")
    expected_metadata = f'{args.origin}/.well-known/oauth-protected-resource/mcp'
    if status != 401 or expected_metadata not in challenge:
        raise RuntimeError("MCP unauthenticated challenge did not advertise the configured resource metadata")

    _, _, metadata = request(
        "GET", args.gateway_url + "/.well-known/oauth-protected-resource/mcp",
        headers={"Host": host}, context=context,
    )
    _, _, authorization = request(
        "GET", args.gateway_url + "/.well-known/oauth-authorization-server",
        headers={"Host": host}, context=context,
    )
    _, _, jwks = request(
        "GET", args.gateway_url + "/oauth2/jwks",
        headers={"Host": host}, context=context,
    )
    if metadata.get("resource") != args.resource or metadata.get("authorization_servers") != [args.origin]:
        raise RuntimeError("protected-resource metadata does not match the configured origin/resource")
    if authorization.get("issuer") != args.origin or authorization.get("jwks_uri") != f"{args.origin}/oauth2/jwks":
        raise RuntimeError("authorization metadata issuer/JWKS mismatch")
    if [key.get("kid") for key in jwks.get("keys", [])] != ["mcp-test-1"]:
        raise RuntimeError("authorization JWKS did not expose the generated test key")

    initialized = rpc(
        args.gateway_url + "/mcp", host, args.runtime_dir / "tls-ca.crt", token,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "isolated-test", "version": "1"},
        }},
    )
    tools = rpc(
        args.gateway_url + "/mcp", host, args.runtime_dir / "tls-ca.crt", token,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    found = rpc(
        args.gateway_url + "/mcp", host, args.runtime_dir / "tls-ca.crt", token,
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "find_documents",
            "arguments": {"query": "Synthetic MCP read proof", "cursor": None, "page_size": 10},
        }},
    )
    names = [tool.get("name") for tool in tools.get("result", {}).get("tools", [])]
    results = found.get("result", {}).get("structuredContent", {}).get("results", [])
    if initialized.get("result", {}).get("protocolVersion") != "2025-11-25":
        raise RuntimeError("MCP initialize failed")
    if names != ["search_wiki", "find_documents", "get_document", "get_wiki_page"]:
        raise RuntimeError("MCP public read catalog mismatch")
    if document["id"] not in [item.get("document_id") for item in results]:
        raise RuntimeError("synthetic document was not returned by authenticated MCP read")

    output = {
        "email": email,
        "password": password,
        "user_id": signup["id"],
        "workspace_id": workspace_id,
        "document_id": document["id"],
        "client_id": args.client_id,
        "real_client_id": args.real_client_id or None,
        "grant_id": grant_id,
        "policy_generation": policy["generation"],
        "web_access_token": web_token,
        "mcp_access_token": token,
        "mcp_access_token_expires_at": int(time.time()) + 8 * 60 * 60,
    }
    credentials.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    os.chmod(credentials, 0o600)
    print(f"[mcp-test-seed] synthetic fixture and MCP read proof ready: {credentials}")


if __name__ == "__main__":
    main()
