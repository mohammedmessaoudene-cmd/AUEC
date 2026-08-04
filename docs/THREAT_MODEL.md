# Threat model

## Assets

- local files and credentials;
- host compute, energy and thermal capacity;
- manifest integrity;
- policy integrity;
- typed outputs and receipts;
- private data classifications;
- user consent and action authority.

## Adversaries

1. malicious cloud planner;
2. compromised provider account;
3. prompt-injected document treated as instructions;
4. malicious or buggy local operator implementation;
5. network attacker modifying requests or results;
6. tenant attempting cross-tenant replay;
7. verifier receiving a truncated or equivocated journal.

## Primary abuse cases

- capability escalation;
- path traversal and symlink escape;
- unbounded CPU, memory, disk, network or energy use;
- secret egress or inference leakage;
- classification downgrade;
- unverified claim authorizing a side effect;
- replay under changed inputs or policy;
- receipt-chain tampering;
- fingerprinting through over-detailed hardware capability disclosure;
- denial of service through manifests, graphs or output amplification.

## Required controls

- deny by default;
- canonical parsing with bounded depth and size;
- host-owned allowlists;
- consent tokens bound to exact action hashes;
- deterministic receipt and terminal digests;
- replay and idempotency controls;
- per-profile isolation and preemption;
- red-team and independent review before production.

## Residual risk

The reference U0 runtime demonstrates deterministic policy and receipt mechanisms. It does not prove full resistance to prompt injection, native sandbox escape, side channels, hardware faults, malicious compilers or compromised operating systems.
