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

    def test_operational_alarm_explains_state_and_description_in_korean(self):
        topic = TOPIC.replace("budget", "operations")
        reason = "Threshold Crossed: no datapoints were received for 1 period"
        with patch.dict(os.environ, {"OPERATIONS_TOPIC_ARN": topic}):
            content = notifier.discord_payload({"TopicArn": topic, "Message": json.dumps({
                "AlarmName": "fruition-ops-ai_fx_refresh_failed", "OldStateValue": "INSUFFICIENT_DATA",
                "NewStateValue": "OK", "AlarmDescription": "일일 환율 갱신이 실패했습니다.",
                "NewStateReason": reason})})["content"]
            self.assertIn("상태: 데이터 없음 → 정상", content)
            self.assertIn("설명: 일일 환율 갱신이 실패했습니다.", content)
            self.assertTrue(content.endswith(f"원문 사유: {reason}"))

            content = notifier.discord_payload({"TopicArn": topic, "Message": json.dumps({
                "AlarmName": "fruition-ops-node_cpu", "NewStateValue": "ALARM"})})["content"]
            self.assertIn("상태: 경보", content)
            self.assertNotIn("설명:", content)

    def test_malformed_operational_alarm_fails_before_secret_read(self):
        topic = TOPIC.replace("budget", "operations")
        for message in ("not-json", "[]", "{}", '{"AlarmName":"test","NewStateValue":"invalid"}'):
            with self.subTest(message=message), patch.dict(os.environ, {"OPERATIONS_TOPIC_ARN": topic}), \
                 patch.object(notifier, "read_webhook") as read, self.assertRaises(notifier.DeliveryError):
                notifier.handler(event(message, topic), None)
            read.assert_not_called()

    def test_threshold_evidence_is_explained_in_korean(self):
        topic = TOPIC.replace("budget", "operations")
        with patch.dict(os.environ, {"OPERATIONS_TOPIC_ARN": topic}):
            payload = notifier.discord_payload({"TopicArn": topic, "Message": json.dumps({
                "AlarmName": "fruition-ops-node_cpu", "NewStateValue": "ALARM",
                "AlarmDescription": "노드 CPU 사용률 경보입니다.",
                "NewStateReason": "Threshold Crossed: 3 out of the last 3 datapoints [91.2 (23/10/26 01:00:00)] were greater than the threshold (80.0).",
                "Trigger": {"MetricName": "node_cpu_utilization", "Threshold": 80,
                            "ComparisonOperator": "GreaterThanThreshold", "Period": 300,
                            "EvaluationPeriods": 3, "DatapointsToAlarm": 2}})})
        content = payload["content"]
        self.assertIn("측정값이 설정된 경보 조건을 충족", content)
        self.assertIn("node_cpu_utilization 값이 80 초과", content)
        self.assertIn("300초씩 최근 3구간 중 2구간", content)
        self.assertIn("측정값(시각): 91.2 (23/10/26 01:00:00)", content)
        self.assertIn("실제 장애 원인은 관련 로그·자원 상태를 확인", content)

    def test_missing_data_ok_does_not_claim_actual_recovery(self):
        reason = ("Threshold Crossed: no datapoints were received for 1 period and "
                  "1 missing datapoint was treated as [NonBreaching].")
        for trigger in (None, {"TreatMissingData": "breaching"}, {"TreatMissingData": "ignore"},
                        {"TreatMissingData": "missing"}, {"TreatMissingData": "unknown"},
                        {"TreatMissingData": ["notBreaching"]}):
            with self.subTest(trigger=trigger):
                summary = notifier.alarm_diagnosis({"NewStateValue": "OK", "NewStateReason": reason, "Trigger": trigger})
                self.assertIn("측정 데이터가 누락", summary)
                self.assertIn("실제 복구 여부는 추가 확인", summary)

    def test_not_breaching_ok_explains_policy_without_claiming_recovery(self):
        summary = notifier.alarm_diagnosis({
            "NewStateValue": "OK", "Trigger": {"TreatMissingData": "notBreaching"},
            "NewStateReason": "Threshold Crossed: no datapoints were received for 1 period and "
                              "1 missing datapoint was treated as [NonBreaching]."})
        self.assertIn("누락 데이터를 임계값 미초과로 처리하도록 설정되어 정상으로 판정", summary)
        self.assertIn("누락 데이터 처리: notBreaching (임계값 미초과로 처리)", summary)
        for claim in ("0건", "복구됐", "복구 완료", "추가 확인이 필요"):
            self.assertNotIn(claim, summary)

    def test_missing_data_alarm_does_not_blame_gap_alone(self):
        for policy, label in (("breaching", "임계값 초과로 처리"), ("missing", "전부 누락 시 데이터 없음 상태"),
                              ("ignore", "현재 상태 유지"), ("notBreaching", "임계값 미초과로 처리")):
            with self.subTest(policy=policy):
                summary = notifier.alarm_diagnosis({
                    "NewStateValue": "ALARM", "Trigger": {"TreatMissingData": policy},
                    "NewStateReason": "Threshold Crossed: no datapoints were received for 3 periods and "
                                      "3 missing datapoints were treated as [Breaching]."})
                self.assertIn("누락만으로 경보가 됐는지는 이 이벤트로 단정할 수 없으니", summary)
                self.assertIn(f"누락 데이터 처리: {policy} ({label})", summary)
        summary = notifier.alarm_diagnosis({"NewStateValue": "ALARM", "NewStateReason": "no datapoints"})
        self.assertNotIn("누락 데이터 처리:", summary)

    def test_range_without_datapoints_to_alarm_does_not_assume_n_of_n(self):
        trigger = {"MetricName": "BlockedRequests", "Threshold": 100.0, "ComparisonOperator": "GreaterThanThreshold",
                   "Period": 300, "EvaluationPeriods": 3}
        summary = notifier.alarm_diagnosis({"NewStateValue": "ALARM", "Trigger": trigger})
        self.assertIn("평가 범위: 300초씩 최근 3구간\n", summary)
        self.assertNotIn("구간 중", summary)

    def test_malformed_optional_metadata_still_delivers_core_alarm(self):
        topic = TOPIC.replace("budget", "operations")
        response = MagicMock(status=200)
        response.read.return_value = b'{"id":"123"}'
        response.__enter__.return_value = response
        for trigger in ({"ComparisonOperator": [], "Threshold": 80}, {"ComparisonOperator": {}, "Threshold": 80},
                        {"ComparisonOperator": "GreaterThanThreshold", "Threshold": [80], "MetricName": {},
                         "Period": "300", "EvaluationPeriods": True, "TreatMissingData": {}}, "trigger"):
            opener = MagicMock()
            opener.open.return_value = response
            message = json.dumps({"AlarmName": "fruition-ops-node_cpu", "NewStateValue": "ALARM",
                                  "OldStateValue": ["OK"], "Trigger": trigger,
                                  "NewStateReason": "Threshold Crossed: no datapoints were received"})
            with self.subTest(trigger=trigger), patch.dict(os.environ, {"OPERATIONS_TOPIC_ARN": topic}), \
                 patch.object(notifier, "read_webhook", return_value=URL), \
                 patch.object(notifier, "build_opener", return_value=opener):
                self.assertEqual({"delivered": 1}, notifier.handler(event(message, topic), None))
                content = json.loads(opener.open.call_args.args[0].data)["content"]
                self.assertIn("AWS 운영 경보 [ALARM]\nfruition-ops-node_cpu\n상태: 경보\n", content)
                self.assertNotIn("경보 조건:", content)
                self.assertNotIn("누락 데이터 처리:", content)

    def test_unknown_and_insufficient_data_do_not_invent_evidence(self):
        for trigger in (None, {}, {"Metrics": []}):
            with self.subTest(trigger=trigger):
                summary = notifier.alarm_diagnosis({"NewStateValue": "ALARM", "Trigger": trigger})
                self.assertIn("상세 발생 원인은 추가 확인", summary)
                self.assertNotIn("경보 조건:", summary)
        self.assertIn("측정 데이터가 부족", notifier.alarm_diagnosis({"NewStateValue": "INSUFFICIENT_DATA"}))

    def test_recovery_and_all_threshold_operators(self):
        for operator, label in notifier.COMPARISONS.items():
            with self.subTest(operator=operator):
                summary = notifier.alarm_diagnosis({"NewStateValue": "OK", "Trigger": {
                    "ComparisonOperator": operator, "Threshold": 0}})
                self.assertIn(f"값이 0 {label}", summary)
                self.assertIn("경보 조건을 충족하지 않아", summary)
                self.assertNotIn("원인 확인:", summary)

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
