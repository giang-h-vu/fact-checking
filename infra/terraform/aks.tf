resource "azurerm_resource_group" "main" {
  name     = var.cluster_name
  location = var.location
}

resource "azurerm_kubernetes_cluster" "main" {
  name                = var.cluster_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = var.cluster_name

	sku_tier = "Free"

  default_node_pool {
    name       = "default"
    node_count = 1
    vm_size    = var.node_size
  }

	# Enable system-assigned managed identity for the AKS cluster
  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin = "azure"
  }

  oidc_issuer_enabled = true
}
