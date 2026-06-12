# Network Proxy Pool Plan

## Goal

Build a proxy-pool system in `/home/king/github/jinbangyi/network-proxy` with these capabilities:

- Use V2Ray core as the data-plane runtime.
- Use `subconverter` to publish Clash and other client formats.
- Replace the current shell-based `subscribe.py` scraping flow with database-backed subscriptions.
- Allow proxy nodes to request to join the pool and wait for admin approval.
- Allow the manager to approve, reject, disable, reconfigure, and remove nodes.
- Support both traffic modes required by the task:
  - direct mode: `user -> node`
  - relay mode: `user -> manager -> node`
- Continuously health-check approved nodes.
- On direct-path failure, try port rotation and update published subscriptions.
- Fall back to relay mode when direct mode is blocked but node-to-manager connectivity still works.
- Remove or disable a node after repeated remediation failure.

## Problem Statement

The system has three actors with different needs.

- Admin
  - bootstraps a manager with Docker
  - approves or rejects node join requests
  - disables or removes unhealthy nodes
  - distributes subscription links to end users
- Node operator
  - starts a node with Docker
  - points the node agent at the manager
  - waits for approval
  - lets the manager drive future config changes
- End user
  - consumes one subscription URL
  - imports that URL into clients such as v2rayN, Clash, and FlClash
  - gets updated endpoints automatically when the manager rotates ports or switches publish mode

The design must keep those workflows simple while still handling the hard case where a node is reachable from one region but blocked from another.

## Current Starting Point

The repo currently starts from a minimal FastAPI service in `src/subscribe.py`.

- Subscription output is still built by shelling out to `v2ray url`.
- Clash conversion is hard-coded to a local `subconverter` endpoint.
- There is no persistence layer, node registry, admin API, or node agent yet.
- `main.py` is only a placeholder and is not yet the real service entrypoint.

This means V1 should be implemented as an incremental refactor rather than a full rewrite in one step.

## Success Criteria

V1 is complete when all of the following are true.

1. The manager can be started with Docker and persists state in SQLite.
2. A new node can be started with Docker, submit a join request, and wait for approval.
3. An admin can approve or reject join requests using API calls.
4. Approval creates a working node record and returns node credentials for future authenticated sync.
5. The node agent can poll desired state, render V2Ray config, restart V2Ray, and report the applied version.
6. `/subscribe` returns a valid base64 subscription built from the database rather than process scraping.
7. `/subscribe/clash` returns converted output through `subconverter`.
8. Only approved and currently publishable nodes appear in subscriptions.
9. Health checks can detect a direct-path failure, rotate the node port, and republish the updated endpoint.
10. If repeated direct remediation fails but relay remains available, the manager can switch the node to relay mode.
11. If neither direct nor relay mode is usable, the node is disabled and removed from published subscriptions.

## Delivery Strategy

Use an incremental refactor tied to the current codebase.

- Preserve the current FastAPI surface early, especially `/subscribe` and `/subscribe/clash`.
- Move logic out of `src/subscribe.py` into a real package under `src/network_proxy/`.
- Keep direct-mode subscriptions as the first working data plane.
- Build the node control loop around manager-defined desired state and node-initiated sync.
- Add relay mode only after the direct control plane is stable.

This sequence keeps the first deliverable small enough to verify, while leaving the data model ready for the bidirectional channel required by the task.

## V1 Scope

V1 should deliver a usable control plane plus a bootstrap node stack.

- Manager server with admin and node APIs.
- SQLite-backed registry for join requests, nodes, health state, credentials, and published subscription entries.
- Node agent that keeps an outbound control connection to the manager.
- Direct subscription output for approved healthy nodes.
- Relay-capable design so nodes can still serve traffic through the manager when direct ingress is blocked.
- Automated health checks and port remediation for direct-mode endpoints.
- Docker Compose packaging for both manager and node roles.

## Non-Goals For V1

- Multi-manager clustering
- Cross-region replicated health-check workers
- Browser admin dashboard
- Billing, quota, or user account management
- Support for non-V2Ray runtimes
- Zero-downtime hot reload guarantees across every node type

## Architecture Principles

- Keep the manager authoritative for desired configuration.
- Keep nodes authoritative for what they have actually applied.
- Never depend on manager-to-node inbound access for control.
- Publish only endpoints that can be justified by recent node state and health data.
- Persist every approval, reconfiguration, and remediation step.
- Prefer simple bootstrapping and a small dependency set over premature generalization.

## Runtime Architecture

Split the system into two roles.

### 1. Manager Server

The manager server is the control plane and subscription publisher.

