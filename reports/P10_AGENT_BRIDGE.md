# P10 — Safe agent bridge

PHASE: P10 agent bridge  
OBJECTIVE: Make the AI output a strict document, never code or calldata.  
OBSERVED RESULTS: duplicate keys, all JSON numbers, floats, exponent strings, unknown fields, executable dispatch fields, overflow and unknown IDs reject; canonical output is sorted ASCII JSON; deterministic `MockAgent` requires no credential or live model.  
COMMANDS: `PYTHONPATH=agent python -m unittest discover -s agent/tests -v` => 9 PASS.  
COMMITTEE OBJECTIONS: hand-written validation must remain synchronized with JSON Schema and Solidity; no live LLM is necessary or used.  
GATE VERDICT: `P10_PASS`  
REMAINING RISKS: production relayer/signature transport excluded.  
NEXT PHASE: P11 adversarial.

