#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"
EXAMPLE_FILE="$SCRIPT_DIR/.env.example"

mkdir -p "$REPO_ROOT/data/client"

if [ ! -f "$ENV_FILE" ]; then
  cp "$EXAMPLE_FILE" "$ENV_FILE"
  echo "created $ENV_FILE from .env.example"
fi

chmod +x "$SCRIPT_DIR/run-client-v2ray.sh"

cat <<EOF
client bootstrap scaffold is ready.

Start the stack:
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up --build -d

The client agent polls the manager subscription endpoint, renders a V2Ray
client config (SOCKS inbound on port ${NETWORK_PROXY_CLIENT_SOCKS_PORT:-10808}),
and reloads the client-v2ray sidecar when the subscription changes.

Test the SOCKS proxy:
curl --socks5 127.0.0.1:${NETWORK_PROXY_CLIENT_SOCKS_PORT:-10808} http://httpbin.org/ip

Override NETWORK_PROXY_CLIENT_OVERRIDE_HOST and NETWORK_PROXY_CLIENT_OVERRIDE_PORT
in $ENV_FILE when the subscription host/port do not match what the client
container can actually reach (common in local Docker test environments).
EOF
