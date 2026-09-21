# Initial small feedback traffic limits; both API hosts share the global limit.
# Source IP is the TCP peer, not an untrusted X-Forwarded-For header.
variable "waf_requests_per_ip_5m" {
  type    = number
  default = 600
  validation {
    condition     = var.waf_requests_per_ip_5m >= 10 && var.waf_requests_per_ip_5m <= 2000000000 && floor(var.waf_requests_per_ip_5m) == var.waf_requests_per_ip_5m
    error_message = "WAF limit must be an integer between 10 and 2000000000."
  }
}

variable "waf_requests_total_5m" {
  type    = number
  default = 3000
  validation {
    condition     = var.waf_requests_total_5m >= 10 && var.waf_requests_total_5m <= 2000000000 && floor(var.waf_requests_total_5m) == var.waf_requests_total_5m
    error_message = "WAF limit must be an integer between 10 and 2000000000."
  }
}

variable "waf_emergency_block" {
  description = "Manual emergency stop for public API HTTP requests; does not stop queued jobs or fixed charges."
  type        = bool
  default     = false
}

resource "aws_wafv2_web_acl" "cost_guard" {
  name  = "${var.project}-cost-guard"
  scope = "REGIONAL"
  default_action {
    allow {}
  }

  dynamic "rule" {
    for_each = var.waf_emergency_block ? [1] : []
    content {
      name     = "emergency-block"
      priority = 0
      action {
        block {}
      }
      statement {
        size_constraint_statement {
          comparison_operator = "GT"
          size                = 0
          field_to_match {
            uri_path {}
          }
          text_transformation {
            priority = 0
            type     = "NONE"
          }
        }
      }
      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "fruition-emergency-block"
        sampled_requests_enabled   = false
      }
    }
  }

  # 보안 룰: 관리형 룰 그룹이 rate limit보다 먼저 평가된다.
  dynamic "rule" {
    for_each = {
      1 = "AWSManagedRulesAmazonIpReputationList"
      2 = "AWSManagedRulesCommonRuleSet"
      3 = "AWSManagedRulesKnownBadInputsRuleSet"
      4 = "AWSManagedRulesSQLiRuleSet"
    }
    content {
      name     = rule.value
      priority = rule.key
      override_action {
        none {}
      }
      statement {
        managed_rule_group_statement {
          vendor_name = "AWS"
          name        = rule.value
          # Keep labels for these two body rules, then re-block all requests
          # except the exact multipart document upload contract below.
          dynamic "rule_action_override" {
            for_each = rule.value == "AWSManagedRulesCommonRuleSet" ? ["SizeRestrictions_BODY", "GenericLFI_BODY"] : []
            content {
              name = rule_action_override.value
              action_to_use {
                count {}
              }
            }
          }
        }
      }
      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "fruition-${rule.value}"
        sampled_requests_enabled   = false
      }
    }
  }

  # Count overrides are NOT global exceptions: re-block their labels unless
  # POST + exact document collection path + multipart boundary all match.
  # No terminating Allow: every other managed rule and both rate limits apply.
  dynamic "rule" {
    for_each = {
      5 = "SizeRestrictions_Body"
      6 = "GenericLFI_Body"
    }
    content {
      name     = "body-guard-${rule.value}"
      priority = rule.key
      action {
        block {}
      }
      statement {
        and_statement {
          statement {
            label_match_statement {
              scope = "LABEL"
              key   = "awswaf:managed:aws:core-rule-set:${rule.value}"
            }
          }
          statement {
            not_statement {
              statement {
                and_statement {
                  statement {
                    byte_match_statement {
                      search_string         = "POST"
                      positional_constraint = "EXACTLY"
                      field_to_match {
                        method {}
                      }
                      text_transformation {
                        priority = 0
                        type     = "NONE"
                      }
                    }
                  }
                  statement {
                    regex_match_statement {
                      regex_string = "^/api/workspaces/ws_[0-9a-f]{32}/documents$"
                      field_to_match {
                        uri_path {}
                      }
                      text_transformation {
                        priority = 0
                        type     = "NONE"
                      }
                    }
                  }
                  statement {
                    regex_match_statement {
                      regex_string = "^multipart/form-data;[ ]*boundary="
                      field_to_match {
                        single_header {
                          name = "content-type"
                        }
                      }
                      text_transformation {
                        priority = 0
                        type     = "LOWERCASE"
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "fruition-body-guard-${rule.value}"
        sampled_requests_enabled   = false
      }
    }
  }

  rule {
    name     = "per-source-ip"
    priority = 10
    action {
      block {
        custom_response {
          response_code = 429
        }
      }
    }
    statement {
      rate_based_statement {
        aggregate_key_type    = "IP"
        limit                 = var.waf_requests_per_ip_5m
        evaluation_window_sec = 300
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "fruition-per-source-ip"
      sampled_requests_enabled   = false
    }
  }

  rule {
    name     = "all-api-requests"
    priority = 20
    action {
      block {
        custom_response {
          response_code = 429
        }
      }
    }
    statement {
      rate_based_statement {
        aggregate_key_type    = "CONSTANT"
        limit                 = var.waf_requests_total_5m
        evaluation_window_sec = 300
        scope_down_statement {
          size_constraint_statement {
            comparison_operator = "GT"
            size                = 0
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "fruition-all-api-requests"
      sampled_requests_enabled   = false
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "fruition-cost-guard"
    sampled_requests_enabled   = false
  }
}

# WAF 로그 — 공격 조사에 필요. 이름은 aws-waf-logs- prefix가 필수다.
resource "aws_cloudwatch_log_group" "waf" {
  name              = "aws-waf-logs-${var.project}"
  retention_in_days = 14
}

resource "aws_wafv2_web_acl_logging_configuration" "cost_guard" {
  resource_arn            = aws_wafv2_web_acl.cost_guard.arn
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]

  # Logs must not retain session credentials or URL query tokens. Sampling is
  # disabled separately above because logging redaction does not cover samples.
  redacted_fields {
    single_header {
      name = "authorization"
    }
  }
  redacted_fields {
    single_header {
      name = "cookie"
    }
  }
  redacted_fields {
    single_header {
      name = "x-api-key"
    }
  }
  redacted_fields {
    query_string {}
  }
}

output "waf_acl_arn" {
  description = "Required deploy-config waf_acl_arn; ALB controller associates this ACL during app deployment."
  value       = aws_wafv2_web_acl.cost_guard.arn
}
