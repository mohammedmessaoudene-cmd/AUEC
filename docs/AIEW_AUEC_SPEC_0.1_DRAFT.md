# AIEW Universal Execution Contract (AUEC) 0.1

**Status:** public pre-standard draft. Normative keywords MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are used in their RFC 2119 sense.

## 1. Scope

AUEC defines a transport-neutral manifest by which a remote planner proposes bounded work to a sovereign host. The host remains the final authority over capabilities, data egress, placement and budgets. AUEC does not define a new network transport or virtual machine.

## 2. Design principles

1. **Host sovereignty:** the remote planner proposes; the host admits, restricts or rejects.
2. **No implicit authority:** a manifest receives only explicitly granted capabilities.
3. **Transport neutrality:** MCP, A2A, HTTP and offline files are bindings.
4. **Determinism at U0:** the base profile contains only pure deterministic operations.
5. **Epistemic separation:** `fact`, `claim`, `hypothesis`, `artifact` and `secret` are not interchangeable.
6. **No claim-as-authority:** an unverified `claim` MUST NOT authorize a side effect.
7. **Verifiable execution:** accepted nodes produce deterministic chained receipts.
8. **Data minimization:** classification and egress rules are hard constraints, not optimization weights.

## 3. Core manifest

A manifest contains:

```json
{
  "auecVersion": "0.1",
  "manifestId": "example",
  "profile": "U0-pure",
  "resources": {},
  "budgets": {
    "maxNodes": 16,
    "maxOutputBytes": 65536,
    "maxWallMs": 5000
  },
  "nodes": []
}
```

Unknown normative fields MUST be rejected unless negotiated by an extension profile.

## 4. Data classifications

The ordered classifications are:

```text
public < internal < confidential < secret
```

A node MUST NOT declare an output classification lower than any of its inputs. The host MUST reject export above its configured maximum. `secret` output MUST NOT leave the host in the base profile.

## 5. Epistemic kinds

- `fact`: deterministic and verified output.
- `claim`: probabilistic assertion requiring an explicit verification transition.
- `hypothesis`: candidate explanation not asserted as true.
- `artifact`: content-addressed output.
- `secret`: output explicitly forbidden from egress.

The U0 profile emits only `fact` or `artifact`. Later profiles may introduce claims, but MUST preserve the rule `claim != authority`.

## 6. Placement

A node declares allowed and preferred placements from `local`, `edge` and `cloud`. The host intersects these with policy. No effective placement means rejection. A preferred placement is advisory; privacy and capability constraints are mandatory.

## 7. Budgets

The manifest requests bounded resources. The host computes the minimum of requested and local policy limits. U0 defines at least:

- maximum nodes;
- maximum canonical output bytes;
- maximum wall time;
- maximum manifest bytes.

A budget violation MUST reject or abort execution with a stable error code.

## 8. U0 operations

The reference U0 registry includes deterministic operations such as identity, SHA-256, JSON projection, safe-integer sum, concatenation, length, literal redaction, literal search and deduplication. Hosts MAY support a subset but MUST advertise it explicitly.

## 9. Receipts

For each executed node, the host produces a receipt binding:

- manifest digest and identifier;
- sequence and node identifier;
- operation and effect;
- selected placement;
- canonical input digest;
- typed output digest;
- previous receipt digest.

The receipt digest is computed over the canonical receipt body. The terminal object binds the final receipt digest and export digest. Any historical modification MUST break verification.

## 10. Host policy

Host policy is independent of manifest content and MUST NOT be widened by data read during execution. It controls:

- profiles, operations and effects;
- placements;
- export classifications;
- claim export;
- budgets;
- implementation-specific capability grants.

## 11. Bindings

A binding transports the manifest and result without changing AUEC semantics. Binding-specific success MUST NOT imply that the manifest was accepted; the structured AUEC status remains authoritative.

## 12. Security considerations

Implementations must defend against duplicate JSON keys, non-finite numbers, unpaired Unicode surrogates, unsafe integers, graph cycles, reference confusion, classification downgrade, output amplification and receipt-chain substitution.

The base profile is not a production sandbox. Native-code, network, filesystem, model and device profiles require separate capability and isolation specifications.
