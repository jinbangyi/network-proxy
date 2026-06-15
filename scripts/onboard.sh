#!/usr/bin/env bash
#
# onboard.sh — single-entry onboarding for the network-proxy stack.
#
# Wraps deploy/manager/docker-compose.yml + deploy/node/docker-compose.yml
# and drives the full lifecycle: init → start → tokens → approve → status.
#
# Data volumes are redirected into the workspace by exporting HOME=$WORKSPACE
# for all `docker compose` invocations (compose expands ~/... using $HOME).
# Docker client config (~/.docker/config.json) is preserved via DOCKER_CONFIG.
#
set -euo pipefail

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
readonly DEFAULT_WORKSPACE="/opt/network-proxy"
readonly DEFAULT_PUBLIC_HOST="127.0.0.1"
readonly DEFAULT_NODE_PORT="21001"
readonly DEFAULT_MANAGER_PORT="9001"
readonly DEFAULT_ADMIN_TOKEN="admin-db"
readonly DEFAULT_SUB_TOKEN="sub-db"
readonly COMPOSE_PROJECT="network-proxy"

readonly SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
readonly ORIGINAL_HOME="${HOME:-}"

readonly MANAGER_COMPOSE="$REPO_ROOT/deploy/manager/docker-compose.yml"
readonly NODE_COMPOSE="$REPO_ROOT/deploy/node/docker-compose.yml"
readonly MANAGER_ENV_EXAMPLE="$REPO_ROOT/deploy/manager/.env.example"
readonly NODE_ENV_EXAMPLE="$REPO_ROOT/deploy/node/.env.example"

# --------------------------------------------------------------------------
# Color helpers (no-ops when stdout is not a TTY)
# --------------------------------------------------------------------------
if [[ -t 1 ]]; then
  readonly C_RED=$'\033[0;31m'
  readonly C_GREEN=$'\033[0;32m'
  readonly C_YELLOW=$'\033[0;33m'
  readonly C_BLUE=$'\033[0;34m'
  readonly C_NC=$'\033[0m'
else
  readonly C_RED='' C_GREEN='' C_YELLOW='' C_BLUE='' C_NC=''
fi

log_info()  { printf '%s[INFO]%s %s\n' "$C_BLUE" "$C_NC" "$*"; }
log_ok()    { printf '%s[OK]%s %s\n' "$C_GREEN" "$C_NC" "$*"; }
log_warn()  { printf '%s[WARN]%s %s\n' "$C_YELLOW" "$C_NC" "$*"; }
log_error() { printf '%s[ERROR]%s %s\n' "$C_RED" "$C_NC" "$*" >&2; }
die()       { log_error "$*"; exit 1; }

# --------------------------------------------------------------------------
# Mutable options (set per-invocation via flags)
# --------------------------------------------------------------------------
WORKSPACE="$DEFAULT_WORKSPACE"
PUBLIC_HOST="$DEFAULT_PUBLIC_HOST"
NODE_PORT="$DEFAULT_NODE_PORT"
ADMIN_TOKEN_VAL=""
SUB_TOKEN_VAL=""

# --------------------------------------------------------------------------
# Prerequisites
# --------------------------------------------------------------------------
check_prereqs() {
  command -v docker >/dev/null 2>&1 || die "docker is required (install Docker Engine or Docker Desktop)"
  docker compose version >/dev/null 2>&1 || die "docker compose v2 is required"
  command -v curl >/dev/null 2>&1 || die "curl is required"
  if ! command -v jq >/dev/null 2>&1; then
    log_warn "jq is not installed; 'approve' and 'status' commands will not work"
  fi
  [[ -f "$MANAGER_COMPOSE" ]] || die "missing $MANAGER_COMPOSE (run from the repo root)"
  [[ -f "$NODE_COMPOSE" ]] || die "missing $NODE_COMPOSE (run from the repo root)"
}

