import base64
import io
import json
import unittest
from email.message import Message
from unittest.mock import Mock
from urllib.error import HTTPError

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aws_security_auth_smoke as smoke


def token(algorithm="RS256"):
    header = base64.urlsafe_b64encode(json.dumps({"alg": algorithm, "kid": "test"}).encode()).decode().rstrip("=")
    return header + ".e30." + base64.urlsafe_b64encode(b"test-signature").decode().rstrip("=")


class FakeClient:
    def __init__(self, rotate=True, algorithm="RS256", failure=None):
        self.cookie = None
        self.calls = []
        self.rotate = rotate
        self.algorithm = algorithm
        self.failure = failure

    def call(self, method, url, payload=None, token=None, cookie=False, expected=(200,)):
        self.calls.append((method, url, expected))
        if url.endswith("/login"):
            self.cookie = "initial-test-cookie"
        if self.failure and self.failure in url:
            raise ValueError("simulated failure")
        if url.endswith("/refresh") and self.rotate:
            self.cookie = "rotated-test-cookie"
        if url.endswith("/logout"):
            self.cookie = None
        return {"access_token": globals()["token"](self.algorithm)}


class SecuritySmokeTests(unittest.TestCase):
    settings = {"AWS_SMOKE_EMAIL": "test@example.invalid", "AWS_SMOKE_PASSWORD": "test-only-password",
                "AWS_SMOKE_WORKSPACE_ID": "ws_" + "0" * 32}

    def test_reads_only_application_data_and_revokes_test_session(self):
        client = FakeClient()
        smoke.run({"domain": "example.invalid"}, self.settings, client=client)
        self.assertEqual(["/api/auth/login", "/api/auth/refresh", "/api/auth/logout"],
                         [url.split("example.invalid")[1] for method, url, _ in client.calls if method != "GET"])
        self.assertEqual(2, sum(expected == (401, 403) for _, _, expected in client.calls))
        self.assertIsNone(client.cookie)

    def test_session_cleanup_on_document_failure(self):
        client = FakeClient(failure="/documents")
        with self.assertRaises(ValueError):
            smoke.run({"domain": "example.invalid"}, self.settings, client=client)
        self.assertTrue(client.calls[-1][1].endswith("/logout"))

    def test_rejects_wrong_algorithm_and_unchanged_refresh_cookie(self):
        for client in (FakeClient(algorithm="HS512"), FakeClient(rotate=False)):
            with self.assertRaises(ValueError):
                smoke.run({"domain": "example.invalid"}, self.settings, client=client)
            self.assertIsNone(client.cookie)

    def test_tamper_changes_signature_bytes_only(self):
        original = token()
        changed = smoke.tamper(original)
        self.assertEqual(original.split(".")[:2], changed.split(".")[:2])
        self.assertNotEqual(original.split(".")[2], changed.split(".")[2])

    def test_invalid_domain_never_sends_credentials(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            smoke.run({"domain": "example.invalid/redirect"}, self.settings, client=client)
        self.assertFalse(client.calls)

    def test_expected_unauthorized_closes_response_without_reading_body(self):
        client = smoke.Client()
        body = io.BytesIO(b"sensitive-server-error")
        client.opener = Mock()
        client.opener.open.side_effect = HTTPError("https://example.invalid", 401, "private", Message(), body)
        self.assertEqual({}, client.call("GET", "https://example.invalid", expected=(401, 403)))
        self.assertTrue(body.closed)

    def test_transport_error_is_redacted(self):
        client = smoke.Client()
        client.opener = Mock()
        client.opener.open.side_effect = RuntimeError("sensitive credential")
        with self.assertRaisesRegex(ValueError, "^Security smoke transport failed$"):
            client.call("GET", "https://example.invalid")


if __name__ == "__main__":
    unittest.main()
