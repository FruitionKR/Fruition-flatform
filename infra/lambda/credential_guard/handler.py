"""Audit credential metadata only; this function cannot read secret values."""
from datetime import datetime, timezone
import os

import boto3


def age_days(tags, name, created, now):
    value = tags.get(name)
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")) if value else created
        if timestamp.tzinfo is None or timestamp > now:
            return 10000
        return (now - timestamp).total_seconds() / 86400
    except (ValueError, AttributeError, TypeError):
        return 10000


def measurements(summary, devices, policies, secret, now):
    tags = {item["Key"]: item["Value"] for item in secret.get("Tags", [])}
    # Credential-less organization member roots need no newly created password/MFA.
    root_risk = bool(summary.get("AccountAccessKeysPresent", 0)
                     or summary.get("AccountSigningCertificatesPresent", 0)
                     or (summary.get("AccountPasswordPresent", 0) and not summary.get("AccountMFAEnabled", 0)))
    return {
        "RootCredentialsUnprotected": int(root_risk),
        "HumanMfaMissing": int(not devices),
        "HumanDirectAdministratorAccess": int(any(p["PolicyName"] == "AdministratorAccess" for p in policies)),
        "DbCredentialAgeDays": age_days(tags, "fruition:db-credentials-rotated-at", secret.get("CreatedDate"), now),
        "JwtSigningKeyAgeDays": age_days(tags, "fruition:jwt-signing-key-rotated-at", secret.get("CreatedDate"), now),
        "CredentialAuditHeartbeat": 1,
    }


def list_all(iam, operation, result_key, **kwargs):
    """IAM list responses can be truncated even below their requested page size."""
    return [item for page in iam.get_paginator(operation).paginate(**kwargs)
            for item in page[result_key]]


def handler(event, context):
    iam = boto3.client("iam")
    user = os.environ["OPERATOR_USER"]
    values = measurements(
        iam.get_account_summary()["SummaryMap"],
        list_all(iam, "list_mfa_devices", "MFADevices", UserName=user),
        list_all(iam, "list_attached_user_policies", "AttachedPolicies", UserName=user),
        boto3.client("secretsmanager").describe_secret(SecretId=os.environ["APP_SECRET_ARN"]),
        datetime.now(timezone.utc),
    )
    boto3.client("cloudwatch").put_metric_data(Namespace="Fruition/Security", MetricData=[
        {"MetricName": name, "Value": value, "Dimensions": [{"Name": "Project", "Value": os.environ["PROJECT"]}]}
        for name, value in values.items()
    ])
    return {"metrics_published": len(values)}
