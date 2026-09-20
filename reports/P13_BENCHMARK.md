# P13 — VAEK versus fair policy wallet

PHASE: P13 differential benchmark  
OBJECTIVE: Avoid a strawman and identify both assurance gain and cost.  
OBSERVED RESULTS: comparator enforces agent, target+selector rules, exact ERC-20 recipient/amount parser, aggregate cap, expiry and replay. It blocks substitution/over-cap. When a `multicall(address,bytes)` selector is allowed, nested target/selector remains uninspected. The same allowed target/selector also changed semantic behavior without a policy change. Six comparator tests PASS. A deterministic 6 x 1,000 reference corpus records its assumptions and distinguishes on-chain directed evidence from synthetic counts.  
MEASURED: generic wallet runtime 2,256 bytes; VAEK kernel 24,108 bytes plus adapters (1,007 / 1,617 / 2,622 bytes). Representative generic parsed transfer test gas 98,013; VAEK low transfer lifecycle test gas 877,096 (test-harness totals, not transaction-only production gas).  
INTERPRETATION: VAEK demonstrates a concrete closed-language assurance advantage for nested calls, but with roughly an order-of-magnitude core bytecode cost, lower composability and adapter trust.  
COMMITTEE OBJECTIONS: the 6,000-case corpus is a deterministic model, not 6,000 EVM transactions; gas comparison includes different setup/lifecycle work.  
GATE VERDICT: `P13_PASS` for hypothesis survival, not superiority proof.  
REMAINING RISKS: quantitative benchmark is preliminary and insufficient for publication claims.  
NEXT PHASE: P14 static/formal.
