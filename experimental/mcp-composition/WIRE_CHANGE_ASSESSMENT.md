# Wire-change assessment

## Verdict

```text
INTERCEPTOR_PROFILE_CANDIDATE
```

The experiment found no need for a new generic MCP transport, signed
declaration format or audit-record chain.

The open SEP-2624 `ValidationResult` already provides:

- a boolean validation decision;
- severity and structured messages;
- an `info` object for profile-specific evidence.

The AUEC result fits that shape as a host-owned validator profile. The
experimental `info` data binds the decision to the action digest and effective
host-policy digest and records bounded reason codes. These profile semantics may
benefit from community agreement, but this experiment does not establish that a
new wire field is required.

SEP-3140-style authenticated declarations can supply integrity-protected risk
inputs. They do not grant authority, and the tests prove that a valid signature
cannot expand the host allow-list.

SEP-3004 can record the terminal allow/deny outcome after evaluation. Its
current `caller-governance` extension is sufficient for the bounded mapping
tested here. The record never participates in the authority predicate.

## Causal evidence

Six isolated source mutations each turned the security oracle red:

1. removed host-policy intersection;
2. accepted `claim` as authority;
3. ignored the consent digest;
4. treated an authenticated declaration as authority;
5. accepted an unknown critical field;
6. treated an audit record as permission.

Restoration returned every oracle to green. Property tests also covered
canonical key ordering, float rejection, action-digest binding, monotonic policy
narrowing, record tampering, 1,000 repeated decisions and concurrent execution.

## Limits

- All upstream inputs are open proposals, not final standards.
- Signature verification is represented by synthetic verification outcomes; no
  JWS/JWKS implementation is claimed.
- The canonical form is a deterministic local contract, not an RFC 8785
  implementation claim.
- No MCP wire transport or external server was exercised.
- This is not official MCP conformance, endorsement or production validation.

No SEP is submitted by this assessment.
