# MCP authority-delta composition experiment

Status: **experimental, draft-aligned, non-conformant**

This draft-only experiment tests a narrow composition:

1. SEP-3140-style authenticated declarations are decision inputs, not authority.
2. A host-owned validator computes requested, host-allowed and effective
   authority plus the requested-to-effective delta.
3. A separate action-boundary emitter verifies the action, principal, decision
   digest and actual outcome.
4. The boundary emits the current SEP-3004 record shape.

```bash
make demo-mcp-composition
python -m unittest discover -s experimental/mcp-composition/tests -v
python experimental/mcp-composition/sep3004_vectors.py
```

The implementation performs no network request and no consequential action.
It uses deterministic fixtures, fixed upstream commit pins, disposable source
mutants and a clean-room Python verifier.

## Non-negotiable authority boundary

```text
signature != authority
trust label != authority
annotation != authority
audit record != authority
claim != authority
```

Only host policy grants effective authority. The caller cannot set the
decision time, decision authority, boundary emitter, governed principal or
chain link.

## Evidence envelope

`auec.authority-decision-evidence.v0` commits to:

- `requested`, `hostAllowed`, `effective` and `delta`;
- policy id, version and digest;
- principal and exact action digest;
- declaration, epistemic, consent and ignored-audit digests;
- separate `decisionAuthorityId` and `recordEmitterId`;
- verdict and bounded reason codes.

The envelope is an internal evidence object, not a new MCP wire primitive.

## SEP-3004 boundary

The Python implementation reproduces the published two-extension KAT
`f733fed9cc757165f810b778e4baba1f51a45504988e937707aaab4361b2f064`
and all 23 published C-REC-1…7 vector expectations.

A concrete vector shows that current `caller-governance` records cannot commit
to different policy limits and deltas when their core fields are otherwise the
same. One optional `decision_evidence_hash` field is evaluated privately.
It remains unregistered and is rejected by the unchanged current verifier.

## Trust limit

A valid hash chain proves integrity after emission, not the truth or
independence of its producer. Outputs from this experiment are
`self_attested`; no external anchor or independent producer authentication is
claimed.

This is not official MCP conformance, acceptance, endorsement, production
hardening or external security validation. The pull request remains a draft.

AI assistance disclosure: OpenAI Codex assisted with implementation, tests,
analysis and drafting. Mohammed Messaoudene reviewed the executed evidence and
remains responsible for the contribution.
