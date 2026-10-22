# The ALB belongs to AWS Load Balancer Controller. Terraform owns only its log
# destination; the Ingress annotation enables delivery after this bucket exists.
locals {
  alb_access_logs_prefix = "alb"
}

resource "aws_s3_bucket" "alb_access_logs" {
  bucket = "${var.project}-alb-access-logs-${data.aws_caller_identity.budget.account_id}-${var.region}"
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "alb_access_logs" {
  bucket = aws_s3_bucket.alb_access_logs.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "alb_access_logs" {
  bucket                  = aws_s3_bucket.alb_access_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Traditional ALB S3 access logging supports SSE-S3, not the app bucket's KMS key.
resource "aws_s3_bucket_server_side_encryption_configuration" "alb_access_logs" {
  bucket = aws_s3_bucket.alb_access_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "alb_access_logs" {
  bucket = aws_s3_bucket.alb_access_logs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowALBLogDelivery"
        Effect    = "Allow"
        Principal = { Service = "logdelivery.elasticloadbalancing.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.alb_access_logs.arn}/${local.alb_access_logs_prefix}/AWSLogs/${data.aws_caller_identity.budget.account_id}/*"
        Condition = { ArnLike = { "aws:SourceArn" = "arn:aws:elasticloadbalancing:${var.region}:${data.aws_caller_identity.budget.account_id}:loadbalancer/*" } }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.alb_access_logs.arn, "${aws_s3_bucket.alb_access_logs.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "alb_access_logs" {
  bucket = aws_s3_bucket.alb_access_logs.id
  rule {
    id     = "expire-access-logs"
    status = "Enabled"
    filter {
      prefix = "${local.alb_access_logs_prefix}/AWSLogs/"
    }
    expiration {
      days = 30
    }
  }
  # evidence/ is deliberately outside the expiration prefix.
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

output "alb_access_logs" {
  description = "Create this destination before deploying the Ingress logging annotation. Raw logs contain URL queries and client IPs."
  value = {
    bucket         = aws_s3_bucket.alb_access_logs.id
    prefix         = local.alb_access_logs_prefix
    retention_days = 30
  }
  depends_on = [aws_s3_bucket_policy.alb_access_logs, aws_s3_bucket_public_access_block.alb_access_logs]
}

# Deployment preflight reads destination metadata only, never log objects.
resource "aws_iam_role_policy" "github_deploy_alb_logs" {
  name = "alb-log-destination-check"
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetBucketLocation", "s3:GetBucketPolicyStatus"]
      Resource = aws_s3_bucket.alb_access_logs.arn
    }]
  })
}
