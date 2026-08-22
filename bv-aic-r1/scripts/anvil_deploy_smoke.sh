#!/usr/bin/env bash
set -euo pipefail
RPC_URL="${ANVIL_RPC_URL:-http://127.0.0.1:8545}"
DEV_KEY="${ANVIL_DEV_PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"
DEV_ADDR="${ANVIL_DEV_ADDRESS:-0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266}"
LOG_DIR="${LOG_DIR:-reports/anvil-smoke}"
mkdir -p "$LOG_DIR"
cleanup() { if [[ -n "${ANVIL_PID:-}" ]] && kill -0 "$ANVIL_PID" 2>/dev/null; then kill "$ANVIL_PID" || true; fi; }
trap cleanup EXIT
anvil --silent --host 127.0.0.1 --port 8545 >"$LOG_DIR/anvil.log" 2>&1 &
ANVIL_PID=$!
for _ in $(seq 1 30); do if cast chain-id --rpc-url "$RPC_URL" >/dev/null 2>&1; then break; fi; sleep 0.2; done
CHAIN_ID=$(cast chain-id --rpc-url "$RPC_URL")
[[ "$CHAIN_ID" == "31337" ]] || { echo "Unexpected Anvil chain id: $CHAIN_ID" >&2; exit 1; }
forge create contracts/MockERC20.sol:MockERC20 --rpc-url "$RPC_URL" --private-key "$DEV_KEY" --broadcast >"$LOG_DIR/mock-deploy.txt" 2>&1
forge create contracts/BVAICAuthority.sol:BVAICAuthority --constructor-args "$DEV_ADDR" --rpc-url "$RPC_URL" --private-key "$DEV_KEY" --broadcast >"$LOG_DIR/authority-deploy.txt" 2>&1
grep -Eq 'Deployed to:|deployedTo' "$LOG_DIR/mock-deploy.txt"
grep -Eq 'Deployed to:|deployedTo' "$LOG_DIR/authority-deploy.txt"
echo "ANVIL_DEPLOY_SMOKE=PASS"
echo "CHAIN_ID=$CHAIN_ID"
