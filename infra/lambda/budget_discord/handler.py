"""Forward trusted budget/CloudWatch SNS events without logging secrets/payloads."""

import json
import logging
import os
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
WEBHOOK = re.compile(r"https://discord\.com/api(?:/v[0-9]+)?/webhooks/[0-9]+/[A-Za-z0-9_-]+")


class DeliveryError(RuntimeError):
    """Safe error text only: Lambda records unhandled exceptions."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_webhook():
    # boto3 is provided by the AWS Python runtime; offline tests mock the SDK.
    import boto3
    from botocore.config import Config

    client = boto3.client("secretsmanager", config=Config(
        connect_timeout=2, read_timeout=2, retries={"total_max_attempts": 2}))
    value = client.get_secret_value(SecretId=os.environ["WEBHOOK_SECRET_ARN"])
    url = value["SecretString"].strip()
    if not WEBHOOK.fullmatch(url):
        raise DeliveryError("invalid_webhook_secret")
    return url


def discord_payload(sns):
    message = sns.get("Message")
    if not isinstance(message, str) or not message.strip():
        raise DeliveryError("invalid_sns_message")
    if sns.get("TopicArn") == os.environ.get("OPERATIONS_TOPIC_ARN") and os.environ.get("OPERATIONS_TOPIC_ARN"):
        try:
            alarm = json.loads(message)
        except (ValueError, TypeError):
            raise DeliveryError("invalid_cloudwatch_message") from None
        if not isinstance(alarm, dict) or alarm.get("NewStateValue") not in ("ALARM", "OK", "INSUFFICIENT_DATA") or not alarm.get("AlarmName"):
            raise DeliveryError("invalid_cloudwatch_message")
        state = alarm["NewStateValue"]
        title = "복구" if state == "OK" else "경보"
        content = (f"AWS 운영 {title} [{state}]\n{alarm['AlarmName']}\n"
                   f"계정: {alarm.get('AWSAccountId', 'unknown')}\n"
                   f"시각: {alarm.get('StateChangeTime', 'unknown')}\n"
                   f"사유: {alarm.get('NewStateReason', 'unknown')}")
    else:
        # Budget notifications contain text, not a guaranteed JSON schema.
        content = "AWS 예산 알림\n" + str(sns.get("Subject") or "Budget notification") + "\n\n" + message
    encoded = content.encode("utf-16-le")
    if len(encoded) > 3800:
        content = encoded[:3800].decode("utf-16-le", errors="ignore") + "\n… (이하 생략)"
    return {"content": content, "allowed_mentions": {"parse": []}}


def send(url, payload):
    request = Request(url + "?wait=true", data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json", "User-Agent": "FruitionBudgetNotifier/1.0"},
                      method="POST")
    try:
        with build_opener(NoRedirect()).open(request, timeout=5) as response:
            if response.status != 200:
                raise DeliveryError("unexpected_discord_status")
            # wait=true confirms a saved message. Never log the response body.
            body = json.loads(response.read(65536))
            if not isinstance(body, dict) or not body.get("id"):
                raise DeliveryError("missing_discord_confirmation")
    except HTTPError as error:
        # Let Lambda's async retries handle failures, including 429 and 5xx.
        code = error.code
        error.close()
        raise DeliveryError(f"discord_http_{code}") from None


def handler(event, context):
    try:
        records = event.get("Records", [])
        if len(records) != 1:
            raise DeliveryError("expected_one_sns_record")
        record = records[0]
        sns = record["Sns"]
        allowed_topics = {os.environ["SNS_TOPIC_ARN"]}
        if os.environ.get("OPERATIONS_TOPIC_ARN"):
            allowed_topics.add(os.environ["OPERATIONS_TOPIC_ARN"])
        if record.get("EventSource") != "aws:sns" or sns.get("TopicArn") not in allowed_topics:
            raise DeliveryError("unexpected_sns_source")
        payload = discord_payload(sns)
        url = read_webhook()
        send(url, payload)
    except Exception as error:
        # SDK/HTTP exceptions may contain the webhook URL. Never propagate them.
        reason = str(error) if isinstance(error, DeliveryError) else "delivery_failed"
        LOGGER.error("budget_notification_failed reason=%s", reason)
        raise DeliveryError(reason) from None
    LOGGER.info("budget_notification_delivered")
    return {"delivered": 1}
