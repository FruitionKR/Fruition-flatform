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
STATE_LABELS = {"ALARM": "경보", "OK": "정상", "INSUFFICIENT_DATA": "데이터 없음"}
COMPARISONS = {
    "GreaterThanThreshold": "초과", "GreaterThanOrEqualToThreshold": "이상",
    "LessThanThreshold": "미만", "LessThanOrEqualToThreshold": "이하",
}


def alarm_diagnosis(alarm):
    """Explain evidence in the event, without inventing a root cause."""
    state = alarm["NewStateValue"]
    reason = str(alarm.get("NewStateReason") or "")
    trigger = alarm.get("Trigger")
    trigger = trigger if isinstance(trigger, dict) else {}
    missing = re.search(r"no datapoints|missing datapoints?|datapoints? (?:was|were) unknown", reason, re.I)
    if state == "INSUFFICIENT_DATA":
        summary = "판정에 필요한 측정 데이터가 부족합니다."
    elif missing:
        summary = ("경보 판정에 측정 데이터 누락이 포함되어 있습니다. 수집 상태와 누락 데이터 처리 설정을 확인하세요." if state == "ALARM" else
                   "측정 데이터가 누락된 상태에서 정상으로 판정됐습니다. 실제 복구 여부는 추가 확인이 필요합니다.")
    elif state == "OK":
        summary = "현재 경보 조건을 충족하지 않아 정상 상태로 전환됐습니다."
    elif "Threshold Crossed" in reason:
        summary = "측정값이 설정된 경보 조건을 충족했습니다."
    else:
        summary = "경보 상태로 전환됐습니다. 상세 발생 원인은 추가 확인이 필요합니다."
    lines = [f"판정 사유: {summary}"]
    comparison = COMPARISONS.get(trigger.get("ComparisonOperator"))
    if comparison and trigger.get("Threshold") is not None:
        lines.append(f"경보 조건: {trigger.get('MetricName', '계산 지표')} 값이 {trigger['Threshold']} {comparison}")
        if trigger.get("Period") and trigger.get("EvaluationPeriods"):
            periods = trigger["EvaluationPeriods"]
            lines.append(f"평가 범위: {trigger['Period']}초씩 최근 {periods}구간 중 "
                         f"{trigger.get('DatapointsToAlarm', periods)}구간")
    # CloudWatch includes evaluated values followed by timestamps in brackets.
    values = re.search(r"datapoints?\s*\[([^\]]+)\]", reason, re.I)
    if values:
        lines.append(f"판정에 사용된 측정값(시각): {values.group(1)[:300]}")
    if state == "ALARM":
        lines.append("원인 확인: 이 알림은 경보 판정 근거입니다. 실제 장애 원인은 관련 로그·자원 상태를 확인해야 합니다.")
    return "\n".join(lines)


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
        # Explain the event in Korean; retain AWS's original evidence last.
        transition = STATE_LABELS[state]
        if alarm.get("OldStateValue") in STATE_LABELS:
            transition = f"{STATE_LABELS[alarm['OldStateValue']]} → {transition}"
        description = f"설명: {alarm['AlarmDescription']}\n" if alarm.get("AlarmDescription") else ""
        content = (f"AWS 운영 {title} [{state}]\n{alarm['AlarmName']}\n"
                   f"상태: {transition}\n{alarm_diagnosis(alarm)}\n{description}"
                   f"계정: {alarm.get('AWSAccountId', 'unknown')}\n"
                   f"시각: {alarm.get('StateChangeTime', 'unknown')}\n"
                   f"원문 사유: {alarm.get('NewStateReason', 'unknown')}")
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
