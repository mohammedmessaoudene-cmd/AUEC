# P02 — Architecture freeze

> RESEARCH PROTOTYPE — NOT AUDITED — NO PRODUCTION FUNDS

PHASE: P02 architecture freeze  
INPUT COMMIT: base `e1dda3b01c94d427cda75f10535d8fddf86c2c02` plus P00/P01 reports  
OBJECTIVE: Select a falsifiable architecture before implementation.

HYPOTHESES: typed adapter isolation can share a stable authority state machine across three effects; the added complexity must later beat a fair policy wallet on at least one assurance dimension.  
ASSUMPTIONS: deterministic mocks are the declared external-system model; registry governance is a privileged R2 admin; no proxy upgradeability.

FILES CHANGED: `docs/vaek-r2/architecture.md`, three ADRs, invariant matrix, this report.  
COMMANDS: full handoff/spec review; source and workflow inventory; architecture comparison recorded in ADR-001.  
OBSERVED RESULTS: all three variants can preserve typed closure, but variant B best exposes the adapter boundary without splitting replay/budget accounting.  
FAILURES FOUND: automatic proportional swap attenuation is ambiguous.  
ROOT CAUSES: max-input and min-output are coupled by market price, so numeric reduction alone does not define semantic narrowing.  
CORRECTIONS: ADR-002 requires unchanged/stricter min-output and explicit escalation when infeasible.  
REGRESSION TESTS: P04/P06 must reject venue substitution, lowered min-output and principal approval hash reuse.

## Cross-committee objections

- EVM: extra calls and stored receipts increase gas and bytecode.
- Distributed systems: a global registry version creates safe but coarse invalidation and liveness loss.
- Cryptography: canonical encoding must include every semantic and domain field; missing one is fatal.
- Formal methods: a common kernel reduces state duplication but still needs cross-effect budget invariants.
- AI safety: bridge schema closure is required; Solidity typing alone does not secure JSON coercion.
- DeFi/MEV: a mock two-asset venue cannot establish production DEX safety.
- Capability security: privileged registry owner remains a concentrated authority.
- Red team: a malicious approved adapter can still lie unless state deltas are independently measured.
- DevSecOps: pinned compiler/tooling and prohibited-surface scans must be CI gates.
- Standards: symbolic IDs need an explicit catalog; no interoperability claim follows from `bytes32` alone.
- Product: three typed integrations impose real extension cost and reduced composability.
- Contradiction board: code-bound adapters strengthen dispatch assurance while moving trust into adapter review; benchmark must report both.

COMMIT: pending phase commit.  
GATE VERDICT: `P02_PASS`  
REMAINING RISKS: registry admin compromise, adapter concentration, gas overhead, mock-only external economics.  
NEXT PHASE: P03 closed types, hashes, strict schemas and prohibited-surface guard.

