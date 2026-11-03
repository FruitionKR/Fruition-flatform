"""Read-only application checks; credentials and HTTP bodies never leave memory."""
import base64
import json
import os
import re
import sys
from http.cookies import SimpleCookie
from urllib import error, request

from aws_release_safety import NoRedirect, smoke_settings


def tamper(token):
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    signature = bytearray(base64.urlsafe_b64decode(parts[2] + "=" * (-len(parts[2]) % 4)))
    if not signature:
        raise ValueError("Missing signature")
    signature[0] ^= 1
    return ".".join(parts[:2] + [base64.urlsafe_b64encode(signature).decode().rstrip("=")])


class Client:
    def __init__(self):
        self.opener = request.build_opener(NoRedirect())
        self.cookie = None

    def call(self, method, url, payload=None, token=None, cookie=False, expected=(200,)):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        req = request.Request(url, method=method, headers=headers,
                              data=None if payload is None else json.dumps(payload).encode())
        try:
            response = self.opener.open(req, timeout=30)
        except error.HTTPError as exc:
            response = exc
        except Exception:
            raise ValueError("Security smoke transport failed") from None
        with response:
            if response.code not in expected:
                raise ValueError("Security smoke unexpected HTTP status")
            if cookie:
                for value in response.headers.get_all("Set-Cookie", []):
                    parsed = SimpleCookie(value)
                    if "fruition_refresh_token" in parsed:
                        item = parsed["fruition_refresh_token"]
                        if item.value and not (item["secure"] and item["httponly"]):
                            raise ValueError("Refresh cookie protection missing")
                        self.cookie = "fruition_refresh_token=" + item.value if item.value else None
            if response.code in (401, 403, 204):
                return {}
            try:
                return json.loads(response.read(1048576))
            except Exception:
                raise ValueError("Security smoke invalid JSON") from None


def run(config, settings, expected_algorithm="RS256", client=None):
    domain = config.get("domain", "")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain) or "." not in domain:
        raise ValueError("Invalid configured domain")
    if expected_algorithm not in ("RS256", "HS512"):
        raise ValueError("Unsupported expected algorithm")
    client = client or Client()
    access = "https://access." + domain
    documents = "https://api." + domain + "/api/workspaces/" + settings["AWS_SMOKE_WORKSPACE_ID"] + "/documents"

    def check_token(body):
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("Login requires a dedicated non-MFA smoke account")
        header = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=" * (-len(token.split(".")[0]) % 4)))
        if header.get("alg") != expected_algorithm or (expected_algorithm == "RS256" and not header.get("kid")):
            raise ValueError("Unexpected signing algorithm or missing key ID")
        return token

    try:
        token = check_token(client.call("POST", access + "/api/auth/login", {
            "email": settings["AWS_SMOKE_EMAIL"], "password": settings["AWS_SMOKE_PASSWORD"]}, cookie=True))
        if not client.cookie:
            raise ValueError("Missing refresh cookie")
        for url in (access + "/api/auth/me", documents):
            client.call("GET", url, token=token)
            client.call("GET", url, token=tamper(token), expected=(401, 403))
        old_cookie = client.cookie
        refreshed = check_token(client.call("POST", access + "/api/auth/refresh", cookie=True))
        if not client.cookie or client.cookie == old_cookie:
            raise ValueError("Refresh cookie did not rotate")
        client.call("GET", access + "/api/auth/me", token=refreshed)
        client.call("GET", documents, token=refreshed)
    finally:
        if client.cookie:
            client.call("POST", access + "/api/auth/logout", cookie=True, expected=(204,))


if __name__ == "__main__":
    try:
        run(json.loads(os.environ["DEPLOY_CONFIG"]), smoke_settings(), os.environ.get("EXPECTED_ALGORITHM", "RS256"))
    except Exception:
        print("Security authentication smoke failed; no response or credentials logged.", file=sys.stderr)
        raise SystemExit(1)
    print("Security authentication smoke passed: login, Access/Document reads, refresh rotation, signature rejection, logout.")
