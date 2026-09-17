# Account-wide actual USD spend. No application deployment dependency.
data "aws_caller_identity" "budget" {}

resource "aws_budgets_budget" "monthly" {
  for_each = toset(["400", "550", "650"])

  name         = "${var.project}-monthly-${each.value}"
  budget_type  = "COST"
  limit_amount = each.value
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.budget.arn]
  }
  depends_on = [aws_sns_topic_policy.budget, aws_sns_topic_subscription.budget]
}

resource "aws_sns_topic" "budget" {
  name = "${var.project}-budget-alerts"
}

resource "aws_sns_topic_policy" "budget" {
  arn = aws_sns_topic.budget.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "budgets.amazonaws.com" }
      Action    = "SNS:Publish"
      Resource  = aws_sns_topic.budget.arn
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.budget.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:budgets::${data.aws_caller_identity.budget.account_id}:budget/${var.project}-monthly-*" }
      }
    }]
  })
}

# Terraform owns only the empty container. Set raw SecretString outside Terraform.
resource "aws_secretsmanager_secret" "budget_discord" {
  name        = "${var.project}/budget-discord-webhook"
  description = "Discord budget webhook URL (raw SecretString, entered outside Terraform)"
}

resource "aws_sqs_queue" "budget_failures" {
  name                      = "${var.project}-budget-alert-failures"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

# Also retain SNS -> Lambda delivery failures, before Lambda accepts an event.
resource "aws_sqs_queue_policy" "budget_failures" {
  queue_url = aws_sqs_queue.budget_failures.url
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "sns.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.budget_failures.arn
      Condition = {
        ArnEquals    = { "aws:SourceArn" = [aws_sns_topic.budget.arn, aws_sns_topic.operations.arn] }
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.budget.account_id }
      }
    }]
  })
}

resource "aws_iam_role" "budget_discord" {
  name = "${var.project}-budget-discord"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_cloudwatch_log_group" "budget_discord" {
  name              = "/aws/lambda/${var.project}-budget-discord"
  retention_in_days = 14
}

resource "aws_iam_role_policy" "budget_discord" {
  role = aws_iam_role.budget_discord.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.budget_discord.arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.budget_discord.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.budget_failures.arn
      }
    ]
  })
}

data "archive_file" "budget_discord" {
  type        = "zip"
  source_file = "${path.module}/../lambda/budget_discord/handler.py"
  output_path = "${path.module}/.terraform/budget-discord.zip"
}

# No VPC attachment, NAT gateway, provisioned concurrency or function URL.
resource "aws_lambda_function" "budget_discord" {
  function_name    = "${var.project}-budget-discord"
  role             = aws_iam_role.budget_discord.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.budget_discord.output_path
  source_code_hash = data.archive_file.budget_discord.output_base64sha256
  memory_size      = 128
  timeout          = 20
  environment {
    variables = {
      WEBHOOK_SECRET_ARN   = aws_secretsmanager_secret.budget_discord.arn
      SNS_TOPIC_ARN        = aws_sns_topic.budget.arn
      OPERATIONS_TOPIC_ARN = aws_sns_topic.operations.arn
    }
  }
  depends_on = [aws_iam_role_policy.budget_discord]
}

resource "aws_lambda_function_event_invoke_config" "budget_discord" {
  function_name                = aws_lambda_function.budget_discord.function_name
  maximum_event_age_in_seconds = 3600
  maximum_retry_attempts       = 2
  destination_config {
    on_failure {
      destination = aws_sqs_queue.budget_failures.arn
    }
  }
}

resource "aws_lambda_permission" "budget_sns" {
  statement_id   = "BudgetSNSTopicOnly"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.budget_discord.function_name
  principal      = "sns.amazonaws.com"
  source_arn     = aws_sns_topic.budget.arn
  source_account = data.aws_caller_identity.budget.account_id
}

resource "aws_sns_topic_subscription" "budget" {
  topic_arn      = aws_sns_topic.budget.arn
  protocol       = "lambda"
  endpoint       = aws_lambda_function.budget_discord.arn
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.budget_failures.arn })
  depends_on     = [aws_lambda_permission.budget_sns, aws_lambda_function_event_invoke_config.budget_discord, aws_sqs_queue_policy.budget_failures]
}
