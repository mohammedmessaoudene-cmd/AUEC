# Security policy

## Status

AUEC is an engineering-alpha research artifact. It is not approved for
production processing of untrusted code or sensitive data.

## Private vulnerability reporting

Report suspected vulnerabilities through GitHub private vulnerability reporting
on this repository's **Security → Advisories → Report a vulnerability** page.
Do not disclose an uncoordinated vulnerability in a public issue.

Private reporting is a communication channel, not a promise of a response time,
a CVE, a bounty, certification or production support.

## Enforced base-profile boundaries

The reference profile aims to preserve explicit host authority, an operation
allowlist, no classification downgrade, no secret egress, no unverified claim
becoming authority, deterministic receipt-chain verification, and bounded
manifest/node/output/wall-time budgets.

## Not established

Production authentication, multi-tenant isolation, hostile native-code
execution, an audited WASI 0.3 host, distributed idempotency, hardware
attestation, formal verification of the entire runtime, and external penetration
testing remain outside the evidence.
