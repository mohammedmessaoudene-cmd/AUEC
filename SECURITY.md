# Security policy

## Status

This is an engineering-alpha research artifact. It is not approved for
production processing of untrusted code or sensitive data.

## Future private reporting

After a repository exists, suspected vulnerabilities should be reported through
that repository's private security-advisory mechanism. No external contact
channel was opened by this prepublication campaign.

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