- FastAPI service for onboarding, admin operations, subscriptions, and node state sync.
- SQLite database for requests, nodes, desired config state, health events, and tokens.
- `subconverter` sidecar for Clash and other derived subscription formats.
- Background scheduler for health checks and remediation.
- Optional manager-side V2Ray instance for relay ingress.

Manager responsibilities:

- accept node join requests
- issue node credentials after approval
- hold desired state for every node
- generate raw subscription links
- convert those raw links through `subconverter`
- run health probes from the manager-side network
- rotate ports and switch publish mode when required

### 2. Node Agent

Each proxy node runs V2Ray core plus a small node agent.

- Registers itself with the manager.
- Polls or long-polls desired state from the manager.
- Renders local V2Ray config from templates.
- Restarts or reloads V2Ray after config changes.
- Reports applied config version, effective endpoint, and health metadata back to the manager.
- Optionally maintains a relay bridge toward the manager.

Node-agent responsibilities:

- bootstrap once with minimal operator input
- continue operating behind NAT or a firewall
- reconcile manager desired state with local V2Ray runtime
- expose enough status for the manager to make publishing decisions

The node agent must be node-initiated. The manager must not depend on direct callback access to the node, because many nodes will sit behind NAT or restrictive firewalls.

## Data-Plane Modes

The plan must support two distinct ways users consume proxies.

### Direct mode

- The manager publishes a node's public host and assigned port.
- End users connect directly to the node.
- This is the preferred fast path when the node endpoint is reachable from the target region.
- Health checks probe this path from the manager network, which should be treated as the primary user-region proxy for V1.

### Relay mode

- The manager publishes a manager-hosted ingress endpoint.
- The node establishes the server-side leg from node to manager.
- End users connect to the manager, and traffic is relayed onward to the node.
- This mode is required for the case where `user -> node` is blocked but `node -> manager` still works.

### Proposed Relay Topology

For V1, the preferred V2Ray topology is:

- manager side: relay ingress plus reverse portal
- node side: reverse bridge plus local outbound to the node's own V2Ray service

The exact V2Ray JSON may change during implementation, but the manager and node models must already store relay capability and relay endpoint metadata.

## Protocol Strategy

V1 should minimize protocol surface area.

- Pick one primary upstream proxy protocol for node templates.
- Prefer whichever protocol matches the existing reference scripts most closely.
- Use raw subscription generation plus `subconverter` to satisfy different client formats.

Recommended V1 default:

- keep a single protocol template end to end for the first implementation
- publish multiple client-consumable outputs from the same source subscription
- postpone multi-protocol node runtime support until the control plane is stable

## State Model

The control plane needs explicit state transitions.

### Join Request States

- `pending`
  - node submitted request and is waiting for admin review
- `approved`
  - admin accepted request and manager created an active node record
- `rejected`
  - admin rejected request and no active node should be created
- `expired`
  - optional follow-up state for old pending requests not acted on in time

### Node States

- `provisioning`
  - approved but node has not yet reported an applied config
- `active`
  - node is healthy and publishable in direct or relay mode
- `degraded`
  - node exists but current published mode is unhealthy or stale
- `relay_only`
  - direct mode is not publishable but relay mode is healthy
- `disabled`
  - node remains in inventory but is excluded from subscriptions
- `removed`
  - node is deleted from the active pool and preserved only in audit history if needed later

### Desired-State Flow

Each node should reconcile against a versioned desired-state record.

1. Manager increments `desired_config_version`.
2. Node agent fetches the new desired state.
3. Node agent renders config locally.
4. Node agent restarts or reloads V2Ray.
5. Node agent reports `applied_config_version` with effective endpoint data.
6. Manager marks the node reconciled if the report matches the desired version.

This versioned flow is the control boundary for port rotation, credential updates, publish-mode changes, and relay enablement.

## Repository Layout

Use the existing repo and evolve it into a structured application.

```text
network-proxy/
├── docs/
├── deploy/
│   ├── manager/
│   │   ├── docker-compose.yml
│   │   ├── .env.example
│   │   └── bootstrap.sh
│   └── node/
│       ├── docker-compose.yml
│       ├── .env.example
│       └── bootstrap.sh
├── src/
│   ├── network_proxy/
│   │   ├── api/
│   │   │   ├── admin.py
│   │   │   ├── node.py
│   │   │   ├── subscribe.py
│   │   │   └── deps.py
│   │   ├── db/
│   │   │   ├── models.py
│   │   │   ├── migrations.py
│   │   │   └── session.py
│   │   ├── repositories/
│   │   ├── services/
│   │   │   ├── onboarding.py
│   │   │   ├── subscriptions.py
│   │   │   ├── health.py
│   │   │   ├── relay.py
│   │   │   └── config_render.py
│   │   ├── workers/
│   │   │   └── scheduler.py
│   │   ├── templates/
│   │   │   ├── node-direct.json.j2
│   │   │   └── node-relay.json.j2
│   │   └── settings.py
│   ├── subscribe.py
│   └── node_agent.py
├── tests/
│   ├── api/
│   ├── services/
│   └── smoke/
├── main.py
└── pyproject.toml
```

