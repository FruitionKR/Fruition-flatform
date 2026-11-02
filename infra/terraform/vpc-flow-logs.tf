# Direct S3 delivery retains ACCEPT and REJECT evidence without CloudWatch Logs ingestion.
resource "aws_s3_bucket" "vpc_flow_logs" {
  bucket = "${var.project}-vpc-flow-logs-${data.aws_caller_identity.budget.account_id}-${var.region}"
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "vpc_flow_logs" {
  bucket = aws_s3_bucket.vpc_flow_logs.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "vpc_flow_logs" {
  bucket                  = aws_s3_bucket.vpc_flow_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "vpc_flow_logs" {
  bucket = aws_s3_bucket.vpc_flow_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "vpc_flow_logs" {
  bucket = aws_s3_bucket.vpc_flow_logs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AWSLogDeliveryWrite"
        Effect    = "Allow"
        Principal = { Service = "delivery.logs.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.vpc_flow_logs.arn}/flow/AWSLogs/${data.aws_caller_identity.budget.account_id}/*"
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.budget.account_id, "s3:x-amz-acl" = "bucket-owner-full-control" }
          ArnLike      = { "aws:SourceArn" = "arn:aws:logs:${var.region}:${data.aws_caller_identity.budget.account_id}:*" }
        }
      },
      {
        Sid       = "AWSLogDeliveryAclCheck"
        Effect    = "Allow"
        Principal = { Service = "delivery.logs.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.vpc_flow_logs.arn
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.budget.account_id }
          ArnLike      = { "aws:SourceArn" = "arn:aws:logs:${var.region}:${data.aws_caller_identity.budget.account_id}:*" }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.vpc_flow_logs.arn, "${aws_s3_bucket.vpc_flow_logs.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "vpc_flow_logs" {
  bucket = aws_s3_bucket.vpc_flow_logs.id
  rule {
    id     = "expire-flow-logs"
    status = "Enabled"
    filter {
      prefix = "flow/AWSLogs/"
    }
    expiration {
      days = 14
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Separate resource allows delivery verification before retiring the old flow log.
resource "aws_flow_log" "vpc_s3" {
  vpc_id                   = module.vpc.vpc_id
  traffic_type             = "ALL"
  log_destination_type     = "s3"
  log_destination          = "${aws_s3_bucket.vpc_flow_logs.arn}/flow/"
  max_aggregation_interval = 60
  destination_options {
    file_format                = "plain-text"
    hive_compatible_partitions = false
    per_hour_partition         = true
  }
  depends_on = [aws_s3_bucket_policy.vpc_flow_logs, aws_s3_bucket_public_access_block.vpc_flow_logs,
    aws_s3_bucket_ownership_controls.vpc_flow_logs, aws_s3_bucket_server_side_encryption_configuration.vpc_flow_logs,
  aws_s3_bucket_lifecycle_configuration.vpc_flow_logs]
}

output "vpc_flow_logs" {
  value = {
    bucket         = aws_s3_bucket.vpc_flow_logs.id
    prefix         = "flow/AWSLogs/"
    retention_days = 14
  }
}

# Keep historical CloudWatch evidence until its existing 14-day expiry.
# Migration does not delete or recreate this log group.
moved {
  from = module.vpc.aws_cloudwatch_log_group.flow_log[0]
  to   = aws_cloudwatch_log_group.vpc_flow_legacy
}

resource "aws_cloudwatch_log_group" "vpc_flow_legacy" {
  name              = "/aws/vpc-flow-log/${module.vpc.vpc_id}"
  retention_in_days = 14
  lifecycle {
    prevent_destroy = true
  }
}
