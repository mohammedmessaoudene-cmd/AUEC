# Draft SEP: Verifiable Hybrid Execution Contract Extension

**Status:** pre-submission discussion draft  
**Track:** Extensions  
**Authors:** Mohammed Messaoudene  
**Extension identifier:** `REPLACE_WITH_CONTROLLED_REVERSE_DNS_ID`  

## Abstract

This proposal defines an optional MCP extension for transporting and verifying bounded hybrid-execution contracts. It adds a provider-neutral manifest, data and epistemic annotations, host-enforced placement and budget constraints, and deterministic chained receipts. The extension does not replace MCP tools or transports and does not grant remote code execution authority.

## Motivation

MCP standardizes access to tools and context. Implementations may log or audit tool calls, but the base protocol does not define a portable execution contract that simultaneously binds host policy, placement, data classification, epistemic status, deterministic outputs and tamper-evident, replay-checkable receipts.

The extension addresses four use cases:

1. local preprocessing of private data before cloud reasoning;
2. deterministic delegation with explicit resource and egress limits;
3. verifiable result provenance across heterogeneous runtimes;
4. prevention of an unverified model claim becoming action authority.

## Non-goals

- defining a new transport;
- replacing WebAssembly or WASI;
- standardizing model weights or split inference;
- making arbitrary shell or native execution safe;
- declaring a production security profile.

## Negotiation

Clients and servers advertise support under MCP's extension negotiation mechanism. The value is a configuration object containing supported AUEC versions and profiles.

```json
{
  "extensions": {
    "REPLACE_WITH_CONTROLLED_REVERSE_DNS_ID": {
      "auecVersions": ["0.1"],
      "profiles": ["U0-pure"],
      "receiptAlgorithms": ["sha-256-chain-v1"]
    }
  }
}
```

Absence of the identifier means the peer MUST NOT assume support.

## Tool metadata

A tool accepting AUEC manifests SHOULD advertise the profile and media type in extension metadata. The manifest executor MUST remain strict; conformance fixtures MUST NOT be satisfied by accepting an empty or malformed manifest.

## Result metadata

A successful execution returns structured content containing:

- AUEC status;
- manifest digest;
- typed exports;
- receipt array or a receipt reference;
- terminal digest;
- optional host-attestation reference.

The MCP transport result and the AUEC execution status are distinct. A successful MCP exchange may carry an AUEC rejection.

## Epistemic annotations

The extension defines `fact`, `claim`, `hypothesis`, `artifact` and `secret`. An unverified `claim` MUST NOT be interpreted as authority for a side effect. A host may require a separate verification or consent token bound to the exact action digest.

## Security considerations

The host is the authority boundary. Manifest content cannot widen policy. Implementations must enforce bounded parsing, deny-by-default capabilities, no classification downgrade, secret egress prohibition, replay binding and receipt-chain verification.

## Compatibility

The extension is optional and independently versioned. Peers that do not negotiate it continue to use ordinary MCP behavior. AUEC semantics are transport-neutral and must not be silently changed by the binding.

## Conformance

A conformance suite should include:

- positive U0 vectors;
- malformed and oversized manifests;
- classification and egress violations;
- claim-as-authority negative tests;
- replay and receipt tampering;
- unknown profile and extension behavior;
- causal negative controls.

## Open questions

- controlled extension identifier and repository;
- receipt storage versus inline transport;
- signature and attestation profiles;
- privacy-preserving capability disclosure;
- standard error mapping;
- relationship to MCP tasks and long-running operations.
