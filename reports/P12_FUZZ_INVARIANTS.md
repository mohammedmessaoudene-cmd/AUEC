# P12 — Fuzz, stateful invariants and differential model

PHASE: P12 fuzz/invariants  
OBJECTIVE: Execute mandatory volume without reduced settings.  
OBSERVED RESULTS: three core fuzz properties each PASS at 5,000 runs; six stateful invariants PASS at 512 campaigns, depth 64, 32,768 calls each. Three cover transfer accounting and three generate mixed transfer/swap/escrow actions with shared budgets and two-token conservation. Transfer attenuation matches independent `ReferenceModel`.  
FAILURES FOUND: first invariant setup used unknown cheatcode selector `0x147039f6`.  
ROOT CAUSES: the direct `targetContract(address)` interface did not match Foundry 1.7.1.  
CORRECTIONS: replaced it with the native `targetContracts()` configuration hook used by frozen R1.  
REGRESSION TESTS: corrected suite rerun at full volume and included in full regression.  
COMMITTEE OBJECTIONS: mixed campaigns cover declared mocks and funding effects, not every escrow terminal transition or production venue; bounded campaigns are not proof.  
GATE VERDICT: `P12_PASS`  
REMAINING RISKS: no model-checker proof and no invariant mutation engine.  
NEXT PHASE: P13 benchmark.
