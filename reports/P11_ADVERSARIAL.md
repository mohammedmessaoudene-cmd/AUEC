# P11 — Adversarial tournament

PHASE: P11 red team  
OBJECTIVE: Attack typed closure, authority freshness, adapters, accounting and receipts.  
OBSERVED RESULTS: tests cover hidden calldata/adapter, duplicate JSON, unknown resources, recipient substitution in comparator, cap widening, revocation, registry/adapter drift, quote staleness, false/no-return/fee/reentrant tokens, lying venue, replay, high/critical gates and receipt tampering.  
FAILURES FOUND: missing cross-effect execution lock; unsupported invariant cheatcode; code-size breach.  
CORRECTIONS: global lock; native target hook; API/code-size reduction. All have regression coverage.  
SECURITY FINDINGS: no unresolved critical/high within tested model; limitations are not findings closed by tests.  
COMMITTEE OBJECTIONS: malicious registry owner and malicious newly activated adapter remain governance trust; real oracle/DEX economics untested.  
GATE VERDICT: `P11_PASS`  
REMAINING RISKS: attack catalog is not one-test-per-line complete, notably rebasing, verifier collusion, DoS/storage exhaustion and proxy implementation drift.  
NEXT PHASE: P12 fuzz/invariants.