`src/subscribe.py` should remain the first refactor anchor, then shrink into a thin compatibility entrypoint once the manager package exists.

## Dependency Plan

The current dependency set is too small for the full control plane.

Add or evaluate these libraries during implementation:

- `sqlalchemy`
  - ORM and SQLite session handling
- `alembic`
  - migrations, if we want tracked schema evolution instead of bootstrap-only DDL
- `httpx`
  - manager-side HTTP calls and health probes
- `pydantic-settings`
  - structured environment-driven settings
- `jinja2`
  - rendering V2Ray config templates
- `apscheduler`
  - background scheduling more suitable than the current `schedule` library for service-style execution

Keep these current dependencies unless implementation proves they are no longer useful:

- `fastapi`
- `uvicorn`
- `click`

## Security Model

V1 security should be simple but explicit.

### Admin Access

- Admin APIs require `Authorization: Bearer <admin-token>`.
- Admin tokens are stored hashed in `admin_tokens`.
- Provide a one-time bootstrap CLI command to create the first admin token.

### Node Bootstrap

- Joining a node should require a manager bootstrap secret or join secret so the public join endpoint is not fully open.
- On approval, the manager issues a per-node token.
- All later node calls use `Authorization: Bearer <node-token>`.
- Node tokens are stored hashed and tied to one node record.

### Subscription Access

- Subscription endpoints require a user-facing subscription token.
- Subscription tokens are stored hashed in a dedicated table.
- One token may map to one audience or distribution group.
- Disabling a subscription token should revoke access immediately without changing node records.

## Core Data Model

Create the first SQLite schema around five core tables.

### `join_requests`

- `id`
- `node_name`
- `server_url`
- `agent_version`
- `requested_protocols`
- `requested_port`
- `requested_modes` (`direct`, `relay`, or both)
- `public_host`
- `region`
- `metadata_json`
- `status` (`pending`, `approved`, `rejected`, `expired`)
- `review_note`
- `created_at`
- `updated_at`

Indexes:

- `status`
- `created_at`

### `nodes`

- `id`
- `join_request_id`
- `node_name`
- `public_host`
- `region`
- `protocol`
- `active_port`
- `last_assigned_port`
- `credential_json`
- `approval_status`
- `lifecycle_status`
- `health_status`
- `published_mode`
- `direct_enabled`
- `relay_enabled`
- `relay_public_host`
- `relay_public_port`
- `desired_config_version`
- `applied_config_version`
- `retry_count`
- `max_retry_count`
- `last_check_at`
- `last_success_at`
- `last_report_at`
- `created_at`
- `updated_at`

Indexes:

- `approval_status`
- `lifecycle_status`
- `health_status`
- `published_mode`
- `last_report_at`

### `health_events`

- `id`
- `node_id`
- `attempt_no`
- `probe_scope` (`direct`, `relay`)
- `probe_result`
- `old_port`
- `new_port`
- `action`
- `detail`
- `created_at`

Indexes:

- `node_id`
- `created_at`

### `admin_tokens`

- `id`
- `name`
- `token_hash`
- `enabled`
- `created_at`

### `subscription_tokens`

- `id`
- `name`
- `token_hash`
- `enabled`
- `description`
- `expires_at`
- `created_at`

## API Plan

The APIs should separate public node flows from admin-only flows.

### Node-Facing APIs

#### `POST /join-requests`

Purpose:

- submit a node registration request

Request body:

- `node_name`
- `public_host`
- `region`
- `requested_protocols`
- `requested_port`
- `requested_modes`
- `agent_version`
- `metadata`

Response:

- `join_request_id`
- `status`
- `poll_after_seconds`

#### `GET /join-requests/{id}`

Purpose:

- poll approval status before the node is activated

Response states:

- `pending`
- `approved` with `node_id` and bootstrap credentials
- `rejected` with `review_note`

#### `GET /nodes/{id}/desired-state`

Purpose:

- fetch the desired config version and assigned settings

Behavior:

- support long polling with `wait_seconds`
- return `304`-style no-change semantics or equivalent compact response when the version is unchanged

