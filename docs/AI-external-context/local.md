# Local Environment Info

## Current Workspace Assumptions

- Workspace root: `/home/king/github/jinbangyi/network-proxy`
- Operating system during current implementation: Linux
- Primary workflow uses `uv sync` and `uv run ...`
- Main manager entrypoint is `main.py`
- Node-agent entrypoint is `src/node_agent.py`

## Current Local Runtime Defaults

- Manager API default bind: `0.0.0.0:9001`
- SQLite database default: `sqlite:///data/network_proxy.db`
- Default node-agent state files live under `data/`
- Subscription conversion expects `subconverter` at `http://subconverter:25500`

## Deployment Paths In Use

- Manager compose file: `deploy/manager/docker-compose.yml`
- Manager env example: `deploy/manager/.env.example`
- Node compose file: `deploy/node/docker-compose.yml`
- Node env example: `deploy/node/.env.example`

## Local Persistence Layout

- Manager stack persists data under `data/manager/`
- Node stack persists data under `data/node/`

## Current Deployment Scope

- Manager deployment covers the API service and `subconverter`
- Manager deployment also includes an opt-in relay runtime under the compose `relay` profile
- Node deployment covers the node agent plus a node-side V2Ray sidecar driven by a shared config volume
- Health-driven relay fallback is implemented in the manager health service
- Manager-side relay config generation is automatic and writes `data/manager/manager-v2ray-config.json`
