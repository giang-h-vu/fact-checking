# GitHub Actions -> Azure OIDC, via a USER-ASSIGNED MANAGED IDENTITY.
#
# A managed identity lives in the Azure RBAC plane (not the Entra directory
# plane), so creating it needs only subscription Owner/Contributor rights --
# no Application Administrator role. GitHub's azure/login treats the identity's
# client_id exactly like an app registration's: same passwordless OIDC exchange.

# 1. The identity itself (=> AZURE_CLIENT_ID). An Azure resource, not an Entra app.
resource "azurerm_user_assigned_identity" "github_deploy" {
  name                = "github-fact-checking-deploy"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
}

# 2. Authorization -- Contributor on the resource group the cluster lives in.
resource "azurerm_role_assignment" "github_deploy_rg" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.github_deploy.principal_id
}

# 3. Federated credential -- the trust rule. Subject must match the GitHub
#    token's `sub` EXACTLY, including the environment segment.
resource "azurerm_federated_identity_credential" "github_prod" {
  name                = "github-fact-checking-${var.github_environment}"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.github_deploy.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = "repo:${var.github_repository}:environment:${var.github_environment}"
}

# Copy these into GitHub (Settings -> Secrets and variables -> Actions).
output "azure_client_id" {
  value       = azurerm_user_assigned_identity.github_deploy.client_id
  description = "AZURE_CLIENT_ID — environment secret for the deploy job."
}

output "azure_tenant_id" {
  value       = azurerm_user_assigned_identity.github_deploy.tenant_id
  description = "AZURE_TENANT_ID — environment secret for the deploy job."
}

output "azure_subscription_id" {
  value       = var.subscription_id
  sensitive   = true
  description = "AZURE_SUBSCRIPTION_ID — environment secret for the deploy job."
}
