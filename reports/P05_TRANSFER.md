# P05 — TRANSFER_ERC20 adapter

PHASE: P05 transfer  
OBJECTIVE: Kernel-selected, measured ERC-20 transfer with rollback.  
OBSERVED RESULTS: standard, no-return and 1% fee-on-transfer tokens are measured; false-return token reverts; allowance resets to zero; receipt records spent and received separately.  
FAILURES FOUND: inter-effect reentrancy was not blocked by per-record state alone during review.  
ROOT CAUSES: a malicious token could attempt another authorized execution ID while the first adapter was active.  
CORRECTIONS: global execution lock added around every adapter call; transaction rollback preserves lock/budget state on revert.  
REGRESSION TESTS: `test_INV031_ReentrantTokenCannotExecuteNestedEffect`, false/no-return/fee tests, replay and failed receipt tests.  
COMMITTEE OBJECTIONS: fee-on-transfer support records less received but may violate a user's business expectation; rebasing tokens remain unsupported/unmodeled.  
GATE VERDICT: `P05_PASS`  
REMAINING RISKS: token behavior beyond the declared mocks is not claimed safe.  
NEXT PHASE: P06 swap.

