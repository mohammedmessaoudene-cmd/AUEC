# VAEK R2 Assumption Register

> RESEARCH PROTOTYPE — NOT AUDITED — NO PRODUCTION FUNDS

| ID | Classification | Assumption or decision | Evidence / disposition |
|---|---|---|---|
| A-001 | OBSERVED | R2 starts from `bv-aic-r1-ci-20260822` commit `e1dda3b01c94d427cda75f10535d8fddf86c2c02`. | Local clone and `git ls-remote` agree. |
| A-002 | OBSERVED | The seven core R1 artifacts match the handoff Git blob IDs. | `git hash-object` reproduced every value in `references/BASELINE_PROVENANCE.md`. |
| A-003 | ASSUMED | Solidity 0.8.24 and Foundry 1.7.1 remain the reproduction toolchain. | Required by the frozen baseline; installation and live reproduction occur in P01. |
| A-004 | OBSERVED | Public Shido/Zenith/Sepolia scripts are historical experiments, not mandatory R2 evidence. | They are absent from the packaged baseline subset; handoff explicitly excludes faucet/RPC experiments from semantic evidence. |
| A-005 | ASSUMED | R2 will live in an isolated `vaek-r2/` Foundry project while preserving `bv-aic-r1/` unchanged. | Reversible layout choice to prevent collision with the repository's existing Python/AUEC work. Architecture is frozen in P02. |
| A-006 | ASSUMED | Deterministic mocks are sufficient for the R2 swap and service effect experiment. | Permitted by the charter; no real funds or mainnet integrations are authorized. |
| A-007 | OBSERVED | GitHub account access is available for the target repository. | `gh auth status` and repository read operations succeeded. No remote write has yet occurred. |
| A-008 | ASSUMED | A draft PR may be visible publicly, but it is not an official publication or release. | Direct user request requires warning before final publication; handoff permits a draft PR and prohibits merge/release/tag. |

