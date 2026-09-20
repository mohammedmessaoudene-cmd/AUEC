# P07 — BUY_SERVICE_ESCROW

PHASE: P07 service escrow  
OBJECTIVE: Typed provider/service/evaluator IDs, funding, delivery, settlement and refund states without callbacks.  
OBSERVED RESULTS: typed purchase funds exact amount; unknown provider blocks; provider alone submits matching delivery; evaluator alone completes/rejects; expiry refunds kernel; provider callbacks do not exist.  
REGRESSION TESTS: normal funding/complete path and unknown provider. Lifecycle transition rules are executable in `ServiceEscrowAdapter`.  
COMMITTEE OBJECTIONS: the kernel receipt represents the funding effect, not a later amended terminal-settlement receipt; no dispute/arbitration model exists.  
GATE VERDICT: `P07_PASS`  
REMAINING RISKS: directed tests do not exhaust every escrow transition; evaluator remains trusted within the declared model.  
NEXT PHASE: P08 risk/verification.

