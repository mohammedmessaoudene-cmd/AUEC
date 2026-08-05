# Claims and limitations

## Permitted public claims

Historical official-protocol statements remain supported by sealed evidence
bundle `EB-2026-08-02`. Core-semantic statements are supported separately by
`CS-2026-08-04`.

1. A deterministic AUEC U0 reference runtime and multi-binding gateway were implemented.
2. The unchanged official MCP conformance runner recorded 39/39 active checks for `2025-11-25`, 22/22 active checks for `2026-07-28`, and 85/85 checks in the tested draft suite.
3. Four historical causal controls deliberately disabled distinct transport mechanisms. A current internal mechanism-level rerun is green at baseline, red under each mutation, and green after restoration; this rerun is not official conformance.
4. The delivered archive was built reproducibly, verified by manifest, and reconstructed byte-identically after clean extraction.
5. A2A official conformance was not achieved in EB-2026-08-02; the red evidence was retained.
6. NC-SEM-01 causally exercises the U0 host-operation allowlist.
7. NC-SEM-02 causally exercises the conservative U0 exclusion of claim-tagged outputs.
8. NC-SEM-03 causally exercises a pure authorization predicate against claim-to-authority escalation without executing an external effect.
9. Finite models cover 345 declared cases without a counterexample; no unbounded proof is claimed.

## Prohibited or unsupported claims

Do not state that AIEW is:

- an adopted international standard;
- officially endorsed by MCP, A2A, W3C, IETF, Linux Foundation or DARPA;
- production ready;
- externally audited;
- legally novel or patentable;
- interoperable across independent organizations;
- proven to reduce commercial cloud cost or tokens without quality loss;
- a secure replacement for operating-system isolation.

## Claim boundary

The technically differentiated proposal is the composition of:

- a provider- and transport-neutral declarative manifest;
- explicit capability, placement, data-classification and budget constraints;
- epistemic result types such as `fact`, `claim` and `hypothesis`;
- the invariant that an unverified claim is not authority;
- deterministic, chained execution receipts;
- an optional binding to existing protocols rather than a replacement for them.

The novelty of this composition remains a legal question requiring professional prior-art and claim analysis.
