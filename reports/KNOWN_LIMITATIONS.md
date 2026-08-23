# Known limitations

- Research-only mocks; no production DEX, oracle, provider network, mainnet or real funds.
- One verifier identity; method metadata is committed but no quorum/family independence proof exists.
- The adapter registry is privileged despite versioning, code hashes and a one-hour replacement delay.
- The resource registry uses coarse global-version invalidation, creating avoidable liveness loss.
- Kernel runtime is 24,108 bytes, leaving only 468 bytes under EIP-170.
- Risk thresholds are deterministic but not economically calibrated.
- Service receipt proves escrow funding; later completion/rejection/refund is visible in adapter state/events but does not rewrite that receipt.
- Fee-on-transfer is measured; rebasing and exotic balance behavior are not supported claims.
- Swap quote commitment/freshness and min-output are enforced, but no production oracle or MEV defense is demonstrated.
- The independent verifier has a cross-language golden vector and tamper corpus; automatic extraction from arbitrary live RPC logs is not productionized.
- Slither, Echidna, Halmos, Medusa and a general mutation engine were not available/run.
- The 6,000-case comparative corpus is a deterministic reference model, not 6,000 EVM transactions.
- Novelty, legal freedom to operate, audit status and standard acceptance are not established.