# --------------------------------------------------------------------------
# Workspace helpers
# --------------------------------------------------------------------------
resolve_workspace() {
  # Canonicalize to an absolute path so docker compose bind mounts work.
  if [[ ! -d "$WORKSPACE" ]]; then
    # Create a temp absolute path so realpath -m works even if parent missing.
    local parent
    parent="$(dirname -- "$WORKSPACE")"
    if [[ ! -d "$parent" ]]; then
      die "parent directory '$parent' does not exist (cannot create workspace at $WORKSPACE)"
    fi
    parent="$(cd "$parent" && pwd)"
    WORKSPACE="$parent/$(basename -- "$WORKSPACE")"
  else
    WORKSPACE="$(cd "$WORKSPACE" && pwd)"
  fi
}

workspace_env()  { printf '%s/.env\n' "$WORKSPACE"; }
workspace_data() { printf '%s/data\n' "$WORKSPACE"; }

require_workspace() {
  local env_file
  env_file="$(workspace_env)"
  if [[ ! -f "$env_file" ]]; then
    die "no workspace at $WORKSPACE (run: $0 init -w $WORKSPACE)"
  fi
}

# Read a single key from the workspace .env (empty string if missing).
env_value() {
  local key="$1" env_file
  env_file="$(workspace_env)"
  [[ -f "$env_file" ]] || return 0
  grep -E "^${key}=" "$env_file" 2>/dev/null | tail -n1 | cut -d= -f2- || true
}

# Set (or update) a key in the workspace .env.
env_set() {
  local key="$1" val="$2" env_file tmp
  env_file="$(workspace_env)"
  if grep -qE "^${key}=" "$env_file"; then
    tmp="$(mktemp)"
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k {$0=k"="v} {print}' "$env_file" > "$tmp"
    mv "$tmp" "$env_file"
  else
    printf '%s=%s\n' "$key" "$val" >> "$env_file"
  fi
}

manager_port() {
  local p
  p="$(env_value NETWORK_PROXY_PORT)"
  printf '%s\n' "${p:-$DEFAULT_MANAGER_PORT}"
}

# --------------------------------------------------------------------------
# Compose invocation (HOME trick redirects bind mounts into the workspace)
# --------------------------------------------------------------------------
compose_manager() {
  local env_file
  env_file="$(workspace_env)"
  HOME="$WORKSPACE" DOCKER_CONFIG="${ORIGINAL_HOME}/.docker" \
    docker compose --env-file "$env_file" -f "$MANAGER_COMPOSE" -p "$COMPOSE_PROJECT" "$@"
}

compose_node() {
  local env_file
  env_file="$(workspace_env)"
  HOME="$WORKSPACE" DOCKER_CONFIG="${ORIGINAL_HOME}/.docker" \
    docker compose --env-file "$env_file" -f "$NODE_COMPOSE" -p "$COMPOSE_PROJECT" "$@"
}

# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------
wait_for_http() {
  local url="$1" tries="${2:-60}" i=0
  log_info "waiting for $url (up to ${tries}s)..."
  while [[ $i -lt $tries ]]; do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then
      log_ok "$url is responding"
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  die "timeout waiting for $url (is the manager healthy?)"
}

# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
cmd_init() {
  local force=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -w|--workspace)   WORKSPACE="$2"; shift 2 ;;
      --public-host)    PUBLIC_HOST="$2"; shift 2 ;;
      --node-port)      NODE_PORT="$2"; shift 2 ;;
      --admin-token)    ADMIN_TOKEN_VAL="$2"; shift 2 ;;
      --sub-token)      SUB_TOKEN_VAL="$2"; shift 2 ;;
      --force)          force=1; shift ;;
      -h|--help)        usage_init; return 0 ;;
      *)                die "init: unknown option: $1" ;;
    esac
  done

  check_prereqs

  # Create the workspace directory (handle /opt/* needing root).
  if [[ ! -d "$WORKSPACE" ]]; then
    if ! mkdir -p "$WORKSPACE" 2>/dev/null; then
      die "cannot create $WORKSPACE (try: sudo $0 init -w $WORKSPACE, or pick a path under your home with -w)"
    fi
  fi

  # If we ran as root with sudo, hand the workspace over to the invoking user.
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    local target_user="${SUDO_USER:-${USER:-}}"
    if [[ -n "$target_user" && "$target_user" != "root" ]]; then
      chown -R "$target_user":"$(id -g "$target_user")" "$WORKSPACE" 2>/dev/null || true
    fi
  fi

  resolve_workspace

  mkdir -p "$WORKSPACE/data/manager" "$WORKSPACE/data/node" "$WORKSPACE/run"

  local env_file
  env_file="$(workspace_env)"
  if [[ -f "$env_file" && $force -ne 1 ]]; then
    log_warn "$env_file already exists; use --force to overwrite"
  else
    {
      echo "# Generated by scripts/onboard.sh on $(date -u +%FT%TZ 2>/dev/null || date)"
      echo "# Merged from deploy/manager/.env.example + deploy/node/.env.example"
      echo "# Do not edit by hand unless you know what you are doing."
      echo
      cat "$MANAGER_ENV_EXAMPLE"
      echo
      cat "$NODE_ENV_EXAMPLE"
    } > "$env_file"

    # Apply onboarding overrides.
    env_set "NETWORK_PROXY_MANAGER_PUBLIC_URL" "http://${PUBLIC_HOST}:$(manager_port)"
    env_set "NETWORK_PROXY_NODE_PUBLIC_HOST" "$PUBLIC_HOST"
    env_set "NETWORK_PROXY_NODE_MANAGER_URL" "http://host.docker.internal:$(manager_port)"
    env_set "NETWORK_PROXY_NODE_PUBLISHED_PORT" "$NODE_PORT"
    env_set "NETWORK_PROXY_NODE_REQUESTED_PORT" "$NODE_PORT"

    log_ok "wrote $env_file"
  fi

  # Seed token values: explicit flag > existing value > dev default.
  if [[ -n "$ADMIN_TOKEN_VAL" ]]; then
    env_set "NETWORK_PROXY_ADMIN_TOKEN" "$ADMIN_TOKEN_VAL"
  elif [[ -z "$(env_value NETWORK_PROXY_ADMIN_TOKEN)" ]]; then
    env_set "NETWORK_PROXY_ADMIN_TOKEN" "$DEFAULT_ADMIN_TOKEN"
  fi
  if [[ -n "$SUB_TOKEN_VAL" ]]; then
    env_set "NETWORK_PROXY_SUBSCRIPTION_TOKEN" "$SUB_TOKEN_VAL"
  elif [[ -z "$(env_value NETWORK_PROXY_SUBSCRIPTION_TOKEN)" ]]; then
    env_set "NETWORK_PROXY_SUBSCRIPTION_TOKEN" "$DEFAULT_SUB_TOKEN"
  fi

  log_info "pre-pulling images (may take a while on first run)..."
  compose_manager pull --ignore-pull-failures 2>&1 | sed 's/^/  /' || true
  compose_node    pull --ignore-pull-failures 2>&1 | sed 's/^/  /' || true

  cat <<EOF

$(log_ok "workspace ready at $WORKSPACE")

Layout:
  $WORKSPACE/.env
  $WORKSPACE/data/manager/   (SQLite DB lives here)
  $WORKSPACE/data/node/

Next steps:
  $0 start  -w $WORKSPACE
  $0 tokens -w $WORKSPACE
  $0 approve -w $WORKSPACE
EOF
}

cmd_start() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -w|--workspace) WORKSPACE="$2"; shift 2 ;;
      -h|--help)      usage_start; return 0 ;;
      *)              die "start: unknown option: $1" ;;
    esac
  done

  check_prereqs
  require_workspace
  resolve_workspace

  log_info "building + starting manager stack (manager-api + subconverter)..."
  compose_manager up --build -d

  wait_for_http "http://127.0.0.1:$(manager_port)/docs" 90

  log_info "building + starting node stack (node-agent + node-v2ray)..."
  compose_node up --build -d

  print_summary
}

cmd_stop() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -w|--workspace) WORKSPACE="$2"; shift 2 ;;
      -h|--help)      usage_stop; return 0 ;;
      *)              die "stop: unknown option: $1" ;;
    esac
  done

  require_workspace
  resolve_workspace

  log_info "stopping node stack..."
  compose_node down 2>&1 || true
  log_info "stopping manager stack..."
  compose_manager down 2>&1 || true
  log_ok "stopped"
}

