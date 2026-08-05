# Security and falsification report — 0.36.0-prestandard

## Result

The U0 host-operation allowlist and epistemic-admission guards are causally
exercised. A separate pure authorization predicate is also mutation-tested
against claim-to-authority escalation.

## Evidence classes

1. Historical official MCP runner counts remain attributed to sealed evidence
   bundle `EB-2026-08-02`.
2. Four transport-mechanism controls were rerun internally and returned red
   under mutation and green after restoration. This rerun is not relabeled as
   official conformance.
3. Three AUEC core-semantic controls use exact single mutations, direct attack
   observations, focused red tests, executed-line traces, and green
   restorations.
4. Finite models report all 345 checked cases and zero counterexamples.

## Boundaries

- U0 excludes claims and hypotheses from executable outputs; it does not
  implement a production consequential-effect profile.
- The authorization predicate returns a decision and performs no effect.
- A successful finite model is not an unbounded proof.
- Receipt integrity does not establish semantic truth or platform integrity.
- No external red-team, independent implementation, provider pilot, or
  production sandbox is claimed.
