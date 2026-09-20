# P01 — Reproduce and freeze BV-AIC R1 baseline

> RESEARCH PROTOTYPE — NOT AUDITED — NO PRODUCTION FUNDS

PHASE: P01 baseline reproduction  
INPUT COMMIT: `e1dda3b01c94d427cda75f10535d8fddf86c2c02`  
OBJECTIVE: Reproduce the frozen R1 evidence using the pinned real Foundry toolchain without modifying the seven historical artifacts.

## Hypotheses and exit conditions

- The packaged historical result is a claim until independently reproduced on this host.
- Exit requires format, compile/sizes, directed/fuzz, stateful invariants, full regression and local Anvil lifecycle.
- Fuzz and invariant settings must remain `5000` and `512 x depth 64`.

## Tool supply-chain record

- Official release: `foundry-rs/foundry` tag `v1.7.1`, published 2026-05-08.
- Windows archive: `foundry_v1.7.1_win32_amd64.zip`.
- Archive SHA-256 observed and matched to the release checksum: `6d41121b4bbb809845821c903619cfee75ed364f2bdc58a6787c9b0454114537`.
- Forge/Anvil/Cast commit: `4072e48705af9d93e3c0f6e29e93b5e9a40caed8`.
- Compiler selected by the project: Solidity `0.8.24`.

## Commands and observed results

| Command | Result |
|---|---|
| `forge fmt --check` | PASS; no files changed |
| `forge build --sizes` | PASS; compiler run successful |
| `forge test --match-contract BVAICAuthorityTest -vvv` | 20 passed, 0 failed, 0 skipped; four fuzz properties at 5,000 runs each |
| `forge test --match-contract BVAICInvariantTest -vvv` | 4 passed, 0 failed, 0 skipped; each 512 runs and 32,768 calls (depth 64) |
| `forge test -vvv` | 24 passed, 0 failed, 0 skipped |
| `bash ./scripts/anvil_deploy_smoke.sh` | `ANVIL_DEPLOY_SMOKE=PASS`, chain ID 31337 |

No failing seed was generated because no test failed. The full run generated different action distributions from the focused invariant run while maintaining all four properties, as expected for randomized campaigns.

## Size measurements

| Contract | Runtime bytes | Initcode bytes |
|---|---:|---:|
| `BVAICAuthority` | 7,354 | 7,567 |
| `MockERC20` | 1,106 | 1,572 |
| `MockFalseERC20` | 413 | 442 |
| `MockReentrantERC20` | 1,044 | 1,073 |
| `AuthorityHandler` | 1,606 | 11,547 |

All deployable production-path contracts are below the EVM runtime size limit in this baseline measurement.

## Preserved warnings

- Forge lint emitted six `block-timestamp` warnings in `BVAICAuthority.sol`. Timestamp manipulation is bounded but not eliminated by tests; R2 must retain explicit expiry semantics and treat timestamp dependence as a threat-model assumption.
- Foundry 1.7.1 emitted repeated warnings while probing optional invariant-target helper selectors that the test contract does not implement. The invariant campaign still executed the configured target contract and completed 4/4 PASS; the warnings are preserved rather than suppressed.
- The first signature-cache lookup reported a missing local cache directory. It had no compilation or test effect.

## Files changed

- No historical R1 source, test, configuration or frozen report was changed.
- New local Anvil logs exist under `bv-aic-r1/reports/anvil-smoke/` as reproduction evidence.
- `.gitignore` now excludes Foundry `cache/` and `out/` build products.
- This report and the tool record were added.

## Failures, causes and corrections

- Initial environment failure: Foundry/Anvil missing from PATH.
- Root cause: host toolchain not installed.
- Correction: downloaded exact official v1.7.1 Windows asset, verified SHA-256, extracted to a workspace-local tools directory, and reran every gate.
- No Solidity compatibility correction or test change was necessary.

## Committee objections

- EVM: R1 is transfer-specific and cannot establish adapter isolation for swaps or escrow.
- Formal methods: 24 passing tests and bounded invariant campaigns are not an exhaustive proof.
- AI safety: the test corpus assumes structured decision submission; it does not validate a strict AI JSON boundary.
- Red team: timestamp reliance and the invariant-target probe warnings deserve explicit R2 regression coverage.
- Interoperability: R1 uses address-oriented transfer semantics and does not establish portable symbolic resource IDs.

## Gate verdict

`P01_PASS`

REMAINING RISKS: bounded test scope; no multi-effect architecture; no independent receipt verifier; local-only reproduction.  
NEXT PHASE: P02 architecture variants, invariant mapping and freeze.

