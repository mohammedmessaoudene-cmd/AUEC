# Security findings

## Resolved during closed loop

### F-001 — Cross-effect reentrancy gap — HIGH — RESOLVED

Per-effect state alone did not stop a malicious token from attempting a second, different authorized execution ID during an adapter call. A global execution lock was added; the regression proves the nested call fails while the outer transfer and later independent execution remain correct.

### F-002 — EIP-170 kernel breach — HIGH deployment gate — RESOLVED WITH RESIDUAL RISK

The first IR build was 25,604 runtime bytes. Full-record getters were removed and optimizer settings documented. Current runtime is 24,108 bytes, 468 below the limit. Residual maintainability risk remains MEDIUM.

### F-003 — Immediate adapter replacement — HIGH governance boundary — RESOLVED

Initial registry code allowed immediate replacement. Replacement now requires schedule plus one-hour activation delay, emits version/code hash, and invalidates pending authorizations. Emergency disable remains immediate and fail-closed.

### F-004 — Invariant runner API mismatch — TEST INFRASTRUCTURE — RESOLVED

The first R2 invariant setup failed on an unknown cheatcode. It now uses Foundry's native `targetContracts()` hook and passes full campaigns.

## Open bounded risks

- MEDIUM: single verifier address/method commitment; quorum independence is not demonstrated.
- MEDIUM: mock venue plus min-output bounds do not model oracle manipulation, MEV or production liquidity.
- MEDIUM: the kernel has only 468 runtime bytes of size margin.
- MEDIUM: registry owner and principal keys are trusted administrative boundaries.
- LOW/MEDIUM: timestamp manipulation is bounded by expiries but not eliminated.
- LOW/MEDIUM: escrow terminal settlement is separate from the initial funding receipt.

No unresolved critical/high finding was reproduced inside the declared mock/local model. This is not an audit conclusion for production integrations.

