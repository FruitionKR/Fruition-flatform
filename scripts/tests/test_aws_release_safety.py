"""Exercise failure/cleanup boundaries without accounts, AWS, or actual HTTP traffic."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release_safety", ROOT / "scripts/aws_release_safety.py")
safety = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safety)
SHA = "a" * 40
REVIEW = {"release_sha": SHA, "migration_mode": "expand-only",
          "compatibility_test_url": "https://github.com/FruitionKR/Fruition-ai/actions/runs/12",
          "restore_test_url": "https://github.com/FruitionKR/Fruition-flatform/issues/34"}
SETTINGS = {"AWS_SMOKE_EMAIL": "fixture@example.test", "AWS_SMOKE_PASSWORD": "secret-fixture",
            "AWS_SMOKE_WORKSPACE_ID": "ws_00000000000000000000000000000001"}
DOC = "doc_00000000000000000000000000000002"


class Response:
    def __init__(self, body, status=200):
        self.body, self.status = body, status
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size):
        return json.dumps(self.body).encode()


class SmokeTests(unittest.TestCase):
    def test_review_rejects_unreviewed_sha_destructive_modes_and_placeholder_evidence(self):
        safety.validate_review(REVIEW, SHA)
        for key, value in (("release_sha", "b" * 40), ("migration_mode", "contract"),
                           ("compatibility_test_url", "TODO"), ("restore_test_url", "https://evil.test/ok")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                safety.validate_review({**REVIEW, key: value}, SHA)
        with self.assertRaises(ValueError):
            safety.validate_review(None, SHA)

    def test_credentials_missing_or_invalid_workspace_fail_before_http(self):
        for env in ({}, {**SETTINGS, "AWS_SMOKE_WORKSPACE_ID": "../../production"}):
            with patch.dict(safety.os.environ, env, clear=True), self.assertRaises(ValueError):
                safety.smoke_settings()

    def test_login_write_ingest_and_cleanup_only_created_document(self):
        for terminal in ("completed", "failed"):
            events = []
            def request(req, timeout):
                events.append(req)
                if req.full_url.endswith("/login"):
                    self.assertNotIn("Authorization", req.headers)
                    return Response({"access_token": "fixture-token"})
                self.assertEqual("Bearer fixture-token", req.headers["Authorization"])
                if req.full_url.endswith("/markdown"):
                    return Response({"id": DOC}, 201)
                if req.full_url.endswith("/ingest"):
                    return Response({}, 202)
                return Response({"status": terminal, "current_version": 3})
            with patch.object(safety.request, "build_opener") as builder:
                builder.return_value.open.side_effect = request
                if terminal == "failed":
                    with self.assertRaisesRegex(ValueError, "AI 작업 실패"):
                        safety.authenticated_smoke({"domain": "example.test"}, SHA, settings=SETTINGS)
                else:
                    safety.authenticated_smoke({"domain": "example.test"}, SHA, settings=SETTINGS)
            self.assertEqual(["POST", "POST", "GET", "POST", "GET", "GET", "DELETE"], [r.method for r in events])
            self.assertTrue(events[-1].full_url.endswith("/" + DOC))
            self.assertEqual(json.loads(events[-1].data), {"base_version": 3})
            self.assertTrue(events[-1].get_header("Idempotency-key").startswith("deploy-smoke-cleanup-"))
            self.assertNotEqual(events[1].get_header("Idempotency-key"), events[-1].get_header("Idempotency-key"))

    def test_real_workspace_id_contract_and_cleanup_error_preserves_primary_failure(self):
        with patch.dict(safety.os.environ, SETTINGS, clear=True):
            self.assertEqual(safety.smoke_settings(), SETTINGS)
        with patch.dict(safety.os.environ, {**SETTINGS, "AWS_SMOKE_WORKSPACE_ID": "00000000-0000-0000-0000-000000000001"}, clear=True):
            with self.assertRaises(ValueError):
                safety.smoke_settings()
        def request(req, timeout):
            if req.full_url.endswith("/login"):
                return Response({"access_token": "fixture-token"})
            if req.full_url.endswith("/markdown"):
                return Response({"id": DOC}, 201)
            if req.full_url.endswith("/ingest"):
                return Response({}, 202)
            if req.method == "DELETE":
                raise HTTPError(req.full_url, 409, "private-response", {}, None)
            return Response({"status": "failed", "current_version": 3})
        with patch.object(safety.request, "build_opener") as builder, patch.object(safety.sys, "stderr") as stderr:
            builder.return_value.open.side_effect = request
            with self.assertRaisesRegex(ValueError, "AI 작업 실패"):
                safety.authenticated_smoke({"domain": "example.test"}, SHA, settings=SETTINGS)
            written = "".join(str(c.args[0]) for c in stderr.write.call_args_list)
            self.assertIn("정리도 실패", written)
            self.assertNotIn("private-response", written)

    def test_http_errors_do_not_echo_response_or_credentials(self):
        with patch.object(safety.request, "build_opener") as builder:
            builder.return_value.open.side_effect = HTTPError("https://secret", 401, "secret-fixture", {}, None)
            with self.assertRaises(ValueError) as result:
                safety.authenticated_smoke({"domain": "example.test"}, SHA, settings=SETTINGS)
            self.assertNotIn("secret", str(result.exception))

    def test_cross_host_redirect_is_rejected(self):
        self.assertIsNone(safety.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test"))


if __name__ == "__main__":
    unittest.main()
