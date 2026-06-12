# Subscriptions Guide

This guide describes how subscription access works in the current implementation.

## Access Model

Subscription endpoints require a token.

Valid tokens can come from either source:

- `NETWORK_PROXY_SUBSCRIPTION_TOKEN`
- a token stored in the `subscription_tokens` database table

If neither exists, subscription endpoints return `503` because access is not configured.

## Create A Subscription Token

CLI example:

```bash
uv run python main.py create-subscription-token --name default-subscription --token sub-db
```

API example:

```bash
curl -X POST \
  -H "Authorization: Bearer admin-db" \
  -H "Content-Type: application/json" \
  -d '{"name": "default-subscription", "token": "sub-db", "description": "default access"}' \
  http://127.0.0.1:9001/admin/subscription-tokens
```

## Available Endpoints

Base64 subscription:

```bash
curl "http://127.0.0.1:9001/subscribe?token=sub-db"
```

Raw newline-delimited links:

```bash
curl "http://127.0.0.1:9001/subscribe/raw?token=sub-db"
```

Clash conversion through `subconverter`:

```bash
curl "http://127.0.0.1:9001/subscribe/clash?token=sub-db"
```

## Publication Rules

Current subscription output prefers node records from the database.

A node is published when:

- `approval_status` is `approved`
- `lifecycle_status` is not `disabled`
- `applied_config_version >= desired_config_version`
- the node has enough data to render a subscription link

If no eligible database-backed nodes exist, the service falls back to bootstrap links from settings.

## Current Protocol Scope

The current subscription builder only emits `vmess://` links.

Relay-mode publication is available when a node's `published_mode` is switched to `relay` and the node has relay endpoint metadata. The manager health service now performs that switch automatically after direct remediation fails for a relay-capable node with a fresh report, and the manager generates the relay runtime config automatically from that node state.
