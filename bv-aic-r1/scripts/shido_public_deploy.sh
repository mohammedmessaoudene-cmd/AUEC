#!/usr/bin/env bash
set -euo pipefail

RPC_URL="${SHIDO_RPC_URL:-https://rpc.testnet.shidoscan.net}"
FAUCET_URL="${SHIDO_FAUCET_URL:-https://faucet.testnet.shidoscan.net/api/drip}"
EXPECTED_CHAIN_ID="9007"
LOG_DIR="${SHIDO_LOG_DIR:-reports/shido-testnet}"
REPORT="${SHIDO_REPORT:-reports/SHIDO_TESTNET_DEPLOYMENT.json}"
mkdir -p "$LOG_DIR"

if [[ -s "$REPORT" ]]; then
  echo "SHIDO_PUBLIC_DEPLOYMENT=ALREADY_RECORDED"
  exit 0
fi

CHAIN_ID="$(cast chain-id --rpc-url "$RPC_URL")"
[[ "$CHAIN_ID" == "$EXPECTED_CHAIN_ID" ]] || { echo "Unexpected Shido chain id: $CHAIN_ID" >&2; exit 1; }

# Ephemeral deployment/verifier key: never persisted in the repository or artifacts.
PRIVATE_KEY="0x$(openssl rand -hex 32)"
DEPLOYER="$(cast wallet address --private-key "$PRIVATE_KEY")"
VENDOR="0x$(openssl rand -hex 20)"

