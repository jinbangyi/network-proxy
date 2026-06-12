# Network Proxy Pool Plan

## Goal

Build a proxy-pool system in `/home/king/github/jinbangyi/network-proxy` with these capabilities:

- Use V2Ray core as the proxy server runtime.
- Use `subconverter` to expose multi-protocol subscription outputs.
- Use a `subscribe.py`-style service to publish subscription links.
- Allow proxy nodes to request to join the pool and wait for server approval.
- Allow the server to approve, reject, disable, and remove nodes.
- Continuously health-check approved nodes.
- On node failure, try port rotation and update the published pool.
- Remove a node from the pool after repeated remediation failure.

## Architecture

Split the system into two roles.

### 1. Manager Server

The manager server is the control plane.

- FastAPI service for node onboarding and admin operations.
- SQLite database for requests, nodes, health state, and retry history.
- Subscription publisher for raw links.
- `subconverter` sidecar for Clash and other client formats.
- Background scheduler for health checks and remediation.

### 2. Node Agent

Each proxy node runs V2Ray core plus a small node agent.

- Registers itself with the manager.
- Waits for approval.
- Accepts assigned port updates from the manager.
- Rewrites local V2Ray config.
- Restarts or reloads V2Ray after config changes.
- Reports its effective endpoint back to the manager.

This node agent is required because the manager must be able to increase the port number of an unhealthy node and keep the pool synchronized.

## Repository Layout

Use the existing repo and evolve it into a structured application.

```text
network-proxy/
├── docs/
├── deploy/
│   ├── manager/
│   └── node/
├── src/
│   ├── network_proxy/
│   │   ├── api/
│   │   ├── db/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── workers/
│   │   └── settings.py
│   ├── subscribe.py
│   └── node_agent.py
├── main.py
└── pyproject.toml
```

## Implementation Phases

### Phase 1: Refactor the current service entrypoint

Use `src/subscribe.py` as the initial anchor, but remove the current shell-based link scraping logic.

- Keep FastAPI as the HTTP layer.
- Move business logic into services and repositories.
- Keep `main.py` as a thin launch entrypoint.

### Phase 2: Add persistence with SQLite

Create the first database schema.

#### `join_requests`

- `id`
- `server_url`
- `callback_url`
- `requested_protocols`
- `requested_port`
- `metadata_json`
- `status` (`pending`, `approved`, `rejected`)
- `review_note`
- `created_at`
- `updated_at`

#### `nodes`

- `id`
- `join_request_id`
- `host`
- `active_port`
- `last_assigned_port`
- `protocol`
- `credential_json`
- `approval_status`
- `health_status`
- `retry_count`
- `max_retry_count`
- `callback_url`
- `last_check_at`
- `last_success_at`
- `created_at`
- `updated_at`

#### `health_events`

- `id`
- `node_id`
- `attempt_no`
- `probe_result`
- `old_port`
- `new_port`
- `action`
- `detail`
- `created_at`

#### `admin_tokens`

- `id`
- `name`
- `token_hash`
- `enabled`
- `created_at`

### Phase 3: Add onboarding and approval workflow

Add APIs so a proxy node can join the pool safely.

#### Node-facing APIs

- `POST /join-requests`
  Submit a node registration request.
- `GET /join-requests/{id}`
  Allow the node to poll approval status.
- `POST /nodes/{id}/report`
  Report the node's effective endpoint and health metadata.

#### Admin APIs

- `GET /admin/join-requests`
  List pending and historical requests.
- `POST /admin/join-requests/{id}/approve`
  Approve a request and assign the initial active port.
- `POST /admin/join-requests/{id}/reject`
  Reject a request with an optional reason.
- `GET /admin/nodes`
  List approved nodes and their health state.
- `POST /admin/nodes/{id}/disable`
  Disable a node without deleting history.
- `DELETE /admin/nodes/{id}`
  Remove a node from the pool.

Approval should create or activate the node record and return a configuration payload that the node agent can apply locally.

### Phase 4: Implement the node agent

The node agent is responsible for controlled node updates.

- Register the node with the manager.
- Poll for approval or receive approval callback.
- Render local V2Ray config from template.
- Apply port changes requested by the manager.
- Restart or reload V2Ray.
- Confirm the new endpoint after change.

The first version can use a shared secret per node instead of a more complex trust model.

### Phase 5: Normalize subscription generation

Replace process output scraping with database-backed subscription generation.

- Only approved and healthy nodes are included.
- Generate raw protocol links directly from stored node metadata.
- Base64-encode the raw list for standard subscription clients.
- Forward raw subscriptions into `subconverter` for Clash and other formats.

Expose at least:

- `GET /subscribe?token=...`
- `GET /subscribe/clash?token=...`

Optional follow-up endpoints can filter by protocol or node tag.

### Phase 6: Add active health checks and remediation

Run a background scheduler in the manager.

For each approved node:

1. Probe the currently published endpoint.
2. If reachable, mark the node healthy and reset retry count.
3. If unreachable, mark the node degraded.
4. Ask the node agent to increase its listening port within an allowed range.
5. Persist the new port candidate.
6. Re-probe after a short cooldown.
7. Repeat until `max_retry_count` is reached.
8. If all attempts fail, disable or remove the node and exclude it from subscriptions.

Every remediation attempt must be written into `health_events`.

### Phase 7: Deployment packaging

Define two Docker Compose stacks.

#### Manager stack

- FastAPI manager service
- SQLite-backed volume
- `subconverter`
- Optional central V2Ray instance if a shared ingress or relay role is needed later

#### Node stack

- V2Ray core
- Node agent
- Config template and persistent data volume

### Phase 8: Documentation and operations

Document:

- Manager bootstrap steps
- Node bootstrap steps
- Join request lifecycle
- Admin approval and removal flow
- Subscription URLs
- Health-check interval and retry policy
- Port rotation range and cooldown rules

## Reuse From Existing Repositories

Reuse patterns from the current V2Ray automation repo.

- `v2ray-docker-compose/subscriber/subscribe.py`
  FastAPI subscription service and `subconverter` integration pattern.
- `v2ray-docker-compose/subscriber/generate-v2ray-config.py`
  Programmatic V2Ray config mutation pattern.
- `v2ray-docker-compose/subscriber/docker-compose.yml`
  Manager stack shape with V2Ray and `subconverter`.
- `v2ray-docker-compose/v2ray-relay-server/clients.py`
  Protocol link generation examples.

## Verification Plan

Add focused tests and smoke checks for:

1. Pending to approved node transition.
2. Pending to rejected node transition.
3. Node removal and exclusion from subscription output.
4. Raw subscription generation from approved healthy nodes only.
5. `subconverter` integration on top of the raw subscription endpoint.
6. Health-check failure triggering port rotation.
7. Repeated health-check failure causing disable or removal.
8. One end-to-end smoke test with a healthy node and one failing node.

## Decisions For V1

- The joining entity is a proxy node, not an end-user account.
- The manager can actively reconfigure nodes through a node agent.
- SQLite is the preferred first persistence layer.
- The first version is API-first and does not require a full admin frontend.

## Out Of Scope For V1

- Multi-manager clustering
- Advanced SSO or OAuth flows
- Billing and quota management
- Non-V2Ray proxy runtimes
- A full browser admin dashboard

## Recommended Next Step

Start with the shortest critical path:

1. Refactor `src/subscribe.py` into the manager app.
2. Add SQLite models and repositories.
3. Implement join request and approval APIs.
4. Replace raw link scraping with database-backed subscriptions.
5. Add the node agent and health remediation loop.