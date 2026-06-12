#!/bin/sh
set -eu

CONFIG_PATH=${NETWORK_PROXY_NODE_RUNTIME_CONFIG_FILE:-/app/data/node-v2ray-config.json}
RELOAD_MARKER=${NETWORK_PROXY_NODE_RELOAD_MARKER_FILE:-/app/data/node-v2ray-reload.marker}
POLL_SECONDS=${NETWORK_PROXY_NODE_V2RAY_POLL_SECONDS:-2}

mkdir -p "$(dirname "$CONFIG_PATH")"
touch "$RELOAD_MARKER"

runner_pid=""
last_marker=""

stop_runner() {
  if [ -n "$runner_pid" ] && kill -0 "$runner_pid" 2>/dev/null; then
    kill "$runner_pid" 2>/dev/null || true
    wait "$runner_pid" 2>/dev/null || true
  fi
  runner_pid=""
}

start_runner() {
  if [ ! -s "$CONFIG_PATH" ]; then
    return
  fi
  v2ray run -config "$CONFIG_PATH" &
  runner_pid=$!
}

trap 'stop_runner; exit 0' INT TERM

while :; do
  if [ -e "$RELOAD_MARKER" ]; then
    marker_value=$(stat -c %Y "$RELOAD_MARKER")
  else
    marker_value="missing"
  fi

  if [ "$marker_value" != "$last_marker" ]; then
    stop_runner
    start_runner
    last_marker="$marker_value"
  fi

  if [ -n "$runner_pid" ] && ! kill -0 "$runner_pid" 2>/dev/null; then
    wait "$runner_pid" 2>/dev/null || true
    runner_pid=""
  fi

  sleep "$POLL_SECONDS"
done