resource "aws_iam_role" "credential_guard" {
  count = var.human_operator_user_name == "" ? 0 : 1
  name  = "${var.project}-credential-guard"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_cloudwatch_log_group" "credential_guard" {
  count             = var.human_operator_user_name == "" ? 0 : 1
  name              = "/aws/lambda/${var.project}-credential-guard"
  retention_in_days = 14
}

resource "aws_iam_role_policy" "credential_guard" {
  count = var.human_operator_user_name == "" ? 0 : 1
  role  = aws_iam_role.credential_guard[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = "secretsmanager:DescribeSecret", Resource = aws_secretsmanager_secret.app.arn },
      { Effect = "Allow", Action = "iam:GetAccountSummary", Resource = "*" },
      { Effect = "Allow", Action = ["iam:ListMFADevices", "iam:ListAttachedUserPolicies"], Resource = local.human_operator_arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.credential_guard[0].arn}:*" },
      { Effect = "Allow", Action = "cloudwatch:PutMetricData", Resource = "*", Condition = { StringEquals = { "cloudwatch:namespace" = "Fruition/Security" } } }
    ]
  })
}

data "archive_file" "credential_guard" {
  type        = "zip"
  source_file = "${path.module}/../lambda/credential_guard/handler.py"
  output_path = "${path.module}/.terraform/credential-guard.zip"
}

resource "aws_lambda_function" "credential_guard" {
  count            = var.human_operator_user_name == "" ? 0 : 1
  function_name    = "${var.project}-credential-guard"
  role             = aws_iam_role.credential_guard[0].arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.credential_guard.output_path
  source_code_hash = data.archive_file.credential_guard.output_base64sha256
  memory_size      = 128
  timeout          = 30
  environment {
    variables = {
      APP_SECRET_ARN = aws_secretsmanager_secret.app.arn
      OPERATOR_USER  = var.human_operator_user_name
      PROJECT        = var.project
    }
  }
  depends_on = [aws_iam_role_policy.credential_guard]
}

resource "aws_cloudwatch_event_rule" "credential_guard" {
  count               = var.human_operator_user_name == "" ? 0 : 1
  name                = "${var.project}-credential-audit-daily"
  schedule_expression = "rate(1 day)"
}

resource "aws_cloudwatch_event_target" "credential_guard" {
  count = var.human_operator_user_name == "" ? 0 : 1
  rule  = aws_cloudwatch_event_rule.credential_guard[0].name
  arn   = aws_lambda_function.credential_guard[0].arn
}

resource "aws_lambda_permission" "credential_guard" {
  count          = var.human_operator_user_name == "" ? 0 : 1
  statement_id   = "ScheduledCredentialMetadataAudit"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.credential_guard[0].function_name
  principal      = "events.amazonaws.com"
  source_arn     = aws_cloudwatch_event_rule.credential_guard[0].arn
  source_account = data.aws_caller_identity.budget.account_id
}

locals {
  credential_guard_metrics = {
    RootCredentialsUnprotected     = { threshold = 0, comparison = "GreaterThanThreshold" }
    HumanMfaMissing                = { threshold = 0, comparison = "GreaterThanThreshold" }
    HumanDirectAdministratorAccess = { threshold = 0, comparison = "GreaterThanThreshold" }
    DbCredentialAgeDays            = { threshold = 90, comparison = "GreaterThanThreshold" }
    JwtSigningKeyAgeDays           = { threshold = 90, comparison = "GreaterThanThreshold" }
    CredentialAuditHeartbeat       = { threshold = 1, comparison = "LessThanThreshold" }
  }
}

resource "aws_cloudwatch_metric_alarm" "credential_guard" {
  for_each          = var.human_operator_user_name == "" ? {} : local.credential_guard_metrics
  alarm_name        = "${var.project}-ops-security-${each.key}"
  alarm_description = "${lookup({ RootCredentialsUnprotected = "루트 계정에 액세스 키·서명 인증서가 있거나 MFA 없는 비밀번호가 있습니다. 루트 자격 증명을 제거하거나 MFA를 설정하세요.", HumanMfaMissing = "운영자 IAM 사용자에 MFA 장치가 없습니다. MFA 장치 등록 여부를 확인하세요.", HumanDirectAdministratorAccess = "운영자 IAM 사용자에 AdministratorAccess 정책이 직접 연결되어 있습니다. 연결된 정책과 변경 이력(CloudTrail)을 확인하세요.", DbCredentialAgeDays = "DB 자격 증명이 90일 넘게 교체되지 않았습니다(교체 시각 태그가 없거나 잘못돼도 경보). Secrets Manager 태그와 교체 이력을 확인하세요.", JwtSigningKeyAgeDays = "JWT 서명 키가 90일 넘게 교체되지 않았습니다(교체 시각 태그가 없거나 잘못돼도 경보). Secrets Manager 태그와 교체 이력을 확인하세요.", CredentialAuditHeartbeat = "일일 자격 증명 점검 결과가 이틀 연속 들어오지 않아 다른 보안 지표가 오래된 값일 수 있습니다. EventBridge 규칙과 Lambda 실행·오류 로그를 확인하세요." }, each.key, "자격 증명 메타데이터 점검 경보: ${each.key}.")} 확인 절차: docs/aws-credential-rotation.md. 암호화 키는 영향 확인 없이 교체하지 마세요."
  namespace         = "Fruition/Security"
  metric_name       = each.key
  dimensions        = { Project = var.project }
  statistic         = "Maximum"
  period            = 86400
  # Two daily heartbeat periods tolerate a scheduled run crossing a UTC boundary.
  # Risk metrics report their last observed state; only heartbeat pages on silence.
  evaluation_periods  = each.key == "CredentialAuditHeartbeat" ? 2 : 1
  datapoints_to_alarm = each.key == "CredentialAuditHeartbeat" ? 2 : 1
  threshold           = each.value.threshold
  comparison_operator = each.value.comparison
  treat_missing_data  = each.key == "CredentialAuditHeartbeat" ? "breaching" : "ignore"
  alarm_actions       = [aws_sns_topic.operations.arn]
  ok_actions          = [aws_sns_topic.operations.arn]
  depends_on          = [aws_sns_topic_policy.operations]
}
