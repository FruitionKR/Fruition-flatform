# WAF needs only this field. Never duplicate the app JSON/JWT signing key here.
resource "aws_secretsmanager_secret" "waf_access_code" {
  name       = "${var.project}/waf-access-code"
  kms_key_id = aws_kms_key.secrets.arn
}

# Bootstrap this resource first, then copy the current frontend code with the
# helper. Empty bootstrap values fail the existing required-gate precondition.
resource "aws_secretsmanager_secret_version" "waf_access_code" {
  secret_id     = aws_secretsmanager_secret.waf_access_code.id
  secret_string = jsonencode({ ACCESS_CODE = "" })
  lifecycle {
    ignore_changes = [secret_string]
  }
}
