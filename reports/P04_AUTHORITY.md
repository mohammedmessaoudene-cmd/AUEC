# P04 — Attenuation and execution-time authority

PHASE: P04 authority  
OBJECTIVE: Enforce `authorized <= requested`, current mandate/budget/version checks and exact approval binding.  
FILES CHANGED: kernel, risk engine, reference model, unit/fuzz tests.  
COMMANDS: focused 5,000-run fuzz properties and full Foundry suite.  
OBSERVED RESULTS: transfer/service caps attenuate amounts; swap narrowing cannot lower `minOutput` and starts escalated when capped; revocation, registry change, adapter change, stale deadlines and aggregate budget are rechecked before effects.  
FAILURES FOUND: automatic swap proportional narrowing was semantically ambiguous.  
CORRECTIONS: ADR-002 freezes equal/stricter min-output and principal-bound explicit approval.  
REGRESSION TESTS: attenuation differential against `ReferenceModel`, identity/resource substitution, stale authority, approval hash and budget rollback.  
COMMITTEE OBJECTIONS: global resource version invalidation is safe but harms liveness; policy fields are compact and not a production mandate language.  
GATE VERDICT: `P04_PASS`  
REMAINING RISKS: reference model covers transfer attenuation/risk, not a full three-effect state machine.  
NEXT PHASE: P05 transfer.

