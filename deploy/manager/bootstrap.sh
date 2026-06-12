#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"
EXAMPLE_FILE="$SCRIPT_DIR/.env.example"

mkdir -p "$REPO_ROOT/data/manager"

if [ ! -f "$ENV_FILE" ]; then
  cp "$EXAMPLE_FILE" "$ENV_FILE"
  echo "created $ENV_FILE from .env.example"
fi

cat <<EOF
manager bootstrap scaffold is ready.

Start the stack:
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up --build -d

Start the optional relay scaffold profile:
docker compose --profile relay --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d manager-v2ray

Create an admin token:
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec manager-api \
  uv run python main.py create-admin-token --name primary-admin --token admin-db

Create a subscription token:
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec manager-api \
  uv run python main.py create-subscription-token --name default-subscription --token sub-db

The relay profile uses the manager-generated config at data/manager/manager-v2ray-config.json.
Relay enablement is driven by node state and health fallback, but the runtime is still packaged as an opt-in profile.
EOF