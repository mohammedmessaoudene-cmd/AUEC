# VAEK R2 test results

> Evidence snapshot: 2026-08-23, local Windows host, Foundry v1.7.1 / Solidity 0.8.24.

| Gate | Result |
|---|---|
| `forge fmt --check` | PASS |
| `forge build --sizes` | PASS; all deployable runtime/initcode below limits |
| Full R2 Foundry suite | 36 PASS, 0 FAIL, 0 skipped |
| Core fuzz | 3 properties x 5,000 runs PASS |
| Stateful invariants | 6 properties x 512 campaigns x depth 64; 32,768 calls/property PASS |
| Agent bridge/source guard | 9 PASS |
| Independent receipt verifier | 4 PASS, including seven-field tamper corpus |
| Prohibited surface scan | PASS |
| Anvil three-effect demo | PASS, chain 31337 |
| Frozen R1 reproduction | 24 PASS (20 directed/fuzz + 4 invariants), Anvil PASS |
| Existing AUEC Python regression | 54 PASS |
| Synthetic benchmark corpus | 6 classes x 1,000 deterministic model cases generated |

Preserved non-fatal warnings: Foundry probes optional invariant configuration hooks that are absent; Forge lint flags timestamp comparisons used for mandate, quote, verification, timelock and escrow expiry. These warnings are not reclassified as security proof or ignored test failures.

