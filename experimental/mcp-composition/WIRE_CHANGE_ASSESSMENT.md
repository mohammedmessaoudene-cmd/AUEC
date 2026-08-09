# Caller-governance field assessment

## Verdict

```text
CALLER_GOVERNANCE_OPTIONAL_FIELDS_CANDIDATE
UNREGISTERED_PRIVATE_CANDIDATE
NO_NEW_RECORD_CORE
NO_NEW_CANONICALIZATION
```

No MCP transport, signature format, receipt primitive, chain construction or
new extension type is proposed.

## Concrete loss vector

`CG-DELTA-LOSS-01` evaluates the same requested action under two host policy
limits. Both decisions allow the action, but one preserves a ten-node budget
and the other narrows it to five nodes. Their AUEC evidence envelopes therefore
have different policy digests and requested-to-effective deltas.

Mapped with the currently registered `caller-governance` fields, the two
records are byte-identical and have the same `event_hash`. The current
registration has no field that commits to the decision basis.

Adding one experimental field makes the records distinct:

| Candidate field | Type | Meaning |
| --- | --- | --- |
| `decision_evidence_hash` | string | Algorithm-qualified digest of a separately canonicalized authority-decision evidence envelope |

The unchanged current-registry verifier correctly rejects that field before
registration. The candidate is therefore not described as conformant.

## Why one field is sufficient

The separate evidence envelope commits to:

- requested, host-allowed and effective authority;
- the exact delta;
- policy id, version and digest;
- principal and action digest;
- declaration, epistemic, consent and ignored-audit input digests;
- decision authority, expected boundary emitter, verdict and reason codes.

Repeating those fields in `caller-governance` would create two representations
and two drift surfaces. One opaque commitment preserves the existing record
construction and lets an exported envelope be verified out of band.

## Evidence boundary

The hash chain establishes post-emission integrity and linkage. It does not
establish that a self-emitted decision was true or independently observed.
The verifier therefore reports `self_attested`, `authenticated`, or
`externally_anchored`; this experiment establishes only `self_attested`.

Public traceability now includes the AUEC result comment on SEP-3004
([issuecomment-5228991875](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3004#issuecomment-5228991875))
and the targeted external vector PR
([tersignhq/evidence-record-conformance#5](https://github.com/tersignhq/evidence-record-conformance/pull/5)).
Neither is MCP acceptance, field registration, sponsorship, independent
validation or a production-readiness claim.
