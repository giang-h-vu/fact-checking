# Infrastructure

Everything needed to run the fact-checking app on Azure: Terraform provisions a single-node AKS cluster, and plain Kubernetes manifests deploy the app behind the Kubernetes Gateway API with automatic TLS.

For the step-by-step walkthrough (DNS, cert-manager, image registry, troubleshooting), see [`deploy_instructions.md`](../deploy_instructions.md).

## How it works

```
Terraform ──► Azure: resource group + AKS cluster (default Standard_D4s_v6 node, free control plane)
                                │
kubectl/manifests ──► inside the cluster:
  Gateway (NGINX Gateway Fabric) ── factchecking.dpdns.org, TLS via cert-manager/Let's Encrypt
        ├── HTTPRoute /api/* ──► server (FastAPI)  ──► OpenRouter (hosted LLM, default)
        │                                          └─► ollama (optional, ClusterIP only)
        └── HTTPRoute /*     ──► web (React/nginx)
```

- **Traffic**: one public LoadBalancer IP (provisioned by NGF when the `Gateway` is applied) routes `/api/*` to the backend and everything else to the SPA.
- **LLM**: `LLM_PROVIDER` in the `server-config` ConfigMap picks the backend. `openrouter` (current default) needs `OPENROUTER_API_KEY` in the `app-secrets` Secret; `ollama` uses the in-cluster Service. The bootstrap tier still applies the Ollama Deployment and PVC in OpenRouter mode, so they sit idle (6Gi memory request, 10Gi disk).
- **State**: the SQLite database (and the Ollama model, if used) live on PersistentVolumeClaims backed by Azure Managed Disks — they survive pod restarts *and* cluster stop/start.
- **Cost control**: `az aks stop` deallocates the worker node (billing stops, ~$0.75/mo for disks only); a subscription-scoped Terraform budget emails alerts at 50% actual / 70% forecast / 90% actual (subscription scope, because AKS bills compute into the `MC_*` node resource group, which a resource-group budget never sees).

## Layout

```
infra/
├── terraform/
│   ├── main.tf            # azurerm provider config
│   ├── variables.tf       # subscription, region, cluster name, node size, GitHub repo/env
│   ├── aks.tf             # resource group + AKS cluster (OIDC issuer enabled)
│   ├── budget.tf          # subscription-scoped cost alerts
│   ├── github-oidc.tf     # user-assigned identity + federated credential for GitHub Actions
│   ├── outputs.tf         # kubeconfig, resource group, cluster name
│   └── terraform.tfvars   # your values — gitignored, never commit
├── k8s/
│   ├── bootstrap/         # set-once, applied by the bootstrap workflow (`kubectl apply -k`)
│   │   ├── namespace.yaml, cluster-issuer.yaml, gatewayclass.yaml, gateway.yaml
│   │   ├── server-pvc.yaml            # 5Gi SQLite volume
│   │   └── ollama-{deployment,service,pvc}.yaml   # optional LLM runtime, 10Gi PVC
│   └── app/               # per-release, applied by the deploy workflow (`kubectl apply -k`)
│       ├── configmap.yaml             # non-sensitive server config (LLM_PROVIDER, models, URLs…)
│       ├── server-{deployment,service,httproute}.yaml
│       ├── web-{deployment,service,httproute}.yaml
│       └── kustomization.yaml         # image names/tags
└── scripts/
    ├── start.sh                    # az aks start (run before a demo, ~3–5 min)
    ├── stop.sh                     # az aks stop  (run after — stops node billing)
    └── ensure-cluster-running.sh   # start only if stopped (used by the workflows)
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

Normally via GitHub Actions: run **bootstrap** once after the cluster is (re)created (installs Gateway API CRDs, NGINX Gateway Fabric, cert-manager, creates `app-secrets`, applies `k8s/bootstrap`), then **deploy** on a `v*.*.*` tag. Both authenticate to Azure over OIDC; see Phase 6 of [`deploy_instructions.md`](../deploy_instructions.md).

By hand, after the cluster add-ons and `app-secrets` exist:

```bash
kubectl apply -k infra/k8s/bootstrap   # namespace, issuer, gateway, PVCs, Ollama
kubectl apply -k infra/k8s/app         # server + web + ConfigMap
```

Sensitive config — `JWT_SECRET`, `SESSION_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BRAVE_API_KEY` and, in OpenRouter mode, `OPENROUTER_API_KEY` (see the Configuration table in [`server/README.md`](../server/README.md)) — lives in the `app-secrets` Secret, never in git:

```bash
kubectl create secret generic app-secrets --from-env-file=.env.prod -n fact-checking
```

> **Gap:** `.github/workflows/bootstrap.yaml` currently creates `app-secrets` from `JWT_SECRET`, `SESSION_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `BRAVE_API_KEY` only. With `LLM_PROVIDER=openrouter` you must also add `OPENROUTER_API_KEY` there (or patch the Secret by hand), otherwise the server cannot reach the LLM.

Non-sensitive config lives in the ConfigMap (`k8s/app/configmap.yaml`): `LLM_PROVIDER`, `OPENROUTER_MODEL`, `OPENROUTER_FALLBACK_MODELS`, `OLLAMA_*`, URLs, cookie flags.

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
