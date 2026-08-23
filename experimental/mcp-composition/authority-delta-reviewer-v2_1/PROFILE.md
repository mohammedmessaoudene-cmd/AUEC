# Narrowed structured-decision profile

Profile identifier: `auec-authority-delta-decision-v2_1`

Canonicalization identifier: `auec-authority-delta-c14n-v2_1`

The accepted record has exactly two fields:

```json
{
  "decision": {},
  "decisionEvidence": {
    "form": "structured+digest",
    "algorithm": "sha-256",
    "canonicalization": "auec-authority-delta-c14n-v2_1",
    "digest": "sha256:<64 lowercase hexadecimal characters>"
  }
}
```

The digest is computed over the canonical UTF-8 bytes of `decision`. Object
keys use unsigned UTF-8 byte order. Strings must be NFC and contain no lone
surrogates. Duplicate JSON keys, floating-point values, unsafe integers,
overlong integer tokens, excessive depth/nodes/string bytes, and nonconforming
schema fields are rejected before acceptance.

This is an external profile for a bounded representation experiment. It is not
an MCP schema, protocol extension, conformance designation, or implementation
requirement.
