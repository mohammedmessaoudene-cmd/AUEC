#!/usr/bin/env bash
set -euo pipefail

RPC_URL="${ANVIL_RPC_URL:-http://127.0.0.1:8545}"
DEV_KEY="${ANVIL_DEV_PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"
DEV_ADDR="${ANVIL_DEV_ADDRESS:-0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266}"
LOG_DIR="${LOG_DIR:-reports/anvil-smoke}"
mkdir -p "$LOG_DIR"

cleanup() {
  if [[ -n "${ANVIL_PID:-}" ]] && kill -0 "$ANVIL_PID" 2>/dev/null; then
    kill "$ANVIL_PID" || true
  fi
}
trap cleanup EXIT

anvil --silent --host 127.0.0.1 --port 8545 >"$LOG_DIR/anvil.log" 2>&1 &
ANVIL_PID=$!
for _ in $(seq 1 40); do
  if cast chain-id --rpc-url "$RPC_URL" >/dev/null 2>&1; then break; fi
  sleep 0.2
done
[[ "$(cast chain-id --rpc-url "$RPC_URL")" == "31337" ]]

forge create contracts/MockEffectEnvironment.sol:MockPurchaseAdapter \
  --rpc-url "$RPC_URL" --private-key "$DEV_KEY" --broadcast \
  >"$LOG_DIR/adapter-deploy.txt" 2>&1
ADAPTER="$(awk '/Deployed to:/ {print $3}' "$LOG_DIR/adapter-deploy.txt" | tail -1)"
[[ "$ADAPTER" =~ ^0x[0-9a-fA-F]{40}$ ]]

forge create contracts/RefinementEffectKernel.sol:RefinementEffectKernel \
  --rpc-url "$RPC_URL" --private-key "$DEV_KEY" --broadcast \
  --constructor-args "$DEV_ADDR" "$ADAPTER" \
  >"$LOG_DIR/kernel-deploy.txt" 2>&1
KERNEL="$(awk '/Deployed to:/ {print $3}' "$LOG_DIR/kernel-deploy.txt" | tail -1)"
[[ "$KERNEL" =~ ^0x[0-9a-fA-F]{40}$ ]]
[[ "$(cast call "$KERNEL" 'verifier()(address)' --rpc-url "$RPC_URL" | tr '[:upper:]' '[:lower:]')" == "$(echo "$DEV_ADDR" | tr '[:upper:]' '[:lower:]')" ]]
[[ "$(cast call "$KERNEL" 'purchaseAdapter()(address)' --rpc-url "$RPC_URL" | tr '[:upper:]' '[:lower:]')" == "$(echo "$ADAPTER" | tr '[:upper:]' '[:lower:]')" ]]
CODE="$(cast code "$KERNEL" --rpc-url "$RPC_URL")"
[[ -n "$CODE" && "$CODE" != "0x" ]]

echo "VAEK_R2_ANVIL_DEPLOYMENT=PASS"
echo "CHAIN_ID=31337"
echo "KERNEL=$KERNEL"
echo "PURCHASE_ADAPTER=$ADAPTER"
