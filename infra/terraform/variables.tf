variable "subscription_id" {
  description = "Azure Subscription ID where the AKS cluster will be deployed"
  type        = string
  sensitive   = true
}

variable "location" {
  description = "Azure region to deploy resources in"
  type        = string
  default     = "swedencentral" # Cheapest option
}

variable "cluster_name" {
  description = "Name of the AKS cluster and resource group"
  type        = string
  default     = "fact-checking"
}

variable "node_size" {
  description = "VM size for the AKS node. GPU (demo): Standard_NC4as_T4_v3 (~$0.50/hr, T4 16GB). CPU (learning): Standard_B4s_v2 (~$0.13/hr, slow inference)."
  type        = string
  default     = "Standard_B4s_v2"
}

variable "github_repository" {
  description = "GitHub repo (owner/name) trusted for OIDC deploys. Used to build the federated credential subject."
  type        = string
  default     = "giang-h-vu/fact-checking"
}

variable "github_environment" {
  description = "GitHub Actions environment that the OIDC subject is scoped to (must match `environment:` in the deploy job)."
  type        = string
  default     = "production"
}
