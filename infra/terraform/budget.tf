# Budget alerting — three-tier email notifications:
#   50% Actual     → warning: you've spent half your budget
#   70% Forecasted → early warning: Azure predicts overspend this month
#   90% Actual     → urgent: stop the cluster manually with `az aks stop`
# Stop the cluster manually when done: az aks stop --name fact-checking --resource-group fact-checking
#
# Scoped to the SUBSCRIPTION, not the resource group: AKS bills its compute
# (VMSS, disks, load balancer) in the auto-created node resource group
# MC_<rg>_<cluster>_<region>, so a budget on the app RG only ever sees the
# free control plane (€0) and its alerts never fire.

resource "azurerm_consumption_budget_subscription" "main" {
  name            = "fact-checking-budget"
  subscription_id = "/subscriptions/${var.subscription_id}"

  amount     = 10
  time_grain = "Monthly"

  time_period {
    start_date = "2026-07-01T00:00:00Z"
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
