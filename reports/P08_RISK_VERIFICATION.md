# P08 — Risk and verification

PHASE: P08 risk/verification  
OBJECTIVE: Deterministic monotone tiers, exact verification and human/timelock escalation.  
OBSERVED RESULTS: swap/service floor at MEDIUM; thresholds raise to HIGH/CRITICAL; model concern only raises; MEDIUM requires verifier; HIGH requires exact principal hash; CRITICAL also waits one hour. Adapter replacement waits one hour and invalidates old pending authorization.  
REGRESSION TESTS: 5,000-run concern monotonicity, compromised verifier boundaries through hard checks, high/critical approvals, adapter timelock.  
COMMITTEE OBJECTIONS: one verifier address and a method commitment demonstrate binding, not independent quorum or verifier diversity.  
GATE VERDICT: `P08_PASS`  
REMAINING RISKS: quorum/family independence is not implemented; risk thresholds are mandate inputs rather than economically calibrated constants.  
NEXT PHASE: P09 receipts.

