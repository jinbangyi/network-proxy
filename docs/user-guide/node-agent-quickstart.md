# Node Agent Quickstart

This guide shows how to start one node agent and let it reconcile against the manager.

## Prerequisites

- manager running and reachable
- admin token already created on the manager
- `uv sync` already completed in the repo

## Important Environment Variables

The node agent reads its configuration from `NETWORK_PROXY_...` settings.

Core node settings:

- `NETWORK_PROXY_NODE_MANAGER_URL`
- `NETWORK_PROXY_NODE_NAME`
- `NETWORK_PROXY_NODE_PUBLIC_HOST`
- `NETWORK_PROXY_NODE_REGION`
- `NETWORK_PROXY_NODE_REQUESTED_PROTOCOLS`
- `NETWORK_PROXY_NODE_REQUESTED_MODES`
- `NETWORK_PROXY_NODE_REQUESTED_PORT`
- `NETWORK_PROXY_NODE_STATE_FILE`
- `NETWORK_PROXY_NODE_DESIRED_STATE_FILE`
- `NETWORK_PROXY_NODE_RUNTIME_CONFIG_FILE`
- `NETWORK_PROXY_NODE_VALIDATE_COMMAND`
- `NETWORK_PROXY_NODE_APPLY_COMMAND`

Example:

```bash
export NETWORK_PROXY_NODE_MANAGER_URL="http://127.0.0.1:9001"
export NETWORK_PROXY_NODE_NAME="node-jp-1"
export NETWORK_PROXY_NODE_PUBLIC_HOST="node-jp-1.example.com"
export NETWORK_PROXY_NODE_REGION="jp"
export NETWORK_PROXY_NODE_REQUESTED_PROTOCOLS="vmess"
export NETWORK_PROXY_NODE_REQUESTED_MODES="direct,relay"
export NETWORK_PROXY_NODE_REQUESTED_PORT="21001"
export NETWORK_PROXY_NODE_STATE_FILE="data/node-agent-state.json"
export NETWORK_PROXY_NODE_DESIRED_STATE_FILE="data/node-desired-state.json"
export NETWORK_PROXY_NODE_RUNTIME_CONFIG_FILE="data/node-v2ray-config.json"
```

## Run One Reconciliation Step

Use one-shot mode while testing:

```bash
uv run python src/node_agent.py --once
```

Behavior:

1. First run creates a join request.
2. Later run polls for approval.
3. After approval, the agent fetches desired state.
4. The agent renders a runtime config file.
5. The agent optionally runs validate and apply commands.
6. The agent sends heartbeat and report updates back to the manager.

## Run Continuously

```bash
uv run python src/node_agent.py --interval 10
```

Compose-based startup is also available and currently starts both the node agent and a V2Ray sidecar:

```bash
cp deploy/node/.env.example deploy/node/.env
docker compose --env-file deploy/node/.env -f deploy/node/docker-compose.yml up --build -d
```

## Local Files Written By The Agent

- state file
  tracks `join_request_id`, `node_id`, `node_token`, current status, and runtime metadata
- desired-state file
  stores the latest desired state from the manager
- runtime config file
  stores the rendered V2Ray JSON that the node should run

## Runtime Commands

The agent can call operator-provided commands after rendering the runtime config.

In the provided compose stack, the defaults are already wired:

- validate command checks that the rendered config file exists and is non-empty
- apply command touches `data/node/node-v2ray-reload.marker`
- the `node-v2ray` sidecar watches that marker and restarts V2Ray against the rendered config

Example:

```bash
export NETWORK_PROXY_NODE_VALIDATE_COMMAND="v2ray test -config data/node-v2ray-config.json"
export NETWORK_PROXY_NODE_APPLY_COMMAND="systemctl restart v2ray"
```

If these settings are not provided, validation and apply steps are skipped and the agent still reports the rendered config path.
