#!/usr/bin/env bash
#
# End-to-end test for the network-proxy stack.
#
# Starts the manager, node, and client deployments, approves any pending
# join request, waits for the proxy data-plane to come up, and verifies
# that HTTP traffic can flow through the VMess tunnel via the client's
# SOCKS proxy.
#
set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

MANAGER_DIR="$REPO_ROOT/deploy/manager"
NODE_DIR="$REPO_ROOT/deploy/node"
CLIENT_DIR="$REPO_ROOT/deploy/client"

ADMIN_TOKEN="${NETWORK_PROXY_ADMIN_TOKEN:-admin-db}"
SUB_TOKEN="${NETWORK_PROXY_SUBSCRIPTION_TOKEN:-sub-db}"
MANAGER_API="http://127.0.0.1:9001"

NODE_PUBLISHED_PORT="${NETWORK_PROXY_NODE_PUBLISHED_PORT:-21001}"
CLIENT_SOCKS_PORT="${NETWORK_PROXY_CLIENT_SOCKS_PORT:-10808}"

log() { printf '\033[1;34m[test]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; }

ensure_env() {
  local dir="$1"
  if [ ! -f "$dir/.env" ]; then
    cp "$dir/.env.example" "$dir/.env"
    log "created $dir/.env from .env.example"
  fi
}

# Wait until a TCP port accepts connections (host port arg).
wait_for_tcp() {
  local host="$1" port="$2" name="$3" tries="${4:-60}"
  local i
  for i in $(seq 1 "$tries"); do
    if (echo > "/dev/tcp/$host/$port") 2>/dev/null; then
      log "$name is reachable at $host:$port"
      return 0
    fi
    sleep 1
  done
  err "timed out waiting for $name at $host:$port"
  return 1
}

# --------------------------------------------------------------------------- #
# 1. Ensure .env files exist
# --------------------------------------------------------------------------- #
log "ensuring .env files"
ensure_env "$MANAGER_DIR"
ensure_env "$NODE_DIR"
ensure_env "$CLIENT_DIR"

# Disable health-check port rotation for the local Docker test environment.
# The health checker probes node.public_host:active_port, but Docker only
# publishes a single static port.  When the probe fails the checker rotates
# the port (21001 -> 21002 -> ...), V2Ray follows, and the published port no
# longer matches.  The node heartbeat already reports health_status="healthy"
# to the manager, so disabling the checker keeps the node in the subscription
# without the rotation cascade.
if grep -q "^NETWORK_PROXY_HEALTH_CHECK_ENABLED=" "$MANAGER_DIR/.env"; then
  sed -i 's/^NETWORK_PROXY_HEALTH_CHECK_ENABLED=.*/NETWORK_PROXY_HEALTH_CHECK_ENABLED=false/' "$MANAGER_DIR/.env"
else
  echo "NETWORK_PROXY_HEALTH_CHECK_ENABLED=false" >> "$MANAGER_DIR/.env"
fi

# The client override must match the node's published port so the SOCKS
# proxy can actually reach the node through the Docker host gateway.
if ! grep -q "^NETWORK_PROXY_CLIENT_OVERRIDE_PORT=" "$CLIENT_DIR/.env" \
    || [ -z "$(grep "^NETWORK_PROXY_CLIENT_OVERRIDE_PORT=" "$CLIENT_DIR/.env" | cut -d= -f2)" ]; then
  echo "NETWORK_PROXY_CLIENT_OVERRIDE_PORT=$NODE_PUBLISHED_PORT" >> "$CLIENT_DIR/.env"
fi

# --------------------------------------------------------------------------- #
# 2. Start all three stacks
# --------------------------------------------------------------------------- #
log "starting manager"
docker compose --env-file "$MANAGER_DIR/.env" -f "$MANAGER_DIR/docker-compose.yml" up --build -d

log "starting node"
docker compose --env-file "$NODE_DIR/.env" -f "$NODE_DIR/docker-compose.yml" up --build -d

log "starting client"
docker compose --env-file "$CLIENT_DIR/.env" -f "$CLIENT_DIR/docker-compose.yml" up --build -d

# --------------------------------------------------------------------------- #
# 3. Wait for manager API
# --------------------------------------------------------------------------- #
log "waiting for manager API"
wait_for_tcp 127.0.0.1 9001 "manager API" 90

# --------------------------------------------------------------------------- #
# 3b. Bootstrap admin and subscription tokens (idempotent)
# --------------------------------------------------------------------------- #
log "ensuring admin and subscription tokens"
docker compose --env-file "$MANAGER_DIR/.env" -f "$MANAGER_DIR/docker-compose.yml" exec -T manager-api \
  uv run python main.py create-admin-token --name primary-admin --token "$ADMIN_TOKEN" >/dev/null
docker compose --env-file "$MANAGER_DIR/.env" -f "$MANAGER_DIR/docker-compose.yml" exec -T manager-api \
  uv run python main.py create-subscription-token --name default-subscription --token "$SUB_TOKEN" >/dev/null

# --------------------------------------------------------------------------- #
# 4. Approve any pending join request
# --------------------------------------------------------------------------- #
log "checking for pending join requests"
join_json=$(curl -sf -H "Authorization: Bearer $ADMIN_TOKEN" "$MANAGER_API/admin/join-requests" \
            || echo '[]')

pending=$(printf '%s' "$join_json" \
  | python3 -c '
import json, sys
data = json.load(sys.stdin)
items = data if isinstance(data, list) else data.get("items", [])
out = [r for r in items if r.get("status") == "pending"]
print(json.dumps(out))
')

if [ "$pending" != "[]" ] && [ -n "$pending" ]; then
  join_id=$(printf '%s' "$pending" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
  log "approving join request $join_id"
  curl -sf -X POST \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"protocol\":\"vmess\",\"publish_mode\":\"direct\",\"assigned_port\":$NODE_PUBLISHED_PORT}" \
    "$MANAGER_API/admin/join-requests/$join_id/approve" >/dev/null
  log "join request approved"
else
  log "no pending join requests (already approved or not yet submitted)"
fi

# --------------------------------------------------------------------------- #
# 5. Wait for node V2Ray to start listening on the published port
# --------------------------------------------------------------------------- #
log "waiting for node V2Ray data-plane on port $NODE_PUBLISHED_PORT"
wait_for_tcp 127.0.0.1 "$NODE_PUBLISHED_PORT" "node V2Ray" 90

# --------------------------------------------------------------------------- #
# 5b. Wait for the subscription to publish at least one vmess link
#     (the node must apply config, heartbeat, and report before the manager
#      considers it healthy and includes it in the subscription).
# --------------------------------------------------------------------------- #
log "waiting for subscription content"
sub_ready=false
for i in $(seq 1 120); do
  if curl -sf --max-time 5 "$MANAGER_API/subscribe/raw?token=$SUB_TOKEN" 2>/dev/null | grep -q '^vmess://'; then
    sub_ready=true
    log "subscription is publishing vmess links"
    break
  fi
  sleep 2
done
if [ "$sub_ready" != "true" ]; then
  err "subscription never published vmess links"
  exit 1
fi

# --------------------------------------------------------------------------- #
# 6. Wait for the client agent to render config and the SOCKS proxy to come up
# --------------------------------------------------------------------------- #
log "waiting for client SOCKS proxy on port $CLIENT_SOCKS_PORT"
wait_for_tcp 127.0.0.1 "$CLIENT_SOCKS_PORT" "client SOCKS proxy" 90

# --------------------------------------------------------------------------- #
# 7. Proxy a real HTTP request through the VMess tunnel
#    (retry for a few cycles — the client agent may still be converging)
# --------------------------------------------------------------------------- #
log "testing HTTP request through VMess proxy"
response=""
for i in $(seq 1 6); do
  response=$(curl -sf --max-time 15 \
    --socks5-hostname "127.0.0.1:$CLIENT_SOCKS_PORT" \
    http://httpbin.org/ip 2>/dev/null) && break
  log "attempt $i failed, retrying in 5s..."
  sleep 5
done

if [ -z "$response" ]; then
  err "request through proxy failed after retries"
  err "client logs (last 20 lines):"
  docker compose --env-file "$CLIENT_DIR/.env" -f "$CLIENT_DIR/docker-compose.yml" logs --tail 20 client-agent client-v2ray 2>&1 | tail -20
  exit 1
fi

origin_ip=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("origin","?"))' 2>/dev/null || echo "?")

printf '\n'
log "================ PROXY TEST PASSED ================"
log "  SOCKS proxy : 127.0.0.1:$CLIENT_SOCKS_PORT"
log "  Exit IP     : $origin_ip"
log "  Subscription: $MANAGER_API/subscribe/raw?token=$SUB_TOKEN"
log "==================================================="
