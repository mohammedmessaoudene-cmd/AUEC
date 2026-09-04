# Draft-overlap matrix

Rechecked on 2026-08-08. All three proposals are open and unstable.

| Draft | Reused conceptually | AUEC boundary | What this spike does not duplicate |
| --- | --- | --- | --- |
| SEP-2624 at `3a276064...` | Strictly non-mutating validator and structured `ValidationResult` | `valid` is a host decision; interceptor discovery or transport does not grant authority | No new interceptor transport, discovery method or chain executor |
| SEP-3004 at `377f8d26...` | Post-decision core record plus `caller-governance` extension and deterministic digest | The record reflects what happened; its presence never permits an action | No second generic audit chain or competing core record |
| SEP-3140 at `8fd469a5...` | Authenticated declaration and closed risk labels as inputs | Signing proves provenance/integrity, not local permission or publisher honesty | No JWS/JWKS, publisher discovery, declaration manifest or competing labels |

Related boundaries:

- SEP-1913 and Tool Annotations provide descriptive trust/sensitivity
  vocabulary, not authority.
- SEP-2809 covers server admission, not the final per-action host decision.
- closed SEP-1766 treated digests as integrity inputs, not authorization.
- Discussion #2462 concerns MCP server discovery via `mcp://`; an earlier
  pointer to receipt work there was erroneous and has been removed.
- SEP-3004's registered `caller-governance` extension is the only candidate
  record home evaluated here. No parallel receipt or chain is proposed.

The Python verifier is independently implemented from SEP-3004's normative
text. The 23 Apache-2.0 conformance fixture definitions are adapted with
attribution so that the independent implementation can be scored against the
published C-REC-1…7 matrix.
