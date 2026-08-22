#!/usr/bin/env bash
set -euo pipefail
: "${SEPOLIA_RPC_URL:?Set SEPOLIA_RPC_URL locally.}"
: "${VERIFIER_ADDRESS:?Set VERIFIER_ADDRESS.}"
if [[ -n "${DEPLOYER_ACCOUNT:-}" ]]; then
  SIGNER=(--account "$DEPLOYER_ACCOUNT")
elif [[ -n "${DEPLOYER_PRIVATE_KEY:-}" ]]; then
  SIGNER=(--private-key "$DEPLOYER_PRIVATE_KEY")
else
  echo "No signer configured. Prefer a local Foundry keystore via DEPLOYER_ACCOUNT; never commit or paste a private key into chat." >&2
  exit 2
fi
CHAIN_ID=$(cast chain-id --rpc-url "$SEPOLIA_RPC_URL")
[[ "$CHAIN_ID" == "11155111" ]] || { echo "Refusing deployment: expected Sepolia chain id 11155111, got $CHAIN_ID" >&2; exit 3; }
forge build
mkdir -p reports/sepolia
UTC=$(date -u +%Y%m%dT%H%M%SZ)
OUT="reports/sepolia/deploy-$UTC.txt"
{
  echo "BV-AIC R1 Sepolia deployment"
  echo "timestamp_utc=$UTC"
  echo "chain_id=$CHAIN_ID"
  echo "verifier=$VERIFIER_ADDRESS"
  forge create contracts/BVAICAuthority.sol:BVAICAuthority --constructor-args "$VERIFIER_ADDRESS" --rpc-url "$SEPOLIA_RPC_URL" "${SIGNER[@]}" --broadcast
} | tee "$OUT"
echo "Deployment log: $OUT"