cmd_status() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -w|--workspace) WORKSPACE="$2"; shift 2 ;;
      -h|--help)      return 0 ;;
      *)              die "status: unknown option: $1" ;;
    esac
  done

  require_workspace
  resolve_workspace

  echo "=== Containers (project: $COMPOSE_PROJECT) ==="
  # Both compose files share the project name, so either lists every container.
  compose_manager ps 2>&1 || true

  local admin_token base_url
  admin_token="$(env_value NETWORK_PROXY_ADMIN_TOKEN)"
  base_url="http://127.0.0.1:$(manager_port)"

  if [[ -n "$admin_token" ]]; then
    echo
    echo "=== Join requests ==="
    if curl -fsS -H "Authorization: Bearer $admin_token" "$base_url/admin/join-requests" 2>/dev/null \
        | jq -r '.[] | "  \(.id)  \(.status)  name=\(.node_name) host=\(.public_host) port=\(.requested_port // 0)"' 2>/dev/null; then
      :
    else
      log_warn "could not fetch join requests (is the manager up?)"
    fi

    echo
    echo "=== Nodes ==="
    if curl -fsS -H "Authorization: Bearer $admin_token" "$base_url/admin/nodes" 2>/dev/null \
        | jq -r '.[] | "  \(.id)  \(.lifecycle_status)/\(.health_status)  name=\(.node_name) host=\(.public_host) port=\(.active_port // 0) mode=\(.published_mode)"' 2>/dev/null; then
      :
    else
      log_warn "could not fetch nodes (is the manager up?)"
    fi
  else
    log_warn "no NETWORK_PROXY_ADMIN_TOKEN in $(workspace_env); skipping join-request/node listing"
    log_warn "run: $0 tokens -w $WORKSPACE"
  fi
}

cmd_logs() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -w|--workspace) WORKSPACE="$2"; shift 2 ;;
      --)             shift; break ;;
      -h|--help)      usage_logs; return 0 ;;
      -*)             die "logs: unknown option: $1" ;;
      *)              break ;;
    esac
  done

  require_workspace
  resolve_workspace

  local service="${1:-}"
  if [[ -z "$service" ]]; then
    log_info "tailing all manager + node logs (Ctrl-C to exit)"
    compose_manager logs --tail 100 -f
  elif [[ "$service" == node-* ]]; then
    compose_node logs --tail 100 -f "$service"
  else
    compose_manager logs --tail 100 -f "$service"
  fi
}

cmd_tokens() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -w|--workspace) WORKSPACE="$2"; shift 2 ;;
      --admin-token)  ADMIN_TOKEN_VAL="$2"; shift 2 ;;
      --sub-token)    SUB_TOKEN_VAL="$2"; shift 2 ;;
      -h|--help)      usage_tokens; return 0 ;;
      *)              die "tokens: unknown option: $1" ;;
    esac
  done

  require_workspace
  resolve_workspace

  local admin_token sub_token actual_admin actual_sub
  admin_token="${ADMIN_TOKEN_VAL:-$(env_value NETWORK_PROXY_ADMIN_TOKEN)}"
  admin_token="${admin_token:-$DEFAULT_ADMIN_TOKEN}"
  sub_token="${SUB_TOKEN_VAL:-$(env_value NETWORK_PROXY_SUBSCRIPTION_TOKEN)}"
  sub_token="${sub_token:-$DEFAULT_SUB_TOKEN}"

  log_info "creating admin token (name=onboard-admin)..."
  if ! actual_admin="$(compose_manager exec -T manager-api \
        uv run python main.py create-admin-token --name onboard-admin --token "$admin_token" 2>/dev/null)"; then
    die "failed to create admin token (is the manager running? try: $0 start -w $WORKSPACE)"
  fi
  env_set "NETWORK_PROXY_ADMIN_TOKEN" "$actual_admin"

  log_info "creating subscription token (name=onboard-subscription)..."
  if ! actual_sub="$(compose_manager exec -T manager-api \
        uv run python main.py create-subscription-token --name onboard-subscription --token "$sub_token" 2>/dev/null)"; then
    die "failed to create subscription token"
  fi
  env_set "NETWORK_PROXY_SUBSCRIPTION_TOKEN" "$actual_sub"

  cat <<EOF

$(log_ok "tokens created and persisted to $(workspace_env)")

  Admin token:        $actual_admin
  Subscription token: $actual_sub

