# Network Proxy

`network-proxy` is a small manager and node-agent control plane for database-backed V2Ray subscription publishing.

The current implementation already includes:

- a FastAPI manager with admin, node, and subscription routes
- SQLite-backed join requests, nodes, and token storage
- a node agent that submits join requests, polls desired state, renders runtime config, and reports applied state
- a node deployment stack that runs both the node agent and a V2Ray sidecar against a shared runtime config volume
- base64, raw, and Clash subscription outputs
- direct-path health checks with port-rotation remediation

The current implementation now supports health-driven fallback from direct publication into relay publication for relay-capable nodes with fresh manager connectivity. Manager-side relay runtime packaging is still manual scaffolding rather than fully automated config generation.

## Quickstart

Install dependencies:

```bash
uv sync
```

Start the manager locally:

```bash
uv run python main.py serve
```

Create bootstrap tokens:

```bash
uv run python main.py create-admin-token --name primary-admin --token admin-db
uv run python main.py create-subscription-token --name default-subscription --token sub-db
```

Run one node-agent reconciliation step:

```bash
uv run python src/node_agent.py --once
```

## Deployment Artifacts

Initial deployment files live under `deploy/`.

- `deploy/manager/docker-compose.yml`
  manager API plus `subconverter`
- `deploy/manager/.env.example`
  manager stack environment defaults
- `deploy/manager/bootstrap.sh`
  creates local directories and prints bootstrap commands
- `deploy/manager/run-manager-v2ray.sh`
  relay-runtime watcher that reloads the manager-generated V2Ray config
- `deploy/node/docker-compose.yml`
  node-agent plus node-side V2Ray runtime stack
- `deploy/node/.env.example`
  node-agent stack environment defaults
- `deploy/node/bootstrap.sh`
  creates local directories and prints node startup commands
- `deploy/node/run-node-v2ray.sh`
  watches the rendered config and restarts the node-side V2Ray runtime on marker changes

Manager stack example:

```bash
docker compose \
  --env-file deploy/manager/.env.example \
  -f deploy/manager/docker-compose.yml \
  up --build
```

Node stack example:

```bash
docker compose \
  --env-file deploy/node/.env.example \
  -f deploy/node/docker-compose.yml \
  up --build
```

Optional manager relay profile:

```bash
docker compose \
  --profile relay \
  --env-file deploy/manager/.env.example \
  -f deploy/manager/docker-compose.yml \
  up -d manager-v2ray
```

The relay profile watches `data/manager/manager-v2ray-config.json` and restarts V2Ray when that file changes. That config is generated automatically from relay-published node state.

## Compose Happy Path

This is the current end-to-end operator path using only repository artifacts.

1. Prepare the manager environment.

```bash
cp deploy/manager/.env.example deploy/manager/.env
mkdir -p data/manager
docker compose --env-file deploy/manager/.env -f deploy/manager/docker-compose.yml up --build -d
```

1. Create the admin and subscription tokens inside the running manager container.

```bash
docker compose --env-file deploy/manager/.env -f deploy/manager/docker-compose.yml exec manager-api \
  uv run python main.py create-admin-token --name primary-admin --token admin-db

docker compose --env-file deploy/manager/.env -f deploy/manager/docker-compose.yml exec manager-api \
  uv run python main.py create-subscription-token --name default-subscription --token sub-db
```

1. Prepare and start one node stack.

```bash
cp deploy/node/.env.example deploy/node/.env
mkdir -p data/node
docker compose --env-file deploy/node/.env -f deploy/node/docker-compose.yml up --build -d
```

1. Confirm the manager received a pending join request.

```bash
curl -H "Authorization: Bearer admin-db" \
  http://127.0.0.1:9001/admin/join-requests
```

1. Approve that join request. Keep the assigned port aligned with `NETWORK_PROXY_NODE_PUBLISHED_PORT` in `deploy/node/.env` for the first direct-mode pass.

```bash
curl -X POST \
  -H "Authorization: Bearer admin-db" \
  -H "Content-Type: application/json" \
  -d '{"assigned_port": 21001}' \
  http://127.0.0.1:9001/admin/join-requests/<join-request-id>/approve
```

1. Verify that the node agent rendered and applied the runtime config.

```bash
docker compose --env-file deploy/node/.env -f deploy/node/docker-compose.yml logs node-agent --tail 50
ls data/node
```

The node stack writes:

- `data/node/node-agent-state.json`
- `data/node/node-desired-state.json`
- `data/node/node-v2ray-config.json`

The node agent touches `data/node/node-v2ray-reload.marker`, and the `node-v2ray` sidecar restarts against the updated config.

1. Fetch the published subscription output.

```bash
curl "http://127.0.0.1:9001/subscribe/raw?token=sub-db"
curl "http://127.0.0.1:9001/subscribe?token=sub-db"
```

## Documentation

Operator guides are in `docs/user-guide/`.

- `docs/user-guide/manager-quickstart.md`
- `docs/user-guide/node-agent-quickstart.md`
- `docs/user-guide/subscriptions.md`
- `docs/user-guide/operations.md`

## Current Limitations

- join requests are not yet protected by a manager-side join secret
- manager-side relay runtime is still an opt-in compose profile
- relay publication still depends on the `manager-v2ray` profile actually running
