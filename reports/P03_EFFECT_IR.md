# P03 — Closed Effect IR and schemas

> RESEARCH PROTOTYPE — NOT AUDITED — NO PRODUCTION FUNDS

PHASE: P03 Effect IR  
OBJECTIVE: Three closed request types, canonical domain-separated hashes, symbolic resources and strict JSON.  
HYPOTHESES: compile-time typed paths plus strict off-chain parsing remove AI-originated generic call authority.  
ASSUMPTIONS: schema `0.2` maps explicitly to Solidity schema integer `2`.

FILES CHANGED: `VAEKTypes.sol`, registry contracts, effect schema, bridge parser, source guard.  
COMMANDS: `forge fmt`; `forge build --sizes`; Python bridge tests; `python tools/check_prohibited_surfaces.py`.  
OBSERVED RESULTS: three distinct structs/submission functions; all hashes bind chain, kernel, header and payload; 9 bridge/source tests PASS; prohibited-surface scan PASS.  
FAILURES FOUND: initial legacy codegen produced `Stack too deep`; first IR build produced a 25,604-byte kernel over EIP-170.  
ROOT CAUSES: large typed static records and full-struct read APIs inflated legacy stack/code.  
CORRECTIONS: pinned `via_ir=true`, optimizer runs 1, removed three full-record getters in favor of a bounded authorization view; kernel now 24,108 bytes.  
REGRESSION TESTS: duplicate key, extra calldata, adapter address, float/scientific notation, overflow, unknown catalog ID and source patterns.  
COMMITTEE OBJECTIONS: IR compiler path adds trust; `bytes32` IDs are not interoperable semantics by themselves; kernel size margin is only 468 bytes.  
GATE VERDICT: `P03_PASS`  
REMAINING RISKS: schema validation is a hand-written reference bridge plus published schema, not a second production parser implementation.  
NEXT PHASE: P04 authority and attenuation.

