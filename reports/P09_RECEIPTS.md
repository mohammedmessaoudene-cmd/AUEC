# P09 — Requested / authorized / executed receipts

PHASE: P09 receipts  
OBJECTIVE: Bind three semantic stages and independently reject tampering.  
OBSERVED RESULTS: compact receipt stored only after success; adapter failure reverts receipt and budget; typed actuals are measured; Python Keccak/ABI verifier reproduces golden Solidity hash `0xc46a24e90343c37e36740d80a1e67b0fa733a207f6b2acd42dce0d1a5cd11340`; seven tamper mutations and unknown fields are rejected.  
COMMANDS: 4 verifier tests plus Solidity cross-language golden vector.  
COMMITTEE OBJECTIONS: the golden vector proves encoding agreement, while live log extraction into canonical JSON is still demo tooling rather than a production indexer.  
GATE VERDICT: `P09_PASS`  
REMAINING RISKS: receipt privacy and long-term log/index availability not evaluated.  
NEXT PHASE: P10 bridge.

