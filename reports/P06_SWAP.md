# P06 — SWAP_EXACT_INPUT adapter

PHASE: P06 bounded swap  
OBJECTIVE: Approved two-asset venue, exact approval, freshness and measured bounds without route bytes.  
OBSERVED RESULTS: normal 100-in/200-out swap PASS; approval returns to zero; stale quote blocks; a venue lying by one output unit causes atomic revert and zero budget/recipient change; capped input escalates until principal approval.  
COMMANDS: focused swap tests and full suite.  
REGRESSION TESTS: stale quote, false actual, lower min-output rejection, adapter/registry drift.  
COMMITTEE OBJECTIONS: quote commitment is bound but the mock venue rate is not validated by a production oracle; MEV and real liquidity are outside this model.  
GATE VERDICT: `P06_PASS`  
REMAINING RISKS: deterministic mock only; no partial-fill production router.  
NEXT PHASE: P07 service escrow.