Response fields:

- `desired_config_version`
- `protocol`
- `publish_mode`
- `direct_config`
- `relay_config`
- `health_policy`

#### `POST /nodes/{id}/report`

Purpose:

- report applied config version, effective endpoint, and health metadata

Request body:

- `applied_config_version`
- `direct_effective_host`
- `direct_effective_port`
- `relay_effective_host`
- `relay_effective_port`
- `runtime_metadata`

#### `POST /nodes/{id}/heartbeat`

Purpose:

- send liveness and capability metadata on a regular interval

Request body:

- `agent_version`
- `v2ray_version`
- `local_status`
- `supports_relay`
- `supports_restart`
- `observed_errors`

### Admin APIs

#### `GET /admin/join-requests`

- list pending and historical join requests

#### `POST /admin/join-requests/{id}/approve`

- approve a request
- assign initial port and protocol
- assign publish mode
- create the node record
- mint a node token

#### `POST /admin/join-requests/{id}/reject`

- reject a request with an optional reason

#### `GET /admin/nodes`

- list approved nodes and their health state

#### `POST /admin/nodes/{id}/publish-mode`

- switch whether subscriptions prefer direct or relay output for that node

#### `POST /admin/nodes/{id}/disable`

- disable a node without deleting history

#### `DELETE /admin/nodes/{id}`

- remove a node from the pool

#### `POST /admin/nodes/{id}/rotate-port`

- manually request port rotation

#### `POST /admin/subscription-tokens`

- create user-facing subscription tokens

Approval should create the initial desired state rather than assuming the manager can directly push config into the node.

## Subscription Plan

Replace process output scraping with database-backed subscription generation.

- Only approved and publishable nodes are included.
- Publishable means:
  - node is approved
  - node is not disabled
  - node has a recent report
  - node health status allows publication
- Raw protocol links are generated directly from stored node metadata.
- Each node contributes either a direct endpoint, a relay endpoint, or both depending on policy.
- Base64-encode the raw list for standard subscription clients.
- Forward raw subscriptions into `subconverter` for Clash and other formats.

Expose at least:

- `GET /subscribe?token=...`
  - returns base64-encoded line-separated links
- `GET /subscribe/raw?token=...`
  - returns newline-delimited links without base64 encoding
- `GET /subscribe/clash?token=...`
  - returns converted output from `subconverter`

Optional follow-up endpoints:

- `GET /subscribe?token=...&mode=direct`
- `GET /subscribe?token=...&region=jp`
- `GET /subscribe?token=...&protocol=vmess`

## Publication Rules

The manager should make publication decisions deterministically.

- Publish direct mode when direct is healthy and enabled.
- Publish relay mode when direct is unhealthy but relay is healthy and enabled.
- Publish nothing for disabled or stale nodes.
- Never publish two conflicting active endpoints for the same node unless a later feature explicitly introduces multi-endpoint output.

## Health Check And Remediation Plan

Run a background scheduler in the manager.

### Default Policy Values

- heartbeat interval: 30 seconds
- desired-state long-poll timeout: 30 seconds
- health-check interval: 60 seconds
- direct failure threshold before remediation: 1 failed check
- remediation cooldown: 20 seconds
- max port-rotation attempts per incident: 3
- default port-rotation range: initial port through initial port + 20
- node stale threshold without heartbeat: 120 seconds

### Direct-Mode Remediation Flow

For each approved node:

1. Probe the currently published direct endpoint from the manager-side network.
2. If direct mode is healthy, mark the node healthy and reset retry count.
3. If direct mode is unhealthy, mark the node degraded and write a `health_events` record.
4. Increase the desired listening port within the allowed range.
5. Increment `desired_config_version` so the node agent picks up the change.
6. Wait for the node to report that the new config was applied.
7. Re-probe after cooldown.
8. Repeat until the direct path is healthy or `max_retry_count` is reached.

### Relay Fallback Flow

If direct mode remains unreachable after retry exhaustion:

1. Check whether the node heartbeat is fresh.
2. Check whether relay capability is enabled for the node.
3. Probe the manager-hosted relay endpoint.
4. If relay is healthy, switch `published_mode` to `relay` and record the event.
5. If relay is not healthy, disable the node and exclude it from subscriptions.

Every remediation attempt must be persisted.

## Node Configuration Plan

The node agent should manage only a small local state set.

- current desired config version
- current rendered V2Ray config file
- last successful apply timestamp
- local bootstrap credentials

The manager should send or derive:

- protocol selection
- listen port
- TLS or transport parameters when relevant
- relay enablement
- relay remote host and port
- publish mode intent

