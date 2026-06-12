# User Guide

This directory contains the operator-facing guides for the current `network-proxy` implementation.

## Guides

- [Manager Quickstart](./manager-quickstart.md)
  Start the manager API, initialize admin and subscription tokens, and run the core admin flows.
- [Node Agent Quickstart](./node-agent-quickstart.md)
  Start a node agent, let it join the pool, and understand the local files it writes.
- [Subscriptions Guide](./subscriptions.md)
  Create subscription tokens and fetch raw or encoded subscription outputs.
- [Operations Guide](./operations.md)
  Approve nodes, trigger health checks, and understand the current remediation behavior.

## Current Scope

The current project version already supports:

- manager startup with `uv`
- SQLite-backed admin and subscription tokens
- node join requests and admin approval
- desired-state polling for nodes
- node-agent runtime config rendering and local config writes
- database-backed subscription publishing
- manual or scheduled direct-path health checks with port rotation

## Current Limitations

The current user guides document the implementation that exists today.

- Relay-mode publication is not yet a full fallback flow.
- V2Ray runtime control is template-backed, but the actual apply and validate commands are still operator-provided environment settings.
- There is no browser admin UI yet; current operations are API- and CLI-driven.
