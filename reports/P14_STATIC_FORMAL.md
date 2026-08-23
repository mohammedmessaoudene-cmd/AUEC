# P14 — Static, formal and mutation review

PHASE: P14 static/formal  
OBJECTIVE: Record available mechanical checks and unavailable tools honestly.  
OBSERVED RESULTS: `forge lint` finds timestamp-comparison warnings only after safe-cast cleanup; `forge build --sizes` PASS; prohibited-surface scan PASS; independent Solidity reference differential and Python receipt ABI model PASS.  
TOOL_UNAVAILABLE: Slither, Echidna, Halmos, Medusa and solc-select are not installed on this host. No result is claimed for them.  
MUTATION: directed malicious mocks (lying venue, reentrant/false-return tokens and comparator semantic mutation) are exercised; a general mutation-testing engine was unavailable/not run.  
COMMITTEE OBJECTIONS: timestamp manipulation is only bounded by deadlines; no SMT/model-checker proof; optimizer-via-IR increases compiler reliance.  
GATE VERDICT: `P14_PASS` for available mandatory local checks with explicit tool gaps.  
REMAINING RISKS: no independent static analyzer or formal model checker result.  
NEXT PHASE: P15 demo/CI.

