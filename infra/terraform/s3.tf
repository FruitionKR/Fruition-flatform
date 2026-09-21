# MinIO 대체. 문서 원본·snapshot·AI 파일 저장 (§8.5).
# 서비스별 IRSA와 object prefix 권한을 사용한다. Access·converter는 S3 권한이 없다.
resource "random_id" "bucket" {
  byte_length = 4
}

resource "aws_s3_bucket" "storage" {
  bucket = "${var.project}-storage-${random_id.bucket.hex}"
}

resource "aws_s3_bucket_versioning" "storage" {
  bucket = aws_s3_bucket.storage.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_kms_key" "storage" {
  description         = "${var.project} storage bucket CMK"
  enable_key_rotation = true
}

resource "aws_kms_alias" "storage" {
  name          = "alias/${var.project}-storage"
  target_key_id = aws_kms_key.storage.key_id
}

resource "aws_s3_bucket_server_side_encryption_configuration" "storage" {
  bucket = aws_s3_bucket.storage.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.storage.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_policy" "storage_tls" {
  bucket = aws_s3_bucket.storage.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.storage.arn, "${aws_s3_bucket.storage.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_s3_bucket_public_access_block" "storage" {
  bucket                  = aws_s3_bucket.storage.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 브라우저는 서명된 multipart PUT로만 임시 PDF를 업로드한다. 공개 읽기 권한을 부여하지 않는다.
resource "aws_s3_bucket_cors_configuration" "document_upload" {
  count  = length(var.document_upload_allowed_origins) > 0 ? 1 : 0
  bucket = aws_s3_bucket.storage.id
  cors_rule {
    allowed_origins = var.document_upload_allowed_origins
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_headers = ["content-type", "range"]
    expose_headers  = ["ETag", "Content-Range", "Accept-Ranges", "Content-Length"]
    max_age_seconds = 300
  }
}

# 임시 파일 lifecycle (tmp/ prefix 7일 후 삭제)
resource "aws_s3_bucket_lifecycle_configuration" "storage" {
  bucket = aws_s3_bucket.storage.id

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "expire-tmp"
    status = "Enabled"
    filter {
      prefix = "tmp/"
    }
    expiration {
      days = 7
    }
    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

locals {
  storage_permissions = {
    document = {
      read   = ["sources/documents/*", "assets/*", "wiki/*", "tmp/document-uploads/*"]
      write  = ["sources/documents/*", "assets/*", "tmp/document-uploads/*"]
      delete = ["sources/documents/*", "assets/*"]
    }
    pipeline = {
      read   = ["sources/documents/*", "wiki/*", "agent-runs/*", "pipeline-runs/*"]
      write  = ["wiki/*", "agent-runs/*", "pipeline-runs/*"]
      delete = ["wiki/*", "agent-runs/*"]
    }
  }
}

module "storage_irsa" {
  for_each         = local.storage_permissions
  source           = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version          = "5.60.0"
  role_name        = "${var.project}-${each.key}-storage"
  role_policy_arns = { storage = aws_iam_policy.storage[each.key].arn }
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["fruition:fruition-${each.key}"]
    }
  }
}

resource "aws_iam_policy" "storage" {
  for_each = local.storage_permissions
  name     = "${var.project}-${each.key}-storage"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = each.key == "document" ? ["s3:GetObject", "s3:GetObjectVersion"] : ["s3:GetObject"], Resource = [for p in each.value.read : "${aws_s3_bucket.storage.arn}/${p}"] },
      { Effect = "Allow", Action = ["s3:PutObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"], Resource = [for p in each.value.write : "${aws_s3_bucket.storage.arn}/${p}"] },
      { Effect = "Allow", Action = ["s3:DeleteObject"], Resource = [for p in each.value.delete : "${aws_s3_bucket.storage.arn}/${p}"] },
      # 없는 객체의 GET을 403 대신 404로 판별해야 AI journal이 신규 생성을 기록한다.
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = [aws_s3_bucket.storage.arn] },
      # SSE-KMS 객체 읽기/쓰기용 — storage CMK에만 한정.
      { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = [aws_kms_key.storage.arn] }
    ]
  })
}