Template rendering should live in `src/network_proxy/templates/` so both manager tests and node-agent tests can validate the expected structure.

## Background Workers

V1 needs at least three recurring loops.

### 1. Heartbeat freshness checker

- marks nodes stale when reports stop arriving

### 2. Direct health probe worker

- tests currently published direct endpoints

### 3. Remediation worker

- rotates ports
- waits for applied reports
- flips nodes to relay mode or disables them

These loops may start in one process for V1. If they become noisy or slow, split them later without changing the API surface.

## Deployment Plan

Define two Docker Compose stacks.

### Manager Stack

Services:

- `manager-api`
  - FastAPI manager service
- `subconverter`
  - conversion service for Clash and related outputs
- `manager-v2ray`
  - optional relay ingress and reverse portal runtime

Volumes:

- SQLite database file
- rendered config files
- logs if required

Environment variables:

- `NETWORK_PROXY_DB_PATH`
- `NETWORK_PROXY_SUBCONVERTER_URL`
- `NETWORK_PROXY_MANAGER_PUBLIC_HOST`
- `NETWORK_PROXY_MANAGER_DIRECT_HEALTH_INTERVAL`
- `NETWORK_PROXY_JOIN_SECRET`

### Node Stack

Services:

- `node-v2ray`
  - node data-plane runtime
- `node-agent`
  - manager sync agent

Volumes:

- rendered V2Ray config
- local node state

Environment variables:

- `NETWORK_PROXY_MANAGER_URL`
- `NETWORK_PROXY_JOIN_SECRET`
- `NETWORK_PROXY_NODE_NAME`
- `NETWORK_PROXY_PUBLIC_HOST`
- `NETWORK_PROXY_REGION`
- `NETWORK_PROXY_REQUESTED_PORT`
- `NETWORK_PROXY_REQUESTED_MODES`

## Implementation Phases

### Phase 1: Refactor the current service entrypoint

Use `src/subscribe.py` as the initial anchor.

- Keep FastAPI as the HTTP layer.
- Move business logic into `src/network_proxy/` services and repositories.
- Keep `main.py` as a thin launch entrypoint.
- Preserve the existing `/subscribe` and `/subscribe/clash` surface while swapping the backend logic.

Exit criteria:

- app boots from `main.py`
- route registration no longer depends on shell scraping helpers

### Phase 2: Add persistence and token bootstrap

- Add the SQLite schema.
- Add repository helpers and migrations or bootstrap DDL.
- Add admin token bootstrap.
- Add subscription-token storage.

Exit criteria:

- manager starts with an empty database and self-initializes schema
- admin token can be created and validated

### Phase 3: Add onboarding and approval workflow

- Implement join request submission and review.
- Create node records on approval.
- Issue node credentials.
- Store desired config state for each approved node.

Exit criteria:

- pending join request can become approved or rejected
- approved join request returns node credentials and desired state seed

### Phase 4: Implement the node agent

- Register with the manager.
- Poll or long-poll for desired state.
- Render local V2Ray config from templates.
- Apply assigned port and credential changes.
- Restart or reload V2Ray.
- Report applied version and effective endpoint.

The first version can use a shared secret per node instead of a more complex trust model.

Exit criteria:

- approved node reaches `provisioning`, then `active`
- manager sees applied version and fresh heartbeat

### Phase 5: Ship direct-mode subscriptions first

- Generate raw protocol links from the database.
- Publish base64 subscriptions.
- Feed `subconverter` for Clash output.
- Restrict output to approved and publishable nodes only.

Exit criteria:

- `/subscribe`, `/subscribe/raw`, and `/subscribe/clash` all work from stored node data

### Phase 6: Add health checks and automated port remediation

- Probe direct endpoints.
- Rotate ports through the desired-state workflow.
- Persist every remediation event.

Exit criteria:

- direct failure updates node state and rotates port without manual editing

### Phase 7: Add relay-mode support

- Add manager-side relay ingress.
- Add node-side outbound relay configuration.
- Publish relay endpoints when direct mode is blocked or disabled.
- Fall back to relay mode where possible.

Exit criteria:

- manager can publish a relay endpoint for a node when direct mode is unhealthy but relay is healthy

### Phase 8: Package deployment

- Create manager Docker Compose stack.
- Create node Docker Compose stack.
- Add bootstrap examples and env docs.

Exit criteria:

- operator can start one manager and one node using the repo artifacts only

### Phase 9: Documentation and operations

Document:

