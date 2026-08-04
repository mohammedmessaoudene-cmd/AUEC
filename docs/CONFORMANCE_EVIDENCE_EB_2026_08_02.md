# EB-2026-08-02 conformance evidence

## Immutable input

```text
File:    private-evidence-archive.zip
SHA-256: e8d07f3108bfaae73b165c663ba2993057d6fc844931f85ef74b3dd5b187c59c
Size:    125,135,828 bytes
```

## Official MCP results preserved in EB-2026-08-02

| Runner profile | Applicable success | Failure | Expected-failure file |
|---|---:|---:|---|
| `2025-11-25`, active | 39 | 0 | none |
| `2026-07-28`, active | 22 | 0 | none |
| `2026-07-28`, draft | 85 | 0 | none |

The SUT was not mutated during the runs and produced zero stderr bytes according to the machine-readable summary.

## Causal negative controls

Four independent mutations were introduced one at a time. Each made the official runner red; restoration returned it to green:

1. first-tool ordering;
2. HTTP optional-whitespace handling;
3. `InputRequiredResult` handling;
4. advertised subscription behavior.

## A2A evidence

The unchanged upstream TCK remained red:

```text
JSON-RPC:  79 pass / 1 fail / 185 skip
HTTP+JSON: 76 pass / 2 fail / 187 skip
```

This release does not represent a patched TCK as official.

## Interpretation

EB-2026-08-02 supports publication as an engineering evidence checkpoint. It does not establish independent interoperability, production security or standards adoption.