# Official Shido testnet faucet API. Retry only transient server/network errors.
CLAIM_OK=0
for attempt in $(seq 1 6); do
  : > "$LOG_DIR/faucet-headers.txt"
  HTTP_CODE="$(curl -sS --connect-timeout 10 --max-time 30 \
    -D "$LOG_DIR/faucet-headers.txt" \
    -o "$LOG_DIR/faucet.json" -w '%{http_code}' \
    -X POST "$FAUCET_URL" \
    -H 'Content-Type: application/json' \
    -d "{\"address\":\"$DEPLOYER\"}" || echo 000)"

  if [[ "$HTTP_CODE" =~ ^2[0-9][0-9]$ ]] && python - "$LOG_DIR/faucet.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        d=json.load(f)
    raise SystemExit(0 if d.get('success') is True else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    CLAIM_OK=1
    break
  fi

  # A 429 is a hard CI-environment rate limit on this faucet, not a contract error.
  if [[ "$HTTP_CODE" == "429" ]]; then
    echo "Shido faucet rate-limited this runner IP" >&2
    cat "$LOG_DIR/faucet.json" >&2 || true
    exit 2
  fi

  echo "Shido faucet attempt $attempt failed (HTTP $HTTP_CODE); retrying" >&2
  sleep $((attempt * 2))
done
[[ "$CLAIM_OK" == "1" ]] || {
  echo "Shido faucet claim failed after bounded retries" >&2
  cat "$LOG_DIR/faucet.json" >&2 || true
  exit 1
}

BALANCE_WEI="0"
for _ in $(seq 1 30); do
  BALANCE_WEI="$(cast balance "$DEPLOYER" --wei --rpc-url "$RPC_URL" 2>/dev/null || echo 0)"
  if [[ "$BALANCE_WEI" =~ ^[0-9]+$ ]] && (( BALANCE_WEI > 0 )); then
    break
  fi
  sleep 2
done
[[ "$BALANCE_WEI" =~ ^[0-9]+$ ]] && (( BALANCE_WEI > 0 )) || { echo "Faucet funds not received on Shido" >&2; exit 1; }

forge create contracts/MockERC20.sol:MockERC20 \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY" --broadcast \
  > "$LOG_DIR/token-deploy.txt" 2>&1
TOKEN="$(awk '/Deployed to:/ {print $3}' "$LOG_DIR/token-deploy.txt" | tail -1)"
TOKEN_DEPLOY_TX="$(awk '/Transaction hash:/ {print $3}' "$LOG_DIR/token-deploy.txt" | tail -1)"
[[ "$TOKEN" =~ ^0x[0-9a-fA-F]{40}$ ]] || { cat "$LOG_DIR/token-deploy.txt" >&2; exit 1; }

forge create contracts/BVAICAuthority.sol:BVAICAuthority \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY" --broadcast \
  --constructor-args "$DEPLOYER" \
  > "$LOG_DIR/authority-deploy.txt" 2>&1
AUTHORITY="$(awk '/Deployed to:/ {print $3}' "$LOG_DIR/authority-deploy.txt" | tail -1)"
AUTHORITY_DEPLOY_TX="$(awk '/Transaction hash:/ {print $3}' "$LOG_DIR/authority-deploy.txt" | tail -1)"
[[ "$AUTHORITY" =~ ^0x[0-9a-fA-F]{40}$ ]] || { cat "$LOG_DIR/authority-deploy.txt" >&2; exit 1; }

CODE="$(cast code "$AUTHORITY" --rpc-url "$RPC_URL")"
[[ "$CODE" != "0x" && -n "$CODE" ]] || { echo "No runtime bytecode at authority address" >&2; exit 1; }
CODE_HASH="$(cast keccak "$CODE")"
VERIFIER_ONCHAIN="$(cast call "$AUTHORITY" 'verifier()(address)' --rpc-url "$RPC_URL" | tail -1)"
[[ "${VERIFIER_ONCHAIN,,}" == "${DEPLOYER,,}" ]] || { echo "Verifier mismatch" >&2; exit 1; }

send_tx() {
  local out="$1"; shift
  cast send "$@" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY" --json > "$LOG_DIR/$out.json"
  python - "$LOG_DIR/$out.json" <<'PY'
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as f:
    d = json.load(f)
h = d.get('transactionHash') or d.get('hash')
if not h:
    raise SystemExit('transaction hash missing')
print(h)
PY
}

MINT_TX="$(send_tx mint "$TOKEN" 'mint(address,uint256)' "$AUTHORITY" 1000)"

NOW="$(date +%s)"
VALID_UNTIL="$((NOW + 86400))"
DEADLINE="$((NOW + 3600))"

# First public lifecycle: deployer acts as principal, AI executor and verifier only for smoke proof.
MANDATE_TX="$(send_tx mandate "$AUTHORITY" \
  'createMandate(address,address,uint128,uint128,uint128,uint64,uint64,bool,address[])' \
  "$DEPLOYER" "$TOKEN" 100 250 50 "$NOW" "$VALID_UNTIL" true "[$VENDOR]")"

NONCE="$(cast call "$AUTHORITY" 'mandateNonce()(uint256)' --rpc-url "$RPC_URL" | tail -1)"
[[ "$NONCE" == "1" ]] || { echo "Unexpected mandate nonce: $NONCE" >&2; exit 1; }
MANDATE_ENCODED="$(cast abi-encode 'f(address,uint256,address,uint256)' "$AUTHORITY" "$CHAIN_ID" "$DEPLOYER" "$NONCE")"
MANDATE_ID="$(cast keccak "$MANDATE_ENCODED")"

EXECUTION_ID="$(cast keccak 'BV-AIC/SHIDO/DEMO/R1')"
OBSERVATION_HASH="$(cast keccak 'shido:observation:r1')"
MODEL_COMMITMENT="$(cast keccak 'model:demo:r1')"
POLICY_COMMITMENT="$(cast keccak 'policy:bounded-transfer:r1')"
EVIDENCE_HASH="$(cast keccak 'evidence:shido-public-lifecycle:r1')"

SUBMIT_TX="$(send_tx submit "$AUTHORITY" \
  'submitDecision(bytes32,bytes32,address,address,uint128,uint64,bytes32,bytes32,bytes32)' \
  "$EXECUTION_ID" "$MANDATE_ID" "$VENDOR" "$TOKEN" 20 "$DEADLINE" \
  "$OBSERVATION_HASH" "$MODEL_COMMITMENT" "$POLICY_COMMITMENT")"

DECISION_HASH="$(cast call "$AUTHORITY" \
  'computeDecisionHash(bytes32,bytes32,address,address,uint128,uint64,bytes32,bytes32,bytes32)(bytes32)' \
  "$EXECUTION_ID" "$MANDATE_ID" "$VENDOR" "$TOKEN" 20 "$DEADLINE" \
  "$OBSERVATION_HASH" "$MODEL_COMMITMENT" "$POLICY_COMMITMENT" \
  --rpc-url "$RPC_URL" | tail -1)"

VERIFY_TX="$(send_tx verify "$AUTHORITY" \
  'recordVerification(bytes32,bytes32,uint8,bytes32,uint64)' \
  "$EXECUTION_ID" "$DECISION_HASH" 1 "$EVIDENCE_HASH" "$DEADLINE")"

EVAL_RAW="$(cast call "$AUTHORITY" 'evaluate(bytes32)(uint8,bytes32)' "$EXECUTION_ID" --rpc-url "$RPC_URL")"
EVAL_RESULT="$(printf '%s\n' "$EVAL_RAW" | head -1 | tr -d '[:space:]')"
[[ "$EVAL_RESULT" == "1" ]] || { printf 'Unexpected evaluate result: %s\n' "$EVAL_RAW" >&2; exit 1; }

EXECUTE_TX="$(send_tx execute "$AUTHORITY" 'execute(bytes32)' "$EXECUTION_ID")"

VENDOR_BALANCE="$(cast call "$TOKEN" 'balanceOf(address)(uint256)' "$VENDOR" --rpc-url "$RPC_URL" | tail -1)"
SPENT="$(cast call "$AUTHORITY" 'spentOf(bytes32)(uint128)' "$MANDATE_ID" --rpc-url "$RPC_URL" | tail -1)"
CONSUMED="$(cast call "$AUTHORITY" 'isConsumed(bytes32)(bool)' "$EXECUTION_ID" --rpc-url "$RPC_URL" | tail -1)"
[[ "$VENDOR_BALANCE" == "20" ]] || { echo "Vendor balance mismatch: $VENDOR_BALANCE" >&2; exit 1; }
[[ "$SPENT" == "20" ]] || { echo "Spent mismatch: $SPENT" >&2; exit 1; }
[[ "$CONSUMED" == "true" ]] || { echo "Consumed mismatch: $CONSUMED" >&2; exit 1; }

DEPLOYER_BALANCE_AFTER="$(cast balance "$DEPLOYER" --wei --rpc-url "$RPC_URL")"
SOURCE_COMMIT="${GITHUB_SHA:-unknown}"
RUN_ID="${GITHUB_RUN_ID:-unknown}"
UTC_TIME="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
FAUCET_TX="$(python - "$LOG_DIR/faucet.json" <<'PY'
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as f: d=json.load(f)
print(d.get('txHash',''))
PY
)"

