#!/usr/bin/env bash
set -euo pipefail

RPC_URL="${ZENITH_RPC_URL:-https://rpc.testnet.zenith.network/}"
FAUCET_URL="${ZENITH_FAUCET_URL:-https://explorer.testnet.zenith.network/api/faucet}"
EXPECTED_CHAIN_ID="936485"
LOG_DIR="${ZENITH_LOG_DIR:-reports/zenith-testnet}"
REPORT="${ZENITH_REPORT:-reports/ZENITH_TESTNET_DEPLOYMENT.json}"
mkdir -p "$LOG_DIR"

if [[ -s "$REPORT" ]]; then
  echo "ZENITH_PUBLIC_DEPLOYMENT=ALREADY_RECORDED"
  exit 0
fi

CHAIN_ID="$(cast chain-id --rpc-url "$RPC_URL")"
[[ "$CHAIN_ID" == "$EXPECTED_CHAIN_ID" ]] || { echo "Unexpected Zenith chain id: $CHAIN_ID" >&2; exit 1; }

# Ephemeral deployment/verifier key: kept only in process memory for this CI job.
PRIVATE_KEY="0x$(openssl rand -hex 32)"
DEPLOYER="$(cast wallet address --private-key "$PRIVATE_KEY")"
VENDOR="0x$(openssl rand -hex 20)"

# The public faucet is a separate web service from the EVM RPC and can have transient
# 502/503 failures. Probe status first, then retry claims with bounded backoff.
FAUCET_READY=0
for attempt in $(seq 1 8); do
  HTTP_CODE="$(curl -sS --connect-timeout 10 --max-time 30 \
    -o "$LOG_DIR/faucet-status.json" -w '%{http_code}' "$FAUCET_URL" || echo 000)"
  if [[ "$HTTP_CODE" == "200" ]] && python - "$LOG_DIR/faucet-status.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        d=json.load(f)
    raise SystemExit(0 if d.get('enabled') is True else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    FAUCET_READY=1
    break
  fi
  echo "Faucet status attempt $attempt failed (HTTP $HTTP_CODE); retrying" >&2
  sleep $((attempt * 2))
done
[[ "$FAUCET_READY" == "1" ]] || { echo "Zenith faucet status never became healthy" >&2; exit 1; }

CLAIM_OK=0
for attempt in $(seq 1 10); do
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
    raise SystemExit(0 if d.get('ok') is True else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    CLAIM_OK=1
    break
  fi

  if [[ "$HTTP_CODE" == "429" ]]; then
    RETRY_AFTER="$(awk 'BEGIN{IGNORECASE=1} /^Retry-After:/ {gsub("\r",""); print $2}' "$LOG_DIR/faucet-headers.txt" | tail -1)"
    if [[ "$RETRY_AFTER" =~ ^[0-9]+$ ]] && (( RETRY_AFTER <= 120 )); then
      echo "Faucet rate-limited; respecting Retry-After=${RETRY_AFTER}s" >&2
      sleep "$RETRY_AFTER"
      continue
    fi
  fi

  echo "Faucet claim attempt $attempt failed (HTTP $HTTP_CODE); retrying" >&2
  sleep $((attempt * 3))
done
[[ "$CLAIM_OK" == "1" ]] || {
  echo "Zenith faucet claim failed after bounded retries" >&2
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
[[ "$BALANCE_WEI" =~ ^[0-9]+$ ]] && (( BALANCE_WEI > 0 )) || { echo "Faucet funds not received" >&2; exit 1; }

# Deploy the demo ERC-20 and the BV-AIC authority kernel.
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

# Helper: send a transaction and print the receipt transactionHash.
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

# Fund the authority kernel with mock tokens.
MINT_TX="$(send_tx mint "$TOKEN" 'mint(address,uint256)' "$AUTHORITY" 1000)"

NOW="$(date +%s)"
VALID_UNTIL="$((NOW + 86400))"
DEADLINE="$((NOW + 3600))"

# Principal = deployer, AI executor = deployer for this first public lifecycle demonstration.
MANDATE_TX="$(send_tx mandate "$AUTHORITY" \
  'createMandate(address,address,uint128,uint128,uint128,uint64,uint64,bool,address[])' \
  "$DEPLOYER" "$TOKEN" 100 250 50 "$NOW" "$VALID_UNTIL" true "[$VENDOR]")"

NONCE="$(cast call "$AUTHORITY" 'mandateNonce()(uint256)' --rpc-url "$RPC_URL" | tail -1)"
[[ "$NONCE" == "1" ]] || { echo "Unexpected mandate nonce: $NONCE" >&2; exit 1; }
MANDATE_ENCODED="$(cast abi-encode 'f(address,uint256,address,uint256)' "$AUTHORITY" "$CHAIN_ID" "$DEPLOYER" "$NONCE")"
MANDATE_ID="$(cast keccak "$MANDATE_ENCODED")"

EXECUTION_ID="$(cast keccak 'BV-AIC/ZENITH/DEMO/R1')"
OBSERVATION_HASH="$(cast keccak 'zenith:observation:r1')"
MODEL_COMMITMENT="$(cast keccak 'model:demo:r1')"
POLICY_COMMITMENT="$(cast keccak 'policy:bounded-transfer:r1')"
EVIDENCE_HASH="$(cast keccak 'evidence:zenith-public-lifecycle:r1')"

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

export CHAIN_ID RPC_URL DEPLOYER VENDOR TOKEN TOKEN_DEPLOY_TX AUTHORITY AUTHORITY_DEPLOY_TX CODE_HASH
export MINT_TX MANDATE_TX MANDATE_ID EXECUTION_ID DECISION_HASH SUBMIT_TX VERIFY_TX EXECUTE_TX
export VENDOR_BALANCE SPENT CONSUMED BALANCE_WEI DEPLOYER_BALANCE_AFTER SOURCE_COMMIT RUN_ID UTC_TIME REPORT
python - <<'PY'
import json, os
r = {
  'status': 'PASS',
  'network': 'Zenith EVM Testnet',
  'chain_id': int(os.environ['CHAIN_ID']),
  'rpc': os.environ['RPC_URL'],
  'deployed_at_utc': os.environ['UTC_TIME'],
  'source_commit': os.environ['SOURCE_COMMIT'],
  'github_run_id': os.environ['RUN_ID'],
  'deployer_address': os.environ['DEPLOYER'],
  'verifier_address': os.environ['DEPLOYER'],
  'verifier_key_persistence': 'EPHEMERAL_DESTROYED_AFTER_CI_JOB',
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

# Never persist the ephemeral key.
unset PRIVATE_KEY

echo "ZENITH_PUBLIC_DEPLOYMENT=PASS"
echo "CHAIN_ID=$CHAIN_ID"
echo "AUTHORITY=$AUTHORITY"
echo "EXECUTION_ID=$EXECUTION_ID"
echo "EXECUTE_TX=$EXECUTE_TX"
