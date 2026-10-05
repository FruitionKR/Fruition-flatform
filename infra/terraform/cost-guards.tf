# Initial small feedback traffic limits. The global limit counts /api/ requests on every host;
# the per-IP limit counts everything except immutable /_next/static/ assets.
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

variable "app_domain" {
  description = "Host serving the frontend and same-origin API on the shared ALB (e.g. fruitiontest.accesscam.org). Empty disables the access-code rule."
  type        = string
  default     = ""
  validation {
    condition     = var.app_domain == "" || can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.app_domain))
    error_message = "app_domain must be a lowercase DNS name."
  }
}

# The frontend pod reads ACCESS_CODE from the same secret. Reading it here keeps the WAF hash from
# drifting from the pod; after changing ACCESS_CODE in Secrets Manager, run terraform apply again.
data "aws_secretsmanager_secret_version" "app_current" {
  secret_id  = aws_secretsmanager_secret.app.id
  depends_on = [aws_secretsmanager_secret_version.app]
}

locals {
  # Same as the frontend: trimmed code, cookie = lowercase hex SHA-256 (hashAccessCode).
  waf_access_code = trimspace(try(jsondecode(data.aws_secretsmanager_secret_version.app_current.secret_string).ACCESS_CODE, ""))
  # The frontend middleware no longer sees /api/* once the ALB routes it, so WAF enforces the same gate.
  # Whether a code is set is not secret; for_each cannot take a sensitive value.
  waf_access_code_enabled = var.app_domain != "" && nonsensitive(local.waf_access_code != "")
  # Paths open without the code, mirroring OPEN_API_PATTERNS in the frontend middleware.ts.
  waf_access_code_open_path_regex = "^/api/(auth/|invitations/|workspaces$|workspaces/[^/]+$)"
  waf_document_content_contracts  = jsondecode(file("${path.module}/../waf/document-content-contracts.json"))
  waf_content_body_overrides = {
    AWSManagedRulesCommonRuleSet = {
      SizeRestrictions_BODY   = "awswaf:managed:aws:core-rule-set:SizeRestrictions_Body"
      GenericLFI_BODY         = "awswaf:managed:aws:core-rule-set:GenericLFI_Body"
      CrossSiteScripting_BODY = "awswaf:managed:aws:core-rule-set:CrossSiteScripting_Body"
    }
    AWSManagedRulesSQLiRuleSet = {
      SQLi_BODY = "awswaf:managed:aws:sql-database:SQLi_Body"
    }
  }
}

