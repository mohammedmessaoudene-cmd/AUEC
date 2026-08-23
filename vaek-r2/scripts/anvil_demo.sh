#!/usr/bin/env bash
set -euo pipefail

RPC_URL="${ANVIL_RPC_URL:-http://127.0.0.1:8545}"
DEV_KEY="${ANVIL_DEV_PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"
LOG_DIR="${TMPDIR:-/tmp}/vaek-r2-anvil-demo-$$"
mkdir -p "$LOG_DIR"

anvil --silent --port 8545 >"$LOG_DIR/anvil.log" 2>&1 &
ANVIL_PID=$!
trap 'kill "$ANVIL_PID" >/dev/null 2>&1 || true' EXIT

for _ in $(seq 1 50); do
  if cast chain-id --rpc-url "$RPC_URL" >/dev/null 2>&1; then break; fi
  sleep 0.2
done

forge create demo/VAEKDemo.sol:VAEKDemo --rpc-url "$RPC_URL" --private-key "$DEV_KEY" --broadcast \
  >"$LOG_DIR/deploy.txt" 2>&1
DEMO=$(awk '/Deployed to:/ {print $3}' "$LOG_DIR/deploy.txt" | tail -1)
[[ "$DEMO" =~ ^0x[0-9a-fA-F]{40}$ ]] || { cat "$LOG_DIR/deploy.txt" >&2; exit 1; }
cast send "$DEMO" 'run()' --rpc-url "$RPC_URL" --private-key "$DEV_KEY" >/dev/null
COMPLETED=$(cast call "$DEMO" 'completed()(bool)' --rpc-url "$RPC_URL" | tail -1)
BLOCKED=$(cast call "$DEMO" 'blockedObserved()(bool)' --rpc-url "$RPC_URL" | tail -1)
[[ "$COMPLETED" == "true" && "$BLOCKED" == "true" ]]

echo "VAEK_R2_ANVIL_DEMO=PASS"
echo "CHAIN_ID=$(cast chain-id --rpc-url "$RPC_URL")"
echo "DEMO=$DEMO"

