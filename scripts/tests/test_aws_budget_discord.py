"""Offline delivery tests: no AWS credentials or Discord requests."""

import importlib.util
import json
import os
import sys
import traceback
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "budget_discord", ROOT / "infra/lambda/budget_discord/handler.py")
notifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notifier)

TOPIC = "arn:aws:sns:ap-northeast-2:123456789012:fruition-budget-alerts"
URL = "https://discord.com/api/webhooks/123456789/fake-test-token"


def event(message="Actual spend: $551.00", topic=TOPIC):
    return {"Records": [{"EventSource": "aws:sns", "Sns": {
        "TopicArn": topic, "Subject": "AWS Budgets: fruition-monthly-550",
        "Message": message,
    }}]}


class BudgetDiscordTests(unittest.TestCase):
    def test_operational_alarm_and_recovery_use_trusted_topic(self):
        topic = TOPIC.replace("budget", "operations")
        for state, title in (("ALARM", "경보"), ("OK", "복구")):
            with self.subTest(state=state), patch.dict(os.environ, {"OPERATIONS_TOPIC_ARN": topic}), \
                 patch.object(notifier, "read_webhook", return_value=URL), patch.object(notifier, "send") as send:
                message = json.dumps({"AlarmName": "fruition-ops-node_cpu", "NewStateValue": state,
                                      "NewStateReason": "@everyone threshold crossed", "AWSAccountId": "123456789012"})
                self.assertEqual({"delivered": 1}, notifier.handler(event(message, topic), None))
                payload = send.call_args.args[1]
                self.assertIn(title, payload["content"])
                self.assertIn(state, payload["content"])
                self.assertEqual({"parse": []}, payload["allowed_mentions"])

    def test_malformed_operational_alarm_fails_before_secret_read(self):
        topic = TOPIC.replace("budget", "operations")
        for message in ("not-json", "[]", "{}", '{"AlarmName":"test","NewStateValue":"invalid"}'):
            with self.subTest(message=message), patch.dict(os.environ, {"OPERATIONS_TOPIC_ARN": topic}), \
                 patch.object(notifier, "read_webhook") as read, self.assertRaises(notifier.DeliveryError):
                notifier.handler(event(message, topic), None)
            read.assert_not_called()

    def setUp(self):
        env = patch.dict(os.environ, {"SNS_TOPIC_ARN": TOPIC, "WEBHOOK_SECRET_ARN": "secret-arn"})
        env.start()
        self.addCleanup(env.stop)

    def test_delivery_confirms_saved_message_and_disables_mentions(self):
        response = MagicMock(status=200)
        response.read.return_value = b'{"id":"123"}'
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(notifier, "read_webhook", return_value=URL), \
             patch.object(notifier, "build_opener", return_value=opener), \
             self.assertLogs(notifier.LOGGER, level="INFO") as logs:
            self.assertEqual({"delivered": 1}, notifier.handler(event("@everyone $551"), None))
        request = opener.open.call_args.args[0]
        self.assertEqual(URL + "?wait=true", request.full_url)
        self.assertEqual("POST", request.method)
        payload = json.loads(request.data)
        self.assertIn("@everyone $551", payload["content"])
        self.assertEqual({"parse": []}, payload["allowed_mentions"])
        self.assertNotIn(URL, " ".join(logs.output))
        self.assertNotIn("$551", " ".join(logs.output))

    def test_long_unicode_message_fits_discord_limit(self):
        result = notifier.discord_payload({"Message": "😀" * 3000})
        self.assertLessEqual(len(result["content"].encode("utf-16-le")) // 2, 2000)
        self.assertTrue(result["content"].endswith("(이하 생략)"))

    def test_unexpected_source_or_empty_record_is_rejected_before_secret_read(self):
        for data in ({}, {"Records": []}, event(topic="other-topic"), event(message="")):
            with self.subTest(data=data), patch.object(notifier, "read_webhook") as read:
                with self.assertRaises(notifier.DeliveryError):
                    notifier.handler(data, None)
                read.assert_not_called()

    def test_http_failures_raise_for_lambda_retries_without_leaking_url(self):
        for code in (301, 400, 401, 404, 429, 500, 503):
            opener = MagicMock()
            opener.open.side_effect = HTTPError(URL, code, URL, {}, None)
            with self.subTest(code=code), patch.object(notifier, "read_webhook", return_value=URL), \
                 patch.object(notifier, "build_opener", return_value=opener), \
                 self.assertLogs(notifier.LOGGER, level="ERROR") as logs:
                try:
                    notifier.handler(event(), None)
                    self.fail("delivery must fail")
                except notifier.DeliveryError:
                    rendered = traceback.format_exc()
                    self.assertIn(f"discord_http_{code}", rendered)
                    self.assertNotIn(URL, rendered)
            self.assertNotIn(URL, " ".join(logs.output))

    def test_sdk_network_and_timeout_errors_are_sanitized(self):
        for target in ("read_webhook", "send"):
            for error in (RuntimeError(URL), URLError(URL), TimeoutError(URL)):
                with self.subTest(target=target, error=type(error)), \
                     patch.object(notifier, "read_webhook", return_value=URL), \
                     patch.object(notifier, target, side_effect=error), \
                     self.assertLogs(notifier.LOGGER, level="ERROR") as logs:
                    try:
                        notifier.handler(event(), None)
                        self.fail("delivery must fail")
                    except notifier.DeliveryError as caught:
                        self.assertEqual("delivery_failed", str(caught))
                        self.assertNotIn(URL, traceback.format_exc())
                self.assertNotIn(URL, " ".join(logs.output))

    def test_missing_confirmation_is_not_success(self):
        for status, body in ((204, b""), (200, b"{}"), (200, b"invalid-json")):
            response = MagicMock(status=status)
            response.read.return_value = body
            response.__enter__.return_value = response
            opener = MagicMock()
            opener.open.return_value = response
            with self.subTest(status=status, body=body), \
                 patch.object(notifier, "read_webhook", return_value=URL), \
                 patch.object(notifier, "build_opener", return_value=opener):
                with self.assertRaises(notifier.DeliveryError):
                    notifier.handler(event(), None)

    def test_secret_is_read_fresh_and_url_is_validated(self):
        sdk = MagicMock()
        modules = {"boto3": sdk, "botocore": MagicMock(), "botocore.config": MagicMock()}
        client = sdk.client.return_value
        with patch.dict(sys.modules, modules):
            client.get_secret_value.return_value = {"SecretString": URL + "\n"}
            self.assertEqual(URL, notifier.read_webhook())
            updated = URL + "-rotated"
            client.get_secret_value.return_value = {"SecretString": updated}
            self.assertEqual(updated, notifier.read_webhook())
            self.assertEqual(2, client.get_secret_value.call_count)
            client.get_secret_value.assert_called_with(SecretId="secret-arn")
            for value in ("", "http://discord.com/api/webhooks/1/token", URL + "?thread_id=1",
                          URL.replace("discord.com", "discord.com.evil.example"),
                          "https://127.0.0.1/private", json.dumps({"url": URL})):
                client.get_secret_value.return_value = {"SecretString": value}
                with self.subTest(value=value), self.assertRaises(notifier.DeliveryError):
                    notifier.read_webhook()

    def test_redirects_are_not_followed(self):
        self.assertIsNone(notifier.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))


if __name__ == "__main__":
    unittest.main()
