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
  alarm_description = each.key == "CredentialAuditHeartbeat" ? "Daily credential audit missing for two daily periods (allow scheduler boundary jitter). Investigate EventBridge/Lambda and stale security measurements; follow docs/aws-credential-rotation.md." : "Credential metadata audit: ${each.key}. Follow docs/aws-credential-rotation.md; never rotate encryption keys blindly."
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
