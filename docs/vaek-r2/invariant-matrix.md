# Invariant-to-component and test matrix

| Invariants | Enforcement component | Primary test strategy |
|---|---|---|
| INV-001..005 | typed interfaces, bridge, registries | source guard, schema rejection, dispatch tests |
| INV-010..015 | kernel attenuation functions | boundary fuzz, identity-substitution directed tests, reference model |
| INV-020..026 | mandate/risk/verification gates | stateful revocation/budget/version tests, risk matrix |
| INV-030..036 | kernel lock + typed adapters | replay/reentrancy/malicious token/venue tests |
| INV-040..045 | receipt store + verifier | success/revert/tamper differential corpus |
| INV-050..052 | lifecycle + version commitments | mixed-action stateful invariants |

Every property is bounded by the declared token, venue and escrow mocks. Passing it does not prove arbitrary production integrations safe.

