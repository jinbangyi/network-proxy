# Kubernetes deployment (ArgoCD / GitOps)

This directory contains Kustomize manifests for deploying the network-proxy
manager control plane to Kubernetes. Two overlays ship out of the box:

| Overlay | Includes | Use when |
| --- | --- | --- |
| `overlays/default` | `manager-api` + `subconverter` + `Ingress` | You only want the API, dashboard, and direct/node subscriptions. |
| `overlays/relay`   | everything in `default` + `manager-v2ray` relay pod | You also want the manager-hosted relay feature. Requires a node with a public IP. |

## Layout

```
deploy/k8s/
├── base/                          # shared manifests
│   ├── kustomization.yaml
│   ├── namespace.yaml             # Namespace: network-proxy
│   ├── configmap.yaml             # non-secret env for manager-api
│   ├── secret.yaml                # placeholder tokens -- REPLACE
│   ├── subconverter-pref-configmap.yaml
│   ├── manager-api.yaml           # Deployment + Service + PVC (port 9001)
│   ├── subconverter.yaml          # Deployment + Service (port 25500)
│   └── ingress.yaml               # sample Ingress -- patch host in overlay
└── overlays/
    ├── default/
    │   └── kustomization.yaml     # base + host patch for Ingress
    └── relay/
        ├── kustomization.yaml     # base + manager-v2ray resources
        ├── manager-v2ray-script.yaml
        └── manager-v2ray.yaml     # hostNetwork Deployment + headless Service
```

## Prerequisites on the cluster

1. A storage class that can bind a 1 GiB `ReadWriteOnce` PVC for SQLite + relay
   config JSON. (Both relay pods land on the same node, so RWO is fine.)
2. An Ingress controller if you want to expose `manager-api` over HTTP(S).
3. cert-manager (optional) if you want TLS on the Ingress.

## Required GitHub secrets (for the CI that builds the image)

The workflow at `.github/workflows/docker-publish.yml` pushes the image to
`docker.io/jinbangyi/network-proxy`. In the repo settings under
*Settings -> Secrets and variables -> Actions* add:

| Secret name | Value |
| --- | --- |
| `DOCKERHUB_USERNAME` | Your Docker Hub username (`jinbangyi`) |
| `DOCKERHUB_TOKEN`    | A Docker Hub personal access token with read/write on the repo |

After a successful run on `master`, tags `latest`, `master`, and `sha-<short>`
are available. Tags pushed as `v1.2.3` produce `1.2.3`, `1.2`, `1`, and
`latest`.

## Quick start: ArgoCD app pointing at the default overlay

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: network-proxy
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jinbangyi/network-proxy
    targetRevision: master
    path: deploy/k8s/overlays/default
  destination:
    server: https://kubernetes.default.svc
    namespace: network-proxy
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

For the relay overlay change `path:` to `deploy/k8s/overlays/relay`.

## Required pre-deploy customisation

These are placeholder values that **must** be patched before the manifests hit
a real cluster. The recommended pattern is a third overlay that inherits from
`default` or `relay` and patches them -- do not edit `base/` for site-specific
values.

1. **Secret `manager-api-secrets`** (`base/secret.yaml`) -- placeholder tokens.
   Better: create the secret out-of-band so the token never lives in git:
   ```bash
   kubectl -n network-proxy create secret generic manager-api-secrets \
     --from-literal=NETWORK_PROXY_ADMIN_TOKEN=$(openssl rand -hex 24) \
     --from-literal=NETWORK_PROXY_SUBSCRIPTION_TOKEN=$(openssl rand -hex 24) \
     --dry-run=client -o yaml | kubectl apply -f -
   ```
   Then add a `$patch: delete` for `base/secret.yaml` in your overlay so ArgoCD
   doesn't fight you for ownership of the secret.

2. **Ingress host** -- patch `spec.rules[0].host` from `np.example.com` to your
   hostname (the `default` overlay already does this patch -- replace the value
   there).

3. **`NETWORK_PROXY_MANAGER_PUBLIC_URL`** in `base/configmap.yaml` -- the
   external URL clients and nodes use to reach the manager API. Defaults to the
   in-cluster Service DNS.

4. **(relay overlay only)** `NETWORK_PROXY_MANAGER_RELAY_PUBLIC_HOST` -- the
   public hostname / IP of the node that runs `manager-v2ray`. Add a
   `nodeSelector` to the manager-v2ray Deployment so it lands on a node with a
   public IP and a firewall that allows the relay port pool.

## Pinning the image tag

`base/kustomization.yaml` declares:

```yaml
images:
  - name: jinbangyi/network-proxy
    newTag: latest
```

Both overlays inherit and re-declare it as `latest`. To pin a specific CI build,
override `newTag` in your own overlay (e.g. `newTag: sha-abc1234` or
`newTag: 1.2.3`). Or run [ArgoCD Image Updater](https://argocd-image-updater.readthedocs.io/)
against the `docker.io/jinbangyi/network-proxy` registry to advance the tag
automatically.

## Local test without ArgoCD

```bash
# Render
kubectl kustomize deploy/k8s/overlays/default

# Apply
kubectl apply -k deploy/k8s/overlays/default

# Check
kubectl -n network-proxy get pods,svc,ingress
kubectl -n network-proxy port-forward svc/manager-api 9001:9001
curl http://127.0.0.1:9001/
```

## Notes on the relay overlay

`manager-v2ray` runs with `hostNetwork: true` and binds a pool of inbound ports
(default starts at 31001 with 20 ports). This is the only practical option
given v2ray's dynamic port pool. Consequences:

- The pod's host IP is what clients connect to. Set
  `NETWORK_PROXY_MANAGER_RELAY_PUBLIC_HOST` to that IP / hostname.
- `manager-api` and `manager-v2ray` must be co-scheduled on the same node so
  they share the PVC that holds `manager-v2ray-config.json`. Either use a
  `ReadWriteMany` storage class or a `podAffinity` with
  `requiredDuringSchedulingIgnoredDuringExecution`.
- The Ingress / Service doesn't cover the relay ports -- they must be allowed
  through the node's firewall / cloud security group directly.
