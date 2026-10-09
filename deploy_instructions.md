# Deployment Guide: Azure AKS + Terraform + Kubernetes Gateway API

**Goal:** Deploy the fact-checking app to Azure Kubernetes Service (AKS) at minimum cost, using Terraform to provision infrastructure and Kubernetes manifests to run the app. The cluster can be stopped when not in use so your Azure student credit lasts for months.

**Domain:** `factchecking.dpdns.org`
**Estimated active cost:** depends on `node_size` (default `Standard_D4s_v6`); ~$0.75/mo when stopped (disks only)
**Out of pocket:** $0 (covered by Azure student credit)

---

## How it all fits together

```
Your machine
  │
  ├── Terraform  →  Azure (creates the AKS cluster + resource group)
  │
  └── kubectl    →  Kubernetes (deploys the app workloads inside the cluster)

Internet
  └── factchecking.dpdns.org
        └── Azure Load Balancer
              └── NGINX Gateway Fabric  (k8s Gateway API)
                    ├── /api/*  →  FastAPI backend pod
                    └── /*      →  Nginx/React frontend pod
                                       └── backend pod
                                             └── OpenRouter (hosted LLM)   or   Ollama pod (optional)
```

**Why AKS instead of running k8s yourself on VMs?**
AKS gives you a free managed control plane — Azure handles k8s upgrades, etcd backups, and API server certificates. You only pay for the worker nodes (the VMs that run your containers). Self-managed k8s on VMs would cost extra (you'd need a VM just for the control plane) and add maintenance burden.

**Why `az aks stop`?**
When stopped, worker nodes are deallocated (billing stops). Persistent Volumes (your SQLite database, and the Ollama model if you use it) survive on Azure Managed Disks and reattach when you restart. The cluster comes back in ~3–5 minutes exactly where it left off.

---

## Prerequisites — install these first

```bash
# Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
az login   # opens browser, log in with your student account

# Terraform
sudo apt-get install -y gnupg software-properties-common
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# Helm (package manager for k8s add-ons)
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verify
az --version
terraform --version
kubectl version --client
helm version
```

The student subscription restricts which regions you can use. Check which ones are allowed:
```bash
az account list-locations --output table | grep -i europe

# faster — check what your subscription policy actually permits:
az policy assignment list --output table

# list the allowed regions directly
az policy definition show \
  --name "b86dabb9-b578-4d7b-b842-3b45e95769a1" \
  --query "properties.parameters" \
  --output json
```
The regions are differnt for each account, detailed by navigating to Azure Policy -- Authoring -- Assignments:
Current allowed regions for this account: ["swedencentral","spaincentral","francecentral","italynorth","polandcentral"]


---

## Phase 1: Terraform — provision the AKS cluster

**What Terraform does here:** talks to the Azure API to create a resource group (a logical container for all Azure resources) and an AKS cluster inside it.

**Why Terraform instead of clicking in the Azure portal?**
Infrastructure as Code — your cluster is reproducible, version-controlled, and can be torn down and recreated with one command.

### Step 1.1 — Get your Azure subscription ID

```bash
az account show --query id -o tsv
# Copy the output — you'll need it in the next step
```

### Step 1.2 — The Terraform files

The files are committed under `infra/terraform/`; read them rather than recreating them. What each does:

| File | Purpose |
|---|---|
| `main.tf` | `azurerm` provider (`~> 3.0`) and `subscription_id` |
| `variables.tf` | `subscription_id`, `location` (default `swedencentral`), `cluster_name`, `node_size` (default `Standard_D4s_v6`), `github_repository`, `github_environment` |
| `aks.tf` | Resource group + single-node AKS cluster, `sku_tier = "Free"` control plane, system-assigned identity, Azure CNI, OIDC issuer enabled |
| `budget.tf` | Subscription-scoped monthly budget with email alerts (see 1.2b) |
| `github-oidc.tf` | User-assigned managed identity + federated credential for GitHub Actions (Phase 6) |
| `outputs.tf` | `kube_config`, `resource_group`, `cluster_name` |
| `terraform.tfvars` | Your values — gitignored, never commit |

**Choosing a node size.** The Azure for Students subscription has a hard regional cap of 10 vCPUs and **zero quota for the Bsv2 family in every region**. The D/E/F families work. Stay at 4 vCPUs: a size change rotates through a temporary pool (`temporary_name_for_rotation`), so node + temp pool = 8 vCPUs, which fits under the cap. Options listed in `variables.tf`: `Standard_D4s_v6` (4 vCPU / 16 GB, default), `Standard_E4s_v6` (4 vCPU / 32 GB, more room for Ollama), `Standard_NC4as_T4_v3` (GPU, needs `standardNCFamily` quota).

**Choosing a region.** The student subscription restricts regions via Azure Policy, so `location` must be one of the allowed ones (see the list above). `swedencentral` is the default.

### Step 1.2b — Budget alerting

Three email notifications, defined in `infra/terraform/budget.tf`:

```
50% Actual     → email   "you've spent half your budget — check usage"
70% Forecasted → email   "Azure predicts you'll overspend this month"
90% Actual     → email   "urgent — stop the cluster manually now"
```

**The budget is subscription-scoped on purpose.** AKS bills its compute (VMSS, disks, load balancer) into the auto-created node resource group `MC_<rg>_<cluster>_<region>`. A budget on the `fact-checking` resource group only sees the free control plane (€0), so its alerts would never fire. The budget resource is `azurerm_consumption_budget_subscription` with `amount = 10`, `time_grain = "Monthly"`, and a `start_date` that must be the first of a month.

Before applying, set `contact_emails` and `start_date` in `budget.tf` to your own values.

> **Note on auto-stop:** Azure Automation Accounts (needed to stop the cluster automatically on a budget breach) are not available in `swedencentral`, so auto-stop via runbook is not possible. Stop the cluster manually when done:
> ```bash
> az aks stop --name fact-checking --resource-group fact-checking
> ```

### Step 1.3 — Apply

```bash
cd infra/terraform

# Download the Azure provider plugin (~40MB, one-time)
terraform init

# Preview what will be created (no changes yet)
terraform plan -var="subscription_id=<YOUR_SUBSCRIPTION_ID>"

# Create the cluster (~5–10 minutes)
terraform apply -var="subscription_id=<YOUR_SUBSCRIPTION_ID>"
# Type "yes" when prompted

```

Terraform log levels, least to most verbose: `ERROR → WARN → INFO → DEBUG → TRACE`.

```bash
TF_LOG=DEBUG terraform apply                              # every API call — very verbose
TF_LOG=ERROR terraform apply                              # quieter but still detailed
TF_LOG=DEBUG terraform apply 2> terraform-debug.log       # save to read at your own pace
```

### Step 1.4 — Connect kubectl to the cluster

```bash
# Export the kubeconfig Terraform captured
terraform output -raw kube_config > ~/.kube/aks-fact-checking

# Tell kubectl to use it
export KUBECONFIG=~/.kube/aks-fact-checking

# Add to ~/.bashrc so it persists across terminal sessions:
echo 'export KUBECONFIG=~/.kube/aks-fact-checking' >> ~/.bashrc

# Verify you're connected
kubectl get nodes
# Should show one node in "Ready" state
```

---

## Phase 2: Install cluster add-ons

These are infrastructure components that run inside k8s and extend it. You install them once; they stay until you delete the cluster.

### Step 2.1 — Install Gateway API CRDs

**What are CRDs?** Custom Resource Definitions extend k8s with new resource types. The Gateway API (GatewayClass, Gateway, HTTPRoute) isn't built into k8s — you install these type definitions first.

```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/standard-install.yaml

# Verify the new resource types exist
kubectl get crd | grep gateway
# Should show: gatewayclasses.gateway.networking.k8s.io, gateways.gateway.networking.k8s.io, httproutes.gateway.networking.k8s.io
```

### Step 2.2 — Install NGINX Gateway Fabric

**What is this?** The controller that watches for `Gateway` and `HTTPRoute` resources and programs an NGINX instance to route traffic accordingly.

**Why NGINX Gateway Fabric instead of ingress-nginx?**
`ingress-nginx` uses the older `Ingress` API. NGINX Gateway Fabric is the official NGINX implementation of the modern Gateway API — same NGINX under the hood, but uses the newer, more expressive resource model.

**NGF 2.x architecture — control plane vs data plane (important!)**
Since v2.0, NGF splits into two parts:
- **Control plane** — the `ngf-nginx-gateway-fabric` pod/service installed by Helm in `nginx-gateway`. It is **ClusterIP with only port 443** (internal agent communication). This is normal — do NOT patch it to LoadBalancer; it never serves your traffic.
- **Data plane** — provisioned **dynamically when you create a `Gateway` resource** (Phase 3, Step 3.2). NGF spawns an NGINX deployment + LoadBalancer Service **in the Gateway's namespace** (`fact-checking`), with ports matching the Gateway's listeners (80 + 443). *That* service gets the public IP.

So: no public IP exists until the Gateway is applied, and it appears in `fact-checking`, not `nginx-gateway`.

```bash
# Install NGINX Gateway Fabric (chart moved to OCI registry — no helm repo add needed)
helm install ngf oci://ghcr.io/nginx/charts/nginx-gateway-fabric --namespace nginx-gateway --create-namespace

# Wait for the control-plane pod to be ready (~1 minute)
kubectl get pods -n nginx-gateway -w
# Press Ctrl+C once it shows "Running"

# Sanity check — the control-plane service stays ClusterIP/443. This is expected:
kubectl get svc -n nginx-gateway
# ngf-nginx-gateway-fabric   ClusterIP   10.x.x.x   <none>   443/TCP
```

#### Troubleshooting log: "no EXTERNAL-IP" rabbit hole (2026-06-11)

What actually happened during the first deployment, kept here so future-me doesn't repeat it. Every symptom below traces back to one misunderstanding: **treating the NGF control-plane service as the traffic entry point.**

**Symptom 1 — service is ClusterIP with no EXTERNAL-IP**
```
ngf-nginx-gateway-fabric   ClusterIP   10.0.53.124   <none>   443/TCP   23m
```
Wrong diagnosis: "the `--set service.type=LoadBalancer` flag didn't take effect." (The chart's *data-plane* default is in fact already `LoadBalancer` — see `nginx.service.type` in `helm show values`.)
Wrong fix: `kubectl patch svc ... -p '{"spec": {"type": "LoadBalancer"}}'` — this turned the **control plane** into a LoadBalancer, which Azure happily gave a public IP (`4.166.145.106`). That IP serves nothing.

**Symptom 2 — two different IPs that don't match**
- `kubectl describe gateway` → `Status.Addresses = 4.165.209.74` (the *real* data-plane LoadBalancer, auto-created by NGF in `fact-checking` when the Gateway was applied)
- `kubectl get svc -n nginx-gateway` → `4.166.145.106` (the wrongly patched control plane)

DNS got pointed at the control-plane IP. The Gateway status address was dismissed as stale. It was the correct one all along.

**Symptom 3 — cert-manager challenge stuck pending**
```
Reason: Waiting for HTTP-01 challenge propagation: failed to perform self check
GET 'http://factchecking.dpdns.org/.well-known/acme-challenge/<token>':
dial tcp 4.166.145.106:80: connect: connection refused
```
First it was `context deadline exceeded` (port 80 not open at all), then after manually patching port 80 onto the control-plane service it became `connection refused` — Azure now forwarded port 80, but the control-plane pod has no NGINX listening there. Nothing ever could have answered: it's a controller, not a proxy.

**Root cause**
NGF 2.x (installed: 2.6.3) split the architecture:

| | Control plane | Data plane |
|---|---|---|
| Created by | Helm install | NGF, **when a `Gateway` is applied** |
| Namespace | `nginx-gateway` | the Gateway's namespace (`fact-checking`) |
| Service | `ngf-nginx-gateway-fabric`, ClusterIP :443 (agent gRPC) | `<gateway-name>-nginx`, LoadBalancer, ports = Gateway listeners (80/443) |
| Public IP? | Never (by design) | Yes — this is what DNS must point at |

Older NGF 1.x docs/tutorials show a single LoadBalancer service in `nginx-gateway` — that's where the `--set service.type=LoadBalancer` advice (and the patching instinct) came from. It no longer applies.

**Correct resolution**
1. Leave the control-plane service alone (revert/uninstall any patches — a clean `helm uninstall ngf` + reinstall is fine).
2. Apply the `Gateway` resource (Step 3.2).
3. Read the IP from `kubectl get gateway -n fact-checking` (ADDRESS column) or the LoadBalancer service in `fact-checking`.
4. Point the Cloudflare A record at *that* IP. Port 80 is exposed automatically because the Gateway declares an HTTP :80 listener — no patches needed, and the cert-manager HTTP-01 challenge can complete.

### Step 2.3 — Install cert-manager

**What is cert-manager?** A k8s controller that automatically requests, renews, and stores TLS certificates. You tell it "I want a Let's Encrypt cert for factchecking.dpdns.org" via a `Certificate` resource, and it handles the ACME challenge and stores the cert as a k8s Secret
```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update

helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set crds.enabled=true \
  --set config.enableGatewayAPI=true   # REQUIRED: see note below

# Wait for cert-manager pods (~1–2 minutes)
kubectl get pods -n cert-manager -w
# Press Ctrl+C once all three pods show "Running"
```

> **Why `config.enableGatewayAPI=true` is required (not optional).** cert-manager's
> Gateway API support is OFF by default. We rely on it for two things, both of which
> silently no-op without the flag:
> 1. **gateway-shim** — turns the `cert-manager.io/cluster-issuer` annotation on the
>    `Gateway` into an actual `Certificate`. No flag → no Certificate → no TLS Secret.
> 2. **`gatewayHTTPRoute` HTTP-01 solver** (used by `cluster-issuer.yaml`) — answers the
>    ACME challenge by creating a temporary HTTPRoute on the Gateway.
>
> Without the flag the https (`:443`) listener stays `Invalid / InvalidCertificateRef`
> and the browser gets `ERR_CONNECTION_REFUSED` on HTTPS, even though every pod is healthy.
> Verify with `kubectl get certificate -n fact-checking` → it should reach `READY: True`.

### Step 2.4 — Get the Gateway IP and update DNS

> **Note:** the public IP only exists after the `Gateway` resource is applied (Phase 3, Step 3.2) — NGF 2.x provisions the data-plane LoadBalancer per Gateway, in the Gateway's namespace. Do Phase 3 up to Step 3.3 first, then come back here.

```bash
# Easiest: read the IP straight off the Gateway resource
kubectl get gateway -n fact-checking
# NAME                    CLASS   ADDRESS         PROGRAMMED   AGE
# fact-checking-gateway   nginx   4.x.x.x         True         1m

# Same IP, via the dynamically created data-plane service:
kubectl get svc -n fact-checking
# Look for a LoadBalancer service (named like fact-checking-gateway-nginx) with ports 80 + 443
```

Once you have the IP, go to Cloudflare (which manages `factchecking.dpdns.org`) and add:
```
Type:  A
Name:  @
Value: <EXTERNAL-IP from above>
TTL:   Auto
Proxy: DNS only (grey cloud)
```

`@` means "this domain itself" — since `factchecking.dpdns.org` is the full domain, not a subdomain.

Use **DNS only** (grey cloud), not Proxied — cert-manager's Let's Encrypt HTTP-01 challenge needs to reach your server directly. Cloudflare's proxy can interfere with certificate issuance.

Verify DNS has propagated (may take a few minutes):
```bash
nslookup factchecking.dpdns.org
# Should return the Azure IP
```

---

## Phase 3: Kubernetes manifests — deploy the app

**What are manifests?** YAML files that describe the desired state of your app. `kubectl apply` sends them to the cluster and k8s makes reality match.

The manifests are committed in `infra/k8s/` and are **not copied into this guide** (inlined copies went stale). Read the files; this section explains what each one is for. They are split into two kustomize tiers:

| Tier | Path | Applied | Contains |
|---|---|---|---|
| **bootstrap** | `infra/k8s/bootstrap/` | Once per new cluster (bootstrap workflow, or by hand) | `namespace`, `cluster-issuer`, `gatewayclass`, `gateway`, `server-pvc` (5Gi SQLite), `ollama-{pvc,deployment,service}` |
| **app** | `infra/k8s/app/` | Every release (deploy workflow) | `configmap`, `server-{deployment,service,httproute}`, `web-{deployment,service,httproute}`, image tags in `kustomization.yaml` |

Bootstrap is kept separate because re-applying it risks the PVCs, the Gateway's public IP and the TLS cert.

### Step 3.1 — Namespace and secrets

```bash
kubectl apply -f infra/k8s/bootstrap/namespace.yaml     # `fact-checking`: isolates the app from system components
```

**Never commit real secret values to git.** There is no Secret manifest; `app-secrets` is created imperatively (the bootstrap workflow does the same from GitHub secrets). Generate the signing secrets and fill `.env.prod` (already in `.gitignore`):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # JWT_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # SESSION_SECRET
```

```
JWT_SECRET=<generated>
SESSION_SECRET=<generated>
GOOGLE_CLIENT_ID=<Google Cloud Console>
GOOGLE_CLIENT_SECRET=<Google Cloud Console>
BRAVE_API_KEY=                       # optional
OPENROUTER_API_KEY=<openrouter.ai/keys>   # required when LLM_PROVIDER=openrouter
```

```bash
kubectl create secret generic app-secrets --from-env-file=.env.prod -n fact-checking
```

### Step 3.2 — Gateway, TLS issuer

```bash
kubectl apply -k infra/k8s/bootstrap
```

- **`cluster-issuer.yaml`** — a Let's Encrypt `ClusterIssuer` (`letsencrypt-prod`) using the HTTP-01 challenge. cert-manager is not a web server and has no public IP, so the solver's `gatewayHTTPRoute.parentRefs` points at `fact-checking-gateway` and cert-manager serves the challenge token through it.
- **`gatewayclass.yaml`** — binds `Gateway`s of class `nginx` to NGINX Gateway Fabric (`gateway.nginx.org/nginx-gateway-controller`).
- **`gateway.yaml`** — the entry point: listeners on :80 and :443 for `factchecking.dpdns.org`, TLS terminated with the `fact-checking-tls` Secret, and a `cert-manager.io/cluster-issuer: letsencrypt-prod` annotation.

How the annotation turns into a certificate:

```
cert-manager starts → watches Gateway resources
You apply the Gateway
  → cert-manager sees the cluster-issuer annotation
  → creates a Certificate resource
  → ACME HTTP-01 challenge via the Gateway → Let's Encrypt issues the cert
  → stored in the fact-checking-tls Secret
```

```bash
kubectl get certificate -n fact-checking    # READY should become True after ~1–2 minutes
```

The data-plane LoadBalancer (and its public IP) appears once the Gateway is applied — now do **Step 2.4** (DNS) if you have not.

### Step 3.3 — Build and push images

`deploy.yaml` builds and pushes immutable `sha-<full-sha>` images for you. To do it by hand (the image names must match `infra/k8s/app/kustomization.yaml`):

```bash
echo "<YOUR_GITHUB_TOKEN>" | docker login ghcr.io -u giang-h-vu --password-stdin   # PAT with write:packages

docker build -t ghcr.io/giang-h-vu/fact-checking-server:latest     ./server
docker build -t ghcr.io/giang-h-vu/fact-checking-web-client:latest ./web-client
docker push ghcr.io/giang-h-vu/fact-checking-server:latest
docker push ghcr.io/giang-h-vu/fact-checking-web-client:latest
```

Make both packages public (GitHub → Packages → *Package settings* → *Change visibility*) so AKS can pull without credentials, or create an `imagePullSecret`.

### Step 3.4 — The app tier

```bash
kubectl apply -k infra/k8s/app
```

**Why a ConfigMap?** Secrets hold sensitive values; the ConfigMap (`infra/k8s/app/configmap.yaml`) holds non-sensitive config you can read in git. The server Deployment loads both with `envFrom`.

LLM-related keys in the ConfigMap:

| Key | Meaning |
|---|---|
| `LLM_PROVIDER` | `openrouter` (hosted, current default) or `ollama` (in-cluster Service) |
| `OPENROUTER_MODEL` | Model slug, e.g. `anthropic/claude-haiku-4.5` |
| `OPENROUTER_FALLBACK_MODELS` | Optional comma-separated fallbacks tried in order if the primary errors |
| `OLLAMA_HOST` / `OLLAMA_MODEL` / `OLLAMA_NUM_CTX` | Used only when `LLM_PROVIDER=ollama` |

`OPENROUTER_API_KEY` comes from the `app-secrets` Secret, not the ConfigMap.

**Why a PVC for Ollama?** (Ollama mode only.) The `qwen2.5:7b-instruct` model is ~4.7 GB; without a PersistentVolumeClaim it would be re-downloaded on every pod restart. The PVC is an Azure Managed Disk that persists independently of the pod, including across `az aks stop/start`. The model is pulled in a `postStart` hook because the Ollama HTTP API must be up before `ollama pull` works. In OpenRouter mode this Deployment still runs but is idle — scale it to 0 to free its 6Gi memory request:

```bash
kubectl scale deployment/ollama -n fact-checking --replicas=0
```

## Phase 4: Stop/start the cluster to save credit

### Stop (run after every demo session)

```bash
az aks stop \
  --name fact-checking \
  --resource-group fact-checking

# Billing stops for worker nodes. Only PVC disks (~$0.75/mo) continue.
```

### Start (run before a demo)

```bash
az aks start \
  --name fact-checking \
  --resource-group fact-checking

# Takes ~3–5 minutes. Then verify pods are back:
kubectl get pods -n fact-checking
```

Save these as shell scripts for convenience:

```bash
# infra/scripts/stop.sh
az aks stop --name fact-checking --resource-group fact-checking

# infra/scripts/start.sh
az aks start --name fact-checking --resource-group fact-checking
```

```bash
mkdir -p infra/scripts
chmod +x infra/scripts/stop.sh infra/scripts/start.sh
```

---

## Phase 5: Post-deploy checklist

Work through these in order after all manifests are applied.

### 5.1 — Confirm TLS certificate is issued
```bash
kubectl get certificate -n fact-checking
# READY column should be "True". If not, wait 2 more minutes and retry.
# If still failing: kubectl describe certificate -n fact-checking  (shows ACME challenge status)
```

### 5.2 — Update Google OAuth redirect URI
Go to [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials → your OAuth 2.0 Client ID.

Under **Authorised redirect URIs**, add:
```
https://factchecking.dpdns.org/api/v1/auth/google/callback
```

### 5.3 — Confirm the LLM backend is reachable

```bash
# OpenRouter mode (LLM_PROVIDER=openrouter): the key must be in the Secret
kubectl get secret app-secrets -n fact-checking -o jsonpath='{.data.OPENROUTER_API_KEY}' | wc -c   # > 0
kubectl get configmap server-config -n fact-checking -o jsonpath='{.data.LLM_PROVIDER}{"\n"}{.data.OPENROUTER_MODEL}{"\n"}'

# Ollama mode (LLM_PROVIDER=ollama): the model must have been pulled onto the PVC
kubectl exec -n fact-checking deploy/ollama -- ollama list      # should show qwen2.5:7b-instruct
```

### 5.4 — Confirm all pods are running

```bash
kubectl get pods -n fact-checking
# NAME                      READY   STATUS    RESTARTS   AGE
# server-xxxxx              1/1     Running   0          3m
# web-xxxxx                 1/1     Running   0          2m
# ollama-xxxxx              1/1     Running   0          5m   <- applied by bootstrap even in OpenRouter mode (idle)
```
### 5.5 — End-to-end test
Open `https://factchecking.dpdns.org` in your browser. Submit a claim and watch the live SSE progress stream. Confirm a verdict and citations appear.

---

## Phase 6: GitHub Actions CI/CD (automated bootstrap + deploy)

Phases 1–5 are the **manual** path. The same steps are codified in two GitHub Actions workflows so you don't have to run them by hand:

- `.github/workflows/bootstrap.yaml` — one-time / rare, **manual trigger only** (`workflow_dispatch`). Mirrors Phase 2 + the stateful parts of Phase 3 (namespace, secret, ClusterIssuer, GatewayClass, Gateway, PVCs, Ollama). Run it once after `terraform apply` (re)creates the cluster.
- `.github/workflows/deploy.yaml` — the app promotion pipeline (`ci → test-tools → build-images → deploy`). Triggers on a `v*.*.*` tag, a published release, or a manual run. Builds immutable `sha-<full-sha>` images and rolls them out.

Both authenticate to Azure with **OIDC** (federated credentials) — there is no stored Azure password. Terraform (Phase 1) creates the identity and stays manual; this phase explains it and lists the GitHub secrets to set. `deploy.yaml` also gates on `ci.yaml` (spec lint, codegen drift, build, tests) and `test-tools.yaml` (real-API tool tests).

### 6.1 — How OIDC auth works (mental model)

```
managed identity     = the identity        (who the workflow acts as)
federated credential = the trust           (Azure accepts a GitHub token whose
                                            subject is this repo's `production`
                                            environment — instead of a password)
role assignment      = the permission      (what that identity may do, scoped to
                                            the fact-checking resource group)
```

GitHub mints a short-lived signed token for jobs running in the `production` environment, with subject `repo:giang-h-vu/fact-checking:environment:production`. Azure verifies that subject against the federated credential and issues an access token. Possession of the `AZURE_*` identifiers alone grants nothing — only a GitHub job in the `production` environment can produce an acceptable token.

### 6.2 — The identity is created by Terraform

All three pieces live in `infra/terraform/github-oidc.tf`, so `terraform apply` (Phase 1) already created them:

- `azurerm_user_assigned_identity.github_deploy` — a **user-assigned managed identity**, not an Entra app registration. It lives in the Azure RBAC plane, so creating it needs only subscription Owner/Contributor rights (no Application Administrator role); `azure/login` treats its client ID exactly like an app registration's.
- `azurerm_role_assignment.github_deploy_rg` — **Contributor**, scoped to the `fact-checking` resource group (not the subscription).
- `azurerm_federated_identity_credential.github_prod` — the trust rule. The `subject` is built from the `github_repository` and `github_environment` variables and must match the GitHub token's `sub` **exactly**, including the `:environment:production` suffix. A job running without that environment produces a different subject and is rejected, which is the intended safety property.

Print the three values GitHub needs:

```bash
cd infra/terraform
terraform output azure_client_id
terraform output azure_tenant_id
terraform output -raw azure_subscription_id
```

If you fork the repo, set `github_repository` in `terraform.tfvars` before applying.
### 6.3 — Configure GitHub secrets and variables

Create a **`production` environment** under Settings → Environments (this is what enables the approval gate and scopes the secrets below). Then add:

**Repository variables** (Settings → Secrets and variables → Actions → *Variables*) — non-sensitive, shared by both workflows:

| Variable | Value |
|---|---|
| `AKS_CLUSTER` | `fact-checking` |
| `AKS_RESOURCE_GROUP` | `fact-checking` |
| `K8S_NAMESPACE` | `fact-checking` |

**Environment secrets** (Settings → Environments → production → Environment secrets) — only readable by the gated `deploy` / `bootstrap` jobs:

| Secret | Source |
|---|---|
| `AZURE_CLIENT_ID` | `terraform output azure_client_id` |
| `AZURE_TENANT_ID` | `terraform output azure_tenant_id` |
| `AZURE_SUBSCRIPTION_ID` | `terraform output -raw azure_subscription_id` |
| `JWT_SECRET` | generated (Step 3.1) |
| `SESSION_SECRET` | generated (Step 3.1) |
| `GOOGLE_CLIENT_ID` | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console |
| `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) — required when the ConfigMap has `LLM_PROVIDER=openrouter` (see note below) |

**Repository secret** (Settings → Secrets and variables → Actions → *Secrets*):

| Secret | Why repository-scoped |
|---|---|
| `BRAVE_API_KEY` | Used by the `test-tools` job, which has **no** `environment:` (it also runs standalone and as a reusable call via `secrets: inherit`). An environment secret would be invisible to it. A gated job can still read repository secrets, so this one definition serves both `test-tools` and `bootstrap`. |

> **Known gap — `OPENROUTER_API_KEY`:** `bootstrap.yaml`'s *Create app-secrets* step currently passes only `JWT_SECRET`, `SESSION_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `BRAVE_API_KEY` into the `app-secrets` Secret. For OpenRouter mode add `--from-literal=OPENROUTER_API_KEY="${{ secrets.OPENROUTER_API_KEY }}"` to that step (and re-run bootstrap), or patch the Secret by hand — otherwise the server starts but every LLM call fails.

> `GITHUB_TOKEN` (used to push images to GHCR) is **auto-provided** per run — you never create or store it. Its scope is governed by the `permissions:` block in `deploy.yaml` (`packages: write`).

### 6.4 — Run order

1. **Terraform** (Phase 1) — create the cluster. Manual.
2. **bootstrap.yaml** — run once from the Actions tab (`workflow_dispatch`). Approve the `production` environment prompt. Note the Gateway IP it prints and set the Cloudflare A record (Step 2.4).
3. **deploy.yaml** — push a `v*.*.*` tag (or run manually) to build images and roll out the app.

First app deploy requires bootstrap to have run already (it depends on the namespace, secret, and PVCs that bootstrap creates).

---

## Useful kubectl commands for debugging

```bash
# See all resources in the app namespace
kubectl get all -n fact-checking

# Stream logs from the backend
kubectl logs -n fact-checking deploy/server -f

# Stream logs from Ollama (only if you run the in-cluster LLM)
kubectl logs -n fact-checking deploy/ollama -f

# Open a shell inside the backend pod
kubectl exec -it -n fact-checking deploy/server -- bash

# Describe a pod (shows events, resource usage, why it might be crashing)
kubectl describe pod -n fact-checking <pod-name>

# Check Gateway status and attached routes
kubectl describe gateway fact-checking-gateway -n fact-checking

# Check cert-manager certificate status
kubectl describe certificate -n fact-checking
```

---

## Tear down (when you're done with the project)

```bash
# Deletes ALL Azure resources (cluster, disks, load balancer, resource group)
cd infra/terraform
terraform destroy -var="subscription_id=<YOUR_SUBSCRIPTION_ID>"
# Type "yes" when prompted
```

This stops all billing immediately.
