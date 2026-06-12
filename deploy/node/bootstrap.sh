#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"
EXAMPLE_FILE="$SCRIPT_DIR/.env.example"

mkdir -p "$REPO_ROOT/data/node"

if [ ! -f "$ENV_FILE" ]; then
  cp "$EXAMPLE_FILE" "$ENV_FILE"
  echo "created $ENV_FILE from .env.example"
fi

cat <<EOF
node bootstrap scaffold is ready.

Start the stack:
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up --build -d

This stack starts both the node agent and a V2Ray runtime sidecar.
The agent will submit a join request, render /app/data/node-v2ray-config.json, and touch a reload marker when config changes.

If you want runtime validation or restart hooks, set these values in $ENV_FILE:
- NETWORK_PROXY_NODE_VALIDATE_COMMAND
- NETWORK_PROXY_NODE_APPLY_COMMAND

Keep NETWORK_PROXY_NODE_PUBLISHED_PORT aligned with NETWORK_PROXY_NODE_REQUESTED_PORT for the first approval path.
EOF