- manager bootstrap steps
- node bootstrap steps
- join request lifecycle
- admin approval and removal flow
- subscription URLs
- health-check interval and retry policy
- port rotation range and cooldown rules
- relay-mode behavior and fallback rules

Exit criteria:

- README and user guide are sufficient for a fresh operator to reproduce the happy path

## Milestone Plan

Break implementation into short milestones.

### Milestone A: Manager skeleton

- package layout exists
- app boots
- settings load from environment

### Milestone B: Persistent control plane

- database schema exists
- admin auth works
- join request and node records persist

### Milestone C: First managed node

- node agent registers
- admin approves
- desired-state sync works

### Milestone D: Real subscriptions

- database-backed raw output works
- Clash conversion works through `subconverter`

### Milestone E: Self-healing direct mode

- health probes work
- port rotation works
- subscriptions update automatically

### Milestone F: Relay fallback

- relay path works
- manager can switch a node to relay publication

## Verification Plan

Add focused tests and smoke checks for:

1. Pending to approved node transition.
2. Pending to rejected node transition.
3. Desired-state update being applied and acknowledged by a node agent.
4. Node removal and exclusion from subscription output.
5. Raw subscription generation from approved healthy nodes only.
6. `subconverter` integration on top of the raw subscription endpoint.
7. Health-check failure triggering port rotation.
8. Repeated direct-path health-check failure switching a node to relay mode.
9. Repeated health-check failure across all modes causing disable or removal.
10. One end-to-end smoke test with one healthy node and one failing node.

Additional validation targets:

- stale node heartbeat marks node non-publishable
- disabled subscription token denies access
- direct and relay publication rules never emit duplicate active endpoints for one node

## Definition Of Done

The feature is done when these operator-level checks pass.

1. `docker compose up` for the manager stack starts the API, database, and `subconverter`.
2. `docker compose up` for the node stack creates a pending join request automatically.
3. Admin can approve the join request and see the node become active.
4. End user can fetch at least one working subscription endpoint and import it into a client.
5. A forced direct-path failure causes an automatic port change or relay fallback.
6. The subscription output updates without manual file editing on the manager or node.

## Risks And Mitigations

- SQLite write contention
  - keep background workers simple and serialize DB writes when necessary in V1
- Manager-region health probes may not represent every end-user region
  - treat manager-region reachability as the V1 publication truth and document that limitation
- Relay topology complexity
  - keep relay support behind one clear service boundary and one default V2Ray template pair
- Token sprawl
  - separate admin, node, and subscription tokens from the start

## Reuse From Existing Repositories

Reuse patterns from the current V2Ray automation repo.

- `v2ray-docker-compose/subscriber/subscribe.py`
  - FastAPI subscription service and `subconverter` integration pattern.
- `v2ray-docker-compose/subscriber/generate-v2ray-config.py`
  - programmatic V2Ray config mutation pattern.
- `v2ray-docker-compose/subscriber/docker-compose.yml`
  - manager stack shape with V2Ray and `subconverter`.
- `v2ray-docker-compose/v2ray-relay-server/clients.py`
  - protocol link generation examples.

## Decisions For V1

- The joining entity is a proxy node, not an end-user account.
- The manager controls nodes through desired state, not through direct inbound callbacks.
- SQLite is the preferred first persistence layer.
- The first version is API-first and does not require a full admin frontend.
- Direct-mode delivery ships before relay-mode delivery, but the data model must support both from the start.
- Subscription access is token-based rather than account-based.
- A single manager-region health viewpoint is acceptable for V1.

## Out Of Scope For V1

- Multi-manager clustering
- Advanced SSO or OAuth flows
- Billing and quota management
- Non-V2Ray proxy runtimes
- A full browser admin dashboard
- Per-user custom subscription personalization

## Immediate Execution Backlog

Start with the shortest critical path that matches the current repo:

1. Refactor `src/subscribe.py` into a manager app package without changing the public subscription routes.
2. Add settings, database bootstrap, and token storage.
3. Implement join request, approval, and desired-state polling APIs.
4. Replace raw link scraping with database-backed direct-mode subscriptions.
5. Add the first node agent and node Docker Compose stack.
6. Add health probing and port rotation.
7. Layer in relay-mode ingress and fallback after direct mode is stable.

## File-By-File Implementation Backlog

Use this as the execution checklist for the first implementation pass.

### Stage 1: Application bootstrap

- [ ] `pyproject.toml`
  - add runtime dependencies for persistence, settings, templating, HTTP calls, and scheduling
  - add test dependencies needed for API and service validation
  - acceptance: project installs without ad hoc local packages
