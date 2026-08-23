# VAEK R2 typed-effect execution kernel (research candidate)

## Scope

This draft introduces a research-only typed-effect kernel for ERC-20 transfer, exact-input swap and service escrow. It preserves the R1 baseline and adds symbolic resources, attenuated authority, execution-time revalidation, monotone risk escalation, typed adapters and durable receipts.

## Evidence reproduced locally

- R1: 24/24 Foundry tests pass, including the preserved invariant campaign.
- R2: 36/36 Foundry tests pass, including 3 core fuzz properties at 5,000 cases and 6 invariant campaigns at 512 runs x 64 depth.
- Python: 9 bridge/source-guard tests and 4 independent receipt-verifier tests pass.
- Existing repository Python regression: 54 tests pass.
- Local Anvil demo: pass on chain ID 31337.
- `forge fmt --check`, build/size gate and prohibited-surface source scan: pass.

## Explicit limits

- No production DEX, oracle, provider network, mainnet or real funds.
- The 6,000-case comparator is a deterministic reference-model corpus, not 6,000 EVM transactions.
- Kernel runtime is 24,108 bytes, only 468 bytes below EIP-170.
- Slither, Echidna, Halmos, Medusa and general mutation tooling were unavailable.
- This is not an audit, novelty determination, release approval or production-readiness claim.

## Review requested

Please challenge effect containment, attenuation, authorization invalidation, reentrancy, receipt integrity, bridge strictness, benchmark fairness and the documented novelty boundaries. The PR must remain draft; do not merge, release, deploy to mainnet or use real funds.
