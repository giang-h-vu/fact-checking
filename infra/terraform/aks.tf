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

    # Required to change vm_size in place: the provider spins up a temp pool,
    # drains onto it, then recreates "default" at the new size. Avoids a full
    # cluster recreate, so in-cluster state survives.
    temporary_name_for_rotation = "defaulttmp"
    upgrade_settings {
      drain_timeout_in_minutes      = 0
      max_surge                     = "10%"
      node_soak_duration_in_minutes = 0
    }
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
