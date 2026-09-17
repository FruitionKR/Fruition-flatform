# Verified in Seoul for EKS 1.35 on 2026-09-16. Independent of the four core addons.
variable "cloudwatch_addon_version" {
  type    = string
  default = "v6.6.0-eksbuild.1"
}

variable "observability_alb_arn_suffix" {
  description = "After app deployment, set the ALB ARN suffix app/name/id to enable ALB alarms and widgets."
  type        = string
  default     = ""
  validation {
    condition     = var.observability_alb_arn_suffix == "" || can(regex("^app/[A-Za-z0-9-]+/[0-9a-f]+$", var.observability_alb_arn_suffix))
    error_message = "Use the app/name/id ARN suffix, or empty before the ALB exists."
  }
}

resource "aws_cloudwatch_log_group" "containers" {
  for_each          = toset(["application", "host", "dataplane", "performance"])
  name              = "/aws/containerinsights/${var.project}-eks/${each.key}"
  retention_in_days = 14
}

module "cloudwatch_irsa" {
  source           = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version          = "5.60.0"
  role_name        = "${var.project}-cloudwatch-agent"
  role_policy_arns = { agent = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy" }
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["amazon-cloudwatch:cloudwatch-agent", "amazon-cloudwatch:fluent-bit"]
    }
  }
}

resource "aws_eks_addon" "observability" {
  cluster_name                = module.eks.cluster_name
  addon_name                  = "amazon-cloudwatch-observability"
  addon_version               = var.cloudwatch_addon_version
  service_account_role_arn    = module.cloudwatch_irsa.iam_role_arn
  configuration_values        = chomp(file("${path.module}/../observability/addon-config.json"))
  resolve_conflicts_on_create = "NONE"
  resolve_conflicts_on_update = "PRESERVE"
  depends_on                  = [module.eks, aws_cloudwatch_log_group.containers]
}

resource "aws_sns_topic" "operations" {
  name = "${var.project}-operations-alerts"
}

resource "aws_sns_topic_policy" "operations" {
  arn = aws_sns_topic.operations.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudwatch.amazonaws.com" }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.operations.arn
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.budget.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:cloudwatch:${var.region}:${data.aws_caller_identity.budget.account_id}:alarm:${var.project}-ops-*" }
      }
    }]
  })
}

resource "aws_lambda_permission" "operations_sns" {
  statement_id   = "OperationsSNSTopicOnly"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.budget_discord.function_name
  principal      = "sns.amazonaws.com"
  source_arn     = aws_sns_topic.operations.arn
  source_account = data.aws_caller_identity.budget.account_id
}

resource "aws_sns_topic_subscription" "operations" {
  topic_arn      = aws_sns_topic.operations.arn
  protocol       = "lambda"
  endpoint       = aws_lambda_function.budget_discord.arn
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.budget_failures.arn })
  depends_on     = [aws_lambda_permission.operations_sns, aws_lambda_function_event_invoke_config.budget_discord, aws_sqs_queue_policy.budget_failures]
}

locals {
  operations_metrics = merge({
    notification_test = { namespace = "Fruition/Operations", metric = "NotificationTest", dimensions = { Environment = "feedback" }, stat = "Sum", threshold = 0, comparison = "GreaterThanThreshold", periods = 1, missing = "notBreaching" }

    pod_cpu                = { namespace = "ContainerInsights", metric = "pod_cpu_utilization", dimensions = { ClusterName = module.eks.cluster_name, Namespace = "fruition" }, stat = "Maximum", threshold = 80, comparison = "GreaterThanThreshold", periods = 3, missing = "missing" }
    pod_memory             = { namespace = "ContainerInsights", metric = "pod_memory_utilization", dimensions = { ClusterName = module.eks.cluster_name, Namespace = "fruition" }, stat = "Maximum", threshold = 85, comparison = "GreaterThanThreshold", periods = 3, missing = "missing" }
    application_log_volume = { namespace = "AWS/Logs", metric = "IncomingBytes", dimensions = { LogGroupName = aws_cloudwatch_log_group.containers["application"].name }, stat = "Sum", threshold = 104857600, comparison = "GreaterThanThreshold", periods = 1, missing = "notBreaching" }

    node_cpu          = { namespace = "ContainerInsights", metric = "node_cpu_utilization", dimensions = { ClusterName = module.eks.cluster_name }, stat = "Average", threshold = 80, comparison = "GreaterThanThreshold", periods = 3, missing = "missing" }
    node_memory       = { namespace = "ContainerInsights", metric = "node_memory_utilization", dimensions = { ClusterName = module.eks.cluster_name }, stat = "Maximum", threshold = 85, comparison = "GreaterThanThreshold", periods = 3, missing = "missing" }
    failed_nodes      = { namespace = "ContainerInsights", metric = "cluster_failed_node_count", dimensions = { ClusterName = module.eks.cluster_name }, stat = "Maximum", threshold = 0, comparison = "GreaterThanThreshold", periods = 2, missing = "missing" }
    telemetry_missing = { namespace = "ContainerInsights", metric = "node_cpu_utilization", dimensions = { ClusterName = module.eks.cluster_name }, stat = "SampleCount", threshold = 1, comparison = "LessThanThreshold", periods = 3, missing = "breaching" }
    waf_blocked       = { namespace = "AWS/WAFV2", metric = "BlockedRequests", dimensions = { WebACL = aws_wafv2_web_acl.cost_guard.name, Region = var.region, Rule = "ALL" }, stat = "Sum", threshold = 100, comparison = "GreaterThanThreshold", periods = 1, missing = "notBreaching" }
    nat_egress        = { namespace = "AWS/NATGateway", metric = "BytesOutToDestination", dimensions = { NatGatewayId = module.vpc.natgw_ids[0] }, stat = "Sum", threshold = 1073741824, comparison = "GreaterThanThreshold", periods = 1, missing = "notBreaching" }
    redis_memory      = { namespace = "AWS/ElastiCache", metric = "DatabaseMemoryUsagePercentage", dimensions = { CacheClusterId = sort(tolist(aws_elasticache_replication_group.main.member_clusters))[0], CacheNodeId = "0001" }, stat = "Maximum", threshold = 80, comparison = "GreaterThanThreshold", periods = 2, missing = "missing" }
    }, {
    for name, db in { access = aws_db_instance.access, core = aws_db_instance.core } : "rds_${name}_space" => {
      namespace              = "AWS/RDS", metric = "FreeStorageSpace", dimensions = { DBInstanceIdentifier = db.identifier }, stat = "Minimum", threshold = 5368709120, comparison = "LessThanThreshold", periods = 2, missing = "missing"
    }
    }, {
    for name, db in { access = aws_db_instance.access, core = aws_db_instance.core } : "rds_${name}_cpu" => {
      namespace              = "AWS/RDS", metric = "CPUUtilization", dimensions = { DBInstanceIdentifier = db.identifier }, stat = "Average", threshold = 80, comparison = "GreaterThanThreshold", periods = 3, missing = "missing"
    }
    }, var.observability_alb_arn_suffix == "" ? {} : {
    alb_5xx      = { namespace = "AWS/ApplicationELB", metric = "HTTPCode_Target_5XX_Count", dimensions = { LoadBalancer = var.observability_alb_arn_suffix }, stat = "Sum", threshold = 10, comparison = "GreaterThanThreshold", periods = 1, missing = "notBreaching" }
    alb_latency  = { namespace = "AWS/ApplicationELB", metric = "TargetResponseTime", dimensions = { LoadBalancer = var.observability_alb_arn_suffix }, stat = "Average", threshold = 2, comparison = "GreaterThanThreshold", periods = 3, missing = "notBreaching" }
    alb_requests = { namespace = "AWS/ApplicationELB", metric = "RequestCount", dimensions = { LoadBalancer = var.observability_alb_arn_suffix }, stat = "Sum", threshold = 2000, comparison = "GreaterThanThreshold", periods = 1, missing = "notBreaching" }
  })
}

