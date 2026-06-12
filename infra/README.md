# Infrastructure

Everything needed to run the fact-checking app on Azure: Terraform provisions a single-node AKS cluster, and plain Kubernetes manifests deploy the app behind the Kubernetes Gateway API with automatic TLS.

For the step-by-step walkthrough (DNS, cert-manager, image registry, troubleshooting).

## How it works

```
Terraform ──► Azure: resource group + AKS cluster (Standard_NC4as_T4_v3 or Standard_B4s_v2 node, free control plane)
                                │
kubectl/manifests ──► inside the cluster:
  Gateway (NGINX Gateway Fabric) ── factchecking.dpdns.org, TLS via cert-manager/Let's Encrypt
        ├── HTTPRoute /api/* ──► server (FastAPI)  ──► ollama (LLM, ClusterIP only)
        └── HTTPRoute /*     ──► web (React/nginx)
```

- **Traffic**: one public LoadBalancer IP (provisioned by NGF when the `Gateway` is applied) routes `/api/*` to the backend and everything else to the SPA.
- **State**: the Ollama model (~4.7 GB) and the SQLite database live on PersistentVolumeClaims backed by Azure Managed Disks — they survive pod restarts *and* cluster stop/start.
- **Cost control**: `az aks stop` deallocates the worker node (billing stops, ~$0.75/mo for disks only); a Terraform budget resource emails alerts at 50% / 70% forecast / 90% of credit.

## Layout

```
infra/
├── terraform/
│   ├── main.tf            # azurerm provider config
│   ├── variables.tf       # subscription, region, cluster name, node size
│   ├── aks.tf             # resource group + AKS cluster
│   ├── budget.tf          # cost alerts
│   ├── outputs.tf         # kubeconfig, resource group
│   └── terraform.tfvars   # your values — gitignored, never commit
├── k8s/
│   ├── namespace.yaml         # fact-checking namespace
│   ├── cluster-issuer.yaml    # Let's Encrypt ACME issuer (cert-manager)
│   ├── gatewayclass.yaml      # binds Gateways to NGINX Gateway Fabric
│   ├── gateway.yaml           # listeners :80/:443 for factchecking.dpdns.org + TLS
│   ├── ollama/                # LLM: deployment + service + 10Gi PVC
│   ├── server/                # backend: deployment + service + configmap + 5Gi PVC + HTTPRoute (/api)
│   └── web/                   # frontend: deployment + service + HTTPRoute (catch-all)
└── scripts/
    ├── start.sh           # az aks start (run before a demo, ~3–5 min)
    └── stop.sh            # az aks stop  (run after — stops node billing)
```

## Provision the cluster

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply

# Connect kubectl
terraform output -raw kube_config > ~/.kube/aks-fact-checking
export KUBECONFIG=~/.kube/aks-fact-checking
kubectl get nodes
```

## Deploy the app

Cluster add-ons first (Gateway API CRDs, NGINX Gateway Fabric, cert-manager), then:

```bash
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/cluster-issuer.yaml
kubectl apply -f infra/k8s/gatewayclass.yaml
kubectl apply -f infra/k8s/gateway.yaml
kubectl apply -f infra/k8s/ollama/ -f infra/k8s/server/ -f infra/k8s/web/
```

The sensitive config — `JWT_SECRET`, `SESSION_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BRAVE_API_KEY` (see the Configuration table in [`server/README.md`](../server/README.md)) — is delivered as a k8s Secret, created imperatively from a git-ignored `.env.prod` file (never committed):

```bash
kubectl create secret generic app-secrets --from-env-file=.env.prod -n fact-checking
```

Non-sensitive config lives in the ConfigMap (`k8s/server/configmap.yaml`).

## Stop/start between demos

```bash
./infra/scripts/stop.sh    # billing stops; disks (~$0.75/mo) persist
./infra/scripts/start.sh   # back in ~3–5 minutes, same state
```

## Tear down

```bash
cd infra/terraform
terraform destroy   # deletes cluster, disks, load balancer, resource group — all billing stops
```
