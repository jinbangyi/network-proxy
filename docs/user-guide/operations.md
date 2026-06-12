# Operations Guide

This guide documents the main day-to-day actions for the current control plane.

## Join Request Lifecycle

1. Node agent submits `POST /join-requests`.
2. Admin reviews `GET /admin/join-requests`.
3. Admin approves or rejects the request.
4. Approved node polls `GET /join-requests/{id}` until it receives `node_id` and `node_token`.
5. Node starts polling `GET /nodes/{id}/desired-state` and reporting status.

## Node States You Will See

- `pending`
  join request exists but has not been reviewed
- `approved`
  join request approved and node token issued
- `provisioning`
  node record exists but has not yet applied desired state
- `active`
  node has reported desired state as applied
- `disabled`
  node has been removed from active publication by health remediation

## Manual Health Check

Run one health-check pass:

```bash
curl -X POST \
  -H "Authorization: Bearer admin-db" \
  http://127.0.0.1:9001/admin/health/run
```

Current behavior:

- tries a direct TCP connection to the node host and active port
- marks a healthy node as `healthy`
- increments retry count on failure
- rotates the direct port by `NETWORK_PROXY_HEALTH_CHECK_PORT_STEP`
- increments `desired_config_version` when rotating
- switches `published_mode` to `relay` after retry budget exhaustion when the node is relay-capable and has a fresh report
- disables a node after retry budget exhaustion only when relay fallback is not available

## Relay Fallback

Relay fallback currently requires all of the following:

- the node was approved with relay mode enabled
- the node has a fresh `last_report_at` timestamp within `NETWORK_PROXY_NODE_STALE_AFTER_SECONDS`
- the manager has a relay endpoint host and port configured
- the `manager-v2ray` relay profile is running so the generated relay config is actually served

When those conditions are met, the manager increments `desired_config_version`, switches the node to `published_mode=relay`, and waits for the node to apply the new desired state before probing the relay endpoint.

## Scheduled Health Checks

Enable the background worker with:

```bash
export NETWORK_PROXY_HEALTH_CHECK_ENABLED="true"
```

Useful related settings:

- `NETWORK_PROXY_HEALTH_CHECK_INTERVAL_SECONDS`
- `NETWORK_PROXY_HEALTH_CHECK_TIMEOUT_SECONDS`
- `NETWORK_PROXY_HEALTH_CHECK_PORT_STEP`

## Troubleshooting

If a node stays stuck in `pending`:

- verify the manager is reachable from the node
- verify the node is polling the correct `join_request_id`
- verify the admin approved the request

If a node stays stuck in `provisioning`:

- inspect the node state file
- inspect the desired-state file
- inspect the rendered runtime config file
- verify any configured validate or apply command actually works on the node host

If subscriptions are empty or denied:

- verify a subscription token exists
- verify the request includes `?token=...`
- verify the node is approved and not disabled
- verify `applied_config_version >= desired_config_version`

## Current Gaps

Current operations are still missing:

- full relay remediation and fallback
- full V2Ray reverse-bridge runtime packaging
- richer health probes beyond a direct TCP connection