- [ ] `main.py`
  - replace the placeholder with the real manager entrypoint
  - expose a simple CLI or direct runner that starts the FastAPI app cleanly
  - acceptance: `python main.py` or the chosen runner boots the manager app
- [ ] `src/subscribe.py`
  - convert into a compatibility entrypoint that imports the package-backed FastAPI app
  - preserve `/subscribe` and `/subscribe/clash` behavior at the routing level while internals move out
  - acceptance: existing route paths still exist after refactor
- [ ] `src/network_proxy/__init__.py`
  - create the application package root
  - acceptance: package imports resolve cleanly
- [ ] `src/network_proxy/app.py`
  - create the app factory or singleton app assembly point
  - register routers, startup tasks, and shared state initialization
  - acceptance: the app starts without route registration side effects scattered across files
- [ ] `src/network_proxy/settings.py`
  - define environment-driven configuration for DB path, manager public host, join secret, subconverter URL, scheduling intervals, and publish defaults
  - acceptance: manager configuration is centralized and typed

### Stage 2: Persistence and bootstrap auth

- [ ] `src/network_proxy/db/session.py`
  - create SQLAlchemy engine and session management for SQLite
  - acceptance: request-scoped DB access works through one shared abstraction
- [ ] `src/network_proxy/db/models.py`
  - define ORM models for `join_requests`, `nodes`, `health_events`, `admin_tokens`, and `subscription_tokens`
  - include indexes that match the plan
  - acceptance: metadata can create the initial schema
- [ ] `src/network_proxy/db/migrations.py`
  - provide schema bootstrap logic and, if chosen, migration helpers
  - acceptance: a fresh database can be initialized automatically on first boot
- [ ] `src/network_proxy/repositories/join_requests.py`
  - encapsulate pending, approved, rejected, and expired join-request operations
  - acceptance: no route writes SQL or ORM queries inline for join requests
- [ ] `src/network_proxy/repositories/nodes.py`
  - encapsulate node lifecycle, publish mode, desired state versioning, and heartbeat updates
  - acceptance: node state transitions are centralized
- [ ] `src/network_proxy/repositories/health_events.py`
  - persist probe and remediation history
  - acceptance: every remediation step can be audited
- [ ] `src/network_proxy/repositories/tokens.py`
  - manage hashed admin, node, and subscription tokens
  - acceptance: no raw token values are persisted after issuance
- [ ] `src/network_proxy/cli.py`
  - add bootstrap commands for creating the first admin token and initializing schema
  - acceptance: a fresh operator can bring up the manager without touching the database manually

### Stage 3: HTTP layer and auth dependencies

- [ ] `src/network_proxy/api/deps.py`
  - implement DB session injection, admin auth, node auth, and subscription token validation helpers
  - acceptance: auth rules are reusable across routers
- [ ] `src/network_proxy/api/admin.py`
  - add admin routes for join review, node listing, disable, delete, manual publish-mode changes, manual rotation, and subscription-token creation
  - acceptance: all admin control-plane operations are under one router with bearer auth
- [ ] `src/network_proxy/api/node.py`
  - add node-facing join, status, desired-state, heartbeat, and report endpoints
  - acceptance: node onboarding and reconciliation paths are complete without admin routes leaking into them
- [ ] `src/network_proxy/api/subscribe.py`
  - add `/subscribe`, `/subscribe/raw`, and `/subscribe/clash`
  - acceptance: subscriptions come from the database rather than shell commands

### Stage 4: Control-plane services

- [ ] `src/network_proxy/services/onboarding.py`
  - implement join request creation, approval, rejection, node token issuance, and initial desired-state creation
  - acceptance: approving a request creates exactly one usable node record
- [ ] `src/network_proxy/services/subscriptions.py`
  - build raw protocol links from approved publishable nodes
  - integrate base64 output and `subconverter` forwarding
  - acceptance: the service emits correct raw and converted subscription payloads from stored node data
- [ ] `src/network_proxy/services/health.py`
  - implement direct-path probes, stale-node evaluation, retry accounting, and disable decisions
  - acceptance: health outcomes map deterministically to node status and recorded events
- [ ] `src/network_proxy/services/relay.py`
  - encapsulate relay-mode metadata, relay publication rules, and relay fallback decisions
  - acceptance: relay publication policy is not duplicated in routes or workers
- [ ] `src/network_proxy/services/config_render.py`
  - render direct and relay V2Ray templates from desired-state data
  - acceptance: config generation is deterministic and testable without a running V2Ray process

### Stage 5: Background workers and scheduling

- [ ] `src/network_proxy/workers/scheduler.py`
  - register heartbeat freshness checks, direct probes, and remediation loops
  - acceptance: one startup hook can start and stop all recurring manager workers