Subscription URL:
  http://${PUBLIC_HOST}:$(manager_port)/subscribe/raw?token=${actual_sub}

Next step:
  $0 approve -w $WORKSPACE
EOF
}

cmd_approve() {
  local join_id="" wait_secs=30
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -w|--workspace) WORKSPACE="$2"; shift 2 ;;
      --id)           join_id="$2"; shift 2 ;;
      --port)         APPROVE_PORT="$2"; shift 2 ;;
      --wait)         wait_secs="$2"; shift 2 ;;
      -h|--help)      usage_approve; return 0 ;;
      *)              die "approve: unknown option: $1" ;;
    esac
  done

  require_workspace
  resolve_workspace

  command -v jq >/dev/null 2>&1 || die "jq is required for approve"

  local admin_token port base_url
  admin_token="$(env_value NETWORK_PROXY_ADMIN_TOKEN)"
  [[ -n "$admin_token" ]] || die "no NETWORK_PROXY_ADMIN_TOKEN in $(workspace_env) (run: $0 tokens -w $WORKSPACE)"
  port="${APPROVE_PORT:-$(env_value NETWORK_PROXY_NODE_PUBLISHED_PORT)}"
  port="${port:-$DEFAULT_NODE_PORT}"
  base_url="http://127.0.0.1:$(manager_port)"

  log_info "looking for pending join requests (waiting up to ${wait_secs}s)..."
  local elapsed=0 first=""
  while [[ $elapsed -lt $wait_secs ]]; do
    local resp
    resp="$(curl -fsS -H "Authorization: Bearer $admin_token" "$base_url/admin/join-requests" 2>/dev/null || echo "[]")"
    if [[ -z "$join_id" ]]; then
      first="$(printf '%s' "$resp" | jq -r '.[] | select(.status=="pending") | .id' 2>/dev/null | head -n1)"
      [[ -n "$first" ]] && join_id="$first"
    fi
    [[ -n "$join_id" ]] && break
    sleep 2
    elapsed=$((elapsed + 2))
  done

  [[ -n "$join_id" ]] || die "no pending join request found after ${wait_secs}s (check node-agent logs: $0 logs node-agent)"

  log_info "approving join request $join_id with assigned_port=$port"
  local result
  if ! result="$(curl -fsS -X POST \
        -H "Authorization: Bearer $admin_token" \
        -H "Content-Type: application/json" \
        -d "{\"assigned_port\": $port}" \
        "$base_url/admin/join-requests/${join_id}/approve")"; then
    die "approval request failed (is the join request still pending?)"
  fi

  printf '%s\n' "$result" | jq .
  log_ok "node approved"
}

cmd_reset() {
  local force=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -w|--workspace) WORKSPACE="$2"; shift 2 ;;
      -f|--force)     force=1; shift ;;
      -h|--help)      usage_reset; return 0 ;;
      *)              die "reset: unknown option: $1" ;;
    esac
  done

  # Allow reset even if .env was deleted — canonicalize the path.
  if [[ -d "$WORKSPACE" ]]; then
    resolve_workspace
  fi

  local env_file data_dir
  env_file="$(workspace_env)"
  data_dir="$(workspace_data)"

  if [[ -f "$env_file" || -d "$data_dir" ]]; then
    if [[ $force -ne 1 ]]; then
      printf 'This will stop all services and delete %s. Continue? [y/N] ' "$data_dir"
      read -r ans
      if ! [[ "${ans:-}" =~ ^[Yy]$ ]]; then
        log_info "aborted"
        return 0
      fi
    fi
  fi

  if [[ -f "$env_file" ]]; then
    log_info "stopping stacks..."
    compose_node    down --volumes 2>&1 || true
    compose_manager down --volumes 2>&1 || true
  fi

  if [[ -d "$data_dir" ]]; then
    rm -rf "$data_dir"
  fi
  log_ok "reset complete (data removed; .env preserved at $env_file)"
}

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
print_summary() {
  local port admin_token sub_token
  port="$(manager_port)"
  admin_token="$(env_value NETWORK_PROXY_ADMIN_TOKEN)"
  sub_token="$(env_value NETWORK_PROXY_SUBSCRIPTION_TOKEN)"

  cat <<EOF

$(log_ok "stack is up")

  Manager:     http://127.0.0.1:${port}
  Dashboard:   http://127.0.0.1:${port}/dashboard
  Docs:        http://127.0.0.1:${port}/docs

EOF
  if [[ -n "$sub_token" ]]; then
    printf '  Subscription: http://%s:%s/subscribe/raw?token=%s\n' "$PUBLIC_HOST" "$port" "$sub_token"
  else
    printf '  Subscription: (run: %s tokens -w %s)\n' "$0" "$WORKSPACE"
  fi
  if [[ -z "$admin_token" ]]; then
    printf '  Admin token:  (run: %s tokens -w %s)\n' "$0" "$WORKSPACE"
  fi
  cat <<EOF

  Next: approve the node:
    $0 approve -w $WORKSPACE
EOF
}

