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

1. A storage class that can bind a `ReadWriteOnce` PVC for SQLite + relay
   config JSON. The base asks for 1 GiB; the `default` overlay patches it to
   10 GiB with `storageClassName: standard` -- adjust both in your overlay.
   (Both relay pods land on the same node, so RWO is fine.)
2. An Ingress controller if you want to expose `manager-api` over HTTP(S).
3. cert-manager (optional) if you want TLS on the Ingress.

## Container image

The Deployment references `docker.io/jinbangyi/network-proxy:latest`, built by
`.github/workflows/docker-publish.yml` on every push to `master` and every `v*`
tag. The image is built to run as non-root UID/GID 1000 (see `Dockerfile`):
the uv venv and cache live under `/app` and are owned by that user, matching
the pod `securityContext.runAsUser: 1000` / `fsGroup: 1000` in
`base/manager-api.yaml`. Don't lower the security context to root -- the
image isn't laid out for it and you'd hit write errors from uv.

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
# NOTE: GET / requires a subscription token (returns 401 otherwise).
# Use /dashboard for an unauthenticated 200.
curl http://127.0.0.1:9001/dashboard
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

## Non-k8s alternative

If you just want to run the stack on a VM or localhost with docker compose,
use `scripts/onboard.sh` from the repo root. It wraps
`deploy/manager/docker-compose.yml` and `deploy/node/docker-compose.yml`,
handles workspace setup under `/opt/network-proxy` by default, and walks
through init / start / token creation / approve / status. See
`scripts/onboard.sh --help` for subcommands.

## Troubleshooting

These are the failures we hit while shaking down the manifests. Symptoms and
fixes recorded here so the next operator doesn't repeat the debug.

### `exec: "--host": executable file not found in $PATH`

**Cause:** container spec used `args:` instead of `command:`. With
`args:`-only, the kubelet keeps the image's `CMD ["uv","run","python","main.py","serve"]`
as the entrypoint and appends your args after it, producing a garbled command
line. This is the K8s vs docker-compose semantic gap -- docker-compose
`command:` replaces the whole CMD, K8s `args:` only replaces the args half.

**Fix:** the base manifest uses `command:` (full override). Don't migrate it
back to `args:`-only.

### `Failed to initialize cache at .uv-cache ... Permission denied`

**Cause:** pod runs as UID 1000 but the image's `/app/.uv-cache` (and
`.venv`) were created during `docker build` as root.

**Fix:** the Dockerfile creates a non-root `app` user (UID/GID 1000) and
switches to `USER app` before `uv sync`, so the venv and cache are owned by
the same UID that runs at runtime. Don't strip the `securityContext` -- the
image isn't laid out for root execution.

### `Readiness probe failed: HTTP probe failed with statuscode: 401`

**Cause:** the probe path was `GET /`, but in this app `/` is the
subscription endpoint and requires a `?token=` query param. Without a token
it returns 401.

**Fix:** both probes hit `GET /dashboard` instead, which is the only
unauthenticated 200-OK route in the codebase. If you add a dedicated
`GET /healthz` endpoint later, switch the probes to that.

### SQLite write errors on the PVC after the above fixes

If `fsGroup: 1000` doesn't propagate to a `subPath` mount on your storage
class (known to be inconsistent across CSI drivers), the next failure mode
is the SQLite DB at `/app/data/network_proxy.db` being unwritable. Workaround
options:

- Drop `subPath: manager` and mount the PVC root at `/app/data`.
- Add an `initContainer` that `chown -R 1000:1000 /app/data` before the
  manager container starts.
- Switch to a storage class that honours `fsGroup` on subPath mounts.
