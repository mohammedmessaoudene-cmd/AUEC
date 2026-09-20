# VAEK R2 subtree rules

- Preserve closed typed effects; never add agent-controlled executable bytes, arbitrary selectors, target calls or adapter addresses.
- Do not use `delegatecall`.
- Keep Solidity 0.8.24 and Foundry v1.7.1 pinned unless an ADR and full regression justify a change.
- Never reduce fuzz below 5,000 or invariants below 512 campaigns / depth 64 to obtain PASS.
- Preserve failing evidence and add regression tests before fixes.
- No mainnet, real funds, release, tag or merge authorization exists.
- Label every result as a research prototype, not audited.