resource "aws_cloudwatch_metric_alarm" "operations" {
  for_each            = local.operations_metrics
  alarm_name          = "${var.project}-ops-${each.key}"
  alarm_description   = "See docs/aws-observability.md: ${each.key}. ALARM and recovery are sent to Discord."
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  dimensions          = each.value.dimensions
  statistic           = each.value.stat
  period              = 300
  evaluation_periods  = each.value.periods
  datapoints_to_alarm = each.value.periods
  threshold           = each.value.threshold
  comparison_operator = each.value.comparison
  treat_missing_data  = each.value.missing
  alarm_actions       = [aws_sns_topic.operations.arn]
  ok_actions          = [aws_sns_topic.operations.arn]
  depends_on          = [aws_sns_topic_policy.operations, aws_sns_topic_subscription.operations]
}

# No SNS actions on notifier-health alarms: avoid a self-amplifying failure loop.
resource "aws_cloudwatch_metric_alarm" "notification_failures" {
  alarm_name          = "${var.project}-ops-discord-delivery-failures"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.budget_failures.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "${var.project}-operations"
  dashboard_body = jsonencode({ widgets = concat(
    [{ type = "log", x = 0, y = 12 + ceil(length(local.operations_metrics) / 3) * 6, width = 24, height = 6, properties = {
      title = "Recent application logs (query scans incur costs)", region = var.region, view = "table",
      query = "SOURCE '/aws/containerinsights/${var.project}-eks/application' | fields @timestamp, kubernetes.namespace_name, kubernetes.pod_name, log | sort @timestamp desc | limit 50"
    } }],
    [{ type = "text", x = 0, y = 0, width = 24, height = 2, properties = { markdown = "# Fruition operations\n5-minute metrics. Logs: 14 days. Discord delivery failures require manual inspection. ALB widgets require observability_alb_arn_suffix. No automatic shutdown." } }],
    [for i, key in sort(keys(local.operations_metrics)) : {
      type = "metric", x = (i % 3) * 8, y = 2 + floor(i / 3) * 6, width = 8, height = 6
      properties = {
        title   = key, region = var.region, period = 300, stat = local.operations_metrics[key].stat, view = "timeSeries"
        metrics = [concat([local.operations_metrics[key].namespace, local.operations_metrics[key].metric], flatten([for k, v in local.operations_metrics[key].dimensions : [k, v]]))]
      }
    }],
    [{ type = "alarm", x = 0, y = 2 + ceil(length(local.operations_metrics) / 3) * 6, width = 24, height = 4, properties = { title = "Alarm states (including Discord failure queue)", alarms = concat([for a in aws_cloudwatch_metric_alarm.operations : a.arn], [aws_cloudwatch_metric_alarm.notification_failures.arn]) } }]
  ) })
}

output "observability" {
  value = {
    dashboard_name       = aws_cloudwatch_dashboard.operations.dashboard_name
    dashboard_url        = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.operations.dashboard_name}"
    operations_topic_arn = aws_sns_topic.operations.arn
    webhook_secret_arn   = aws_secretsmanager_secret.budget_discord.arn
    log_groups           = { for k, g in aws_cloudwatch_log_group.containers : k => g.name }
    alb_alarms_enabled   = var.observability_alb_arn_suffix != ""
  }
}