- [ ] `src/network_proxy/workers/remediation.py`
  - optionally split the remediation loop out if the scheduler file becomes too dense
  - acceptance: port rotation and relay fallback remain isolated from route code

### Stage 6: Node agent and local runtime control

- [ ] `src/node_agent.py`
  - implement join submission, approval polling, desired-state polling, config rendering, V2Ray restart or reload, heartbeat, and applied-state reporting
  - acceptance: one approved node can fully reconcile from empty local state to active publication
- [ ] `src/network_proxy/templates/node-direct.json.j2`
  - create the direct-mode V2Ray template
  - acceptance: direct endpoint fields map cleanly from desired state to rendered config
- [ ] `src/network_proxy/templates/node-relay.json.j2`
  - create the relay-mode V2Ray template or bridge fragment
  - acceptance: relay fields map cleanly from desired state to rendered config
- [ ] `src/network_proxy/node_state.py`
  - optionally persist the node agent's local cache for token, last desired version, and last applied version
  - acceptance: node restart does not require re-approval to continue reconciling

### Stage 7: Deployment artifacts

- [ ] `deploy/manager/docker-compose.yml`
  - define manager API, `subconverter`, volumes, and optional manager-side V2Ray relay runtime
  - acceptance: manager stack boots with one command
- [ ] `deploy/manager/.env.example`
  - document required environment variables and safe defaults
  - acceptance: operator can copy and edit one file to start the manager stack
- [ ] `deploy/manager/bootstrap.sh`
  - automate first-run schema bootstrap and admin token creation guidance
  - acceptance: manager bootstrap is reproducible
- [ ] `deploy/node/docker-compose.yml`
  - define node V2Ray plus node agent services and shared volumes
  - acceptance: a node can start and submit a join request automatically
- [ ] `deploy/node/.env.example`
  - document manager URL, join secret, node identity, region, requested modes, and requested port
  - acceptance: node bootstrap input is explicit and minimal
- [ ] `deploy/node/bootstrap.sh`
  - automate first-run node setup flow
  - acceptance: node operator does not need to edit runtime internals manually

### Stage 8: Test backlog

- [ ] `tests/api/test_join_requests.py`
  - cover pending, approved, and rejected join-request flows
  - acceptance: admin review flow is regression-tested
- [ ] `tests/api/test_nodes.py`
  - cover node desired-state polling, heartbeat, and applied-state reports
  - acceptance: node control-plane API contract is stable
- [ ] `tests/api/test_subscribe.py`
  - cover raw, base64, and Clash subscription outputs
  - acceptance: only publishable nodes are emitted
- [ ] `tests/services/test_health.py`
  - cover port rotation thresholds, retry accounting, stale-node detection, and disable decisions
  - acceptance: remediation policy stays deterministic
- [ ] `tests/services/test_relay.py`
  - cover relay fallback rules and publish-mode switching
  - acceptance: relay decisions remain separate from direct-mode logic
- [ ] `tests/smoke/test_manager_node_flow.py`
  - cover one happy-path manager plus node bootstrap and one degraded-node scenario
  - acceptance: the end-to-end control loop works under realistic sequencing

### Stage 9: Documentation follow-through

- [ ] `README.md`
  - replace the template content with manager and node quickstart instructions
  - acceptance: a new operator can boot one manager and one node from repository docs alone
- [ ] `docs/user-guide/README.md`
  - document admin actions, subscription URLs, and node lifecycle
  - acceptance: routine operations no longer depend on reading source code
- [ ] `docs/AI-external-context/local.md`
  - record local deployment assumptions and external paths actually used during implementation
  - acceptance: future work has the right local context without rediscovery

## First Build Slice

The narrowest implementation slice to start immediately is:

1. Update `pyproject.toml` with the manager dependencies.
2. Replace `main.py` with a real entrypoint.
3. Add `src/network_proxy/app.py` and `src/network_proxy/settings.py`.
4. Convert `src/subscribe.py` into a compatibility wrapper.
5. Add `src/network_proxy/api/subscribe.py` with placeholder database-backed service wiring.

That slice gives a clean package structure without opening the full persistence and node-agent scope on day one.

## Open Questions

These do not block the first implementation, but they should be resolved while coding.

- Which exact V2Ray protocol template should be the V1 default?
- Should manager health probes use plain TCP reachability, HTTP CONNECT verification, or an actual client handshake?
- How much relay traffic should the manager be expected to carry before we need explicit capacity controls?
- Do we want to preserve removed-node audit history in separate tables during V1, or is soft-disable enough for now?
