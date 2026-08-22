# BV-AIC R1 — Sepolia deployment runbook

Target: Ethereum Sepolia, chain ID `11155111`.

## Security
Never commit or paste a private key or seed phrase. Prefer a Foundry encrypted keystore and pass its account name through `DEPLOYER_ACCOUNT`.

## Required gates before broadcast
1. `forge build` PASS.
2. Directed and fuzz tests PASS.
3. Stateful invariants PASS.
4. `./scripts/anvil_deploy_smoke.sh` PASS.
5. Deployment account funded with Sepolia ETH.
6. Verifier address confirmed.

## Deployment
Set `SEPOLIA_RPC_URL`, `VERIFIER_ADDRESS`, and `DEPLOYER_ACCOUNT`, then run `./scripts/deploy_sepolia.sh`.

The script refuses to broadcast unless the connected chain ID is exactly `11155111`.

## Evidence to preserve
Deployed address, transaction hash, block number, compiler/Foundry version, source commit, source SHA-256, and complete deployment log. Verify the contract address on a Sepolia explorer before any funded research interaction.
