# Manager Quickstart

This guide shows how to start the manager, initialize tokens, and approve a node.

## Prerequisites

- `uv` installed locally
- the repository checked out
- a writable database path such as `data/network_proxy.db`

## Install Dependencies

Run:

```bash
uv sync
```

## Start The Manager

The manager entrypoint is `main.py`.

Run:

```bash
uv run python main.py serve
```

Optional host and port overrides:

```bash
uv run python main.py serve --host 0.0.0.0 --port 9001
```

Compose-based startup is also available:

```bash
cp deploy/manager/.env.example deploy/manager/.env
docker compose --env-file deploy/manager/.env -f deploy/manager/docker-compose.yml up --build -d
```

## Important Environment Variables

Common manager settings:

- `NETWORK_PROXY_DATABASE_URL`
- `NETWORK_PROXY_HOST`
- `NETWORK_PROXY_PORT`
- `NETWORK_PROXY_MANAGER_PUBLIC_URL`
- `NETWORK_PROXY_SUBCONVERTER_URL`
- `NETWORK_PROXY_HEALTH_CHECK_ENABLED`
- `NETWORK_PROXY_HEALTH_CHECK_INTERVAL_SECONDS`
- `NETWORK_PROXY_HEALTH_CHECK_TIMEOUT_SECONDS`
- `NETWORK_PROXY_HEALTH_CHECK_PORT_STEP`

Example:

```bash
export NETWORK_PROXY_DATABASE_URL="sqlite:///data/network_proxy.db"
export NETWORK_PROXY_MANAGER_PUBLIC_URL="http://127.0.0.1:9001"
export NETWORK_PROXY_HEALTH_CHECK_ENABLED="true"
```

## Create An Admin Token

Create a token explicitly:

```bash
uv run python main.py create-admin-token --name primary-admin --token admin-db
```

Or let the CLI generate one:

```bash
uv run python main.py create-admin-token --name primary-admin
```

The command prints the raw token once. Store it securely.

## Create A Subscription Token

Create a token for end-user subscription access:

```bash
uv run python main.py create-subscription-token --name default-subscription --token sub-db --description "default client access"
```

## Review Join Requests

List pending join requests:

```bash
curl -H "Authorization: Bearer admin-db" \
  http://127.0.0.1:9001/admin/join-requests
```

Approve a request:

```bash
curl -X POST \
  -H "Authorization: Bearer admin-db" \
  -H "Content-Type: application/json" \
  -d '{"assigned_port": 21001}' \
  http://127.0.0.1:9001/admin/join-requests/<join-request-id>/approve
```

Reject a request:

```bash
curl -X POST \
  -H "Authorization: Bearer admin-db" \
  -H "Content-Type: application/json" \
  -d '{"review_note": "not approved"}' \
  http://127.0.0.1:9001/admin/join-requests/<join-request-id>/reject
```

## Inspect Nodes

List current nodes:

```bash
curl -H "Authorization: Bearer admin-db" \
  http://127.0.0.1:9001/admin/nodes
```

## Health Checks

Trigger one manual health-check pass:

```bash
curl -X POST \
  -H "Authorization: Bearer admin-db" \
  http://127.0.0.1:9001/admin/health/run
```

If `NETWORK_PROXY_HEALTH_CHECK_ENABLED=true`, the manager also starts a background scheduler on app startup.

## Optional Relay Scaffold

The manager deployment also includes an opt-in `relay` compose profile.

Start it when you want the manager to serve relay-published endpoints:

```bash
docker compose --profile relay --env-file deploy/manager/.env -f deploy/manager/docker-compose.yml up -d manager-v2ray
```

The manager generates `data/manager/manager-v2ray-config.json` automatically from relay-published node state. The `manager-v2ray` service simply watches that file and restarts when it changes.
