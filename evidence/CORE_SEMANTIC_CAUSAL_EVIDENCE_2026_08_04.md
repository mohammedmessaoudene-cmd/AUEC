# Core-semantic causal evidence

Evidence identifier: `CS-2026-08-04`.

Three safety mechanisms were tested with isolated single-source mutations in
disposable copies. Each mutation needle occurred exactly once, the targeted
line was observed during the focused test, the attack became possible, the
safety test became red, and the unmodified source remained green.

| Control | Baseline | Mutant | Restored | Scope |
|---|---|---|---|---|
| NC-SEM-01 | `E_OPERATION` | forbidden `hash.sha256` succeeds | `E_OPERATION` | U0 operation allowlist |
| NC-SEM-02 | `E_EPISTEMIC` | claim-tagged U0 output succeeds | `E_EPISTEMIC` | conservative U0 admission |
| NC-SEM-03 | claim denied authority | claim authorized | claim denied authority | pure decision predicate only |

The third control exercises `UniversalRuntime.evaluate_authority`. The method
evaluates epistemic status, independent validation, host effect policy, and
digest-bound consent. It does not dispatch or simulate the described action.

Finite models checked 345 declared cases: 64 capability-policy pairs, 96
planner capability additions, 64 placement-policy pairs, 25 budget pairs, and
96 authority states. No counterexample was found. This is exhaustive only for
the published finite domains, not an unbounded formal proof.

Raw diffs, red outputs, executed-line traces, restoration traces, the model
domain, and the machine-readable summary are stored in this evidence
directory.
