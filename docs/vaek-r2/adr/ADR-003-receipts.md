# ADR-003 — Compact stored receipt plus canonical document

Status: accepted for R2.

Events-only are cheap but force independent verifiers to trust complete log availability. Full documents on-chain are expensive. R2 stores a compact canonical receipt summary and emits typed actuals. The external verifier recomputes hashes from public fields and needs no private database.

