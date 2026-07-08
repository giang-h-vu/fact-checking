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
  # NOTE: the Azure for Students subscription has 0 quota for the Bsv2 family in
  # EVERY region (total regional cap is 10 vCPUs, spread across families). The
  # D/E/F families do get 10 vCPUs. Keep to 4 vCPUs so a surge/rotation node (node + temp pool = 8)
  # stays under the 10-core cap.
  # GPU (demo): Standard_NC4as_T4_v3 (~$0.50/hr, T4 16GB) — needs standardNCFamily quota (12).
  # CPU (learning): Standard_D4s_v6 (4 vCPU / 16GB). More RAM for Ollama: Standard_E4s_v6 (4 vCPU / 32GB).
  type        = string
  default     = "Standard_D4s_v6"
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
