# §8.6: 필수 수신 이메일로 월 USD 500·700 budget alarm을 항상 생성한다.
resource "aws_budgets_budget" "monthly" {
  for_each = { warn = "500", high = "700" }

  name         = "${var.project}-monthly-${each.value}"
  budget_type  = "COST"
  limit_amount = each.value
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
}