resource "aws_wafv2_web_acl" "cost_guard" {
  name  = "${var.project}-cost-guard"
  scope = "REGIONAL"
  default_action {
    allow {}
  }

  dynamic "custom_response_body" {
    for_each = local.waf_access_code_enabled ? [1] : []
    content {
      key          = "access-code-required"
      content_type = "APPLICATION_JSON"
      content      = jsonencode({ error = { message = "설정에서 접근 코드를 입력해야 사용할 수 있습니다." } })
    }
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

  # ALB path rules return 404 for these, but ALB matches the raw path; a percent-encoded path
  # (/%69nternal/...) would skip them and Tomcat would decode it. Block the decoded path on every host.
  rule {
    name     = "not-public-paths"
    priority = 2
    action {
      block {
        custom_response {
          response_code = 404
        }
      }
    }
    statement {
      regex_match_statement {
        regex_string = "^/+(internal|swagger-ui|v3/api-docs)"
        field_to_match {
          uri_path {}
        }
        text_transformation {
          priority = 0
          type     = "URL_DECODE"
        }
        text_transformation {
          priority = 1
          type     = "NORMALIZE_PATH"
        }
        text_transformation {
          priority = 2
          type     = "LOWERCASE"
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "fruition-not-public-paths"
      sampled_requests_enabled   = false
    }
  }

  # Mark only routes that intentionally carry arbitrary document text. Count
  # continues evaluation; this is never a terminating Allow or an auth bypass.
  rule {
    name     = "document-content-contract"
    priority = 1
    action {
      count {}
    }
    rule_label { name = "fruition:document-content" }
    statement {
      or_statement {
        dynamic "statement" {
          for_each = local.waf_document_content_contracts
          content {
            and_statement {
              statement {
                byte_match_statement {
                  search_string         = statement.value.method
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
                  regex_string = statement.value.path_regex
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
                  regex_string = statement.value.content_type_regex
                  field_to_match {
                    single_header { name = "content-type" }
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
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "fruition-document-content-contract"
      sampled_requests_enabled   = false
    }
  }

  dynamic "rule" {
    for_each = {
      10 = "AWSManagedRulesAmazonIpReputationList"
      11 = "AWSManagedRulesCommonRuleSet"
      12 = "AWSManagedRulesKnownBadInputsRuleSet"
      13 = "AWSManagedRulesSQLiRuleSet"
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
          # Preserve labels; the guard below re-blocks these outside the contract.
          # Header, cookie, URI, query, reputation and known-bad-input rules remain.
          dynamic "rule_action_override" {
            for_each = lookup(local.waf_content_body_overrides, rule.value, {})
            content {
              name = rule_action_override.key
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

  rule {
    name     = "document-content-body-guard"
    priority = 20
    action {
      block {}
    }
    statement {
      and_statement {
        statement {
          or_statement {
            dynamic "statement" {
              for_each = toset(flatten([for rules in local.waf_content_body_overrides : values(rules)]))
              content {
                label_match_statement {
                  scope = "LABEL"
                  key   = statement.value
                }
              }
            }
          }
        }
        statement {
          not_statement {
            statement {
              label_match_statement {
                scope = "LABEL"
                # Same-WebACL labels use their local name; AWS adds the prefix.
                key = "fruition:document-content"
              }
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "fruition-document-content-body-guard"
      sampled_requests_enabled   = false
    }
  }

  dynamic "rule" {
    for_each = local.waf_access_code_enabled ? [1] : []
    content {
      name     = "frontend-access-code"
      priority = 25
      action {
        block {
          custom_response {
            response_code            = 403
            custom_response_body_key = "access-code-required"
          }
        }
      }
      statement {
        and_statement {
          statement {
            byte_match_statement {
              search_string         = var.app_domain
              positional_constraint = "EXACTLY"
              field_to_match {
                single_header { name = "host" }
              }
              text_transformation {
                priority = 0
                type     = "LOWERCASE"
              }
            }
          }
          statement {
            byte_match_statement {
              search_string         = "/api/"
              positional_constraint = "STARTS_WITH"
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
            not_statement {
              statement {
                regex_match_statement {
                  regex_string = local.waf_access_code_open_path_regex
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
          statement {
            not_statement {
              statement {
                byte_match_statement {
                  search_string         = sha256(local.waf_access_code)
                  positional_constraint = "EXACTLY"
                  field_to_match {
                    cookies {
                      match_pattern {
                        included_cookies = ["fruition_access"]
                      }
                      match_scope       = "VALUE"
                      oversize_handling = "NO_MATCH"
                    }
                  }
                  text_transformation {
                    priority = 0
                    type     = "NONE"
                  }
                }
              }
            }
          }
        }
      }
      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "fruition-frontend-access-code"
        sampled_requests_enabled   = false
      }
    }
  }

  rule {
    name     = "per-source-ip"
    priority = 30
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
        # Immutable Next.js build assets are cached by browsers; counting them would 429 page loads.
        scope_down_statement {
          not_statement {
            statement {
              byte_match_statement {
                search_string         = "/_next/static/"
                positional_constraint = "STARTS_WITH"
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
    priority = 40
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
        # API calls only. Page HTML and assets on the frontend host would otherwise make one
        # crawler or page-load burst return 429 to every user's API calls.
        scope_down_statement {
          byte_match_statement {
            search_string         = "/api/"
            positional_constraint = "STARTS_WITH"
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
