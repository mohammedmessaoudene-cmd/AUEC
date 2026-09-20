# P15 — CI and local demonstration

PHASE: P15 demo/CI  
OBJECTIVE: Stable pinned CI and actual local EVM lifecycle.  
OBSERVED RESULTS: local Anvil chain 31337 deployed `VAEKDemo` at `0x5FbDB2315678afecb367f032d93F642f64180aa3`; transfer, swap, escrow funding, three receipts and an unlisted-resource block completed; `VAEK_R2_ANVIL_DEMO=PASS`. Existing repository Python regression suite: 54 PASS.  
FILES CHANGED: read-only-permission Ubuntu workflow pinned to Foundry v1.7.1, Python 3.11 and PyCryptodome 3.23.0; local demo contract/script.  
COMMANDS: format, build/sizes, focused/full Foundry, two Python suites, source guard and Anvil demo.  
COMMITTEE OBJECTIONS: demo collapses principal/agent/verifier roles into one harness for reproducibility; the first GitHub-hosted run exposed the initially omitted Python Keccak dependency and therefore did not complete the post-verifier steps.  
GATE VERDICT: `P15_PASS` locally; remote CI status pending P16.  
REMAINING RISKS: public testnet intentionally not attempted; corrected remote workflow result pending.  
NEXT PHASE: P16 draft PR and exact handoff.