export CHAIN_ID RPC_URL DEPLOYER VENDOR TOKEN TOKEN_DEPLOY_TX AUTHORITY AUTHORITY_DEPLOY_TX CODE_HASH
export MINT_TX MANDATE_TX MANDATE_ID EXECUTION_ID DECISION_HASH SUBMIT_TX VERIFY_TX EXECUTE_TX
export VENDOR_BALANCE SPENT CONSUMED BALANCE_WEI DEPLOYER_BALANCE_AFTER SOURCE_COMMIT RUN_ID UTC_TIME REPORT FAUCET_TX
python - <<'PY'
import json, os
r = {
  'status': 'PASS',
  'network': 'Shido Testnet',
  'chain_id': int(os.environ['CHAIN_ID']),
  'rpc': os.environ['RPC_URL'],
  'explorer': 'https://testnet.shidoscan.net',
  'deployed_at_utc': os.environ['UTC_TIME'],
  'source_commit': os.environ['SOURCE_COMMIT'],
  'github_run_id': os.environ['RUN_ID'],
  'deployer_address': os.environ['DEPLOYER'],
  'verifier_address': os.environ['DEPLOYER'],
  'verifier_key_persistence': 'EPHEMERAL_DESTROYED_AFTER_CI_JOB',
  'faucet_tx': os.environ['FAUCET_TX'],
  'vendor_address': os.environ['VENDOR'],
  'mock_token': {'address': os.environ['TOKEN'], 'deployment_tx': os.environ['TOKEN_DEPLOY_TX']},
  'authority': {
    'address': os.environ['AUTHORITY'],
    'deployment_tx': os.environ['AUTHORITY_DEPLOY_TX'],
    'runtime_code_hash': os.environ['CODE_HASH']
  },
  'lifecycle': {
    'mint_tx': os.environ['MINT_TX'],
    'mandate_tx': os.environ['MANDATE_TX'],
    'mandate_id': os.environ['MANDATE_ID'],
    'execution_id': os.environ['EXECUTION_ID'],
    'decision_hash': os.environ['DECISION_HASH'],
    'submit_tx': os.environ['SUBMIT_TX'],
    'verification_tx': os.environ['VERIFY_TX'],
    'execute_tx': os.environ['EXECUTE_TX'],
    'vendor_balance': int(os.environ['VENDOR_BALANCE']),
    'spent': int(os.environ['SPENT']),
    'consumed': os.environ['CONSUMED'].lower() == 'true'
  },
  'faucet_balance_before_wei': int(os.environ['BALANCE_WEI']),
  'deployer_balance_after_wei': int(os.environ['DEPLOYER_BALANCE_AFTER']),
  'security_note': 'Public research smoke instance only; verifier private key was never persisted. Do not use with assets of value.'
}
with open(os.environ['REPORT'], 'w', encoding='utf-8') as f:
    json.dump(r, f, indent=2, sort_keys=True)
    f.write('\n')
PY

unset PRIVATE_KEY

echo "SHIDO_PUBLIC_DEPLOYMENT=PASS"
echo "CHAIN_ID=$CHAIN_ID"
echo "AUTHORITY=$AUTHORITY"
echo "EXECUTION_ID=$EXECUTION_ID"
echo "EXECUTE_TX=$EXECUTE_TX"