# --------------------------------------------------------------------------
# Usage / help
# --------------------------------------------------------------------------
usage() {
  cat <<EOF
Usage: $0 <command> [options]

Single-entry onboarding for the network-proxy stack.

Commands:
  init     Create workspace, generate .env, pre-pull images
  start    Start manager + subconverter + node agent + node v2ray
  tokens   Create admin + subscription tokens in the running manager
  approve  Approve a pending node join request
  status   Show container status + join requests + published nodes
  logs     Tail service logs (default: all manager services)
  stop     Stop both stacks (manager + node)
  reset    Stop everything and remove data/ (use -f to skip confirm)

Common options:
  -w, --workspace <path>   Workspace root (default: $DEFAULT_WORKSPACE)

Examples:
  sudo $0 init
  $0 start
  $0 tokens
  $0 approve
  $0 status
  $0 logs node-agent
  $0 stop
  $0 reset -f

Run '$0 <command> -h' for command-specific options.
EOF
}

usage_init() {
  cat <<'EOF'
init options:
  -w, --workspace <path>    Workspace root (default: /opt/network-proxy)
  --public-host <host>      Host advertised by manager + node (default: 127.0.0.1)
  --node-port <port>        Node published + requested port (default: 21001)
  --admin-token <token>     Seed admin token value (default: admin-db)
  --sub-token <token>       Seed subscription token value (default: sub-db)
  --force                   Overwrite an existing .env
EOF
}

usage_start() {
  cat <<'EOF'
start options:
  -w, --workspace <path>    Workspace root to start
EOF
}

usage_stop() {
  cat <<'EOF'
stop options:
  -w, --workspace <path>    Workspace root to stop
EOF
}

usage_logs() {
  cat <<'EOF'
logs options:
  -w, --workspace <path>    Workspace root
  [service]                 e.g. manager-api, node-agent, subconverter, node-v2ray
                            (default: tail all manager services)
EOF
}

usage_tokens() {
  cat <<'EOF'
tokens options:
  -w, --workspace <path>    Workspace root
  --admin-token <token>     Override admin token value
  --sub-token <token>       Override subscription token value
EOF
}

usage_approve() {
  cat <<'EOF'
approve options:
  -w, --workspace <path>    Workspace root
  --id <join-request-id>    Approve a specific join request (default: first pending)
  --port <port>             Assigned port (default: NETWORK_PROXY_NODE_PUBLISHED_PORT)
  --wait <seconds>          How long to wait for a join request (default: 30)
EOF
}

usage_reset() {
  cat <<'EOF'
reset options:
  -w, --workspace <path>    Workspace root
  -f, --force               Skip confirmation prompt
EOF
}

# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------
main() {
  local cmd="${1:-}"
  if [[ -z "$cmd" ]]; then
    usage
    exit 1
  fi
  shift
  case "$cmd" in
    init)    cmd_init "$@" ;;
    start)   cmd_start "$@" ;;
    stop)    cmd_stop "$@" ;;
    status)  cmd_status "$@" ;;
    logs)    cmd_logs "$@" ;;
    tokens)  cmd_tokens "$@" ;;
    approve) cmd_approve "$@" ;;
    reset)   cmd_reset "$@" ;;
    -h|--help|help) usage ;;
    *) die "unknown command: $cmd (try: $0 --help)" ;;
  esac
}

main "$@"
