#!/usr/bin/env bash
# Start the AKS cluster only if it is not already running.
#
# The cluster is normally stopped (`az aks stop`), which
# deallocates the nodes AND the control plane. `az aks start` is blocking and
# errors if the cluster is already running, so we guard on powerState first.
#
# Reads (from the environment):
#   AKS_CLUSTER         AKS cluster name
#   AKS_RESOURCE_GROUP  its resource group
#
# Used by both .github/workflows/deploy.yaml and bootstrap.yaml.
set -euo pipefail

: "${AKS_CLUSTER:?AKS_CLUSTER must be set}"
: "${AKS_RESOURCE_GROUP:?AKS_RESOURCE_GROUP must be set}"

state=$(az aks show -n "$AKS_CLUSTER" -g "$AKS_RESOURCE_GROUP" \
          --query "powerState.code" -o tsv)
echo "Cluster power state: $state"
if [ "$state" != "Running" ]; then
  echo "Starting cluster (blocks until ready, ~3-5 min)..."
  az aks start -n "$AKS_CLUSTER" -g "$AKS_RESOURCE_GROUP"
else
  echo "Already running -- skipping start."
fi
