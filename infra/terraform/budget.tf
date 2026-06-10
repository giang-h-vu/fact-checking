# Budget alerting — three-tier email notifications:
#   50% Actual     → warning: you've spent half your budget
#   70% Forecasted → early warning: Azure predicts overspend this month
#   90% Actual     → urgent: stop the cluster manually with `az aks stop`
#
# Note: Azure Automation Accounts are not available in student subscription
# regions (francecentral etc.), so auto-stop via runbook is not possible.
# Stop the cluster manually when done: az aks stop --name fact-checking --resource-group fact-checking

resource "azurerm_consumption_budget_resource_group" "main" {
  name              = "fact-checking-budget"
  resource_group_id = azurerm_resource_group.main.id

  amount     = 10
  time_grain = "Monthly"

  time_period {
    start_date = "2026-06-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 50.0
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = ["vhgiang98@gmail.com"]
  }

  notification {
    enabled        = true
    threshold      = 70.0
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = ["vhgiang98@gmail.com"]
  }

  notification {
    enabled        = true
    threshold      = 90.0
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = ["vhgiang98@gmail.com"]
  }
}
