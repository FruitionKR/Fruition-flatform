# Opt-in after the application ALB exists. This controller runs outside EKS.
variable "request_wake_enabled" {
  type    = bool
  default = false
}

variable "request_wake_alb_arn_suffix" {
  description = "Existing application ALB ARN suffix used to detect requests during sleep."
  type        = string
  default     = ""
}

locals {
  request_wake_groups = {
    for key in ["general", "ai_worker"] : key => split(":", module.eks.eks_managed_node_groups[key].node_group_id)[1]
  }
  request_wake_asgs = flatten([
    for key in ["general", "ai_worker"] : module.eks.eks_managed_node_groups[key].node_group_autoscaling_group_names
  ])
}

resource "aws_dynamodb_table" "request_wake" {
  count        = var.request_wake_enabled ? 1 : 0
  name         = "${var.project}-request-wake"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"
  attribute {
    name = "id"
    type = "S"
  }
  server_side_encryption { enabled = true }
}

resource "aws_iam_role" "request_wake" {
  count = var.request_wake_enabled ? 1 : 0
  name  = "${var.project}-request-wake"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_cloudwatch_log_group" "request_wake" {
  count             = var.request_wake_enabled ? 1 : 0
  name              = "/aws/lambda/${var.project}-request-wake"
  retention_in_days = 14
}

resource "aws_iam_role_policy" "request_wake" {
  count = var.request_wake_enabled ? 1 : 0
  role  = aws_iam_role.request_wake[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow", Action = ["eks:DescribeNodegroup", "eks:UpdateNodegroupConfig"]
        Resource = [for key in ["general", "ai_worker"] : module.eks.eks_managed_node_groups[key].node_group_arn]
      },
      {
        Effect   = "Allow", Action = ["autoscaling:SuspendProcesses", "autoscaling:ResumeProcesses"]
        Resource = [for name in local.request_wake_asgs : "arn:aws:autoscaling:${var.region}:${data.aws_caller_identity.budget.account_id}:autoScalingGroup:*:autoScalingGroupName/${name}"]
      },
      {
        # These read APIs do not support resource-level permissions.
        Effect = "Allow", Action = ["autoscaling:DescribeAutoScalingGroups", "cloudwatch:GetMetricStatistics"], Resource = "*"
      },
      {
        Effect   = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = aws_dynamodb_table.request_wake[0].arn
      },
      {
        Effect   = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.request_wake[0].arn}:*"
      }
    ]
  })
}

data "archive_file" "request_wake" {
  count       = var.request_wake_enabled ? 1 : 0
  type        = "zip"
  source_file = "${path.module}/../lambda/request_wake/handler.py"
  output_path = "${path.module}/.terraform/request-wake.zip"
}

resource "aws_lambda_function" "request_wake" {
  count                          = var.request_wake_enabled ? 1 : 0
  function_name                  = "${var.project}-request-wake"
  role                           = aws_iam_role.request_wake[0].arn
  runtime                        = "python3.12"
  handler                        = "handler.handler"
  filename                       = data.archive_file.request_wake[0].output_path
  source_code_hash               = data.archive_file.request_wake[0].output_base64sha256
  memory_size                    = 128
  timeout                        = 55
  reserved_concurrent_executions = 1
  environment {
    variables = {
      CLUSTER_NAME = module.eks.cluster_name
      # Strip the cluster prefix from the module's cluster:nodegroup output.
      NODE_GROUPS = jsonencode(local.request_wake_groups)
      STATE_TABLE = aws_dynamodb_table.request_wake[0].name
      ALB_SUFFIX  = var.request_wake_alb_arn_suffix
    }
  }
  lifecycle {
    precondition {
      condition     = can(regex("^app/[A-Za-z0-9-]+/[0-9a-f]+$", var.request_wake_alb_arn_suffix))
      error_message = "Request wake requires the existing application ALB suffix."
    }
  }
  depends_on = [aws_iam_role_policy.request_wake]
}

resource "aws_cloudwatch_event_rule" "request_wake" {
  count               = var.request_wake_enabled ? 1 : 0
  name                = "${var.project}-request-wake"
  schedule_expression = "rate(1 minute)"
}

resource "aws_lambda_permission" "request_wake" {
  count          = var.request_wake_enabled ? 1 : 0
  statement_id   = "RequestWakeSchedulerOnly"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.request_wake[0].function_name
  principal      = "events.amazonaws.com"
  source_arn     = aws_cloudwatch_event_rule.request_wake[0].arn
  source_account = data.aws_caller_identity.budget.account_id
}

resource "aws_cloudwatch_event_target" "request_wake" {
  count = var.request_wake_enabled ? 1 : 0
  rule  = aws_cloudwatch_event_rule.request_wake[0].name
  arn   = aws_lambda_function.request_wake[0].arn
  input = jsonencode({ action = "tick" })
  retry_policy {
    maximum_event_age_in_seconds = 60
    maximum_retry_attempts       = 0
  }
  depends_on = [aws_lambda_permission.request_wake]
}

resource "aws_lambda_function_event_invoke_config" "request_wake" {
  count                        = var.request_wake_enabled ? 1 : 0
  function_name                = aws_lambda_function.request_wake[0].function_name
  maximum_event_age_in_seconds = 60
  maximum_retry_attempts       = 0
}

resource "aws_cloudwatch_metric_alarm" "request_wake_errors" {
  count               = var.request_wake_enabled ? 1 : 0
  alarm_name          = "${var.project}-ops-request-wake-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.request_wake[0].function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.operations.arn]
  ok_actions          = [aws_sns_topic.operations.arn]
}

output "request_wake" {
  value = var.request_wake_enabled ? {
    function_name = aws_lambda_function.request_wake[0].function_name
    state_table   = aws_dynamodb_table.request_wake[0].name
  } : null
}
